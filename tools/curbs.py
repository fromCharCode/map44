"""Bordsteinkanten je Kachel (Nachbearbeitung, ohne Neubau): city["curbs"] = [[[x, z, y], ...], ...]

  python tools/curbs.py [E,N ...]      (ohne Argument: alle Kacheln)

Ein Bordstein liegt dort, wo die Fahrbahnfläche (befahrbare Straßen, Achse ± Breite/2) an Gehweg oder Platz grenzt
(Splat-Kanäle G/B, splat0.png). Die Linien sind so ausgerichtet, dass der Gehweg links der Laufrichtung liegt;
y = Fahrbahnhöhe an der Kante (Gelände, inkl. Straßenprofil). Godot (roads.gd) baut daraus die Granitkante.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from shapely.geometry import LineString, MultiLineString
from shapely.ops import linemerge, unary_union

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0
DRIVE = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
         "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}


def curbs_tile(name):
    d = TILES / name
    cf = d / "city.json"
    if not cf.exists():
        return 0
    city = json.loads(cf.read_text(encoding="utf-8"))
    e_km, n_km = (int(v) for v in name.split("_"))
    x0, z0 = e_km * 1000.0 - ORIGIN_E, -((n_km + 2) * 1000.0 - ORIGIN_N)      # NW-Ecke lokal
    s0 = np.asarray(Image.open(d / "splat0.png"))
    f = s0.shape[0] / 2000.0
    walk = np.maximum(s0[:, :, 1], s0[:, :, 2])
    ter = np.frombuffer((d / "terrain.f32").read_bytes(), dtype="<f4").reshape(2000, 2000)

    def walk_at(x, z):
        px, py = int((x - x0) * f), int((z - z0) * f)
        if 0 <= px < walk.shape[1] and 0 <= py < walk.shape[0]:
            return walk[py, px] > 110
        return False

    def h_at(x, z):
        c = min(max(x - x0 - 0.5, 0.0), 1998.999)
        r = min(max(z - z0 - 0.5, 0.0), 1998.999)
        c0, r0 = int(c), int(r)
        fc, fr = c - c0, r - r0
        top = ter[r0, c0] * (1 - fc) + ter[r0, c0 + 1] * fc
        bot = ter[r0 + 1, c0] * (1 - fc) + ter[r0 + 1, c0 + 1] * fc
        return float(top * (1 - fr) + bot * fr)

    # Kanten im Bodenraster zwischen Fahrbahn (R) und Gehweg/Platz (G/B): Pixelgrenzen, gerichtet so, dass der Gehweg
    # auf der Seite (−dz, dx) liegt; dann zu Linien verketten, vereinfachen und glätten (Treppenstufen weg)
    # Fahrbahnseite: alles außer Gehweg/Platz im Umkreis von 4 m einer Fahrbahn (OSM-Fahrbahnen decken die echte
    # Asphaltfläche oft nicht ganz ab; der Bordstein sitzt an der Gehwegkante)
    from scipy.ndimage import binary_dilation
    side = walk > 110
    # nur dort, wo Gehweg direkt (≤ 1 m) an Fahrbahn grenzt – nicht an Grün/Höfe
    road = binary_dilation(s0[:, :, 0] > 128, iterations=int(1 * f)) & ~side
    H, W = road.shape
    segs = {}

    def add(ax, ay, bx, by):
        segs.setdefault((ax, ay), []).append((bx, by))
    # waagrechte Nachbarn (x, x+1): senkrechte Kante bei x+1
    ys, xs = np.nonzero(road[:, :-1] & side[:, 1:])          # Fahrbahn links, Gehweg rechts
    for y, x in zip(ys.tolist(), xs.tolist()):
        add(x + 1, y + 1, x + 1, y)                            # nach Norden: Gehweg (+x) liegt auf (−dz, dx)
    ys, xs = np.nonzero(side[:, :-1] & road[:, 1:])          # Gehweg links, Fahrbahn rechts
    for y, x in zip(ys.tolist(), xs.tolist()):
        add(x + 1, y, x + 1, y + 1)
    ys, xs = np.nonzero(road[:-1, :] & side[1:, :])          # Fahrbahn oben (Norden), Gehweg unten
    for y, x in zip(ys.tolist(), xs.tolist()):
        add(x, y + 1, x + 1, y + 1)                            # nach Osten: (−dz, dx) = (0, +1) = Süden
    ys, xs = np.nonzero(side[:-1, :] & road[1:, :])
    for y, x in zip(ys.tolist(), xs.tolist()):
        add(x + 1, y + 1, x, y + 1)
    out = []
    while segs:
        start = next(iter(segs))
        line = [start]
        cur = start
        while cur in segs:
            nxt = segs[cur].pop()
            if not segs[cur]:
                del segs[cur]
            line.append(nxt)
            cur = nxt
            if cur == start:
                break
        if len(line) < 6:
            continue
        pts = [(x0 + px / f, z0 + py / f) for px, py in line]
        ls = LineString(pts).simplify(0.3)
        c = list(ls.coords)
        for _ in range(2):                                      # Chaikin-Glättung
            if len(c) < 3:
                break
            nc = [c[0]]
            for (ax, az), (bx, bz) in zip(c[:-1], c[1:]):
                nc.append((0.75 * ax + 0.25 * bx, 0.75 * az + 0.25 * bz))
                nc.append((0.25 * ax + 0.75 * bx, 0.25 * az + 0.75 * bz))
            nc.append(c[-1])
            c = nc
        lsc = LineString(c)
        if lsc.length < 3.0:
            continue
        c = list(lsc.simplify(0.03).coords)
        res_line = []
        for i, (x, z) in enumerate(c):
            j = min(i + 1, len(c) - 1)
            k = max(i - 1, 0)
            dx, dz = c[j][0] - c[k][0], c[j][1] - c[k][1]
            dl = (dx * dx + dz * dz) ** 0.5 or 1.0
            nx, nz = -dz / dl, dx / dl                           # Gehwegseite
            res_line.append((x, z, h_at(x - nx * 0.35, z - nz * 0.35), nx, nz))
        out.append(res_line)
    # Ausrichtung: Gehweg links der Laufrichtung; auf 5-cm-Toleranz vereinfachen
    res = []
    x1, z1 = x0 + 2000.0, z0 + 2000.0
    for c in out:
        pts = [[round(p[0], 2), round(p[1], 2), round(p[2], 3)] for p in c]
        pts = [p for p in pts if x0 <= p[0] < x1 and z0 <= p[1] < z1]
        if len(pts) >= 2:
            res.append(pts)
    city["curbs"] = res
    cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    return sum(len(c) for c in res)


_PT_CACHE = {}


def _pt(x, z):
    from shapely.geometry import Point
    return Point(x, z)


def main():
    names = [a.replace(",", "_") for a in sys.argv[1:]] or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    tot = 0
    for nm in names:
        tot += curbs_tile(nm)
    print(f"Bordsteine: {tot} Stützpunkte in {len(names)} Kacheln")


if __name__ == "__main__":
    main()
