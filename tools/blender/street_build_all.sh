#!/usr/bin/env bash
# Baut alle Straßen-Assets (Schilder, Werbung) reproduzierbar neu.
# Texturen/Atlanten mit PIL, Modelle + Vorschauen mit Blender 5.2 (Flatpak), danach Godot-Import.
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=.venv/bin/python
$PY tools/blender/make_traffic_signs.py
$PY tools/blender/make_posters.py
$PY tools/blender/make_street_textures.py
$PY tools/blender/street_preview_inputs.py
flatpak run org.blender.Blender -b --python "$PWD/tools/blender/street_models_build.py" -- "$@"
~/.local/bin/godot --headless --path godot --import >/dev/null 2>&1 || true
echo "fertig"
