"""Brückengeländer je Bauwerk: ergänzt city["bridge_rails"] um Bauart und Farbe (ohne Neubau der Kachel).

  python tools/bridge_styles.py [E,N ...]      (ohne Argument: alle Kacheln)

Zuordnung: Brüstungsstück -> nächster OSM-Brückenweg (≤ 25 m) bzw. man_made=bridge-Fläche -> Bauwerk aus der
Recherche data/research/bruecken.json (osm_way_ids / osm_area_id, Feld railing{kind,color}); ohne Recherche-Eintrag
Regel: Autobahn -> Beton, Bahn -> Stahl grau, historische Stein-Bogenbrücken (Name) -> Stein, sonst Stahl grau.
Rail-Zeile: [ax, az, bx, bz, y, art, farbe, höhe]  art: stone | concrete | steel | glass
"""
import json
import sys
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
RAW = ROOT / "data" / "raw" / "tiles"
RESEARCH = ROOT / "data" / "research" / "bruecken.json"
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)

STONE_NAMES = ("Augustusbrücke", "Albertbrücke", "Marienbrücke", "Friedrich-August-Brücke")
GREY = "#6E7378"


def _research():
    if not RESEARCH.exists():
        return {}, {}
    j = json.loads(RESEARCH.read_text(encoding="utf-8"))
    by_way, by_area = {}, {}
    for b in j.get("bridges", []):
        rail = b.get("railing") or {}
        kind = (rail.get("kind") or "").lower()
        head = kind[:40]
        if b.get("type") == "abgerissen":
            continue
        if any(k in head for k in ("massive sandstein", "sandsteinbrüstung", "steinbrüstung", "massive brüstung",
                                    "balustrade")):
            art = "stone"
        elif any(k in head for k in ("lärmschutz", "glas", "transparente", "schutzwand")):
            art = "glass"
        elif "betonschutzwand" in head or head.startswith("beton"):
            art = "concrete"
        else:
            art = "steel"
        col = rail.get("color") or (b.get("colors") or {}).get("railing") or GREY
        if not isinstance(col, str) or not col.startswith("#") or len(col) not in (4, 7):
            col = GREY
        h = rail.get("height_m")
        try:
            h = float(h) if h else (2.4 if art == "glass" else 1.1)
        except (TypeError, ValueError):
            h = 1.1
        spec = (art, col, round(min(max(h, 0.9), 4.5), 2))
        for w in b.get("osm_way_ids") or []:
            try:
                by_way[int(str(w).lstrip("w"))] = spec
            except ValueError:
                pass
        if b.get("osm_area_id"):
            try:
                by_area[int(str(b["osm_area_id"]).lstrip("w"))] = spec
            except ValueError:
                pass
    return by_way, by_area


def _local(lon, lat):
    e, n = TO_UTM.transform(lon, lat)
    return e - ORIGIN_E, -(n - ORIGIN_N)


def style_tile(name, by_way, by_area):
    cf = TILES / name / "city.json"
    of = RAW / name / "osm" / "bridges.json"
    if not cf.exists() or not of.exists():
        return 0
    city = json.loads(cf.read_text(encoding="utf-8"))
    rails = city.get("bridge_rails", [])
    if not rails:
        return 0
    ways, areas = [], []
    for el in json.loads(of.read_text(encoding="utf-8")).get("elements", []):
        g = el.get("geometry") or []
        if len(g) < 2:
            continue
        pts = [_local(p["lon"], p["lat"]) for p in g]
        t = el.get("tags", {})
        if t.get("man_made") == "bridge" and pts[0] == pts[-1] and len(pts) >= 4:
            pg = Polygon(pts)
            if pg.is_valid:
                areas.append((pg, el["id"], t))
        elif t.get("bridge") not in (None, "no"):
            ways.append((LineString(pts), el["id"], t))
    wt = STRtree([w[0] for w in ways]) if ways else None
    at = STRtree([a[0] for a in areas]) if areas else None
    n = 0
    for r in rails:
        mid = Point((r[0] + r[2]) * 0.5, (r[1] + r[3]) * 0.5)
        spec = None
        if at is not None:
            for i in at.query(mid.buffer(3.0)):
                pg, aid, t = areas[int(i)]
                if pg.distance(mid) < 3.0:
                    spec = by_area.get(aid) or spec
                    if spec is None and any(s in (t.get("name") or "") for s in STONE_NAMES):
                        spec = ("stone", GREY, 1.1)
        best = None
        if wt is not None:
            for i in wt.query(mid.buffer(25.0)):
                ln, wid, t = ways[int(i)]
                d = ln.distance(mid)
                if d < 25.0 and (best is None or d < best[0]):
                    best = (d, wid, t)
        if spec is None and best is not None:
            _d, wid, t = best
            spec = by_way.get(wid)
            if spec is None:
                nm = (t.get("bridge:name") or t.get("name") or "")
                if any(s in nm for s in STONE_NAMES):
                    spec = ("stone", GREY, 1.1)
                elif t.get("highway") in ("motorway", "motorway_link", "trunk"):
                    spec = ("concrete", GREY, 1.0)
                else:
                    spec = ("steel", GREY, 1.1)
        if spec is None:
            spec = ("steel", GREY, 1.1)
        del r[5:]
        r += [spec[0], spec[1], spec[2]]
        n += 1
    cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    return n


def main():
    by_way, by_area = _research()
    names = [a.replace(",", "_") for a in sys.argv[1:]] or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    tot = 0
    for nm in names:
        tot += style_tile(nm, by_way, by_area)
    print(f"Brückengeländer: {tot} Stücke in {len(names)} Kacheln gestaltet (Recherche: {len(by_way)} Wege)")


if __name__ == "__main__":
    main()
