#!/usr/bin/env bash
# Map44 – Release-Pakete bauen (Linux-Entwicklungsrechner mit Godot 4.7.1 + Exportvorlagen)
#
#   tools/package_release.sh <version> [data-version]
#     z. B. tools/package_release.sh v0.1.0 data-v1
#
# Ergebnis in dist/:
#   map44-linux-x86_64.zip      Spiel (Programm + .pck + DATA_VERSION + Lizenzen)
#   map44-windows-x86_64.zip
#   map44-macos.zip             Dresden.app (Universal, ad-hoc signiert) + DATA_VERSION; Installer: install-macos.sh
#   map44-<data-version>-NN.zip Kartendaten (je < 1,9 GB; entpacken nach <Spielordner>/data/…)
#   SHA256SUMS, map44-<data-version>.sha256
# Hochladen (Beispiel):
#   gh release create <data-version> dist/map44-<data-version>-*.zip dist/map44-<data-version>.sha256 --latest=false
#   gh release create <version> dist/map44-*-x86_64.zip dist/map44-macos.zip dist/SHA256SUMS
set -euo pipefail
cd "$(dirname "$0")/.."
VER="${1:?Version angeben, z. B. v0.1.0}"
DATA_VER="${2:-data-v1}"
GODOT="${GODOT:-$HOME/.local/bin/godot}"
ROOT="$PWD"
STAGE="$ROOT/build/stage"
DIST="$ROOT/dist"
mkdir -p "$DIST" "$ROOT/build/linux" "$ROOT/build/windows" "$ROOT/build/macos"

echo "==> Materialtexturen vorbacken (res://texcache)"
"$GODOT" --headless --path godot -s res://scripts/dev/bake_textures.gd -- --texcache

echo "==> Exportieren"
"$GODOT" --headless --path godot --export-release "Linux" "$ROOT/build/linux/map44.x86_64"
"$GODOT" --headless --path godot --export-release "Windows" "$ROOT/build/windows/map44.exe"
# macOS: Exportvorlage macos.zip nötig (offizielles Godot-Vorlagenpaket); arm64 verlangt ETC2/ASTC-Import
rm -f "$ROOT/build/macos/map44.zip"
"$GODOT" --headless --path godot --export-release "macOS" "$ROOT/build/macos/map44.zip"

echo "==> Datenstufe: Kacheln (nur Laufzeitdateien) + vorgebackene Geländetexturen"
rm -rf "$STAGE/data"
mkdir -p "$STAGE/data/tiles"
for d in data/processed/tiles/*/; do
  k=$(basename "$d")
  [ -f "$d/city.json" ] || continue
  mkdir -p "$STAGE/data/tiles/$k"
  for f in city.json terrain.json terrain.f32 terrain_col.f32 splat0.png cover.png; do
    [ -f "$d/$f" ] && ln -f "$d/$f" "$STAGE/data/tiles/$k/$f" 2>/dev/null || cp "$d/$f" "$STAGE/data/tiles/$k/$f"
  done
done
for i in 0 1 2 3 4 5; do
  "$GODOT" --headless --path godot -s res://scripts/dev/bake_textures.gd -- \
    --tiles_src="$ROOT/data/processed/tiles" --tiles_out="$STAGE/data/tiles" --part=$i/6 &
done
wait
cp godot/data/bus_routes.json godot/data/tram_routes.json godot/data/streets.json godot/data/elbe.json "$STAGE/data/"
# data/VERSION schreibt der Installer erst nach dem vollständigen Entpacken

echo "==> Spielpakete"
rm -f "$DIST"/map44-*.zip "$DIST"/SHA256SUMS "$DIST"/*.sha256
for plat in linux windows; do
  P="$ROOT/build/pkg_$plat"
  rm -rf "$P" && mkdir -p "$P"
  if [ $plat = linux ]; then cp build/linux/map44.x86_64 build/linux/map44.pck "$P/"; else cp build/windows/map44.exe build/windows/map44.pck "$P/"; fi
  echo "$DATA_VER" > "$P/DATA_VERSION"
  cp README.md THIRD_PARTY.md "$P/" 2>/dev/null || true
  (cd "$P" && zip -q -r "$DIST/map44-$plat-x86_64.zip" .)
done
# macOS: Godots signiertes App-Zip unverändert übernehmen, DATA_VERSION/Lizenzen daneben anhängen
P="$ROOT/build/pkg_macos"
rm -rf "$P" && mkdir -p "$P"
cp "$ROOT/build/macos/map44.zip" "$DIST/map44-macos.zip"
echo "$DATA_VER" > "$P/DATA_VERSION"
cp README.md THIRD_PARTY.md "$P/" 2>/dev/null || true
(cd "$P" && zip -q "$DIST/map44-macos.zip" DATA_VERSION README.md THIRD_PARTY.md)

echo "==> Datenpakete (je < 1,9 GB)"
.venv/bin/python - "$STAGE" "$DIST" "$DATA_VER" <<'PY'
import os, sys, zipfile
stage, dist, ver = sys.argv[1], sys.argv[2], sys.argv[3]
LIMIT = 1_850_000_000
files = []
for root, _dirs, names in os.walk(os.path.join(stage, "data")):
    for n in sorted(names):
        p = os.path.join(root, n)
        files.append((os.path.relpath(p, stage), p))
files.sort(key=lambda t: (t[0].count("/") > 1, t[0]))      # Wurzeldateien (Linien, VERSION) zuerst
part, zf = 0, None
def open_part():
    global part
    part += 1
    return zipfile.ZipFile(os.path.join(dist, f"map44-{ver}-{part:02d}.zip"), "w", zipfile.ZIP_DEFLATED, compresslevel=6)
zf = open_part()
cur_tile = None
for rel, p in files:
    tile = rel.split("/")[2] if rel.startswith("data/tiles/") else None
    # neue Datei nur an Kachelgrenzen beginnen (eine Kachel nie auf zwei Pakete verteilen)
    if tile != cur_tile and zf.fp.tell() > LIMIT:
        zf.close()
        zf = open_part()
    cur_tile = tile
    zf.write(p, rel)
zf.close()
print(f"{part} Datenpakete")
PY

echo "==> Prüfsummen"
(cd "$DIST" && sha256sum map44-linux-x86_64.zip map44-windows-x86_64.zip map44-macos.zip > SHA256SUMS)
(cd "$DIST" && sha256sum map44-"$DATA_VER"-*.zip > "map44-$DATA_VER.sha256")
ls -la "$DIST"
