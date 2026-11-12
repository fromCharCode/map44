#!/bin/bash
cd "$(dirname "$0")"
source ../.venv/bin/activate
export DRESDEN_TILE="$1"
python build_city.py > "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || { echo "FAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt; exit 1; }
python vegetation.py >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "VEGFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python street_green.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "GREENFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python curbs.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "CURBFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python bridge_styles.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "BRIDGEFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python bridge_mounds.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "MOUNDFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python bridge_arches.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "ARCHFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python bridge_ramps.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "RAMPFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
python platform_rails.py "$1" >> "../data/raw/tilelogs/rebuild_$1.log" 2>&1 || echo "PRAILFAIL $1" >> ../data/raw/tilelogs/REBUILD_FAILS.txt
