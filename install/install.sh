#!/usr/bin/env bash
# Map44 – Dresden: Installer für Linux (x86_64)
#
#   curl -fsSL https://raw.githubusercontent.com/fromCharCode/map44/main/install/install.sh | bash
#
# Lädt die neueste Spielversion und die Kartendaten (~5 GB, einmalig) von GitHub-Releases, installiert nach
# ~/.local/share/map44 und legt den Befehl "map44" sowie einen Startmenü-Eintrag an. Erneut ausführen = Update
# (Kartendaten werden nur neu geladen, wenn sich ihre Version ändert; abgebrochene Downloads werden fortgesetzt).
#
# Umgebungsvariablen: MAP44_HOME=<ordner> (Ziel), MAP44_KEEP_ZIPS=1 (Downloads behalten)
# Deinstallieren:     curl -fsSL …/install.sh | bash -s -- --uninstall
set -euo pipefail

REPO="fromCharCode/map44"
API="https://api.github.com/repos/$REPO/releases"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
DEST="${MAP44_HOME:-$DATA_HOME/map44}"
BIN_DIR="$HOME/.local/bin"
APP_FILE="$DATA_HOME/applications/map44.desktop"

say()  { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mFehler:\033[0m %s\n' "$*" >&2; exit 1; }

if [ "${1:-}" = "--uninstall" ]; then
  rm -rf "$DEST" "$BIN_DIR/map44" "$APP_FILE"
  say "Map44 entfernt."
  exit 0
fi

for c in curl unzip sha256sum; do
  command -v "$c" >/dev/null 2>&1 || die "Bitte zuerst '$c' installieren (z. B. sudo apt install $c / sudo dnf install $c)."
done
[ "$(uname -m)" = "x86_64" ] || die "Nur x86_64 wird unterstützt."

DL="$DEST/.downloads"
mkdir -p "$DL"

# Release-Dateien (Name -> URL) aus der GitHub-API, ohne jq
assets() {
  curl -fsSL -H "Accept: application/vnd.github+json" "$1" \
    | grep -o '"browser_download_url": *"[^"]*"' | sed -E 's/.*"(https[^"]+)"$/\1/'
}

# Download mit Fortsetzen; vorhandene, geprüfte Dateien werden übersprungen
fetch() {  # $1 url, $2 datei, $3 erwartete sha256 (optional)
  local url="$1" out="$2" sum="${3:-}"
  if [ -n "$sum" ] && [ -f "$out" ] && echo "$sum  $out" | sha256sum -c --status 2>/dev/null; then
    return 0
  fi
  for try in 1 2 3; do
    curl -fL --retry 5 --retry-delay 3 -C - --progress-bar -o "$out" "$url" || true
    if [ -z "$sum" ] || echo "$sum  $out" | sha256sum -c --status 2>/dev/null; then
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
GAME_URL=$(echo "$GAME_URLS" | grep -E '/map44-linux-x86_64\.zip$' | head -1)
SUMS_URL=$(echo "$GAME_URLS" | grep -E '/SHA256SUMS$' | head -1)
[ -n "$GAME_URL" ] || die "Keine Linux-Version im neuesten Release gefunden."
[ -n "$SUMS_URL" ] && curl -fsSL -o "$DL/SHA256SUMS" "$SUMS_URL"

say "Lade das Spiel …"
fetch "$GAME_URL" "$DL/map44-linux-x86_64.zip" "$(sum_of "$DL/SHA256SUMS" map44-linux-x86_64.zip)"
unzip -oq "$DL/map44-linux-x86_64.zip" -d "$DEST"
chmod +x "$DEST/map44.x86_64"
[ "${MAP44_KEEP_ZIPS:-0}" = 1 ] || rm -f "$DL/map44-linux-x86_64.zip"

NEED=$(tr -d '[:space:]' < "$DEST/DATA_VERSION")
HAVE=""; [ -f "$DEST/data/VERSION" ] && HAVE=$(tr -d '[:space:]' < "$DEST/data/VERSION")
if [ "$NEED" != "$HAVE" ]; then
  say "Lade die Kartendaten $NEED (rund 5 GB, einmalig – das dauert je nach Leitung eine Weile) …"
  DATA_URLS=$(assets "$API/tags/$NEED")
  DSUM_URL=$(echo "$DATA_URLS" | grep -E "/map44-$NEED\.sha256\$" | head -1)
  [ -n "$DSUM_URL" ] && curl -fsSL -o "$DL/data.sha256" "$DSUM_URL"
  PARTS=$(echo "$DATA_URLS" | grep -E "/map44-$NEED-[0-9]+\.zip\$" | sort)
  [ -n "$PARTS" ] || die "Kartendaten $NEED nicht gefunden."
  n=$(echo "$PARTS" | wc -l); i=0
  for u in $PARTS; do
    i=$((i + 1)); f="$DL/$(basename "$u")"
    say "Kartendaten Teil $i/$n"
    fetch "$u" "$f" "$(sum_of "$DL/data.sha256" "$(basename "$u")")"
  done
  say "Entpacke Kartendaten …"
  rm -rf "$DEST/data"
  for u in $PARTS; do unzip -oq "$DL/$(basename "$u")" -d "$DEST"; done
  echo "$NEED" > "$DEST/data/VERSION"
  [ "${MAP44_KEEP_ZIPS:-0}" = 1 ] || rm -f "$DL"/map44-"$NEED"-*.zip
else
  say "Kartendaten $HAVE sind aktuell."
fi

# Startbefehl und Menüeintrag
mkdir -p "$BIN_DIR" "$(dirname "$APP_FILE")"
cat > "$BIN_DIR/map44" <<EOF
#!/bin/sh
cd "$DEST" && exec ./map44.x86_64 "\$@"
EOF
chmod +x "$BIN_DIR/map44"
cat > "$APP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Map44 – Dresden
Comment=Open-World-Dresden
Exec=$BIN_DIR/map44
Path=$DEST
Icon=applications-games
Terminal=false
Categories=Game;
EOF

say "Fertig! Starten mit:  map44   (oder über das Startmenü „Map44 – Dresden“)"
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) say "Hinweis: $BIN_DIR ist nicht im PATH – dann direkt: $BIN_DIR/map44";; esac
