#!/bin/bash
# Startet Dresden (Godot 4.7). Fenster-Größe/Vollbild: mit --fullscreen oder --resolution 1920x1080 ergänzen.
# Für den Steam Controller: in Steam als Nicht-Steam-Spiel hinzufügen (Eintrag "Dresden") und dort
# Steam Input mit dem Layout "Gamepad" aktivieren – dann kommt der Controller als echtes Gamepad an.
cd "$(dirname "$0")/godot" || exit 1
GODOT="$(command -v godot 2>/dev/null)"
[ -x "$GODOT" ] || GODOT="$HOME/.local/bin/godot"
exec "$GODOT" --path . "$@"
