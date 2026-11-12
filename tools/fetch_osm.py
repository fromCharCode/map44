"""Lädt OSM-Daten (Straßen, Gebäude, Bäume, Flächen, Wasser, Schienen) per Overpass.

Quelle: © OpenStreetMap-Mitwirkende, ODbL.
"""
import json
import sys
import time

import requests
from pyproj import Transformer

from config import BBOX_UTM, OSM_DIR, OVERPASS, RAW, USER_AGENT


MIRRORS = [OVERPASS, "https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter"]


def main() -> None:
    out = OSM_DIR
    out.mkdir(parents=True, exist_ok=True)
    t = Transformer.from_crs("EPSG:25833", "EPSG:4326", always_xy=True)
    min_e, min_n, max_e, max_n = BBOX_UTM
    # etwas Rand (100 m), damit nichts an der Kante abgeschnitten wird
    lon0, lat0 = t.transform(min_e - 100, min_n - 100)
    lon1, lat1 = t.transform(max_e + 100, max_n + 100)
    bb = f"{lat0:.6f},{lon0:.6f},{lat1:.6f},{lon1:.6f}"

    queries = {
        "buildings": f'(way["building"]({bb});relation["building"]({bb});way["building:part"]({bb}););out geom;',
        "roads": f'way["highway"]({bb});out geom;',
        "rail": f'way["railway"~"^(tram|rail|light_rail|subway)$"]({bb});out geom;',
        "landuse": f'(way["landuse"]({bb});relation["landuse"]({bb});way["leisure"]({bb});relation["leisure"]({bb});'
                   f'way["natural"~"^(wood|scrub|grassland|heath|sand)$"]({bb});relation["natural"~"^(wood|scrub|grassland)$"]({bb});'
                   f'way["amenity"="parking"]({bb}););out geom;',
        "water": f'(way["natural"="water"]({bb});relation["natural"="water"]({bb});way["waterway"]({bb});way["water"]({bb}););out geom;',
        "points": f'(node["natural"="tree"]({bb});node["highway"~"^(street_lamp|traffic_signals|crossing|stop)$"]({bb});'
                  f'node["amenity"~"^(bench|waste_basket|bicycle_parking)$"]({bb}););out;',
        "tree_rows": f'way["natural"="tree_row"]({bb});out geom;',
        "barriers": f'way["barrier"~"^(wall|fence|retaining_wall|city_wall)$"]({bb});out geom;',
        "bridges": f'(way["bridge"]({bb});way["man_made"="bridge"]({bb}););out geom;',
    }
    for name, q in queries.items():
        f = out / f"{name}.json"
        if f.exists() and f.stat().st_size > 50:
            continue
        data = f"[out:json][timeout:180];{q}"
        for attempt in range(8):
            try:
                r = requests.post(MIRRORS[attempt % len(MIRRORS)], data={"data": data}, timeout=240,
                                  headers={"User-Agent": USER_AGENT})
                if r.status_code == 200:
                    n = len(r.json().get("elements", []))
                    f.write_text(r.text, encoding="utf-8")
                    print(f"ok {name}: {n} Elemente", flush=True)
                    break
                print(f"fehler {name}: HTTP {r.status_code}", file=sys.stderr)
            except (requests.RequestException, json.JSONDecodeError) as exc:
                print(f"fehler {name}: {exc}", file=sys.stderr)
            time.sleep(10 * (attempt + 1))
        else:
            sys.exit(f"{name} nicht ladbar")
        time.sleep(2)


if __name__ == "__main__":
    main()
