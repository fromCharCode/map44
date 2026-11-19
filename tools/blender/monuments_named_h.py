"""Vierte Runde benannter Dresdner Brunnen nach Fotovorlagen (Wikimedia Commons, nur als Vorlage)
nach godot/assets/models/monuments/mon_<name>.glb.

Aufruf (Projektordner, immer nur ein Blender gleichzeitig):
  flatpak run --filesystem=host org.blender.Blender -b --python "$PWD/tools/blender/monuments_named_h.py" \
      [-- name ...] [--nopreview] [--close]

Bausteine, Konventionen und Materialien stammen aus monuments_build.py, monuments_named_b.py, _d.py und _f.py
(Blender Z-up, Meter, Ursprung = Bodenmitte, Vorderseite +Y; Sockelkranz 0,6 m unter dem Ursprung). Maße: belegt,
wo im Kommentar "belegt" steht, sonst aus den Fotos in data/research/denkmal_fotos/ geschätzt. Zusätzliche
Materialien: Mosaik (blaugrün), Mosaik_braun (Mosaikbrunnen).
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
import monuments_named_f as F6  # noqa: E402
from monuments_build import (L, V, Soup, mat, loft, lathe, cyl, cbox, tube, circle, rrect, rect, build,  # noqa: E402
                             finish, ico, TAU, STONE, BRONZE, GOLD, GRANITE, WATER, stack, limb)
from monuments_named_b import DARK, F, robe, place, ground, rock, floor0  # noqa: E402
from monuments_named_d import crect  # noqa: E402
from monuments_named_f import octa, skirt, B_skirt, rosette, SKIRT  # noqa: E402

MOSAIC, MOSAIC_BROWN = "Mosaik", "Mosaik_braun"

B.POSES.update({
    # Schweinetreiber: breitbeinig über dem Schwein, vorgebeugt, beide Hände an den Ohren des Tiers
    "swine": [("Spine1", (0.0, 0.55, 0.84)), ("Head", (0.05, 0.70, 0.71))]
    + B._legs(((-0.40, 0.55, -0.73), (-0.02, -0.42, -0.91)), ((0.40, -0.05, -0.92), (0.04, -0.50, -0.87)))
    + B._arms(((-0.12, 0.42, -0.90), (0.10, 0.50, -0.86)), ((0.12, 0.42, -0.90), (-0.10, 0.50, -0.86))),
    # Putto: sitzt, ein Arm erhoben
    "putto": B._legs(((-0.18, 1.0, 0.05), (0.0, 0.45, -0.90)), ((0.18, 1.0, 0.15), (0.0, 0.30, -0.95)))
    + B._arms(((-0.40, 0.50, -0.75), (0.20, 0.85, 0.10)), ((0.55, 0.45, 0.30), (0.10, 0.50, 0.85))),
})


def mats():
    F6.mats()
    mat(MOSAIC, "#2E6E7A", 0.35)
    mat(MOSAIC_BROWN, "#77664F", 0.55)


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


def _rz(prof, z):
    """Halbmesser eines Drehprofils [(r, z)] in der Höhe z (linear interpoliert)."""
    for (r0, z0), (r1, z1) in zip(prof, prof[1:]):
        if z0 <= z <= z1 and z1 > z0:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return prof[-1][0]


def lattice(prof, n, turn, m, steps=9, r=0.022):
    """Rautennetz auf einem Drehkörper: je n links- und rechtsgängige Wendeln (Dreikantstäbe)."""
    s = Soup()
    z0, z1 = prof[0][1], prof[-1][1]
    for sgn in (-1, 1):
        for k in range(n):
            pts = []
            for i in range(steps + 1):
                t = i / steps
                z = z0 + (z1 - z0) * t
                a = TAU * k / n + sgn * turn * t
                rr = _rz(prof, z) + r * 0.2
                pts.append(V((math.cos(a) * rr, math.sin(a) * rr, z)))
            s.add(tube(pts, r, 3, m, caps=False))
    return s


@model(views=((20, 8), (200, 28)), close=((0, 0, 4.2), 2.0, ((20, 5), (20, 35))))
def mon_mosaikbrunnen():
    """Mosaikbrunnen (Hans Poelzig und Marlene Moeschke-Poelzig 1926), Großer Garten, Wegekreuz südlich der
    Hauptallee. Wikipedia nennt keine Maße; alles aus Fotos geschätzt (Becken Ø ca. 5 m und 1,1 m hoch,
    Gesamthöhe ca. 5,9 m). Drei übereinander stehende Blütenkelche über runder Schale, ganz mit Mosaik belegt."""
    s = Soup()
    N = 36
    # Plattenring im Wegekreuz mit Sockelkranz
    s.add(lathe([(3.30, -SKIRT), (3.30, 0.03), (2.1, 0.03)], N, GRANITE, cap1=False))
    # Becken: nach oben ausschwingende Wand (erdbraun), Wulstrand, innen blaue flache Mulde
    Rr = 2.50
    s.add(lathe([(2.12, 0.03), (2.14, 0.30), (2.20, 0.62), (2.32, 0.88), (2.46, 1.02), (Rr, 1.06), (Rr, 1.10),
                 (Rr - 0.06, 1.13), (Rr - 0.20, 1.13)], N, MOSAIC_BROWN, cap0=False, cap1=False))
    s.add(lathe([(Rr - 0.20, 1.13), (Rr - 0.26, 1.08), (1.9, 0.86), (0.6, 0.74)], N, MOSAIC, cap0=False, cap1=False))
    s.poly(circle(Rr - 0.34, N, 1.03, a0=math.pi / N), WATER)
    # flache Spitzbogenrippen auf der Beckenwand
    wall = [(2.12, 0.03), (2.14, 0.30), (2.20, 0.62), (2.32, 0.88), (2.46, 1.02)]
    for k in range(12):
        for sgn in (-1, 1):
            pts = []
            for i in range(6):
                t = i / 5
                z = 0.08 + 0.86 * t
                a = TAU * (k + 0.5) / 12 + sgn * (TAU / 24) * (1.0 - t ** 1.6)
                rr = _rz(wall, z) + 0.006
                pts.append(V((math.cos(a) * rr, math.sin(a) * rr, z)))
            s.add(tube(pts, 0.02, 3, GOLD, caps=False))
    # Fußkelch
    s.add(lathe([(0.56, 0.74), (0.56, 1.00), (0.60, 1.20), (0.64, 1.30), (0.64, 1.34), (0.40, 1.34)], 20, MOSAIC,
                cap0=False, cap1=False))
    # großer Kelch: schlanker Trichter mit weit ausladender Lippe, obenauf flache Wasserschale
    p1 = [(0.40, 1.34), (0.42, 1.80), (0.47, 2.30), (0.56, 2.80), (0.70, 3.25), (0.90, 3.62), (1.10, 3.88),
          (1.23, 4.04)]
    s.add(lathe(p1, 24, MOSAIC, cap0=False, cap1=False))
    s.add(lathe([(1.23, 4.04), (1.25, 4.09), (1.23, 4.14), (1.12, 4.14), (1.08, 4.07), (0.30, 4.07)], 24,
                MOSAIC_BROWN, cap0=False, cap1=False))
    s.poly(circle(1.09, 24, 4.11, a0=math.pi / 24), WATER)
    s.add(lattice(p1, 10, TAU * 0.30, GOLD, steps=10))
    # mittlerer Kelch (rotbraun-golden gerautet)
    p2 = [(0.34, 4.07), (0.35, 4.45), (0.40, 4.78), (0.50, 5.02), (0.59, 5.14)]
    s.add(lathe(p2, 20, MOSAIC_BROWN, cap0=False, cap1=False))
    s.add(lathe([(0.59, 5.14), (0.60, 5.18), (0.58, 5.21), (0.50, 5.21), (0.47, 5.17), (0.18, 5.17)], 20,
                MOSAIC_BROWN, cap0=False, cap1=False))
    s.poly(circle(0.48, 20, 5.19, a0=math.pi / 20), WATER)
    s.add(lattice(p2, 8, TAU * 0.22, GOLD, steps=6, r=0.016))
    # oberer, goldener, kannelierter Kelch mit dunkler Kuppe
    s.add(lathe([(0.20, 5.17), (0.19, 5.30), (0.23, 5.50), (0.30, 5.66), (0.31, 5.72), (0.26, 5.74), (0.14, 5.74)],
                16, GOLD, cap0=False, cap1=False))
    for k in range(16):
        a = TAU * k / 16
        s.add(tube([V((math.cos(a) * 0.205, math.sin(a) * 0.205, 5.30)), V((math.cos(a) * 0.245, math.sin(a) * 0.245, 5.50)),
                    V((math.cos(a) * 0.315, math.sin(a) * 0.315, 5.68))], 0.018, 3, GOLD, caps=False))
    s.add(lathe([(0.15, 5.74), (0.14, 5.82), (0.09, 5.88), (0.0, 5.90)], 12, MOSAIC, cap0=False))
    return s, ("Mosaikbrunnen (Poelzig 1926, Großer Garten): runde, nach oben ausschwingende Mosaikschale Ø 5,0 m, "
               "1,1 m hoch, darüber drei übereinander stehende Blütenkelche (Lippen Ø 2,5 / 1,2 / 0,6 m) mit "
               "goldenem Rautennetz, oberster Kelch golden mit dunkler Kuppe; 5,9 m hoch. Alle Maße aus Fotos "
               "geschätzt; Mosaik nur als Farbflächen (blaugrün/erdbraun) mit Goldrippen. Plattenring Ø 6,6 m, "
               "Sockelkranz 0,6 m unter dem Ursprung.")


def pig(m):
    """Schwein in Lebensgröße (Rücken ca. 0,75 m), Kopf nach +Y und an den Ohren hochgezogen, Klauen auf z = 0."""
    s = limb([(-0.66, 0.52, 0.04, 0.04), (-0.56, 0.50, 0.19, 0.21), (-0.20, 0.47, 0.25, 0.27),
              (0.22, 0.49, 0.24, 0.26), (0.48, 0.58, 0.21, 0.22), (0.68, 0.72, 0.17, 0.17), (0.84, 0.86, 0.11, 0.105),
              (0.94, 0.95, 0.08, 0.075), (0.97, 0.98, 0.07, 0.065)], 10, m, sub=2)
    for sx in (-1, 1):
        s.add(ico(0.10, m, 0).scale(0.45, 1.0, 1.3).rot((1, 0, 0), -35).move(sx * 0.14, 0.60, 0.93))     # Ohr
        s.add(limb([(0.34, 0.40, 0.085, 0.10), (0.40, 0.20, 0.055, 0.06), (0.42, 0.0, 0.05, 0.055)], 6, m,
                   x0=sx * 0.15, sub=2))
        s.add(limb([(-0.44, 0.42, 0.10, 0.13), (-0.50, 0.20, 0.06, 0.065), (-0.46, 0.0, 0.05, 0.055)], 6, m,
                   x0=sx * 0.16, sub=2))
    return s


@model(views=((30, 8), (250, 20)), close=((0, 0, 2.15), 0.85, ((30, 5), (90, 5), (250, 5))))
def mon_schweinetreiberbrunnen():
    """Schweinetreiberbrunnen (»Metzger mit Schwein«, Georg Wrba 1922), ehem. Schlachthof im Ostragehege,
    Messering 26 (Innenhof Sportgymnasium). Belegt (Wikipedia): achteckiges Becken Ø ca. 2,60 m, Bronzeplatte
    50 × 55 cm, quadratischer Sandsteinsockel. Höhen aus Fotos geschätzt (Sockel ca. 1,5 m, Gruppe ca. 1,1 m)."""
    s = Soup()
    S = STONE
    # Plattenkranz mit Sockelkranz, achteckiges Becken mit breiter, niedriger Brüstung
    s.add(skirt(octa(1.72, 0), GRANITE, top=0.04))
    s.add(loft([octa(1.72, 0.04), octa(1.2, 0.04)], GRANITE, orient=V((0, 0, 1)), cap0=False, cap1=False))
    Rb, hb = 1.30, 0.38
    s.add(loft([octa(Rb, 0.0), octa(Rb, hb - 0.04), octa(Rb - 0.03, hb), octa(Rb - 0.30, hb), octa(Rb - 0.32, 0.12)],
               S, orient=V((0, 0, 1))))
    s.poly(octa(Rb - 0.315, hb - 0.10), WATER)
    # Sockel: Quader, Schaft mit gefasten Ecken, ausladende Deckplatte
    s.add(stack([(0.68, 0.68, 0.10), (0.68, 0.68, 0.74), (0.60, 0.60, 0.77)], S))
    s.add(loft([crect(0.54, 0.54, 0.09, 0.77), crect(0.54, 0.54, 0.09, 1.40)], S, orient=V((0, 0, 1))))
    s.add(stack([(0.54, 0.54, 1.38), (0.56, 0.56, 1.42), (0.70, 0.74, 1.49), (0.70, 0.74, 1.56)], S))
    zt = 1.56
    s.add(cbox(0, 0, zt, 0.50, 0.55, 0.03, BRONZE))                                   # Bronzeplatte (belegt)
    # Treiber mit Lederschürze, das Schwein zwischen den Beinen
    f, j = F("m", "swine", BRONZE)
    lo = min(v.z for v in f.v)
    f.move(0, 0, -lo)
    hip = j["UpperLeg_L"][0] + V((0, 0, -lo))
    f.add(robe([(hip.z - 0.42, 0.0, hip.y + 0.10, 0.25, 0.13), (hip.z - 0.15, 0.0, hip.y + 0.05, 0.24, 0.15),
                (hip.z + 0.10, 0.0, hip.y + 0.02, 0.19, 0.15)], BRONZE, 10))            # Schürze
    f.scale(1.22, 1.15, 1.0)
    p = pig(BRONZE).scale(0.85, 0.74, 0.74).move(0.0, hip.y * 1.15 + 0.10, 0)
    f.add(p)
    ys = [v.y for v in f.v]
    f.move(0, -(min(ys) + max(ys)) / 2, 0)
    k = 1.10 / max(v.z for v in f.v)
    s.add(f.scale(k, k, k).move(0, 0, zt + 0.03))
    return s, ("Schweinetreiberbrunnen (Georg Wrba 1922, Messering 26, ehem. Schlachthof): achteckiges "
               "Sandsteinbecken Ø 2,6 m (belegt) mit niedriger breiter Brüstung, quadratischer Sandsteinsockel "
               "mit gefastem Schaft und Deckplatte (1,56 m, geschätzt), Bronzeplatte 50 × 55 cm (belegt), "
               "darauf vorgebeugter Treiber über dem Schwein, das er an den Ohren packt (Blick +Y, Gruppe "
               "1,1 m, geschätzt); gesamt ca. 2,7 m. Sockelkranz 0,6 m unter dem Ursprung.")


def _lobed(a, b, bulge, n, z, e=0.0):
    """Barocker Beckengrundriss: abgerundetes Rechteck (Halbachsen a, b) mit vorgewölbter Mitte der Langseiten."""
    pts = []
    for i in range(n):
        t = TAU * (i + 0.5) / n
        c, sn = math.cos(t), math.sin(t)
        x = (a - e) * math.copysign(abs(c) ** 0.55, c)
        y = (b - e) * math.copysign(abs(sn) ** 0.55, sn)
        y += math.copysign(bulge * max(0.0, 1.0 - (x / (a * 0.42)) ** 2) ** 1.5, sn) * (abs(sn) ** 2)
        pts.append(V((x, y, z)))
    return pts


@model(views=((25, 10), (205, 25)), close=((0, 0, 1.9), 1.5, ((25, 5), (160, 8))))
def mon_nymphenbrunnen():
    """Westlicher Nymphenbrunnen (Benjamin Thomae 1739–42), Neustädter Markt, am Beginn der Hauptstraße
    (Innere Neustadt); der östliche ist das Gegenstück. Keine Maße belegt; aus Fotos geschätzt (Becken ca.
    5,0 × 3,9 m, Brüstung 0,85 m, Gruppe ca. 2,2 m breit, Gesamthöhe ca. 2,7 m)."""
    s = Soup()
    S, D = STONE, DARK
    N = 48
    a, b, bg = 2.50, 1.80, 0.26

    def R(e, z):
        return _lobed(a, b, bg, N, z, e)
    # Stufe mit Sockelkranz
    s.add(B_skirt(R(-0.45, 0), GRANITE, 0.12))
    # Becken: Sockelzone, Wand, kräftiger Wulstrand
    z0, hb = 0.12, 0.85
    s.add(loft([R(-0.06, z0), R(-0.06, z0 + 0.24), R(0.0, z0 + 0.28), R(0.0, z0 + hb - 0.22), R(-0.05, z0 + hb - 0.17),
                R(-0.10, z0 + hb - 0.09), R(-0.08, z0 + hb - 0.02), R(0.0, z0 + hb), R(0.30, z0 + hb),
                R(0.34, z0 + hb - 0.12), R(0.36, z0 + 0.25)], S, orient=V((0, 0, 1))))
    s.poly(R(0.35, z0 + hb - 0.20), WATER)
    # Quadersockel im Becken
    zp = z0 + hb + 0.22
    s.add(stack([(2.50, 1.50, z0 + 0.25), (2.50, 1.50, zp)], S))
    # Felssockel der Gruppe mit wasserspeiendem Delphinkopf vorn
    g = Soup()
    g.add(floor0(rock(0.95, D, 3.1, sx=1.20, sy=0.72, sz=0.62).move(0, -0.05, 0.12)))
    g.add(floor0(rock(0.50, D, 7.7, sx=1.2, sy=1.0, sz=0.8).move(0.80, 0.0, 0.10)))
    g.add(floor0(rock(0.45, D, 5.2, sx=1.2, sy=0.9, sz=0.7).move(-0.80, 0.05, 0.08)))
    g.add(limb([(-0.05, 0.42, 0.30, 0.20), (0.30, 0.38, 0.28, 0.22), (0.52, 0.30, 0.22, 0.17),
                (0.68, 0.22, 0.13, 0.09)], 8, D, x0=-0.25, sub=2))                        # Delphinkopf
    g.add(tube([V((-0.25, 0.10, 0.55)), V((-0.65, -0.10, 0.70)), V((-0.95, -0.22, 0.58)), V((-1.05, -0.05, 0.40))],
               0.10, 6, D, rs=[0.16, 0.13, 0.09, 0.04]))                                 # Delphinschwanz
    # Nymphe: sitzt auf dem Fels, Unterschenkel hängen, halb nach links gewandt, Tuch über dem Schoß
    f, j = F("f", "sit", D)
    ground(f)
    f.add(robe([(0.30, 0.0, 0.22, 0.26, 0.34), (0.50, 0.0, 0.16, 0.25, 0.32), (0.62, 0.0, 0.06, 0.22, 0.2)], D, 10))
    g.add(f.rot((0, 0, 1), -28).move(0.12, -0.28, 0.28))
    # Putto links neben ihr (vom Betrachter aus), ihr zugewandt
    c, jc = F("k", "putto", D)
    ground(c)
    kc = 0.80
    g.add(c.scale(kc, kc, kc).rot((0, 0, 1), 40).move(0.85, -0.22, 0.16))
    s.add(g.move(0, 0, zp))
    return s, ("Westlicher Nymphenbrunnen (Thomae 1739–42, Neustädter Markt): geschweiftes Sandsteinbecken "
               "5,0 × 3,9 m mit vorgewölbten Langseiten und Wulstrand (Brüstung 0,85 m) auf einer Stufe; im "
               "Becken Quadersockel, darauf dunkle Sandsteingruppe: sitzende Nymphe auf Fels mit Delphin, "
               "Putto neben ihr (Schauseite +Y). Gesamthöhe ca. 2,7 m. Alle Maße geschätzt, Gruppe stark "
               "vereinfacht. Sockelkranz 0,6 m unter dem Ursprung.")


@model(views=((35, 10), (215, 25)), close=((0, 0, 1.9), 1.2, ((35, 5), (125, 5))))
def mon_steinblumenbrunnen():
    """Steinblumenbrunnen, Gartenheimsiedlung Gruna (Platz an der Straße Am Anfang). Keine Maße belegt; aus Fotos
    geschätzt (Trog ca. 2,2 × 2,2 m, Rand 0,85 m über dem Pflaster, Gesamthöhe ca. 2,9 m). Steinkegel aus
    Blättern, Blüten, Vögeln und Kindern, bekrönt von einem kannelierten Blütenkelch."""
    s = Soup()
    D = DARK
    # zurückgesetzter Fuß (zugleich Sockelkranz), bauchiger Trog mit ausschwingenden Wänden
    s.add(stack([(1.30, 1.30, -SKIRT), (1.30, 1.30, 0.22)], D))
    W = 2.20
    s.add(loft([rrect(1.40, 1.40, 0.12, 3, 0.20), rrect(1.72, 1.72, 0.20, 3, 0.30), rrect(2.00, 2.00, 0.26, 3, 0.50),
                rrect(W - 0.04, W - 0.04, 0.28, 3, 0.72), rrect(W, W, 0.28, 3, 0.80), rrect(W, W, 0.28, 3, 0.85),
                rrect(W - 0.34, W - 0.34, 0.16, 3, 0.85), rrect(W - 0.44, W - 0.44, 0.14, 3, 0.45)], D,
               orient=V((0, 0, 1))))
    s.poly(rrect(W - 0.37, W - 0.37, 0.15, 3, 0.77), WATER)
    # profilierter Sockel im Trog
    s.add(stack([(1.02, 1.02, 0.45), (1.02, 1.02, 0.90), (0.94, 0.94, 0.95), (0.86, 0.86, 0.97), (0.86, 0.86, 1.10)],
                D))
    for k in range(4):                      # Auslaufröhrchen
        s.add(place(cyl(0.02, 0.10, 6, BRONZE).rot((1, 0, 0), -90), 90 * k + 90, 0.50, 0.93))
    # Kegelkern
    zb = 1.10
    core = [(0.40, zb), (0.50, zb + 0.20), (0.52, zb + 0.60), (0.44, zb + 1.00), (0.34, zb + 1.30), (0.26, zb + 1.46)]
    s.add(lathe(core, 10, D, cap0=False))
    rng = random.Random(1926)
    # Blätter: flache Schuppen, dachziegelartig in Ringen
    rows = 9
    for i in range(rows):
        z = zb + 0.10 + 1.28 * i / (rows - 1)
        rr = _rz(core, z)
        n = max(6, int(round(rr * 20)))
        for k in range(n):
            a = 360.0 * (k + 0.5 * (i % 2)) / n + rng.uniform(-8, 8)
            lf = ico(0.13, D, 0).scale(rng.uniform(0.9, 1.3), 0.38, rng.uniform(1.2, 1.7))
            lf.rot((1, 0, 0), rng.uniform(15, 40)).rot((0, 1, 0), rng.uniform(-35, 35))
            s.add(place(lf, a, rr + rng.uniform(0.0, 0.06), z + rng.uniform(-0.05, 0.05)))
    # große Blüten (Margeriten)
    for a, z, r in ((80, zb + 0.16, 0.21), (130, zb + 0.72, 0.19), (20, zb + 0.95, 0.17), (250, zb + 0.30, 0.20),
                    (200, zb + 0.85, 0.17), (320, zb + 0.55, 0.19)):
        fl = rosette(D, r=r, t=0.07).rot((1, 0, 0), 12)
        s.add(place(fl, a, _rz(core, z) + 0.10, z))
    # Kinder (Kopf und Rumpf) und Vögel, stark vereinfacht
    for a, z in ((150, zb + 0.20), (160, zb + 1.02), (300, zb + 0.95), (10, zb + 0.42)):
        ch = ico(0.105, D, 1).move(0, 0.02, 0.30)
        ch.add(ico(0.13, D, 1).scale(1.0, 0.85, 1.35).move(0, 0, 0.08))
        for sx in (-1, 1):
            ch.add(ico(0.06, D, 0).scale(1.0, 1.6, 1.0).move(sx * 0.08, 0.10, 0.0))
        s.add(place(ch, a, _rz(core, z) + 0.12, z))
    for a, z in ((60, zb + 1.26), (240, zb + 1.18), (100, zb + 0.50)):
        bd = F6.dove(D, -0.4).scale(0.36, 0.36, 0.5).rot((1, 0, 0), 25)
        s.add(place(bd, a, _rz(core, z) + 0.14, z, face="tan"))
    # Blütenkelch als Bekrönung: kannelierter Becher
    zc = zb + 1.42
    s.add(lathe([(0.20, zc), (0.27, zc + 0.08), (0.31, zc + 0.26), (0.30, zc + 0.36), (0.22, zc + 0.36),
                 (0.20, zc + 0.30)], 14, D))
    for k in range(14):
        a = TAU * k / 14
        s.add(tube([V((math.cos(a) * 0.275, math.sin(a) * 0.275, zc + 0.07)),
                    V((math.cos(a) * 0.32, math.sin(a) * 0.32, zc + 0.24)),
                    V((math.cos(a) * 0.30, math.sin(a) * 0.30, zc + 0.35))], 0.026, 4, D))
    return s, ("Steinblumenbrunnen (Gartenheimsiedlung Gruna): dunkler, bauchiger Steintrog 2,2 × 2,2 m mit "
               "ausschwingenden Wänden auf zurückgesetztem Fuß (Rand 0,85 m), im Trog profilierter Sockel mit "
               "vier Auslaufröhrchen, darauf Steinkegel aus Blättern, Margeritenblüten, Kindern und Vögeln, "
               "bekrönt von einem kannelierten Blütenkelch; ca. 2,9 m hoch. Alle Maße geschätzt, Bildwerk nur "
               "als Blatt-/Blütenschuppen angedeutet. Fuß reicht 0,6 m unter den Ursprung.")


def closeup(name, c, R, views):
    """Kontrollbilder (nicht Teil der Auslieferung) nach tools/blender/tmp_h/."""
    sc = bpy.context.scene
    cam = sc.camera
    Dd = R / math.sin(cam.data.angle / 2) * 1.02
    for k, (az, el) in enumerate(views):
        a, e = math.radians(az), math.radians(el)
        d = V((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
        cam.location = V(c) + d * Dd
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        sc.render.resolution_x = sc.render.resolution_y = 640
        sc.render.filepath = os.path.join(HERE, "tmp_h", f"{name}_c{k}.png")
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
