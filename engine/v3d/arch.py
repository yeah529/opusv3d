"""Architecture builders for realistic scenes: blocks, cut openings, windows, doors, louvres, railings,
lattice gates, hip roofs with tile rows, pipes. Units are metres; Z is up. Built with bmesh (no bpy.ops).

Bounds are (x0, x1, y0, y1, z0, z1). A facade is one side of a block, named by its outward normal:
'-y' '+y' '-x' '+x'. facade(b, side, u, z) returns the matrix of a facade frame: origin on the wall surface,
u metres from the facade's left end (as seen from outside), z metres above the block's base; local +X runs
right, +Z up, -Y points out of the wall (into the wall is +Y). window(), door() and louver() build in that
frame and return the cutter box that carve() cuts out of the wall.

Every mesh gets a UV map in metres (box projection) unless it writes its own; materials.pbr() textures use it.
"""
import math

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

ROT = {'-y': 0.0, '+x': 90.0, '+y': 180.0, '-x': -90.0}
_FACES = ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5))


# ---- mesh basics ----
def _need(mats, keys, who):
    gone = [k for k in keys if k not in mats]
    if gone:
        raise KeyError(f'{who}: mats needs {", ".join(keys)}; missing {", ".join(gone)}')


def uv_box(me):
    """UVs in metres: each face is projected along its dominant normal axis."""
    uv = me.uv_layers.get('UVMap') or me.uv_layers.new(name='UVMap')
    vs, out = me.vertices, []
    for p in me.polygons:
        n = p.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in p.loop_indices:
            c = vs[me.loops[li].vertex_index].co
            out += (c.x, c.y) if ax == 2 else (c.x, c.z) if ax == 1 else (c.y, c.z)
    uv.data.foreach_set('uv', out)


def cube(bm, b, mat=0, M=None):
    """Add a box with bounds b (in the frame M, if given) to bm."""
    x0, x1, y0, y1, z0, z1 = b
    vs = []
    for i in range(8):
        co = Vector(((x0, x1)[i & 1], (y0, y1)[(i >> 1) & 1], (z0, z1)[(i >> 2) & 1]))
        vs.append(bm.verts.new(M @ co if M is not None else co))
    for f in _FACES:
        bm.faces.new([vs[i] for i in f]).material_index = mat
    return vs


def cyl(bm, p0, p1, r, mat=0, segs=12, r1=None):
    """Add a (capped) cylinder from p0 to p1 to bm."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    if d.length < 1e-6:
        return
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    M = Matrix.Translation((p0 + p1) / 2) @ rot
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=r if r1 is None else r1,
                                depth=d.length, matrix=M)
    for v in res['verts']:
        for f in v.link_faces:
            f.material_index = mat


def mesh(w, name, bm, mats, coll=None, bevel=0.0, uv=True, smooth=False):
    """Object "<world>.<name>" from bm with material slots mats (face material_index picks one)."""
    me = bpy.data.meshes.new(w.n(name))
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    for m in (mats if isinstance(mats, (list, tuple)) else [mats]):
        me.materials.append(m)
    if uv:
        uv_box(me)
    if smooth:
        me.shade_smooth()
    ob = bpy.data.objects.new(w.n(name), me)
    (coll or w.coll).objects.link(ob)
    if bevel:
        add_bevel(ob, bevel)
    return ob


def add_bevel(ob, width, segments=2):
    """Rounded edges that catch light (render-time modifier, sharp edges only)."""
    m = ob.modifiers.new('bevel', 'BEVEL')
    m.width, m.segments = width, segments
    m.limit_method = 'ANGLE'
    m.angle_limit = math.radians(35)
    m.harden_normals = True
    return m


def block(w, name, b, mat, bevel=0.0, coll=None):
    bm = bmesh.new()
    cube(bm, b)
    return mesh(w, name, bm, mat, coll, bevel)


def carve(w, ob, boxes, mat=None):
    """Cut boxes out of ob with an exact boolean and keep the result as plain mesh data.
    boxes: bounds in ob's local space, or (bounds, matrix) pairs (as returned by window/door/louver).
    mat: material of the new cut faces (e.g. a dark 'room' for window recesses)."""
    if not boxes:
        return ob
    bm = bmesh.new()
    for b in boxes:
        if len(b) == 2:
            cube(bm, b[0], 0, b[1])
        else:
            cube(bm, b)
    cme = bpy.data.meshes.new('_cut')
    bm.to_mesh(cme)
    bm.free()
    if mat is not None:
        cme.materials.append(mat)
    cut = bpy.data.objects.new('_cut', cme)
    cut.matrix_world = ob.matrix_world
    w.coll.objects.link(cut)
    mod = ob.modifiers.new('_cut', 'BOOLEAN')
    mod.operation, mod.solver, mod.object = 'DIFFERENCE', 'EXACT', cut
    mod.material_mode = 'TRANSFER'
    ob.modifiers.move(ob.modifiers.find(mod.name), 0)  # the cut goes before any bevel
    others = [(m, m.show_viewport) for m in ob.modifiers if m != mod]
    for m, _ in others:
        m.show_viewport = False
    dg = w.scene.view_layers[0].depsgraph
    dg.update()
    new = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    for m, s in others:
        m.show_viewport = s
    ob.modifiers.remove(mod)
    old = ob.data
    ob.data = new
    nm = old.name
    bpy.data.meshes.remove(old)
    new.name = nm
    bpy.data.objects.remove(cut)
    bpy.data.meshes.remove(cme)
    uv_box(new)
    return ob


def facade(b, side, u, z=0.0):
    x0, x1, y0, y1, z0, _ = b
    o = {'-y': (x0 + u, y0), '+y': (x1 - u, y1), '+x': (x1, y0 + u), '-x': (x0, y1 - u)}[side]
    return Matrix.LocRotScale((o[0], o[1], z0 + z), Euler((0, 0, math.radians(ROT[side]))), None)


# ---- openings ----
def _frame4(bm, x0, x1, z0, z1, f, y0, y1, mat):
    cube(bm, (x0, x0 + f, y0, y1, z0, z1), mat)
    cube(bm, (x1 - f, x1, y0, y1, z0, z1), mat)
    cube(bm, (x0 + f, x1 - f, y0, y1, z0, z0 + f), mat)
    cube(bm, (x0 + f, x1 - f, y0, y1, z1 - f, z1), mat)


def _curtain(bm, x0, x1, z0, z1, y, mat, fold=0.11, amp=0.022):
    n = max(2, int((x1 - x0) / (fold / 4)))
    rows = []
    for z in (z0, z1):
        rows.append([bm.verts.new((x0 + (x1 - x0) * i / n, y + amp * math.sin(2 * math.pi * (x0 + (x1 - x0) * i / n) / fold), z))
                     for i in range(n + 1)])
    for i in range(n):
        bm.faces.new((rows[0][i], rows[0][i + 1], rows[1][i + 1], rows[1][i])).material_index = mat


def window(w, name, M, W, H, mats, kind='slide', depth=0.45, curtains=(0.3, 0.2), grille=False, sill=True,
           coll=None):
    """A window in facade frame M, opening W x H (bottom at the frame origin).
    mats: dict frame, glass, fabric (curtains), sill. kind: 'slide' (two sashes) or 'fixed'.
    curtains: (left, right) fractions of the width covered, or None. grille: outside vertical bars.
    Returns (cutter bounds, M) for carve()."""
    _need(mats, ('frame', 'glass'), 'window')
    bm = bmesh.new()
    F, G, C, S = 0, 1, 2, 3
    f, x0, x1 = 0.045, -W / 2, W / 2
    _frame4(bm, x0, x1, 0, H, f, 0.03, 0.12, F)
    if kind == 'slide':
        mid, s = 0.0, 0.035
        for (a, b), (ya, yb) in (((x0 + f, mid + 0.02), (0.05, 0.08)), ((mid - 0.02, x1 - f), (0.085, 0.115))):
            _frame4(bm, a, b, f, H - f, s, ya, yb, F)
            cube(bm, (a + s, b - s, (ya + yb) / 2 - 0.003, (ya + yb) / 2 + 0.003, f + s, H - f - s), G)
    else:
        cube(bm, (x0 + f, x1 - f, 0.072, 0.078, f, H - f), G)
    if curtains:
        cl, cr = curtains
        if cl:
            _curtain(bm, x0 + f, x0 + f + (W - 2 * f) * cl, 0.04, H - 0.03, 0.24, C)
        if cr:
            _curtain(bm, x1 - f - (W - 2 * f) * cr, x1 - f, 0.04, H - 0.03, 0.24, C)
    if sill:
        cube(bm, (x0 - 0.05, x1 + 0.05, -0.07, 0.03, -0.035, 0.0), S)
    if grille:
        n = max(2, int(W / 0.1))
        for i in range(1, n):
            x = x0 + W * i / n
            cube(bm, (x - 0.008, x + 0.008, -0.075, -0.06, 0.02, H - 0.02), F)
        for z in (0.03, H - 0.03):
            cube(bm, (x0 + 0.01, x1 - 0.01, -0.08, -0.055, z - 0.012, z + 0.012), F)
    me_mats = [mats['frame'], mats['glass'], mats.get('fabric', mats['frame']), mats.get('sill', mats['frame'])]
    for v in bm.verts:
        v.co = M @ v.co
    mesh(w, name, bm, me_mats, coll, bevel=0.004)
    return ((x0, x1, -0.02, depth, 0.0, H), M)


def door(w, name, M, W, H, mats, side=0.32, coll=None):
    """Front door (slab + battens + long bar handle) with a frosted side light on the right.
    mats: dict wood, frame, metal, frosted. Returns the cutter for carve()."""
    _need(mats, ('wood', 'frame', 'metal', 'frosted'), 'door')
    bm = bmesh.new()
    WD, FR, ME, FG = 0, 1, 2, 3
    Wt, f = W + side, 0.06
    x0, x1 = -Wt / 2, Wt / 2
    _frame4(bm, x0, x1, 0, H, f, 0.02, 0.16, FR)
    dx0, dx1 = x0 + f, x0 + f + W
    cube(bm, (dx1, dx1 + f, 0.02, 0.16, 0, H), FR)              # mullion between door and side light
    cube(bm, (dx0, dx1, 0.07, 0.12, 0.01, H - f), WD)
    for i in range(1, 5):                                      # vertical battens
        x = dx0 + (dx1 - dx0) * i / 5
        cube(bm, (x - 0.012, x + 0.012, 0.062, 0.07, 0.12, H - f - 0.1), WD)
    hx = dx1 - 0.12                                            # long bar handle with two standoffs
    cyl(bm, (hx, -0.0, 0.72), (hx, -0.0, 1.38), 0.014, ME)
    for z in (0.8, 1.3):
        cyl(bm, (hx, 0.0, z), (hx, 0.07, z), 0.009, ME)
    cube(bm, (hx - 0.02, hx + 0.02, 0.055, 0.07, 1.0, 1.1), ME)    # lock plate
    cube(bm, (dx1 + f, x1 - f, 0.09, 0.096, f, H - f), FG)
    cube(bm, (x0 - 0.04, x1 + 0.04, -0.12, 0.16, -0.05, 0.0), FR)   # threshold
    for v in bm.verts:
        v.co = M @ v.co
    mesh(w, name, bm, [mats['wood'], mats['frame'], mats['metal'], mats['frosted']], coll, bevel=0.004)
    return ((x0, x1, -0.02, 0.5, 0.0, H), M)


def louver(w, name, M, W, H, mat, slat=0.075, pitch=0.06, angle=35.0, y=0.05, frame=0.045, vertical=False,
           cut=True, coll=None):
    """Louvred panel (shutter, slatted gate) in frame M; bottom-centre at the origin, set y metres into the wall.
    vertical=True turns the slats upright. Returns the cutter (if cut) for carve()."""
    bm = bmesh.new()
    x0, x1 = -W / 2, W / 2
    _frame4(bm, x0, x1, 0, H, frame, y - 0.03, y + 0.03, 0)
    if vertical:
        n = int((W - 2 * frame) / pitch)
        for i in range(n):
            x = x0 + frame + (i + 0.5) * (W - 2 * frame) / n
            R = Matrix.Translation((x, y, H / 2)) @ Matrix.Rotation(math.radians(angle), 4, 'Z')
            cube(bm, (-0.007, 0.007, -slat / 2, slat / 2, -(H / 2 - frame), H / 2 - frame), 0, R)
    else:
        n = int((H - 2 * frame) / pitch)
        for i in range(n):
            z = frame + (i + 0.5) * (H - 2 * frame) / n
            R = Matrix.Translation((0, y, z)) @ Matrix.Rotation(math.radians(angle), 4, 'X')
            cube(bm, (x0 + frame, x1 - frame, -slat / 2, slat / 2, -0.007, 0.007), 0, R)
    for v in bm.verts:
        v.co = M @ v.co
    mesh(w, name, bm, mat, coll, bevel=0.003)
    return ((x0, x1, -0.02, y + 0.12, 0.0, H), M) if cut else None


# ---- fences and frames ----
def _seg_box(bm, p0, p1, wdt, thk, mat):
    """Flat bar from p0 to p1 (3D), width across in the vertical plane of the bar, thickness horizontal."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    L = d.length
    if L < 1e-6:
        return
    x = d.normalized()
    hz = Vector((x.y, -x.x, 0)).normalized() if abs(x.z) < 0.999 else Vector((1, 0, 0))
    z = x.cross(hz)
    R = Matrix((x, hz, z)).transposed().to_4x4()
    M = Matrix.Translation((p0 + p1) / 2) @ R
    cube(bm, (-L / 2, L / 2, -thk / 2, thk / 2, -wdt / 2, wdt / 2), mat, M)


def bars(w, name, p0, p1, z0, z1, mat, spacing=0.11, bar=0.018, rail=0.04, coll=None):
    """Railing of vertical square bars from p0 to p1 (plan points) with top and bottom rails."""
    p0, p1 = Vector((*p0, 0)), Vector((*p1, 0))
    d = p1 - p0
    n = max(1, int(d.length / spacing))
    bm = bmesh.new()
    for i in range(n + 1):
        c = p0 + d * (i / n)
        cube(bm, (c.x - bar / 2, c.x + bar / 2, c.y - bar / 2, c.y + bar / 2, z0, z1))
    for z in (z0, z1):
        _seg_box(bm, p0 + Vector((0, 0, z)), p1 + Vector((0, 0, z)), rail, rail * 0.8, 0)
    return mesh(w, name, bm, mat, coll, bevel=0.003)


def lattice(w, name, p0, p1, z0, z1, mat, cell=0.32, bar=0.022, thk=0.008, coll=None):
    """Expansion-gate lattice: crossing diagonal flat bars between plan points p0 and p1, with rails and posts."""
    p0, p1 = Vector((*p0, 0)), Vector((*p1, 0))
    d = p1 - p0
    L, h = d.length, z1 - z0
    e = d.normalized()
    bm = bmesh.new()

    def P(u, v, off=0.0):
        n = Vector((-e.y, e.x, 0))
        return p0 + e * u + Vector((0, 0, z0 + v)) + n * off

    for sgn, off in ((1, -thk), (-1, thk)):
        u = -h
        while u < L + h:
            a, b = (u, 0.0), (u + sgn * h, h)
            # clip the segment to 0 <= u <= L
            (ua, va), (ub, vb) = a, b
            if ua > ub:
                (ua, va), (ub, vb) = (ub, vb), (ua, va)
            if ub > 0 and ua < L:
                if ua < 0:
                    va += (vb - va) * (0 - ua) / (ub - ua)
                    ua = 0
                if ub > L:
                    vb = va + (vb - va) * (L - ua) / (ub - ua)
                    ub = L
                _seg_box(bm, P(ua, va, off), P(ub, vb, off), bar, thk, 0)
            u += cell
    for v in (0.0, h):
        _seg_box(bm, P(0, v), P(L, v), 0.035, 0.03, 0)
    for u in (0.0, L):
        _seg_box(bm, P(u, 0), P(u, h), 0.04, 0.04, 0)
    return mesh(w, name, bm, mat, coll, bevel=0.002)


def pipe(w, name, pts, r, mat, coll=None, res=3):
    """Round pipe through pts (gutter, downpipe, antenna, carport frame) as a bevelled curve."""
    cu = bpy.data.curves.new(w.n(name), 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth, cu.bevel_resolution = r, res
    cu.use_fill_caps = True
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for p, c in zip(sp.points, pts):
        p.co = (*c, 1.0)
    cu.materials.append(mat)
    ob = bpy.data.objects.new(w.n(name), cu)
    (coll or w.coll).objects.link(ob)
    return ob


# ---- roofs ----
def hip_roof(w, name, b, z, mats, pitch=24.0, overhang=0.6, row=0.3, step=0.028, fascia=0.2, gutters=True,
             coll=None):
    """Hip roof over the wall rectangle b=(x0, x1, y0, y1); eave line at height z.
    Built from tile rows (each row a shallow step, so rows cast shadow lines), hip and ridge caps,
    a fascia slab with a soffit underneath and half-round gutters.
    mats: dict tile, cap, fascia, gutter. UVs of the tiles: u along the eave, v up the slope (metres).
    Returns dict(ridge=(p0, p1), corners=[...], eave_z, top_z)."""
    _need(mats, ('tile', 'cap', 'fascia', 'gutter'), 'hip_roof')
    x0, x1, y0, y1 = b[:4]
    a, bb, c, d = x0 - overhang, x1 + overhang, y0 - overhang, y1 + overhang
    W, D = bb - a, d - c
    t = math.tan(math.radians(pitch))
    smax = min(W, D) / 2
    ds = row * math.cos(math.radians(pitch))
    Z = Vector((0, 0, 1))
    # each face: eave start, along unit, inward unit, eave length
    faces = [(Vector((a, c, z)), Vector((1, 0, 0)), Vector((0, 1, 0)), W),
             (Vector((bb, d, z)), Vector((-1, 0, 0)), Vector((0, -1, 0)), W),
             (Vector((a, d, z)), Vector((0, -1, 0)), Vector((1, 0, 0)), D),
             (Vector((bb, c, z)), Vector((0, 1, 0)), Vector((-1, 0, 0)), D)]
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new('UVMap')
    T, CAP, FAS, GUT = 0, 1, 2, 3

    def P(E0, e, n, s, u, lift=0.0):
        return E0 + e * u + n * s + Z * (s * t + lift)

    def quad(pts, uvs, mat):
        f = bm.faces.new([bm.verts.new(p) for p in pts])
        f.material_index = mat
        for lp, uv in zip(f.loops, uvs):
            lp[uvl].uv = uv
        return f

    for E0, e, n, L in faces:
        # base surface under the rows (keeps the sky from showing through the steps)
        base = [P(E0, e, n, 0, 0, -0.012), P(E0, e, n, 0, L, -0.012), P(E0, e, n, smax, L - smax, -0.012),
                P(E0, e, n, smax, smax, -0.012)]
        if L - 2 * smax < 1e-4:
            base = base[:3]
        quad(base, [(0, 0)] * len(base), T)
        s, k = 0.0, 0
        while s < smax - 1e-4:
            s2 = min(s + ds, smax)
            vs, vs2 = s / math.cos(math.radians(pitch)), s2 / math.cos(math.radians(pitch))
            lo0, lo1 = P(E0, e, n, s, s, step), P(E0, e, n, s, L - s, step)
            hi0, hi1 = P(E0, e, n, s2, s2), P(E0, e, n, s2, L - s2)
            if (L - 2 * s2) > 1e-4:
                quad([lo0, lo1, hi1, hi0], [(s, vs), (L - s, vs), (L - s2, vs2), (s2, vs2)], T)
            else:
                quad([lo0, lo1, hi0], [(s, vs), (L - s, vs), (s2, vs2)], T)
            quad([P(E0, e, n, s, s, -0.01), P(E0, e, n, s, L - s, -0.01), lo1, lo0],
                 [(s, vs - 0.03), (L - s, vs - 0.03), (L - s, vs), (s, vs)], T)
            s, k = s2, k + 1
    # caps along hips and ridge
    top = z + smax * t
    if W >= D:
        r0, r1 = Vector((a + smax, c + smax, top)), Vector((bb - smax, c + smax, top))
    else:
        r0, r1 = Vector((a + smax, c + smax, top)), Vector((a + smax, d - smax, top))
    lift = Vector((0, 0, step + 0.02))
    corners = [Vector((a, c, z)), Vector((bb, c, z)), Vector((bb, d, z)), Vector((a, d, z))]
    for cn in corners:
        end = r0 if (cn - r0).length < (cn - r1).length else r1
        cyl(bm, cn + lift, end + lift, 0.075, CAP, 14)
    if (r1 - r0).length > 1e-3:
        cyl(bm, r0 + lift, r1 + lift, 0.085, CAP, 14)
    # fascia slab: its sides are the fascia boards, its underside the soffit
    cube(bm, (a + 0.02, bb - 0.02, c + 0.02, d - 0.02, z - fascia, z - 0.005), FAS)
    if gutters:
        g = 0.065
        ring = [(a - g, c - g), (bb + g, c - g), (bb + g, d + g), (a - g, d + g)]
        for i in range(4):
            p, q = ring[i], ring[(i + 1) % 4]
            cyl(bm, (*p, z - 0.07), (*q, z - 0.07), g, GUT, 12)
    ob = mesh(w, name, bm, [mats['tile'], mats['cap'], mats['fascia'], mats['gutter']], coll, uv=False)
    # box UVs for the parts that did not write their own (caps, fascia, gutters)
    me = ob.data
    uv = me.uv_layers['UVMap']
    vs = me.vertices
    for p in me.polygons:
        if p.material_index == T:
            continue
        nrm = p.normal
        ax = max(range(3), key=lambda i: abs(nrm[i]))
        for li in p.loop_indices:
            co = vs[me.loops[li].vertex_index].co
            uv.data[li].uv = (co.x, co.y) if ax == 2 else (co.x, co.z) if ax == 1 else (co.y, co.z)
    return dict(ridge=(r0, r1), corners=corners, eave_z=z, top_z=top, outer=(a, bb, c, d))
