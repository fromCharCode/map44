"""Tankstellen (Nachbearbeitung nach build_city): Überdachung, Zapfsäulen, Marke.

  python tools/fuel.py [E,N ...]            (ohne Argument: alle Kacheln)

Quelle: OSM amenity=fuel (Punkt oder Fläche: Marke/Name) und building=roof in der Nähe (Grundriss der Überdachung).
Die Überdachung ist im LoD2-Stadtmodell ein massiver Block über den Zapfsäulen – der Block wird entfernt, das Spiel
baut stattdessen ein offenes Dach auf Stützen mit Zapfinseln (godot/scripts/fuel.gd).
Schreibt city.life.fuel: [x, z, gier, y, breite, länge, höhe, marke, name]   (länge = lange Seite, Gier der
langen Achse; Zapfinseln stehen quer dazu in Reihe). Wiederholbar (entfernte Gebäude werden in fuel_removed gemerkt).
"""
import json
import math
import sys
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
RAW = ROOT / "data" / "raw" / "tiles"
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0
# einheitliche Schreibweise der Marke (Farben/Schriftzug wählt fuel.gd)
BRANDS = {"total": "TotalEnergies", "totalenergies": "TotalEnergies", "aral": "Aral", "jet": "JET", "star": "star",
          "shell": "Shell", "esso": "Esso", "hem": "HEM", "sprint": "Sprint", "agip": "Agip", "eni": "Agip",
          "orlen": "Orlen", "oil!": "OIL!", "greenline": "Greenline", "hoyer": "Hoyer", "kaufland": "Kaufland"}


def local(lon, lat):
    e, n = TO_UTM.transform(lon, lat)
    return e - ORIGIN_E, -(n - ORIGIN_N)


def poly_of(el):
    g = el.get("geometry") or []
    if len(g) < 4:
        return None
    pg = Polygon([local(p["lon"], p["lat"]) for p in g])
    if not pg.is_valid:
        pg = pg.buffer(0)
    return pg if (not pg.is_empty and pg.geom_type == "Polygon") else None


def rect_of(pg):
    """Mitte, Gier der langen Achse, Breite (kurz), Länge (lang) des kleinsten umschließenden Rechtecks"""
    r = pg.minimum_rotated_rectangle
    c = list(r.exterior.coords)[:4]
    e0 = (c[1][0] - c[0][0], c[1][1] - c[0][1])
    e1 = (c[2][0] - c[1][0], c[2][1] - c[1][1])
    l0, l1 = math.hypot(*e0), math.hypot(*e1)
    long_e, L, W = (e0, l0, l1) if l0 >= l1 else (e1, l1, l0)
    # Gier wie im Spiel: Basis(UP, gier) * (0, 0, 1) = Richtung der langen Achse
    yaw = math.atan2(long_e[0], long_e[1])
    return r.centroid.x, r.centroid.y, yaw, W, L


def tile_fuel(name):
    cf = TILES / name / "city.json"
    if not cf.exists():
        return 0
    city = json.loads(cf.read_text(encoding="utf-8"))
    e_km, n_km = (int(v) for v in name.split("_"))
    x0, z0 = e_km * 1000.0 - ORIGIN_E, -((n_km + 2) * 1000.0 - ORIGIN_N)
    stations, roofs = [], []
    for fn in ("pois.json", "buildings.json", "landuse.json"):
        f = RAW / name / "osm" / fn
        if not f.exists():
            continue
        for el in json.loads(f.read_text(encoding="utf-8")).get("elements", []):
            t = el.get("tags") or {}
            if t.get("amenity") == "fuel":
                if el.get("type") == "node":
                    stations.append((Point(local(el["lon"], el["lat"])), None, t))
                else:
                    pg = poly_of(el)
                    if pg is not None:
                        stations.append((pg.centroid, pg, t))
            if fn == "buildings.json" and t.get("building") == "roof":
                pg = poly_of(el)
                if pg is not None and 25.0 <= pg.area <= 2500.0:
                    roofs.append(pg)
    out, removed = [], []
    used = set()
    seen_pos = []
    terr = None
    for pt, area, t in stations:
        if not (x0 <= pt.x < x0 + 2000.0 and z0 <= pt.y < z0 + 2000.0):
            continue
        if any(pt.distance(q) < 25.0 for q in seen_pos):
            continue                                # Punkt und Fläche derselben Tankstelle
        seen_pos.append(pt)
        # Überdachung: OSM-Dach an der Tankstelle (in der Fläche bzw. ≤ 45 m vom Punkt), das größte
        cand = [(i, r) for i, r in enumerate(roofs) if i not in used and
                ((area is not None and r.intersects(area)) or r.distance(pt) <= 45.0)]
        if cand:
            i, roof = max(cand, key=lambda c: c[1].area)
            used.add(i)
            cx, cz, yaw, W, L = rect_of(roof)
        else:
            # ohne erfasstes Dach: Regelüberdachung 9 × 16 m am Punkt, lange Achse entlang der nächsten Straße
            roof = None
            cx, cz, W, L = pt.x, pt.y, 9.0, 16.0
            yaw = 0.0
            best = None
            for r in city.get("roads", []):
                if r.get("cls") in ("footway", "path", "cycleway", "steps", "service") or len(r["pts"]) < 2:
                    continue
                ln = LineString([p[:2] for p in r["pts"]])
                d = ln.distance(pt)
                if d < 80.0 and (best is None or d < best[0]):
                    s = ln.project(pt)
                    a, b = ln.interpolate(max(s - 2.0, 0.0)), ln.interpolate(min(s + 2.0, ln.length))
                    best = (d, math.atan2(b.x - a.x, b.y - a.y))
            if best:
                yaw = best[1]
        h = 5.0
        if roof is not None:
            # LoD2-Block der Überdachung entfernen (Schwerpunkt im Dach oder > 50 % überdeckt)
            keep = []
            for b in city.get("buildings", []):
                try:
                    bp = Polygon([(q[0], q[1]) for q in b["rings"][0]])
                except (KeyError, IndexError, ValueError, TypeError):
                    keep.append(b)
                    continue
                if not bp.is_valid:
                    bp = bp.buffer(0)
                if bp.is_empty or bp.area < 1.0:
                    keep.append(b)
                    continue
                inter = bp.intersection(roof.buffer(1.0)).area
                if inter > 0.5 * bp.area and bp.area <= 1.6 * roof.area:
                    removed.append(b.get("gid") or b.get("id"))
                    ev = b.get("eave")
                    if isinstance(ev, (int, float)) and 3.8 <= ev <= 7.5:
                        h = float(ev)
                else:
                    keep.append(b)
            city["buildings"] = keep
        # Bäume/Laternen unter dem Dach (Laserscan-Bäume standen zwischen den Zapfsäulen)
        ca, sa = math.cos(yaw), math.sin(yaw)

        def under(px, pz):
            dx, dz = px - cx, pz - cz
            lz = dx * sa + dz * ca                       # entlang der langen Achse
            lx = dx * ca - dz * sa
            return abs(lx) < W * 0.5 + 1.5 and abs(lz) < L * 0.5 + 1.5
        for key in ("trees", "lamps"):
            if city.get(key):
                city[key] = [o_ for o_ in city[key] if not under(o_[0], o_[1])]
        if terr is None:
            import numpy as np
            terr = np.frombuffer((TILES / name / "terrain.f32").read_bytes(), dtype="<f4").reshape(2000, 2000)
        c_, r_ = min(max(int(cx - x0), 0), 1999), min(max(int(cz - z0), 0), 1999)
        y = float(terr[r_, c_])
        raw_brand = (t.get("brand") or t.get("operator") or "").strip()
        nm = (t.get("name") or raw_brand or "Tankstelle").strip()
        brand = BRANDS.get(raw_brand.lower(), raw_brand or "frei")
        if "dynamo" in nm.lower():
            brand = "Dynamo"
        out.append([round(cx, 2), round(cz, 2), round(yaw, 3), round(y, 2), round(max(W, 6.0), 1), round(max(L, 8.0), 1),
                    round(h, 1), brand, nm[:40]])
    life = city.setdefault("life", {})
    if out or life.get("fuel"):
        life["fuel"] = out
        if removed:
            city["fuel_removed"] = sorted(set((city.get("fuel_removed") or []) + [str(r) for r in removed]))
        cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    if out:
        print(f"  {name}: {len(out)} Tankstellen ({', '.join(o[7] for o in out)}), {len(removed)} LoD2-Dachblöcke entfernt")
    return len(out)


def main():
    args = [a.replace(",", "_") for a in sys.argv[1:] if not a.startswith("--")]
    names = args or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    n = sum(tile_fuel(nm) for nm in names)
    if not args:
        print(f"{n} Tankstellen")


if __name__ == "__main__":
    main()
