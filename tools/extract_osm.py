"""Schneidet OSM-Daten für alle Kacheln aus dem Geofabrik-Auszug (Sachsen) aus.

Ersetzt fetch_osm.py (Overpass) für das ganze Stadtgebiet: ein Durchlauf, alle Kacheln.
Ausgabe: data/raw/tiles/<E>_<N>/osm/<kategorie>.json im Overpass-Format ("elements" mit "geometry").
Quelle: (c) OpenStreetMap-Mitwirkende, ODbL (Geofabrik-Extrakt).
"""
import json
import sys
import time
from collections import defaultdict

import numpy as np
import osmium
from pyproj import Transformer

from config import RAW

PBF = RAW / "geofabrik" / "sachsen.osm.pbf"
TILES = [tuple(int(v) for v in l.split(",")) for l in (RAW / "tile_order.txt").read_text().split() if l]
MARGIN = 0.0016   # Grad (~110-180 m) Rand um jede Kachel

TO_LL = Transformer.from_crs("EPSG:25833", "EPSG:4326", always_xy=True)

RAIL = {"tram", "rail", "light_rail", "subway"}
NATURAL_AREA = {"wood", "scrub", "grassland", "heath", "sand"}
POINT_HIGHWAY = {"street_lamp", "traffic_signals", "crossing", "stop"}
POINT_AMENITY = {"bench", "waste_basket", "bicycle_parking"}
BARRIER = {"wall", "fence", "retaining_wall", "city_wall"}


def categories_way(t):
    c = []
    if "building" in t or "building:part" in t:
        c.append("buildings")
    if "highway" in t:
        c.append("roads")
    if t.get("railway") in RAIL:
        c.append("rail")
    if "landuse" in t or "leisure" in t or t.get("natural") in NATURAL_AREA or t.get("amenity") == "parking":
        c.append("landuse")
    if t.get("natural") == "water" or "waterway" in t or "water" in t:
        c.append("water")
    if t.get("natural") == "tree_row":
        c.append("tree_rows")
    if t.get("barrier") in BARRIER:
        c.append("barriers")
    if "bridge" in t or t.get("man_made") == "bridge":
        c.append("bridges")
    return c


def categories_rel(t):
    c = []
    if "building" in t:
        c.append("buildings")
    if "landuse" in t or "leisure" in t or t.get("natural") in {"wood", "scrub", "grassland"}:
        c.append("landuse")
    if t.get("natural") == "water":
        c.append("water")
    return c


POI_KEYS = ("shop", "craft", "office", "advertising", "public_transport", "traffic_sign", "vending", "emergency",
            "historic", "tourism", "leisure", "man_made", "healthcare")
POI_HIGHWAY = {"bus_stop", "give_way", "stop", "traffic_signals", "crossing", "street_lamp", "speed_camera"}
POI_RAILWAY = {"tram_stop", "station", "halt", "level_crossing"}


def categories_node(t):
    c = []
    if t.get("natural") == "tree" or t.get("highway") in POINT_HIGHWAY or t.get("amenity") in POINT_AMENITY:
        c.append("points")
    # Straßenleben: Läden, Gastronomie, Stadtmöbel, Haltestellen, Zeichen, Denkmäler ...
    if "amenity" in t or any(k in t for k in POI_KEYS) or t.get("highway") in POI_HIGHWAY \
            or t.get("railway") in POI_RAILWAY or t.get("barrier") in ("bollard", "gate", "lift_gate"):
        c.append("pois")
    return c


def main() -> None:
    t0 = time.time()
    # Tile-Grenzen in lon/lat
    tb = []
    for e, n in TILES:
        xs, ys = [], []
        for ee, nn in ((e, n), (e + 2, n), (e, n + 2), (e + 2, n + 2)):
            lon, lat = TO_LL.transform(ee * 1000.0, nn * 1000.0)
            xs.append(lon)
            ys.append(lat)
        tb.append((min(xs) - MARGIN * 1.6, min(ys) - MARGIN, max(xs) + MARGIN * 1.6, max(ys) + MARGIN))
    tb = np.array(tb)
    gminlon, gminlat, gmaxlon, gmaxlat = tb[:, 0].min(), tb[:, 1].min(), tb[:, 2].max(), tb[:, 3].max()

    # Pass 1: Relationen
    print("Pass 1: Relationen ...", flush=True)
    rels = {}
    member_ways = set()
    for o in osmium.FileProcessor(str(PBF), osmium.osm.RELATION):
        t = {x.k: x.v for x in o.tags}
        if t.get("type") not in ("multipolygon", "building"):
            continue
        cats = categories_rel(t)
        if not cats:
            continue
        mem = [(m.ref, m.role) for m in o.members if m.type == "w"]
        if not mem:
            continue
        rels[o.id] = {"tags": t, "cats": cats, "members": mem}
        member_ways.update(r for r, _ in mem)
    print(f"  {len(rels)} Relationen ({time.time() - t0:.0f} s)", flush=True)

    # Pass 2: Wege + Knoten (Positionen aus Index)
    print("Pass 2: Wege/Knoten ...", flush=True)
    way_geom = {}      # nur Mitglieder-Wege
    elements = []      # (cat, element, bbox)
    fp = osmium.FileProcessor(str(PBF), osmium.osm.NODE | osmium.osm.WAY).with_locations()
    cnt = 0
    for o in fp:
        if o.is_node():
            if not o.tags:
                continue
            t = {x.k: x.v for x in o.tags}
            cats = categories_node(t)
            if not cats:
                continue
            lon, lat = o.location.lon, o.location.lat
            if not (gminlon <= lon <= gmaxlon and gminlat <= lat <= gmaxlat):
                continue
            nd = {"type": "node", "id": o.id, "lat": lat, "lon": lon, "tags": t}
            for c in cats:
                elements.append((c, nd, (lon, lat, lon, lat)))
            continue
        t = {x.k: x.v for x in o.tags}
        cats = categories_way(t) if t else []
        if not cats and o.id not in member_ways:
            continue
        try:
            pts = [(n.lon, n.lat) for n in o.nodes if n.location.valid()]
        except osmium.InvalidLocationError:
            continue
        if len(pts) < 2:
            continue
        lons = [p[0] for p in pts]
        lats = [p[1] for p in pts]
        bb = (min(lons), min(lats), max(lons), max(lats))
        if bb[2] < gminlon or bb[0] > gmaxlon or bb[3] < gminlat or bb[1] > gmaxlat:
            continue
        geom = [{"lat": p[1], "lon": p[0]} for p in pts]
        if o.id in member_ways:
            way_geom[o.id] = geom
        if cats:
            el = {"type": "way", "id": o.id, "tags": t, "geometry": geom}
            for c in cats:
                elements.append((c, el, bb))
        cnt += 1
        if cnt % 200000 == 0:
            print(f"  {cnt} Wege ({time.time() - t0:.0f} s)", flush=True)

    # Relationen zusammensetzen
    for rid, r in rels.items():
        members = []
        lons, lats = [], []
        for ref, role in r["members"]:
            g = way_geom.get(ref)
            if g is None:
                continue
            members.append({"type": "way", "ref": ref, "role": role, "geometry": g})
            lons += [p["lon"] for p in g]
            lats += [p["lat"] for p in g]
        if not members:
            continue
        el = {"type": "relation", "id": rid, "tags": r["tags"], "members": members}
        bb = (min(lons), min(lats), max(lons), max(lats))
        for c in r["cats"]:
            elements.append((c, el, bb))
    print(f"  {len(elements)} Elemente gesamt ({time.time() - t0:.0f} s)", flush=True)

    # Verteilen
    per = defaultdict(lambda: defaultdict(list))
    for cat, el, bb in elements:
        m = (tb[:, 0] <= bb[2]) & (tb[:, 2] >= bb[0]) & (tb[:, 1] <= bb[3]) & (tb[:, 3] >= bb[1])
        for i in np.nonzero(m)[0]:
            per[int(i)][cat].append(el)
    cats_all = ["buildings", "roads", "rail", "landuse", "water", "points", "tree_rows", "barriers", "bridges", "pois"]
    for i, (e, n) in enumerate(TILES):
        out = RAW / "tiles" / f"{e}_{n}" / "osm"
        out.mkdir(parents=True, exist_ok=True)
        for c in cats_all:
            (out / f"{c}.json").write_text(json.dumps({"elements": per[i].get(c, [])}, separators=(",", ":")), encoding="utf-8")
    print(f"fertig: {len(TILES)} Kacheln ({time.time() - t0:.0f} s)", flush=True)


if __name__ == "__main__":
    main()
