"""timeline.json: the single source of truth for picture, transitions, sound and checks.

Pure Python (no bpy), so the Blender side, compose.py, mix.py and seamcheck.py all read the same numbers.

Times can be written as:
  12.5            seconds
  "bar:5"         start of bar 5 (1-based; needs "bpm"; "meter" beats per bar, default 4)
  "beat:9.5"      beat 9.5 (1-based)
  "@lift"         a named mark from "marks"
  "bar:5-0.25"    any of the above plus or minus seconds
Transition times are free. Use bar/beat only where a cut should land on the music.
"""
import hashlib
import json
import os
import re

# composited after rendering, from the two shots' frames
POST = {'cut': 0.0, 'iris': 0.5, 'lens': 0.8, 'breach': 0.8, 'fade': 0.5}
# a camera move through a surface that shows the other shot; switch is seamless
WORLD = {'push_in': 1.5, 'pull_out': 1.5}
TYPES = {**POST, **WORLD}
# options each transition type accepts in its "in" object (besides the common keys)
COMMON = {'type', 't', 'dur', 'anchor', 'match', 'settle'}
OPTS = {'cut': set(), 'fade': set(), 'iris': {'mode', 'feather', 'rim'}, 'lens': {'radius', 'mag', 'dir'},
        'breach': {'wavelength', 'amp'}, 'push_in': {'surface', 'seam', 'ease', 'fade'},
        'pull_out': {'surface', 'seam', 'ease', 'fade'}}
CHOICES = {'mode': ('open', 'close'), 'dir': ('ltr', 'rtl')}
NUMBERS = {'dur', 'settle', 'feather', 'rim', 'radius', 'mag', 'wavelength', 'amp', 'fade', 'seam'}
_NUM = r'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)'
_T = re.compile(rf'^\s*(?:(bar|beat):({_NUM})|@([A-Za-z_][\w-]*)|(-?{_NUM}))\s*(?:([+-])\s*({_NUM}))?\s*$')
_ID = re.compile(r'^[A-Za-z0-9_-]+$')


class TimelineError(ValueError):
    pass


class Shot:
    def __init__(self, i, d):
        self.i = i
        if not isinstance(d, dict) or 'id' not in d or 'world' not in d:
            raise TimelineError(f'shot #{i + 1}: needs "id" and "world"')
        self.id = str(d['id'])
        if not _ID.match(self.id):     # the id becomes a folder name under out/<q>/shots/
            raise TimelineError(f'shot id "{self.id}": use only letters, digits, "_" and "-"')
        self.world = d['world']
        self.cam = d.get('cam', 'cam.' + self.id)
        self.engine = d.get('engine')          # None = the look's engine
        self.anchor = d.get('anchor', 'hero')  # object name inside the world, for anchor matching
        self.raw_in = d.get('in')
        self.tin = None                        # Transition entering this shot (None for the first)
        self.tout = None                       # Transition leaving this shot
        self.t0 = self.t1 = None

    def __repr__(self):
        return f'<Shot {self.id} {self.world} {self.t0:.3f}-{self.t1:.3f}>'


class Transition:
    def __init__(self, a, b, d, tl):
        self.a, self.b = a, b
        if not isinstance(d, dict):
            raise TimelineError(f'shot {b.id}: "in" must be an object like {{"type": "cut", "t": 4.0}}')
        self.type = d.get('type', 'cut')
        if self.type not in TYPES:
            raise TimelineError(f'shot {b.id}: unknown transition "{self.type}" (known: {", ".join(sorted(TYPES))})')
        bad = sorted(set(d) - COMMON - OPTS[self.type])
        if bad:
            ok = ', '.join(sorted(COMMON | OPTS[self.type]))
            raise TimelineError(f'shot {b.id}: {self.type} has no option {", ".join(bad)} (options: {ok})')
        for k, v in d.items():
            if k in CHOICES and v not in CHOICES[k]:
                raise TimelineError(f'shot {b.id}: "{k}" must be one of {", ".join(CHOICES[k])}, not "{v}"')
            if k in NUMBERS and (isinstance(v, bool) or not isinstance(v, (int, float))):
                raise TimelineError(f'shot {b.id}: "{k}" must be a number, not {v!r}')
        if 't' not in d:
            raise TimelineError(f'shot {b.id}: "in" needs "t" (when the transition happens)')
        self.t = tl.T(d['t'])
        self.dur = float(d.get('dur', TYPES[self.type]))
        if self.dur < 0:
            raise TimelineError(f'shot {b.id}: negative dur')
        anc = d.get('anchor', [a.anchor, b.anchor])
        self.anchor = [anc, anc] if isinstance(anc, str) else list(anc)
        self.match = bool(d.get('match', self.type in ('iris', 'breach', 'lens')))  # shift B's camera so anchors line up
        self.settle = float(d.get('settle', 1.0))      # seconds for B's camera to ease back after the match
        self.surface = d.get('surface')                # push_in / pull_out: object name of the portal surface
        self.seam = int(d.get('seam', 2))              # frames crossfaded at a world switch
        self.opts = {k: v for k, v in d.items() if k not in ('type', 't', 'dur', 'anchor', 'match', 'settle', 'surface', 'seam')}
        if self.type in WORLD and not self.surface:
            raise TimelineError(f'shot {b.id}: {self.type} needs "surface" (the object that shows the other shot)')

    @property
    def kind(self):
        return 'world' if self.type in WORLD else 'post'

    def window(self):
        """Seconds during which both shots are on screen (post) or the move runs (world)."""
        if self.type == 'push_in':
            return self.t - self.dur, self.t
        if self.type == 'pull_out':
            return self.t, self.t + self.dur
        return self.t - self.dur / 2, self.t + self.dur / 2

    def __repr__(self):
        return f'<{self.type} {self.a.id}->{self.b.id} @{self.t:.3f} dur {self.dur}>'


class Timeline:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.dir = os.path.dirname(self.path)
        try:
            with open(self.path, encoding='utf-8') as f:
                d = json.load(f)
        except FileNotFoundError:
            raise TimelineError(f'{self.path} not found') from None
        except json.JSONDecodeError as e:
            raise TimelineError(f'not valid JSON: {e.msg} at line {e.lineno} column {e.colno}') from None
        if not isinstance(d, dict):
            raise TimelineError('the file must hold one JSON object')
        self.raw = d
        self.name = d.get('name') or os.path.basename(self.dir)
        self.fps = d.get('fps', 30)
        if isinstance(self.fps, bool) or not isinstance(self.fps, int) or not 1 <= self.fps <= 240:
            raise TimelineError(f'"fps" must be a whole number from 1 to 240, not {self.fps!r}')
        size = d.get('size', [1920, 1080])
        if (not isinstance(size, list) or len(size) != 2
                or not all(isinstance(x, int) and not isinstance(x, bool) and x >= 16 for x in size)):
            raise TimelineError(f'"size" must be [width, height] in whole pixels (16 or more), not {size!r}')
        self.size = tuple(size)
        if self.size[0] % 2 or self.size[1] % 2:
            raise TimelineError('size must be even numbers')
        self.bpm = d.get('bpm')
        if self.bpm is not None and (isinstance(self.bpm, bool) or not isinstance(self.bpm, (int, float)) or self.bpm <= 0):
            raise TimelineError(f'"bpm" must be a positive number, not {self.bpm!r}')
        self.meter = d.get('meter', 4)
        if isinstance(self.meter, bool) or not isinstance(self.meter, int) or self.meter < 1:
            raise TimelineError(f'"meter" must be a whole number of beats per bar, not {self.meter!r}')
        self.offset = float(d.get('music_offset', 0.0))
        self.post = d.get('post', {})                  # compose-time grade: bloom, vignette, contrast, sat
        self.fade_in = float(d.get('fade_in', 0.0))     # seconds from black at the start
        self.fade_out = float(d.get('fade_out', 0.0))   # seconds to black at the end
        ad = d.get('allow_dark', [])
        if not isinstance(ad, list) or not all(isinstance(r, list) and len(r) == 2 for r in ad):
            raise TimelineError(f'"allow_dark" must be a list of [from, to] pairs, not {ad!r}')
        self.allow_dark = [tuple(self.T(x) for x in r) for r in ad]
        if not isinstance(d.get('marks', {}), dict):
            raise TimelineError('"marks" must be an object like {"name": time}')
        self.marks = {}
        for k, v in d.get('marks', {}).items():          # marks may use earlier marks
            self.marks[k] = self.T(v)
        if 'dur' not in d:
            raise TimelineError('"dur" (film length in seconds) is missing')
        self.dur = self.T(d['dur'])
        if self.dur <= 0:
            raise TimelineError('"dur" must be more than 0')
        if not isinstance(d.get('shots'), list) or not d['shots']:
            raise TimelineError('"shots" must be a list with at least one shot')
        self.shots = [Shot(i, s) for i, s in enumerate(d['shots'])]
        if self.shots[0].raw_in:
            raise TimelineError(f'shot {self.shots[0].id} is the first shot: it has no "in" (nothing comes before it)')
        ids = [s.id for s in self.shots]
        if len(set(ids)) != len(ids):
            raise TimelineError('shot ids must be unique')
        self.transitions = []
        for a, b in zip(self.shots, self.shots[1:]):
            if not b.raw_in:
                raise TimelineError(f'shot {b.id}: missing "in" (how we enter it: type and t)')
            tr = Transition(a, b, b.raw_in, self)
            a.tout, b.tin = tr, tr
            self.transitions.append(tr)
        for s in self.shots:
            s.t0 = s.tin.t if s.tin else 0.0
            s.t1 = s.tout.t if s.tout else self.dur
            if s.t1 - s.t0 < 1.0 / self.fps:
                raise TimelineError(f'shot {s.id} is shorter than one frame ({s.t0:.3f}-{s.t1:.3f})')
        for tr in self.transitions:
            w0, w1 = tr.window()
            if w0 < tr.a.t0 - 1e-6 or w1 > tr.b.t1 + 1e-6:
                raise TimelineError(f'{tr}: its window {w0:.2f}-{w1:.2f} s runs past shot {tr.a.id} or {tr.b.id}')
        for p, q in zip(self.transitions, self.transitions[1:]):
            if p.window()[1] > q.window()[0] + 1e-6:
                raise TimelineError(f'{p} and {q} overlap; give the shot between them more time')
        self._check_overlays(d.get('overlays', []))

    def _check_overlays(self, ovs):
        """Titles drawn by compose.py; checked here so a bad one fails at plan, not after a full render."""
        if not isinstance(ovs, list) or not all(isinstance(o, dict) for o in ovs):
            raise TimelineError('"overlays" must be a list of objects like {"image": "title.png", "t": "@title"}')
        for i, o in enumerate(ovs):
            who = f'overlay {i} ({o.get("image")})'
            for k in ('image', 't'):
                if k not in o:
                    raise TimelineError(f'{who}: field "{k}" is missing')
            if not os.path.isfile(os.path.join(self.dir, o['image'])):
                raise TimelineError(f'{who}: no file {o["image"]} (paths are relative to the project)')
            t0 = self.T(o['t'])
            t1 = self.T(o['until']) if 'until' in o else self.dur
            if not 0 <= t0 < self.dur or t1 <= t0:
                raise TimelineError(f'{who}: shows from {t0:.2f} to {t1:.2f} s; it must start inside 0-{self.dur:.2f} s '
                                    f'and end after it starts')
            for k, lo, hi in (('in', 0.0, 60.0), ('x', 0.0, 1.0), ('y', 0.0, 1.0), ('w', 0.01, 1.0)):
                v = o.get(k)
                if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi):
                    raise TimelineError(f'{who}: "{k}" must be a number from {lo} to {hi}, not {v!r}')
            if o.get('reveal', 'fade') not in ('write', 'stamp', 'fade'):
                raise TimelineError(f'{who}: reveal must be write, stamp or fade, not {o.get("reveal")!r}')

    # ---- time ----
    def T(self, v):
        if isinstance(v, (int, float)):
            return float(v)
        m = _T.match(str(v))
        if not m:
            raise TimelineError(f'bad time "{v}" (use seconds, "bar:N", "beat:N" or "@mark", optionally +/- seconds)')
        unit, n, mark, sec, sign, delta = m.groups()
        if unit:
            if not self.bpm:
                raise TimelineError(f'"{v}" needs "bpm" in timeline.json')
            beat = 60.0 / float(self.bpm)
            t = self.offset + (float(n) - 1) * beat * (self.meter if unit == 'bar' else 1)
        elif mark:
            if mark not in self.marks:
                raise TimelineError(f'unknown mark "@{mark}"')
            t = self.marks[mark]
        else:
            t = float(sec)
        if sign:
            t += float(delta) * (1 if sign == '+' else -1)
        return t

    def F(self, t):
        """Global frame index of time t (frame 0 = 0 s)."""
        return int(round(t * self.fps))

    @property
    def frames(self):
        return self.F(self.dur)

    def shot(self, sid):
        for s in self.shots:
            if s.id == sid:
                return s
        raise TimelineError(f'unknown shot "{sid}"')

    def active(self, f):
        """The shot on screen at frame f (before any transition blending)."""
        t = f / self.fps
        for s in self.shots:
            if self.F(s.t0) <= f < self.F(s.t1):
                return s
        return self.shots[-1] if t >= self.shots[-1].t0 else self.shots[0]

    def handles(self, s):
        """Frame range [f0, f1] this shot must render: its own time plus what transitions need.

        post:     both shots render the whole window.
        push_in:  the inner shot (B) also renders the dive, because A's surface shows it.
        pull_out: the inner shot (A) also renders the pull, because B's surface shows it.
        world:    both render `seam` extra frames for the crossfade at the switch.
        """
        t0, t1 = s.t0, s.t1
        tr = s.tin
        if tr:
            seam = tr.seam / self.fps
            if tr.kind == 'post':
                t0 = min(t0, tr.window()[0])
            elif tr.type == 'push_in':
                t0 = min(t0, tr.t - tr.dur - seam)
            else:
                t0 = min(t0, tr.t - seam)
        tr = s.tout
        if tr:
            seam = tr.seam / self.fps
            if tr.kind == 'post':
                t1 = max(t1, tr.window()[1])
            elif tr.type == 'pull_out':
                t1 = max(t1, tr.t + tr.dur + seam)
            else:
                t1 = max(t1, tr.t + seam)
        return max(0, self.F(t0)), min(self.frames - 1, self.F(t1))


# top-level fields and post-transition options that only compose.py and seamcheck.py read: changing them
# must not re-render the shots
_POST_ONLY = ('name', 'post', 'fade_in', 'fade_out', 'allow_dark', 'overlays')


def signature(project_dir, q):
    """Hash of everything that changes rendered frames: film.py, the render-relevant part of timeline.json,
    the engine (v3d/*.py) and the quality. Pure python, so compose.py can check that frames are current."""
    h = hashlib.sha1()
    with open(os.path.join(project_dir, 'timeline.json'), encoding='utf-8') as f:
        d = json.load(f)
    for k in _POST_ONLY:
        d.pop(k, None)
    for s in d.get('shots', []):
        tin = s.get('in') if isinstance(s, dict) else None
        if isinstance(tin, dict) and tin.get('type', 'cut') in POST:
            s['in'] = {k: v for k, v in tin.items() if k in COMMON}
    h.update(json.dumps(d, sort_keys=True).encode())
    fp = os.path.join(project_dir, 'film.py')
    if os.path.exists(fp):
        h.update(open(fp, 'rb').read())
    eng = os.path.dirname(os.path.abspath(__file__))
    for f in sorted(x for x in os.listdir(eng) if x.endswith('.py')):
        h.update(open(os.path.join(eng, f), 'rb').read())
    h.update(q.encode())
    return h.hexdigest()[:16]
