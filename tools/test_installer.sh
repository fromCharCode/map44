#!/usr/bin/env bash
# Map44 – Test der inkrementellen Kartendaten (Packer aus package_release.sh + Kartendaten-Block der Shell-Installer)
#
#   tools/test_installer.sh
#
# Baut kleine Schein-Releases, ersetzt curl durch Kopieren aus einem lokalen Ordner und prüft:
# Neuinstallation, Teil-Update, Austausch aller Pakete, Umstieg von einer Installation ohne Manifest (auch mit
# abgebrochenem Download), alte Datenversion (404) und Serverfehler (5xx). Außerdem, dass install.sh und
# install-macos.sh denselben Kartendaten-Block enthalten.
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
sed -n "/^\.venv\/bin\/python - \"\$STAGE\" \"\$DIST\" \"\$DATA_VER\" \"\$PREV_MF\" <<'PY'/,/^PY$/p" \
  tools/package_release.sh | sed '1d;$d' > "$T/pack.py"
[ -s "$T/pack.py" ] || fail "Packer nicht gefunden"
pack() {  # $1 version, $2 vorheriges manifest oder leer
  mkdir -p "$T/rel/$1"
  local prev="$T/empty"; : > "$prev"; [ -n "${2:-}" ] && prev="$T/rel/$2/map44-$2.manifest"
  python3 "$T/pack.py" "$T/stage" "$T/rel/$1" "$1" "$prev" >/dev/null
}
tile() { mkdir -p "$T/stage/data/tiles/$1"; echo "$2" > "$T/stage/data/tiles/$1/city.json"; }

tile 410_5654 a; tile 411_5655 b; tile 414_5660 c; echo r > "$T/stage/data/streets.json"
pack data-v1
touch "$T/stage/data/streets.json"                     # nur Zeitstempel: Paket muss wiederverwendet werden
echo c2 > "$T/stage/data/tiles/414_5660/city.json"
rm -r "$T/stage/data/tiles/410_5654" "$T/stage/data/tiles/411_5655"; tile 420_5670 d
pack data-v2 data-v1
grep -q ' map44-data-v1-root.zip data-v1 ' "$T/rel/data-v2/map44-data-v2.manifest" || fail "unverändertes Paket nicht wiederverwendet"
[ ! -e "$T/rel/data-v2/map44-data-v2-root.zip" ] || fail "unverändertes Paket wurde neu gepackt"
ok "Packer: unveränderter Inhalt wird referenziert, nicht neu gepackt"
echo r3 > "$T/stage/data/streets.json"; echo c3 > "$T/stage/data/tiles/414_5660/city.json"
echo d3 > "$T/stage/data/tiles/420_5670/city.json"
pack data-v3 data-v2                                     # alle Pakete geändert

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
[ "$(files)" = "data/MANIFEST data/VERSION data/streets.json data/tiles/410_5654/city.json data/tiles/411_5655/city.json data/tiles/414_5660/city.json " ] \
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
echo "Alle Tests bestanden."
