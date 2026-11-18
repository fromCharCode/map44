"""Kleingartenanlagen (Gartensparten) je Kachel: city["allotments"] – Parzellen mit Hecke/Zaun, Laube, Beeten,
Gewächshaus, Obstbäumen und Kieswegen (Nachbearbeitung, ohne Neubau der Kachel).

  python tools/allotments.py [E,N ...] [--dry]     (ohne Argument: alle Kacheln)

Quelle der Flächen: OSM landuse=allotments (© OpenStreetMap-Mitwirkende, ODbL). Einzelne Parzellen sind in Dresden
nicht kartiert; sie entstehen als Raster entlang der Hauptrichtung der Anlage: je zwei Parzellenreihen Rücken an
Rücken (22 m tief, 13 m breit, typische 300 m²), dazwischen 2,6 m breite Kieswege. Vorhandene Gebäude (LoD2: echte
Lauben, Vereinsheime) und Wege (OSM) bleiben; eine eigene Laube bekommt nur die Parzelle ohne Gebäude.
Die Anordnung hängt nur von der OSM-Fläche ab (gleiches Ergebnis in Nachbarkacheln), jede Kachel behält die
Parzellen, deren Mittelpunkt in ihr liegt.

Ausgabe:
  huts   [x, z, y, rot, breite, tiefe, wandhöhe, wandfarbe, dachfarbe, dachform(0 Sattel, 1 Pult, 2 flach)]
  hedges [ax, az, bx, bz, höhe, art(0 Hecke, 1 Holzzaun, 2 Maschendraht)]
  beds   [x, z, rot, breite, länge, art(0 Gemüse, 1 Blumen, 2 Rasenweg-Platten)]
  glass  [x, z, rot]                       Gewächshaus 2 × 3 m
  lanes  [[[x, z], …], …]                  Kieswege (Mittellinien, 2,6 m breit)
Obstbäume kommen in city["trees"] (letztes Feld "allot", wiederholbar).
"""
import json
import math
import random
import sys
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
RAW = ROOT / "data" / "raw" / "tiles"
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
PLOT_W, PLOT_D, LANE = 13.0, 22.0, 2.6
PATH_CLS = {"path", "footway", "track", "service", "pedestrian", "cycleway", "residential", "living_street", "unclassified"}


def _local(lon, lat):
    e, n = TO_UTM.transform(lon, lat)
    return e - ORIGIN_E, -(n - ORIGIN_N)


def _polys(el):
    """Flächen eines OSM-Elements (Weg oder Multipolygon-Relation) in Spielkoordinaten."""
    out = []
    if el["type"] == "way":
        g = el.get("geometry") or []
        if len(g) >= 4:
            out.append(Polygon([_local(p["lon"], p["lat"]) for p in g]))
    else:
        holes = []
        for m in el.get("members", []):
            g = m.get("geometry") or []
            if len(g) < 4 or g[0] != g[-1]:
                continue
            pg = Polygon([_local(p["lon"], p["lat"]) for p in g])
            (holes if m.get("role") == "inner" else out).append(pg)
        if holes:
            hu = unary_union(holes)
            out = [p.difference(hu) for p in out]
    res = []
    for p in out:
        if not p.is_valid:
            p = p.buffer(0)
        for g in getattr(p, "geoms", [p]):
            if g.geom_type == "Polygon" and g.area > 150.0:
                res.append(g)
    return res


def layout(pid, poly, block):
    """Parzellen einer Anlage. block = Flächen, die frei bleiben (Straßen, echte Wege). Ergebnis in Weltkoordinaten:
    [(parzelle, wegseite_richtung, θ, i, j)], Wege [LineString]."""
    mrr = poly.minimum_rotated_rectangle
    cs = list(mrr.exterior.coords)
    e1 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
    e2 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
    ex = e1 if math.hypot(*e1) >= math.hypot(*e2) else e2
    th = math.atan2(ex[1], ex[0])
    c = poly.centroid
    pr = affinity.rotate(poly, -math.degrees(th), origin=(c.x, c.y))
    inner = pr.buffer(-0.8)
    if inner.is_empty:
        return [], [], th
    blk = affinity.rotate(block, -math.degrees(th), origin=(c.x, c.y)) if block is not None and not block.is_empty else None
    x0, y0, x1, y1 = pr.bounds
    period = 2 * PLOT_D + LANE
    nper = max(1, int(math.ceil((y1 - y0 + LANE) / period)))
    ys = y0 - 0.5 * (nper * period - LANE - (y1 - y0)) - LANE      # Raster mittig; am Rand beginnt eine Parzellenreihe
    ncol = max(1, int(round((x1 - x0) / PLOT_W)))
    wcol = (x1 - x0) / ncol
    plots, lanes = [], []
    for k in range(nper + 1):
        ly = ys + k * period
        lane = box(x0 - 1.0, ly, x1 + 1.0, ly + LANE).intersection(pr.buffer(-0.3))
        for g in getattr(lane, "geoms", [lane]):
            if g.geom_type == "Polygon" and g.area > 6.0:
                bx0, _b, bx1, _c = g.bounds
                if bx1 - bx0 > 4.0:
                    lanes.append(LineString([(bx0, ly + LANE * 0.5), (bx1, ly + LANE * 0.5)]))
        for row in (0, 1):
            ya = ly + LANE + row * PLOT_D
            yb = ya + PLOT_D
            lane_y = ya if row == 0 else yb                     # Wegseite der Reihe
            for i in range(ncol):
                cell = box(x0 + i * wcol, ya, x0 + (i + 1) * wcol, yb).intersection(inner)
                if blk is not None and not cell.is_empty:
                    cell = cell.difference(blk)
                parts = [g for g in getattr(cell, "geoms", [cell]) if g.geom_type == "Polygon"]
                if not parts:
                    continue
                g = max(parts, key=lambda q: q.area)
                if g.area < 110.0:
                    continue
                bx0, by0, bx1, by1 = g.bounds
                if min(bx1 - bx0, by1 - by0) < 7.0:
                    continue
                plots.append((g, lane_y, 1.0 if row == 0 else -1.0, (k, row, i)))

    def back(g):
        return affinity.rotate(g, math.degrees(th), origin=(c.x, c.y))
    return [(g, ly, sgn, key, back) for g, ly, sgn, key in plots], [back(l) for l in lanes], th


def tile_allotments(name, dry=False):
    d = TILES / name
    cf = d / "city.json"
    lf = RAW / name / "osm" / "landuse.json"
    if not cf.exists() or not lf.exists():
        return None
    e_km, n_km = (int(v) for v in name.split("_"))
    x0, z0 = e_km * 1000.0 - ORIGIN_E, -((n_km + 2) * 1000.0 - ORIGIN_N)
    tbox = box(x0, z0, x0 + 2000.0, z0 + 2000.0)
    areas = []
    for el in json.loads(lf.read_text(encoding="utf-8")).get("elements", []):
        if (el.get("tags") or {}).get("landuse") == "allotments":
            for pg in _polys(el):
                if pg.intersects(tbox):
                    areas.append((el["id"], pg))
    city = json.loads(cf.read_text(encoding="utf-8"))
    had = "allotments" in city
    city["trees"] = [t for t in city.get("trees", []) if not (len(t) > 7 and t[7] == "allot")]
    if not areas:
        if had and not dry:
            city.pop("allotments", None)
            cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
        return 0, 0
    ter = np.frombuffer((d / "terrain.f32").read_bytes(), dtype="<f4").reshape(2000, 2000)

    def ground(x, z):
        cc = min(max(x - x0 - 0.5, 0.0), 1998.999)
        r = min(max(z - z0 - 0.5, 0.0), 1998.999)
        c0, r0 = int(cc), int(r)
        fc, fr = cc - c0, r - r0
        top = ter[r0, c0] * (1 - fc) + ter[r0, c0 + 1] * fc
        bot = ter[r0 + 1, c0] * (1 - fc) + ter[r0 + 1, c0 + 1] * fc
        return float(top * (1 - fr) + bot * fr)

    # frei zu haltende Flächen: Straßen/Wege der Kachel und alle OSM-Wege (auch jenseits der Kachelgrenze: gleiche Lage)
    blocks = []
    rf = RAW / name / "osm" / "roads.json"
    if rf.exists():
        for el in json.loads(rf.read_text(encoding="utf-8")).get("elements", []):
            t = el.get("tags") or {}
            g = el.get("geometry") or []
            if el.get("type") != "way" or len(g) < 2 or not t.get("highway"):
                continue
            ln = LineString([_local(p["lon"], p["lat"]) for p in g])
            hw = 1.4 if t["highway"] in ("path", "footway", "steps", "cycleway") else 2.2 if t["highway"] in ("track", "service") else 4.0
            blocks.append(ln.buffer(hw, cap_style="flat"))
    btree = STRtree(blocks) if blocks else None
    bpolys = []
    for b in city.get("buildings", []):
        rs = b.get("rings") or []
        if rs and len(rs[0]) >= 3:
            pg = Polygon(rs[0])
            bpolys.append(pg if pg.is_valid else pg.buffer(0))
    for el in (json.loads((RAW / name / "osm" / "buildings.json").read_text(encoding="utf-8")).get("elements", [])
               if (RAW / name / "osm" / "buildings.json").exists() else []):
        g = el.get("geometry") or []
        if el.get("type") == "way" and len(g) >= 4:
            pg = Polygon([_local(p["lon"], p["lat"]) for p in g])
            bpolys.append(pg if pg.is_valid else pg.buffer(0))
    htree = STRtree(bpolys) if bpolys else None
    out = {"huts": [], "hedges": [], "beds": [], "glass": [], "lanes": []}
    trees = []
    seen_edges = set()
    nplots = 0
    for pid, poly in areas:
        blk = None
        if btree is not None:
            hit = [blocks[int(i)] for i in btree.query(poly) if blocks[int(i)].intersects(poly)]
            if hit:
                blk = unary_union(hit)
        plots, lanes, th = layout(pid, poly, blk)
        ux, uz = (math.cos(th), math.sin(th)), (-math.sin(th), math.cos(th))
        for ln in lanes:
            part = ln.intersection(tbox)
            for g in getattr(part, "geoms", [part]):
                if g.geom_type == "LineString" and g.length > 3.0:
                    if blk is not None:
                        g2 = g.difference(blk)
                    else:
                        g2 = g
                    for h in getattr(g2, "geoms", [g2]):
                        if h.geom_type == "LineString" and h.length > 3.0:
                            out["lanes"].append([[round(q[0], 2), round(q[1], 2)] for q in h.coords])
        for g_r, lane_y, sgn, key, back in plots:
            g = back(g_r)
            cen = g.centroid
            if not tbox.contains(cen):
                continue
            nplots += 1
            rnd = random.Random(hash((pid, key)) & 0xFFFFFFFF)
            has_b = htree is not None and any(bpolys[int(i)].intersects(g) for i in htree.query(g))
            # --- Einfriedung: Wegseite Zaun mit Pforte, sonst Hecke (jede Kante nur einmal)
            hedge_h = rnd.choice([1.0, 1.2, 1.2, 1.5, 1.8])
            hedge_k = 0 if rnd.random() < 0.72 else 2
            rc = list(g_r.exterior.coords)
            for (a, b_) in zip(rc[:-1], rc[1:]):
                if math.dist(a, b_) < 1.2:
                    continue
                front = abs(a[1] - lane_y) < 0.9 and abs(b_[1] - lane_y) < 0.9
                segs = [(a, b_)]
                if front and math.dist(a, b_) > 5.0:            # Pforte 1,2 m in der Mitte
                    m = ((a[0] + b_[0]) * 0.5, (a[1] + b_[1]) * 0.5)
                    dx, dy = (b_[0] - a[0]), (b_[1] - a[1])
                    dl = math.hypot(dx, dy)
                    dx, dy = dx / dl * 0.6, dy / dl * 0.6
                    segs = [(a, (m[0] - dx, m[1] - dy)), ((m[0] + dx, m[1] + dy), b_)]
                for s0, s1 in segs:
                    w0, w1 = back(Point(s0)), back(Point(s1))
                    k_ = (round((w0.x + w1.x) * 1.0), round((w0.y + w1.y) * 1.0))
                    if k_ in seen_edges:
                        continue
                    seen_edges.add(k_)
                    out["hedges"].append([round(w0.x, 2), round(w0.y, 2), round(w1.x, 2), round(w1.y, 2),
                                          0.95 if front else hedge_h, 1 if front else hedge_k])
            bx0, by0, bx1, by1 = g_r.bounds
            taken = []
            # --- Laube hinten in der Parzelle
            if not has_b:
                hw_, hd_ = rnd.choice([(3.0, 4.0), (3.5, 4.5), (4.0, 5.0), (4.0, 6.0), (3.0, 3.0)])
                hx = min(max(0.5 * (bx0 + bx1) + rnd.uniform(-2.5, 2.5), bx0 + hw_ * 0.5 + 1.2), bx1 - hw_ * 0.5 - 1.2)
                hy = (by1 - 2.0 - hd_ * 0.5) if sgn > 0 else (by0 + 2.0 + hd_ * 0.5)
                rect = box(hx - hw_ * 0.5, hy - hd_ * 0.5, hx + hw_ * 0.5, hy + hd_ * 0.5)
                if g_r.buffer(-0.6).contains(rect):
                    w = back(Point(hx, hy))
                    out["huts"].append([round(w.x, 2), round(w.y, 2), round(ground(w.x, w.y), 2), round(th + (0.0 if sgn > 0 else math.pi), 4),
                                        hw_, hd_, rnd.choice([2.2, 2.3, 2.5]), rnd.randrange(8), rnd.randrange(5),
                                        rnd.choice([0, 0, 0, 1, 1, 2])])
                    taken.append(rect.buffer(0.8))
                    if rnd.random() < 0.16:                     # Gewächshaus neben der Laube
                        gx = hx + (hw_ * 0.5 + 2.2) * rnd.choice([-1.0, 1.0])
                        gr = box(gx - 1.0, hy - 1.5, gx + 1.0, hy + 1.5)
                        if g_r.buffer(-0.6).contains(gr):
                            w = back(Point(gx, hy))
                            out["glass"].append([round(w.x, 2), round(w.y, 2), round(th, 4)])
                            taken.append(gr.buffer(0.5))
            # --- Beete im vorderen Teil, Reihen quer zum Weg
            nb = rnd.randrange(2, 6)
            bl = rnd.uniform(4.0, 7.5)
            side = rnd.choice([-1.0, 1.0])
            for j in range(nb):
                bxp = (bx0 + 2.0 + j * 1.9) if side < 0 else (bx1 - 2.0 - j * 1.9)
                byp = (lane_y + sgn * (2.2 + bl * 0.5))
                rect = box(bxp - 0.6, byp - bl * 0.5, bxp + 0.6, byp + bl * 0.5)
                if not g_r.buffer(-0.5).contains(rect) or any(t_.intersects(rect) for t_ in taken):
                    continue
                w = back(Point(bxp, byp))
                out["beds"].append([round(w.x, 2), round(w.y, 2), round(th + math.pi * 0.5, 4), 1.2, round(bl, 1),
                                    0 if rnd.random() < 0.7 else 1])
                taken.append(rect.buffer(0.3))
            # --- Obstbäume
            for _ in range(rnd.choice([0, 1, 1, 2, 2, 3])):
                for _try in range(6):
                    px, py = rnd.uniform(bx0 + 1.8, bx1 - 1.8), rnd.uniform(by0 + 1.8, by1 - 1.8)
                    pt = Point(px, py)
                    if g_r.buffer(-1.5).contains(pt) and not any(t_.buffer(1.2).contains(pt) for t_ in taken):
                        w = back(pt)
                        hh = rnd.uniform(3.2, 5.2)
                        trees.append([round(w.x, 1), round(w.y, 1), round(ground(w.x, w.y), 2), round(hh, 1), 0,
                                      round(hh * 0.8, 1), rnd.choice(["tree_small", "tree_small_b"]), "allot"])
                        taken.append(pt.buffer(1.6))
                        break
    if not dry:
        city["allotments"] = out
        city["trees"] = city["trees"] + trees
        cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    return nplots, len(out["huts"])


def main():
    dry = "--dry" in sys.argv
    names = [a.replace(",", "_") for a in sys.argv[1:] if not a.startswith("--")] or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    tp = th = 0
    for nm in names:
        r = tile_allotments(nm, dry)
        if r:
            tp += r[0]
            th += r[1]
            if r[0]:
                print(f"  {nm}: {r[0]} Parzellen, {r[1]} Lauben")
    print(f"Kleingärten: {tp} Parzellen, {th} eigene Lauben in {len(names)} Kacheln")


if __name__ == "__main__":
    main()
