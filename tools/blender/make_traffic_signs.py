"""Verkehrszeichen-Atlas (StVO, amtliche Werke § 5 UrhG) prozedural mit PIL zeichnen.

Aufruf:  .venv/bin/python tools/blender/make_traffic_signs.py
Ausgabe: godot/assets/textures/street/traffic_signs.png (8x4 Zellen a 256 px, RGBA)
         godot/assets/textures/street/traffic_signs.json

Jede Zelle füllt die ganze 256-px-Kachel und ist auf das Seitenverhältnis der Platte vorverzerrt
(UV 0..1 der Plattenfläche = ganze Zelle). Farben nach RAL (Verkehrsrot 3020, Verkehrsblau 5017,
Signalgelb 1003 für 306, Verkehrsgelb 1023, Verkehrsgrün 6024). Schrift: Noto Sans (OFL) als DIN-1451-Ersatz.
"""
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont, ImageChops

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sign_shapes import PLATES, outline  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_DIR = os.path.join(ROOT, "godot", "assets", "textures", "street")
FONT_DIR = "/usr/share/fonts/google-noto/"
F_DIN = FONT_DIR + "NotoSans-SemiCondensedMedium.ttf"
F_DIN_B = FONT_DIR + "NotoSans-SemiCondensedSemiBold.ttf"
F_STOP = FONT_DIR + "NotoSans-SemiCondensedBold.ttf"

CELL = 256
GRID = (8, 4)
SS = 1536  # Überabtastung (längste Seite)

WHITE = (243, 243, 240)
BLACK = (22, 22, 22)
RED = (193, 18, 28)
BLUE = (21, 72, 137)
YELLOW_306 = (247, 186, 11)
YELLOW = (240, 202, 0)
GREEN = (0, 135, 84)
GREY = (150, 150, 150)


class Canvas:
    """Zeichenfläche in Millimetern, Ursprung oben links der Plattenbox, y nach unten."""

    def __init__(self, plate, edge=WHITE):
        p = PLATES[plate]
        self.plate = plate
        self.wmm, self.hmm = p["w"] * 1000.0, p["h"] * 1000.0
        self.s = SS / max(self.wmm, self.hmm)
        self.W, self.H = round(self.wmm * self.s), round(self.hmm * self.s)
        self.im = Image.new("RGB", (self.W, self.H), edge)
        self.d = ImageDraw.Draw(self.im)
        self.tk, self.tx, self.ty = 1.0, 0.0, 0.0  # Hilfstransformation für Piktogramme

    def scaled(self, k, ax, ay):
        """Piktogramm um Ankerpunkt (ax, ay) skalieren (bis reset())."""
        self.tk, self.tx, self.ty = k, ax * (1 - k), ay * (1 - k)

    def reset(self):
        self.tk, self.tx, self.ty = 1.0, 0.0, 0.0

    # Koordinaten
    def P(self, x, y):
        return ((self.tx + x * self.tk) * self.s, (self.ty + y * self.tk) * self.s)

    def pts(self, pts):
        return [self.P(x, y) for x, y in pts]

    def shape_pts(self, inset_mm):
        w, h = self.wmm / 1000.0, self.hmm / 1000.0
        o = outline(self.plate, inset_mm / 1000.0, seg=24, circle_seg=360)
        return [((x + w / 2) * 1000 * self.s, (h / 2 - y) * 1000 * self.s) for x, y in o]

    def shape_mask(self, inset_mm):
        m = Image.new("L", (self.W, self.H), 0)
        ImageDraw.Draw(m).polygon(self.shape_pts(inset_mm), fill=255)
        return m

    # Grundformen
    def fill_shape(self, inset_mm, col):
        self.d.polygon(self.shape_pts(inset_mm), fill=col)

    def poly(self, pts, col, d=None):
        (d or self.d).polygon(self.pts(pts), fill=col)

    def circle(self, cx, cy, r, col, d=None):
        x, y = self.P(cx, cy)
        rr = r * self.s * self.tk
        (d or self.d).ellipse([x - rr, y - rr, x + rr, y + rr], fill=col)

    def ring(self, cx, cy, r, w, col, d=None):
        x, y = self.P(cx, cy)
        ro, ri = r * self.s * self.tk, (r - w) * self.s * self.tk
        (d or self.d).ellipse([x - ro, y - ro, x + ro, y + ro], outline=col, width=max(1, round(ro - ri)))

    def stroke(self, pts, w, col, d=None, caps=True):
        d = d or self.d
        P = self.pts(pts)
        ww = max(1, round(w * self.s * self.tk))
        d.line(P, fill=col, width=ww, joint="curve")
        if caps:
            for x, y in (P[0], P[-1]):
                r = ww / 2
                d.ellipse([x - r, y - r, x + r, y + r], fill=col)

    def rrect(self, x0, y0, x1, y1, r, col, d=None):
        (d or self.d).rounded_rectangle([*self.P(x0, y0), *self.P(x1, y1)], radius=r * self.s * self.tk, fill=col)

    def text(self, s, cx, cy, cap_mm, font, col, max_w=None, sx=1.0, track=0.0):
        """Text mit Versalhöhe cap_mm zentriert auf (cx, cy) setzen."""
        probe = ImageFont.truetype(font, 200)
        bb = probe.getbbox("H", anchor="ls")
        cap_ratio = -bb[1] / 200.0
        size = max(4, round(cap_mm * self.s / cap_ratio))
        f = ImageFont.truetype(font, size)
        # Breite inkl. Sperrung
        adv = [f.getlength(ch) for ch in s]
        tr = track * self.s
        tw = sum(adv) + tr * (len(s) - 1)
        asc, desc = f.getmetrics()
        tmp = Image.new("L", (int(tw) + 8, asc + desc + 8), 0)
        td = ImageDraw.Draw(tmp)
        x = 4
        for ch, a in zip(s, adv):
            td.text((x, 4 + asc), ch, font=f, fill=255, anchor="ls")
            x += a + tr
        scale = sx
        if max_w is not None and tw * sx > max_w * self.s:
            scale = max_w * self.s / tw
        if abs(scale - 1.0) > 1e-3:
            tmp = tmp.resize((max(1, round(tmp.width * scale)), tmp.height), Image.LANCZOS)
        cap_px = cap_mm * self.s
        px, py = self.P(cx, cy)
        ox = round(px - tmp.width / 2)
        oy = round(py + cap_px / 2 - (4 + asc))
        self.im.paste(Image.new("RGB", tmp.size, col), (ox, oy), tmp)

    # Ebene mit Beschnitt
    def layer(self):
        lay = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        return lay, ImageDraw.Draw(lay)

    def composite(self, lay, clip_mask=None):
        a = lay.getchannel("A")
        if clip_mask is not None:
            a = ImageChops.multiply(a, clip_mask)
        self.im.paste(lay.convert("RGB"), (0, 0), a)

    def finish(self):
        rgb = self.im.resize((CELL, CELL), Image.LANCZOS)
        a = self.shape_mask(0).resize((CELL, CELL), Image.LANCZOS)
        rgb.putalpha(a)
        return rgb


# ---------------------------------------------------------------------------
# Hilfen für Gestaltungselemente
# ---------------------------------------------------------------------------
def end_stripes(c, clip_inset, n=5, lw=None, pitch=None, direction=(1, -1), center=None, length=None):
    """Schwarze Diagonalstreifen der 'Ende'-Zeichen (von unten links nach oben rechts)."""
    W, H = c.wmm, c.hmm
    lw = lw or 0.013 * W
    pitch = pitch or 0.028 * W
    cx, cy = center or (W / 2, H / 2)
    dx, dy = direction
    L = math.hypot(dx, dy)
    dx, dy = dx / L, dy / L
    nx, ny = -dy, dx
    length = length or 2 * max(W, H)
    lay, ld = c.layer()
    for k in range(n):
        o = (k - (n - 1) / 2) * pitch
        p0 = (cx + nx * o - dx * length / 2, cy + ny * o - dy * length / 2)
        p1 = (cx + nx * o + dx * length / 2, cy + ny * o + dy * length / 2)
        c.stroke([p0, p1], lw, BLACK + (255,), d=ld, caps=False)
    c.composite(lay, c.shape_mask(clip_inset))


def triangle_frame(c, up=True):
    c.fill_shape(0, WHITE)
    c.fill_shape(9, RED)
    c.fill_shape(76, WHITE)


def round_prohibition(c, ring=None, inner=WHITE):
    D = c.wmm
    ring = ring or 0.115 * D
    c.fill_shape(0, WHITE)
    c.fill_shape(8, RED)
    c.fill_shape(8 + ring, inner)


def round_blue(c):
    c.fill_shape(0, WHITE)
    c.fill_shape(9, BLUE)


def square_blue(c):
    c.fill_shape(0, WHITE)
    c.fill_shape(9, BLUE)


def square_white_framed(c):
    c.fill_shape(0, WHITE)
    c.fill_shape(10, BLACK)
    c.fill_shape(22, WHITE)


# ---------------------------------------------------------------------------
# Piktogramme
# ---------------------------------------------------------------------------
def woman_child(c, cx, cy, R, col):
    """Frau mit Kind (Gestaltung wie 239/242.1). Grundmaße bezogen auf Kreis (300,240) R=180."""
    k = R / 180.0

    def T(x, y):
        return (cx + (x - 300) * k, cy + (y - 240) * k)

    def TP(pts):
        return [T(*p) for p in pts]

    c.circle(*T(252, 110), 21 * k, col)
    c.poly(TP([(224, 152), (232, 139), (272, 139), (280, 152), (274, 226), (230, 226)]), col)
    c.stroke(TP([(227, 152), (221, 222)]), 16 * k, col)
    c.stroke(TP([(276, 152), (309, 226)]), 15 * k, col)
    c.poly(TP([(232, 218), (272, 218), (300, 292), (202, 292)]), col)
    c.stroke(TP([(241, 290), (241, 360)]), 17 * k, col)
    c.stroke(TP([(263, 290), (263, 360)]), 17 * k, col)
    # Kind
    c.circle(*T(347, 230), 17 * k, col)
    c.poly(TP([(334, 254), (360, 254), (369, 318), (325, 318)]), col)
    c.stroke(TP([(337, 262), (309, 228)]), 12 * k, col)
    c.stroke(TP([(359, 262), (392, 300)]), 12 * k, col)
    c.stroke(TP([(339, 316), (339, 372)]), 14 * k, col)
    c.stroke(TP([(356, 316), (356, 372)]), 14 * k, col)


def bicycle(c, cx, cy, s, col, bg=None):
    """Fahrrad, s = Raddurchmesser in mm; (cx, cy) = Mitte zwischen den Naben."""
    r = s / 2

    def T(x, y):
        return (cx + x * r, cy + y * r)

    lw = 0.15 * r
    for hx in (-1.55, 1.55):
        c.ring(*T(hx, 0), r, 0.17 * r, col)
    R_, B, S, H, Hb, F = T(-1.55, 0), T(-0.12, 0.05), T(-0.52, -1.12), T(0.98, -1.02), T(1.08, -0.72), T(1.55, 0)
    c.stroke([R_, B, Hb], lw, col)
    c.stroke([R_, S, B], lw, col)
    c.stroke([S, H], lw, col)
    c.stroke([H, Hb, F], lw, col)
    c.stroke([H, T(0.92, -1.42)], lw, col)
    c.stroke([T(0.70, -1.42), T(1.22, -1.42)], lw * 1.05, col)
    c.stroke([S, T(-0.58, -1.30)], lw, col)
    c.stroke([T(-0.85, -1.33), T(-0.33, -1.33)], lw * 1.3, col)
    c.circle(*B, 0.2 * r, col)
    c.stroke([T(-0.30, 0.30), T(0.08, -0.22)], lw * 0.9, col)


def pedestrian_walk(c, col, k=1.0, ox=0.0, oy=0.0, outline_col=None):
    """Gehender Mensch (Gestaltung 350), Grundmaße für 600-mm-Quadrat."""
    def T(x, y):
        return (ox + x * k, oy + y * k)

    def TP(pts):
        return [T(*p) for p in pts]

    parts_legs = [([(281, 300), (255, 370), (229, 444)], 26), ([(297, 300), (330, 368), (352, 440)], 26),
                  ([(229, 444), (212, 448)], 18), ([(352, 440), (372, 438)], 18)]
    if outline_col is not None:
        for p, w in parts_legs:
            c.stroke(TP(p), (w + 16) * k, outline_col)
    c.circle(*T(296, 168), 23 * k, col)
    c.poly(TP([(268, 210), (276, 198), (310, 198), (316, 210), (308, 306), (272, 306)]), col)
    c.stroke(TP([(272, 212), (242, 265), (228, 304)]), 20 * k, col)
    c.stroke(TP([(311, 212), (346, 232), (354, 286)]), 20 * k, col)
    for p, w in parts_legs:
        c.stroke(TP(p), w * k, col)


def car_front(c, cx, cy, w, col, cut):
    """Pkw von vorn (325.1). w = Breite in mm, (cx, cy) = Mitte."""
    k = w / 2.0

    def T(x, y):
        return (cx + x * k, cy + y * k)

    c.poly([T(-0.62, -0.62), T(0.62, -0.62), T(0.86, -0.06), T(-0.86, -0.06)], col)
    c.rrect(*T(-1.0, -0.12), *T(1.0, 0.42), 0.16 * k, col)
    c.rrect(*T(-0.82, 0.30), *T(-0.48, 0.72), 0.08 * k, col)
    c.rrect(*T(0.48, 0.30), *T(0.82, 0.72), 0.08 * k, col)
    c.poly([T(-0.50, -0.50), T(0.50, -0.50), T(0.68, -0.12), T(-0.68, -0.12)], cut)
    c.circle(*T(-0.66, 0.12), 0.13 * k, cut)
    c.circle(*T(0.66, 0.12), 0.13 * k, cut)
    c.rrect(*T(-0.34, 0.05), *T(0.34, 0.20), 0.04 * k, cut)


def house(c, x0, y0, w, col):
    """Haus-Umriss (325.1); (x0, y0) = linke obere Ecke des Wandkastens."""
    k = w
    lw = 0.085 * k

    def T(x, y):
        return (x0 + x * k, y0 + y * k)

    c.stroke([T(-0.25, 0.08), T(0.5, -0.42), T(1.25, 0.08)], lw, col)
    c.stroke([T(0.84, -0.12), T(0.84, -0.36), T(0.98, -0.36), T(0.98, -0.03)], lw * 0.75, col, caps=False)
    c.stroke([T(0.04, 0.0), T(0.04, 0.96), T(0.96, 0.96), T(0.96, 0.0)], lw, col)
    c.poly([T(0.20, 0.16), T(0.42, 0.16), T(0.42, 0.40), T(0.20, 0.40)], col)
    c.poly([T(0.58, 0.16), T(0.80, 0.16), T(0.80, 0.40), T(0.58, 0.40)], col)
    c.poly([T(0.58, 0.54), T(0.80, 0.54), T(0.80, 0.96), T(0.58, 0.96)], col)


def child_running(c, cx, cy, k, col):
    def T(x, y):
        return (cx + x * k, cy + y * k)

    c.circle(*T(0, -0.62), 0.16 * k, col)
    c.poly([T(-0.17, -0.40), T(0.17, -0.40), T(0.14, 0.10), T(-0.14, 0.10)], col)
    c.stroke([T(-0.12, -0.36), T(-0.40, -0.14), T(-0.58, -0.22)], 0.11 * k, col)
    c.stroke([T(0.12, -0.36), T(0.34, -0.22), T(0.46, -0.02)], 0.11 * k, col)
    c.stroke([T(-0.06, 0.08), T(-0.10, 0.48), T(-0.12, 0.78)], 0.14 * k, col)
    c.stroke([T(0.08, 0.08), T(0.36, 0.34), T(0.68, 0.30)], 0.14 * k, col)


def adult_walking(c, cx, cy, k, col):
    """Erwachsener (325.1), gehend nach rechts; Höhe ca. 2.2 k."""
    def T(x, y):
        return (cx + x * k, cy + y * k)

    c.circle(*T(0.05, -0.92), 0.17 * k, col)
    c.poly([T(-0.17, -0.66), T(-0.08, -0.74), T(0.16, -0.74), T(0.22, -0.64), T(0.18, -0.02), T(-0.14, -0.02)], col)
    c.stroke([T(-0.12, -0.60), T(-0.34, -0.24), T(-0.40, 0.0)], 0.13 * k, col)
    c.stroke([T(0.18, -0.58), T(0.30, -0.26), T(0.52, -0.16)], 0.13 * k, col)
    c.stroke([T(-0.06, 0.0), T(-0.28, 0.52), T(-0.46, 1.0)], 0.17 * k, col)
    c.stroke([T(0.10, 0.0), T(0.14, 0.50), T(0.14, 1.02)], 0.17 * k, col)


def worker(c, col):
    """Arbeitsstelle (123) im 900er-Dreieck."""
    c.circle(498, 352, 30, col)
    c.poly([(445, 384), (478, 382), (500, 404), (452, 522), (400, 512)], col)
    c.stroke([(456, 400), (402, 410), (382, 470)], 24, col)
    c.stroke([(484, 408), (510, 456), (548, 488)], 24, col)
    c.stroke([(394, 470), (474, 500), (620, 628)], 14, col)
    c.poly([(600, 600), (650, 630), (628, 660), (585, 630)], col)
    c.stroke([(418, 508), (372, 580), (352, 652)], 40, col)
    c.stroke([(352, 652), (330, 654)], 26, col)
    c.stroke([(440, 512), (468, 580), (476, 650)], 40, col)
    c.stroke([(476, 650), (500, 650)], 26, col)
    # Haufen
    pts = []
    for i in range(41):
        t = i / 40
        x = 585 + 170 * t
        y = 668 - 110 * math.sin(math.pi * t) ** 0.8
        pts.append((x, y))
    c.poly(pts + [(755, 668), (585, 668)], col)


# ---------------------------------------------------------------------------
# Zeichen
# ---------------------------------------------------------------------------
def z205(c):
    triangle_frame(c)


def z206(c):
    c.fill_shape(0, WHITE)
    c.fill_shape(12, RED)
    c.text("STOP", c.wmm / 2, c.hmm / 2, 0.34 * c.wmm, F_STOP, WHITE, max_w=0.80 * c.wmm)


def z306(c, end=False):
    c.fill_shape(0, WHITE)
    c.fill_shape(7, BLACK)
    c.fill_shape(15, WHITE)
    W = c.wmm
    cx = cy = W / 2
    a = 0.30 * W  # halbe Diagonale des gelben Quadrats
    o = 0.012 * W
    c.poly([(cx, cy - a - o * 1.41), (cx + a + o * 1.41, cy), (cx, cy + a + o * 1.41), (cx - a - o * 1.41, cy)], BLACK)
    c.poly([(cx, cy - a), (cx + a, cy), (cx, cy + a), (cx - a, cy)], YELLOW_306)
    if end:
        end_stripes(c, 15, n=5, lw=0.015 * W, pitch=0.034 * W, direction=(1, -1))


def z307(c):
    z306(c, end=True)


def z301(c):
    triangle_frame(c)
    W, H = c.wmm, c.hmm
    cx = W / 2
    bw = 0.078 * W  # halbe Balkenbreite
    top, bot = 0.40 * H, 0.83 * H
    c.poly([(cx, top), (cx + bw, top + bw), (cx + bw, bot), (cx, bot - bw), (cx - bw, bot), (cx - bw, top + bw)], BLACK)
    c.poly([(cx - 0.185 * W, 0.595 * H), (cx + 0.185 * W, 0.595 * H), (cx + 0.185 * W, 0.645 * H),
            (cx - 0.185 * W, 0.645 * H)], BLACK)


def z101(c):
    triangle_frame(c)
    W, H = c.wmm, c.hmm
    cx = W / 2
    c.poly([(cx - 0.040 * W, 0.37 * H), (cx + 0.040 * W, 0.37 * H), (cx + 0.026 * W, 0.70 * H),
            (cx - 0.026 * W, 0.70 * H)], BLACK)
    c.circle(cx, 0.37 * H, 0.040 * W, BLACK)
    c.circle(cx, 0.79 * H, 0.040 * W, BLACK)


def z123(c):
    triangle_frame(c)
    c.scaled(1.10, 430, 672)
    worker(c, BLACK)
    c.reset()


def z138(c):
    triangle_frame(c)
    bicycle(c, c.wmm / 2, 0.66 * c.hmm, 0.22 * c.wmm, BLACK)


def z131(c):
    triangle_frame(c)
    W, H = c.wmm, c.hmm
    cx = W / 2
    for y, col in ((0.42, RED), (0.585, YELLOW), (0.75, GREEN)):
        c.circle(cx, y * H, 0.056 * W, BLACK)
        c.circle(cx, y * H, 0.049 * W, col)


def speed(c, num, D=None, cx=None, cy=None, g=False):
    D = D or c.wmm
    cx = c.wmm / 2 if cx is None else cx
    cy = c.hmm / 2 if cy is None else cy
    ringc = GREY if g else RED
    numc = GREY if g else BLACK
    r = D / 2
    c.circle(cx, cy, r, WHITE)
    c.circle(cx, cy, r - 0.013 * D, ringc)
    c.circle(cx, cy, r - 0.013 * D - 0.115 * D, WHITE)
    c.text(str(num), cx, cy, 0.44 * D, F_DIN_B, numc, max_w=0.60 * D)


def z274(c, num):
    speed(c, num)


def z267(c):
    c.fill_shape(0, WHITE)
    c.fill_shape(8, RED)
    W = c.wmm
    c.poly([(0.12 * W, 0.415 * W), (0.88 * W, 0.415 * W), (0.88 * W, 0.585 * W), (0.12 * W, 0.585 * W)], WHITE)


def z250(c):
    round_prohibition(c)


def z283(c, single=False):
    W = c.wmm
    ring = 0.13 * W
    round_prohibition(c, ring=ring, inner=BLUE)
    cx = cy = W / 2
    lay, ld = c.layer()
    L = W
    bw = 0.115 * W
    dirs = [(1, 1)] if single else [(1, 1), (1, -1)]
    for dx, dy in dirs:
        n = math.hypot(dx, dy)
        dx, dy = dx / n, dy / n
        c.stroke([(cx - dx * L, cy - dy * L), (cx + dx * L, cy + dy * L)], bw, RED + (255,), d=ld, caps=False)
    c.composite(lay, c.shape_mask(8 + ring * 0.5))


def z286(c):
    z283(c, single=True)


def z237(c):
    round_blue(c)
    bicycle(c, c.wmm / 2, 0.56 * c.wmm, 0.25 * c.wmm, WHITE)


def z239(c):
    round_blue(c)
    woman_child(c, c.wmm / 2, c.wmm / 2 + 0.01 * c.wmm, 0.42 * c.wmm, WHITE)


def z240(c):
    round_blue(c)
    W = c.wmm
    woman_child(c, W / 2, 0.345 * W, 0.235 * W, WHITE)
    c.poly([(0.06 * W, 0.535 * W), (0.94 * W, 0.535 * W), (0.94 * W, 0.555 * W), (0.06 * W, 0.555 * W)], WHITE)
    bicycle(c, W / 2, 0.74 * W, 0.165 * W, WHITE)


def z224(c):
    W = c.wmm
    c.fill_shape(0, YELLOW)
    c.fill_shape(0.016 * W, GREEN)
    c.fill_shape(0.016 * W + 0.135 * W, YELLOW)
    cx = cy = W / 2
    hw, hh, sw = 0.19 * W, 0.26 * W, 0.068 * W
    c.poly([(cx - hw, cy - hh), (cx - hw + sw, cy - hh), (cx - hw + sw, cy + hh), (cx - hw, cy + hh)], GREEN)
    c.poly([(cx + hw - sw, cy - hh), (cx + hw, cy - hh), (cx + hw, cy + hh), (cx + hw - sw, cy + hh)], GREEN)
    c.poly([(cx - hw, cy - sw / 2), (cx + hw, cy - sw / 2), (cx + hw, cy + sw / 2), (cx - hw, cy + sw / 2)], GREEN)


def zone(c, kind, end=False):
    square_white_framed(c)
    W = c.wmm
    g = end
    if kind == "30":
        speed(c, 30, D=0.62 * W, cx=W / 2, cy=0.415 * W, g=g)
    else:
        col = GREY if g else BLUE
        c.circle(W / 2, 0.40 * W, 0.30 * W, col)
        woman_child(c, W / 2, 0.40 * W, 0.30 * W, WHITE)
    c.text("ZONE", W / 2, 0.835 * W, 0.15 * W, F_DIN, GREY if g else BLACK, max_w=0.56 * W, track=0.012 * W)
    if end:
        end_stripes(c, 10, n=5, lw=0.014 * W, pitch=0.030 * W, direction=(1, -1))


def z350(c):
    square_blue(c)
    c.poly([(300, 70), (551, 505), (49, 505)], WHITE)
    # Zebrastreifen
    for k in range(-2, 3):
        xt, xb = 300 + k * 78, 300 + k * 98
        wt, wb = 34, 44
        c.poly([(xt - wt / 2, 405), (xt + wt / 2, 405), (xb + wb / 2, 478), (xb - wb / 2, 478)], BLACK)
    k = 1.12
    pedestrian_walk(c, BLACK, k=k, ox=300 * (1 - k), oy=330 * (1 - k), outline_col=WHITE)


def z314(c):
    square_blue(c)
    W = c.wmm
    c.text("P", 0.52 * W, 0.5 * W, 0.70 * W, F_DIN, WHITE)


def z357(c):
    square_blue(c)
    W = c.wmm
    o = 0.013 * W
    c.poly([(0.436 * W, 0.37 * W), (0.564 * W, 0.37 * W), (0.564 * W, W), (0.436 * W, W)], WHITE)
    c.poly([(0.27 * W - o, 0.27 * W - o), (0.73 * W + o, 0.27 * W - o), (0.73 * W + o, 0.385 * W + o),
            (0.27 * W - o, 0.385 * W + o)], WHITE)
    c.poly([(0.27 * W, 0.27 * W), (0.73 * W, 0.27 * W), (0.73 * W, 0.385 * W), (0.27 * W, 0.385 * W)], RED)


def z220(c, right=True):
    c.fill_shape(0, WHITE)
    c.fill_shape(8, BLUE)
    W, H = c.wmm, c.hmm

    def X(x):
        return x if right else W - x

    shaft_t, shaft_b = 0.36 * H, 0.66 * H
    c.poly([(X(0.045 * W), shaft_t), (X(0.72 * W), shaft_t), (X(0.72 * W), shaft_b), (X(0.045 * W), shaft_b)], WHITE)
    c.poly([(X(0.69 * W), 0.10 * H), (X(0.955 * W), 0.51 * H), (X(0.69 * W), 0.92 * H)], WHITE)
    c.text("Einbahnstraße", X(0.38 * W), 0.515 * H, 0.17 * H, F_DIN, BLACK, max_w=0.64 * W)


def z325(c, end=False):
    c.fill_shape(0, WHITE)
    c.fill_shape(9, BLUE)
    W, H = c.wmm, c.hmm  # 900 x 600
    adult_walking(c, 0.185 * W, 0.60 * H, 0.30 * H, WHITE)
    car_front(c, 0.45 * W, 0.235 * H, 0.20 * W, WHITE, BLUE)
    house(c, 0.745 * W, 0.235 * H, 0.15 * W, WHITE)
    child_running(c, 0.56 * W, 0.735 * H, 0.235 * H, WHITE)
    c.circle(0.40 * W, 0.875 * H, 0.036 * H, WHITE)
    # Fahrbahnrand
    pts = []
    # Kurve: senkrecht nach unten, dann Bogen nach rechts unten
    for i in range(40):
        t = i / 39
        if t < 0.35:
            x = 0.625 * W
            y = 0.36 * H + t / 0.35 * 0.18 * H
        else:
            u = (t - 0.35) / 0.65
            ang = u * math.radians(55)
            rr = 0.16 * W
            x = 0.625 * W + rr * (1 - math.cos(ang))
            y = 0.54 * H + rr * math.sin(ang)
        pts.append((x, y))
    last = pts[-1]
    d = (math.cos(math.radians(35)), math.sin(math.radians(35)))
    pts.append((last[0] + d[0] * 0.14 * W, last[1] + d[1] * 0.14 * W))
    c.stroke(pts, 0.026 * W, WHITE)
    if end:
        lay, ld = c.layer()
        c.stroke([(-0.05 * W, 1.05 * H), (1.05 * W, -0.05 * H)], 0.06 * W, RED + (255,), d=ld, caps=False)
        c.composite(lay, c.shape_mask(9))


def z209(c):
    round_blue(c)
    W = c.wmm
    sw = 0.095 * W
    x0 = 0.355 * W
    pts = [(x0, 0.82 * W), (x0, 0.50 * W)]
    r = 0.16 * W
    cxr, cyr = x0 + r, 0.50 * W
    for i in range(1, 17):
        a = math.pi - (math.pi / 2) * i / 16
        pts.append((cxr + r * math.cos(a), cyr - r * math.sin(a)))
    pts.append((0.62 * W, cyr - r))
    c.stroke(pts, sw, WHITE, caps=False)
    y = cyr - r
    c.poly([(0.60 * W, y - 0.17 * W), (0.80 * W, y), (0.60 * W, y + 0.17 * W)], WHITE)


def z222(c):
    round_blue(c)
    W = c.wmm
    d = (math.sqrt(0.5), math.sqrt(0.5))
    a = (0.22 * W, 0.22 * W)
    tip = (0.76 * W, 0.76 * W)
    sw = 0.10 * W
    neck = (tip[0] - d[0] * 0.20 * W, tip[1] - d[1] * 0.20 * W)
    c.stroke([a, neck], sw, WHITE, caps=False)
    n = (-d[1], d[0])
    hw = 0.17 * W
    c.poly([tip, (neck[0] + n[0] * hw, neck[1] + n[1] * hw), (neck[0] - n[0] * hw, neck[1] - n[1] * hw)], WHITE)
    # Pfeilschaft-Ende gerade abschneiden (rechtwinklig)
    c.poly([(a[0] - n[0] * sw / 2, a[1] - n[1] * sw / 2), (a[0] + n[0] * sw / 2, a[1] + n[1] * sw / 2),
            (a[0] + n[0] * sw / 2 + d[0], a[1] + n[1] * sw / 2 + d[1])], WHITE)


# name, plate, Zeichenfunktion, Beschreibung
SIGNS = [
    ("205", "plate_triangle_down", z205, "Vorfahrt gewähren"),
    ("206", "plate_octagon", z206, "Halt! Vorfahrt gewähren (STOP)"),
    ("306", "plate_diamond", z306, "Vorfahrtstraße"),
    ("307", "plate_diamond", z307, "Ende der Vorfahrtstraße"),
    ("301", "plate_triangle", z301, "Vorfahrt an der nächsten Kreuzung"),
    ("101", "plate_triangle", z101, "Gefahrstelle"),
    ("123", "plate_triangle", z123, "Arbeitsstelle (Baustelle)"),
    ("138", "plate_triangle", z138, "Radverkehr"),
    ("131", "plate_triangle", z131, "Lichtzeichenanlage"),
    ("274_30", "plate_round", lambda c: z274(c, 30), "Zulässige Höchstgeschwindigkeit 30"),
    ("274_50", "plate_round", lambda c: z274(c, 50), "Zulässige Höchstgeschwindigkeit 50"),
    ("267", "plate_round", z267, "Verbot der Einfahrt"),
    ("250", "plate_round", z250, "Verbot für Fahrzeuge aller Art"),
    ("283", "plate_round", z283, "Absolutes Haltverbot"),
    ("286", "plate_round", z286, "Eingeschränktes Haltverbot"),
    ("237", "plate_round", z237, "Radweg"),
    ("240", "plate_round", z240, "Gemeinsamer Geh- und Radweg"),
    ("239", "plate_round", z239, "Gehweg"),
    ("224", "plate_round", z224, "Haltestelle"),
    ("274.1", "plate_square", lambda c: zone(c, "30"), "Beginn Tempo-30-Zone"),
    ("274.2", "plate_square", lambda c: zone(c, "30", end=True), "Ende Tempo-30-Zone"),
    ("242.1", "plate_square", lambda c: zone(c, "ped"), "Beginn Fußgängerzone"),
    ("242.2", "plate_square", lambda c: zone(c, "ped", end=True), "Ende Fußgängerzone"),
    ("350", "plate_square", z350, "Fußgängerüberweg"),
    ("314", "plate_square", z314, "Parken"),
    ("357", "plate_square", z357, "Sackgasse"),
    ("220", "plate_oneway", lambda c: z220(c, True), "Einbahnstraße, rechtsweisend"),
    ("220_links", "plate_oneway", lambda c: z220(c, False), "Einbahnstraße, linksweisend"),
    ("325.1", "plate_rect_wide", z325, "Beginn verkehrsberuhigter Bereich"),
    ("325.2", "plate_rect_wide", lambda c: z325(c, end=True), "Ende verkehrsberuhigter Bereich"),
    ("209", "plate_round", z209, "Vorgeschriebene Fahrtrichtung rechts"),
    ("222", "plate_round", z222, "Vorgeschriebene Vorbeifahrt rechts vorbei"),
]

SHAPE = {"plate_round": "round", "plate_triangle": "triangle", "plate_triangle_down": "triangle_down",
         "plate_octagon": "octagon", "plate_diamond": "diamond", "plate_square": "square",
         "plate_rect": "rect", "plate_rect_wide": "rect_wide", "plate_oneway": "rect_oneway"}


def main():
    atlas = Image.new("RGBA", (CELL * GRID[0], CELL * GRID[1]), (0, 0, 0, 0))
    cells = {}
    assert len(SIGNS) <= GRID[0] * GRID[1]
    for i, (name, plate, fn, desc) in enumerate(SIGNS):
        edge = YELLOW if name == "224" else WHITE
        c = Canvas(plate, edge=edge)
        fn(c)
        img = c.finish()
        col, row = i % GRID[0], i // GRID[0]
        atlas.paste(img, (col * CELL, row * CELL))
        p = PLATES[plate]
        cells[name] = {"index": i, "col": col, "row": row, "plate": plate, "shape": SHAPE[plate],
                       "size_m": [round(p["w"], 4), round(p["h"], 4)], "desc": desc}
    # Leere Bereiche außerhalb der Formen: Farbe der Nachbarpixel behalten (Alpha 0) -> kein Saum bei Mipmaps
    atlas.save(os.path.join(OUT_DIR, "traffic_signs.png"), optimize=True)
    meta = {
        "texture": "res://assets/textures/street/traffic_signs.png",
        "grid": list(GRID), "cell_px": CELL,
        "layout": "Zellindex i: Spalte i % 8, Zeile i // 8, Zeile 0 oben. UV 0..1 der Schildfläche = ganze Zelle "
                  "(Godot-UV.y=0 oben). Inhalt ist auf das Seitenverhältnis der Platte vorverzerrt. Alpha = Umriss "
                  "(Kante weich, RGB außerhalb = Randfarbe).",
        "source": "selbst gezeichnet nach amtlicher Gestaltung (VzKat/StVO, amtliche Werke § 5 UrhG); "
                  "Schrift Noto Sans SemiCondensed (OFL)",
        "cells": cells,
    }
    with open(os.path.join(OUT_DIR, "traffic_signs.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print("ok", len(cells), "Zeichen")


if __name__ == "__main__":
    main()
