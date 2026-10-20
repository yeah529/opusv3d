"""Check a composed film for the failures that matter in a nested-world film.

usage: python seamcheck.py <project_dir> [video.mp4] [--draft]
checks (FAIL -> exit code 1):
  frames    the video has exactly dur * fps frames
  seams     at every push_in / pull_out switch, no frame-to-frame jump bigger than the motion around it
            (jump <= max(2.5 x local median, local median + 0.012); differences are mean |a-b| of 320x180 luma)
  glitch    no single odd frame anywhere: second difference e = |g[f] - (g[f-1] + g[f+1]) / 2| fails when it is
            > max(4 x local median, local median + 0.025) AND > 1.5 x the motion just before or after
            (min(d[f-1], d[f+2])), so a fast but smooth camera move in a still scene passes. Skipped: frames next to a cut and inside
            iris / lens / breach / fade windows (a moving wipe edge is a large second difference by design;
            review those windows on the contact sheet)
  anchors   matched transitions keep A's and B's anchor within 0.01 (NDC) of each other
  black     no frame with mean luma < 0.03 outside fade_in / fade_out / allow_dark
  frozen    no run of 8+ identical frames outside allow_dark (warning only)
  anchor_missing  an unmatched iris / lens / breach whose anchor object does not exist uses the frame centre
            (warning only; a matched one is an error at render time)
writes out/<q>/seamcheck.json
"""
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'v3d'))
from timeline import Timeline, TimelineError  # noqa: E402

W, H = 320, 180
WARN_ONLY = ('frozen', 'anchor_missing')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        sys.exit('usage: python seamcheck.py <project_dir> [video.mp4] [--draft]')
    pdir = os.path.abspath(args[0])
    q = 'draft' if '--draft' in sys.argv else 'final'
    try:
        tl = Timeline(os.path.join(pdir, 'timeline.json'))
    except TimelineError as e:
        sys.exit(f'seamcheck: timeline.json: {e}')
    video = os.path.abspath(args[1]) if len(args) > 1 else os.path.join(pdir, 'out', q, 'video.mp4')
    if not os.path.exists(video):
        sys.exit(f'seamcheck: {video} not found')
    r = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', video, '-vf', f'scale={W}:{H}', '-f', 'rawvideo',
                        '-pix_fmt', 'gray', '-'], capture_output=True)
    if r.returncode != 0 or not r.stdout:
        sys.exit(f'seamcheck: ffmpeg cannot read {video}: {r.stderr.decode(errors="replace").strip()[-300:]}')
    raw = r.stdout
    g = np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32) / 255
    n = len(g)
    d = np.zeros(n, np.float32)
    d[1:] = np.abs(g[1:] - g[:-1]).mean(axis=(1, 2))
    luma = g.mean(axis=(1, 2))
    res = dict(video=video, frames=n, expected=tl.frames, checks=[])
    fails = 0

    def add(kind, ok, **kw):
        nonlocal fails
        res['checks'].append(dict(kind=kind, ok=bool(ok), **kw))
        if not ok and kind not in WARN_ONLY:
            fails += 1

    add('frames', n == tl.frames, got=n, want=tl.frames)
    F = tl.F

    def local(k, excl):
        idx = [i for i in range(max(1, k - 20), min(n, k + 21)) if not (excl[0] <= i <= excl[1])]
        return float(np.median(d[idx])) if idx else 0.0

    for tr in tl.transitions:
        if tr.kind == 'world':
            k = F(tr.t)
            lo, hi = (k - tr.seam, k) if tr.type == 'push_in' else (k, k + tr.seam)
            ref = local(k, (lo - 1, hi + 1))
            seg = d[max(1, lo):min(n, hi + 1)]
            jump = float(seg.max()) if len(seg) else 0.0
            lim = max(2.5 * ref, ref + 0.012)
            add('seam', jump <= lim, at=round(tr.t, 3), type=tr.type, shots=f'{tr.a.id}>{tr.b.id}', jump=round(jump, 4),
                local=round(ref, 4), limit=round(lim, 4))
    e = np.zeros(n, np.float32)
    if n > 2:
        e[1:-1] = np.abs(g[1:-1] - (g[:-2] + g[2:]) / 2).mean(axis=(1, 2))
    cuts = {F(tr.t) + k for tr in tl.transitions if tr.type == 'cut' for k in (-1, 0, 1)}
    for tr in tl.transitions:
        if tr.kind == 'post' and tr.type != 'cut':
            cuts |= set(range(F(tr.window()[0]) - 1, F(tr.window()[1]) + 2))
    bad = []
    for f in range(1, n - 1):
        if f in cuts:
            continue
        idx = [i for i in range(max(1, f - 15), min(n - 1, f + 16)) if i != f and i not in cuts]
        m = float(np.median(e[idx])) if idx else 0.0
        if e[f] > max(4 * m, m + 0.025) and e[f] > 1.5 * min(d[f - 1], d[min(n - 1, f + 2)]):
            bad.append((f, round(float(e[f]), 4), round(m, 4)))
    add('glitch', not bad, frames=bad[:10], count=len(bad))
    try:
        an = json.load(open(os.path.join(pdir, 'out', q, 'anchors.json')))
    except FileNotFoundError:
        an = {}
    for key, v in an.items():
        if v.get('matched'):
            err = max((abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) for _, pa, pb in v['frames']), default=0.0)
            add('anchor', err <= 0.01, shots=key, type=v['type'], max_err=round(err, 4))
        elif v.get('missing'):
            add('anchor_missing', False, shots=key, type=v['type'], missing=v['missing'], note='frame centre used')

    def allowed(f):
        t = f / tl.fps
        if t < tl.fade_in or t >= tl.dur - tl.fade_out - 1e-6:
            return True
        return any(a <= t <= b for a, b in tl.allow_dark)
    dark = [f for f in range(n) if luma[f] < 0.03 and not allowed(f)]
    add('black', not dark, frames=dark[:20], count=len(dark))
    run, runs = 0, []
    for f in range(1, n):
        run = run + 1 if d[f] < 1e-4 else 0
        if run == 7 and not allowed(f):           # 7 zero differences in a row = 8 identical frames
            runs.append(f - 7)
    add('frozen', not runs, starts=runs[:10])
    out = os.path.join(pdir, 'out', q, 'seamcheck.json')
    json.dump(res, open(out, 'w'), indent=1)
    for c in res['checks']:
        print(('PASS ' if c['ok'] else ('WARN ' if c['kind'] in WARN_ONLY else 'FAIL ')) +
              ' '.join(f'{k}={v}' for k, v in c.items() if k != 'ok'))
    print(f'seamcheck: {fails} failure(s); report {out}')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
