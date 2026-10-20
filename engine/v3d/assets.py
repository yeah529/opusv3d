"""Imported assets (Tripo / Mixamo GLB, FBX): load once into an unlinked collection, normalise, check, instance.

    coll = assets.load(W, os.path.join(HERE, '02_assets/T1_shrub.glb'), 'shrub', height=0.9)   # HERE: project dir; bottom-centre at origin, 0.9 m tall
    assets.place(W, coll, 'shrub1', (x, y, 0), rot=30, scale=1.1)          # collection instance, cheap to repeat
    print(assets.report(coll))

Check a file on its own (stats + front/right/back/left sheet on a grey card):
    Blender -b --factory-startup --python-exit-code 1 -P engine/v3d/assets.py -- <file> <out.jpg> [height]
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector


def _import(path, mesh=True):
    if not os.path.exists(path):
        raise FileNotFoundError(f'assets: no file {path}')
    before = set(bpy.data.objects)
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.glb', '.gltf'):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == '.fbx':
        bpy.ops.wm.fbx_import(filepath=path)
    else:
        raise ValueError(f'assets: unsupported file type {ext} ({path})')
    new = [o for o in bpy.data.objects if o not in before]
    if mesh and not any(o.type == 'MESH' for o in new):
        raise RuntimeError(f'assets: no mesh imported from {path}')
    gone = missing_images(new)
    if gone:                               # else the asset renders magenta, silently
        raise FileNotFoundError(f'assets: {path} uses texture(s) that are not there: {gone}. Keep the texture folder '
                                f'next to the file, as exported (or export a GLB, which embeds them)')
    n = _fix_mappings({s.material for o in new for s in getattr(o, 'material_slots', []) if s.material})
    if n:
        print(f'assets: bypassed {n} Mapping node(s) with non-finite values in {os.path.basename(path)}')
    bpy.context.view_layer.update()
    return new


def missing_images(objs):
    """Image files that the objects' materials use but that are not on disk (packed images count as there)."""
    return sorted({bpy.path.abspath(n.image.filepath) for o in objs for sl in getattr(o, 'material_slots', [])
                   if sl.material and sl.material.node_tree for n in sl.material.node_tree.nodes
                   if n.type == 'TEX_IMAGE' and n.image and n.image.source == 'FILE' and n.image.packed_file is None
                   and not os.path.exists(bpy.path.abspath(n.image.filepath))})


def _fix_mappings(mats):
    """Some FBX files carry a texture scale whose inverse is inf (seen: scale (1, 1, inf) on a Tripo character re-saved
    in another tool). inf turns every UV into NaN and the whole mesh renders one flat colour. Wire the Mapping node's
    input straight to its outputs and drop it."""
    n = 0
    for m in mats:
        nt = m.node_tree
        if nt is None:
            continue
        for node in [x for x in nt.nodes if x.type == 'MAPPING']:
            vals = [v for i in node.inputs if i.name != 'Vector' and hasattr(i.default_value, '__len__') for v in i.default_value]
            if all(math.isfinite(v) for v in vals):
                continue
            src = node.inputs['Vector'].links[0].from_socket if node.inputs['Vector'].links else None
            for link in list(node.outputs['Vector'].links):
                if src is not None:
                    nt.links.new(src, link.to_socket)
                else:
                    nt.links.remove(link)
            nt.nodes.remove(node)
            n += 1
    return n


def _bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == 'MESH' for c in o.bound_box]
    return (Vector([min(p[i] for p in pts) for i in range(3)]), Vector([max(p[i] for p in pts) for i in range(3)]))


def load(w, path, name, height=None):
    """Import path into a new collection that no scene links (render it through place()). Bottom-centre goes to the
    origin; height (m) rescales it. The collection keeps 'src', 'size' (x, y, z after scaling) and 'scale'."""
    objs = _import(path)
    lo, hi = _bounds(objs)
    if hi.z - lo.z <= 1e-6:
        raise RuntimeError(f'assets: {path} has zero height')
    s = height / (hi.z - lo.z) if height else 1.0
    M = Matrix.Scale(s, 4) @ Matrix.Translation(-Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z)))
    coll = bpy.data.collections.new(w.n(name) if w else name)
    for o in objs:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
        o.name = f'{coll.name}.{o.name}'
        if o.parent is None:
            o.matrix_world = M @ o.matrix_world
    coll['src'], coll['scale'] = os.path.abspath(path), s
    coll['size'] = [round((hi[i] - lo[i]) * s, 4) for i in range(3)]
    return coll


def report(coll):
    """Counts a reviewer needs before using an asset: triangles, materials, texture sizes, size in metres, rig."""
    objs = list(coll.all_objects)
    meshes = {o.data for o in objs if o.type == 'MESH'}
    tris = 0
    for me in meshes:
        me.calc_loop_triangles()
        tris += len(me.loop_triangles)
    mats = {s.material for o in objs for s in o.material_slots if s.material}
    imgs = {n.image.name: list(n.image.size) for m in mats if m.node_tree
            for n in m.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image}
    return dict(src=coll.get('src'), objects=len(objs), meshes=len(meshes), tris=tris, materials=sorted(m.name for m in mats),
                images=imgs, size_m=list(coll.get('size', [])), scale=coll.get('scale'),
                armature=any(o.type == 'ARMATURE' for o in objs), uv=all(len(me.uv_layers) > 0 for me in meshes))


def place(w, coll, name, loc, rot=0.0, scale=1.0, parent=None):
    """A collection instance of coll at loc, turned rot degrees about Z. scale: one number, or (x, y, z) to fit a slot."""
    ob = w.empty(name, loc, parent=parent)
    ob.instance_type, ob.instance_collection = 'COLLECTION', coll
    ob.rotation_euler.z = math.radians(rot)
    ob.scale = tuple(scale) if isinstance(scale, (tuple, list)) else (scale,) * 3
    return ob


class _Bare:
    """Stand-in for a World when checking a file outside a film."""
    def __init__(self, scene):
        self.scene, self.coll = scene, scene.collection

    def n(self, name):
        return f'CHECK.{name}'

    def empty(self, name, loc=(0, 0, 0), parent=None):
        ob = bpy.data.objects.new(self.n(name), None)
        ob.location, ob.parent = loc, parent
        self.coll.objects.link(ob)
        return ob


def check(path, out, height=None):
    """Four instances turned 0/90/180/270 deg in a row (front, its left side, back, right side) under neutral light."""
    sc = bpy.context.scene
    for o in list(sc.objects):                                # factory scene: cube, light, camera
        bpy.data.objects.remove(o)
    w = _Bare(sc)
    coll = load(w, path, os.path.splitext(os.path.basename(path))[0], height)
    sx, sy, sz = coll['size']
    gap = max(sx, sy) * 1.25
    for i, r in enumerate((0, 90, 180, 270)):
        place(w, coll, f'view{r}', ((i - 1.5) * gap, 0, 0), rot=r)
    card = bpy.data.meshes.new('CHECK.card')
    card.from_pydata([(-50, -50, 0), (50, -50, 0), (50, 50, 0), (-50, 50, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new('CHECK.card', card)
    sc.collection.objects.link(ob)
    m = bpy.data.materials.new('CHECK.grey')
    m.diffuse_color = (0.42, 0.42, 0.42, 1)
    ob.data.materials.append(m)
    wd = bpy.data.worlds.new('CHECK.world')
    wd.use_nodes = True
    wd.node_tree.nodes['Background'].inputs['Color'].default_value = (0.55, 0.58, 0.62, 1)
    sc.world = wd
    sun = bpy.data.objects.new('CHECK.sun', bpy.data.lights.new('CHECK.sun', 'SUN'))
    sun.data.energy, sun.data.angle = 3.0, math.radians(8)
    sun.rotation_euler = (math.radians(50), 0, math.radians(-35))
    sc.collection.objects.link(sun)
    cam = bpy.data.objects.new('CHECK.cam', bpy.data.cameras.new('CHECK.cam'))
    cam.data.type, cam.data.ortho_scale = 'ORTHO', max(4 * gap, sz * 1.25 * 3.2)
    cam.location, cam.rotation_euler = (0, -20 * max(gap, sz), sz * 0.5 + 20 * max(gap, sz) * math.tan(math.radians(8))), (math.radians(82), 0, 0)
    cam.data.clip_end = 1000 * max(gap, sz)
    sc.collection.objects.link(cam)
    sc.camera = cam
    r = sc.render
    r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage = 'CYCLES', 1600, 500, 100
    sc.cycles.samples, sc.cycles.use_denoising = 48, True
    sc.view_settings.view_transform = 'AgX'
    r.image_settings.file_format, r.filepath = 'JPEG', os.path.abspath(out)
    bpy.ops.render.render(write_still=True)
    return report(coll)


if __name__ == '__main__':
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if len(a) < 2:
        sys.exit('usage: Blender -b --factory-startup --python-exit-code 1 -P assets.py -- <file> <out.jpg> [height]')
    print('assets:', json.dumps(check(a[0], a[1], float(a[2]) if len(a) > 2 else None)))
