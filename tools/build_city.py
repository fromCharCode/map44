"""Bereitet OSM + Luftbilder + Gelände für Godot auf.

Ausgabe in data/processed/:
  city.json    Gebäude (mit Dachgeometrie), Straßen, Brücken, Gleise, Bäume, Laternen, Straßengraph
  splat0.png   RGBA: R Straße, G Gehweg/Pfad, B Platz/Pflaster, A Tram-Bett   (0,5 m pro Pixel)
  splat1.png   RGBA: R Wiese/Park, G Wald/Gebüsch, B Parkplatz, A unbenutzt
  ortho.jpg    Luftbild 4096 x 4096 (ca. 0,49 m pro Pixel) für Farbvariation

Koordinaten im Spiel (Godot): x = Ost - ORIGIN_E, z = -(Nord - ORIGIN_N), y = Höhe - base_height.
"""
import colorsys
from collections import defaultdict
from pathlib import Path
import hashlib
import json
import math
import re
import sys

import mapbox_earcut
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import linemerge, polygonize, unary_union
from shapely.strtree import STRtree

from config import BASE_HEIGHT, BBOX_UTM, DOP_DIR, ORIGIN_E, ORIGIN_N, OSM_DIR, PROCESSED, RAW
from bridge_fix import DomMosaic
from road_surface import PAD as RS_PAD, Mosaic, RoadSurface, raster_tris
from parking import lane_widths, park_sides

Image.MAX_IMAGE_PIXELS = None
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
MIN_E, MIN_N, MAX_E, MAX_N = BBOX_UTM
SIZE = int(MAX_E - MIN_E)
AREA_BOX = box(MIN_E - 30, MIN_N - 30, MAX_E + 30, MAX_N + 30)
TILE_BOX = box(MIN_E, MIN_N, MAX_E, MAX_N)          # strikte Besitzgrenze (Gebäude, Bäume ...)
WATER_BOX = box(MIN_E - 0.5, MIN_N - 0.5, MAX_E + 0.5, MAX_N + 0.5)
SPLAT_PX = 2  # Pixel pro Meter

# ---------------------------------------------------------------------------
# Gelände
# ---------------------------------------------------------------------------
TERRAIN_META = json.loads((PROCESSED / "terrain.json").read_text())
_RAW = PROCESSED / ("terrain_raw.f32" if (PROCESSED / "terrain_raw.f32").exists() else "terrain.f32")
TERRAIN = np.frombuffer(_RAW.read_bytes(), dtype="<f4").reshape(
    TERRAIN_META["height"], TERRAIN_META["width"]).copy()


def ground(e: float, n: float) -> float:
    """Bilinear interpolierte Geländehöhe (relativ zu base_height) an UTM-Position."""
    c = min(max(e - MIN_E - 0.5, 0.0), SIZE - 1.001)
    r = min(max(MAX_N - n - 0.5, 0.0), SIZE - 1.001)
    c0, r0 = int(c), int(r)
    fc, fr = c - c0, r - r0
    t = TERRAIN
    top = t[r0, c0] * (1 - fc) + t[r0, c0 + 1] * fc
    bot = t[r0 + 1, c0] * (1 - fc) + t[r0 + 1, c0 + 1] * fc
    return float(top * (1 - fr) + bot * fr)


def to_local(e: float, n: float) -> tuple[float, float]:
    return (round(e - ORIGIN_E, 2), round(-(n - ORIGIN_N), 2))


# ---------------------------------------------------------------------------
# OSM einlesen
# ---------------------------------------------------------------------------
def load(name: str) -> list[dict]:
    f = OSM_DIR / f"{name}.json"
    els = json.loads(f.read_text(encoding="utf-8"))["elements"] if f.exists() else []
    if name in ("roads", "bridges"):
        for el in els:
            if el.get("type") == "way" and "tags" in el:
                el["tags"]["_id"] = el["id"]          # für gemessene Breiten (width_override)
    return els


def way_coords(el: dict) -> np.ndarray:
    g = el.get("geometry") or []
    if not g:
        return np.zeros((0, 2))
    lon = [p["lon"] for p in g]
    lat = [p["lat"] for p in g]
    e, n = TO_UTM.transform(lon, lat)
    return np.column_stack([e, n])


def polygons_of(el: dict) -> list[Polygon]:
    """Polygone eines Weges (geschlossen) oder einer Multipolygon-Relation."""
    if el["type"] == "way":
        c = way_coords(el)
        if len(c) < 4 or not np.allclose(c[0], c[-1]):
            return []
        p = make_valid(Polygon(c))
        return [g for g in getattr(p, "geoms", [p]) if isinstance(g, Polygon) and g.area > 0.5]
    outers, inners = [], []
    for m in el.get("members", []):
        if m.get("type") != "way" or not m.get("geometry"):
            continue
        c = np.array(TO_UTM.transform([p["lon"] for p in m["geometry"]], [p["lat"] for p in m["geometry"]])).T
        if len(c) < 2:
            continue
        (inners if m.get("role") == "inner" else outers).append(LineString(c))
    if not outers:
        return []
    out_polys = list(polygonize(linemerge(outers)))
    in_polys = list(polygonize(linemerge(inners))) if inners else []
    result = []
    for op in out_polys:
        holes = [ip for ip in in_polys if op.contains(ip.representative_point())]
        p = op.difference(unary_union(holes)) if holes else op
        p = make_valid(p)
        result += [g for g in getattr(p, "geoms", [p]) if isinstance(g, Polygon) and g.area > 0.5]
    return result


def num(s, default=None):
    if s is None:
        return default
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(s))
    return float(m.group(0).replace(",", ".")) if m else default


def stable_rand(key: str) -> float:
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Luftbild: Mosaik, Dachfarben
# ---------------------------------------------------------------------------
def build_ortho() -> np.ndarray:
    """Setzt die 500-m-Kacheln zu einem Bild mit 1 Pixel = 0,2 m zusammen (nur als Array, nicht gespeichert)."""
    tiles = sorted(DOP_DIR.glob("dop_*_*.jpg"))
    if not tiles:
        sys.exit("keine Luftbilder")
    n = SIZE // 500
    mosaic = Image.new("RGB", (SIZE * 5, SIZE * 5))
    for f in tiles:
        ix, iy = map(int, f.stem.split("_")[1:])
        im = Image.open(f).convert("RGB")
        mosaic.paste(im, (ix * 2500, (n - 1 - iy) * 2500))
    small = mosaic.resize((4096, 4096), Image.LANCZOS)
    small.save(PROCESSED / "ortho.jpg", quality=92)
    return mosaic  # PIL-Bild, 10000 x 10000


# ---------------------------------------------------------------------------
# Dächer
# ---------------------------------------------------------------------------
def earcut(rings: list[np.ndarray]) -> list[int]:
    verts = np.concatenate(rings).astype(np.float32)
    ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
    return [int(i) for i in mapbox_earcut.triangulate_float32(verts, ends)]


def ring_coords(poly: Polygon) -> list[np.ndarray]:
    rings = [np.array(poly.exterior.coords)[:-1]]
    for h in poly.interiors:
        rings.append(np.array(h.coords)[:-1])
    return rings


PITCHED = {"gabled", "hipped", "pyramidal", "skillion", "half-hipped", "mansard", "gambrel", "round", "dome", "saltbox"}


def roof_mesh(poly: Polygon, eave: float, shape: str, roof_h: float | None, angle: float | None):
    """Erzeugt Dreiecke (x,z,y relativ zu Gebäudebasis in lokalen Koordinaten) für ein Dach.

    Gibt (tris, kind) zurück. tris: flache Liste [x,y,z, x,y,z, ...] in Weltkoordinaten (lokal), y = absolute Höhe über base.
    Für nicht rechteckige Grundrisse: flaches Dach.
    """
    rect = poly.minimum_rotated_rectangle
    fill = poly.area / rect.area if rect.area > 0 else 0
    pitched = shape in PITCHED
    if not pitched or fill < 0.72 or poly.area < 12 or len(poly.interiors) > 0 and fill < 0.9:
        return None
    pts = np.array(rect.exterior.coords)[:-1]
    e01 = pts[1] - pts[0]
    e12 = pts[2] - pts[1]
    l01, l12 = np.hypot(*e01), np.hypot(*e12)
    if l01 >= l12:
        long_vec, short_vec, long_l, short_l = e01 / l01, e12 / l12, l01, l12
    else:
        long_vec, short_vec, long_l, short_l = e12 / l12, e01 / l01, l12, l01
    c = np.array(rect.centroid.coords[0])
    over = 0.25  # Dachüberstand
    hl, hs = long_l / 2 + over, short_l / 2 + over
    ridge_h = roof_h if roof_h else min(7.5, max(1.2, (short_l / 2) * math.tan(math.radians(angle or 38))))

    def P(a, b, y):  # a entlang long, b entlang short
        p = c + long_vec * a + short_vec * b
        return [float(p[0]), y, float(p[1])]

    ridge = eave + ridge_h
    tris = []
    if shape in ("gabled", "saltbox", "gambrel", "mansard", "round"):
        A, B = P(-hl, -hs, eave), P(hl, -hs, eave)
        C, D = P(hl, hs, eave), P(-hl, hs, eave)
        R1, R2 = P(-hl, 0, ridge), P(hl, 0, ridge)
        tris = [A, B, R2, A, R2, R1, D, R1, R2, D, R2, C, A, R1, D, B, C, R2]
    elif shape == "skillion":
        A, B = P(-hl, -hs, eave), P(hl, -hs, eave)
        C, D = P(hl, hs, ridge), P(-hl, hs, ridge)
        tris = [A, B, C, A, C, D]
    elif shape == "pyramidal" or short_l >= long_l * 0.85 or shape == "dome":
        A, B = P(-hl, -hs, eave), P(hl, -hs, eave)
        C, D = P(hl, hs, eave), P(-hl, hs, eave)
        T = P(0, 0, ridge)
        tris = [A, B, T, B, C, T, C, D, T, D, A, T]
    else:  # hipped / half-hipped: Firstlinie verkürzt
        inset = hs * (0.5 if shape == "half-hipped" else 1.0)
        a_r = max(hl - inset, 0.1)
        A, B = P(-hl, -hs, eave), P(hl, -hs, eave)
        C, D = P(hl, hs, eave), P(-hl, hs, eave)
        R1, R2 = P(-a_r, 0, ridge), P(a_r, 0, ridge)
        tris = [A, B, R2, A, R2, R1,  # Süd-/Nordseite
                D, R1, R2, D, R2, C,
                A, R1, D,             # Stirnseite links
                B, C, R2]             # Stirnseite rechts
    flat = [round(v, 2) for p in tris for v in p]
    lx, lz = to_local(float(c[0]), float(c[1]))
    info = {"c": [lx, lz], "u": [round(float(long_vec[0]), 3), round(-float(long_vec[1]), 3)],
            "L": round(float(long_l), 2), "S": round(float(short_l), 2), "rh": round(float(ridge_h), 2), "shape": shape}
    return flat, info


# ---------------------------------------------------------------------------
# Farben
# ---------------------------------------------------------------------------
PLASTER = ["#e7dcc5", "#d9c9a3", "#c9b78f", "#e9e4d8", "#d4cfc4", "#bfae8c", "#e3cfa6", "#cfc3b0",
           "#d8b9a0", "#c5bfb3", "#ece3cf", "#b9a98a"]
SANDSTONE = ["#b8a98c", "#a99b80", "#c2b49a"]
HOUSE_TYPES_LOW = {"house": 7, "detached": 7, "semidetached_house": 8, "terrace": 8, "garage": 3, "garages": 3,
                   "shed": 3, "hut": 3, "roof": 4, "carport": 3, "kiosk": 3, "service": 5, "construction": 6,
                   "greenhouse": 4, "cabin": 4, "bungalow": 5, "static_caravan": 3, "container": 3}


def parse_color(s: str | None):
    if not s:
        return None
    s = s.strip().lower()
    named = {"white": "#f0eee8", "red": "#a84a3a", "brown": "#8a6a50", "grey": "#9a9a98", "gray": "#9a9a98",
             "black": "#3a3a3a", "yellow": "#d8c27a", "beige": "#dccfb0", "green": "#7a8f6a", "blue": "#6f86a0",
             "orange": "#c98a55", "pink": "#d8a8a0", "cream": "#ebe2c8", "tan": "#c9b48e", "sand": "#d6c9a3"}
    if s in named:
        return named[s]
    if re.fullmatch(r"#[0-9a-f]{6}", s):
        return s
    return None


# ---------------------------------------------------------------------------
# Gebäude
# ---------------------------------------------------------------------------
STYLE_PALETTE = {
    # Gründerzeit (Recherche Pieschen/Löbtau/Neustadt): Weiß/Creme/Sandocker/Rosé, vereinzelt Pastellgrün/-blau
    0: ["#edebe4", "#e6d9b8", "#d4b98a", "#e0a5a0", "#ebdfc4", "#e2cf9f", "#efe8da", "#dfb594", "#c5d1b0", "#d9c3a5",
        "#e8d3a3", "#b4c1cf"],
    1: ["#b8a98c", "#a99b80", "#c2b49a", "#b3a58a"],
    # WBS 70 saniert: weiß/hellgrau (unsaniert = Waschbeton macht der Fassaden-Shader je Gebäude)
    2: ["#ecebe6", "#e4e2db", "#f1efe8", "#dcd9d0", "#d4d0c8", "#e9e5d8"],
    # 20er/30er Genossenschafts-Zeilenbau, 50er: Creme/Gelb, gelegentlich Ziegelrot-Töne
    3: ["#efe3b8", "#ebe0c6", "#e8d9a8", "#f0ebd8", "#dcc9a0", "#e5d5b5", "#e9d38f", "#d9b48a"],
    4: ["#6d7b88", "#58656f", "#7c8a96", "#8b95a0", "#4d5963"],
    5: ["#b9b4a8", "#a9a49a", "#c4bdb0", "#9c978d"],
    6: ["#a65a43", "#9a4f3a", "#b0654a", "#8f5a46"],
}


def parse_year(v):
    if not v:
        return None
    m = re.search(r"(1[0-9]{3}|20[0-9]{2})", str(v))
    return int(m.group(1)) if m else None


_YEARS_OK = None


def _era_info(e, n):
    """Baualter/Strukturtyp am Punkt (UTM33) aus tools/build_years.py (Zensus 2022 100-m-Gitter +
    Dresdner Stadtstrukturtypen); None, wenn die Daten fehlen."""
    global _YEARS_OK
    if _YEARS_OK is False:
        return None
    try:
        from build_years import lookup
        info = lookup(e, n)
        _YEARS_OK = True
        return info
    except Exception as ex:
        if _YEARS_OK is None:
            print(f"  Baujahre nicht verfügbar ({ex}) – Stil nur aus Geometrie", flush=True)
        _YEARS_OK = False
        return None


SST_INDUSTRY = {"D41", "A41", "B41", "C41", "D43", "D42"}
SST_PLATTE = {"B13", "B14", "C12"}
SST_ZEILE = {"B12", "B11"}
OLD_TOWN = (410900, 5655500, 412300, 5656800)     # Innere Alt-/Neustadt: Zensus taugt dort nicht (Neumarkt, 50er)


def classify_style(tags, poly, levels, eave, btype, shape, attached=None):
    mat = tags.get("building:material", "")
    sd = parse_year(tags.get("start_date"))
    arch = tags.get("building:architecture", "")
    if btype in ("church", "cathedral", "chapel", "palace", "castle", "monastery", "synagogue", "temple") \
            or tags.get("historic") or "baroque" in arch or "classic" in arch or "renaissance" in arch:
        return 1
    if btype in ("industrial", "warehouse", "garage", "garages", "shed", "hangar", "service", "roof", "carport",
                 "greenhouse", "construction", "container", "kiosk", "hut", "cabin", "barn", "stable", "parking"):
        return 5
    if mat in ("brick", "clinker"):
        return 6
    rect = poly.minimum_rotated_rectangle
    fill = poly.area / rect.area if rect.area > 0 else 0
    pts = np.array(rect.exterior.coords)[:-1]
    e1 = np.hypot(*(pts[1] - pts[0]))
    e2 = np.hypot(*(pts[2] - pts[1]))
    long_l, short_l = max(e1, e2), min(e1, e2)
    pitched = shape in PITCHED
    if mat in ("concrete", "concrete_panel", "panel") or (sd and 1955 <= sd <= 1992):
        return 2
    if long_l / max(short_l, 1) > 3.0 and 8 <= short_l <= 17 and (levels or 0) >= 4 and fill > 0.88 and not pitched:
        return 2
    if btype in ("office", "commercial", "retail", "hotel", "public", "university", "school", "hospital") and (
            (levels or 0) >= 5 or eave >= 18 or (sd and sd >= 1995)):
        return 4
    if sd and sd >= 1995:
        return 4
    if sd and sd < 1925:
        return 0
    lv = levels or max(1, int(round(eave / 3.2)))
    asp = long_l / max(short_l, 1)
    blockrand = attached is not None and attached >= 0.18 and lv <= 7
    # Baualter der Umgebung (Zensus 2022) und Stadtstrukturtyp – ersetzt das Raten, wo es eindeutig ist
    c = poly.centroid
    info = None if sd else _era_info(c.x, c.y)
    if info:
        er = info.get("eras") or {}
        sst = info.get("sst") or ""
        wbs = er.get("ddr_wbs70", 0.0) + er.get("ddr_frueh_60er", 0.0)
        old = er.get("vor1919", 0.0)
        mid = er.get("1919-1949", 0.0)
        new_ = er.get("nachwende", 0.0)
        in_old_town = OLD_TOWN[0] <= c.x <= OLD_TOWN[2] and OLD_TOWN[1] <= c.y <= OLD_TOWN[3]
        residential = btype in ("apartments", "residential", "house", "detached", "terrace", "semidetached_house",
                                "dormitory", "yes", "")
        if sst in SST_INDUSTRY and btype not in ("apartments", "residential", "house", "detached", "terrace") and lv <= 5:
            return 5
        # Plattenbau: Strukturtyp Platte/Gebäudekette oder klar DDR-geprägte Umgebung. Ketten (WBS 70) stehen Wand an
        # Wand – das "Blockrand"-Merkmal darf hier nicht ausschließen, nur bei gemischter Umgebung.
        if not pitched and lv >= 4 and (sst in SST_PLATTE or wbs >= 0.6 or (wbs >= 0.45 and not blockrand)):
            return 2
        if not in_old_town:
            if sst in SST_ZEILE and mid >= 0.3 and not blockrand:
                return 3                     # Genossenschafts-Zeilenbau / Reformstil der 20er/30er
            if new_ >= 0.6 and not pitched and not blockrand and residential:
                return 4                     # Nachwende-Neubau
            if old >= 0.5 and (blockrand or pitched):
                return 0                     # Gründerzeit-Blockrand, Villen, "Kaffeemühlen"
            if mid >= 0.5 and pitched and lv <= 5 and not blockrand:
                return 3
    if not pitched and lv >= 5 and fill > 0.85 and asp > 2.2 and not blockrand:
        return 2
    if not pitched and lv >= 5 and fill > 0.9 and btype in ("apartments", "residential", "dormitory") and not blockrand:
        return 2
    # Ohne Baujahr: Blockrand (Wand an Wand) = Gründerzeit, frei stehende längliche Zeilen = Nachkriegs-Zeilenbau
    if attached is not None:
        if attached >= 0.18 and 2 <= lv <= 6:
            return 0
        if attached < 0.06 and 3 <= lv <= 6 and asp > 2.0 and fill > 0.85 and poly.area > 250:
            return 3
        if attached < 0.06 and pitched and lv <= 3 and poly.area < 450:
            return 0            # Villa/Einzelhaus (Gründerzeit-Ornamentik passt am ehesten)
    p3 = 0.5
    if info and info.get("eras"):
        er = info["eras"]
        o, m = er.get("vor1919", 0.0), er.get("1919-1949", 0.0) + er.get("wiederaufbau_50er", 0.0)
        if o + m > 0.05:
            p3 = m / (o + m)
    if pitched and 3 <= lv <= 5 and fill > 0.8 and poly.area < 900 and not poly.interiors:
        return 3 if stable_rand(str(poly.centroid.x)) < p3 else 0
    if not pitched and lv <= 4 and not sd:
        return 3 if stable_rand(str(poly.centroid.y)) < min(0.9, p3 + 0.1) else 0
    return 0
def roof_color(mosaic, poly):
    roof_col = None
    try:
        inner = poly.buffer(-0.8) if poly.area > 20 else poly
        if inner.is_empty:
            inner = poly
        minx, miny, maxx, maxy = inner.bounds
        px0, px1 = int((minx - MIN_E) * 5), int((maxx - MIN_E) * 5)
        py0, py1 = int((MAX_N - maxy) * 5), int((MAX_N - miny) * 5)
        px0, py0 = max(px0, 0), max(py0, 0)
        px1, py1 = min(px1, SIZE * 5), min(py1, SIZE * 5)
        if px1 - px0 > 2 and py1 - py0 > 2:
            crop = mosaic.crop((px0, py0, px1, py1))
            if crop.width * crop.height > 250_000:
                f = math.sqrt(250_000 / (crop.width * crop.height))
                crop = crop.resize((max(2, int(crop.width * f)), max(2, int(crop.height * f))))
            mask = Image.new("L", crop.size, 0)
            sx, sy = crop.width / (px1 - px0), crop.height / (py1 - py0)
            for r in ring_coords(inner if isinstance(inner, Polygon) else poly):
                pts = [((((e - MIN_E) * 5) - px0) * sx, (((MAX_N - n) * 5) - py0) * sy) for e, n in r]
                ImageDraw.Draw(mask).polygon(pts, fill=255)
            arr = np.asarray(crop, dtype=np.float32)
            m = np.asarray(mask) > 0
            if m.sum() > 4:
                rgb = arr[m].mean(axis=0)
                roof_col = "#%02x%02x%02x" % tuple(int(min(255, v * 1.08)) for v in rgb)
    except Exception:
        roof_col = None

    return roof_col


def build_buildings(mosaic: Image.Image) -> list[dict]:
    elements = load("buildings")
    items = []
    for el in elements:
        tags = el.get("tags", {})
        for poly in polygons_of(el):
            if not poly.intersects(AREA_BOX):
                continue
            poly = poly.simplify(0.15)
            if poly.is_empty or not isinstance(poly, Polygon) or poly.area < 4:
                continue
            items.append((el["id"], tags, poly, "building:part" in tags and "building" not in tags))

    # Elterngebäude entfernen, wenn Teile (building:part) es überwiegend abdecken
    parts = [(i, it) for i, it in enumerate(items) if it[3]]
    drop = set()
    if parts:
        tree = STRtree([it[2] for _, it in parts])
        for i, it in enumerate(items):
            if it[3]:
                continue
            cover = 0.0
            for j in tree.query(it[2]):
                cover += it[2].intersection(parts[j][1][2]).area
            if cover > 0.55 * it[2].area:
                drop.add(i)

    out = []
    for idx, (osm_id, tags, poly, is_part) in enumerate(items):
        if idx in drop:
            continue
        key = f"{osm_id}-{idx}"
        btype = tags.get("building", "yes")
        levels = num(tags.get("building:levels"))
        roof_h = num(tags.get("roof:height"))
        shape = tags.get("roof:shape") or tags.get("building:part:roof:shape") or ""
        height = num(tags.get("height")) or num(tags.get("building:height"))
        if height is None:
            if levels:
                height = levels * 3.1 + (roof_h or 0)
            else:
                height = HOUSE_TYPES_LOW.get(btype, 13.0 + stable_rand(key + "h") * 5)
        eave = height - roof_h if (roof_h and shape in PITCHED) else height
        min_h = num(tags.get("min_height"), 0.0) or ((num(tags.get("building:min_level"), 0.0) or 0.0) * 3.1)
        if min_h >= eave - 1:
            min_h = 0.0
        # Höhenreferenz aus Gelände entlang des Randes
        ring = np.array(poly.exterior.coords)[:-1]
        gh = [ground(e, n) for e, n in ring[:: max(1, len(ring) // 12)]]
        gmin, gmed = min(gh), float(np.median(gh))

        # Dach
        flat_top = True
        roof_tris = None
        if shape in PITCHED and not roof_h:
            roof_h = None
        rres = roof_mesh(poly, eave, shape, roof_h, num(tags.get("roof:angle"))) if shape in PITCHED else None
        roof_tris, rinfo = (rres if rres is not None else (None, None))
        if roof_tris is not None:
            flat_top = False

        rings = ring_coords(poly)
        loc = [[to_local(e, n) for e, n in r] for r in rings]
        # Lokale Koordinaten für Dachdreiecke (x,y,z) -> Spiel-Koordinaten (x, y, z)
        if roof_tris is not None:
            roof_local = []
            for k in range(0, len(roof_tris), 3):
                x, y, z = roof_tris[k:k + 3]
                lx, lz = to_local(x, z)
                roof_local += [lx, y, lz]
            roof_tris = roof_local
        top_idx = earcut([np.array(r) for r in loc]) if flat_top else []

        roof_col = roof_color(mosaic, poly)

        style = classify_style(tags, poly, levels, eave, btype, shape)
        pal = STYLE_PALETTE[style]
        wall = parse_color(tags.get("building:colour")) or pal[int(stable_rand(key + "c") * len(pal)) % len(pal)]
        if style == 1 and not parse_color(tags.get("building:colour")):
            wall = pal[int(stable_rand(key) * len(pal)) % len(pal)]
        cx, cy_ = poly.representative_point().coords[0]
        out.append({
            "id": key,
            "rings": loc,
            "base": round(gmin - 0.4, 2),
            "ref": round(gmed, 2),
            "eave": round(eave, 2),
            "min_h": round(min_h, 2),
            "levels": int(levels) if levels else max(1, int(round(eave / 3.2))),
            "wall": wall,
            "roof_col": parse_color(tags.get("roof:colour")) or roof_col or "#8a6a58",
            "roof": roof_tris,
            "top": top_idx,
            "kind": btype,
            "style": style,
            "rinfo": rinfo,
            "name": tags.get("name", ""),
            "pos": list(to_local(cx, cy_)),
        })
    return out



LOD2_SHAPE = {1000: "flat", 2100: "skillion", 3100: "gabled", 3200: "hipped", 3300: "hipped", 3400: "mansard",
              3500: "mansard", 3600: "hipped", 3700: "pyramidal", 3800: "hipped", 3900: "gabled", 4000: "hipped"}


def _plane_2d(pts3):
    """Projiziert Punkte auf die Hauptebene (größte Normalenkomponente weglassen)."""
    p = np.array(pts3, dtype=float)
    nrm = np.zeros(3)
    for i in range(len(p)):
        a, b = p[i], p[(i + 1) % len(p)]
        nrm += np.array([(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])])
    return nrm


def _tri_poly(ext, holes):
    """Trianguliert ein 3D-Polygon. Gibt (Dreiecke[[3x(e,n,z)]], Normale) zurück."""
    rings3 = [ext] + holes
    nrm = _plane_2d(ext)
    ax = int(np.argmax(np.abs(nrm)))
    if abs(nrm[ax]) < 1e-6:
        return [], nrm
    keep = [i for i in range(3) if i != ax]
    rings2 = [np.array([[p[keep[0]], p[keep[1]]] for p in r]) for r in rings3]
    flat = [p for r in rings3 for p in r]
    try:
        idx = earcut(rings2)
    except Exception:
        return [], nrm
    return [[flat[idx[k]], flat[idx[k + 1]], flat[idx[k + 2]]] for k in range(0, len(idx), 3)], nrm


def _clip_above(poly3, zc):
    out = []
    n = len(poly3)
    for i in range(n):
        a, b = poly3[i], poly3[(i + 1) % n]
        ina, inb = a[2] >= zc, b[2] >= zc
        if ina:
            out.append(a)
        if ina != inb:
            t = (zc - a[2]) / (b[2] - a[2])
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, zc))
    return out


def roof_palette(hexcol, flat, key):
    """Plausible Dachfarbe: Luftbildfarbe nur zur Wahl der Materialklasse (Ziegel/Schiefer/Bitumen)."""
    r = stable_rand(key + "r")
    try:
        c = [int(hexcol[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
    except Exception:
        c = [0.5, 0.4, 0.35]
    lum = 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]
    reddish = c[0] > c[1] * 1.08 and c[0] > c[2] * 1.15
    if flat:
        g = 0.30 + 0.16 * r
        return "#%02x%02x%02x" % (int(g * 255), int(g * 255 * 0.99), int(g * 255 * 0.97))
    if reddish and lum > 0.22:
        base = [(0.52, 0.27, 0.20), (0.46, 0.23, 0.17), (0.58, 0.31, 0.22), (0.40, 0.21, 0.17)][int(r * 4) % 4]
    elif lum < 0.33:
        base = [(0.20, 0.21, 0.24), (0.25, 0.26, 0.29), (0.17, 0.18, 0.20)][int(r * 3) % 3]
    else:
        base = [(0.36, 0.30, 0.27), (0.30, 0.29, 0.29), (0.44, 0.30, 0.24)][int(r * 3) % 3]
    return "#%02x%02x%02x" % tuple(int(min(1.0, v * (0.9 + 0.2 * stable_rand(key + "v"))) * 255) for v in base)


def build_buildings_lod2(mosaic: Image.Image) -> list[dict] | None:
    import lod2
    parts = lod2.read_area(BBOX_UTM)
    if not parts:
        return None
    # OSM-Gebäude liefern Attribute (Typ, Etagen, Farbe, Name, Baujahr ...)
    osm = []
    for el in load("buildings"):
        tags = el.get("tags", {})
        if "building:part" in tags and "building" not in tags:
            continue
        for poly in polygons_of(el):
            if poly.intersects(AREA_BOX) and poly.area > 4:
                osm.append((tags, poly))
    tree = STRtree([p for _, p in osm])
    # Wege/Gleise: ein hochliegendes Bauteil wird nur geöffnet, wenn wirklich etwas darunter hindurchführt
    under = []
    for el in load("roads") + load("rail"):
        t = el.get("tags", {})
        if el["type"] != "way" or not (t.get("highway") or t.get("railway")):
            continue
        c = way_coords(el)
        if len(c) >= 2:
            under.append(LineString(c))
    under_tree = STRtree(under) if under else None

    # Stapelung: GeoSN modelliert große Bauten als übereinandergesetzte BuildingParts (Turmhaube auf Turm,
    # Zwerchhaus auf Flügel). Je GML-Gebäude (id ohne "_n") liegt das unterste Teil am Boden; jedes andere
    # Teil wird um (seine Unterkante - Unterkante des untersten Teils) angehoben.
    def _gid(pid: str) -> str:
        a, _, b = pid.rpartition("_")
        return a if a and b.isdigit() else pid

    def _zref(part):
        zg = [p[2] for ext, _ in part["ground"] for p in ext]
        zw = [p[2] for ext, _ in part["walls"] for p in ext]
        zr = [p[2] for ext, _ in part["roofs"] for p in ext]
        if zg:
            return float(np.median(zg))
        return min(zw) if zw else (min(zr) if zr else None)

    def _foot(part):
        polys = []
        for ext, holes in (part["ground"] or part["roofs"]):
            try:
                pg = Polygon([(p[0], p[1]) for p in ext])
                polys.append(pg if pg.is_valid else make_valid(pg))
            except Exception:
                pass
        if not polys:
            return None
        f = unary_union(polys).buffer(0)
        return None if f.is_empty else f

    stack = {}
    for part in parts:
        if (part.get("function") or "").startswith(("53001_1800", "51009_1700")):
            continue
        z = _zref(part)
        if z is None:
            continue
        stack.setdefault(_gid(part["id"]), []).append((z, part["id"]))
    stack_info = {}       # part id -> (lift, unterstes Teil id, Liste tieferer Teile)
    for gid, lst in stack.items():
        g0, low_id = min(lst)
        for z, pid in lst:
            stack_info[pid] = (z - g0, low_id, [q for zz, q in lst if zz < z - 0.5])
    part_by_id = {p["id"]: p for p in parts}
    low_ref = {}          # unterstes Teil -> DGM-Referenz

    # Anbau-Grad je GML-Gebäude: Anteil des Umrisses, der an andere Gebäude grenzt (Blockrand vs. frei stehend)
    g_feet = {}
    for part in parts:
        if (part.get("function") or "").startswith(("53001_1800", "51009_1700")):
            continue
        if stack_info.get(part["id"], (0.0,))[0] > 1.0:
            continue
        f = _foot(part)
        if f is not None and f.area > 8:
            g_feet.setdefault(_gid(part["id"]), []).append(f)
    gid_list = list(g_feet.keys())
    g_union = [unary_union(g_feet[g]).buffer(0) for g in gid_list]
    g_tree = STRtree(g_union) if g_union else None
    attached = {}
    for gi, gu in enumerate(g_union):
        try:
            per = gu.boundary.length
            if per <= 0:
                continue
            near = [g_union[int(j)] for j in g_tree.query(gu.buffer(0.8)) if int(j) != gi]
            if not near:
                attached[gid_list[gi]] = 0.0
                continue
            shared = gu.boundary.intersection(unary_union(near).buffer(0.8)).length
            attached[gid_list[gi]] = float(min(shared / per, 1.0))
        except Exception:
            pass

    def _low_ref(low_id):
        if low_id not in low_ref:
            f = _foot(part_by_id[low_id])
            if f is None:
                low_ref[low_id] = None
            else:
                g = f if isinstance(f, Polygon) else max([x for x in getattr(f, "geoms", []) if isinstance(x, Polygon)] or [None], key=lambda x: x.area if x else 0)
                if g is None:
                    low_ref[low_id] = None
                else:
                    rr = np.array(g.exterior.coords)[:-1]
                    hs = [ground(e, n) for e, n in rr[:: max(1, len(rr) // 12)]]
                    cp = g.representative_point()
                    hs.append(ground(cp.x, cp.y))
                    low_ref[low_id] = float(np.median(hs))
        return low_ref[low_id]

    # Brandwände: Grundflächen aller bodenstehenden Teile (≥ 2.5 m hoch) – eine Außenkante, die zu ≥ 50 %
    # an ein anderes Teil grenzt (Nachbarhaus oder Nachbarteil desselben Gebäudes), bekommt keine
    # Balkone/Türen (Godot: buildings.gd, Feld "pw" = Kantenmitten).
    pw_feet, pw_ids = [], []
    for part in parts:
        if (part.get("function") or "").startswith(("53001_1800", "51009_1700")):
            continue
        if stack_info.get(part["id"], (0.0,))[0] > 1.0:
            continue
        f = _foot(part)
        if f is None or f.area < 4:
            continue
        zs = [q[2] for ext, _ in part["roofs"] for q in ext]
        z0 = _zref(part)
        if zs and z0 is not None and max(zs) - z0 < 2.5:
            continue
        pw_feet.append(f)
        pw_ids.append(part["id"])
    pw_tree = STRtree(pw_feet) if pw_feet else None

    def _party_edges(pid, foot):
        if pw_tree is None:
            return []
        near = [pw_feet[int(j)] for j in pw_tree.query(foot.buffer(1.0)) if pw_ids[int(j)] != pid]
        if not near:
            return []
        try:
            nb = unary_union(near).buffer(0.6)
        except Exception:
            return []
        res = []
        ext = list(foot.exterior.coords)
        for i in range(len(ext) - 1):
            seg = LineString([ext[i][:2], ext[i + 1][:2]])
            if seg.length < 2.0:
                continue
            try:
                cov = seg.intersection(nb).length / seg.length
            except Exception:
                continue
            if cov >= 0.5:
                mx, mz = to_local((ext[i][0] + ext[i + 1][0]) * 0.5, (ext[i][1] + ext[i + 1][1]) * 0.5)
                res.append([round(mx, 2), round(mz, 2)])
        return res

    out = []
    for pi, part in enumerate(parts):
        if (part.get("function") or "").startswith(("53001_1800", "51009_1700")):
            continue   # Brücken/Überführungen: übernimmt die Brückengeometrie aus OSM
        if (part.get("function") or "").startswith(("51002_1251", "51002_1260")):
            continue   # Freileitungs-/Funkmasten: LoD2 führt sie als massive Prismen (graue "Türme" in der Landschaft)
        lift, low_id, lower_ids = stack_info.get(part["id"], (0.0, part["id"], []))
        stacked = lift > 1.0
        # Grundfläche
        polys = []
        for ext, holes in part["ground"]:
            pg = Polygon([(p[0], p[1]) for p in ext], [[(p[0], p[1]) for p in h] for h in holes])
            if not pg.is_valid:
                pg = make_valid(pg)
            polys.append(pg)
        if not polys:
            for ext, holes in part["roofs"]:
                pg = Polygon([(p[0], p[1]) for p in ext])
                polys.append(pg if pg.is_valid else make_valid(pg))
        if not polys:
            continue
        foot = unary_union(polys).buffer(0)
        if foot.is_empty:
            continue
        if not isinstance(foot, Polygon):
            gs = [g for g in getattr(foot, "geoms", []) if isinstance(g, Polygon)]
            if not gs:
                continue
            foot = max(gs, key=lambda g: g.area)
        foot = foot.simplify(0.1)
        # aufgesetzte Teile dürfen klein sein (Laternen, Turmspitzen)
        if not isinstance(foot, Polygon) or foot.area < (1.0 if stacked else 4.0) or not foot.intersects(AREA_BOX):
            continue
        rp = foot.representative_point()
        if not TILE_BOX.contains(rp):
            continue

        zs_ground = [p[2] for ext, _ in part["ground"] for p in ext]
        zs_roof = [p[2] for ext, _ in part["roofs"] for p in ext]
        zs_wall = [p[2] for ext, _ in part["walls"] for p in ext]
        if not zs_roof:
            continue
        zref = float(np.median(zs_ground)) if zs_ground else (min(zs_wall) if zs_wall else min(zs_roof))
        roof_min = min(zs_roof)
        roof_max = max(zs_roof)
        eave = max(2.4, roof_min - zref)
        ridge_h = max(0.0, roof_max - roof_min)
        rt = part["roof_type"]
        shape = LOD2_SHAPE.get(rt, "gabled" if ridge_h > 1.5 else "flat")
        if ridge_h < 1.0:
            shape = "flat"

        tags = {}
        for j in tree.query(rp):
            if osm[j][1].contains(rp):
                tags = osm[j][0]
                break
        btype = tags.get("building", "yes")
        fn = part.get("function") or ""
        if btype == "yes":
            if fn.startswith("31001_2"):
                btype = "commercial"
            elif fn.startswith("31001_3"):
                btype = "public"
        levels = num(tags.get("building:levels")) or part.get("storeys")
        key = f"{part['id']}"

        ring = np.array(foot.exterior.coords)[:-1]
        gh = [ground(e, n) for e, n in ring[:: max(1, len(ring) // 12)]]
        cpt = foot.representative_point()
        gh.append(ground(cpt.x, cpt.y))
        gmin, gmed = min(gh), float(np.median(gh))
        # Hochliegendes Bauteil (Übergang, Durchfahrt-Überbau, Erker): LoD2-Unterkante überall > 2 m über dem
        # Gelände -> Wände beginnen dort (nicht am Boden), Unterseite wird geschlossen, darunter bleibt frei.
        ref_out, base_out = gmed, gmin - 0.4
        elevated = False
        if PLAT is not None and not stacked:
            pv = [platform_at(e, n) for e, n in ring[:: max(1, len(ring) // 12)]]
            pv = [v for v in pv if np.isfinite(v)]
            zr = zref - BASE_HEIGHT
            if pv and abs(zr - float(np.median(pv))) < 2.0 and zr > gmed + 1.0:
                ref_out = zr            # Gebäude steht auf der Terrasse (LoD2-Boden), Wände reichen bis unten
        if stacked:
            lr = _low_ref(low_id)
            if lr is not None:
                ref_out = lr + lift
                base_out = ref_out
                # nichts darunter (kein tieferes Teil desselben Gebäudes) -> echter Überbau: unten offen
                cov = 0.0
                for q in lower_ids:
                    fq = _foot(part_by_id[q])
                    if fq is not None:
                        try:
                            cov += fq.intersection(foot).area
                        except Exception:
                            pass
                elevated = cov < 0.5 * foot.area
            else:
                stacked = False
        if not stacked and (zref - BASE_HEIGHT) > max(gh) + 2.0:
            # einzelnes hochliegendes Teil, unter dem ein Weg hindurchführt
            core = foot.buffer(-0.3)
            elevated = under_tree is not None and not core.is_empty and any(
                under[int(i)].intersects(core) for i in under_tree.query(core))
            if elevated:
                ref_out = base_out = zref - BASE_HEIGHT

        # Dachdreiecke (lokal, y relativ zur Referenz)
        tris = []
        for ext, holes in part["roofs"]:
            ts, nrm = _tri_poly(ext, holes)
            if not ts:
                continue
            nl = np.array([nrm[0], nrm[2], -nrm[1]])  # lokal: x, y(hoch), z=-Nord
            if nl[1] < -0.05 * np.linalg.norm(nl):
                nl = -nl   # Dachflächen zeigen nach oben/außen
            nl = nl / (np.linalg.norm(nl) + 1e-9)
            for t in ts:
                loc = []
                for e, n, z in t:
                    lx, lz = to_local(e, n)
                    loc.append(np.array([lx, z - zref, lz]))
                a, b, c = loc
                if -np.cross(b - a, c - a).dot(nl) < 0:
                    b, c = c, b
                for v in (a, b, c):
                    tris += [round(float(v[0]), 2), round(float(v[1]), 2), round(float(v[2]), 2)]
        if len(tris) < 9:
            continue
        if elevated:
            # Unterseite (nach unten zeigend) auf Höhe der Unterkante
            for r_ in ring_coords(foot)[:1]:
                loc = [to_local(e, n) for e, n in r_]
                idx_ = earcut([np.array(loc)])
                for t in range(0, len(idx_) - 2, 3):
                    a, b, c = (np.array([loc[idx_[t + k]][0], 0.0, loc[idx_[t + k]][1]]) for k in range(3))
                    if (-np.cross(b - a, c - a))[1] > 0:
                        b, c = c, b
                    for v in (a, b, c):
                        tris += [round(float(v[0]), 2), 0.0, round(float(v[2]), 2)]

        # Giebel: Wandteile oberhalb der Traufe
        gables = []
        zc = zref + eave + 0.05
        for ext, holes in part["walls"]:
            if max(p[2] for p in ext) <= zc + 0.1:
                continue
            clip = _clip_above(ext, zc)
            if len(clip) < 3:
                continue
            ts, nrm = _tri_poly(clip, [])
            nh = np.array([nrm[0], -nrm[1]])
            ln = np.linalg.norm(nh)
            if ln < 1e-6:
                continue
            nh = nh / ln
            for t in ts:
                gables += [round(float(nh[0]), 3), round(float(nh[1]), 3)]
                for e, n, z in t:
                    lx, lz = to_local(e, n)
                    gables += [round(lx, 2), round(float(z - zref), 2), round(lz, 2)]

        rings = ring_coords(foot)
        loc_rings = [[to_local(e, n) for e, n in r] for r in rings]

        # Gauben-Info (Rechteck-Näherung) für einfache Sattel-/Walmdächer
        rinfo = None
        rect = foot.minimum_rotated_rectangle
        fill = foot.area / rect.area if rect.area > 0 else 0
        if shape in ("gabled", "hipped") and fill > 0.72 and ridge_h >= 2.0 and foot.area >= 12:
            pts = np.array(rect.exterior.coords)[:-1]
            e01, e12 = pts[1] - pts[0], pts[2] - pts[1]
            l01, l12 = float(np.hypot(*e01)), float(np.hypot(*e12))
            lv, ll, ss = (e01 / l01, l01, l12) if l01 >= l12 else (e12 / l12, l12, l01)
            c = rect.centroid.coords[0]
            lx, lz = to_local(c[0], c[1])
            rinfo = {"c": [lx, lz], "u": [round(float(lv[0]), 3), round(-float(lv[1]), 3)], "L": round(ll, 2),
                     "S": round(ss, 2), "rh": round(ridge_h, 2), "shape": shape}

        _rc = OVERRIDES.get("lod2_roof_colour", {})
        roof_override = _rc.get(part["id"])           # nur genau das genannte Teil
        pitched = shape in PITCHED
        style = classify_style(tags, foot, levels, eave, btype, shape if pitched else "flat",
                               attached=attached.get(_gid(part["id"])))
        pal = STYLE_PALETTE[style]
        wall = parse_color(tags.get("building:colour")) or pal[int(stable_rand(key + "c") * len(pal)) % len(pal)]
        if style == 1 and not parse_color(tags.get("building:colour")):
            wall = pal[int(stable_rand(key) * len(pal)) % len(pal)]
        cx, cy_ = rp.coords[0]
        out.append({
            "id": key, "rings": loc_rings,
            "base": round(base_out, 2), "ref": round(ref_out, 2), "elev": bool(elevated), "stacked": bool(stacked),
            "gid": _gid(part["id"]),
            "eave": round(eave, 2), "min_h": 0.0,
            "levels": int(levels) if levels else max(1, int(round(eave / 3.2))),
            "wall": wall, "roof_col": (roof_override or {}).get("colour") or parse_color(tags.get("roof:colour")) or roof_palette(roof_color(mosaic, foot) or "#806050", shape == "flat", key),
            "roof": tris, "top": [], "kind": btype, "style": style, "rinfo": rinfo, "lod2": True, "gables": gables,
            "name": tags.get("name", ""), "pos": list(to_local(cx, cy_)),
            "hn": str(tags.get("addr:housenumber", ""))[:6] if not stacked else "",
            "pw": _party_edges(part["id"], foot) if not stacked and not elevated else [],
            "_tags": tags, "_shape": shape, "_foot": foot, "_wall_tag": bool(parse_color(tags.get("building:colour"))),
        })
    unify_group_styles(out, attached)
    out += osm_elevated_buildings(out)
    return out


def unify_group_styles(out, attached):
    """Ein Gebäude = ein Stil. LoD2 zerlegt Häuser in Teile (z. B. Mansarddach-Teil + Flachdach-Teil); einzeln
    klassifiziert bekäme der Flachdach-Teil leicht 'Plattenbau'. Der Stil wird deshalb für die ganze Gruppe
    (gid) aus der vereinigten Grundfläche bestimmt: geneigt, wenn geneigte Teile >= 25 % der Fläche haben."""
    from collections import defaultdict
    groups = defaultdict(list)
    for o in out:
        groups[o["gid"]].append(o)
    for gid, lst in groups.items():
        if len(lst) >= 2:
            areas = [o["_foot"].area for o in lst]
            tot = sum(areas) or 1.0
            pitched_share = sum(a for o, a in zip(lst, areas) if o["_shape"] in PITCHED) / tot
            main = lst[int(np.argmax(areas))]
            try:
                union = unary_union([o["_foot"] for o in lst])
                if not isinstance(union, Polygon):
                    union = max(getattr(union, "geoms", [union]), key=lambda g: g.area)
            except Exception:
                union = main["_foot"]
            style = classify_style(main["_tags"], union, max(o["levels"] for o in lst), max(o["eave"] for o in lst),
                                   main["kind"], "gabled" if pitched_share >= 0.25 else "flat",
                                   attached=attached.get(gid))
            if any(o["style"] == 1 for o in lst):
                style = 1
            pal = STYLE_PALETTE[style]
            wall = main["wall"] if main["style"] == style else pal[int(stable_rand(gid + "c") * len(pal)) % len(pal)]
            for o in lst:
                o["style"] = style
                if not o["_wall_tag"]:
                    o["wall"] = wall
        for o in lst:
            for k in ("_tags", "_shape", "_foot", "_wall_tag"):
                o.pop(k, None)


def osm_elevated_buildings(existing):
    """OSM-Gebäude, die in der Luft hängen (building=bridge, min_height), aber in LoD2 fehlen:
    hochliegender Block mit offener Unterseite. Höhen ggf. aus overrides.json."""
    ov = OVERRIDES.get("osm_elevated", {})
    have = []
    for b in existing:
        try:
            have.append(Polygon(b["rings"][0]))
        except Exception:
            pass
    have_tree = STRtree(have) if have else None
    res = []
    for el in load("buildings"):
        t = el.get("tags", {})
        o = ov.get(str(el["id"]), {})
        if t.get("building") != "bridge" and not o:
            continue
        for poly in polygons_of(el):
            if not poly.is_valid or poly.area < 6 or not TILE_BOX.contains(poly.representative_point()):
                continue
            loc = Polygon([to_local(e, n) for e, n in poly.exterior.coords])
            if have_tree is not None:
                ov_area = sum(have[int(i)].intersection(loc).area for i in have_tree.query(loc) if have[int(i)].is_valid)
                if ov_area > 0.3 * loc.area and not o:
                    continue
            h0 = float(o.get("min_height", num(t.get("min_height"), 0.0) or 0.0))
            h1 = float(o.get("height", num(t.get("height"), h0 + 3.5) or (h0 + 3.5)))
            if h0 < 2.0 or h1 <= h0 + 1.0:
                continue
            ring = np.array(poly.exterior.coords)[:-1]
            gmed = float(np.median([ground(e, n) for e, n in ring]))
            r_loc = [list(to_local(e, n)) for e, n in ring]
            idx = earcut([np.array(r_loc)])
            tris = []
            for k in range(0, len(idx) - 2, 3):
                a, b, c = (np.array([r_loc[idx[k + q]][0], 0.0, r_loc[idx[k + q]][1]]) for q in range(3))
                for yv, up in ((h1 - h0, True), (0.0, False)):
                    aa, bb, cc = a.copy(), b.copy(), c.copy()
                    aa[1] = bb[1] = cc[1] = yv
                    fy = (-np.cross(bb - aa, cc - aa))[1]
                    if (fy < 0) == up:
                        bb, cc = cc, bb
                    for v in (aa, bb, cc):
                        tris += [round(float(v[0]), 2), round(float(v[1]), 2), round(float(v[2]), 2)]
            cpt = poly.representative_point()
            res.append({
                "id": f"osm{el['id']}", "rings": [r_loc], "base": round(gmed + h0, 2), "ref": round(gmed + h0, 2),
                "elev": True, "stacked": False, "gid": f"osm{el['id']}",
                "eave": round(h1 - h0, 2), "min_h": 0.0, "levels": 1, "wall": o.get("colour", "#d2c5a6"),
                "roof_col": o.get("roof_colour", "#6f7f88"), "roof": tris, "top": [], "kind": "bridge", "style": 1,
                "rinfo": None, "lod2": True, "gables": [], "name": t.get("name", ""), "pos": list(to_local(cpt.x, cpt.y)),
            })
    if res:
        print(f"  {len(res)} hochliegende OSM-Bauten (building=bridge)", flush=True)
    return res


# ---------------------------------------------------------------------------
# Straßen
# ---------------------------------------------------------------------------
DRIVE = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
         "service", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}
WALK = {"footway", "path", "pedestrian", "cycleway", "steps", "bridleway", "track"}
WIDTH = {"motorway": 14, "trunk": 12, "primary": 11, "secondary": 9.5, "tertiary": 7.5, "unclassified": 6.0,
         "residential": 6.0, "living_street": 5.0, "service": 3.5, "motorway_link": 6, "trunk_link": 6,
         "primary_link": 5.5, "secondary_link": 5.5, "tertiary_link": 5, "footway": 2.0, "path": 1.5,
         "pedestrian": 5.0, "cycleway": 2.0, "steps": 2.0, "bridleway": 2.0, "track": 3.0}
SPEED = {"motorway": 100, "trunk": 70, "primary": 50, "secondary": 50, "tertiary": 50, "unclassified": 30,
         "residential": 30, "living_street": 10, "service": 15, "motorway_link": 50, "trunk_link": 50,
         "primary_link": 40, "secondary_link": 40, "tertiary_link": 40}


def road_width(tags: dict) -> float:
    """Fahrbahnbreite inkl. Parkstreifen auf der Fahrbahn (parking:*=lane/half_on_kerb, siehe parking.py)."""
    cls = tags["highway"]
    ov = OVERRIDES.get("road_width", {}).get(str(tags.get("_id")))
    if ov:
        return float(ov)
    w = num(tags.get("width"))
    pl, pr = lane_widths(park_sides(tags)) if cls in DRIVE else (0.0, 0.0)
    oneway = tags.get("oneway") in ("yes", "1", "true", "-1") or tags.get("junction") == "roundabout"
    if w:
        w = max(1.0, min(w, 30))
        if cls in DRIVE and pl + pr > 0:
            w = max(w, pl + pr + (3.0 if oneway else 5.0))
        return w
    lanes = num(tags.get("lanes"))
    base = WIDTH.get(cls, 4.0)
    if lanes and cls in DRIVE:
        base = max(base, lanes * 3.1)
    if oneway and cls in DRIVE and not lanes:
        base = max(3.2, base * 0.7)
    est = base + pl + pr
    if cls in DRIVE and tags.get("_id") is not None:
        # gemessen/aus dem echten Straßenraum abgeleitet (tools/strassenraum.py, ALKIS + OSM), mit Plausibilitätsgrenzen
        from width_override import measured
        m = measured(tags["_id"], est)
        if m:
            return m
    return est


SURFACE_CLASS = {"sett": "pflaster", "cobblestone": "kopfstein", "unhewn_cobblestone": "kopfstein",
                 "paving_stones": "pflaster", "concrete:plates": "pflaster", "grass_paver": "pflaster",
                 "unpaved": "unbefestigt", "gravel": "unbefestigt", "fine_gravel": "unbefestigt", "compacted": "unbefestigt",
                 "dirt": "unbefestigt", "ground": "unbefestigt", "grass": "unbefestigt"}


def road_park(tags: dict):
    """(Seiten-Infos, Parkstreifenbreite links, rechts) – JSON-tauglich."""
    sides = park_sides(tags)
    pl, pr = lane_widths(sides)
    js = {k: (list(v) if isinstance(v, tuple) else v) for k, v in sides.items()}
    return js, pl, pr



OVERRIDES = json.loads((Path(__file__).resolve().parent / "overrides.json").read_text()) \
    if (Path(__file__).resolve().parent / "overrides.json").exists() else {}
GLOBAL_BRIDGES = json.loads((RAW / "bridge_heights.json").read_text()) if (RAW / "bridge_heights.json").exists() else {}


def carve_under_bridges():
    """Das DGM enthält oft die Brückenplatte als Boden. Unter der Brücke wird das Gelände auf die Höhe der
    Ränder abgesenkt (Brückenenden bleiben unberührt), damit darunter Platz für Weg/Straße/Gleis ist."""
    mask = Image.new("L", (SIZE, SIZE), 0)
    dr = ImageDraw.Draw(mask)
    deck = np.full((SIZE, SIZE), np.inf, dtype=np.float32)
    n_b = 0
    items = []
    for name, key in (("roads", "r"), ("rail", "t")):
        for el in load(name):
            t = el.get("tags", {})
            if el["type"] != "way" or t.get("tunnel") == "yes":
                continue
            if name == "roads" and not (t.get("highway") and t.get("bridge") not in (None, "no") and "bridge" in t):
                continue
            if name == "rail" and not (t.get("railway") in ("tram", "rail", "light_rail") and "bridge" in t and t["bridge"] != "no"):
                continue
            ys = GLOBAL_BRIDGES.get(f"{key}{el['id']}")
            c = way_coords(el)
            if ys is None or len(c) < 2 or len(ys) != len(c):
                continue
            line = LineString(c)
            if not line.intersects(AREA_BOX) or line.length < 14:
                continue
            w = road_width(t) if name == "roads" else 4.0
            items.append((line, ys, w))
    if not items:
        return
    for line, ys, w in items:
        L = line.length
        core = LineString([line.interpolate(d) for d in np.linspace(5.0, L - 5.0, max(2, int(L / 4)))])
        poly = core.buffer(w / 2 + 2.5, cap_style="flat")
        for g in getattr(poly, "geoms", [poly]):
            if not isinstance(g, Polygon):
                continue
            dr.polygon([(e - MIN_E, MAX_N - n) for e, n in g.exterior.coords], fill=255)
        n_b += 1
    m = np.asarray(mask) > 0
    if not m.any():
        return
    # Höhen von außen nach innen fortpflanzen (Flutung, 4er-Nachbarschaft)
    val = np.where(m, np.nan, TERRAIN).astype(np.float32)
    for _ in range(40):
        unknown = np.isnan(val)
        if not unknown.any():
            break
        acc = np.zeros_like(val)
        cnt = np.zeros_like(val)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sh = np.roll(val, (dy, dx), axis=(0, 1))
            ok = ~np.isnan(sh)
            acc += np.where(ok, sh, 0.0)
            cnt += ok
        fill = unknown & (cnt > 0)
        val[fill] = acc[fill] / cnt[fill]
    val = np.where(np.isnan(val), TERRAIN, val)
    for _ in range(3):   # glätten, nur innerhalb der Maske
        sm = (val + np.roll(val, 1, 0) + np.roll(val, -1, 0) + np.roll(val, 1, 1) + np.roll(val, -1, 1)) / 5.0
        val = np.where(m, sm, val)
    TERRAIN[m] = np.minimum(TERRAIN[m], val[m])
    print(f"  Gelände unter {n_b} Brücken abgesenkt ({int(m.sum())} m²)", flush=True)



BRIDGE_FN = ("53001_1800", "51009_1700")


def _oriented_tris(polys, zref_unused=0.0):
    """Trianguliert 3D-Polygone (UTM, z absolut) -> flache Liste lokaler Dreiecke [x, y, z, ...] mit y = z - base.
    Windung so, dass Godots Vorderseite = Außenseite (nach CityGML-Normale)."""
    out = []
    utm = []
    for ext, holes in polys:
        ts, nrm = _tri_poly(ext, holes)
        if not ts:
            continue
        nl = np.array([nrm[0], nrm[2], -nrm[1]])
        nl = nl / (np.linalg.norm(nl) + 1e-9)
        for t in ts:
            loc = []
            for e, n, z in t:
                lx, lz = to_local(e, n)
                loc.append(np.array([lx, z - BASE_HEIGHT, lz]))
            a, b, c = loc
            if -np.cross(b - a, c - a).dot(nl) < 0:
                b, c = c, b
            for v in (a, b, c):
                out += [round(float(v[0]), 2), round(float(v[1]), 2), round(float(v[2]), 2)]
            utm.append([(p[0], p[1], p[2]) for p in t])
    return out, utm


def bridge_lines():
    """OSM-Brückenwege (Straße/Gleis/Weg) als [(coords UTM ndarray, Breite)]."""
    res = []
    for name in ("roads", "rail"):
        for el in load(name):
            t = el.get("tags", {})
            if el["type"] != "way" or t.get("tunnel") == "yes" or "bridge" not in t or t["bridge"] == "no":
                continue
            if name == "roads" and not t.get("highway"):
                continue
            if name == "rail" and t.get("railway") not in ("tram", "rail", "light_rail"):
                continue
            c = way_coords(el)
            if len(c) >= 2 and LineString(c).intersects(AREA_BOX):
                res.append((c, road_width(t) if name == "roads" else 4.0))
    return res


def _dip_fix(part):
    """LoD2-Brückenteil mit Knick im Deck (Datenfehler, overrides.json bridge_part_dip_fix): Querschnitte, deren
    Oberkante mehr als 0,5 m unter der Geraden zwischen den Deckhöhen an beiden Enden liegt, anheben."""
    allp = [q for ext, holes in part["roofs"] + part["walls"] + part["ground"] for q in ext]
    if len(allp) < 6:
        return part
    P = np.array([(q[0], q[1]) for q in allp])
    c = P.mean(axis=0)
    ev, evec = np.linalg.eigh(np.cov((P - c).T))
    ax = evec[:, 1]
    tops = [(float((q[0] - c[0]) * ax[0] + (q[1] - c[1]) * ax[1]), q[2]) for ext, _ in part["roofs"] for q in ext]
    if len(tops) < 6:
        return part
    us = np.array([t[0] for t in tops])
    zs = np.array([t[1] for t in tops])
    u0, u1 = float(us.min()), float(us.max())
    L = max(u1 - u0, 1.0)
    a = zs[us < u0 + 0.15 * L]
    b = zs[us > u1 - 0.15 * L]
    if len(a) == 0 or len(b) == 0:
        return part
    za, zb = float(np.percentile(a, 80)), float(np.percentile(b, 80))
    # Oberkante je 4-m-Abschnitt
    bins = {}
    for u, z in zip(us, zs):
        k = int((u - u0) // 4.0)
        bins[k] = max(bins.get(k, -1e9), z)

    def delta(q):
        u = float((q[0] - c[0]) * ax[0] + (q[1] - c[1]) * ax[1])
        k = int((u - u0) // 4.0)
        top = max(bins.get(k, -1e9), bins.get(k - 1, -1e9), bins.get(k + 1, -1e9))
        target = za + (zb - za) * min(max((u - u0) / L, 0.0), 1.0)
        d = target - top
        return d if (top > -1e8 and d > 0.5) else 0.0

    def mv(polys):
        return [([(q[0], q[1], q[2] + delta(q)) for q in ext], [[(q[0], q[1], q[2] + delta(q)) for q in hh] for hh in holes])
                for ext, holes in polys]
    def mv_top(polys):
        # Oberkante eckenweise: Dreiecke spannen im Knick hohe und tiefe Ecken an derselben Stelle
        def up(q):
            u = float((q[0] - c[0]) * ax[0] + (q[1] - c[1]) * ax[1])
            target = za + (zb - za) * min(max((u - u0) / L, 0.0), 1.0)
            return (q[0], q[1], target) if target - q[2] > 0.5 else q
        return [([up(q) for q in ext], [[up(q) for q in hh] for hh in holes]) for ext, holes in polys]
    def target_of(qq):
        u = float((qq[0] - c[0]) * ax[0] + (qq[1] - c[1]) * ax[1])
        return za + (zb - za) * min(max((u - u0) / L, 0.0), 1.0)
    # Seitenwände, die tiefer als jede Deckdicke unter die Soll-Linie reichen, gehören zum Knick -> weglassen
    walls = [(ext, holes) for ext, holes in part["walls"] if max(target_of(qq) - qq[2] for qq in ext) <= 6.0]
    q = dict(part)
    q["roofs"], q["walls"], q["ground"] = mv_top(part["roofs"]), mv(walls), mv(part["ground"])
    print(f"  Brücke {part['id']}: Knick im Deck begradigt (Enden {za:.1f} / {zb:.1f} m)", flush=True)
    return q


def collect_bridges():
    """Brücken aus LoD2 (Bauwerke 53001_1800 / 51009_1700), Höhen per DOM1 korrigiert (bridge_fix).
    Gibt (meshes, rails, deck, deck_win) zurück: meshes nur für Teile dieser Kachel; deck = (SIZE,SIZE)-Raster der
    Fahrbahnoberkante relativ base_height (NaN = keine Brücke); deck_win = (hi, lo, x0, ytop) für das Profil-Fenster."""
    import lod2
    from bridge_fix import correct_parts
    win = (MIN_E - RS_PAD, MIN_N - RS_PAD, MAX_E + RS_PAD, MAX_N + RS_PAD)
    skip = set(OVERRIDES.get("skip_bridge_parts", []))      # z. B. abgerissene Carolabrücke
    parts = [p for p in lod2.read_bridges(win) if p.get("id") not in skip]
    dip = set(OVERRIDES.get("bridge_part_dip_fix", []))
    if dip:
        parts = [_dip_fix(p) if p.get("id") in dip else p for p in parts]
    parts = correct_parts(parts, DOM, _oriented_tris)
    tris = []
    for p in parts:
        _, utm = _oriented_tris(p["roofs"])
        tris += [[(q[0], q[1], q[2] - BASE_HEIGHT) for q in t] for t in utm]
    wn = int(win[2] - win[0])
    hi_w, lo_w = raster_tris(tris, win[0], win[3], wn, wn)
    pad = int(RS_PAD)
    deck = hi_w[pad:pad + SIZE, pad:pad + SIZE].copy()
    deck_lo = lo_w[pad:pad + SIZE, pad:pad + SIZE].copy()
    meshes = []
    deck_polys = []
    for p in parts:
        top, _ = _oriented_tris(p["roofs"])
        for ext, holes in p["roofs"]:
            try:
                pg = Polygon([(q[0], q[1]) for q in ext])
                deck_polys.append(pg if pg.is_valid else make_valid(pg))
            except Exception:
                pass
        # Eigentum: nur Einheiten mit Schwerpunkt in dieser Kachel erzeugen Mesh
        allp = [q for ext, _ in p["roofs"] + p["walls"] for q in ext]
        if not allp:
            continue
        cx = sum(q[0] for q in allp) / len(allp)
        cy = sum(q[1] for q in allp) / len(allp)
        if not TILE_BOX.contains(Point(cx, cy)):
            continue
        side, _ = _oriented_tris(p["walls"])
        bot, _ = _oriented_tris(p["ground"])
        meshes.append({"id": p["id"], "top": top, "side": side, "bot": bot})
    # Geländer entlang der Außenkanten der Deckflächen (nur lange Kanten parallel zur Fahrtrichtung)
    rails = []
    blines = [(LineString(c), c) for c, _w in bridge_lines()]
    if deck_polys:
        try:
            uni = unary_union([g.buffer(0.05) for g in deck_polys]).buffer(-0.05)
        except Exception:
            uni = None
        if uni is not None and not uni.is_empty:
            for g in getattr(uni, "geoms", [uni]):
                if not isinstance(g, Polygon):
                    continue
                g = g.simplify(0.25)
                cs = list(g.exterior.coords)
                for i in range(len(cs) - 1):
                    (x0, y0), (x1, y1) = cs[i], cs[i + 1]
                    L = math.hypot(x1 - x0, y1 - y0)
                    if L < 6.0:
                        continue
                    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
                    if not TILE_BOX.contains(Point(mx, my)):
                        continue
                    # nur Kanten parallel zur nächsten Brückenachse (keine Querabschlüsse an den Enden)
                    best = None
                    for ls, cc in blines:
                        dd = ls.distance(Point(mx, my))
                        if best is None or dd < best[0]:
                            best = (dd, ls)
                    if best is None or best[0] > 30.0:
                        continue
                    sp = best[1].project(Point(mx, my))
                    a_ = best[1].interpolate(max(sp - 1.0, 0.0))
                    b_ = best[1].interpolate(min(sp + 1.0, best[1].length))
                    tx, ty = b_.x - a_.x, b_.y - a_.y
                    tl = math.hypot(tx, ty)
                    if tl < 1e-6 or abs(((x1 - x0) * tx + (y1 - y0) * ty) / (L * tl)) < 0.85:
                        continue
                    ix, iy = int(mx - MIN_E), int(MAX_N - my)
                    h = deck[iy, ix] if 0 <= ix < SIZE and 0 <= iy < SIZE else np.nan
                    if not np.isfinite(h):
                        continue
                    a = to_local(x0, y0)
                    b = to_local(x1, y1)
                    rails.append([a[0], a[1], b[0], b[1], round(float(h), 2)])
    global DECK_LO
    DECK_LO = deck_lo
    return meshes, rails, deck, (hi_w, lo_w, win[0], win[3])


DECK = None
DECK_LO = None
DOM = DomMosaic()
PLAT = None          # Plattformhöhe (Terrassen/Bastionen), NaN = keine


def detect_platforms():
    """Terrassen/Bastionen, die im DGM fehlen (platforms.py); hebt TERRAIN an, schreibt platform.f32."""
    import lod2
    from platforms import WALL_KINDS, detect
    e_km, n_km = int(MIN_E // 1000), int(MIN_N // 1000)
    dom = DOM._tile(e_km, n_km)
    walls = []
    for el in load("barriers"):
        t = el.get("tags", {})
        if el["type"] == "way" and t.get("barrier") in WALL_KINDS and el["id"] not in OVERRIDES.get("skip_barriers", []):
            c = way_coords(el)
            if len(c) >= 2:
                walls.append(c)
    im = Image.new("L", (SIZE, SIZE), 0)
    dr = ImageDraw.Draw(im)
    for part in lod2.read_area(BBOX_UTM):
        for ext, _h in part["roofs"] + part["ground"]:
            pts = [(q[0] - MIN_E, MAX_N - q[1]) for q in ext]
            if len(pts) >= 3:
                dr.polygon(pts, fill=255)
    # Wasser und OSM-Gebäude (auch neue, die noch nicht im LoD2 sind – deren Flachdach ist keine Terrasse)
    for el in load("water") + load("buildings"):
        for pg in polygons_of(el):
            for g in getattr(pg, "geoms", [pg]):
                if isinstance(g, Polygon) and g.intersects(AREA_BOX):
                    dr.polygon([(e - MIN_E, MAX_N - n) for e, n in g.exterior.coords], fill=255)
    block = np.asarray(im) > 0
    if DECK is not None:
        from scipy.ndimage import binary_dilation
        block |= binary_dilation(np.isfinite(DECK), iterations=3)
    plat = detect(TERRAIN, dom, MIN_E, MAX_N, walls, block, log=lambda m: print(m, flush=True))
    m = np.isfinite(plat)
    TERRAIN[m] = np.maximum(TERRAIN[m], plat[m])
    # atomar schreiben: Nachbarkacheln lesen die Datei parallel (sonst halbe Datei gelesen)
    _tmp = PROCESSED / "platform.f32.tmp"
    _tmp.write_bytes(plat.astype("<f4").tobytes())
    _tmp.replace(PROCESSED / "platform.f32")
    return plat


def platform_at(e, n):
    if PLAT is None:
        return np.nan
    c, r = int(e - MIN_E), int(MAX_N - n)
    if 0 <= c < SIZE and 0 <= r < SIZE:
        return float(PLAT[r, c])
    return np.nan


SURF_SKIP = {"corridor", "elevator", "construction", "proposed", "planned", "platform", "bus_stop", "abandoned",
             "razed", "disused"}


def _is_bridge(t: dict) -> bool:
    return "bridge" in t and t["bridge"] not in ("no",)


def _road_skipped(t: dict, coords) -> bool:
    cls = t.get("highway")
    if cls is None or cls in SURF_SKIP:
        return True
    if (t.get("indoor") in ("yes", "room", "area", "corridor") or t.get("tunnel") in ("yes", "culvert", "covered")) \
            and t.get("tunnel") != "building_passage":
        return True
    if t.get("area") == "yes" and len(coords) >= 4 and np.allclose(coords[0], coords[-1]):
        return True
    return False


def build_surface(deck_win) -> RoadSurface:
    """Längsprofile aller Wege im Fenster Kachel ± RS_PAD (siehe road_surface.py)."""
    ways = []
    for el in load("roads"):
        t = el.get("tags", {})
        if el["type"] != "way":
            continue
        c = way_coords(el)
        if len(c) < 2 or _road_skipped(t, c):
            continue
        ways.append({"id": el["id"], "kind": "road", "cls": t["highway"], "hw": road_width(t) / 2,
                     "bridge": _is_bridge(t), "coords": c})
    for el in load("rail"):
        t = el.get("tags", {})
        if el["type"] != "way" or t.get("railway") not in ("tram", "rail", "light_rail") or t.get("tunnel") == "yes":
            continue
        c = way_coords(el)
        if len(c) >= 2:
            ways.append({"id": el["id"], "kind": "rail", "cls": t["railway"], "hw": 1.6 if t["railway"] == "tram" else 2.2,
                         "bridge": _is_bridge(t), "coords": c})
    e_km, n_km = int(MIN_E // 1000), int(MIN_N // 1000)
    mos = Mosaic(PROCESSED.parent, e_km, n_km)
    for de in (-2, 0, 2):
        for dn in (-2, 0, 2):
            pf = PROCESSED.parent / f"{e_km + de}_{n_km + dn}" / "platform.f32"
            if not pf.exists():
                continue
            raw = pf.read_bytes()
            if len(raw) != 2000 * 2000 * 4:
                print(f"  Warnung: {pf} unvollständig ({len(raw)} B) – übersprungen", flush=True)
                continue
            pl = np.frombuffer(raw, dtype="<f4").reshape(2000, 2000)
            r0, c0 = (1 - dn // 2) * 2000, (de // 2 + 1) * 2000
            sub = mos.a[r0:r0 + 2000, c0:c0 + 2000]
            mk = np.isfinite(pl)
            sub[mk] = np.fmax(sub[mk], pl[mk])
    return RoadSurface(ways, mos, deck_win, BBOX_UTM, dom=DOM.sample,
                       log=lambda m: print(m, flush=True))


def _piece_pts(pc):
    return [[*to_local(float(e), float(n)), round(float(y), 2)] for e, n, y in zip(pc["E"], pc["N"], pc["y"])]


def building_mask(buildings) -> np.ndarray:
    """Grundrisse (lokale Ringe) als bool-Raster der Kachel (1 m)."""
    im = Image.new("L", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(im)
    ox, oz = MIN_E - ORIGIN_E, MAX_N - ORIGIN_N
    for b in buildings:
        if b.get("elev"):
            continue          # Übergänge/Überbauten: darunter verläuft Straße/Weg
        for i, r in enumerate(b.get("rings", [])):
            pts = [(q[0] - ox, q[1] + oz) for q in r]
            if len(pts) >= 3:
                d.polygon(pts, fill=255 if i == 0 else 0)
    return np.asarray(im) > 0


def build_roads(surface: RoadSurface):
    roads_el = load("roads")
    rails_el = load("rail")
    bridges_el = load("bridges")
    bridge_polys = []
    for el in bridges_el:
        if el.get("tags", {}).get("man_made") == "bridge":
            bridge_polys += polygons_of(el)

    roads, bridges, graph_ways = [], [], []
    splat_roads, splat_walk, splat_plaza, splat_tram = [], [], [], []
    sidewalk_strips = []
    for el in roads_el:
        tags = el.get("tags", {})
        cls = tags.get("highway")
        if cls is None or cls in SURF_SKIP:
            continue
        if tags.get("indoor") in ("yes", "room", "area", "corridor") or tags.get("tunnel") in ("yes", "building_passage", "culvert", "covered"):
            if tags.get("tunnel") != "building_passage":
                continue
        coords = way_coords(el)
        if len(coords) < 2:
            continue
        # Flächenhafte Fußgängerzonen / Plätze
        if tags.get("area") == "yes" and np.allclose(coords[0], coords[-1]) and len(coords) >= 4:
            p = Polygon(coords)
            if p.is_valid and p.area > 1:
                (splat_plaza if cls in ("pedestrian", "footway", "service") else splat_roads).append(p)
            continue
        line = LineString(coords)
        if not line.intersects(AREA_BOX):
            continue
        w = road_width(tags)
        is_bridge = _is_bridge(tags)
        pieces = surface.way_pieces(el["id"]) if not _road_skipped(tags, coords) else []
        if not pieces:
            pieces = [{"E": coords[:, 0], "N": coords[:, 1], "y": np.array([ground(e, n) for e, n in coords]),
                       "deck": np.zeros(len(coords), dtype=bool), "has_deck": False, "deck_frac": 0.0}]
        if is_bridge:
            for pc in pieces:
                # OSM-Brücke ohne (ausreichendes) LoD2-Deck: eigene Platte aus dem Profil
                if pc["deck_frac"] < 0.25 and len(pc["E"]) >= 2:
                    bridges.append({"id": el["id"], "kind": "drive" if cls in DRIVE else "walk", "width": round(w, 2),
                                    "pts": _piece_pts(pc)})
        else:
            if cls in DRIVE:
                splat_roads.append(line.buffer(w / 2, cap_style="round", join_style="round"))
            elif cls == "pedestrian":
                splat_plaza.append(line.buffer(w / 2, cap_style="round", join_style="round"))
            else:
                splat_walk.append(line.buffer(w / 2, cap_style="round", join_style="round"))
            sw = tags.get("sidewalk", "")
            if cls in DRIVE and cls != "service":
                from width_override import sidewalk_width
                sides = []
                if sw in ("both", "left", "right", "yes"):
                    sides = [1, -1] if sw in ("both", "yes") else [1 if sw == "left" else -1]
                elif sw in ("", None):
                    # ohne OSM-Angabe: Gehweg dort, wo der echte Straßenraum einen hergibt
                    sides = [s_ for s_ in (1, -1) if sidewalk_width(tags.get("_id"), s_)]
                for s_ in sides:
                    ws = sidewalk_width(tags.get("_id"), s_) or 2.6
                    try:
                        off = line.offset_curve(s_ * (w / 2 + ws / 2))
                        if not off.is_empty:
                            sidewalk_strips.append(off.buffer(ws / 2, cap_style="flat"))
                    except Exception:
                        pass

        if cls in DRIVE:
            oneway = tags.get("oneway") in ("yes", "1", "true") or tags.get("junction") == "roundabout"
            reverse = tags.get("oneway") == "-1"
            speed = num(tags.get("maxspeed"), SPEED.get(cls, 30))
            if "zone30" in tags.get("maxspeed", "") or "zone:30" in tags.get("source:maxspeed", ""):
                speed = 30
            park, pl, pr = road_park(tags)
            prio = tags.get("priority_road") in ("designated", "yes_unposted", "yes")
            for pc in pieces:
                roads.append({
                    "id": el["id"], "cls": cls, "name": tags.get("name", ""), "width": round(w, 2),
                    "lanes": int(num(tags.get("lanes"), 2 if w - pl - pr >= 6 else 1) or 1),
                    "oneway": 1 if oneway and not reverse else (-1 if reverse else 0),
                    "speed": speed, "bridge": is_bridge, "pts": _piece_pts(pc),
                    "park": park, "pl": pl, "pr": pr, "prio": prio, "rb": tags.get("junction") in ("roundabout", "circular"),
                    "bus": tags.get("bus") == "designated" or tags.get("highway") == "busway",
                    "surf": SURFACE_CLASS.get(tags.get("surface", ""), ""),
                    # für Kfz gesperrt (z. B. Augustusbrücke: nur Tram, Fuß, Rad)
                    "nomv": any(tags.get(k) in ("no", "private", "agricultural", "forestry", "delivery")
                                for k in ("motor_vehicle", "access", "vehicle", "motorcar"))
                            and tags.get("bus") not in ("yes", "designated") and tags.get("psv") not in ("yes", "designated"),
                })

    # Gleise
    rails = []
    for el in rails_el:
        tags = el.get("tags", {})
        if tags.get("railway") not in ("tram", "rail", "light_rail"):
            continue
        if tags.get("tunnel") in ("yes",):
            continue
        coords = way_coords(el)
        if len(coords) < 2 or not LineString(coords).intersects(AREA_BOX):
            continue
        is_bridge = _is_bridge(tags)
        if not is_bridge:
            splat_tram.append(LineString(coords).buffer(1.35, cap_style="flat"))
        pieces = surface.way_pieces(el["id"], kind="rail")
        if not pieces:
            pieces = [{"E": coords[:, 0], "N": coords[:, 1], "y": np.array([ground(e, n) for e, n in coords])}]
        for pc in pieces:
            rails.append({"id": el["id"], "kind": tags["railway"], "bridge": is_bridge, "pts": _piece_pts(pc)})

    return roads, bridges, rails, dict(roads=splat_roads, walk=splat_walk, plaza=splat_plaza,
                                      tram=splat_tram, strips=sidewalk_strips)


# ---------------------------------------------------------------------------
# Flächen
# ---------------------------------------------------------------------------
GRASS_LANDUSE = {"grass", "meadow", "village_green", "recreation_ground", "cemetery", "allotments", "orchard", "flowerbed"}
GRASS_LEISURE = {"park", "garden", "pitch", "playground", "common", "nature_reserve", "dog_park", "golf_course"}
FOREST = {"forest", "wood", "scrub"}


def collect_areas():
    grass, forest, parking, plaza, water = [], [], [], [], []
    for el in load("landuse"):
        t = el.get("tags", {})
        polys = polygons_of(el)
        lu, le, na, am = t.get("landuse"), t.get("leisure"), t.get("natural"), t.get("amenity")
        for p in polys:
            if am == "parking":
                parking.append(p)
            elif lu in FOREST or na in FOREST:
                forest.append(p)
            elif lu in GRASS_LANDUSE or le in GRASS_LEISURE or na in ("grassland", "heath"):
                grass.append(p)
            elif lu in ("commercial", "retail", "industrial") and False:
                plaza.append(p)
    for el in load("water"):
        t = el.get("tags", {})
        if el["type"] == "way" and "waterway" in t and "natural" not in t:
            continue
        for p in polygons_of(el):
            water.append(p)
    return grass, forest, parking, plaza, water


# ---------------------------------------------------------------------------
# Splat-Karten
# ---------------------------------------------------------------------------
def draw_layer(geoms, blur=0.6) -> Image.Image:
    px = SIZE * SPLAT_PX
    im = Image.new("L", (px, px), 0)
    d = ImageDraw.Draw(im)

    def to_px(coords):
        return [((e - MIN_E) * SPLAT_PX, (MAX_N - n) * SPLAT_PX) for e, n in coords]

    for g in geoms:
        parts = [g] if isinstance(g, Polygon) else list(getattr(g, "geoms", []))
        for p in parts:
            if not isinstance(p, Polygon) or p.is_empty:
                continue
            d.polygon(to_px(p.exterior.coords), fill=255)
            for h in p.interiors:
                d.polygon(to_px(h.coords), fill=0)
    return im.filter(ImageFilter.GaussianBlur(blur)) if blur else im


def alkis_plazas():
    """ALKIS-Verkehrsflächen (GeoSN, dl-de/by-2-0; data/raw/strassenraum/tiles, tools/fetch_strassenraum.py) der
    Nutzungsarten Straßenverkehr und Platz als gepflasterte Fläche: in OSM fehlen viele Platzflächen (z. B. Altmarkt
    nur als zwei Fußwege). Im Shader haben Fahrbahn und Gehweg Vorrang – das füllt nur die Lücken."""
    f = RAW / "strassenraum" / "tiles" / f"{MIN_E // 1000:.0f}_{MIN_N // 1000:.0f}.json"
    if not f.exists():
        return []
    from shapely.geometry import shape as _shape
    out = []
    try:
        lay = json.loads(f.read_text(encoding="utf-8"))["layers"].get("alkis_verkehr", [])
    except Exception:
        return []
    for ft in lay:
        if ft.get("properties", {}).get("nutzart") not in ("Straßenverkehr", "Platz"):
            continue
        try:
            g = make_valid(_shape(ft["geometry"]))
        except Exception:
            continue
        for pg in getattr(g, "geoms", [g]):
            if isinstance(pg, Polygon) and pg.area > 20 and pg.intersects(AREA_BOX):
                out.append(pg)
    print(f"  ALKIS: {len(out)} Verkehrs-/Platzflächen als Pflaster", flush=True)
    return out


def build_splats(road_layers, grass, forest, parking, plaza_areas, water):
    road = draw_layer(road_layers["roads"])
    walk_geoms = road_layers["walk"] + road_layers["strips"]
    walk = draw_layer(walk_geoms)
    plaza = draw_layer(road_layers["plaza"] + plaza_areas)
    tram = draw_layer(road_layers["tram"])
    z = Image.new("L", road.size, 0)
    Image.merge("RGBA", (road, walk, plaza, tram)).save(PROCESSED / "splat0.png", optimize=False, compress_level=3)
    gr = draw_layer(grass)
    fo = draw_layer(forest)
    pk = draw_layer(parking)
    wa = draw_layer([w for w in water if w.intersects(AREA_BOX)], blur=1.0)
    Image.merge("RGBA", (gr, fo, pk, wa)).save(PROCESSED / "splat1.png", optimize=False, compress_level=3)
    return road, walk, plaza


# ---------------------------------------------------------------------------
# Punkte (Bäume, Laternen ...) und Straßengraph
# ---------------------------------------------------------------------------
def build_points(water_polys):
    trees, lamps, signals, crossings, stops, props = [], [], [], [], [], []
    for el in load("points"):
        if el["type"] != "node":
            continue
        t = el.get("tags", {})
        e, n = TO_UTM.transform(el["lon"], el["lat"])
        if not (MIN_E <= e < MAX_E and MIN_N <= n < MAX_N):
            continue
        x, z = to_local(e, n)
        y = round(ground(e, n), 2)
        if t.get("natural") == "tree":
            h = num(t.get("height"), 7 + stable_rand(str(el["id"])) * 8)
            trees.append([x, z, y, round(h, 1), 1 if t.get("leaf_type") == "needleleaved" else 0])
        elif t.get("highway") == "street_lamp":
            gas = t.get("lamp_type") in ("gaslight", "gas") or str(t.get("light:method", "")).lower() == "gas"
            lamps.append([x, z, y, 2 if gas else -1])
        elif t.get("highway") == "traffic_signals":
            signals.append([x, z, y])
        elif t.get("highway") == "crossing":
            crossings.append([x, z, y])
        elif t.get("highway") == "stop":
            stops.append([x, z, y])
        elif t.get("amenity") in ("bench", "waste_basket", "bicycle_parking"):
            props.append([x, z, y, t["amenity"]])
    for el in load("tree_rows"):
        c = way_coords(el)
        if len(c) < 2:
            continue
        line = LineString(c)
        for s in np.arange(0, line.length, 7.0):
            p = line.interpolate(s)
            if MIN_E <= p.x <= MAX_E and MIN_N <= p.y <= MAX_N:
                x, z = to_local(p.x, p.y)
                trees.append([x, z, round(ground(p.x, p.y), 2), round(8 + stable_rand(f"{el['id']}{s}") * 6, 1), 0])
    return trees, lamps, signals, crossings, stops, props


def clip_polyline(pts, box):
    """Schneidet eine Polylinie [[x,z,y],...] (lokale Koordinaten) auf eine Box. Gibt Teilstücke zurück."""
    if len(pts) < 2:
        return []
    xy = [(p[0], p[1]) for p in pts]
    line = LineString(xy)
    if line.length < 1e-6:
        return []
    inter = line.intersection(box)
    if inter.is_empty:
        return []
    parts = [inter] if inter.geom_type == "LineString" else [g for g in getattr(inter, "geoms", []) if g.geom_type == "LineString"]
    d = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(np.array(xy), axis=0).T))])
    ys = [p[2] for p in pts]
    out = []
    for g in parts:
        if g.length < 0.05:
            continue
        seg = []
        for x, z in g.coords:
            s_ = line.project(Point(x, z))
            seg.append([round(x, 2), round(z, 2), round(float(np.interp(s_, d, ys)), 2)])
        out.append(seg)
    return out


def local_tile_box():
    from shapely.geometry import box as _box
    x0, x1 = MIN_E - ORIGIN_E, MAX_E - ORIGIN_E
    z0, z1 = -(MAX_N - ORIGIN_N), -(MIN_N - ORIGIN_N)
    return _box(x0, z0, x1, z1)


def clip_roads(roads):
    box_l = local_tile_box()
    out = []
    for r in roads:
        for seg in clip_polyline(r["pts"], box_l):
            rr = dict(r)
            rr["pts"] = seg
            out.append(rr)
    return out


def clip_rails(rails):
    box_l = local_tile_box()
    out = []
    for r in rails:
        for seg in clip_polyline(r["pts"], box_l):
            rr = dict(r)
            rr["pts"] = seg
            out.append(rr)
    return out


def build_passages(buildings):
    """Durchfahrten/Durchgänge (OSM tunnel=building_passage) durch LoD2-Gebäude.
    Je Weg und Gebäude (GML-Einheit) ein Tunnelstück über die Vereinigung der Grundrisse:
    {"b": Bauteil-id (zeichnet den Tunnel), "bs": [gequerte Bauteil-ids (Wandöffnungen)],
     "pts": [[x, z, y], ...] (lokal, y = Boden), "w": Breite, "h": lichte Höhe}."""
    from shapely.strtree import STRtree as _T
    groups = {}
    for b in buildings:
        if b.get("elev") or b.get("stacked") or not b.get("rings"):
            continue
        r = b["rings"][0]
        if len(r) < 3:
            continue
        pg = Polygon(r, [h for h in b["rings"][1:] if len(h) >= 3])
        if not pg.is_valid:
            pg = make_valid(pg)
        groups.setdefault(b.get("gid", b["id"]), []).append((pg, b["id"], float(b["eave"])))
    if not groups:
        return []
    gkeys = list(groups.keys())
    unions = [unary_union([g for g, _, _ in groups[k]]).buffer(0) for k in gkeys]
    tree = _T(unions)
    box_l = local_tile_box()
    out = []
    for el in load("roads"):
        t = el.get("tags", {})
        cls = t.get("highway")
        if el["type"] != "way" or t.get("tunnel") != "building_passage" or not cls or cls in ("steps", "corridor"):
            continue
        c = way_coords(el)
        if len(c) < 2:
            continue
        line = LineString([to_local(e, n) for e, n in c])
        if not line.intersects(box_l):
            continue
        w = road_width(t)
        w = float(np.clip(w, 2.4, 7.5)) if cls in DRIVE else float(np.clip(w, 2.0, 4.5))
        mh = num(str(t.get("maxheight", "")).replace("m", "").strip())
        h_min = float(mh) if mh and 2.0 <= mh <= 8.0 else (4.2 if cls in DRIVE else 3.2)
        for gi in tree.query(line):
            uni = unions[int(gi)]
            members = groups[gkeys[int(gi)]]
            inter = line.intersection(uni)
            for g in getattr(inter, "geoms", [inter]):
                if g.geom_type != "LineString" or g.length < 0.3:
                    continue
                gb = g.buffer(0.6)
                crossed = [(pid, ev) for pg, pid, ev in members if pg.intersects(gb)]
                if not crossed:
                    continue
                eave = max(ev for _, ev in crossed)
                # maxheight ist eine Verkehrsangabe (Untergrenze), Tore großer Bauten sind höher
                h = max(h_min, min(0.2 * eave, 6.0))
                h = float(min(h, max(eave - 1.0, 2.2)))
                mid = g.interpolate(0.5, normalized=True)
                owner = next((pid for pg, pid, _ in members if pg.contains(mid)), crossed[0][0])
                pts = []
                for x, z in g.coords:
                    e, n = x + ORIGIN_E, ORIGIN_N - z
                    pts.append([round(x, 2), round(z, 2), round(ground(e, n), 2)])
                out.append({"b": owner, "bs": [pid for pid, _ in crossed], "pts": pts, "w": round(w, 2), "h": round(h, 2)})
    return out


def build_life(buildings, roads, graph, crossings, curb=None):
    """Straßenleben (street_life.py): Läden, Stadtmöbel, Schilder, Müll."""
    from street_life import StreetLife
    pois = []
    for el in load("pois"):
        if el.get("type") != "node":
            continue
        e, n = TO_UTM.transform(el["lon"], el["lat"])
        el["_utm"] = (e, n)
        pois.append(el)
    shop_blds = []
    for el in load("buildings"):
        t = el.get("tags", {})
        if not ("shop" in t or t.get("amenity") in ("cafe", "restaurant", "bar", "pub", "fast_food", "bank", "pharmacy")):
            continue
        for pg in polygons_of(el):
            c = pg.representative_point()
            shop_blds.append((*to_local(c.x, c.y), t))

    def gy(x, z):
        return ground(x + ORIGIN_E, ORIGIN_N - z)
    sl = StreetLife(pois, buildings, roads, graph, crossings, lambda e, n: to_local(e, n), gy, local_tile_box(),
                    log=lambda m: print(m, flush=True))
    sl.shops(shop_blds)
    sl.furniture()
    cons_polys, cons_ways = [], []
    for el in load("landuse"):
        if el.get("tags", {}).get("landuse") == "construction":
            for pg in polygons_of(el):
                cons_polys.append(Polygon([to_local(e, n) for e, n in pg.exterior.coords]))
    for el in load("roads"):
        if el.get("tags", {}).get("highway") == "construction":
            c = way_coords(el)
            if len(c) >= 2:
                cons_ways.append(LineString([to_local(e, n) for e, n in c]))
    sl.construction(cons_polys, cons_ways)
    sl.names_and_signs()
    sl.litter()
    if curb is not None:
        sl.keep_off_road(curb)
    return sl.out


def gy_local(x, z):
    return round(ground(x + ORIGIN_E, ORIGIN_N - z), 2)


def build_sign_nodes():
    """Vorfahrt-gewähren-/Stopp-Knoten aus OSM (highway=give_way/stop, traffic_sign=DE:205/206)."""
    out = []
    for el in load("pois"):
        if el.get("type") != "node":
            continue
        t = el.get("tags", {})
        ts = t.get("traffic_sign", "")
        kind = 0
        if t.get("highway") == "stop" or "DE:206" in ts:
            kind = 2
        elif t.get("highway") == "give_way" or "DE:205" in ts:
            kind = 1
        if kind:
            e, n = TO_UTM.transform(el["lon"], el["lat"])
            x, z = to_local(e, n)
            out.append((x, z, kind))
    return out


def bus_stop_points():
    pts = []
    for el in load("pois"):
        if el.get("type") != "node":
            continue
        t = el.get("tags", {})
        if t.get("highway") == "bus_stop" or (t.get("public_transport") == "platform" and t.get("bus") == "yes"):
            e, n = TO_UTM.transform(el["lon"], el["lat"])
            pts.append(list(to_local(e, n)))
    return pts


# ---------------------------------------------------------------------------
# Straßenbeleuchtung: OSM erfasst nur ~1/6 der Dresdner Leuchten -> Lücken entlang der Straßen füllen und jedem
# Mast einen Typ geben (Recherche data/research/stadtteile_*.md): 0 moderne Mastleuchte, 1 historischer Kandelaber
# (Altstadt, Gründerzeit-Blockrand), 2 Gaslaterne (Villen-/Dorfgebiete), 3 DDR-Peitschenmast (Plattenbaugebiete,
# DDR-Ausfallstraßen).
# ---------------------------------------------------------------------------
LAMP_SPACING = {"primary": 34.0, "secondary": 34.0, "trunk": 36.0, "tertiary": 32.0, "residential": 30.0,
                "unclassified": 32.0, "living_street": 24.0}
MAIN_ROADS = ("primary", "secondary", "trunk", "primary_link", "secondary_link", "trunk_link")


def build_stops_tile(buildings, roads, rails, life):
    """Haltestellen aus dem Dresdner Steig-Datensatz + OSM-Bahnsteigen (tools/stops.py). Ersetzt die OSM-Masten
    (stop_pole) und Wartehallen (bus_stop) im Umkreis von 30 m echter Steige."""
    from stops import build_stops
    box_l = local_tile_box()
    x0, z0, x1, z1 = box_l.bounds

    def inside(x, z):
        return x0 <= x < x1 and z0 <= z < z1

    def gy(x, z):
        return ground(x + ORIGIN_E, ORIGIN_N - z)
    plats = []
    for el in load("roads"):
        t = el.get("tags", {})
        if el.get("type") == "way" and (t.get("highway") == "platform" or t.get("railway") == "platform"
                                        or t.get("public_transport") == "platform"):
            c = way_coords(el)
            if len(c) >= 2:
                plats.append((t, [to_local(e, n) for e, n in c]))
    for el in load("pois"):
        t = el.get("tags", {})
        if el.get("type") == "node" and (t.get("highway") == "bus_stop" or t.get("public_transport") == "platform"):
            e, n = TO_UTM.transform(el["lon"], el["lat"])
            x, z = to_local(e, n)
            plats.append((t, [(x, z), (x + 0.05, z)]))
    polys = []
    for b in buildings:
        if b.get("elev") or b.get("stacked") or not b.get("rings") or len(b["rings"][0]) < 3:
            continue
        try:
            pg = Polygon(b["rings"][0])
            if pg.is_valid and pg.area > 4:
                polys.append(pg)
        except Exception:
            pass
    btree = STRtree(polys) if polys else None

    def in_building(x, z):
        if btree is None:
            return False
        p = Point(x, z)
        return any(polys[int(i)].contains(p) for i in btree.query(p))
    st = build_stops(ORIGIN_E, ORIGIN_N, inside, gy, rails, roads, plats, in_building,
                     log=lambda m: print(m, flush=True))
    masts = [(m[0], m[1]) for m in st["masts"]]
    if masts:
        mt = STRtree([Point(x, z) for x, z in masts])
        keep = []
        for f in life.get("furniture", []):
            if f[0] in ("stop_pole", "bus_stop") and len(mt.query(Point(f[1], f[2]).buffer(30.0))):
                continue
            keep.append(f)
        life["furniture"] = keep
    return st


def tram_rail_meta(rails, stops_xy):
    """Je Straßenbahngleis: Fahrtrichtung "pref" (Rechtsverkehr: Gegengleis liegt links; +1 entlang der Punkte,
    −1 dagegen, 0 eingleisig/unklar) und Haltepunkte "stops" (Bogenlänge der zugeordneten Haltestellenmasten).
    Früher zur Laufzeit in GDScript berechnet (50–120 ms Ruckler je Kachel)."""
    tram = [i for i, r in enumerate(rails) if r.get("kind") == "tram" and len(r["pts"]) >= 2]
    if not tram:
        return
    lines = {i: LineString([(p[0], p[1]) for p in rails[i]["pts"]]) for i in tram}
    tree = STRtree([lines[i] for i in tram])

    def tangent(ln, s):
        a = ln.interpolate(max(s - 1.0, 0.0))
        b = ln.interpolate(min(s + 1.0, ln.length))
        dx, dz = b.x - a.x, b.y - a.y
        dl = math.hypot(dx, dz) or 1.0
        return dx / dl, dz / dl
    n_dir = [0, 0, 0]
    for i in tram:
        ln = lines[i]
        L = ln.length
        left = right = 0
        s = min(3.0, L * 0.5)
        while s <= L - 1.0:
            p = ln.interpolate(s)
            tx, tz = tangent(ln, s)
            best_d, best_side = 6.5, 0
            for j in tree.query(p.buffer(6.5)):
                k = tram[int(j)]
                if k == i:
                    continue
                l2 = lines[k]
                s2 = l2.project(p)
                q = l2.interpolate(s2)
                ux, uz = tangent(l2, s2)
                if abs(ux * tx + uz * tz) < 0.92:
                    continue
                rx, rz = q.x - p.x, q.y - p.y
                lat = tx * rz - tz * rx                 # > 0 rechts, < 0 links (x Ost, z Süd)
                if abs(rx * tx + rz * tz) > 5.0 or abs(lat) < 2.2:
                    continue
                if abs(lat) < best_d:
                    best_d, best_side = abs(lat), (1 if lat > 0 else -1)
            if best_side < 0:
                left += 1
            elif best_side > 0:
                right += 1
            s += 6.0
        n = left + right
        pref = 1 if (n >= 2 and left >= right * 2) else (-1 if (n >= 2 and right >= left * 2) else 0)
        rails[i]["pref"] = pref
        rails[i]["stops"] = []
        n_dir[pref + 1] += 1
    n_st = 0
    for (x, z) in stops_xy:
        pt = Point(x, z)
        cand = sorted((lines[tram[int(j)]].distance(pt), tram[int(j)]) for j in tree.query(pt.buffer(9.0)))
        cand = [c for c in cand if c[0] < 9.0]
        for d, k in cand:
            if k == cand[0][1] or d < 4.5:                # nächstes Gleis; weitere nur bei Mittelbahnsteig
                rails[k]["stops"].append(round(lines[k].project(pt), 2))
                n_st += 1
    for i in tram:
        rails[i]["stops"] = sorted(rails[i]["stops"])
    print(f"  Straßenbahn: Richtung +{n_dir[2]}/−{n_dir[0]}/frei {n_dir[1]}, {n_st} Haltepunkte", flush=True)


def sidewalk_style_img(px):
    """Gehwegbelag je 25-m-Zelle nach Baualter/Strukturtyp (Recherche data/research/stadtteile_*.md):
    Gründerzeit/Altstadt Granitplatten mit Mosaikpflaster-Streifen (0), DDR-Wohngebiete Betonplatten 40×40 (128),
    Nachwende-/Einfamilienhaus-Gebiete Beton-Verbundpflaster (255)."""
    try:
        import build_years as by
        n = 80
        cell = SIZE / n
        es = MIN_E + (np.arange(n) + 0.5) * cell
        ns = MAX_N - (np.arange(n) + 0.5) * cell             # Zeile 0 = Norden (Bildoben)
        E, N = np.meshgrid(es, ns)
        r = by.lookup_many(E.ravel(), N.ravel())
        codes = by._grid()["meta"]["sst_codes"]
        y = r["years"]
        old = y[:, 0]
        wbs = y[:, 3] + y[:, 4] + y[:, 5]
        new = y[:, 6:].sum(1)
        sst = np.array([codes[int(i)] for i in r["sst"]])
        style = np.full(n * n, 128, np.uint8)
        gruend = (old >= 0.35) | np.isin(sst, ["C11", "C21", "A13", "B21"])
        verbund = (new >= 0.5) | np.isin(sst, ["A12", "B11", "D41", "A41", "B41", "C41"])
        platte = (wbs >= 0.4) | np.isin(sst, ["B13", "B14", "C12"])
        style[verbund] = 255
        style[gruend] = 0
        style[platte] = 128
        in_old = (E.ravel() >= OLD_TOWN[0]) & (E.ravel() <= OLD_TOWN[2]) & (N.ravel() >= OLD_TOWN[1]) & (N.ravel() <= OLD_TOWN[3])
        style[in_old] = 0
        return Image.fromarray(style.reshape(n, n)).resize((px, px), Image.NEAREST)
    except Exception as ex:
        print(f"  Gehwegbelag: keine Baualterdaten ({ex})", flush=True)
        return None


def lamp_type(x, z, cls):
    e, n = x + ORIGIN_E, ORIGIN_N - z
    if OLD_TOWN[0] <= e <= OLD_TOWN[2] and OLD_TOWN[1] <= n <= OLD_TOWN[3]:
        return 1
    info = _era_info(e, n)
    if not info or not info.get("eras"):
        return 0
    er = info["eras"]
    sst = info.get("sst") or ""
    wbs = er.get("ddr_wbs70", 0.0) + er.get("ddr_frueh_60er", 0.0)
    old = er.get("vor1919", 0.0)
    if wbs >= 0.4 or sst in SST_PLATTE:
        return 3
    if cls in MAIN_ROADS:
        return 0
    if old >= 0.45 and sst in ("A13", "A12", "A11", "A21"):
        return 2
    if old >= 0.4 and sst in ("C11", "C21", "B21"):
        return 1
    return 0


def build_lamps(lamps, roads, buildings, curb):
    from collections import Counter
    polys = []
    for b in buildings:
        if b.get("elev") or b.get("stacked") or not b.get("rings") or len(b["rings"][0]) < 3:
            continue
        try:
            pg = Polygon(b["rings"][0])
            if not pg.is_valid:
                pg = pg.buffer(0)
            if not pg.is_empty and pg.area > 4:
                polys.append(pg)
        except Exception:
            pass
    btree = STRtree(polys) if polys else None

    def in_building(x, z):
        if btree is None:
            return False
        pt = Point(x, z)
        return any(polys[int(i)].distance(pt) < 0.3 for i in btree.query(pt, predicate="dwithin", distance=0.3))
    road_lines, road_cls = [], []
    for r in roads:
        if len(r["pts"]) >= 2:
            road_lines.append(LineString([(p[0], p[1]) for p in r["pts"]]))
            road_cls.append(r["cls"])
    rtree = STRtree(road_lines) if road_lines else None

    def near_cls(x, z):
        if rtree is None:
            return "residential"
        pt = Point(x, z)
        best, bd = "residential", 18.0
        for i in rtree.query(pt.buffer(18.0)):
            d = road_lines[int(i)].distance(pt)
            if d < bd:
                bd, best = d, road_cls[int(i)]
        return best
    grid = defaultdict(list)

    def add(x, z):
        grid[(int(x // 20), int(z // 20))].append((x, z))

    def near(x, z, rad):
        cx, cz = int(x // 20), int(z // 20)
        for i in range(cx - 1, cx + 2):
            for j in range(cz - 1, cz + 2):
                for (a, b) in grid.get((i, j), ()):
                    if (a - x) ** 2 + (b - z) ** 2 < rad * rad:
                        return True
        return False
    out = []
    for l in lamps:
        t = int(l[3]) if len(l) > 3 and int(l[3]) >= 0 else lamp_type(l[0], l[1], near_cls(l[0], l[1]))
        out.append([l[0], l[1], l[2], t])
        add(l[0], l[1])
    x0, z0, x1, z1 = local_tile_box().bounds
    n_new = 0
    for r in roads:
        sp = LAMP_SPACING.get(r["cls"])
        if sp is None or r.get("bridge") or len(r["pts"]) < 2:
            continue
        ln = LineString([(p[0], p[1]) for p in r["pts"]])
        L = ln.length
        if L < 8.0:
            continue
        w = float(r["width"])
        both = w >= 13.0
        side0 = 1 if stable_rand(str(r["id"]) + "ls") < 0.5 else -1
        s = stable_rand(str(r["id"]) + "lo") * sp * 0.8 + 3.0
        while s < L - 2.0:
            pa = ln.interpolate(max(s - 1.0, 0.0))
            pb = ln.interpolate(min(s + 1.0, L))
            pc = ln.interpolate(s)
            dx, dz = pb.x - pa.x, pb.y - pa.y
            dl = math.hypot(dx, dz) or 1.0
            nx, nz = -dz / dl, dx / dl
            for sd in ([side0, -side0] if both else [side0]):
                off = w * 0.5 + 0.7
                px, pz = pc.x + nx * off * sd, pc.y + nz * off * sd
                if not (x0 <= px < x1 and z0 <= pz < z1) or near(px, pz, sp * 0.6):
                    continue
                q = curb.push(px, pz, 0.5, max_move=3.0)
                if q is None:
                    continue
                px, pz = q
                if in_building(px, pz) or near(px, pz, sp * 0.6):
                    continue
                out.append([round(px, 2), round(pz, 2), gy_local(px, pz), lamp_type(px, pz, r["cls"])])
                add(px, pz)
                n_new += 1
            s += sp
    print(f"  Laternen: {len(lamps)} aus OSM, {n_new} ergänzt; Typen {dict(Counter(l[3] for l in out))}", flush=True)
    return out


def build_parking(roads, buildings, graph, crossings, signals, curb):
    """Geparkte Autos nur auf echten Parkständen (parking.py)."""
    from parking import LOT_TYPES, Parking
    deg = defaultdict(int)
    for e in graph["edges"]:
        deg[e["a"]] += 1
        deg[e["b"]] += 1
    junc = [[n["pos"][0], n["pos"][2]] for n in graph["nodes"] if deg[n["id"]] >= 3]
    lots = []
    for el in load("landuse"):
        t = el.get("tags", {})
        if t.get("amenity") != "parking" or t.get("parking") not in LOT_TYPES:
            continue
        if t.get("access") in ("no",) or t.get("location") in ("underground", "roof", "rooftop"):
            continue
        for pg in polygons_of(el):
            loc = Polygon([to_local(e, n) for e, n in pg.exterior.coords])
            if loc.is_valid and loc.intersects(local_tile_box()):
                lots.append((loc, t.get("parking")))
    side_lots = [pg for pg, k in lots if k in ("street_side", "lane", "layby", "lay_by")]
    side_tree = STRtree(side_lots) if side_lots else None

    def lots_near(x, z):
        if side_tree is None:
            return False
        p = Point(x, z)
        return any(side_lots[int(i)].distance(p) < 3.0 for i in side_tree.query(p.buffer(3.0)))
    pk = Parking(curb, buildings, junc, [[c[0], c[1]] for c in crossings], bus_stop_points(),
                 [[s[0], s[1]] for s in signals], log=lambda m: print(m, flush=True))
    pk.street(roads, lots_near)
    pk.lots(lots)
    pk.report()
    out = pk.out
    if len(out) > 2600:
        rng = np.random.default_rng(5)
        idx = rng.choice(len(out), 2600, replace=False)
        out = [out[i] for i in sorted(idx)]
    return out


def build_tram_poles(rails, curb):
    """Oberleitungsmasten am Fahrbahnrand (nicht auf der Fahrbahn), mit Querdraht-Ansatzpunkt über dem Gleis."""
    poles = []
    have = []
    for r in rails:
        if r.get("kind") != "tram" or r.get("bridge"):
            continue
        pts = r["pts"]
        if len(pts) < 2:
            continue
        ln = LineString([(p[0], p[1]) for p in pts])
        L = ln.length
        side = 1.0 if int(L) % 2 == 0 else -1.0
        sv = 10.0
        while sv < L - 6.0:
            a = ln.interpolate(max(sv - 1.0, 0.0))
            b = ln.interpolate(min(sv + 1.0, L))
            q = ln.interpolate(sv)
            tx, tz = b.x - a.x, b.y - a.y
            tl = math.hypot(tx, tz) or 1.0
            nx, nz = -tz / tl * side, tx / tl * side
            px, pz = q.x + nx * 3.0, q.y + nz * 3.0
            sv += 38.0
            side = -side
            pp = curb.push(px, pz, 0.7, max_move=10.0)
            if pp is None:
                continue
            px, pz = pp
            if any(math.hypot(px - hx, pz - hz) < 9.0 for hx, hz in have):
                continue
            have.append((px, pz))
            # Fahrleitungs-Ansatz: Lotpunkt auf dem Gleis, Höhe aus dem Gleisprofil
            s2 = ln.project(Point(px, pz))
            g = ln.interpolate(s2)
            gy_t = float(np.interp(s2, np.concatenate([[0.0], np.cumsum([math.dist(pts[i][:2], pts[i + 1][:2]) for i in range(len(pts) - 1)])]),
                                   [p[2] for p in pts]))
            yaw = math.atan2(-(g.y - pz), g.x - px)
            poles.append([round(px, 2), round(pz, 2), gy_local(px, pz), round(yaw, 3), round(g.x, 2), round(g.y, 2), round(gy_t, 2)])
    return poles


def clip_2d(items):
    """Polylinien [[x,z],...] (lokal) auf die Kachel schneiden; jedes Teilstück wird ein eigenes Element."""
    box_l = local_tile_box()
    out = []
    for it in items:
        pts = it["pts"]
        if len(pts) < 2:
            continue
        line = LineString([(p[0], p[1]) for p in pts])
        if box_l.contains(line):
            out.append(it)
            continue
        inter = line.intersection(box_l)
        for g in getattr(inter, "geoms", [inter]):
            if g.geom_type == "LineString" and g.length > 0.3:
                q = dict(it)
                q["pts"] = [[round(x, 2), round(z, 2)] for x, z in g.coords]
                out.append(q)
    return out


def inside_tile(items):
    """Punktobjekte [x, z, ...] (lokal) nur innerhalb der Kachel behalten."""
    x0, x1 = MIN_E - ORIGIN_E, MAX_E - ORIGIN_E
    z0, z1 = -(MAX_N - ORIGIN_N), -(MIN_N - ORIGIN_N)
    return [p for p in items if x0 <= p[0] < x1 and z0 < p[1] <= z1]


def build_graph(roads, signals):
    """Straßengraph: Knoten an Kreuzungen/Enden, Kanten als Polylinien, nur befahrbare Straßen."""
    def key(p):
        return (round(p[0], 1), round(p[1], 1))

    usage = {}
    for r in roads:
        if (r["cls"] == "service" and r["width"] < 3.0) or r.get("nomv"):
            continue
        for i, p in enumerate(r["pts"]):
            usage.setdefault(key(p), set()).add(r["id"])
    nodes = {}
    edges = []
    sig_keys = {key(s) for s in signals}

    def node_id(p):
        k = key(p)
        if k not in nodes:
            nodes[k] = {"id": len(nodes), "pos": [p[0], p[2], p[1]]}
        return nodes[k]["id"]

    sig_arr = np.array([[s[0], s[1]] for s in signals] or [[1e9, 1e9]], dtype=float)
    sig_pts = set()       # Schlüssel der Knoten, an denen eine Ampel steht (Wege werden dort geteilt)
    for r in roads:
        if (r["cls"] == "service" and r["width"] < 3.0) or r.get("nomv"):
            continue
        pts = r["pts"]
        cut = [0]
        # Ampel auf dem Weg (OSM: oft 15–30 m vor der Kreuzung) -> eigener Knoten
        sig_cut = set()
        P = np.array([[p[0], p[1]] for p in pts], dtype=float)
        if len(P) >= 3:
            lo, hi = P.min(axis=0) - 2.5, P.max(axis=0) + 2.5
            for sx, sz in sig_arr:
                if lo[0] <= sx <= hi[0] and lo[1] <= sz <= hi[1]:
                    dd = np.hypot(P[:, 0] - sx, P[:, 1] - sz)
                    i = int(np.argmin(dd))
                    if dd[i] < 2.5 and 0 < i < len(pts) - 1:
                        sig_cut.add(i)
                        sig_pts.add(key(pts[i]))
        for i in range(1, len(pts) - 1):
            if len(usage[key(pts[i])]) > 1 or pts[i][:2] in [pts[0][:2], pts[-1][:2]] or i in sig_cut:
                cut.append(i)
        cut.append(len(pts) - 1)
        for a, b in zip(cut[:-1], cut[1:]):
            seg = pts[a:b + 1]
            if len(seg) < 2:
                continue
            length = sum(math.dist(seg[i][:2], seg[i + 1][:2]) for i in range(len(seg) - 1))
            if length < 0.5:
                continue
            edges.append({
                "a": node_id(seg[0]), "b": node_id(seg[-1]), "cls": r["cls"], "lanes": r["lanes"],
                "oneway": r["oneway"], "speed": r["speed"], "width": r["width"], "len": round(length, 1), "bridge": r["bridge"],
                "pts": seg, "name": r["name"], "wid": r["id"], "pl": r.get("pl", 0.0), "pr": r.get("pr", 0.0),
                "prio": bool(r.get("prio")), "rb": bool(r.get("rb")), "bus": bool(r.get("bus")),
            })
    for k, nd in nodes.items():
        nd["signal"] = k in sig_keys or k in sig_pts or any(math.dist(k, (s[0], s[1])) < 6 for s in signals)
    return {"nodes": [n for n in sorted(nodes.values(), key=lambda n: n["id"])], "edges": edges}


# ---------------------------------------------------------------------------
def raise_curbs(road_img, walk_img, plaza_img) -> None:
    """Hebt Gehwege/Plätze um 12 cm gegenüber der Fahrbahn an (Bordstein) und schreibt terrain.f32."""
    def small(im):
        return np.asarray(im.resize((SIZE, SIZE), Image.BOX), dtype=np.float32) / 255.0
    road = small(road_img)
    walk = np.maximum(small(walk_img), small(plaza_img))
    m = np.clip((walk - 0.35) / 0.4, 0.0, 1.0) * np.clip(1.0 - road * 2.0, 0.0, 1.0)
    # Fahrbahn ist bereits exakt (Längsprofil + conform) -> keine zusätzliche Glättung
    smoothed = TERRAIN.astype(np.float32)
    out = (smoothed + 0.12 * m).astype("<f4")
    (PROCESSED / "terrain.f32").write_bytes(out.tobytes())
    # Kollisionsraster 2001x2001 (Stützstellen auf ganzen Metern, deckt die Kachel lückenlos ab)
    pad = np.empty((SIZE + 1, SIZE + 1), dtype="<f4")
    mid = 0.5 * (out[:, :-1] + out[:, 1:])
    row = np.concatenate([out[:, :1], mid, out[:, -1:]], axis=1)
    midr = 0.5 * (row[:-1] + row[1:])
    pad = np.concatenate([row[:1], midr, row[-1:]], axis=0).astype("<f4")
    (PROCESSED / "terrain_col.f32").write_bytes(pad.tobytes())
    print(f"  Bordsteine: {int((m > 0.5).sum()) } m² angehoben", flush=True)


def build_walls_steps(steps_src):
    """Mauern/Zäune (OSM barrier) und Treppen als einfache Polylinien für Godot."""
    barriers = []
    for el in load("barriers"):
        t = el.get("tags", {})
        kind = t.get("barrier")
        if kind not in ("wall", "fence", "retaining_wall", "city_wall"):
            continue
        # Sonderfälle: Brunnenränder, Mauern, die zugleich Gebäude/Fläche sind, Ringe auf Brücken
        if el["id"] in OVERRIDES.get("skip_barriers", []) or "building" in t or t.get("area") == "yes" \
                or t.get("amenity") == "fountain" or t.get("natural") == "water" or "bridge" in t \
                or (num(t.get("layer"), 0) or 0) >= 1:
            continue
        c = way_coords(el)
        if len(c) < 2:
            continue
        line = LineString(c)
        if not line.intersects(AREA_BOX) or line.length < 1.5:
            continue
        pts = [list(to_local(e, n)) for e, n in line.simplify(0.1).coords]
        barriers.append({"kind": kind, "h": num(t.get("height")), "pts": pts,
                         "mat": t.get("material", ""), "bridge": "bridge" in t})
    steps = []
    for el in steps_src:
        t = el.get("tags", {})
        if t.get("highway") != "steps":
            continue
        c = way_coords(el)
        if len(c) < 2 or not LineString(c).intersects(AREA_BOX):
            continue
        if t.get("indoor") in ("yes",) or t.get("tunnel") == "yes" or t.get("bridge") not in (None, "no"):
            continue
        L = LineString(c).length
        if L < 1.5:
            continue
        steps.append({"width": num(t.get("width"), 2.2) or 2.2, "pts": [list(to_local(e, n)) for e, n in c]})
    return barriers, steps


# ---------------------------------------------------------------------------
def build_street_details(roads, graph, crossings, road_img):
    """Gullydeckel, Entwässerungsgitter, Flicken, Randverschmutzung und geparkte Autos."""
    rng = np.random.default_rng(11)
    cnt = {}
    for e in graph["edges"]:
        cnt[e["a"]] = cnt.get(e["a"], 0) + 1
        cnt[e["b"]] = cnt.get(e["b"], 0) + 1
    junc = np.array([[n["pos"][0], n["pos"][2]] for n in graph["nodes"] if cnt.get(n["id"], 0) >= 3] or [[1e9, 1e9]])
    cross = np.array([[c[0], c[1]] for c in crossings] or [[1e9, 1e9]])

    def near(pt, arr, r):
        return bool((np.hypot(arr[:, 0] - pt[0], arr[:, 1] - pt[1]) < r).any())

    manholes, grates, parked = [], [], []
    patches = []
    parkable = {"residential": 0.34, "tertiary": 0.2, "unclassified": 0.3, "living_street": 0.25, "secondary": 0.08}
    for r in roads:
        if r["bridge"] or r["cls"] in ("service", "motorway", "motorway_link", "trunk_link"):
            continue
        pts = [(p[0], p[1]) for p in r["pts"]]
        if len(pts) < 2:
            continue
        line = LineString(pts)
        L = line.length
        if L < 12:
            continue
        w = r["width"]

        def frame(sv):
            a = line.interpolate(max(sv - 0.6, 0.0))
            b = line.interpolate(min(sv + 0.6, L))
            p = line.interpolate(sv)
            t = np.array([b.x - a.x, b.y - a.y])
            n = np.hypot(*t) or 1.0
            t = t / n
            return np.array([p.x, p.y]), t, np.array([-t[1], t[0]])

        sv = rng.uniform(8, 30)
        while sv < L - 6:
            p, t, nrm = frame(sv)
            if not near(p, junc, 9):
                q = p + nrm * rng.uniform(-w * 0.28, w * 0.28)
                manholes.append([round(float(q[0]), 2), round(float(q[1]), 2)])
            sv += rng.uniform(30, 70)
        if w >= 5.0:
            sv = rng.uniform(5, 20)
            while sv < L - 5:
                p, t, nrm = frame(sv)
                if not near(p, junc, 9):
                    for side in (1, -1):
                        q = p + nrm * side * (w * 0.5 - 0.28)
                        grates.append([round(float(q[0]), 2), round(float(q[1]), 2), round(float(math.atan2(-t[0], -t[1])), 3)])
                sv += rng.uniform(28, 48)
        sv = rng.uniform(10, 35)
        while sv < L - 8:
            p, t, nrm = frame(sv)
            ln = rng.uniform(2.0, 7.0)
            wd = rng.uniform(1.0, max(1.05, min(2.6, w * 0.45)))
            c = p + nrm * rng.uniform(-w * 0.3, w * 0.3)
            ang = math.atan2(t[1], t[0])
            rect = Polygon([(-ln / 2, -wd / 2), (ln / 2, -wd / 2), (ln / 2, wd / 2), (-ln / 2, wd / 2)])
            from shapely import affinity
            rect = affinity.translate(affinity.rotate(rect, ang, origin=(0, 0), use_radians=True), c[0], c[1])
            patches.append(rect)
            sv += rng.uniform(22, 55)
        # Parkplätze am Fahrbahnrand
        occ = parkable.get(r["cls"], 0.0)
        if occ > 0 and w >= 7.0 and L > 20:
            sides = [1] if (int(r["oneway"]) != 0 or w < 9.0) else [1, -1]
            for side in sides:
                sv = 9.0
                while sv < L - 9.0:
                    p, t, nrm = frame(sv)
                    if rng.random() < occ and not near(p, junc, 11) and not near(p, cross, 7):
                        q = p - nrm * side * (w * 0.5 - 0.95)     # rechts der Fahrtrichtung: -nrm
                        yaw = math.atan2(-t[0], -t[1]) + (0.0 if side == 1 else math.pi)
                        parked.append([round(float(q[0]), 2), round(float(q[1]), 2), round(float(yaw), 3), int(rng.integers(0, 1000))])
                    sv += 5.9
    # Splat2: R = Flicken, G = Randverschmutzung, B = Gehwegbelag (0 Granitplatten+Mosaik, 128 Betonplatten,
    # 255 Verbundpflaster), A frei
    pm = draw_layer([_to_utm_poly(pp) for pp in patches], blur=0.5)
    blur = road_img.filter(ImageFilter.GaussianBlur(5))
    b = np.asarray(blur, dtype=np.float32) / 255.0
    dirt = (1.0 - np.abs(2.0 * b - 1.0)) ** 1.5
    dirt_img = Image.fromarray((dirt * 255).astype(np.uint8))
    zero = Image.new("L", road_img.size, 0)
    walk_style = sidewalk_style_img(road_img.size[0]) or zero
    Image.merge("RGBA", (pm, dirt_img, walk_style, zero)).save(PROCESSED / "splat2.png", optimize=False, compress_level=3)
    if len(parked) > 900:
        idx = rng.choice(len(parked), 900, replace=False)
        parked = [parked[i] for i in sorted(idx)]
    return manholes, grates, parked


def _to_utm_poly(local_poly):
    """Lokale Spielkoordinaten (x, z) -> UTM, damit draw_layer sie wie alle anderen Flächen zeichnet."""
    from shapely.ops import transform as shp_transform
    return shp_transform(lambda x, z, *a: (x + ORIGIN_E, ORIGIN_N - z), local_poly)


# ---------------------------------------------------------------------------
def main() -> None:
    global DECK
    PROCESSED.mkdir(parents=True, exist_ok=True)
    print("Luftbild-Mosaik ...", flush=True)
    mosaic = build_ortho()
    carve_under_bridges()
    br_meshes, br_rails, DECK, deck_win = collect_bridges()
    print(f"  {len(br_meshes)} LoD2-Brücken, {len(br_rails)} Brüstungsstücke", flush=True)
    global PLAT
    PLAT = detect_platforms()
    print("Straßenprofil ...", flush=True)
    surface = build_surface(deck_win)
    n_r = len(br_rails)
    br_rails = surface.crossing_filter(br_rails, to_local)
    print(f"  {n_r - len(br_rails)} Brüstungsstücke über Wegen entfernt", flush=True)
    print("Gebäude ...", flush=True)
    buildings = None
    if "--osm-buildings" not in sys.argv:
        buildings = build_buildings_lod2(mosaic)
        if buildings:
            print("  (LoD2)", flush=True)
    if not buildings:
        buildings = build_buildings(mosaic)
    print(f"  {len(buildings)} Gebäude, davon {sum(1 for b in buildings if b['roof'])} mit Schrägdach", flush=True)
    del mosaic
    print("Gelände an Fahrbahnen anpassen ...", flush=True)
    n_px = surface.conform(TERRAIN, MIN_E, MAX_N, protect=building_mask(buildings), deck_lo_tile=DECK_LO)
    print(f"  {n_px} m² angepasst", flush=True)
    print("Straßen ...", flush=True)
    roads, bridges, rails, layers = build_roads(surface)
    roads = clip_roads(roads)          # strikte Kachelgrenze: keine Markierungen/Autos außerhalb
    bridges = clip_roads(bridges)
    rails = clip_rails(rails)
    print(f"  {len(roads)} Straßen, {len(bridges)} Brücken, {len(rails)} Gleisstücke", flush=True)
    grass, forest, parking, plaza, water = collect_areas()
    print("Splat-Karten ...", flush=True)
    road_img, walk_img, plaza_img = build_splats(layers, grass, forest, parking, plaza + alkis_plazas(), water)
    raise_curbs(road_img, walk_img, plaza_img)
    trees, lamps, signals, crossings, stops, props = build_points(water)
    print(f"  {len(trees)} Bäume, {len(lamps)} Laternen, {len(signals)} Ampeln, {len(crossings)} Übergänge", flush=True)

    # Wasserflächen mit Pegel (obere Perzentile des Geländes im Polygon)
    water_out = []
    for p in water:
        if not p.intersects(AREA_BOX) or p.area < 30:
            continue
        p = p.intersection(WATER_BOX)
        for g in getattr(p, "geoms", [p]):
            if not isinstance(g, Polygon) or g.area < 30:
                continue
            g = g.simplify(0.5)
            minx, miny, maxx, maxy = g.bounds
            hs = []
            for _ in range(200):
                pt = Point(np.random.uniform(minx, maxx), np.random.uniform(miny, maxy))
                if g.contains(pt):
                    hs.append(ground(pt.x, pt.y))
            level = float(np.percentile(hs, 80)) if hs else -3.0
            rings = ring_coords(g)
            loc = [[to_local(e, n) for e, n in r] for r in rings]
            water_out.append({"rings": loc, "level": round(level, 2), "tris": earcut([np.array(r) for r in loc])})
    print(f"  {len(water_out)} Wasserflächen", flush=True)

    barriers, steps_out = build_walls_steps(load("roads"))
    barriers, steps_out = clip_2d(barriers), clip_2d(steps_out)
    passages = build_passages(buildings)
    print(f"  {len(passages)} Durchfahrten/Durchgänge in Gebäuden", flush=True)
    print(f"  {len(barriers)} Mauern/Zäune, {len(steps_out)} Treppen", flush=True)
    graph = build_graph(roads, [[s[0], s[1]] for s in signals])
    print(f"  Graph: {len(graph['nodes'])} Knoten, {len(graph['edges'])} Kanten", flush=True)
    # Fahrbahn freihalten: Laternen, Bänke, Masten ... an den Bordstein
    from curb import Curb
    from junctions import analyse as analyse_junctions
    curb = Curb(roads, rails)
    lamps_ok = []
    for l in lamps:
        q = curb.push(l[0], l[1], 0.5, max_move=6.0)
        if q is not None:
            lamps_ok.append([round(q[0], 2), round(q[1], 2), gy_local(q[0], q[1]), l[3] if len(l) > 3 else -1])
    props_ok = []
    for pr in props:
        q = curb.push(pr[0], pr[1], 0.7, max_move=6.0)
        if q is not None:
            props_ok.append([round(q[0], 2), round(q[1], 2), gy_local(q[0], q[1]), pr[3]])
    print(f"  Fahrbahn freigehalten: {len(lamps) - len(lamps_ok)} Laternen verworfen, {curb.moved} verschoben", flush=True)
    lamps, props = lamps_ok, props_ok
    signal_heads = analyse_junctions(graph, None, [[s[0], s[1]] for s in signals], build_sign_nodes(), curb, gy_local,
                                     log=lambda m: print(m, flush=True))
    signal_heads = inside_tile(signal_heads)
    tram_poles = inside_tile(build_tram_poles(rails, curb))
    manholes, grates, _old_parked = build_street_details(roads, graph, crossings, road_img)
    manholes, grates = inside_tile(manholes), inside_tile(grates)
    lamps = build_lamps(lamps, roads, buildings, curb)
    parked = inside_tile(build_parking(roads, buildings, graph, crossings, signals, curb))
    life = build_life(buildings, roads, graph, crossings, curb)
    stops = build_stops_tile(buildings, roads, rails, life)
    tram_rail_meta(rails, [(m[0], m[1]) for m in stops["masts"] if m[6] == "tram"] +
                   [(f[1], f[2]) for f in life.get("furniture", []) if f[0] == "stop_pole"])
    print(f"  {len(manholes)} Gullydeckel, {len(grates)} Gitter, {len(parked)} geparkte Autos, {len(tram_poles)} Fahrleitungsmasten", flush=True)

    city = {
        "meta": {"origin_utm": [ORIGIN_E, ORIGIN_N], "size": SIZE, "base_height": TERRAIN_META["base_height"],
                 "splat_px_per_m": SPLAT_PX,
                 "attribution": "Geodaten Sachsen (GeoSN), dl-de/by-2.0; (c) OpenStreetMap-Mitwirkende (ODbL)"},
        "buildings": buildings, "roads": roads, "bridges": bridges, "rails": rails, "water": water_out,
        "manholes": manholes, "grates": grates, "parked": parked,
        "barriers": barriers, "steps": steps_out, "trees": trees, "lamps": lamps, "signals": signals, "crossings": crossings, "props": props,
        "graph": graph, "bridge_meshes": br_meshes, "bridge_rails": br_rails, "passages": passages, "life": life,
        "signal_heads": signal_heads, "tram_poles": tram_poles, "stops": stops,
    }
    (PROCESSED / "city.json").write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    print(f"city.json: {(PROCESSED / 'city.json').stat().st_size / 1e6:.1f} MB", flush=True)


if __name__ == "__main__":
    np.random.seed(7)
    main()
