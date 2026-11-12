"""Schutzgitter an Straßenbahn-Haltestelleninseln (Nachbearbeitung, ohne Neubau): city["stops"]["prails"]

  python tools/platform_rails.py [--dry] [E,N ...]      (ohne Argument: alle Kacheln)

Recherche (data/research/dvb_haltestellen.md, A4): Liegt hinter dem Bahnsteig eine Fahrbahn (Mittelinsel zwischen Gleis
und Fahrbahn, z. B. Albertplatz, Pirnaischer Platz), steht fahrbahnseitig ein Schutzgitter (anthrazit Rohrrahmen,
graue Füllplatte, ≈ 1,0 m; Modell stops/platform_rail.glb, 2,0-m-Raster). An den Inselenden bleibt der Zugang frei.
Liegt dahinter ein Gleis (Mittelbahnsteig) oder Gehweg (Kap), gibt es kein Gitter.
Ausgabe je Segment: [x, z, y, yaw]  (Modell-X entlang der Kante, yaw wie Basis(UP, yaw)).
"""
import json
import math
import sys
from pathlib import Path

from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
NO_DRIVE = {"footway", "path", "cycleway", "steps", "pedestrian", "track", "service", "platform", "bridleway",
            "living_street"}
SEG = 2.0           # Rasterlänge des Gitter-Segments (MANIFEST segment_length)
END_GAP = 1.6       # freier Zugang an den Inselenden
INSET = 0.12        # Abstand Gitterachse zur Bahnsteig-Rückkante


def _rails_for(plat, d_lines, d_tree, t_lines, t_tree):
    pts = plat["pts"]
    edge = plat.get("edge") or []
    n = len(edge)
    if plat.get("kind") != "tram" or n < 2 or len(pts) != 2 * n:
        return []
    back = [pts[2 * n - 1 - k] for k in range(n)]               # Rückseite, gleiche Reihenfolge wie die Kante
    # Rückseite außen: von der Kante zur Rückseite. Je Stützpunkt zählt eine Fahrbahn, wenn ihre Fläche hinter der
    # Rückkante liegt: Mittellinie dahinter mit Lücke < 3 m (Richtungsfahrbahn) oder Mittellinie auf Gleisseite, aber
    # Fläche reicht ≥ 2 m über die Rückkante hinaus (Insel in einer Straße mit gemeinsamer Achse). Gleis dahinter =
    # Mittelbahnsteig (kein Gitter).
    votes = 0
    tot = 0
    for k in range(n):
        ex, ez = pts[k][0], pts[k][1]
        bx, bz = back[k][0], back[k][1]
        ux, uz = bx - ex, bz - ez
        L = math.hypot(ux, uz) or 1.0
        ux, uz = ux / L, uz / L
        b = Point(bx, bz)
        tot += 1
        track_behind = False
        if t_tree is not None:
            for j in t_tree.query(b.buffer(4.5)):
                ln = t_lines[int(j)]
                if ln.distance(b) > 4.5:
                    continue
                c = ln.interpolate(ln.project(b))
                o = (c.x - bx) * ux + (c.y - bz) * uz
                if 0.0 < o < 4.0:
                    track_behind = True
                    break
        if track_behind or d_tree is None:
            continue
        for j in d_tree.query(b.buffer(25.0)):
            ln, hw = d_lines[int(j)]
            if ln.distance(b) > hw + 3.0:
                continue
            c = ln.interpolate(ln.project(b))
            o = (c.x - bx) * ux + (c.y - bz) * uz
            lat = abs((c.x - bx) * uz - (c.y - bz) * ux)       # Versatz längs der Kante: Querstraßen ausschließen
            if lat > 1.5:
                continue
            if (o > 0.0 and o - hw < 3.5) or (o <= 0.0 and o + hw > 2.0):
                votes += 1
                break
    if tot == 0 or votes < 0.6 * tot:
        return []
    # Gitter entlang der Rückseite, um INSET nach innen versetzt, Segmente im 2-m-Raster mit Zugang an den Enden
    inner = []
    for k in range(n):
        ex, ez = pts[k][0], pts[k][1]
        bx, bz, by = back[k]
        ux, uz = bx - ex, bz - ez
        L = math.hypot(ux, uz) or 1.0
        inner.append((bx - ux / L * INSET, bz - uz / L * INSET, by))
    ln = LineString([(x, z) for x, z, _y in inner])
    total = ln.length
    usable = total - 2 * END_GAP
    if usable < SEG:
        return []
    cnt = int(usable // SEG)
    s = (total - cnt * SEG) * 0.5 + SEG * 0.5
    out = []
    ys = [y for _x, _z, y in inner]
    cum = [0.0]
    for a, b in zip(inner[:-1], inner[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    for i in range(cnt):
        si = s + i * SEG
        p = ln.interpolate(si)
        p0 = ln.interpolate(max(si - 0.5, 0.0))
        p1 = ln.interpolate(min(si + 0.5, total))
        dx, dz = p1.x - p0.x, p1.y - p0.y
        yaw = math.atan2(-dz, dx)                              # Basis(UP, yaw): lokales X -> (cos, 0, −sin)
        # Höhe linear entlang der Rückseite
        y = ys[-1]
        for k in range(len(cum) - 1):
            if cum[k] <= si <= cum[k + 1]:
                t = (si - cum[k]) / max(cum[k + 1] - cum[k], 1e-6)
                y = ys[k] + (ys[k + 1] - ys[k]) * t
                break
        out.append([round(p.x, 2), round(p.y, 2), round(y, 3), round(yaw, 4)])
    return out


def rails_tile(name, dry=False):
    cf = TILES / name / "city.json"
    if not cf.exists():
        return 0, 0
    city = json.loads(cf.read_text(encoding="utf-8"))
    stops = city.get("stops") or {}
    plats = stops.get("platforms") or []
    if not plats:
        if "prails" in stops and not dry:
            del stops["prails"]
            cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
        return 0, 0
    d_lines = [(LineString([(p[0], p[1]) for p in r["pts"]]), float(r.get("width", 6.0)) * 0.5)
               for r in city.get("roads", []) if len(r["pts"]) >= 2 and r.get("cls") not in NO_DRIVE
               and not r.get("bridge") and not r.get("tunnel")]
    d_tree = STRtree([ln for ln, _ in d_lines]) if d_lines else None
    t_lines = [LineString([(p[0], p[1]) for p in r["pts"]]) for r in city.get("rails", [])
               if r.get("kind") == "tram" and len(r["pts"]) >= 2]
    t_tree = STRtree(t_lines) if t_lines else None
    res = []
    n_isl = 0
    for p in plats:
        segs = _rails_for(p, d_lines, d_tree, t_lines, t_tree)
        if segs:
            n_isl += 1
            res += segs
    if not dry:
        stops["prails"] = res
        city["stops"] = stops
        cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    return n_isl, len(res)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv
    names = [a.replace(",", "_") for a in args] or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    ti = ts = 0
    for nm in names:
        i, s = rails_tile(nm, dry)
        ti += i
        ts += s
        if i and len(names) <= 4:
            print(f"  {nm}: {i} Inseln, {s} Segmente")
    print(f"Bahnsteig-Schutzgitter: {ti} Inseln, {ts} Segmente in {len(names)} Kacheln" + (" (Probelauf)" if dry else ""))


if __name__ == "__main__":
    main()
