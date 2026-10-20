"""Cameras: aimed paths, orbits, the cover pose of a portal surface, and screen positions (NDC).

Cameras use quaternion rotation and are not parented. NDC: x right, y up, both 0..1 over the frame.
Lens shift moves the picture: +shift_x moves content left by shift_x in NDC; +shift_y moves it down by
shift_y * W / H (sensor fit is horizontal for landscape frames).
"""
import math

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Quaternion, Vector

from . import anim


def look_q(loc, target, roll=0.0):
    d = Vector(target) - Vector(loc)
    if d.length < 1e-9:
        return Quaternion()
    q = d.to_track_quat('-Z', 'Y')
    if roll:
        q = q @ Quaternion((0, 0, 1), math.radians(roll))
    return q


def make(world, shot, lens=35.0, loc=(0, -10, 2), target=(0, 0, 0), clip=(0.01, 500.0)):
    name = world.n(f'cam.{shot}')
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.sensor_width = 36.0
    cd.sensor_fit = 'HORIZONTAL'
    cd.clip_start, cd.clip_end = clip
    ob = bpy.data.objects.new(name, cd)
    world.coll.objects.link(ob)
    ob.rotation_mode = 'QUATERNION'
    ob.location = loc
    ob.rotation_quaternion = look_q(loc, target)
    return ob


def path(cam, keys, ease='inout'):
    """keys: [(t, loc, target[, ease_into_key[, roll]])]. Location and aim point are eased between keys;
    the rotation is recomputed every frame so the aim point stays exactly framed."""
    keys = sorted(keys, key=lambda k: k[0])
    if len(keys) == 1:
        t, loc, tgt = keys[0][:3]
        anim.key(cam, 'location', [(t, loc)])
        anim.key(cam, 'rotation_quaternion', [(t, look_q(loc, tgt, keys[0][4] if len(keys[0]) > 4 else 0))])
        return

    def at(t):
        j = 0
        while j < len(keys) - 2 and t > keys[j + 1][0]:
            j += 1
        a, b = keys[j], keys[j + 1]
        x = 0.0 if b[0] <= a[0] else (t - a[0]) / (b[0] - a[0])
        e = anim.ease(b[3] if len(b) > 3 and b[3] else ease, x)
        loc = Vector(a[1]).lerp(Vector(b[1]), e)
        tgt = Vector(a[2]).lerp(Vector(b[2]), e)
        roll = anim.lerp(a[4] if len(a) > 4 else 0.0, b[4] if len(b) > 4 else 0.0, e)
        return loc, look_q(loc, tgt, roll)
    t0, t1 = keys[0][0], keys[-1][0]
    anim.bake(cam, 'location', t0, t1, lambda t: at(t)[0])
    qs = {}

    def rot(t):
        q = at(t)[1]
        prev = qs.get('p')
        if prev is not None and q.dot(prev) < 0:
            q = -q
        qs['p'] = q
        return q
    anim.bake(cam, 'rotation_quaternion', t0, t1, rot)


def orbit(cam, center, t0, t1, radius, az=(0, 90), el=(15, 15), ease='inout', target=None):
    """Circle around center: azimuth/elevation in degrees (azimuth 0 = camera on -Y looking +Y)."""
    c = Vector(center)
    tg = Vector(target) if target is not None else c

    def loc(t):
        e = anim.ease(ease, (t - t0) / (t1 - t0) if t1 > t0 else 1)
        a = math.radians(anim.lerp(az[0], az[1], e))
        h = math.radians(anim.lerp(el[0], el[1], e))
        return c + Vector((math.sin(a) * math.cos(h), -math.cos(a) * math.cos(h), math.sin(h))) * radius
    anim.bake(cam, 'location', t0, t1, loc)
    anim.bake(cam, 'rotation_quaternion', t0, t1, lambda t: look_q(loc(t), tg))


def hfov_tan(cam_data):
    """tan(horizontal fov / 2) for a horizontal-fit perspective camera."""
    return cam_data.sensor_width / (2.0 * cam_data.lens)


def world_matrix(ob, f=None):
    """Evaluated world matrix of an object in its own scene (the original's matrix_world is only kept
    up to date for the active scene, so never read it directly)."""
    sc = ob.users_scene[0]
    if f is not None:
        sc.frame_set(f)
    dg = sc.view_layers[0].depsgraph
    dg.update()
    return ob.evaluated_get(dg).matrix_world.copy()


def surface_frame(surface, aspect, margin=0.995, f=None):
    """The largest frame-shaped rectangle inside a planar surface (local XY plane, normal +Z).

    Returns dict(center, normal, rot, wf, hf, lo, sx, sy): world centre and normal, world rotation (quaternion),
    the frame rectangle size on the surface in world units, and what is needed to compute UVs in local space.
    """
    if surface is None or surface.type != 'MESH' or not len(surface.data.vertices):
        name = getattr(surface, 'name', surface)
        raise ValueError(f'{name}: a portal surface must be a flat mesh (e.g. shapes.plane or monitor ".screen"), '
                         f'not {getattr(surface, "type", "nothing")}')
    me = surface.data
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    if max(zs) - min(zs) > 1e-5 * max(1e-6, max(xs) - min(xs)):
        raise ValueError(f'{surface.name}: portal surface must be flat in its local XY plane')
    mw = world_matrix(surface, f)
    loc, rot, scl = mw.decompose()
    ws, hs = (max(xs) - min(xs)) * scl.x, (max(ys) - min(ys)) * scl.y
    wf = margin * min(ws, hs * aspect)
    lo = Vector(((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, 0))
    center = mw @ lo
    normal = (rot @ Vector((0, 0, 1))).normalized()
    return dict(center=center, normal=normal, rot=rot, wf=wf, hf=wf / aspect, lo=lo, sx=scl.x, sy=scl.y, mw=mw)


def cover_pose(cam, surface, aspect, f=None):
    """Camera pose whose frame is exactly the surface's frame rectangle (no lens shift).
    The surface must not move while a transition uses it."""
    sf = surface_frame(surface, aspect, f=f)
    d = sf['wf'] / (2.0 * hfov_tan(cam.data))
    return sf['center'] + sf['normal'] * d, sf['rot'].copy(), d


def eval_obj(scene, ob, f):
    scene.frame_set(f)
    dg = scene.view_layers[0].depsgraph
    return ob.evaluated_get(dg), dg


def anchor_point(ob_eval):
    """World point that represents an object on screen: bbox centre for plain meshes, origin otherwise."""
    if ob_eval.type == 'MESH' and not any(m.type == 'NODES' for m in ob_eval.modifiers):
        pts = [ob_eval.matrix_world @ Vector(c) for c in ob_eval.bound_box]
        return sum(pts, Vector()) / 8.0
    return ob_eval.matrix_world.translation.copy()


def ndc(scene, cam, point, f):
    """NDC (x, y) of a world point (or an object's anchor point) seen by cam at frame f."""
    scene.frame_set(f)
    dg = scene.view_layers[0].depsgraph
    ce = cam.evaluated_get(dg)
    if isinstance(point, bpy.types.Object):
        point = anchor_point(point.evaluated_get(dg))
    v = world_to_camera_view(scene, ce, Vector(point))
    return v.x, v.y, v.z
