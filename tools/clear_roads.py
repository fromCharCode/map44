"""Fahrbahnen freiräumen (Nachbearbeitung, letzter Schritt): Bäume, Laternen, Stadtmöbel, Schilder und Denkmäler,
die auf einer Fahrbahn stehen, werden entfernt; Bäume werden an den Fahrbahnrand gerückt.

  python tools/clear_roads.py [E,N ...] [--dry]

Ursachen solcher Fehlstellungen: Laserscan-Bäume, deren Krone über die Straße ragt (Stamm wird in der Kronenmitte
angenommen), ungenaue OSM-Punkte, Objekte an Kreuzungen. Fahrbahn = Achse ± halbe Breite der befahrbaren Straßen
(ohne Fuß-/Radwege); Brücken und Tunnel zählen mit. Gehwege bleiben unberührt. Wiederholbar.
"""
import json
import sys
from pathlib import Path

from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
NO_DRIVE = {"footway", "path", "cycleway", "steps", "pedestrian", "track", "bridleway", "corridor", "platform"}
# Modelle, die absichtlich auf/an der Fahrbahn stehen
KEEP_FURN = {"traffic_cone", "construction_fence", "bus_stop", "stop_pole"}


def tile_clear(name, dry=False):
    cf = TILES / name / "city.json"
    if not cf.exists():
        return {}
    city = json.loads(cf.read_text(encoding="utf-8"))
    lines, half = [], []
    for r in city.get("roads", []):
        if r.get("cls") in NO_DRIVE or r.get("nomv") or len(r.get("pts", [])) < 2:
            continue
        lines.append(LineString([p[:2] for p in r["pts"]]))
        half.append(max(float(r.get("width") or 5.0), 3.0) * 0.5)
    if not lines:
        return {}
    tree = STRtree(lines)

    def on_road(x, z, margin):
        pt = Point(x, z)
        for j in tree.query(pt.buffer(12.0)):
            if lines[j].distance(pt) < half[j] + margin:
                return True
        return False

    n = {}

    def keep(key, items, xz, margin, cond=lambda o: True):
        if not items:
            return items
        out = [o for o in items if not (cond(o) and on_road(*xz(o), margin))]
        if len(out) != len(items):
            n[key] = n.get(key, 0) + len(items) - len(out)
        return out

    # Bäume: Stamm (Radius ~0,3 m) muss neben der Fahrbahn stehen; −0,2 m Spielraum, weil Straßenbäume oft im
    # Parkstreifen stehen, der zur erfassten Breite zählt
    # Sie werden an den Fahrbahnrand gerückt (Alleen bleiben erhalten) und nur gelöscht, wenn auch dort Fahrbahn ist.
    trees, moved, gone = [], 0, 0
    for t in city.get("trees", []):
        pt = Point(t[0], t[1])
        hit = None
        for j in tree.query(pt.buffer(12.0)):
            d = lines[j].distance(pt)
            if d < half[j] - 0.2 and (hit is None or d < hit[0]):
                hit = (d, j)
        if hit is None:
            trees.append(t)
            continue
        j = hit[1]
        q = lines[j].interpolate(lines[j].project(pt))
        dx, dz = pt.x - q.x, pt.y - q.y
        ln = (dx * dx + dz * dz) ** 0.5
        if ln < 0.05:                                    # genau auf der Achse: quer zur Fahrtrichtung
            s_ = lines[j].project(pt)
            a_, b_ = lines[j].interpolate(max(s_ - 1.0, 0.0)), lines[j].interpolate(min(s_ + 1.0, lines[j].length))
            dx, dz, ln = -(b_.y - a_.y), b_.x - a_.x, max(((b_.x - a_.x) ** 2 + (b_.y - a_.y) ** 2) ** 0.5, 1e-6)
        nx, nz = q.x + dx / ln * (half[j] + 0.9), q.y + dz / ln * (half[j] + 0.9)
        if on_road(nx, nz, 0.3):
            gone += 1
            continue
        t = list(t)
        t[0], t[1] = round(nx, 2), round(nz, 2)
        trees.append(t)
        moved += 1
    if moved or gone:
        n["Bäume an den Rand"] = moved
        if gone:
            n["Bäume entfernt"] = gone
        city["trees"] = trees
    city["lamps"] = keep("Laternen", city.get("lamps", []), lambda o: (o[0], o[1]), -0.1)
    life = city.get("life", {})
    life["furniture"] = keep("Möbel", life.get("furniture", []), lambda o: (o[1], o[2]), -0.1,
                             lambda o: o[0] not in KEEP_FURN)
    life["signs"] = keep("Schilder", life.get("signs", []), lambda o: (o[2], o[3]), -0.25)
    if life.get("monuments"):
        # Abstand nach Größe des Modells: ein Brunnenbecken (Ø 6 m) ragte sonst in die Fahrbahn
        rad = {"mon_fountain": 3.3, "mon_reiter": 2.3, "mon_reiter_gold": 2.3, "mon_obelisk": 1.7, "mon_war": 1.8}
        for model in sorted({o[0] for o in life["monuments"]}):
            r_ = rad.get(model, 1.1) * 1.0
            life["monuments"] = keep("Denkmäler", life["monuments"], lambda o: (o[1], o[2]), r_,
                                     lambda o, m=model: o[0] == m)
    city["props"] = keep("Kleinobjekte", city.get("props", []), lambda o: (o[0], o[1]), -0.1)
    # Mauern, Zäune und Stützmauern, die quer über eine Fahrbahn laufen: dort unterbrechen (Einfahrten, Lagefehler)
    from shapely.ops import unary_union
    road_area = unary_union([ln.buffer(h + 0.25, cap_style=2) for ln, h in zip(lines, half)])
    bars, cut = [], 0
    for b in city.get("barriers", []):
        pts = b.get("pts") or []
        if b.get("bridge") or len(pts) < 2:
            bars.append(b)
            continue
        ln = LineString([p[:2] for p in pts])
        if not ln.intersects(road_area):
            bars.append(b)
            continue
        rest = ln.difference(road_area)
        parts = [g for g in getattr(rest, "geoms", [rest]) if g.geom_type == "LineString" and g.length >= 0.8]
        cut += 1
        for g in parts:
            nb = dict(b)
            nb["pts"] = [[round(x, 2), round(z, 2)] for x, z in g.coords]
            bars.append(nb)
    if cut:
        n["Mauern/Zäune unterbrochen"] = cut
        city["barriers"] = bars
    if n and not dry:
        cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    if n:
        print(f"  {name}: " + ", ".join(f"{v} {k}" for k, v in n.items()), flush=True)
    return n


def main():
    dry = "--dry" in sys.argv
    args = [a.replace(",", "_") for a in sys.argv[1:] if not a.startswith("--")]
    names = args or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    tot = {}
    for nm in names:
        for k, v in tile_clear(nm, dry).items():
            tot[k] = tot.get(k, 0) + v
    print("gesamt:", tot, "(nur gezählt)" if dry else "")


if __name__ == "__main__":
    main()
