#!/bin/sh
# Start a new opusv3d film: the starter template plus a frozen copy of the engine (a later engine change
# never re-renders or breaks an old film).
# usage: sh new.sh [--blank] <project_dir>
#   --blank: skeleton film.py + timeline.json (one world, one shot) instead of the 22 s nested-world starter
set -e
SKILL=$(cd "$(dirname "$0")/.." && pwd)
T=starter
[ "${1:-}" = "--blank" ] && { T=blank; shift; }
[ -n "${1:-}" ] || { echo "usage: sh new.sh [--blank] <project_dir>" >&2; exit 1; }
[ -e "$1" ] && { echo "new.sh: $1 already exists; nothing changed" >&2; exit 1; }
mkdir -p "$1"
cp "$SKILL"/templates/$T/timeline.json "$SKILL"/templates/$T/film.py "$SKILL"/templates/starter/mix.py \
   "$SKILL"/templates/starter/build.sh "$SKILL"/templates/starter/PROGRESS.md "$1"/
mkdir -p "$1/checks"
cp -R "$SKILL/engine" "$1/engine"
find "$1/engine" -name __pycache__ -type d -prune -exec rm -rf {} +
echo "new.sh: $1 ready"
echo "  next: cd \"$1\" && /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 -P film.py -- plan"
