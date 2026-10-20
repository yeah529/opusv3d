"""Keyframes baked per frame from Python easing.

Every animated value is written as one key per frame with linear interpolation, so the curve is exactly the
easing function (no Bezier handles to reason about), any frame renders alone, and changing fps only means
re-running film.py. Calls on the same property with different time ranges merge; the later call wins inside
its own range.
"""
import math

import bpy
from bpy_extras import anim_utils
from mathutils import Quaternion, Vector

FPS = 30  # set by Film
EVENTS = []  # sound cues: dicts with t, kind, gain, pan, dur (written to out/events.json)


def emit(t, kind, gain=1.0, pan=0.0, dur=0.0, **kw):
    """Record a sound cue at time t. mix.py turns kinds into sounds (whoosh, riser, pop, thump, step, ...)."""
    EVENTS.append(dict(t=round(float(t), 4), kind=kind, gain=gain, pan=pan, dur=dur, **kw))


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def lerp(a, b, t):
    return a + (b - a) * t


EASE = {
    'linear': lambda x: x,
    'in': lambda x: x * x * x,
    'out': lambda x: 1 - (1 - x) ** 3,
    'inout': lambda x: 4 * x * x * x if x < .5 else 1 - (-2 * x + 2) ** 3 / 2,
    'smooth': lambda x: x * x * (3 - 2 * x),
    'smoother': lambda x: x * x * x * (x * (x * 6 - 15) + 10),
    'gravity': lambda x: x * x,                               # free fall
    'rise': lambda x: 1 - (1 - x) ** 2,                       # thrown up, slowing
    'back': lambda x: 1 + 2.7 * (x - 1) ** 3 + 1.7 * (x - 1) ** 2,   # overshoot then settle
    'expo': lambda x: x if x in (0, 1) else (2 ** (20 * x - 10) / 2 if x < .5 else (2 - 2 ** (-20 * x + 10)) / 2),
    'step': lambda x: 0.0 if x < 1 else 1.0,
}


def ease(name, x):
    if callable(name):
        return name(clamp(x))
    if name not in EASE:
        raise ValueError(f'unknown ease "{name}" (known: {", ".join(EASE)})')
    return EASE[name](clamp(x))


def F(t):
    return int(round(t * FPS))


# ---------- fcurve access (Blender 4.4+ slotted actions) ----------
def channelbag(idb):
    ad = idb.animation_data or idb.animation_data_create()
    if ad.action is None:
        ad.action = bpy.data.actions.new(f'{idb.name}.act')
    act = ad.action
    if ad.action_slot is None:
        slot = act.slots.new(id_type=idb.id_type, name=idb.name)
        ad.action_slot = slot
    return anim_utils.action_ensure_channelbag_for_slot(act, ad.action_slot)


def fcurve(idb, path, index=0):
    cb = channelbag(idb)
    fc = cb.fcurves.find(path, index=index)
    return fc or cb.fcurves.new(path, index=index)


def find_fcurve(idb, path, index=0):
    ad = idb.animation_data
    if not ad or not ad.action or not ad.action_slot:
        return None
    cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    return cb.fcurves.find(path, index=index) if cb else None


def _write(idb, path, index, pts, constant=False):
    """Merge (frame, value) points into the fcurve: points of this call replace old ones in its range."""
    fc = fcurve(idb, path, index)
    f0, f1 = pts[0][0], pts[-1][0]
    old = [tuple(k.co) for k in fc.keyframe_points if not (f0 - .5 <= k.co[0] <= f1 + .5)]
    allp = sorted(old + [(float(f), float(v)) for f, v in pts])
    kp = fc.keyframe_points
    kp.clear()
    kp.add(len(allp))
    kp.foreach_set('co', [c for p in allp for c in p])
    kp.foreach_set('interpolation', [0 if constant else 1] * len(allp))   # CONSTANT / LINEAR
    fc.update()


def _getattr_path(idb, path):
    obj = idb
    for part in path.replace('"]', '').replace('["', '.').replace('[', '.').replace(']', '').split('.'):
        obj = obj[int(part)] if part.isdigit() else (obj[part] if not hasattr(obj, part) and hasattr(obj, '__getitem__') else getattr(obj, part))
    return obj


def value_at(idb, path, t, size=None):
    """Value of an animated property at time t (from its fcurves; falls back to the current value)."""
    cur = _getattr_path(idb, path)
    n = size or (len(cur) if hasattr(cur, '__len__') else 1)
    out = []
    for i in range(n):
        fc = find_fcurve(idb, path, i)
        out.append(fc.evaluate(t * FPS) if fc else (cur[i] if n > 1 or hasattr(cur, '__len__') else cur))
    return out if n > 1 else out[0]


def key(idb, path, keys, ease_default='inout'):
    """Animate `path` through keys [(t, value) or (t, value, ease_into_this_key)], baked one key per frame.

    value: number or sequence. rotation_quaternion is slerped. Outside the keys the value holds.
    """
    if not keys:
        return
    keys = sorted(keys, key=lambda k: k[0])
    vals = [k[1] for k in keys]
    vec = hasattr(vals[0], '__len__')
    n = len(vals[0]) if vec else 1
    quat = path.endswith('rotation_quaternion')
    if quat:
        vals = [Quaternion(v) for v in vals]
        for i in range(1, len(vals)):          # shortest path
            if vals[i].dot(vals[i - 1]) < 0:
                vals[i] = -vals[i]
    fa, fb = F(keys[0][0]), F(keys[-1][0])
    series = [[] for _ in range(n)]
    for f in range(fa, fb + 1):
        # the end frames may round to the far side of their key (0.05 s past the start: already 4% into the move,
        # held for every frame before it); pin them to the keys exactly
        t = keys[-1][0] if f == fb else keys[0][0] if f == fa else f / FPS
        j = 0
        while j < len(keys) - 2 and t > keys[j + 1][0]:
            j += 1
        ta, tb = keys[j][0], keys[j + 1][0] if len(keys) > 1 else keys[j][0]
        x = 1.0 if tb <= ta else (t - ta) / (tb - ta)
        e = ease(keys[j + 1][2] if len(keys) > 1 and len(keys[j + 1]) > 2 else ease_default, x) if len(keys) > 1 else 1.0
        if quat:
            v = vals[j].slerp(vals[min(j + 1, len(vals) - 1)], e) if len(vals) > 1 else vals[0]
        elif vec:
            a, b = vals[j], vals[min(j + 1, len(vals) - 1)]
            v = [lerp(a[i], b[i], e) for i in range(n)]
        else:
            v = lerp(vals[j], vals[min(j + 1, len(vals) - 1)], e)
        for i in range(n):
            series[i].append((f, v[i] if (vec or quat) else v))
    for i in range(n):
        _write(idb, path, i, series[i])


def bake(idb, path, t0, t1, fn):
    """Animate `path` with fn(t) -> value for every frame in [t0, t1]."""
    first = fn(t0)
    n = len(first) if hasattr(first, '__len__') else 1
    series = [[] for _ in range(n)]
    for f in range(F(t0), F(t1) + 1):
        v = fn(f / FPS)
        for i in range(n):
            series[i].append((f, v[i] if n > 1 or hasattr(v, '__len__') else v))
    for i in range(n):
        _write(idb, path, i, series[i])


def visible(obj, windows, children=True):
    """Show obj only inside the given [(t0, t1), ...] windows, in renders.
    Only hide_render is keyed: an object hidden in the viewport is not evaluated, so its position would be stale
    for anchor matching, film.through() and voxelize()."""
    ws = sorted((F(t0), F(t1)) for t0, t1 in windows)
    pts = [(min(-1, ws[0][0] - 1) if ws else -1, 1.0)]  # hidden before the first window (keys must stay sorted)
    for f0, f1 in ws:
        pts += [(f0, 0.0), (f1, 1.0)]
    for o in [obj] + (list(obj.children_recursive) if children else []):
        for p in ('hide_render',):
            fc = fcurve(o, p)
            kp = fc.keyframe_points
            kp.clear()
            kp.add(len(pts))
            kp.foreach_set('co', [c for q in pts for c in q])
            kp.foreach_set('interpolation', [0] * len(pts))
            fc.update()


# ---------- performance helpers ----------
def _land(t, t1, settle, attack=0.1):
    """Landing squash amount: rises over `attack` seconds (no one-frame pop at 30 fps), then a damped settle."""
    tau = t - t1
    if tau < attack:
        return math.sin(clamp(tau / attack) * math.pi / 2)
    x = clamp((tau - attack) / settle)
    return math.exp(-4 * x) * math.cos(x * math.pi * 1.5) * (1 - x)


def hop(obj, t0, t1, p0, p1, height=0.6, squash=0.18, base_scale=None, anticip=0.12, settle=0.18):
    """Jump from p0 to p1 between t0 (take-off) and t1 (landing): anticipation squash, stretch in the air,
    squash on landing, settle. Origin should sit at the bottom of the body for the squash to read."""
    s = Vector(base_scale or obj.scale)
    p0, p1 = Vector(p0), Vector(p1)

    def loc(t):
        x = clamp((t - t0) / (t1 - t0))
        e = EASE['inout'](x) * .35 + x * .65
        p = p0.lerp(p1, e)
        p.z += height * 4 * x * (1 - x)
        return p
    key(obj, 'location', [(t0, p0), (t1, p1)])
    bake(obj, 'location', t0, t1, loc)

    def sc(t):
        if t < t0:                                     # anticipation
            k = math.sin(clamp((t - (t0 - anticip)) / anticip) * math.pi / 2)
            return (s.x * (1 + squash * .6 * k), s.y * (1 + squash * .6 * k), s.z * (1 - squash * k))
        if t < t1:                                     # stretch, eases back before landing
            x = (t - t0) / (t1 - t0)
            k = math.sin(x * math.pi) * .6
            return (s.x * (1 - squash * .4 * k), s.y * (1 - squash * .4 * k), s.z * (1 + squash * k))
        k = _land(t, t1, settle)                       # landing squash, damped
        return (s.x * (1 + squash * .6 * k), s.y * (1 + squash * .6 * k), s.z * (1 - squash * k))
    bake(obj, 'scale', t0 - anticip, t1 + 0.1 + settle, sc)


def hops(obj, t0, points, dt=0.45, gap=0.12, height=0.5, sound='step', **kw):
    """A chain of hops through points, starting at t0. Returns the time of the last landing."""
    t = t0
    for a, b in zip(points, points[1:]):
        hop(obj, t, t + dt, a, b, height=height, **kw)
        if sound:
            emit(t + dt, sound, gain=0.6)
        t += dt + gap
    return t - gap


def drop(obj, t0, t1, p0, p1, squash=0.22, base_scale=None, settle=0.3, sound='thump'):
    """Fall from p0 to p1 under gravity between t0 and t1, then squash on landing and settle."""
    s = Vector(base_scale or obj.scale)
    key(obj, 'location', [(t0, tuple(p0)), (t1, tuple(p1), 'gravity')])

    def sc(t):
        if t < t1:
            k = clamp((t - t0) / (t1 - t0)) ** 2 * .5          # stretch while falling
            return (s.x * (1 - squash * .3 * k), s.y * (1 - squash * .3 * k), s.z * (1 + squash * .6 * k))
        k = _land(t, t1, settle)
        return (s.x * (1 + squash * .6 * k), s.y * (1 + squash * .6 * k), s.z * (1 - squash * k))
    bake(obj, 'scale', t0, t1 + 0.1 + settle, sc)
    if sound:
        emit(t1, sound, gain=0.9)


def blink(objs, t, dur=0.16):
    """Close and open eyes (scale z) around time t."""
    for o in objs:
        z = o.scale.z
        key(o, 'scale', [(t - dur / 2, tuple(o.scale)), (t, (o.scale.x, o.scale.y, z * .08), 'out'),
                         (t + dur / 2, tuple(o.scale), 'out')])
