"""Asset tools run outside a film (not part of the render signature, so editing them never re-renders shots).

  check   stats + front/right/back/left sheet on a grey card
          Blender -b --factory-startup --python-exit-code 1 -P engine/assettool.py -- check <file> <out.jpg> [height]
  mixamo  a Tripo character as one mesh for the Mixamo auto-rigger (manual 6A): joined (material slots kept), feet at
          the origin, height in metres, turned so the face looks at -Y, transforms applied, no textures in the FBX
          (smaller, steadier upload; the film puts the Tripo material back after rigging)
          Blender -b --factory-startup --python-exit-code 1 -P engine/assettool.py -- mixamo <in.fbx|glb> <out.fbx> [height] [turn]
          turn: degrees about Z; run check on the result: its first view must show the face
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from v3d import assets  # noqa: E402


def prepare(src, height=None, turn=0.0):
    """Import a character as one mesh named 'character': feet at the origin, height in metres, turned `turn` degrees
    about Z, transforms applied."""
    for o in list(bpy.context.scene.objects):
        bpy.data.objects.remove(o)
    objs = assets._import(src)
    if any(o.type == 'ARMATURE' for o in objs):
        raise RuntimeError(f'assettool: {src} already has an armature; expected a bare mesh')
    meshes = [o for o in objs if o.type == 'MESH']
    for o in meshes:                                   # keep where each mesh is, then drop parents and empties
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    for o in objs:
        if o.type != 'MESH':
            bpy.data.objects.remove(o)
    if len(meshes) > 1:
        with bpy.context.temp_override(active_object=meshes[0], selected_editable_objects=meshes, selected_objects=meshes):
            bpy.ops.object.join()
    ob = meshes[0]
    bpy.context.view_layer.update()
    lo, hi = assets._bounds([ob])
    s = height / (hi.z - lo.z) if height else 1.0
    M = (Matrix.Rotation(math.radians(turn), 4, 'Z') @ Matrix.Scale(s, 4)
         @ Matrix.Translation(-Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))) @ ob.matrix_world)
    ob.data.transform(M)
    ob.matrix_world = Matrix.Identity(4)
    ob.name = ob.data.name = 'character'
    bpy.context.view_layer.update()
    return ob, s


def mixamo(src, out, height=None, turn=0.0):
    ob, s = prepare(src, height, turn)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    bpy.ops.export_scene.fbx(filepath=os.path.abspath(out), object_types={'MESH'}, apply_unit_scale=True,
                             add_leaf_bones=False, path_mode='STRIP', embed_textures=False, mesh_smooth_type='FACE')
    lo, hi = assets._bounds([ob])
    coll = bpy.data.collections.new('mixamo')
    coll.objects.link(ob)
    coll['src'], coll['scale'], coll['size'] = os.path.abspath(out), s, [round(hi[i] - lo[i], 4) for i in range(3)]
    r = assets.report(coll)
    r['mb'] = round(os.path.getsize(out) / 2 ** 20, 2)
    return r


if __name__ == '__main__':
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if a[:1] == ['check'] and len(a) >= 3:
        print('assettool:', json.dumps(assets.check(a[1], a[2], float(a[3]) if len(a) > 3 else None)))
    elif a[:1] == ['mixamo'] and len(a) >= 3:
        print('assettool:', json.dumps(mixamo(a[1], a[2], float(a[3]) if len(a) > 3 else None, float(a[4]) if len(a) > 4 else 0.0)))
    else:
        sys.exit(__doc__)
