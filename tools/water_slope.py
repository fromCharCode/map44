"""Flüsse mit Gefälle: Wasserspiegel je Uferpunkt statt eines einzigen Pegels (Nachbearbeitung, ohne Neubau).

  python tools/water_slope.py [E,N ...] [--dry]      (ohne Argument: alle Kacheln)

build_city.py gibt jeder Wasserfläche einen einzigen Pegel ("level"). Ein steiler Fluss ist aber oft EINE Fläche
(Weißeritz in Plauen: 1 km lang, Sohle fällt um fast 20 m). Mit einem Pegel lag das Wasser flussaufwärts unter dem
Bett und stand flussabwärts meterhoch über Ufer und Brückendecks.
Für solche Flächen kommt "ys" dazu: je Ringpunkt (Reihenfolge wie in "rings", alle Ringe hintereinander) die
Wasserhöhe = tiefster Geländepunkt im Umkreis von 10 m (das Geländemodell enthält den gemessenen Wasserspiegel)
+ 0,15 m, entlang des Flusses über 40 m geglättet. Das Spiel (water.gd) nimmt "ys", wenn vorhanden.
Nur Flächen ab 300 m² mit deutlichem Gefälle (mittlere 60 % der Uferpunkte ≥ 2,5 m auseinander); stehende
Gewässer bleiben eben.
Wiederholbar.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import minimum_filter
from scipy.spatial import cKDTree
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0


def tile_slope(name, dry=False):
    d = TILES / name
    cf = d / "city.json"
    if not cf.exists():
        return 0
    city = json.loads(cf.read_text(encoding="utf-8"))
    waters = city.get("water") or []
    if not waters:
        return 0
    e_km, n_km = (int(v) for v in name.split("_"))
    x0, z0 = e_km * 1000.0 - ORIGIN_E, -((n_km + 2) * 1000.0 - ORIGIN_N)
    ter = np.frombuffer((d / "terrain.f32").read_bytes(), dtype="<f4").reshape(2000, 2000)
    low = minimum_filter(ter, size=21, mode="nearest")          # tiefster Punkt im 10-m-Umkreis
    n = 0
    changed = False
    for w in waters:
        had = "ys" in w
        w.pop("ys", None)
        if "plane" in w or not w.get("rings"):
            changed |= had
            continue
        pts = [p for r in w["rings"] for p in r]
        try:
            area = Polygon([(p[0], p[1]) for p in w["rings"][0]]).area
        except Exception:
            area = 0.0
        if area < 300.0 or len(pts) < 8:
            changed |= had
            continue
        xy = np.array([(p[0], p[1]) for p in pts], dtype=float)
        col = np.clip(np.round(xy[:, 0] - x0 - 0.5), 0, 1999).astype(int)
        row = np.clip(np.round(xy[:, 1] - z0 - 0.5), 0, 1999).astype(int)
        inside = (xy[:, 0] >= x0) & (xy[:, 0] < x0 + 2000.0) & (xy[:, 1] >= z0) & (xy[:, 1] < z0 + 2000.0)
        raw = low[row, col].astype(float) + 0.15
        if inside.sum() < 8:
            changed |= had
            continue
        tree = cKDTree(xy[inside])
        src = raw[inside]
        ys = np.empty(len(pts))
        for i, q in enumerate(xy):
            idx = tree.query_ball_point(q, 40.0)
            if not idx:
                idx = [int(tree.query(q)[1])]
            ys[i] = float(np.median(src[idx]))
        # nur deutliches Gefälle: mittlere 60 % der Uferpunkte liegen um mindestens 2,5 m auseinander (einzelne
        # hohe Uferpunkte eines ebenen Gewässers zählen so nicht)
        if float(np.percentile(raw[inside], 80) - np.percentile(raw[inside], 20)) < 2.5:
            changed |= had
            continue
        w["ys"] = [round(float(v), 2) for v in ys]
        n += 1
        changed = True
    if changed and not dry:
        cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    if n:
        print(f"  {name}: {n} Wasserflächen mit Gefälle", flush=True)
    return n


def main():
    dry = "--dry" in sys.argv
    args = [a.replace(",", "_") for a in sys.argv[1:] if not a.startswith("--")]
    names = args or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    tot = sum(tile_slope(nm, dry) for nm in names)
    print(f"Flüsse mit Gefälle: {tot} Wasserflächen in {len(names)} Kacheln" + (" (nur gezählt)" if dry else ""))


if __name__ == "__main__":
    main()
