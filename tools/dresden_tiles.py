"""Berechnet, welche DGM1-2x2-km-Kacheln (GeoSN) für das gesamte Stadtgebiet Dresden nötig sind.

Quelle der Stadtgrenze: OSM-Relation (Overpass). Ausgabe: data/dgm_tiles.txt
"""
import json
import math
import sys
import time

import requests
from pyproj import Transformer
from shapely.geometry import LineString, Polygon, box
from shapely.ops import linemerge, polygonize, unary_union

from config import OVERPASS, RAW, USER_AGENT, ROOT

Q = '[out:json][timeout:120];relation["boundary"="administrative"]["admin_level"="6"]["name"="Dresden"];out geom;'


def main() -> None:
    f = RAW / "dresden_boundary.json"
    if not f.exists():
        for attempt in range(5):
            r = requests.post(OVERPASS, data={"data": Q}, timeout=180, headers={"User-Agent": USER_AGENT})
            if r.status_code == 200:
                f.write_text(r.text, encoding="utf-8")
                break
            print("Overpass:", r.status_code, file=sys.stderr)
            time.sleep(10 * (attempt + 1))
        else:
            sys.exit("Stadtgrenze nicht ladbar")
    data = json.loads(f.read_text(encoding="utf-8"))["elements"]
    t = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
    outers = []
    for el in data:
        for m in el.get("members", []):
            if m.get("role") == "outer" and m.get("geometry"):
                pts = [t.transform(p["lon"], p["lat"]) for p in m["geometry"]]
                if len(pts) > 1:
                    outers.append(LineString(pts))
    poly = unary_union(list(polygonize(linemerge(outers))))
    print(f"Stadtfläche: {poly.area / 1e6:.0f} km²")
    minx, miny, maxx, maxy = poly.bounds
    tiles = []
    for e in range(int(minx // 2000) * 2, int(maxx // 2000) * 2 + 2, 2):        # km
        for n in range(int(miny // 2000) * 2, int(maxy // 2000) * 2 + 2, 2):
            if poly.intersects(box(e * 1000, n * 1000, (e + 2) * 1000, (n + 2) * 1000)):
                tiles.append((e, n))
    have = {p.name.split("_")[1] + "_" + p.name.split("_")[2] for p in (RAW / "dgm").glob("dgm1_*")} if (RAW / "dgm").exists() else set()
    lines = []
    todo = []
    for e, n in tiles:
        name = f"33{e - 0}"  # Ost in km (3-stellig nach Zone 33)
        key = f"33{e:03d}"[-5:] if False else f"33{e % 1000:03d}"
        tile = f"{key}_{n}"
        if tile in have:
            continue
        todo.append(tile)
    out = ROOT / "data" / "dgm_tiles.txt"
    out.write_text("\n".join(todo) + "\n", encoding="utf-8")
    print(f"Kacheln insgesamt: {len(tiles)}, schon vorhanden: {len(tiles) - len(todo)}, fehlen: {len(todo)}")
    # Übersicht als Raster (Zeilen = Nord absteigend, Spalten = Ost)
    es = sorted({e for e, n in tiles})
    ns = sorted({n for e, n in tiles}, reverse=True)
    tset = set(tiles)
    print("Ost(km) ->  " + " ".join(f"{e % 1000:3d}" for e in es))
    for n in ns:
        row = ""
        for e in es:
            k = f"33{e % 1000:03d}_{n}"
            row += "  . " if (e, n) not in tset else ("  # " if k in have else "  o ")
        print(f"N{n}  " + row)


if __name__ == "__main__":
    main()
