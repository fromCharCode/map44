"""Vierte Runde benannter Dresdner Denkmäler nach Fotovorlagen: godot/assets/models/monuments/mon_<name>.glb.

Aufruf (Projektordner, immer nur ein Blender gleichzeitig):
  flatpak run --filesystem=host org.blender.Blender -b --python "$PWD/tools/blender/monuments_named_g.py" [-- name ...] [--nopreview]

Aufbau, Bausteine und Konventionen wie monuments_named_e.py (Blender Z-up, Meter, Ursprung = Bodenmitte, Vorderseite
+Y; echte Gesamthöhe eingebaut, Maßstab im Spiel 1,0). Wanddenkmäler (Moritzmonument, Schiller-Körner-Denkmal):
Mauerflucht bei Y = 0, das Modell bringt ein eigenes Stück Rückwand mit (hinter Y = 0).
ACHTUNG Seiten: Der Betrachter steht bei +Y; »links im Bild« ist daher +X.
Vorlagen: Wikimedia-Commons-Fotos in data/research/denkmal_fotos/ (nur Vorlage, siehe QUELLEN_standbilder4.txt).
Materialien: Sandstein, Sandstein_dunkel, Bronze, Granit, GranitDunkel, Eisen (wie bisher); neu nur Porzellan.
"""
import math
import os
import sys

import bpy  # noqa: F401
from mathutils import Vector, noise

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import monuments_named_a as A  # noqa: E402
import monuments_named_c as C  # noqa: E402
import monuments_named_e as E  # noqa: E402
from monuments_named_a import (L, V, Soup, mat, loft, lathe, tube, build, finish, ico, TAU,  # noqa: E402
                               stack, STONE, BRONZE, GRANITE, DARK, box, fig, decimate, cb, rod, wreath,
                               cstack, place, PED_M, PED_F)
from monuments_named_e import prism_x, disc_y, athlete  # noqa: E402
from monuments_build import prism_y  # noqa: E402

SDARK, IRON, PORC, MARBLE = "Sandstein_dunkel", "Eisen", "Porzellan", "Marmor"


def mats():
    E.mats()
    mat(PORC, "#E9E9E3", 0.18)          # weißes Meissener Porzellan (Böttger-Medaillon)
    mat(MARBLE, "#E4E1DA", 0.55)        # wie monuments_named_b: hier für die hell restaurierten Relieffiguren


def wstack(levels, m, cx=0.0, y0=0.0):
    """Wie stack, aber an die Wand gestellt: Rückseite bei y0, levels = [(Breite, Ausladung, z), ...]."""
    return loft([L.rect(w, d, z, cx, y0 + d / 2) for w, d, z in levels], m, orient=V((0, 0, 1)))


def lines(n, z0, dz, w, y, m=DARK, h=0.035, x=0.0, vary=0.12):
    """Inschriftzeilen als dünne dunkle Streifen auf der Fläche y (Vorderseite +Y)."""
    s = Soup()
    for i in range(n):
        s.add(cb(x, y + 0.003, z0 - i * dz, w * (1.0 - vary * ((i * 7) % 3) / 2), 0.006, h, m))
    return s


def relief_fig(pose, h, m=STONE, ratio=0.35, rz=0.0, flat=0.55, k=1.1, wide=1.0):
    """Relieffigur: geposter Fußgänger mit Körpermassen, vereinfacht, auf Höhe h skaliert, in y abgeflacht.
    Füße bei z = 0, Mitte bei x = y = 0."""
    f, j = fig(pose, m)
    athlete(f, j, m, k=k)
    f = decimate(f, ratio, m)
    place(f, 0.0, h, rz=rz)
    xs = [v.x for v in f.v]
    ys = [v.y for v in f.v]
    f.move(-(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2, 0)
    return f.scale(wide, flat, 1)


POSES = {
    "rest": (PED_M, []),
    "f_rest": (PED_F, []),
    # Kurfürst Moritz: Schrittstellung, reicht mit der Rechten das Kurschwert schräg nach oben
    "moritz": (PED_M, [
        ("UpperLeg_L", (0.0, 0.32, -1.0)), ("LowerLeg_L", (0.0, 0.05, -1.0)),
        ("UpperLeg_R", (0.0, -0.28, -1.0)), ("LowerLeg_R", (0.0, -0.40, -1.0)),
        ("UpperArm_R", (0.12, 0.75, -0.40)), ("LowerArm_R", (0.0, 0.55, 0.85)),
        ("UpperArm_L", (-0.10, 0.55, -0.80)), ("LowerArm_L", (0.0, 1.0, 0.15))]),
    # Kurfürst August: Ausfallschritt, greift mit der Linken nach dem Schwert, Rechte am eigenen Schwertgriff
    "august": (PED_M, [
        ("UpperLeg_R", (0.0, 0.38, -1.0)), ("LowerLeg_R", (0.0, 0.0, -1.0)),
        ("UpperLeg_L", (0.0, -0.22, -1.0)), ("LowerLeg_L", (0.0, -0.32, -1.0)),
        ("UpperArm_L", (-0.10, 0.85, -0.45)), ("LowerArm_L", (0.0, 1.0, 0.30)),
        ("UpperArm_R", (0.25, -0.10, -1.0)), ("LowerArm_R", (0.10, 0.55, -0.80))]),
}


# ====================================================================== Modelle
MODELS = {}
HEIGHT = {}
VIEWS = {}


def model(fn):
    MODELS[fn.__name__] = fn
    return fn


@model
def mon_moritzmonument():
    """Moritzmonument (Hans Walther II, 1555; ältestes Denkmal Dresdens), Jungfernbastei der Brühlschen Terrasse."""
    zt = 7.5                     # Oberkante Mauerkrone (geschätzt); das Monument überragt sie
    s = Soup()
    # Rückwand: Stück der Festungsmauer mit Kordongesims
    s.add(box(-4.2, -0.5, 0, 4.2, 0, zt - 0.22, SDARK))
    s.add(box(-4.2, -0.56, zt - 0.22, 4.2, 0.07, zt, SDARK))
    # Unterbau bis unter die Konsolen (Form unterhalb der Konsolen nur aus dem Fernfoto, vereinfacht)
    s.add(wstack([(3.2, 0.55, 0), (3.2, 0.55, 0.45), (2.9, 0.40, 0.55), (2.9, 0.40, 3.45)], STONE))
    s.add(wstack([(6.1, 0.30, 3.40), (6.3, 0.42, 3.55), (6.3, 0.42, 3.72), (5.9, 0.26, 3.80)], STONE))
    # Seitenflügel mit den großen Inschrifttafeln, darüber Gesims und zum Säulenbau aufschwingende Wangen
    for sx in (-1, 1):
        g = wstack([(1.80, 0.22, 3.80), (1.80, 0.22, 5.92)], STONE, cx=2.08)
        g.add(wstack([(1.52, 0.03, 4.06), (1.52, 0.03, 5.72)], STONE, cx=2.08, y0=0.22))        # Schrifttafel
        g.add(wstack([(1.66, 0.07, 5.72), (1.66, 0.07, 5.80)], STONE, cx=2.08, y0=0.22))
        g.add(wstack([(1.66, 0.07, 3.98), (1.66, 0.07, 4.06)], STONE, cx=2.08, y0=0.22))
        g.add(lines(13, 5.60, 0.118, 1.36, 0.25, m=SDARK, h=0.014, x=2.08, vary=0.06))
        g.add(wstack([(2.0, 0.30, 5.92), (2.06, 0.36, 5.98), (2.06, 0.36, 6.08)], STONE, cx=2.06))
        wing = [(1.12, 6.08), (3.08, 6.08), (3.0, 6.20), (2.45, 6.26), (1.95, 6.42), (1.62, 6.72), (1.42, 7.10),
                (1.34, 7.42), (1.12, 7.42)]
        g.add(prism_y(wing, 0.0, 0.16, STONE))
        g.add(disc_y(0.11, 0.20, STONE, 10).move(1.33, 0.0, 7.36))                                # Volutenauge
        if sx < 0:
            g.scale(-1, 1, 1)
        s.add(g)
    # Mittelbau: Sockelzone mit Inschrift, Konsolen und Postamente unter den Säulen
    s.add(wstack([(2.0, 0.46, 3.45), (2.0, 0.46, 5.15)], STONE))
    s.add(wstack([(1.36, 0.03, 4.18), (1.36, 0.03, 4.92)], STONE, y0=0.46))
    s.add(lines(5, 4.80, 0.125, 1.16, 0.49, m=SDARK, h=0.022))
    s.add(wstack([(0.44, 0.05, 3.42), (0.44, 0.05, 3.92)], STONE, y0=0.46))                        # »Erneuert …«
    s.add(lines(4, 3.84, 0.10, 0.32, 0.51, m=SDARK, h=0.016))
    for sx in (-1, 1):
        s.add(wstack([(0.50, 0.66, 3.55), (0.60, 0.84, 3.72), (0.60, 0.86, 4.05), (0.54, 0.80, 4.20), (0.48, 0.74, 4.26),
                      (0.48, 0.74, 5.00)], SDARK, cx=sx * 0.97))
        s.add(wstack([(0.58, 0.84, 5.00), (0.58, 0.84, 5.15)], STONE, cx=sx * 0.97))
    s.add(wstack([(2.60, 0.92, 5.15), (2.60, 0.92, 5.25)], STONE))                                 # Standplatte
    # Reliefwand, Pilaster, Säulen (links hell, rechts schwarz verwittert)
    zb, zk = 5.25, 7.55
    s.add(wstack([(1.66, 0.30, zb), (1.66, 0.30, zk)], STONE))
    for sx, m in ((1, STONE), (-1, SDARK)):
        s.add(wstack([(0.30, 0.36, zb), (0.30, 0.36, zk)], STONE, cx=sx * 0.97))
        s.add(lathe([(0.19, zb), (0.19, zb + 0.10), (0.145, zb + 0.17), (0.135, zb + 0.24)], 12, m if sx > 0 else DARK,
                    cx=sx * 0.97, cy=0.64, cap1=False))
        s.add(lathe([(0.135, zb + 0.24), (0.118, zk - 0.26), (0.15, zk - 0.20)], 12, m, cx=sx * 0.97, cy=0.64,
                    cap0=False, cap1=False))
        s.add(lathe([(0.12, zk - 0.22), (0.17, zk - 0.14), (0.20, zk - 0.08)], 12, STONE, cx=sx * 0.97, cy=0.64, cap0=False))
        s.add(stack([(0.44, 0.44, zk - 0.08), (0.44, 0.44, zk)], STONE, cx=sx * 0.97, cy=0.64))
    # Gebälk mit Triglyphenfries, Kranzgesims, flache Abdeckung
    s.add(wstack([(2.46, 0.88, zk), (2.46, 0.88, zk + 0.09), (2.36, 0.80, zk + 0.12), (2.36, 0.80, zk + 0.42),
                  (2.50, 0.90, zk + 0.46), (2.96, 1.10, zk + 0.56), (2.96, 1.10, zk + 0.68), (2.86, 1.04, zk + 0.72),
                  (2.30, 0.78, zk + 0.76), (2.30, 0.78, 8.40)], STONE))
    for i in range(8):
        s.add(cb(-1.05 + i * 0.30, 0.81, zk + 0.27, 0.10, 0.03, 0.26, STONE))
    # Relief: Moritz (links im Bild, +X) übergibt August (rechts, -X) das Kurschwert; dahinter der Tod (Gerippe)
    yr = 0.30
    W = MARBLE
    f = relief_fig("moritz", 1.86, W, rz=90).move(0.36, yr + 0.20, zb)
    s.add(f)
    s.add(relief_fig("august", 1.80, W, rz=-90).move(-0.42, yr + 0.20, zb))
    sk = relief_fig("rest", 1.62, W, ratio=0.15, flat=0.35, k=0.55, wide=0.75).move(0.66, yr + 0.07, zb + 0.10)
    s.add(sk)
    s.add(rod((0.02, yr + 0.26, zb + 1.02), (0.22, yr + 0.26, zb + 2.02), 0.024, BRONZE, n=5, r1=0.010))   # Kurschwert
    s.add(cb(0.06, yr + 0.26, zb + 1.22, 0.24, 0.03, 0.03, BRONZE).rot((0, 1, 0), 11, (0.06, 0, zb + 1.22)))
    s.add(rod((-0.52, yr + 0.34, zb + 0.92), (-0.90, yr + 0.30, zb + 0.38), 0.022, BRONZE, n=5, r1=0.010))  # Augusts Schwert
    for x, r in ((0.10, 0.17), (-0.74, 0.16)):                                                     # abgelegte Helme
        s.add(ico(1.0, W, 1).scale(r, r * 0.8, r * 1.1).move(x, yr + 0.20, zb + r * 1.05))
    # Dreifaltigkeit über den Fürsten: Christus mit Kreuz, Gottvater auf Wolken, Taube
    for x, r in ((0.40, 0.15), (-0.02, 0.18)):
        s.add(ico(1.0, W, 1).scale(r, 0.09, r * 0.75).move(x, yr + 0.03, zb + 1.86))             # Wolke
        s.add(ico(1.0, W, 1).scale(r * 0.70, 0.09, r * 0.95).move(x, yr + 0.05, zb + 2.02))      # Oberkörper
        s.add(ico(r * 0.38, W, 1).move(x, yr + 0.07, zb + 2.02 + r * 1.15))                      # Kopf
    s.add(cb(0.55, yr + 0.04, zb + 2.10, 0.025, 0.03, 0.26, W)).add(cb(0.55, yr + 0.04, zb + 2.16, 0.12, 0.03, 0.025, W))
    s.add(ico(1.0, W, 1).scale(0.17, 0.03, 0.045).rot((0, 1, 0), -12).move(-0.42, yr + 0.03, zb + 1.92))  # Taube
    return s, ("Moritzmonument (Hans Walther II, 1555, mehrfach erneuert; ältestes erhaltenes Denkmal Dresdens) an der "
               "Spitze der Jungfernbastei der Brühlschen Terrasse: Sandstein-Ädikula mit zwei toskanischen Säulen (links "
               "hell, rechts schwarz), Triglyphengebälk und Relief – Kurfürst Moritz (links im Bild, +X) übergibt seinem "
               "Bruder August das Kurschwert, dahinter der Tod, darüber die Dreifaltigkeit; Konsolen, Inschriftfeld, "
               "seitliche Flügel mit großen Schrifttafeln und Volutenwangen. WANDDENKMAL: Mauerflucht Y = 0, eigenes "
               "Mauerstück 8,4 m breit dahinter (Mauerkrone 7,5 m, geschätzt); Vorderseite +Y. Gesamthöhe 8,4 m "
               "(geschätzt aus Figurengröße; Ädikula ab Konsolen 4,85 m, Unterbau bis zum Boden vereinfacht).")


@model
def mon_boettger_stele():
    """Böttger-Stele (Peter Makolies 1982), Brühlscher Garten unterhalb der Jungfernbastei. Höhe geschätzt 2,1 m."""
    s = stack([(1.70, 1.70, 0), (1.70, 1.70, 0.05)], GRANITE)
    s.add(stack([(0.85, 0.85, 0.05), (0.85, 0.85, 0.11)], GRANITE))
    m = STONE
    s.add(cstack([(0.50, 0.40, 0.11), (0.55, 0.44, 0.50), (0.55, 0.44, 0.54), (0.45, 0.33, 0.62)], m, c=0.09))    # Sockel
    s.add(cstack([(0.45, 0.33, 0.62), (0.43, 0.31, 1.46)], m, c=0.10))                                          # Schaft
    yf = 0.16
    s.add(cb(0, 0.0, 1.50, 0.34, 0.30, 0.12, m))
    s.add(ico(0.042, m, 1).move(0, yf, 1.44))                                                                   # Kugel
    for sx in (-1, 1):                                                                                           # Voluten
        s.add(disc_y(0.085, 0.26, m, 12).move(sx * 0.225, -0.13, 1.46))
        s.add(disc_y(0.055, 0.26, m, 10).move(sx * 0.235, -0.13, 1.31))
        s.add(cb(sx * 0.255, 0.0, 1.385, 0.05, 0.26, 0.17, m))
    # ovaler Steinrahmen mit Porzellanmedaillon (Profilbildnis nach rechts im Bild = -X)
    zc, rx, rz = 1.79, 0.25, 0.31
    s.add(disc_y(1.0, 0.15, SDARK, 24).scale(rx, 1, rz).move(0, -0.075, zc))
    s.add(disc_y(1.0, 0.02, PORC, 24).scale(rx - 0.055, 1, rz - 0.06).move(0, 0.062, zc))
    prof = [(-0.13, -0.19), (0.07, -0.19), (0.05, -0.10), (0.10, -0.06), (0.13, 0.0), (0.155, 0.03), (0.13, 0.06),
            (0.135, 0.12), (0.09, 0.18), (0.0, 0.20), (-0.09, 0.17), (-0.15, 0.09), (-0.17, -0.02), (-0.18, -0.12)]
    q = 0.92
    s.add(loft([[V((-x * q * k, y, zc + 0.01 + z * q * k)) for x, z in prof] for y, k in ((0.080, 1.0), (0.095, 0.95),
                                                                                           (0.108, 0.78))], PORC))
    # Inschriften: Name und Lebensdaten am Schaft, Widmung am Sockel
    s.add(lines(5, 1.34, 0.052, 0.17, yf, m=SDARK, h=0.018, vary=0.3))
    s.add(lines(6, 0.47, 0.055, 0.26, 0.22, m=SDARK, h=0.018, vary=0.15))
    top = HEIGHT["mon_boettger_stele"]
    hi = max(v.z for v in s.v)
    s.warp(lambda c: (c.x, c.y, c.z * top / hi))
    return s, ("Böttger-Stele (Peter Makolies, 1982) im Brühlschen Garten an der Kasematten-Böschung: schlanke "
               "Sandsteinstele mit gefasten Kanten auf Sockel und zwei Bodenplatten, Voluten und Kugel am Kopf, darüber "
               "ovaler dunkler Steinrahmen mit weißem Porzellanmedaillon (Profilbildnis Böttgers, blickt nach -X). "
               "Vorderseite +Y. Gesamthöhe ca. 2,1 m (geschätzt). Neues Material: Porzellan.")


@model
def mon_neuber():
    """Denkmal für Caroline Neuber (1776, 1852/1897 erneuert), Dresden-Laubegast. Gesamthöhe geschätzt 2,6 m."""
    m = SDARK
    # roh behauener Felssockel
    rk = cstack([(1.42, 1.36, 0), (1.36, 1.30, 0.45), (1.24, 1.18, 0.90), (1.10, 1.04, 1.0)], m, c=0.30)
    rk.warp(lambda c: (c.x * (1 + 0.10 * noise.noise(Vector((c.x * 3, c.y * 3, c.z * 3 + 1.3)))),
                       c.y * (1 + 0.10 * noise.noise(Vector((c.y * 3, c.x * 3, c.z * 3 + 4.1)))), c.z))
    s = rk
    for a in range(0, 360, 45):                                                                    # Bruchkanten
        r = 0.60 + 0.06 * math.sin(a * 1.7)
        s.add(ico(1.0, m, 1).scale(0.26, 0.16, 0.30).rot((0, 1, 0), 25 + a / 9).move(r, 0, 0.30 + 0.3 * ((a // 45) % 2))
              .rot((0, 0, 1), a + 12))
    w = 0.82
    s.add(stack([(0.98, 0.98, 0.97), (0.98, 0.98, 1.13), (w, w, 1.16), (w, w, 2.08)], m))
    yf = w / 2
    for k in range(4):
        g = Soup()
        g.add(cb(0, yf + 0.006, 1.63, 0.60, 0.012, 0.80, m))                                       # Feld
        for sx in (-1, 1):
            g.add(cb(sx * 0.365, yf + 0.012, 1.63, 0.07, 0.024, 0.86, m))                          # Ecklisene
            g.add(tube([V((sx * 0.365, yf + 0.03, 1.98)), V((sx * 0.365, yf + 0.04, 1.75)), V((sx * 0.365, yf + 0.03, 1.45))],
                       0.03, 5, m, rs=[0.018, 0.034, 0.012]))                                      # Fruchtgehänge
            g.add(ico(0.045, m, 1).move(sx * 0.365, yf + 0.02, 2.03))                              # Rosette
        if k in (1, 3):                                                                            # Seiten: Trophäen (Masken, Instrumente)
            g.add(ico(1.0, m, 1).scale(0.15, 0.03, 0.20).move(0, yf + 0.012, 1.72))
            g.add(cb(0, yf + 0.02, 1.62, 0.03, 0.02, 0.50, m).rot((0, 1, 0), 22, (0, 0, 1.62)))
            g.add(cb(0, yf + 0.02, 1.62, 0.03, 0.02, 0.50, m).rot((0, 1, 0), -22, (0, 0, 1.62)))
        s.add(g.rot((0, 0, 1), 90 * k))
    # Bronzemedaillon mit Brustbild, Schleife darüber, Inschrift
    zc = 1.74
    s.add(disc_y(0.215, 0.022, BRONZE, 20).move(0, yf + 0.012, zc))
    s.add(wreath(0.215, 0.022, BRONZE, n=20).move(0, yf + 0.034, zc))
    s.add(ico(1.0, BRONZE, 1).scale(0.135, 0.035, 0.085).move(0, yf + 0.04, zc - 0.10))            # Büste
    s.add(ico(1.0, BRONZE, 1).scale(0.030, 0.03, 0.05).move(0, yf + 0.045, zc - 0.01))             # Hals
    s.add(ico(1.0, BRONZE, 1).scale(0.055, 0.04, 0.068).move(0.005, yf + 0.05, zc + 0.075))        # Kopf
    s.add(ico(1.0, BRONZE, 1).scale(0.062, 0.035, 0.04).move(0.0, yf + 0.045, zc + 0.125))         # Frisur
    s.add(ico(0.035, BRONZE, 1).move(0, yf + 0.04, zc + 0.255))                                    # Schleifenknoten
    for sx in (-1, 1):
        s.add(ico(1.0, BRONZE, 1).scale(0.085, 0.022, 0.04).rot((0, 1, 0), -sx * 14).move(sx * 0.095, yf + 0.035, zc + 0.265))
        s.add(tube([V((sx * 0.16, yf + 0.03, zc + 0.25)), V((sx * 0.235, yf + 0.03, zc + 0.21)), V((sx * 0.25, yf + 0.03, zc + 0.12))],
                   0.02, 4, BRONZE, rs=[0.022, 0.018, 0.008]))
    for zz, lw, lh in ((1.42, 0.50, 0.045), (1.355, 0.56, 0.026), (1.30, 0.56, 0.026)):
        s.add(cb(0, yf + 0.014, zz, lw, 0.006, lh, DARK))
    # Gesims und gestuftes Dach mit Girlande und vier Masken
    s.add(stack([(0.86, 0.86, 2.08), (0.90, 0.90, 2.12), (1.14, 1.14, 2.18), (1.14, 1.14, 2.25), (1.02, 1.02, 2.27),
                 (1.02, 1.02, 2.33), (0.66, 0.66, 2.50), (0.66, 0.66, 2.56), (0.52, 0.52, 2.60)], m))
    sq = 0.47
    s.add(tube([V((sq, sq, 2.36)), V((-sq, sq, 2.36)), V((-sq, -sq, 2.36)), V((sq, -sq, 2.36))], 0.055, 6, m,
               closed_path=True))
    for k in range(4):
        g = ico(1.0, m, 1).scale(0.105, 0.085, 0.125).move(0, 0.44, 2.455)                         # Maske
        g.add(ico(1.0, m, 1).scale(0.13, 0.05, 0.04).move(0, 0.44, 2.565))                         # Haarkranz
        for sx in (-1, 1):
            g.add(ico(1.0, m, 1).scale(0.085, 0.07, 0.07).move(sx * 0.27, 0.47, 2.40))             # Fruchtbüschel
        s.add(g.rot((0, 0, 1), 90 * k))
    top = HEIGHT["mon_neuber"]
    hi = max(v.z for v in s.v)
    s.warp(lambda c: (c.x, c.y, c.z * top / hi))
    # schmiedeeisernes Gitter
    r = 1.12
    oct_ = [V((math.cos(TAU * (i + 0.5) / 8) * r / math.cos(TAU / 16), math.sin(TAU * (i + 0.5) / 8) * r / math.cos(TAU / 16), 0))
            for i in range(8)]
    s.add(C.fence(oct_, 0.88, IRON, bars=4, closed=True, tip=0.07))
    return s, ("Denkmal für Friederike Caroline Neuber (»Neuberin«) in Dresden-Laubegast: schwarz verwitterter "
               "Sandsteinpfeiler auf roh behauenem Felssockel, Felder zwischen Ecklisenen mit Fruchtgehängen, vorn (+Y) "
               "Bronzemedaillon mit Brustbild unter einer Schleife und Inschrift, seitlich Trophäenreliefs; Gesims, "
               "gestuftes Dach mit Girlande und vier Masken. Achteckiges Eisengitter 2,2 m. Gesamthöhe ca. 2,6 m "
               "(geschätzt).")


@model
def mon_schiller_koerner():
    """Schiller-Körner-Denkmal (M. Pietzsch / O. Rost, 1912/13), Schillerstraße, Dresden-Loschwitz. Höhe gesch. 4,5 m."""
    zw = 3.70                    # Oberkante der Stützmauer
    m, w, W = GRANITE, SDARK, STONE
    s = Soup()
    # Stützmauer: links/rechts der Nische, unter der Sohlbank, Nischenrückwand
    for sx in (-1, 1):
        s.add(box(sx * 3.3 if sx < 0 else 1.74, -0.9, 0, -1.74 if sx < 0 else 3.3, 0, zw, w))
        s.add(box(sx * 3.3 if sx < 0 else 1.76, -0.95, zw, -1.76 if sx < 0 else 3.3, 0.05, zw + 0.12, w))
    s.add(box(-1.74, -0.9, 0, 1.74, 0, 1.93, w))
    s.add(box(-1.74, -0.9, 1.93, 1.74, -0.62, 4.0, m))
    for z in (0.62, 1.24, 1.86, 2.48, 3.10):                                                       # Lagerfugen
        for sx in (-1, 1):
            s.add(cb(sx * 2.52, 0.002, z, 1.56, 0.006, 0.014, DARK))
    for z in (0.62, 1.24):
        for sx in (-1, 1):
            s.add(cb(sx * 1.19, 0.002, z, 1.10, 0.006, 0.014, DARK))
    # Sohlbank, Pfeiler, Architrav, Segmentdach
    s.add(box(-1.76, -0.62, 1.93, 1.76, 0.24, 2.12, m))
    for sx in (-1, 1):
        s.add(cb(sx * 1.495, -0.20, 3.035, 0.47, 0.84, 1.83, m))                                   # Pfeiler
        s.add(cb(sx * 1.495, 0.225, 3.72, 0.30, 0.02, 0.10, m))                                    # Feston am Pfeilerkopf
        for dx in (-0.13, 0.13):
            s.add(cb(sx * 1.495 + dx, 0.225, 3.56, 0.035, 0.02, 0.36, m))
        s.add(cb(sx * 1.44, 0.03, 1.77, 0.40, 0.06, 0.27, m))                                      # Reliefsteine unter der Bank
        s.add(cb(sx * 1.44, 0.065, 1.77, 0.22, 0.02, 0.15, w))
    s.add(box(-1.27, -0.62, 3.70, 1.27, 0.12, 3.92, m))
    for i in range(11):                                                                            # Zahnschnitt
        s.add(cb(-1.10 + i * 0.22, 0.125, 3.76, 0.11, 0.02, 0.07, m))
    arc = [(1.78 - 3.56 * i / 12, 4.14 + (HEIGHT["mon_schiller_koerner"] - 4.14) * (1 - (1 - 2 * i / 12) ** 2)) for i in range(13)]
    s.add(prism_y([(-1.78, 3.92), (1.78, 3.92)] + arc, -0.75, 0.50, m))
    for i in range(8):                                                                             # Schriftzeichen im Giebel
        if i not in (3, 4):
            s.add(cb(-0.665 + i * 0.19, 0.503, 4.20, 0.09, 0.008, 0.045, DARK))
    # Mittelrisalit mit Brunnennische
    s.add(box(-0.52, -0.62, 2.12, 0.52, 0.02, 3.66, m))
    s.add(cb(0, 0.024, 2.98, 0.56, 0.02, 0.98, w))
    s.add(prism_y([(-0.20, 2.52), (0.20, 2.52), (0.20, 3.20), (0.12, 3.34), (0.0, 3.38), (-0.12, 3.34), (-0.20, 3.20)],
                  0.03, 0.07, m))
    s.add(cb(0, 0.08, 3.02, 0.07, 0.04, 0.10, w))                                                  # Wasserauslauf
    for sx in (-1, 1):
        s.add(cb(sx * 0.235, 0.045, 2.98, 0.05, 0.03, 0.82, m))
    # Relieffelder: links (+X) Schiller mit Körner und Kind, rechts (-X) sitzende Minna Körner mit Dora Stock u. a.
    zf = 2.27
    for sx in (-1, 1):
        s.add(box(min(sx * 0.52, sx * 1.27), -0.62, 2.12, max(sx * 0.52, sx * 1.27), -0.10, zf, m))
        s.add(box(min(sx * 0.52, sx * 1.27), -0.62, zf, max(sx * 0.52, sx * 1.27), -0.42, 3.70, W))
    yr = -0.30
    s.add(relief_fig("rest", 1.26, W, ratio=0.22, flat=0.5).move(1.08, yr, zf))
    s.add(relief_fig("rest", 1.32, W, ratio=0.22, flat=0.5, rz=-20).move(0.84, yr + 0.04, zf))
    s.add(relief_fig("f_rest", 0.72, W, ratio=0.15, flat=0.5, rz=25).move(0.64, yr + 0.06, zf))
    s.add(relief_fig("f_rest", 1.30, W, ratio=0.22, flat=0.5).move(-1.10, yr, zf))
    s.add(relief_fig("f_rest", 1.28, W, ratio=0.22, flat=0.5, rz=20).move(-0.90, yr + 0.02, zf))
    g = relief_fig("f_rest", 1.25, W, ratio=0.22, flat=0.5, rz=30)
    g.warp(lambda c: (c.x, c.y, c.z if c.z > 0.62 else c.z * 0.55 + 0.0))                          # Sitzende: Beine gestaucht
    lo = min(v.z for v in g.v)
    s.add(g.move(-0.72, yr + 0.06, zf - lo))
    s.add(loft([A.ring(z, -0.74, yr + 0.08, rx, ry, 0.08, n=10) for z, rx, ry in ((zf, 0.19, 0.12), (zf + 0.42, 0.18, 0.12),
                                                                                 (zf + 0.56, 0.14, 0.10))], W, orient=V((0, 0, 1))))
    # Brunnenpfeiler vor der Mauer mit Putten-Relief (Weinlese), Trog aus drei Stufen
    s.add(wstack([(1.18, 0.30, 0.78), (1.18, 0.30, 2.12), (1.10, 0.36, 2.14), (1.10, 0.36, 2.30), (1.0, 0.30, 2.34),
                  (1.0, 0.30, 2.44), (0.9, 0.24, 2.46)], m))
    s.add(cb(0, 0.305, 1.40, 0.56, 0.016, 0.78, w))
    for sx in (-1, 1):
        s.add(relief_fig("f_rest", 0.56, W, ratio=0.10, flat=0.45, rz=-sx * 60).move(sx * 0.15, 0.345, 1.06))
    s.add(ico(1.0, W, 1).scale(0.10, 0.04, 0.17).move(0, 0.33, 1.50))                              # Traube
    s.add(cb(0, 0.33, 1.14, 0.10, 0.05, 0.20, W))
    s.add(wstack([(1.26, 0.56, 0), (1.26, 0.56, 0.21), (1.22, 0.53, 0.23), (1.22, 0.53, 0.43), (1.18, 0.50, 0.45),
                  (1.18, 0.50, 0.60), (1.32, 0.60, 0.62), (1.32, 0.60, 0.80)], m))
    return s, ("Schiller-Körner-Denkmal (Martin Pietzsch / Oskar Rost, 1912/13) in der Stützmauer der Schillerstraße "
               "gegenüber dem Schillerhäuschen, Dresden-Loschwitz: Wandbrunnen als Nische mit zwei Pfeilern, Zahnschnitt "
               "und Segmentdach; Mittelrisalit mit Brunnennische, beidseits Figurenreliefs (links im Bild/+X Schiller und "
               "Körner mit Kind, rechts/-X sitzende und stehende Frauen der Familie Körner); davor Brunnenpfeiler mit "
               "Putten-Relief und gestuftem Trog. Grau verwitterte Architektur als Material Granit (reine Farbe), Reliefs "
               "als Sandstein. WANDDENKMAL: Mauerflucht Y = 0, eigenes Mauerstück 6,6 m breit, 3,7 m "
               "hoch, 0,9 m tief dahinter; Vorderseite +Y. Gesamthöhe ca. 4,5 m (geschätzt). Die Straße steigt im "
               "Original leicht an (Modell eben).")


@model
def mon_gardereiter():
    """Garde-Reiter-Denkmal (1920er), Hechtpark an der Stauffenbergallee: erhaltene Anlage OHNE die Reiterfigur."""
    m = STONE
    zt = 0.30                    # Terrassenhöhe
    s = box(-7.6, -0.6, 0, 7.6, 6.2, zt, m)
    s.add(box(-3.6, 6.2, 0, 3.6, 6.6, zt / 2, m))                                                  # Stufe
    s.add(box(-7.6, 5.7, zt, -4.2, 6.2, zt + 0.10, m)).add(box(4.2, 5.7, zt, 7.6, 6.2, zt + 0.10, m))  # Randschwellen
    for sx in (-1, 1):
        s.add(box(min(sx * 7.6, sx * 7.1), -0.6, zt, max(sx * 7.6, sx * 7.1), 6.2, zt + 0.10, m))
    zw = zt + 0.88
    s.add(box(-7.0, -0.25, zt, 7.0, 0.25, zw - 0.12, m))                                           # Brüstungsmauer
    s.add(box(-7.06, -0.31, zw - 0.12, 7.06, 0.31, zw, m))
    for x in (-5.6, -4.2, -2.8, 2.8, 4.2, 5.6):                                                    # Stoßfugen
        s.add(cb(x, 0.252, zt + 0.38, 0.014, 0.006, 0.76, SDARK))
    for sx in (-1, 1):
        s.add(box(min(sx * 6.5, sx * 7.15), -0.36, zt, max(sx * 6.5, sx * 7.15), 0.62, zw + 0.02, m))   # Endpfeiler
        s.add(box(min(sx * 2.7, sx * 5.4), 0.25, zt + 0.36, max(sx * 2.7, sx * 5.4), 0.82, zt + 0.47, m))  # Bank
        for x in (2.9, 4.05, 5.2):
            s.add(cb(sx * x, 0.50, zt + 0.18, 0.20, 0.44, 0.36, m))
    # Postament des verlorenen Reiters: Quaderfuß mit Lisenen, weit ausladende Kehle, Deckplatte mit Gedenktafeln
    cy = 0.30
    s.add(stack([(2.50, 1.60, zt), (2.50, 1.60, zt + 0.62)], m, cy=cy))
    for x in (-1.05, -0.35, 0.35, 1.05):
        s.add(stack([(0.36, 1.70, zt), (0.36, 1.70, zt + 0.10), (0.30, 1.66, zt + 0.13), (0.30, 1.66, zt + 0.62)], m,
                    cx=x, cy=cy))
    z0 = zt + 0.62
    kehle = [(3.50, 2.50, z0), (3.50, 2.50, z0 + 0.14), (3.30, 2.30, z0 + 0.20), (3.02, 2.02, z0 + 0.32),
             (2.84, 1.84, z0 + 0.46), (2.74, 1.74, z0 + 0.62), (2.70, 1.70, z0 + 0.64)]
    s.add(stack(kehle, m, cy=cy))
    top = HEIGHT["mon_gardereiter"]
    s.add(stack([(2.70, 1.70, z0 + 0.64), (2.70, 1.70, top)], m, cy=cy))
    s.add(cb(0, cy + 0.85 + 0.008, top - 0.10, 0.80, 0.016, 0.13, DARK))                           # Gedenktafeln (2001)
    return s, ("Garde-Reiter-Denkmal im Hechtpark gegenüber Stauffenbergallee 12 (Albertstadt), heutiger Zustand: "
               "Sandsteinanlage OHNE die verlorene Reiterfigur – erhöhte Terrasse 15,2 × 6,8 m mit Stufe vorn (+Y), an der "
               "Rückseite 14 m lange Brüstungsmauer mit Endpfeilern und zwei Steinbänken, in der Mitte das leere Postament "
               "(Quaderfuß, weit ausladende Kehle, Deckplatte mit kleinen Gedenktafeln). Mauer liegt bei Y = 0, Terrasse "
               "davor. Gesamthöhe ca. 1,75 m (geschätzt), alle Maße aus Fotos geschätzt.")


HEIGHT.update({"mon_moritzmonument": 8.4, "mon_boettger_stele": 2.1, "mon_neuber": 2.6, "mon_schiller_koerner": 4.5,
               "mon_gardereiter": 1.75})
VIEWS.update({n: ((12, 6), (62, 12)) for n in HEIGHT})
VIEWS["mon_moritzmonument"] = ((14, 4), (-40, 8))
VIEWS["mon_schiller_koerner"] = ((14, 5), (-40, 10))
VIEWS["mon_gardereiter"] = ((10, 12), (55, 18))
FOCUS = {"mon_moritzmonument": 5.0, "mon_boettger_stele": 1.2, "mon_neuber": 0.9, "mon_schiller_koerner": 1.9,
         "mon_gardereiter": 0.0}


_SETUP = L._setup_preview_scene


def _setup_front():
    """Vorschau der Wanddenkmäler: Sonne von vorn links statt von hinten (nur in diesem Skript)."""
    cam = _SETUP()
    sun = bpy.data.objects.get("Sun")
    if sun:
        sun.rotation_euler = (math.radians(52), 0, math.radians(150))
    return cam


SUNFRONT = {"mon_moritzmonument", "mon_schiller_koerner", "mon_boettger_stele", "mon_neuber", "mon_gardereiter"}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    dev = "--dev" in argv
    L.NOPREVIEW = "--nopreview" in argv
    names = [a for a in argv if not a.startswith("--")] or list(MODELS)
    A.FIG.update(A.figures(POSES))
    for name in names:
        L._setup_preview_scene = _setup_front if name in SUNFRONT else _SETUP
        L.reset()
        mats()
        soup, notes = MODELS[name]()
        ob = build(soup, name, smooth_angle=42, merge=True)
        if dev:
            if "--whole" in argv:
                A.dev_render(ob, name, -1.0, tag="all")
            else:
                A.dev_render(ob, name, FOCUS[name])
            print(f"[dev] {name}: {L.tri_count([ob])} Dreiecke, Höhe {max(v.co.z for v in ob.data.vertices):.3f}")
            continue
        e = finish(name, [ob], notes, views=VIEWS.get(name))
        print(f"[named] {name}: Höhe {e['height']} (Soll {HEIGHT[name]}), {e['tris']} Dreiecke")
    try:
        os.rmdir(L.TMP)
    except OSError:
        pass


if __name__ == "__main__":
    main()
