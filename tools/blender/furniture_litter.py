"""Litter-Decal-Atlas fuer Strassenboeden (Draufsicht, RGBA mit weichem Alpha).

Aufruf (Projektordner): .venv/bin/python tools/blender/furniture_litter.py
Ausgabe: godot/assets/textures/street/litter.png (2048 px, 4 x 4 Zellen a 512 px)
         godot/assets/textures/street/litter.json (Zelle -> Name, UV-Rechteck, empfohlene Groesse)
Alles prozedural erzeugt (keine Fremdbilder, keine Marken/Schrift).
"""
import json
import os
import numpy as np
from scipy import ndimage
from furniture_texutil import (fbm, hexcol, Canvas, rng, blob_poly, rot_pts, value_noise, to_img)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUTD = os.path.join(ROOT, "godot", "assets", "textures", "street")
os.makedirs(OUTD, exist_ok=True)
C = 512           # Zellgroesse
PAD = 20          # Randabstand (Mipmaps)
LIGHT = np.array([-0.6, -0.8])  # Licht von links oben (Bild-x, Bild-y)


class Layer:
    """Vormultiplizierte RGBA-Akkumulation einer Zelle."""

    def __init__(self):
        self.rgb = np.zeros((C, C, 3))
        self.a = np.zeros((C, C))

    def over(self, col, alpha):
        alpha = np.clip(alpha, 0, 1)
        col = np.asarray(col, dtype=float)
        if col.ndim == 1:
            col = np.ones((C, C, 3)) * col
        self.rgb = col * alpha[..., None] + self.rgb * (1 - alpha[..., None])
        self.a = alpha + self.a * (1 - alpha)

    def shadow(self, mask, strength=0.35, off=(3, 4), soft=3.0):
        sh = ndimage.shift(ndimage.gaussian_filter(mask, soft), (off[1], off[0]), order=1, mode="constant")
        self.over(np.zeros(3), sh * strength)

    def result(self):
        a = self.a.copy()
        y, x = np.mgrid[0:C, 0:C]
        d = np.minimum(np.minimum(x, C - 1 - x), np.minimum(y, C - 1 - y)).astype(float)
        edge = np.clip((d - 4) / (PAD - 4), 0, 1)
        edge = edge * edge * (3 - 2 * edge)
        a *= edge
        rgb = np.where(self.a[..., None] > 1e-4, self.rgb / np.maximum(self.a[..., None], 1e-4), 0)
        # Farbe in transparente Bereiche ausbluten lassen (keine dunklen Raender bei Filterung)
        w = ndimage.gaussian_filter(self.a, 12) + 1e-6
        bleed = np.stack([ndimage.gaussian_filter(rgb[..., i] * self.a, 12) / w for i in range(3)], -1)
        mean = (rgb * self.a[..., None]).sum((0, 1)) / max(self.a.sum(), 1e-6)
        bleed = np.where(w[..., None] > 1e-3, bleed, mean)
        k = np.clip(self.a * 4, 0, 1)[..., None]
        rgb = rgb * k + bleed * (1 - k)
        return np.clip(rgb, 0, 1), np.clip(a, 0, 1)


def shade(mask, strength=0.6, soft=2.0):
    """Einfache Reliefschattierung aus einer Hoehenmaske (1 = neutral)."""
    h = ndimage.gaussian_filter(mask, soft)
    gy, gx = np.gradient(h)
    s = -(gx * LIGHT[0] + gy * LIGHT[1]) * strength * 6
    return np.clip(1 + s, 0.55, 1.45)


def tint(base, mask_shade, var=None, amount=0.12):
    out = np.ones((C, C, 3)) * hexcol(base) if isinstance(base, str) else base
    out = out * mask_shade[..., None]
    if var is not None:
        out = out * (1 - amount + 2 * amount * var[..., None])
    return out


def jag(pts, r, amt, seed):
    """Polygon mit ausgefransten Kanten (Kanten unterteilen + Zufallsversatz)."""
    rr = rng(seed)
    out = []
    for i in range(len(pts)):
        a = np.array(pts[i])
        b = np.array(pts[(i + 1) % len(pts)])
        L = np.linalg.norm(b - a)
        n = max(2, int(L / 4))
        nrm = np.array([-(b - a)[1], (b - a)[0]]) / max(L, 1e-6)
        for k in range(n):
            t = k / n
            p = a + (b - a) * t + nrm * rr.normal(0, amt)
            out.append(tuple(p))
    return out


# =================================================================== Zellen
def paper_scraps(seed=1):
    L = Layer()
    r = rng(seed)
    var = fbm(C, C, 20, 3, seed)
    for i in range(7):
        cx, cy = r.uniform(110, 400), r.uniform(110, 400)
        w, h = r.uniform(40, 110), r.uniform(30, 80)
        ang = r.uniform(0, np.pi)
        pts = [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2 + r.uniform(-8, 8)),
               (cx + w / 2 + r.uniform(-10, 10), cy + h / 2), (cx - w / 2, cy + h / 2)]
        pts = rot_pts(jag(pts, 1, 1.6, seed + i), cx, cy, ang)
        c = Canvas(C, C)
        c.poly(pts)
        m = c.mask(0.6)
        L.shadow(m, 0.28, (2, 3), 2.5)
        col = ["#f3f1ea", "#e9e6dc", "#f6f4ee", "#dcd9cf"][i % 4]
        base = tint(col, shade(m, 0.3), var, 0.05)
        # Knick: eine Haelfte etwas dunkler
        fold = Canvas(C, C)
        fold.poly(rot_pts([(cx, cy - h), (cx + w, cy - h), (cx + w, cy + h), (cx, cy + h)], cx, cy,
                          ang + r.uniform(-0.6, 0.6)))
        base = base * (1 - 0.08 * fold.mask(1.0)[..., None])
        # Druckzeilen auf einigen Fetzen
        if i % 2 == 0:
            tl = Canvas(C, C)
            for k in range(4):
                yy = cy - h * 0.3 + k * h * 0.17
                tl.line(rot_pts([(cx - w * 0.38, yy), (cx + w * r.uniform(0.0, 0.35), yy)], cx, cy, ang), 2.2,
                        255, joint=False)
            base = base * (1 - 0.45 * (tl.mask() * m)[..., None])
        L.over(base, m * 0.97)
    return L


def crumpled_cup(seed=2):
    L = Layer()
    r = rng(seed)
    cx, cy, ang = 256, 262, 0.45
    pts = [(cx - 105, cy - 42), (cx + 105, cy - 58), (cx + 105, cy + 58), (cx - 105, cy + 42)]
    pts = rot_pts(jag(pts, 1, 3.5, seed), cx, cy, ang)
    c = Canvas(C, C)
    c.poly(pts)
    m = c.mask(0.8)
    L.shadow(m, 0.45, (5, 7), 5)
    # Knautschfacetten
    fac = np.zeros((C, C))
    for k in range(40):
        fc = Canvas(C, C)
        px, py = cx + r.uniform(-110, 110), cy + r.uniform(-60, 60)
        fc.poly(rot_pts(blob_poly(px, py, r.uniform(12, 30), 6, 0.5, k), cx, cy, ang))
        fac += fc.mask() * r.uniform(-0.18, 0.18)
    base = tint("#ece6da", shade(m, 0.6, 4), None)
    base = base * np.clip(1 + fac, 0.6, 1.3)[..., None]
    # Pappmanschette
    band = Canvas(C, C)
    band.poly(rot_pts([(cx - 30, cy - 70), (cx + 30, cy - 70), (cx + 30, cy + 70), (cx - 30, cy + 70)], cx, cy, ang))
    base = np.where((band.mask() * m)[..., None] > 0.5, base * hexcol("#a06e45") / hexcol("#ece6da"), base)
    # Deckel (dunkler Kunststoff) am weiten Ende
    lid = Canvas(C, C)
    lid.poly(rot_pts([(cx + 96, cy - 64), (cx + 122, cy - 62), (cx + 122, cy + 62), (cx + 96, cy + 64)], cx, cy, ang))
    lm = lid.mask(0.8)
    L.over(base, m)
    L.over(tint("#2a2a2a", shade(lm, 0.8, 2)), lm)
    # Kaffeerest-Fleck
    st = Canvas(C, C)
    st.poly(blob_poly(cx + 150, cy + 90, 40, 26, 0.4, seed + 9, 1.3, 0.8))
    sm = st.mask(4)
    L.over(hexcol("#3b2617"), sm * 0.35 * (1 - m))
    return L


def can(seed=3):
    L = Layer()
    cx, cy, ang = 256, 256, -0.35
    w, h = 118, 66
    c = Canvas(C, C)
    pts = [(cx - w, cy - h), (cx + w, cy - h), (cx + w, cy + h), (cx - w, cy + h)]
    pts = rot_pts(jag(pts, 1, 2.5, seed), cx, cy, ang)
    c.poly(pts)
    m = c.mask(0.7)
    L.shadow(m, 0.45, (5, 7), 4)
    # Zylinderschattierung quer zur Achse
    y, x = np.mgrid[0:C, 0:C].astype(float)
    ca, sa = np.cos(ang), np.sin(ang)
    u = (x - cx) * ca + (y - cy) * sa
    v = -(x - cx) * sa + (y - cy) * ca
    cylsh = 0.55 + 0.6 * np.cos(np.clip(v / h, -1, 1) * 1.35 - 0.35) ** 2
    dent = 1 + 0.25 * (fbm(C, C, 10, 3, seed) - 0.5)
    body = np.ones((C, C, 3)) * hexcol("#b3242c")
    stripe = (np.abs(v) < h * 0.22)
    body = np.where(stripe[..., None], hexcol("#e8e8e8"), body)
    ends = np.abs(u) > w - 16
    body = np.where(ends[..., None], hexcol("#c9ccce"), body)
    body = body * (cylsh * dent)[..., None]
    hl = np.exp(-((v + h * 0.35) / (h * 0.12)) ** 2) * 0.5
    body = np.clip(body + hl[..., None], 0, 1)
    L.over(body, m)
    # Deckel mit Lasche
    lid = Canvas(C, C)
    lid.ellipse(*rot_pts([(cx + w + 4, cy)], cx, cy, ang)[0], 9, 9)
    return L


def _butt(c_filter, c_paper, cx, cy, ang, L, r, scale=1.0):
    fl, fw = 30 * scale, 11 * scale
    pl = r.uniform(6, 22) * scale
    f = Canvas(C, C)
    f.poly(rot_pts([(cx - fl, cy - fw / 2), (cx, cy - fw / 2), (cx, cy + fw / 2), (cx - fl, cy + fw / 2)],
                   cx, cy, ang))
    p = Canvas(C, C)
    p.poly(rot_pts([(cx, cy - fw / 2.2), (cx + pl, cy - fw / 2.4), (cx + pl, cy + fw / 2.4),
                    (cx, cy + fw / 2.2)], cx, cy, ang))
    t = Canvas(C, C)
    t.poly(rot_pts([(cx + pl - 3 * scale, cy - fw / 2.4), (cx + pl + 1, cy - fw / 3),
                    (cx + pl + 1, cy + fw / 3), (cx + pl - 3 * scale, cy + fw / 2.4)], cx, cy, ang))
    fm, pm, tm = f.mask(0.5), p.mask(0.5), t.mask(0.6)
    allm = np.clip(fm + pm, 0, 1)
    L.shadow(allm, 0.35, (2, 3), 1.5)
    sh = shade(allm, 0.5, 1.5)
    speck = fbm(C, C, 90, 2, int(cx * 7 + cy))
    L.over(tint(c_filter, sh, speck, 0.15), fm)
    L.over(tint(c_paper, sh), pm)
    L.over(tint("#2b2522", sh), tm)


def cigarette_butts(seed=4):
    L = Layer()
    r = rng(seed)
    for i in range(9):
        cx, cy = r.uniform(110, 400), r.uniform(110, 400)
        filt = ["#c98a4a", "#d29a5c", "#efeae0", "#c98a4a"][i % 4]
        paper = ["#efece4", "#e6e2d8"][i % 2]
        _butt(filt, paper, cx, cy, r.uniform(0, 2 * np.pi), L, r, 1.4)
    return L


def gum_stains(seed=5):
    L = Layer()
    r = rng(seed)
    for i in range(46):
        rad = r.uniform(5, 16) * (1.4 if r.random() < 0.15 else 1.0)
        ang = r.uniform(0, 2 * np.pi)
        dist = abs(r.normal(0, 95))
        cx, cy = 256 + np.cos(ang) * dist, 256 + np.sin(ang) * dist
        if not (PAD + 20 < cx < C - PAD - 20 and PAD + 20 < cy < C - PAD - 20):
            continue
        c = Canvas(C, C)
        c.poly(blob_poly(cx, cy, rad, 18, 0.25, i))
        m = c.mask(1.0)
        col = ["#3d3c39", "#5f5e5a", "#7d7c77", "#2c2b29", "#908e88"][i % 5]
        rim = np.clip(m - ndimage.gaussian_filter(m, 2.0), 0, 1) * 2
        base = tint(col, 1 + 0.2 * rim)
        L.over(base, m * r.uniform(0.55, 0.9))
    return L


def _leaf_poly(kind, cx, cy, s, ang, r):
    """Blattumriss (Spitze oben, Stiel unten), Ursprung = Blattmitte."""
    pts = []
    if kind == "heart":   # Linde: herzfoermiger Grund, Spitze oben, fein gesaegt
        asym = r.uniform(0.85, 1.1)
        sx, sy = 0.75 * s / 16, 1.6 * s / 22
        for t in np.linspace(0, 2 * np.pi, 48, endpoint=False):
            x = 16 * np.sin(t) ** 3
            y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
            ser = 1 + 0.03 * np.sin(34 * t)
            x *= (asym if x > 0 else 1.0)
            pts.append((cx + x * sx * ser, cy + 0.6 * s - (5 - y) * sy * ser))
    else:                  # Ahorn/Platane: 5 Lappen nach oben/seitlich, Stielbucht unten
        for t in np.linspace(0, 2 * np.pi, 70, endpoint=False):
            k = 0.5 + 0.5 * np.abs(np.cos(2.5 * (t + np.pi / 2))) ** 0.6
            k *= 1 + 0.035 * np.sin(26 * t)
            if abs(((t - np.pi / 2 + np.pi) % (2 * np.pi)) - np.pi) < 0.3:
                k *= 0.8
            pts.append((cx + np.cos(t) * s * k, cy + np.sin(t) * s * k * 0.95))
    return rot_pts(pts, cx, cy, ang)


def leaves(seed, kind, palette, n, size):
    L = Layer()
    r = rng(seed)
    var = fbm(C, C, 14, 3, seed)
    for i in range(n):
        ang = r.uniform(0, 2 * np.pi)
        dist = abs(r.normal(0, 105))
        cx, cy = 256 + np.cos(ang) * dist, 256 + np.sin(ang) * dist
        cx, cy = np.clip(cx, 70, 442), np.clip(cy, 70, 442)
        s = r.uniform(*size)
        rot = r.uniform(0, 2 * np.pi)
        c = Canvas(C, C)
        c.poly(_leaf_poly(kind, cx, cy, s, rot, r))
        m = c.mask(0.6)
        col = hexcol(palette[r.integers(len(palette))])
        curl = shade(m, 0.4, 4.0)
        base = col * curl[..., None] * (0.88 + 0.24 * var[..., None])
        vein = Canvas(C, C)
        stemc = Canvas(C, C)
        R = lambda x, y: rot_pts([(x, y)], cx, cy, rot)[0]  # noqa: E731
        if kind == "heart":
            bp = R(cx, cy + 0.6 * s)
            vein.line([R(cx, cy - 0.95 * s), bp], 1.4, 255, joint=False)
            for f in (-0.35, 0.05, 0.42):
                for sg in (-1, 1):
                    vein.line([R(cx, cy + f * s), R(cx + sg * 0.5 * s, cy + f * s - 0.38 * s)], 0.9, 255,
                              joint=False)
            stemc.line([bp, R(cx + 0.05 * s, cy + 1.45 * s)], 1.8, 255, joint=False)
        else:
            bp = R(cx, cy + 0.38 * s)
            for a in (-90, -18, -162, 54, 126):
                aa = np.radians(a)
                vein.line([bp, R(cx + np.cos(aa) * 0.85 * s, cy + np.sin(aa) * 0.85 * s)], 1.1, 255, joint=False)
            stemc.line([bp, R(cx, cy + 1.35 * s)], 1.9, 255, joint=False)
        stem_only = stemc.mask() * (1 - m)
        L.shadow(np.clip(m + stem_only, 0, 1), 0.3, (3, 4), 2.5)
        vm = vein.mask()
        base = base * (1 - 0.22 * (vm * m)[..., None])
        base = np.where((stem_only > 0.05)[..., None], col * 0.7, base)
        # braune Flecken / Raender
        sp = np.clip((fbm(C, C, 30, 3, seed + i) - 0.72) * 4, 0, 1)
        edge = np.clip(m - ndimage.gaussian_filter(m, 2.5), 0, 1) * 2
        base = base * (1 - 0.3 * sp[..., None]) * (1 - 0.25 * edge[..., None])
        L.over(base, np.clip(m * 0.98 + stem_only * 0.9, 0, 1))
    return L


def caps_glass(seed=8):
    L = Layer()
    r = rng(seed)
    # Kronkorken
    for i, col in enumerate(["#c9a13a", "#c2c5c8", "#b0242a", "#2e6b3a", "#c9a13a"]):
        cx, cy = r.uniform(110, 400), r.uniform(110, 400)
        R = 15.5
        c = Canvas(C, C)
        pts = []
        sq = r.uniform(0.75, 1.0)
        for t in np.linspace(0, 2 * np.pi, 63, endpoint=False):
            k = 1.0 + 0.09 * np.cos(21 * t)
            pts.append((cx + np.cos(t) * R * k, cy + np.sin(t) * R * k * sq))
        c.poly(rot_pts(pts, cx, cy, r.uniform(0, np.pi)))
        m = c.mask(0.5)
        L.shadow(m, 0.4, (2, 3), 1.5)
        inner = Canvas(C, C)
        inner.ellipse(cx, cy, R * 0.72, R * 0.72 * sq)
        im = inner.mask(1.0)
        base = tint(col, shade(m, 1.0, 1.0) * (1 - 0.12 * im))
        L.over(base, m)
    # Glasscherben
    for i in range(16):
        cx, cy = 256 + r.normal(0, 85), 256 + r.normal(0, 85)
        cx, cy = np.clip(cx, 60, 452), np.clip(cy, 60, 452)
        s = r.uniform(7, 22)
        n = r.integers(3, 6)
        pts = []
        a0 = r.uniform(0, 2 * np.pi)
        for k in range(n):
            a = a0 + 2 * np.pi * k / n + r.uniform(-0.4, 0.4)
            pts.append((cx + np.cos(a) * s * r.uniform(0.5, 1.3), cy + np.sin(a) * s * r.uniform(0.5, 1.3)))
        c = Canvas(C, C)
        c.poly(pts)
        m = c.mask(0.4)
        col = ["#3f7a3a", "#6b4422", "#c9d6d2", "#3f7a3a"][i % 4]
        edge = np.clip(m - ndimage.gaussian_filter(m, 1.2), 0, 1) * 2.5
        base = tint(col, np.ones((C, C)) * 1.0)
        base = np.clip(base + edge[..., None] * 0.6, 0, 1)
        spec = Canvas(C, C)
        spec.line([pts[0], pts[1]], 1.2, 255, joint=False)
        base = np.clip(base + (spec.mask() * m)[..., None] * 0.7, 0, 1)
        L.over(base, m * np.clip(0.55 + edge * 0.4, 0, 1))
    return L


def wet_patch(seed=9):
    L = Layer()
    y, x = np.mgrid[0:C, 0:C].astype(float)
    d = np.hypot((x - 256) / 200, (y - 256) / 170)
    n = fbm(C, C, 5, 5, seed)
    f = np.clip((1.0 - d) * 1.4 + (n - 0.5) * 1.1, 0, 1)
    a = np.clip((f - 0.25) * 3.0, 0, 1)
    a = ndimage.gaussian_filter(a, 4)
    core = np.clip((f - 0.55) * 3, 0, 1)
    col = np.ones((C, C, 3)) * hexcol("#14181b")
    L.over(col, a * (0.38 + 0.22 * core))
    return L


def oil_stain(seed=10):
    L = Layer()
    r = rng(seed)
    y, x = np.mgrid[0:C, 0:C].astype(float)
    n = fbm(C, C, 6, 5, seed)
    acc = np.zeros((C, C))
    for i, (ox, oy, rad) in enumerate([(0, 0, 150), (-90, 70, 60), (110, -60, 45), (60, 120, 30),
                                       (-140, -90, 22), (150, 90, 16)]):
        d = np.hypot(x - 256 - ox, y - 256 - oy) / rad
        acc = np.maximum(acc, np.clip(1.0 - d + (n - 0.5) * 0.5, 0, 1))
    halo = np.clip(acc * 3, 0, 1)
    halo = ndimage.gaussian_filter(halo, 3)
    core = np.clip((acc - 0.25) * 2.5, 0, 1)
    col = np.ones((C, C, 3)) * hexcol("#1a1714")
    # leicht schillernder Rand
    irid = np.stack([0.5 + 0.5 * np.sin(acc * 40 + k * 2.1) for k in range(3)], -1)
    ring = np.clip(halo - core, 0, 1)
    col = col + irid * ring[..., None] * 0.10
    L.over(col, halo * 0.35 + core * 0.4)
    return L


def sand_grit(seed=11):
    L = Layer()
    r = rng(seed)
    y, x = np.mgrid[0:C, 0:C].astype(float)
    d = np.hypot((x - 256) / 210, (y - 256) / 180)
    n = fbm(C, C, 6, 4, seed)
    dens = np.clip((1 - d) * 1.5 + (n - 0.5) * 0.9, 0, 1)
    # Sandschleier
    L.over(np.ones((C, C, 3)) * hexcol("#b19c78"), ndimage.gaussian_filter(dens, 3) * 0.35)
    # Koerner
    grain = r.random((C, C)) < (dens * 0.20)
    gcol = r.random((C, C))
    gm = ndimage.gaussian_filter(grain.astype(float), 0.6) * 2.5
    cols = np.where(gcol[..., None] < 0.4, hexcol("#c6b28a"),
                    np.where(gcol[..., None] < 0.75, hexcol("#8f8578"), hexcol("#e3ddd0")))
    L.over(cols, np.clip(gm, 0, 1) * 0.9)
    # Splittsteine
    for i in range(70):
        cx, cy = 256 + r.normal(0, 110), 256 + r.normal(0, 95)
        if not (50 < cx < 462 and 50 < cy < 462):
            continue
        c = Canvas(C, C)
        c.poly(blob_poly(cx, cy, r.uniform(3, 8), 7, 0.4, i))
        m = c.mask(0.5)
        L.shadow(m, 0.35, (1, 2), 1.0)
        col = ["#77736d", "#9a958c", "#5e5b57", "#b0aa9e"][i % 4]
        L.over(tint(col, shade(m, 1.0, 1.0)), m)
    return L


def flyer(seed=12):
    L = Layer()
    r = rng(seed)
    cx, cy, ang = 256, 256, 0.28
    w, h = 95, 135
    pts = [(cx - w, cy - h), (cx + w, cy - h), (cx + w, cy + h), (cx - w, cy + h)]
    c = Canvas(C, C)
    c.poly(rot_pts(pts, cx, cy, ang))
    m = c.mask(0.6)
    L.shadow(m, 0.3, (3, 4), 3)
    y, x = np.mgrid[0:C, 0:C].astype(float)
    ca, sa = np.cos(ang), np.sin(ang)
    u = (x - cx) * ca + (y - cy) * sa
    v = -(x - cx) * sa + (y - cy) * ca
    base = np.ones((C, C, 3)) * hexcol("#f2f0ea")
    head = (v < -h + 55)
    base = np.where(head[..., None], hexcol("#d0482f"), base)
    img = (v > -h + 70) & (v < -h + 150) & (np.abs(u) < w - 18)
    grad = np.clip((u + w) / (2 * w), 0, 1)
    imc = hexcol("#3a6f9a") * (1 - grad[..., None]) + hexcol("#e3b44a") * grad[..., None]
    base = np.where(img[..., None], imc, base)
    lines = np.zeros((C, C), bool)
    for k in range(7):
        yy = -h + 168 + k * 14
        ll = w - 18 - (r.uniform(0, 60) if k % 3 == 2 else 0)
        lines |= (np.abs(v - yy) < 2.2) & (u > -w + 18) & (u < ll)
    base = np.where(lines[..., None], hexcol("#55575a"), base)
    # Knick quer + Schmutzabdruck (Schuhsohle angedeutet)
    crease = np.exp(-(v / 2.0) ** 2) * 0.18
    side = np.where(v > 0, 0.95, 1.0)
    base = base * (side - crease)[..., None]
    sole = np.exp(-(((u - 30) / 55) ** 2 + ((v - 60) / 95) ** 2) * 2.0)
    tread = 0.5 + 0.5 * np.sign(np.sin(v / 4.0))
    base = base * (1 - (sole * tread * 0.35 * fbm(C, C, 20, 3, seed))[..., None])
    base = base * (0.92 + 0.1 * fbm(C, C, 8, 4, seed + 1))[..., None]
    L.over(base, m)
    return L


def plastic_bag(seed=13):
    L = Layer()
    r = rng(seed)
    cx, cy = 256, 262
    c = Canvas(C, C)
    c.poly(blob_poly(cx, cy, 135, 40, 0.28, seed, 1.15, 0.85))
    m = c.mask(1.0)
    # Henkel: zwei flachgedrueckte Schlaufen an der Oberkante
    hd = Canvas(C, C)
    hole = Canvas(C, C)
    for sgn in (-1, 1):
        hx, hy = cx + sgn * 48, cy - 112
        hd.ellipse(hx, hy, 30, 24)
        hole.ellipse(hx, hy - 4, 17, 12)
    hm = np.clip(hd.mask(0.8) - hole.mask(0.8), 0, 1) * (1 - m)
    allm = np.clip(m + hm, 0, 1)
    L.shadow(allm, 0.25, (4, 6), 6)
    folds = np.zeros((C, C))
    for k in range(18):
        fc = Canvas(C, C)
        a = r.uniform(0, np.pi)
        p0 = (cx + r.normal(0, 60), cy + r.normal(0, 45))
        p1 = (p0[0] + np.cos(a) * r.uniform(40, 110), p0[1] + np.sin(a) * r.uniform(40, 110))
        fc.line([p0, p1], r.uniform(8, 16), 255)
        folds += fc.mask(6.0) * r.choice([-1, 1]) * 0.18
    sh = shade(allm + folds * 0.8, 0.9, 5) * np.clip(1 + folds, 0.75, 1.25)
    base = tint("#e4e9ec", sh, fbm(C, C, 10, 3, seed), 0.05)
    stripe = Canvas(C, C)
    sp = [(cx - 150 + k * 15, cy + 28 + 7 * np.sin(k * 0.9) + r.normal(0, 2)) for k in range(21)]
    stripe.line(rot_pts(sp, cx, cy, 0.12), 9, 255)
    base = np.where((stripe.mask() * m)[..., None] > 0.5, base * hexcol("#5b86c4") / hexcol("#e4e9ec"), base)
    spec = np.clip((sh - 1.15) * 3, 0, 1)
    base = np.clip(base + spec[..., None] * 0.3, 0, 1)
    L.over(base, allm * (0.78 + 0.15 * np.clip(folds + 0.5, 0, 1)))
    return L


def butts_ash(seed=14):
    L = Layer()
    r = rng(seed)
    y, x = np.mgrid[0:C, 0:C].astype(float)
    d = np.hypot((x - 256) / 150, (y - 256) / 120)
    n = fbm(C, C, 10, 5, seed)
    ash = np.clip((1 - d) * 1.6 + (n - 0.5) * 1.2, 0, 1)
    ash = ndimage.gaussian_filter(ash, 2)
    fine = fbm(C, C, 60, 3, seed + 3)
    acol = hexcol("#6f6d69") * (0.75 + 0.5 * fine[..., None])
    L.over(acol, ash * 0.75)
    specks = (r.random((C, C)) < ash * 0.03)
    L.over(np.ones((C, C, 3)) * hexcol("#1e1c1a"), ndimage.gaussian_filter(specks.astype(float), 0.7) * 2.0)
    for i in range(11):
        a = r.uniform(0, 2 * np.pi)
        dd = abs(r.normal(0, 70))
        filt = ["#c98a4a", "#d29a5c", "#efeae0"][i % 3]
        _butt(filt, "#e8e4da", 256 + np.cos(a) * dd, 256 + np.sin(a) * dd, r.uniform(0, 2 * np.pi), L, r, 1.2)
    return L


def dirt_crumbs(seed=15):
    """Erdkruemel/Schmutzspritzer (bewusst KEIN Hundekot)."""
    L = Layer()
    r = rng(seed)
    y, x = np.mgrid[0:C, 0:C].astype(float)
    d = np.hypot((x - 256) / 190, (y - 256) / 150)
    n = fbm(C, C, 7, 5, seed)
    f = np.clip((1 - d) * 1.3 + (n - 0.5) * 1.3, 0, 1)
    smear = np.clip((f - 0.3) * 2.5, 0, 1)
    L.over(np.ones((C, C, 3)) * hexcol("#5a4632"), ndimage.gaussian_filter(smear, 3) * 0.45)
    for i in range(120):
        cx, cy = 256 + r.normal(0, 90), 256 + r.normal(0, 70)
        if not (40 < cx < 472 and 40 < cy < 472):
            continue
        c = Canvas(C, C)
        c.poly(blob_poly(cx, cy, r.uniform(1.5, 6), 7, 0.45, i))
        m = c.mask(0.5)
        col = ["#4a3826", "#6b543b", "#3a2c1f", "#7d7466"][i % 4]
        L.over(tint(col, shade(m, 1.0, 0.8)), m * 0.95)
    return L


def petals(seed=16):
    L = Layer()
    r = rng(seed)
    for i in range(140):
        cx, cy = 256 + r.normal(0, 105), 256 + r.normal(0, 90)
        if not (40 < cx < 472 and 40 < cy < 472):
            continue
        s = r.uniform(6, 11)
        ang = r.uniform(0, 2 * np.pi)
        pts = []
        for t in np.linspace(0, 2 * np.pi, 16, endpoint=False):
            k = 1 - 0.25 * np.cos(t) - (0.25 if abs(t) < 0.3 or abs(t - 2 * np.pi) < 0.3 else 0)
            pts.append((cx + np.cos(t) * s * k, cy + np.sin(t) * s * 0.62))
        c = Canvas(C, C)
        c.poly(rot_pts(pts, cx, cy, ang))
        m = c.mask(0.5)
        col = ["#f4c9d6", "#f7dde5", "#fbf2f4", "#e8a9bd", "#c9a48f"][i % 5]
        L.shadow(m, 0.18, (1, 2), 1.2)
        L.over(tint(col, shade(m, 0.6, 1.5)), m * 0.95)
    return L


CELLS = [
    ("paper_scraps", "Papierfetzen", paper_scraps, 0.6),
    ("crumpled_cup", "Zerknuellter Kaffeebecher", crumpled_cup, 0.3),
    ("can", "Getraenkedose (zerdrueckt)", can, 0.25),
    ("cigarette_butts", "Zigarettenstummel-Gruppe", cigarette_butts, 0.35),
    ("gum_stains", "Kaugummiflecken", gum_stains, 0.8),
    ("leaves_a", "Laub A (Linde, gelb)", lambda: leaves(6, "heart", ["#d8b23a", "#c9962b", "#b5862a", "#9fa13a",
                                                                     "#e0c24e"], 34, (20, 30)), 1.2),
    ("leaves_b", "Laub B (Ahorn/Platane, braun-orange)", lambda: leaves(7, "lobed", ["#a3561f", "#8a4a22", "#c46f2a",
                                                                                     "#6e4426", "#b9852f"], 26,
                                                                        (24, 36)), 1.2),
    ("caps_glass", "Kronkorken + Glasscherben", caps_glass, 0.5),
    ("wet_patch", "Nasser Fleck", wet_patch, 1.5),
    ("oil_stain", "Oelfleck", oil_stain, 1.2),
    ("sand_grit", "Sand/Splitt", sand_grit, 1.2),
    ("flyer", "Zettel/Flyer (A5, ohne Text)", flyer, 0.4),
    ("plastic_bag", "Plastiktuete", plastic_bag, 0.5),
    ("butts_ash", "Kippen + Asche", butts_ash, 0.4),
    ("dirt_crumbs", "Erdkruemel/Schmutz (kein Kot)", dirt_crumbs, 0.8),
    ("petals", "Bluetenblaetter", petals, 1.0),
]


def main():
    W = 4 * C
    rgb = np.zeros((W, W, 3))
    a = np.zeros((W, W))
    meta = []
    for k, (name, label, fn, size) in enumerate(CELLS):
        col, row = k % 4, k // 4
        Lr = fn()
        c_rgb, c_a = Lr.result()
        rgb[row * C:(row + 1) * C, col * C:(col + 1) * C] = c_rgb
        a[row * C:(row + 1) * C, col * C:(col + 1) * C] = c_a
        meta.append({"index": k, "col": col, "row": row, "name": name, "label": label,
                     "uv_rect": [col / 4, row / 4, (col + 1) / 4, (row + 1) / 4],
                     "size_m": size})
        print("cell", k, name)
    to_img(rgb, a).save(os.path.join(OUTD, "litter.png"), optimize=True)
    info = {"atlas": "litter.png", "grid": [4, 4], "cell_px": C, "size_px": W,
            "uv_convention": "uv_rect = [u0, v0, u1, v1], Ursprung oben links (Godot-UV), v nach unten",
            "view": "Draufsicht, Licht von oben links, weiches Alpha, Rand je Zelle 20 px transparent",
            "size_m": "empfohlene Kantenlaenge der Decal-Projektion je Zelle in Metern",
            "cells": meta}
    with open(os.path.join(OUTD, "litter.json"), "w") as fh:
        json.dump(info, fh, indent=2, ensure_ascii=False)
    # Vorschau auf Asphaltgrau
    bg = np.ones((W, W, 3)) * hexcol("#5d5f60") * (0.9 + 0.2 * fbm(W // 4, W // 4, 20, 3, 1).repeat(4, 0).repeat(4, 1)[..., None])
    comp = rgb * a[..., None] + bg * (1 - a[..., None])
    prev = to_img(comp).resize((1024, 1024))
    os.makedirs(os.path.join(HERE, "furniture_tmp"), exist_ok=True)
    prev.save(os.path.join(HERE, "furniture_tmp", "litter_preview.png"))


if __name__ == "__main__":
    main()
