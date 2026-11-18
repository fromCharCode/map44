"""Fensterraster aus Mapillary-Rundumbildern: Achsabstand der Fenster je Gebäude (Prototyp/Bibliothek).

Die Drehung der Rundumbilder ist zuverlässig, ihre Position nicht. Deshalb wird nur Maßstabsfreies gemessen: In einer
auf die Wand entzerrten Ansicht (virtuelle Kamera blickt senkrecht auf die Wand) bilden die Fenster ein Raster; das
Verhältnis waagrechte Periode / senkrechte Periode ist unabhängig vom Abstand. Mit der Geschosshöhe aus dem Stadtmodell
folgt daraus der Achsabstand in Metern. Bilder: Mapillary, CC BY-SA 4.0.
"""
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mly_facade as mf                                           # noqa: E402

SIZE = 512                                                        # entzerrte Ansicht SIZE × SIZE
TAN_H, TAN_UP, TAN_DN = 0.9, 1.3, 0.1                             # Bildfeld: ±42° seitlich, +52° … −6° in der Höhe


def pano_2048(im):
    f = mf.CACHE / f"{im['id']}_2048.jpg"
    if not f.exists():
        url = im.get("thumb_2048_url")
        try:
            data = mf.get(url, binary=True, auth=False) if url else None
        except Exception:                                         # noqa: BLE001 – Adresse abgelaufen
            data = None
        if data is None:
            d = mf.get(f"https://graph.mapillary.com/{im['id']}?fields=thumb_2048_url")
            data = mf.get(d["thumb_2048_url"], binary=True, auth=False)
        f.write_bytes(data)
    return np.asarray(Image.open(f).convert("RGB"))


def rectify(pano, R, nrm_xz):
    """Ansicht senkrecht auf die Wand; nrm_xz = Wandnormale (zum Betrachter) in Spielkoordinaten (x, z)"""
    ph, pw = pano.shape[:2]
    fwd = np.array([-nrm_xz[0], nrm_xz[1], 0.0])                  # Blick zur Wand in (Ost, Nord, oben); Nord = −z
    fwd /= np.linalg.norm(fwd)
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(fwd, up)
    xs = (np.arange(SIZE) + 0.5) / SIZE * 2 * TAN_H - TAN_H
    ys = TAN_UP - (np.arange(SIZE) + 0.5) / SIZE * (TAN_UP + TAN_DN)
    xx, yy = np.meshgrid(xs, ys)
    d = fwd[None, None, :] + xx[..., None] * right + yy[..., None] * up
    cam = d @ R.T
    lon = np.arctan2(cam[..., 0], cam[..., 2])
    lat = np.arctan2(-cam[..., 1], np.hypot(cam[..., 0], cam[..., 2]))
    sx = ((lon / (2 * math.pi) + 0.5) * pw).astype(int) % pw
    sy = np.clip(((0.5 - lat / math.pi) * ph).astype(int), 0, ph - 1)
    return pano[sy, sx]


def _period(sig, lo, hi):
    """stärkste Periode (in Proben) per Autokorrelation: (Periode, Stärke 0..1)"""
    s = sig - sig.mean()
    if s.std() < 1e-6:
        return 0.0, 0.0
    ac = np.correlate(s, s, "full")[len(s) - 1:]
    ac = ac / ac[0]
    best, bv = 0, 0.0
    for k in range(lo, min(hi, len(ac) - 2)):
        if ac[k] > ac[k - 1] and ac[k] >= ac[k + 1] and ac[k] > bv:
            best, bv = k, float(ac[k])
    if best == 0:
        return 0.0, 0.0
    # Scheitel per Parabel verfeinern
    a, b_, c = ac[best - 1], ac[best], ac[best + 1]
    off = 0.5 * (a - c) / (a - 2 * b_ + c) if abs(a - 2 * b_ + c) > 1e-9 else 0.0
    return best + off, bv


def window_grid(img, x_lo=0.2, x_hi=0.8):
    """(Periode waagrecht, Periode senkrecht, Stärke) in tan-Einheiten; ausgewertet wird das Mittelfeld"""
    g = img.astype(float).mean(2)
    mx = img.max(2).astype(float)
    mn = img.min(2).astype(float)
    sat = (mx - mn) / np.maximum(mx, 1.0)
    sky = (mx > 150) & ((sat < 0.18) | (img[..., 2] > img[..., 0] * 1.1))
    green = (img[..., 1] > img[..., 0] * 1.06) & (img[..., 1] > img[..., 2] * 1.06) & (sat > 0.2)
    c0, c1 = int(SIZE * x_lo), int(SIZE * x_hi)
    sub = g[:, c0:c1]
    bad = (sky | green)[:, c0:c1]
    rows_ok = np.where(bad.mean(1) < 0.45)[0]                    # Zeilen mit überwiegend Bauwerk
    if len(rows_ok) < 80:
        return None
    r0, r1 = rows_ok.min(), rows_ok.max()
    r1 = min(r1, int(SIZE * (TAN_UP - 0.18) / (TAN_UP + TAN_DN)))   # unter ~10° Höhe: Autos, Zäune, Läden
    if r1 - r0 < 80:
        return None
    area = sub[r0:r1]
    dark = (area < np.median(area) - 22.0).astype(float)         # Fensteröffnungen sind dunkler als die Wand
    if not 0.04 < dark.mean() < 0.6:
        return None
    px_h = 2 * TAN_H / SIZE
    px_v = (TAN_UP + TAN_DN) / SIZE
    ph_, sh = _period(dark.mean(0), 10, (c1 - c0) // 2)
    pv_, sv = _period(dark.mean(1), 14, (r1 - r0) // 2)
    if ph_ == 0 or pv_ == 0:
        return None
    return ph_ * px_h, pv_ * px_v, min(sh, sv), (r0, r1)


if __name__ == "__main__":
    import json
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import mly_colors as mc
    from shapely.geometry import Polygon
    from shapely.strtree import STRtree
    tile, x, z, radius, outdir = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
    city = json.loads((mf.TILES / tile / "city.json").read_text(encoding="utf-8"))
    feet, blds = [], []
    for b in city["buildings"]:
        pg = Polygon([(q[0], q[1]) for q in b["rings"][0]])
        if pg.is_valid and pg.area > 20 and not b.get("stacked"):
            feet.append(pg)
            blds.append(b)
    tree = STRtree(feet)
    images = [t for t in mc.load_images(x, z, radius + 30.0, True) if t[0].get("camera_type") == "spherical"]
    n = 0
    for b in blds:
        if math.hypot(b["pos"][0] - x, b["pos"][1] - z) > radius or float(b["eave"]) < 8.0:
            continue
        ring = b["rings"][0]
        best = None
        for i in range(len(ring) - 1):
            p0, p1 = np.array(ring[i][:2], float), np.array(ring[i + 1][:2], float)
            L = float(np.linalg.norm(p1 - p0))
            if L < 9.0:
                continue
            mid, dirv = (p0 + p1) / 2, (p1 - p0) / L
            for im, c in images:
                off = c - mid
                nrm = np.array([-dirv[1], dirv[0]])
                dist = float(off @ nrm)
                sgn = 1.0 if dist > 0 else -1.0
                dist = abs(dist)
                if dist < 5.0 or dist > 22.0 or abs(float(off @ dirv)) > L * 0.3:
                    continue
                from shapely.geometry import LineString
                sight = LineString([tuple(c), tuple(mid + (c - mid) / np.linalg.norm(c - mid) * 0.6)])
                if any(feet[j].intersects(sight) for j in tree.query(sight)):
                    continue
                sc = abs(dist - 12.0) / 12.0 + abs(float(off @ dirv)) / L
                if best is None or sc < best[0]:
                    best = (sc, im, c, nrm * sgn, L, dist)
        if best is None:
            continue
        _, im, c, nrm, L, dist = best
        img = rectify(pano_2048(im), mf.rodrigues(im["computed_rotation"]), nrm)
        half = min(0.8, (L * 0.5) / dist / TAN_H * 0.8)           # Breite der Wand im Bild (laut Pose), davon 80 %
        r = window_grid(img, 0.5 - half * 0.5, 0.5 + half * 0.5)
        levels = max(1.0, float(b["levels"]))
        fh = min(max(float(b["eave"]) / levels, 2.7), 4.6)
        n += 1
        Image.fromarray(img).save(f"{outdir}/w_{n:02d}.jpg", quality=88)
        if r:
            print(f"{n:02d} {b['id']} Stil {b['style']} L {L:.0f} m H {b['eave']} Geschosse {levels:.0f}: Achsabstand/Geschosshöhe "
                  f"{r[0] / r[1]:.2f} -> Achse {fh * r[0] / r[1]:.2f} m (Stärke {r[2]:.2f})")
        else:
            print(f"{n:02d} {b['id']}: kein Raster erkannt")
        if n >= 12:
            break
