#!/usr/bin/env bash
# Map44 – Release-Pakete bauen (Linux-Entwicklungsrechner mit Godot 4.7.1 + Exportvorlagen)
#
#   tools/package_release.sh <version> [data-version] [vorherige-data-version]
#     z. B. tools/package_release.sh v0.1.0 data-v2 data-v1
#     (vorherige Datenversion: Standard = neuestes data-v*-Release auf GitHub; hat sie kein Manifest,
#      bricht das Skript ab – erster Vollbau bzw. bewusster Neubau aller Pakete mit MAP44_FULL_DATA=1)
#   WICHTIG: alte data-v*-Releases nie löschen – neuere Manifeste verweisen auf ihre Pakete.
#
# Ergebnis in dist/:
#   map44-linux-x86_64.zip      Spiel (Programm + .pck + DATA_VERSION + Lizenzen)
#   map44-windows-x86_64.zip
#   map44-macos.zip             Dresden.app (Universal, ad-hoc signiert) + DATA_VERSION; Installer: install-macos.sh
#   map44-<data-version>-<block>.zip  Kartendaten je 2×2-km-Block bzw. "root" (entpacken nach <Spielordner>/data/…);
#                               nur geänderte Blöcke, unveränderte verweist das Manifest auf ihr älteres Release
#   map44-<data-version>.manifest  Zeilen "zip-sha256 größe datei release-tag inhalts-hash" (alle Pakete)
#   UPLOAD_DATA                 hochzuladende Datendateien (relativ zu dist/, eine je Zeile)
#   SHA256SUMS
# Hochladen (Beispiel):
#   (cd dist && xargs -d '\n' gh release create <data-version> --latest=false < UPLOAD_DATA)
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

echo "==> Vorherige Datenversion (vor dem langen Export prüfen)"
# Vorherige Datenversion: Pakete mit unverändertem Inhalt werden von dort referenziert statt neu hochgeladen.
# Ohne vorheriges Manifest bricht das Skript ab – außer MAP44_FULL_DATA=1 erlaubt ausdrücklich den Vollbau.
PREV_MF="$ROOT/build/prev.manifest"
rm -f "$PREV_MF"
if [ "${MAP44_FULL_DATA:-0}" = 1 ]; then
  echo "    MAP44_FULL_DATA=1 – alle Pakete neu"
  : > "$PREV_MF"
else
  if [ -n "${3:-}" ]; then
    PREV_DATA="$3"
  else
    TAGS=$(gh release list -L 1000 --json tagName -q '.[].tagName') \
      || { echo "Fehler: Releases nicht abrufbar (gh offline/nicht angemeldet?) – Vorversion als 3. Argument angeben." >&2; exit 1; }
    PREV_DATA=$(echo "$TAGS" | grep -E '^data-v' | grep -vx "$DATA_VER" | head -1 || true)
    [ -n "$PREV_DATA" ] || { echo "Fehler: kein data-v*-Release gefunden – für den Vollbau MAP44_FULL_DATA=1 setzen." >&2; exit 1; }
  fi
  gh release download "$PREV_DATA" -p "map44-$PREV_DATA.manifest" -O "$PREV_MF" \
    || { echo "Fehler: $PREV_DATA hat kein Manifest (altes Format?) – für den Vollbau MAP44_FULL_DATA=1 setzen." >&2; exit 1; }
  echo "    Vergleiche mit $PREV_DATA"
fi

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
  # Fotofassaden (tools/mly_photofacade.py)
  if [ -f "$d/facades.json" ] && [ -d "$d/facades" ]; then
    cp "$d/facades.json" "$STAGE/data/tiles/$k/"
    mkdir -p "$STAGE/data/tiles/$k/facades"
    cp "$d"/facades/*.dds "$STAGE/data/tiles/$k/facades/" 2>/dev/null || true
  fi
done
for i in 0 1 2 3 4 5; do
  "$GODOT" --headless --path godot -s res://scripts/dev/bake_textures.gd -- \
    --tiles_src="$ROOT/data/processed/tiles" --tiles_out="$STAGE/data/tiles" --part=$i/6 &
done
wait
cp godot/data/bus_routes.json godot/data/tram_routes.json godot/data/streets.json godot/data/elbe.json godot/data/timetable.json "$STAGE/data/"
# data/VERSION schreibt der Installer erst nach dem vollständigen Entpacken

echo "==> Spielpakete"
rm -f "$DIST"/map44-*.zip "$DIST"/SHA256SUMS "$DIST"/*.sha256 "$DIST"/*.manifest "$DIST"/UPLOAD_DATA
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

echo "==> Datenpakete (je 2×2-km-Kachelblock)"
.venv/bin/python - "$STAGE" "$DIST" "$DATA_VER" "$PREV_MF" <<'PY'
import hashlib, os, sys, zipfile
stage, dist, ver, prev_mf = sys.argv[1:5]
BLOCK = 2  # km; eine Kachel landet immer im selben Paket

def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

prev = {}  # gruppe -> Manifestzeile; Spalten: zip-sha256 größe datei release-tag inhalts-hash
for line in open(prev_mf):
    col = line.split()
    if len(col) < 5:
        continue
    prev[col[2].removeprefix(f"map44-{col[3]}-").removesuffix(".zip")] = col
groups = {}
for root, _dirs, names in os.walk(os.path.join(stage, "data")):
    for n in names:
        p = os.path.join(root, n)
        rel = os.path.relpath(p, stage)
        parts = rel.split("/")
        g = "root"
        if parts[1] == "tiles" and len(parts) > 3:
            try:
                e, n_ = (int(v) for v in parts[2].split("_"))
                g = f"t{e // BLOCK * BLOCK}_{n_ // BLOCK * BLOCK}"
            except ValueError:
                g = "tx"
        groups.setdefault(g, []).append((rel, p))
manifest, upload, reused = [], [], 0
for g in sorted(groups):
    files = sorted(groups[g])
    # Inhalts-Hash über sortierte Pfade + Datei-Hashes: unabhängig von zlib/Zip-Metadaten
    ch = hashlib.sha256()
    for rel, p in files:
        ch.update(f"{rel}\0{sha_file(p)}\n".encode())
    chash = ch.hexdigest()
    if g in prev and prev[g][4] == chash:
        manifest.append(" ".join(prev[g][:5]))
        reused += 1
        continue
    name = f"map44-{ver}-{g}.zip"
    out = os.path.join(dist, name)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for rel, p in files:
            zi = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            with open(p, "rb") as f:
                zf.writestr(zi, f.read(), compresslevel=6)
    manifest.append(f"{sha_file(out)} {os.path.getsize(out)} {name} {ver} {chash}")
    upload.append(name)
mf = f"map44-{ver}.manifest"
with open(os.path.join(dist, mf), "w") as f:
    f.write("\n".join(manifest) + "\n")
with open(os.path.join(dist, "UPLOAD_DATA"), "w") as f:   # relativ zu dist/, eine Datei je Zeile
    f.write("\n".join(upload + [mf]) + "\n")
mb = sum(os.path.getsize(os.path.join(dist, u)) for u in upload) / 1e6
print(f"{len(groups)} Datenpakete: {len(upload)} neu ({mb:.0f} MB), {reused} unverändert – Liste in dist/UPLOAD_DATA")
PY

echo "==> Prüfsummen"
(cd "$DIST" && sha256sum map44-linux-x86_64.zip map44-windows-x86_64.zip map44-macos.zip > SHA256SUMS)
ls -la "$DIST"
