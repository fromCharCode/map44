"""Zweite Runde benannter Dresdner Brunnen nach Fotovorlagen (Wikimedia Commons, nur als Vorlage)
nach godot/assets/models/monuments/mon_<name>.glb.

Aufruf (Projektordner, immer nur ein Blender gleichzeitig):
  flatpak run --filesystem=host org.blender.Blender -b --python "$PWD/tools/blender/monuments_named_d.py" \
      [-- name ...] [--nopreview] [--close]

Bausteine, Konventionen und Materialien stammen aus monuments_build.py und monuments_named_b.py (Blender Z-up,
Meter, Ursprung = Bodenmitte, Vorderseite +Y). Maße: belegt, wo im Kommentar "belegt" steht (Wikipedia), sonst
aus den Fotos in data/research/denkmal_fotos/ geschätzt. Zusätzliches Material: Lack_rot (Schnabel und Beine des
Queckbrunnen-Storchs).
"""
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import monuments_build as MB  # noqa: E402
import monuments_named_b as B  # noqa: E402
from monuments_build import (L, V, Soup, mat, loft, lathe, cyl, cbox, tube, circle, rrect, rect, build,  # noqa: E402
                             finish, ico, TAU, STONE, BRONZE, GRANITE, WATER, STEEL, stack, prism_y, limb)
from monuments_named_b import MARBLE, DARK, IRON, F, robe, place, ground  # noqa: E402

RED = "Lack_rot"
SQ = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
TRI = [(1, 0), (-0.5, 0.866), (-0.5, -0.866)]

B.POSES.update({
    # Wasserträgerin: rechter Arm stützt den Krug auf dem Kopf, linker hängt
    "jug": B._arms(((-0.12, 0.05, -1.0), (-0.05, 0.25, -0.95)), ((0.75, 0.05, 0.65), (-0.72, 0.05, 0.70)))
    + [("UpperLeg_L", (-0.03, 0.12, -1.0)), ("LowerLeg_L", (-0.02, -0.04, -1.0))],
    # Aphrodite mit Trauben: beide Arme erhoben, Oberarme seitlich, Unterarme nach oben; Schrittstellung
    "grapes": [("Head", (0.12, 0.30, 0.94))]
    + B._legs(((-0.06, 0.26, -0.96), (-0.02, -0.06, -1.0)), ((0.05, -0.10, -1.0), (0.0, -0.12, -1.0)))
    + B._arms(((-0.92, 0.10, 0.30), (-0.10, 0.20, 0.97)), ((0.90, 0.20, 0.05), (0.22, 0.25, 0.94))),
})


def mats():
    B.mats()
    mat(RED, "#B03A2E", 0.5)


def crect(w, d, c, z=0.0, cx=0.0, cy=0.0):
    """Rechteck mit abgeschrägten Ecken (unregelmäßiges Achteck), CCW von oben."""
    hw, hd = w / 2, d / 2
    return [V((cx + x, cy + y, z)) for x, y in ((hw, -hd + c), (hw, hd - c), (hw - c, hd), (-hw + c, hd),
                                                (-hw, hd - c), (-hw, -hd + c), (-hw + c, -hd), (hw - c, -hd))]


def ring_basin(ringfn, h, t, zf, m, z0=0.0, wl=None, lip=0.0):
    """Becken über beliebigem Grundriss: ringfn(Einzug, z) liefert den um 'Einzug' verkleinerten Ring.
    Außenwand, Rand (optional mit Überstand), Innenwand, geschlossener Boden bei zf, Wasser bei wl."""
    rings = [ringfn(0.0, z0)]
    if lip:
        rings += [ringfn(0.0, z0 + h - 0.12), ringfn(-lip, z0 + h - 0.09), ringfn(-lip, z0 + h)]
    else:
        rings += [ringfn(0.0, z0 + h)]
    rings += [ringfn(t, z0 + h), ringfn(t + 0.01, zf)]
    s = loft(rings, m, orient=V((0, 0, 1)))
    if wl is not None:
        s.poly(ringfn(t + 0.008, wl), WATER)
    return s


# ====================================================================== Modelle
MODELS = {}
VIEWS = {}
CLOSE = {}


def model(views=None, close=None):
    def deco(fn):
        MODELS[fn.__name__] = fn
        if views:
            VIEWS[fn.__name__] = views
        if close:
            CLOSE[fn.__name__] = close
        return fn
    return deco


def dandelion(zc, rc, rl, nrod, stem_r, m=STEEL, seed=0.0):
    """Pusteblume: Stiel bis zur Kugelmitte zc, Kugel mit Halbmesser rc, nrod Röhrchen der Länge rl."""
    s = Soup()
    s.add(lathe([(stem_r * 1.6, 0.0), (stem_r * 1.6, 0.06), (stem_r, 0.08), (stem_r, zc - rc * 0.8)], 8, m, cap1=False))
    s.add(ico(rc, m, 2).move(0, 0, zc))
    ga = math.pi * (3 - math.sqrt(5))
    for i in range(nrod):
        u = 1 - 2 * (i + 0.5) / nrod
        if u < -0.93:                       # unten, wo der Stiel sitzt, keine Röhrchen
            continue
        rr = math.sqrt(1 - u * u)
        a = ga * i + seed
        d = V((math.cos(a) * rr, math.sin(a) * rr, u))
        c = V((0, 0, zc))
        s.add(tube([c + d * (rc * 0.95), c + d * (rc + rl)], 0.011, 3, m, caps=False, prof=TRI))
        s.add(ico(0.03, m, 0).move(*(c + d * (rc + rl))))     # Sprühteller am Röhrchenende
    return s


@model(views=((25, 10), (60, 30)), close=((0, 0, 2.3), 2.6, ((20, 5),)))
def mon_pusteblumen():
    """Pusteblumenbrunnen (Leoni Wirth 1969), Prager Straße: drei Edelstahl-Pusteblumen in flachem
    Rechteckbecken. Keine Maße belegt; aus Fotos geschätzt (Becken 11 × 7,5 m, höchste Blume ca. 3,8 m)."""
    s = Soup()
    W, D = 11.0, 7.5
    # Becken: breite Granitbrüstung, innen flache Edelstahlrinne, Wasser fast randvoll
    s.add(ring_basin(lambda e, z: rect(W - 2 * e, D - 2 * e, z), 0.42, 0.55, 0.20, GRANITE, wl=0.37))
    for x, y, zc, rc, rl, n, sr, sd in ((-0.2, 0.9, 2.85, 0.34, 0.68, 96, 0.055, 0.0),
                                        (1.25, -0.35, 2.50, 0.30, 0.60, 84, 0.05, 1.3),
                                        (-1.35, -0.75, 1.65, 0.21, 0.40, 64, 0.04, 2.1)):
        s.add(dandelion(zc - 0.20, rc, rl, n, sr, seed=sd).move(x, y, 0.20))
    return s, ("Pusteblumenbrunnen (Leoni Wirth 1969, Prager Straße): drei Edelstahl-Pusteblumen (Kugel mit "
               "Röhrchenkranz auf Stiel, 3,8 / 3,4 / 2,3 m hoch) in flachem Granit-Rechteckbecken 11 × 7,5 m "
               "(lange Seite X). Maße geschätzt.")


def dish(R, z, x, y, m=STEEL, legs=3, n=16):
    """Flache Wasserschale (Rand bei z) auf einem Bündel dünner Rohre."""
    s = lathe([(0.10, z - 0.30), (R, z - 0.02), (R, z + 0.02), (0.10, z - 0.26)], n, m)
    s.poly(circle(R - 0.18 * (R - 0.10), n, z - 0.03, a0=math.pi / n), WATER)
    s.add(lathe([(0.13, z - 0.42), (0.13, z - 0.28)], 8, m))
    for k in range(legs):
        a = TAU * k / legs + 0.5
        s.add(tube([V((math.cos(a) * 0.085, math.sin(a) * 0.085, 0.0)), V((math.cos(a) * 0.085, math.sin(a) * 0.085, z - 0.40))],
                   0.035, 6, m, caps=False))
    return s.move(x, y, 0)


@model(views=((20, 8), (55, 30)), close=((0, 0, 2.6), 4.2, ((20, 5),)))
def mon_schalenbrunnen_prager():
    """Schalenbrunnen (Leoni Wirth 1970/71), früher Prager Straße, seit 2021 Dippoldiswalder Platz. Belegt:
    zehn Schalen. Maße, Höhenstaffelung und Anordnung aus Fotos geschätzt."""
    s = Soup()
    W, D = 12.0, 8.0
    s.add(ring_basin(lambda e, z: rect(W - 2 * e, D - 2 * e, z), 0.45, 0.60, 0.15, GRANITE, wl=0.33))
    zf = 0.15
    spec = [(0.0, 0.3, 5.2, 1.20, 4), (-1.5, -0.4, 4.3, 0.75, 3), (-2.6, 0.5, 3.9, 0.95, 3), (1.6, 0.9, 3.6, 0.80, 3),
            (-1.1, 1.3, 3.1, 0.70, 3), (0.5, -1.2, 2.6, 0.70, 3), (2.6, -0.5, 2.2, 0.85, 3), (-3.4, -1.0, 2.9, 0.65, 3),
            (1.1, -0.2, 1.45, 1.0, 3)]
    for x, y, z, R, lg in spec:
        s.add(dish(R * 1.2, z - zf, x, y, legs=lg).move(0, 0, zf))
    # zehnte Schale an einem gebogenen Rohrarm, der vom Bündel der Schale links außen abzweigt
    x0, y0 = -3.4, -1.0
    pts = [V((x0 - 0.05 - 0.9 * (1 - math.cos(t)), y0 + 0.05, 2.30 - 0.55 * math.sin(t)))
           for t in (math.pi * i / 8 for i in range(9))]
    pts = [V((x0 - 0.05, y0 + 0.05, 2.45))] + pts
    pts.append(V((pts[-1].x, pts[-1].y, 3.05)))
    s.add(tube(pts, 0.05, 6, STEEL))
    xe, ye = pts[-1].x, pts[-1].y
    d10 = lathe([(0.10, 3.05), (0.72, 3.33), (0.72, 3.37), (0.10, 3.09)], 16, STEEL)
    d10.poly(circle(0.61, 16, 3.32, a0=math.pi / 16), WATER)
    s.add(d10.move(xe, ye, 0))
    return s, ("Schalenbrunnen (Leoni Wirth, früher Prager Straße, seit 2021 Dippoldiswalder Platz): zehn flache "
               "Edelstahlschalen Ø 1,4–2,9 m auf Rohrbündeln in 1,5–5,2 m Höhe, eine an gebogenem Arm, in "
               "Rechteckbecken 12 × 8 m (lange Seite X). Maße und Anordnung geschätzt.")


def stork():
    """Storch (Blick +Y) mit halb gebreiteten Flügeln; Fußpunkt der Stange im Ursprung, Höhe ca. 0,65 m."""
    s = Soup()
    W = MARBLE
    s.add(tube([V((0, 0, 0)), V((0, 0, 0.24))], 0.012, 4, IRON, caps=False, prof=SQ))
    s.add(limb([(-0.20, 0.20, 0.02, 0.02), (-0.12, 0.23, 0.07, 0.065), (0.0, 0.27, 0.085, 0.08), (0.08, 0.33, 0.06, 0.06),
                (0.11, 0.40, 0.035, 0.035)], 8, W, sub=2))
    s.add(limb([(0.10, 0.38, 0.035, 0.035), (0.13, 0.47, 0.024, 0.024), (0.10, 0.55, 0.022, 0.022),
                (0.11, 0.59, 0.03, 0.032), (0.14, 0.61, 0.018, 0.02)], 6, W, sub=2))
    s.add(tube([V((0, 0.13, 0.60)), V((0, 0.25, 0.66))], 0.012, 4, RED, rs=[0.014, 0.004]))
    s.add(cyl(0.022, 0.16, 6, W).rot((0, 1, 0), 90).move(-0.08, 0.20, 0.635))        # Wickelkind im Schnabel
    for sx in (-1, 1):
        wing = loft([[V((sx * x, cy + c * ch, cz + c2 * 0.012)) for c, c2 in ((1, 0), (0, 1), (-1, 0), (0, -1))]
                     for x, cy, cz, ch in ((0.05, 0.02, 0.31, 0.09), (0.22, -0.02, 0.30, 0.11), (0.40, -0.08, 0.22, 0.09),
                                           (0.52, -0.14, 0.10, 0.03))], W)
        s.add(wing)
        s.add(tube([V((sx * 0.03, -0.03, 0.21)), V((sx * 0.035, 0.02, 0.03))], 0.008, 4, RED, caps=False, prof=SQ))
    s.add(cyl(0.022, 0.18, 6, W).rot((0, 1, 0), 90).move(-0.09, 0.03, 0.03))         # Wickelkind in den Fängen
    return s


@model(views=((25, 10), (215, 15)), close=((0, 0, 3.6), 1.4, ((20, 5),)))
def mon_queckbrunnen():
    """Queckbrunnen, Hertha-Lindner-Straße. Belegt (Wikipedia): Brunnenhaus 3,6 m, Gesamthöhe 4,5 m,
    Sockel 2,73 × 1,95 m, Brunnenhaus in mittlerer Höhe 1,35 × 1,35 m. Gliederung aus Fotos."""
    s = Soup()
    D = DARK
    # Sockelplatte: Rechteck mit halbrundem Trog vorn (1,95 breit, 2,73 tief)
    R, yb, yfront = 0.975, -0.975, 0.78

    def dring(e, z):
        return ([V((R - e, yb + e, z))]
                + [V((math.cos(math.pi * i / 12) * (R - e), yfront + math.sin(math.pi * i / 12) * (R - e), z))
                   for i in range(13)] + [V((-R + e, yb + e, z))])
    s.add(loft([dring(0.0, 0), dring(0.0, 0.10), dring(0.04, 0.16), dring(0.04, 0.27), dring(0.08, 0.31)], D,
               orient=V((0, 0, 1))))
    s.poly(circle(0.13, 10, 0.315, 0, yfront + 0.42), WATER)       # Ablauf
    # dunkler Sockelblock, nach unten ausschwingend
    s.add(stack([(1.90, 1.56, 0.31), (1.84, 1.52, 0.40), (1.56, 1.46, 0.62), (1.46, 1.44, 0.80), (1.44, 1.44, 1.08)], D))
    # Brunnenhaus
    s.add(stack([(1.30, 1.30, 1.08), (1.30, 1.30, 2.20), (1.40, 1.40, 2.22), (1.40, 1.40, 2.30), (1.46, 1.46, 2.32),
                 (1.46, 1.46, 2.92), (1.50, 1.50, 2.94), (1.50, 1.50, 3.02), (1.66, 1.66, 3.07), (1.76, 1.76, 3.12),
                 (1.76, 1.76, 3.16)], STONE))
    for k in range(4):                      # Zahnschnitt unter dem Fries und unter der Traufe, Spiegelfelder
        for zz, w, nd, dh in ((2.16, 1.30, 11, 0.05), (3.02, 1.50, 9, 0.07)):
            for i in range(nd):
                x = -w / 2 + w * (i + 0.5) / nd
                s.add(cbox(x, w / 2 + 0.02, zz, w / nd * 0.5, 0.05, dh, STONE).rot((0, 0, 1), 90 * k))
        s.add(cbox(0, 0.73, 2.40, 1.16, 0.025, 0.44, STONE).rot((0, 0, 1), 90 * k))
    # Wappen mit Verdachung (vorn), Auslauf, zwei Knäufe am Sockel
    s.add(cbox(0, 0.67, 1.68, 0.34, 0.06, 0.50, STONE))
    s.add(prism_y([(-0.36, 2.20), (0.36, 2.20), (0.36, 2.30), (0.0, 2.44), (-0.36, 2.30)], 0.72, 0.80, STONE))
    s.add(cyl(0.085, 0.24, 8, IRON).rot((1, 0, 0), -90).move(0, 0.70, 1.02))
    s.add(cyl(0.05, 0.12, 6, IRON, z0=-0.12).move(0, 0.90, 1.0))
    for sx in (-1, 1):
        s.add(cyl(0.06, 0.06, 8, D).rot((1, 0, 0), -90).move(sx * 0.52, 0.72, 1.0))
    # Pumpenschwengel (Schmiedeeisen) an der linken Seite (+X), unten eingerollt
    pts = [V((0.64, 0.1, 2.02)), V((0.80, 0.1, 2.02)), V((0.90, 0.1, 1.92)), V((0.93, 0.1, 1.60)), V((0.95, 0.1, 0.95))]
    for i in range(10):
        a = math.pi + TAU * 0.8 * i / 9
        rr = 0.16 * (1 - 0.6 * i / 9)
        pts.append(V((1.11 + math.cos(a) * rr, 0.1, 0.80 + math.sin(a) * rr)))
    s.add(tube(pts, 0.028, 4, IRON, prof=SQ, up=(0, 1, 0)))
    s.add(tube([V((0.64, 0.1, 1.82)), V((0.92, 0.1, 1.82))], 0.022, 4, IRON, caps=False, prof=SQ))
    s.add(tube([V((0.70, 0.1, 1.12)), V((0.95, 0.1, 1.12))], 0.022, 4, IRON, caps=False, prof=SQ))
    # Rückseite: Schlitz mit Gestänge
    s.add(cbox(0, -0.66, 1.75, 0.07, 0.03, 0.40, IRON))
    s.add(tube([V((0, -0.68, 1.10)), V((0, -0.68, 1.80))], 0.015, 4, IRON, caps=False, prof=SQ))
    # steinernes Zeltdach in vier Plattenlagen, Knauf
    z, w = 3.16, 1.80
    for i in range(4):
        w2 = w - 0.34
        s.add(stack([(w, w, z), (w, w, z + 0.03), (w2 + 0.05, w2 + 0.05, z + 0.105)], D))
        for k in range(4):                  # Deckleisten
            for j in range(-1, 2):
                x = j * w / 3.2
                s.add(tube([V((x, w / 2 - 0.01, z + 0.045)), V((x * (w2 + 0.05) / w, w2 / 2 + 0.03, z + 0.115))], 0.03, 4, D,
                           caps=False, prof=SQ).rot((0, 0, 1), 90 * k))
        z, w = z + 0.105, w2
    s.add(lathe([(0.20, z), (0.20, z + 0.04), (0.10, z + 0.07), (0.09, z + 0.12), (0.13, z + 0.16), (0.13, z + 0.20),
                 (0.07, z + 0.24), (0.05, z + 0.27)], 8, D))
    st = stork()
    hi = max(v.z for v in st.v)
    k = (4.5 - (z + 0.27)) / hi
    s.add(st.scale(k, k, k).move(0, 0, z + 0.27))
    return s, ("Queckbrunnen (Hertha-Lindner-Straße): quadratisches Sandstein-Brunnenhaus 1,35 m mit Fries, "
               "Zahnschnitt und steinernem Zeltdach, dunkler Sockel 1,95 × 2,73 m mit halbrundem Trog, Wappen und "
               "Auslauf vorn (+Y), Schwengel an +X, Storch mit Wickelkindern obenauf; 4,5 m hoch (belegt).")


def dolphin(m, k=1.0):
    """Wasserspeiender Delphin: Kopf unten vorn (+Y), Leib aufsteigend, Schwanzflosse oben."""
    s = limb([(0.34, 0.02, 0.07, 0.05), (0.26, 0.06, 0.12, 0.11), (0.12, 0.14, 0.13, 0.13), (0.02, 0.30, 0.10, 0.10),
              (0.03, 0.48, 0.07, 0.07), (0.10, 0.60, 0.04, 0.04), (0.16, 0.70, 0.12, 0.02)], 6, m, sub=2)
    return s.scale(k, k, k)


@model(views=((20, 8), (45, 28)), close=((0, 0, 3.6), 2.4, ((20, 5),)))
def mon_rebekkabrunnen():
    """Rebekka-Brunnen (1863/64), An der Dreikönigskirche. Belegt (Wikipedia): Trog 1,10 m hoch, quadratisch mit
    gerundeten Ecken, dreistufige Rundtreppe, Sandsteinsäule, darüber Eisengusssäule mit Figur, Höhe ca. 5,70 m,
    vier halbrunde Becken mit Delphinköpfen. Durchmesser und Einzelhöhen aus Fotos geschätzt."""
    s = Soup()
    # drei runde Stufen
    s.add(lathe([(3.70, 0), (3.70, 0.15), (3.20, 0.15), (3.20, 0.30), (2.70, 0.30), (2.70, 0.45), (1.0, 0.45)], 40,
                STONE, cap1=False))
    z0 = 0.45
    Wt, rr = 3.1, 0.55

    def tring(e, z):
        return rrect(Wt - 2 * e, Wt - 2 * e, rr - e * 0.6, 3, z)
    # Trog mit Fuß- und Randprofil
    s.add(loft([tring(-0.06, z0), tring(-0.06, z0 + 0.16), tring(0.0, z0 + 0.22), tring(0.0, z0 + 0.92),
                tring(-0.07, z0 + 0.98), tring(-0.07, z0 + 1.10), tring(0.26, z0 + 1.10), tring(0.27, z0 + 0.35)],
               STONE, orient=V((0, 0, 1))))
    s.poly(tring(0.268, z0 + 0.98), WATER)
    for k in range(4):
        a = 90 * k
        # halbrundes Wandbecken (halb in der Trogwand), Delphinkopf darüber
        bw = lathe([(0.10, z0 + 0.40), (0.34, z0 + 0.48), (0.56, z0 + 0.62), (0.62, z0 + 0.70), (0.62, z0 + 0.76),
                    (0.53, z0 + 0.76), (0.48, z0 + 0.66)], 14, STONE, cap0=True)
        bw.poly(circle(0.50, 14, z0 + 0.72, a0=math.pi / 14), WATER)
        s.add(bw.move(0, Wt / 2, 0).rot((0, 0, 1), a))
        s.add(ico(0.14, STONE, 1).scale(0.9, 1.0, 1.2).move(0, Wt / 2 + 0.07, z0 + 1.02).rot((0, 0, 1), a))
        # Volutenaufsätze über den gerundeten Ecken
        s.add(place(cyl(0.13, 0.12, 8, STONE).rot((0, 1, 0), 90).move(0.0, 0, 0), 45 + a, Wt / 2 * 1.414 - 0.36,
                    z0 + 1.20, "out"))
    q = Soup()
    # Sandsteinsäule (dunkel patiniert): achteckiger Unterbau in zwei Stufen
    zt = z0 + 0.35
    q.add(lathe([(0.62, zt), (0.62, zt + 0.20), (0.54, zt + 0.26), (0.54, 2.18), (0.60, 2.23), (0.62, 2.30),
                 (0.50, 2.36), (0.40, 2.42), (0.38, 2.50), (0.38, 3.02), (0.44, 3.07), (0.46, 3.14), (0.30, 3.20)], 8,
                DARK))
    for k in range(4):                      # Rosettenfelder unten, Wappenfelder oben
        q.add(place(cbox(0, 0, 0, 0.28, 0.04, 0.28, DARK), 90 * k, 0.50, 1.62))
        q.add(place(cbox(0, 0, 0, 0.16, 0.04, 0.36, DARK), 90 * k, 0.35, 2.56))
        q.add(place(dolphin(DARK, 0.75), 45 + 90 * k, 0.40, 2.36, "out"))
    s.add(q.move(0, 0, -zt).scale(1, 1, (3.0 - zt) / (3.2 - zt)).move(0, 0, zt))
    q = Soup()
    # Eisengusssäule: Blattkelch, Schaft mit Girlande, Kapitell, Aufsatz
    I = IRON
    q.add(lathe([(0.25, 3.20), (0.27, 3.26), (0.20, 3.32), (0.23, 3.40), (0.24, 3.62), (0.17, 3.74), (0.145, 3.80),
                 (0.125, 4.32), (0.14, 4.36), (0.12, 4.40), (0.20, 4.48), (0.27, 4.58)], 10, I))
    q.add(lathe([(0.16, 4.04), (0.19, 4.07), (0.16, 4.10)], 10, I, cap0=False, cap1=False))
    q.add(stack([(0.56, 0.56, 4.58), (0.56, 0.56, 4.62), (0.40, 0.40, 4.64), (0.46, 0.46, 4.76), (0.40, 0.40, 4.88),
                 (0.64, 0.64, 4.92), (0.64, 0.64, 4.98), (0.34, 0.34, 4.99), (0.34, 0.34, 5.04)], I))
    for k in range(4):                      # Eckvoluten des Kapitells
        q.add(place(ico(0.07, I, 0), 45 + 90 * k, 0.26, 4.52))
    zi = 3.0 + (5.04 - 3.2) * 0.93
    s.add(q.move(0, 0, -3.2).scale(1, 1, 0.93).move(0, 0, 3.0))
    # Rebekka mit Krug auf dem Kopf
    f, j = F("f", "jug", I, 0.5)
    f.add(robe([(0.02, 0, 0.0, 0.22, 0.19), (0.50, 0, 0.0, 0.185, 0.155), (0.86, 0, 0, 0.165, 0.13),
                (1.02, 0, 0, 0.155, 0.12)], I, 8))
    hd, ht = j["Head"]
    jz = ht.z + 0.04
    f.add(lathe([(0.05, 0.0), (0.11, 0.07), (0.12, 0.14), (0.07, 0.22), (0.05, 0.25), (0.07, 0.28)], 8, I)
          .move(hd.x, hd.y, jz - 0.02))
    ground(f)
    hf = max(v.z for v in f.v)
    kf = (5.70 - zi) / hf
    s.add(f.scale(kf, kf, kf).move(0, 0, zi))
    return s, ("Rebekka-Brunnen (An der Dreikönigskirche): Sandsteintrog 1,10 m, quadratisch mit gerundeten Ecken "
               "und vier halbrunden Wandbecken, auf dreistufiger Rundtreppe Ø 7,4 m; achteckige dunkle "
               "Sandsteinsäule mit vier Delphinen, darüber Eisengusssäule mit Rebekka (Krug auf dem Kopf); "
               "5,70 m hoch (belegt), Durchmesser geschätzt.")


@model(views=((25, 8), (205, 20)), close=((0, 0, 3.5), 1.9, ((25, 5), (200, 5))))
def mon_marie_gey_brunnen():
    """Marie-Gey-Brunnen (Wrba 1908–10), Friedrich-List-Platz. Belegt (Wikipedia): achteckiges Becken,
    quadratischer Sandsteinaufbau, Bronzesockel, vier Putten stützen eine Muschelschale, darin nackte Aphrodite
    mit Trauben. Keine Maße belegt; aus Fotos geschätzt (Figur leicht überlebensgroß)."""
    s = Soup()
    D, Bz = DARK, BRONZE
    Wb, c = 4.0, 0.95
    # heller Fußstreifen, dunkles Becken (Quadrat mit gebrochenen Ecken)
    s.add(loft([crect(Wb + 0.12, Wb + 0.12, c + 0.03, 0), crect(Wb + 0.12, Wb + 0.12, c + 0.03, 0.22),
                crect(Wb, Wb, c, 0.24)], STONE, orient=V((0, 0, 1)), cap1=False))
    s.add(ring_basin(lambda e, z: crect(Wb - 2 * e, Wb - 2 * e, c - e * 0.83, z), 0.60, 0.30, 0.30, D, z0=0.22,
                     wl=0.70, lip=0.03))
    for k in range(4):                      # Trinkschälchen außen an den gebrochenen Ecken
        bw = lathe([(0.30, 0), (0.33, 0.10), (0.33, 0.22), (0.25, 0.22), (0.22, 0.12)], 10, STONE)
        bw.poly(circle(0.23, 10, 0.18, a0=math.pi / 10), WATER)
        rr = (Wb - c) / math.sqrt(2) + 0.22
        s.add(place(bw, 45 + 90 * k, rr, 0))
        s.add(place(cyl(0.035, 0.12, 6, Bz).rot((1, 0, 0), -90), 45 + 90 * k, rr - 0.24, 0.52))
    # Mittelblock mit vier Fischköpfen
    s.add(stack([(1.36, 1.36, 0.30), (1.36, 1.36, 2.02)], D))
    for k in range(4):
        s.add(place(ico(0.17, D, 1).scale(0.9, 1.1, 1.15), 90 * k, 0.70, 1.72))
        s.add(place(cyl(0.03, 0.10, 6, Bz).rot((1, 0, 0), -90), 90 * k, 0.86, 1.62))
    # Bronzesockel: Stufenplatte, Wellenkegel
    s.add(stack([(1.40, 1.40, 2.02), (1.40, 1.40, 2.05), (1.30, 1.30, 2.07), (1.30, 1.30, 2.10), (1.20, 1.20, 2.12),
                 (1.20, 1.20, 2.15), (1.08, 1.08, 2.17)], Bz))
    s.add(lathe([(0.50, 2.15), (0.42, 2.40), (0.32, 2.62), (0.24, 2.80)], 12, Bz))
    # Muschelschale, leicht nach hinten geneigt
    sh = []
    n = 14
    for r_, z_ in ((0.20, -0.16), (0.60, -0.10), (0.84, 0.02), (0.88, 0.08), (0.80, 0.08), (0.3, -0.02)):
        sh.append([V((math.cos(a) * r_ * (1 + 0.07 * math.cos(a * 7)), math.sin(a) * r_ * (1 + 0.07 * math.cos(a * 7)) * 0.85, z_))
                   for a in (TAU * i / n for i in range(n))])
    zs = 2.84
    s.add(loft(sh, Bz, orient=V((0, 0, 1))).rot((1, 0, 0), -16).move(0, -0.10, zs + 0.06))
    # vier Putten rund um den Kegel, auf der Stufenplatte sitzend
    for k in range(4):
        f, j = F("k", "sit", Bz, 0.4)
        hk = max(v.z for v in f.v) - min(v.z for v in f.v)
        kk = 0.78 / hk
        f.move(0, 0, -(j["Hips"][0].z - 0.10)).scale(kk, kk, kk)
        s.add(place(f, 45 + 90 * k, 0.56, 2.17, "out"))
    # Aphrodite
    f, j = F("f", "grapes", Bz)
    for side in ("L", "R"):
        h, t = j["Hand_" + side]
        p = h + (t - h) * 0.8
        s_g = ico(0.07, Bz, 1).scale(1.0, 1.0, 1.5).move(p.x, p.y, p.z - 0.06)
        f.add(s_g)
    hd = j["Head"][0]
    f.add(ico(0.115, Bz, 1).scale(1.0, 1.0, 0.9).move(hd.x, hd.y - 0.04, hd.z + 0.09))      # Haarkranz
    ground(f).scale(1.2, 1.25, 1.0)
    body = max(v.z for v in f.v if abs(v.x) < 0.2)
    kf = 1.95 / body
    s.add(f.scale(kf, kf, kf).move(0, 0.12, zs - 0.02))
    return s, ("Marie-Gey-Brunnen (Wrba, Friedrich-List-Platz): Bronze-Aphrodite mit erhobenen Armen und Trauben "
               "auf Muschelschale, die vier sitzende Putten umgeben; Bronzesockel auf quadratischem dunklem "
               "Steinblock mit vier Fischkopf-Speiern, Becken 4 m als Quadrat mit gebrochenen Ecken und vier "
               "Trinkschälchen. Maße geschätzt. Figur blickt nach +Y.")


@model(views=((20, 10), (45, 30)), close=((0, 0, 2.6), 2.4, ((20, 5),)))
def mon_hietzigbrunnen():
    """Hietzigbrunnen/Rathausbrunnen (Wrba 1911), An der Kreuzkirche/Schulgasse. Belegt (Wikipedia): achteckig,
    Lausitzer Granit, acht Wasserspeier (vier Masken, vier Fische). Keine Maße belegt; aus Fotos geschätzt."""
    s = Soup()
    G = GRANITE
    cf = math.cos(math.pi / 8)
    s.add(lathe([(3.7 / cf, 0), (3.7 / cf, 0.16), (3.0 / cf, 0.16)], 8, G, cap1=False))
    s.add(B.basin(3.05 / cf, 0.58, 0.32, 0.30, 8, G, z0=0.16, wl=0.60, bulge=0.03))
    for k in range(8):                      # Spiegelfelder der Brüstung
        s.add(place(cbox(0, 0, 0, 1.55, 0.03, 0.26, G), 90 + 45 * k, 3.05, 0.32))
    # runder Sockel mit Wulst, Hals
    s.add(lathe([(1.18, 0.30), (1.18, 0.92), (1.24, 0.97), (1.24, 1.03), (1.10, 1.08), (1.02, 1.14), (1.02, 1.36)],
                24, G, cap1=False))
    # große Schale, achtfach gebrochener Rand mit Ausgusslippen
    s.add(lathe([(1.0, 1.32), (1.40, 1.46), (1.74, 1.72), (1.88, 1.96), (1.90, 2.06), (1.90, 2.13), (1.76, 2.13),
                 (1.62, 1.92), (0.5, 1.70)], 16, G, cap0=False))
    s.poly(circle(1.70, 16, 2.05, a0=math.pi / 16), WATER)
    for k in range(8):
        s.add(place(stack([(0.34, 0.20, 0), (0.34, 0.20, 0.10), (0.26, 0.12, 0.13)], G), 90 + 45 * k, 1.88, 2.05))
    # achteckiger Mittelpfeiler mit vier Masken
    s.add(lathe([(0.52, 1.70), (0.52, 2.42), (0.44, 2.48), (0.42, 2.88), (0.50, 2.93), (0.54, 3.02), (0.46, 3.07),
                 (0.24, 3.10)], 8, G))
    for k in range(4):
        s.add(place(ico(0.10, G, 1).scale(1, 0.8, 1.1), 90 * k, 0.42, 2.66))
    # Vase mit Schuppenleib, Masken und Knauf
    s.add(lathe([(0.22, 3.10), (0.14, 3.16), (0.14, 3.24), (0.26, 3.34), (0.37, 3.52), (0.40, 3.72), (0.36, 3.92),
                 (0.25, 4.04), (0.13, 4.08), (0.10, 4.12), (0.14, 4.17), (0.14, 4.25), (0.06, 4.31), (0.0, 4.33)], 12,
                G, cap1=False))
    for k in range(4):
        s.add(place(ico(0.11, G, 1).scale(1, 0.7, 1.2), 90 * k, 0.36, 3.78))
    return s, ("Hietzigbrunnen (Rathausbrunnen, Wrba 1911): achteckiges Granitbecken Ø 6,1 m auf achteckiger "
               "Stufe, runder Sockel, große Schale Ø 3,8 m mit acht Ausgusslippen, achteckiger Pfeiler mit Masken "
               "und bekrönender Vase; 4,3 m hoch. Maße geschätzt.")


def closeup(name, c, R, views):
    """Kontrollbilder (nicht Teil der Auslieferung) nach tools/blender/mond_tmp/."""
    sc = bpy.context.scene
    cam = sc.camera
    Dd = R / math.sin(cam.data.angle / 2) * 1.02
    for k, (az, el) in enumerate(views):
        a, e = math.radians(az), math.radians(el)
        d = V((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
        cam.location = V(c) + d * Dd
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        sc.render.resolution_x = sc.render.resolution_y = 640
        sc.render.filepath = os.path.join(HERE, "mond_tmp", f"{name}_c{k}.png")
        bpy.ops.render.render(write_still=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    L.NOPREVIEW = "--nopreview" in argv
    names = [a for a in argv if not a.startswith("--")] or list(MODELS)
    B.load_figures()
    for name in names:
        L.reset()
        mats()
        soup, notes = MODELS[name]()
        ob = build(soup, name, smooth_angle=42, merge=True)
        finish(name, [ob], notes, views=VIEWS.get(name))
        if "--close" in argv and name in CLOSE and not L.NOPREVIEW:
            closeup(name, *CLOSE[name])
    try:
        os.rmdir(L.TMP)
    except OSError:
        pass


if __name__ == "__main__":
    main()
