"""Saubere Brückenübergänge (Nachbearbeitung): Gelände unter Brücken-Rampenstücken ohne LoD2-Deck aufs Fahrbahnprofil.

  python tools/bridge_ramps.py [E,N ...]      (ohne Argument: alle Kacheln)

OSM markiert oft schon die Rampen bzw. Widerlager als bridge=yes; liegt dort kein LoD2-Deck, fährt man auf dem
Gelände – das road_surface.conform() für Brückenstücke nicht anpasst. Ergebnis waren Stufen von 10–40 cm am
Brückenende (tools/check_roads.py "[Brücke]"). Hier wird das Gelände in Fahrbahnbreite exakt auf das Profil gelegt
und über 2 m seitlich eingeblendet; Deckflächen (LoD2) bleiben unberührt. Schreibt terrain.f32 und terrain_col.f32.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
TILES = ROOT / "data" / "processed" / "tiles"
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0
DRIVE = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
         "service", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link", "pedestrian"}
FADE = 2.0


RAMP = 8.0


def _samples(pts, step):
    out = []
    for a_, b_ in zip(pts[:-1], pts[1:]):
        L = math.hypot(b_[0] - a_[0], b_[1] - a_[1])
        n = max(1, int(L / step))
        for k in range(n):
            t = k / n
            out.append((a_[0] + (b_[0] - a_[0]) * t, a_[1] + (b_[1] - a_[1]) * t, a_[2] + (b_[2] - a_[2]) * t))
    out.append(tuple(pts[-1][:3]))
    return out


def _deck_heights(city, x0, z0):
    """Raster (1 m) der Deck-Oberkante aus den LoD2-Dreiecken (NaN = kein Deck)."""
    h = np.full((2000, 2000), np.nan, dtype=np.float32)
    for m in city.get("bridge_meshes", []):
        t = m["top"]
        for k in range(0, len(t) - 8, 9):
            ax, ay, az = t[k] - x0, t[k + 1], t[k + 2] - z0
            bx, by, bz = t[k + 3] - x0, t[k + 4], t[k + 5] - z0
            cx, cy, cz = t[k + 6] - x0, t[k + 7], t[k + 8] - z0
            c0, c1 = int(max(min(ax, bx, cx), 0)), int(min(max(ax, bx, cx), 1999)) + 1
            r0, r1 = int(max(min(az, bz, cz), 0)), int(min(max(az, bz, cz), 1999)) + 1
            if c1 <= c0 or r1 <= r0:
                continue
            yy, xx = np.mgrid[r0:r1, c0:c1]
            px, pz = xx + 0.5, yy + 0.5
            den = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
            if abs(den) < 1e-9:
                continue
            l1 = ((bz - cz) * (px - cx) + (cx - bx) * (pz - cz)) / den
            l2 = ((cz - az) * (px - cx) + (ax - cx) * (pz - cz)) / den
            l3 = 1.0 - l1 - l2
            ins = (l1 >= -0.01) & (l2 >= -0.01) & (l3 >= -0.01)
            hv = l1 * ay + l2 * by + l3 * cy
            sub = h[r0:r1, c0:c1]
            upd = ins & (np.isnan(sub) | (hv > sub))
            sub[upd] = hv[upd]
    return h


def _deck_at(h, x, z):
    c, r = int(x), int(z)
    if 0 <= c < 2000 and 0 <= r < 2000:
        v = h[r, c]
        return None if np.isnan(v) else float(v)
    return None


def _splat(corr, cw, x, z, hw, val, deckm):
    R = int(math.ceil(hw + FADE)) + 1
    c, rr = int(x), int(z)
    r0, r1 = max(rr - R, 0), min(rr + R + 1, 2000)
    c0, c1 = max(c - R, 0), min(c + R + 1, 2000)
    if r1 <= r0 or c1 <= c0:
        return
    yy, xx = np.mgrid[r0:r1, c0:c1]
    dist = np.hypot(xx + 0.5 - x, yy + 0.5 - z)
    w = np.clip(1.0 - (dist - hw) / FADE, 0.0, 1.0)
    w[deckm[r0:r1, c0:c1]] = 0.0
    corr[r0:r1, c0:c1] += w * val
    cw[r0:r1, c0:c1] += w


def ramps_tile(name):
    d = TILES / name
    cf = d / "city.json"
    if not cf.exists():
        return 0
    city = json.loads(cf.read_text(encoding="utf-8"))
    e_km, n_km = (int(v) for v in name.split("_"))
    x0, z0 = e_km * 1000.0 - ORIGIN_E, -((n_km + 2) * 1000.0 - ORIGIN_N)
    ter = np.frombuffer((d / "terrain.f32").read_bytes(), dtype="<f4").reshape(2000, 2000).copy()
    # Deckflächen (LoD2) als Maske, 1 m Raster, etwas erweitert
    deck = Image.new("L", (2000, 2000), 0)
    dd = ImageDraw.Draw(deck)
    for m in city.get("bridge_meshes", []):
        t = m["top"]
        for k in range(0, len(t) - 8, 9):
            dd.polygon([(t[k] - x0, t[k + 2] - z0), (t[k + 3] - x0, t[k + 5] - z0), (t[k + 6] - x0, t[k + 8] - z0)], fill=255)
    for b in city.get("bridges", []):                     # OSM-Brückenplatten (Spiel baut dort eigene Decks)
        pts = b.get("pts", [])
        w = float(b.get("width", 3.0)) * 0.5 + 1.0
        for a_, b_ in zip(pts[:-1], pts[1:]):
            ax, az, bx, bz = a_[0] - x0, a_[1] - z0, b_[0] - x0, b_[1] - z0
            dd.line([(ax, az), (bx, bz)], fill=255, width=int(w * 2))
    deckm = np.asarray(deck) > 0
    acc = np.zeros_like(ter)
    wsum = np.zeros_like(ter)
    n_pts = 0
    for r in city.get("roads", []):
        if not r.get("bridge") or r.get("cls") not in DRIVE or len(r["pts"]) < 2:
            continue
        hw = float(r["width"]) * 0.5
        pts = r["pts"]
        for a_, b_ in zip(pts[:-1], pts[1:]):
            L = math.hypot(b_[0] - a_[0], b_[1] - a_[1])
            if L < 0.05:
                continue
            nseg = max(1, int(L / 0.5))
            for k in range(nseg + 1):
                t = k / nseg
                x = a_[0] + (b_[0] - a_[0]) * t
                z = a_[1] + (b_[1] - a_[1]) * t
                y = a_[2] + (b_[2] - a_[2]) * t
                c, rr = int(x - x0), int(z - z0)
                if not (0 <= c < 2000 and 0 <= rr < 2000) or deckm[rr, c]:
                    continue
                if abs(y - float(ter[rr, c])) > 1.5:
                    continue                                 # echte Spannweite über einer Lücke: kein Damm
                n_pts += 1
                R = int(math.ceil(hw + FADE)) + 1
                r0, r1 = max(rr - R, 0), min(rr + R + 1, 2000)
                c0, c1 = max(c - R, 0), min(c + R + 1, 2000)
                yy, xx = np.mgrid[r0:r1, c0:c1]
                dist = np.hypot(xx + 0.5 - (x - x0), yy + 0.5 - (z - z0))
                w = np.clip(1.0 - (dist - hw) / FADE, 0.0, 1.0)
                w[deckm[r0:r1, c0:c1]] = 0.0
                acc[r0:r1, c0:c1] += w * y
                wsum[r0:r1, c0:c1] += w
    m = wsum > 0
    target = np.where(m, acc / np.maximum(wsum, 1e-6), ter)
    blend = np.clip(wsum, 0.0, 1.0)
    out = (ter * (1.0 - blend) + target * blend).astype("<f4")
    # --- Anrampung am Deckrand: Gelände am Übergang exakt auf Deckhöhe, über RAMP m zurück zum Verlauf ---------
    dh = _deck_heights(city, x0, z0)
    corr = np.zeros_like(out)
    cw = np.zeros_like(out)
    n_edges = 0
    for r in city.get("roads", []):
        if r.get("cls") not in DRIVE or len(r["pts"]) < 2:
            continue
        hw = float(r["width"]) * 0.5
        samp = _samples(r["pts"], 0.5)
        ondeck = [_deck_at(dh, x - x0, z - z0) for x, z, _y in samp]
        for i in range(1, len(samp)):
            a_on, b_on = ondeck[i - 1] is not None, ondeck[i] is not None
            if a_on == b_on:
                continue
            # Übergang: Seite auf dem Deck (Höhe) und Richtung weg vom Deck
            j_deck, step = (i - 1, 1) if a_on else (i, -1)
            hd = ondeck[j_deck]
            j0 = j_deck + step
            x, z, _y = samp[j0]
            c, rr = int(x - x0), int(z - z0)
            if not (0 <= c < 2000 and 0 <= rr < 2000):
                continue
            delta = hd - float(out[rr, c])
            if not (0.03 < abs(delta) < 1.2):
                continue
            n_edges += 1
            j = j0
            dist = 0.0
            while 0 <= j < len(samp) and dist <= RAMP:
                if ondeck[j] is not None:
                    break
                x, z, _y = samp[j]
                f = 0.5 * (1.0 + math.cos(math.pi * dist / RAMP))          # 1 am Deckrand -> 0 nach RAMP m
                _splat(corr, cw, x - x0, z - z0, hw, delta * f, deckm)
                j += step
                dist += 0.5
    if n_edges == 0 and n_pts == 0:
        return 0
    mm = cw > 0
    out = np.where(mm, out + corr / np.maximum(cw, 1e-6) * np.clip(cw, 0.0, 1.0), out).astype("<f4")
    (d / "terrain.f32").write_bytes(out.tobytes())
    mid = 0.5 * (out[:, :-1] + out[:, 1:])
    row = np.concatenate([out[:, :1], mid, out[:, -1:]], axis=1)
    midr = 0.5 * (row[:-1] + row[1:])
    pad = np.concatenate([row[:1], midr, row[-1:]], axis=0).astype("<f4")
    (d / "terrain_col.f32").write_bytes(pad.tobytes())
    return n_pts + n_edges


def main():
    names = [a.replace(",", "_") for a in sys.argv[1:]] or sorted(p.name for p in TILES.iterdir() if p.is_dir())
    tot = 0
    for nm in names:
        tot += ramps_tile(nm)
    print(f"Brückenrampen: {tot} Profilpunkte angeglichen in {len(names)} Kacheln")


if __name__ == "__main__":
    main()
