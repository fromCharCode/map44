"""Inseln in Wasserflächen entfernen, die es nicht mehr gibt (Nachbearbeitung, ohne Neubau der Kachel).

  python tools/water_fill.py [E,N ...]      (ohne Argument: alle Kacheln mit Einträgen)

tools/overrides.json "water_fill": [[x, z, radius, "Anmerkung"], ...] – Löcher einer Wasserfläche, deren Mitte im
Umkreis liegt, werden geschlossen; das Gelände darunter (terrain.f32, terrain_col.f32) wird auf 2,5 m unter den
Wasserspiegel gesenkt. Beispiel: Strompfeiler der 2025 abgerissenen Carolabrücke. Wiederholbar.
"""
import json
import sys
from pathlib import Path

import mapbox_earcut
import numpy as np
from shapely.geometry import Point, Polygon

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0
FILL = json.loads((ROOT / "tools" / "overrides.json").read_text(encoding="utf-8")).get("water_fill", [])


def _earcut(rings):
    verts = np.concatenate([np.array(r, dtype=np.float32) for r in rings])
    ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
    return [int(i) for i in mapbox_earcut.triangulate_float32(verts, ends)]


def fix_tile(name):
    cf = TILES / name / "city.json"
    if not cf.exists():
        return 0
    e_km, n_km = (int(v) for v in name.split("_"))
    x0, z0 = e_km * 1000.0 - ORIGIN_E, -((n_km + 2) * 1000.0 - ORIGIN_N)
    spots = [f for f in FILL if x0 - 50 <= f[0] <= x0 + 2050 and z0 - 50 <= f[1] <= z0 + 2050]
    if not spots:
        return 0
    city = json.loads(cf.read_text(encoding="utf-8"))
    tj = json.loads((TILES / name / "terrain.json").read_text(encoding="utf-8"))
    sp = float(tj["spacing"])
    n = 0
    grids = []
    for fn, size in (("terrain.f32", int(tj["width"])), ("terrain_col.f32", int(tj["width"]) + 1)):
        p = TILES / name / fn
        if p.exists() and p.stat().st_size == size * size * 4:
            grids.append((p, np.fromfile(p, dtype="<f4").reshape(size, size), size))
    for w in city.get("water", []):
        keep = [w["rings"][0]]
        for r in w["rings"][1:]:
            pg = Polygon([(q[0], q[1]) for q in r])
            c = pg.centroid
            if not any(Point(f[0], f[1]).distance(c) <= f[2] for f in spots):
                keep.append(r)
                continue
            n += 1
            big = pg.buffer(4.0)
            bx0, bz0, bx1, bz1 = big.bounds
            for _, g, size in grids:
                for row in range(max(int((bz0 - z0) / sp), 0), min(int((bz1 - z0) / sp) + 2, size)):
                    for col in range(max(int((bx0 - x0) / sp), 0), min(int((bx1 - x0) / sp) + 2, size)):
                        if big.contains(Point(x0 + col * sp, z0 + row * sp)):
                            g[row, col] = min(g[row, col], float(w["level"]) - 2.5)
        if len(keep) != len(w["rings"]):
            w["rings"] = keep
            w["tris"] = _earcut(keep)
    if n:
        cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
        for p, g, _ in grids:
            g.astype("<f4").tofile(p)
    return n


def main():
    names = [a.replace(",", "_") for a in sys.argv[1:]] or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    print(f"Wasserflächen: {sum(fix_tile(nm) for nm in names)} Inseln entfernt")


if __name__ == "__main__":
    main()
