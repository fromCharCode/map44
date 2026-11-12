"""Straßenbegleitgrün sichtbar machen (Nachbearbeitung nach vegetation.py, vor curbs.py).

  python tools/street_green.py [--dry] [E,N ...]      (ohne Argument: alle Kacheln)

Befund: Grünstreifen zwischen Fahrbahn und Gehweg, Rasen-Mittelinseln usw. waren im Bodenraster zwar als Gras
markiert (splat1.R), lagen aber zu ~90 % auch unter der Gehweg-/Platzfläche (splat0.G/B: Gehwegstreifen bis zur
Hauskante). Der Gelände-Shader legt den Gehweg über das Gras -> das Grün erschien gepflastert.

Hier werden die OSM-Grünflächen im Straßenraum (strassenraum.green_strips_for_tile: Quelle 'osm_strassengruen',
sowie begrünte Verkehrsinseln) aus Gehweg/Platz herausgenommen und als Rasen gesetzt. Fahrbahn, Gleisbett, Wasser
und echte Fußwege (OSM footway/path/cycleway/steps, neu eingezeichnet) bleiben unangetastet.
Schreibt splat0.png, splat1.png, cover.png und street_green.png (Maske für curbs.py: Bordstein auch Fahrbahn↔Grün).
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_cover import make as make_cover  # noqa: E402
from strassenraum import green_strips_for_tile  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
RAW = ROOT / "data" / "raw" / "tiles"
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
ISLAND_GREEN = {"grass", "flowerbed", "meadow", "planter"}
PATH_W = {"footway": 2.0, "path": 1.5, "cycleway": 2.0, "steps": 2.0, "bridleway": 1.5, "track": 3.0,
          "pedestrian": 4.0}


def _local(lon, lat):
    e, n = TO_UTM.transform(lon, lat)
    return e - ORIGIN_E, -(n - ORIGIN_N)


def green_tile(name, dry=False):
    d = TILES / name
    if not (d / "splat0.png").exists() or not (d / "splat1.png").exists():
        return 0.0
    e_km, n_km = (int(v) for v in name.split("_"))
    x0, z0 = e_km * 1000.0 - ORIGIN_E, -((n_km + 2) * 1000.0 - ORIGIN_N)
    s0 = np.array(Image.open(d / "splat0.png").convert("RGBA"))
    s1 = np.array(Image.open(d / "splat1.png").convert("RGBA"))
    H, W = s0.shape[:2]
    f = H / 2000.0

    gm_img = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(gm_img)
    n_poly = 0
    for g in green_strips_for_tile(e_km, n_km):
        q, art = g.get("quelle"), (g.get("art") or "")
        if not (q == "osm_strassengruen" or (q == "osm_insel" and art in ISLAND_GREEN)):
            continue
        if len(g["pts"]) < 3:
            continue
        dr.polygon([((p[0] - x0) * f, (p[1] - z0) * f) for p in g["pts"]], fill=255)
        for h in g.get("holes") or []:
            if len(h) >= 3:
                dr.polygon([((p[0] - x0) * f, (p[1] - z0) * f) for p in h], fill=0)
        n_poly += 1
    gm = np.asarray(gm_img) > 0
    if not gm.any():
        return 0.0

    # echte Fußwege durchs Grün wieder einzeichnen (nicht wegnehmen)
    fw_img = Image.new("L", (W, H), 0)
    dw = ImageDraw.Draw(fw_img)
    rf = RAW / name / "osm" / "roads.json"
    if rf.exists():
        for el in json.loads(rf.read_text(encoding="utf-8")).get("elements", []):
            t = el.get("tags") or {}
            cls = t.get("highway")
            geo = el.get("geometry") or []
            if cls not in PATH_W or len(geo) < 2 or t.get("area") == "yes":
                continue
            try:
                w = float(str(t.get("width", "")).split()[0]) if t.get("width") else PATH_W[cls]
            except ValueError:
                w = PATH_W[cls]
            pts = [_local(p["lon"], p["lat"]) for p in geo]
            dw.line([((x - x0) * f, (z - z0) * f) for x, z in pts], fill=255, width=max(1, int(round(w * f))))
    fw = np.asarray(fw_img) > 0

    road = s0[:, :, 0] > 128
    track = s0[:, :, 3] > 128
    water = s1[:, :, 3] > 128
    paved = np.maximum(s0[:, :, 1], s0[:, :, 2]) > 0
    sel = gm & ~road & ~track & ~water & ~fw
    changed = sel & paved
    area = float(changed.sum()) / (f * f)
    print(f"  {name}: {n_poly} Grünflächen, {area:.0f} m² Gehweg/Platz -> Rasen")
    if dry:
        return area
    s0[:, :, 1][sel] = 0
    s0[:, :, 2][sel] = 0
    s1[:, :, 0][sel] = 255
    Image.fromarray(s0, "RGBA").save(d / "splat0.png", optimize=False, compress_level=3)
    Image.fromarray(s1, "RGBA").save(d / "splat1.png", optimize=False, compress_level=3)
    Image.fromarray((sel * 255).astype(np.uint8), "L").save(d / "street_green.png", optimize=False, compress_level=6)
    make_cover(d)
    return area


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv
    names = [a.replace(",", "_") for a in args] or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    tot = 0.0
    for nm in names:
        tot += green_tile(nm, dry)
    print(f"Straßengrün: {tot:.0f} m² als Rasen in {len(names)} Kacheln" + (" (Probelauf)" if dry else ""))


if __name__ == "__main__":
    main()
