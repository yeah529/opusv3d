"""Geometry Nodes groups, built from Python.

assembly: a points mesh where each point is one piece. Per-point attributes drive the piece over time:
    pa, pb   start / end position          (FLOAT_VECTOR)
    ra, rb   start / end euler rotation    (FLOAT_VECTOR)
    sa, sb   start / end scale             (FLOAT_VECTOR)
    t0, dur  start time and duration in s  (FLOAT)
    arc      height of a parabolic hop     (FLOAT)
    col      colour, read in the material with an INSTANCER Attribute node named "col"
Progress p = ease((scene seconds - t0) / dur), clamped to 0..1. Time comes from Scene Time, so the same
.blend renders at any fps.

scatter: instances of one object on the faces of a mesh (grass, flowers, pebbles).
"""
import bpy

ATTRS = {'pa': 'FLOAT_VECTOR', 'pb': 'FLOAT_VECTOR', 'ra': 'FLOAT_VECTOR', 'rb': 'FLOAT_VECTOR',
         'sa': 'FLOAT_VECTOR', 'sb': 'FLOAT_VECTOR', 't0': 'FLOAT', 'dur': 'FLOAT', 'arc': 'FLOAT',
         'col': 'FLOAT_COLOR'}
EASES = ('smoother', 'linear', 'gravity', 'rise', 'smooth')


def _sock(node, ident, out=False):
    for s in (node.outputs if out else node.inputs):
        if s.identifier == ident:
            return s
    raise KeyError(f'{node.bl_idname} has no socket {ident}')


def _iface(ng, name, kind, io):
    ng.interface.new_socket(name, in_out=io, socket_type=kind)


def assembly_group(ease='smoother'):
    if ease not in EASES:
        raise ValueError(f'assembly ease "{ease}" not in {EASES}')
    name = f'v3d.assembly.{ease}'
    if name in bpy.data.node_groups:
        return bpy.data.node_groups[name]
    ng = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    _iface(ng, 'Geometry', 'NodeSocketGeometry', 'INPUT')
    _iface(ng, 'Piece', 'NodeSocketObject', 'INPUT')
    _iface(ng, 'Geometry', 'NodeSocketGeometry', 'OUTPUT')
    N, L = ng.nodes, ng.links
    gi, go = N.new('NodeGroupInput'), N.new('NodeGroupOutput')

    def attr(n):
        a = N.new('GeometryNodeInputNamedAttribute')
        a.data_type = 'FLOAT_VECTOR' if ATTRS[n] == 'FLOAT_VECTOR' else 'FLOAT'
        a.inputs['Name'].default_value = n
        return a.outputs['Attribute']

    def math(op, a, b=None):
        m = N.new('ShaderNodeMath')
        m.operation = op
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                m.inputs[i].default_value = v
            else:
                L.new(v, m.inputs[i])
        return m.outputs[0]

    def vmix(f, a, b):
        m = N.new('ShaderNodeMix')
        m.data_type = 'VECTOR'
        L.new(f, _sock(m, 'Factor_Float'))
        L.new(a, _sock(m, 'A_Vector'))
        L.new(b, _sock(m, 'B_Vector'))
        return _sock(m, 'Result_Vector', out=True)

    st = N.new('GeometryNodeInputSceneTime')
    t0 = attr('t0')
    mr = N.new('ShaderNodeMapRange')
    mr.data_type = 'FLOAT'
    mr.interpolation_type = {'smoother': 'SMOOTHERSTEP', 'smooth': 'SMOOTHSTEP'}.get(ease, 'LINEAR')
    mr.clamp = True
    L.new(st.outputs['Seconds'], mr.inputs['Value'])
    L.new(t0, mr.inputs['From Min'])
    L.new(math('ADD', t0, math('MAXIMUM', attr('dur'), 1e-4)), mr.inputs['From Max'])
    p = mr.outputs['Result']
    if ease == 'gravity':
        p = math('MULTIPLY', p, p)
    elif ease == 'rise':
        q = math('SUBTRACT', 1.0, p)
        p = math('SUBTRACT', 1.0, math('MULTIPLY', q, q))

    pos = vmix(p, attr('pa'), attr('pb'))
    hop = math('MULTIPLY', math('MULTIPLY', p, math('SUBTRACT', 1.0, p)), math('MULTIPLY', attr('arc'), 4.0))
    cz = N.new('ShaderNodeCombineXYZ')
    L.new(hop, cz.inputs['Z'])
    va = N.new('ShaderNodeVectorMath')
    va.operation = 'ADD'
    L.new(pos, va.inputs[0])
    L.new(cz.outputs[0], va.inputs[1])
    sp = N.new('GeometryNodeSetPosition')
    L.new(gi.outputs['Geometry'], sp.inputs['Geometry'])
    L.new(va.outputs[0], sp.inputs['Position'])

    e2r = N.new('FunctionNodeEulerToRotation')
    L.new(vmix(p, attr('ra'), attr('rb')), e2r.inputs[0])
    oi = N.new('GeometryNodeObjectInfo')
    oi.transform_space = 'ORIGINAL'
    L.new(gi.outputs['Piece'], oi.inputs['Object'])
    iop = N.new('GeometryNodeInstanceOnPoints')
    L.new(sp.outputs['Geometry'], iop.inputs['Points'])
    L.new(oi.outputs['Geometry'], iop.inputs['Instance'])
    L.new(e2r.outputs[0], iop.inputs['Rotation'])
    L.new(vmix(p, attr('sa'), attr('sb')), iop.inputs['Scale'])
    L.new(iop.outputs['Instances'], go.inputs['Geometry'])
    return ng


def scatter_group():
    name = 'v3d.scatter'
    if name in bpy.data.node_groups:
        return bpy.data.node_groups[name]
    ng = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    _iface(ng, 'Geometry', 'NodeSocketGeometry', 'INPUT')
    _iface(ng, 'Piece', 'NodeSocketObject', 'INPUT')
    for n in ('Density', 'Scale', 'Scale Random', 'Seed'):
        _iface(ng, n, 'NodeSocketFloat', 'INPUT')
    _iface(ng, 'Keep Base', 'NodeSocketBool', 'INPUT')
    _iface(ng, 'Geometry', 'NodeSocketGeometry', 'OUTPUT')
    N, L = ng.nodes, ng.links
    gi, go = N.new('NodeGroupInput'), N.new('NodeGroupOutput')
    d = N.new('GeometryNodeDistributePointsOnFaces')
    d.distribute_method = 'RANDOM'
    L.new(gi.outputs['Geometry'], d.inputs['Mesh'])
    L.new(gi.outputs['Density'], d.inputs['Density'])
    f2i = N.new('FunctionNodeFloatToInt')
    L.new(gi.outputs['Seed'], f2i.inputs[0])
    L.new(f2i.outputs[0], d.inputs['Seed'])
    oi = N.new('GeometryNodeObjectInfo')
    oi.transform_space = 'ORIGINAL'
    L.new(gi.outputs['Piece'], oi.inputs['Object'])
    rz = N.new('FunctionNodeRandomValue')
    rz.data_type = 'FLOAT'
    rz.inputs['Max'].default_value = 6.2832
    L.new(f2i.outputs[0], rz.inputs['Seed'])
    rs = N.new('FunctionNodeRandomValue')       # scale * (1 - random * scale_random)
    rs.data_type = 'FLOAT'
    L.new(f2i.outputs[0], rs.inputs['Seed'])
    k = N.new('ShaderNodeMath')
    k.operation = 'MULTIPLY'
    L.new(rs.outputs['Value'], k.inputs[0])
    L.new(gi.outputs['Scale Random'], k.inputs[1])
    one = N.new('ShaderNodeMath')
    one.operation = 'SUBTRACT'
    one.inputs[0].default_value = 1.0
    L.new(k.outputs[0], one.inputs[1])
    mul = N.new('ShaderNodeMath')
    mul.operation = 'MULTIPLY'
    L.new(one.outputs[0], mul.inputs[0])
    L.new(gi.outputs['Scale'], mul.inputs[1])
    cz = N.new('ShaderNodeCombineXYZ')
    L.new(rz.outputs['Value'], cz.inputs['Z'])
    e2r = N.new('FunctionNodeEulerToRotation')
    L.new(cz.outputs[0], e2r.inputs[0])
    iop = N.new('GeometryNodeInstanceOnPoints')
    L.new(d.outputs['Points'], iop.inputs['Points'])
    L.new(oi.outputs['Geometry'], iop.inputs['Instance'])
    L.new(e2r.outputs[0], iop.inputs['Rotation'])
    L.new(mul.outputs[0], iop.inputs['Scale'])
    sw = N.new('GeometryNodeJoinGeometry')
    L.new(iop.outputs['Instances'], sw.inputs[0])
    gate = N.new('GeometryNodeSwitch')
    gate.input_type = 'GEOMETRY'
    L.new(gi.outputs['Keep Base'], gate.inputs['Switch'])
    L.new(gi.outputs['Geometry'], gate.inputs['True'])
    L.new(gate.outputs[0], sw.inputs[0])
    L.new(sw.outputs[0], go.inputs['Geometry'])
    return ng


def points_mesh(name, n, collection):
    me = bpy.data.meshes.new(name)
    me.vertices.add(n)
    ob = bpy.data.objects.new(name, me)
    collection.objects.link(ob)
    return ob


def set_attrs(ob, data):
    """data: {attr: flat list or list of tuples}, one entry per point. Missing attributes get defaults."""
    me = ob.data
    n = len(me.vertices)
    defaults = {'pa': (0, 0, 0), 'ra': (0, 0, 0), 'rb': None, 'sa': (1, 1, 1), 'sb': None, 't0': 0.0, 'dur': 1.0,
                'arc': 0.0, 'col': (1, 1, 1, 1)}
    full = dict(data)
    full.setdefault('pb', full.get('pa'))
    for k in ATTRS:
        if k not in full:
            dv = defaults[k]
            if dv is None:   # rb/sb default to the start values
                full[k] = full['ra' if k == 'rb' else 'sa'] if ('ra' if k == 'rb' else 'sa') in full else ([(0, 0, 0)] * n if k == 'rb' else [(1, 1, 1)] * n)
            else:
                full[k] = [dv] * n
    for k, typ in ATTRS.items():
        vals = full[k]
        if len(vals) != n:
            raise ValueError(f'{ob.name}: attribute {k} has {len(vals)} values for {n} points')
        if typ == 'FLOAT_VECTOR':
            vals = [tuple(v)[:3] if hasattr(v, '__len__') else (v, v, v) for v in vals]
        if typ == 'FLOAT_COLOR':
            vals = [tuple(v) + (1.0,) * (4 - len(v)) for v in vals]
        a = me.attributes.get(k) or me.attributes.new(k, typ, 'POINT')
        flat = [c for v in vals for c in v] if typ != 'FLOAT' else [float(v) for v in vals]
        a.data.foreach_set('vector' if typ == 'FLOAT_VECTOR' else 'color' if typ == 'FLOAT_COLOR' else 'value', flat)
    me.vertices.foreach_set('co', [c for v in full['pa'] for c in tuple(v)[:3]])
    me.update()


def assembly(name, piece, data, collection, ease='smoother'):
    """Create an assembly object: one `piece` instance per point, animated by `data` (see module doc)."""
    n = len(data['pa'])
    ob = points_mesh(name, n, collection)
    set_attrs(ob, data)
    mod = ob.modifiers.new('assembly', 'NODES')
    mod.node_group = assembly_group(ease)
    _set_input(mod, 'Piece', piece)
    return ob


def scatter(base, piece, density=200.0, scale=1.0, scale_random=0.4, seed=0, keep_base=True):
    mod = base.modifiers.new('scatter', 'NODES')
    mod.node_group = scatter_group()
    for k, v in (('Piece', piece), ('Density', density), ('Scale', scale), ('Scale Random', scale_random),
                 ('Seed', float(seed)), ('Keep Base', keep_base)):
        _set_input(mod, k, v)
    return mod


def _set_input(mod, name, value):
    """Blender 5.x: modifier inputs live at mod.properties.inputs.<identifier>.value (no id-property access)."""
    for item in mod.node_group.interface.items_tree:
        if getattr(item, 'in_out', None) == 'INPUT' and item.name == name:
            getattr(mod.properties.inputs, item.identifier).value = value
            return
    raise KeyError(name)
