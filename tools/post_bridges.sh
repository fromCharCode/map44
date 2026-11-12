#!/bin/bash
# Nach Änderungen an bridge_arches.py/bridge_decks.py: Schritte für alle Kacheln neu (idempotent).
#   bash tools/post_bridges.sh [-P n] [--decks-only]
cd "$(dirname "$0")"
P=4
[ "$1" = "-P" ] && P=$2
rm -f ../data/raw/tilelogs/POST_FAILS.txt
if [ "$3" != "--decks-only" ] && [ "$1" != "--decks-only" ]; then
  ls ../data/processed/tiles | xargs -P "$P" -I{} sh -c '../.venv/bin/python bridge_arches.py {} > ../data/raw/tilelogs/post_{}.log 2>&1 || echo "ARCHFAIL {}" >> ../data/raw/tilelogs/POST_FAILS.txt'
fi
# Deck-Auszüge für die Nachbarkacheln, dann Deckaufbau
../.venv/bin/python bridge_decks.py --cache > /dev/null 2>&1 || echo "CACHEFAIL" >> ../data/raw/tilelogs/POST_FAILS.txt
ls ../data/processed/tiles | xargs -P "$P" -I{} sh -c '../.venv/bin/python bridge_decks.py {} >> ../data/raw/tilelogs/post_{}.log 2>&1 || echo "DECKFAIL {}" >> ../data/raw/tilelogs/POST_FAILS.txt'
if [ "$3" != "--decks-only" ] && [ "$1" != "--decks-only" ]; then
  ../.venv/bin/python tunnels.py > ../data/raw/tilelogs/tunnels_post.log 2>&1 || echo "TUNNELFAIL" >> ../data/raw/tilelogs/POST_FAILS.txt
fi
echo POST_DONE
