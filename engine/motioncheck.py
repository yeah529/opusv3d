"""Speed curves of the moving parts, for what a still frame cannot show: stiff, gliding, jerky or lock-step motion.

usage (in the project directory; save the scene first with `film.py -- blend [--draft]`):
  B -b out/<q>/film.blend --python-exit-code 1 -P engine/motioncheck.py -- <from> <to> <part> [<part> ...] [--out f.json]
  then: PY engine/review.py curves out/<q>/motion.json out/<q>/motion.png   (and look at it next to a review.py strip)

<from> <to>   f120 (frame), 14.0 (seconds), @jump-0.3 (timeline.json of this project)
<part>        OBJ             object, speed of its world position (m/s)          W.prop
              OBJ:rot         object, speed of its world rotation (deg/s)         W.cam.s4:rot
              RIG:BONE@REF    bone, rotation relative to bone REF (deg/s)         W.hero.rig:head.x@spine_02.x
              RIG:BONE        bone, rotation relative to its parent (deg/s). On an Auto-Rig Pro rig the parent is a
                              control (c_spine_02.x, c_traj): always give @REF there
              RIG:BONE:pos    bone, speed of its head in the world (m/s)          W.hero.rig:hand.r:pos
              Object and bone names may hold ':' (the longest matching object name wins).
flags (signals to look at on a frame strip, not pass/fail; frames are the frames the change spans):
  jolt     the speed changes by more than 40 % of the part's peak in one frame (and by 60 deg/s or 0.4 m/s at least):
           a hard stop or start. Legitimate on an impact
  glide    0.3 s or more at one speed (within 3 % of the peak) that starts or ends with a corner (a step > 5 % of the
           peak in one frame): linear interpolation, reads mechanical. A smooth ease is not flagged
  jitter   the speed goes up and down 3 times within 5 frames, each step > 8 % of the peak (15 deg/s, 0.1 m/s at
           least): pose search noise
  sync     3 or more rotating parts, and at least 3/4 of them, peak within +-1 frame of each other: the body moves as one
           block. Only rotations count (list one chain: spine, head, upper arm, forearm, hand)
writes <dir of the .blend>/motion.json (or --out); prints MC lines; warns when film.py, timeline.json or the engine is
newer than the .blend (the scene may be stale: save it again)
"""
import glob
import json
import math
import os
import re
import sys

import bpy
from mathutils import Quaternion

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'v3d'))
from timeline import Timeline, TimelineError  # noqa: E402  (pure python)

STILL = {'m/s': 0.02, 'deg/s': 5.0}      # a peak below this is not visible motion (a camera pan of 9 deg/s is)
JOLT = {'m/s': 0.4, 'deg/s': 60.0}       # smallest one-frame change that counts as a jolt
JIT = {'m/s': 0.1, 'deg/s': 15.0}        # smallest step that counts toward a jitter


def die(msg):
    print(f'motioncheck.py: {msg}', file=sys.stderr)
    sys.exit(1)


def frame_of(tl, s):
    if re.fullmatch(r'f\d+', s.strip()):
        return int(s.strip()[1:])
    try:
        return tl.F(tl.T(s.strip()))
    except TimelineError as e:
        die(str(e))


def target(spec):
    """(label, unit, object, sample(depsgraph) -> Vector or Quaternion)"""
    names = [spec[:i] for i in range(len(spec), 0, -1) if i == len(spec) or spec[i] == ':']
    name = next((n for n in names if n in bpy.data.objects), None)
    if name is None:
        die(f'no object "{spec.partition(":")[0]}" in {bpy.data.filepath}')
    ob, rest = bpy.data.objects[name], spec[len(name) + 1:]
    if not ob.users_scene:
        die(f'"{name}" is in no scene')
    if not rest:
        return spec, 'm/s', ob, lambda dg: ob.evaluated_get(dg).matrix_world.translation.copy()
    bones = ob.pose.bones if ob.type == 'ARMATURE' else {}
    if rest == 'rot' and 'rot' not in bones:
        return spec, 'deg/s', ob, lambda dg: ob.evaluated_get(dg).matrix_world.to_quaternion()
    if ob.type != 'ARMATURE':
        die(f'"{name}" is not an armature; use OBJ or OBJ:rot')
    pos = rest.endswith(':pos') and rest not in bones
    body = rest[:-4] if pos else rest
    bone, ref = (body, '') if body in bones or '@' not in body else body.rsplit('@', 1)
    for b in (bone, ref):
        if b and b not in bones:
            die(f'no bone "{b}" in {name} (deform bones: '
                f'{", ".join(p.name for p in bones if p.bone.use_deform)[:400]})')
    if pos:
        return spec, 'm/s', ob, lambda dg: (ob.evaluated_get(dg).matrix_world @ ob.evaluated_get(dg).pose.bones[bone].head)

    def rot(dg):
        pb = ob.evaluated_get(dg).pose.bones
        par = pb[ref] if ref else pb[bone].parent
        M = pb[bone].matrix if par is None else par.matrix.inverted() @ pb[bone].matrix
        return M.to_quaternion()
    return spec, 'deg/s', ob, rot


def speed(a, b, fps):
    """Speed from frame to frame (a forward difference: a central one hides a one-frame jitter)."""
    if isinstance(a, Quaternion):                      # (a Vector has rotation_difference too)
        ang = a.rotation_difference(b).angle            # q and -q are one rotation: 359 deg is 1 deg
        return math.degrees(min(ang, 2 * math.pi - ang)) * fps
    return (b - a).length * fps


def runs(ks):
    out = []
    for k in ks:
        if out and k == out[-1][1] + 1:
            out[-1][1] = k
        else:
            out.append([k, k])
    return out


def flags(v, fps, unit):
    """[(kind, i0, i1)]: sample indices (frame f0 + i) spanned by each flag. v[k] is the speed from f0+k to f0+k+1."""
    top, n = max(v), len(v)
    dv = [v[k + 1] - v[k] for k in range(n - 1)]       # dv[k] spans frames k .. k+2
    out = [('jolt', a, b + 2) for a, b in runs([k for k, d in enumerate(dv) if abs(d) > max(0.4 * top, JOLT[unit])])]
    need = max(3, round(0.3 * fps))
    flat = runs([k for k in range(n - 1) if v[k] > 0.25 * top and v[k + 1] > 0.25 * top and abs(dv[k]) < 0.01 * top])
    for a, b in flat:                                  # v[a] .. v[b+1] are about equal
        seg = v[a:b + 2]
        corner = (a > 0 and abs(dv[a - 1]) > 0.05 * top) or (b + 1 < n - 1 and abs(dv[b + 1]) > 0.05 * top)
        if len(seg) >= need and max(seg) - min(seg) < 0.03 * top and corner:
            out.append(('glide', a, b + 2))
    jit = []
    for k in range(len(dv) - 3):
        w = dv[k:k + 4]
        if all(abs(d) > max(0.08 * top, JIT[unit]) for d in w) and sum(w[i] * w[i + 1] < 0 for i in range(3)) >= 3:
            jit.append(k)
    out += [('jitter', a, b + 5) for a, b in runs(jit)]
    return out


def stale(blend):
    """Inputs of the scene that are newer than the saved .blend."""
    proj = os.path.dirname(HERE)
    t = os.path.getmtime(blend)
    files = [os.path.join(proj, 'film.py'), os.path.join(proj, 'timeline.json')] + glob.glob(os.path.join(HERE, 'v3d', '*.py'))
    return [os.path.relpath(f, proj) for f in files if os.path.exists(f) and os.path.getmtime(f) > t + 1]


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    out_path = None
    if '--out' in argv:
        i = argv.index('--out')
        if i + 1 >= len(argv):
            die('--out needs a path')
        out_path = argv[i + 1]
        del argv[i:i + 2]
    if len(argv) < 3:
        die('usage: motioncheck.py -- <from> <to> <part> [<part> ...] [--out f.json]')
    if not bpy.data.filepath:
        die('open a saved .blend (film.py -- blend [--draft] writes out/<q>/film.blend)')
    tl = Timeline(os.path.join(os.path.dirname(HERE), 'timeline.json'))
    f0, f1 = frame_of(tl, argv[0]), frame_of(tl, argv[1])
    if f1 - f0 < 4:
        die(f'need at least 5 frames (got f{f0}..f{f1})')
    if f0 < 0 or f1 + 1 > tl.frames:
        die(f'f{f0}..f{f1} is outside the film (f0..f{tl.frames - 1})')
    out_path = out_path or os.path.join(os.path.dirname(bpy.data.filepath), 'motion.json')
    if not os.path.isdir(os.path.dirname(os.path.abspath(out_path))):
        die(f'no directory for {out_path}')
    old = stale(bpy.data.filepath)
    if old:
        print(f'MC warning: {", ".join(old)} newer than {os.path.basename(bpy.data.filepath)}: the scene may be stale '
              f'(save it again: film.py -- blend)')
    parts = [target(s) for s in argv[2:]]
    scenes = []
    for p in parts:                                    # every scene of every part advances (one scene per world)
        if p[2].users_scene[0] not in scenes:
            scenes.append(p[2].users_scene[0])
    fps = scenes[0].render.fps
    if any(sc.render.fps != tl.fps for sc in scenes):
        die(f'scene fps {[sc.render.fps for sc in scenes]} != timeline fps {tl.fps}')
    samples = {p[0]: [] for p in parts}
    for f in range(f0, f1 + 2):
        dgs = {}
        for sc in scenes:
            sc.frame_set(f)
            dgs[sc.name] = sc.view_layers[0].depsgraph    # this scene's, not the context scene's
        for label, _, ob, fn in parts:
            samples[label].append(fn(dgs[ob.users_scene[0].name]))
    series = []
    for label, unit, _, _ in parts:
        s = samples[label]
        v = [speed(s[k], s[k + 1], fps) for k in range(len(s) - 1)]      # v[k]: frame f0+k -> f0+k+1
        top = max(v)
        still = top < STILL[unit]
        fl = [] if still else [dict(kind=k, f0=f0 + a, f1=f0 + min(b, len(v))) for k, a, b in flags(v, fps, unit)]
        series.append(dict(name=label, unit=unit, v=[round(x, 5) for x in v], flags=fl, still=still))
        kp = f0 + v.index(top)
        print(f'MC {label:40s} peak {top:8.2f} {unit:5s} at f{kp}-f{kp + 1}' + ('  (still)' if still else ''))
        for x in fl:
            print(f'MC   {x["kind"]:6s} f{x["f0"]}..f{x["f1"]}')
    moving = [s for s in series if not s['still']]
    if not moving:
        print(f'MC warning: every part is still in f{f0}..f{f1}: wrong range, or nothing animated')
    rot = [s for s in moving if s['unit'] == 'deg/s']
    sync = []
    if len(rot) >= 3:
        need = max(3, math.ceil(0.75 * len(rot)))
        peaks = []
        for s in rot:
            v, top = s['v'], max(s['v'])
            peaks.append({k for k in range(len(v)) if (k == 0 or v[k] >= v[k - 1]) and (k == len(v) - 1 or v[k] > v[k + 1])
                          and v[k] >= 0.5 * top})
        hit = {}
        for k in range(len(rot[0]['v'])):
            who = [s['name'] for s, ps in zip(rot, peaks) if any(abs(k - p) <= 1 for p in ps)]
            if len(who) >= need:
                hit[k] = who
        for a, b in runs(sorted(hit)):
            who = sorted(set(sum((hit[k] for k in range(a, b + 1)), [])))
            sync.append(dict(kind='sync', f0=f0 + a, f1=f0 + b + 1, parts=who))
            print(f'MC sync   {len(who)}/{len(rot)} rotating parts peak together at f{f0 + a}..f{f0 + b + 1}: '
                  f'{", ".join(n.split(":", 1)[-1] for n in who)}')
    json.dump(dict(fps=fps, f0=f0, f1=f1, series=series, sync=sync), open(out_path, 'w'))
    n = sum(len(s['flags']) for s in series) + len(sync)
    print(f'MC done: {len(series)} parts, f{f0}..f{f1}, {n} flags -> {out_path}')


try:
    main()
except TimelineError as e:
    die(str(e))
