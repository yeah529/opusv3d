"""Review the film as pictures, not numbers (SKILL.md section 6): labelled sheets of the frames that matter.

usage (in the project directory, PY = $LEMO_OPUSCAR_HOME/.venv/bin/python):
  PY engine/review.py strip  <src> <out.jpg> <from> <to> [--every N] [--box x,y,w,h] [--cols N] [--w PX]
  PY engine/review.py pick   <src> <out.jpg> <at,at,...>  [--box x,y,w,h] [--cols N] [--w PX]
  PY engine/review.py curves <motion.json> <out.png>

  strip    every frame (or every Nth, always ending on <to>) from <from> to <to>, one cell each: a fast action is
           reviewed frame by frame, because the broken frame is usually between two key poses
  pick     the listed frames: key poses, and every frame a numeric check flagged
  curves   the speed curves written by engine/motioncheck.py, one panel per part, flags marked in red
<src>      a film (out/<q>/film.mp4; its fps must match timeline.json) or a directory of frames named
           NNNNN.jpg / <shot>_NNNNN.jpg (4+ digits; out/<q>/shots/<id>, out/<q>/stills); one image per frame number
times      f362 (frame), 14.6 (seconds), @jump+0.2, bar:5 (timeline.json of this project)
--box      crop, as fractions of the frame: x,y,w,h from the top left; the same box for every cell.
           Crop to the subject: it should fill at least half of the cell height
--w --cols cell width in px and cells per row (default 320 x 6 for strip, 480 x 4 for pick: 1920 px wide). A sheet
           taller than 2000 px is split into pages out.jpg, out_2.jpg, ... (an image viewer shrinks larger sheets)
"""
import json
import os
import re
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'v3d'))
from timeline import Timeline, TimelineError  # noqa: E402  (pure python, no bpy)

MAX_CELLS = 240
MAX_SIDE = 2000
LABEL = 24
TERMS = 60                                             # select terms per ffmpeg run (about 100 fail to allocate)


def die(msg):
    print(f'review.py: {msg}', file=sys.stderr)
    sys.exit(1)


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                                  # Pillow < 10.1
        return ImageFont.load_default()


def frame_of(tl, s):
    s = s.strip()
    if re.fullmatch(r'f\d+', s):
        return int(s[1:])
    try:
        return tl.F(tl.T(s))
    except TimelineError as e:
        die(str(e))


def options(args, names):
    out = {}
    for n in names:
        if n in args:
            i = args.index(n)
            if i + 1 >= len(args):
                die(f'{n} needs a value')
            out[n] = args[i + 1]
            del args[i:i + 2]
    bad = [a for a in args if a.startswith('--')]
    if bad:
        die(f'unknown option {bad[0]}')
    return out


def whole(o, name, default, lo, hi):
    v = o.get(name, str(default))
    if not re.fullmatch(r'\d+', v) or not lo <= int(v) <= hi:
        die(f'{name} must be a whole number from {lo} to {hi}, not {v!r}')
    return int(v)


def parse_box(s):
    try:
        b = [float(v) for v in s.split(',')]
    except ValueError:
        die(f'--box must be x,y,w,h fractions, not {s!r}')
    if len(b) != 4 or not (0 <= b[0] < 1 and 0 <= b[1] < 1 and 0.02 <= b[2] and 0.02 <= b[3]
                           and b[0] + b[2] <= 1.0001 and b[1] + b[3] <= 1.0001):
        die(f'--box must be x,y,w,h inside the frame (w, h >= 0.02; x+w <= 1, y+h <= 1), not {s!r}')
    return b


def runs(ks):
    out = []
    for k in ks:
        if out and k == out[-1][1] + 1:
            out[-1][1] = k
        else:
            out.append([k, k])
    return out


def grab(src, frames, fps):
    """{frame: PIL image} for the wanted frames of a film or a frame directory; dies when one is missing."""
    want = sorted(set(frames))
    if os.path.isdir(src):
        have = {}
        for f in sorted(os.listdir(src)):
            m = re.fullmatch(r'(?:.*_)?(\d{4,})\.(jpg|jpeg|png)', f, re.I)
            if m:
                k = int(m.group(1))
                if k in have:
                    die(f'{src}: frame {k} is both {os.path.basename(have[k])} and {f}; use one shot directory')
                have[k] = os.path.join(src, f)
        miss = [f for f in want if f not in have]
        if miss:
            die(f'{src} has no frame {miss[:8]} (it holds {min(have) if have else "-"}..{max(have) if have else "-"})')
        return {f: Image.open(have[f]).convert('RGB') for f in want}
    if not os.path.isfile(src):
        die(f'{src} not found')
    n, rate = probe(src)
    if abs(rate - fps) > 0.01:
        die(f'{src} runs at {rate:g} fps, timeline.json at {fps}: frame numbers and times would not match')
    miss = [f for f in want if not 0 <= f < n]
    if miss:
        die(f'{src} has frames 0..{n - 1}; asked for {miss[:8]}')
    terms = [f'between(n\\,{a}\\,{b})' for a, b in runs(want)]
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(0, len(terms), TERMS):          # one ffmpeg run per batch of terms
            d = os.path.join(tmp, str(i))
            os.mkdir(d)
            r = subprocess.run(['ffmpeg', '-v', 'error', '-i', src, '-vf', 'select=' + '+'.join(terms[i:i + TERMS]),
                                '-fps_mode', 'passthrough', os.path.join(d, '%05d.png')], capture_output=True, text=True)
            if r.returncode:
                die(f'ffmpeg failed: {r.stderr.strip()[-300:]}')
            out[i] = [os.path.join(d, g) for g in sorted(os.listdir(d))]
        files = sum((out[i] for i in sorted(out)), [])
        if len(files) != len(want):
            die(f'ffmpeg gave {len(files)} frames for {len(want)} asked')
        return {f: Image.open(p).convert('RGB') for f, p in zip(want, files)}


def probe(src):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_packets', '-show_entries',
                        'stream=nb_read_packets,r_frame_rate', '-of', 'json', src], capture_output=True, text=True)
    try:
        st = json.loads(r.stdout)['streams'][0]
        a, b = st['r_frame_rate'].split('/')
        return int(st['nb_read_packets']), float(a) / float(b)
    except (ValueError, KeyError, IndexError, ZeroDivisionError):
        die(f'cannot read {src} as a video: {r.stderr.strip()[-200:]}')


def save(img, path, **kw):
    try:
        img.save(path, **kw)
    except (OSError, ValueError, KeyError) as e:
        die(f'cannot write {path}: {e}')


def sheet(imgs, frames, fps, out, box, cols, w):
    W, H = imgs[frames[0]].size
    crop = (0, 0, W, H) if not box else (round(box[0] * W), round(box[1] * H),
                                         round((box[0] + box[2]) * W), round((box[1] + box[3]) * H))
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    h = max(1, round(w * ch / cw))
    cols = min(cols, len(frames))
    per = cols * max(1, MAX_SIDE // (h + LABEL))       # cells per page
    base, ext = os.path.splitext(out)
    paths = []
    for p in range(0, len(frames), per):
        page = frames[p:p + per]
        rows = (len(page) + cols - 1) // cols
        S = Image.new('RGB', (cols * w, rows * (h + LABEL)), (20, 20, 24))
        d, fnt = ImageDraw.Draw(S), font(16)
        for k, f in enumerate(page):
            x, y = (k % cols) * w, (k // cols) * (h + LABEL)
            S.paste(imgs[f].crop(crop).resize((w, h), Image.LANCZOS), (x, y + LABEL))
            d.text((x + 6, y + 3), f'f{f}  {f / fps:.2f}s', fill=(235, 235, 235), font=fnt)
            d.line([(x, y), (x, y + h + LABEL)], fill=(20, 20, 24), width=2)
        path = out if p == 0 else f'{base}_{p // per + 1}{ext}'
        save(S, path, quality=90)
        paths.append(f'{path} {S.size[0]}x{S.size[1]}')
    print(f'review.py: {len(frames)} cells of {w}x{h} (crop {cw}x{ch} px, scale {w / cw:.2f}) -> ' + ', '.join(paths))


def curves(js, out):
    try:
        m = json.load(open(js, encoding='utf-8'))
        f0, fps, series = m['f0'], m['fps'], m['series']
        n = max(len(s['v']) for s in series)
    except (OSError, ValueError, KeyError, TypeError) as e:
        die(f'{js}: not a motioncheck.py file ({e})')
    W, P, L = 1600, 150, 190
    S = Image.new('RGB', (W, len(series) * P + 30), (250, 250, 250))
    d, fnt = ImageDraw.Draw(S), font(14)
    sx = (W - L - 10) / max(1, n - 1)
    for i, s in enumerate(series):
        y0, v = i * P, s['v']
        top = max(v) or 1.0
        name = s['name'].split(':', 1)[-1] if ':' in s['name'] else s['name']   # the bone (or object) part
        d.rectangle([L, y0 + 8, W - 10, y0 + P - 8], outline=(200, 200, 200))
        for j in range(0, min(len(name), 66), 22):
            d.text((6, y0 + 10 + j), name[j:j + 22], fill=(30, 30, 30), font=fnt)
        d.text((6, y0 + P - 30), f'peak {top:.3g} {s["unit"]}', fill=(110, 110, 110), font=fnt)
        for fl in s.get('flags', []) + [x for x in m.get('sync', []) if s['name'] in x.get('parts', [s['name']])]:
            for f in range(fl['f0'], min(fl['f1'], f0 + n - 1) + 1):
                x = L + (f - f0) * sx
                d.line([(x, y0 + 8), (x, y0 + P - 8)], fill=(255, 190, 190))
            ty = y0 + 10 if fl['kind'] == 'sync' else y0 + P - 26          # sync on top: it often starts with a jolt
            d.text((L + (fl['f0'] - f0) * sx + 2, ty), fl['kind'], fill=(200, 30, 30), font=fnt)
        pts = [(L + k * sx, y0 + P - 10 - (P - 24) * (x / top)) for k, x in enumerate(v)]
        d.line(pts, fill=(40, 90, 200), width=2)
    for f in range(f0, f0 + n):
        if (f - f0) % max(1, fps // 2) == 0:
            x = L + (f - f0) * sx
            d.line([(x, len(series) * P), (x, len(series) * P + 6)], fill=(80, 80, 80))
            d.text((x + 2, len(series) * P + 8), f'f{f}', fill=(80, 80, 80), font=fnt)
    save(S, out)
    print(f'review.py: {out} {S.size[0]}x{S.size[1]}, {len(series)} panels, f{f0}..f{f0 + n - 1} '
          f'(the value at f is the speed from f to f+1)')


def main(argv):
    if len(argv) < 3 or argv[0] not in ('strip', 'pick', 'curves'):
        die('usage: review.py strip|pick|curves ... (see the top of this file)')
    cmd, args = argv[0], list(argv[1:])
    if cmd == 'curves':
        return curves(args[0], args[1])
    o = options(args, ('--every', '--box', '--cols', '--w'))
    out_dir = os.path.dirname(os.path.abspath(args[1])) if len(args) > 1 else '.'
    if not os.path.isdir(out_dir):
        die(f'no directory {out_dir}')
    tl = Timeline(os.path.join(os.path.dirname(HERE), 'timeline.json'))
    if cmd == 'strip':
        if len(args) != 4:
            die('usage: review.py strip <src> <out.jpg> <from> <to> [--every N] [--box x,y,w,h]')
        src, out, a, b = args
        fa, fb, every = frame_of(tl, a), frame_of(tl, b), whole(o, '--every', 1, 1, 10000)
        if fb < fa:
            die(f'need <from> <= <to> (got f{fa}..f{fb})')
        frames = list(range(fa, fb + 1, every))
        if frames[-1] != fb:
            frames.append(fb)
        cols, w = whole(o, '--cols', 6, 1, 40), whole(o, '--w', 320, 64, 1920)
    else:
        if len(args) != 3:
            die('usage: review.py pick <src> <out.jpg> <at,at,...> [--box x,y,w,h]')
        src, out, at = args
        frames = sorted(set(frame_of(tl, s) for s in at.split(',') if s.strip()))
        if not frames:
            die('no frames given')
        cols, w = whole(o, '--cols', 4, 1, 40), whole(o, '--w', 480, 64, 1920)
    if any(f < 0 for f in frames):
        die(f'frames must be >= 0 (got f{min(frames)})')
    if len(frames) > MAX_CELLS:
        die(f'{len(frames)} cells; at most {MAX_CELLS} (use --every or a shorter range)')
    box = parse_box(o['--box']) if '--box' in o else None
    sheet(grab(src, frames, tl.fps), frames, tl.fps, out, box, cols, w)


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except TimelineError as e:
        die(str(e))
