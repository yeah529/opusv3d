"""Looks: one coherent render style per world (scene).

A look sets the engine and samples, the sky/background, a sun rig, how each material *kind* is built, how
shapes are finished (bevel, flat shading, toon outline), and the post grade that compose.py applies.

Material kinds: body, ground, accent, glass, emit, screen, dark, metal.
The stylised looks render with the Khronos PBR Neutral view transform. Portal images use the colorspace
"Khronos PBR Neutral sRGB" (the inverse), so a portal shows the source frames unchanged (measured mean error
0.0014 on 0..1). Bloom, vignette and tilt-shift happen in compose.py.

'film' is the high-fidelity look: Cycles, AgX view transform, a physical sky (multiple scattering) with a
sun lamp aimed along the sky's sun, adaptive sampling + OpenImageDenoise. Use the procedural PBR materials
in materials.py (World.pbr) for its surfaces. Its sky tuple is ('sky', elevation deg, strength, rotation deg);
the sky's sun sits at direction (sin r, cos r) in plan (r = rotation; measured in Blender 5.2).
Per world: film.world(name, 'film', sky=..., sun=(energy, '#rrggbb', angle)) recolours the sun (the default is a warm
golden-hour sun: use about (4.0, '#fff4e6', 0.6) under a high noon sky); suns=[((rx, ry, rz), energy, colour, angle),
...] replaces it with fixed lamps (a studio: a 'color' or 'gradient' sky); samples={'final': 128} changes Cycles samples.
Portals assume the Khronos view transform, so a portal in a 'film' world is graded twice; avoid that.
"""
import math

import bpy

SAMPLES = {('eevee', 'final'): 64, ('eevee', 'draft'): 8, ('cycles', 'final'): 128, ('cycles', 'draft'): 16}

# post: compose-time grade. bloom = strength, thr = bloom threshold, vig = vignette, con = contrast,
# sat = saturation, tilt = tilt-shift blur (0..1), warm = white balance shift (-1 cool .. 1 warm)
LOOKS = {
    'clay': dict(
        sky=('gradient', '#cfd8e6', '#f3e9dc', 1.0),
        suns=[((50, 0, -35), 3.2, '#fff1de', 6.0), ((60, 0, 150), 0.9, '#cfe0ff', 20.0)],
        body=dict(rough=0.55, sss=0.06), ground=dict(rough=0.8), bevel=0.08,
        post=dict(bloom=0.12, thr=0.85, vig=0.22, con=1.04, sat=1.0, warm=0.1)),
    'voxel': dict(
        sky=('gradient', '#8fc3ff', '#e8f3ff', 1.1),
        suns=[((45, 0, -30), 4.0, '#fff4e0', 2.0), ((65, 0, 140), 0.8, '#bcd6ff', 15.0)],
        body=dict(rough=0.35, coat=0.1), ground=dict(rough=0.6), bevel=0.03,
        post=dict(bloom=0.1, thr=0.9, vig=0.15, con=1.06, sat=1.08)),
    'lowpoly': dict(
        sky=('gradient', '#a7c8f0', '#fbe3c8', 1.0),
        suns=[((55, 0, -40), 3.6, '#fff0d8', 1.0)],
        body=dict(rough=0.85), ground=dict(rough=0.9), bevel=0.0, flat=True, segments=0.35,
        post=dict(bloom=0.05, thr=0.9, vig=0.18, con=1.05, sat=1.05)),
    'glass': dict(
        sky=('gradient', '#1a1f2b', '#05060a', 0.6),
        suns=[((40, 0, -50), 2.5, '#ffffff', 3.0), ((70, 0, 160), 2.0, '#9ec8ff', 3.0), ((80, 0, 40), 1.5, '#ffd2a8', 3.0)],
        body=dict(rough=0.06, trans=1.0, ior=1.45), ground=dict(rough=0.25), bevel=0.06,
        post=dict(bloom=0.35, thr=0.7, vig=0.3, con=1.08, sat=1.05)),
    'paper': dict(
        sky=('gradient', '#efe6d6', '#e8dcc6', 1.1),
        suns=[((50, 0, -30), 3.0, '#fff6e8', 12.0)],
        body=dict(rough=1.0, bump=0.25), ground=dict(rough=1.0, bump=0.3), bevel=0.0,
        post=dict(bloom=0.0, thr=1.0, vig=0.28, con=0.98, sat=0.9, warm=0.15)),
    'toon': dict(
        sky=('gradient', '#bfe3ff', '#ffffff', 1.0),
        suns=[((50, 0, -35), 3.0, '#ffffff', 1.0)],
        body=dict(toon=True), ground=dict(toon=True), bevel=0.04, outline=0.015, engine='eevee',
        post=dict(bloom=0.0, thr=1.0, vig=0.0, con=1.0, sat=1.05)),
    'neon': dict(
        sky=('gradient', '#070912', '#020205', 0.4),
        suns=[((60, 0, -30), 0.6, '#9fb4ff', 4.0)],
        body=dict(rough=0.25, glow=0.6), ground=dict(rough=0.18, dark=0.08), bevel=0.05,
        post=dict(bloom=0.55, thr=0.55, vig=0.35, con=1.06, sat=1.12)),
    'film': dict(
        sky=('sky', 15, 0.12, 217),                   # golden hour; tuned on a test house (sky 0.12 + sun 7 read best)
        suns='sky', sun=(7.0, '#ffb978', 1.0),        # (energy W/m2, colour, angle deg), aimed along the sky sun
        view=('AgX', 'AgX - Medium High Contrast'), engine='cycles', samples=dict(final=256, draft=24),
        body=dict(rough=0.5), ground=dict(rough=0.85), bevel=0.0,
        post=dict(bloom=0.05, thr=0.92, vig=0.16, con=1.0, sat=1.0)),
    'miniature': dict(
        sky=('gradient', '#7fb6ff', '#f2f7ff', 1.2),
        suns=[((38, 0, -40), 4.2, '#fff2dc', 1.5), ((70, 0, 150), 0.7, '#bcd6ff', 20.0)],
        body=dict(rough=0.45, sss=0.04), ground=dict(rough=0.7), bevel=0.05, sat_mul=1.15,
        post=dict(bloom=0.12, thr=0.85, vig=0.2, con=1.08, sat=1.18, tilt=0.8)),
}


def hex2lin(c):
    """'#rrggbb' or (r, g, b[, a]) in sRGB 0..1 -> linear RGBA."""
    if isinstance(c, str):
        h = c.lstrip('#')
        if len(h) != 6 or any(x not in '0123456789abcdefABCDEF' for x in h):
            raise ValueError(f'colour {c!r}: use \'#rrggbb\' (hex) or an (r, g, b) tuple')
        c = tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    rgb = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c[:3]]
    return (*rgb, c[3] if len(c) > 3 else 1.0)


def _sat(rgba, k):
    r, g, b, a = rgba
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return tuple(max(0.0, y + (x - y) * k) for x in (r, g, b)) + (a,)


OVERRIDES = ('sun', 'suns', 'samples', 'persistent')  # per-world look overrides: film.world(name, look, sun=...)


class Look:
    def __init__(self, name, scene, quality='final', sky=None, over=None):
        if name not in LOOKS:
            raise ValueError(f'unknown look "{name}" (known: {", ".join(LOOKS)})')
        self.name, self.scene, self.q = name, scene, quality
        self.d = dict(LOOKS[name])
        if sky is not None:
            self.d['sky'] = sky
        for k, v in (over or {}).items():              # film.world(..., sun=, suns=, samples=)
            if k not in OVERRIDES:
                raise ValueError(f'look {name}: cannot override "{k}" (can: {", ".join(OVERRIDES)})')
            if k == 'samples' and not (isinstance(v, dict) and set(v) <= {'final', 'draft'}
                                       and all(isinstance(n, int) and n > 0 for n in v.values())):
                raise ValueError(f'look {name}: samples={v!r}; use {{"final": 128, "draft": 16}} (positive ints)')
            if k == 'sun' and not (isinstance(v, (tuple, list)) and len(v) == 3 and v[0] >= 0 and v[2] >= 0):
                raise ValueError(f'look {name}: sun={v!r}; use (energy W/m2, "#rrggbb", angle deg)')
            if k == 'suns' and v != 'sky' and not (isinstance(v, (tuple, list)) and all(len(x) == 4 for x in v)):
                raise ValueError(f'look {name}: suns={v!r}; use "sky" or [((rx, ry, rz) deg, energy, "#rrggbb", angle deg), ...]')
            self.d[k] = dict(self.d.get('samples') or {}, **v) if k == 'samples' else v
        self.engine = self.d.get('engine', 'eevee')
        self.mats = {}
        self.post = dict(self.d['post'])

    # ---- scene ----
    def setup(self, prefix):
        sc = self.scene
        view, look = self.d.get('view', ('Khronos PBR Neutral', 'None'))
        sc.view_settings.view_transform = view
        sc.view_settings.look = look
        sc.render.use_motion_blur = True
        sc.render.motion_blur_shutter = 0.5
        e = sc.eevee
        e.use_raytracing = True
        e.ray_tracing_method = 'SCREEN'
        e.use_shadows = True
        e.shadow_ray_count = 2
        e.use_fast_gi = True
        e.use_overscan = True
        e.overscan_size = 3.0
        self.set_engine(self.engine)
        w = bpy.data.worlds.new(prefix + 'world')
        sc.world = w
        w.use_nodes = True
        nt = w.node_tree
        bg = nt.nodes['Background']
        sky = self.d['sky']
        if sky[0] == 'gradient':
            _, top, bottom, strength = sky
            tc = nt.nodes.new('ShaderNodeTexCoord')
            sep = nt.nodes.new('ShaderNodeSeparateXYZ')
            ramp = nt.nodes.new('ShaderNodeValToRGB')
            mr = nt.nodes.new('ShaderNodeMapRange')
            mr.inputs['From Min'].default_value = -0.2
            mr.inputs['From Max'].default_value = 0.8
            nt.links.new(tc.outputs['Generated'], sep.inputs[0])
            nt.links.new(sep.outputs['Z'], mr.inputs['Value'])
            nt.links.new(mr.outputs['Result'], ramp.inputs['Fac'])
            ramp.color_ramp.elements[0].color = hex2lin(bottom)
            ramp.color_ramp.elements[1].color = hex2lin(top)
            nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
            bg.inputs['Strength'].default_value = strength
        elif sky[0] == 'sky':                          # ('sky', sun elevation deg, strength[, rotation deg])
            st = nt.nodes.new('ShaderNodeTexSky')
            st.sun_rotation = math.radians(sky[3] if len(sky) > 3 else 0.0)
            try:
                st.sky_type = 'MULTIPLE_SCATTERING'
            except TypeError:
                st.sky_type = 'NISHITA'
            st.sun_elevation = math.radians(sky[1])
            st.sun_disc = False
            nt.links.new(st.outputs['Color'], bg.inputs['Color'])
            bg.inputs['Strength'].default_value = sky[2]
        else:                                          # ('color', '#hex', strength)
            bg.inputs['Color'].default_value = hex2lin(sky[1])
            bg.inputs['Strength'].default_value = sky[2]
        self.suns = []
        suns = self.d['suns']
        if suns == 'sky':                              # one sun lamp shining from where the sky draws its sun
            if sky[0] != 'sky':
                raise ValueError(f'look {self.name}: suns="sky" needs a ("sky", elevation, strength, rotation) sky; '
                                 f'for a studio or gradient sky pass suns=[((rx, ry, rz), energy, "#rrggbb", angle), ...]')
            r = sky[3] if len(sky) > 3 else 0.0
            energy, color, angle = self.d['sun']
            suns = [((90 - sky[1], 0, 180 - r), energy, color, angle)]
        for i, (rot, energy, color, angle) in enumerate(suns):
            ld = bpy.data.lights.new(f'{prefix}sun{i}', 'SUN')
            ld.energy = energy
            ld.color = hex2lin(color)[:3]
            ld.angle = math.radians(angle)
            ob = bpy.data.objects.new(f'{prefix}sun{i}', ld)
            ob.rotation_euler = [math.radians(a) for a in rot]
            sc.collection.objects.link(ob)
            self.suns.append(ob)

    def set_engine(self, engine):
        sc = self.scene
        if engine == 'cycles':
            sc.render.engine = 'CYCLES'
            p = bpy.context.preferences.addons['cycles'].preferences
            p.compute_device_type = 'METAL'
            p.get_devices()
            for d in p.devices:
                d.use = d.type == 'METAL'
            sc.cycles.device = 'GPU'
            sc.cycles.samples = self.d.get('samples', {}).get(self.q) or SAMPLES[('cycles', self.q)]
            sc.cycles.use_denoising = True
            if 'samples' in self.d:                    # the hi-fi look: noise-driven sampling, GPU denoise
                sc.cycles.use_adaptive_sampling = True
                sc.cycles.adaptive_threshold = 0.01 if self.q == 'final' else 0.05
                sc.cycles.denoiser = 'OPENIMAGEDENOISE'
                sc.cycles.denoising_use_gpu = True
                sc.cycles.blur_glossy = 0.5           # filter glossy: fewer fireflies from glass and metal
                sc.cycles.caustics_reflective = sc.cycles.caustics_refractive = False
                # keep BVH and textures between frames. persistent=False: an animation render with it on drew one frame
                # wrong (the frame after a motion-blurred object stops: a dark hilt; a still of that frame was right)
                sc.render.use_persistent_data = self.d.get('persistent', True)
        else:
            if self.name == 'toon' and engine != 'eevee':
                raise ValueError('toon look needs EEVEE (Shader to RGB)')
            sc.render.engine = 'BLENDER_EEVEE'
            sc.eevee.taa_render_samples = self.d.get('samples', {}).get(self.q) or SAMPLES[('eevee', self.q)]

    # ---- materials ----
    def mat(self, name, color='#cccccc', kind='body', attr=None, strength=None):
        """Material of a kind in this look. attr: name of an INSTANCER colour attribute (assembly pieces)."""
        key = (name, kind)
        if key in self.mats:
            return self.mats[key]
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        N, L = nt.nodes, nt.links
        b = N['Principled BSDF']
        out = N['Material Output']
        rgba = _sat(hex2lin(color), self.d.get('sat_mul', 1.0))
        col_in = None                                  # socket that carries the base colour
        if attr:
            a = N.new('ShaderNodeAttribute')
            a.attribute_type = 'INSTANCER'
            a.attribute_name = attr
            col_in = a.outputs['Color']
        p = dict(self.d.get(kind, self.d['body'])) if kind in ('body', 'ground') else {}
        if kind in ('emit', 'screen'):
            N.remove(b)
            em = N.new('ShaderNodeEmission')
            em.inputs['Strength'].default_value = strength if strength is not None else (1.0 if kind == 'screen' else 4.0)
            if col_in:
                L.new(col_in, em.inputs['Color'])
            else:
                em.inputs['Color'].default_value = rgba
            L.new(em.outputs[0], out.inputs['Surface'])
            self.mats[key] = m
            return m
        if kind == 'glass' or p.get('trans'):
            b.inputs['Transmission Weight'].default_value = 1.0
            b.inputs['Roughness'].default_value = p.get('rough', 0.04)
            b.inputs['IOR'].default_value = p.get('ior', 1.45)
            m.use_raytrace_refraction = True
            m.surface_render_method = 'DITHERED'
        elif p.get('toon'):
            N.remove(b)
            dif = N.new('ShaderNodeBsdfDiffuse')
            s2r = N.new('ShaderNodeShaderToRGB')
            ramp = N.new('ShaderNodeValToRGB')
            ramp.color_ramp.interpolation = 'CONSTANT'
            ramp.color_ramp.elements[0].color = (0.42, 0.42, 0.46, 1)
            ramp.color_ramp.elements[1].position = 0.35
            ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
            mul = N.new('ShaderNodeMix')
            mul.data_type = 'RGBA'
            mul.blend_type = 'MULTIPLY'
            mul.inputs['Factor'].default_value = 1.0
            em = N.new('ShaderNodeEmission')
            L.new(dif.outputs[0], s2r.inputs[0])
            L.new(s2r.outputs['Color'], ramp.inputs['Fac'])
            L.new(ramp.outputs['Color'], _socket(mul, 'A_Color'))
            if col_in:
                L.new(col_in, _socket(mul, 'B_Color'))
            else:
                _socket(mul, 'B_Color').default_value = rgba
            L.new(_socket(mul, 'Result_Color', out=True), em.inputs['Color'])
            L.new(em.outputs[0], out.inputs['Surface'])
            self.mats[key] = m
            return m
        else:
            b.inputs['Roughness'].default_value = {'accent': 0.3, 'metal': 0.25, 'dark': 0.5}.get(kind, p.get('rough', 0.5))
            if kind == 'metal':
                b.inputs['Metallic'].default_value = 1.0
            if p.get('sss'):
                b.inputs['Subsurface Weight'].default_value = p['sss']
                b.inputs['Subsurface Radius'].default_value = (0.1, 0.05, 0.03)
            if p.get('coat'):
                b.inputs['Coat Weight'].default_value = p['coat']
            if p.get('bump'):
                nz = N.new('ShaderNodeTexNoise')
                nz.inputs['Scale'].default_value = 180.0
                nz.inputs['Detail'].default_value = 6.0
                bm = N.new('ShaderNodeBump')
                bm.inputs['Strength'].default_value = p['bump']
                bm.inputs['Distance'].default_value = 0.002
                L.new(nz.outputs['Fac'], bm.inputs['Height'])
                L.new(bm.outputs['Normal'], b.inputs['Normal'])
        if kind == 'dark':
            rgba = tuple(x * 0.15 for x in rgba[:3]) + (1,)
        if p.get('dark'):
            rgba = tuple(x * p['dark'] for x in rgba[:3]) + (1,)
        if col_in:
            L.new(col_in, b.inputs['Base Color'])
        else:
            b.inputs['Base Color'].default_value = rgba
        glow = p.get('glow', 0.0) if kind == 'body' else (1.5 if kind == 'accent' and self.name == 'neon' else 0.0)
        if glow:
            if col_in:
                L.new(col_in, b.inputs['Emission Color'])
            else:
                b.inputs['Emission Color'].default_value = rgba
            b.inputs['Emission Strength'].default_value = glow
            if kind == 'body':
                b.inputs['Base Color'].default_value = tuple(x * 0.2 for x in rgba[:3]) + (1,)
                if col_in:
                    nt.links.remove(b.inputs['Base Color'].links[0])
        self.mats[key] = m
        return m

    # ---- shape finish ----
    def finish(self, ob, kind='body', bevel=None):
        """Per-look modifiers: bevel (fraction of the smallest dimension), flat shading, toon outline."""
        me = ob.data
        if not hasattr(me, 'polygons'):
            return ob
        flat = self.d.get('flat', False)
        me.polygons.foreach_set('use_smooth', [not flat] * len(me.polygons))
        bv = self.d.get('bevel', 0.0) if bevel is None else bevel
        if bv > 0 and kind not in ('screen', 'emit', 'ground'):
            dims = sorted(x for x in ob.dimensions if x > 1e-6) or [1.0]
            mod = ob.modifiers.new('bevel', 'BEVEL')
            mod.width = bv * dims[0]
            mod.segments = 4
            mod.limit_method = 'ANGLE'
            mod.harden_normals = True
        if self.d.get('outline') and kind not in ('screen', 'emit', 'glass', 'ground'):
            dims = sorted(x for x in ob.dimensions if x > 1e-6) or [1.0]
            line = self.outline_mat()
            if line.name not in [m.name for m in me.materials if m]:
                me.materials.append(line)
            so = ob.modifiers.new('outline', 'SOLIDIFY')
            so.thickness = self.d['outline'] * max(dims[-1], 0.2)
            so.offset = 1.0
            so.use_flip_normals = True
            so.use_rim = False
            so.material_offset = len(me.materials) - 1
        return ob

    def outline_mat(self):
        key = ('outline', 'line')
        if key not in self.mats:
            m = bpy.data.materials.new(f'{self.scene.name}.outline')
            m.use_nodes = True
            nt = m.node_tree
            nt.nodes.remove(nt.nodes['Principled BSDF'])
            em = nt.nodes.new('ShaderNodeEmission')
            em.inputs['Color'].default_value = (0.02, 0.02, 0.03, 1)
            nt.links.new(em.outputs[0], nt.nodes['Material Output'].inputs['Surface'])
            m.use_backface_culling = True
            self.mats[key] = m
        return self.mats[key]

    def segments(self, n):
        return max(3, int(round(n * self.d.get('segments', 1.0))))


def _socket(node, ident, out=False):
    for s in (node.outputs if out else node.inputs):
        if s.identifier == ident:
            return s
    raise KeyError(ident)
