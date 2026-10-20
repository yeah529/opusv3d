"""Auto-Rig Pro tools (the ARP add-on must be installed in this Blender). Not part of the render signature.

  build  rig a character: ARP human rig, reference bones from a rig spec JSON (.l bones mirror to .r), fingers off,
         Match to Rig, bind the mesh, save a .blend
         Blender -b --factory-startup --python-exit-code 1 -P engine/arptool.py -- build <char.fbx|glb> <spec.json> <out.blend> [engine]
         spec: {"height": metres, "turn": degrees about Z (face to -Y), "bones": {ref bone: [head, tail]}}; bone points are
         in metres on the character after height + turn. engine: PSEUDO_VOXELS (default) or HEAT_MAP. ARP's own weights are kept: on C1, hand-written weight fixes
         (rigid head, head / shoulder / root fades) cracked the neck on a 45 deg head turn and fixed nothing visible.
  test   joints overlay (see-through mesh + deform bones, front + side), then pose the rig (FK arms, IK squat, FK leg
         lift, spine twist, head turn...), render front + side per pose plus heat maps, and report stretched edges and
         intersections that the rest pose does not have. Runs WITHOUT the ARP add-on, as
         the film does.
         Blender -b --factory-startup --python-exit-code 1 -P engine/arptool.py -- test <rig.blend> <outdir> [pose,...]
"""
import json
import math
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addon_utils  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

import assettool  # noqa: E402

ARP = 'bl_ext.user_default.auto_rig_pro'


def _arp():
    addon_utils.enable(ARP, default_set=True)
    if ARP not in bpy.context.preferences.addons:
        raise RuntimeError(f'arptool: add-on {ARP} is not installed in this Blender')
    from bl_ext.user_default.auto_rig_pro.src import auto_rig
    return auto_rig


def _ui():
    """ARP sets 3D-view overlay flags. Headless Blender still has one window; lend ARP its 3D view."""
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return bpy.context.temp_override(window=win, screen=win.screen, area=area, region=region, space_data=area.spaces.active)


def _active(ob, mode='OBJECT'):
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    if mode != 'OBJECT':
        bpy.ops.object.mode_set(mode=mode)


def joints(spec):
    J = dict(spec['bones'])
    for k in [k for k in J if k.endswith('.l')]:
        (h, t) = J[k]
        J[k[:-2] + '.r'] = [[-h[0], h[1], h[2]], [-t[0], t[1], t[2]]]
    return J


def build(src, spec_path, out, engine='PSEUDO_VOXELS'):
    if engine not in ('PSEUDO_VOXELS', 'HEAT_MAP'):
        raise ValueError(f'arptool: engine {engine!r}; use PSEUDO_VOXELS or HEAT_MAP')
    spec = json.load(open(spec_path))
    if not spec.get('height', 0) > 0:
        raise ValueError(f'arptool: {spec_path} needs "height" > 0 (the metres its bone points assume)')
    ar = _arp()
    t0 = time.time()
    ob, _ = assettool.prepare(os.path.abspath(src), spec['height'], spec.get('turn', 0.0))   # absolute: right texture path
    J = joints(spec)
    with _ui():
        bpy.ops.arp.append_arp(rig_preset='human')
        rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
        _active(rig, 'EDIT')
        eb = rig.data.edit_bones
        missing = sorted(k for k in J if k not in eb)
        if missing:
            raise RuntimeError(f'arptool: joints name bones the ARP rig lacks: {missing}')
        inv = rig.matrix_world.inverted()
        for k, (h, t) in J.items():
            eb[k].head, eb[k].tail = inv @ Vector(h), inv @ Vector(t)
        for side in ('.l', '.r'):                        # hooves / mittens: no finger bones (set_fingers reads the selection)
            for b in eb:
                b.select = b.select_head = b.select_tail = False
            b = eb['hand_ref' + side]
            b.select = b.select_head = b.select_tail = True
            eb.active = b
            with bpy.context.temp_override(selected_editable_bones=[b]):   # the ref bones' collection may be hidden
                ar.set_fingers(False, False, False, False, False)
        _active(rig)
        bpy.ops.arp.match_to_rig()
        _active(rig)
        ob.select_set(True)
        bpy.context.scene.arp_bind_engine = engine
        bpy.ops.arp.bind_to_rig()
    _active(ob)
    mods = [m for m in ob.modifiers if m.type == 'ARMATURE']
    groups = {g.index: g.name for g in ob.vertex_groups}
    deform = {b.name for b in rig.data.bones if b.use_deform}
    unweighted = sum(1 for v in ob.data.vertices if not any(groups.get(g.group) in deform and g.weight > 1e-4 for g in v.groups))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0      # no .blend1 next to the asset
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out), relative_remap=True)
    return {'rig': rig.name, 'bones': len(rig.data.bones), 'deform_bones': len(deform),
            'fingers': sorted(b.name for b in rig.data.bones if any(f in b.name for f in ('thumb', 'index', 'middle', 'ring', 'pinky'))),
            'armature_mods': [(m.name, m.object.name if m.object else None, m.use_deform_preserve_volume) for m in mods],
            'vertex_groups': len(ob.vertex_groups), 'verts': len(ob.data.vertices), 'unweighted_verts': unweighted,
            'engine': engine, 'seconds': round(time.time() - t0, 1)}


# ---- pose tests -------------------------------------------------------------------------------------------------
# Each pose: list of (controller, op, args). rot: world axis + degrees about the controller's head. move: world offset.
# fk / ik: set the limb's ik_fk_switch (1 = FK). Left side is given; .l mirrors to .r unless the pose says 'one side'.
POSES = {
    'rest': [],
    'arms_up45': [('c_hand_ik.l', 'fk'), ('c_arm_fk.l', 'rot', 'Y', -45)],
    'arms_up60': [('c_hand_ik.l', 'fk'), ('c_arm_fk.l', 'rot', 'Y', -60)],
    'arms_up75': [('c_hand_ik.l', 'fk'), ('c_arm_fk.l', 'rot', 'Y', -75)],
    'arms_down': [('c_hand_ik.l', 'fk'), ('c_arm_fk.l', 'rot', 'Y', 60)],
    'arms_forward': [('c_hand_ik.l', 'fk'), ('c_arm_fk.l', 'rot', 'Z', -80)],
    'elbow_90': [('c_hand_ik.l', 'fk'), ('c_forearm_fk.l', 'rot', 'Z', -90)],
    'wrist_bend': [('c_hand_ik.l', 'fk'), ('c_hand_fk.l', 'rot', 'Y', -45), ('c_hand_fk.l', 'rot', 'X', 40)],
    'squat': [('c_root_master.x', 'move', (0, 0, -0.035))],
    'squat_deep': [('c_root_master.x', 'move', (0, 0, -0.06))],
    'leg_lift45': [('c_foot_ik.l', 'fk', 'one'), ('c_thigh_fk.l', 'rot', 'X', -45, 'one'), ('c_leg_fk.l', 'rot', 'X', 50, 'one')],
    'leg_lift': [('c_foot_ik.l', 'fk', 'one'), ('c_thigh_fk.l', 'rot', 'X', -70, 'one'), ('c_leg_fk.l', 'rot', 'X', 80, 'one')],
    'leg_side': [('c_foot_ik.l', 'fk', 'one'), ('c_thigh_fk.l', 'rot', 'Y', -35, 'one')],
    'twist_45': [('c_spine_01.x', 'rot', 'Z', 20), ('c_spine_02.x', 'rot', 'Z', 25)],
    'bend_fwd': [('c_spine_01.x', 'rot', 'X', 20), ('c_spine_02.x', 'rot', 'X', 15)],
    'head_turn': [('c_head.x', 'rot', 'Z', 45)],
    'head_nod': [('c_head.x', 'rot', 'X', 25)],
    'shrug': [('c_shoulder.l', 'rot', 'Y', -15)],
    'hip_sway': [('c_root.x', 'rot', 'Y', 12), ('c_root.x', 'rot', 'X', -10)],
}
MIRROR = {'X': 1, 'Y': -1, 'Z': -1}     # rotation sign for the .r copy, per world axis (mirror across x = 0)


def _region(name):
    side = name[-2:] if name[-2:] in ('.l', '.r') else ''
    for key, reg in (('head', 'head'), ('neck', 'head'), ('hand', 'hand'), ('forearm', 'arm'), ('arm', 'arm'), ('shoulder', 'arm'),
                     ('spine', 'torso'), ('root', 'torso'), ('thigh', 'leg'), ('leg', 'leg'), ('foot', 'foot'), ('toes', 'foot')):
        if key in name:
            return reg + side
    return name


def _pose(rig, steps):
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    for pb in rig.pose.bones:
        if 'ik_fk_switch' in pb.keys():
            pb['ik_fk_switch'] = 0.0
    bpy.context.view_layer.update()
    W = rig.matrix_world
    for st in steps:
        one = st[-1] == 'one'
        names = [st[0]] if one or not st[0].endswith('.l') else [st[0], st[0][:-2] + '.r']
        for n in names:
            pb = rig.pose.bones[n]
            if st[1] == 'fk':
                pb['ik_fk_switch'] = 1.0
            elif st[1] == 'rot':
                ang = st[3] * (MIRROR[st[2]] if n.endswith('.r') else 1)
                M = W @ pb.matrix
                h = M.translation.copy()
                M = Matrix.Translation(h) @ Matrix.Rotation(math.radians(ang), 4, st[2]) @ Matrix.Translation(-h) @ M
                pb.matrix = W.inverted() @ M
            elif st[1] == 'move':
                d = Vector(st[2])
                if n.endswith('.r'):
                    d.x = -d.x
                M = W @ pb.matrix
                M.translation += d
                pb.matrix = W.inverted() @ M
            bpy.context.view_layer.update()


def _measure(ob, rest_len, tri_region, base_pairs):
    dg = bpy.context.evaluated_depsgraph_get()
    eo = ob.evaluated_get(dg)
    me = eo.to_mesh()
    co = [ob.matrix_world @ v.co for v in me.vertices]
    stretch = Counter()
    worst = {}
    for e, l0 in zip(me.edges, rest_len):
        if l0 < 1e-6:
            continue
        r = (co[e.vertices[0]] - co[e.vertices[1]]).length / l0
        if r > 1.6 or r < 0.5:
            reg = tri_region['v'][e.vertices[0]]
            stretch[reg] += 1
            worst[reg] = max(worst.get(reg, 1), r if r > 1 else 1 / r)
    polys = [tuple(p.vertices) for p in me.polygons]
    bvh = BVHTree.FromPolygons(co, polys, all_triangles=False, epsilon=0.0)
    pairs = set()
    for a, b in bvh.overlap(bvh):
        if a < b and not set(polys[a]) & set(polys[b]):
            pairs.add((a, b))
    heat = [0.0] * len(co)                             # per vertex: worst edge ratio (>1), 9 = in a new intersection
    for e, l0 in zip(me.edges, rest_len):
        if l0 >= 1e-6:
            r = (co[e.vertices[0]] - co[e.vertices[1]]).length / l0
            r = r if r > 1 else 1 / r
            for i in e.vertices:
                heat[i] = max(heat[i], r)
    new = Counter()
    for a, b in pairs - base_pairs:
        new[tuple(sorted((tri_region['f'][a], tri_region['f'][b])))] += 1
        for i in polys[a] + polys[b]:
            heat[i] = 9.0
    eo.to_mesh_clear()
    return pairs, stretch, worst, new, heat


def _paint(ob, heat):
    """grey = fine, yellow = edge 1.3-1.6x, red = over 1.6x (stretched or squashed), magenta = new intersection."""
    at = ob.data.color_attributes.get('arp_heat') or ob.data.color_attributes.new('arp_heat', 'FLOAT_COLOR', 'POINT')
    cols = []
    for h in heat:
        cols += ((1, 0, 1, 1) if h >= 9 else (1, 0.05, 0.05, 1) if h > 1.6 else (1, 0.8, 0.1, 1) if h > 1.3 else (0.7, 0.7, 0.7, 1))
    at.data.foreach_set('color', cols)
    ob.data.update()


def _heat_material():
    m = bpy.data.materials.get('_arp_heat') or bpy.data.materials.new('_arp_heat')
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    for n in list(N):
        N.remove(n)
    a = N.new('ShaderNodeVertexColor')
    a.layer_name = 'arp_heat'
    b = N.new('ShaderNodeBsdfPrincipled')
    o = N.new('ShaderNodeOutputMaterial')
    L.new(a.outputs['Color'], b.inputs['Base Color'])
    L.new(b.outputs['BSDF'], o.inputs['Surface'])
    return m


def _views(path, ob, scene, heat_mat=None):
    cam = bpy.data.objects.get('_cam') or bpy.data.objects.new('_cam', bpy.data.cameras.new('_cam'))
    if cam.name not in scene.collection.objects:
        scene.collection.objects.link(cam)
    cam.data.type, cam.data.ortho_scale = 'ORTHO', 1.25
    scene.camera = cam
    keep = [sl.material for sl in ob.material_slots]
    for mats, suffix in ((keep, ''), ([heat_mat] * len(keep), '_heat')):
        if mats[0] is None and suffix:
            continue
        for sl, m in zip(ob.material_slots, mats):
            sl.material = m
        for tag, loc, rot in (('front', (0, -5, 0.5), (math.pi / 2, 0, 0)), ('side', (5, 0, 0.5), (math.pi / 2, 0, math.pi / 2))):
            cam.location, cam.rotation_euler = loc, rot
            scene.render.filepath = f'{path}_{tag}{suffix}.jpg'
            bpy.ops.render.render(write_still=True)
    for sl, m in zip(ob.material_slots, keep):
        sl.material = m


def _overlay(path, rig, ob, scene):
    """Rest pose: the mesh at 25% opacity, every deform bone as a red stick, joints as dark balls."""
    ghost = bpy.data.materials.new('_ghost')
    ghost.use_nodes = True
    N, L = ghost.node_tree.nodes, ghost.node_tree.links
    mix = N.new('ShaderNodeMixShader')
    mix.inputs['Fac'].default_value = 0.75
    L.new(N['Principled BSDF'].outputs['BSDF'], mix.inputs[1])
    L.new(N.new('ShaderNodeBsdfTransparent').outputs['BSDF'], mix.inputs[2])
    L.new(mix.outputs['Shader'], N['Material Output'].inputs['Surface'])
    stick, ball = bpy.data.materials.new('_stick'), bpy.data.materials.new('_ball')
    for m, c in ((stick, (1, 0.1, 0.05, 1)), (ball, (0.05, 0.05, 0.2, 1))):
        m.use_nodes = True
        N = m.node_tree.nodes
        N.remove(N['Principled BSDF'])
        e = N.new('ShaderNodeEmission')
        e.inputs['Color'].default_value = c
        m.node_tree.links.new(e.outputs['Emission'], N['Material Output'].inputs['Surface'])
    tmp = []
    for b in rig.data.bones:
        if not b.use_deform:
            continue
        h, t = rig.matrix_world @ b.head_local, rig.matrix_world @ b.tail_local
        d = t - h
        bpy.ops.mesh.primitive_cylinder_add(radius=0.004, depth=d.length, location=(h + t) / 2, vertices=8)
        c = bpy.context.object
        c.rotation_euler = d.to_track_quat('Z', 'Y').to_euler()
        c.data.materials.append(stick)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.008, location=h, segments=12, ring_count=6)
        bpy.context.object.data.materials.append(ball)
        tmp += [c, bpy.context.object]
    keep = [sl.material for sl in ob.material_slots]
    for sl in ob.material_slots:
        sl.material = ghost
    _views(path, ob, scene)
    for sl, m in zip(ob.material_slots, keep):
        sl.material = m
    for o in tmp:
        bpy.data.objects.remove(o)


def test(blend, outdir, only=None):
    bad = sorted(set(only or []) - set(POSES))
    if bad:
        raise ValueError(f'arptool: unknown pose(s) {bad}; poses: {list(POSES)}')
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend))
    scene = bpy.context.scene
    rig = next((o for o in scene.objects if o.type == 'ARMATURE'), None)
    ob = next((o for o in scene.objects if o.type == 'MESH' and any(m.type == 'ARMATURE' for m in o.modifiers)), None)
    if rig is None or ob is None:
        raise RuntimeError(f'arptool: {blend} needs an armature and a mesh with an Armature modifier (run build first)')
    for o in scene.objects:
        if o not in (rig, ob) and o.type == 'MESH':
            o.hide_render = True
    os.makedirs(outdir, exist_ok=True)
    r = scene.render
    r.engine, r.resolution_x, r.resolution_y = 'CYCLES', 560, 560
    scene.cycles.samples, scene.cycles.use_denoising = 16, True
    r.image_settings.file_format = 'JPEG'
    scene.view_settings.view_transform = 'Standard'
    if not scene.world:
        scene.world = bpy.data.worlds.new('w')
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes['Background']
    bg.inputs['Color'].default_value, bg.inputs['Strength'].default_value = (0.8, 0.8, 0.82, 1), 1.0
    sun = bpy.data.objects.new('_sun', bpy.data.lights.new('_sun', 'SUN'))
    sun.data.energy, sun.rotation_euler = 3, (math.radians(50), 0, math.radians(-30))
    scene.collection.objects.link(sun)
    groups = {g.index: g.name for g in ob.vertex_groups}
    vreg = []
    for v in ob.data.vertices:
        g = max(v.groups, key=lambda g: g.weight, default=None)
        vreg.append(_region(groups[g.group]) if g else '-')
    freg = [Counter(vreg[i] for i in p.vertices).most_common(1)[0][0] for p in ob.data.polygons]
    tri_region = {'v': vreg, 'f': freg}
    rest_len = [(ob.data.vertices[e.vertices[0]].co - ob.data.vertices[e.vertices[1]].co).length for e in ob.data.edges]
    _pose(rig, [])
    _overlay(os.path.join(outdir, 'joints'), rig, ob, scene)
    base, _, _, _, _ = _measure(ob, rest_len, tri_region, set())
    hm = _heat_material()
    out = {'rest_intersections': len(base)}
    for name, steps in POSES.items():
        if only and name not in only:
            continue
        _pose(rig, steps)
        _, stretch, worst, new, heat = _measure(ob, rest_len, tri_region, base)
        _paint(ob, heat)
        _views(os.path.join(outdir, name), ob, scene, hm)
        out[name] = {'stretched_edges': dict(stretch), 'worst_ratio': {k: round(v, 2) for k, v in worst.items()},
                     'new_intersections': {f'{a} x {b}': n for (a, b), n in new.most_common(8)}}
        print('arptool test:', name, json.dumps(out[name]))
    _pose(rig, [])
    if 'arp_heat' in ob.data.color_attributes:
        ob.data.color_attributes.remove(ob.data.color_attributes['arp_heat'])
    return out


if __name__ == '__main__':
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if a[:1] == ['build'] and len(a) >= 4:
        print('arptool:', json.dumps(build(a[1], a[2], a[3], *a[4:5])))
    elif a[:1] == ['test'] and len(a) >= 3:
        res = test(a[1], a[2], a[3].split(',') if len(a) > 3 else None)
        json.dump(res, open(os.path.join(a[2], 'report.json'), 'w'), indent=1)
        print('arptool: rest_intersections', res['rest_intersections'])
    else:
        sys.exit(__doc__)
