#!/bin/bash
# Baut Texturen + Modelle + Litter-/Graffiti-Atlas. Aufruf: tools/blender/furniture_run.sh [modellname ...]
set -e
D="$(cd "$(dirname "$0")" && pwd)"
P="$(cd "$D/../.." && pwd)"
if [ "$1" != "--models-only" ]; then
  "$P/.venv/bin/python" "$D/furniture_textures.py"
  "$P/.venv/bin/python" "$D/furniture_litter.py"
  "$P/.venv/bin/python" "$D/furniture_graffiti.py"
else
  shift
fi
flatpak run org.blender.Blender -b --python "$D/furniture_build.py" -- "$@" 2>&1 | grep -E "^\[furniture\]|Error|error|Traceback|File \"" || true
