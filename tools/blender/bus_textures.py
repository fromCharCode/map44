"""Prozedurale Texturen für die Stadtbusse (bus_solo.glb, bus_articulated.glb).

Aufruf (Projektordner):  .venv/bin/python tools/blender/bus_textures.py
Ausgabe: tools/blender/tex/bus_*.png (werden von bus_build.py eingebettet)

  bus_led_col / bus_led_emit  LED-Matrix (Kachel = 16 x 16 LEDs, 10 mm Raster -> 0.16 m)
  bus_seat                    Sitzbezug (Moquette), Kachel 0.25 m
  bus_floor                   heller Bodenbelag mit Einstreuung, Kachel 0.5 m
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from veg_texlib import fnoise, lerp, save, smoothstep, srgb, to_img  # noqa: E402


def led():
    S, n = 256, 16
    p = S // n
    yy, xx = np.mgrid[0:S, 0:S] + 0.5
    fx = (xx % p) / p - 0.5
    fy = (yy % p) / p - 0.5
    d = np.sqrt(fx * fx + fy * fy)
    dot = smoothstep(0.36, 0.26, d)                 # runde LED, ~60 % des Rasters
    core = smoothstep(0.22, 0.05, d)
    bg = srgb("#0b0b0c")
    unlit = srgb("#3a2a12")
    col = lerp(bg, unlit, dot * 0.8)
    col = lerp(col, srgb("#5a3c14"), core * 0.4)
    save(to_img(col), "bus_led_col.png")
    amber = srgb("#ffa21a")
    em = amber[None, None, :] * (dot * 0.55 + core * 0.45)[..., None]
    save(to_img(em), "bus_led_emit.png")


def seat():
    S = 512
    rng = np.random.default_rng(3)
    base = srgb("#1d2a44")
    col = np.ones((S, S, 3)) * base
    n = fnoise(S, S, 1.0, seed=4)
    col = col * (1 + 0.08 * n[..., None])
    # Muster: kleine versetzte Rauten + Striche in Gelb, Hellblau, Rot (generisch, kein Firmenmuster)
    yy, xx = np.mgrid[0:S, 0:S]
    cell = 64
    for k, c in enumerate(("#e8b51e", "#5aa7d6", "#c8433a", "#d9d9d9")):
        ox = (k * 23) % cell
        oy = (k * 41) % cell
        u = ((xx + ox) % cell) - cell / 2
        v = ((yy + oy + (xx // cell % 2) * cell / 2) % cell) - cell / 2
        m = (np.abs(u) + np.abs(v) < 6 + k)
        if k == 3:
            m = (np.abs(v) < 1.5) & (np.abs(u) < 14)
        col = np.where(m[..., None], srgb(c) * 0.9, col)
    weave = 0.5 + 0.5 * np.sin(xx * math.pi / 2) * np.sin(yy * math.pi / 2)
    col = col * (0.9 + 0.12 * weave[..., None])
    save(to_img(np.clip(col, 0, 1)), "bus_seat.png")


def floor():
    S = 512
    rng = np.random.default_rng(5)
    n = fnoise(S, S, 1.6, seed=6)
    col = lerp(srgb("#8f9294"), srgb("#a3a6a7"), smoothstep(-2, 2, n))
    r = rng.random((S, S))
    col = np.where((r < 0.03)[..., None], col * 0.55, col)
    col = np.where((r > 0.985)[..., None], lerp(col, srgb("#e0e2e2"), 0.7), col)
    col = np.where(((r > 0.5) & (r < 0.508))[..., None], lerp(col, srgb("#7a5a3a"), 0.5), col)
    col = np.stack([ndi.gaussian_filter(col[..., c], 0.5, mode="wrap") for c in range(3)], -1)
    dirt = smoothstep(0.8, 2.0, fnoise(S, S, 2.4, seed=7))
    col = lerp(col, srgb("#6d6e6c"), dirt * 0.3)
    save(to_img(col), "bus_floor.png")


if __name__ == "__main__":
    led()
    seat()
    floor()
    print("ok")
