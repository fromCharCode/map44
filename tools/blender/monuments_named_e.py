"""Dritte Runde benannter Dresdner Standbilder nach Fotovorlagen: godot/assets/models/monuments/mon_<name>.glb.

Aufruf (Projektordner, immer nur ein Blender gleichzeitig):
  flatpak run --filesystem=host org.blender.Blender -b --python "$PWD/tools/blender/monuments_named_e.py" [-- name ...] [--nopreview]

Aufbau, Bausteine und Konventionen wie monuments_named_a.py / monuments_named_c.py (Blender Z-up, Meter, Ursprung =
Bodenmitte des Denkmals, Vorderseite +Y; rechts der Figur = +X; echte Gesamthöhe eingebaut, Maßstab im Spiel 1,0).
Vorlagen: Wikimedia-Commons-Fotos in data/research/denkmal_fotos/ (nur Vorlage, siehe QUELLEN_standbilder3.txt).
Materialien: Sandstein, Sandstein_dunkel, Bronze, Granit, GranitRot, GranitDunkel, Eisen (wie bisher), keine neuen.
"""
import math
import os
import sys

import bpy  # noqa: F401
from mathutils import Vector, noise

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import monuments_named_a as A  # noqa: E402
from monuments_named_a import (L, V, Soup, mat, loft, lathe, cbox, tube, rrect, build, finish, ico, TAU,  # noqa: E402
                               stack, plaque, cloak, STONE, BRONZE, GOLD, GRANITE, RED, DARK, box,
                               fig, clip, decimate, ring, robe, sleeve, hand, cb, rod, wreath, cstack, place,
                               PED_M, PED_F)

SDARK, IRON = "Sandstein_dunkel", "Eisen"
PED_K = os.path.join(os.path.dirname(PED_M), "ped_k.glb")


def mats():
    A.mats()
    mat(SDARK, "#4F473D", 0.9)          # schwarz verwitterter Elbsandstein (wie monuments_named_b/c)
    mat(IRON, "#26292B", 0.6, 0.6)      # Gusseisen (wie monuments_named_b/c)


def prism_x(yz, x0, x1, m):
    """Prisma entlang X über dem Umriss yz = [(y, z), ...]."""
    return loft([[V((x, y, z)) for y, z in yz] for x in (x0, x1)], m)


def disc_y(r, t, m, n=16):
    """Flache Scheibe in der XZ-Ebene (Achse = Y), Vorderfläche bei y = t, Mitte im Ursprung."""
    return lathe([(r, 0.0), (r, t)], n, m).rot((1, 0, 0), -90)


def joints_z(w, d, zs, m=SDARK, t=0.006, cx=0.0, cy=0.0):
    """Lagerfugen eines Quaderbaus als dünne dunkle Bänder."""
    s = Soup()
    for z in zs:
        s.add(stack([(w + 0.006, d + 0.006, z - t), (w + 0.006, d + 0.006, z + t)], m, cx=cx, cy=cy))
    return s


def level(f, j, side_a="L", side_b="R"):
    """Schert die Figur in z, bis die tiefsten Punkte beider Füße auf gleicher Höhe liegen; liefert neue Gelenke."""
    def low(side):
        c = j["Foot_" + side][0]
        vs = [v for v in f.v if (v.x - c.x) ** 2 + (v.y - c.y) ** 2 < 0.25 ** 2 and v.z < c.z + 0.05]
        v = min(vs, key=lambda q: q.z)
        return V((c.x, c.y, v.z))
    a, b = low(side_a), low(side_b)
    d = V((b.x - a.x, b.y - a.y, 0.0))
    k = (b.z - a.z) / d.length_squared

    def sh(c):
        return V((c.x, c.y, c.z - k * ((c.x - a.x) * d.x + (c.y - a.y) * d.y)))
    f.warp(sh)
    return {n: (sh(h), sh(t)) for n, (h, t) in j.items()}


def athlete(f, j, m=BRONZE, k=1.0):
    """Gibt dem kantigen Fußgänger die Massen eines Athleten: Rumpf, Brustkorb, Gesäß, Schenkel, Waden, Arme."""
    hip = j["UpperLeg_L"][0].lerp(j["UpperLeg_R"][0], 0.5)
    sh = j["UpperArm_L"][0].lerp(j["UpperArm_R"][0], 0.5)
    nk = j["Neck"][0]
    ax = (j["UpperArm_R"][0] - j["UpperArm_L"][0]).normalized()       # Schulterachse
    hx = (j["UpperLeg_R"][0] - j["UpperLeg_L"][0]).normalized()       # Beckenachse
    up = (sh - hip).normalized()
    rings = []
    for t, wx, wy, tw, fy in ((-0.20, 0.135, 0.105, 0.0, -0.01), (-0.04, 0.172, 0.118, 0.0, -0.012), (0.22, 0.150, 0.100, 0.3, 0.0),
                              (0.48, 0.158, 0.105, 0.6, 0.008), (0.74, 0.196, 0.122, 0.9, 0.018), (0.93, 0.208, 0.112, 1.0, 0.008),
                              (1.04, 0.150, 0.085, 1.0, 0.0), (1.10, 0.060, 0.058, 1.0, 0.0)):
        c = hip.lerp(sh, t) if t <= 1.0 else sh.lerp(nk + (nk - sh).normalized() * 0.02, (t - 1.0) / 0.10)
        a = hx.lerp(ax, tw).normalized()
        a = (a - up * a.dot(up)).normalized()
        b = up.cross(a).normalized()
        c = c + b * fy
        rings.append([c + a * (math.cos(TAU * i / 12) * wx * k) + b * (math.sin(TAU * i / 12) * wy * k) for i in range(12)])
    f.add(loft(rings, m, orient=up))
    for side in "LR":
        h, kn, an = j["UpperLeg_" + side][0], j["LowerLeg_" + side][0], j["Foot_" + side][0]
        f.add(tube([h + (h - kn).normalized() * 0.05, h.lerp(kn, 0.30), h.lerp(kn, 0.75), kn, kn.lerp(an, 0.28), kn.lerp(an, 0.72),
                    an], 0.1, 8, m, rs=[x * k for x in (0.092, 0.098, 0.074, 0.060, 0.066, 0.046, 0.040)]))
        a, e, w = j["UpperArm_" + side][0], j["LowerArm_" + side][0], j["Hand_" + side][0]
        f.add(ico(0.068 * k, m, 1).move(*a))                              # Schulter
        f.add(tube([a, a.lerp(e, 0.40), e, e.lerp(w, 0.28), w], 0.05, 7, m,
                   rs=[x * k for x in (0.058, 0.060, 0.044, 0.048, 0.032)]))
    return f


def headc(j):
    return j["Head"][0].lerp(j["Head"][1], 0.95)


POSES = {
    "rest": (PED_M, []),
    "k_rest": (PED_K, []),
    # Bogenschütze (im Fußgängerrahmen: Brust +Y, Schuss nach -X): weiter Ausfallschritt, Standbein links nahezu
    # senkrecht, rechtes Bein weit nach hinten gestreckt (Ferse gehoben), Oberkörper zurückgelehnt, linker Arm
    # gestreckt am Bogen, rechter Ellbogen hoch zurückgezogen, Hand an der Wange, Kopf zum Ziel gedreht
    "bogen": (PED_M, [
        ("UpperLeg_L", (-0.12, 0.03, -1.0)), ("LowerLeg_L", (-0.07, -0.02, -1.0)), ("Foot_L", (-0.85, 0.5, -0.12)),
        ("UpperLeg_R", (0.68, -0.04, -1.0)), ("LowerLeg_R", (0.74, -0.10, -1.0)), ("Foot_R", (0.25, 0.75, -0.65)),
        ("Spine1", (0.16, 0.0, 1.0)), ("Chest", (0.27, -0.04, 1.0)), ("Neck", (0.14, 0.0, 1.0), 28),
        ("Head", (0.0, 0.0, 1.0), 48),
        ("UpperArm_L", (-1.0, 0.10, 0.12)), ("LowerArm_L", (-1.0, 0.04, 0.10)),
        ("UpperArm_R", (0.85, -0.28, 0.50)), ("LowerArm_R", (-0.95, 0.30, 0.08))]),
    # Ballwerfer: Standbein rechts, linkes Bein weit zur Seite gestellt, rechter Arm mit dem Ball gesenkt nach
    # hinten ausholend, linker Arm in Schulterhöhe angewinkelt vor der Brust (Hand hängt), Kopf nach links
    "ball": (PED_M, [
        ("UpperLeg_R", (0.07, 0.0, -1.0)), ("LowerLeg_R", (0.05, -0.02, -1.0)), ("Foot_R", (0.25, 1.0, -0.2)),
        ("UpperLeg_L", (-0.40, 0.10, -1.0)), ("LowerLeg_L", (-0.42, 0.02, -1.0)), ("Foot_L", (-0.75, 0.65, -0.15)),
        ("Chest", (0.03, 0.0, 1.0), -12), ("Neck", (0.0, 0.0, 1.0), 22), ("Head", (-0.03, 0.0, 1.0), 34),
        ("UpperArm_R", (0.38, -0.30, -1.0)), ("LowerArm_R", (0.50, 0.30, -0.80)),
        ("UpperArm_L", (-0.72, 0.68, -0.04)), ("LowerArm_L", (0.95, 0.12, -0.15)), ("Hand_L", (0.25, 0.25, -0.9))]),
    # Putto des Lipsius-Denkmals: sitzend, Knie hochgezogen und gespreizt, Tafel zwischen den Knien, rechte Hand
    # schreibt, linker Ellbogen auf dem Knie, Kopf in die linke Hand gestützt
    "putto": (PED_K, [
        ("UpperLeg_L", (-0.50, 0.80, 0.30)), ("LowerLeg_L", (0.18, 0.22, -1.0)), ("Foot_L", (-0.2, 1.0, -0.25)),
        ("UpperLeg_R", (0.50, 0.80, 0.22)), ("LowerLeg_R", (-0.18, 0.30, -1.0)), ("Foot_R", (0.2, 1.0, -0.25)),
        ("Spine2", (0.0, 0.18, 1.0)), ("Chest", (-0.04, 0.34, 1.0)), ("Neck", (-0.08, 0.40, 1.0)),
        ("Head", (-0.22, 0.42, 1.0), -8),
        ("UpperArm_L", (-0.30, 0.62, -0.70)), ("LowerArm_L", (0.28, -0.05, 1.0)),
        ("UpperArm_R", (0.22, 0.50, -0.85)), ("LowerArm_R", (-0.62, 0.72, -0.25))]),
}


# ====================================================================== Modelle
MODELS = {}
HEIGHT = {}
VIEWS = {}


def model(fn):
    MODELS[fn.__name__] = fn
    return fn


@model
def mon_bogenschuetze():
    """»Bogenschütze« (E. M. Geyger, Guss 1902), Königsufer. Figur mit Bogen knapp 4 m (Wikipedia, Original)."""
    zw, zp = 3.8, 5.8            # Oberkante Ufermauer / Oberkante Pfeiler (aus den Fotos geschätzt)
    s = stack([(1.70, 2.20, 0), (1.70, 2.20, zp - 0.32), (1.62, 2.12, zp - 0.32), (1.62, 2.12, zp)], STONE)
    s.add(joints_z(1.70, 2.20, (0.95, 1.9, 2.85, zw, 4.75)))
    # Mauerzunge nach hinten (-Y) mit konkav abschwingender Oberkante
    arc = [(-3.1 + 2.0 * math.cos(math.radians(a)), 5.0 - 1.1 * math.sin(math.radians(a))) for a in range(0, 91, 15)]
    s.add(prism_x([(-1.1, 0.0)] + arc + [(-3.1, 0.0)], -0.78, 0.78, STONE))
    for z in (0.95, 1.9, 2.85):
        s.add(cb(0, -2.1, z, 1.566, 2.006, 0.012, SDARK))
    # Bronzeplinthe (unregelmäßige Scholle) und Figur
    pl = stack([(0.86, 1.86, 0.0), (0.84, 1.84, 0.06), (0.74, 1.74, 0.11)], BRONZE, r=0.18)
    pl.warp(lambda c: (c.x * (1 + 0.06 * noise.noise(Vector((c.x * 2, c.y * 2, 1.3)))),
                       c.y * (1 + 0.04 * noise.noise(Vector((c.y * 2, c.x * 2, 4.1)))), c.z))
    s.add(pl.move(0, -0.12, zp))
    f, j = fig("bogen")
    j = level(f, j)
    athlete(f, j, k=1.2)
    c = headc(j)
    f.add(lathe([(0.150, 0.0), (0.158, 0.012), (0.118, 0.035), (0.108, 0.085), (0.075, 0.125), (0.0, 0.14)], 12, BRONZE,
                cx=c.x, cy=c.y - 0.005).move(0, 0, c.z + 0.015))                             # flacher Helm mit Krempe
    hl, dl = hand(j, "L")
    hr, dr = hand(j, "R")
    g = Soup()
    # Bogen in der XZ-Ebene durch die Bogenhand, Enden zum Schützen zurückgezogen, Spitzen leicht nach vorn gerollt
    pts, rs = [], []
    N = 16
    for i in range(N + 1):
        t = -1.0 + 2.0 * i / N
        x = 0.32 * t * t - 0.07 * max(0.0, abs(t) - 0.82) / 0.18
        pts.append(V((hl.x - 0.02 + x, hl.y, hl.z + 0.80 * t)))
        rs.append(0.020 - 0.010 * abs(t))
    g.add(tube(pts, 0.02, 6, BRONZE, rs=rs))
    nock = V((hr.x - 0.04, hl.y, hl.z + (hr.z - hl.z) * 0.3))
    sq = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
    g.add(tube([pts[0], nock, pts[-1]], 0.005, 4, BRONZE, prof=sq))                           # Sehne
    tip = V((hl.x - 0.24, hl.y, nock.z + (hl.z - nock.z) * 1.1))
    g.add(rod(nock + V((0.03, 0, 0)), tip, 0.009, n=5))                                       # Pfeil
    d = (tip - nock).normalized()
    g.add(rod(tip - d * 0.01, tip + d * 0.11, 0.028, n=4, r1=0.001))                          # Pfeilspitze
    g.rot((0, 1, 0), 6, tuple(hl))                                                            # Schuss leicht aufwärts
    f.add(g)
    place(f, zp + 0.10, HEIGHT["mon_bogenschuetze"] - zp - 0.10, rz=-90)
    ys = [v.y for v in f.v if v.z < zp + 0.5]
    f.move(0, -(min(ys) + max(ys)) / 2 - 0.12, 0)
    s.add(f)
    return s, ("»Bogenschütze« von Ernst Moritz Geyger (Königsufer, Neustädter Elbufer): Bronzeakt mit Helm im weiten "
               "Ausfallschritt, Bogen voll gespannt; SCHUSSRICHTUNG = +Y (über die Elbe), Brust nach +X. Hoher "
               "Sandsteinpfeiler 1,7 × 2,2 m als Kopf der Ufermauer mit konkav abschwingender Mauerzunge nach -Y. "
               "Ursprung auf Höhe des Elbuferwegs; Oberkante der Ufermauer/Terrasse bei 3,8 m, Pfeilerkopf 5,8 m. "
               "Figur mit Bogen ca. 3,9 m (Original laut Wikipedia »fast vier Meter«), Pfeilermaße geschätzt.")


@model
def mon_ballwerfer():
    """»Ballwerfer« (R. D. Fabricius 1907), seit 1983 vor dem Deutschen Hygiene-Museum. Gesamthöhe geschätzt 6,4 m."""
    s = stack([(2.9, 2.9, 0), (2.9, 2.9, 0.08)], GRANITE)
    s.add(stack([(2.30, 2.30, 0.08), (2.30, 2.30, 1.68)], GRANITE))
    s.add(stack([(2.12, 2.12, 1.68), (2.12, 2.12, 2.06)], GRANITE))
    for sgn in (-1, 1):                                                                    # Stoßfugen der Quader
        s.add(cb(0.18, sgn * 1.152, 0.88, 0.012, 0.006, 1.60, DARK))
        s.add(cb(sgn * 1.152, -0.18, 0.88, 0.006, 0.012, 1.60, DARK))
    zb = 2.06
    s.add(stack([(1.98, 1.98, zb), (1.98, 1.98, zb + 0.10), (1.80, 1.80, zb + 0.16)], BRONZE))
    f, j = fig("ball")
    j = level(f, j)
    athlete(f, j, k=1.22)
    hr, dr = hand(j, "R")
    f.add(ico(0.105, BRONZE, 2).move(hr.x + 0.01, hr.y + 0.03, hr.z + 0.085))                  # Ball in der Rechten
    place(f, zb + 0.16, HEIGHT["mon_ballwerfer"] - zb - 0.16)
    xs = [v.x for v in f.v if v.z < zb + 0.6]
    f.move(-(min(xs) + max(xs)) / 2, 0.05, 0)
    s.add(f)
    return s, ("»Ballwerfer« von Richard Daniel Fabricius (vor dem Deutschen Hygiene-Museum): kolossaler Bronzeakt, "
               "rechter Arm mit dem Ball gesenkt ausholend, linker Arm angewinkelt vor der Brust, Kopf nach links, "
               "linkes Bein weit ausgestellt (Brust nach +Y). Zweistufiger grauer Granitsockel 2,3 m im Quadrat mit "
               "Bronzeplinthe. Gesamthöhe ca. 6,4 m (geschätzt, Figur ca. 4,2 m).")


@model
def mon_palitzsch():
    """Palitzsch-Denkmal (1877), Dresden-Prohlis. Gesamthöhe geschätzt 3,0 m."""
    k = 0.80                     # Tiefe / Breite
    s = stack([(1.9, 1.9 * k, 0), (1.9, 1.9 * k, 0.03)], GRANITE)
    lv = [(1.22, 0.03), (1.22, 0.36), (1.16, 0.40), (1.06, 0.44), (1.00, 0.46), (1.00, 1.64), (1.04, 1.67), (1.04, 1.70),
          (1.00, 1.70), (1.00, 1.84), (1.06, 1.87), (1.20, 1.93), (1.24, 1.95), (1.24, 2.02), (1.02, 2.06), (0.99, 2.06),
          (0.99, 2.20), (1.03, 2.23), (1.03, 2.28), (0.97, 2.30), (0.75, 2.30), (0.75, 2.38)]
    s.add(stack([(w, w * k + (0.0 if w > 0.8 else 0.0), z) for w, z in lv], STONE))
    yf = 1.00 * k / 2
    # Bronzemedaillon mit Profilbildnis (nach rechts), Rahmenwulst
    zc = 1.22
    s.add(disc_y(0.255, 0.020, BRONZE, 20).move(0, yf, zc))
    s.add(wreath(0.245, 0.022, BRONZE, n=20).move(0, yf + 0.02, zc))
    prof = [(-0.13, -0.19), (0.06, -0.19), (0.05, -0.10), (0.10, -0.06), (0.13, 0.0), (0.155, 0.03), (0.13, 0.06),
            (0.135, 0.12), (0.09, 0.18), (0.0, 0.20), (-0.09, 0.17), (-0.14, 0.09), (-0.15, -0.02), (-0.17, -0.12)]
    s.add(loft([[V((x * q, y, zc + z * q)) for x, z in prof] for y, q in ((yf + 0.015, 1.0), (yf + 0.035, 0.96),
                                                                        (yf + 0.05, 0.8))], BRONZE))
    # Inschriften (eingehauen, dunkel gefasst) und Lorbeerzweig
    s.add(cb(0, yf + 0.003, 1.77, 0.74, 0.006, 0.065, DARK))                               # JOHANN GEORG PALITZSCH.
    for zz, lw in ((0.86, 0.66), (0.77, 0.76)):
        s.add(cb(0, yf + 0.003, zz, lw, 0.006, 0.05, DARK))                                 # GEB. … / GEST. …
    for sx in (-1, 1):
        s.add(cb(sx * 0.19, yf + 0.008, 0.575, 0.36, 0.016, 0.06, STONE).rot((0, 1, 0), -sx * 8, (0, yf, 0.56)))
    s.add(cb(0, yf + 0.012, 0.56, 0.07, 0.024, 0.07, STONE))
    # Bekrönung: Himmelsglobus im Gestell mit Horizontring, zwei Kränze, Fernrohr
    z0 = 2.38
    s.add(lathe([(0.20, z0), (0.20, z0 + 0.03), (0.10, z0 + 0.06), (0.07, z0 + 0.12), (0.19, z0 + 0.22), (0.27, z0 + 0.34)],
                12, STONE))
    gz = z0 + 0.36
    g = ico(0.255, STONE, 2)
    s.add(g.move(0, 0, gz))
    s.add(lathe([(0.255, gz - 0.02), (0.30, gz - 0.02), (0.30, gz + 0.02), (0.255, gz + 0.02)], 16, STONE))   # Horizontring
    s.add(wreath(0.27, 0.022, STONE, n=16).scale(0.92, 1, 1).rot((0, 0, 1), 90).move(0, 0, gz))   # Meridianring
    for sx in (-1, 1):
        s.add(wreath(0.145, 0.045, STONE, n=12).rot((1, 0, 0), -14).rot((0, 0, 1), -sx * 24)
              .move(sx * 0.21, 0.5 * 0.75 * k - 0.04, z0 + 0.16))
    s.add(rod(V((0.03, 0.26, z0 + 0.02)), V((0.16, 0.20, gz + 0.22)), 0.028, STONE, n=6, r1=0.036))   # Fernrohr
    top = HEIGHT["mon_palitzsch"]
    s.warp(lambda c: (c.x, c.y, c.z if c.z < z0 else z0 + (c.z - z0) * (top - z0) / (gz + 0.27 - z0)))
    return s, ("Palitzsch-Denkmal (Dresden-Prohlis, am Palitzschhof): Sandsteinpfeiler auf Sockel mit Gesims und Attika, "
               "vorn (+Y) Bronzemedaillon mit Profilbildnis, Namensfries und Lebensdaten, Lorbeerzweig; Bekrönung aus "
               "Himmelsglobus mit Horizontring, zwei Kränzen und Fernrohr. Gesamthöhe ca. 3,0 m (geschätzt).")


@model
def mon_friedrich_list():
    """Friedrich-List-Denkmal (1964), Friedrich-List-Platz. Sandsteinblock, Höhe geschätzt 3,1 m."""
    w, ln, h = 1.35, 4.5, HEIGHT["mon_friedrich_list"]
    m = SDARK
    s = stack([(w + 0.5, ln + 0.5, 0), (w + 0.5, ln + 0.5, 0.02)], GRANITE)
    s.add(stack([(w, ln, 0.02), (w, ln, h)], m))
    z1, z2 = 1.00, 2.36          # Lagerfugen der drei Quaderschichten
    s.add(joints_z(w, ln, (z1, z2), STONE, t=0.004))
    yf, xf = ln / 2, w / 2
    R = DARK                     # Reliefs und Schrift heben sich dunkel ab
    # Stirnseite (+Y): Name und Lebensdaten, darunter vertieftes Schriftfeld
    for zz, lw, lh in ((2.84, 0.80, 0.13), (2.62, 0.52, 0.19), (2.45, 0.66, 0.09)):
        s.add(cb(0, yf + 0.006, zz, lw, 0.012, lh, R))
    for i in range(14):
        s.add(cb(0, yf + 0.008, z2 - 0.10 - i * 0.089, 0.74 - 0.05 * ((i * 7) % 3), 0.008, 0.05, R))
    # Längsseite +X: Lokomotive mit Tender (oben links), Raddampfer (Mitte rechts), Menschenmenge (darunter)

    def side(sx):
        g = Soup()
        t = 0.03

        def bx(y, z, wy, hz, tt=t):                # Reliefquader: Mitte (y, z) auf der Seitenfläche
            g.add(cb(xf + tt / 2, y, z, tt, wy, hz, R))

        def wheel(y, z, r):
            g.add(lathe([(r, 0.0), (r, t + 0.01)], 10, R).rot((0, 1, 0), 90).move(xf, y, z))
        y0 = 1.25                                   # Lokomotive: fährt nach +Y
        bx(y0 + 0.08, 2.74, 0.62, 0.20)             # Kessel
        bx(y0 + 0.32, 2.94, 0.07, 0.26)             # Schornstein
        bx(y0 - 0.18, 2.86, 0.16, 0.14)             # Führerstand
        bx(y0 - 0.62, 2.72, 0.46, 0.22)             # Tender
        bx(y0 - 0.20, 2.535, 1.60, 0.025)           # Gleis
        for dy, r in ((0.22, 0.10), (-0.02, 0.10), (-0.26, 0.07), (-0.50, 0.07), (-0.76, 0.07)):
            wheel(y0 + dy, 2.55 + r, r)
        y1 = -0.85                                  # Raddampfer
        hull = [(-1.05, 2.18), (-0.95, 2.04), (0.85, 2.04), (1.10, 2.20), (1.02, 2.24), (-0.98, 2.24)]
        g.add(loft([[V((x, y1 + yy, zz)) for yy, zz in hull] for x in (xf, xf + t)], R))
        wheel(y1, 2.20, 0.22)                       # Radkasten
        bx(y1 - 0.05, 2.30, 1.50, 0.07)             # Deck mit Fahrgästen
        bx(y1 - 0.30, 2.66, 0.045, 0.68)            # Schornstein / Mast
        bx(y1, 1.96, 2.2, 0.03)                     # Wasserlinie
        for i in range(11):                         # Menschenmenge am Ufer
            yy = y1 - 0.92 + i * 0.185
            hh = 0.50 + 0.08 * ((i * 5) % 3)
            bx(yy, 1.12 + hh / 2, 0.12, hh, 0.035)
            g.add(lathe([(0.055, 0.0), (0.055, 0.04)], 8, R).rot((0, 1, 0), 90).move(xf, yy, 1.12 + hh + 0.06))
        bx(y1 + 0.12, 1.10, 2.25, 0.03)
        if sx < 0:
            g.scale(-1, 1, 1)
        return g
    s.add(side(1))
    s.add(side(-1).scale(1, -1, 1))
    return s, ("Friedrich-List-Denkmal (Friedrich-List-Platz, Südvorstadt): frei stehender Block aus dunkel verwittertem "
               "Sandstein, 1,35 × 4,5 m, drei Quaderschichten. Stirnseite (+Y) mit Namen, Lebensdaten und Schriftfeld; "
               "Längsseiten mit Flachreliefs zur Verkehrsgeschichte (Lokomotive, Raddampfer, Menschenmenge – die "
               "Seite -X ist mangels Foto gespiegelt angenommen). Höhe ca. 3,1 m (geschätzt).")


@model
def mon_lipsius():
    """Lipsius-Denkmal (Stele für Constantin Lipsius), Stübelallee / Ecke Lipsiusstraße. Gesamthöhe geschätzt 5,0 m."""
    m = SDARK
    a8 = math.pi / 8
    s = stack([(1.40, 1.40, 0), (1.40, 1.40, 0.12), (1.16, 1.16, 0.12), (1.16, 1.16, 0.40)], m)
    s.add(stack([(1.02, 1.02, 0.40), (1.02, 1.02, 1.26), (0.98, 0.98, 1.30)], m))            # Sockelblock
    for sx in (-1, 1):                                                                         # seitliche Vorlagen
        s.add(stack([(0.12, 0.70, 0.40), (0.12, 0.70, 0.95), (0.04, 0.70, 1.05)], m, cx=sx * 0.55))
    # achtkantiger, leicht verjüngter Schaft mit gekehlten Seiten
    s.add(lathe([(0.56, 1.30), (0.54, 1.36), (0.50, 3.12), (0.52, 3.15), (0.52, 3.20)], 8, m, a0=a8))
    for k in range(8):                                                                         # Kehlen als dunklere Bänder
        a = TAU * k / 8
        g = cb(0, 0.497, 2.24, 0.16, 0.012, 1.70, m).rot((1, 0, 0), 0.65, (0, 0.5, 2.24))
        s.add(g.rot((0, 0, 1), math.degrees(a)))
    # Inschrifttafel an der Vorderseite mit Kapitell-Aufsatz
    s.add(cb(0, 0.535, 1.82, 0.50, 0.09, 1.00, m))
    s.add(stack([(0.50, 0.09, 2.32), (0.62, 0.15, 2.40), (0.62, 0.15, 2.56), (0.70, 0.19, 2.62), (0.70, 0.19, 2.70),
                 (0.56, 0.12, 2.74)], m, cy=0.535))
    for i in range(5):
        s.add(cb(0, 0.583, 2.18 - i * 0.12, 0.38 - 0.06 * (i % 2), 0.006, 0.05, m))
    # Schriftband, gerippte Trommel, Mäanderband, Kuppe
    s.add(lathe([(0.53, 3.20), (0.53, 3.36), (0.50, 3.38)], 16, m))
    s.add(lathe([(0.47, 3.205), (0.535, 3.215), (0.535, 3.345), (0.47, 3.355)], 16, m, cap0=False, cap1=False))   # DEM MEISTER …
    s.add(lathe([(0.50, 3.38), (0.555, 3.42), (0.565, 3.66), (0.54, 3.72), (0.50, 3.73)], 16, m))
    for k in range(16):
        s.add(cb(0, 0.562, 3.55, 0.035, 0.02, 0.26, m).rot((0, 0, 1), 360 * k / 16))
    s.add(lathe([(0.50, 3.73), (0.515, 3.75), (0.515, 3.86), (0.50, 3.88)], 16, m))
    s.add(lathe([(0.518, 3.775), (0.518, 3.835)], 16, m, cap0=False, cap1=False))           # Mäander
    s.add(lathe([(0.50, 3.88), (0.47, 3.98), (0.40, 4.06), (0.30, 4.10), (0.0, 4.11)], 16, m))
    # heller Sandsteinaufsatz: Polster mit Lorbeerblättern, darauf der schreibende Putto
    z0 = 4.08
    s.add(lathe([(0.33, z0), (0.37, z0 + 0.05), (0.33, z0 + 0.13), (0.20, z0 + 0.17), (0.0, z0 + 0.18)], 14, STONE))
    for k in range(12):
        s.add(ico(1.0, STONE, 1).scale(0.085, 0.035, 0.022).move(0.30, 0, 0).rot((0, 0, 1), 360 * k / 12 + 12)
              .move(0, 0, z0 + 0.13))
    f, j = fig("putto", STONE)
    H = max(v.z for v in A.FIG["k_rest"][0].v)
    athlete(f, j, STONE, k=H / 1.78 * 1.42)
    c = headc(j)
    f.add(ico(1.0, STONE, 1).scale(0.105 * H, 0.108 * H, 0.090 * H).move(c.x, c.y - 0.012 * H, c.z + 0.02 * H))   # Locken
    hl, _ = hand(j, "L")
    hr, _ = hand(j, "R")
    kl, kr = j["LowerLeg_L"][0], j["LowerLeg_R"][0]
    kc = kl.lerp(kr, 0.5)
    lo = min(v.z for v in f.v)
    f.add(cb(0, 0, 0, 0.30 * H, 0.035 * H, 0.26 * H, STONE).rot((1, 0, 0), -38)
          .move(kc.x, kc.y + 0.02 * H, lo + 0.14 * H))                                         # Schreibtafel / Mappe
    f.add(rod(hr + V((0, 0, 0.05 * H)), hr + V((-0.01, 0.02, -0.06)) , 0.012 * H, STONE, n=4))  # Griffel
    f.setmat(STONE)
    place(f, z0 + 0.15, HEIGHT["mon_lipsius"] - z0 - 0.15)
    ys = [v.y for v in f.v]
    f.move(0, -(min(ys) + max(ys)) / 2 + 0.02, 0)
    s.add(f)
    return s, ("Lipsius-Denkmal (Stele für den Architekten Constantin Lipsius, Stübelallee/Lipsiusstraße): achtkantiger "
               "Pfeiler aus schwarz verwittertem Sandstein auf Sockelblock, vorn (+Y) Inschrifttafel mit Kapitell, oben "
               "Schriftband, gerippte Trommel, Mäanderband und Kuppe; darauf aus hellem Sandstein ein sitzender, "
               "schreibender Putto, den Kopf in die linke Hand gestützt (Blick +Y). Gesamthöhe ca. 5,0 m (geschätzt).")


@model
def mon_koenig_albert_obelisk():
    """König-Albert-Denkmal (Obelisk) im Albertpark, Dresdner Heide. Gesamthöhe geschätzt 9,0 m."""
    m = DARK
    q = HEIGHT["mon_koenig_albert_obelisk"] / 9.4
    lv = [(3.4, 0.0), (3.4, 0.38), (2.05, 0.38), (2.05, 1.48), (1.40, 1.48), (1.40, 2.78), (1.90, 2.78), (1.90, 3.38),
          (1.00, 3.38), (1.00, 3.88), (0.70, 3.88), (0.52, 9.15), (0.0, 9.40)]
    s = stack([(w, w, z * q) for w, z in lv[:2]], GRANITE)
    s.add(stack([(w, w, z * q) for w, z in lv[2:]], m))
    zc = 2.10 * q
    s.add(disc_y(0.40, 0.03, BRONZE, 20).move(0, 0.70, zc))                                # Bildnismedaillon
    s.add(wreath(0.385, 0.03, BRONZE, n=20).move(0, 0.73, zc))
    prof = [(-0.20, -0.30), (0.14, -0.30), (0.10, -0.16), (0.16, -0.10), (0.20, 0.0), (0.24, 0.04), (0.20, 0.09),
            (0.20, 0.18), (0.13, 0.27), (0.0, 0.30), (-0.13, 0.26), (-0.21, 0.14), (-0.22, -0.02), (-0.25, -0.18)]
    s.add(loft([[V((-x * k, y, zc + z * k)) for x, z in prof] for y, k in ((0.72, 1.0), (0.75, 0.96), (0.775, 0.8))],
               BRONZE))
    return s, ("König-Albert-Denkmal (Obelisk im Albertpark, Dresdner Heide): schlanker Obelisk aus dunklem Granit auf "
               "gestuftem Unterbau (Sockelblock, Würfel mit Bronzemedaillon des Königs nach +Y, Deckplatte, Zwischenstück), "
               "graue Bodenplatte 3,4 m. Gesamthöhe ca. 9,0 m (geschätzt).")


@model
def mon_fahnentraeger():
    """Obelisk des Sowjetischen Garnisonfriedhofs (1947–49), Marienallee. Höhe 16 m (Wikipedia)."""
    h = HEIGHT["mon_fahnentraeger"]
    hs = h - 1.25                 # Steinschaft; darüber Stab und Stern
    b0, b1 = 3.6, 2.4
    s = stack([(11.0, 11.0, 0), (11.0, 11.0, 0.12)], GRANITE)
    s.add(stack([(b0, b0, 0.12), (b1, b1, hs - 0.22), (b1 - 0.5, b1 - 0.5, hs)], STONE))

    def half(z):
        return (b0 + (b1 - b0) * (z - 0.12) / (hs - 0.34)) / 2
    for i in range(1, 9):                                                                      # Lagerfugen
        z = 0.12 + i * (hs - 0.34) / 9
        w = 2 * half(z) + 0.008
        s.add(stack([(w, w, z - 0.008), (w, w, z + 0.008)], SDARK))
    sl = math.degrees(math.atan((b0 - b1) / 2 / (hs - 0.34)))

    def relief(pts, zc, t=0.24, x=0.0):
        g = loft([[V((px, yy, pz)) for px, pz in pts] for yy in (-0.05, t)], STONE)
        return g.rot((1, 0, 0), sl).move(x, half(zc), zc)
    # Vorderseite (+Y): Soldat mit Fahnenstange (Fahnenträger), zu seinen Füßen ein Panzer
    body = [(-0.55, -2.0), (0.55, -2.0), (0.62, -0.9), (0.50, 0.0), (0.72, 0.9), (0.95, 0.2), (1.10, 0.3), (0.86, 1.25),
            (0.40, 1.60), (0.22, 1.66), (0.26, 2.05), (0.05, 2.25), (-0.20, 2.10), (-0.22, 1.66), (-0.50, 1.55),
            (-0.80, 1.20), (-0.86, 0.70), (-0.60, 0.60), (-0.52, 0.0), (-0.62, -0.9)]
    s.add(relief(body, 5.3, x=0.25))
    s.add(relief([(-0.07, -1.4), (0.07, -1.4), (0.07, 3.4), (-0.07, 3.4)], 5.9, t=0.20, x=-0.62))    # Fahnenstange
    s.add(relief([(-0.07, 1.6), (1.2, 1.5), (1.45, 2.4), (1.3, 3.3), (-0.07, 3.4)], 5.9, t=0.09, x=-0.62))   # Fahnentuch
    s.add(relief([(-0.9, -0.25), (0.9, -0.25), (1.0, 0.0), (0.5, 0.12), (0.3, 0.38), (-0.3, 0.38), (-0.5, 0.12),
                  (-1.0, 0.0)], 3.05, x=0.4))                                                  # Panzer
    # übrige Seiten: Halbfigur eines Soldaten, darüber Staatswappen im Kranz
    bust = [(-0.55, -1.6), (0.55, -1.6), (0.60, -0.4), (0.78, 0.5), (0.42, 0.95), (0.22, 1.0), (0.25, 1.4), (0.0, 1.6),
            (-0.25, 1.4), (-0.22, 1.0), (-0.42, 0.95), (-0.78, 0.5), (-0.60, -0.4)]
    for k in (1, 2, 3):
        g = Soup()
        g.add(relief(bust, 5.6))
        g.add(wreath(0.55, 0.09, STONE, n=16).rot((1, 0, 0), sl).move(0, half(9.0) + 0.03, 9.0))
        g.add(disc_y(0.42, 0.05, STONE, 14).rot((1, 0, 0), sl).move(0, half(9.0), 9.0))
        s.add(g.rot((0, 0, 1), -90 * k))
    # Bronzestern auf Stab
    s.add(rod(V((0, 0, hs)), V((0, 0, hs + 0.45)), 0.04, BRONZE, n=6))
    star = [V((math.sin(TAU * i / 10) * (0.50 if i % 2 == 0 else 0.20), 0.0, math.cos(TAU * i / 10) * (0.50 if i % 2 == 0 else 0.20)))
            for i in range(10)]
    st = Soup()
    for sy in (-1, 1):
        apex = st.vert(V((0, sy * 0.10, 0)))
        ids = [st.vert(pt) for pt in star]
        for i in range(10):
            a_, b_ = ids[i], ids[(i + 1) % 10]
            st.face([apex, a_, b_] if sy < 0 else [apex, b_, a_], BRONZE)
    s.add(st.move(0, 0, h - 0.50))
    return s, ("Obelisk des Sowjetischen Garnisonfriedhofs (Marienallee, Albertstadt): 16 m hoher, sich verjüngender "
               "Pfeiler aus hellem Sandsteinquadern, bekrönt vom bronzenen Sowjetstern; Vorderseite (+Y) mit Relief "
               "eines Soldaten mit Fahne (Fahnenträger) über einem Panzer, übrige Seiten mit Soldatenrelief und Wappen "
               "im Kranz (vereinfacht); gepflasterter Platz 11 m. Höhe 16 m (belegt, Wikipedia), Grundmaß 3,6 m geschätzt.")


HEIGHT.update({"mon_bogenschuetze": 9.8, "mon_ballwerfer": 6.4, "mon_palitzsch": 3.0, "mon_friedrich_list": 3.1,
               "mon_lipsius": 5.0, "mon_koenig_albert_obelisk": 9.0, "mon_fahnentraeger": 16.0})
VIEWS.update({n: ((12, 6), (62, 12)) for n in HEIGHT})
VIEWS["mon_bogenschuetze"] = ((90, 4), (35, 10))
VIEWS["mon_ballwerfer"] = ((5, 6), (-80, 8))
VIEWS["mon_friedrich_list"] = ((40, 10), (110, 12))
VIEWS["mon_fahnentraeger"] = ((20, 4), (-60, 8))
# Nahansichten (--dev): Teil oberhalb dieser Höhe
FOCUS = {"mon_bogenschuetze": 5.8, "mon_ballwerfer": 2.1, "mon_palitzsch": 1.6, "mon_friedrich_list": 0.0,
         "mon_lipsius": 3.9, "mon_koenig_albert_obelisk": 0.0, "mon_fahnentraeger": 2.0}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    dev = "--dev" in argv
    L.NOPREVIEW = "--nopreview" in argv
    names = [a for a in argv if not a.startswith("--")] or list(MODELS)
    A.FIG.update(A.figures(POSES))
    for name in names:
        L.reset()
        mats()
        soup, notes = MODELS[name]()
        ob = build(soup, name, smooth_angle=42, merge=True)
        if dev:
            mat(BRONZE).node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.25, 0.33, 0.27, 1)
            mat(BRONZE).node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 0.2
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
