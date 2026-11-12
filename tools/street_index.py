"""Straßenindex für ganz Dresden: Name -> Punkt in Spielkoordinaten (Mitte des längsten Wegstücks).

Ausgabe: godot/data/streets.json  [[name, x, z], ...] alphabetisch (nur befahrbare Straßen mit Namen).
"""
import glob
import json

import numpy as np
from pyproj import Transformer

from config import ORIGIN_E, ORIGIN_N, RAW, ROOT

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
DRIVE = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service", "pedestrian"}

cands = {}   # name -> [(length, x, z)]
for f in glob.glob(str(RAW / "tiles" / "*" / "osm" / "roads.json")):
    for el in json.load(open(f))["elements"]:
        t = el.get("tags", {})
        name = t.get("name")
        if el["type"] != "way" or not name or t.get("highway") not in DRIVE or t.get("tunnel") == "yes":
            continue
        g = el["geometry"]
        if len(g) < 2:
            continue
        e, n = TO_UTM.transform([p["lon"] for p in g], [p["lat"] for p in g])
        c = np.column_stack([e, n])
        seg = np.hypot(*np.diff(c, axis=0).T)
        L = float(seg.sum())
        half = L / 2
        cum = np.concatenate([[0], np.cumsum(seg)])
        i = int(np.searchsorted(cum, half)) - 1
        i = min(max(i, 0), len(seg) - 1)
        u = (half - cum[i]) / max(seg[i], 1e-6)
        p = c[i] + (c[i + 1] - c[i]) * u
        cands.setdefault(name, []).append((L, float(p[0] - ORIGIN_E), float(-(p[1] - ORIGIN_N))))
rows = []
for name, lst in cands.items():
    lst.sort(reverse=True)
    kept = []
    for L, x, z in lst:
        if all((x - k[1]) ** 2 + (z - k[2]) ** 2 > 700.0 ** 2 for k in kept):
            kept.append((L, x, z))
    for L, x, z in kept[:4]:
        rows.append([name, round(x, 1), round(z, 1), round(((x - 494.0) ** 2 + (z - 12.0) ** 2) ** 0.5 / 1000.0, 1)])
out = sorted(rows, key=lambda r: (r[0].lower(), r[3]))
(ROOT / "godot" / "data" / "streets.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
print(len(out), "Straßen")
