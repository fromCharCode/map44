"""Nur lesende Prüfung: Brückenbauteile im Lichtraum (0,4–3,6 m über der Fahrbahn) befahrbarer Straßen ohne Brückenlage.

  python tools/check_under_bridges.py [E_N ...]      (ohne Argument: alle Kacheln; aus dem Projektordner starten)

Tastet Bögen, Kanzeln sowie Seiten- und Unterflächen aller Brückendecks ab und meldet je Straße und Bauteil die
Zahl der Treffer mit Lage und Höhenbereich. Deckunterseiten ab etwa 3,3 m sind nur niedrige Durchfahrten.
"""
import json, sys, math, glob
import numpy as np
from scipy.spatial import cKDTree
DRIVE = {"motorway","trunk","primary","secondary","tertiary","unclassified","residential","living_street","service",
         "motorway_link","trunk_link","primary_link","secondary_link","tertiary_link"}
def tri_pts(a, step=0.6):
    t = np.asarray(a, dtype=np.float64).reshape(-1, 3, 3)
    if len(t) == 0: return np.zeros((0, 3))
    out = []
    e = np.maximum(np.linalg.norm(t[:,1]-t[:,0],axis=1), np.linalg.norm(t[:,2]-t[:,0],axis=1))
    for n in (1, 2, 4, 8, 16, 40):
        lo = 0 if n == 1 else prev
        m = (e / step > lo) & ((e / step <= n) | (n == 40))
        prev = n
        if not m.any(): continue
        tt = t[m]
        for i in range(n + 1):
            for j in range(n + 1 - i):
                u, v = i / n, j / n
                out.append(tt[:,0] + (tt[:,1]-tt[:,0]) * u + (tt[:,2]-tt[:,0]) * v)
    return np.concatenate(out) if out else np.zeros((0, 3))
tot = []
for f in sorted(glob.glob("data/processed/tiles/*/city.json")):
    name = f.split("/")[-2]
    if len(sys.argv) > 1 and name not in sys.argv[1:]: continue
    c = json.load(open(f))
    ba = c.get("bridge_arches") or {}
    src = [("bogen", ba.get("tris") or []), ("kanzel", ba.get("kz_tris") or [])]
    for bm in c.get("bridge_meshes") or []:
        src.append(("deck:" + str(bm["id"]), (bm.get("side") or []) + (bm.get("bot") or [])))
    P, L = [], []
    for lab, a in src:
        p = tri_pts(a)
        if len(p): P.append(p); L += [lab] * len(p)
    if not P: continue
    P = np.concatenate(P); L = np.array(L)
    S, SY, SR = [], [], []
    for r in c.get("roads", []):
        if r.get("cls") not in DRIVE or r.get("bridge"): continue
        hw = max((float(r["width"]) - float(r.get("pl", 0)) - float(r.get("pr", 0))) * 0.5 - 0.3, 1.0)
        pts = r["pts"]
        for (x0, z0, y0), (x1, z1, y1) in zip(pts[:-1], pts[1:]):
            d = math.hypot(x1 - x0, z1 - z0)
            if d < 0.05: continue
            nx, nz = -(z1 - z0) / d, (x1 - x0) / d
            for k in range(int(d / 1.0) + 1):
                u = min(k * 1.0 / d, 1.0)
                for o in np.linspace(-hw, hw, max(3, int(hw * 2 / 0.8) + 1)):
                    S.append((x0 + (x1 - x0) * u + nx * o, z0 + (z1 - z0) * u + nz * o)); SY.append(y0 + (y1 - y0) * u)
                    SR.append((r["id"], r.get("name") or r["cls"]))
    if not S: continue
    S = np.array(S); SY = np.array(SY)
    tree = cKDTree(S)
    d, i = tree.query(P[:, [0, 2]], distance_upper_bound=0.45)
    ok = np.isfinite(d)
    idx = np.where(ok)[0]
    dy = P[idx, 1] - SY[i[idx]]
    bad = idx[(dy > 0.4) & (dy < 3.6)]
    hits = {}
    for b in bad:
        key = (SR[i[b]], L[b])
        h = hits.setdefault(key, [0, P[b], 9e9, -9e9])
        h[0] += 1; dyv = P[b, 1] - SY[i[b]]; h[2] = min(h[2], dyv); h[3] = max(h[3], dyv)
    for (rd, lab), h in sorted(hits.items(), key=lambda kv: -kv[1][0]):
        if h[0] >= 4:
            print(f"{name} {rd[1][:34]:34s} way {rd[0]} {lab[:26]:26s} n={h[0]:4d} bei ({h[1][0]:.0f},{h[1][2]:.0f}) dy {h[2]:.1f}..{h[3]:.1f}")
            tot.append(name)
print("Treffer:", len(tot), "in", len(set(tot)), "Kacheln")
