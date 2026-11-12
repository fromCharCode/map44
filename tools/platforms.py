"""Plattformen, die im DGM fehlen: Terrassen, Bastionen, Kasematten (z. B. Brühlsche Terrasse).

Das DGM1 behandelt solche aufgeschütteten/überbauten Flächen teils als Bauwerk und interpoliert den Boden
darunter (Brühlsche Terrasse: DGM 109–110 m, Oberfläche 118,5 m). Erkennung:
  - DOM liegt 3–12 m über dem DGM und ist eben (keine Bäume, keine Fahrzeuge),
  - kein Gebäude, kein Brückendeck, kein Wasser,
  - Fläche ≥ 1500 m² und grenzt an eine OSM-Stadt-/Stützmauer.
Ergebnis: Raster der Plattformhöhe (NaN = keine Plattform); das Gelände wird darauf angehoben (max).
"""
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

MIN_AREA = 1500
WALL_KINDS = ("city_wall", "retaining_wall")


def detect(dgm, dom, min_e, max_n, wall_lines, block, log=print):
    """dgm, dom: (H,W) relativ base, Zeile 0 = Nordrand bei max_n; wall_lines: [ndarray (n,2) UTM];
    block: bool (Gebäude, Decks, Wasser). Gibt Höhenraster (NaN außerhalb) zurück."""
    H, W = dgm.shape
    out = np.full((H, W), np.nan, dtype=np.float32)
    if dom is None or not wall_lines:
        return out
    dom = np.where(np.isfinite(dom), dom, dgm)
    d = dom - dgm
    med = ndimage.median_filter(dom, size=3)
    gy, gx = np.gradient(ndimage.uniform_filter(dom, 3))
    flat = (np.abs(dom - med) < 0.2) & (np.hypot(gx, gy) < 0.12)
    blk = ndimage.binary_dilation(block, iterations=1)
    cand = (d > 3.0) & (d < 12.0) & flat & ~blk
    if cand.sum() < MIN_AREA:
        return out
    # Mauern rastern
    im = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(im)
    for c in wall_lines:
        pts = [(e - min_e, max_n - n) for e, n in c]
        if len(pts) >= 2:
            dr.line(pts, fill=255, width=7)
    wall = np.asarray(im) > 0
    # Lücken (Bäume, Laternen, Menschen) schließen, Löcher füllen
    region = ndimage.binary_closing(cand, structure=np.ones((5, 5)), iterations=2)
    region = ndimage.binary_fill_holes(region)
    lab, n = ndimage.label(region)
    if n == 0:
        return out
    sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
    touch = ndimage.sum(wall, lab, index=np.arange(1, n + 1))
    keep = [i + 1 for i in range(n) if sizes[i] >= MIN_AREA and touch[i] >= 30]
    if not keep:
        return out
    sel = np.isin(lab, keep)
    # Höhe: geglättetes DOM auf ebenen Pixeln, Lücken per normierter Faltung aufgefüllt
    good = sel & cand
    h = np.where(good, ndimage.median_filter(dom, size=5), 0.0)
    w = good.astype(np.float32)
    filled = np.full((H, W), np.nan, dtype=np.float32)
    for r in (2, 4, 8, 16, 32):
        num = ndimage.uniform_filter(h * w, 2 * r + 1)
        den = ndimage.uniform_filter(w, 2 * r + 1)
        m = sel & np.isnan(filled) & (den > 1e-3)
        filled[m] = (num[m] / den[m]).astype(np.float32)
    ok = sel & np.isfinite(filled) & (filled > dgm + 0.5)
    out[ok] = filled[ok]
    for k in keep:
        mk = lab == k
        log(f"  Plattform (Terrasse/Bastion): {int(mk.sum())} m², Höhe {np.nanmedian(out[mk]):.1f} m "
            f"(DGM darunter {np.median(dgm[mk]):.1f} m)")
    return out
