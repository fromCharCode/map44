"""Gemeinsame Konfiguration: Spielgebiet in UTM33 (EPSG:25833 = ETRS89 / UTM 33N).

Der Ursprung (0,0) des Spiels liegt in der Mitte des Gebiets (Altmarkt).
Godot-Achsen: x = Osten, y = Höhe, z = -Norden (Godot ist rechtshändig, -z ist "vorne").
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

# Gebiet: 2 km x 2 km um den Altmarkt (UTM33)
ORIGIN_E = 411000.0
ORIGIN_N = 5656200.0
HALF = 1000.0
BBOX_UTM = (ORIGIN_E - HALF, ORIGIN_N - HALF, ORIGIN_E + HALF, ORIGIN_N + HALF)  # minE, minN, maxE, maxN
BASE_HEIGHT = 112.77   # globales Höhen-Nullniveau (m ü. NHN), Altmarkt

# Kachelmodus: DRESDEN_TILE="410,5656" (Ost-km, Nord-km der SW-Ecke einer 2x2-km-Kachel)
import os as _os
TILE = _os.environ.get("DRESDEN_TILE")
OSM_DIR = RAW / "osm"
DOP_DIR = RAW / "dop"
if TILE:
    _e, _n = (int(v) for v in TILE.split(","))
    TILE_NAME = f"{_e}_{_n}"
    BBOX_UTM = (_e * 1000.0, _n * 1000.0, (_e + 2) * 1000.0, (_n + 2) * 1000.0)
    OSM_DIR = RAW / "tiles" / TILE_NAME / "osm"
    DOP_DIR = RAW / "tiles" / TILE_NAME / "dop"
    PROCESSED = PROCESSED / "tiles" / TILE_NAME

DOP_WMS = "https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest"
DOP_LAYER = "sn_dop_020"
OVERPASS = "https://overpass-api.de/api/interpreter"
USER_AGENT = "DresdenGame/0.1 (private hobby project; contact via GitHub-less local use)"
