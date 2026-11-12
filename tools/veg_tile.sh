#!/bin/bash
cd "$(dirname "$0")"
source ../.venv/bin/activate
export DRESDEN_TILE="$1"
python vegetation.py >> "../data/raw/tilelogs/veg_$1.log" 2>&1 || echo "FAIL $1" >> ../data/raw/tilelogs/VEG_FAILS.txt
