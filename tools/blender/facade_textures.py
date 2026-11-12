"""Prozedurale Texturen für Fassadenteile (godot/assets/models/facade).

Aufruf (Projektordner):  .venv/bin/python tools/blender/facade_textures.py
Ausgabe: tools/blender/tex/facade_*.png (werden von facade_build.py eingebettet)

  facade_sandstone_*   Elbsandstein, gealtert (Patina, Scharrierung), Kachel = 1 m
  facade_concrete_*    heller Sichtbeton, Kachel = 1 m
  facade_waschbeton_*  DDR-Waschbeton (Elbkies in Zementmatrix), Kachel = 0.5 m
  facade_wood_*        Eiche dunkel lasiert, Maserung vertikal, Kachel = 1 m
  facade_iron_rail_*   Schmiedeeisen-Atlas RGBA:
                       Bildzeilen 0..383 (Blender-v 0.25..1): Geländerfeld 1.2 m x 0.9 m,
                       2 Motive à 0.6 m, horizontal kachelbar;
                       Bildzeilen 384..511 (v 0..0.25): massives Eisen (Handlauf, Pfosten).
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from veg_texlib import fnoise, lerp, normal_from_height, save, smoothstep, srgb, to_img  # noqa: E402

S = 512


def sandstone(seed=5):
    rng = np.random.default_rng(seed)
    grain = fnoise(S, S, 0.8, seed=seed)                       # feines Korn
    mid = fnoise(S, S, 2.0, seed=seed + 1)
    bed = fnoise(S, S, 2.2, sx=6.0, sy=1.0, seed=seed + 2)     # Schichtung (waagerecht)
    pat = fnoise(S, S, 2.6, seed=seed + 3)                     # Patina-Flecken
    drip = fnoise(S, S, 2.2, sx=1.0, sy=8.0, seed=seed + 4)    # Laufspuren (senkrecht)
    fresh = srgb("#bdb197")
    aged = srgb("#968d7c")
    col = lerp(fresh, aged, 0.55 + 0.25 * np.tanh(mid))
    col = col * (1 + 0.035 * grain[..., None] + 0.04 * bed[..., None])
    iron = smoothstep(1.6, 2.4, fnoise(S, S, 2.4, seed=seed + 5))
    col = lerp(col, srgb("#a8794a"), iron * 0.45)
    dark = smoothstep(-0.2, 1.8, pat * 0.6 + drip * 0.6)
    col = lerp(col, srgb("#5e5850"), dark * 0.45)
    # Scharrierung: feine senkrechte Rillen (ca. 8 mm)
    x = np.arange(S)[None, :]
    scharr = np.sin(2 * math.pi * x / 4.0 + 0.8 * fnoise(S, S, 2.0, sx=1, sy=6, seed=seed + 6))
    hgt = 0.25 * grain + 0.35 * mid + 0.18 * scharr
    hgt = ndi.gaussian_filter(hgt, 0.6, mode="wrap")
    save(to_img(col), "facade_sandstone_col.png")
    save(normal_from_height(hgt, 1.6), "facade_sandstone_nrm.png")


def concrete(seed=7):
    rng = np.random.default_rng(seed)
    n1 = fnoise(S, S, 2.0, seed=seed)
    n2 = fnoise(S, S, 1.0, seed=seed + 1)
    col = lerp(srgb("#8f8c85"), srgb("#a9a69e"), smoothstep(-2, 2, n1))
    col = col * (1 + 0.03 * n2[..., None])
    pores = rng.random((S, S)) < 0.004
    pores = ndi.binary_dilation(pores, iterations=1) & (rng.random((S, S)) < 0.7)
    col = np.where(pores[..., None], col * 0.6, col)
    stain = smoothstep(0.8, 1.8, fnoise(S, S, 2.5, sx=1.0, sy=4.0, seed=seed + 2))
    col = lerp(col, srgb("#6f6c66"), stain * 0.35)
    hgt = 0.2 * n1 + 0.15 * n2 - 0.6 * pores
    save(to_img(col), "facade_concrete_col.png")
    save(normal_from_height(ndi.gaussian_filter(hgt, 0.6, mode="wrap"), 1.5), "facade_concrete_nrm.png")


def waschbeton(seed=9):
    """Elbkies 4..16 mm in grauer Zementmatrix, Kachel 0.5 m (1 px ~ 1 mm)."""
    rng = np.random.default_rng(seed)
    mat = lerp(srgb("#7d7a72"), srgb("#8f8b82"), smoothstep(-2, 2, fnoise(S, S, 1.6, seed=seed)))
    col = mat.copy()
    hgt = np.zeros((S, S)) - 0.2 + 0.05 * fnoise(S, S, 1.0, seed=seed + 1)
    palette = [("#cfc6b4", 3), ("#e2ddd2", 2), ("#9a8f80", 3), ("#7a6e62", 2), ("#b09070", 2),
               ("#5f5a55", 1), ("#c9b9a0", 2), ("#a7a39b", 2), ("#8e6b55", 1)]
    cols = [srgb(c) for c, w in palette for _ in range(w)]
    yy, xx = np.mgrid[-12:13, -12:13]
    n = 2600
    for i in range(n):
        cx, cy = rng.uniform(0, S), rng.uniform(0, S)
        r = rng.uniform(2.2, 7.5) if rng.random() < 0.85 else rng.uniform(7.5, 10)
        e = rng.uniform(0.65, 1.0)
        a = rng.uniform(0, math.pi)
        ca, sa = math.cos(a), math.sin(a)
        c = cols[rng.integers(len(cols))] * rng.uniform(0.85, 1.1)
        ix, iy = int(cx), int(cy)
        fx, fy = cx - ix, cy - iy
        X = xx - fx
        Y = yy - fy
        U = (X * ca + Y * sa) / r
        V = (-X * sa + Y * ca) / (r * e)
        d2 = U * U + V * V
        m = d2 < 1.0
        if not m.any():
            continue
        h = np.sqrt(np.clip(1 - d2, 0, 1)) * (r / 7.0) * 0.8 + 0.1
        rows = (iy + yy) % S
        colsx = (ix + xx) % S
        sel = m & (h > hgt[rows, colsx])
        if not sel.any():
            continue
        shade = (0.78 + 0.22 * np.sqrt(np.clip(1 - d2, 0, 1)))[..., None]
        col[rows[sel], colsx[sel]] = (c * shade)[sel]
        hgt[rows[sel], colsx[sel]] = h[sel]
    col = np.clip(col * (1 + 0.04 * fnoise(S, S, 2.0, seed=seed + 2)[..., None]), 0, 1)
    dirt = smoothstep(0.6, 1.8, fnoise(S, S, 2.4, sx=1.0, sy=3.0, seed=seed + 3))
    col = lerp(col, srgb("#5a564f"), dirt * 0.3)
    save(to_img(col), "facade_waschbeton_col.png")
    save(normal_from_height(ndi.gaussian_filter(hgt, 0.5, mode="wrap"), 2.2), "facade_waschbeton_nrm.png")


def wood(seed=11):
    rng = np.random.default_rng(seed)
    warp = fnoise(S, S, 2.6, sx=1.0, sy=5.0, seed=seed)
    x = np.arange(S)[None, :] + 14 * warp
    rings = 0.5 + 0.5 * np.sin(2 * math.pi * x / rng.uniform(9, 12) + 3 * fnoise(S, S, 2.4, sx=1, sy=10, seed=seed + 1))
    fib = fnoise(S, S, 1.2, sx=1.0, sy=16.0, seed=seed + 2)
    col = lerp(srgb("#4a2c17"), srgb("#6b4426"), rings ** 1.5)
    col = col * (1 + 0.07 * fib[..., None])
    pores = (fnoise(S, S, 0.6, sx=1.0, sy=12.0, seed=seed + 3) > 2.0)
    col = np.where(pores[..., None], col * 0.7, col)
    col = lerp(col, srgb("#2e1d10"), smoothstep(1.0, 2.2, fnoise(S, S, 2.2, seed=seed + 4)) * 0.4)
    hgt = 0.3 * rings + 0.2 * fib - 0.4 * pores
    save(to_img(col), "facade_wood_col.png")
    save(normal_from_height(ndi.gaussian_filter(hgt, 0.7, mode="wrap"), 1.2), "facade_wood_nrm.png")


def iron_rail():
    ss = 2
    W = S * ss
    img = Image.new("L", (W, W), 0)
    d = ImageDraw.Draw(img)

    def L(pts, w):
        for ox in (-S, 0, S):
            d.line([((x + ox) * ss, y * ss) for x, y in pts], fill=255, width=int(w * ss), joint="curve")

    def R(x0, y0, x1, y1):
        for ox in (-S, 0, S):
            d.rectangle([(x0 + ox) * ss, y0 * ss, (x1 + ox) * ss - 1, y1 * ss - 1], fill=255)

    def ring(cx, cy, r, w):
        for ox in (-S, 0, S):
            d.ellipse([(cx + ox - r) * ss, (cy - r) * ss, (cx + ox + r) * ss, (cy + r) * ss], outline=255,
                      width=int(w * ss))

    def disc(cx, cy, r):
        for ox in (-S, 0, S):
            d.ellipse([(cx + ox - r) * ss, (cy - r) * ss, (cx + ox + r) * ss, (cy + r) * ss], fill=255)

    def spiral(cx, cy, r0, r1, a0, turns, sgn, w=6):
        pts = []
        n = 90
        for i in range(n + 1):
            t = i / n
            a = a0 + sgn * 2 * math.pi * turns * t
            r = r0 + (r1 - r0) * t
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        L(pts, w)
        disc(cx + r0 * math.cos(a0), cy + r0 * math.sin(a0), w * 0.9)

    # Rahmenstäbe
    R(0, 0, S, 10)            # Obergurt
    R(0, 62, S, 69)           # Friesunterkante
    R(0, 328, S, 335)         # Untergurt Feld
    R(0, 376, S, 384)         # Fußstab
    def arc(cx, cy, r, a0, a1, w):
        for ox in (-S, 0, S):
            d.arc([(cx + ox - r) * ss, (cy - r) * ss, (cx + ox + r) * ss, (cy + r) * ss], a0, a1,
                  fill=255, width=int(w * ss))

    for m in range(2):
        ox = m * 256
        # oberer Fries: Ringe
        for k in range(4):
            ring(ox + 32 + 64 * k, 37, 24, 5)
        # Senkrechtstäbe
        for k in range(8):
            bx = ox + 16 + 32 * k
            R(bx - 3.5, 69, bx + 3.5, 328)
        # Bogenfries unter dem Fries zwischen den Stäben
        for k in range(8):
            arc(ox + 32 + 32 * k, 69, 16, 0, 180, 4.5)
        # Mittelornament: Ring mit Vierpass-Rosette
        cx, cy = ox + 128, 200
        ring(cx, cy, 54, 6.5)
        for dx, dy in ((22, 0), (-22, 0), (0, 22), (0, -22)):
            ring(cx + dx, cy + dy, 18, 4.5)
        disc(cx, cy, 7)
        # Voluten links/rechts am Ring (C-Schnecken)
        for sgn in (1, -1):
            spiral(cx + sgn * 74, cy - 30, 5, 20, math.pi / 2, 0.9, sgn, w=5)
            spiral(cx + sgn * 74, cy + 30, 5, 20, -math.pi / 2, 0.9, -sgn, w=5)
        # unterer Fries: kleine Ringe zwischen den Stäben
        for k in range(8):
            ring(ox + 32 * k + 32, 355, 11, 4)
    # Massiver Bereich
    R(0, 384, S, S)
    mask = np.asarray(img).astype(np.float32) / 255.0
    dist = ndi.distance_transform_edt(mask > 0.5)
    hgt_ss = np.sqrt(np.clip(dist / (4.0 * ss), 0, 1))
    a = mask.reshape(S, ss, S, ss).mean((1, 3))
    hgt = hgt_ss.reshape(S, ss, S, ss).mean((1, 3))
    hgt[384:, :] = 1.0
    n = fnoise(S, S, 1.4, seed=21)
    col = np.ones((S, S, 3)) * srgb("#1b1c1e")
    col = col * (1 + 0.15 * n[..., None])
    rust = smoothstep(1.5, 2.3, fnoise(S, S, 2.2, seed=22))
    col = lerp(col, srgb("#4a3022"), rust * 0.5)
    a[384:, :] = 1.0
    save(to_img(col, a), "facade_iron_rail_col.png")
    save(normal_from_height(hgt * 3.0, 2.5), "facade_iron_rail_nrm.png")


def main():
    sandstone()
    concrete()
    waschbeton()
    wood()
    iron_rail()
    print("ok")


if __name__ == "__main__":
    main()
