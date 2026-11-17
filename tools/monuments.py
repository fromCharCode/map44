"""Denkmäler, Standbilder und Brunnen (Nachbearbeitung nach build_city).

  python tools/monuments.py [E,N ...]            (ohne Argument: alle Kacheln)

Quellen: OSM (tourism=artwork, historic=memorial/monument, amenity=fountain; data/raw/tiles/*/osm/pois.json) und die
Dresdner Denkmallisten (tools/fetch_denkmale.py), soweit dort ein Standbild/Brunnen/Gedenkstein ohne OSM-Objekt steht.
Schreibt city.life.monuments: [modell, x, z, gier, maßstab, name]. Die Modelle (mon_*.glb) baut
tools/blender/monuments_build.py; das Spiel stellt sie über street_life.gd auf. Objekte in Gebäudegrundrissen
(Fassaden- und Dachfiguren) werden ausgelassen – die gehören zum Gebäude. Wiederholbar.
"""
import json
import math
import re
import sys
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
RAW = ROOT / "data" / "raw" / "tiles"
DENKMALE = ROOT / "data" / "raw" / "denkmale" / "denkmale.json"
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0

# benannte Sondermodelle (Name enthält … -> Modell); fehlt das Modell im Spiel, greift dort der Ersatz "mon_statue"
SPECIAL = (("goldener reiter", "mon_reiter_gold"), ("könig-johann", "mon_reiter"), ("könig johann", "mon_reiter"),
           ("reiterstandbild", "mon_reiter"), ("reiterdenkmal", "mon_reiter"))
# Art laut Denkmalliste (Klammer in der Datierung) -> Modell
DK_KIND = (("reiterstandbild", "mon_reiter"), ("sitzstatue", "mon_statue"), ("statue", "mon_statue"),
           ("standbild", "mon_statue"), ("figurengruppe", "mon_statue"), ("figur", "mon_statue"),
           ("büste", "mon_bust"), ("obelisk", "mon_obelisk"), ("kriegerdenkmal", "mon_war"),
           ("brunnenplastik", "mon_fountain"), ("brunnen", "mon_fountain"), ("gedenkstein", "mon_stone"),
           ("stele", "mon_stele"), ("postmeilensäule", "mon_obelisk"), ("denkmal", "mon_stele"))


def num(v, default):
    m = re.search(r"[0-9]+(?:[.,][0-9]+)?", str(v or ""))
    return float(m.group(0).replace(",", ".")) if m else default


def local(lon, lat):
    e, n = TO_UTM.transform(lon, lat)
    return e - ORIGIN_E, -(n - ORIGIN_N)


def osm_model(t):
    """(Modell, Maßstab) oder None"""
    name = (t.get("name") or "").lower()
    for key, model in SPECIAL:
        if key in name:
            return model, 1.0
    if t.get("amenity") == "fountain":
        if t.get("fountain") in ("drinking", "bubbler", "bottle_refill", "stone_block", "mist") or t.get("drinking_water") == "yes":
            return "mon_fountain_small", 1.0
        d = num(t.get("diameter") or t.get("width"), 0.0)
        return "mon_fountain", min(max(d / 6.0, 0.6), 2.5) if d > 0 else 1.0
    kind = t.get("artwork_type") or t.get("memorial") or ""
    hist = t.get("historic") or ""
    h = num(t.get("height"), 0.0)
    if h > 12.0:
        return None                                   # Figuren auf Dächern/Türmen (Höhe über Grund)
    if kind in ("statue", "sculpture") and hist != "memorial" and t.get("artwork_type") == "sculpture":
        return "mon_sculpture", min(max(h / 2.4, 0.5), 2.5) if h > 0 else 1.0
    if kind in ("statue", "sculpture"):
        return "mon_statue", min(max(h / 4.2, 0.5), 2.2) if h > 0 else 1.0
    if kind == "bust":
        return "mon_bust", 1.0
    if kind == "obelisk":
        return "mon_obelisk", min(max(h / 6.0, 0.5), 2.5) if h > 0 else 1.0
    if kind == "stele":
        return "mon_stele", 1.0
    if kind == "stone" or hist == "stone":
        return "mon_stone", 1.0
    if kind == "war_memorial":
        return "mon_war", 1.0
    if hist == "monument":
        return "mon_statue", 1.4
    if hist == "memorial" and kind == "":
        return "mon_stone", 1.0
    if t.get("tourism") == "artwork" and kind in ("", "installation", "stone"):
        return "mon_sculpture", 1.0
    return None                                       # Stolpersteine, Tafeln, Wandbilder, Grenzsteine …


def tile_monuments(name, denkmale):
    cf = TILES / name / "city.json"
    if not cf.exists():
        return 0
    city = json.loads(cf.read_text(encoding="utf-8"))
    e_km, n_km = (int(v) for v in name.split("_"))
    x0, z0 = e_km * 1000.0 - ORIGIN_E, -((n_km + 2) * 1000.0 - ORIGIN_N)
    feet = []
    for b in city.get("buildings", []):
        try:
            pg = Polygon([(q[0], q[1]) for q in b["rings"][0]])
            if pg.is_valid and pg.area > 4.0:
                feet.append(pg)
        except (KeyError, IndexError, ValueError, TypeError):
            pass
    btree = STRtree(feet) if feet else None
    lines = []
    for r in city.get("roads", []):
        if len(r.get("pts", [])) >= 2 and r.get("cls") not in ("steps",):
            lines.append(LineString([p[:2] for p in r["pts"]]))
    rtree = STRtree(lines) if lines else None

    def in_building(pt):
        return btree is not None and any(feet[j].contains(pt) for j in btree.query(pt))

    def on_road(pt):
        # Fahrbahnmitte näher als 2 m: Lagefehler der Quelle – nicht mitten auf die Straße stellen
        return rtree is not None and any(lines[j].distance(pt) < 2.0 for j in rtree.query(pt.buffer(2.0)))

    def facing(pt):
        """Blick zur nächsten Straße/zum nächsten Weg (Gier: Vorderseite = +z des Modells)"""
        if rtree is None:
            return 0.0
        best = None
        for j in rtree.query(pt.buffer(40.0)):
            d = lines[j].distance(pt)
            if best is None or d < best[0]:
                best = (d, j)
        if best is None:
            return 0.0
        q = lines[best[1]].interpolate(lines[best[1]].project(pt))
        return math.atan2(q.x - pt.x, q.y - pt.y)

    out, placed = [], []
    f = RAW / name / "osm" / "pois.json"
    if f.exists():
        for el in json.loads(f.read_text(encoding="utf-8")).get("elements", []):
            t = el.get("tags") or {}
            if not (t.get("tourism") == "artwork" or t.get("historic") in ("memorial", "monument", "stone")
                    or t.get("amenity") == "fountain"):
                continue
            if el.get("type") == "node":
                x, z = local(el["lon"], el["lat"])
            elif el.get("geometry"):
                g = el["geometry"]
                x, z = local(sum(p["lon"] for p in g) / len(g), sum(p["lat"] for p in g) / len(g))
            else:
                continue
            if not (x0 <= x < x0 + 2000.0 and z0 <= z < z0 + 2000.0):
                continue
            mm = osm_model(t)
            pt = Point(x, z)
            if mm is None or in_building(pt) or on_road(pt) or any(pt.distance(q) < 2.5 for q in placed):
                continue
            placed.append(pt)
            out.append([mm[0], round(x, 2), round(z, 2), round(facing(pt), 3), round(mm[1], 2), (t.get("name") or "")[:48]])
    for o in denkmale:
        x, z = o["x"], o["z"]
        if not (x0 <= x < x0 + 2000.0 and z0 <= z < z0 + 2000.0):
            continue
        kinds = " ".join(re.findall(r"\(([^)]*)\)", o["datierung"])).lower()
        # nur reine Kleindenkmale: sobald ein Gebäude genannt ist, gehört der Eintrag zum Haus
        if re.search(r"haus|villa|gebäude|kirche|schule|hof|fabrik|kapelle|bahnhof|anlage|friedhof|garten", kinds):
            continue
        model = next((m for k, m in DK_KIND if k in kinds), None)
        nm = o["name"].lower()
        for key, sm in SPECIAL:
            if key in nm:
                model = sm
        pt = Point(x, z)
        if model is None or in_building(pt) or on_road(pt) or any(pt.distance(q) < 15.0 for q in placed):
            continue
        placed.append(pt)
        out.append([model, round(x, 2), round(z, 2), round(facing(pt), 3), 1.0, o["name"][:48]])
    life = city.setdefault("life", {})
    if out or life.get("monuments"):
        life["monuments"] = out
        cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    if out:
        kinds = {}
        for o in out:
            kinds[o[0]] = kinds.get(o[0], 0) + 1
        print(f"  {name}: {len(out)} Denkmäler/Brunnen ({', '.join(f'{v} {k[4:]}' for k, v in sorted(kinds.items()))})")
    return len(out)


def main():
    args = [a.replace(",", "_") for a in sys.argv[1:] if not a.startswith("--")]
    names = args or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    denkmale = json.loads(DENKMALE.read_text(encoding="utf-8")) if DENKMALE.exists() else []
    n = sum(tile_monuments(nm, denkmale) for nm in names)
    if not args:
        print(f"{n} Denkmäler/Brunnen")


if __name__ == "__main__":
    main()
