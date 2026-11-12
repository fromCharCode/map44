"""Selbst gezeichnete Texturen für die DVB-Haltestellenausstattung (PIL, deterministisch).

Aufruf:  .venv/bin/python tools/blender/stops/make_stop_textures.py
Ausgabe: tools/blender/stops/tex/
  dvb_sign.png    1024 x 1024 Atlas (Material SignPrint):
                  - Kopf der Haltestellenfahne (weiß, gelber Schwung unten rechts, Zeichen 224: gelbe Scheibe,
                    grüner Ring, grünes H, schmaler gelber Außenrand) + gelbes Namensfeld mit Trennlinie unten
                  - Fußzeile (gelb, Schriftzug DVB / VVO in Noto Sans Bold, keine Logos)
                  - Fahrplanaushang A4 (frei erfundener Platzhalter, keine echten Daten)
  dfi_panel.png   Uhrfeld der großen Abfahrtstafel (gelb, Analoguhr 10:10, Schriftzug DVB)
  info_board.png  Infovitrine in der Wartehalle (Kopf „Information“, abstrakter Netzplan, Aushänge)
Die Regionen (Pixel und Meter) stehen in REGIONS und werden von build_stops.py identisch verwendet.
Farben: Recherchebericht data/research/dvb_haltestellen.md (A1/A2/A3), Grün an Fotos geprüft (Farbton ≈ 160°,
deckt sich mit RAL 6024 Verkehrsgrün; Albedo leicht aufgehellt).
"""
import math
import os
import random

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "tex")
N = "/usr/share/fonts/google-noto/"
F_BOLD = N + "NotoSans-Bold.ttf"
F_SEMI = N + "NotoSans-SemiBold.ttf"
F_REG = N + "NotoSans-Regular.ttf"
F_CB = N + "NotoSans-CondensedBold.ttf"

YELLOW = "#F2B01E"      # DVB-Schildgelb (≈ RAL 1003/1023)
GREEN = "#0A8A62"       # Zeichen 224, RAL 6024 Verkehrsgrün (Albedo)
WHITE = "#F2F2F2"
INK = "#1A1A1A"
GREY_TXT = "#4A4A4A"

# --- Maße der Fahne (müssen zu build_stops.py passen) ----------------------------------------------------------
PANEL_W = 0.556          # Schildplatte zwischen den Rahmenrohren (bis unter die Rohrmitte)
HIDE = 0.008             # Streifen, der unter dem Rahmenrohr verschwindet (oben/unten)
HEAD_WHITE = 0.43        # sichtbarer weißer Kopf
NAME_H = 0.18            # Namensfeld
FOOT_H = 0.09            # Fußzeile (sichtbar)
SEP = 0.004              # Trennlinie zwischen Modulen
S = 1100.0               # px/m für Kopf und Fußzeile
S_A4 = 1500.0            # px/m für den Fahrplanaushang
HEAD_PANEL_H = HIDE + HEAD_WHITE + NAME_H            # 0.618
FOOT_PANEL_H = FOOT_H + HIDE                          # 0.098

ATLAS = 1024
REGIONS = {
    # name: (x0, y0, breite_px, hoehe_px) im Atlas (y nach unten)
    "head": (0, 0, round(PANEL_W * S), round(HEAD_PANEL_H * S)),
    "foot": (0, 700, round(PANEL_W * S), round(FOOT_PANEL_H * S)),
    "a4": (640, 0, round(0.210 * S_A4), round(0.297 * S_A4)),
}
SS = 3                   # Supersampling


def font(path, px):
    return ImageFont.truetype(path, max(4, int(px)))


class Canvas:
    """Zeichenfläche in Metern (x nach rechts, y nach unten) mit Supersampling."""

    def __init__(self, w_m, h_m, scale, bg):
        self.s = scale * SS
        self.im = Image.new("RGB", (round(w_m * self.s), round(h_m * self.s)), bg)
        self.d = ImageDraw.Draw(self.im)

    def p(self, x, y):
        return (x * self.s, y * self.s)

    def rect(self, x0, y0, x1, y1, col):
        self.d.rectangle([*self.p(x0, y0), *self.p(x1, y1)], fill=col)

    def circle(self, cx, cy, r, col):
        self.d.ellipse([*self.p(cx - r, cy - r), *self.p(cx + r, cy + r)], fill=col)

    def poly(self, pts, col):
        self.d.polygon([self.p(x, y) for x, y in pts], fill=col)

    def text(self, x, y, s, path, cap_m, col, anchor="ls"):
        # cap_m = Versalhöhe in Metern; Noto: Versalhöhe ≈ 0.714 * Schriftgröße
        f = font(path, cap_m / 0.714 * self.s)
        self.d.text(self.p(x, y), s, font=f, fill=col, anchor=anchor)

    def done(self, w_px, h_px):
        return self.im.resize((w_px, h_px), Image.LANCZOS)


def sign_head():
    W, H = PANEL_W, HEAD_PANEL_H
    c = Canvas(W, H, S, YELLOW)
    yw = HIDE + HEAD_WHITE
    # weißer Kopf mit gelbem Schwung nach unten rechts (Grenze steigt nach rechts an)
    pts = [(0.0, 0.0), (W, 0.0)]
    n = 40
    for i in range(n + 1):
        t = 1.0 - i / n
        x = W * t
        y = yw - 0.135 * t ** 1.8
        pts.append((x, y))
    c.poly(pts, WHITE)
    # Zeichen 224: gelber Außenrand, grüner Ring, gelbe Scheibe, grünes H
    cx, cy = W / 2 - 0.004, HIDE + 0.218
    c.circle(cx, cy, 0.177, YELLOW)
    c.circle(cx, cy, 0.170, GREEN)
    c.circle(cx, cy, 0.124, YELLOW)
    hh, hw, st, cb = 0.165, 0.128, 0.034, 0.032
    c.rect(cx - hw / 2, cy - hh / 2, cx - hw / 2 + st, cy + hh / 2, GREEN)
    c.rect(cx + hw / 2 - st, cy - hh / 2, cx + hw / 2, cy + hh / 2, GREEN)
    c.rect(cx - hw / 2, cy - cb / 2, cx + hw / 2, cy + cb / 2, GREEN)
    # Trennlinie unter dem Namensfeld
    c.rect(0, H - SEP, W, H, INK)
    return c.done(REGIONS["head"][2], REGIONS["head"][3])


def sign_foot():
    W, H = PANEL_W, FOOT_PANEL_H
    c = Canvas(W, H, S, YELLOW)
    base = FOOT_H * 0.70
    c.text(0.035, base, "DVB", F_BOLD, 0.030, INK)
    c.text(0.142, base - 0.012, "Ihr Partner", F_REG, 0.0075, INK)
    c.text(0.142, base, "im Verbund", F_REG, 0.0075, INK)
    c.text(W - 0.035, base, "VVO", F_BOLD, 0.030, INK, anchor="rs")
    return c.done(REGIONS["foot"][2], REGIONS["foot"][3])


def timetable_a4(seed=3):
    rnd = random.Random(seed)
    W, H = 0.210, 0.297
    c = Canvas(W, H, S_A4, "#F7F6F1")
    # Kopf gelb-orange mit Liniennummer und Haltestellenzeile
    c.rect(0, 0, W, 0.040, "#F2A41E")
    c.rect(0.008, 0.007, 0.046, 0.033, WHITE)
    c.text(0.027, 0.028, "62", F_BOLD, 0.016, INK, anchor="ms")
    c.text(0.054, 0.018, "Haltestelle", F_SEMI, 0.0055, INK)
    c.text(0.054, 0.030, "Richtung", F_REG, 0.0045, INK)
    c.rect(0, 0.040, W, 0.0425, INK)
    # drei Spalten (Mo–Fr, Sa, So) mit Stundenzeilen
    cols = [(0.008, 0.098), (0.102, 0.152), (0.156, 0.202)]
    y = 0.050
    for x0, x1 in cols:
        c.rect(x0, y, x1, y + 0.007, "#D9D6CB")
    y += 0.011
    for hour in range(5, 24):
        if hour % 2 == 0:
            c.rect(0.008, y - 0.001, 0.202, y + 0.0095, "#ECEAE2")
        c.text(0.010, y + 0.007, "%02d" % hour, F_BOLD, 0.0045, INK)
        for x0, x1 in cols:
            xs = x0 + (0.012 if x0 < 0.01 else 0.002)
            k = rnd.randint(2, 6) if x0 < 0.01 else rnd.randint(1, 3)
            for j in range(k):
                xx = xs + j * 0.0125
                if xx + 0.009 < x1:
                    c.text(xx, y + 0.007, "%02d" % rnd.randint(0, 59), F_REG, 0.0038, GREY_TXT)
        y += 0.0105
    # Fußbereich: Haltestellenfolge und Kleingedrucktes als Linien
    y += 0.004
    c.rect(0.008, y, 0.202, y + 0.0008, INK)
    y += 0.006
    for i in range(6):
        c.rect(0.010, y, 0.010 + rnd.uniform(0.06, 0.18), y + 0.002, "#9A978E")
        y += 0.0045
    return c.done(REGIONS["a4"][2], REGIONS["a4"][3])


def sign_atlas():
    im = Image.new("RGB", (ATLAS, ATLAS), YELLOW)
    for key, fn in (("head", sign_head), ("foot", sign_foot), ("a4", timetable_a4)):
        x0, y0, w, h = REGIONS[key]
        im.paste(fn(), (x0, y0))
    im.save(os.path.join(OUT, "dvb_sign.png"))


def dfi_panel():
    """Gelbes Uhrfeld der großen Tafel: 0.54 x 0.72 m (Textur 384 x 512, leicht gestreckt ok)."""
    W, H = 0.54, 0.72
    c = Canvas(W, H, 640.0, YELLOW)
    cx, cy, r = W / 2, 0.25, 0.14
    c.circle(cx, cy, r + 0.008, "#2A2A2A")
    c.circle(cx, cy, r, "#F4F4F0")
    for i in range(60):
        a = math.radians(i * 6)
        big = i % 5 == 0
        r0 = r - (0.030 if big else 0.012)
        w = 0.009 if big else 0.003
        x0, y0 = cx + math.sin(a) * r0, cy - math.cos(a) * r0
        x1, y1 = cx + math.sin(a) * (r - 0.006), cy - math.cos(a) * (r - 0.006)
        c.d.line([c.p(x0, y0), c.p(x1, y1)], fill=INK, width=max(1, int(w * c.s)))

    def hand(deg, length, width, col):
        a = math.radians(deg)
        dx, dy = math.sin(a), -math.cos(a)
        nx, ny = -dy, dx
        tail = 0.025
        pts = [(cx - dx * tail + nx * width, cy - dy * tail + ny * width),
               (cx + dx * length + nx * width * 0.5, cy + dy * length + ny * width * 0.5),
               (cx + dx * length - nx * width * 0.5, cy + dy * length - ny * width * 0.5),
               (cx - dx * tail - nx * width, cy - dy * tail - ny * width)]
        c.poly(pts, col)

    hand(10 * 30 + 10 * 0.5, 0.085, 0.009, INK)     # 10:10
    hand(10 * 6, 0.125, 0.006, INK)
    c.circle(cx, cy, 0.008, INK)
    c.text(W - 0.05, 0.66, "DVB", F_BOLD, 0.034, INK, anchor="rs")
    im = c.done(384, 512)
    im.save(os.path.join(OUT, "dfi_panel.png"))


def info_board(seed=7):
    """Infovitrine an der Hallenrückwand, sichtbare Fläche 0.92 x 0.68 m."""
    rnd = random.Random(seed)
    W, H = 0.92, 0.68
    c = Canvas(W, H, 900.0, "#E9E6DC")
    c.rect(0, 0, W, 0.075, "#F2A93B")
    c.text(0.03, 0.055, "Information", F_SEMI, 0.028, INK)
    c.text(W - 0.03, 0.055, "DVB", F_BOLD, 0.030, INK, anchor="rs")
    # abstrakter Liniennetzplan (frei erfunden)
    mx0, my0, mx1, my1 = 0.03, 0.10, 0.44, 0.40
    c.rect(mx0, my0, mx1, my1, "#FBFAF6")
    cols = ["#D7262E", "#1E64B0", "#2E9A48", "#F2A41E", "#8E3A97", "#00A3C4", "#6B6B6B"]
    for k, col in enumerate(cols):
        pts = []
        x, y = mx0 + 0.02, my0 + 0.03 + k * 0.035
        for i in range(7):
            pts.append((x, y))
            x += rnd.uniform(0.04, 0.07)
            y += rnd.choice((-0.03, 0.0, 0.0, 0.03))
            x = min(x, mx1 - 0.02)
            y = min(max(y, my0 + 0.02), my1 - 0.02)
        c.d.line([c.p(*q) for q in pts], fill=col, width=int(0.006 * c.s), joint="curve")
        for q in pts[::2]:
            c.circle(q[0], q[1], 0.005, "#FFFFFF")
    # Aushänge (A4-Platzhalter), zwei Reihen
    for row, (y0, kinds) in enumerate(((0.10, 2), (0.43, 6))):
        if row == 0:
            xs = [0.47, 0.70]
            w, h = 0.20, 0.29
        else:
            xs = [0.03 + i * 0.148 for i in range(6)]
            w, h = 0.135, 0.22
        for x in xs:
            head = rnd.choice(("#F2A41E", "#E8742A", "#FFFFFF", "#F2A41E"))
            c.rect(x, y0, x + w, y0 + h, "#FCFCF8")
            c.rect(x, y0, x + w, y0 + h * 0.12, head)
            yy = y0 + h * 0.18
            while yy < y0 + h - 0.012:
                c.rect(x + 0.01, yy, x + 0.01 + rnd.uniform(0.4, 0.92) * (w - 0.02), yy + 0.003, "#A7A49B")
                yy += 0.009
    im = c.done(736, 544)
    im.save(os.path.join(OUT, "info_board.png"))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    sign_atlas()
    dfi_panel()
    info_board()
    print("Texturen geschrieben:", OUT, REGIONS)
