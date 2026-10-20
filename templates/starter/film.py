"""opusv3d starter film: SCREEN -> DESK -> MEADOW -> DESK, one yellow hero, every transition generator.

  s1 SCREEN  a cursor spits out pixels -> the pixels extrude to voxels -> they melt into the smooth hero
  s2 DESK    pull_out: the screen was a monitor on a desk
  s3 DESK    cut: insert on the monitor; the hero lunges at the glass
  s4 DESK    breach: it comes out of the screen, hops over the keyboard and dives into a glass key
  s5 MEADOW  push_in through the key: an island; a tree grows, fruit clones fall, they build a giant
  s6 MEADOW  lens: low angle on the giant
  s7 DESK    iris: the whole island is a diorama on the key; pull back to the monitor (bookend)

Run: Blender -b --factory-startup --python-exit-code 1 -P film.py -- plan | stills [--at 1,5] | render [--draft]
     or sh build.sh [--draft] for the whole film (render, compose, mix, mux, seamcheck)
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engine'))
from mathutils import Vector  # noqa: E402

from v3d import *  # noqa: E402,F401,F403
from v3d import shapes as S  # noqa: E402

film = Film(__file__)
T = film.T
YEL, INK = '#F2C230', '#15161a'
PAL = {'Y': YEL, 'K': INK}


def into(coll, *obs):
    """Move objects (and their children) into a collection, e.g. one that another world instances."""
    for ob in obs:
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        coll.objects.link(ob)
        into(coll, *ob.children)


# ============ SCREEN: the terminal world inside the monitor (neon) ============
SC = film.world('SCREEN', look='neon')
S.box(SC, 'floor', (40, 40, 0.1), (0, 8, -0.1), color='#0b0e1a', kind='ground')
for i in range(-6, 7):
    S.box(SC, f'gx{i}', (0.025, 26, 0.004), (i * 1.0, 8, 0), color='#1d46b8', kind='accent')
for j in range(-3, 18):
    S.box(SC, f'gy{j}', (13, 0.025, 0.004), (0, j * 1.0, 0), color='#1d46b8', kind='accent')
S.text(SC, 'prompt', '>', size=0.5, loc=(-3.05, 0, 2.15), color='#5cf2a0', strength=3.0)
cursor = S.box(SC, 'cursor', (0.22, 0.04, 0.36), (-2.62, 0, 2.15), color='#5cf2a0', kind='emit')
visible(cursor, [(k * 0.5, k * 0.5 + 0.3) for k in range(26)])          # blinks on the beat
CUR = Vector((-2.62, 0, 2.33))

cell = 0.25
px = S.pixels(S.HERO_PIXELS, PAL, cell=cell)
cells = [(x, 0.0, z + 0.9) for x, z, _ in px]
cols = [c for _, _, c in px]
plate = S.cube_piece(SC, 'px', bevel=0.06)
PLATE = (cell, 0.12 * cell, cell)
hero_s = S.hero(SC, 'hero', size=2.0)

# 1) pixels fly out of the cursor  2) extrude to voxels  3) melt into the smooth hero
assemble(SC, 'px1', plate, cells, T('@assemble'), 1.5, cols, start='point', point=CUR, order='dist', stagger=0.6,
         arc=0.3, spin=0.6, scale=PLATE, until=T('@lift') + 0.02)
LIFT, MELT = 1.4, 0.35
lift(SC, 'lift', plate, cells, T('@lift'), LIFT, cols, cell=cell, plate=0.12, axis=(0, -1, 0), then=hero_s, melt=MELT)
born = T('@lift') + LIFT * (1 - MELT)
hops(hero_s, 3.6, [(0, 0, 0), (0, 0, 0)], dt=0.4, height=0.5)
blink([SC['hero.eyeL'], SC['hero.eyeR']], 4.3)
blink([SC['hero.eyeL'], SC['hero.eyeR']], 5.6)
key(hero_s, 'rotation_euler', [(6.0, (0, 0, 0)), (6.35, (0, 0, math.radians(25))), (6.8, (0, 0, math.radians(-20))),
                               (7.2, (0, 0, 0))])
blink([SC['hero.eyeL'], SC['hero.eyeR']], 7.5)
LUNGE = Vector((0, -1.4, 0.3))
hop(hero_s, 8.2, T('@breach'), (0, 0, 0), LUNGE, height=0.3)  # lunges at the glass ...
visible(hero_s, [(born, T('@breach'))])                                 # ... and is gone: it came out
assemble(SC, 'px2', plate, cells, 9.6, 1.4, cols, start='point', point=CUR, order='dist', stagger=0.7, arc=0.3,
         spin=0.6, scale=PLATE, sound=None)                            # the icon re-forms (bookend)

c1 = SC.camera('s1', lens=35)
camera.path(c1, [(0.0, (-2.3, -2.2, 2.4), (-2.75, 0, 2.3)),
                 (2.6, (0, -6.5, 1.3), (0, 0, 0.9), 'smooth')])     # one move that follows the pixels

# ============ DESK: a clay desk with the monitor and a keyboard with one glass key ============
D = film.world('DESK', look='clay')
S.box(D, 'desk', (3.4, 1.7, 0.06), (0, 0.15, -0.06), color='#b9a48a', kind='ground')
S.box(D, 'wall', (8, 0.1, 4), (0, 1.05, -1.0), color='#e6dfd3', kind='ground')
mon, scr = S.monitor(D, 'mon', width=1.0, loc=(0, 0.42, 0))
U = 0.08
kb = S.keyboard(D, 'kb', cols=13, rows=4, u=U, loc=(0, -0.12, 0), glass=(1, 8))
S.cyl(D, 'mug', 0.055, 0.1, (0.82, -0.02, 0), color='#7d9bb5')
S.box(D, 'notebook', (0.3, 0.22, 0.018), (-0.82, -0.12, 0), rot=(0, 0, 12), color='#9fb8cc')
S.cyl(D, 'pot', 0.07, 0.11, (-0.85, 0.42, 0), color='#d8d2c8', r2=0.085)
S.sphere(D, 'plant', 0.13, (-0.85, 0.42, 0.21), color='#6aa84f')
film.portal(scr, 's1', since=T('@out'), until=12.0)       # the monitor shows SCREEN live until 12 s, then holds


def top(ob):
    return Vector(kb['root'].location) + Vector((ob.location.x, ob.location.y, kb['height']))


# where the SCREEN hero is on the monitor at the breach: the DESK hero comes out right there
P = film.through(scr, 's1', hero_s, T('@breach'))
D.empty('screen_hero', loc=P)
H = S.hero(D, 'hero', size=0.1)
# it comes out as big as it looks on the screen (hero height 0.9 x size), then shrinks to desk size on its first hop
foot = film.through(scr, 's1', LUNGE, T('@breach'))
head = film.through(scr, 's1', LUNGE + Vector((0, 0, 0.9 * 2.0)), T('@breach'))
k_out = (head - foot).length / (0.9 * 0.1)
out0 = foot + Vector((0, -0.01, 0))
out1 = out0 + Vector((0, -0.02 - 0.45 * 0.1 * k_out, 0))
key(H, 'location', [(T('@breach'), out0), (T('@breach') + 0.15, out1, 'out')])
key(H, 'scale', [(T('@breach'), (1, 0.05, 1)), (T('@breach') + 0.15, (1, 1, 1), 'out')])
emit(T('@breach'), 'pop', gain=0.8)
desk_pt = Vector((P.x + 0.03, 0.2, 0))
hop(H, 8.8, 9.2, out1, desk_pt, height=0.06)


def shrink(t):                                       # k_out -> 1 between the breach and the first landing
    m = anim.lerp(k_out, 1, ease('smooth', (t - T('@breach')) / (9.2 - T('@breach'))))
    return [v * m for v in anim.value_at(H, 'scale', t, 3)]


bake(H, 'scale', T('@breach'), 9.5, shrink)
emit(9.2, 'thump', gain=0.5)
G = top(kb['glass'])
hops(H, 9.4, [desk_pt, top(D['kb.key0_6']), top(D['kb.key0_7']), G], dt=0.3, gap=0.1, height=0.07)
blink([D['hero.eyeL'], D['hero.eyeR']], 10.62)
key(H, 'location', [(10.8, G), (10.92, G + Vector((0, 0, 0.05)), 'rise'), (11.05, G + Vector((0, 0, -0.04)), 'gravity')])
key(H, 'scale', [(10.92, (1, 1, 1)), (11.05, (0.3, 0.3, 0.3), 'in')])
emit(10.92, 'whoosh', gain=0.6, dur=0.3)
visible(H, [(T('@breach'), 11.05)])

c2 = D.camera('s2', lens=35)
camera.path(c2, [(T('@out') + 1.5, (0.55, -2.0, 0.95), (0, 0.15, 0.42)),
                 (T('@insert'), (0.42, -1.85, 0.9), (0, 0.18, 0.45), 'smooth')])
c3 = D.camera('s3', lens=40)
camera.path(c3, [(T('@insert'), (-0.7, -0.8, 0.82), (0, 0.39, 0.66)),
                 (8.9, (-0.6, -0.66, 0.79), (0, 0.39, 0.66), 'linear')])
c4 = D.camera('s4', lens=35)
camera.path(c4, [(8.1, (0.85, -1.2, 0.7), (0.0, 0.1, 0.35)),
                 (T('@dive'), (0.62, -0.78, 0.4), (0.17, -0.06, 0.08))])

# ============ MEADOW: a 16:9 island (the key's shape), in a collection DESK can show as a diorama ============
M = film.world('MEADOW', look='miniature')
isl = M.collection('island')
S.box(M, 'island', (8, 4.5, 0.6), (0, 0, -0.6), color='#8a6a4a', bevel=0.08, coll=isl)
turf = S.plane(M, 'turf', (7.9, 4.4), (0, 0, 0.002), color='#7aa55a', kind='ground', coll=isl)
geo.scatter(turf, S.blade_piece(M, 'blade', h=0.22, color='#5b8f42'), density=120, scale_random=0.5, seed=3)
S.sphere(M, 'rock1', 0.25, (2.9, -1.4, 0.05), color='#9aa0a6', scale=(1.3, 1, 0.6), coll=isl)
S.sphere(M, 'rock2', 0.16, (-3.2, -1.2, 0.03), color='#9aa0a6', scale=(1.2, 1, 0.7), coll=isl)
vox = S.cube_piece(M, 'vox', bevel=0.08)
mini = S.hero_piece(M, 'mini', size=0.32)

# the hero falls in from the key and lands
Hm = S.hero(M, 'hero', size=0.6, coll=isl)
drop(Hm, 11.0, T('@land'), (-0.3, -0.6, 6.0), (-0.3, -0.9, 0))
visible(Hm, [(11.0, 1e6)])
blink([M['hero.eyeL'], M['hero.eyeR']], 12.9)
key(Hm, 'rotation_euler', [(13.0, (0, 0, 0)), (13.4, (0, 0, math.radians(45))), (15.4, (0, 0, math.radians(45))),
                           (15.8, (0, 0, math.radians(-40)))])

# a voxel tree grows; fruit clones pop on it, fall, and fly into a voxel giant
TB = Vector((1.7, 0.5, 0))
tc = S.tree_cells(base=TB, height=2.0, canopy=1.2, step=0.25, seed=2)
tree = grow(M, 'tree', vox, [p for p, _ in tc], T('@grow'), 1.5, [c for _, c in tc], seed_point=TB, order='z',
            scale=0.245)
ctr = TB + Vector((0, 0, 2.0 + 1.2 * 0.55))
rnd = random.Random(5)
fruit_pts = [ctr + Vector((math.cos(a) * 1.25, -abs(math.sin(a)) * 1.25 - 0.1, rnd.uniform(-0.5, 0.4)))
             for a in [math.radians(15 + 150 * k / 7) for k in range(8)]]
fruit = grow(M, 'fruit', mini, fruit_pts, T('@fruit'), 0.35, [YEL] * 8, order='random', stagger=0.6, sound='pop')
visible(fruit, [(0, T('@fall'))])
ground_pts = [Vector((p.x + rnd.uniform(-0.6, 0.6), p.y - rnd.uniform(0.3, 1.0), 0)) for p in fruit_pts]
drops = scatter(M, 'drop', mini, fruit_pts, T('@fall'), 0.45, [YEL] * 8, targets=ground_pts, ease='gravity',
                stagger=0.4, spin=0.15, since=T('@fall'), until=T('@giant') + 0.05)
GC, gcell = Vector((-1.6, 0.6, 0)), 0.3
gpx = S.pixels(S.HERO_PIXELS, PAL, cell=gcell, origin='bottom')
gcells, gcols = [], []
for k in range(6):
    for x, z, col in gpx:
        gcells.append(GC + Vector((x, -0.75 + k * gcell, z + gcell / 2)))
        gcols.append(col if k == 0 else YEL)
giant = assemble(M, 'giant.vox', vox, gcells, T('@giant'), 1.2, gcols,
                 start=[ground_pts[i % 8] + Vector((0, 0, 0.15)) for i in range(len(gcells))], stagger=0.65,
                 order='z', arc=1.5, spin=0.5, scale=gcell * 0.98, start_scale=0.4)
gz = 7 * gcell / 2
giant_anchor = M.empty('giant', loc=GC + Vector((0, 0, gz)))
hop(Hm, T('@peak'), T('@peak') + 0.35, (-0.3, -0.9, 0), (0.1, -1.1, 0), height=0.25)
emit(T('@peak') + 0.35, 'step', gain=0.6)
hops(Hm, 18.2, [(0.1, -1.1, 0), (-0.3, -1.0, 0), (-0.6, -0.85, 0)], dt=0.35, gap=0.1, height=0.3)
into(isl, tree, fruit, drops, giant, giant_anchor)

c5 = M.camera('s5', lens=35)
camera.path(c5, [(T('@dive'), (0, 0, 7.9), (0, 0.001, 0)),                    # top-down: the key's view
                 (T('@land'), (0, -0.4, 6.6), (0, 0.05, 0), 'smooth'),
                 (14.0, (0.4, -8.6, 4.6), (0.1, 0.3, 1.9), 'smooth'),
                 (17.4, (1.4, -8.2, 4.0), (-0.3, 0.4, 1.8), 'smooth')])
c6 = M.camera('s6', lens=24)
camera.path(c6, [(16.6, (0.9, -3.0, 0.22), (-1.4, 0.5, 1.6)),
                 (19.65, (1.2, -3.5, 1.4), (-1.6, 0.6, 1.3))])

# ============ back on the DESK: the island is a diorama on the glass key ============
k_isl = 0.92 * (16 / 9 * U - 0.12 * U) / 8.0                       # island width 8 -> the key top's width
Gi = G + Vector((0, 0, 0.0008))
dio = D.instance('island', isl, loc=Gi, scale=k_isl)
visible(dio, [(19.0, 1e6)])
D.empty('mini_giant', loc=Gi + (GC + Vector((0, 0, gz))) * k_isl)
c7 = D.camera('s7', lens=50)
camera.path(c7, [(19.15, (0.3, -0.31, 0.16), Gi + Vector((-0.02, 0.008, 0.016))),
                 (21.8, (0.5, -1.75, 0.85), (0.0, 0.3, 0.55))])

film.run()
