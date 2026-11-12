"""Kleine Texturen für die Straßenmodelle (Straßennamensschild, Haltestellenschild, Fahrplanaushang).

Aufruf:  .venv/bin/python tools/blender/make_street_textures.py
Ausgabe: godot/assets/textures/street/street_sign.png   512 x 128  (Dresdner Straßenschild, dunkelblau Email, weiße Linie)
         godot/assets/textures/street/stop_sign.png     256 x 512  (Haltestellen-Fahne gelb, H-Zeichen 224, Felder leer)
         godot/assets/textures/street/timetable.png     256 x 352  (Fahrplanaushang, unleserliche Tabellen)
"""
import os
import random

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "godot", "assets", "textures", "street")

NAVY = (26, 40, 104)           # gemessen an Fotos Dresdner Straßenschilder (Email, ultramarin-dunkelblau)
WHITE = (242, 242, 238)
YELLOW = (240, 202, 0)         # RAL 1023
GREEN = (0, 135, 84)           # RAL 6024
BLACK = (24, 24, 24)
SS = 4


def noise_overlay(im, amount, blur=0.8, seed=1):
    random.seed(seed)
    n = Image.effect_noise(im.size, 30).filter(ImageFilter.GaussianBlur(blur))
    return Image.blend(im, Image.merge("RGB", (n, n, n)), amount)


def street_sign():
    W, H = 512 * SS, 128 * SS
    im = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(im)
    # leichte Wölbung/Glanz des Emailschilds: oben heller, unten dunkler
    for y in range(H):
        t = y / (H - 1)
        k = 1.10 - 0.18 * t
        d.line([(0, y), (W, y)], fill=tuple(min(255, round(c * k)) for c in NAVY))
    # weiße Zierlinie innen (ca. 1,2 cm vom Rand, 0,6 cm breit bei 0,90 x 0,22 m)
    s = W / 0.90  # px pro Meter
    ins, lw, rad = 0.011 * s, 0.0055 * s, 0.016 * s
    d.rounded_rectangle([ins, ins, W - ins, H - ins], radius=rad, outline=WHITE, width=round(lw))
    im = im.resize((512, 128), Image.LANCZOS)
    im = noise_overlay(im, 0.025)
    im.save(os.path.join(OUT, "street_sign.png"), optimize=True)


def stop_sign():
    """Haltestellen-Fahne 0,45 x 1,08 m (Textur vorverzerrt auf 256 x 512)."""
    Wm, Hm = 0.45, 1.08
    W, H = 256 * SS, 512 * SS
    sx, sy = W / Wm, H / Hm
    im = Image.new("RGB", (W, H), YELLOW)
    d = ImageDraw.Draw(im)

    def R(x0, y0, x1, y1, col, outline=None, width=0, radius=0):
        box = [x0 * sx, y0 * sy, x1 * sx, y1 * sy]
        if radius:
            d.rounded_rectangle(box, radius=radius * sx, fill=col, outline=outline, width=width)
        else:
            d.rectangle(box, fill=col, outline=outline, width=width)

    def E(cx, cy, r, col):
        d.ellipse([(cx - r) * sx, (cy - r) * sy, (cx + r) * sx, (cy + r) * sy], fill=col)

    # schwarze Innenlinie
    R(0.012, 0.012, Wm - 0.012, Hm - 0.012, None, outline=BLACK, width=round(0.004 * sx), radius=0.02)
    # Zeichen 224 (Ø 0,34 m)
    cx, cy, r = Wm / 2, 0.215, 0.17
    E(cx, cy, r, YELLOW)
    E(cx, cy, r - 0.006, GREEN)
    E(cx, cy, r - 0.006 - 0.046, YELLOW)
    hw, hh, sw = 0.064, 0.088, 0.023
    R(cx - hw, cy - hh, cx - hw + sw, cy + hh, GREEN)
    R(cx + hw - sw, cy - hh, cx + hw, cy + hh, GREEN)
    R(cx - hw, cy - sw / 2, cx + hw, cy + sw / 2, GREEN)
    # Trennlinien: Namensfeld 0,41..0,57, Linienfelder 0,58..0,95
    lw = round(0.003 * sy)
    for y in (0.405, 0.575):
        R(0.03, y, Wm - 0.03, y + lw / sy, BLACK)
    for i in range(4):
        y = 0.585 + i * 0.09
        R(0.035, y + 0.012, 0.135, y + 0.072, BLACK, radius=0.008)          # Linienfeld (Nummer)
        R(0.155, y + 0.078, Wm - 0.035, y + 0.078 + lw / sy, (90, 80, 20))   # Ziel-Zeile
    R(0.03, 0.955, Wm - 0.03, 0.955 + lw / sy, BLACK)
    # Fußleiste (ohne Logos): dunkles Feld
    R(0.06, 0.975, Wm - 0.06, 1.045, (40, 40, 44), radius=0.008)
    im = im.resize((256, 512), Image.LANCZOS)
    im = noise_overlay(im, 0.02, seed=2)
    im.save(os.path.join(OUT, "stop_sign.png"), optimize=True)


def timetable():
    W, H = 256 * SS // 2, 352 * SS // 2
    im = Image.new("RGB", (W, H), (236, 236, 230))
    d = ImageDraw.Draw(im)
    rnd = random.Random(5)
    s = W / 256
    d.rectangle([0, 0, W, 34 * s], fill=(250, 210, 30))
    d.rectangle([8 * s, 8 * s, 40 * s, 26 * s], fill=(30, 30, 30))
    for i in range(3):
        d.rectangle([52 * s, (9 + i * 6) * s, (52 + rnd.randint(60, 150)) * s, (12 + i * 6) * s], fill=(40, 40, 40))
    cols = [(10, 84), (90, 170), (176, 248)]
    for ci, (x0, x1) in enumerate(cols):
        d.rectangle([x0 * s, 42 * s, x1 * s, 50 * s], fill=(60, 60, 60))
        y = 56
        while y < 330:
            d.rectangle([x0 * s, y * s, (x0 + 10) * s, (y + 3) * s], fill=(30, 30, 30))
            n = rnd.randint(3, 8)
            for k in range(n):
                xx = x0 + 14 + k * 8
                if xx + 6 > x1:
                    break
                d.rectangle([xx * s, y * s, (xx + 5) * s, (y + 3) * s], fill=(80, 80, 80))
            y += 7
            if rnd.random() < 0.08:
                y += 6
        d.line([(x1 + 2) * s, 42 * s, (x1 + 2) * s, 330 * s], fill=(170, 170, 165), width=max(1, round(s)))
    d.rectangle([0, 336 * s, W, H], fill=(210, 210, 205))
    im = im.resize((256, 352), Image.LANCZOS)
    im = noise_overlay(im, 0.03, seed=3)
    im.save(os.path.join(OUT, "timetable.png"), optimize=True)


def lantern():
    """Glas mit Sprossen (Dresdner Litfaßsäule mit Laterne) + Zackenfries."""
    W = 256 * SS
    im = Image.new("RGB", (W, W), (236, 233, 218))
    d = ImageDraw.Draw(im)
    for y in range(W):  # leichte Mattierung
        t = y / W
        d.line([(0, y), (W, y)], fill=(round(236 - 18 * t), round(233 - 16 * t), round(218 - 12 * t)))
    g = (38, 58, 46)
    lw = round(0.07 * W)
    d.rectangle([0, 0, lw // 2, W], fill=g)
    d.rectangle([W - lw // 2, 0, W, W], fill=g)
    for yy in (0, W // 2, W):
        d.rectangle([0, yy - lw // 3, W, yy + lw // 3], fill=g)
    im = im.resize((256, 256), Image.LANCZOS)
    im.save(os.path.join(OUT, "lantern_glass.png"), optimize=True)
    # Zackenfries: abwechselnd grüne und gelbe Dreiecke (eine Kachel = 2 Zacken)
    W2, H2 = 256 * SS, 128 * SS
    im = Image.new("RGB", (W2, H2), (38, 58, 46))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W2, H2 * 0.18], fill=(38, 58, 46))
    for k in range(2):
        x0 = k * W2 / 2
        d.polygon([(x0, H2 * 0.85), (x0 + W2 / 4, H2 * 0.2), (x0 + W2 / 2, H2 * 0.85)], fill=(226, 200, 70))
        d.polygon([(x0 + W2 / 4, H2 * 0.2), (x0 + W2 / 2, H2 * 0.85), (x0 + W2 * 0.75, H2 * 0.2)], fill=(70, 150, 84))
    d.rectangle([0, H2 * 0.85, W2, H2], fill=(242, 240, 230))
    im = im.resize((256, 128), Image.LANCZOS)
    im.save(os.path.join(OUT, "lantern_trim.png"), optimize=True)


if __name__ == "__main__":
    street_sign()
    stop_sign()
    timetable()
    lantern()
    print("ok")
