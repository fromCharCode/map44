"""Sportstätten je Kachel: city["sports"] – Spielfelder mit Linien und Toren, Laufbahnen, Tribünen, Stadien
(Nachbearbeitung, ohne Neubau der Kachel).

  python tools/sports.py [E,N ...]      (ohne Argument: alle Kacheln)

Quelle: OSM leisure=pitch/track/stadium/bleachers (© OpenStreetMap-Mitwirkende, ODbL). Jede Fläche wird über ihr
kleinstes umschließendes Rechteck beschrieben (Mitte, Richtung der Längsachse, Länge, Breite).

  pitches   [art, x, z, winkel, länge, breite]   art: 0 Fußball, 1 Tennis, 2 Beachvolleyball, 3 Basketball/Mehrzweck,
            4 sonstiger Hartplatz, 5 Tischtennis, 6 Reitplatz (Sand), 7 Leichtathletik-Anlage (Sand/Tartan),
            8 Volleyball/Handball (Halle draußen), 9 Skatepark
  tracks    [x, z, winkel, länge, breite]        400-m-Rundbahn (Oval)
  bleachers [x, z, winkel, länge, tiefe, bx, bz] Stehstufen/Sitzreihen, (bx, bz) = Richtung zum Spielfeld
  stadiums  {"name", "x", "z", "ang", "len", "wid", "big", "cap", "lod2"}   Spielfeldmitte und -maße;
            big = Stadion mit umlaufenden überdachten Tribünen (im Geländemodell fehlen sie),
            lod2 = Tribünen stehen schon als Gebäude
"""
import json
import math
import sys
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point, Polygon, box

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
RAW = ROOT / "data" / "raw" / "tiles"
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
SPORT = {"soccer": 0, "american_football": 0, "tennis": 1, "beachvolleyball": 2, "basketball": 3, "multi": 3, "streetball": 3,
         "table_tennis": 5, "equestrian": 6, "athletics": 7, "long_jump": 7, "volleyball": 8, "handball": 8, "fistball": 0,
         "skateboard": 9, "running": 7, "field_hockey": 0, "rugby": 0}
BIG = {"Rudolf-Harbig-Stadion"}


def _local(lon, lat):
    e, n = TO_UTM.transform(lon, lat)
    return e - ORIGIN_E, -(n - ORIGIN_N)


def _poly(el):
    g = el.get("geometry") or []
    if el.get("type") == "way" and len(g) >= 4:
        p = Polygon([_local(q["lon"], q["lat"]) for q in g])
        return p if p.is_valid else p.buffer(0)
    if el.get("type") == "relation":
        outs = [Polygon([_local(q["lon"], q["lat"]) for q in m["geometry"]]) for m in el.get("members", [])
                if m.get("role") != "inner" and len(m.get("geometry") or []) >= 4]
        outs = [o if o.is_valid else o.buffer(0) for o in outs]
        if outs:
            return max(outs, key=lambda o: o.area)
    return None


def _rect(pg):
    """(cx, cz, winkel der Längsachse, länge, breite) des kleinsten umschließenden Rechtecks"""
    m = pg.minimum_rotated_rectangle
    if m.geom_type != "Polygon":
        return None
    cs = list(m.exterior.coords)
    e1 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
    e2 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
    l1, l2 = math.hypot(*e1), math.hypot(*e2)
    if l1 < 0.5 or l2 < 0.5:
        return None
    ex = e1 if l1 >= l2 else e2
    c = m.centroid
    return c.x, c.y, math.atan2(ex[1], ex[0]), max(l1, l2), min(l1, l2)


def tile_sports(name):
    cf = TILES / name / "city.json"
    lf = RAW / name / "osm" / "landuse.json"
    if not cf.exists() or not lf.exists():
        return None
    e_km, n_km = (int(v) for v in name.split("_"))
    x0, z0 = e_km * 1000.0 - ORIGIN_E, -((n_km + 2) * 1000.0 - ORIGIN_N)
    tbox = box(x0, z0, x0 + 2000.0, z0 + 2000.0)
    els = json.loads(lf.read_text(encoding="utf-8")).get("elements", [])
    city = json.loads(cf.read_text(encoding="utf-8"))
    bpolys = []
    for b in city.get("buildings", []):
        rs = b.get("rings") or []
        if rs and len(rs[0]) >= 3:
            pg = Polygon(rs[0])
            bpolys.append((pg if pg.is_valid else pg.buffer(0), b))
    out = {"pitches": [], "tracks": [], "bleachers": [], "stadiums": []}
    pitches = []
    for el in els:
        t = el.get("tags") or {}
        le = t.get("leisure")
        if le not in ("pitch", "track", "stadium", "bleachers"):
            continue
        pg = _poly(el)
        if pg is None or pg.is_empty or pg.area < 12.0:
            continue
        r = _rect(pg)
        if r is None:
            continue
        cx, cz, ang, ln, wd = r
        inside = tbox.contains(Point(cx, cz))
        if le == "pitch":
            sp = (t.get("sport") or "").split(";")[0]
            code = SPORT.get(sp, 4)
            if code == 5 and pg.area > 60.0:
                code = 4
            # von Gebäuden überdeckte Felder (Hallen) auslassen
            if any(bp.contains(Point(cx, cz)) and b_.get("eave", 0) > 3.5 for bp, b_ in bpolys):
                continue
            pitches.append((pg, code, cx, cz, ang, ln, wd))
            if inside:
                out["pitches"].append([code, round(cx, 2), round(cz, 2), round(ang, 4), round(ln, 2), round(wd, 2)])
        elif le == "track" and inside:
            if pg.area > 2500.0 and ln > 120.0 and wd > 60.0:
                out["tracks"].append([round(cx, 2), round(cz, 2), round(ang, 4), round(ln, 2), round(wd, 2)])
        elif le == "bleachers" and inside:
            out["bleachers"].append([round(cx, 2), round(cz, 2), round(ang, 4), round(ln, 2), round(wd, 2), pg])
        elif le == "stadium" and inside:
            out["stadiums"].append({"name": t.get("name") or "", "cap": int(str(t.get("capacity") or "0").split(";")[0] or 0)
                                    if str(t.get("capacity") or "0").split(";")[0].isdigit() else 0, "_pg": pg})
    # Stehstufen: Richtung zum nächsten Spielfeld
    for bl in out["bleachers"]:
        pg = bl.pop()
        best = None
        for q, code, cx, cz, ang, ln, wd in pitches:
            if code == 0 or code == 7:
                d = math.hypot(cx - bl[0], cz - bl[1])
                if best is None or d < best[0]:
                    best = (d, cx, cz)
        if best and best[0] < 200.0:
            dx, dz = best[1] - bl[0], best[2] - bl[1]
            dl = math.hypot(dx, dz) or 1.0
            bl += [round(dx / dl, 3), round(dz / dl, 3)]
        else:
            bl += [0.0, 0.0]
    # Stadien: größtes Fußballfeld darin
    stad = []
    for s in out["stadiums"]:
        pg = s.pop("_pg")
        best = None
        for q, code, cx, cz, ang, ln, wd in pitches:
            if code == 0 and pg.buffer(8.0).contains(Point(cx, cz)) and (best is None or ln * wd > best[3] * best[4]):
                best = (cx, cz, ang, ln, wd)
        if best is None:
            continue
        gs = [b_ for bp, b_ in bpolys if pg.buffer(5.0).contains(bp.centroid) and bp.area > 150.0 and b_.get("eave", 0) > 5.0]
        s.update({"x": round(best[0], 2), "z": round(best[1], 2), "ang": round(best[2], 4), "len": round(best[3], 2),
                  "wid": round(best[4], 2), "lod2": len(gs) > 0,
                  "big": (s["name"] in BIG or s["cap"] >= 12000) and len(gs) == 0})
        stad.append(s)
    out["stadiums"] = stad
    # Bodenbewuchs (cover.png, 2 m/px) auf Spielfeldern, Bahnen und im Stadion abschalten
    cp = TILES / name / "cover.png"
    rects = [(p_[1], p_[2], p_[3], p_[4] * 0.5 + 1.0, p_[5] * 0.5 + 1.0) for p_ in out["pitches"]]
    rects += [(t_[0], t_[1], t_[2], t_[3] * 0.5 + 1.0, t_[4] * 0.5 + 1.0) for t_ in out["tracks"]]
    rects += [(s_["x"], s_["z"], s_["ang"], s_["len"] * 0.5 + 40.0, s_["wid"] * 0.5 + 40.0) for s_ in stad if s_["big"]]
    if rects and cp.exists():
        from PIL import Image, ImageDraw
        import numpy as np
        cov = np.array(Image.open(cp).convert("RGB"))
        im = Image.new("L", (cov.shape[1], cov.shape[0]), 0)
        dr = ImageDraw.Draw(im)
        for cx, cz, ang, hl, hw in rects:
            ux, uz = (math.cos(ang), math.sin(ang)), (-math.sin(ang), math.cos(ang))
            pts = [((cx + ux[0] * a * hl + uz[0] * b * hw - x0) / 2.0, (cz + ux[1] * a * hl + uz[1] * b * hw - z0) / 2.0)
                   for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            dr.polygon(pts, fill=255)
        m = np.asarray(im) > 0
        if m.any():
            cov[m] = 0
            Image.fromarray(cov, "RGB").save(cp, optimize=False, compress_level=3)
    n = sum(len(v) for v in out.values())
    if n or "sports" in city:
        city["sports"] = out
        cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    return {k: len(v) for k, v in out.items()}


def main():
    names = [a.replace(",", "_") for a in sys.argv[1:]] or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    tot = {}
    for nm in names:
        for k, v in (tile_sports(nm) or {}).items():
            tot[k] = tot.get(k, 0) + v
    print("Sportstätten: " + ", ".join(f"{v} {k}" for k, v in tot.items()))


if __name__ == "__main__":
    main()
