"""Graffiti-Atlas fuer die Erdgeschosszone der Fassaden (frei erfundene Motive).

Aufruf (Projektordner): .venv/bin/python tools/blender/furniture_graffiti.py
Ausgabe: godot/assets/textures/street/graffiti.png (2048 x 1024, 4 x 2 Zellen a 512 px, RGBA)
         godot/assets/textures/street/graffiti.json (Zelle -> Art, UV-Rechteck, empfohlene Groesse)
Alle Schriftzuege sind erfundene Buchstabenfolgen (keine echten Writer-Namen), keine Marken,
keine Symbole mit politischer Bedeutung. Motive waagerecht, Oberkante = Bildoberkante.
"""
import json
import os
import numpy as np
from scipy import ndimage
from furniture_texutil import fbm, hexcol, Canvas, rng, blob_poly, rot_pts, to_img
from furniture_litter import Layer, C

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUTD = os.path.join(ROOT, "godot", "assets", "textures", "street")
INNER = 56  # Inhalt bleibt mindestens so weit vom Zellrand weg (plus Spruehnebel)


# =================================================================== Strichschrift
def arc(cx, cy, rx, ry, a0, a1, n=9):
    a = np.radians(np.linspace(a0, a1, n))
    return [(cx + rx * np.cos(t), cy + ry * np.sin(t)) for t in a]


# Einheitsbox: x 0..Breite, y 0 (Grundlinie) .. 1 (Oberlaenge), y nach oben
GLYPHS = {
    "A": (0.75, [[(0, 0), (0.375, 1), (0.75, 0)], [(0.15, 0.38), (0.6, 0.38)]]),
    "B": (0.64, [[(0, 0), (0, 1)],
                 [(0, 1), (0.35, 1)] + arc(0.35, 0.75, 0.25, 0.25, 90, -90) + [(0, 0.5)],
                 [(0, 0.5), (0.38, 0.5)] + arc(0.38, 0.25, 0.26, 0.25, 90, -90) + [(0, 0)]]),
    "E": (0.6, [[(0.6, 1), (0, 1), (0, 0), (0.6, 0)], [(0, 0.52), (0.45, 0.52)]]),
    "I": (0.15, [[(0.07, 0), (0.07, 1)]]),
    "K": (0.66, [[(0, 0), (0, 1)], [(0.62, 1), (0.04, 0.42)], [(0.22, 0.6), (0.66, 0)]]),
    "M": (0.85, [[(0, 0), (0, 1), (0.42, 0.35), (0.85, 1), (0.85, 0)]]),
    "N": (0.7, [[(0, 0), (0, 1), (0.7, 0), (0.7, 1)]]),
    "O": (0.75, [arc(0.375, 0.5, 0.375, 0.5, 90, 450, 21)]),
    "Q": (0.78, [arc(0.375, 0.5, 0.375, 0.5, 90, 450, 21), [(0.45, 0.25), (0.82, -0.1)]]),
    "R": (0.66, [[(0, 0), (0, 1), (0.33, 1)] + arc(0.33, 0.75, 0.27, 0.25, 90, -90) + [(0, 0.5)],
                 [(0.25, 0.5), (0.66, 0)]]),
    "S": (0.62, [arc(0.31, 0.75, 0.29, 0.25, 10, 270, 10) + arc(0.31, 0.25, 0.31, 0.25, 90, -190, 10)]),
    "U": (0.68, [[(0, 1), (0, 0.32)] + arc(0.34, 0.32, 0.34, 0.32, 180, 360, 9) + [(0.68, 1)]]),
    "V": (0.7, [[(0, 1), (0.35, 0), (0.7, 1)]]),
    "X": (0.7, [[(0, 1), (0.7, 0)], [(0.7, 1), (0, 0)]]),
    "Z": (0.66, [[(0, 1), (0.66, 1), (0, 0), (0.66, 0)]]),
}


def chaikin(pts, it=2):
    pts = [np.array(p, float) for p in pts]
    for _ in range(it):
        out = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            out += [0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b]
        out.append(pts[-1])
        pts = out
    return [tuple(p) for p in pts]


def word_strokes(word, seed, slant=0.25, jitter=0.03, squeeze=1.0, gap=0.12, bounce=0.08, rot=0.0):
    """Buchstaben -> Liste von Buchstabengruppen (je Liste von Strichen) in Einheiten der Hoehe."""
    r = rng(seed)
    groups = []
    x = 0.0
    for k, ch in enumerate(word):
        w, st = GLYPHS[ch]
        sh = r.uniform(0.88, 1.12) * (1.15 if k == 0 else 1.0)
        sw = sh * squeeze * r.uniform(0.9, 1.08)
        yo = r.uniform(-bounce, bounce)
        ang = r.uniform(-rot, rot)
        cx = x + w * sw / 2
        g = []
        for s in st:
            pts = []
            for px, py in s:
                X = x + (px + r.normal(0, jitter)) * sw + py * slant * sh
                Y = -(py + r.normal(0, jitter)) * sh - yo  # Bild-y nach unten
                pts.append((X, Y))
            if ang:
                pts = rot_pts(pts, cx, -0.5 * sh, ang)
            g.append(pts)
        groups.append(g)
        x += w * sw + gap
    return groups


def fit(groups, box, extra=()):
    """Skaliert Gruppen (+ Zusatzstriche) einheitlich in box=(x0,y0,x1,y1) und zentriert."""
    allp = [p for g in groups for s in g for p in s] + [p for s in extra for p in s]
    xs = [p[0] for p in allp]
    ys = [p[1] for p in allp]
    bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
    x0, y0, x1, y1 = box
    k = min((x1 - x0) / (bx1 - bx0), (y1 - y0) / (by1 - by0))
    ox = (x0 + x1) / 2 - (bx0 + bx1) / 2 * k
    oy = (y0 + y1) / 2 - (by0 + by1) / 2 * k

    def T(s):
        return [(p[0] * k + ox, p[1] * k + oy) for p in s]
    return [[T(s) for s in g] for g in groups], [T(s) for s in extra], k


# =================================================================== Spruehfarbe
def spray(strokes, width, seed, wvar=0.3, smooth=2, taper=True, mist=0.12, dots=0.09):
    """Gesprühte Linien: Alpha mit weicher Kante, Spruehnebel und Farbpunkten."""
    r = rng(seed)
    core = Canvas(C, C)
    for s in strokes:
        pts = chaikin(s, smooth) if smooth else s
        n = len(pts)
        f1, f2, ph = r.uniform(1, 3), r.uniform(0.5, 2), r.uniform(0, 6)
        for i in range(n - 1):
            t = i / max(n - 2, 1)
            w = width * (1 + wvar * np.sin(t * np.pi * f1 + ph) * np.cos(t * f2 * 3))
            if taper:
                w *= 0.55 + 0.45 * min(1.0, t * 7, (1 - t) * 5)
            core.line([pts[i], pts[i + 1]], max(w, 0.8), 255)
    m = core.mask()
    soft = ndimage.gaussian_filter(m, max(width * 0.14, 0.5))
    soft = np.clip(soft * 1.15, 0, 1)
    halo = ndimage.gaussian_filter(m, width * 0.9 + 1.0)
    sp = (r.random((C, C)) < halo * dots).astype(float)
    sp = ndimage.gaussian_filter(sp, 0.55) * 1.6
    a = soft + (1 - soft) * np.clip(halo * mist + sp * 0.45, 0, 1)
    dens = 0.88 + 0.12 * fbm(C, C, 12, 3, seed)
    return np.clip(a * dens, 0, 1), m


def drips(mask, n, seed, maxlen=60.0, width=2.6, minlen=0.25):
    """Laeufer: von der Unterkante gefuellter Bereiche senkrecht nach unten."""
    r = rng(seed)
    ys, xs = np.nonzero(mask > 0.85)
    c = Canvas(C, C)
    if len(xs) == 0:
        return c.mask()
    for k in range(n):
        i = r.integers(len(xs))
        x, y = int(xs[i]), int(ys[i])
        while y + 1 < C and mask[y + 1, x] > 0.5:
            y += 1
        L = (r.uniform(minlen, 1.0) ** 1.8) * maxlen + 4
        w = width * r.uniform(0.6, 1.1)
        xe = x + r.normal(0, 0.8)
        c.line([(x, y - 2), (x + (xe - x) * 0.5, y + L * 0.6), (xe, y + L)], w, 255)
        c.ellipse(xe, y + L, w * 0.75, w * 1.05)
    return c.mask(0.3)


def colvar(col, seed, amt=0.06):
    n = fbm(C, C, 10, 3, seed)
    return np.ones((C, C, 3)) * hexcol(col) * (1 - amt + 2 * amt * n[..., None])


# =================================================================== Tags
def tag(word, col, seed, width, slant=0.28, squeeze=1.0, flourish="swoosh", ndrip=5, box=None,
        jitter=0.035, gap=0.1):
    L = Layer()
    groups = word_strokes(word, seed, slant=slant, squeeze=squeeze, jitter=jitter, gap=gap)
    r = rng(seed + 50)
    extra = []
    allp = [p for g in groups for s in g for p in s]
    xmin, xmax = min(p[0] for p in allp), max(p[0] for p in allp)
    ymax = max(p[1] for p in allp)
    if flourish == "swoosh":    # Unterstreichung, die vom Ende zurueckschwingt
        extra.append([(xmax - 0.1, ymax - 0.2), (xmax + 0.05, ymax + 0.08), (xmax * 0.6, ymax + 0.2),
                      (xmin + 0.1, ymax + 0.18), (xmin - 0.12, ymax + 0.05)])
    elif flourish == "arrow":   # Pfeil am letzten Buchstaben
        extra.append([(xmax - 0.15, ymax - 0.3), (xmax + 0.35, ymax - 0.55)])
        extra.append([(xmax + 0.18, ymax - 0.6), (xmax + 0.36, ymax - 0.56), (xmax + 0.3, ymax - 0.38)])
    elif flourish == "star":    # Sternchen oben rechts + Punktlinie unten
        cx, cy = xmax + 0.18, -1.15
        for a in (0, 60, 120):
            t = np.radians(a)
            extra.append([(cx - 0.13 * np.cos(t), cy - 0.13 * np.sin(t)), (cx + 0.13 * np.cos(t), cy + 0.13 * np.sin(t))])
        extra.append([(xmin, ymax + 0.15), (xmax * 0.95, ymax + 0.1)])
    box = box or (INNER, 150, C - INNER, 362)
    groups, extra, k = fit(groups, box, extra)
    strokes = [s for g in groups for s in g] + extra
    a, m = spray(strokes, width, seed)
    d = drips(m, ndrip, seed + 3, maxlen=70, width=width * 0.32)
    a = np.clip(a + d, 0, 1)
    L.over(colvar(col, seed), a)
    return L


# =================================================================== Throw-ups
def soft_threshold(x, t, k=6.0):
    return np.clip((x - t) * k + 0.5, 0, 1)


def throwup(word, fill, line, seed, slant=0.12, width_rel=0.29, box=None, shine=False):
    L = Layer()
    groups = word_strokes(word, seed, slant=slant, jitter=0.015, gap=0.0, bounce=0.07, rot=0.1,
                          squeeze=1.1)
    box = box or (INNER + 18, 120, C - INNER - 18, 392)
    # Platz fuer Strichbreite und Kontur lassen
    groups, _, k = fit(groups, (box[0] + 40, box[1] + 40, box[2] - 40, box[3] - 40))
    width = width_rel * k
    fills = []
    for g in groups:
        c = Canvas(C, C)
        for s in g:
            c.line(chaikin(s, 3), width, 255)
        m = c.mask()
        b = ndimage.gaussian_filter(m, width * 0.16)
        fills.append(soft_threshold(b, 0.45, 5.0))
    union = np.max(fills, axis=0)
    ow = max(width * 0.16, 4.0)
    outer = soft_threshold(ndimage.gaussian_filter(union, ow * 1.1), 0.12, 6.0)
    # Aussenkontur mit Spruehrand
    halo = ndimage.gaussian_filter(outer, 3.0)
    r = rng(seed)
    sp = (r.random((C, C)) < halo * 0.2).astype(float)
    mist = np.clip(halo * 0.12 + ndimage.gaussian_filter(sp, 0.5) * 1.2, 0, 1) * (1 - outer)
    L.over(colvar(line, seed + 1, 0.04), np.clip(outer + mist, 0, 1))
    # Buchstaben einzeln: Kontur + Fuellung (spaetere ueberdecken fruehere)
    stripes = 0.5 + 0.5 * np.sin(np.mgrid[0:C, 0:C][0] / 5.0 + 3 * fbm(C, C, 6, 2, seed))
    for i, f in enumerate(fills):
        lo = soft_threshold(ndimage.gaussian_filter(f, ow * 0.55), 0.2, 6.0)
        L.over(colvar(line, seed + 10 + i, 0.04), lo)
        inner = soft_threshold(ndimage.gaussian_filter(f, 1.2), 0.55, 6.0)
        fc = colvar(fill, seed + 20 + i, 0.035) * (0.965 + 0.035 * stripes[..., None])
        L.over(fc, inner * (0.93 + 0.07 * fbm(C, C, 20, 3, seed + i)))
    # Laeufer in Fuell- und Konturfarbe
    d1 = drips(outer, 4, seed + 5, maxlen=55, width=3.2)
    L.over(np.ones((C, C, 3)) * hexcol(line), d1 * (1 - outer))
    if shine:
        sh = Canvas(C, C)
        for f in fills:
            ys, xs = np.nonzero(f > 0.95)
            if len(xs) == 0:
                continue
            j = np.argmin(xs + ys)
            x, y = xs[j] + width * 0.25, ys[j] + width * 0.25
            sh.line([(x, y + 10), (x, y), (x + 12, y - 3)], 3.2, 255)
        L.over(np.ones((C, C, 3)) * hexcol("#ffffff"), sh.mask(0.5) * 0.95)
    return L


# =================================================================== Stencil
def stencil(seed=31):
    L = Layer()
    r = rng(seed)
    S, ox, oy = 300.0, 112.0, 120.0   # Einheits-Vogel -> Pixel

    def P(x, y):
        return (ox + x * S, oy + (1 - y) * S * 0.9)
    c = Canvas(C, C)
    # Koerper (gedrehte Ellipse), Kopf, Schnabel, Schwanz, Beine
    body = [P(0.45 + 0.30 * np.cos(t) * np.cos(-0.35) - 0.19 * np.sin(t) * np.sin(-0.35),
              0.45 + 0.30 * np.cos(t) * np.sin(-0.35) + 0.19 * np.sin(t) * np.cos(-0.35))
            for t in np.linspace(0, 2 * np.pi, 40, endpoint=False)]
    c.poly(body)
    hx, hy = P(0.72, 0.66)
    c.ellipse(hx, hy, 0.135 * S, 0.125 * S * 0.9)
    c.poly([P(0.82, 0.70), P(0.97, 0.655), P(0.83, 0.60)])
    c.poly([P(0.22, 0.42), P(-0.12, 0.30), P(-0.10, 0.22), P(0.24, 0.31)])
    for lx in (0.46, 0.56):
        c.line([P(lx, 0.30), P(lx - 0.03, 0.12)], 0.022 * S, 255, joint=False)
    # Ast mit zwei Blaettern
    br = [P(-0.15, 0.10), P(0.3, 0.12), P(0.7, 0.09), P(1.05, 0.13)]
    c.line(br, 0.035 * S, 255)
    for (bx, by, a) in ((0.86, 0.17, -0.6), (0.98, 0.05, 0.5)):
        px, py = P(bx, by)
        c.poly(rot_pts(blob_poly(px, py, 0.06 * S, 14, 0.05, 3, 1.6, 0.6), px, py, a))
    m = c.mask(0.5)
    # Schablonenstege: Auge, Fluegellinie, Trennung Kopf/Koerper
    cut = Canvas(C, C)
    ex, ey = P(0.75, 0.69)
    cut.ellipse(ex, ey, 0.025 * S, 0.025 * S)
    cut.line([P(0.30, 0.50), P(0.48, 0.47), P(0.62, 0.53)], 0.018 * S, 255, joint=False)
    cut.line([P(0.36, 0.40), P(0.52, 0.38), P(0.60, 0.43)], 0.014 * S, 255, joint=False)
    cut.line([P(0.61, 0.59), P(0.66, 0.53)], 0.016 * S, 255, joint=False)
    m = np.clip(m - cut.mask(0.4), 0, 1)
    # leichter Spruehnebel um die Schablone + unregelmaessige Deckung
    halo = ndimage.gaussian_filter(m, 2.5)
    sp = (r.random((C, C)) < halo * 0.25).astype(float)
    a = m * (0.9 + 0.1 * fbm(C, C, 16, 3, seed)) + (1 - m) * np.clip(halo * 0.25 + sp * 0.5, 0, 1)
    L.over(colvar("#1c1c1c", seed, 0.03), np.clip(a, 0, 1))
    # kleines rotes Herz (zweite Schablone)
    hc = Canvas(C, C)
    pts = []
    for t in np.linspace(0, 2 * np.pi, 40, endpoint=False):
        x = 16 * np.sin(t) ** 3
        y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
        pts.append((392 + x * 2.6, 132 - y * 2.6))
    hc.poly(pts)
    hm = hc.mask(0.5)
    hh = ndimage.gaussian_filter(hm, 2.0)
    L.over(colvar("#c8232c", seed + 1, 0.04), np.clip(hm * 0.95 + (1 - hm) * hh * 0.2, 0, 1))
    return L


# =================================================================== Paste-up + Sticker
def _creature(c, cx, cy, s, w):
    """Erfundene Comicfigur (runder Kopf, grosse Augen) als Strichzeichnung."""
    pts = [(cx + np.cos(t) * s * (1 + 0.05 * np.sin(3 * t)), cy + np.sin(t) * s * 0.92)
           for t in np.linspace(0, 2 * np.pi, 40)]
    c.line(pts, w, 255)
    for ex in (-0.38, 0.38):
        e = [(cx + ex * s + np.cos(t) * s * 0.26, cy - 0.1 * s + np.sin(t) * s * 0.3)
             for t in np.linspace(0, 2 * np.pi, 24)]
        c.line(e, w * 0.8, 255)
        c.ellipse(cx + ex * s + 0.06 * s, cy - 0.05 * s, s * 0.09, s * 0.11)
    c.line([(cx - 0.25 * s, cy + 0.45 * s), (cx, cy + 0.55 * s), (cx + 0.25 * s, cy + 0.45 * s)], w * 0.8, 255)
    for sx in (-1, 1):  # Fuehler
        c.line([(cx + sx * 0.35 * s, cy - 0.85 * s), (cx + sx * 0.55 * s, cy - 1.25 * s)], w * 0.8, 255)
        c.ellipse(cx + sx * 0.55 * s, cy - 1.25 * s, w * 1.3, w * 1.3)
    # Koerper angedeutet + Schraffur
    c.line([(cx - 0.6 * s, cy + 0.85 * s), (cx - 0.75 * s, cy + 1.6 * s)], w, 255)
    c.line([(cx + 0.6 * s, cy + 0.85 * s), (cx + 0.75 * s, cy + 1.6 * s)], w, 255)
    for k in range(6):
        x = cx - 0.6 * s + k * 0.12 * s
        c.line([(x, cy + 1.2 * s), (x + 0.18 * s, cy + 1.0 * s)], w * 0.5, 255, joint=False)


def pasteup_group(seed=41):
    L = Layer()
    r = rng(seed)
    # --- Paste-up (Papier, angeklebt, eingerissen)
    cx, cy, ang = 205, 250, -0.05
    w, h = 105, 150
    rect_pts = [(cx - w, cy - h), (cx + w, cy - h), (cx + w, cy + h), (cx - w, cy + h)]
    paper = Canvas(C, C)
    paper.poly(rot_pts(rect_pts, cx, cy, ang))
    pm = paper.mask(0.6)
    tear = Canvas(C, C)
    tear.poly(blob_poly(cx + w * 0.95, cy + h * 0.9, 55, 22, 0.45, seed))
    tear.poly(blob_poly(cx - w * 1.0, cy - h * 0.2, 18, 14, 0.5, seed + 1))
    pm = np.clip(pm - tear.mask(0.8), 0, 1)
    glue = np.clip(ndimage.gaussian_filter(pm, 6) - pm * 0.85, 0, 1)
    L.over(np.ones((C, C, 3)) * hexcol("#8f8a7d"), glue * 0.18)
    wr = fbm(C, C, 9, 4, seed + 2)
    cr = Canvas(C, C)
    for k in range(5):
        x0_, y0_ = cx + r.uniform(-w, w), cy - h
        cr.line([(x0_, y0_), (x0_ + r.uniform(-40, 40), cy + h)], r.uniform(1.5, 3.0), 255, joint=False)
    for k in range(3):
        y0_ = cy + r.uniform(-h, h)
        cr.line([(cx - w, y0_), (cx + w, y0_ + r.uniform(-25, 25))], r.uniform(1.5, 2.5), 255, joint=False)
    crease = ndimage.gaussian_filter(cr.mask(), 1.5)
    pc = np.ones((C, C, 3)) * hexcol("#ebe6d8") * (0.94 + 0.06 * wr[..., None]) * (1 - 0.12 * crease[..., None])
    L.over(pc, pm)
    ink = Canvas(C, C)
    _creature(ink, cx, cy - 40, 62, 4.2)
    im = ink.mask(0.4) * pm
    L.over(np.ones((C, C, 3)) * hexcol("#191919"), im * 0.92)
    # --- Sticker
    def sticker(x, y, sw, sh, a, bg, deco, peel=0.0, sd=0):
        c = Canvas(C, C)
        c.poly(rot_pts([(x - sw, y - sh), (x + sw, y - sh), (x + sw, y + sh), (x - sw, y + sh)], x, y, a))
        m = c.mask(0.5)
        if peel:
            pc_ = Canvas(C, C)
            pc_.poly(blob_poly(x + sw * 0.8, y - sh * 0.7, sw * peel, 16, 0.4, sd))
            m = np.clip(m - pc_.mask(0.6), 0, 1)
        L.over(np.ones((C, C, 3)) * hexcol(bg) * (0.95 + 0.05 * wr[..., None]), m)
        deco(x, y, sw, sh, a, m)

    def d_hello(x, y, sw, sh, a, m):
        band = Canvas(C, C)
        band.poly(rot_pts([(x - sw, y - sh), (x + sw, y - sh), (x + sw, y - sh * 0.35), (x - sw, y - sh * 0.35)], x, y, a))
        L.over(np.ones((C, C, 3)) * hexcol("#d42a2f"), band.mask(0.5) * m)
        sc = Canvas(C, C)
        pts = [(x - sw * 0.75 + k * sw * 0.15, y + sh * 0.25 + np.sin(k * 1.7) * sh * 0.25) for k in range(11)]
        sc.line(rot_pts(pts, x, y, a), 2.4, 255)
        L.over(np.ones((C, C, 3)) * hexcol("#151515"), sc.mask(0.3) * m)

    def d_cat(x, y, sw, sh, a, m):
        cc = Canvas(C, C)
        rr_ = sh * 0.55
        cc.ellipse(x, y + sh * 0.1, rr_, rr_ * 0.85)
        cc.poly(rot_pts([(x - rr_, y - rr_ * 0.1), (x - rr_ * 0.85, y - rr_ * 1.05), (x - rr_ * 0.3, y - rr_ * 0.55)], x, y, a))
        cc.poly(rot_pts([(x + rr_, y - rr_ * 0.1), (x + rr_ * 0.85, y - rr_ * 1.05), (x + rr_ * 0.3, y - rr_ * 0.55)], x, y, a))
        L.over(np.ones((C, C, 3)) * hexcol("#151515"), cc.mask(0.4) * m)
        ey = Canvas(C, C)
        for sx in (-1, 1):
            ey.ellipse(x + sx * rr_ * 0.38, y + sh * 0.05, rr_ * 0.14, rr_ * 0.2)
        L.over(np.ones((C, C, 3)) * hexcol("#f2d23c"), ey.mask(0.4) * m)

    def d_star(x, y, sw, sh, a, m):
        st = Canvas(C, C)
        pts = []
        for k in range(10):
            rad = sh * (0.75 if k % 2 == 0 else 0.32)
            t = -np.pi / 2 + k * np.pi / 5
            pts.append((x + np.cos(t) * rad, y + np.sin(t) * rad))
        st.poly(rot_pts(pts, x, y, a))
        L.over(np.ones((C, C, 3)) * hexcol("#f4f4f0"), st.mask(0.4) * m)

    def d_eye(x, y, sw, sh, a, m):
        e = Canvas(C, C)
        e.poly(rot_pts([(x - sw * 0.75, y), (x, y - sh * 0.55), (x + sw * 0.75, y), (x, y + sh * 0.55)], x, y, a))
        L.over(np.ones((C, C, 3)) * hexcol("#f4f4f0"), e.mask(0.4) * m)
        p = Canvas(C, C)
        p.ellipse(x, y, sh * 0.3, sh * 0.3)
        L.over(np.ones((C, C, 3)) * hexcol("#151515"), p.mask(0.4) * m)

    def d_blob(x, y, sw, sh, a, m):
        b = Canvas(C, C)
        for k, ch in enumerate((-0.45, 0.0, 0.45)):
            b.ellipse(x + ch * sw, y + (k % 2) * sh * 0.1, sw * 0.32, sh * 0.48)
        bm = b.mask(0.4) * m
        ol = np.clip(ndimage.gaussian_filter(bm, 1.5) * 3, 0, 1) * m
        L.over(np.ones((C, C, 3)) * hexcol("#151515"), ol)
        L.over(np.ones((C, C, 3)) * hexcol("#e06aa6"), np.clip(bm * 1.4 - 0.4, 0, 1))

    def d_check(x, y, sw, sh, a, m):
        yy, xx = np.mgrid[0:C, 0:C].astype(float)
        ca, sa = np.cos(a), np.sin(a)
        u = (xx - x) * ca + (yy - y) * sa
        v = -(xx - x) * sa + (yy - y) * ca
        chk = ((np.floor(u / 7) + np.floor(v / 7)) % 2 == 0).astype(float)
        L.over(np.ones((C, C, 3)) * hexcol("#151515"), chk * m)

    def d_none(*_):
        pass
    sticker(380, 120, 52, 30, 0.12, "#f4f4f0", d_hello)
    sticker(395, 215, 34, 34, -0.2, "#f2c230", d_cat)
    sticker(350, 300, 30, 22, 0.35, "#2b56b8", d_star)
    sticker(420, 360, 40, 26, -0.08, "#3d9a55", d_eye, peel=0.7, sd=5)
    sticker(300, 400, 48, 24, 0.05, "#dcdcd8", d_blob)
    sticker(120, 430, 26, 26, 0.6, "#f4f4f0", d_check)
    # abgerissene Stickerreste (weisses Papier)
    for k, (x, y) in enumerate(((455, 270), (260, 455), (90, 95))):
        c = Canvas(C, C)
        c.poly(blob_poly(x, y, r.uniform(9, 15), 12, 0.6, 60 + k, 1.4, 0.8))
        L.over(np.ones((C, C, 3)) * hexcol("#e9e7e0"), c.mask(0.5) * 0.9)
    return L


# =================================================================== Kritzel- und Tropfflaeche
def scribbles(seed=51):
    L = Layer()
    r = rng(seed)
    # Spruehnebel-Wolke
    mist = np.clip(fbm(C, C, 4, 4, seed) - 0.45, 0, 1) * 1.5
    yy, xx = np.mgrid[0:C, 0:C].astype(float)
    env = np.clip(1 - np.hypot((xx - 256) / 220, (yy - 230) / 150), 0, 1)
    L.over(np.ones((C, C, 3)) * hexcol("#6c6f78"), mist * env * 0.22)
    # Spruehlinie mit langen Laeufern (rot) oben
    line = [[(70, 140), (160, 128), (260, 145), (360, 126), (450, 138)]]
    a, m = spray(line, 13, seed, wvar=0.2)
    d = drips(m, 14, seed + 1, maxlen=150, width=3.0, minlen=0.3)
    L.over(colvar("#b8262e", seed, 0.05), np.clip(a + d, 0, 1))
    # Silberne Krakel mit Laeufern
    for k in range(2):
        pts = []
        x0, y0 = r.uniform(80, 140), r.uniform(230, 300)
        for i in range(16):
            pts.append((x0 + i * r.uniform(12, 20), y0 + np.sin(i * 1.3 + k) * r.uniform(12, 30)))
        a, m = spray([pts], 6.5, seed + 10 + k, wvar=0.35)
        d = drips(m, 5, seed + 20 + k, maxlen=60, width=2.0)
        L.over(colvar("#cfd2d4", seed + k, 0.05), np.clip(a + d, 0, 1))
    # Marker-Kritzel (schwarz/blau), unleserliche Kurzschrift
    # feste, geprüfte Fantasie-Kuerzel (keine Zufallsbuchstaben -> keine ungewollten Abkuerzungen)
    words = ["VEKU", "RUME", "ZUNK", "NEKU", "KRUV", "ZEMU", "VURM", "EMKU", "MUREK"]
    for k in range(9):
        letters = words[k]
        groups = word_strokes(letters, seed + 100 + k, slant=0.35, jitter=0.08, gap=0.05)
        cx, cy = r.uniform(110, 400), r.uniform(190, 420)
        wpx = r.uniform(80, 150)
        groups, _, _ = fit(groups, (cx - wpx / 2, cy - wpx * 0.2, cx + wpx / 2, cy + wpx * 0.2))
        mk = Canvas(C, C)
        for g in groups:
            for s in g:
                mk.line(chaikin(s, 2), r.uniform(1.6, 2.6), 255)
        col = ["#141414", "#1d2f7a", "#141414", "#3a3a3a"][k % 4]
        L.over(np.ones((C, C, 3)) * hexcol(col), mk.mask(0.3) * r.uniform(0.75, 0.95))
    # kleine Symbole: Pfeil, Krone, Herz-Umriss, Punkte
    sy = Canvas(C, C)
    sy.line([(400, 250), (450, 228)], 2.2, 255)
    sy.line([(436, 222), (452, 227), (444, 242)], 2.2, 255)
    sy.line([(90, 380), (98, 360), (110, 375), (122, 356), (130, 380), (90, 380)], 2.0, 255)
    pts = []
    for t in np.linspace(0, 2 * np.pi, 30):
        x = 16 * np.sin(t) ** 3
        y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
        pts.append((330 + x * 1.3, 420 - y * 1.3))
    sy.line(pts, 1.8, 255)
    for k in range(7):
        sy.ellipse(160 + k * 14, 440 + np.sin(k) * 4, 2.2, 2.2)
    L.over(np.ones((C, C, 3)) * hexcol("#141414"), sy.mask(0.3) * 0.9)
    return L


CELLS = [
    ("tag_a", "tag", "Tag, schwarz, schnell mit Unterschwung", lambda: tag("KOZE", "#151515", 11, 11.0,
                                                                          slant=0.3, flourish="swoosh", ndrip=6), 1.2),
    ("tag_b", "tag", "Tag, silber, schmale hohe Buchstaben mit Pfeil", lambda: tag("VURN", "#cfd2d4", 12, 9.0,
                                                                                  slant=0.18, squeeze=0.72,
                                                                                  flourish="arrow", ndrip=4,
                                                                                  box=(INNER + 16, 125, C - INNER - 16, 385)), 1.1),
    ("tag_c", "tag", "Tag, blau, breit und huepfend mit Sternchen", lambda: tag("MIQS", "#2a52c4", 13, 8.0,
                                                                               slant=0.4, squeeze=1.15,
                                                                               flourish="star", ndrip=3,
                                                                               jitter=0.05), 1.0),
    ("throwup_a", "throwup", "Throw-up, Silber mit schwarzer Kontur", lambda: throwup("OBU", "#cdd0d2", "#141414",
                                                                                     21, shine=False), 1.8),
    ("throwup_b", "throwup", "Throw-up, Pink mit schwarzer Kontur", lambda: throwup("REZ", "#e2579b", "#141414",
                                                                                   22, slant=0.18), 1.7),
    ("stencil", "stencil", "Schablone: Vogel auf Ast (schwarz) + kleines Herz (rot)", stencil, 0.6),
    ("pasteup_stickers", "pasteup", "Paste-up (Comicfigur auf Papier) + Stickergruppe", pasteup_group, 0.8),
    ("scribbles_drips", "scribble", "Kritzel, Marker, Spruehnebel und Laeufer", scribbles, 1.6),
]


def main():
    W, H = 4 * C, 2 * C
    rgb = np.zeros((H, W, 3))
    a = np.zeros((H, W))
    meta = []
    for k, (name, kind, label, fn, size) in enumerate(CELLS):
        col, row = k % 4, k // 4
        c_rgb, c_a = fn().result()
        rgb[row * C:(row + 1) * C, col * C:(col + 1) * C] = c_rgb
        a[row * C:(row + 1) * C, col * C:(col + 1) * C] = c_a
        ys, xs = np.nonzero(c_a > 0.02)
        meta.append({"index": k, "col": col, "row": row, "name": name, "type": kind, "label": label,
                     "uv_rect": [col / 4, row / 2, (col + 1) / 4, (row + 1) / 2],
                     "size_m": size,
                     "content_px": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]})
        print("cell", k, name)
    to_img(rgb, a).save(os.path.join(OUTD, "graffiti.png"), optimize=True)
    info = {"atlas": "graffiti.png", "grid": [4, 2], "cell_px": C, "size_px": [W, H],
            "uv_convention": "uv_rect = [u0, v0, u1, v1], Ursprung oben links (Godot-UV), v nach unten",
            "orientation": "waagerecht, Bildoberkante = oben an der Wand; je Zelle >= 20 px transparenter Rand",
            "size_m": "empfohlene Kantenlaenge einer Zelle an der Wand in Metern (Inhalt ist kleiner, "
                      "siehe content_px = [x0, y0, x1, y1] innerhalb der Zelle)",
            "zone": "Erdgeschoss ca. 0.3 - 2.4 m; Zellmitte sinnvoll bei 0.9 - 1.5 m",
            "content": "frei erfundene Buchstabenfolgen/Motive, keine echten Namen, Marken oder politischen Symbole",
            "cells": meta}
    with open(os.path.join(OUTD, "graffiti.json"), "w") as fh:
        json.dump(info, fh, indent=2, ensure_ascii=False)
    tmp = os.path.join(HERE, "furniture_tmp")
    os.makedirs(tmp, exist_ok=True)
    bg = np.ones((H, W, 3)) * hexcol("#c9bfae")
    comp = rgb * a[..., None] + bg * (1 - a[..., None])
    to_img(comp).save(os.path.join(tmp, "graffiti_preview.png"))


if __name__ == "__main__":
    main()
