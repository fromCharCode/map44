#!/bin/bash
# usage: run_tile.sh E,N   (Ost-km,Nord-km der SW-Ecke); OSM kommt aus extract_osm.py
cd "$(dirname "$0")"
source ../.venv/bin/activate
export DRESDEN_TILE="$1"
python fetch_dop.py && python build_terrain.py && python build_city.py
