"""Bahnbrücken ohne Deck: Plattenbrücke unter das Gleis legen (Nachbearbeitung, ohne Neubau der Kachel).

  python tools/rail_slabs.py [E,N ...] [--dry]      (ohne Argument: alle Kacheln)

Gleise mit bridge=yes bekommen ihr Deck sonst aus den LoD2-Brückenteilen (city["bridge_meshes"]) oder aus den
Steinbögen (city["bridge_arches"]). Fehlt beides, hingen Schienen und Fahrdraht frei über Fluss oder Straße.
Für solche Abschnitte kommt ein Eintrag {"id", "kind": "rail", "width", "pts"} nach city["bridges"]; das Spiel
(roads.gd, _bridge) baut daraus eine Platte mit Schotterbett, Betonstirn und Geländer.
Nur wo das Gelände mehr als 1,2 m unter dem Gleis liegt (sonst liegt das Gleis ohnehin auf dem Boden).
Wiederholbar: vorhandene "rail"-Einträge werden ersetzt.
"""
import json
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0
WIDTH = {"tram": 4.2}          # Eisenbahn: 5,0 m


def tile_slabs(name, dry=False):
    d = TILES / name
    cf = d / "city.json"
    if not cf.exists():
        return 0
    city = json.loads(cf.read_text(encoding="utf-8"))
    old = [b for b in city.get("bridges", []) if b.get("kind") == "rail"]
    rails = [r for r in city.get("rails", []) if r.get("bridge") and len(r.get("pts", [])) >= 2]
    if not rails and not old:
        return 0
    e_km, n_km = (int(v) for v in name.split("_"))
    x0, z0 = e_km * 1000.0 - ORIGIN_E, -((n_km + 2) * 1000.0 - ORIGIN_N)
    ter = np.frombuffer((d / "terrain.f32").read_bytes(), dtype="<f4").reshape(2000, 2000)

    def h_at(x, z):
        c = int(round(min(max(x - x0 - 0.5, 0.0), 1999.0)))
        r = int(round(min(max(z - z0 - 0.5, 0.0), 1999.0)))
        return float(ter[r, c])

    polys = []
    for bm in city.get("bridge_meshes") or []:
        v = bm.get("top0") or bm.get("bot") or []
        for tri in np.array(v, dtype=float).reshape(-1, 3, 3):
            p = Polygon([(tri[0][0], tri[0][2]), (tri[1][0], tri[1][2]), (tri[2][0], tri[2][2])])
            if p.is_valid and p.area > 0.01:
                polys.append(p)
    tree = STRtree(polys) if polys else None
    at = np.array((city.get("bridge_arches") or {}).get("tris") or [], dtype=float).reshape(-1, 3)
    # Straßenbrücken (Platten): Straßenbahn auf einer Straßenbrücke hat ihr Deck schon
    slabs = [(LineString([(p[0], p[1]) for p in b["pts"]]), float(b.get("width", 4.0)) * 0.5 + 1.0)
             for b in city.get("bridges", []) if b.get("kind") != "rail" and len(b.get("pts", [])) >= 2]
    new = []
    for r in rails:
        pts = r["pts"]
        ln = LineString([(p[0], p[1]) for p in pts])
        if ln.length < 3.0:
            continue
        n = max(2, int(ln.length / 3.0))
        cov, gap = 0, 0.0
        for k in range(n):
            s = (k + 0.5) / n
            q = ln.interpolate(s, normalized=True)
            ok = False
            if tree is not None:
                for i in tree.query(q.buffer(0.5)):
                    if polys[int(i)].distance(q) < 0.5:
                        ok = True
                        break
            if not ok and len(at) and float(np.min(np.hypot(at[:, 0] - q.x, at[:, 2] - q.y))) < 3.0:
                ok = True
            if not ok and any(sl.distance(q) < hw for sl, hw in slabs):
                ok = True
            cov += ok
            # Gleishöhe linear entlang der Punkte
            y = pts[0][2] + (pts[-1][2] - pts[0][2]) * s
            if x0 <= q.x < x0 + 2000.0 and z0 <= q.y < z0 + 2000.0:
                gap = max(gap, y - h_at(q.x, q.y))
        if cov / n >= 0.6 or gap < 1.2:
            continue
        new.append({"id": r["id"], "kind": "rail", "width": WIDTH.get(r.get("kind"), 5.0),
                    "pts": [[round(p[0], 2), round(p[1], 2), round(p[2], 2)] for p in pts]})
    if not dry and (new or old):
        city["bridges"] = [b for b in city.get("bridges", []) if b.get("kind") != "rail"] + new
        cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    if new:
        print(f"  {name}: {len(new)} Gleisabschnitte mit Platte", flush=True)
    return len(new)


def main():
    dry = "--dry" in sys.argv
    args = [a.replace(",", "_") for a in sys.argv[1:] if not a.startswith("--")]
    names = args or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    tot = sum(tile_slabs(nm, dry) for nm in names)
    print(f"Bahnbrücken ohne Deck: {tot} Platten in {len(names)} Kacheln" + (" (nur gezählt)" if dry else ""))


if __name__ == "__main__":
    main()
