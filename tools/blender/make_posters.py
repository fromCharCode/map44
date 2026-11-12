"""Plakat-Atlanten (frei erfundene Veranstaltungen, keine echten Firmen/Marken/Personen).

Aufruf:  .venv/bin/python tools/blender/make_posters.py
Ausgabe: godot/assets/textures/street/posters.png            4 x 2 Hochformat-Plakate à 512 x 724 (A-Format)
         godot/assets/textures/street/posters.json
         godot/assets/textures/street/billboard_posters.png  3 x 3 Querformat-Plakate à 680 x 480 (18/1, ≈√2:1)
         godot/assets/textures/street/billboard_posters.json
Schriften: Noto Sans/Serif, Lato, Open Sans (alle SIL OFL).
"""
import json
import math
import os
import random

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_DIR = os.path.join(ROOT, "godot", "assets", "textures", "street")
N = "/usr/share/fonts/google-noto/"
L = "/usr/share/fonts/lato-fonts/"
FONTS = {
    "black_xc": N + "NotoSans-ExtraCondensedBlack.ttf",
    "bold_c": N + "NotoSans-CondensedBold.ttf",
    "black_c": N + "NotoSans-CondensedBlack.ttf",
    "semi_c": N + "NotoSans-CondensedSemiBold.ttf",
    "med_c": N + "NotoSans-CondensedMedium.ttf",
    "reg_c": N + "NotoSans-Condensed.ttf",
    "sans_b": N + "NotoSans-Bold.ttf",
    "sans_bl": N + "NotoSans-Black.ttf",
    "sans": N + "NotoSans-Regular.ttf",
    "serif_bl": N + "NotoSerif-Black.ttf",
    "serif_b": N + "NotoSerif-Bold.ttf",
    "serif_i": N + "NotoSerif-Italic.ttf",
    "serif_bi": N + "NotoSerif-BoldItalic.ttf",
    "serif": N + "NotoSerif-Regular.ttf",
    "lato_bl": L + "Lato-Black.ttf",
    "lato_b": L + "Lato-Bold.ttf",
    "lato": L + "Lato-Regular.ttf",
    "lato_l": L + "Lato-Light.ttf",
    "lato_h": L + "Lato-Hairline.ttf",
    "lato_hi": L + "Lato-HeavyItalic.ttf",
}
SS = 2  # Überabtastung


class Poster:
    def __init__(self, w, h, bg):
        self.w, self.h = w * SS, h * SS
        self.im = Image.new("RGB", (self.w, self.h), bg)
        self.d = ImageDraw.Draw(self.im)
        self.land = w > h

    # relative Koordinaten 0..1
    def X(self, x):
        return x * self.w

    def Y(self, y):
        return y * self.h

    def rect(self, x0, y0, x1, y1, col):
        self.d.rectangle([self.X(x0), self.Y(y0), self.X(x1), self.Y(y1)], fill=col)

    def poly(self, pts, col):
        self.d.polygon([(self.X(x), self.Y(y)) for x, y in pts], fill=col)

    def circle(self, cx, cy, r, col, rel="w", outline=None, width=0):
        rr = r * (self.w if rel == "w" else self.h)
        x, y = self.X(cx), self.Y(cy)
        self.d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=col, outline=outline, width=round(width * self.w))

    def line(self, pts, col, width):
        self.d.line([(self.X(x), self.Y(y)) for x, y in pts], fill=col, width=max(1, round(width * self.w)),
                    joint="curve")

    def gradient(self, top, bottom, y0=0.0, y1=1.0):
        a, b = round(self.Y(y0)), round(self.Y(y1))
        for y in range(a, b):
            t = (y - a) / max(1, b - a - 1)
            col = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
            self.d.line([(0, y), (self.w, y)], fill=col)

    def text(self, s, x, y, size, font, col, anchor="mm", max_w=None, track=0.0, rel="h"):
        """size = Versalhöhe relativ zu Höhe (rel='h') oder Breite."""
        base = self.h if rel == "h" else self.w
        px = size * base
        path = FONTS[font]
        probe = ImageFont.truetype(path, 200)
        cap = -probe.getbbox("H", anchor="ls")[1] / 200.0
        fs = max(6, round(px / cap))
        f = ImageFont.truetype(path, fs)
        tr = track * self.w

        def width(ff):
            return sum(ff.getlength(ch) for ch in s) + tr * (len(s) - 1)

        if max_w is not None:
            while width(f) > max_w * self.w and fs > 6:
                fs = int(fs * 0.96)
                f = ImageFont.truetype(path, fs)
        tw = width(f)
        capp = cap * fs
        # Ankerauflösung
        ax, ay = anchor[0], anchor[1]
        X0 = self.X(x) - (tw / 2 if ax == "m" else (tw if ax == "r" else 0))
        base_y = self.Y(y) + (capp / 2 if ay == "m" else (capp if ay == "t" else 0))
        if track == 0.0:
            self.d.text((X0, base_y), s, font=f, fill=col, anchor="ls")
        else:
            xx = X0
            for ch in s:
                self.d.text((xx, base_y), ch, font=f, fill=col, anchor="ls")
                xx += f.getlength(ch) + tr
        return tw / self.w

    def lines(self, rows, x, y, size, font, col, lead=1.55, anchor="mm", max_w=None, track=0.0):
        for i, r in enumerate(rows):
            self.text(r, x, y + i * size * lead, size, font, col, anchor=anchor, max_w=max_w, track=track)

    def finish(self, seed):
        im = self.im.resize((self.w // SS, self.h // SS), Image.LANCZOS)
        # Papier: leichtes Rauschen + Randabdunklung (gedruckt, etwas verwittert)
        rnd = random.Random(seed)
        noise = Image.effect_noise(im.size, 18).filter(ImageFilter.GaussianBlur(0.6))
        im = Image.blend(im, Image.merge("RGB", (noise, noise, noise)), 0.035)
        vign = Image.new("L", im.size, 0)
        vd = ImageDraw.Draw(vign)
        w, h = im.size
        for k in range(12):
            vd.rectangle([k, k, w - 1 - k, h - 1 - k], outline=round(60 * (1 - k / 12) ** 2))
        dark = Image.new("RGB", im.size, (40, 36, 30))
        im = Image.composite(dark, im, vign)
        _ = rnd
        return im


# ---------------------------------------------------------------------------
def skyline(p, base, col, scale=1.0, x0=0.0, x1=1.0):
    """Erfundene barocke Stadtsilhouette (Kuppeln, Türme), ohne konkrete Vorlage."""
    pts = [(x0, base)]
    rnd = random.Random(7)
    x = x0
    while x < x1:
        kind = rnd.random()
        w = (0.03 + rnd.random() * 0.06) * scale
        h = (0.03 + rnd.random() * 0.05) * scale
        if kind < 0.18:  # Kuppel mit Laterne
            cx = x + w * 1.2
            r = w * 1.2
            pts += [(x, base - h), (x + 0.2 * w, base - h)]
            for i in range(13):
                a = math.pi - math.pi * i / 12
                pts.append((cx + r * math.cos(a), base - h - r * math.sin(a) * (p.w / p.h) * 0.9))
            x = cx + r
            pts += [(x, base - h)]
        elif kind < 0.33:  # Turm mit Spitze
            tw = w * 0.5
            th = h * 2.6
            pts += [(x, base - h), (x + 0.1 * w, base - h), (x + 0.1 * w, base - th), (x + 0.1 * w + tw / 2, base - th - h * 1.4),
                    (x + 0.1 * w + tw, base - th), (x + 0.1 * w + tw, base - h)]
            x += 0.1 * w + tw
        else:  # Häuserblock mit Dach
            pts += [(x, base - h), (x + w * 0.5, base - h - h * 0.35), (x + w, base - h)]
            x += w
    pts += [(x1, base - 0.02), (x1, base)]
    p.poly([(min(max(a, x0), x1), b) for a, b in pts], col)


def waves(p, y, amp, col, n=3, freq=6.0, phase=0.0, gap=0.025, width=0.008):
    for k in range(n):
        pts = []
        for i in range(81):
            t = i / 80
            pts.append((t, y + k * gap + amp * math.sin(2 * math.pi * (freq * t) + phase + k)))
        p.line(pts, col, width)


# ---------------------------------------------------------------------------
# Die acht Plakate (Hoch- und Querformat)
# ---------------------------------------------------------------------------
def p_konzert(p):
    p.gradient((22, 30, 72), (244, 120, 60), 0, 0.72)
    p.rect(0, 0.72, 1, 1, (18, 70, 92))
    sx = 0.70 if p.land else 0.5
    p.circle(sx, 0.52 if p.land else 0.50, 0.17 if p.land else 0.25, (255, 196, 90))
    skyline(p, 0.72, (30, 24, 40), scale=1.0 if p.land else 1.3)
    waves(p, 0.78, 0.008, (90, 180, 190), n=4, freq=5, gap=0.04, width=0.006)
    if p.land:
        p.text("ELBUFER-SOMMER", 0.05, 0.16, 0.13, "black_xc", (255, 238, 210), anchor="ls", max_w=0.62)
        p.text("Open-Air-Konzerte am Fluss", 0.05, 0.26, 0.05, "lato_b", (255, 214, 160), anchor="ls")
        p.text("14.–16. AUGUST", 0.05, 0.40, 0.085, "black_c", (255, 255, 255), anchor="ls")
        p.lines(["Die Kupferspatzen · Neonfluss", "Kapelle Morgenrot · Lina Sternberg"], 0.05, 0.84, 0.033, "lato_b",
                (230, 245, 245), anchor="ls", lead=1.65)
        p.text("Einlass 18 Uhr · Tickets an der Abendkasse", 0.95, 0.975, 0.022, "lato", (200, 230, 230), anchor="rs")
    else:
        p.text("ELBUFER", 0.5, 0.10, 0.085, "black_xc", (255, 238, 210), max_w=0.9, track=0.01)
        p.text("SOMMER", 0.5, 0.20, 0.085, "black_xc", (255, 196, 90), max_w=0.9, track=0.01)
        p.text("Open-Air-Konzerte am Fluss", 0.5, 0.275, 0.022, "lato_b", (255, 225, 190))
        p.text("14.–16. AUGUST", 0.5, 0.345, 0.032, "black_c", (255, 255, 255))
        p.lines(["Die Kupferspatzen", "Neonfluss · Kapelle Morgenrot", "Lina Sternberg & Band"], 0.5, 0.84, 0.022,
                "lato_b", (230, 245, 245), lead=1.8)
        p.text("Einlass 18 Uhr · Tickets an der Abendkasse", 0.5, 0.965, 0.013, "lato", (200, 230, 230))


def p_theater(p):
    p.rect(0, 0, 1, 1, (14, 14, 16))
    red = (196, 30, 36)
    if p.land:
        p.circle(0.84, 0.46, 0.30, red, rel="h")
        bx0, bx1, by = 0.62, 1.02, 0.70
    else:
        p.circle(0.5, 0.42, 0.19, red, rel="h")
        bx0, bx1, by = -0.02, 1.02, 0.55
    # Brückenbögen als feine Linien
    n = 5
    for i in range(n):
        a = bx0 + (bx1 - bx0) * i / n
        b = bx0 + (bx1 - bx0) * (i + 1) / n
        pts = [(a + (b - a) * t / 20, by - 0.09 * math.sin(math.pi * t / 20) * (0.7 if p.land else 0.5)) for t in range(21)]
        p.line(pts, (235, 230, 220), 0.004)
    p.line([(bx0, by - 0.002), (bx1, by - 0.002)], (235, 230, 220), 0.005)
    if p.land:
        p.text("Die Nacht", 0.05, 0.25, 0.11, "serif_b", (245, 240, 230), anchor="ls", max_w=0.58)
        p.text("der Brücken", 0.05, 0.43, 0.11, "serif_b", (245, 240, 230), anchor="ls", max_w=0.58)
        p.text("Schauspiel von Marta Hellwig", 0.05, 0.55, 0.042, "serif_i", (220, 210, 200), anchor="ls")
        p.text("PREMIERE 3. OKTOBER · 19.30 UHR", 0.05, 0.80, 0.036, "lato_b", red, anchor="ls", track=0.003,
               max_w=0.56)
        p.text("THEATER AM ELBHANG", 0.05, 0.92, 0.05, "lato_bl", (245, 240, 230), anchor="ls", track=0.006)
    else:
        p.text("THEATER AM ELBHANG", 0.5, 0.06, 0.018, "lato_bl", (245, 240, 230), track=0.008)
        p.text("Die Nacht", 0.5, 0.68, 0.055, "serif_b", (245, 240, 230))
        p.text("der Brücken", 0.5, 0.76, 0.055, "serif_b", (245, 240, 230))
        p.text("Schauspiel von Marta Hellwig", 0.5, 0.825, 0.02, "serif_i", (220, 210, 200))
        p.text("PREMIERE", 0.5, 0.89, 0.018, "lato_b", red, track=0.01)
        p.text("3. OKTOBER · 19.30 UHR", 0.5, 0.925, 0.018, "lato_b", (245, 240, 230), track=0.004)


def p_ausstellung(p):
    p.rect(0, 0, 1, 1, (238, 232, 218))
    ochre, sand, blue, dark = (205, 150, 60), (214, 190, 150), (40, 70, 120), (40, 36, 34)
    if p.land:
        p.rect(0.64, 0.0, 1.0, 0.62, sand)
        p.rect(0.76, 0.18, 0.95, 0.80, blue)
        p.circle(0.72, 0.50, 0.15, ochre, rel="h")
        p.rect(0.64, 0.62, 0.76, 1.0, dark)
        tx = 0.05
        p.text("LICHT UND", tx, 0.22, 0.10, "lato_bl", dark, anchor="ls", max_w=0.56)
        p.text("SANDSTEIN", tx, 0.38, 0.10, "lato_bl", ochre, anchor="ls", max_w=0.56)
        p.text("Fotografien 1890–1930", tx, 0.50, 0.045, "serif_i", dark, anchor="ls")
        p.text("12. September – 6. Januar", tx, 0.76, 0.04, "lato_b", dark, anchor="ls")
        p.text("Kunsthaus Elbhang · Di–So 10–18 Uhr", tx, 0.86, 0.033, "lato", dark, anchor="ls", max_w=0.56)
    else:
        p.rect(0.0, 0.0, 0.62, 0.42, sand)
        p.rect(0.40, 0.12, 0.92, 0.36, blue)
        p.circle(0.30, 0.40, 0.13, ochre, rel="h")
        p.rect(0.70, 0.36, 0.92, 0.52, dark)
        p.text("LICHT UND", 0.08, 0.63, 0.05, "lato_bl", dark, anchor="ls")
        p.text("SANDSTEIN", 0.08, 0.71, 0.05, "lato_bl", ochre, anchor="ls")
        p.text("Fotografien 1890–1930", 0.08, 0.765, 0.02, "serif_i", dark, anchor="ls")
        p.text("12. September – 6. Januar", 0.08, 0.86, 0.018, "lato_b", dark, anchor="ls")
        p.text("Kunsthaus Elbhang", 0.08, 0.90, 0.016, "lato", dark, anchor="ls")
        p.text("Di–So 10–18 Uhr", 0.08, 0.935, 0.016, "lato", dark, anchor="ls")


def p_stadtfest(p):
    p.rect(0, 0, 1, 1, (252, 206, 40))
    cols = [(220, 40, 50), (30, 110, 180), (40, 160, 90), (250, 250, 250), (240, 120, 30)]
    # Wimpelketten
    for row, (y, sag) in enumerate(((0.03, 0.05), (0.13, 0.06))):
        n = 14 if p.land else 9
        for i in range(n):
            t0, t1 = i / n, (i + 1) / n
            ya = y + sag * math.sin(math.pi * t0)
            yb = y + sag * math.sin(math.pi * t1)
            tm = (t0 + t1) / 2
            tip = y + sag * math.sin(math.pi * tm) + (0.07 if p.land else 0.05)
            p.poly([(t0 + 0.004, ya), (t1 - 0.004, yb), (tm, tip)], cols[(i + row * 2) % len(cols)])
        p.line([(t / 40, y + sag * math.sin(math.pi * t / 40)) for t in range(41)], (60, 50, 40), 0.003)
    red = (200, 30, 40)
    if p.land:
        p.text("ALTSTADTFEST", 0.5, 0.45, 0.17, "black_xc", red, max_w=0.9)
        p.text("Musik · Markt · Riesenrad · Feuerwerk", 0.5, 0.62, 0.055, "lato_b", (40, 30, 30))
        p.rect(0.0, 0.76, 1.0, 1.0, red)
        p.text("22.–24. JULI", 0.30, 0.88, 0.09, "black_c", (255, 245, 220))
        p.text("Eintritt frei!", 0.75, 0.88, 0.07, "lato_hi", (255, 220, 80))
    else:
        p.text("ALTSTADT", 0.5, 0.36, 0.085, "black_xc", red, max_w=0.9)
        p.text("FEST", 0.5, 0.48, 0.10, "black_xc", red, max_w=0.9)
        p.lines(["Musik · Markt", "Riesenrad · Feuerwerk"], 0.5, 0.58, 0.025, "lato_b", (40, 30, 30), lead=1.7)
        p.rect(0.0, 0.74, 1.0, 1.0, red)
        p.text("22.–24. JULI", 0.5, 0.82, 0.045, "black_c", (255, 245, 220))
        p.text("Eintritt frei!", 0.5, 0.91, 0.032, "lato_hi", (255, 220, 80))


def p_zirkus(p):
    red, cream, gold, navy = (190, 24, 36), (250, 240, 220), (232, 176, 40), (24, 32, 70)
    p.rect(0, 0, 1, 1, cream)
    n = 12 if p.land else 9
    for i in range(n):
        if i % 2 == 0:
            x0, x1 = i / n, (i + 1) / n
            p.poly([(0.5, -0.02), (x0 * 1.6 - 0.3, 1.02), (x1 * 1.6 - 0.3, 1.02)], red)
    # Zeltspitze und Stern
    cy = 0.30 if p.land else 0.24
    r = 0.15 if p.land else 0.12
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.45
        pts.append((0.5 + rr * math.cos(a) * (p.h / p.w), cy + rr * math.sin(a)))
    p.circle(0.5, cy, r * 1.15, navy, rel="h")
    p.poly(pts, gold)
    by0, by1 = (0.56, 0.95) if p.land else (0.48, 0.90)
    p.rect(0.08, by0, 0.92, by1, navy)
    p.rect(0.095, by0 + 0.012, 0.905, by1 - 0.012, None) if False else None
    p.d.rectangle([p.X(0.095), p.Y(by0 + 0.012), p.X(0.905), p.Y(by1 - 0.012)], outline=gold, width=round(0.004 * p.w))
    if p.land:
        p.text("Circus Fiorello", 0.5, 0.68, 0.10, "serif_bi", gold, max_w=0.78)
        p.text("DIE GROSSE MANEGE · AKROBATIK · CLOWNS · PFERDE", 0.5, 0.79, 0.035, "lato_b", cream, max_w=0.78)
        p.text("ab 3. Mai auf dem Festplatz · täglich 15 & 19 Uhr", 0.5, 0.88, 0.035, "lato", cream, max_w=0.78)
    else:
        p.text("Circus", 0.5, 0.55, 0.045, "serif_bi", gold)
        p.text("Fiorello", 0.5, 0.635, 0.06, "serif_bi", gold, max_w=0.78)
        p.text("DIE GROSSE MANEGE", 0.5, 0.71, 0.018, "lato_b", cream, track=0.006)
        p.text("Akrobatik · Clowns · Pferde", 0.5, 0.75, 0.016, "lato", cream)
        p.text("ab 3. Mai", 0.5, 0.80, 0.03, "black_c", (255, 255, 255))
        p.text("auf dem Festplatz · täglich 15 & 19 Uhr", 0.5, 0.86, 0.014, "lato", cream, max_w=0.78)


def p_kino(p):
    p.gradient((10, 42, 52), (6, 16, 22))
    teal, amber = (90, 190, 190), (240, 170, 70)
    # Raddampfer-Silhouette (erfunden, stilisiert)
    if p.land:
        cx, cy, s = 0.70, 0.58, 0.55
    else:
        cx, cy, s = 0.5, 0.46, 0.85
    hw = 0.35 * s
    hull = [(cx - hw, cy), (cx + hw, cy), (cx + hw * 0.85, cy + 0.05 * s), (cx - hw * 0.9, cy + 0.05 * s)]
    p.poly(hull, (4, 8, 10))
    p.rect(cx - hw * 0.7, cy - 0.06 * s, cx + hw * 0.6, cy, (4, 8, 10))
    p.rect(cx - 0.02 * s, cy - 0.20 * s, cx + 0.02 * s, cy - 0.06 * s, (4, 8, 10))
    p.circle(cx + 0.05, cy - 0.005, 0.07 * s, (4, 8, 10), rel="h")
    for k in range(3):
        p.circle(cx + 0.02 * k, cy - 0.25 * s - 0.05 * k, 0.03 + 0.012 * k, (40, 70, 80), rel="h")
    waves(p, cy + 0.07 * s, 0.006, teal, n=3, freq=7, gap=0.03, width=0.004)
    # Filmstreifen
    for yy in ((0.0, 0.035),) if p.land else ((0.0, 0.025),):
        p.rect(0, yy[0], 1, yy[1], (0, 0, 0))
        for i in range(30):
            x = i / 30 + 0.008
            p.rect(x, yy[0] + 0.008, x + 0.014, yy[1] - 0.008, (200, 200, 190))
    if p.land:
        p.text("DER LETZTE DAMPFER", 0.05, 0.25, 0.10, "black_c", amber, anchor="ls", max_w=0.55)
        p.text("Ein Film von Jonas Reimann", 0.05, 0.34, 0.04, "lato_l", (220, 230, 230), anchor="ls")
        p.text("AB 12. JUNI IM KINO", 0.05, 0.86, 0.06, "lato_bl", (255, 255, 255), anchor="ls", track=0.004)
        p.text("mit Ida Vogt · Karl Brenner · Selma Ott", 0.05, 0.93, 0.03, "lato", (160, 190, 190), anchor="ls")
    else:
        p.text("Ein Film von Jonas Reimann", 0.5, 0.08, 0.016, "lato_l", (220, 230, 230))
        p.text("DER LETZTE", 0.5, 0.70, 0.045, "black_c", amber, max_w=0.86)
        p.text("DAMPFER", 0.5, 0.78, 0.065, "black_c", amber, max_w=0.86)
        p.text("mit Ida Vogt · Karl Brenner · Selma Ott", 0.5, 0.845, 0.013, "lato", (160, 190, 190))
        p.text("AB 12. JUNI IM KINO", 0.5, 0.92, 0.026, "lato_bl", (255, 255, 255), track=0.006)


def p_party(p):
    p.rect(0, 0, 1, 1, (12, 8, 20))
    mag, cyan, lime = (255, 50, 170), (40, 220, 255), (190, 255, 60)
    # Neon-Kreise
    cx, cy = (0.72, 0.48) if p.land else (0.5, 0.36)
    for k, col in enumerate((mag, cyan, mag, cyan)):
        r = (0.40 - 0.08 * k) if p.land else (0.30 - 0.06 * k)
        p.circle(cx, cy, r, None, rel="h", outline=col, width=0.006)
    for i in range(24):
        a = 2 * math.pi * i / 24
        r0 = 0.05
        r1 = 0.12 if i % 2 else 0.09
        p.line([(cx + r0 * math.cos(a) * p.h / p.w, cy + r0 * math.sin(a)),
                (cx + r1 * math.cos(a) * p.h / p.w, cy + r1 * math.sin(a))], lime, 0.004)
    if p.land:
        p.text("KELLERLICHT", 0.05, 0.22, 0.13, "black_xc", mag, anchor="ls", max_w=0.55)
        p.text("TECHNO · HOUSE · DISCO", 0.05, 0.32, 0.042, "lato_b", cyan, anchor="ls", track=0.003, max_w=0.42)
        p.lines(["DJ Mira K.", "Ostwind", "Feldrausch"], 0.05, 0.52, 0.05, "lato_bl", (240, 240, 250), anchor="ls",
                lead=1.6)
        p.text("SAMSTAG · 23 UHR", 0.05, 0.92, 0.06, "black_c", lime, anchor="ls")
    else:
        p.text("KELLERLICHT", 0.5, 0.67, 0.07, "black_xc", mag, max_w=0.92)
        p.text("TECHNO · HOUSE · DISCO", 0.5, 0.735, 0.018, "lato_b", cyan, track=0.006)
        p.lines(["DJ Mira K. · Ostwind", "Feldrausch"], 0.5, 0.80, 0.02, "lato_bl", (240, 240, 250), lead=1.7)
        p.text("SAMSTAG · 23 UHR", 0.5, 0.92, 0.032, "black_c", lime)


def p_wahl(p):
    p.rect(0, 0, 1, 1, (246, 246, 242))
    teal, orange, ink = (0, 120, 130), (240, 130, 30), (25, 25, 30)
    # Stimmzettel mit Kreuz
    if p.land:
        bx, by, bw, bh = 0.62, 0.16, 0.30, 0.60
    else:
        bx, by, bw, bh = 0.22, 0.08, 0.56, 0.36
    p.rect(bx, by, bx + bw, by + bh, (255, 255, 255))
    p.d.rectangle([p.X(bx), p.Y(by), p.X(bx + bw), p.Y(by + bh)], outline=ink, width=round(0.006 * p.w))
    for i in range(4):
        yy = by + bh * (0.18 + 0.2 * i)
        cs = bh * 0.10
        p.d.ellipse([p.X(bx + bw * 0.12), p.Y(yy) - cs / 2 * p.h / p.h * 0 - p.Y(cs) / 2,
                     p.X(bx + bw * 0.12) + p.Y(cs), p.Y(yy) + p.Y(cs) / 2], outline=ink, width=round(0.004 * p.w))
        p.rect(bx + bw * 0.32, yy - bh * 0.012, bx + bw * 0.85, yy + bh * 0.012, (170, 170, 170))
    yy = by + bh * 0.38
    cs = p.Y(bh * 0.10)
    x0 = p.X(bx + bw * 0.12)
    p.d.line([(x0 - cs * 0.1, p.Y(yy) - cs * 0.6), (x0 + cs * 1.1, p.Y(yy) + cs * 0.6)], fill=orange, width=round(cs * 0.28))
    p.d.line([(x0 - cs * 0.1, p.Y(yy) + cs * 0.6), (x0 + cs * 1.1, p.Y(yy) - cs * 0.6)], fill=orange, width=round(cs * 0.28))
    if p.land:
        p.text("Wählen gehen!", 0.05, 0.36, 0.16, "sans_bl", teal, anchor="ls", max_w=0.54)
        p.text("Deine Stimme zählt.", 0.05, 0.52, 0.07, "sans_b", ink, anchor="ls", max_w=0.54)
        p.rect(0, 0.80, 1, 1, teal)
        p.text("Wahlsonntag · 8 bis 18 Uhr · Briefwahl im Bürgerbüro", 0.05, 0.90, 0.045, "lato_b", (255, 255, 255),
               anchor="lm", max_w=0.9)
    else:
        p.text("Wählen", 0.5, 0.56, 0.075, "sans_bl", teal, max_w=0.9)
        p.text("gehen!", 0.5, 0.66, 0.075, "sans_bl", teal, max_w=0.9)
        p.text("Deine Stimme zählt.", 0.5, 0.74, 0.028, "sans_b", ink)
        p.rect(0, 0.82, 1, 1, teal)
        p.text("Wahlsonntag · 8 bis 18 Uhr", 0.5, 0.875, 0.022, "lato_b", (255, 255, 255))
        p.text("Briefwahl im Bürgerbüro", 0.5, 0.935, 0.018, "lato", (230, 245, 245))


def p_frei(p):
    p.rect(0, 0, 1, 1, (250, 250, 250))
    blue = (20, 70, 150)
    p.rect(0, 0, 1, 0.08, blue)
    p.rect(0, 0.92, 1, 1, blue)
    p.text("Diese Fläche ist frei.", 0.5, 0.42, 0.13, "sans_bl", blue, max_w=0.86)
    p.text("Hier wirkt Ihre Botschaft – an 50.000 Augenpaaren täglich.", 0.5, 0.60, 0.05, "lato", (60, 60, 70),
           max_w=0.86)


POSTERS = [
    ("konzert", p_konzert, "Open-Air-Konzert 'Elbufer-Sommer'"),
    ("theater", p_theater, "Theater 'Die Nacht der Brücken'"),
    ("ausstellung", p_ausstellung, "Fotoausstellung 'Licht und Sandstein'"),
    ("stadtfest", p_stadtfest, "Altstadtfest mit Wimpeln"),
    ("zirkus", p_zirkus, "Circus Fiorello"),
    ("kino", p_kino, "Kinofilm 'Der letzte Dampfer'"),
    ("party", p_party, "Clubnacht 'Kellerlicht'"),
    ("wahl", p_wahl, "Wahlaufruf 'Wählen gehen!' (parteineutral)"),
]


def build(entries, cw, ch, cols, rows, fname, desc):
    atlas = Image.new("RGB", (cw * cols, ch * rows), (128, 128, 128))
    cells = {}
    for i, (name, fn, d) in enumerate(entries):
        p = Poster(cw, ch, (255, 255, 255))
        fn(p)
        im = p.finish(i)
        col, row = i % cols, i // cols
        atlas.paste(im, (col * cw, row * ch))
        cells[name] = {"index": i, "col": col, "row": row, "desc": d}
    atlas.save(os.path.join(OUT_DIR, fname + ".png"), optimize=True)
    meta = {"texture": "res://assets/textures/street/" + fname + ".png", "grid": [cols, rows], "cell_px": [cw, ch],
            "layout": f"Zellindex i: Spalte i mod {cols}, Zeile i div {cols}, Zeile 0 oben; UV 0..1 = ganze Zelle (Godot-UV.y=0 oben).",
            "note": desc, "cells": cells}
    with open(os.path.join(OUT_DIR, fname + ".json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)


def main():
    build(POSTERS, 512, 724, 4, 2, "posters",
          "Hochformat (A-Format 1:√2) für Litfaßsäulen/Wände. Frei erfundene Inhalte, Schriften OFL.")
    build(POSTERS + [("frei", p_frei, "Leere Fläche 'Diese Fläche ist frei.'")], 680, 480, 3, 3,
          "billboard_posters", "Querformat 18/1 (√2:1) für billboard.glb. Frei erfundene Inhalte, Schriften OFL.")
    print("ok")


if __name__ == "__main__":
    main()
