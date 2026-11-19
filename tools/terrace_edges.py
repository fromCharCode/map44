"""Terrassenkanten schärfen (Nachbearbeitung, ohne Neubau der Kachel).

  python tools/terrace_edges.py [E,N ...]      (ohne Argument: alle Kacheln mit Plattformen)

Die Plattform-Erkennung (platforms.py) hebt Terrassen wie die Brühlsche Terrasse nur dort an, wo das Oberflächenmodell
eben ist. Zwischen dieser Fläche und der Stützmauer blieb ein Streifen auf dem alten Gelände – im Spiel eine wellige
Böschung statt einer Mauer mit ebener Fläche dahinter. Hier wird die Plattform bis an die Mauerlinie (OSM city_wall /
retaining_wall) erweitert: Zellen, die von der Plattform aus erreichbar sind, ohne die Mauer zu kreuzen, höchstens
REACH m von der Plattform und höchstens NEAR m von einer Mauer entfernt, bekommen die Höhe der nächsten Plattformzelle.
Gebäude und Fahrbahnen bleiben unberührt. Wege auf dem Streifen werden mit angehoben. Schreibt terrain.f32,
terrain_col.f32 und city.json (Wegehöhen). Wiederholbar.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0
SIZE = 2000
REACH = 14
NEAR = 12.0
SKIRT = 11.0
DRIVE = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
         "service", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}


def fix_tile(name, dry=False):
    d = TILES / name
    pf, tf, cf = d / "platform.f32", d / "terrain.f32", d / "city.json"
    if not (pf.exists() and tf.exists() and cf.exists()):
        return None
    plat = np.fromfile(pf, dtype="<f4").reshape(SIZE, SIZE)
    P = np.isfinite(plat)
    if P.sum() < 200:
        return None
    e_km, n_km = (int(v) for v in name.split("_"))
    x0, z0 = e_km * 1000.0 - ORIGIN_E, -((n_km + 2) * 1000.0 - ORIGIN_N)
    city = json.loads(cf.read_text(encoding="utf-8"))
    terr = np.fromfile(tf, dtype="<f4").reshape(SIZE, SIZE).copy()

    def px(p):
        return (p[0] - x0, p[1] - z0)
    wim = Image.new("L", (SIZE, SIZE), 0)
    wd = ImageDraw.Draw(wim)
    for b in city.get("barriers", []):
        if b["kind"] in ("city_wall", "retaining_wall") and len(b["pts"]) >= 2:
            wd.line([px(q) for q in b["pts"]], fill=255, width=3)
    wall = np.asarray(wim) > 0
    if not wall.any():
        return None
    bim = Image.new("L", (SIZE, SIZE), 0)
    bd = ImageDraw.Draw(bim)
    for b in city.get("buildings", []):
        r = (b.get("rings") or [None])[0]
        if r and len(r) >= 3:
            bd.polygon([px(q) for q in r], fill=255)
    for r in city.get("roads", []):
        if r.get("cls") in DRIVE and len(r["pts"]) >= 2:
            bd.line([px(q) for q in r["pts"]], fill=255, width=int(float(r["width"]) + 2))
    block = (np.asarray(bim) > 0) | wall
    near_wall = ndimage.distance_transform_edt(~wall) <= NEAR
    allowed = near_wall & ~block
    grown = P.copy()
    st = ndimage.generate_binary_structure(2, 1)
    for _ in range(REACH):
        nxt = grown | (ndimage.binary_dilation(grown, st) & allowed)
        if (nxt == grown).all():
            break
        grown = nxt
    new = grown & ~P
    idx = ndimage.distance_transform_edt(~P, return_distances=False, return_indices=True)
    val = plat[idx[0], idx[1]]
    sim = Image.new("L", (SIZE, SIZE), 0)
    sd = ImageDraw.Draw(sim)
    for stp in city.get("steps", []):
        q = stp.get("pts") or []
        if len(q) >= 2:
            sd.line([px(v) for v in q], fill=255, width=int(float(stp.get("width", 3.0)) + 10))
    for r in city.get("roads", []):
        if r.get("cls") in ("steps", "footway", "path", "pedestrian", "cycleway") and len(r["pts"]) >= 2:
            # Wege, die die Kante hinaufführen (Rampen), nicht absenken
            ys = [float(q[2]) for q in r["pts"] if len(q) >= 3]
            if ys and max(ys) - min(ys) > 1.5:
                sd.line([px(q) for q in r["pts"]], fill=255, width=int(float(r["width"]) + 8))
    keep_slope = np.asarray(sim) > 0
    keep_slope = ndimage.binary_dilation(keep_slope, iterations=4)     # Treppen und Rampen samt Umfeld bleiben, wie sie sind
    up = new & (val > terr + 0.15) & ~keep_slope
    pr = P & ~keep_slope
    terr[pr] = np.maximum(terr[pr], plat[pr])       # geglättete Plattformränder wieder auf Plattformhöhe
    # nur Zellen ZWISCHEN Plattform und Mauer: der Strahl von der nächsten Plattformzelle durch die Zelle muss
    # innerhalb von NEAR m auf die Mauer treffen (sonst läuft die Füllung um Mauerenden herum nach außen)
    rr, cc = np.nonzero(up)
    for r_, c_ in zip(rr.tolist(), cc.tolist()):
        pr, pc = int(idx[0][r_, c_]), int(idx[1][r_, c_])
        dr_, dc_ = r_ - pr, c_ - pc
        ln = float(np.hypot(dr_, dc_)) or 1.0
        dr_, dc_ = dr_ / ln, dc_ / ln
        hit = False
        for k in range(1, int(NEAR) + 2):
            y, x = int(round(r_ + dr_ * k)), int(round(c_ + dc_ * k))
            if not (0 <= y < SIZE and 0 <= x < SIZE):
                break
            if wall[y, x]:
                hit = True
                break
        if not hit:
            up[r_, c_] = False
    before = terr.copy()
    terr[up] = val[up]
    # Außenseite: Das Gelände fiel dort über rund 9 m als Rampe zum Fuß ab (geglättete Kante). Zellen jenseits der
    # Mauer, höchstens SKIRT m von ihr und nahe der Plattform, sinken auf das Niveau am Mauerfuß (kleinster Wert im
    # Umkreis) – so entsteht an der Mauerlinie die senkrechte Stufe. Treppen und Gebäude bleiben unberührt.
    bld = np.asarray(bim) > 0
    near_p = ndimage.distance_transform_edt(~grown) <= SKIRT + 3
    outside = ~grown & ~wall & (ndimage.distance_transform_edt(~wall) <= SKIRT) & near_p & ~keep_slope
    foot = ndimage.minimum_filter(np.where(grown | wall, np.float32(1e6), terr), size=2 * int(SKIRT) + 5)
    down = outside & (foot < terr - 0.3) & (foot < 1e5)
    # nicht unter Gebäuden und nicht auf Fahrbahnen (die haben ihr eigenes Längsprofil)
    down &= ~bld
    rim = Image.new("L", (SIZE, SIZE), 0)
    rd = ImageDraw.Draw(rim)
    for r in city.get("roads", []):
        if r.get("cls") in DRIVE and len(r["pts"]) >= 2:
            rd.line([px(q) for q in r["pts"]], fill=255, width=int(float(r["width"]) + 2))
    down &= ~(np.asarray(rim) > 0)
    terr[down] = foot[down]
    ndown = int(down.sum())
    # Wege auf dem angehobenen Streifen mitnehmen
    nroad = 0
    for r in city.get("roads", []):
        for q in r["pts"]:
            c, rw = int(round(q[0] - x0)), int(round(q[1] - z0))
            if 0 <= c < SIZE and 0 <= rw < SIZE and up[rw, c] and len(q) >= 3 and q[2] < terr[rw, c] - 0.05:
                q[2] = round(float(terr[rw, c]) + 0.02, 2)
                nroad += 1
            elif 0 <= c < SIZE and 0 <= rw < SIZE and down[rw, c] and len(q) >= 3 and q[2] > terr[rw, c] + 0.05:
                q[2] = round(float(terr[rw, c]) + 0.02, 2)
                nroad += 1
    res = {"cells": int(up.sum()), "down": ndown, "roads": nroad, "max_raise": round(float((terr - before).max()), 1),
           "max_lower": round(float((before - terr).max()), 1)}
    if dry or not (up.any() or ndown):
        return res
    terr.astype("<f4").tofile(tf)
    mid = 0.5 * (terr[:, :-1] + terr[:, 1:])
    row = np.concatenate([terr[:, :1], mid, terr[:, -1:]], axis=1)
    midr = 0.5 * (row[:-1] + row[1:])
    np.concatenate([row[:1], midr, row[-1:]], axis=0).astype("<f4").tofile(d / "terrain_col.f32")
    if nroad:
        cf.write_text(json.dumps(city, separators=(",", ":")), encoding="utf-8")
    return res


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv
    names = [a.replace(",", "_") for a in args] or sorted(p.name for p in TILES.iterdir() if (p / "platform.f32").exists())
    for nm in names:
        r = fix_tile(nm, dry)
        if r and (r.get("cells") or r.get("down")):
            print(f"Terrassenkanten {nm}: {r['cells']} m² bis zur Mauer angehoben (höchstens {r['max_raise']} m), "
                  f"{r['down']} m² vor der Mauer abgesenkt (höchstens {r['max_lower']} m), {r['roads']} Wegpunkte mitgenommen")


if __name__ == "__main__":
    main()
