"""Shapes built with bmesh (no bpy.ops, so nothing depends on the active scene).

Every function takes the World first, names the object "<world>.<name>", gives it a material of the world's
look and lets the look finish it (bevel, flat shading, outline). Boxes, the hero and keycaps have their origin
at the bottom centre, so scale animations squash against the floor.
"""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


def _obj(w, name, bm, coll=None):
    me = bpy.data.meshes.new(w.n(name))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(w.n(name), me)
    (coll or w.coll).objects.link(ob)
    return ob


def _place(ob, loc, rot, scale=None):
    ob.location = loc
    ob.rotation_euler = [math.radians(a) for a in rot]
    if scale is not None:
        ob.scale = scale if hasattr(scale, '__len__') else (scale,) * 3
    return ob


def _paint(w, ob, color, kind, bevel, attr=None):
    ob.data.materials.append(w.mat(color, kind, attr))
    w.look.finish(ob, kind, bevel)
    return ob


def box(w, name, size=(1, 1, 1), loc=(0, 0, 0), rot=(0, 0, 0), color='#cccccc', kind='body', origin='bottom',
        bevel=None, coll=None):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    off = size[2] / 2 if origin == 'bottom' else 0.0
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2] + off))
    return _paint(w, _place(_obj(w, name, bm, coll), loc, rot), color, kind, bevel)


def sphere(w, name, r=0.5, loc=(0, 0, 0), rot=(0, 0, 0), color='#cccccc', kind='body', segs=32, scale=None, coll=None):
    bm = bmesh.new()
    s = w.look.segments(segs)
    bmesh.ops.create_uvsphere(bm, u_segments=s, v_segments=max(3, s // 2), radius=r)
    return _paint(w, _place(_obj(w, name, bm, coll), loc, rot, scale), color, kind, 0.0)


def cyl(w, name, r=0.5, h=1.0, loc=(0, 0, 0), rot=(0, 0, 0), color='#cccccc', kind='body', segs=32, r2=None,
        origin='bottom', bevel=None, coll=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=w.look.segments(segs), radius1=r,
                          radius2=r if r2 is None else r2, depth=h)
    if origin == 'bottom':
        for v in bm.verts:
            v.co.z += h / 2
    return _paint(w, _place(_obj(w, name, bm, coll), loc, rot), color, kind, bevel)


def plane(w, name, size=(1, 1), loc=(0, 0, 0), rot=(0, 0, 0), color='#cccccc', kind='body', coll=None):
    """Flat quad in local XY (normal +Z), centred on its origin. Portal surfaces must be planes like this."""
    bm = bmesh.new()
    hx, hy = size[0] / 2, size[1] / 2
    vs = [bm.verts.new(p) for p in ((-hx, -hy, 0), (hx, -hy, 0), (hx, hy, 0), (-hx, hy, 0))]
    bm.faces.new(vs)
    ob = _place(_obj(w, name, bm, coll), loc, rot)
    if color is not None:
        _paint(w, ob, color, kind, 0.0)
    return ob


def disc(w, name, r=1.0, loc=(0, 0, 0), rot=(0, 0, 0), color='#cccccc', kind='ground', segs=64, coll=None):
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, segments=w.look.segments(segs), radius=r)
    return _paint(w, _place(_obj(w, name, bm, coll), loc, rot), color, kind, 0.0)


def text(w, name, body, size=1.0, loc=(0, 0, 0), rot=(90, 0, 0), color='#ffffff', kind='emit', font=None,
         extrude=0.0, align='LEFT', strength=None, coll=None):
    """Text object. Default font is Blender's built-in (Latin only); pass font=path for CJK, e.g.
    /System/Library/Fonts/PingFang.ttc on macOS."""
    cu = bpy.data.curves.new(w.n(name), 'FONT')
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.align_x = align
    if font:
        cu.font = bpy.data.fonts.load(font, check_existing=True)
    ob = bpy.data.objects.new(w.n(name), cu)
    (coll or w.coll).objects.link(ob)
    _place(ob, loc, rot)
    cu.materials.append(w.mat(color, kind, strength=strength))
    return ob


# ---------------- hero ----------------
HERO_PIXELS = [            # front view, 8 x 7; Y body, K eye
    '.YYYYYY.',
    'YYYYYYYY',
    'YYKYYKYY',
    'YYKYYKYY',
    'YYYYYYYY',
    'YYYYYYYY',
    '.YYYYYY.',
]


def hero(w, name='hero', color='#F2C230', size=1.0, loc=(0, 0, 0), rot=(0, 0, 0), eye='#15161a', coll=None):
    """A generic mascot: soft rounded cube with two dot eyes on its front (-Y) face. Origin at the bottom.
    Returns the body; the eyes are children named <name>.eyeL / <name>.eyeR (for blinks)."""
    b = box(w, name, (1.0 * size, 0.9 * size, 0.9 * size), loc, rot, color, 'body', 'bottom', bevel=0.28, coll=coll)
    for side, x in (('L', -0.2), ('R', 0.2)):
        e = sphere(w, f'{name}.eye{side}', 0.075 * size, (x * size, -0.452 * size, 0.55 * size), color=eye,
                   kind='dark', segs=16, scale=(1.0, 0.35, 1.3), coll=coll)
        e.parent = b
    return b


def hero_piece(w, name='hero.piece', size=1.0, attr='col'):
    """The hero as one mesh in the world's hidden parts collection, for assembly pieces and clones.
    Body colour comes from the instancer attribute `attr` (per piece)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size, v.co.y * 0.9 * size, v.co.z * 0.9 * size + 0.45 * size))
    bmesh.ops.bevel(bm, geom=list(bm.verts) + list(bm.edges), offset=0.25 * 0.9 * size, segments=4,
                    affect='EDGES', profile=0.5)
    for f in bm.faces:
        f.smooth = True
    for x in (-0.2, 0.2):
        r = bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=6, radius=0.075 * size)
        for v in r['verts']:
            v.co = Vector((v.co.x + x * size, v.co.y * 0.35 - 0.452 * size, v.co.z * 1.3 + 0.55 * size))
        for f in {f for v in r['verts'] for f in v.link_faces}:
            f.material_index = 1
            f.smooth = True
    ob = _obj(w, name, bm, w.parts)
    ob.data.materials.append(w.mat('#ffffff', 'body', attr))
    ob.data.materials.append(w.mat('#15161a', 'dark'))
    return ob


def cube_piece(w, name='voxel', size=1.0, attr='col', kind='body', bevel=0.08, flat=None):
    """A unit cube centred on its origin in the parts collection, coloured per piece by `attr`.
    flat: thickness along Y for a pixel plate (None = cube)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    if flat:
        for v in bm.verts:
            v.co.y *= flat
    if bevel:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel * size * (flat or 1.0), segments=2, affect='EDGES')
    ob = _obj(w, name, bm, w.parts)
    ob.data.materials.append(w.mat('#ffffff', kind, attr))
    return ob


def pixels(rows, palette, cell=1.0, origin='center'):
    """ASCII art -> cells [(x, z, colour)], first row on top, in the XZ plane (front view from -Y).
    palette maps characters to colours; '.' and ' ' are empty."""
    h, wd = len(rows), max(len(r) for r in rows)
    out = []
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch in '. ':
                continue
            x = (i - (wd - 1) / 2) * cell
            z = ((h - 1) / 2 - j) * cell if origin == 'center' else (h - 1 - j) * cell
            out.append((x, z, palette[ch]))
    return out


def voxelize(w, ob, step):
    """Points on a grid of `step` that lie inside a closed mesh of world w (ray parity test), world space."""
    dg = w.scene.view_layers[0].depsgraph
    dg.update()
    tree = BVHTree.FromObject(ob, dg)
    mw = ob.evaluated_get(dg).matrix_world.copy()
    bb = [mw @ Vector(c) for c in ob.evaluated_get(dg).bound_box]
    lo = Vector([min(p[i] for p in bb) for i in range(3)])
    hi = Vector([max(p[i] for p in bb) for i in range(3)])
    inv = mw.inverted()
    out = []
    n = [max(1, int((hi[i] - lo[i]) / step)) for i in range(3)]
    for i in range(n[0]):
        for j in range(n[1]):
            for k in range(n[2]):
                p = lo + Vector(((i + .5) * step, (j + .5) * step, (k + .5) * step))
                q = inv @ p
                hits, o = 0, q.copy()
                while True:
                    loc, nrm, idx, dist = tree.ray_cast(o, Vector((0.0, 0.0, 1.0)))
                    if loc is None:
                        break
                    hits += 1
                    o = loc + Vector((0, 0, 1e-5))
                if hits % 2 == 1:
                    out.append(p)
    return out


# ---------------- props ----------------
def monitor(w, name='monitor', width=1.0, loc=(0, 0, 0), rot=(0, 0, 0), color='#2b2d33'):
    """A monitor on a stand. Its screen is a 16:9 plane named <name>.screen facing -Y (a portal surface).
    Returns (monitor_root, screen)."""
    sw, sh = width, width * 9 / 16
    border, depth = 0.04 * width, 0.05 * width
    lift = 0.35 * width
    root = w.empty(name, loc)
    root.rotation_euler = [math.radians(a) for a in rot]
    bez = box(w, f'{name}.bezel', (sw + 2 * border, depth, sh + 2 * border), (0, 0, lift), color=color, kind='dark',
              bevel=0.15)
    neck = box(w, f'{name}.neck', (0.08 * width, 0.05 * width, lift), (0, 0.03 * width, 0), color=color, kind='dark')
    base = box(w, f'{name}.base', (0.36 * width, 0.22 * width, 0.02 * width), (0, 0.03 * width, 0), color=color,
               kind='dark', bevel=0.3)
    scr = plane(w, f'{name}.screen', (sw, sh), (0, -depth / 2 - 0.0015 * width, lift + sh / 2 + border), (90, 0, 0),
                color='#05070a', kind='screen')
    for o in (bez, neck, base, scr):
        o.parent = root
    return root, scr


def keyboard(w, name='kb', cols=12, rows=4, u=0.19, loc=(0, 0, 0), color='#e9e5dc', key='#f7f4ee',
             glass=None, glass_u=16 / 9):
    """A keyboard. glass=(row, col): that key is a wide glass key (glass_u keys wide) with a 16:9 portal plane
    <name>.glass.top on its top. Returns dict(root, keys, glass, top)."""
    gap = 0.12 * u
    depth = rows * u + 2 * gap
    width = cols * u + 2 * gap
    root = w.empty(name, loc)
    base = box(w, f'{name}.base', (width, depth, 0.25 * u), (0, 0, 0), color=color, kind='body', bevel=0.2)
    base.parent = root
    keys, gl, top = [], None, None
    kh = 0.38 * u
    for r in range(rows):
        c = 0
        while c < cols:
            wide = glass is not None and (r, c) == tuple(glass)
            span = glass_u if wide else 1.0
            if c + span > cols + 1e-6:
                break
            x = -width / 2 + gap + (c + span / 2) * u
            y = depth / 2 - gap - (r + .5) * u
            kw, kd = span * u - gap, u - gap
            if wide:
                gl = box(w, f'{name}.glass', (kw, kd, kh), (x, y, 0.25 * u), color='#e8f3ff', kind='glass', bevel=0.12)
                gl.parent = root
                top = plane(w, f'{name}.glass.top', (kw * 0.92, kw * 0.92 * 9 / 16), (x, y, 0.25 * u + kh + 0.001 * u),
                            color=None)
                top.parent = root
            else:
                k = box(w, f'{name}.key{r}_{c}', (kw, kd, kh), (x, y, 0.25 * u), color=key, kind='body', bevel=0.18)
                k.parent = root
                keys.append(k)
            c += int(math.ceil(span - 1e-6)) if wide else 1
    return dict(root=root, keys=keys, glass=gl, top=top, height=0.25 * u + kh)


def blade_piece(w, name='blade', h=0.25, wd=0.03, color='#4f9a34'):
    """An upright tapered grass blade in the parts collection (for geo.scatter)."""
    bm = bmesh.new()
    v = [bm.verts.new(p) for p in ((-wd / 2, 0, 0), (wd / 2, 0, 0), (wd * .15, 0.01, h * .6), (0, 0.03, h))]
    bm.faces.new((v[0], v[1], v[2]))
    bm.faces.new((v[0], v[2], v[3]))
    ob = _obj(w, name, bm, w.parts)
    ob.data.materials.append(w.mat(color, 'ground'))
    return ob


def tree_cells(base=(0, 0, 0), height=3.0, canopy=1.6, step=0.25, trunk='#7a5232', leaves=('#3f8f3a', '#5aa845', '#2f7a33'),
               seed=1):
    """Voxel tree as cells [(pos, colour)]: a trunk column and a lumpy canopy ball."""
    rnd = random.Random(seed)
    b = Vector(base)
    out = []
    tw = max(1, int(round(0.35 / step)))
    for k in range(int(height / step)):
        for i in range(tw):
            for j in range(tw):
                out.append((b + Vector(((i - (tw - 1) / 2) * step, (j - (tw - 1) / 2) * step, (k + .5) * step)), trunk))
    c = b + Vector((0, 0, height + canopy * 0.55))
    n = int(canopy / step) + 1
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            for k in range(-n, n + 1):
                p = Vector((i, j, k)) * step
                wob = 1 + 0.18 * math.sin(i * 1.7 + seed) * math.cos(j * 1.3) + 0.1 * math.sin(k * 2.1)
                if p.length < canopy * wob and (p.length > canopy * wob - 2.2 * step or rnd.random() < 0.15):
                    out.append((c + p, rnd.choice(leaves)))
    return out
