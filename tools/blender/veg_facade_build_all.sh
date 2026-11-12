#!/usr/bin/env bash
# Baut Unterholz (godot/assets/models/vegetation) und Fassadenteile (.../facade) komplett neu:
# Texturen -> Blender-Export -> Vorschaubilder -> Godot-Import (+ Importoptionen) -> Prüfung.
set -euo pipefail
cd "$(dirname "$0")/../.."
P="$PWD"
BL=(flatpak run org.blender.Blender -b --python)
GD=~/.local/bin/godot
.venv/bin/python tools/blender/veg_textures.py
.venv/bin/python tools/blender/facade_textures.py
rm -f godot/assets/models/vegetation/MANIFEST.json godot/assets/models/facade/MANIFEST.json
"${BL[@]}" "$P/tools/blender/veg_build.py" 2>&1 | grep -E '^\[veg\]|Error|Traceback' || true
"${BL[@]}" "$P/tools/blender/facade_build.py" 2>&1 | grep -E '^\[facade\]|Error|Traceback' || true
"${BL[@]}" "$P/tools/blender/veg_facade_preview.py" -- veg 2>&1 | grep -E 'Error|Traceback' || true
"${BL[@]}" "$P/tools/blender/veg_facade_preview.py" -- veg_group bush_young_tree bush_a bush_b fern grass_tall \
    grass_tuft heather stump rock_small deadwood 2>&1 | grep -E 'Error|Traceback' || true
"${BL[@]}" "$P/tools/blender/veg_facade_preview.py" -- facade 2>&1 | grep -E 'Error|Traceback' || true
rm -rf tools/blender/_tmp
"$GD" --headless --path godot --import >/dev/null 2>&1 || true
.venv/bin/python tools/blender/veg_set_import.py
"$GD" --headless --path godot --import >/dev/null 2>&1 || true
"$GD" --headless --path godot -s "$P/tools/blender/veg_facade_check.gd" 2>&1 | grep -v '^Godot Engine' | sed -E 's/aabb=\[[^]]*\] //'
