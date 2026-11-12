"""Liest LoD2-CityGML-Kacheln (GeoSN) und liefert Gebäudeteile mit Grundfläche, Dach- und Wandflächen.

Ein "Teil" ist ein BuildingPart (oder ein Gebäude ohne Teile):
  {"id", "ground": [(e,n),...] (Shapely-Polygon als Ring), "ground_z", "roofs": [Polygon3D], "walls": [Polygon3D],
   "roof_type": int|None, "function": str|None, "storeys": int|None}
Polygon3D = (exterior[(e,n,z)...], [interior...])
"""
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from config import RAW

NS = {
    "bldg": "http://www.opengis.net/citygml/building/1.0",
    "gml": "http://www.opengis.net/gml",
    "gen": "http://www.opengis.net/citygml/generics/1.0",
}
B = "{%s}" % NS["bldg"]
G = "{%s}" % NS["gml"]


def tile_names(min_e, min_n, max_e, max_n):
    """Kachelnamen (E-km, N-km, 2 km) die das Gebiet überdecken."""
    out = []
    e = int(min_e // 2000) * 2
    while e * 1000 < max_e:
        n = int(min_n // 2000) * 2
        while n * 1000 < max_n:
            out.append(f"lod2_33{e}_{n}_2_sn_citygml.zip")
            n += 2
        e += 2
    return out


def _ring(el):
    pl = el.find(".//" + G + "posList")
    if pl is None or not pl.text:
        return None
    v = [float(x) for x in pl.text.split()]
    pts = [(v[i], v[i + 1], v[i + 2]) for i in range(0, len(v) - 2, 3)]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts if len(pts) >= 3 else None


def _polys(surface):
    res = []
    for poly in surface.iter(G + "Polygon"):
        ext = poly.find(G + "exterior")
        if ext is None:
            continue
        e = _ring(ext)
        if e is None:
            continue
        holes = []
        for it in poly.findall(G + "interior"):
            r = _ring(it)
            if r is not None:
                holes.append(r)
        res.append((e, holes))
    return res


def _direct_surfaces(el, out):
    for ch in el:
        if ch.tag == B + "BuildingPart":
            continue
        if ch.tag == B + "boundedBy":
            for s in ch:
                out.append(s)
        elif ch.tag == B + "consistsOfBuildingPart":
            continue
        else:
            pass


def _unit(el, uid, attrs_from):
    surfs = []
    _direct_surfaces(el, surfs)
    ground, roofs, walls = [], [], []
    for s in surfs:
        t = s.tag.split("}")[1]
        if t == "GroundSurface":
            ground += _polys(s)
        elif t == "RoofSurface":
            roofs += _polys(s)
        elif t == "WallSurface":
            walls += _polys(s)
    if not roofs and not walls:
        return None
    rt = el.find(B + "roofType")
    if rt is None:
        rt = attrs_from.find(B + "roofType")
    fn = el.find(B + "function")
    if fn is None:
        fn = attrs_from.find(B + "function")
    st = el.find(B + "storeysAboveGround")
    if st is None:
        st = attrs_from.find(B + "storeysAboveGround")
    try:
        rtv = int(rt.text) if rt is not None else None
    except ValueError:
        rtv = None
    try:
        stv = int(st.text) if st is not None else None
    except ValueError:
        stv = None
    return {"id": uid, "ground": ground, "roofs": roofs, "walls": walls, "roof_type": rtv,
            "function": fn.text if fn is not None else None, "storeys": stv}


def read_tile(path: Path, bbox=None):
    """Gibt Liste von Teilen zurück. bbox=(minE,minN,maxE,maxN) filtert nach Gebäudemitte."""
    parts = []
    with zipfile.ZipFile(path) as z:
        name = [n for n in z.namelist() if n.endswith(".gml")][0]
        with z.open(name) as f:
            for _ev, el in ET.iterparse(f, events=("end",)):
                if el.tag != B + "Building":
                    continue
                gid = el.get(G + "id") or ""
                if bbox is not None:
                    lc = el.find(".//" + G + "lowerCorner")
                    uc = el.find(".//" + G + "upperCorner")
                    if lc is not None and uc is not None:
                        a = [float(x) for x in lc.text.split()]
                        b = [float(x) for x in uc.text.split()]
                        # Hüllquader muss das (erweiterte) Gebiet schneiden
                        if b[0] < bbox[0] - 40 or a[0] > bbox[2] + 40 or b[1] < bbox[1] - 40 or a[1] > bbox[3] + 40:
                            el.clear()
                            continue
                subs = [p.find(B + "BuildingPart") for p in el.findall(B + "consistsOfBuildingPart")]
                u = _unit(el, gid, el)
                if u:
                    parts.append(u)
                for i, p in enumerate(subs):
                    if p is None:
                        continue
                    u = _unit(p, f"{gid}_{i}", el)
                    if u:
                        parts.append(u)
                el.clear()
    return parts


def read_area(bbox):
    res = []
    for n in tile_names(*bbox):
        p = RAW / "lod2" / n
        if p.exists():
            res += read_tile(p, bbox)
    return res


BRIDGE_FUNCTIONS = ("53001_1800", "51009_1700")


def _bridge_cache(path: Path):
    """Alle Brücken-Einheiten einer LoD2-Kachel (zwischengespeichert als JSON, atomar geschrieben)."""
    import json
    import os
    cache = RAW / "lod2_bridges" / (path.stem + ".json")
    if cache.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
        return json.loads(cache.read_text())
    parts = [p for p in read_tile(path) if (p.get("function") or "").startswith(BRIDGE_FUNCTIONS)]
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(parts))
    os.replace(tmp, cache)
    return json.loads(cache.read_text())


def read_bridges(bbox, margin=40.0):
    """Brücken-Einheiten (Funktion 53001_1800 / 51009_1700), deren Hülle das Gebiet bbox ± margin schneidet."""
    x0, y0, x1, y1 = bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin
    res = []
    for n in tile_names(x0, y0, x1, y1):
        p = RAW / "lod2" / n
        if not p.exists():
            continue
        for part in _bridge_cache(p):
            pts = [q for ext, _ in part["roofs"] + part["walls"] + part["ground"] for q in ext]
            if not pts:
                continue
            es = [q[0] for q in pts]
            ns = [q[1] for q in pts]
            if max(es) < x0 or min(es) > x1 or max(ns) < y0 or min(ns) > y1:
                continue
            res.append(part)
    return res
