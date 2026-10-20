"""opusv3d blank film: one world, one shot, one box. Replace the middle with your scene (hifi.md P5-P7).

Run: Blender -b --factory-startup --python-exit-code 1 -P film.py -- plan | stills [--at 1,5] | render [--draft]
     or sh build.sh [--draft] for the whole film (render, compose, mix, mux, seamcheck)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engine'))

from v3d import *  # noqa: E402,F401,F403
from v3d import shapes as S  # noqa: E402

film = Film(__file__)
T = film.T                                   # time notation -> seconds
HERE = os.path.dirname(os.path.abspath(__file__))   # asset paths are built from the project dir

W = film.world('MAIN', look='film')          # 'film' = photoreal (Cycles); a stylized look (clay, toon, ...) renders with EEVEE
S.plane(W, 'floor', size=(20, 20), color='#8a8a90', kind='ground')
S.box(W, 'subject', size=(0.5, 0.5, 0.5), color='#d9d9d9')

c = W.camera('SH010', lens=50)               # camera of shot SH010: MAIN.cam.SH010
camera.path(c, [(0, (1.6, -2.4, 1.0), (0, 0, 0.25)), (6, (1.2, -2.0, 0.8), (0, 0, 0.25), 'smooth')])

film.run()
