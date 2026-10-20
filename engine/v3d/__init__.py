"""opusv3d engine: nested-world 3D films rendered with Blender, transitions as generators.

film.py:
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engine'))
    from v3d import *
    film = Film(__file__)
    W = film.world('DESK', look='clay')
    ...
    film.run()
"""
from . import anim, arch, assets, camera, geo, looks, materials, rig, shapes, transitions
from .anim import blink, drop, ease, emit, hop, hops, key, bake, visible
from .core import Film, World
from .transitions import assemble, grow, lift, move, pop, scatter

__all__ = ['Film', 'World', 'anim', 'arch', 'assets', 'materials', 'rig', 'camera', 'geo', 'looks', 'shapes', 'transitions', 'assemble', 'scatter',
           'lift', 'grow', 'pop', 'move', 'key', 'bake', 'visible', 'hop', 'hops', 'drop', 'blink', 'ease', 'emit']
