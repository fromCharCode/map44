#!/usr/bin/env bash
# Map44 – Dresden: Installer für Linux (x86_64)
#
#   curl -fsSL https://raw.githubusercontent.com/fromCharCode/map44/main/install/install.sh | bash
#
# Lädt die neueste Spielversion und die Kartendaten (~5 GB, einmalig) von GitHub-Releases, installiert nach
# ~/.local/share/map44 und legt den Befehl "map44" sowie einen Startmenü-Eintrag an. Erneut ausführen = Update
# (von den Kartendaten werden nur geänderte Pakete geladen; abgebrochene Downloads werden fortgesetzt).
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

# Kartendaten alter Datenversionen (ohne Manifest): alle Teile laden, data/ komplett ersetzen
legacy_data() {  # $1 datenversion, $2 zielordner (enthält data/)
  local need="$1" root="$2"
  say "Lade die Kartendaten $need (rund 5 GB, einmalig – das dauert je nach Leitung eine Weile) …"
  DATA_URLS=$(assets "$API/tags/$need")
  DSUM_URL=$(echo "$DATA_URLS" | grep -E "/map44-$need\.sha256\$" | head -1)
  [ -n "$DSUM_URL" ] && curl -fsSL -o "$DL/data.sha256" "$DSUM_URL"
  PARTS=$(echo "$DATA_URLS" | grep -E "/map44-$need-[0-9]+\.zip\$" | sort)
  [ -n "$PARTS" ] || die "Kartendaten $need nicht gefunden."
  n=$(echo "$PARTS" | wc -l); i=0
  for u in $PARTS; do
    i=$((i + 1)); f="$DL/$(basename "$u")"
    say "Kartendaten Teil $i/$n"
    fetch "$u" "$f" "$(sum_of "$DL/data.sha256" "$(basename "$u")")"
  done
  say "Entpacke Kartendaten …"
  rm -rf "$root/data"
  for u in $PARTS; do unzip -oq "$DL/$(basename "$u")" -d "$root"; done
  echo "$need" > "$root/data/VERSION"
  [ "${MAP44_KEEP_ZIPS:-0}" = 1 ] || rm -f "$DL"/map44-"$need"-*.zip
}

# Kartendaten inkrementell (ab Datenversionen mit Manifest): nur geänderte Pakete laden.
# Zustand in data/MANIFEST (installierte Pakete) und data/.packs/<paket>.files (deren Dateien) –
# wird pro Schritt fortgeschrieben, ein abgebrochenes Update setzt beim nächsten Lauf sauber fort.
install_data() {  # $1 datenversion, $2 zielordner (enthält data/)
  local need="$1" root="$2" data="$2/data" mf="$DL/data.manifest"
  local st="$data/.packs" inst="$data/MANIFEST"
  if ! curl -fsSL -o "$mf" "https://github.com/$REPO/releases/download/$need/map44-$need.manifest"; then
    legacy_data "$need" "$root"; return
  fi
  [ -f "$inst" ] || rm -rf "$data"      # Installation ohne Manifest: einmal komplett neu
  mkdir -p "$st"; touch "$inst"
  rm -f "$data/VERSION"
  local todo gone
  todo=$(awk 'FILENAME==ARGV[1]{h[$1" "$3]=1;next} !(($1" "$3) in h)' "$inst" "$mf")
  gone=$(awk 'FILENAME==ARGV[1]{w[$1" "$3]=1;next} !(($1" "$3) in w)' "$mf" "$inst")
  if [ -n "$todo" ]; then
    local n mb i=0
    n=$(echo "$todo" | wc -l | tr -d ' ')
    mb=$(echo "$todo" | awk '{s+=$2} END{printf "%d", s/1e6}')
    say "Lade die Kartendaten $need: $n Paket(e), rund $mb MB …"
    while read -r sha size name tag; do
      i=$((i + 1)); say "Kartendaten Teil $i/$n ($name)"
      fetch "https://github.com/$REPO/releases/download/$tag/$name" "$DL/$name" "$sha"
    done <<< "$todo"
  fi
  # erst wenn alles geladen ist: veraltete Pakete entfernen …
  if [ -n "$gone" ]; then
    while read -r sha size name tag; do
      if [ -f "$st/$name.files" ]; then
        while read -r f; do case "$f" in */|"") ;; *) rm -f "$root/$f";; esac; done < "$st/$name.files"
        rm -f "$st/$name.files"
      fi
      grep -v " $name " "$inst" > "$inst.tmp" || true; mv "$inst.tmp" "$inst"
    done <<< "$gone"
    find "$data" -mindepth 1 -type d -empty -delete 2>/dev/null || true
  fi
  # … dann neue entpacken
  if [ -n "$todo" ]; then
    say "Entpacke Kartendaten …"
    while read -r sha size name tag; do
      unzip -oq "$DL/$name" -d "$root"
      unzip -Z1 "$DL/$name" > "$st/$name.files"
      echo "$sha $size $name $tag" >> "$inst"
      [ "${MAP44_KEEP_ZIPS:-0}" = 1 ] || rm -f "$DL/$name"
    done <<< "$todo"
  fi
  echo "$need" > "$data/VERSION"
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
  install_data "$NEED" "$DEST"
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
