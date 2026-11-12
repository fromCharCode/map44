"""Gleicht Wasserstände der Elbe über alle Kacheln an (Ebene a + b*x + c*z), damit es an Kachelgrenzen keine Sprünge gibt.

Aufruf nach dem Bau aller Kacheln:  python fix_water.py
Schreibt in jedes city.json bei passenden Wasserflächen das Feld "plane": [a, b, c].
"""
import glob
import json

import numpy as np

from config import PROCESSED

files = sorted(glob.glob(str(PROCESSED / "tiles" / "*" / "city.json")))
rows = []
cities = {}
for f in files:
    c = json.load(open(f))
    cities[f] = c
    for i, w in enumerate(c["water"]):
        r = np.array(w["rings"][0])
        a = 0.5 * abs(np.dot(r[:, 0], np.roll(r[:, 1], 1)) - np.dot(r[:, 1], np.roll(r[:, 0], 1)))
        if a > 20000 and w["level"] < -5:
            rows.append((r[:, 0].mean(), r[:, 1].mean(), w["level"], a))
A = np.array(rows)
if len(A) < 3:
    raise SystemExit("zu wenig Elbe-Flächen")
X = np.column_stack([np.ones(len(A)), A[:, 0], A[:, 1]])
wgt = np.sqrt(A[:, 3])
coef, *_ = np.linalg.lstsq(X * wgt[:, None], A[:, 2] * wgt, rcond=None)
res = A[:, 2] - X @ coef
keep = np.abs(res) < 0.6
coef, *_ = np.linalg.lstsq((X * wgt[:, None])[keep], (A[:, 2] * wgt)[keep], rcond=None)
print("Ebene:", coef, "Rest-Streuung:", np.std((A[:, 2] - X @ coef)[keep]))
n = 0
for f, c in cities.items():
    ch = False
    for w in c["water"]:
        r = np.array(w["rings"][0])
        cx, cz = r[:, 0].mean(), r[:, 1].mean()
        pl = coef[0] + coef[1] * cx + coef[2] * cz
        if abs(w["level"] - pl) < 1.3 and w["level"] < -5:
            w["plane"] = [float(coef[1]), float(coef[2]), float(coef[0])]
            ch = True
            n += 1
    if ch:
        open(f, "w").write(json.dumps(c, separators=(",", ":")))
print(n, "Wasserflächen angepasst")
