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
  shelter_posters.png  vier frei erfundene City-Light-Plakate (2 x 2, je 512 x 768), keine Marken
  glass_marks.png      Kontrastmarkierung für Glasflächen (RGBA, Reihe weißer Quadrate)
  bench_wood.png       Lärchenlatten der Sitzbank
  ticket_front.png     Front des Fahrkartenautomaten (Bildschirm, Tastenfeld, Zahlfelder, Entnahme)
Zusätzlich direkt nach godot/assets/models/stops/ (von stops.gd geladen):
  platform_tactile.png/_n.png  Rillenplatte des Leitstreifens, platform_edge.png  Betonband an der Bahnsteigkante
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


# --- Plakate der City-Light-Vitrine (frei erfundene Motive, keine Marken) --------------------------------------
PW_PX, PH_PX = 512, 768          # je Plakat (4/1-Bogen 1,19 x 1,75 m)


def _grad(w, h, top, bot):
    im = Image.new("RGB", (w, h))
    t = [int(top[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(bot[i:i + 2], 16) for i in (1, 3, 5)]
    px = im.load()
    for y in range(h):
        q = y / (h - 1)
        col = tuple(int(t[i] + (b[i] - t[i]) * q) for i in range(3))
        for x in range(w):
            px[x, y] = col
    return im


def _ctext(d, x, y, s, path, px, col, anchor="ms"):
    d.text((x, y), s, font=font(path, px), fill=col, anchor=anchor)


def poster_konzert(rnd):
    S2 = 2
    w, h = PW_PX * S2, PH_PX * S2
    im = _grad(w, h, "#2B1B4A", "#F08A3C")
    d = ImageDraw.Draw(im)
    d.ellipse([w * 0.30, h * 0.30, w * 0.70, h * 0.30 + w * 0.40], fill="#FFD27A")
    for k in range(5):                                   # Hügel- und Uferlinien
        y0 = h * (0.50 + 0.05 * k)
        pts = [(0, h)]
        for i in range(0, 21):
            x = w * i / 20
            pts.append((x, y0 + math.sin(i * 0.6 + k * 1.7) * h * 0.018 + k * 4))
        pts.append((w, h))
        shade = (40 - k * 6, 26 - k * 3, 62 - k * 8)
        d.polygon(pts, fill=shade)
    for i in range(60):                                  # Lichter am Ufer
        x, y = rnd.uniform(0, w), rnd.uniform(h * 0.58, h * 0.70)
        r = rnd.uniform(1.5, 4) * S2
        d.ellipse([x - r, y - r, x + r, y + r], fill="#FFE9B0")
    _ctext(d, w / 2, h * 0.13, "ELBSOMMER", F_CB, 150 * S2 / 1.6, "#FFF4DE")
    _ctext(d, w / 2, h * 0.185, "Open-Air-Konzerte am Fluss", F_SEMI, 34 * S2 / 1.3, "#FFE0B0")
    d.rectangle([w * 0.12, h * 0.80, w * 0.88, h * 0.925], fill="#FFF4DE")
    _ctext(d, w / 2, h * 0.855, "12.–28. Juli", F_BOLD, 60 * S2 / 1.3, "#2B1B4A")
    _ctext(d, w / 2, h * 0.905, "täglich ab 19 Uhr · Eintritt frei", F_REG, 26 * S2 / 1.3, "#2B1B4A")
    return im.resize((PW_PX, PH_PX), Image.LANCZOS)


def poster_markt(rnd):
    S2 = 2
    w, h = PW_PX * S2, PH_PX * S2
    im = Image.new("RGB", (w, h), "#F4EEDC")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w, h * 0.52], fill="#2F7D4F")
    cols = ["#D8372E", "#F2A41E", "#E8742A", "#8DB33A", "#B8284A", "#F6D14A"]
    for i in range(26):                                  # Obst und Gemüse als Kreise
        x, y = rnd.uniform(0.06, 0.94) * w, rnd.uniform(0.30, 0.58) * h
        r = rnd.uniform(0.045, 0.085) * w
        col = rnd.choice(cols)
        d.ellipse([x - r, y - r, x + r, y + r], fill=col)
        d.ellipse([x - r * 0.55, y - r * 0.6, x - r * 0.15, y - r * 0.2], fill="#FFFFFF")
        d.line([x, y - r, x + r * 0.2, y - r * 1.25], fill="#3B2A1A", width=int(4 * S2))
    _ctext(d, w / 2, h * 0.12, "Frisch.", F_BOLD, 110 * S2 / 1.3, "#F4EEDC")
    _ctext(d, w / 2, h * 0.215, "Regional.", F_BOLD, 110 * S2 / 1.3, "#F6D14A")
    _ctext(d, w / 2, h * 0.72, "Wochenmarkt", F_CB, 120 * S2 / 1.5, "#2F7D4F")
    _ctext(d, w / 2, h * 0.79, "jeden Samstag 8–14 Uhr", F_SEMI, 40 * S2 / 1.3, "#333333")
    d.rectangle([w * 0.2, h * 0.84, w * 0.8, h * 0.845], fill="#2F7D4F")
    _ctext(d, w / 2, h * 0.90, "auf dem Marktplatz", F_REG, 32 * S2 / 1.3, "#555555")
    return im.resize((PW_PX, PH_PX), Image.LANCZOS)


def poster_bibliothek(rnd):
    S2 = 2
    w, h = PW_PX * S2, PH_PX * S2
    im = Image.new("RGB", (w, h), "#12355B")
    d = ImageDraw.Draw(im)
    x = w * 0.08                                          # Bücherregal
    cols = ["#E8B04A", "#C9482E", "#3E8E7E", "#E9E2D0", "#7A4C8F", "#D97B29", "#5C88B8"]
    while x < w * 0.92:
        bw = rnd.uniform(0.035, 0.075) * w
        bh = rnd.uniform(0.20, 0.30) * h
        col = rnd.choice(cols)
        d.rectangle([x, h * 0.70 - bh, x + bw, h * 0.70], fill=col)
        d.rectangle([x + bw * 0.2, h * 0.70 - bh * 0.85, x + bw * 0.8, h * 0.70 - bh * 0.78], fill="#12355B")
        x += bw + 3 * S2
    d.rectangle([w * 0.05, h * 0.70, w * 0.95, h * 0.715], fill="#E9E2D0")
    _ctext(d, w * 0.08, h * 0.13, "Lies mal", F_BOLD, 120 * S2 / 1.3, "#E9E2D0", anchor="ls")
    _ctext(d, w * 0.08, h * 0.24, "wieder.", F_BOLD, 120 * S2 / 1.3, "#E8B04A", anchor="ls")
    _ctext(d, w * 0.08, h * 0.82, "Deine Stadtbibliothek", F_SEMI, 44 * S2 / 1.3, "#E9E2D0", anchor="ls")
    _ctext(d, w * 0.08, h * 0.875, "Ausweis kostenlos bis 18 Jahre", F_REG, 30 * S2 / 1.3, "#B9C7D8", anchor="ls")
    return im.resize((PW_PX, PH_PX), Image.LANCZOS)


def poster_bahn(rnd):
    S2 = 2
    w, h = PW_PX * S2, PH_PX * S2
    im = Image.new("RGB", (w, h), "#F2B01E")
    d = ImageDraw.Draw(im)
    for k in range(9):                                    # Strahlen
        a0 = math.radians(200 + k * 16)
        a1 = math.radians(208 + k * 16)
        d.polygon([(w / 2, h * 0.62), (w / 2 + math.cos(a0) * w * 2, h * 0.62 + math.sin(a0) * w * 2),
                   (w / 2 + math.cos(a1) * w * 2, h * 0.62 + math.sin(a1) * w * 2)], fill="#F6C24A")
    # stilisierte Bahn von vorn (ohne Vorbild)
    bx0, bx1, by0, by1 = w * 0.27, w * 0.73, h * 0.36, h * 0.70
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=int(w * 0.07), fill="#1A1A1A")
    d.rounded_rectangle([bx0 + w * 0.04, by0 + h * 0.03, bx1 - w * 0.04, by0 + h * 0.17], radius=int(w * 0.03),
                        fill="#9CC7DD")
    d.rectangle([bx0 + w * 0.10, by0 + h * 0.005, bx1 - w * 0.10, by0 + h * 0.024], fill="#FFA51F")
    for xx in (bx0 + w * 0.07, bx1 - w * 0.07):
        d.ellipse([xx - w * 0.025, by1 - h * 0.07, xx + w * 0.025, by1 - h * 0.07 + w * 0.05], fill="#FFF4DE")
    d.rectangle([w * 0.10, by1, w * 0.90, by1 + h * 0.012], fill="#1A1A1A")
    d.line([w / 2, by0, w / 2 - w * 0.05, by0 - h * 0.07, w / 2 + w * 0.05, by0 - h * 0.12], fill="#1A1A1A",
           width=int(5 * S2))
    _ctext(d, w / 2, h * 0.14, "Einsteigen.", F_BOLD, 100 * S2 / 1.3, "#1A1A1A")
    _ctext(d, w / 2, h * 0.225, "Ankommen.", F_BOLD, 100 * S2 / 1.3, "#FFFFFF")
    _ctext(d, w / 2, h * 0.83, "Alle 10 Minuten durch die Stadt", F_SEMI, 38 * S2 / 1.3, "#1A1A1A")
    _ctext(d, w / 2, h * 0.89, "Bus und Bahn – auch nachts", F_REG, 30 * S2 / 1.3, "#3A3A3A")
    return im.resize((PW_PX, PH_PX), Image.LANCZOS)


def posters():
    """Atlas 1024 x 1536 mit vier Plakaten (2 x 2); Zelle (i, j): u0 = i/2, v von oben j/2."""
    rnd = random.Random(21)
    im = Image.new("RGB", (PW_PX * 2, PH_PX * 2), "#FFFFFF")
    for k, fn in enumerate((poster_konzert, poster_markt, poster_bibliothek, poster_bahn)):
        im.paste(fn(rnd), ((k % 2) * PW_PX, (k // 2) * PH_PX))
    im.save(os.path.join(OUT, "shelter_posters.png"))


def glass_marks():
    """Kontrastmarkierung auf Glasflächen: Reihe weißer Quadrate (RGBA), kachelbar in u; 1 Kachel = 0,20 m."""
    im = Image.new("RGBA", (128, 32), (255, 255, 255, 0))
    d = ImageDraw.Draw(im)
    for i in range(4):
        d.rectangle([i * 32 + 5, 5, i * 32 + 26, 26], fill=(245, 247, 248, 215))
    im.save(os.path.join(OUT, "glass_marks.png"))


def bench_wood():
    """Holzlatten (Lärche, geölt), Maserung längs u; kachelbar."""
    import numpy as np
    rs = np.random.RandomState(5)
    h, w = 128, 512
    base = np.array([150, 104, 62], dtype=np.float32)
    grain = np.zeros((h, w), dtype=np.float32)
    for _ in range(90):
        y = rs.randint(0, h)
        amp = rs.uniform(-18, 14)
        ph = rs.uniform(0, 6.28)
        fr = rs.choice([1, 2, 3])
        xs = np.arange(w)
        yy = (y + 2.5 * np.sin(xs * 2 * math.pi * fr / w + ph)).astype(int) % h
        grain[yy, xs] += amp
        grain[(yy + 1) % h, xs] += amp * 0.5
    grain += rs.normal(0, 3.0, (h, w))
    img = np.clip(base[None, None, :] + grain[:, :, None] * np.array([1.0, 0.8, 0.55]), 0, 255).astype("uint8")
    Image.fromarray(img, "RGB").save(os.path.join(OUT, "bench_wood.png"))


def ticket_front():
    """Front des Fahrkartenautomaten 0,50 x 1,30 m (Bildschirm, Tasten, Zahlfelder, Ausgabeschacht), frei gestaltet."""
    W, H = 0.50, 1.30
    c = Canvas(W, H, 600.0, "#8D9296")
    c.rect(0, 0, W, 0.11, "#F2B01E")
    c.text(0.03, 0.078, "Fahrkarten", F_BOLD, 0.040, INK)
    c.text(W - 0.03, 0.078, "Tickets", F_REG, 0.026, "#3A3A3A", anchor="rs")
    # Bildschirm
    c.rect(0.045, 0.15, W - 0.045, 0.50, "#15181B")
    c.rect(0.06, 0.165, W - 0.06, 0.485, "#1E3C5A")
    c.rect(0.06, 0.165, W - 0.06, 0.215, "#F2B01E")
    c.text(0.075, 0.202, "Bitte Ziel wählen", F_SEMI, 0.020, INK)
    labels = ["Einzelfahrt", "4er-Karte", "Tageskarte", "Kurzstrecke", "Familie", "Fahrrad"]
    for i, lb in enumerate(labels):
        x0 = 0.075 + (i % 2) * 0.18
        y0 = 0.235 + (i // 2) * 0.078
        c.rect(x0, y0, x0 + 0.165, y0 + 0.062, "#E9EEF2")
        c.text(x0 + 0.0825, y0 + 0.040, lb, F_SEMI, 0.016, "#1E3C5A", anchor="ms")
    # Zahlbereich: Kartenleser, Münzeinwurf, Scheine
    c.rect(0.045, 0.56, 0.22, 0.80, "#2A2D30")
    for r in range(4):
        for q in range(3):
            c.rect(0.06 + q * 0.05, 0.575 + r * 0.054, 0.06 + q * 0.05 + 0.038, 0.575 + r * 0.054 + 0.04, "#C9CCCE")
    c.rect(0.07, 0.535, 0.20, 0.552, "#0C0D0E")
    c.rect(0.27, 0.56, W - 0.045, 0.66, "#2A2D30")
    c.rect(0.29, 0.605, W - 0.065, 0.615, "#0C0D0E")
    c.text(0.275, 0.59, "Scheine", F_REG, 0.012, "#D8DADB")
    c.rect(0.27, 0.69, W - 0.045, 0.80, "#2A2D30")
    c.circle(0.40, 0.745, 0.028, "#B9BCBF")
    c.rect(0.397, 0.725, 0.403, 0.765, "#0C0D0E")
    c.text(0.275, 0.715, "Münzen", F_REG, 0.012, "#D8DADB")
    # Ausgabeschacht
    c.rect(0.07, 0.90, W - 0.07, 1.10, "#101113")
    c.rect(0.085, 0.915, W - 0.085, 1.085, "#1B1D20")
    c.text(W / 2, 0.885, "Entnahme", F_REG, 0.014, "#2A2D30", anchor="ms")
    c.rect(0.045, 1.16, W - 0.045, 1.24, "#F2F2F2")
    c.text(W / 2, 1.212, "Hilfe und Auskunft: Sprechtaste drücken", F_REG, 0.011, "#333333", anchor="ms")
    im = c.done(320, 832)
    im.save(os.path.join(OUT, "ticket_front.png"))


def platform_textures():
    """Bodenplatten für stops.gd (direkt nach godot/assets/models/stops/):
    platform_tactile.png  Rillenplatte 0,30 m, Rillen längs u (u = Laufrichtung, 1 Kachel = 0,30 m)
    platform_tactile_n.png Normalmap dazu
    platform_edge.png     helles Betonband mit Bordsteinfuge (1 Kachel = 1,0 m längs u, v = 0 Kante … 1 innen)"""
    import numpy as np
    dst = os.path.abspath(os.path.join(HERE, "..", "..", "..", "godot", "assets", "models", "stops"))
    rs = np.random.RandomState(11)
    n = 256
    v = np.arange(n) / n
    ribs = 0.5 + 0.5 * np.cos(v * 2 * math.pi * 8)          # 8 Rippen je Platte
    hgt = np.repeat(np.clip(ribs * 1.6 - 0.3, 0, 1)[:, None], n, axis=1)
    hgt[:, :3] = 0
    hgt[:, -3:] = 0                                         # Plattenfuge
    noise = rs.normal(0, 5.0, (n, n))
    alb = 176 + hgt * 28 + noise
    alb[:, :3] -= 45
    alb[:, -3:] -= 45
    col = np.clip(np.stack([alb, alb * 0.985, alb * 0.96], axis=2), 0, 255).astype("uint8")
    Image.fromarray(col, "RGB").save(os.path.join(dst, "platform_tactile.png"))
    dy = np.gradient(hgt, axis=0) * 6.0
    dx = np.gradient(hgt, axis=1) * 6.0
    nz = np.ones_like(dx)
    ln = np.sqrt(dx * dx + dy * dy + nz * nz)
    nrm = np.stack([(-dx / ln) * 0.5 + 0.5, (dy / ln) * 0.5 + 0.5, (nz / ln) * 0.5 + 0.5], axis=2)
    Image.fromarray((nrm * 255).astype("uint8"), "RGB").save(os.path.join(dst, "platform_tactile_n.png"))
    # Betonband: Bordstein (v < 0.45) + Platte, Fugen
    w, h = 512, 256
    g = 168 + rs.normal(0, 6.0, (h, w))
    blot = rs.normal(0, 1.0, (h // 16, w // 16))
    blot = np.kron(blot, np.ones((16, 16))) * 5.0
    g = g + blot
    g[: int(h * 0.42), :] += 10                              # Bordstein etwas heller
    g[int(h * 0.42) - 2: int(h * 0.42) + 2, :] -= 50          # Längsfuge Bord/Platte
    g[:, :3] -= 50
    g[:, -3:] -= 50                                          # Stoßfuge je Meter
    g[int(h * 0.42):, w // 2 - 2: w // 2 + 2] -= 40          # Platten 0,5 m
    g[:6, :] -= 18                                           # Kante leicht verschmutzt
    col = np.clip(np.stack([g, g * 0.99, g * 0.965], axis=2), 0, 255).astype("uint8")
    Image.fromarray(col, "RGB").save(os.path.join(dst, "platform_edge.png"))



if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    sign_atlas()
    dfi_panel()
    info_board()
    posters()
    glass_marks()
    bench_wood()
    ticket_front()
    platform_textures()
    print("Texturen geschrieben:", OUT, REGIONS)
