"""Transition generators.

In-world (call them from film.py; they build animated objects and emit sound cues):
  assemble  pieces fly in from a start (scatter / point / below / above / list) into target cells
  scatter   pieces leave their cells (fall to the ground / burst outward / to a list)
  lift      2D pixel plates extrude into voxels, then melt into a smooth object (the dimension ladder)
  grow      cells pop in from a seed, ordered by height or distance (trees, buildings, crystals)
  pop       one object scales in with overshoot
World transitions (applied by Film from timeline.json; the camera moves through a portal surface):
  push_in   A's camera dives into a surface that shows B; at time t the surface fills the frame -> B
  pull_out  B's camera starts filling a surface that shows A and pulls back
Post transitions (cut, fade, iris, lens, breach) are composited in compose.py.

Times are seconds. Free timing everywhere; pass "bar:3" style strings through film.T() if you want the grid.
"""
import math
import random

from mathutils import Quaternion, Vector

from . import anim, camera, geo


def _order(cells, order, origin=None, seed=0):
    """Return a 0..1 rank per cell for stagger."""
    n = len(cells)
    if n == 1:
        return [0.0]
    if isinstance(order, (list, tuple)):
        return list(order)
    rnd = random.Random(seed)
    if order == 'random':
        return [rnd.random() for _ in range(n)]
    axis = {'x': 0, 'y': 1, 'z': 2}
    if order.lstrip('-') in axis:
        k = [c[axis[order.lstrip('-')]] for c in cells]
        if order.startswith('-'):
            k = [-v for v in k]
    elif order == 'dist':
        o = Vector(origin) if origin is not None else sum((Vector(c) for c in cells), Vector()) / n
        k = [(Vector(c) - o).length for c in cells]
    else:
        raise ValueError(f'unknown order "{order}"')
    lo, hi = min(k), max(k)
    return [0.0 if hi - lo < 1e-9 else (v - lo) / (hi - lo) + rnd.uniform(-0.04, 0.04) for v in k]


def _times(cells, t0, dur, stagger, order, origin, seed):
    r = _order(cells, order, origin, seed)
    each = dur * (1 - stagger)
    return [t0 + max(0.0, min(1.0, x)) * dur * stagger for x in r], [each] * len(cells)


def _vec3(s):
    return tuple(s) if hasattr(s, '__len__') else (s, s, s)


def move(w, name, piece, pa, pb, t0s, durs, colors=None, sa=1.0, sb=1.0, ra=None, rb=None, arc=0.0, ease='smoother',
         show=None):
    """Lowest level: one assembly object, explicit per-piece start/end. show=(t0, t1) limits visibility."""
    n = len(pa)
    per = lambda v: list(v) if isinstance(v, list) else [v] * n
    data = dict(pa=[tuple(p) for p in pa], pb=[tuple(p) for p in pb], t0=per(t0s), dur=per(durs),
                sa=[_vec3(s) for s in per(sa)], sb=[_vec3(s) for s in per(sb)],
                ra=[tuple(r) for r in per(ra or (0, 0, 0))], rb=[tuple(r) for r in per(rb or (0, 0, 0))],
                arc=per(arc), col=[_col(w, c) for c in per(colors or '#ffffff')])
    ob = geo.assembly(w.n(name), piece, data, w.coll, ease)
    if show:
        anim.visible(ob, [show])
    return ob


def _col(w, c):
    from .looks import hex2lin
    return hex2lin(c) if isinstance(c, str) else tuple(c) + (1.0,) * (4 - len(c))


def assemble(w, name, piece, cells, t0, dur, colors=None, start='scatter', spread=4.0, point=None, stagger=0.6,
             order='random', arc=0.0, spin=1.0, scale=1.0, start_scale=None, ease='smoother', seed=0, until=None,
             sound='sparkle'):
    """Pieces fly into `cells` (target positions) during [t0, t0 + dur].

    start: 'scatter' (random offsets of size `spread`), 'point' (all from `point`, growing from 0),
           'below' / 'above' (offset in z by spread), or a list of start positions.
    stagger: fraction of dur over which the start times are spread, in `order`
             ('random', 'x', '-x', 'y', 'z', '-z', 'dist' from point/centroid, or a list of 0..1 ranks).
    until: hide the object after this time (when a later stage takes over).
    """
    rnd = random.Random(seed)
    cells = [Vector(c) for c in cells]
    n = len(cells)
    if isinstance(start, (list, tuple)):
        pa = [Vector(p) for p in start]
    elif start == 'scatter':
        pa = [c + Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))) * spread for c in cells]
    elif start == 'point':
        pa = [Vector(point)] * n
    elif start in ('below', 'above'):
        pa = [c + Vector((rnd.uniform(-.2, .2), rnd.uniform(-.2, .2), (-1 if start == 'below' else 1) * spread)) for c in cells]
    else:
        raise ValueError(f'unknown start "{start}"')
    if start_scale is None:
        start_scale = 0.0 if start == 'point' else 0.3
    t0s, durs = _times(cells, t0, dur, stagger, order, point, seed)
    ra = [(rnd.uniform(-3, 3) * spin, rnd.uniform(-3, 3) * spin, rnd.uniform(-3, 3) * spin) for _ in cells]
    sa = [tuple(x * start_scale for x in _vec3(scale))] * n
    ob = move(w, name, piece, pa, cells, t0s, durs, colors, sa, scale, ra, None, arc, ease,
              show=(-1, until) if until is not None else None)
    if sound:
        anim.emit(t0, 'whoosh', gain=0.5, dur=dur)
        for k in range(max(1, int(dur * stagger / 0.09))):
            anim.emit(t0 + 0.09 * k + durs[0] * 0.8, sound, gain=0.35)
        anim.emit(t0 + dur, 'click', gain=0.6)
    return ob


def scatter(w, name, piece, cells, t0, dur, colors=None, to='fall', ground=0.0, spread=3.0, targets=None,
            stagger=0.4, order='random', scale=1.0, end_scale=None, spin=1.0, seed=0, since=None, until=None,
            sound='thump', ease=None):
    """Pieces leave `cells` during [t0, t0 + dur]: 'fall' (gravity to z=ground, spread sideways),
    'burst' (outward from the centroid, shrinking), or to explicit `targets` (ease 'smoother' unless given,
    e.g. ease='gravity' for a fall onto known spots)."""
    rnd = random.Random(seed)
    cells = [Vector(c) for c in cells]
    c0 = sum(cells, Vector()) / len(cells)
    if targets is not None:
        pb = [Vector(p) for p in targets]
        ease = ease or 'smoother'
    elif to == 'fall':
        pb = [Vector((c.x + rnd.uniform(-1, 1) * spread, c.y + rnd.uniform(-1, 1) * spread, ground)) for c in cells]
        ease = ease or 'gravity'
    elif to == 'burst':
        pb = [c + ((c - c0).normalized() if (c - c0).length > 1e-6 else Vector((0, 0, 1))) * spread for c in cells]
        ease = ease or 'rise'
    else:
        raise ValueError(f'unknown scatter "{to}"')
    if end_scale is None:
        end_scale = 0.0 if to == 'burst' else 1.0
    t0s, durs = _times(cells, t0, dur, stagger, order, None, seed)
    rb = [(rnd.uniform(-2, 2) * spin, rnd.uniform(-2, 2) * spin, rnd.uniform(-3, 3) * spin) for _ in cells]
    sb = [tuple(x * end_scale for x in _vec3(scale))] * len(cells)
    show = None
    if since is not None or until is not None:
        show = (since if since is not None else -1, until if until is not None else 1e6)
    ob = move(w, name, piece, cells, pb, t0s, durs, colors, scale, sb, None, rb, 0.0, ease, show=show)
    if sound:
        for k, t in enumerate(sorted(t + d for t, d in zip(t0s, durs))[::math.ceil(len(cells) / 8)]):   # at most 8
            anim.emit(t, sound, gain=0.4, pan=rnd.uniform(-.5, .5))
    return ob


def lift(w, name, piece, cells, t0, dur, colors=None, cell=1.0, plate=0.12, axis=(0, -1, 0), then=None,
         melt=0.35, order='dist', seed=0, since=None, sound='riser'):
    """Dimension ladder. Flat plates at `cells` extrude along `axis` into cubes, then (if `then` is given)
    the cubes melt away while `then` pops in with overshoot.

    cells are the plate centres (as left by assemble with scale (cell, plate*cell, cell) for axis -Y).
    The back face stays put: cubes grow toward `axis`.
    Returns (voxels_object, melt_object or None)."""
    ax = Vector(axis).normalized()
    cells = [Vector(c) for c in cells]
    n = len(cells)
    thin = [cell * (plate if abs(ax[i]) > .5 else 1.0) for i in range(3)]
    full = (cell, cell, cell)
    back = [c - ax * (plate * cell / 2) for c in cells]           # back faces
    pa = [b + ax * (plate * cell / 2) for b in back]
    pb = [b + ax * (cell / 2) for b in back]
    t_ext = dur * (1 - melt) if then is not None else dur
    t0s, durs = _times(cells, t0, t_ext, 0.5, order, None, seed)
    vox_end = t0 + t_ext
    vox = move(w, f'{name}.vox', piece, pa, pb, t0s, durs, colors, [tuple(thin)] * n, [full] * n, ease='smoother',
               show=(t0 if since is None else since, vox_end + 0.02) if then is not None else (t0 if since is None else since, 1e6))
    anim.emit(t0, sound, gain=0.5, dur=t_ext)
    out = None
    if then is not None:
        tm = vox_end
        mt0s, mdurs = _times(cells, tm, dur * melt, 0.5, 'random', None, seed + 1)
        out = move(w, f'{name}.melt', piece, pb, pb, mt0s, mdurs, colors, [full] * n, [(0, 0, 0)] * n,
                   ease='smooth', show=(tm, tm + dur * melt + 0.05))
        pop(then, tm, dur * melt + 0.1)
        anim.emit(tm, 'pop', gain=0.8)
    return vox, out


def grow(w, name, piece, cells, t0, dur, colors=None, seed_point=None, order='z', stagger=0.85, scale=1.0,
         rise=0.0, sound='pop', seed=0):
    """Cells scale in from 0 at their place (optionally rising by `rise`), ordered by 'z' or 'dist' from
    seed_point. A tree, a city block, a crystal."""
    cells = [Vector(c) for c in cells]
    t0s, durs = _times(cells, t0, dur, stagger, order, seed_point, seed)
    pa = [c - Vector((0, 0, rise)) for c in cells]
    ob = move(w, name, piece, pa, cells, t0s, durs, colors, 0.0, scale, None, None, 0.0, 'smoother')
    if sound:
        k = max(1, len(cells) // 10)
        for t in sorted(t0s)[::k]:
            anim.emit(t, sound, gain=0.25)
    return ob


def pop(ob, t, dur=0.35, start=0.0, sound=None):
    """Scale an object in from `start` (fraction) to its current scale with overshoot; hidden before t."""
    s = tuple(ob.scale)
    anim.key(ob, 'scale', [(t, tuple(x * start for x in s)), (t + dur, s, 'back')])
    if start == 0.0:
        anim.visible(ob, [(t, 1e6)])
    if sound:
        anim.emit(t, sound)
    return ob


# ---------------- world transitions ----------------
def apply_world(film, tr):
    """Bake the camera move of a push_in / pull_out and register the portal surface."""
    inner, outer = (tr.b, tr.a) if tr.type == 'push_in' else (tr.a, tr.b)
    wo = film.world_of(outer)
    surf = wo[tr.surface] if not tr.surface.startswith(wo.name + '.') else film.obj(tr.surface)
    cam = film.cam(outer)
    sc = wo.scene
    aspect = film.tl.size[0] / film.tl.size[1]
    pc, qc, d = camera.cover_pose(cam, surf, aspect, film.F(tr.t))
    C = camera.surface_frame(surf, aspect, f=film.F(tr.t))['center']
    if tr.type == 'push_in':
        ta, tb = tr.t - tr.dur, tr.t
        ref = ta
    else:
        ta, tb = tr.t, tr.t + tr.dur
        ref = tb
    ce, _ = camera.eval_obj(sc, cam, film.F(ref))
    p0 = ce.matrix_world.translation.copy()
    q0 = ce.matrix_world.to_quaternion()
    if cam.rotation_mode == 'QUATERNION' and anim.find_fcurve(cam, 'rotation_quaternion'):
        if q0.dot(Quaternion(anim.value_at(cam, 'rotation_quaternion', ref, 4))) < 0:
            q0 = -q0                                    # same sign as the keys we join (motion blur interpolates keys)
    sx0, sy0 = ce.data.shift_x, ce.data.shift_y
    r0, r1 = max((p0 - C).length, 1e-6), d
    u0, u1 = (p0 - C).normalized(), (pc - C).normalized()
    du = u0.rotation_difference(u1)
    if q0.dot(qc) < 0:
        qc = -qc
    e_pos = tr.opts.get('ease', 'inout')                # ends at rest: no motion blur at the switch
    rev = tr.type == 'pull_out'

    def s_of(t):                                        # 0 = own pose, 1 = cover pose
        x = (t - ta) / (tb - ta) if tb > ta else 1.0
        return 1 - x if rev else x

    def pos(t):
        e = anim.ease(e_pos, s_of(t))
        u = Quaternion().slerp(du, e) @ u0
        return C + u * math.exp(anim.lerp(math.log(r0), math.log(r1), e))

    def rot(t):                                         # at rest at both ends; faces the surface before the cover
        return q0.slerp(qc, anim.ease('smooth', s_of(t) / 0.75))

    anim.bake(cam, 'location', ta, tb, pos)
    anim.bake(cam, 'rotation_quaternion', ta, tb, rot)
    anim.bake(cam.data, 'shift_x', ta, tb, lambda t: sx0 * (1 - anim.ease('smooth', s_of(t))))
    anim.bake(cam.data, 'shift_y', ta, tb, lambda t: sy0 * (1 - anim.ease('smooth', s_of(t))))
    if cam.data.dof.use_dof:
        if cam.data.dof.focus_object is not None:
            raise ValueError(f'{cam.name}: {tr.type} needs dof.focus_distance, not dof.focus_object')
        fd = ce.data.dof.focus_distance
        anim.bake(cam.data, 'dof.focus_distance', ta, tb,
                  lambda t: anim.lerp(fd, max(0.01, (pos(t) - C).length), anim.ease('smooth', s_of(t))))
    if tr.type == 'push_in':                            # hold the cover pose until A is no longer needed
        anim.key(cam, 'location', [(tb, tuple(pc)), (tb + 1.0, tuple(pc))])
        anim.key(cam, 'rotation_quaternion', [(tb, tuple(qc)), (tb + 1.0, tuple(qc))])
    fade = tr.opts.get('fade', tr.dur * 0.45 if tr.type == 'push_in' else 0.0)
    film.portal(surf, inner.id, since=ta, until=tb, fade=(ta, ta + fade) if fade else None, _cover=(cam, outer.id))
    if tr.type == 'push_in':
        anim.emit(ta, 'riser', gain=0.6, dur=tr.dur)
        anim.emit(tb - 0.05, 'whoosh', gain=0.8, dur=0.5)
    else:
        anim.emit(ta, 'whoosh', gain=0.7, dur=0.6)
        anim.emit(ta, 'swell', gain=0.5, dur=tr.dur)
