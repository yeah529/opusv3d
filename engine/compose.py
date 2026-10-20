"""Compose the rendered shots into one video: post transitions, world-switch seams, per-look grade, fades.

usage: python compose.py <project_dir> [--draft] [--stills]
  --stills   grade out/<q>/stills/*.jpg with each shot's look, draw the overlays, into out/<q>/stills/sheet.jpg
needs: numpy, scipy, pillow (the lemo-opuscar venv) and ffmpeg.
reads: timeline.json, out/<q>/render.json, out/<q>/anchors.json, out/<q>/shots/<id>/#####.jpg
writes: out/<q>/video.mp4 (no audio; mux.sh adds the mix)

Post transitions (generators; options go in the shot's "in" object of timeline.json):
  cut                                   hard switch at t
  fade                                  crossfade over dur
  iris    mode: open|close, feather, rim   circle around the anchor; open = B grows from it, close = A shrinks to it
  lens    radius (x frame height), mag, dir: ltr|rtl   a refracting bubble sweeps across and leaves B behind
  breach  amp, wavelength (x frame height)   a ripple ring from the anchor; B is inside the ring
Overlays ("overlays" in timeline.json; compose-only, changing them never re-renders), drawn after the grade and
before the fades, in list order:
  {"image": "title.png", "t": "@title", "in": 1.6, "x": 0.5, "y": 0.15, "w": 0.56, "reveal": "write", "until": 29}
  image  RGBA png (project-relative); x, y its centre and w its width, as fractions of the frame
  reveal write  a soft edge sweeps left to right over "in" seconds (written on)
         stamp  drops from 1.35x to 1x with a small overshoot and fades in over "in" seconds
         fade   fades in over "in" seconds
  until  optional end time (default: to the end of the film); "sfx" is read by mix.py
World switches (push_in / pull_out): `seam` frames crossfaded, and the grade moves from A's look to B's
look across the move, so the frame before the switch and the switch frame use the same grade.
"""
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageFilter
from scipy.ndimage import map_coordinates

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'v3d'))
from timeline import Timeline, TimelineError, signature  # noqa: E402  (pure python, no bpy)

LUM = np.array([0.2126, 0.7152, 0.0722], np.float32)


def die(msg):
    sys.exit(f'compose: {msg}')


def smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def inout(x):
    x = min(1.0, max(0.0, x))
    return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2


def sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


# ---------------- overlays ----------------
def load_overlays(pdir, tl, w, h):
    ovs = []
    for i, o in enumerate(tl.raw.get('overlays', [])):
        try:
            im = Image.open(os.path.join(pdir, o['image'])).convert('RGBA')
            t0, dur = tl.T(o['t']), float(o.get('in', 1.0))
            t1 = tl.T(o['until']) if 'until' in o else None
            x, y, ow = float(o.get('x', 0.5)), float(o.get('y', 0.5)), float(o.get('w', 0.5))
        except KeyError as e:
            die(f'overlay {i} ({o.get("image")}): field "{e.args[0]}" is missing')
        except (ValueError, TypeError, TimelineError, OSError) as e:
            die(f'overlay {i} ({o.get("image")}): {e}')
        if o.get('reveal', 'fade') not in ('write', 'stamp', 'fade'):
            die(f'overlay {i}: reveal must be write, stamp or fade, not {o.get("reveal")!r}')
        pw = max(2, int(round(ow * w)))
        im = im.resize((pw, max(2, int(round(im.height * pw / im.width)))), Image.LANCZOS)
        ovs.append(dict(im=im, t0=t0, dur=max(dur, 1e-3), t1=t1, cx=x * w, cy=y * h, reveal=o.get('reveal', 'fade')))
    return ovs


def overlay(img, ov, t):
    if t < ov['t0'] or (ov['t1'] is not None and t >= ov['t1']):
        return img
    p = min(1.0, (t - ov['t0']) / ov['dur'])
    im = ov['im']
    if ov['reveal'] == 'stamp' and p < 1:
        k = 1 + 0.35 * (1 - inout(p)) - 0.06 * math.sin(math.pi * min(1.0, p * 1.4)) * (p > 0.5)
        im = im.resize((max(2, int(im.width * k)), max(2, int(im.height * k))), Image.BILINEAR)
    a = np.asarray(im, np.float32) / 255
    rgb, al = a[..., :3], a[..., 3].copy()
    if ov['reveal'] == 'write':
        e = 0.08
        front = -e + p * (1 + 2 * e)
        al *= sstep(front + e / 2, front - e / 2, np.linspace(0, 1, al.shape[1], dtype=np.float32))[None, :]
    else:
        al *= smooth(p * (3 if ov['reveal'] == 'stamp' else 1))
    H, W = img.shape[:2]
    x0, y0 = int(round(ov['cx'] - al.shape[1] / 2)), int(round(ov['cy'] - al.shape[0] / 2))
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + al.shape[1]), min(H, y0 + al.shape[0])
    if xa >= xb or ya >= yb:
        return img
    img = img.copy()
    sa = al[ya - y0:yb - y0, xa - x0:xb - x0, None]
    img[ya:yb, xa:xb] = img[ya:yb, xa:xb] * (1 - sa) + rgb[ya - y0:yb - y0, xa - x0:xb - x0] * sa
    return img


# ---------------- grade ----------------
def blur(img, radius, scale=4):
    """Fast gaussian-ish blur of a float image by blurring a downscaled copy."""
    h, w = img.shape[:2]
    small = Image.fromarray((np.clip(img, 0, 1) * 255 + .5).astype(np.uint8)).resize((max(1, w // scale), max(1, h // scale)), Image.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(max(0.5, radius / scale)))
    return np.asarray(small.resize((w, h), Image.BILINEAR), np.float32) / 255


def grade(x, p):
    h, w = x.shape[:2]
    warm = p.get('warm', 0.0)
    if warm:
        x = x * np.array([1 + .04 * warm, 1.0, 1 - .04 * warm], np.float32)
    sat = p.get('sat', 1.0)
    if sat != 1.0:
        y = (x @ LUM)[..., None]
        x = y + (x - y) * sat
    con = p.get('con', 1.0)
    if con != 1.0:
        x = 0.5 + (x - 0.5) * con
    bl = p.get('bloom', 0.0)
    if bl > 0:
        thr = p.get('thr', 0.8)
        hi = np.clip((x - thr) / max(1e-3, 1 - thr), 0, 1)
        b = blur(hi, h / 40) * 0.6 + blur(hi, h / 12) * 0.4
        x = 1 - (1 - np.clip(x, 0, 1)) * (1 - np.clip(b * bl, 0, 1))
    tilt = p.get('tilt', 0.0)
    if tilt > 0:
        yy = np.abs(np.linspace(0, 1, h, dtype=np.float32) - p.get('tilt_y', 0.5))[:, None, None]
        m = sstep(0.12, 0.42, yy) * tilt
        x = x * (1 - m) + blur(x, h / 90) * m
    vig = p.get('vig', 0.0)
    if vig > 0:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        r2 = ((xx / w - .5) * (w / h)) ** 2 + (yy / h - .5) ** 2
        x = x * (1 - vig * np.clip(r2 / (0.25 * (w / h) ** 2 + 0.25), 0, 1))[..., None]
    return np.clip(x, 0, 1)


def mixp(a, b, k):
    return {key: a.get(key, b.get(key, 0.0)) * (1 - k) + b.get(key, a.get(key, 0.0)) * k for key in set(a) | set(b)}


# ---------------- transitions ----------------
def sample(img, ys, xs):
    out = np.empty(ys.shape + (3,), np.float32)
    for c in range(3):
        out[..., c] = map_coordinates(img[..., c], [ys, xs], order=1, mode='nearest')
    return out


def fx_iris(A, B, p, c, o):
    h, w = A.shape[:2]
    cx, cy = c[0] * w, (1 - c[1]) * h
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.hypot(xx - cx, yy - cy)
    rmax = max(math.hypot(cx - x, cy - y) for x in (0, w) for y in (0, h))
    fe = o.get('feather', 0.006) * h + 1
    mode = o.get('mode', 'open')
    e = inout(p)
    r = (e if mode == 'open' else 1 - e) * (rmax + 2 * fe)
    inside = sstep(r + fe, r - fe, d)[..., None]
    out = B * inside + A * (1 - inside) if mode == 'open' else A * inside + B * (1 - inside)
    rim = o.get('rim', 0.35)
    if rim and 0 < p < 1:
        ring = np.exp(-((d - r) / (1.5 * fe)) ** 2)[..., None] * rim
        out = out + (1 - out) * ring
    return out


def fx_lens(A, B, p, c, o):
    h, w = A.shape[:2]
    R = o.get('radius', 0.75) * h
    mag = o.get('mag', 0.3)
    e = smooth(p)
    ltr = o.get('dir', 'ltr') == 'ltr'
    cx = (-R + e * (w + 2 * R)) if ltr else (w + R - e * (w + 2 * R))
    cy = (1 - c[1]) * h
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = xx - cx, yy - cy
    d = np.hypot(dx, dy)
    behind = (xx < cx) if ltr else (xx > cx)
    out = np.where(behind[..., None], B, A)
    ins = d < R
    if ins.any():
        k = 1 - mag * (1 - (d / R) ** 2)
        ref = np.empty_like(A)
        for ch, s in enumerate((1.012, 1.0, 0.988)):
            kk = k * s
            ref[..., ch] = map_coordinates(B[..., ch], [cy + dy * kk, cx + dx * kk], order=1, mode='nearest')
        edge = sstep(R - 0.02 * h, R - 0.002 * h, d)
        ref = ref * (1 - 0.25 * edge[..., None])
        m = sstep(R, R - 1.5, d)[..., None]
        out = ref * m + out * (1 - m)
    rim = np.exp(-((d - R + 0.004 * h) / (0.004 * h)) ** 2)[..., None] * 0.45
    out = out + (1 - out) * rim
    shade = np.exp(-np.clip(d - R, 0, None) / (0.03 * h))[..., None] * (d > R)[..., None] * 0.12
    return np.clip(out * (1 - shade), 0, 1)


def fx_breach(A, B, p, c, o):
    h, w = A.shape[:2]
    cx, cy = c[0] * w, (1 - c[1]) * h
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = xx - cx, yy - cy
    d = np.hypot(dx, dy) + 1e-3
    rmax = max(math.hypot(cx - x, cy - y) for x in (0, w) for y in (0, h))
    lam = o.get('wavelength', 0.07) * h
    amp = o.get('amp', 0.014) * h * (1 - 0.6 * p)
    rw = (1 - (1 - p) ** 2) * (rmax + 2 * lam)
    env = np.exp(-((d - rw) / lam) ** 2)
    disp = amp * np.sin(2 * np.pi * (d - rw) / lam) * env
    pre = amp * 0.35 * np.sin(2 * np.pi * d / (0.5 * lam) - p * 30) * np.exp(-d / (0.15 * h)) * (1 - p)
    s = (disp + pre) / d
    ys, xs = cy + dy * (1 - s) - 0, cx + dx * (1 - s)
    Aw, Bw = sample(A, ys, xs), sample(B, ys, xs)
    m = sstep(rw - 0.2 * lam, rw - lam, d)[..., None]
    out = Bw * m + Aw * (1 - m)
    out = out + (1 - out) * (0.18 * env * np.clip(np.cos(2 * np.pi * (d - rw) / lam), 0, 1))[..., None]
    return np.clip(out, 0, 1)


def fx_fade(A, B, p, c, o):
    e = smooth(p)
    return A * (1 - e) + B * e


FX = {'iris': fx_iris, 'lens': fx_lens, 'breach': fx_breach, 'fade': fx_fade}


# ---------------- main ----------------
class Frames:
    def __init__(self, base, man):
        self.base, self.man, self.cache = base, man, {}

    def get(self, sid, f):
        k = (sid, f)
        if k not in self.cache:
            a, b = self.man['shots'][sid]['range']
            if not a <= f <= b:
                die(f'frame {f} of shot {sid} is outside its rendered range {a}-{b} (engine bug)')
            p = os.path.join(self.base, 'shots', sid, f'{f:05d}.jpg')
            if not os.path.exists(p) or os.path.getsize(p) == 0:
                die(f'missing frame {p}; run: film.py -- render')
            if len(self.cache) > 12:
                self.cache.pop(next(iter(self.cache)))
            try:
                self.cache[k] = np.asarray(Image.open(p).convert('RGB'), np.float32) / 255
            except OSError as e:
                die(f'frame {p} is unreadable ({e}); delete it and run: film.py -- render')
        return self.cache[k]


def stills(base, post, pdir, tl, cols=4):
    d = os.path.join(base, 'stills')
    names = [f for f in os.listdir(d) if f.endswith('.jpg') and '_' in f] if os.path.isdir(d) else []
    names.sort(key=lambda n: (n.rsplit('_', 1)[1], n))          # in film order: <shot>_<frame>.jpg
    if not names:
        die(f'no stills in {d}; run: film.py -- stills')
    tiles, ovs = [], None
    for n in names:
        sid = n.rsplit('_', 1)[0]
        img = np.asarray(Image.open(os.path.join(d, n)).convert('RGB'), np.float32) / 255
        img = grade(img, post.get(sid, {}))
        if ovs is None:                            # titles at the still's own size (draft stills are half size)
            ovs = load_overlays(pdir, tl, img.shape[1], img.shape[0])
        t = int(n.rsplit('_', 1)[1].split('.')[0]) / tl.fps
        for ov in ovs:
            img = overlay(img, ov, t)
        tiles.append((n, Image.fromarray((np.clip(img, 0, 1) * 255 + .5).astype(np.uint8))))
    w, h = tiles[0][1].size
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * w, rows * (h + 18)), (16, 16, 20))
    from PIL import ImageDraw
    dr = ImageDraw.Draw(sheet)
    for i, (n, im) in enumerate(tiles):
        x, y = (i % cols) * w, (i // cols) * (h + 18)
        sheet.paste(im.resize((w, h)), (x, y + 18))
        dr.text((x + 4, y + 3), n, fill=(220, 220, 220))
    out = os.path.join(d, 'sheet.jpg')
    sheet.save(out, quality=90)
    print(f'compose: graded {len(tiles)} stills -> {out}')


def main():
    args = sys.argv[1:]
    if not args:
        die('usage: python compose.py <project_dir> [--draft]')
    pdir = os.path.abspath(args[0])
    q = 'draft' if '--draft' in args else 'final'
    base = os.path.join(pdir, 'out', q)
    try:
        tl = Timeline(os.path.join(pdir, 'timeline.json'))
    except TimelineError as e:
        die(f'timeline.json: {e}')
    try:
        man = json.load(open(os.path.join(base, 'render.json')))
        anchors = json.load(open(os.path.join(base, 'anchors.json')))
    except FileNotFoundError as e:
        die(f'{e.filename} missing; run: film.py -- render{" --draft" if q == "draft" else ""}')
    if '--stills' not in args and signature(pdir, q) != man['sig']:
        die(f'film.py, timeline.json or the engine changed since the last render; run: film.py -- render'
            f'{" --draft" if q == "draft" else ""} (or sh build.sh)')
    for s in tl.shots:
        if s.id not in man['shots']:
            die(f'shot {s.id} is not in render.json; re-run film.py')
        if '--stills' in args:
            continue
        done = os.path.join(base, 'shots', s.id, '.done')
        if not os.path.exists(done) or open(done).read().strip() != man['sig']:
            die(f'shot {s.id} is not rendered with the current film.py/timeline (stale or partial); run render')
    if man['fps'] != tl.fps or man['frames'] != tl.frames:
        die('render.json does not match timeline.json (fps or length changed); re-run film.py render')
    post = {sid: {**v['post'], **tl.post} for sid, v in man['shots'].items()}    # look grade, then the film's
    if '--stills' in args:
        return stills(base, post, pdir, tl)
    fr = Frames(base, man)
    first = fr.get(tl.shots[0].id, man['shots'][tl.shots[0].id]['range'][0])
    h, w = first.shape[:2]
    out_path = os.path.join(base, 'video.mp4')
    tmp = out_path + '.part.mp4'
    ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{w}x{h}',
                           '-r', str(tl.fps), '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '14',
                           '-pix_fmt', 'yuv420p', '-movflags', '+faststart', tmp], stdin=subprocess.PIPE)
    F = tl.F
    ovs = load_overlays(pdir, tl, w, h)

    def params(sid, f):
        """Grade of shot sid at frame f; moves between looks across world transitions."""
        s = tl.shot(sid)
        for tr in (s.tin, s.tout):
            if tr is None or tr.kind != 'world':
                continue
            a, b = tr.window()
            fa, fb = F(a), F(b)
            if fa <= f <= fb and fb > fa:
                return mixp(post[tr.a.id], post[tr.b.id], smooth((f - fa) / (fb - fa)))
            if tr.type == 'push_in' and f > fb and sid == tr.a.id:
                return post[tr.b.id]
            if tr.type == 'pull_out' and f < fa and sid == tr.b.id:
                return post[tr.a.id]
        return post[sid]

    def G(sid, f, p=None):
        return grade(fr.get(sid, f), p or params(sid, f))

    log = []
    try:
        for f in range(tl.frames):
            img, how = None, ''
            for tr in tl.transitions:
                if tr.kind == 'post' and tr.type != 'cut':
                    f0, f1 = F(tr.window()[0]), F(tr.window()[1])
                    if f0 <= f < f1:
                        p = (f - f0 + 0.5) / (f1 - f0)
                        rec = anchors.get(f'{tr.a.id}>{tr.b.id}', {}).get('frames', [])
                        m = {r[0]: r for r in rec}
                        c = (0.5, 0.5)
                        if f in m:
                            pa, pb = m[f][1], m[f][2]
                            c = (pa[0] * (1 - p) + pb[0] * p, pa[1] * (1 - p) + pb[1] * p)
                        img = FX[tr.type](G(tr.a.id, f), G(tr.b.id, f), p, c, tr.opts)
                        how = f'{tr.type} {tr.a.id}>{tr.b.id} p={p:.2f}'
                        break
                elif tr.kind == 'world' and tr.seam > 0:
                    k = F(tr.t)
                    lo, hi = (k - tr.seam, k) if tr.type == 'push_in' else (k, k + tr.seam)
                    if lo <= f < hi:
                        wgt = (f - lo + 1) / (tr.seam + 1)
                        gp = params(tr.b.id if tr.type == 'pull_out' else tr.a.id, f)
                        img = G(tr.a.id, f, gp) * (1 - wgt) + G(tr.b.id, f, gp) * wgt
                        how = f'seam {tr.a.id}>{tr.b.id} w={wgt:.2f}'
                        break
            if img is None:
                s = tl.active(f)
                img = G(s.id, f)
                how = s.id
            t = f / tl.fps
            for ov in ovs:
                img = overlay(img, ov, t)
            k = 1.0
            if tl.fade_in > 0 and t < tl.fade_in:
                k = smooth(t / tl.fade_in)
            if tl.fade_out > 0 and t > tl.dur - tl.fade_out:
                k = min(k, smooth((tl.dur - t - 1 / tl.fps) / tl.fade_out))
            if k < 1:
                img = img * k
            ff.stdin.write((np.clip(img, 0, 1) * 255 + .5).astype(np.uint8).tobytes())
            log.append(how)
            if f % 60 == 0:
                print(f'compose: {f}/{tl.frames}', flush=True)
    except BaseException:                            # die() or an error: no half-written video left behind
        ff.kill()
        ff.wait()
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    ff.stdin.close()
    if ff.wait() != 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        die('ffmpeg failed')
    os.replace(tmp, out_path)
    json.dump(log, open(os.path.join(base, 'compose.json'), 'w'))
    print(f'compose: wrote {out_path} ({tl.frames} frames, {w}x{h}, {tl.fps} fps)')


if __name__ == '__main__':
    main()
