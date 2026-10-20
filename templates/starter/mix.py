"""Sound for the film: every cue in out/events.json becomes a sound effect, under a small synthesized score
whose section, instrument and energy follow the shots' worlds in timeline.json.

usage: python mix.py <project_dir>        (the lemo-opuscar venv: numpy, scipy, soundfile)
writes out/mix.wav (48 kHz stereo); mux.sh then sets loudness to -14 LUFS.

Edit SCORE (per world: instrument and energy), QUIET (near-silences before big moments) and SFX (cue kind ->
sound) for a new film. Unknown cue kinds are listed and skipped, so a typo never silently disappears.
"""
import json
import os
import sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get('LEMO_OPUSCAR_HOME', os.path.expanduser('~/lemo-opuscar')))
from core.audio import sfx as X  # noqa: E402  (before engine/v3d joins the path: it has its own core.py)
sys.path.append(os.path.join(HERE, 'engine', 'v3d'))
from timeline import Timeline  # noqa: E402

SR = X.SR
CHORDS = [(48, 52, 55, 59), (45, 48, 52, 55), (41, 45, 48, 52), (43, 47, 50, 55)]   # Cmaj7 Am F G, one per bar
# per world: arp voice, arp gain, pad gain, kick on beats, hats (from when, seconds)
SCORE = {
    'SCREEN': dict(voice='square', arp=0.20, pad=0.25, kick=False, hats=None),
    'DESK':   dict(voice='marimba', arp=0.28, pad=0.22, kick=True, hats=None),
    'MEADOW': dict(voice='bell', arp=0.30, pad=0.30, kick=True, hats=13.0),
}
QUIET = [(8.0, 8.5), (11.55, 12.35)]       # music dips to near-silence: before the breach, during the dive


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def voice(kind, m, d=0.5, v=1.0):
    t = X.t_(d)
    f = hz(m)
    if kind == 'square':                    # soft square: odd harmonics, low-passed
        x = sum(np.sin(2 * np.pi * f * k * t) / k for k in (1, 3, 5, 7))
        x = X.lp(x, 2400) * X.env_exp(d, 0.12)
    elif kind == 'marimba':                 # wooden bar: fundamental + 4th partial, quick decay
        x = np.sin(2 * np.pi * f * t) * X.env_exp(d, 0.22) + 0.35 * np.sin(2 * np.pi * f * 3.93 * t) * X.env_exp(d, 0.04)
    else:                                   # bell / music box: inharmonic partials, longer ring
        x = sum(a * np.sin(2 * np.pi * f * r * t) * X.env_exp(d, tau)
                for r, a, tau in ((1, 1, .5), (2.76, .35, .18), (5.4, .15, .08)))
    a = min(len(x), int(0.004 * SR))
    x[:a] *= np.linspace(0, 1, a)           # no click at the onset
    return x * v


def pad(chord, d, v):
    t = X.t_(d)
    x = sum(np.sin(2 * np.pi * hz(m + 12) * t * (1 + 0.002 * i)) for i, m in enumerate(chord))
    env = np.minimum(1, t / 0.4) * np.minimum(1, (d - t) / 0.4)
    return X.lp(x, 900) * env * v


def kick(v=1.0):
    d = 0.3
    t = X.t_(d)
    return np.sin(2 * np.pi * 48 * t * (1 + 1.6 * np.exp(-t / 0.03))) * X.env_exp(d, 0.09) * v


def hat(v=1.0):
    return X.hp(X.noise(0.05), 7000) * X.env_exp(0.05, 0.008) * v


def riser(d, v=1.0):
    d = max(0.3, d)
    t = X.t_(d)
    n = X.noise(d)
    out = np.zeros_like(n)
    for i in range(0, len(n), 960):         # band-pass noise sweeping up
        j = min(len(n), i + 960)
        f = 300 + 3000 * (i / len(n)) ** 2
        out[i:j] = X.bp(n[max(0, i - 3000):j], f * .8, f * 1.25)[-(j - i):]
    tone = np.sin(2 * np.pi * np.cumsum(200 + 600 * (t / d) ** 2) / SR) * 0.25
    return X.norm(out + tone) * (t / d) ** 2 * v


def swell(d, v=1.0):
    d = max(0.4, d)
    t = X.t_(d)
    x = sum(np.sin(2 * np.pi * hz(m) * t) for m in (60, 64, 67, 72))
    return X.norm(X.lp(x, 1500)) * np.sin(np.pi * t / d) ** 2 * v


def sparkle(v=1.0):
    m = 84 + [0, 2, 4, 7, 9][np.random.default_rng(int(v * 1e6) % 9973).integers(5)]
    return voice('bell', m, 0.35, 0.5 * v)


def ripple(d, v=1.0):
    d = max(0.5, d)
    t = X.t_(d)
    f = 220 * (1 + 0.5 * np.exp(-t / 0.15)) * (1 + 0.04 * np.sin(2 * np.pi * 14 * t))
    return X.norm(layer(np.sin(2 * np.pi * np.cumsum(f) / SR) * X.env_exp(d, 0.25), 0.4 * X.rumble(d))) * v


def layer(*xs):
    """Sum sounds of different lengths."""
    out = np.zeros(max(len(x) for x in xs), np.float32)
    for x in xs:
        out[:len(x)] += x
    return out


SFX = {
    'whoosh': lambda e: X.whoosh(max(0.25, e.get('dur') or 0.35)),
    'riser': lambda e: riser(e.get('dur') or 1.0),
    'swell': lambda e: swell(e.get('dur') or 1.0),
    'sparkle': lambda e: sparkle(e['t']),
    'click': lambda e: X.click(),
    'pop': lambda e: X.pop(),
    'thump': lambda e: X.thump(),
    'step': lambda e: X.step(),
    'hit': lambda e: layer(X.thump(f=55) * 0.8, X.click(0.6) * 0.3),
    'iris': lambda e: layer(X.whoosh(0.3) * 0.6, sparkle(e['t'] + 1)),
    'lens': lambda e: X.whoosh(max(0.4, e.get('dur') or 0.8)),
    'ripple': lambda e: ripple(e.get('dur') or 0.8),
}


def score(tl, n):
    buf = np.zeros((n, 2), np.float32)
    beat = 60.0 / (tl.bpm or 120)
    end = tl.dur
    t, k = tl.offset, 0
    while t < end:
        s = tl.active(tl.F(t))
        sc = SCORE.get(s.world) or next(iter(SCORE.values()))       # a world not in SCORE uses the first entry
        bar, pos = divmod(k, 8)                         # 8 eighths per bar
        chord = CHORDS[bar % len(CHORDS)]
        if pos == 0:
            X.add(buf, pad(chord, beat * 4, sc['pad']), t, 0.6)
        m = chord[[0, 1, 2, 3, 2, 1, 2, 3][pos]] + 12
        X.add(buf, voice(sc['voice'], m, 0.6, sc['arp']), t, 0.7, pan=-0.3 + 0.6 * (pos % 2))
        if sc['kick'] and pos in (0, 4):
            X.add(buf, kick(0.7), t, 0.8)
        if sc['hats'] is not None and t >= sc['hats'] and pos % 2 == 1:
            X.add(buf, hat(0.25), t, 0.6, pan=0.25)
        t += beat / 2
        k += 1
    g = np.ones(n, np.float32)                          # near-silences
    tt = np.arange(n) / SR
    for a, b in QUIET:
        dip = np.clip(np.minimum((tt - a) / 0.15, (b - tt) / 0.15), 0, 1)
        g *= 1 - 0.9 * dip
    return buf * g[:, None]


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else HERE
    tl = Timeline(os.path.join(d, 'timeline.json'))
    ev = json.load(open(os.path.join(d, 'out', 'events.json')))['events']
    ev += [dict(kind=o['sfx'], t=tl.T(o['t']), dur=float(o.get('in', 1.0)), gain=o.get('gain', 0.8))
           for o in tl.raw.get('overlays', []) if o.get('sfx')]           # a title's sound (timeline overlays)
    n = int(round(tl.dur * SR))
    fx = np.zeros((n, 2), np.float32)
    unknown = {}
    for e in ev:
        f = SFX.get(e['kind'])
        if f is None:
            unknown[e['kind']] = unknown.get(e['kind'], 0) + 1
            continue
        X.add(fx, f(e).astype(np.float32), e['t'], e.get('gain', 1.0), e.get('pan', 0.0))
    mus = score(tl, n)
    mix = mus * 0.55 + fx * 0.8
    if tl.fade_out:
        a = int((tl.dur - tl.fade_out) * SR)
        mix[a:] *= np.linspace(1, 0, n - a)[:, None]
    mix = np.stack([X.limit(X.compress(mix[:, c], thr=0.4, ratio=2.5), 0.9) for c in range(2)], 1)
    os.makedirs(os.path.join(d, 'out'), exist_ok=True)
    out = os.path.join(d, 'out', 'mix.wav')
    sf.write(out, mix.astype(np.float32), SR)
    used = sorted({e['kind'] for e in ev} - set(unknown))
    print(f'mix: {len(ev)} cues ({", ".join(used)}) -> {out}  peak {np.abs(mix).max():.2f}')
    if unknown:
        print(f'mix: WARNING no sound for cue kinds {unknown} (add them to SFX)')


if __name__ == '__main__':
    main()
