#!/bin/sh
# Build the film: render shots (Blender) -> compose (transitions, grade) -> mix -> mux (-14 LUFS) -> seamcheck.
# usage: sh build.sh [--draft]
#   BLENDER=/path/to/Blender     (default: /Applications/Blender.app/Contents/MacOS/Blender)
#   LEMO_OPUSCAR_HOME=~/lemo-opuscar   (python venv with numpy/scipy/pillow/soundfile, sfx.py and mux.sh)
# Rendering resumes where it stopped; a changed film.py, timeline.json or engine re-renders everything.
set -e
cd "$(dirname "$0")"
Q=final; D=""
[ "${1:-}" = "--draft" ] && { Q=draft; D=--draft; }
BLENDER=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
LIB=${LEMO_OPUSCAR_HOME:-$HOME/lemo-opuscar}
PY=$LIB/.venv/bin/python
[ -x "$BLENDER" ] || { echo "build.sh: Blender not found: $BLENDER (set BLENDER=...)" >&2; exit 1; }
[ -x "$PY" ] || { echo "build.sh: python not found: $PY (set LEMO_OPUSCAR_HOME=...)" >&2; exit 1; }
FPS=$("$PY" -c "import json; print(json.load(open('timeline.json')).get('fps', 30))")

"$BLENDER" -b --factory-startup --python-exit-code 1 -P film.py -- render $D
"$PY" engine/compose.py . $D
"$PY" mix.py .
sh "$LIB/core/render/mux.sh" "out/$Q/video.mp4" out/mix.wav "out/$Q/film.mp4" "$FPS" 0
"$PY" engine/seamcheck.py . "out/$Q/film.mp4" $D
echo "build.sh: done -> out/$Q/film.mp4"
