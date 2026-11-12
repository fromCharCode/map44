"""Straßenraum je Spielkachel: Fahrbahnbreiten, Gehwege, Bordsteine, Straßengrün, Stadtbäume.

Datengrundlage: data/raw/strassenraum/tiles/<E>_<N>.json (aus tools/fetch_strassenraum.py, EPSG:25833)
sowie die OSM-Kacheldaten data/raw/tiles/<E>_<N>/osm/{roads,buildings,rail,landuse}.json.
Quellen/Lizenzen: Landeshauptstadt Dresden (dl-de/by-2-0), GeoSN ALKIS (dl-de/by-2-0), OSM (ODbL).

Spielkoordinaten: x = E - 411000, z = -(N - 5656200).
Seiten "links"/"rechts" beziehen sich – wie in tools/parking.py – auf die Digitalisierrichtung des OSM-Wegs.

Öffentliche Funktionen (alle mit e_km, n_km = SW-Ecke der 2x2-km-Kachel):
  trees_for_tile(e, n)           -> [ {x, z, art, art_bot, hoehe_m, krone_m, stamm_cm, alter_j, pflanzjahr, ...} ]
  road_widths_for_tile(e, n)     -> {osm_way_id: {fahrbahn_m, fahrbahn_quelle, gehweg_links_m, ...}}
  kerbs_for_tile(e, n)           -> {"linien": [...], "punkte": [...]}   (Bordsteinkanten, Absenkungen)
  green_strips_for_tile(e, n)    -> [ {pts, holes, quelle, art} ]         (Straßenbegleitgrün, Inseln)
  defaults_for(highway)          -> Regelquerschnitt (Fallback, aus Recherche)
Schneller Test:  .venv/bin/python tools/strassenraum.py 410,5656 [412,5656 ...]
"""
from __future__ import annotations

import html
import json
import math
import re
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import LineString, Polygon, shape
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import parking as _pk      # Parkstreifenbreiten (tools/parking.py)
except Exception:              # pragma: no cover
    _pk = None

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
SR_DIR = RAW / "strassenraum"
ORIGIN_E = 411000.0
ORIGIN_N = 5656200.0
WINDOW = 300.0          # m Datenfenster um die Kachel für Messungen
_TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)

# Straßenklassen, für die Breiten gemessen werden
CAR = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
       "service", "road", "busway", "motorway_link", "trunk_link", "primary_link", "secondary_link",
       "tertiary_link", "pedestrian"}
# area:highway-Werte, die zur Fahrbahn zählen
AREA_CARRIAGE = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
                 "living_street", "service", "road", "busway", "motorway_link", "trunk_link", "primary_link",
                 "secondary_link", "tertiary_link", "bus_stop", "parking_lane", "junction", "yes", "driveway",
                 "emergency"}
ALKIS_RAUM = {"Straßenverkehr", "Platz", "Weg"}
GREEN_LANDUSE = {"grass", "flowerbed", "planter", "village_green", "meadow"}

# Regelquerschnitte (Fallback). Gehwegbreiten aus data/research/stadtteile_g*.json (Median der Spannen),
# Fahrstreifen nach RASt 06; Bordstein Granit-Hochbord 12–16 cm (Recherche-Median 14 cm).
DEFAULTS = {
    #               Fahrstreifen  Gehweg  Bord_m  Grünstreifen
    "motorway":      (3.75, 0.0, 0.00, 0.0),
    "trunk":         (3.50, 0.0, 0.12, 0.0),
    "primary":       (3.25, 3.5, 0.14, 2.0),
    "secondary":     (3.25, 3.0, 0.14, 1.5),
    "tertiary":      (3.00, 2.75, 0.14, 0.0),
    "unclassified":  (2.75, 2.25, 0.12, 0.0),
    "residential":   (2.75, 2.25, 0.12, 0.0),
    "living_street": (2.25, 0.0, 0.03, 0.0),
    "service":       (3.00, 0.0, 0.10, 0.0),
    "pedestrian":    (0.00, 0.0, 0.00, 0.0),
}
# Reihenfolge der Fahrbahnquellen (gemessen vor abgeleitet; Reihenfolge der Ableitungen kalibriert gegen
# Flächenmessungen in ganz Dresden, siehe data/research/strassenraum.md)
FB_ORDER = ["osm_flaeche", "osm_bordstein", "osm_width", "kombiniert", "raum_abgeleitet", "baumreihen",
            "gehweglinien", "fahrstreifen"]
DERIVED = ("raum_abgeleitet", "baumreihen", "gehweglinien", "fahrstreifen")
# Restabweichung "Straßenraum minus Regelgehwege, Grünstreifen, Hochbord-Radwege" gegenüber gemessenen
# Fahrbahnen (area:highway) und width-Tags, Kalibrierung über alle 117 Kacheln (2026-11): Straßenraum enthält
# zusätzlich Parkbuchten, Vorgartenstreifen, breitere Gehwege an Hauptstraßen
RAUM_KORR = {"Haupt": -2.0, "tertiary": -1.0, "Wohn": -1.0, "service": -1.0}


def _klasse(hw):
    hw = (hw or "").replace("_link", "")
    if hw in ("primary", "secondary", "trunk"):
        return "Haupt"
    if hw == "tertiary":
        return "tertiary"
    if hw in ("residential", "unclassified", "living_street", "road", "busway"):
        return "Wohn"
    if hw == "service":
        return "service"
    return None
HOEHE_BORD = {"raised": 0.14, "regular": 0.12, "yes": 0.12, "lowered": 0.03, "flush": 0.0, "no": 0.0,
              "rolled": 0.06, "lowered_and_sloped": 0.03}


def defaults_for(highway):
    """Regelquerschnitt für eine Straßenklasse: dict(fahrstreifen_m, gehweg_m, bordstein_m, gruen_m)."""
    base = (highway or "").replace("_link", "")
    v = DEFAULTS.get(base, DEFAULTS["residential"])
    return {"fahrstreifen_m": v[0], "gehweg_m": v[1], "bordstein_m": v[2], "gruen_m": v[3]}


def game_xz(e, n):
    return float(e) - ORIGIN_E, -(float(n) - ORIGIN_N)


# ----------------------------------------------------------------------------------------------
# Laden
# ----------------------------------------------------------------------------------------------
@lru_cache(maxsize=3)
def _tile_layers(e_km, n_km):
    p = SR_DIR / "tiles" / f"{e_km}_{n_km}.json"
    if not p.exists():
        raise FileNotFoundError(f"{p} fehlt – zuerst tools/fetch_strassenraum.py ausführen")
    return json.loads(p.read_text())["layers"]


@lru_cache(maxsize=6)
def _osm(e_km, n_km, kind):
    p = RAW / "tiles" / f"{e_km}_{n_km}" / "osm" / f"{kind}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text()).get("elements", [])


def _utm_coords(geom):
    lon = np.array([p["lon"] for p in geom])
    lat = np.array([p["lat"] for p in geom])
    x, y = _TO_UTM.transform(lon, lat)
    return np.column_stack([x, y])


def _num(v):
    if v is None:
        return None
    m = re.match(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*(m|meter)?\s*$", str(v))
    return float(m.group(1).replace(",", ".")) if m else None


def _norm_name(s):
    s = (s or "").lower().replace("str.", "straße").replace("strasse", "straße")
    return re.sub(r"[^a-zäöüß0-9]", "", s)


# ----------------------------------------------------------------------------------------------
# Strahl-Schnitt mit Liniensegmenten (vektorisiert)
# ----------------------------------------------------------------------------------------------
class _Segs:
    """Liniensegmente mit STRtree; cast() schneidet Querschnittslinien (Transekte) mit allen Segmenten."""

    def __init__(self, lines, attrs=None):
        a, b, li = [], [], []
        for k, c in enumerate(lines):
            c = np.asarray(c, dtype=np.float64)
            if len(c) < 2:
                continue
            a.append(c[:-1])
            b.append(c[1:])
            li.append(np.full(len(c) - 1, k))
        if a:
            self.A = np.concatenate(a)
            self.B = np.concatenate(b)
            self.line = np.concatenate(li)
        else:
            self.A = self.B = np.zeros((0, 2))
            self.line = np.zeros(0, dtype=int)
        self.attrs = attrs
        d = self.B - self.A
        ln = np.hypot(d[:, 0], d[:, 1])
        self.dir = d / np.maximum(ln, 1e-9)[:, None]
        self.tree = STRtree(shapely.linestrings(np.stack([self.A, self.B], axis=1))) if len(self.A) else None

    def cast(self, P, N, L, tang=None, min_cos=None):
        """Transekte P - L*N .. P + L*N. Rückgabe (ti, s, seg): Transekt-Index, vorzeichenbehafteter Abstand
        (+ = Richtung N = links), Segmentindex. Optional nur Segmente mit |cos(Winkel zu tang)| >= min_cos."""
        if self.tree is None or not len(P):
            return np.zeros(0, int), np.zeros(0), np.zeros(0, int)
        p0 = P - L * N
        p1 = P + L * N
        tr = shapely.linestrings(np.stack([p0, p1], axis=1))
        ti, sj = self.tree.query(tr, predicate="intersects")
        if not len(ti):
            return ti, np.zeros(0), sj
        r = p1[ti] - p0[ti]
        sv = self.B[sj] - self.A[sj]
        qp = self.A[sj] - p0[ti]
        den = r[:, 0] * sv[:, 1] - r[:, 1] * sv[:, 0]
        ok = np.abs(den) > 1e-12
        t = np.where(ok, (qp[:, 0] * sv[:, 1] - qp[:, 1] * sv[:, 0]) / np.where(ok, den, 1.0), np.nan)
        s = (t - 0.5) * 2.0 * L
        keep = ok & np.isfinite(s)
        if tang is not None and min_cos is not None:
            c = np.abs(self.dir[sj, 0] * tang[ti, 0] + self.dir[sj, 1] * tang[ti, 1])
            keep &= c >= min_cos
        return ti[keep], s[keep], sj[keep]


def _nearest_sides(n, ti, s, min_d=0.05):
    """Je Transekt kleinster Abstand links (s>0) und rechts (s<0); NaN, wenn nichts getroffen."""
    left = np.full(n, np.inf)
    right = np.full(n, np.inf)
    m = s > min_d
    np.minimum.at(left, ti[m], s[m])
    m = s < -min_d
    np.minimum.at(right, ti[m], -s[m])
    left[~np.isfinite(left)] = np.nan
    right[~np.isfinite(right)] = np.nan
    return left, right


def _nearest_sides_idx(n, ti, s, seg, min_d):
    """Wie _nearest_sides, zusätzlich Segmentindex des Treffers je Seite (-1 = keiner)."""
    out = []
    for sign in (1, -1):
        d = np.full(n, np.inf)
        idx = np.full(n, -1)
        m = (s * sign) > min_d
        tt, dd, gg = ti[m], s[m] * sign, seg[m]
        order = np.lexsort((dd, tt))
        tt, dd, gg = tt[order], dd[order], gg[order]
        first = np.ones(len(tt), bool)
        first[1:] = tt[1:] != tt[:-1]
        d[tt[first]] = dd[first]
        idx[tt[first]] = gg[first]
        d[~np.isfinite(d)] = np.nan
        out.append((d, idx))
    return out


def _poly_rings(geom):
    """Alle Ringe (außen + innen) einer (Multi)Polygon-Geometrie als Koordinatenarrays."""
    out = []
    for p in getattr(geom, "geoms", [geom]):
        if p.is_empty or p.geom_type != "Polygon":
            continue
        out.append(np.asarray(p.exterior.coords))
        out.extend(np.asarray(r.coords) for r in p.interiors)
    return out


def _union(geoms):
    geoms = [g if g.is_valid else shapely.make_valid(g) for g in geoms if g is not None and not g.is_empty]
    geoms = [g for g in geoms if g.geom_type in ("Polygon", "MultiPolygon", "GeometryCollection")]
    if not geoms:
        return None
    u = shapely.union_all(geoms)
    if u.geom_type == "GeometryCollection":
        u = shapely.union_all([g for g in u.geoms if g.geom_type in ("Polygon", "MultiPolygon")])
    shapely.prepare(u)
    return u


class _Extents:
    """Ausdehnung einer Flächenvereinigung quer zur Achse (zusammenhängendes Stück, das den Punkt enthält)."""

    def __init__(self, union):
        self.u = union
        self.segs = _Segs(_poly_rings(union)) if union is not None else None

    def measure(self, P, N, L, open_nan=False):
        """open_nan: Seiten ohne Grenze innerhalb L -> NaN (sonst L)."""
        n = len(P)
        if self.u is None or not n:
            return np.zeros(n, bool), np.full(n, np.nan), np.full(n, np.nan)
        inside = shapely.contains_xy(self.u, P[:, 0], P[:, 1])
        ti, s, _ = self.segs.cast(P, N, L)
        left, right = _nearest_sides(n, ti, s, 0.0)
        if not open_nan:
            left = np.where(inside & np.isnan(left), L, left)      # offen bis Strahlende
            right = np.where(inside & np.isnan(right), L, right)
        left[~inside] = np.nan
        right[~inside] = np.nan
        return inside, left, right


# ----------------------------------------------------------------------------------------------
# Kachel-Kontext (alle Geometrien einmal je Kachel)
# ----------------------------------------------------------------------------------------------
class _Ctx:
    def __init__(self, e_km, n_km):
        self.e, self.n = e_km, n_km
        self.x0, self.y0 = e_km * 1000.0, n_km * 1000.0
        self.x1, self.y1 = self.x0 + 2000.0, self.y0 + 2000.0
        wx0, wy0, wx1, wy1 = self.x0 - WINDOW, self.y0 - WINDOW, self.x1 + WINDOW, self.y1 + WINDOW
        self.win = shapely.box(wx0, wy0, wx1, wy1)
        L = _tile_layers(e_km, n_km)
        self.layers = L

        def polys(layer, pred=lambda p: True):
            out = []
            for f in L.get(layer, []):
                if f.get("geometry") and pred(f["properties"]):
                    g = shape(f["geometry"])
                    if g.intersects(self.win):
                        out.append(g)
            return out

        # Straßenraum (öffentliche Verkehrsfläche) – ALKIS, Ersatz: Dresdner "Straßenflächen"
        self.raum = _Extents(_union(polys("alkis_verkehr", lambda p: p.get("nutzart") in ALKIS_RAUM)))
        self.raum_dd = _Extents(_union(polys("strassenflaechen")))
        # Fahrbahnflächen und Inseln aus OSM area:highway
        self.carriage = _Extents(_union(polys("osm_area_highway",
                                              lambda p: p.get("area:highway") in AREA_CARRIAGE)))
        self.islands = _union(polys("osm_area_highway", lambda p: p.get("area:highway") == "traffic_island"))
        # Straßengrün: Dresden F31 Verkehrsbegleitgrün + OSM-Grasflächen
        green = polys("gruenflaechen", lambda p: str(p.get("desk2", "")).startswith("F3"))
        self.green_osm = []
        for el in _osm(e_km, n_km, "landuse"):
            t = el.get("tags", {})
            if el["type"] == "way" and (t.get("landuse") in GREEN_LANDUSE or t.get("natural") == "grassland") \
                    and len(el.get("geometry", [])) >= 4:
                c = _utm_coords(el["geometry"])
                if np.allclose(c[0], c[-1]):
                    g = Polygon(c)
                    if g.is_valid and g.intersects(self.win):
                        self.green_osm.append((g, t.get("landuse") or t.get("natural")))
        self.green = _union(green + [g for g, _ in self.green_osm])
        self.green_f31 = _union(green)
        # Gebäude (OSM) – nur Ränder
        brings = []
        for el in _osm(e_km, n_km, "buildings"):
            if "building" not in el.get("tags", {}):
                continue
            if el["type"] == "way" and el.get("geometry"):
                brings.append(_utm_coords(el["geometry"]))
            elif el["type"] == "relation":
                for m in el.get("members", []):
                    if m.get("geometry"):
                        brings.append(_utm_coords(m["geometry"]))
        self.bsegs = _Segs(brings)
        # Bordsteinlinien (OSM barrier=kerb) und Bordsteinpunkte
        kl, ka, self.kerb_pts = [], [], []
        for f in L.get("osm_kerbs", []):
            g = f["geometry"]
            if g["type"] == "LineString":
                kl.append(np.asarray(g["coordinates"]))
                ka.append(f["properties"].get("kerb") or "raised")
            elif g["type"] == "Point":
                self.kerb_pts.append((g["coordinates"], f["properties"]))
        self.kerb_lines = list(zip(kl, ka))
        self.ksegs = _Segs(kl, ka)
        # separat erfasste Gehwege
        sl, sw = [], []
        for f in L.get("osm_sidewalks", []):
            g = f["geometry"]
            if g["type"] == "LineString":
                sl.append(np.asarray(g["coordinates"]))
                sw.append(_num(f["properties"].get("width")))
        self.swsegs = _Segs(sl, sw)
        # Straßenbahngleise
        rl = [_utm_coords(el["geometry"]) for el in _osm(e_km, n_km, "rail")
              if el.get("tags", {}).get("railway") == "tram" and el.get("geometry")]
        self.tram = _Segs(rl)
        # OSM-Straßen (Achsen) und Fußgängerflächen
        self.ways = []
        self.ped_areas = []
        for el in _osm(e_km, n_km, "roads"):
            t = el.get("tags", {})
            if el["type"] != "way" or t.get("highway") not in CAR or len(el.get("geometry", [])) < 2:
                continue
            xy = _utm_coords(el["geometry"])
            if t.get("area") == "yes":
                if t.get("highway") == "pedestrian" and len(xy) >= 4:
                    g = Polygon(xy)
                    if g.is_valid and g.area > 50:
                        self.ped_areas.append((el["id"], t, g))
                continue
            self.ways.append((el["id"], t, xy))
        self.waysegs = _Segs([w[2] for w in self.ways], [w[0] for w in self.ways])
        # Dresdner Radverkehrsanlagen
        rad = []
        rattr = []
        for f in L.get("radverkehr", []):
            g = f["geometry"]
            cs = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"] if g["type"] == "MultiLineString" else []
            for c in cs:
                rad.append(np.asarray(c))
                rattr.append(f["properties"])
        self.radsegs = _Segs(rad, rattr)


@lru_cache(maxsize=2)
def _ctx(e_km, n_km):
    return _Ctx(e_km, n_km)


# ----------------------------------------------------------------------------------------------
# Bäume
# ----------------------------------------------------------------------------------------------
_STREETNAME = re.compile(r"(stra(ß|ss)e|str\.|allee|ufer|platz|ring|weg|gasse|brücke|chaussee|promenade|damm)", re.I)


def trees_for_tile(e_km, n_km, margin=0.0, standort=True):
    """Stadtbäume (Dresdner Baumkataster, dl-de/by-2-0) strikt in der Kachel (± margin m).

    Rückgabe: Liste von dicts {x, z, art, art_bot, hoehe_m, krone_m, stamm_cm, alter_j, pflanzjahr,
    objekt (Straße/Anlage laut Kataster), strassenbaum (bool), standort ('baumscheibe'|'gruenstreifen'|
    'strassenraum'|'ausserhalb', nur mit standort=True)}. standort: im ALKIS-Straßenraum auf Grün/Insel ->
    'gruenstreifen', sonst Straßenbaum -> 'baumscheibe' bzw. Platz/Anlage -> 'strassenraum'; außerhalb des
    Straßenraums nur Dresdner Verkehrsbegleitgrün -> 'gruenstreifen', sonst 'ausserhalb' (Parks, Höfe, Schulen). Fehlende Werte = None.
    Hinweis "jalter": überwiegend Alter in Jahren; Werte > 1700 sind Pflanzjahre (beides wird umgerechnet,
    Bezugsjahr = Jahr der letzten Änderung). pflanzjahr ist daher eine Näherung (±1–2 Jahre).
    """
    x0, y0 = e_km * 1000.0 - margin, n_km * 1000.0 - margin
    x1, y1 = (e_km + 2) * 1000.0 + margin, (n_km + 2) * 1000.0 + margin
    out = []
    pts = []
    for f in _tile_layers(e_km, n_km).get("stadtbaeume", []):
        x, y = f["geometry"]["coordinates"][:2]
        if not (x0 <= x < x1 and y0 <= y < y1):
            continue
        p = f["properties"]
        ref = 2026
        ad = p.get("aend_dat") or ""
        if len(ad) >= 10 and ad[6:10].isdigit():
            ref = int(ad[6:10])
        ja = (p.get("jalter") or "").strip()
        alter = pj = None
        if ja.isdigit():
            v = int(ja)
            if v > 1700:
                pj, alter = v, max(0, ref - v)
            else:
                alter, pj = v, ref - v
        gx, gz = game_xz(x, y)
        name = p.get("name") or ""
        out.append({"x": round(gx, 2), "z": round(gz, 2), "e": x, "n": y,
                    "art": p.get("art_deutsch") or None, "art_bot": p.get("art_botanisch") or None,
                    "hoehe_m": p.get("baumhoehe_akt"), "krone_m": p.get("kronendurchmesser_akt"),
                    "stamm_cm": p.get("stammdurchmesser_akt"), "alter_j": alter, "pflanzjahr": pj,
                    "objekt": name, "strassenbaum": bool(_STREETNAME.search(name)), "id": f.get("id")})
        pts.append((x, y))
    if standort and out:
        c = _ctx(e_km, n_km)
        P = np.asarray(pts)
        in_raum = shapely.contains_xy(c.raum.u, P[:, 0], P[:, 1]) if c.raum.u is not None else np.zeros(len(P), bool)
        in_gr = shapely.contains_xy(c.green, P[:, 0], P[:, 1]) if c.green is not None else np.zeros(len(P), bool)
        in_f31 = shapely.contains_xy(c.green_f31, P[:, 0], P[:, 1]) if c.green_f31 is not None else np.zeros(len(P), bool)
        in_isl = shapely.contains_xy(c.islands, P[:, 0], P[:, 1]) if c.islands is not None else np.zeros(len(P), bool)
        for t, r, g, f31, i in zip(out, in_raum, in_gr, in_f31, in_isl):
            t["standort"] = ("gruenstreifen" if (g or i) else "baumscheibe") if r else \
                            ("gruenstreifen" if f31 else "ausserhalb")
            if r and not (g or i) and not t["strassenbaum"]:
                t["standort"] = "strassenraum"
    return out


# ----------------------------------------------------------------------------------------------
# Fahrbahn- und Gehwegbreiten
# ----------------------------------------------------------------------------------------------
def _stations(c, step=4.0, skip=6.0):
    d = np.diff(c, axis=0)
    sl = np.hypot(d[:, 0], d[:, 1])
    good = sl > 1e-6
    if not good.any():
        return np.zeros((0, 2)), np.zeros((0, 2)), 0.0
    c = np.vstack([c[0], c[1:][good]])
    d = d[good]
    sl = sl[good]
    cum = np.concatenate([[0.0], np.cumsum(sl)])
    L = cum[-1]
    if L < 2 * skip + step:
        pos = np.array([L / 2])
    else:
        pos = np.arange(skip, L - skip + 1e-6, step)
    k = np.clip(np.searchsorted(cum, pos, side="right") - 1, 0, len(sl) - 1)
    f = (pos - cum[k]) / sl[k]
    P = c[k] + d[k] * f[:, None]
    T = d[k] / sl[k][:, None]
    return P, T, L


def _side_tag(t, side, key):
    for k in (f"sidewalk:{side}:{key}", f"sidewalk:both:{key}", f"sidewalk:{key}"):
        if k in t:
            return t[k]
    return None


def _sidewalk_state(t, side):
    """'yes' | 'no' | 'separate' | None für eine Seite."""
    v = t.get(f"sidewalk:{side}") or t.get("sidewalk:both")
    if v:
        return v
    s = t.get("sidewalk")
    if s in ("both",):
        return "yes"
    if s in ("no", "none"):
        return "no"
    if s == "separate":
        return "separate"
    if s in ("left", "right"):
        return "yes" if s == side else "no"
    return None


CYCLE_LANE_W = 1.6      # Radfahr-/Schutzstreifen auf der Fahrbahn (Dresden: 1,5–1,85 m)
CYCLE_TRACK_W = 1.6     # Hochbord-Radweg im Seitenraum


def _cycle(t, side):
    """'lane' | 'track' | None für eine Seite (OSM cycleway*-Schema)."""
    v = t.get(f"cycleway:{side}") or t.get("cycleway:both") or t.get("cycleway")
    if v in ("lane", "opposite_lane", "shared_busway"):
        return "lane"
    if v in ("track", "opposite_track"):
        return "track"
    return None


def _green_between(c, P, N, start, R, every=2):
    """Median-Breite der Grünflächen entlang der Querschnitte von 'start' (Achsabstand) bis zur
    Straßenraumgrenze R (max. 15 m); None, wenn keine Grünflächen bekannt."""
    if c.green is None or not len(P):
        return None
    acc = []
    st = np.broadcast_to(np.asarray(start, dtype=np.float64), (len(P),))
    for j in range(0, len(P), every):
        if not np.isfinite(st[j]):
            continue
        end = R[j] if np.isfinite(R[j]) else st[j] + 6.0
        if end - st[j] < 0.5:
            acc.append(0.0)
            continue
        ds = np.arange(st[j] + 0.25, min(end, st[j] + 15.0), 0.5)
        xy = P[j] + N[j] * ds[:, None]
        acc.append(0.5 * float(shapely.contains_xy(c.green, xy[:, 0], xy[:, 1]).sum()))
    return _med(acc, 1)


def _med(a, minn=2):
    a = np.asarray(a, dtype=np.float64)
    a = a[np.isfinite(a)]
    if len(a) < minn:
        return None
    return float(np.median(a))


def _r(v, nd=2):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), nd)


def road_widths_for_tile(e_km, n_km, ways=None, step=4.0):
    """Breiten je OSM-Weg (Fahrzeugstraßen + Fußgängerzonen), die die Kachel berühren.

    ways: optional eigene Liste [(id, tags, utm_coords Nx2)], sonst OSM roads.json der Kachel.
    Rückgabe {way_id: dict}. Wichtigste Felder (Meter; None = unbekannt):
      fahrbahn_m + fahrbahn_quelle: 'osm_flaeche' (gemessen aus area:highway-Flächen, Median der Querschnitte) |
        'osm_bordstein' (barrier=kerb-Linien) | 'osm_width' (Tag) | 'kombiniert' (Median aller verfügbaren
        Ableitungen, sobald >= 2 vorliegen) | 'raum_abgeleitet' (ALKIS-Straßenraum minus Regel-Gehwege,
        kalibriert) | 'baumreihen' (Abstand der Straßenbaumreihen minus 2 x 1,2 m) | 'gehweglinien'
        (separat erfasste Gehwege) | 'fahrstreifen' (lanes x Regelbreite + Parkstreifen)
      messungen {quelle: wert} (alle verfügbaren Schätzungen), fahrbahn_n, fahrbahn_spanne [p25, p75],
      osm_width, lanes, oneway, achsversatz_m (+ = Fahrbahnmitte links der OSM-Achse; nur Flächenmessung),
      zweibahnig, gegenfahrbahn_seite, abstand_gegenfahrbahn_m, raum_gesamt_m (ganzer Straßenraum beider Fahrbahnen),
      raum_m / raum_links_m / raum_rechts_m (öffentlicher Straßenraum ALKIS, Achse -> Grenze; None = offen/Platz),
      flucht_links_m / flucht_rechts_m (Achse -> erste Gebäudekante), bord_links_m / bord_rechts_m (Achse -> Bord),
      seitenraum_*_m (Bord -> Straßenraumgrenze), gehweg_*_m + gehweg_*_quelle, gruen_*_m (Grünstreifen),
      baeume_* {n, abstand_m, versatz_m} (Stadtbäume, Versatz von der Achse), tram_gleise, radanlage(_lage).
    Fußgängerflächen (highway=pedestrian + area=yes) erscheinen mit flaeche=True, raum_m (Breite) und laenge_m.
    """
    c = _ctx(e_km, n_km)
    if ways is None:
        ways = c.ways
    tile = shapely.box(c.x0, c.y0, c.x1, c.y1)
    res = {}
    for wid, t, poly in c.ped_areas:
        if poly.intersects(tile):
            r = poly.minimum_rotated_rectangle
            xy = np.asarray(r.exterior.coords)
            e1 = float(np.hypot(*(xy[1] - xy[0])))
            e2 = float(np.hypot(*(xy[2] - xy[1])))
            res[wid] = {"name": t.get("name"), "highway": "pedestrian", "flaeche": True,
                        "raum_m": _r(min(e1, e2), 1), "laenge_m": _r(max(e1, e2), 1), "flaeche_m2": _r(poly.area, 0),
                        "fahrbahn_m": None, "fahrbahn_quelle": None, "messungen": {}}
    sel = []
    for wid, t, xy in ways:
        if len(xy) < 2 or not shapely.intersects(tile, LineString(xy)):
            continue
        P, T, L = _stations(np.asarray(xy, dtype=np.float64), step=step)
        inwin = (P[:, 0] > c.x0 - WINDOW + 50) & (P[:, 0] < c.x1 + WINDOW - 50) & \
                (P[:, 1] > c.y0 - WINDOW + 50) & (P[:, 1] < c.y1 + WINDOW - 50)
        if inwin.any():
            sel.append((wid, t, P[inwin], T[inwin], L))
    if not sel:
        return res
    wi = np.concatenate([np.full(len(s_[2]), k) for k, s_ in enumerate(sel)])
    P = np.concatenate([s_[2] for s_ in sel])
    T = np.concatenate([s_[3] for s_ in sel])
    N = np.column_stack([-T[:, 1], T[:, 0]])     # links der Richtung
    n = len(P)
    sel_wid = np.array([s_[0] for s_ in sel])

    # --- Messungen je Querschnitt ---
    c_in, cL, cR = c.carriage.measure(P, N, 25.0)
    _, rL, rR = c.raum.measure(P, N, 40.0, open_nan=True)
    _, dL, dR = c.raum_dd.measure(P, N, 40.0, open_nan=True)
    ti, s, _ = c.bsegs.cast(P, N, 60.0)
    bL, bR = _nearest_sides(n, ti, s, 0.3)
    ti, s, _ = c.ksegs.cast(P, N, 25.0, T, 0.8)
    kL, kR = _nearest_sides(n, ti, s, 1.0)
    ti, s, sg = c.swsegs.cast(P, N, 30.0, T, 0.8)
    (sL, sLi), (sR, sRi) = _nearest_sides_idx(n, ti, s, sg, 1.5)
    if len(c.swsegs.line):
        sw_w = np.array([np.nan if v is None else v for v in c.swsegs.attrs], dtype=np.float64)
        swL_w = np.where(sLi >= 0, sw_w[c.swsegs.line[np.maximum(sLi, 0)]], np.nan)
        swR_w = np.where(sRi >= 0, sw_w[c.swsegs.line[np.maximum(sRi, 0)]], np.nan)
    else:
        swL_w = swR_w = np.full(n, np.nan)
    ti, s, _ = c.tram.cast(P, N, 8.0, T, 0.85)
    tram_n = np.bincount(ti, minlength=n) if len(ti) else np.zeros(n, int)
    # andere (parallele) Fahrbahnachsen je Seite; gleichnamige = Gegenfahrbahn
    wti, ws, wsg = c.waysegs.cast(P, N, 60.0, T, 0.9)
    if len(wti):
        seg_way = np.array(c.waysegs.attrs)[c.waysegs.line[wsg]]
        other = (seg_way != sel_wid[wi[wti]]) & (np.abs(ws) > 1.0)
        own_name = np.array([_norm_name(s_[1].get("name")) for s_ in sel])
        nm = {w[0]: _norm_name(w[1].get("name")) for w in c.ways}
        same = other & np.array([bool(own_name[wi[a]]) and nm.get(b) == own_name[wi[a]] for a, b in zip(wti, seg_way)])
        oL, oR = _nearest_sides(n, wti[other], ws[other], 1.0)
        zL, zR = _nearest_sides(n, wti[same], ws[same], 1.0)
    else:
        oL = oR = zL = zR = np.full(n, np.nan)
    # Gehweglinien hinter einer anderen Fahrbahn oder > 15 m sind nicht die eigenen
    sL = np.where((np.isfinite(oL) & (sL > oL)) | (sL > 15.0), np.nan, sL)
    sR = np.where((np.isfinite(oR) & (sR > oR)) | (sR > 15.0), np.nan, sR)
    ti_r, s_r, sg_r = c.radsegs.cast(P, N, 15.0, T, 0.7)

    # Bäume -> nächster Weg (alle Wege im Fenster); nur Bäume im öffentlichen Straßenraum zählen
    tree_side = {}
    trees = c.layers.get("stadtbaeume", [])
    sel_idx = {s_[0]: k for k, s_ in enumerate(sel)}
    if trees:
        TP = np.array([f["geometry"]["coordinates"][:2] for f in trees])
        in_raum = shapely.contains_xy(c.raum.u, TP[:, 0], TP[:, 1]) if c.raum.u is not None else np.ones(len(TP), bool)
        full = [LineString(w[2]) for w in ways if len(w[2]) >= 2]
        fid = [w[0] for w in ways if len(w[2]) >= 2]
        pts = shapely.points(TP)
        ti_t, wj = STRtree(full).query_nearest(pts, max_distance=22.0, return_distance=False, all_matches=False)
        for a, b in zip(ti_t, wj):
            k_ = sel_idx.get(fid[b])
            if k_ is None or not in_raum[a]:
                continue
            ln = full[b]
            pos = ln.project(pts[a])
            p0 = np.asarray(ln.interpolate(max(0.0, pos - 1.0)).coords[0])
            p1 = np.asarray(ln.interpolate(min(ln.length, pos + 1.0)).coords[0])
            tv = p1 - p0
            v = TP[a] - p0
            side = "links" if tv[0] * v[1] - tv[1] * v[0] > 0 else "rechts"
            tree_side.setdefault((k_, side), []).append((pos, float(shapely.distance(pts[a], ln))))

    for k, (wid, t, _P, _T, Lw) in enumerate(sel):
        m = wi == k
        idx = np.nonzero(m)[0]
        nm_ = int(m.sum())
        need = max(2, int(math.ceil(0.3 * nm_)))
        hw = t.get("highway")
        d = defaults_for(hw)
        o = {"name": t.get("name"), "highway": hw, "laenge_m": _r(Lw, 1), "querschnitte": nm_,
             "lanes": _num(t.get("lanes")), "oneway": t.get("oneway") in ("yes", "1", "-1", "true")}
        osm_w = _num(t.get("width")) or _num(t.get("width:carriageway"))
        if osm_w is not None and not (2.0 <= osm_w <= 45.0):
            osm_w = None
        o["osm_width"] = osm_w
        # Gegenfahrbahn
        nzl, nzr = int(np.isfinite(zL[m]).sum()), int(np.isfinite(zR[m]).sum())
        zweibahnig = bool(o["oneway"] and t.get("name") and max(nzl, nzr) >= need)
        o["zweibahnig"] = zweibahnig
        inner = None
        if zweibahnig:
            inner = "links" if nzl >= nzr else "rechts"
            o["gegenfahrbahn_seite"] = inner
            o["abstand_gegenfahrbahn_m"] = _r(_med((zL if inner == "links" else zR)[m], 1), 1)
        meas = {}
        # 1) Fläche
        both = c_in[m] & np.isfinite(cL[m]) & np.isfinite(cR[m]) & (cL[m] < 25) & (cR[m] < 25)
        nf = int(both.sum())
        if nf >= need:
            wv = cL[m][both] + cR[m][both]
            meas["osm_flaeche"] = float(np.median(wv))
            o["achsversatz_m"] = _r(float(np.median((cL[m][both] - cR[m][both]) / 2)))
            o["fahrbahn_spanne"] = [_r(float(np.percentile(wv, 25))), _r(float(np.percentile(wv, 75)))]
        # 2) Bordsteinlinien
        kb = np.isfinite(kL[m]) & np.isfinite(kR[m])
        if kb.sum() >= max(3, need):
            meas["osm_bordstein"] = float(np.median(kL[m][kb] + kR[m][kb]))
        # 3) Tag
        if osm_w is not None:
            meas["osm_width"] = osm_w
        # Straßenraum (ALKIS; Ersatz Dresdner Straßenflächen)
        RL, RR, raum_src = rL[m].copy(), rR[m].copy(), "alkis"
        if (np.isfinite(RL) | np.isfinite(RR)).sum() < need:
            if (np.isfinite(dL[m]) | np.isfinite(dR[m])).sum() >= need:
                RL, RR, raum_src = dL[m].copy(), dR[m].copy(), "dresden_strassenflaechen"
        if inner is not None:
            full = np.isfinite(RL) & np.isfinite(RR)
            if full.sum() >= need:
                o["raum_gesamt_m"] = _r(float(np.median(RL[full] + RR[full])), 1)   # ganzer Querschnitt
        if inner == "links":
            RL[:] = np.nan
        elif inner == "rechts":
            RR[:] = np.nan
        rb = np.isfinite(RL) & np.isfinite(RR)
        if rb.sum() >= need:
            o["raum_m"] = _r(float(np.median(RL[rb] + RR[rb])), 1)
        o["raum_links_m"] = _r(_med(RL, need), 1)
        o["raum_rechts_m"] = _r(_med(RR, need), 1)
        o["raum_quelle"] = raum_src if (o["raum_links_m"] or o["raum_rechts_m"]) else None
        o["flucht_links_m"] = _r(_med(bL[m]), 1)
        o["flucht_rechts_m"] = _r(_med(bR[m]), 1)
        # 4) Fahrstreifen-Schätzung
        est = None
        if hw != "pedestrian":
            lw = d["fahrstreifen_m"]
            lanes = o["lanes"]
            est = lanes * lw if lanes else (max(3.5, lw + 0.5) if o["oneway"] else 2 * lw)
            if hw == "living_street" and not lanes:
                est = 4.5
            if hw == "service" and not lanes:
                est = 3.0 if o["oneway"] else 4.0
            if _pk is not None:
                pl = _pk.lane_widths(_pk.park_sides(t))
                est += pl[0] + pl[1]
            est += CYCLE_LANE_W * sum(_cycle(t, sd) == "lane" for sd in ("left", "right"))
            meas["fahrstreifen"] = est
        if not zweibahnig and hw != "pedestrian":
            # 5) aus Straßenraum: minus Gehwege (Regel), gemessene Grünstreifen und Hochbord-Radwege
            kl_ = _klasse(hw)
            if "raum_m" in o and kl_ is not None:
                abz = 0.0
                for sd, R_ in (("left", RL), ("right", RR)):
                    abz += 0.0 if _sidewalk_state(t, sd) == "no" else d["gehweg_m"]
                    abz += _green_between(c, P[m], N[m] * (1.0 if sd == "left" else -1.0), est / 2, R_) or 0.0
                    if _cycle(t, sd) == "track":
                        abz += CYCLE_TRACK_W
                v = o["raum_m"] - abz + RAUM_KORR[kl_]
                meas["raum_abgeleitet"] = min(max(v, 0.8 * est), est + 6.0)
            # 6) Baumreihen beidseitig (Baummitte ~1,2 m hinter dem Bord); an Hauptstraßen unzuverlässig
            tl, tr_ = tree_side.get((k, "links"), []), tree_side.get((k, "rechts"), [])
            if len(tl) >= 3 and len(tr_) >= 3 and kl_ != "Haupt":
                ol = float(np.median([v for _, v in tl]))
                orr = float(np.median([v for _, v in tr_]))
                if 2.5 <= ol <= 15 and 2.5 <= orr <= 15:
                    meas["baumreihen"] = ol + orr - 2.4
            # 7) separate Gehwege beidseitig
            sb = np.isfinite(sL[m]) & np.isfinite(sR[m])
            if sb.sum() >= max(3, need):
                wl = np.where(np.isfinite(swL_w[m]), swL_w[m], 2.5)
                wr = np.where(np.isfinite(swR_w[m]), swR_w[m], 2.5)
                meas["gehweglinien"] = float(np.median((sL[m] + sR[m] - wl / 2 - wr / 2 - 1.0)[sb]))

        der = [meas[q] for q in DERIVED if q in meas]
        if len(der) >= 2:
            meas["kombiniert"] = float(np.median(der))
        src = next((q for q in FB_ORDER if q in meas), None)
        o["fahrbahn_m"] = _r(meas[src]) if src else None
        o["fahrbahn_quelle"] = src
        o["fahrbahn_n"] = nf if src == "osm_flaeche" else int(kb.sum()) if src == "osm_bordstein" else None
        o["messungen"] = {q: _r(v) for q, v in meas.items()}

        # Bordsteinlage je Seite (Achse -> Bord)
        if src == "osm_flaeche":
            bordL = np.where(both, cL[m], np.nan)
            bordR = np.where(both, cR[m], np.nan)
        elif src == "osm_bordstein":
            bordL, bordR = kL[m], kR[m]
        else:
            half = (o["fahrbahn_m"] or 0.0) / 2
            bordL = np.full(nm_, half)
            bordR = np.full(nm_, half)
        o["bord_links_m"] = _r(_med(bordL, 1))
        o["bord_rechts_m"] = _r(_med(bordR, 1))

        Pm, Nm = P[m], N[m]
        for side, R_, B_, S_, SW_, sgn, bord in (("links", RL, bL[m], sL[m], swL_w[m], 1.0, bordL),
                                                  ("rechts", RR, bR[m], sR[m], swR_w[m], -1.0, bordR)):
            seit = np.where(np.isfinite(R_) & np.isfinite(bord), R_ - bord, np.nan)
            seit[seit < 0] = np.nan          # Flurstücksgrenze liegt in der Fahrbahn (z. B. Gleisflurstück)
            o[f"seitenraum_{side}_m"] = _r(_med(seit, need), 1)
            # Grünstreifen: Abtastung alle 0,5 m zwischen Bord und Raumgrenze (max. 15 m)
            gw = _green_between(c, Pm, Nm * sgn, bord, R_) if side != inner else None
            o[f"gruen_{side}_m"] = _r(gw, 1)
            # Gehweg
            state = _sidewalk_state(t, side)
            tagw = _num(_side_tag(t, side, "width"))
            if state == "no" and np.isfinite(S_).sum() >= need:
                state = "separate"           # alte Kartierung: sidewalk=no trotz separat gezeichnetem Gehweg
            w = q = None
            if side == inner:
                w, q = 0.0, "mittelstreifen"
            elif state == "no":
                w, q = 0.0, "osm_tag"
            elif tagw is not None:
                w, q = tagw, "osm_tag"
            elif hw == "pedestrian":
                pass
            else:
                ok = np.isfinite(S_)
                if state == "separate" and ok.sum() >= 2:
                    wl_tag = _med(SW_[ok], 1)
                    if wl_tag is not None:
                        w, q = wl_tag, "osm_gehweglinie"
                    else:
                        edge = np.fmin(R_, B_)
                        est1 = np.where(ok & np.isfinite(edge), 2 * (edge - S_), np.nan)
                        est2 = np.where(ok & np.isfinite(bord), 2 * (S_ - bord), np.nan)
                        v = _med(np.fmin(est1, est2))
                        if v is not None and v > 0.5:
                            w, q = float(np.clip(v, 1.0, 8.0)), "gehweglinie_abgeleitet"
                if w is None and o.get(f"seitenraum_{side}_m") is not None:
                    v = o[f"seitenraum_{side}_m"] - (gw or 0.0)
                    if v > 0.5:
                        w, q = float(min(v, 10.0)), "raum_abgeleitet"
                if w is None:
                    w, q = d["gehweg_m"], "regel"
            o[f"gehweg_{side}_m"] = _r(w, 1)
            o[f"gehweg_{side}_quelle"] = q
            tl = tree_side.get((k, side), [])
            if tl:
                pos = sorted(p for p, _ in tl)
                o[f"baeume_{side}"] = {"n": len(tl),
                                       "abstand_m": _r((pos[-1] - pos[0]) / (len(pos) - 1), 1) if len(pos) > 1 else None,
                                       "versatz_m": _r(float(np.median([v for _, v in tl])), 1)}
        o["tram_gleise"] = int(round(float(np.median(tram_n[m]))))
        mr = np.isin(ti_r, idx)
        if mr.any():
            from collections import Counter
            cnt = Counter()
            for j in sg_r[mr]:
                a = c.radsegs.attrs[c.radsegs.line[j]]
                cnt[(html.unescape(a.get("radanlage_text") or ""), a.get("lage"))] += 1
            (txt, lage), _ = cnt.most_common(1)[0]
            o["radanlage"] = txt or None
            o["radanlage_lage"] = lage
        res[wid] = o
    return res


# ----------------------------------------------------------------------------------------------
# Bordsteine und Straßengrün
# ----------------------------------------------------------------------------------------------
def _clip_lines(geom, box):
    g = geom.intersection(box)
    out = []
    for p in getattr(g, "geoms", [g]):
        if p.geom_type == "LineString" and not p.is_empty and p.length > 0.3:
            out.append(np.asarray(p.coords))
    return out


def _to_game(xy):
    return [[round(x - ORIGIN_E, 2), round(-(y - ORIGIN_N), 2)] for x, y in xy]


def kerbs_for_tile(e_km, n_km):
    """Bordsteinkanten in Spielkoordinaten.

    linien: [{pts: [[x,z],...], typ ('raised'|'lowered'|'flush'|...), hoehe_m, quelle}] mit
      quelle 'osm_kerb'   = OSM barrier=kerb-Linie (direkt kartiert)
      quelle 'osm_flaeche' = Rand der OSM-Fahrbahnflächen (area:highway), ohne Einmündungen/Kreuzungsöffnungen
    punkte: [{x, z, typ, hoehe_m}] – Bordsteinknoten (meist Absenkungen an Querungen).
    """
    c = _ctx(e_km, n_km)
    box = shapely.box(c.x0, c.y0, c.x1, c.y1)
    lines = []
    for xy, typ in c.kerb_lines:
        for part in _clip_lines(LineString(xy), box):
            lines.append({"pts": _to_game(part), "typ": typ, "hoehe_m": HOEHE_BORD.get(typ, 0.12), "quelle": "osm_kerb"})
    if c.carriage.u is not None:
        # Flächenrand ohne Stellen, an denen eine Straßenachse die Fläche verlässt (Einmündungen)
        bnd = c.carriage.u.boundary
        ways = shapely.union_all([LineString(w[2]) for w in c.ways if w[1].get("highway") != "pedestrian"]) if c.ways else None
        cut = ways.buffer(4.0) if ways is not None else None
        g = bnd.difference(cut) if cut is not None else bnd
        for part in _clip_lines(g, box):
            if len(part) >= 2:
                lines.append({"pts": _to_game(part), "typ": "raised", "hoehe_m": HOEHE_BORD["raised"], "quelle": "osm_flaeche"})
    pts = []
    for (x, y), p in c.kerb_pts:
        if c.x0 <= x < c.x1 and c.y0 <= y < c.y1:
            typ = p.get("kerb") or "raised"
            gx, gz = game_xz(x, y)
            pts.append({"x": round(gx, 2), "z": round(gz, 2), "typ": typ, "hoehe_m": HOEHE_BORD.get(typ, 0.12)})
    return {"linien": lines, "punkte": pts}


def green_strips_for_tile(e_km, n_km):
    """Straßenbegleitgrün und Verkehrsinseln (auf die Kachel geschnitten), Spielkoordinaten.

    quelle: 'dresden_f31' (Stadtstrukturtyp Verkehrsbegleitgrün, Blockebene – grob),
            'osm_strassengruen' (OSM grass/flowerbed/planter innerhalb des ALKIS-Straßenraums),
            'osm_insel' (area:highway=traffic_island; art = surface-Tag).
    Rückgabe [{pts: [[x,z],...], holes: [[[x,z],...]], quelle, art, flaeche_m2}].
    """
    c = _ctx(e_km, n_km)
    box = shapely.box(c.x0, c.y0, c.x1, c.y1)
    out = []

    def add(g, quelle, art):
        g = g.intersection(box)
        for p in getattr(g, "geoms", [g]):
            if p.geom_type != "Polygon" or p.is_empty or p.area < 2.0:
                continue
            out.append({"pts": _to_game(p.exterior.coords), "holes": [_to_game(r.coords) for r in p.interiors],
                        "quelle": quelle, "art": art, "flaeche_m2": round(p.area, 1)})

    for f in c.layers.get("gruenflaechen", []):
        if str(f["properties"].get("desk2", "")).startswith("F3"):
            add(shape(f["geometry"]), "dresden_f31", "Verkehrsbegleitgrün")
    for g, art in c.green_osm:
        if c.raum.u is not None and shapely.contains_xy(c.raum.u, *g.representative_point().coords[0]):
            add(g, "osm_strassengruen", art)
    for f in c.layers.get("osm_area_highway", []):
        if f["properties"].get("area:highway") == "traffic_island":
            add(shape(f["geometry"]), "osm_insel", f["properties"].get("surface") or "unbekannt")
    return out


# ----------------------------------------------------------------------------------------------
# Selbsttest
# ----------------------------------------------------------------------------------------------
def _report(e_km, n_km):
    import time
    from collections import Counter
    t0 = time.time()
    tr = trees_for_tile(e_km, n_km)
    t1 = time.time()
    rw = road_widths_for_tile(e_km, n_km)
    t2 = time.time()
    kb = kerbs_for_tile(e_km, n_km)
    gs = green_strips_for_tile(e_km, n_km)
    t3 = time.time()
    print(f"\n=== Kachel {e_km},{n_km}: {len(tr)} Bäume ({t1 - t0:.1f} s), {len(rw)} Wege ({t2 - t1:.1f} s), "
          f"{len(kb['linien'])} Bordlinien, {len(kb['punkte'])} Bordpunkte, {len(gs)} Grünflächen ({t3 - t2:.1f} s)")
    print("  Baumstandorte:", dict(Counter(t["standort"] for t in tr)))
    print("  Fahrbahnquelle:", dict(Counter(v["fahrbahn_quelle"] for v in rw.values())))
    print("  Gehwegquelle links:", dict(Counter(v.get("gehweg_links_quelle") for v in rw.values())))
    return tr, rw


if __name__ == "__main__":
    tiles = sys.argv[1:] or ["410,5656", "412,5656"]
    for a in tiles:
        e, n = (int(v) for v in a.split(","))
        _report(e, n)
