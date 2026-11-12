"""Buslinien aus OSM (Relationen route=bus/trolleybus, PTv2) für die Verkehrssimulation.

Ausgabe: godot/data/bus_routes.json (mit --tram: Straßenbahnlinien route=tram -> godot/data/tram_routes.json)
  {"routes": [{"ref": "62", "name": "...", "from": "...", "to": "...", "colour": "#...",
               "pts": [[x, z], ...],                  # Linienweg in Fahrtrichtung (lokal, ~1 m vereinfacht)
               "stops": [[s, x, z, "Name"], ...]}]}   # Haltestellen, s = Bogenlänge entlang pts
Quelle: (c) OpenStreetMap-Mitwirkende, ODbL (Geofabrik-Extrakt sachsen.osm.pbf).
"""
import json
import math
import sys
import time

import osmium
from pyproj import Transformer
from shapely.geometry import LineString, Point

from config import ORIGIN_E, ORIGIN_N, RAW

PBF = RAW / "geofabrik" / "sachsen.osm.pbf"
TRAM = "--tram" in sys.argv
OUT = RAW.parent.parent / "godot" / "data" / ("tram_routes.json" if TRAM else "bus_routes.json")
ROUTES = ("tram",) if TRAM else ("bus", "trolleybus")
TILES = [tuple(int(v) for v in l.split(",")) for l in (RAW / "tile_order.txt").read_text().split() if l]
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)


def local(lon, lat):
    e, n = TO_UTM.transform(lon, lat)
    return (e - ORIGIN_E, -(n - ORIGIN_N))


def main():
    t0 = time.time()
    e0 = min(e for e, n in TILES) * 1000.0
    e1 = (max(e for e, n in TILES) + 2) * 1000.0
    n0 = min(n for e, n in TILES) * 1000.0
    n1 = (max(n for e, n in TILES) + 2) * 1000.0
    x0, x1 = e0 - ORIGIN_E, e1 - ORIGIN_E
    z0, z1 = -(n1 - ORIGIN_N), -(n0 - ORIGIN_N)

    # Pass 1: Relationen
    rels = []
    way_ids, node_ids = set(), set()
    for o in osmium.FileProcessor(str(PBF), osmium.osm.RELATION):
        t = {x.k: x.v for x in o.tags}
        if t.get("type") != "route" or t.get("route") not in ROUTES:
            continue
        ways, stops = [], []
        for m in o.members:
            role = m.role or ""
            if m.type == "w" and not role.startswith("platform"):
                ways.append(m.ref)
                way_ids.add(m.ref)
            elif m.type == "n" and role.startswith("stop"):
                stops.append(("n", m.ref))
                node_ids.add(m.ref)
            elif m.type == "n" and role.startswith("platform"):
                stops.append(("p", m.ref))
                node_ids.add(m.ref)
        if len(ways) >= 2:
            rels.append({"id": o.id, "tags": t, "ways": ways, "stops": stops})
    print(f"{len(rels)} Relationen {ROUTES} ({time.time() - t0:.0f} s)", flush=True)

    # Pass 2: Geometrien
    way_geom, node_pos, node_name = {}, {}, {}
    fp = osmium.FileProcessor(str(PBF), osmium.osm.NODE | osmium.osm.WAY).with_locations()
    for o in fp:
        if o.is_node():
            if o.id in node_ids:
                node_pos[o.id] = local(o.location.lon, o.location.lat)
                node_name[o.id] = o.tags.get("name", "")
            continue
        if o.id in way_ids:
            try:
                way_geom[o.id] = [local(n.lon, n.lat) for n in o.nodes if n.location.valid()]
            except osmium.InvalidLocationError:
                pass
    print(f"Geometrien ({time.time() - t0:.0f} s)", flush=True)

    out = []
    for r in rels:
        segs = [way_geom[w] for w in r["ways"] if w in way_geom and len(way_geom[w]) >= 2]
        if len(segs) < max(2, int(len(r["ways"]) * 0.8)):
            continue
        # Wege in Reihenfolge verketten (Richtung je Weg am Anschluss bestimmen)
        first, second = segs[0], segs[1]
        ends2 = (second[0], second[-1])
        d_fwd = min(math.dist(first[-1], p) for p in ends2)
        d_rev = min(math.dist(first[0], p) for p in ends2)
        line = list(first if d_fwd <= d_rev else first[::-1])
        gaps = 0
        for sg in segs[1:]:
            end = line[-1]
            if math.dist(end, sg[0]) <= math.dist(end, sg[-1]):
                nxt = sg
            else:
                nxt = sg[::-1]
            if math.dist(end, nxt[0]) > 5.0:
                gaps += 1
            line.extend(nxt[1:] if math.dist(end, nxt[0]) < 0.5 else nxt)
        if gaps > 3:
            continue
        ls = LineString(line).simplify(0.8)
        pts = [(round(x, 1), round(z, 1)) for x, z in ls.coords]
        # nur Linien, die das Spielgebiet berühren
        if not any(x0 <= x <= x1 and z0 <= z <= z1 for x, z in pts):
            continue
        ls = LineString(pts)
        # Haltestellen: stop-Knoten bevorzugt, sonst Bahnsteig-Knoten; Bogenlänge monoton
        st = [sid for kind, sid in r["stops"] if kind == "n" and sid in node_pos]
        if not st:
            st = [sid for kind, sid in r["stops"] if kind == "p" and sid in node_pos]
        stops = []
        last_s = -1.0
        for sid in st:
            p = Point(node_pos[sid])
            if ls.distance(p) > 25.0:
                continue
            s = ls.project(p)
            if s < last_s - 5.0:
                # Linie läuft über dieselbe Stelle mehrfach: in Fahrtrichtung weitersuchen
                sub_s = last_s
                best = None
                for k in range(1, 60):
                    q = ls.interpolate(min(sub_s + k * 10.0, ls.length))
                    d = q.distance(p)
                    if best is None or d < best[0]:
                        best = (d, sub_s + k * 10.0)
                if best and best[0] < 25.0:
                    s = best[1]
                else:
                    continue
            last_s = s
            q = ls.interpolate(s)
            stops.append([round(s, 1), round(q.x, 1), round(q.y, 1), (node_name.get(sid) or "")[:32]])
        t = r["tags"]
        out.append({"id": r["id"], "ref": t.get("ref", ""), "name": t.get("name", ""), "from": t.get("from", ""),
                    "to": t.get("to", ""), "colour": t.get("colour", ""), "operator": t.get("operator", ""),
                    "pts": [list(p) for p in pts], "stops": stops, "len": round(ls.length, 1)})
    OUT.write_text(json.dumps({"routes": out, "attribution": "(c) OpenStreetMap-Mitwirkende, ODbL"},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(out)} Linien mit {sum(len(r['stops']) for r in out)} Halten -> {OUT} "
          f"({OUT.stat().st_size / 1e6:.1f} MB, {time.time() - t0:.0f} s)", flush=True)


if __name__ == "__main__":
    main()
