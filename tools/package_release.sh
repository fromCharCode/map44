#!/usr/bin/env bash
# Map44 – Release-Pakete bauen (Linux-Entwicklungsrechner mit Godot 4.7.1 + Exportvorlagen)
#
#   tools/package_release.sh <version> [data-version] [vorherige-data-version]
#     z. B. tools/package_release.sh v0.1.0 data-v2 data-v1
#     (Vergleichsbasis: das Release der eigenen Datenversion, falls vorhanden – dann müssen die Daten unverändert
#      sein –, sonst die angegebene bzw. neueste data-v*-Version; ohne gültiges Manifest Abbruch, erster Vollbau
#      bzw. bewusster Neubau aller Pakete mit MAP44_FULL_DATA=1)
#   WICHTIG: alte data-v*-Releases nie löschen – neuere Manifeste verweisen auf ihre Pakete.
#
# Ergebnis in dist/:
#   map44-linux-x86_64.zip      Spiel (Programm + .pck + DATA_VERSION + Lizenzen)
#   map44-windows-x86_64.zip
#   map44-macos.zip             Dresden.app (Universal, ad-hoc signiert) + DATA_VERSION; Installer: install-macos.sh
#   map44-<data-version>-t<kachel>.zip  Kartendaten je Kachel bzw. "root" (entpacken nach <Spielordner>/data/…);
#                               nur geänderte Kacheln, unveränderte verweist das Manifest auf ihr älteres Release
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

echo "==> Vergleichsbasis der Kartendaten (vor dem langen Export prüfen)"
# Pakete mit unverändertem Inhalt werden aus einem älteren Release referenziert statt neu hochgeladen.
# Basis: das Release der eigenen Datenversion, falls es schon existiert (reines Spiel-Release), sonst das neueste
# data-v*-Release. Ohne gültiges Manifest bricht das Skript ab – außer MAP44_FULL_DATA=1 erlaubt den Vollbau.
PREV_MF="$ROOT/build/prev.manifest"
SAME_DATA=0        # 1: Release der Datenversion existiert schon – Daten müssen unverändert sein, nichts hochzuladen
SKIP_DATA=0        # 1: …und ist im alten Format – keine Datenpakete bauen
rm -f "$PREV_MF"
mf_ok() {  # $1 manifest: mindestens eine Zeile, alle im 5-Spalten-Format
  [ -s "$1" ] && ! grep -Evq '^[0-9a-f]{64} [0-9]+ map44-[^ /]+\.zip [^ /]+ [0-9a-f]{64}$' "$1"
}
if [ "${MAP44_FULL_DATA:-0}" = 1 ]; then
  echo "    MAP44_FULL_DATA=1 – alle Pakete neu"
  : > "$PREV_MF"
else
  TAGS=$(gh release list -L 1000 --json tagName -q '.[].tagName') \
    || { echo "Fehler: Releases nicht abrufbar (gh offline/nicht angemeldet?)." >&2; exit 1; }
  if echo "$TAGS" | grep -qx "$DATA_VER"; then
    SAME_DATA=1
    # altes Format nur, wenn das Release wirklich kein Manifest enthält – ein Netz-/Anmeldefehler beim Abruf darf
    # die Prüfung "Daten unverändert" nicht still überspringen
    ASSETS=$(gh release view "$DATA_VER" --json assets -q '.assets[].name') \
      || { echo "Fehler: Dateien des Release $DATA_VER nicht abrufbar." >&2; exit 1; }
    if echo "$ASSETS" | grep -qx "map44-$DATA_VER.manifest"; then
      gh release download "$DATA_VER" -p "map44-$DATA_VER.manifest" -O "$PREV_MF" \
        || { echo "Fehler: Manifest von $DATA_VER nicht ladbar – bitte erneut versuchen." >&2; exit 1; }
      PREV_DATA="$DATA_VER"
    else
      SKIP_DATA=1
      echo "    $DATA_VER ist bereits veröffentlicht (altes Format) – keine Datenpakete"
    fi
  else
    PREV_DATA="${3:-$(echo "$TAGS" | grep -E '^data-v' | head -1 || true)}"
    [ -n "$PREV_DATA" ] || { echo "Fehler: kein data-v*-Release gefunden – für den Vollbau MAP44_FULL_DATA=1 setzen." >&2; exit 1; }
    gh release download "$PREV_DATA" -p "map44-$PREV_DATA.manifest" -O "$PREV_MF" \
      || { echo "Fehler: $PREV_DATA hat kein Manifest (altes Format?) – für den Vollbau MAP44_FULL_DATA=1 setzen." >&2; exit 1; }
  fi
  if [ "$SKIP_DATA" = 0 ]; then
    mf_ok "$PREV_MF" || { echo "Fehler: Manifest von $PREV_DATA ist leer oder im falschen Format – für den Vollbau MAP44_FULL_DATA=1 setzen." >&2; exit 1; }
    echo "    Vergleiche mit $PREV_DATA"
  fi
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

echo "==> Datenpakete (je Kachel)"
if [ "$SKIP_DATA" = 0 ]; then
.venv/bin/python - "$STAGE" "$DIST" "$DATA_VER" "$PREV_MF" "$SAME_DATA" <<'PY'
import hashlib, os, sys, zipfile
stage, dist, ver, prev_mf, same = sys.argv[1:6]

def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

prev = {}  # gruppe -> Manifestzeile; Spalten: zip-sha256 größe datei release-tag inhalts-hash
for line in open(prev_mf):
    col = line.split()
    prev[col[2].removeprefix(f"map44-{col[3]}-").removesuffix(".zip")] = col
groups = {}
for root, _dirs, names in os.walk(os.path.join(stage, "data")):
    for n in names:
        p = os.path.join(root, n)
        rel = os.path.relpath(p, stage)
        parts = rel.split("/")
        g = f"t{parts[2]}" if parts[1] == "tiles" and len(parts) > 3 else "root"   # ein Paket je Kachel
        groups.setdefault(g, []).append((rel, p))
if len(groups) > 900:
    sys.exit(f"Fehler: {len(groups)} Pakete – GitHub erlaubt höchstens 1000 Dateien je Release")
if same == "1" and set(prev) - set(groups):
    sys.exit(f"Fehler: Kartendaten weichen vom veröffentlichten {ver} ab (Paket {sorted(set(prev) - set(groups))[0]} "
             "fehlt) – neue Datenversion angeben")
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
    if same == "1":
        sys.exit(f"Fehler: Kartendaten weichen vom veröffentlichten {ver} ab (Paket {g}) – neue Datenversion angeben")
    name = f"map44-{ver}-{g}.zip"
    out = os.path.join(dist, name)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for rel, p in files:
            zi = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            with open(p, "rb") as f:
                zf.writestr(zi, f.read(), compresslevel=6)
    if os.path.getsize(out) > 1_900_000_000:
        sys.exit(f"Fehler: {name} ist größer als 1,9 GB – GitHub nimmt je Datei höchstens 2 GB")
    manifest.append(f"{sha_file(out)} {os.path.getsize(out)} {name} {ver} {chash}")
    upload.append(name)
mf = f"map44-{ver}.manifest"
with open(os.path.join(dist, mf), "w") as f:
    f.write("\n".join(manifest) + "\n")
with open(os.path.join(dist, "UPLOAD_DATA"), "w") as f:   # relativ zu dist/, eine Datei je Zeile
    if same != "1":
        f.write("\n".join(upload + [mf]) + "\n")
if same == "1":
    print(f"Kartendaten unverändert gegenüber veröffentlichtem {ver} – nichts hochzuladen")
mb = sum(os.path.getsize(os.path.join(dist, u)) for u in upload) / 1e6
print(f"{len(groups)} Datenpakete: {len(upload)} neu ({mb:.0f} MB), {reused} unverändert – Liste in dist/UPLOAD_DATA")
PY
fi

echo "==> Prüfsummen"
(cd "$DIST" && sha256sum map44-linux-x86_64.zip map44-windows-x86_64.zip map44-macos.zip > SHA256SUMS)
ls -la "$DIST"
