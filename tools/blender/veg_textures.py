"""Prozedurale Texturen für das Unterholz (godot/assets/models/vegetation).

Aufruf (Projektordner):  .venv/bin/python tools/blender/veg_textures.py
Ausgabe: tools/blender/tex/veg_*.png  (werden von veg_build.py in die .glb eingebettet)

Alle Blatt-/Graskarten sind RGBA (Alpha für Alpha-Scissor, Farbe in transparente
Bereiche aufgefüllt), Rinde/Stein haben zusätzlich Normalmaps (OpenGL/glTF-Konvention).
"""
from __future__ import annotations

import math
import sys

import numpy as np

sys.path.insert(0, __import__("os").path.dirname(__file__))
from veg_texlib import (Canvas, draw_leaf, fnoise, jitter_color, lerp, mult_noise,  # noqa: E402
                        normal_from_height, save, smoothstep, srgb, to_img)

S = 512


# =====================================================================
# Blatt-Cluster (Zweig mit Blättern), Zweigbasis unten Mitte
# =====================================================================
def bezier(p0, p1, p2, n=12):
    p0, p1, p2 = (np.asarray(p, float) for p in (p0, p1, p2))
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t * t * p2


def leaf_cluster(name, seed, base_col, leaf_len, leaf_w, shape, n_twigs, spread,
                 twig_len, spacing, serr=0.08, nserr=14, yellow=0.05, twig_col="#5b4a3a",
                 fill_target=0.72, flat_spray=False):
    rng = np.random.default_rng(seed)
    cv = Canvas(S, S, ss=2)
    base = np.array([S * 0.5, S * 0.985])
    twigs = []
    for i in range(n_twigs):
        f = (i + 0.5) / n_twigs
        ang = (f - 0.5) * 2 * spread + rng.uniform(-0.12, 0.12)   # 0 = nach oben
        L = twig_len * rng.uniform(0.85, 1.05) * (1.0 - 0.42 * abs(f - 0.5) * 2)
        if flat_spray:
            ang = (f - 0.5) * 2 * spread
        d = np.array([math.sin(ang), -math.cos(ang)])
        bend = rng.uniform(-0.25, 0.25)
        dn = np.array([-d[1], d[0]])
        for _ in range(20):
            p2 = base + d * L
            p1 = base + d * L * 0.5 + dn * L * bend
            cur = bezier(base, p1, p2, 14)
            if (cur[:, 0].min() > 12 and cur[:, 0].max() < S - 12 and cur[:, 1].min() > 12):
                break
            L *= 0.9
        twigs.append(cur)
    # Nebenzweige
    for tw in list(twigs):
        for k in range(rng.integers(1, 4)):
            j = rng.integers(4, 9)
            p0 = tw[j]
            t = tw[j + 1] - tw[j - 1]
            t /= np.linalg.norm(t)
            sgn = rng.choice([-1, 1])
            a = math.atan2(t[0], -t[1]) + sgn * rng.uniform(0.45, 0.8)
            d = np.array([math.sin(a), -math.cos(a)])
            L = twig_len * rng.uniform(0.25, 0.45)
            for _ in range(20):
                q = p0 + d * L
                if 12 < q[0] < S - 12 and 12 < q[1] < S - 12:
                    break
                L *= 0.85
            twigs.append(bezier(p0, p0 + d * L * 0.5, p0 + d * L, 8))
    tcol = srgb(twig_col)
    for tw in twigs:
        cv.thick_curve(tw, 5.0, 1.8, tcol)
    # Blätter entlang der Zweige
    leaves = []
    for tw in twigs:
        seg = np.linalg.norm(np.diff(tw, axis=0), axis=1)
        cum = np.concatenate([[0], np.cumsum(seg)])
        total = cum[-1]
        s = total * rng.uniform(0.06, 0.16)
        side = rng.choice([-1, 1])
        while s < total:
            p = np.array([np.interp(s, cum, tw[:, 0]), np.interp(s, cum, tw[:, 1])])
            i = min(len(tw) - 2, np.searchsorted(cum, s) - 1)
            t = tw[i + 1] - tw[i]
            t /= np.linalg.norm(t) + 1e-9
            ta = math.atan2(t[0], -t[1])
            dev = rng.uniform(0.6, 1.05) if not flat_spray else rng.uniform(1.0, 1.35)
            leaves.append((p, ta + side * dev, rng.uniform(0.8, 1.15)))
            side = -side
            s += spacing * rng.uniform(0.8, 1.2)
        p = tw[-1]
        t = tw[-1] - tw[-2]
        leaves.append((p, math.atan2(t[0], -t[1]) + rng.uniform(-0.15, 0.15), 1.05))
    rng.shuffle(leaves)
    # Tiefe: zuerst die "hinteren" (dunkler), dann die vorderen
    leaves = [(p, a, sc, rng.uniform(0, 1)) for (p, a, sc) in leaves]
    leaves.sort(key=lambda x: x[3])
    for p, a, sc, dep in leaves:
        c = jitter_color(srgb(base_col), rng, 0.025, 0.12, 0.10)
        if rng.random() < yellow:
            c = lerp(c, srgb("#9a9a3a"), rng.uniform(0.3, 0.6))
        c = c * (0.72 + 0.32 * dep)
        L = leaf_len * sc
        # Blatt muss vollständig in der Karte liegen (keine geraden Schnittkanten)
        tip = p + np.array([math.sin(a), -math.cos(a)]) * L * 1.12
        mid = p + np.array([math.sin(a), -math.cos(a)]) * L * 0.55
        rad = leaf_w * sc * 0.55
        m = 6
        if not all(m + rad * 0.3 < q[k] < S - m - rad * 0.3 for q in (tip,) for k in (0, 1)):
            continue
        if not all(m + rad < mid[k] < S - m - rad for k in (0, 1)):
            continue
        draw_leaf(cv, p[0], p[1], a, L, leaf_w * sc, np.clip(c, 0, 1), rng, shape=shape,
                  serr=serr, nserr=nserr, petiole=L * 0.12, stem_col=tcol * 1.1)
    rgb, a = cv.result()
    rgb = mult_noise(rgb, a, 0.06, seed + 7)
    print(name, "Deckung", round(float((a > 0.5).mean()), 3))
    return save(to_img(rgb, a), name)


# =====================================================================
# Farnwedel (Adlerfarn, Pteridium aquilinum): Stiel unten, Spreite dreieckig
# =====================================================================
def fern_frond(name, seed):
    rng = np.random.default_rng(seed)
    cv = Canvas(S, S, ss=2)
    cx = S * 0.5
    y_base, y_blade, y_tip = S * 0.995, S * 0.66, S * 0.02
    stipe = srgb("#6d6a3c")
    rach = srgb("#7a8a3a")
    green = srgb("#5d8030")
    cv.thick_curve([(cx, y_base), (cx, y_blade)], 7, 5, stipe * 0.8)
    cv.thick_curve([(cx, y_blade), (cx + 2, (y_blade + y_tip) / 2), (cx, y_tip)], 5, 1.5, rach)
    n_p = 13
    pinnae = []
    for i in range(n_p):
        t = i / (n_p - 1)
        y = y_blade + (y_tip - y_blade) * (t ** 0.92) - 6
        Lp = (S * 0.47) * (1.0 - t) ** 0.85 + 18
        for sgn in (-1, 1):
            yo = y + (sgn * 6 if i % 2 else -sgn * 6)
            ang = sgn * (math.radians(62) + t * math.radians(10))
            pinnae.append((cx, yo, ang, Lp, t))
    for (x0, y0, ang, Lp, t) in pinnae:
        d = np.array([math.sin(ang), -math.cos(ang)])
        dn = np.array([-d[1], d[0]])
        droop = 0.18 * Lp
        p0 = np.array([x0, y0])
        p2 = p0 + d * Lp + np.array([0, droop * 0.4])
        p1 = p0 + d * Lp * 0.55 - np.array([0, Lp * 0.06])
        axis = bezier(p0, p1, p2, 16)
        cv.thick_curve(axis, 2.6, 0.8, rach * 0.95)
        # Fiederchen (Pinnulae): längliche, stumpfe Lappen beidseits
        seg = np.linalg.norm(np.diff(axis, axis=0), axis=1)
        cum = np.concatenate([[0], np.cumsum(seg)])
        tot = cum[-1]
        s = 4.0
        while s < tot - 2:
            u = s / tot
            p = np.array([np.interp(s, cum, axis[:, 0]), np.interp(s, cum, axis[:, 1])])
            i = min(len(axis) - 2, np.searchsorted(cum, s) - 1)
            tv = axis[i + 1] - axis[i]
            tv /= np.linalg.norm(tv) + 1e-9
            ta = math.atan2(tv[0], -tv[1])
            pl = (Lp * 0.16 + 6) * (1.0 - u) ** 0.7 + 3
            for sg in (-1, 1):
                c = jitter_color(green, rng, 0.02, 0.1, 0.12)
                c = c * (0.85 + 0.2 * (1 - t)) * (1.05 if sg > 0 else 0.86)
                if rng.random() < 0.04:
                    c = lerp(c, srgb("#a08a3a"), 0.5)
                draw_leaf(cv, p[0], p[1], ta + sg * 1.25, pl, pl * 0.48, np.clip(c, 0, 1), rng,
                          shape="elliptic", serr=0, nserr=0, veins=pl > 9)
            s += max(3.2, pl * 0.42)
        # Spitze des Fiederblatts
        tv = axis[-1] - axis[-2]
        draw_leaf(cv, axis[-1][0], axis[-1][1], math.atan2(tv[0], -tv[1]), 8, 4, green, rng,
                  shape="elliptic", serr=0, nserr=0, veins=False)
    rgb, a = cv.result()
    rgb = mult_noise(rgb, a, 0.05, seed + 3)
    print(name, "Deckung", round(float((a > 0.5).mean()), 3))
    return save(to_img(rgb, a), name)


# =====================================================================
# Gras: Halme von unten; optional Rispen
# =====================================================================
def grass_blades(cv, rng, x0, x1, y_bottom, hmin, hmax, n, wmin, wmax, cols, dry=0.1,
                 lean=0.25, panicles=0, fan=0.0):
    """fan > 0: Halme entspringen einem schmalen Fuß (Breite fan * Kartenbreite) und
    fächern nach oben auf -> keine gerade, voll deckende Unterkante."""
    xc, hw = (x0 + x1) / 2, (x1 - x0) / 2
    for i in range(n):
        if fan > 0:
            xt = xc + hw * np.clip(rng.normal(0, 0.5), -1, 1)       # Spitze
            rel = (xt - xc) / hw
            x = xc + (xt - xc) * fan + rng.normal(0, hw * fan * 0.25)
            h = rng.uniform(hmin, hmax) * (1 - 0.45 * abs(rel) ** 1.5)
            lx = (xt - x) + rng.normal(0, lean * 0.3) * h
        else:
            x = rng.uniform(x0, x1)
            h = rng.uniform(hmin, hmax) * (1 - 0.35 * abs((x - xc) / hw) ** 2)
            lx = rng.normal(0, lean) * h + (x - xc) * 0.35
        bend = rng.uniform(0.2, 0.6) * np.sign(lx if lx != 0 else 1)
        p0 = (x, y_bottom + 2)
        p2 = (x + lx, y_bottom - h)
        p1 = (x + lx * (0.2 + bend * 0.2), y_bottom - h * 0.55)
        pts = bezier(p0, p1, p2, 12)
        c = cols[rng.integers(len(cols))]
        c = jitter_color(c, rng, 0.02, 0.15, 0.15)
        if rng.random() < dry:
            c = jitter_color(srgb("#a89a62"), rng, 0.02, 0.2, 0.15)
        w = rng.uniform(wmin, wmax)
        cv.thick_curve(pts, w, 0.6, c * 0.8)
        cv.thick_curve(pts, w * 0.55, 0.4, np.clip(c * 1.08, 0, 1))
    for i in range(panicles):
        x = rng.uniform(x0 + (x1 - x0) * 0.15, x1 - (x1 - x0) * 0.15)
        h = rng.uniform(hmax * 0.95, hmax * 1.12)
        lx = rng.normal(0, 0.12) * h
        p0, p2 = (x, y_bottom + 2), (x + lx, y_bottom - h)
        p1 = (x + lx * 0.3, y_bottom - h * 0.5)
        pts = bezier(p0, p1, p2, 14)
        stem = jitter_color(srgb("#8a9348"), rng, 0.02, 0.1, 0.1)
        cv.thick_curve(pts, 2.2, 1.0, stem)
        top = pts[-1]
        tv = pts[-1] - pts[-3]
        tv /= np.linalg.norm(tv)
        ph = jitter_color(srgb("#9c8f62"), rng, 0.03, 0.2, 0.15)
        for k in range(26):
            s = rng.uniform(0, 1)
            base = top - tv * s * h * 0.22
            a = math.atan2(tv[0], -tv[1]) + rng.choice([-1, 1]) * rng.uniform(0.25, 0.8)
            ln = (1 - s) * 14 + 5
            q = base + np.array([math.sin(a), -math.cos(a)]) * ln
            cv.line([tuple(base), tuple(q)], ph * 0.85, 1.0)
            cv.ellipse(q[0], q[1], 2.0, 3.0, ph)


def grass_tex(name, seed):
    rng = np.random.default_rng(seed)
    cv = Canvas(S, S, ss=2)
    cols = [srgb("#5a7a2e"), srgb("#6e8a36"), srgb("#4b6a2a"), srgb("#7c9440"), srgb("#55752f")]
    grass_blades(cv, rng, 24, S - 24, S, S * 0.5, S * 0.97, 170, 5, 10, cols, dry=0.12, lean=0.18, fan=0.28)
    rgb, a = cv.result()
    ys = np.linspace(0, 1, S)[:, None, None]       # 0 oben .. 1 unten
    rgb = rgb * (1.0 - 0.45 * ys ** 1.6)          # Fuß dunkler (Eigenverschattung)
    rgb = mult_noise(rgb, a, 0.05, seed + 1)
    print(name, "Deckung", round(float((a > 0.5).mean()), 3))
    return save(to_img(rgb, a), name)


def nettle_plant(cv, rng, cx, y_bottom, height):
    stem = srgb("#4f6a2c")
    leafc = srgb("#3f6127")
    lean = rng.normal(0, 0.06) * height
    pts = bezier((cx, y_bottom + 2), (cx + lean * 0.3, y_bottom - height * 0.5), (cx + lean, y_bottom - height), 20)
    cv.thick_curve(pts, 5.0, 2.0, stem * 0.9)
    n_nodes = 7
    for k in range(n_nodes):
        t = 0.18 + 0.8 * k / (n_nodes - 1)
        i = int(t * (len(pts) - 1))
        p = pts[i]
        L = (1.0 - t * 0.55) * height * 0.16 + 10
        facing = (k % 2 == 0)       # kreuzgegenständig: jedes 2. Paar seitlich, das andere verkürzt
        for sgn in (-1, 1):
            c = jitter_color(leafc, rng, 0.015, 0.1, 0.1) * (1.0 if sgn > 0 else 0.85)
            if facing:
                ang = sgn * rng.uniform(1.75, 2.05)      # seitlich, leicht hängend
                draw_leaf(cv, p[0], p[1], ang, L, L * 0.62, np.clip(c, 0, 1), rng, shape="cordate",
                          serr=0.16, nserr=11, petiole=L * 0.25, stem_col=stem)
            else:
                ang = sgn * rng.uniform(0.5, 0.8)
                draw_leaf(cv, p[0], p[1], ang, L * 0.75, L * 0.55, np.clip(c * 0.9, 0, 1), rng,
                          shape="cordate", serr=0.16, nserr=9, petiole=L * 0.15, stem_col=stem)
        # Blütenrispen (hängende grüne Kätzchen) in den oberen Achseln
        if t > 0.5:
            for sgn in (-1, 1):
                q0 = p
                q1 = p + np.array([sgn * L * 0.5, L * 0.35])
                cv.line([tuple(q0), tuple(q1)], srgb("#7b8a45"), 1.6)
                for m in range(6):
                    u = m / 5
                    q = q0 + (q1 - q0) * u
                    cv.ellipse(q[0], q[1], 2.2, 2.2, srgb("#8d9a52") * rng.uniform(0.85, 1.05))
    # Triebspitze
    draw_leaf(cv, pts[-1][0], pts[-1][1], rng.uniform(-0.2, 0.2), height * 0.07, height * 0.045,
              leafc * 1.05, rng, shape="cordate", serr=0.12, nserr=8)


def tall_grass_tex(name, seed):
    """Atlas: linke Hälfte hohes Gras mit Rispen, rechte Hälfte Brennnessel."""
    rng = np.random.default_rng(seed)
    cv = Canvas(S, S, ss=2)
    cols = [srgb("#5f7d30"), srgb("#72893a"), srgb("#50702b"), srgb("#869a48")]
    grass_blades(cv, rng, 14, S / 2 - 14, S, S * 0.5, S * 0.92, 85, 4, 8, cols, dry=0.18,
                 lean=0.15, panicles=5, fan=0.45)
    for cx, h in ((S * 0.62, S * 0.93), (S * 0.80, S * 0.80), (S * 0.92, S * 0.66)):
        nettle_plant(cv, rng, cx, S, h)
    rgb, a = cv.result()
    ys = np.linspace(0, 1, S)[:, None, None]
    rgb = rgb * (1.0 - 0.40 * ys ** 1.6)
    rgb = mult_noise(rgb, a, 0.05, seed + 1)
    # Mitte trennen (kein Übersprechen der Hälften)
    a[:, S // 2 - 3:S // 2 + 3] = 0
    print(name, "Deckung", round(float((a > 0.5).mean()), 3))
    return save(to_img(rgb, a), name)


# =====================================================================
# Zwergsträucher: oben Blaubeere, unten Heidekraut (Atlas, je 512x256)
# =====================================================================
def dwarf_shrub_tex(name, seed):
    rng = np.random.default_rng(seed)
    cv = Canvas(S, S, ss=2)
    # --- Blaubeere (obere Hälfte, y 0..256)
    yb = S * 0.5 - 2
    stem = srgb("#5e7a34")
    for i in range(38):
        xt = S / 2 + (S / 2 - 40) * np.clip(rng.normal(0, 0.5), -1, 1)
        x = S / 2 + (xt - S / 2) * 0.3 + rng.normal(0, 10)
        dome = 1 - ((xt - S / 2) / (S / 2)) ** 2
        h = (S * 0.5 - 20) * (0.40 + 0.60 * dome) * rng.uniform(0.75, 1.0)
        lx = (xt - x)
        pts = bezier((x, yb), (x + lx * 0.15, yb - h * 0.6), (x + lx, yb - h), 10)
        cv.thick_curve(pts, 3.2, 1.4, stem * rng.uniform(0.8, 1.05))
        # Seitentriebe mit Blättern
        for k in range(rng.integers(3, 6)):
            j = rng.integers(3, 10)
            p = pts[j]
            a = rng.uniform(-1.3, 1.3)
            d = np.array([math.sin(a), -math.cos(a)]) * rng.uniform(15, 35)
            q = p + d
            cv.line([tuple(p), tuple(q)], stem * 0.95, 1.6)
            for m in range(3):
                u = (m + 1) / 3
                r = p + d * u
                c = jitter_color(srgb("#5d8a33"), rng, 0.03, 0.12, 0.14)
                if rng.random() < 0.02:
                    c = lerp(c, srgb("#7a4a2a"), 0.6)             # vereinzelt rötliche Blätter
                draw_leaf(cv, r[0], r[1], a + rng.choice([-1, 1]) * rng.uniform(0.5, 1.2),
                          rng.uniform(16, 22), rng.uniform(9, 12), c, rng, shape="elliptic",
                          serr=0.03, nserr=10, veins=False)
            if rng.random() < 0.25:     # Beere
                cv.ellipse(q[0], q[1] + 4, 3.5, 3.5, srgb("#2b2c4a"))
    # --- Heidekraut (untere Hälfte, y 256..512)
    yb = S - 2
    dark = srgb("#3f5631")
    flower = srgb("#a86f9a")
    for i in range(110):
        xt = S / 2 + (S / 2 - 30) * np.clip(rng.normal(0, 0.5), -1, 1)
        x = S / 2 + (xt - S / 2) * 0.3 + rng.normal(0, 10)
        dome = 1 - ((xt - S / 2) / (S / 2)) ** 2
        h = (S * 0.5 - 16) * (0.35 + 0.65 * dome) * rng.uniform(0.7, 1.0)
        lx = (xt - x)
        pts = bezier((x, yb), (x + lx * 0.2, yb - h * 0.5), (x + lx, yb - h), 12)
        cv.thick_curve(pts, 2.6, 1.0, srgb("#4b3f30"))
        for j in range(2, len(pts)):
            p = pts[j]
            u = j / (len(pts) - 1)
            for m in range(6):
                a = rng.uniform(-1.3, 1.3)
                ln = rng.uniform(6, 14) * (1.1 - u * 0.4)
                q = p + np.array([math.sin(a), -math.cos(a)]) * ln
                cv.line([tuple(p), tuple(q)], jitter_color(dark, rng, 0.02, 0.15, 0.2), 1.6)
            if u > 0.55 and rng.random() < 0.75:
                c = jitter_color(flower, rng, 0.02, 0.15, 0.15)
                cv.ellipse(p[0] + rng.normal(0, 2), p[1], 2.6, 2.2, c)
                cv.ellipse(p[0] + rng.normal(0, 3), p[1] - 2, 2.2, 2.0, c * 0.85)
    rgb, a = cv.result()
    ys = np.linspace(0, 1, S)[:, None, None]
    yh = (ys * 2) % 1.0                            # 0 oben .. 1 unten je Hälfte
    rgb = rgb * (1.0 - 0.45 * yh ** 1.5)
    rgb = mult_noise(rgb, a, 0.05, seed + 1)
    a[S // 2 - 2:S // 2 + 2, :] = 0
    print(name, "Deckung", round(float((a > 0.5).mean()), 3))
    return save(to_img(rgb, a), name)


# =====================================================================
# Rinde-Atlas: u 0..0.75 Rinde (horizontal + vertikal kachelbar, 384 px),
# u 0.75..1 / v 0.75..1 (Bild oben rechts, 128x128): Schnittfläche mit Jahresringen,
# u 0.75..1 / v 0.5..0.75: Bruchholz (hell, faserig)
# =====================================================================
def cut_face(sz, seed, weather=0.4, moss=0.0):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:sz, 0:sz] + 0.5
    cx = cy = sz / 2
    dx, dy = xx - cx, yy - cy
    r = np.sqrt(dx * dx + dy * dy) / (sz / 2)
    ang = np.arctan2(dy, dx)
    wob = 0.03 * np.sin(3 * ang + 1.3) + 0.02 * np.sin(5 * ang + 0.4)
    rr = r * (1 + wob)
    rings = 0.5 + 0.5 * np.sin(rr * 2 * math.pi * 19 + 2 * np.sin(rr * 7))
    rings = rings ** 3
    light = srgb("#b0905f")
    dark_ring = srgb("#7a5a3a")
    col = lerp(light, dark_ring, rings * 0.7)
    heart = smoothstep(0.35, 0.0, rr)
    col = lerp(col, srgb("#8a6038"), heart * 0.45)
    # Radiale Risse
    for k in range(rng.integers(5, 9)):
        a0 = rng.uniform(-math.pi, math.pi)
        d = np.abs(np.angle(np.exp(1j * (ang - a0)))) * r
        crack = smoothstep(0.035, 0.0, d) * smoothstep(0.05, 0.25, r) * smoothstep(0.95, 0.6, r)
        col = lerp(col, srgb("#3a2a1e"), crack * rng.uniform(0.6, 1.0))
    # Verwitterung: vergraut
    n = fnoise(sz, sz, 1.8, seed=seed + 3)
    g = srgb("#8a8478")
    col = lerp(col, g, np.clip(weather + 0.12 * n, 0, 1))
    if moss > 0:
        m = smoothstep(0.6, 1.4, fnoise(sz, sz, 2.2, seed=seed + 5) + r * 0.6) * moss
        col = lerp(col, srgb("#4d6a24"), m)
    # Rindenring
    bark = smoothstep(0.90, 0.96, rr)
    col = lerp(col, srgb("#3b3128"), bark)
    hgt = rings * 0.4 - bark * 0.3 + 0.2 * n
    return col, hgt


def bark_atlas(name, seed, style):
    W, H = S, S
    bw = 384
    rng = np.random.default_rng(seed)
    if style == "furrow":       # Eiche/Kiefer: tiefe Längsfurchen
        n1 = fnoise(H, bw, 2.4, sx=1.0, sy=7.0, seed=seed)
        n2 = fnoise(H, bw, 2.0, sx=3.5, sy=1.0, seed=seed + 1)
        n3 = fnoise(H, bw, 1.5, seed=seed + 2, fmin=40)
        plates = smoothstep(-0.6, 0.9, n1 + 0.35 * n2)
        hgt = plates + 0.05 * n3
        col = lerp(srgb("#241b14"), srgb("#5e5246"), plates)
        col = lerp(col, srgb("#7d7466"), smoothstep(0.75, 1.1, plates) * 0.6)
        lich = smoothstep(1.0, 1.8, fnoise(H, bw, 2.6, seed=seed + 4))
        col = lerp(col, srgb("#8b9076"), lich * 0.7)
        col = col * (1 + 0.06 * n3[..., None])
    elif style == "smooth":     # junge Buche/Hasel: glatt, grau-oliv, Lentizellen
        n1 = fnoise(H, bw, 2.2, sx=1.0, sy=2.5, seed=seed)
        n3 = fnoise(H, bw, 1.4, seed=seed + 2, fmin=40)
        col = lerp(srgb("#6f6b5e"), srgb("#8e8a7c"), smoothstep(-1.5, 1.5, n1))
        col = lerp(col, srgb("#6a7258"), smoothstep(0.8, 1.6, fnoise(H, bw, 2.4, seed=seed + 5)) * 0.5)
        hgt = 0.1 * n1 + 0.05 * n3
        len_ = np.zeros((H, bw))
        for i in range(500):
            y, x = rng.integers(0, H), rng.integers(0, bw)
            ln = rng.integers(3, 8)
            xs = (np.arange(x, x + ln)) % bw
            len_[y, xs] = 1
        len_ = np.clip(len_ + 0.5 * np.roll(len_, 1, 0), 0, 1)
        col = lerp(col, srgb("#4a443a"), len_ * 0.6)
        hgt = hgt - 0.3 * len_
        col = col * (1 + 0.05 * n3[..., None])
    else:                       # "dead": Totholz, teils entrindet, Moos
        n1 = fnoise(H, bw, 2.4, sx=1.0, sy=6.0, seed=seed)
        n2 = fnoise(H, bw, 2.2, sx=2.5, sy=1.0, seed=seed + 1)
        n3 = fnoise(H, bw, 1.5, seed=seed + 2, fmin=40)
        grain = fnoise(H, bw, 1.6, sx=1.0, sy=14.0, seed=seed + 6)
        plates = smoothstep(-0.6, 0.9, n1 + 0.35 * n2)
        barkc = lerp(srgb("#251c15"), srgb("#5a4c3e"), plates)
        wood = lerp(srgb("#5e564b"), srgb("#837868"), smoothstep(-1.5, 1.5, grain))
        peel = smoothstep(0.6, 0.9, fnoise(H, bw, 2.6, sx=1.0, sy=3.0, seed=seed + 7))
        col = lerp(barkc, wood, peel)
        hgt = plates * (1 - peel) + (0.35 + 0.08 * grain) * peel + 0.12 * n3
        moss = smoothstep(0.5, 1.3, fnoise(H, bw, 2.4, sx=1.0, sy=1.6, seed=seed + 8) + 0.25 * n3)
        mcol = lerp(srgb("#3d5a1c"), srgb("#6f8a2c"), smoothstep(-1, 1.5, n3))
        col = lerp(col, mcol, moss * 0.9)
        hgt = hgt + 0.25 * moss
        lich = smoothstep(1.1, 1.8, fnoise(H, bw, 2.6, seed=seed + 4))
        col = lerp(col, srgb("#9aa088"), lich * 0.6 * (1 - moss))
        col = col * (1 + 0.06 * n3[..., None])
    img = np.zeros((H, W, 3))
    hh = np.zeros((H, W))
    img[:, :bw] = col
    hh[:, :bw] = hgt
    # Schnittfläche oben rechts (Bildzeilen 0..127)
    cs = W - bw
    cf, ch = cut_face(cs, seed + 11, weather=0.5 if style != "smooth" else 0.15,
                      moss=0.35 if style == "dead" else 0.0)
    img[0:cs, bw:] = cf
    hh[0:cs, bw:] = ch
    # Bruchholz (Zeilen 128..255): faserig, hell
    gr = fnoise(cs, cs, 1.7, sx=1.0, sy=10.0, seed=seed + 12)
    wcol = lerp(srgb("#8a7860"), srgb("#c0aa84"), smoothstep(-1.5, 1.5, gr))
    if style == "dead":
        wcol = lerp(wcol, srgb("#8a857a"), 0.45)
    img[cs:2 * cs, bw:] = wcol
    hh[cs:2 * cs, bw:] = 0.3 * gr
    # Rest (Zeilen 256..511, rechts): Rinde wiederholen (nicht benutzt, nur Füllung)
    img[2 * cs:, bw:] = col[2 * cs:, :cs]
    hh[2 * cs:, bw:] = hgt[2 * cs:, :cs]
    save(to_img(img), name + "_col.png")
    from scipy import ndimage as ndi
    hh = ndi.gaussian_filter(hh, 0.8, mode="wrap")
    save(normal_from_height(hh, 4.0 if style != "smooth" else 2.5), name + "_nrm.png")


# =====================================================================
# Findling (Lausitzer Granodiorit): grau, Körnung, Flechten, etwas Moos
# =====================================================================
def rock_tex(name, seed):
    rng = np.random.default_rng(seed)
    n1 = fnoise(S, S, 2.2, seed=seed)
    n2 = fnoise(S, S, 1.2, seed=seed + 1, fmin=80)
    base = lerp(srgb("#6c6c68"), srgb("#8e8c86"), smoothstep(-2, 2, n1))
    speck = rng.random((S, S))
    col = base * (1 + 0.10 * n2[..., None])
    col = np.where((speck < 0.06)[..., None], col * 0.45, col)                  # Biotit
    col = np.where((speck > 0.955)[..., None], lerp(col, srgb("#d8d4cc"), 0.6), col)  # Feldspat/Quarz
    col = np.where(((speck > 0.93) & (speck < 0.94))[..., None], lerp(col, srgb("#b49a8a"), 0.5), col)
    from scipy import ndimage as ndi
    col = np.stack([ndi.gaussian_filter(col[..., c], 0.6, mode="wrap") for c in range(3)], -1)
    lich = smoothstep(0.8, 1.5, fnoise(S, S, 2.6, seed=seed + 4))
    col = lerp(col, srgb("#9a9e8c"), lich * 0.6)
    lich2 = smoothstep(1.9, 2.4, fnoise(S, S, 2.8, seed=seed + 5))
    col = lerp(col, srgb("#a09a6a"), lich2 * 0.45)
    moss = smoothstep(1.1, 1.8, fnoise(S, S, 2.3, seed=seed + 6))
    col = lerp(col, srgb("#3f5222"), moss * 0.65)
    hgt = 0.6 * n1 + 0.06 * n2 + 0.2 * moss
    from scipy import ndimage as ndi
    hgt = ndi.gaussian_filter(hgt, 0.7, mode="wrap")
    save(to_img(col), name + "_col.png")
    save(normal_from_height(hgt, 3.5), name + "_nrm.png")


def main():
    leaf_cluster("veg_leaf_hazel.png", 11, "#4e6c2a", 84, 68, "ovate", n_twigs=7, spread=1.4,
                 twig_len=420, spacing=40, serr=0.07, nserr=16)
    leaf_cluster("veg_leaf_dense.png", 23, "#3d5a26", 44, 30, "elliptic", n_twigs=10, spread=1.45,
                 twig_len=400, spacing=19, serr=0.05, nserr=10, yellow=0.03)
    leaf_cluster("veg_leaf_beech.png", 37, "#587a2a", 64, 39, "elliptic", n_twigs=6, spread=1.3,
                 twig_len=430, spacing=30, serr=0.05, nserr=9, yellow=0.04, flat_spray=True)
    fern_frond("veg_fern.png", 41)
    grass_tex("veg_grass.png", 53)
    tall_grass_tex("veg_grass_tall.png", 59)
    dwarf_shrub_tex("veg_heather.png", 61)
    bark_atlas("veg_bark_furrow", 71, "furrow")
    bark_atlas("veg_bark_smooth", 73, "smooth")
    bark_atlas("veg_bark_dead", 79, "dead")
    rock_tex("veg_rock", 83)


if __name__ == "__main__":
    main()
