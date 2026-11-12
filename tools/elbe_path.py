"""Elbe-Mittellinie für Schiffe: kettet OSM-Wege waterway=river/name=Elbe aus allen Kacheln zu einer Linie.

Ausgabe: godot/data/elbe.json  {"pts": [[x, z], ...]} in Spielkoordinaten, West -> Ost.
"""
import glob
import json

import numpy as np
from pyproj import Transformer

from config import ORIGIN_E, ORIGIN_N, RAW, ROOT

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
ways = {}
for f in glob.glob(str(RAW / "tiles" / "*" / "osm" / "water.json")):
    for el in json.load(open(f))["elements"]:
        t = el.get("tags", {})
        if el["type"] == "way" and t.get("waterway") == "river" and t.get("name") == "Elbe":
            g = el["geometry"]
            e, n = TO_UTM.transform([p["lon"] for p in g], [p["lat"] for p in g])
            e, n = np.array(e), np.array(n)
            ways[el["id"]] = np.column_stack([e - ORIGIN_E, -(n - ORIGIN_N)])
print(len(ways), "Elbe-Wegstücke")
# Ketten über Endpunkte
def key(p):
    return (round(p[0] / 2.0), round(p[1] / 2.0))
ends = {}
for wid, c in ways.items():
    for e in (0, -1):
        ends.setdefault(key(c[e]), []).append(wid)
start = None
for wid, c in ways.items():
    for e in (0, -1):
        if len(ends[key(c[e])]) == 1:
            if start is None or c[e][0] < start[1][0]:
                start = (wid, c[e], e)
used = set()
line = []
wid, _, e = start
cur = ways[wid] if e == 0 else ways[wid][::-1]
while True:
    used.add(wid)
    line += [list(map(float, p)) for p in cur]
    nxt = [w for w in ends.get(key(cur[-1]), []) if w not in used]
    if not nxt:
        break
    wid = nxt[0]
    c = ways[wid]
    cur = c if key(c[0]) == key(line[-1]) else c[::-1]
print(len(used), "von", len(ways), "verkettet;", len(line), "Punkte; x von", round(line[0][0]), "bis", round(line[-1][0]))
(ROOT / "godot" / "data" / "elbe.json").write_text(json.dumps({"pts": [[round(p[0], 1), round(p[1], 1)] for p in line]}), encoding="utf-8")
