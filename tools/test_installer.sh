#!/usr/bin/env bash
# Map44 – Test der inkrementellen Kartendaten (Packer aus package_release.sh + Kartendaten-Block der Shell-Installer)
#
#   tools/test_installer.sh
#
# Baut kleine Schein-Releases, ersetzt curl durch Kopieren aus einem lokalen Ordner und prüft:
# Neuinstallation, Teil-Update, Austausch aller Pakete, Umstieg von einer Installation ohne Manifest (auch mit
# abgebrochenem Download), alte Datenversion (404) und Serverfehler (5xx). Außerdem, dass install.sh und
# install-macos.sh denselben Kartendaten-Block enthalten. Ist pwsh installiert, läuft danach tools/test_installer.ps1
# mit denselben Schein-Releases gegen install.ps1.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$PWD"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
fail() { echo "FEHLER: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

block() { sed -n '/^# >>> Kartendaten/,/^# <<< Kartendaten/p' "$1"; }
diff <(block install/install.sh) <(block install/install-macos.sh) >/dev/null \
  || fail "Kartendaten-Block in install.sh und install-macos.sh weicht ab"
ok "Kartendaten-Block in beiden Shell-Installern gleich"

# Packer (Python-Teil aus package_release.sh)
sed -n "/^\.venv\/bin\/python - \"\$STAGE\" .*<<'PY'$/,/^PY$/p" \
  tools/package_release.sh | sed '1d;$d' > "$T/pack.py"
[ -s "$T/pack.py" ] || fail "Packer nicht gefunden"
pack() {  # $1 version, $2 vorheriges manifest oder leer, $3 1 = Datenversion existiert schon
  mkdir -p "$T/rel/$1"
  local prev="$T/empty"; : > "$prev"; [ -n "${2:-}" ] && prev="$T/rel/$2/map44-$2.manifest"
  python3 "$T/pack.py" "$T/stage" "$T/rel/$1" "$1" "$prev" "${3:-0}" >/dev/null
}
tile() { mkdir -p "$T/stage/data/tiles/$1"; echo "$2" > "$T/stage/data/tiles/$1/city.json"; }

tile 410_5654 a; tile 412_5656 b; tile 414_5660 c; echo r > "$T/stage/data/streets.json"
pack data-v1
touch "$T/stage/data/streets.json"                     # nur Zeitstempel: Paket muss wiederverwendet werden
echo c2 > "$T/stage/data/tiles/414_5660/city.json"
rm -r "$T/stage/data/tiles/410_5654" "$T/stage/data/tiles/412_5656"; tile 420_5670 d
pack data-v2 data-v1
grep -q ' map44-data-v1-root.zip data-v1 ' "$T/rel/data-v2/map44-data-v2.manifest" || fail "unverändertes Paket nicht wiederverwendet"
[ ! -e "$T/rel/data-v2/map44-data-v2-root.zip" ] || fail "unverändertes Paket wurde neu gepackt"
ok "Packer: unveränderter Inhalt wird referenziert, nicht neu gepackt"
cp -r "$T/rel/data-v2" "$T/rel/data-v2b"; mv "$T/rel/data-v2b/map44-data-v2.manifest" "$T/rel/data-v2b/map44-data-v2b.manifest"
python3 "$T/pack.py" "$T/stage" "$T/rel/data-v2" data-v2 "$T/rel/data-v2b/map44-data-v2b.manifest" 1 >/dev/null 2>&1 \
  || fail "Spiel-Release mit unveränderten Daten bricht ab"
[ ! -s "$T/rel/data-v2/UPLOAD_DATA" ] || fail "Spiel-Release mit unveränderten Daten will hochladen"
echo x > "$T/stage/data/tiles/420_5670/extra.json"
python3 "$T/pack.py" "$T/stage" "$T/rel/data-v2b" data-v2 "$T/rel/data-v2/map44-data-v2.manifest" 1 >/dev/null 2>&1 \
  && fail "geänderte Daten unter veröffentlichter Datenversion nicht abgelehnt"
rm "$T/stage/data/tiles/420_5670/extra.json"
mv "$T/stage/data/tiles/420_5670" "$T/weg"
python3 "$T/pack.py" "$T/stage" "$T/rel/data-v2b" data-v2 "$T/rel/data-v2/map44-data-v2.manifest" 1 >/dev/null 2>&1 \
  && fail "entfernte Kachel unter veröffentlichter Datenversion nicht abgelehnt"
mv "$T/weg" "$T/stage/data/tiles/420_5670"
rm -r "$T/rel/data-v2b"
ok "Packer: gleiche Datenversion – unverändert nichts hochzuladen, geändert oder entfernt Abbruch"
echo r3 > "$T/stage/data/streets.json"; echo c3 > "$T/stage/data/tiles/414_5660/city.json"
echo d3 > "$T/stage/data/tiles/420_5670/city.json"
pack data-v3 data-v2                                     # alle Pakete geändert
# data-v3r: Paket der Kachel 414_5660 unter GLEICHEM Namen mit anderem Inhalt (city.json entfällt, neu.json kommt)
mkdir -p "$T/rel/data-v3r"
python3 - "$T/rel" <<'PYR'
import hashlib, os, sys, zipfile
rel = sys.argv[1]
name = "map44-data-v3-t414_5660.zip"
out = os.path.join(rel, "data-v3r", name)
with zipfile.ZipFile(out, "w") as zf:
    zf.writestr("data/tiles/414_5660/neu.json", "n\n")
sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
lines = []
for l in open(os.path.join(rel, "data-v3", "map44-data-v3.manifest")):
    c = l.split()
    lines.append(f"{sha} {os.path.getsize(out)} {name} data-v3r" if c[2] == name else " ".join(c[:4]))
open(os.path.join(rel, "data-v3r", "map44-data-v3r.manifest"), "w").write("\n".join(lines) + "\n")
PYR

# Installer-Block mit Schein-curl
cat > "$T/run.sh" <<EOF
set -euo pipefail
REPO=x/y; API=https://api.github.com/repos/x/y/releases; DL="$T/dl"; REL="$T/rel"; mkdir -p "\$DL"
say() { :; }; die() { echo "DIE \$*"; exit 3; }
assets() { echo "LEGACY-ASSETS" >&2; }
sum_of() { :; }
curl() {
  local out="" code="" url="\${*: -1}" a b
  for ((a = 1; a <= \$#; a++)); do
    case "\${!a}" in -o) b=\$((a + 1)); out="\${!b}";; -w) code=1;; esac
  done
  [ -n "\${MOCK_HTTP:-}" ] && { [ -n "\$code" ] && printf '%s' "\$MOCK_HTTP"; return 0; }
  local f="\$REL/\${url#https://github.com/x/y/releases/download/}"
  if [ "\${MOCK_FAIL_ZIP:-}" = 1 ] && [ "\${f%.zip}" != "\$f" ]; then return 22; fi
  if [ -f "\$f" ]; then cp "\$f" "\$out"; [ -n "\$code" ] && printf 200; return 0; fi
  [ -n "\$code" ] && printf 404; return 0
}
EOF
sed -n '/^fetch() {/,/^}/p' install/install.sh >> "$T/run.sh"
block install/install.sh >> "$T/run.sh"
echo 'install_data "$1" "$DEST"' >> "$T/run.sh"
run() { DEST="$T/dest" bash "$T/run.sh" "$@"; }
files() { (cd "$T/dest" && find data -type f ! -path 'data/.packs/*' | LC_ALL=C sort | tr '\n' ' '); }

mkdir -p "$T/dest"
run data-v1
[ "$(files)" = "data/MANIFEST data/VERSION data/streets.json data/tiles/410_5654/city.json data/tiles/412_5656/city.json data/tiles/414_5660/city.json " ] \
  || fail "Neuinstallation: $(files)"
ok "Neuinstallation"
run data-v2
[ "$(files)" = "data/MANIFEST data/VERSION data/streets.json data/tiles/414_5660/city.json data/tiles/420_5670/city.json " ] \
  || fail "Teil-Update: $(files)"
[ "$(cat "$T/dest/data/tiles/414_5660/city.json")" = c2 ] || fail "Teil-Update: Inhalt"
ok "Teil-Update (geänderte, entfernte und neue Kachel)"
run data-v3
[ "$(cat "$T/dest/data/streets.json" "$T/dest/data/VERSION")" = "r3
data-v3" ] || fail "Austausch aller Pakete"
[ "$(ls "$T/dest/data/.packs" | wc -l)" = 3 ] || fail "Austausch aller Pakete: Dateilisten"
ok "Austausch aller Pakete (.packs bleibt erhalten)"
run data-v3; ok "erneuter Lauf ohne Änderungen"

# Paket gleichen Namens neu veröffentlicht: alte Dateien weg, genau eine Manifestzeile
run data-v3r
[ "$(files)" = "data/MANIFEST data/VERSION data/streets.json data/tiles/414_5660/neu.json data/tiles/420_5670/city.json " ] \
  || fail "neu veröffentlichtes Paket: $(files)"
[ "$(grep -c ' map44-data-v3-t414_5660.zip ' "$T/dest/data/MANIFEST")" = 1 ] || fail "neu veröffentlichtes Paket: doppelte Manifestzeile"
run data-v3
[ "$(files)" = "data/MANIFEST data/VERSION data/streets.json data/tiles/414_5660/city.json data/tiles/420_5670/city.json " ] \
  || fail "zurück auf data-v3: $(files)"
ok "Paket gleichen Namens mit neuem Inhalt ersetzt das alte vollständig"

# beschädigtes Manifest: nichts löschen
cp "$T/rel/data-v3/map44-data-v3.manifest" "$T/mf.bak"
for bad in "" "kaputt" "$(head -c 300 "$T/mf.bak")"; do
  printf '%s' "$bad" > "$T/rel/data-v3/map44-data-v3.manifest"
  rm -f "$T/dest/data/VERSION"; echo data-v2 > "$T/dest/data/VERSION"
  out=$(run data-v3 2>&1 || true)
  [[ "$out" == DIE*beschädigt* ]] || fail "beschädigtes Manifest nicht abgelehnt: $out"
  [ "$(files)" = "data/MANIFEST data/VERSION data/streets.json data/tiles/414_5660/city.json data/tiles/420_5670/city.json " ] \
    || fail "beschädigtes Manifest hat Daten verändert: $(files)"
done
cp "$T/mf.bak" "$T/rel/data-v3/map44-data-v3.manifest"
ok "leeres/beschädigtes/abgeschnittenes Manifest: Abbruch ohne Löschen"

# Entpacken abgebrochen (Dateiliste da, Manifestzeile fehlt) und liegengebliebene Zips
mkdir -p "$T/dest/data/tiles/499_5699"; echo y > "$T/dest/data/tiles/499_5699/city.json"
echo "data/tiles/499_5699/city.json" > "$T/dest/data/.packs/map44-data-v9-t499_5699.zip.files"
mkdir -p "$T/dl"; echo z > "$T/dl/map44-data-v9-t499_5699.zip"; echo z > "$T/dl/map44-data-v1-root.zip"
echo data-v2 > "$T/dest/data/VERSION"
run data-v3
[ ! -e "$T/dest/data/tiles/499_5699" ] || fail "Reste abgebrochenen Entpackens nicht entfernt"
[ ! -e "$T/dest/data/.packs/map44-data-v9-t499_5699.zip.files" ] || fail "verwaiste Dateiliste nicht entfernt"
[ -z "$(ls "$T/dl" | grep '\.zip$' || true)" ] || fail "liegengebliebene Zips: $(ls "$T/dl")"
ok "Reste abgebrochenen Entpackens und alte Zips werden entfernt"

# data/.packs fehlt (von Hand gelöscht, unvollständig kopiert): kein stiller Abbruch
rm -rf "$T/dest/data/.packs"; echo data-v2 > "$T/dest/data/VERSION"
run data-v3 || fail "fehlendes .packs bricht ab"
[ "$(cat "$T/dest/data/VERSION")" = data-v3 ] && [ -d "$T/dest/data/.packs" ] || fail "fehlendes .packs: Zustand"
ok "fehlendes data/.packs wird neu angelegt"

# Umstieg von alter Installation: Download bricht ab -> alte Daten unangetastet
rm -rf "$T/dest/data" "$T/dl"; mkdir -p "$T/dest/data"; echo alt > "$T/dest/data/alt.txt"; echo data-v0 > "$T/dest/data/VERSION"
MOCK_FAIL_ZIP=1 run data-v3 >/dev/null 2>&1 && fail "abgebrochener Download hätte scheitern müssen"
[ "$(files)" = "data/VERSION data/alt.txt " ] || fail "abgebrochener Umstieg hat Daten verändert: $(files)"
ok "Umstieg mit abgebrochenem Download lässt alte Daten stehen"
run data-v3
[ "$(files)" = "data/MANIFEST data/VERSION data/streets.json data/tiles/414_5660/city.json data/tiles/420_5670/city.json " ] \
  || fail "Umstieg: $(files)"
ok "Umstieg von Installation ohne Manifest"

out=$(run data-v0 2>&1 || true); [[ "$out" == *LEGACY-ASSETS* ]] || fail "404 führt nicht zum alten Verfahren: $out"
ok "alte Datenversion (404) -> bisheriges Verfahren"
out=$(MOCK_HTTP=503 run data-v3 2>&1 || true); [[ "$out" == "DIE "*503* ]] || fail "5xx nicht als Fehler gemeldet: $out"
ok "Serverfehler (503) bricht mit Meldung ab"
if command -v pwsh >/dev/null 2>&1; then
  pwsh -NoProfile -File tools/test_installer.ps1 "$T/rel" || fail "PowerShell-Test"
else
  echo "  übersprungen: install.ps1 (pwsh nicht installiert)"
fi
echo "Alle Tests bestanden."
