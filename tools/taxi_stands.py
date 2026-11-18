"""Taxistände je Kachel: city["taxi_stands"] = [[x, z, yaw, name, plätze]] (Nachbearbeitung, ohne Neubau).

  python tools/taxi_stands.py [E,N ...]      (ohne Argument: alle Kacheln)

Quelle: OSM amenity=taxi (© OpenStreetMap-Mitwirkende, ODbL), aus den Rohdaten der Kachel (pois.json). Der Stand
wird an den rechten Rand der nächsten Kfz-Straße gelegt (≤ 35 m), yaw = Fahrtrichtung der Aufstellung.
"""
import json
import math
import sys
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, Point

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
RAW = ROOT / "data" / "raw" / "tiles"
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
DRIVE = {"primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service"}


def tile_stands(name):
    cf = TILES / name / "city.json"
    pf = RAW / name / "osm" / "pois.json"
    if not cf.exists() or not pf.exists():
        return 0
    e_km, n_km = (int(v) for v in name.split("_"))
    x0, z0 = e_km * 1000.0 - ORIGIN_E, -((n_km + 2) * 1000.0 - ORIGIN_N)
    city = json.loads(cf.read_text(encoding="utf-8"))
    roads = [(LineString([(p[0], p[1]) for p in r["pts"]]), r) for r in city.get("roads", [])
             if r.get("cls") in DRIVE and len(r["pts"]) >= 2 and not r.get("bridge")]
    out = []
    for el in json.loads(pf.read_text(encoding="utf-8")).get("elements", []):
        t = el.get("tags") or {}
        if t.get("amenity") != "taxi" or "lon" not in el:
            continue
        e, n = TO_UTM.transform(el["lon"], el["lat"])
        x, z = e - ORIGIN_E, -(n - ORIGIN_N)
        if not (x0 <= x < x0 + 2000.0 and z0 <= z < z0 + 2000.0):
            continue
        pt = Point(x, z)
        best = None
        for ln, r in roads:
            d = ln.distance(pt)
            if d < 35.0 and (best is None or d < best[0]):
                best = (d, ln, r)
        if best is None:
            continue
        _d, ln, r = best
        s = ln.project(pt)
        a, b = ln.interpolate(max(s - 1.0, 0.0)), ln.interpolate(min(s + 1.0, ln.length))
        c = ln.interpolate(s)
        tl = math.hypot(b.x - a.x, b.y - a.y) or 1.0
        tx, tz = (b.x - a.x) / tl, (b.y - a.y) / tl
        nx, nz = -tz, tx                                        # rechts der Zeichenrichtung (x/z-Ebene)
        side = 1.0 if (x - c.x) * nx + (z - c.y) * nz >= 0.0 else -1.0
        if side < 0.0:
            tx, tz = -tx, -tz                                   # Aufstellung in Fahrtrichtung dieser Straßenseite
        hw = float(r["width"]) * 0.5
        px, pz = c.x + nx * side * (hw - 1.1), c.y + nz * side * (hw - 1.1)
        yaw = math.atan2(-tx, -tz)
        nm = (t.get("name") or "Taxistand").replace("Taxihalteplatz ", "")
        try:
            cap = int(str(t.get("capacity") or "3").split(";")[0])
        except ValueError:
            cap = 3
        out.append([round(px, 2), round(pz, 2), round(yaw, 3), nm, max(1, min(cap, 6))])
    if out or "taxi_stands" in city:
        city["taxi_stands"] = out
        cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    return len(out)


def main():
    names = [a.replace(",", "_") for a in sys.argv[1:]] or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    print(f"Taxistände: {sum(tile_stands(nm) for nm in names)} in {len(names)} Kacheln")


if __name__ == "__main__":
    main()
