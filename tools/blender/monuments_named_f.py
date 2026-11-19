"""Dritte Runde benannter Dresdner Brunnen nach Fotovorlagen (Wikimedia Commons, nur als Vorlage)
nach godot/assets/models/monuments/mon_<name>.glb.

Aufruf (Projektordner, immer nur ein Blender gleichzeitig):
  flatpak run --filesystem=host org.blender.Blender -b --python "$PWD/tools/blender/monuments_named_f.py" \
      [-- name ...] [--nopreview] [--close]

Bausteine, Konventionen und Materialien stammen aus monuments_build.py, monuments_named_b.py und
monuments_named_d.py (Blender Z-up, Meter, Ursprung = Bodenmitte, Vorderseite +Y). Neu in dieser Runde: jede
Anlage hat einen senkrechten, unten geschlossenen Sockelkranz, der 0,6 m unter den Ursprung reicht (leicht
geneigtes Gelände). Maße: belegt, wo im Kommentar "belegt" steht, sonst aus den Fotos in
data/research/denkmal_fotos/ geschätzt. Zusätzliche Materialien: Messing (Glasbrunnen), Holz (Bank am
Flügelradbrunnen).
"""
import math
import os
import random
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import monuments_build as MB  # noqa: E402
import monuments_named_b as B  # noqa: E402
import monuments_named_d as D4  # noqa: E402
from monuments_build import (L, V, Soup, mat, loft, lathe, cyl, cbox, tube, circle, rrect, rect, build,  # noqa: E402
                             finish, ico, TAU, STONE, BRONZE, GOLD, GRANITE, WATER, STEEL, stack, prism_y, limb)
from monuments_named_b import MARBLE, DARK, IRON, F, robe, place, ground, rock, floor0  # noqa: E402
from monuments_named_d import ring_basin, crect, SQ  # noqa: E402

GLASS, BRASS, WOOD = "Glas", "Messing", "Holz"
SKIRT = 0.6          # Tiefe des Sockelkranzes unter dem Ursprung

B.POSES.update({
    # Victoria/Irene: linker Arm hält die Fahnenstange, rechter den Kranz vor dem Leib, Spielbein rechts
    "victoria": [("Head", (0.15, 0.25, 0.95))]
    + B._legs(((-0.03, 0.04, -1.0), (0.0, -0.03, -1.0)), ((0.10, 0.20, -0.97), (0.0, -0.10, -1.0)))
    + B._arms(((-0.62, 0.10, -0.78), (-0.25, 0.30, 0.92)), ((0.30, 0.12, -0.95), (-0.62, 0.72, 0.05))),
    # Müller: trägt mit beiden Händen einen Sack auf der linken Schulter, leicht gebeugt
    "miller": [("Head", (-0.15, 0.15, 0.97))]
    + B._legs(((-0.05, 0.22, -0.97), (0.0, -0.06, -1.0)), ((0.06, -0.14, -1.0), (0.0, -0.14, -1.0)))
    + B._arms(((-0.42, 0.25, -0.87), (0.45, 0.10, 0.89)), ((0.50, 0.10, -0.86), (0.55, 0.22, -0.80))),
})


def mats():
    D4.mats()
    mat(GLASS, "#5A6E72", 0.12)             # wie in monuments_named_c.py
    mat(BRASS, "#B08E3C", 0.35, 0.9)
    mat(WOOD, "#8A5B38", 0.7)


def octa(Rf, z, cx=0.0, cy=0.0):
    """Regelmäßiges Achteck, Rf = Halbmesser über die Flächen (Flächen zeigen nach ±X/±Y)."""
    return circle(Rf / math.cos(math.pi / 8), 8, z, cx, cy, a0=math.pi / 8)


def skirt(ring, m, top=0.0):
    """Senkrechter, unten geschlossener Sockelkranz unter einem Grundrissring (reicht SKIRT unter den Ursprung)."""
    return loft([[V((p.x, p.y, -SKIRT)) for p in ring], [V((p.x, p.y, top)) for p in ring]], m,
                orient=V((0, 0, 1)), cap1=False)


def B_skirt(ring, m, top):
    """Flache Platte über einem Grundrissring (Oberkante top) samt Sockelkranz."""
    return loft([[V((p.x, p.y, -SKIRT)) for p in ring], [V((p.x, p.y, top)) for p in ring]], m, orient=V((0, 0, 1)))


def rosette(m, r=0.19, t=0.05):
    """Rosette (flache Scheibe mit Mittelknopf), Achse +Y, Rückseite bei y = 0."""
    s = lathe([(r, 0.0), (r, t * 0.5), (r * 0.72, t), (r * 0.28, t * 0.8), (r * 0.22, t * 1.5), (0.0, t * 1.6)], 8, m,
              cap0=False, cap1=False)
    return s.rot((1, 0, 0), -90)


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


@model(views=((25, 10), (200, 25)), close=((0, 0, 3.4), 2.0, ((20, 5), (200, 5))))
def mon_friedensbrunnen():
    """Friedensbrunnen/Türkenbrunnen, Jüdenhof am Neumarkt (Becken 1616, Figur der Victoria 1683 von Conrad Max
    Süßner; seit 1969 Kopie). Belegt (Wikipedia): achteckiges Becken 4,5 × 4,5 m, je Seite drei Rosetten,
    Granitsteig. Höhen aus Fotos geschätzt (Brüstung ca. 1 m, Gesamthöhe ca. 5,3 m)."""
    s = Soup()
    G, S = GRANITE, STONE
    cf = math.cos(math.pi / 8)
    # achteckige Granitstufe mit Sockelkranz
    Rs = 3.05
    s.add(skirt(octa(Rs, 0), G))
    s.add(loft([octa(Rs, 0), octa(Rs, 0.16), octa(2.2, 0.16)], G, orient=V((0, 0, 1)), cap0=False, cap1=False))
    # Becken: Sockelprofil, Wand, kräftiges Randgesims
    Rb, z0, hb = 2.25, 0.16, 0.98
    s.add(loft([octa(Rb + 0.07, z0), octa(Rb + 0.07, z0 + 0.12), octa(Rb, z0 + 0.19), octa(Rb, z0 + hb - 0.20),
                octa(Rb + 0.05, z0 + hb - 0.16), octa(Rb + 0.09, z0 + hb - 0.10), octa(Rb + 0.09, z0 + hb),
                octa(Rb - 0.30, z0 + hb), octa(Rb - 0.31, z0 + 0.22)], S, orient=V((0, 0, 1))))
    s.poly(octa(Rb - 0.305, z0 + hb - 0.14), WATER)
    side = 2 * Rb * math.tan(math.pi / 8)
    for k in range(8):
        # Eckpfeiler: verkröpfte Rundvorlage mit Basis und Kapitell
        col = lathe([(0.21, 0), (0.21, 0.12), (0.165, 0.20), (0.165, hb - 0.21), (0.20, hb - 0.16), (0.235, hb - 0.10),
                     (0.235, hb + 0.005)], 8, S)
        s.add(place(col, 22.5 + 45 * k, Rb / cf - 0.02, z0))
        # drei Rosettenfelder je Seite
        for i in (-1, 0, 1):
            x = i * (side - 0.50) / 3
            pan = cbox(x, 0.012, -0.24, 0.44, 0.024, 0.48, S)
            pan.add(rosette(S).move(x, 0.02, 0))
            s.add(place(pan, 90 + 45 * k, Rb, z0 + 0.19 + (hb - 0.39) / 2))
    # Mittelpfeiler (achteckig) aus dem Wasser
    zt = z0 + hb
    s.add(lathe([(0.36, z0 + 0.2), (0.36, zt + 0.22), (0.40, zt + 0.25), (0.40, zt + 0.30), (0.30, zt + 0.34)], 8, S))
    # bauchiger Vasenkörper mit Kartuschen, Löwenmasken und Fruchtgehängen
    zv = zt + 0.34
    s.add(lathe([(0.30, zv), (0.36, zv + 0.06), (0.48, zv + 0.22), (0.60, zv + 0.48), (0.64, zv + 0.72),
                 (0.60, zv + 0.90), (0.50, zv + 0.98)], 12, S, cap0=False, cap1=False))
    for k in range(4):
        cart = ico(0.27, S, 1).scale(1.0, 0.30, 1.30)
        s.add(place(cart, 90 * k, 0.60, zv + 0.55))                                # Kartusche
        s.add(place(ico(0.17, S, 1).scale(1.0, 0.8, 1.1), 45 + 90 * k, 0.62, zv + 0.50))   # Löwenmaske
        for sgn in (-1, 1):                                                         # Fruchtgehänge
            a0 = math.radians(90 * k + sgn * 8)
            a1 = math.radians(90 * k + sgn * 37)
            pts = [V((math.cos(a0 + (a1 - a0) * t) * 0.68, math.sin(a0 + (a1 - a0) * t) * 0.68,
                      zv + 0.88 - 0.17 * math.sin(math.pi * t))) for t in (i / 4 for i in range(5))]
            s.add(tube(pts, 0.07, 5, S, rs=[0.05, 0.085, 0.10, 0.085, 0.05]))
    # ausladende achteckige Deckplatte, Plinthe
    zc = zv + 0.98
    s.add(lathe([(0.52, zc - 0.02), (0.74, zc + 0.05), (0.82, zc + 0.11), (0.82, zc + 0.19), (0.66, zc + 0.30),
                 (0.48, zc + 0.36), (0.48, zc + 0.44), (0.42, zc + 0.46)], 8, S))
    zf = zc + 0.46
    # Victoria: Helm mit Federbusch, Brustpanzer, kurzer Rock, Kranz, Fahne
    f, j = F("f", "victoria", S)
    f.add(robe([(0.52, 0.0, 0.01, 0.29, 0.25), (0.70, 0.0, 0.0, 0.25, 0.20), (0.88, 0, 0, 0.20, 0.155),
                (1.02, 0, 0, 0.17, 0.13)], S, 10))
    f.add(robe([(1.02, 0, 0.0, 0.175, 0.135), (1.20, 0, 0.01, 0.185, 0.15), (1.36, 0, 0.0, 0.175, 0.13)], S, 8))
    hd, ht = j["Head"]
    up = (ht - hd).normalized()
    f.add(ico(0.125, S, 1).scale(1.0, 1.05, 0.85).move(*(hd + up * 0.13 + V((0, -0.02, 0)))))    # Helm
    for dx, dz, r in ((-0.10, 0.08, 0.075), (0.0, 0.13, 0.085), (0.10, 0.08, 0.075), (0.0, 0.05, 0.07)):
        f.add(ico(r, S, 1).move(*(hd + up * (0.17 + dz) + V((dx, -0.03, 0)))))                    # Federbusch
    hr = j["Hand_R"]
    c = hr[0] + (hr[1] - hr[0]) * 0.8
    ring = [V((c.x + math.cos(TAU * i / 10) * 0.12, c.y + 0.03, c.z - 0.06 + math.sin(TAU * i / 10) * 0.12))
            for i in range(10)]
    f.add(tube(ring, 0.04, 5, S, closed_path=True, up=(0, 1, 0)))                                 # Lorbeerkranz
    hl = j["Hand_L"]
    p = hl[0] + (hl[1] - hl[0]) * 0.6
    f.add(tube([V((p.x - 0.02, p.y, 0.0)), V((p.x - 0.02, p.y, 1.98))], 0.022, 6, S))            # Fahnenstange
    f.add(lathe([(0.03, 1.98), (0.045, 2.03), (0.0, 2.16)], 6, S, cx=p.x - 0.02, cy=p.y, cap0=False))
    # Fahnentuch: hängt in Falten von der Stange hinter die linke Schulter
    cloth = []
    for z, w, dy in ((0.80, 0.10, -0.16), (1.00, 0.20, -0.20), (1.25, 0.27, -0.18), (1.50, 0.26, -0.12),
                     (1.75, 0.18, -0.05), (1.93, 0.05, 0.0)):
        cloth.append([V((p.x - 0.02 - a * w, p.y + dy * abs(a) + b * 0.02 + 0.035 * math.sin(a * 9 + z * 3), z))
                      for a, b in ((-0.25, -1), (0.0, -1), (0.5, -1), (1.0, -1), (1.0, 1), (0.5, 1), (0.0, 1), (-0.25, 1))])
    f.add(loft(cloth, S))
    # Mantelbahn im Rücken bis zum Boden
    f.add(MB.cloak([(1.40, -0.02, 0.21, 0.14), (1.10, -0.05, 0.25, 0.19), (0.60, -0.08, 0.27, 0.23),
                    (0.04, -0.10, 0.28, 0.25)], S, half=75.0))
    ground(f)
    kf = 2.05 / max(v.z for v in f.v if abs(v.x) < 0.2)
    s.add(f.scale(kf, kf, kf).move(0, 0, zf))
    return s, ("Friedensbrunnen/Türkenbrunnen (Jüdenhof, Neumarkt): achteckiges Sandsteinbecken (4,5 m über die "
               "Flächen, belegt; Brüstung 1 m) mit Eckvorlagen und je drei Rosettenfeldern auf achteckiger Granitstufe; "
               "Mittelpfeiler mit bauchigem, kartuschen- und girlandengeschmücktem Körper und achteckiger "
               "Deckplatte, darauf Victoria mit Helm, Kranz und Fahne (blickt nach +Y). Höhen geschätzt. "
               "Sockelkranz 0,6 m unter dem Ursprung.")


def bull(m):
    """Stier in Lebensgröße (Widerrist ca. 1,5 m), Kopf nach +Y, Hufe auf z = 0, mit Stützblock unter dem Leib."""
    s = Soup()
    st = [(-1.06, 1.08, 1.30, 0.06), (-0.98, 0.80, 1.44, 0.27), (-0.70, 0.66, 1.47, 0.37), (-0.20, 0.60, 1.42, 0.41),
          (0.30, 0.60, 1.46, 0.41), (0.65, 0.64, 1.56, 0.39), (0.92, 0.76, 1.54, 0.31), (1.06, 0.94, 1.44, 0.15)]
    rings = []
    for y, zb, zt, hw in MB.spline(st, 3):
        zc, rz = (zb + zt) / 2, (zt - zb) / 2
        rings.append([V((math.cos(a) * hw * (1.0 - 0.14 * max(math.sin(a), 0.0)), y, zc + math.sin(a) * rz))
                      for a in (TAU * k / 12 for k in range(12))])
    s.add(loft(rings, m))
    # Hals mit Wamme, Kopf waagerecht vorgestreckt
    s.add(limb([(0.78, 1.14, 0.29, 0.40), (1.04, 1.20, 0.26, 0.35), (1.28, 1.27, 0.21, 0.25)], 10, m))
    s.add(limb([(1.20, 1.32, 0.20, 0.21), (1.38, 1.29, 0.20, 0.21), (1.58, 1.18, 0.155, 0.16),
                (1.74, 1.06, 0.13, 0.12), (1.81, 1.00, 0.085, 0.07)], 8, m))
    for sx in (-1, 1):
        s.add(tube([V((sx * 0.14, 1.32, 1.44)), V((sx * 0.27, 1.34, 1.48)), V((sx * 0.31, 1.38, 1.55))], 0.04, 5, m,
                   rs=[0.055, 0.045, 0.015]))                                           # Horn
        s.add(ico(0.075, m, 0).scale(1.5, 0.6, 0.8).move(sx * 0.27, 1.27, 1.34))        # Ohr
        s.add(limb([(0.72, 0.90, 0.17, 0.22), (0.73, 0.50, 0.12, 0.13), (0.73, 0.14, 0.095, 0.10),
                    (0.75, 0.0, 0.11, 0.12)], 8, m, x0=sx * 0.23))
        s.add(limb([(-0.76, 0.96, 0.18, 0.28), (-0.86, 0.52, 0.125, 0.15), (-0.80, 0.14, 0.095, 0.10),
                    (-0.77, 0.0, 0.11, 0.12)], 8, m, x0=sx * 0.24))
    s.add(limb([(-1.02, 1.36, 0.045, 0.045), (-1.12, 1.20, 0.035, 0.035), (-1.13, 0.70, 0.03, 0.03),
                (-1.12, 0.36, 0.055, 0.055), (-1.12, 0.26, 0.02, 0.02)], 5, m, sub=2))    # Schwanz
    s.add(stack([(0.46, 0.95, 0.0), (0.40, 0.80, 0.72)], m, r=0.15, cy=-0.05))            # Stütze unter dem Leib
    return s


@model(views=((30, 10), (120, 20)), close=((0, 0, 2.6), 1.3, ((30, 5), (110, 5))))
def mon_stierbrunnen():
    """Stierbrunnen (Georg Wrba 1910), Schlachthof im Ostragehege, Messering (Friedrichstadt). Belegt
    (Wikipedia): Gesamthöhe 2,95 m, Stier (Zöblitzer Serpentin) 53 cm hoch, Granitsockel mit zwei Löwenköpfen
    und je einem halbrunden Becken an den Langseiten, Untersockel aus Granodiorit. Grundriss aus Fotos
    geschätzt."""
    s = Soup()
    G = GRANITE
    # runde gepflasterte Insel mit Granitbord, Sockelkranz
    zi = 0.10
    s.add(lathe([(2.9, -SKIRT), (2.9, zi - 0.02), (2.86, zi), (0.5, zi)], 32, G, cap1=False))
    q = Soup()
    # Unterbau mit dunklem Fuß und Wulst, beidseits halbrunde Tröge
    q.add(stack([(1.06, 1.36, 0), (1.06, 1.36, 0.12), (1.0, 1.30, 0.13), (1.0, 1.30, 0.62),
                 (1.08, 1.38, 0.66), (1.08, 1.38, 0.74), (0.96, 1.26, 0.78)], G))
    for sx in (-1, 1):
        tr = lathe([(0.50, 0), (0.50, 0.12), (0.46, 0.13), (0.46, 0.62), (0.51, 0.66), (0.51, 0.74), (0.39, 0.74),
                    (0.36, 0.50)], 16, G)
        tr.poly(circle(0.37, 16, 0.66, a0=math.pi / 16), WATER)
        q.add(tr.move(sx * 0.52, 0, 0))
        # Löwenmaske mit Auslauf über dem Trog
        q.add(ico(0.16, G, 1).scale(0.45, 1.0, 1.1).move(sx * 0.44, 0, 1.22))
        q.add(cyl(0.02, 0.10, 6, BRONZE).rot((0, 1, 0), sx * 90).move(sx * 0.47, 0, 1.16))
    # geböschter Pfeiler, Gesims, Plinthe
    zp = 0.76
    q.add(stack([(0.90, 1.20, zp), (0.84, 1.14, zp + 1.38), (0.88, 1.18, zp + 1.42), (1.02, 1.32, zp + 1.50),
                 (1.02, 1.32, zp + 1.58), (0.84, 1.14, zp + 1.62)], G))
    q.add(cbox(0, 0.60 - 0.012, zp + 0.62, 0.62, 0.02, 0.52, G))               # Inschriftfeld vorn
    zb = zp + 1.62
    q.add(stack([(0.62, 1.08, zb), (0.62, 1.08, zb + 0.13)], G))
    kq = (2.95 - 0.53 - zi) / (zb + 0.13)
    s.add(q.scale(kq, kq, kq).move(0, 0, zi))
    b = bull(DARK)
    k = 0.53 / max(v.z for v in b.v)
    s.add(b.scale(k, k, k).move(0, -0.03, 2.95 - 0.53))
    return s, ("Stierbrunnen (Georg Wrba 1910, Schlachthof Ostragehege, Messering): geböschter Granitpfeiler "
               "0,8 × 1,1 m mit Gesims, an beiden Langseiten (±X) halbrunde Tröge unter Löwenmasken, obenauf "
               "stehender Stier aus dunklem Serpentin (53 cm, Kopf nach +Y, über der Inschriftseite); "
               "Gesamthöhe 2,95 m (belegt). Runde Pflasterinsel Ø 5,8 m mit Granitbord (geschätzt). "
               "Sockelkranz 0,6 m unter dem Ursprung.")


def _wheel(m, r=0.44, w=0.32, n=12):
    """Mühlrad, Achse X, Mitte im Ursprung."""
    s = cyl(r * 0.72, w, n, m, z0=-w / 2)
    s.add(cyl(r, 0.04, n, m, z0=-w / 2 - 0.04)).add(cyl(r, 0.04, n, m, z0=w / 2))
    for k in range(n):
        s.add(cbox(r * 0.84, 0, -w / 2, r * 0.30, 0.035, w, m).rot((0, 0, 1), 360 * k / n))
    return s.rot((0, 1, 0), 90)


@model(views=((20, 8), (200, 25)), close=((0, 0, 4.0), 2.6, ((15, 5), (200, 5))))
def mon_muellerbrunnen():
    """Müllerbrunnen (Lossow & Viehweger 1902, Figur nach Robert Henze, Kopie 1986), F.-C.-Weiskopf-Platz,
    Dresden-Plauen. Keine Maße belegt; aus Fotos geschätzt (Figur lebensgroß angenommen → Gesamthöhe ca. 6,2 m,
    Becken außen ca. 6,8 m)."""
    s = Soup()
    D = DARK
    # runde Plattenstufe mit Sockelkranz
    s.add(lathe([(4.35, -SKIRT), (4.35, 0.12), (4.30, 0.15), (3.2, 0.15)], 40, GRANITE, cap1=False))
    # Becken mit dickem, gewölbtem Wulstrand
    z0 = 0.15
    s.add(lathe([(3.22, z0), (3.30, z0 + 0.10), (3.40, z0 + 0.32), (3.40, z0 + 0.52), (3.30, z0 + 0.70),
                 (3.12, z0 + 0.78), (2.94, z0 + 0.76), (2.82, z0 + 0.66), (2.78, z0 + 0.50), (2.76, z0 + 0.15)],
                40, D))
    s.poly(circle(2.77, 40, z0 + 0.56, a0=math.pi / 40), WATER)
    for k in range(4):                      # vier Fischungeheuer über dem Rand
        fsh = limb([(-0.55, 0.84, 0.26, 0.20), (-0.20, 0.98, 0.38, 0.27), (0.20, 0.94, 0.36, 0.28),
                    (0.42, 0.66, 0.30, 0.22), (0.46, 0.34, 0.22, 0.14)], 8, D, sub=2)
        fsh.add(ico(0.20, D, 1).scale(1.5, 1.0, 0.9).move(0, -0.48, 1.00))
        s.add(place(fsh, 45 + 90 * k, 3.12, 0.0))
    # Mittelsockel mit vier angesetzten Halbschalen
    zf = z0 + 0.15
    s.add(stack([(2.0, 2.0, zf), (2.0, 2.0, 1.42), (2.24, 2.24, 1.48), (2.24, 2.24, 1.72), (1.72, 1.72, 1.80)], D))
    for k in range(4):
        bw = lathe([(0.34, zf), (0.24, 0.62), (0.28, 0.92), (0.56, 1.14), (0.88, 1.38), (0.93, 1.44), (0.93, 1.72),
                    (0.78, 1.72), (0.74, 1.50)], 14, D)
        bw.poly(circle(0.75, 14, 1.65, a0=math.pi / 14), WATER)
        s.add(place(bw, 90 * k, 1.05, 0))
        for sgn in (-1, 1):                 # Wasserspeier-Köpfe an den Ecken
            s.add(place(ico(0.13, D, 1).scale(1, 1.3, 1), 90 * k + sgn * 33, 1.42, 1.55))
    # Mühlradgeschoss: Kern, vier Eckpfeiler mit Schmuckbändern, Mühlrad vorn und hinten
    s.add(stack([(1.56, 1.56, 1.78), (1.30, 1.30, 2.00), (1.02, 1.02, 2.02), (1.02, 1.02, 3.0)], D))
    for sx in (-1, 1):
        for sy in (-1, 1):
            s.add(stack([(0.40, 0.40, 1.98), (0.36, 0.36, 2.06), (0.36, 0.36, 2.48), (0.42, 0.42, 2.50),
                         (0.42, 0.42, 2.70), (0.36, 0.36, 2.72), (0.36, 0.36, 3.0)], D, cx=sx * 0.52, cy=sy * 0.52))
    for sy in (-1, 1):
        s.add(_wheel(BRONZE).move(0, sy * 0.50, 2.46))
    # schwerer Schmuckblock mit Segmentgiebeln, darüber Felskuppe
    s.add(stack([(1.44, 1.44, 2.88), (1.44, 1.44, 3.02), (1.74, 1.74, 3.10), (1.80, 1.80, 3.62), (1.66, 1.66, 3.70)],
                D, r=0.16))
    for k in range(4):
        arc = [(-0.74, 3.60)] + [(math.cos(math.pi * (1 - i / 6)) * 0.74, 3.60 + math.sin(math.pi * i / 6) * 0.26)
                                 for i in range(1, 6)] + [(0.74, 3.60)]
        s.add(prism_y(arc, 0.55, 0.90, D).rot((0, 0, 1), 90 * k))
        for sgn in (-1, 1):                 # Köpfe an den Ecken des Schmuckblocks
            s.add(place(ico(0.16, D, 1).scale(1, 0.8, 1.2), 90 * k + 45, 1.20, 3.36))
    s.add(lathe([(0.86, 3.66), (0.80, 3.92), (0.62, 4.14), (0.36, 4.26), (0.0, 4.30)], 10, D, cap0=False, cap1=False))
    # Müllerbursche: Hut in der gesenkten Rechten, Sack über der linken Schulter, Schürze
    zt = 4.28
    f, j = F("m", "miller", BRONZE)
    f.add(robe([(0.52, 0.0, 0.02, 0.27, 0.22), (0.80, 0.0, 0.02, 0.22, 0.17), (1.02, 0, 0.01, 0.18, 0.14)], BRONZE, 10))
    hr = j["Hand_R"]
    c = hr[0] + (hr[1] - hr[0]) * 0.9
    f.add(lathe([(0.16, 0.0), (0.165, 0.015), (0.09, 0.03), (0.08, 0.09), (0.0, 0.11)], 8, BRONZE)
          .rot((0, 1, 0), 75).move(c.x + 0.02, c.y, c.z - 0.10))                                    # Hut
    sh = j["UpperArm_L"][0]
    f.add(ico(0.20, BRONZE, 1).scale(0.9, 0.8, 1.35).move(sh.x + 0.02, sh.y - 0.22, sh.z - 0.10))   # Sack
    hd = j["Head"][0]
    f.add(ico(0.115, BRONZE, 1).scale(1.0, 1.0, 0.85).move(hd.x, hd.y - 0.03, hd.z + 0.10))         # Haarschopf
    ground(f)
    kf = 1.92 / max(v.z for v in f.v)
    s.add(f.scale(kf, kf, kf).move(0, 0, zt))
    return s, ("Müllerbrunnen (F.-C.-Weiskopf-Platz, Plauen): rundes dunkles Sandsteinbecken Ø 6,8 m mit dickem "
               "Wulstrand und vier Fischungeheuern, quadratischer Mittelsockel mit vier Halbschalen, darüber "
               "Mühlradgeschoss mit vier Eckpfeilern (Mühlrad nach ±Y), schwerer Schmuckblock mit Felskuppe und "
               "bronzenem Müllerburschen (Hut in der Rechten, Sack über der Schulter, blickt nach +Y); 6,2 m hoch. "
               "Maße geschätzt, Wasserspeier und Ornamentik stark vereinfacht. Sockelkranz 0,6 m unter dem Ursprung.")


@model(views=((25, 12), (150, 25)), close=((0, -0.9, 1.1), 1.7, ((20, 8), (200, 10))))
def mon_maerchenbrunnen():
    """Märchenbrunnen (1903, Schilling & Graebner), Hermann-Seidel-Park, Striesen. Belegt (Wikipedia):
    Mittelteil 2,10 m hoch, Lausitzer Granit, halbrundes Becken, seitlich Bänke mit Froschwangen, Metallrelief
    »Brüderchen und Schwesterchen«. Grundriss und übrige Höhen aus Fotos geschätzt."""
    s = Soup()
    G = GRANITE
    CX, CY, RO = 0.0, 1.9, 2.35

    def pol(a, r, z):
        return V((CX + math.cos(math.radians(a)) * r, CY + math.sin(math.radians(a)) * r, z))
    # gepflasterte Vorfläche mit Granitbord (Ellipse), Sockelkranz
    zp = 0.08
    ap = circle(1.0, 36, 0.0, 0.0, 0.95, rx=2.55, ry=1.80)
    s.add(B_skirt(ap, G, zp))
    # Bänke: Sitz mit niedriger Rückenlehne, im Bogen links und rechts des Mittelteils
    prof = [(RO - 0.62, zp), (RO - 0.62, 0.36), (RO - 0.66, 0.40), (RO - 0.66, 0.46), (RO - 0.16, 0.46),
            (RO - 0.16, 0.64), (RO, 0.64), (RO, zp)]
    for a0, a1 in ((198.0, 259.0), (281.0, 342.0)):
        rings = [[pol(a0 + (a1 - a0) * i / 8, r, z) for r, z in prof] for i in range(9)]
        s.add(loft(rings, G))
    for a in (196.0, 344.0):                # Wangen mit Fröschen
        blk = stack([(0.60, 0.86, zp), (0.60, 0.86, 0.66), (0.54, 0.80, 0.80), (0.40, 0.62, 0.86)], G, r=0.10)
        blk.add(ico(0.17, G, 1).scale(1.0, 1.35, 0.75).move(0, 0.12, 0.90))
        blk.add(ico(0.09, G, 1).move(0, 0.34, 0.95))
        p = pol(a, RO - 0.36, 0)
        s.add(blk.rot((0, 0, 1), a - 90 + 90).move(p.x, p.y, 0))
    # Mittelteil: geböschter Unterbau, Rahmen mit Öffnung, abgerundeter Kopf
    yc = CY - RO + 0.30
    q = Soup()
    q.add(stack([(1.32, 0.84, zp), (1.26, 0.78, 0.78), (1.06, 0.60, 1.00)], G))
    for sx in (-1, 1):
        q.add(cbox(sx * 0.385, 0, 0.98, 0.29, 0.58, 0.68, G))
        q.add(cbox(sx * 0.385, 0, 1.56, 0.32, 0.62, 0.10, G))                 # Kämpferband
    head = [(-0.53, 1.66), (0.53, 1.66), (0.53, 1.88)] + \
           [(0.53 - 0.22 + math.cos(math.radians(a)) * 0.22, 1.88 + math.sin(math.radians(a)) * 0.22)
            for a in (30, 60, 90)] + \
           [(-0.53 + 0.22 + math.cos(math.radians(a)) * 0.22, 1.88 + math.sin(math.radians(a)) * 0.22)
            for a in (90, 120, 150)] + [(-0.53, 1.88)]
    q.add(prism_y(head, -0.29, 0.29, G))
    # Metalltreibarbeit in der Öffnung: Blech mit Stämmen, Mädchen und Reh (angedeutet)
    q.add(cbox(0, -0.02, 0.98, 0.50, 0.03, 0.70, BRONZE))
    for x, w in ((-0.17, 0.035), (-0.02, 0.05), (0.15, 0.04)):
        q.add(cbox(x, 0.02, 0.98, w, 0.04, 0.70, BRONZE))
    q.add(ico(0.09, BRONZE, 1).scale(0.9, 0.5, 1.9).move(-0.09, 0.05, 1.18))
    q.add(ico(0.08, BRONZE, 1).scale(1.3, 0.5, 1.2).move(0.10, 0.05, 1.10))
    # Wasserspeier (Fischmaul) über dem Becken
    q.add(ico(0.20, G, 1).scale(1.0, 0.7, 0.9).move(0, 0.36, 0.72))
    q.add(cyl(0.025, 0.10, 6, BRONZE).rot((1, 0, 0), -90).move(0, 0.46, 0.68))
    s.add(q.move(0, yc, 0))
    # Becken vor dem Mittelteil: gerundeter Trog
    by = yc + 0.36 + 0.52
    s.add(ring_basin(lambda e, z: rrect(1.46 - 2 * e, 1.16 - 2 * e, 0.40 - e * 0.8, 3, z, 0, by), 0.58, 0.15, 0.30,
                     G, z0=zp, wl=0.56, lip=0.025))
    s.move(0, -0.95, 0)
    return s, ("Märchenbrunnen (Hermann-Seidel-Park, Striesen): Granit-Mittelteil 2,10 m (belegt) mit "
               "Rahmenöffnung und Metallrelief, davor (+Y) gerundeter Trog, beidseits im Bogen Bänke mit "
               "Froschwangen, gepflasterte Vorfläche 5,1 × 3,6 m mit Bord; Rückseite -Y. Grundriss geschätzt. "
               "Sockelkranz 0,6 m unter dem Ursprung.")


def glass_tree(h, n_post, n_glass, rng):
    """Glasbaum: Bündel aus Messing-Vierkantstäben mit waagerechten Armen, an deren Enden Glasbrocken sitzen."""
    s = Soup()
    posts = [(0.0, 0.0), (0.13, 0.05), (-0.04, 0.14), (0.10, -0.11)][:n_post]
    for i, (x, y) in enumerate(posts):
        s.add(cbox(x, y, 0.0, 0.07, 0.07, h * (1.0 - 0.07 * i), BRASS))
    z = h * 0.26
    k = 0
    while k < n_glass:
        x, y = posts[k % n_post]
        zz = min(z, h * (1.0 - 0.07 * (k % n_post)) - 0.03)
        a = rng.uniform(0, TAU) if k % 3 else (k % 4) * TAU / 4 + 0.4
        ln = rng.uniform(0.22, 0.55) * (1.0 - 0.35 * max(z / h - 0.6, 0.0))
        arm = cbox(ln / 2, 0, -0.012, ln, 0.05, 0.024, BRASS).rot((0, 0, 1), math.degrees(a)).move(x, y, zz)
        s.add(arm)
        sz = rng.uniform(0.17, 0.27)
        g = ico(sz * 0.62, GLASS, 0).scale(rng.uniform(0.8, 1.3), rng.uniform(0.6, 1.0), rng.uniform(0.75, 1.15))
        g.rot((0, 0, 1), rng.uniform(0, 360)).rot((1, 0, 0), rng.uniform(-25, 25))
        s.add(g.move(x + math.cos(a) * (ln + sz * 0.3), y + math.sin(a) * (ln + sz * 0.3), zz + sz * 0.30))
        z += (h * 0.76) / n_glass
        k += 1
    return s


@model(views=((25, 10), (60, 30)), close=((0, 0, 2.2), 2.4, ((20, 5), (110, 10))))
def mon_glasbrunnen():
    """Glasbrunnen (Leoni Wirth 1975), vor dem ehem. Robotron-Komplex, Grunaer Straße/Pirnaischer Platz
    (Glasbrunnenplatz). Belegt (Wikipedia): Terrazzobecken Ø 9,3 m. Höhen der drei Glasbäume aus Fotos
    geschätzt (ca. 2,7 / 3,3 / 3,8 m), Zahl und Lage der Glasbrocken frei verteilt."""
    s = Soup()
    T = STONE
    # Terrazzobecken: niedrige, nach außen geneigte Wand mit breitem Rand
    s.add(lathe([(4.46, -SKIRT), (4.46, 0.0), (4.65, 0.40), (4.65, 0.46), (4.17, 0.46), (4.14, 0.12)], 48, T))
    s.poly(circle(4.15, 48, 0.30, a0=math.pi / 48), WATER)
    s.add(lathe([(1.25, 0.12), (1.25, 0.34), (1.20, 0.36)], 24, GRANITE))               # Mittelplatte
    rng = random.Random(1975)
    for x, y, h, npost, ng in ((0.40, 0.05, 3.80, 4, 34), (-0.20, -0.55, 3.30, 3, 26), (-0.70, 0.35, 2.70, 3, 20)):
        s.add(glass_tree(h - 0.36, npost, ng, rng).move(x, y, 0.36))
    return s, ("Glasbrunnen (Leoni Wirth 1975, Glasbrunnenplatz an der Grunaer Straße): rundes Terrazzobecken "
               "Ø 9,3 m (belegt) mit niedrigem, breitem Rand; in der Mitte drei »Glasbäume« aus gebündelten "
               "Messingstäben mit waagerechten Armen und grünlichen Glasbrocken, 2,7 / 3,3 / 3,8 m hoch "
               "(geschätzt, Brocken frei verteilt). Sockelkranz 0,6 m unter dem Ursprung.")


def dove(m, up):
    """Fliegender Vogel (Kopf +Y), Rumpfmitte im Ursprung; up = Flügelhebung (−0,3 gesenkt … 1 hoch erhoben)."""
    s = limb([(-0.62, -0.03, 0.10, 0.015), (-0.34, 0.0, 0.10, 0.06), (0.0, 0.0, 0.15, 0.13), (0.24, 0.04, 0.12, 0.115),
              (0.40, 0.07, 0.085, 0.085), (0.50, 0.06, 0.06, 0.06), (0.57, 0.04, 0.02, 0.02)], 8, m, sub=2)
    for sx in (-1, 1):
        st = [(0.07, 0.02, 0.05, 0.20, 0.045), (0.36, -0.06, 0.07 + up * 0.30, 0.22, 0.04),
              (0.66, -0.20, 0.08 + up * 0.56, 0.17, 0.03), (0.88, -0.36, 0.08 + up * 0.66, 0.05, 0.015)]
        s.add(loft([[V((sx * x, cy + math.cos(TAU * i / 6) * ch, cz + math.sin(TAU * i / 6) * th)) for i in range(6)]
                    for x, cy, cz, ch, th in st], m))
    return s


@model(views=((35, 10), (250, 15)), close=((0, 0, 1.7), 1.5, ((35, 5), (270, 5))))
def mon_fluegelradbrunnen():
    """Flügelradbrunnen, Hettnerstraße (vor dem Gerhart-Potthoff-Bau der TU, Südvorstadt): Steinkugel mit drei
    fliegenden Vögeln auf geböschtem Sockel, seit der Sanierung von einer quadratischen Holzbank umgeben.
    Keine Maße belegt; aus Fotos geschätzt (Kugel Ø ca. 0,95 m, Gesamthöhe ca. 3,2 m einschließlich 0,4 m
    Banksockel, Bank 3,3 m)."""
    s = Soup()
    S = STONE
    # Betonsockel der Bank mit Sockelkranz, Holzbelag als Rahmen, Kiesfläche innen
    Wo, Wi = 3.30, 2.10
    s.add(B_skirt(rect(Wo - 0.5, Wo - 0.5, 0), GRANITE, 0.38))
    for k in range(4):
        s.add(prism_y([(-Wo / 2, 0.38), (Wo / 2, 0.38), (Wo / 2, 0.44), (-Wo / 2, 0.44)], Wi / 2, Wo / 2, WOOD)
              .rot((0, 0, 1), 90 * k))
    for sx in (-1, 1):
        for sy in (-1, 1):
            c = (Wo + Wi) / 4
            s.add(cbox(sx * c, sy * c, 0.38, (Wo - Wi) / 2, (Wo - Wi) / 2, 0.06, WOOD))
    # geböschter Sockel, Kissenplatte, Kugel mit Fuge
    z0 = 0.38
    s.add(stack([(1.10, 1.10, z0), (0.84, 0.84, z0 + 0.74)], S))
    s.add(stack([(0.56, 0.56, z0 + 0.74), (0.50, 0.50, z0 + 0.84)], S))
    R = 0.475
    zc = z0 + 0.80 + R
    prof = [(math.cos(math.radians(a)) * R, zc + math.sin(math.radians(a)) * R) for a in range(-78, 91, 14)]
    prof = [p for p in prof if p[1] < zc - 0.001] + [(R, zc - 0.012), (R - 0.012, zc), (R, zc + 0.012)] + \
           [p for p in prof if p[1] > zc + 0.02]
    s.add(lathe(prof, 20, S))
    zt = zc + R
    # drei Vögel, alle nach +Y fliegend: zwei unten nebeneinander, einer mit erhobenen Flügeln darüber
    s.add(ico(0.20, S, 1).scale(1.3, 1.5, 0.8).move(0, 0.0, zt + 0.03))
    kb = 0.86
    s.add(dove(S, -0.45).scale(kb, kb, kb * 1.3).rot((0, 0, 1), -8).move(0.24, 0.16, zt + 0.20))
    s.add(dove(S, -0.35).scale(kb, kb, kb * 1.3).rot((0, 0, 1), 10).move(-0.26, 0.08, zt + 0.22))
    s.add(dove(S, 0.85).scale(kb * 1.1, kb * 1.1, kb * 1.3).rot((1, 0, 0), 8).move(0.0, -0.05, zt + 0.52))
    return s, ("Flügelradbrunnen (Hettnerstraße, vor dem Gerhart-Potthoff-Bau): helle Steinkugel Ø 0,95 m mit "
               "Äquatorfuge auf geböschtem Quadersockel, darauf drei fliegende Vögel (Flugrichtung +Y), ringsum "
               "quadratische Holzbank 3,3 m auf Betonsockel; ca. 3,2 m hoch. Maße geschätzt, kein Wasserbecken "
               "(Anlage läuft trocken). Sockelkranz 0,6 m unter dem Ursprung.")


def closeup(name, c, R, views):
    """Kontrollbilder (nicht Teil der Auslieferung) nach tools/blender/monf_tmp/."""
    sc = bpy.context.scene
    cam = sc.camera
    Dd = R / math.sin(cam.data.angle / 2) * 1.02
    for k, (az, el) in enumerate(views):
        a, e = math.radians(az), math.radians(el)
        d = V((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
        cam.location = V(c) + d * Dd
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        sc.render.resolution_x = sc.render.resolution_y = 640
        sc.render.filepath = os.path.join(HERE, "monf_tmp", f"{name}_c{k}.png")
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
