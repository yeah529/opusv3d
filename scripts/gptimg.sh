#!/bin/bash
# Make one reference image with the local Codex CLI's built-in image tool (GPT image), for stage P2 of the
# high-fidelity track (references/hifi.md).
# usage: bash gptimg.sh <project_dir> <name> <brief.txt> [reference images...]
#   writes <project_dir>/01_ref/p2/<name>.png, plus <name>.log (Codex output) and <name>.codex.txt (its reply)
#   CODEX=/path/to/codex   (default: codex on PATH)
#   CODEX_MODEL=...  CODEX_EFFORT=...   (default: gpt-6.1-sol, high; the user's choice). The image itself is always gpt-image-2 (Codex's built-in image_gen)
# Exit 1 when no PNG came back (refusal, failure, no Codex). One image per call; it never retries by itself.
set -u
[ $# -ge 3 ] || { echo "usage: bash gptimg.sh <project_dir> <name> <brief.txt> [reference images...]" >&2; exit 1; }
P=$(cd "$1" && pwd) || exit 1
name=$2; brief=$3; shift 3
case "$name" in *[!A-Za-z0-9_-]*|'') echo "gptimg.sh: name must use letters, digits, _ and - only: $name" >&2; exit 1;; esac
[ -f "$brief" ] || { echo "gptimg.sh: no brief file $brief" >&2; exit 1; }
CODEX=${CODEX:-$(command -v codex)}
[ -x "$CODEX" ] || { echo "gptimg.sh: codex not found (install the Codex CLI or set CODEX=...)" >&2; exit 1; }
MODEL=${CODEX_MODEL:-gpt-6.1-sol}; EFFORT=${CODEX_EFFORT:-high}
imgs=()
for f in "$@"; do
  [ -f "$f" ] || { echo "gptimg.sh: no reference image $f" >&2; exit 1; }
  imgs+=(-i "$f")
done
out=$P/01_ref/p2; mkdir -p "$out"
rm -f "$out/$name.png"
{ echo "Use the built-in image_gen tool exactly once to create the image described below. Do not write code or scripts."
  echo "After it is generated, copy the generated PNG file to ./01_ref/p2/$name.png (overwrite if it exists) and reply only with that path."
  echo "If the image tool refuses or fails, do not retry with a different subject; reply 'FAILED: <reason>'."
  [ ${#imgs[@]} -gt 0 ] && echo "The attached image(s) are references; their roles are described in the brief."
  echo; echo "=== BRIEF ==="; cat "$brief"; } |
  "$CODEX" exec -m "$MODEL" -c model_reasoning_effort="$EFFORT" --skip-git-repo-check -C "$P" -s workspace-write ${imgs[@]+"${imgs[@]}"} -o "$out/$name.codex.txt" - > "$out/$name.log" 2>&1
rc=$?
if [ -s "$out/$name.png" ]; then
  echo "gptimg.sh: $out/$name.png"
else
  echo "gptimg.sh: $name failed (codex exit $rc): $(tail -1 "$out/$name.codex.txt" 2>/dev/null)  log: $out/$name.log" >&2
  exit 1
fi
