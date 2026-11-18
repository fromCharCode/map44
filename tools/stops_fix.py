"""Haltestellen von der Fahrbahn holen (Nachbearbeitung, ohne Neubau der Kachel).

  python tools/stops_fix.py [E,N ...]      (ohne Argument: alle Kacheln)

Prüft jedes Haltestellen-Objekt gegen die Fahrbahnen (Kfz-Straßen, Breite ohne Parkstreifen) und Gleise der Kachel:
  * Masten, Wartehallen, Anzeiger, Papierkörbe, Geländer und die Haltestellen-Möbel des Straßenlebens, die in einem
    Fahrband oder im Gleisbereich stehen, rücken quer zur Straße auf die Seite, auf der sie schon stehen, bis sie
    0,5 m neben dem Rand sind. Wäre dort die nächste Fahrbahn, wird die andere Seite versucht; geht beides nicht,
    entfällt das Objekt.
  * Bahnsteige, die zu mehr als 30 % in einer Kfz-Fahrbahn liegen, entfallen: Das sind in Dresden Haltestellen, an
    denen man von der Fahrbahn oder einem überfahrbaren Kap einsteigt – ein erhöhter Bahnsteig versperrte dort die Spur.
    Bahnsteige mit kleinerem Überstand bleiben.
Wiederholbar (ein zweiter Lauf ändert nichts mehr).
"""
import json
import math
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
DRIVE = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
         "service", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}
GAP = 0.5


def fix_tile(name):
    cf = TILES / name / "city.json"
    if not cf.exists():
        return None
    city = json.loads(cf.read_text(encoding="utf-8"))
    stops = city.get("stops") or {}
    furn = (city.get("life") or {}).get("furniture") or []
    if not stops and not furn:
        return None
    lines, half, drive = [], [], []
    for r in city.get("roads", []):
        if r.get("cls") in DRIVE and len(r["pts"]) >= 2:
            ln = LineString([(p[0], p[1]) for p in r["pts"]])
            if ln.length > 0.5:
                lines.append(ln)
                half.append(max((float(r["width"]) - float(r.get("pl", 0.0)) - float(r.get("pr", 0.0))) * 0.5, 1.2))
                drive.append(True)
    for r in city.get("rails", []):
        if len(r["pts"]) >= 2:
            ln = LineString([(p[0], p[1]) for p in r["pts"]])
            if ln.length > 0.5:
                lines.append(ln)
                half.append(1.25 if r.get("kind") == "tram" else 1.7)
                drive.append(False)
    if not lines:
        return None
    tree = STRtree(lines)

    def worst(x, z, rad):
        """(Eindringtiefe > 0, Index) des Bandes, in dem der Punkt am tiefsten steckt – oder None"""
        p = Point(x, z)
        best = None
        for i in tree.query(p.buffer(14.0)):
            i = int(i)
            dep = half[i] + rad - lines[i].distance(p)
            if dep > 0.15 and (best is None or dep > best[0]):
                best = (dep, i)
        return best

    def moved(x, z, rad):
        """neue Lage neben der Fahrbahn oder None (kein Platz); unverändert, wenn nichts zu tun ist"""
        w = worst(x, z, rad)
        if w is None:
            return x, z, False
        i = w[1]
        ln = lines[i]
        s = ln.project(Point(x, z))
        a, b = ln.interpolate(max(s - 1.0, 0.0)), ln.interpolate(min(s + 1.0, ln.length))
        c = ln.interpolate(s)
        tl = math.hypot(b.x - a.x, b.y - a.y) or 1.0
        nx, nz = -(b.y - a.y) / tl, (b.x - a.x) / tl
        side = 1.0 if (x - c.x) * nx + (z - c.y) * nz >= 0.0 else -1.0
        for sd in (side, -side):
            for extra in (0.0, 1.0, 2.5):
                d = half[i] + rad + GAP + extra
                qx, qz = c.x + nx * d * sd, c.y + nz * d * sd
                if worst(qx, qz, rad) is None:
                    return qx, qz, True
        return None

    st = {"moved": 0, "dropped": 0, "platforms": 0}

    def fix_list(lst, ix, iz, rad):
        keep = []
        for it in lst:
            r = moved(float(it[ix]), float(it[iz]), rad)
            if r is None:
                st["dropped"] += 1
                continue
            if r[2]:
                it[ix], it[iz] = round(r[0], 2), round(r[1], 2)
                st["moved"] += 1
            keep.append(it)
        return keep

    if stops:
        stops["masts"] = fix_list(stops.get("masts", []), 0, 1, 0.15)
        stops["shelters"] = fix_list(stops.get("shelters", []), 1, 2, 0.9)
        stops["dfis"] = fix_list(stops.get("dfis", []), 1, 2, 0.25)
        stops["bins"] = fix_list(stops.get("bins", []), 0, 1, 0.25)
        keep = []
        for pf in stops.get("platforms", []):
            pg = Polygon([(p[0], p[1]) for p in pf["pts"]])
            if not pg.is_valid:
                pg = pg.buffer(0)
            bands = [lines[int(i)].buffer(half[int(i)] - 0.2, cap_style="flat") for i in tree.query(pg) if drive[int(i)]]
            ov = pg.intersection(unary_union(bands)).area if bands else 0.0
            if pg.area > 0.5 and ov > 0.3 * pg.area:
                st["platforms"] += 1
                continue
            if ov > 1.0:
                # Teilüberstand: Bahnsteig an der Fahrbahnkante abschneiden (größtes Reststück), sonst entfällt er
                wide = unary_union([lines[int(i)].buffer(half[int(i)] + 0.05, cap_style="flat") for i in tree.query(pg) if drive[int(i)]])
                rest = pg.difference(wide)
                parts = [g for g in getattr(rest, "geoms", [rest]) if g.geom_type == "Polygon" and g.area > 4.0]
                if not parts:
                    st["platforms"] += 1
                    continue
                g = max(parts, key=lambda q: q.area).simplify(0.05)
                if g.area < 0.4 * pg.area or g.geom_type != "Polygon":
                    st["platforms"] += 1
                    continue
                old_pts = pf["pts"]
                ring = list(g.exterior.coords)[:-1]
                if Polygon(ring).exterior.is_ccw is False:
                    ring = ring[::-1]

                def y_of(x, z):
                    q = min(old_pts, key=lambda o: (o[0] - x) ** 2 + (o[1] - z) ** 2)
                    return q[2]
                new_pts = [[round(x, 2), round(z, 2), y_of(x, z)] for x, z in ring]
                tris = []
                import shapely
                gp = Polygon([(q[0], q[1]) for q in new_pts])
                try:
                    tri_list = list(shapely.constrained_delaunay_triangles(gp.buffer(0)).geoms)
                except Exception:
                    tri_list = []
                if not tri_list:
                    st["platforms"] += 1
                    continue
                for tr in tri_list:
                    idx = []
                    for cx, cz in list(tr.exterior.coords)[:3]:
                        j = min(range(len(new_pts)), key=lambda k: (new_pts[k][0] - cx) ** 2 + (new_pts[k][1] - cz) ** 2)
                        idx.append(j)
                    if len(set(idx)) == 3:
                        tris += idx
                old_edge = pf.get("edge") or []
                if len(old_edge) >= 2:
                    el = LineString([(old_pts[i][0], old_pts[i][1]) for i in old_edge])
                    ne = [k for k, q in enumerate(new_pts) if el.distance(Point(q[0], q[1])) < 0.3]
                    pf["edge"] = ne if len(ne) >= 2 else []
                pf["pts"], pf["tris"] = new_pts, tris
                st["trimmed"] = st.get("trimmed", 0) + 1
            keep.append(pf)
        stops["platforms"] = keep
        # Geländer hinter entfallenen Bahnsteigen stehen dann frei – nur behalten, wenn sie nicht in der Fahrbahn sind
        if stops.get("prails"):
            stops["prails"] = [r for r in stops["prails"] if worst(float(r[0]), float(r[1]), 0.1) is None]
    if furn:
        keep = []
        for fu in furn:
            if fu[0] in ("bus_stop", "stop_pole"):
                r = moved(float(fu[1]), float(fu[2]), 0.9 if fu[0] == "bus_stop" else 0.15)
                if r is None:
                    st["dropped"] += 1
                    continue
                if r[2]:
                    fu[1], fu[2] = round(r[0], 2), round(r[1], 2)
                    st["moved"] += 1
            keep.append(fu)
        city["life"]["furniture"] = keep
    if st["moved"] or st["dropped"] or st["platforms"] or st.get("trimmed"):
        cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    return st


def main():
    names = [a.replace(",", "_") for a in sys.argv[1:]] or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    tot = {"moved": 0, "dropped": 0, "platforms": 0, "trimmed": 0}
    for nm in names:
        st = fix_tile(nm)
        for k, v in (st or {}).items():
            tot[k] = tot.get(k, 0) + v
    print(f"Haltestellen: {tot['moved']} Objekte neben die Fahrbahn gerückt, {tot['dropped']} ohne Platz entfernt, "
          f"{tot['platforms']} Bahnsteige in der Fahrbahn entfernt, {tot['trimmed']} an der Fahrbahnkante beschnitten ({len(names)} Kacheln)")


if __name__ == "__main__":
    main()
