#!/usr/bin/env bash
# Godot-Import der Audio-Assets: importieren, loop=true fuer alle Loops setzen (laut MANIFEST.json),
# erneut importieren, danach pruefen, dass kein .import valid=false enthaelt.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GODOT="${GODOT:-$HOME/.local/bin/godot}"
PY="$ROOT/.venv/bin/python"
AUD="$ROOT/godot/assets/audio"

echo "== Import 1"
"$GODOT" --headless --path "$ROOT/godot" --import > /dev/null 2>&1 || true

echo "== loop=true setzen"
"$PY" -I - "$AUD" <<'EOF'
import json, re, sys
from pathlib import Path
aud = Path(sys.argv[1])
man = json.loads((aud / "MANIFEST.json").read_text())
changed = 0
for s in man["sounds"]:
    imp = aud / (s["file"] + ".import")
    if not imp.exists():
        print("FEHLT:", imp); continue
    t = imp.read_text()
    want = "true" if s["loop"] else "false"
    t2 = re.sub(r"(?m)^loop=(true|false)$", f"loop={want}", t)
    if t2 != t:
        imp.write_text(t2); changed += 1
print("geaendert:", changed)
EOF

echo "== Import 2"
"$GODOT" --headless --path "$ROOT/godot" --import > /dev/null 2>&1 || true

echo "== Pruefung"
bad=$(grep -l "valid=false" "$AUD"/*/*.import || true)
n=$(ls "$AUD"/*/*.import | wc -l)
loops=$(grep -l "^loop=true" "$AUD"/*/*.import | wc -l)
echo "import-Dateien: $n, davon loop=true: $loops"
if [ -n "$bad" ]; then echo "UNGUELTIG:"; echo "$bad"; exit 1; fi
echo "alle gueltig"
