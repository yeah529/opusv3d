"""Film and World: build every world as a Blender scene, apply the timeline, render shots.

usage inside Blender:  Blender -b --factory-startup -P film.py -- <command> [options]
commands:
  plan     check the timeline, print shots, render ranges, order and frame counts (no rendering)
  stills   render a few frames per shot to out/<q>/stills/ (or --at 1.5,7.2 seconds)
  render   render all frames of all shots (resumable) to out/<q>/shots/<id>/#####.jpg
  export   write out/<q>/render.json, anchors.json and out/events.json only
  blend    save out/<q>/film.blend to inspect in the Blender UI
options:
  --draft          half resolution, low samples, separate out/draft/
  --shots s1,s4    only these shots
  --at 1.5,7.2     stills at these times (seconds or "bar:3" style)
"""
import json
import os
import sys
import time

import bpy

from . import anim, camera, transitions
from .looks import Look
from .timeline import Timeline, TimelineError, signature


def jpeg_ok(path):
    """A complete JPEG: starts with SOI and ends with EOI (a killed render leaves empty or cut-off files)."""
    try:
        if os.path.getsize(path) < 4:
            return False
        with open(path, 'rb') as f:
            head = f.read(2)
            f.seek(-2, 2)
            return head == b'\xff\xd8' and f.read(2) == b'\xff\xd9'
    except OSError:
        return False


class World:
    def __init__(self, film, name, look='clay', sky=None, post=None, **over):
        self.film, self.name = film, name
        sc = self.scene = bpy.data.scenes.new(name)
        sc.render.fps, sc.render.fps_base = film.tl.fps, 1.0
        w, h = film.tl.size
        if film.draft:                     # half size, rounded to even numbers (libx264 needs even sizes)
            w, h = max(2, w // 4 * 2), max(2, h // 4 * 2)
        sc.render.resolution_x, sc.render.resolution_y = w, h
        sc.render.resolution_percentage = 100
        sc.frame_start, sc.frame_end = 0, film.tl.frames - 1
        st = sc.render.image_settings
        st.file_format = 'JPEG'
        st.quality = 85 if film.draft else 94
        sc.render.use_overwrite = False
        sc.render.use_placeholder = True
        sc.render.use_file_extension = True
        self.coll = sc.collection
        self.parts = bpy.data.collections.new(name + '.parts')
        self.coll.children.link(self.parts)
        self.parts.hide_render = True
        self.parts.hide_viewport = True
        self.look = Look(look, sc, film.q, sky, over)
        self.look.setup(name + '.')
        if post:
            self.look.post.update(post)

    def n(self, name):
        return f'{self.name}.{name}'

    def __getitem__(self, name):
        ob = bpy.data.objects.get(self.n(name))
        if ob is None:
            raise KeyError(f'no object "{name}" in world {self.name}')
        return ob

    def get(self, name):
        return bpy.data.objects.get(self.n(name))

    def mat(self, color, kind='body', attr=None, strength=None):
        nm = f'{self.name}.{kind}.{color}' + (f'.{attr}' if attr else '') + (f'.s{strength}' if strength is not None else '')
        return self.look.mat(nm, color, kind, attr, strength)

    def pbr(self, name, preset, color=None, **kw):
        """Procedural PBR material (materials.py presets: plaster, tiles, brick, clay_tile, wood, metal, ...)."""
        from . import materials
        return materials.pbr(f'{self.name}.{name}', preset, color, **kw)

    def empty(self, name, loc=(0, 0, 0), parent=None, coll=None):
        ob = bpy.data.objects.new(self.n(name), None)
        ob.empty_display_size = 0.2
        ob.location = loc
        (coll or self.coll).objects.link(ob)
        if parent is not None:
            ob.parent = parent
        return ob

    def collection(self, name):
        c = bpy.data.collections.new(self.n(name))
        self.coll.children.link(c)
        return c

    def instance(self, name, collection, loc=(0, 0, 0), scale=1.0, rot=(0, 0, 0), parent=None):
        """Show another collection (possibly from another world) here, e.g. a miniature of a whole world."""
        import math
        ob = self.empty(name, loc, parent)
        ob.instance_type = 'COLLECTION'
        ob.instance_collection = collection
        ob.scale = (scale,) * 3 if not hasattr(scale, '__len__') else scale
        ob.rotation_euler = [math.radians(a) for a in rot]
        return ob

    def camera(self, shot, lens=35.0, loc=(0, -10, 2), target=(0, 0, 0), **kw):
        return camera.make(self, shot, lens, loc, target, **kw)


class Film:
    def __init__(self, file):
        self.dir = os.path.dirname(os.path.abspath(file))
        argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
        cmds, self.draft, self.only, self.at = [], False, None, None
        i = 0
        while i < len(argv):
            a = argv[i]
            if a in ('--shots', '--at'):
                if i + 1 >= len(argv) or argv[i + 1].startswith('--'):
                    sys.exit(f'opusv3d: {a} needs a value, e.g. {a} {"s1,s4" if a == "--shots" else "1.5,bar:3"}')
                vals = [x for x in argv[i + 1].split(',') if x]
                if a == '--shots':
                    self.only = vals
                else:
                    self.at = vals
                i += 2
                continue
            if a == '--draft':
                self.draft = True
            elif a.startswith('-'):
                sys.exit(f'opusv3d: unknown option "{a}" (--draft, --shots, --at)')
            else:
                cmds.append(a)
            i += 1
        if len(cmds) > 1:
            sys.exit(f'opusv3d: one command at a time, got {" ".join(cmds)}')
        self.cmd = cmds[0] if cmds else 'plan'
        if self.cmd not in ('plan', 'stills', 'render', 'export', 'blend'):
            sys.exit(f'opusv3d: unknown command "{self.cmd}" (plan | stills | render | export | blend)')
        try:
            self.tl = Timeline(os.path.join(self.dir, 'timeline.json'))
            for sid in self.only or []:
                self.tl.shot(sid)
            for x in self.at or []:
                self.tl.T(x)
        except (TimelineError, KeyError) as e:
            sys.exit(f'opusv3d: timeline.json: {e}')
        self.q = 'draft' if self.draft else 'final'
        self.out = os.path.join(self.dir, 'out', self.q)
        anim.FPS = self.tl.fps
        anim.EVENTS.clear()
        self.worlds = {}
        self.portals = {}          # surface name -> dict(surface, shot, windows, fade)
        self.anchors = {}
        self.ranges = {}
        self._finalized = False
        self.F = self.tl.F
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob)
        bpy.context.scene.name = '_unused'          # Blender needs one scene; worlds are new scenes

    def T(self, v):
        """Seconds for a time in timeline syntax (12.5, "bar:5", "@mark-0.25"); a bad one stops with a clear message."""
        try:
            return self.tl.T(v)
        except TimelineError as e:
            sys.exit(f'opusv3d: film.py: {e} (marks in timeline.json: {", ".join(self.tl.marks) or "none"})')

    # ---- building ----
    def world(self, name, look='clay', sky=None, post=None, **over):
        """over: look overrides sun=, suns=, samples= (looks.py)."""
        if name in self.worlds:
            raise ValueError(f'world {name} exists')
        w = self.worlds[name] = World(self, name, look, sky, post, **over)
        return w

    def world_of(self, shot):
        if shot.world not in self.worlds:
            raise ValueError(f'shot {shot.id}: world "{shot.world}" was never created in film.py')
        return self.worlds[shot.world]

    def obj(self, full):
        ob = bpy.data.objects.get(full)
        if ob is None:
            raise KeyError(full)
        return ob

    def cam(self, shot):
        s = shot if not isinstance(shot, str) else self.tl.shot(shot)
        w = self.world_of(s)
        ob = w.get(s.cam)
        if ob is None or ob.type != 'CAMERA':
            raise ValueError(f'shot {s.id}: camera "{w.n(s.cam)}" not found (use {s.world}.camera("{s.id}", ...))')
        return ob

    def event(self, t, kind, **kw):
        anim.emit(self.T(t), kind, **kw)

    def portal(self, surface, shot, since=None, until=None, fade=None, _cover=None):
        """Make `surface` (a flat plane, local +Z normal) show the frames of `shot`.
        The shot is rendered over [since, until] in addition to its own time; outside its rendered range the
        surface holds the first/last frame. fade=(t0, t1): opacity ramps 0 -> 1 (hidden before t0)."""
        sid = shot if isinstance(shot, str) else shot.id
        self.tl.shot(sid)
        p = self.portals.setdefault(surface.name, dict(surface=surface, shot=sid, windows=[], fade=None))
        if p['shot'] != sid:
            raise ValueError(f'{surface.name} already shows {p["shot"]}; one surface shows one shot')
        s = self.tl.shot(sid)
        p['windows'].append((self.T(since) if since is not None else s.t0, self.T(until) if until is not None else s.t1))
        if fade:
            p['fade'] = (self.T(fade[0]), self.T(fade[1]))

    def through(self, surface, shot, point, t):
        """World position on `surface` where `point` (object or position in the shot's world) appears at t."""
        s = self.tl.shot(shot) if isinstance(shot, str) else shot
        x, y, _ = camera.ndc(self.world_of(s).scene, self.cam(s), point, self.F(self.T(t)))
        sf = camera.surface_frame(surface, self.tl.size[0] / self.tl.size[1], f=self.F(self.T(t)))
        from mathutils import Vector
        lo = sf['lo'] + Vector(((x - .5) * sf['wf'] / sf['sx'], (y - .5) * sf['hf'] / sf['sy'], 0))
        return sf['mw'] @ lo

    # ---- finalize ----
    def finalize(self):
        if self._finalized:
            return
        tl = self.tl
        for s in tl.shots:
            self.cam(s)
        for tr in tl.transitions:
            if tr.kind == 'world':
                transitions.apply_world(self, tr)
        for tr in tl.transitions:
            if tr.kind == 'post' and tr.type != 'cut':
                self._match(tr)
        for tr in tl.transitions:                      # world transitions emit their own cues
            if tr.kind == 'post':
                kind = {'cut': 'hit', 'fade': 'swell', 'iris': 'iris', 'lens': 'lens', 'breach': 'ripple'}[tr.type]
                anim.emit(tr.window()[0], kind, gain=0.7, dur=tr.dur, auto=tr.type)
        self._ranges()
        self._portal_materials()
        self._finalized = True

    def _match(self, tr):
        """Anchor matching: lens-shift B's camera so B's anchor sits where A's anchor is, during the
        transition window, then ease the shift back to its authored value over `settle` seconds."""
        wa, wb = self.world_of(tr.a), self.world_of(tr.b)
        ca, cb = self.cam(tr.a), self.cam(tr.b)
        oa, ob = wa.get(tr.anchor[0]), wb.get(tr.anchor[1])
        if tr.match:
            for name, o, w in ((tr.anchor[0], oa, wa), (tr.anchor[1], ob, wb)):
                if o is None:
                    raise ValueError(f'{tr.type} {tr.a.id}>{tr.b.id}: anchor "{name}" is not an object in world {w.name}; '
                                     f'set "anchor" to an object name, or "match": false to use the frame centre')
        w0, w1 = tr.window()
        f0, f1 = self.F(w0), max(self.F(w0), self.F(w1))
        rec = []
        W, H = self.tl.size
        sx, sy = {}, {}
        for f in range(f0, f1 + 1):
            pa = camera.ndc(wa.scene, ca, oa, f)[:2] if oa else (0.5, 0.5)
            pb = camera.ndc(wb.scene, cb, ob, f)[:2] if ob else (0.5, 0.5)
            if tr.match and oa and ob:
                cbe = cb.evaluated_get(wb.scene.view_layers[0].depsgraph)   # evaluated at f by ndc()
                bx, by = cbe.data.shift_x, cbe.data.shift_y
                sx[f], sy[f] = bx + (pb[0] - pa[0]), by + (pb[1] - pa[1]) * H / W
            rec.append([f, pa, pb])
        if sx:
            end = w1 + tr.settle
            wb.scene.frame_set(self.F(end))
            cbe = cb.evaluated_get(wb.scene.view_layers[0].depsgraph)
            ex, ey = cbe.data.shift_x, cbe.data.shift_y
            anim.bake(cb.data, 'shift_x', f0 / self.tl.fps, f1 / self.tl.fps, lambda t: sx[self.F(t)])
            anim.bake(cb.data, 'shift_y', f0 / self.tl.fps, f1 / self.tl.fps, lambda t: sy[self.F(t)])
            anim.key(cb.data, 'shift_x', [(f1 / self.tl.fps, sx[f1]), (end, ex)])
            anim.key(cb.data, 'shift_y', [(f1 / self.tl.fps, sy[f1]), (end, ey)])
            cb.data.update_tag()
            wb.scene.frame_set(f0 - 1)
            rec = [[f, pa, list(camera.ndc(wb.scene, cb, ob, f)[:2])] for f, pa, _ in rec]
        self.anchors[f'{tr.a.id}>{tr.b.id}'] = dict(type=tr.type, frames=rec, matched=bool(sx),
                                                   missing=[n for n, o in zip(tr.anchor, (oa, ob)) if o is None])

    def _ranges(self):
        tl = self.tl
        for s in tl.shots:
            f0, f1 = tl.handles(s)
            for p in self.portals.values():
                if p['shot'] == s.id:
                    for a, b in p['windows']:
                        f0, f1 = min(f0, self.F(a)), max(f1, self.F(b))
            self.ranges[s.id] = (max(0, f0), min(tl.frames - 1, f1))

    def shot_dir(self, sid):
        return os.path.join(self.out, 'shots', sid)

    def _portal_materials(self):
        aspect = self.tl.size[0] / self.tl.size[1]
        for name, p in self.portals.items():
            surf, sid = p['surface'], p['shot']
            a, b = self.ranges[sid]
            sf = camera.surface_frame(surf, aspect)
            me = surf.data
            uv = me.uv_layers.get('portal') or me.uv_layers.new(name='portal')
            co = [v.co for v in me.vertices]
            uvs = []
            for loop in me.loops:
                c = co[loop.vertex_index]
                uvs += [0.5 + (c.x - sf['lo'].x) * sf['sx'] / sf['wf'], 0.5 + (c.y - sf['lo'].y) * sf['sy'] / sf['hf']]
            uv.data.foreach_set('uv', uvs)
            img = bpy.data.images.new(f'portal.{sid}', 16, 16)
            img.source = 'SEQUENCE'
            img.filepath = os.path.join(self.shot_dir(sid), '00000.jpg')
            try:                                       # inverse of the view transform -> pass-through
                img.colorspace_settings.name = 'Khronos PBR Neutral sRGB'
            except TypeError:
                img.colorspace_settings.name = 'sRGB'
            m = bpy.data.materials.new(f'portal.{name}')
            m.use_nodes = True
            nt = m.node_tree
            N, L = nt.nodes, nt.links
            N.remove(N['Principled BSDF'])
            uvn = N.new('ShaderNodeUVMap')
            uvn.uv_map = 'portal'
            tex = N.new('ShaderNodeTexImage')
            tex.image = img
            tex.extension = 'EXTEND'
            tex.interpolation = 'Linear'
            iu = tex.image_user
            iu.frame_start, iu.frame_offset, iu.frame_duration = a + 1, a, max(1, b - a)
            iu.use_auto_refresh, iu.use_cyclic = True, False
            em = N.new('ShaderNodeEmission')
            em.inputs['Strength'].default_value = 1.0
            L.new(uvn.outputs['UV'], tex.inputs['Vector'])
            L.new(tex.outputs['Color'], em.inputs['Color'])
            out = N['Material Output']
            if p['fade']:
                tr_ = N.new('ShaderNodeBsdfTransparent')
                mix = N.new('ShaderNodeMixShader')
                val = N.new('ShaderNodeValue')
                val.name = 'opacity'
                L.new(val.outputs[0], mix.inputs['Fac'])
                L.new(tr_.outputs[0], mix.inputs[1])
                L.new(em.outputs[0], mix.inputs[2])
                L.new(mix.outputs[0], out.inputs['Surface'])
                t0, t1 = p['fade']
                end = max(b for _, b in p['windows']) + 3 / self.tl.fps   # hidden again once the dive is over
                fp = 'nodes["opacity"].outputs[0].default_value'
                anim.key(nt, fp, [(t0 - 1 / self.tl.fps, 0.0), (t0, 0.0), (t1, 1.0, 'smooth')])
                anim.key(nt, fp, [(end, 1.0), (end + 1 / self.tl.fps, 0.0, 'step')])
                m.surface_render_method = 'DITHERED'
                m.use_transparent_shadow = True
            else:
                L.new(em.outputs[0], out.inputs['Surface'])
            me.materials.clear()
            me.materials.append(m)
            p['image'] = img

    def deps(self):
        """shot -> set of shots whose frames it shows through portals (in its world)."""
        d = {s.id: set() for s in self.tl.shots}
        for p in self.portals.values():
            wname = p['surface'].users_scene[0].name if p['surface'].users_scene else None
            for s in self.tl.shots:
                if s.world == wname and p['shot'] != s.id:
                    d[s.id].add(p['shot'])
        return d

    def order(self):
        d, done, out = self.deps(), set(), []

        def visit(s, stack):
            if s in done:
                return
            if s in stack:
                raise ValueError(f'portal cycle: {" -> ".join(stack + [s])}')
            for x in sorted(d[s]):
                visit(x, stack + [s])
            done.add(s)
            out.append(s)
        for s in self.tl.shots:
            visit(s.id, [])
        return out

    # ---- outputs ----
    def signature(self):
        return signature(self.dir, self.q)

    def export(self):
        os.makedirs(self.out, exist_ok=True)
        tl = self.tl
        man = dict(name=tl.name, sig=self.signature(), fps=tl.fps, size=list(tl.size), draft=self.draft,
                   frames=tl.frames, order=self.order(), shots={})
        for s in tl.shots:
            w = self.world_of(s)
            man['shots'][s.id] = dict(world=s.world, look=w.look.name, range=list(self.ranges[s.id]), post=w.look.post,
                                      engine=s.engine or w.look.engine)
        json.dump(man, open(os.path.join(self.out, 'render.json'), 'w'), indent=1)
        json.dump(self.anchors, open(os.path.join(self.out, 'anchors.json'), 'w'))
        ev = sorted(anim.EVENTS, key=lambda e: e['t'])
        json.dump(dict(fps=tl.fps, dur=tl.dur, events=ev), open(os.path.join(self.dir, 'out', 'events.json'), 'w'), indent=0)
        return man

    def run(self):
        t_start = time.time()
        try:
            self.finalize()
        except (ValueError, KeyError) as e:
            sys.exit(f'opusv3d: {e}')
        man = self.export()
        if self.cmd == 'plan':
            self.print_plan(man)
        elif self.cmd == 'blend':
            p = os.path.join(self.out, 'film.blend')
            bpy.ops.wm.save_as_mainfile(filepath=p)
            print('opusv3d: saved', p)
        elif self.cmd == 'stills':
            self.stills()
        elif self.cmd == 'render':
            self.render(man)
        print(f'opusv3d: {self.cmd} done in {time.time() - t_start:.1f} s')

    def print_plan(self, man):
        tl = self.tl
        print(f'opusv3d plan: {tl.name}  {tl.dur:.2f} s  {tl.fps} fps  {tl.frames} frames  {tl.size[0]}x{tl.size[1]}'
              f'  quality={self.q}')
        print(f'{"shot":6} {"world":10} {"look":10} {"on screen":>14} {"render frames":>16} {"n":>5}  in')
        total = 0
        for s in tl.shots:
            a, b = self.ranges[s.id]
            total += b - a + 1
            tin = f'{s.tin.type} @{s.tin.t:.2f}' + (f' dur {s.tin.dur}' if s.tin.dur else '') if s.tin else '-'
            print(f'{s.id:6} {s.world:10} {self.world_of(s).look.name:10} {s.t0:6.2f}-{s.t1:6.2f}s {a:7d}-{b:<7d} {b - a + 1:5d}  {tin}')
        d = self.deps()
        print('render order:', ' '.join(man['order']), ' (portal sources first)')
        for k, v in d.items():
            if v:
                print(f'  {k} shows {", ".join(sorted(v))} through a portal')
        for k, v in self.anchors.items():
            if v['missing']:
                print(f'  warning: {k}: anchor object(s) {v["missing"]} not found; using frame centre')
        print(f'total rendered frames: {total}')

    def _targets(self):
        ids = self.only or [s.id for s in self.tl.shots]
        for i in ids:
            self.tl.shot(i)
        return [s for s in self.order() if s in ids]

    def _prep(self, s):
        w = self.world_of(s)
        sc = w.scene
        sc.camera = self.cam(s)
        w.look.set_engine(s.engine or w.look.engine)
        for p in self.portals.values():
            if p['surface'].name in sc.objects:
                p['image'].reload()
        return sc

    def render(self, man):
        sig = man['sig']
        for sid in self._targets():
            s = self.tl.shot(sid)
            sc = self._prep(s)
            d = self.shot_dir(sid)
            os.makedirs(d, exist_ok=True)
            sigf, donef = os.path.join(d, '.sig'), os.path.join(d, '.done')
            old = open(sigf).read() if os.path.exists(sigf) else None
            if old != sig:
                for f in os.listdir(d):
                    if f.endswith('.jpg') or f == '.done':
                        os.remove(os.path.join(d, f))
                open(sigf, 'w').write(sig)
            for f in os.listdir(d):                              # placeholders and cut-off files of a killed render
                if f.endswith('.jpg') and not jpeg_ok(os.path.join(d, f)):
                    os.remove(os.path.join(d, f))
            a, b = self.ranges[sid]
            sc.frame_start, sc.frame_end = a, b
            sc.render.filepath = os.path.join(d, '#####')
            have = sum(1 for f in range(a, b + 1) if os.path.exists(os.path.join(d, f'{f:05d}.jpg')))
            print(f'opusv3d: render {sid} frames {a}-{b} ({b - a + 1 - have} to do) engine {sc.render.engine}', flush=True)
            t = time.time()
            if have < b - a + 1:
                bpy.ops.render.render(animation=True, scene=sc.name)
            bad = [f for f in range(a, b + 1) if not jpeg_ok(os.path.join(d, f'{f:05d}.jpg'))]
            if bad:
                sys.exit(f'opusv3d: shot {sid}: {len(bad)} frames missing or incomplete after render, e.g. {bad[:5]}')
            open(donef, 'w').write(sig)
            n = b - a + 1 - have
            print(f'opusv3d: {sid} done, {n} frames in {time.time() - t:.1f} s' + (f' ({(time.time() - t) / n:.2f} s/frame)' if n else ''), flush=True)

    def stills(self):
        d = os.path.join(self.out, 'stills')
        os.makedirs(d, exist_ok=True)
        jobs = []
        if self.at:
            for x in self.at:
                f = self.F(self.T(x))
                jobs.append((self.tl.active(f), f))
        else:
            for sid in self._targets():
                s = self.tl.shot(sid)
                for t in (s.t0 + 0.05, (s.t0 + s.t1) / 2, s.t1 - 0.1):
                    jobs.append((s, self.F(t)))
        for s, f in jobs:
            sc = self._prep(s)
            sc.frame_set(f)
            sc.render.filepath = os.path.join(d, f'{s.id}_{f:05d}.jpg')
            sc.render.use_overwrite = True
            t = time.time()
            with bpy.context.temp_override(scene=sc):          # a still renders the context scene's frame
                bpy.ops.render.render(write_still=True)
            sc.render.use_overwrite = False
            print(f'opusv3d: still {s.id} frame {f} ({f / self.tl.fps:.2f} s) in {time.time() - t:.1f} s', flush=True)
