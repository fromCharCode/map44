#!/usr/bin/env bash
# Map44 – Dresden: Installer für macOS (Apple Silicon und Intel, macOS 11+)
#
#   curl -fsSL https://raw.githubusercontent.com/fromCharCode/map44/main/install/install-macos.sh | bash
#
# Lädt die neueste Spielversion und die Kartendaten (~5 GB, einmalig) von GitHub-Releases:
#   App:          ~/Applications/Map44.app   (Universal-Binary, ad-hoc signiert)
#   Kartendaten:  ~/Library/Application Support/Godot/app_userdata/Dresden/data
#                 (Benutzer-Datenordner des Spiels; nicht in der App, sonst bricht die Signatur)
# Erneut ausführen = Update (Kartendaten nur bei neuer Datenversion; abgebrochene Downloads werden fortgesetzt).
#
# Umgebungsvariablen: MAP44_APPS=<ordner> (statt ~/Applications), MAP44_KEEP_ZIPS=1 (Downloads behalten)
# Deinstallieren:     curl -fsSL …/install-macos.sh | bash -s -- --uninstall
set -euo pipefail

REPO="fromCharCode/map44"
API="https://api.github.com/repos/$REPO/releases"
APPS="${MAP44_APPS:-$HOME/Applications}"
APP="$APPS/Map44.app"
USERDIR="$HOME/Library/Application Support/Godot/app_userdata/Dresden"
DATA="$USERDIR/data"
DL="$HOME/Library/Caches/map44-downloads"
BIN_DIR="$HOME/.local/bin"

say()  { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mFehler:\033[0m %s\n' "$*" >&2; exit 1; }

if [ "${1:-}" = "--uninstall" ]; then
  rm -rf "$APP" "$DATA" "$DL" "$BIN_DIR/map44"
  say "Map44 entfernt (Spielstände/Einstellungen in $USERDIR bleiben erhalten)."
  exit 0
fi

[ "$(uname -s)" = "Darwin" ] || die "Dieser Installer ist für macOS. Linux: install.sh, Windows: install.ps1."
for c in curl unzip shasum; do
  command -v "$c" >/dev/null 2>&1 || die "'$c' fehlt (gehört eigentlich zu macOS)."
done
FREE_GB=$(df -g "$HOME" | awk 'NR==2 {print $4}')
[ "${FREE_GB:-99}" -ge 12 ] || say "Achtung: nur ${FREE_GB} GB frei – Download und Entpacken brauchen rund 12 GB."

mkdir -p "$DL" "$APPS" "$USERDIR"

assets() {  # Release-Dateien (URLs) aus der GitHub-API, ohne jq
  curl -fsSL -H "Accept: application/vnd.github+json" "$1" \
    | grep -o '"browser_download_url": *"[^"]*"' | sed -E 's/.*"(https[^"]+)"$/\1/'
}

check() {  # $1 sha256, $2 datei
  echo "$1  $2" | shasum -a 256 -c -s 2>/dev/null
}

fetch() {  # $1 url, $2 datei, $3 erwartete sha256 (optional); mit Fortsetzen
  local url="$1" out="$2" sum="${3:-}"
  if [ -n "$sum" ] && [ -f "$out" ] && check "$sum" "$out"; then
    return 0
  fi
  for try in 1 2 3; do
    curl -fL --retry 5 --retry-delay 3 -C - --progress-bar -o "$out" "$url" || true
    if [ -z "$sum" ] || check "$sum" "$out"; then
      return 0
    fi
    say "Prüfsumme falsch, lade $(basename "$out") neu (Versuch $try) …"
    rm -f "$out"
  done
  die "Download fehlgeschlagen: $url"
}

sum_of() {  # $1 sha256-datei, $2 dateiname
  [ -f "$1" ] && grep " $2\$" "$1" | cut -d' ' -f1 || true
}

say "Suche die neueste Version …"
GAME_URLS=$(assets "$API/latest")
GAME_URL=$(echo "$GAME_URLS" | grep -E '/map44-macos\.zip$' | head -1)
SUMS_URL=$(echo "$GAME_URLS" | grep -E '/SHA256SUMS$' | head -1)
[ -n "$GAME_URL" ] || die "Keine macOS-Version im neuesten Release gefunden."
[ -n "$SUMS_URL" ] && curl -fsSL -o "$DL/SHA256SUMS" "$SUMS_URL"

say "Lade das Spiel …"
fetch "$GAME_URL" "$DL/map44-macos.zip" "$(sum_of "$DL/SHA256SUMS" map44-macos.zip)"
TMP="$DL/app"
rm -rf "$TMP" && mkdir -p "$TMP"
unzip -oq "$DL/map44-macos.zip" -d "$TMP"
SRC_APP=$(find "$TMP" -maxdepth 1 -name "*.app" -type d | head -1)
[ -n "$SRC_APP" ] || die "Im Spielpaket fehlt die App."
rm -rf "$APP"
mv "$SRC_APP" "$APP"
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true      # Download per curl hat ohnehin keine Quarantäne
NEED=$(tr -d '[:space:]' < "$TMP/DATA_VERSION")
rm -rf "$TMP"
[ "${MAP44_KEEP_ZIPS:-0}" = 1 ] || rm -f "$DL/map44-macos.zip"

HAVE=""; [ -f "$DATA/VERSION" ] && HAVE=$(tr -d '[:space:]' < "$DATA/VERSION")
if [ "$NEED" != "$HAVE" ]; then
  say "Lade die Kartendaten $NEED (rund 5 GB, einmalig – das dauert je nach Leitung eine Weile) …"
  DATA_URLS=$(assets "$API/tags/$NEED")
  DSUM_URL=$(echo "$DATA_URLS" | grep -E "/map44-$NEED\.sha256\$" | head -1)
  [ -n "$DSUM_URL" ] && curl -fsSL -o "$DL/data.sha256" "$DSUM_URL"
  PARTS=$(echo "$DATA_URLS" | grep -E "/map44-$NEED-[0-9]+\.zip\$" | sort)
  [ -n "$PARTS" ] || die "Kartendaten $NEED nicht gefunden."
  n=$(echo "$PARTS" | wc -l | tr -d ' '); i=0
  for u in $PARTS; do
    i=$((i + 1)); f="$DL/$(basename "$u")"
    say "Kartendaten Teil $i/$n"
    fetch "$u" "$f" "$(sum_of "$DL/data.sha256" "$(basename "$u")")"
  done
  say "Entpacke Kartendaten …"
  rm -rf "$DATA"
  for u in $PARTS; do unzip -oq "$DL/$(basename "$u")" -d "$USERDIR"; done      # Pakete enthalten data/…
  echo "$NEED" > "$DATA/VERSION"
  [ "${MAP44_KEEP_ZIPS:-0}" = 1 ] || rm -f "$DL"/map44-"$NEED"-*.zip
else
  say "Kartendaten $HAVE sind aktuell."
fi

# Startbefehl fürs Terminal (optional) – sonst Map44 in ~/Applications bzw. Launchpad
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/map44" <<EOF
#!/bin/sh
exec open "$APP" --args "\$@"
EOF
chmod +x "$BIN_DIR/map44"

say "Fertig! Starten: Map44 im Ordner ~/Applications (Finder/Launchpad) oder im Terminal:  map44"
say "Falls macOS meldet, die App sei nicht verifiziert: Systemeinstellungen → Datenschutz & Sicherheit → „Trotzdem öffnen“."
