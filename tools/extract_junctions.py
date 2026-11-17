"""Autobahn-Anschlussstellen (highway=motorway_junction: Nummer, Name) aus dem Geofabrik-Auszug.

  python tools/extract_junctions.py
Ausgabe: data/raw/osm_extra/motorway_junctions.json  [{"id", "ref", "name", "e", "n"}]  (UTM33)
Quelle: (c) OpenStreetMap-Mitwirkende, ODbL. Für die Wegweiser (street_life.py: Ankündigungs-/Ausfahrttafeln).
"""
import json

import osmium
from pyproj import Transformer

from config import RAW

PBF = RAW / "geofabrik" / "sachsen.osm.pbf"
TILES = [tuple(int(v) for v in l.split(",")) for l in (RAW / "tile_order.txt").read_text().split() if l]
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)


def main():
    e0 = min(t[0] for t in TILES) * 1000.0 - 3000.0
    e1 = (max(t[0] for t in TILES) + 2) * 1000.0 + 3000.0
    n0 = min(t[1] for t in TILES) * 1000.0 - 3000.0
    n1 = (max(t[1] for t in TILES) + 2) * 1000.0 + 3000.0
    out = []
    fp = osmium.FileProcessor(str(PBF), osmium.osm.NODE).with_filter(osmium.filter.KeyFilter("highway"))
    for o in fp:
        if o.tags.get("highway") != "motorway_junction":
            continue
        e, n = TO_UTM.transform(o.location.lon, o.location.lat)
        if e0 <= e <= e1 and n0 <= n <= n1:
            out.append({"id": o.id, "ref": o.tags.get("ref", ""), "name": o.tags.get("name", ""), "e": round(e, 1), "n": round(n, 1)})
    d = RAW / "osm_extra"
    d.mkdir(parents=True, exist_ok=True)
    (d / "motorway_junctions.json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print(len(out), "Anschlussstellen")
    for j in sorted(out, key=lambda j: (j["name"], j["ref"]))[:60]:
        print(" ", j["ref"], j["name"])


if __name__ == "__main__":
    main()
