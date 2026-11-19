#!/bin/bash
cd "$(dirname "$0")"
source ../.venv/bin/activate
export DRESDEN_TILE="$1"
python build_city.py > "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || { echo "FAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt; exit 1; }
python mly_colors.py apply "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "COLFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python vegetation.py >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "VEGFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python street_green.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "GREENFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python curbs.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "CURBFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python bridge_styles.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "BRIDGEFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python bridge_mounds.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "MOUNDFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python bridge_arches.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "ARCHFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python bridge_decks.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "DECKFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python bridge_ramps.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "RAMPFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python platform_rails.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "PRAILFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python fuel.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "FUELFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python monuments.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "MONFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python clear_roads.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "CLEARFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python blitzer.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "BLITZFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python allotments.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "ALLOTFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python facade_eras.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "ERAFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python stops_fix.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "STOPFIXFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python sports.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "SPORTFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python taxi_stands.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "TAXIFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python landmark_looks.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "LOOKFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python water_fill.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "WATERFILLFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python terrace_edges.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "TERRACEFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python rail_slabs.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "RAILSLABFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python under_decks.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "UNDERDECKFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
