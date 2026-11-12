"""Lädt offene Straßenraum-Daten für ganz Dresden nach data/raw/strassenraum/ (wiederholbar).

Quellen (alle frei nutzbar, Namensnennung):
  * Landeshauptstadt Dresden, Themenstadtplan / Open-Data-Portal (OGC API Features
    https://kommisdd.dresden.de/net4/public/ogcapi) – Lizenz dl-de/by-2-0
      L1261 Stadtbäume, L1564 Straßenflächen, L1264 Verkehrsflächen, L1266 Grün- und Freiflächen
      (u. a. F31 Verkehrsbegleitgrün), L1652 Anlagen des Radverkehrs, L123 Straßenknotennetz SKN5 (Kanten)
  * GeoSN, ALKIS vereinfacht (WFS https://geodienste.sachsen.de/aaa/public_alkis/vereinf/wfs) –
    kostenfrei mit Quellenangabe "GeoSN" (dl-de/by-2-0): tatsächliche Nutzung (nur Verkehrsarten)
  * OpenStreetMap (lokaler Geofabrik-Auszug data/raw/geofabrik/sachsen.osm.pbf) – ODbL:
    area:highway-Flächen, barrier=kerb-Linien, Bordstein-Knoten, separat erfasste Gehwege

Aufruf (aus dem Projektordner):
  .venv/bin/python tools/fetch_strassenraum.py            # alles (überspringt Vorhandenes)
  .venv/bin/python tools/fetch_strassenraum.py --force    # alles neu
  .venv/bin/python tools/fetch_strassenraum.py --only ogc|alkis|osm|tiles
Ausgaben (EPSG:25833, GeoJSON): stadtbaeume, strassenflaechen, verkehrsflaechen, gruenflaechen,
radverkehr, skn5_kanten, alkis_verkehr, osm_area_highway, osm_kerbs, osm_sidewalks (.geojson)
und je Spielkachel tiles/<E>_<N>.json (kompakt, Kachel ± 400 m) für tools/strassenraum.py.
"""
import argparse
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = RAW / "strassenraum"
TILES = [tuple(int(v) for v in l.split(",")) for l in (RAW / "tile_order.txt").read_text().split() if l]
TILE_MARGIN = 400.0     # m Rand der Kachel-Auszüge

UA = "strassenraum-fetch/1.0 (python-requests; open data client)"
OGC = "https://kommisdd.dresden.de/net4/public/ogcapi/collections"
CRS25833 = "http://www.opengis.net/def/crs/EPSG/0/25833"
ALKIS_WFS = "https://geodienste.sachsen.de/aaa/public_alkis/vereinf/wfs"
ALKIS_NS = "http://repository.gdi-de.org/schemas/adv/produkt/alkis-vereinfacht/2.0"
GML = "{http://www.opengis.net/gml/3.2}"
PAUSE = 0.6             # s zwischen Anfragen (höflich drosseln)

# Dresdner OGC-Collections: Ausgabename, Collection-ID, Attribute (None = alle)
OGC_LAYERS = [
    ("stadtbaeume", "L1261", None),
    ("strassenflaechen", "L1564", None),
    ("verkehrsflaechen", "L1264", None),
    ("gruenflaechen", "L1266", None),
    ("radverkehr", "L1652", None),
    ("skn5_kanten", "L123", None),
]
ALKIS_KEEP = {"Straßenverkehr", "Weg", "Platz", "Bahnverkehr"}

SESSION = requests.Session()
SESSION.headers["User-Agent"] = UA


def _get(url, params=None, tries=5, timeout=180):
    for i in range(tries):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r
            print(f"    HTTP {r.status_code} – Wiederholung {i + 1}", flush=True)
        except requests.RequestException as ex:
            print(f"    Fehler {ex!r} – Wiederholung {i + 1}", flush=True)
        time.sleep(3 + 5 * i)
    raise RuntimeError(f"Abruf fehlgeschlagen: {url} {params}")


def _write_fc(path, feats, meta):
    fc = {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25833"}},
          "meta": meta, "features": feats}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")))
    tmp.replace(path)


# ----------------------------------------------------------------------------------------------
# 1) Dresden OGC API Features
# ----------------------------------------------------------------------------------------------
def _ogc_items(cid, bbox=None, limit=100000):
    params = {"limit": limit, "f": "json", "crs": CRS25833}
    if bbox:
        params["bbox"] = ",".join(f"{v:.1f}" for v in bbox)
        params["bbox-crs"] = CRS25833
    d = _get(f"{OGC}/{cid}/items", params).json()
    time.sleep(PAUSE)
    return d.get("features", [])


def _ogc_collect(cid, bbox, limit, acc, depth=0):
    """Rekursiv: bbox abfragen, bei vollem Ergebnis vierteln (Server kennt kein offset)."""
    fs = _ogc_items(cid, bbox, limit)
    if len(fs) >= limit and depth < 6:
        x0, y0, x1, y1 = bbox
        xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
        for b in ((x0, y0, xm, ym), (xm, y0, x1, ym), (x0, ym, xm, y1), (xm, ym, x1, y1)):
            _ogc_collect(cid, b, limit, acc, depth + 1)
        return
    for f in fs:
        acc[str(f.get("id"))] = f


def fetch_ogc(force=False):
    e0 = min(e for e, _ in TILES) * 1000.0 - 1000
    e1 = (max(e for e, _ in TILES) + 2) * 1000.0 + 1000
    n0 = min(n for _, n in TILES) * 1000.0 - 1000
    n1 = (max(n for _, n in TILES) + 2) * 1000.0 + 1000
    for name, cid, _ in OGC_LAYERS:
        path = OUT / f"{name}.geojson"
        if path.exists() and not force:
            print(f"[ogc] {name}: vorhanden", flush=True)
            continue
        t0 = time.time()
        limit = 100000
        fs = _ogc_items(cid, None, limit)
        acc = {}
        if len(fs) < limit:
            for f in fs:
                acc[str(f.get("id"))] = f
        else:   # zu groß: in 4-km-Blöcken (rekursiv verfeinert)
            step = 4000.0
            y = n0
            while y < n1:
                x = e0
                while x < e1:
                    _ogc_collect(cid, (x, y, x + step, y + step), 50000, acc)
                    x += step
                y += step
        feats = []
        for fid, f in acc.items():
            g = f.get("geometry")
            if not g:
                continue
            g.pop("crs", None)
            p = f.get("properties") or {}
            for k, v in list(p.items()):
                if isinstance(v, str):
                    p[k] = v.strip()
            feats.append({"type": "Feature", "id": fid, "geometry": g, "properties": p})
        _write_fc(path, feats, {"source": f"Landeshauptstadt Dresden, Themenstadtplan {cid}",
                                "license": "dl-de/by-2-0", "url": f"{OGC}/{cid}",
                                "fetched": time.strftime("%Y-%m-%d")})
        print(f"[ogc] {name} ({cid}): {len(feats)} Objekte, {time.time() - t0:.0f} s", flush=True)


# ----------------------------------------------------------------------------------------------
# 2) GeoSN ALKIS vereinfacht – tatsächliche Nutzung (Verkehrsarten)
# ----------------------------------------------------------------------------------------------
def _poslist(el):
    v = [float(t) for t in el.text.split()]
    return [[v[i], v[i + 1]] for i in range(0, len(v) - 1, 2)]


def _ring(el):
    """LinearRing oder Ring (curveMember/LineStringSegment/Arc) -> Koordinatenliste."""
    pts = []
    for pl in el.iter(GML + "posList"):
        p = _poslist(pl)
        if pts and p and pts[-1] == p[0]:
            p = p[1:]
        pts.extend(p)
    if pts and pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


def _polys(geom_el):
    out = []
    for pg in list(geom_el.iter(GML + "Polygon")) + list(geom_el.iter(GML + "PolygonPatch")):
        ext = pg.find(GML + "exterior")
        if ext is None:
            continue
        rings = [_ring(ext)]
        for it in pg.findall(GML + "interior"):
            rings.append(_ring(it))
        if len(rings[0]) >= 4:
            out.append(rings)
    return out


def fetch_alkis(force=False):
    path = OUT / "alkis_verkehr.geojson"
    if path.exists() and not force:
        print("[alkis] vorhanden", flush=True)
        return
    cache = OUT / "alkis_cache"
    cache.mkdir(parents=True, exist_ok=True)
    acc = {}
    t0 = time.time()
    for i, (e, n) in enumerate(TILES):
        cf = cache / f"{e}_{n}.gml"
        if not cf.exists() or force:
            params = {"REQUEST": "GetFeature", "SERVICE": "WFS", "VERSION": "2.0.0", "TYPENAMES": "ave:Nutzung",
                      "NAMESPACES": f"xmlns(ave,{ALKIS_NS})", "SRSNAME": "urn:ogc:def:crs:EPSG::25833",
                      "BBOX": f"{e * 1000},{n * 1000},{(e + 2) * 1000},{(n + 2) * 1000},urn:ogc:def:crs:EPSG::25833",
                      "COUNT": 20000}
            r = _get(ALKIS_WFS, params, timeout=300)
            cf.write_bytes(r.content)
            time.sleep(PAUSE)
        root = ET.parse(cf).getroot()
        nret = int(root.get("numberReturned") or 0)
        if nret >= 20000:
            print(f"  WARNUNG {e},{n}: Obergrenze 20000 erreicht", flush=True)
        for nu in root.iter("{%s}Nutzung" % ALKIS_NS):
            art = nu.findtext("{%s}nutzart" % ALKIS_NS) or ""
            if art not in ALKIS_KEEP:
                continue
            oid = nu.findtext("{%s}oid" % ALKIS_NS)
            if oid in acc:
                continue
            geo = nu.find("{%s}geometrie" % ALKIS_NS)
            polys = _polys(geo) if geo is not None else []
            if not polys:
                continue
            props = {"nutzart": art}
            for tag in ("bez", "name", "info", "zweck", "aktualit"):
                v = nu.findtext("{%s}%s" % (ALKIS_NS, tag))
                if v:
                    props[tag] = v
            g = {"type": "Polygon", "coordinates": polys[0]} if len(polys) == 1 else \
                {"type": "MultiPolygon", "coordinates": polys}
            acc[oid] = {"type": "Feature", "id": oid, "geometry": g, "properties": props}
        if (i + 1) % 10 == 0:
            print(f"  [alkis] {i + 1}/{len(TILES)} Kacheln, {len(acc)} Verkehrsflächen ({time.time() - t0:.0f} s)",
                  flush=True)
    _write_fc(path, list(acc.values()), {"source": "GeoSN, ALKIS vereinfacht (ave:Nutzung), WFS " + ALKIS_WFS,
                                         "license": "dl-de/by-2-0 (kostenfrei, Quellenangabe GeoSN)",
                                         "filter": sorted(ALKIS_KEEP), "fetched": time.strftime("%Y-%m-%d")})
    print(f"[alkis] {len(acc)} Verkehrsflächen, {time.time() - t0:.0f} s", flush=True)


# ----------------------------------------------------------------------------------------------
# 3) OSM aus dem lokalen Geofabrik-Auszug
# ----------------------------------------------------------------------------------------------
CAR_AREA = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
            "living_street", "service", "road", "busway", "motorway_link", "trunk_link", "primary_link",
            "secondary_link", "tertiary_link", "bus_stop", "platform"}


def fetch_osm(force=False):
    paths = {k: OUT / f"osm_{k}.geojson" for k in ("area_highway", "kerbs", "sidewalks")}
    if all(p.exists() for p in paths.values()) and not force:
        print("[osm] vorhanden", flush=True)
        return
    import osmium
    from pyproj import Transformer
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
    to_ll = Transformer.from_crs("EPSG:25833", "EPSG:4326", always_xy=True)
    e0 = min(e for e, _ in TILES) * 1000.0 - 500
    e1 = (max(e for e, _ in TILES) + 2) * 1000.0 + 500
    n0 = min(n for _, n in TILES) * 1000.0 - 500
    n1 = (max(n for _, n in TILES) + 2) * 1000.0 + 500
    lo0, la0 = to_ll.transform(e0, n0)
    lo1, la1 = to_ll.transform(e1, n1)
    lo0, lo1 = lo0 - 0.02, lo1 + 0.02
    pbf = RAW / "geofabrik" / "sachsen.osm.pbf"
    t0 = time.time()
    out = {k: [] for k in paths}

    def utm(pts):
        xs, ys = to_utm.transform([p[0] for p in pts], [p[1] for p in pts])
        return [[round(x, 2), round(y, 2)] for x, y in zip(xs, ys)]

    # Multipolygon-Relationen mit area:highway (selten) – nur äußere Ringe aus geschlossenen Wegen
    rel_members = {}
    rel_tags = {}
    for o in osmium.FileProcessor(str(pbf), osmium.osm.RELATION):
        t = {x.k: x.v for x in o.tags}
        if t.get("type") == "multipolygon" and "area:highway" in t:
            rel_tags[o.id] = t
            for m in o.members:
                if m.type == "w":
                    rel_members.setdefault(m.ref, []).append((o.id, m.role))
    rel_ways = {}

    fp = osmium.FileProcessor(str(pbf), osmium.osm.NODE | osmium.osm.WAY).with_locations()
    for o in fp:
        if o.is_node():
            if not o.tags:
                continue
            t = {x.k: x.v for x in o.tags}
            if t.get("barrier") == "kerb" or "kerb" in t:
                lon, lat = o.location.lon, o.location.lat
                if lo0 <= lon <= lo1 and la0 <= lat <= la1:
                    x, y = to_utm.transform(lon, lat)
                    out["kerbs"].append({"type": "Feature", "id": f"n{o.id}",
                                         "geometry": {"type": "Point", "coordinates": [round(x, 2), round(y, 2)]},
                                         "properties": {k: v for k, v in t.items() if k.startswith(("kerb", "barrier", "highway", "crossing", "tactile"))}})
            continue
        t = {x.k: x.v for x in o.tags}
        want_rel = o.id in rel_members
        kind = None
        if "area:highway" in t:
            kind = "area_highway"
        elif t.get("barrier") == "kerb" or (t.get("kerb") and "highway" not in t):
            kind = "kerbs"
        elif (t.get("footway") == "sidewalk" or t.get("path") == "sidewalk" or t.get("cycleway") == "sidewalk"
              or (t.get("highway") == "cycleway" and t.get("is_sidepath") == "yes")):
            kind = "sidewalks"
        if kind is None and not want_rel:
            continue
        try:
            pts = [(n.lon, n.lat) for n in o.nodes if n.location.valid()]
        except osmium.InvalidLocationError:
            continue
        if len(pts) < 2:
            continue
        if not any(lo0 <= p[0] <= lo1 and la0 <= p[1] <= la1 for p in pts[:: max(1, len(pts) // 8)] + [pts[-1]]):
            continue
        if want_rel:
            rel_ways[o.id] = utm(pts)
        if kind is None:
            continue
        c = utm(pts)
        closed = len(c) >= 4 and c[0] == c[-1]
        if kind == "area_highway":
            if not closed:
                continue
            g = {"type": "Polygon", "coordinates": [c]}
        else:
            g = {"type": "LineString", "coordinates": c}
        keep = {k: v for k, v in t.items() if not k.startswith(("source", "note", "fixme", "check_date"))}
        out[kind].append({"type": "Feature", "id": f"w{o.id}", "geometry": g, "properties": keep})

    # Relationen zusammensetzen (geschlossene Mitgliedswege bzw. einfache Ringverkettung)
    for rid, t in rel_tags.items():
        outers, inners = [], []
        for wid, roles in rel_members.items():
            for r, role in roles:
                if r == rid and wid in rel_ways:
                    (inners if role == "inner" else outers).append(rel_ways[wid])
        rings = _chain(outers)
        if not rings:
            continue
        holes = _chain(inners)
        polys = [[r] + [h for h in holes] for r in rings] if len(rings) == 1 else [[r] for r in rings]
        g = {"type": "Polygon", "coordinates": polys[0]} if len(polys) == 1 else {"type": "MultiPolygon", "coordinates": polys}
        out["area_highway"].append({"type": "Feature", "id": f"r{rid}", "geometry": g,
                                    "properties": {k: v for k, v in t.items() if k != "type"}})

    meta = {"source": "OpenStreetMap-Mitwirkende, Geofabrik-Auszug sachsen.osm.pbf", "license": "ODbL 1.0",
            "fetched": time.strftime("%Y-%m-%d")}
    for k, p in paths.items():
        _write_fc(p, out[k], meta)
        print(f"[osm] {k}: {len(out[k])} Objekte", flush=True)
    print(f"[osm] fertig in {time.time() - t0:.0f} s", flush=True)


def _chain(segs):
    """Wegstücke zu geschlossenen Ringen verketten."""
    segs = [list(s) for s in segs]
    rings = []
    while segs:
        cur = segs.pop()
        changed = True
        while cur[0] != cur[-1] and changed:
            changed = False
            for i, s in enumerate(segs):
                if s[0] == cur[-1]:
                    cur += s[1:]
                elif s[-1] == cur[-1]:
                    cur += s[::-1][1:]
                elif s[-1] == cur[0]:
                    cur = s[:-1] + cur
                elif s[0] == cur[0]:
                    cur = s[::-1][:-1] + cur
                else:
                    continue
                segs.pop(i)
                changed = True
                break
        if cur[0] == cur[-1] and len(cur) >= 4:
            rings.append(cur)
    return rings


# ----------------------------------------------------------------------------------------------
# 4) Kachel-Auszüge für die Pipeline
# ----------------------------------------------------------------------------------------------
TILE_LAYERS = ["stadtbaeume", "strassenflaechen", "verkehrsflaechen", "gruenflaechen", "radverkehr", "skn5_kanten",
               "alkis_verkehr", "osm_area_highway", "osm_kerbs", "osm_sidewalks"]
# nur diese Grünflächen-Klassen werden in die Kachel-Auszüge übernommen (Straßenraum)
GREEN_KEEP = ("F3",)


def _bbox(g):
    t = g["type"]
    c = g["coordinates"]
    if t == "Point":
        return c[0], c[1], c[0], c[1]
    if t in ("LineString",):
        pts = c
    elif t in ("Polygon", "MultiLineString"):
        pts = [p for r in c for p in r]
    elif t == "MultiPolygon":
        pts = [p for poly in c for r in poly for p in r]
    else:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def build_tiles():
    import numpy as np
    tdir = OUT / "tiles"
    tdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    layers = {}
    for name in TILE_LAYERS:
        p = OUT / f"{name}.geojson"
        if not p.exists():
            print(f"[tiles] {name} fehlt – übersprungen", flush=True)
            continue
        fc = json.loads(p.read_text())
        feats = fc["features"]
        if name == "gruenflaechen":
            feats = [f for f in feats if str(f["properties"].get("desk2", "")).startswith(GREEN_KEEP)]
        bbs = []
        keep = []
        for f in feats:
            b = _bbox(f["geometry"]) if f.get("geometry") else None
            if b is None:
                continue
            keep.append(f)
            bbs.append(b)
        layers[name] = (keep, np.array(bbs, dtype=np.float64).reshape(-1, 4), fc.get("meta"))
        print(f"[tiles] {name}: {len(keep)}", flush=True)
    for e, n in TILES:
        x0, y0 = e * 1000.0 - TILE_MARGIN, n * 1000.0 - TILE_MARGIN
        x1, y1 = (e + 2) * 1000.0 + TILE_MARGIN, (n + 2) * 1000.0 + TILE_MARGIN
        res = {"tile": [e, n], "crs": "EPSG:25833", "margin": TILE_MARGIN, "layers": {}, "meta": {}}
        for name, (feats, bb, meta) in layers.items():
            if not len(feats):
                continue
            m = (bb[:, 2] >= x0) & (bb[:, 0] <= x1) & (bb[:, 3] >= y0) & (bb[:, 1] <= y1)
            res["layers"][name] = [feats[i] for i in np.nonzero(m)[0]]
            res["meta"][name] = meta
        (tdir / f"{e}_{n}.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    print(f"[tiles] {len(TILES)} Kachel-Auszüge in {time.time() - t0:.0f} s", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", choices=["ogc", "alkis", "osm", "tiles"])
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    steps = {"ogc": fetch_ogc, "alkis": fetch_alkis, "osm": fetch_osm}
    for k, fn in steps.items():
        if a.only in (None, k):
            fn(a.force)
    if a.only in (None, "tiles"):
        build_tiles()
    (OUT / "QUELLEN.txt").write_text(
        "Straßenraum-Daten (siehe data/research/strassenraum.md)\n"
        "- Landeshauptstadt Dresden, Themenstadtplan/Open-Data-Portal: Stadtbäume, Straßenflächen, Verkehrsflächen,\n"
        "  Grün- und Freiflächen, Anlagen des Radverkehrs, Straßenknotennetz SKN5 – Datenlizenz Deutschland –\n"
        "  Namensnennung – 2.0 (dl-de/by-2-0)\n"
        "- GeoSN (Landesamt für Geobasisinformation Sachsen), ALKIS vereinfacht, tatsächliche Nutzung –\n"
        "  dl-de/by-2-0 (Quellenvermerk 'GeoSN')\n"
        "- OpenStreetMap-Mitwirkende (Geofabrik-Auszug) – ODbL 1.0\n")


if __name__ == "__main__":
    sys.exit(main())
