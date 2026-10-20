"""Procedural PBR materials for the 'film' look (Cycles first; they also work in EEVEE).

pbr(name, preset, color=None, **kw) -> bpy material. Texture coordinates are the mesh UVs in metres
(arch.box_uv / arch builders write them), so patterns keep their real size on every object:
  plaster    warm render with soft lumps and fine grain             kw: rough
  tiles      square tiles in stack bond (wall cladding, paving)     kw: size, grout, grout_color
  brick      running-bond brick                                     kw: size=(w, h), grout_color
  clay_tile  glazed terracotta roof tile (colour noise, dirt)
  wood       varnished wood, grain along V                          kw: grain
  metal      brushed metal (alu, steel)                             kw: rough
  paint      painted surface (gutters, gates, boards)               kw: rough
  glass      thin-wall glass, reflects and transmits                kw: tint
  polycarb   translucent tinted roof sheet                          kw: tint
  asphalt    road with aggregate speckles
  concrete   cast concrete / pavement
  fabric     curtains, cloth (sheen)
  soil       garden soil
  leaf       foliage card (two-sided, translucent)
  room       dark room interior seen through windows
  candy      translucent hard candy (subsurface, lumpy, faint stripe) kw: stripe
  cord       cord-wrapped grip, criss-cross diamonds                kw: scale
  emit       light source surface                                   kw: strength
Every preset takes color='#rrggbb' to override its base colour.
"""
import bpy

from .looks import hex2lin

DEFAULT = {
    'plaster': '#efe7da', 'tiles': '#e4cf86', 'brick': '#b4442f', 'clay_tile': '#c4553a', 'wood': '#8a5530',
    'metal': '#c3c7cc', 'paint': '#e9e2d0', 'glass': '#e8f2f6', 'polycarb': '#7d9cd4', 'asphalt': '#55575b',
    'concrete': '#bdb8ae', 'fabric': '#bcd3ea', 'soil': '#5b4330', 'leaf': '#4f8a3a', 'room': '#24272c',
    'emit': '#fff1d6', 'candy': '#f7e6e4', 'cord': '#c3262b',
}
_cache = {}


class _G:
    """Small node-graph helper."""

    def __init__(self, m):
        self.nt = m.node_tree
        self.N, self.L = self.nt.nodes, self.nt.links
        self.bsdf = self.N['Principled BSDF']
        self.out = self.N['Material Output']
        self._uv = None

    def new(self, kind, **inputs):
        n = self.N.new(kind)
        for k, v in inputs.items():
            if k in n.inputs:
                n.inputs[k].default_value = v
            else:
                setattr(n, k, v)
        return n

    def link(self, a, b):
        self.L.new(a, b)

    def uv(self, scale=1.0, rot=0.0):
        """UV in metres (times scale), as a vector."""
        tc = self.new('ShaderNodeTexCoord')
        if scale == 1.0 and not rot:
            return tc.outputs['UV']
        mp = self.new('ShaderNodeMapping')
        mp.inputs['Scale'].default_value = (scale, scale, scale)
        mp.inputs['Rotation'].default_value = (0, 0, rot)
        self.link(tc.outputs['UV'], mp.inputs['Vector'])
        return mp.outputs['Vector']

    def obj(self):
        return self.new('ShaderNodeTexCoord').outputs['Object']

    def noise(self, vec, scale, detail=4.0, rough=0.5):
        n = self.new('ShaderNodeTexNoise', Scale=scale, Detail=detail, Roughness=rough)
        self.link(vec, n.inputs['Vector'])
        return n

    def ramp(self, fac, stops):
        """stops: [(pos, rgba)]"""
        r = self.new('ShaderNodeValToRGB')
        els = r.color_ramp.elements
        els[0].position, els[0].color = stops[0]
        els[1].position, els[1].color = stops[-1]
        for p, c in stops[1:-1]:
            e = els.new(p)
            e.color = c
        self.link(fac, r.inputs['Fac'])
        return r.outputs['Color']

    def mix(self, a, b, fac, blend='MIX'):
        m = self.new('ShaderNodeMix', data_type='RGBA', blend_type=blend)
        for s in m.inputs:
            if s.identifier == 'A_Color':
                (self.link(a, s) if not isinstance(a, tuple) else setattr(s, 'default_value', a))
            elif s.identifier == 'B_Color':
                (self.link(b, s) if not isinstance(b, tuple) else setattr(s, 'default_value', b))
            elif s.identifier == 'Factor_Float':
                (self.link(fac, s) if not isinstance(fac, float) else setattr(s, 'default_value', fac))
        return [o for o in m.outputs if o.identifier == 'Result_Color'][0]

    def bump(self, height, strength=0.3, distance=0.004, normal=None):
        b = self.new('ShaderNodeBump', Strength=strength, Distance=distance)
        self.link(height, b.inputs['Height'])
        if normal is not None:
            self.link(normal, b.inputs['Normal'])
        return b.outputs['Normal']

    def set(self, **kw):
        for k, v in kw.items():
            s = self.bsdf.inputs[k]
            if hasattr(v, 'node'):
                self.link(v, s)
            else:
                s.default_value = v


def _shade(c, k):
    return tuple(min(1.0, x * k) for x in c[:3]) + (1.0,)


def pbr(name, preset, color=None, **kw):
    key = (name, preset, color, tuple(sorted(kw.items())))
    if key in _cache and _cache[key].name in bpy.data.materials:
        return _cache[key]
    if preset not in DEFAULT:
        raise ValueError(f'unknown material preset "{preset}" (known: {", ".join(DEFAULT)})')
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    g = _G(m)
    c = hex2lin(color or DEFAULT[preset])
    getattr(_P, preset)(g, m, c, **kw)
    _cache[key] = m
    return m


class _P:
    @staticmethod
    def plaster(g, m, c, rough=0.88):
        v = g.uv()
        lump = g.noise(v, 1.6, 3.0)
        grain = g.noise(v, 90.0, 6.0, 0.7)
        col = g.ramp(lump.outputs['Fac'], [(0.3, _shade(c, 0.95)), (0.7, _shade(c, 1.03))])
        dirt = g.noise(g.obj(), 0.8, 2.0)
        col = g.mix(col, _shade(c, 0.86), g.ramp(dirt.outputs['Fac'], [(0.55, (0, 0, 0, 1)), (0.85, (0.35, 0.35, 0.35, 1))]).node.outputs[0])
        n = g.bump(grain.outputs['Fac'], 0.12, 0.002, g.bump(lump.outputs['Fac'], 0.05, 0.02))
        g.set(**{'Base Color': col, 'Roughness': rough, 'Normal': n})

    @staticmethod
    def tiles(g, m, c, size=0.3, grout=0.014, grout_color='#b3a88c', offset=0.0):
        v = g.uv()
        br = g.new('ShaderNodeTexBrick', offset=offset, offset_frequency=2, squash=1.0, squash_frequency=2)
        br.inputs['Scale'].default_value = 1.0
        br.inputs['Brick Width'].default_value = size
        br.inputs['Row Height'].default_value = size
        br.inputs['Mortar Size'].default_value = grout
        br.inputs['Mortar Smooth'].default_value = 0.3
        br.inputs['Bias'].default_value = 0.0
        br.inputs['Color1'].default_value = _shade(c, 1.04)
        br.inputs['Color2'].default_value = _shade(c, 0.92)
        br.inputs['Mortar'].default_value = hex2lin(grout_color)
        g.link(v, br.inputs['Vector'])
        grain = g.noise(v, 60.0, 5.0)
        n = g.bump(grain.outputs['Fac'], 0.05, 0.001, g.bump(br.outputs['Fac'], 0.8, 0.006))
        rough = g.ramp(br.outputs['Fac'], [(0.0, (0.45, 0.45, 0.45, 1)), (1.0, (0.9, 0.9, 0.9, 1))])
        g.set(**{'Base Color': br.outputs['Color'], 'Roughness': rough, 'Normal': n})

    @staticmethod
    def brick(g, m, c, size=(0.21, 0.065), grout_color='#d8d2c6'):
        v = g.uv()
        br = g.new('ShaderNodeTexBrick', offset=0.5, offset_frequency=2, squash=1.0, squash_frequency=2)
        br.inputs['Scale'].default_value = 1.0
        br.inputs['Brick Width'].default_value = size[0]
        br.inputs['Row Height'].default_value = size[1]
        br.inputs['Mortar Size'].default_value = 0.008
        br.inputs['Mortar Smooth'].default_value = 0.2
        br.inputs['Bias'].default_value = 0.0
        br.inputs['Color1'].default_value = _shade(c, 1.08)
        br.inputs['Color2'].default_value = _shade(c, 0.85)
        br.inputs['Mortar'].default_value = hex2lin(grout_color)
        g.link(v, br.inputs['Vector'])
        grain = g.noise(v, 40.0, 6.0, 0.65)
        col = g.mix(br.outputs['Color'], _shade(c, 0.7), g.ramp(grain.outputs['Fac'], [(0.6, (0, 0, 0, 1)), (0.8, (0.3, 0.3, 0.3, 1))]).node.outputs[0])
        n = g.bump(grain.outputs['Fac'], 0.15, 0.002, g.bump(br.outputs['Fac'], 0.5, 0.006))
        g.set(**{'Base Color': col, 'Roughness': 0.85, 'Normal': n})

    @staticmethod
    def clay_tile(g, m, c, rib=0.28):
        """Glazed tile rows: S-tile ribs every `rib` metres along U (the eave), per-tile tint, dirt patches."""
        v = g.obj()
        uv = g.uv()
        cells = g.new('ShaderNodeTexBrick', offset=0.5, offset_frequency=2, squash=1.0, squash_frequency=2)
        cells.inputs['Scale'].default_value = 1.0
        cells.inputs['Brick Width'].default_value = rib
        cells.inputs['Row Height'].default_value = 0.3
        cells.inputs['Mortar Size'].default_value = 0.0
        cells.inputs['Color1'].default_value = _shade(c, 0.9)
        cells.inputs['Color2'].default_value = _shade(c, 1.08)
        g.link(uv, cells.inputs['Vector'])
        dirt = g.noise(v, 0.6, 3.0)
        col = g.mix(cells.outputs['Color'], _shade(c, 0.62),
                    g.ramp(dirt.outputs['Fac'], [(0.58, (0, 0, 0, 1)), (0.8, (0.45, 0.45, 0.45, 1))]).node.outputs[0])
        wv = g.new('ShaderNodeTexWave', wave_type='BANDS', bands_direction='X', wave_profile='SIN')
        wv.inputs['Scale'].default_value = 0.314 / rib
        g.link(uv, wv.inputs['Vector'])
        grain = g.noise(uv, 120.0, 4.0)
        n = g.bump(grain.outputs['Fac'], 0.08, 0.001, g.bump(wv.outputs['Fac'], 0.75, 0.03))
        g.set(**{'Base Color': col, 'Roughness': 0.45, 'Coat Weight': 0.3, 'Coat Roughness': 0.2, 'Normal': n})

    @staticmethod
    def wood(g, m, c, grain=1.0):
        v = g.uv()
        mp = g.new('ShaderNodeMapping')
        mp.inputs['Scale'].default_value = (14.0, 1.2, 1.0)
        g.link(v, mp.inputs['Vector'])
        warp = g.noise(mp.outputs['Vector'], 3.0, 4.0)
        wv = g.new('ShaderNodeTexWave', wave_type='BANDS', bands_direction='X')
        wv.inputs['Scale'].default_value = 1.5
        wv.inputs['Distortion'].default_value = 6.0 * grain
        wv.inputs['Detail'].default_value = 3.0
        g.link(mp.outputs['Vector'], wv.inputs['Vector'])
        col = g.ramp(wv.outputs['Fac'], [(0.0, _shade(c, 0.72)), (0.5, c), (1.0, _shade(c, 1.15))])
        col = g.mix(col, _shade(c, 0.8), warp.outputs['Fac'], 'MULTIPLY')
        g.set(**{'Base Color': col, 'Roughness': 0.42, 'Coat Weight': 0.5, 'Coat Roughness': 0.15,
                 'Normal': g.bump(wv.outputs['Fac'], 0.06, 0.002)})

    @staticmethod
    def metal(g, m, c, rough=0.32):
        v = g.uv()
        mp = g.new('ShaderNodeMapping')
        mp.inputs['Scale'].default_value = (400.0, 4.0, 1.0)
        g.link(v, mp.inputs['Vector'])
        br = g.noise(mp.outputs['Vector'], 1.0, 2.0)
        r = g.ramp(br.outputs['Fac'], [(0.3, (rough * 0.8,) * 3 + (1,)), (0.7, (rough * 1.25,) * 3 + (1,))])
        g.set(**{'Base Color': c, 'Metallic': 1.0, 'Roughness': r})

    @staticmethod
    def paint(g, m, c, rough=0.45):
        grain = g.noise(g.uv(), 200.0, 3.0)
        g.set(**{'Base Color': c, 'Roughness': rough, 'Normal': g.bump(grain.outputs['Fac'], 0.03, 0.001)})

    @staticmethod
    def glass(g, m, c, tint=None):
        g.set(**{'Base Color': hex2lin(tint) if tint else c, 'Roughness': 0.02, 'IOR': 1.5, 'Transmission Weight': 1.0,
                 'Thin Wall': True})
        m.surface_render_method = 'DITHERED'
        m.use_raytrace_refraction = True

    @staticmethod
    def polycarb(g, m, c, tint=None):
        v = g.uv()
        mp = g.new('ShaderNodeMapping')
        mp.inputs['Scale'].default_value = (1.0, 60.0, 1.0)
        g.link(v, mp.inputs['Vector'])
        wv = g.new('ShaderNodeTexWave', wave_type='BANDS', bands_direction='Y')
        wv.inputs['Scale'].default_value = 0.5
        g.link(mp.outputs['Vector'], wv.inputs['Vector'])
        g.set(**{'Base Color': hex2lin(tint) if tint else c, 'Roughness': 0.12, 'IOR': 1.58, 'Transmission Weight': 0.88,
                 'Thin Wall': True, 'Normal': g.bump(wv.outputs['Fac'], 0.15, 0.002)})
        m.surface_render_method = 'DITHERED'

    @staticmethod
    def asphalt(g, m, c):
        v = g.uv()
        vor = g.new('ShaderNodeTexVoronoi')
        vor.inputs['Scale'].default_value = 140.0
        g.link(v, vor.inputs['Vector'])
        big = g.noise(v, 0.35, 3.0)
        col = g.ramp(big.outputs['Fac'], [(0.35, _shade(c, 0.85)), (0.65, _shade(c, 1.08))])
        spk = g.ramp(vor.outputs['Distance'], [(0.0, (0.55, 0.55, 0.55, 1)), (0.25, (0, 0, 0, 1))])
        col = g.mix(col, _shade(c, 1.5), spk.node.outputs[0])
        g.set(**{'Base Color': col, 'Roughness': 0.9, 'Normal': g.bump(vor.outputs['Distance'], 0.35, 0.003)})

    @staticmethod
    def concrete(g, m, c):
        v = g.uv()
        big = g.noise(v, 0.8, 4.0)
        fine = g.noise(v, 70.0, 6.0, 0.7)
        col = g.ramp(big.outputs['Fac'], [(0.3, _shade(c, 0.9)), (0.7, _shade(c, 1.05))])
        g.set(**{'Base Color': col, 'Roughness': 0.85, 'Normal': g.bump(fine.outputs['Fac'], 0.12, 0.002)})

    @staticmethod
    def fabric(g, m, c):
        v = g.uv()
        mp = g.new('ShaderNodeMapping')
        mp.inputs['Scale'].default_value = (6.0, 1.0, 1.0)
        g.link(v, mp.inputs['Vector'])
        wv = g.new('ShaderNodeTexWave', wave_type='BANDS', bands_direction='X')
        wv.inputs['Scale'].default_value = 1.0
        g.link(mp.outputs['Vector'], wv.inputs['Vector'])
        col = g.ramp(wv.outputs['Fac'], [(0.0, _shade(c, 0.82)), (1.0, _shade(c, 1.05))])
        g.set(**{'Base Color': col, 'Roughness': 0.9, 'Sheen Weight': 0.4, 'Subsurface Weight': 0.0})

    @staticmethod
    def soil(g, m, c):
        v = g.uv()
        n = g.noise(v, 8.0, 6.0, 0.6)
        col = g.ramp(n.outputs['Fac'], [(0.35, _shade(c, 0.75)), (0.65, _shade(c, 1.15))])
        g.set(**{'Base Color': col, 'Roughness': 0.95, 'Normal': g.bump(n.outputs['Fac'], 0.6, 0.01)})

    @staticmethod
    def leaf(g, m, c):
        var = g.noise(g.obj(), 3.0, 2.0)
        col = g.ramp(var.outputs['Fac'], [(0.3, _shade(c, 0.8)), (0.7, _shade(c, 1.2))])
        g.set(**{'Base Color': col, 'Roughness': 0.45, 'Subsurface Weight': 0.15, 'Subsurface Radius': (0.2, 0.3, 0.05),
                 'Sheen Weight': 0.1})

    @staticmethod
    def room(g, m, c):
        g.set(**{'Base Color': c, 'Roughness': 0.9})

    @staticmethod
    def candy(g, m, c, stripe='#ec8396', period=0.07):
        """Chitose-ame candy stick: diagonal stripes in object space (period metres along the stick), soft sugar SSS, lumpy coat."""
        v = g.obj()
        lump = g.noise(v, 22.0, 3.0)
        wv = g.new('ShaderNodeTexWave', wave_type='BANDS', bands_direction='DIAGONAL', wave_profile='SIN')
        wv.inputs['Scale'].default_value = 0.628 / period
        wv.inputs['Distortion'].default_value = 0.6
        wv.inputs['Detail'].default_value = 1.0
        g.link(v, wv.inputs['Vector'])
        col = g.mix(c, hex2lin(stripe), g.ramp(wv.outputs['Fac'], [(0.5, (0, 0, 0, 1)), (0.62, (1, 1, 1, 1))]).node.outputs[0])
        g.set(**{'Base Color': col, 'Roughness': 0.3, 'Subsurface Weight': 0.5, 'Subsurface Radius': (1.0, 0.55, 0.5),
                 'Subsurface Scale': 0.01, 'Coat Weight': 0.5, 'Coat Roughness': 0.12,
                 'Normal': g.bump(lump.outputs['Fac'], 0.35, 0.002)})

    @staticmethod
    def cord(g, m, c, scale=55.0):
        v = g.obj()
        bands = []
        for rot in (0.785, -0.785):
            mp = g.new('ShaderNodeMapping')
            mp.inputs['Rotation'].default_value = (0.0, rot, 0.0)
            mp.inputs['Scale'].default_value = (scale, scale, scale)
            g.link(v, mp.inputs['Vector'])
            wv = g.new('ShaderNodeTexWave', wave_type='BANDS', bands_direction='X', wave_profile='SAW')
            wv.inputs['Scale'].default_value = 1.0
            g.link(mp.outputs['Vector'], wv.inputs['Vector'])
            bands.append(wv.outputs['Fac'])
        h = g.new('ShaderNodeMath', operation='MAXIMUM')
        g.link(bands[0], h.inputs[0])
        g.link(bands[1], h.inputs[1])
        col = g.ramp(h.outputs[0], [(0.0, _shade(c, 0.55)), (0.6, c), (1.0, _shade(c, 1.15))])
        g.set(**{'Base Color': col, 'Roughness': 0.6, 'Sheen Weight': 0.3, 'Normal': g.bump(h.outputs[0], 0.6, 0.002)})

    @staticmethod
    def emit(g, m, c, strength=5.0):
        g.set(**{'Base Color': c, 'Emission Color': c, 'Emission Strength': strength})
