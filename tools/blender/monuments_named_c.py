"""Zweite Runde benannter Dresdner Standbilder nach Fotovorlagen: godot/assets/models/monuments/mon_<name>.glb.

Aufruf (Projektordner, immer nur ein Blender gleichzeitig):
  flatpak run --filesystem=host org.blender.Blender -b --python "$PWD/tools/blender/monuments_named_c.py" [-- name ...] [--nopreview]

Aufbau, Bausteine und Konventionen wie monuments_named_a.py (Blender Z-up, Meter, Ursprung = Bodenmitte des
Denkmals, Vorderseite +Y; rechts der Figur = +X; echte Gesamthöhe eingebaut, Maßstab im Spiel 1,0).
Vorlagen: Wikimedia-Commons-Fotos in data/research/denkmal_fotos/ (nur Vorlage, siehe QUELLEN_standbilder2.txt).
Materialien: Sandstein, Bronze, Gold, Granit, GranitRot, GranitDunkel, Sandstein_dunkel, Eisen (wie in den
bisherigen Skripten) und neu Glas (Glasfelder der Kästner-Mauer).
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

SDARK, IRON, GLASS = "Sandstein_dunkel", "Eisen", "Glas"
PED_K = os.path.join(os.path.dirname(PED_M), "ped_k.glb")


def mats():
    A.mats()
    mat(SDARK, "#4F473D", 0.9)          # schwarz verwitterter Elbsandstein (wie monuments_named_b)
    mat(IRON, "#26292B", 0.6, 0.6)      # Gusseisen / Schmiedeeisen (wie monuments_named_b)
    mat(GLASS, "#5A6E72", 0.12)         # Glasfelder


def rock(r, m, seed, sx=1.0, sy=1.0, sz=0.7):
    s = ico(r, m, 1)

    def w(co):
        k = 1.0 + 0.35 * noise.noise(co * (1.6 / r) + Vector((seed, seed * 1.7, seed * 0.3)))
        return (co.x * k * sx, co.y * k * sy, co.z * k * sz)
    return s.warp(w)


def fence(pts, h, m, z0=0.0, bars=3, closed=False, tip=0.10):
    """Eisenzaun entlang einer Polylinie: Pfosten mit Spitze an den Punkten, zwei Gurte, Stäbe dazwischen."""
    s = Soup()
    sq = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
    pts = [V(p) for p in pts]
    segs = list(zip(pts, pts[1:])) + ([(pts[-1], pts[0])] if closed else [])
    for p in pts:
        s.add(cbox(p.x, p.y, z0, 0.05, 0.05, h, m))
        s.add(stack([(0.09, 0.09, z0 + h), (0.0, 0.0, z0 + h + tip)], m, cx=p.x, cy=p.y))
    for a, b in segs:
        for zz in (z0 + 0.14, z0 + h - 0.12):
            s.add(tube([a + V((0, 0, zz)), b + V((0, 0, zz))], 0.018, 4, m, caps=False, prof=sq))
        for i in range(1, bars + 1):
            p = a.lerp(b, i / (bars + 1))
            s.add(tube([p + V((0, 0, z0 + 0.05)), p + V((0, 0, z0 + h - 0.02))], 0.011, 4, m, caps=False, prof=sq))
    return s


def helmet(j, m=BRONZE):
    """Stahlhelm über dem Kopf der Figur."""
    c = j["Head"][0].lerp(j["Head"][1], 0.95)
    return lathe([(0.138, -0.045), (0.132, 0.0), (0.125, 0.05), (0.10, 0.105), (0.055, 0.135), (0.0, 0.145)], 10, m,
                 cx=c.x, cy=c.y - 0.01).move(0, 0, c.z)


def hair(j, sx=0.115, sy=0.125, sz=0.10, dz=0.035, dy=-0.03, m=BRONZE, sub=1):
    c = j["Head"][0].lerp(j["Head"][1], 0.95)
    return ico(1.0, m, sub).scale(sx, sy, sz).move(c.x, c.y + dy, c.z + dz)


def _legs_sit(dy=(0.0, 0.0), spread=0.12):
    return A._legs_sit(dy, spread)


POSES = {
    "rest": (PED_M, []),
    "k_rest": (PED_K, []),
    # Rotarmist vorn: Ausfallschritt, rechter Arm mit Handgranate nach hinten gesenkt, linke Hand an der MPi
    "sov_a": (PED_M, [
        ("UpperLeg_L", (-0.05, 0.30, -1.0)), ("LowerLeg_L", (0.0, 0.06, -1.0)), ("Foot_L", (-0.2, 1.0, -0.2)),
        ("UpperLeg_R", (0.07, -0.20, -1.0)), ("LowerLeg_R", (0.0, -0.28, -1.0)), ("Foot_R", (0.3, 1.0, -0.35)),
        ("Head", (0.0, 0.02, 1.0), -8),
        ("UpperArm_R", (0.42, -0.22, -0.9)), ("LowerArm_R", (0.50, 0.02, -0.85)),
        ("UpperArm_L", (-0.22, 0.12, -1.0)), ("LowerArm_L", (0.72, 0.60, 0.25))]),
    # Fahnenträger dahinter: beide Hände am Fahnenschaft
    "sov_b": (PED_M, [
        ("UpperLeg_L", (-0.08, 0.10, -1.0)), ("UpperLeg_R", (0.08, -0.06, -1.0)),
        ("Head", (0.0, 0.0, 1.0), -15),
        ("UpperArm_R", (0.15, 0.75, -0.45)), ("LowerArm_R", (-0.05, 0.75, 0.55)),
        ("UpperArm_L", (-0.20, 0.60, -0.75)), ("LowerArm_L", (0.35, 0.80, 0.10))]),
    # Ludwig Richter: sitzend, linkes Bein vorgestreckt, Skizzenbuch auf dem Schoß, Stift in der Rechten
    "richter": (PED_M, [
        ("UpperLeg_L", (-0.15, 1.0, -0.12)), ("LowerLeg_L", (-0.05, 0.62, -0.80)), ("Foot_L", (-0.15, 1.0, -0.15)),
        ("UpperLeg_R", (0.15, 1.0, 0.0)), ("LowerLeg_R", (0.02, -0.22, -1.0)), ("Foot_R", (0.2, 1.0, -0.3)),
        ("Spine2", (0.0, 0.10, 1.0)), ("Head", (0.05, 0.20, 1.0), -10),
        ("UpperArm_R", (0.20, 0.28, -1.0)), ("LowerArm_R", (-0.55, 0.80, 0.12)),
        ("UpperArm_L", (-0.22, 0.20, -1.0)), ("LowerArm_L", (0.28, 0.92, -0.05))]),
    # Kruzianer, sitzend mit dem Notenbuch auf den Knien
    "k_sit": (PED_K, _legs_sit((0.10, 0.10), 0.05) + [
        ("Head", (0.0, 0.25, 1.0)),
        ("UpperArm_R", (0.15, 0.35, -1.0)), ("LowerArm_R", (-0.10, 1.0, -0.15)),
        ("UpperArm_L", (-0.15, 0.35, -1.0)), ("LowerArm_L", (0.10, 1.0, -0.15))]),
    # Kruzianer, stehend: Hand auf der Brust, Blick nach oben
    "k_chest": (PED_K, [
        ("UpperLeg_L", (-0.04, 0.10, -1.0)), ("Head", (0.0, -0.20, 1.0), 12),
        ("UpperArm_R", (0.25, -0.20, -1.0)), ("LowerArm_R", (0.10, -0.55, -0.6)),
        ("UpperArm_L", (-0.20, 0.15, -1.0)), ("LowerArm_L", (0.70, 0.60, 0.45))]),
    # Kruzianer, stehend: Hände in die Hüften gestützt, Blick ins Buch
    "k_hips": (PED_K, [
        ("UpperLeg_R", (0.05, 0.12, -1.0)), ("Head", (0.10, 0.35, 1.0), -18),
        ("UpperArm_R", (0.55, -0.20, -0.75)), ("LowerArm_R", (-0.60, 0.35, -0.45)),
        ("UpperArm_L", (-0.55, -0.20, -0.75)), ("LowerArm_L", (0.60, 0.35, -0.45))]),
    # Kurfürstin Anna: Gebetbuch mit der Linken an die Brust gedrückt, Rechte mit Schlüsseln vor dem Leib, Blick gesenkt
    "anna": (PED_F, [
        ("Neck", (0.0, 0.10, 1.0)), ("Head", (-0.03, 0.22, 1.0), -6),
        ("UpperArm_R", (0.20, 0.10, -1.0)), ("LowerArm_R", (-0.80, 0.58, 0.05)),
        ("UpperArm_L", (-0.20, 0.12, -1.0)), ("LowerArm_L", (0.60, 0.62, 0.50)), ("Hand_L", (0.5, 0.4, 0.8))]),
    # Kästner als Junge: seitlich auf der Mauer sitzend, Beine nach rechts gelegt, nach links auf den Arm gestützt
    "kaestner": (PED_K, [
        ("Hips", (-0.30, -0.04, 1.0)),
        ("UpperLeg_R", (0.92, 0.38, 0.14)), ("LowerLeg_R", (0.30, -0.90, -0.28)), ("Foot_R", (0.2, -1.0, -0.2)),
        ("UpperLeg_L", (0.80, 0.58, 0.04)), ("LowerLeg_L", (0.50, -0.82, -0.22)), ("Foot_L", (0.3, -1.0, -0.2)),
        ("Spine1", (-0.36, 0.0, 1.0)), ("Chest", (-0.26, 0.02, 1.0)), ("Neck", (-0.05, 0.04, 1.0)),
        ("Head", (0.08, 0.04, 1.0), 32),
        ("UpperArm_L", (-0.40, -0.05, -1.0)), ("LowerArm_L", (-0.12, 0.02, -1.0)), ("Hand_L", (-0.7, 0.4, -0.5)),
        ("UpperArm_R", (0.50, 0.30, -0.85)), ("LowerArm_R", (0.85, 0.35, -0.30))]),
}


# ====================================================================== Modelle
MODELS = {}
HEIGHT = {}
VIEWS = {}


def model(fn):
    MODELS[fn.__name__] = fn
    return fn


@model
def mon_sowjetisches_ehrenmal():
    """Sowjetisches Ehrenmal (O. Rost 1945), seit 1994 am Olbrichtplatz. Gesamthöhe geschätzt 9,1 m."""
    # unterer Stufenbau (drei Stufen) und oberes Podest mit Freitreppe zwischen zwei Wangenblöcken
    s = stack([(9.0, 7.4, 0), (9.0, 7.4, 0.15), (8.3, 6.7, 0.15), (8.3, 6.7, 0.30), (7.6, 6.0, 0.30), (7.6, 6.0, 0.45)],
              RED, cy=0.5)
    s.add(stack([(5.2, 3.4, 0.45), (5.2, 3.4, 1.20)], RED, cy=-0.1))
    for k in range(5):
        s.add(box(-1.5, 1.6, 0.45, 1.5, 1.6 + 0.26 * (5 - k), 0.45 + 0.15 * (k + 1), RED))
    for sx in (-1, 1):
        s.add(stack([(1.1, 1.5, 0.45), (1.1, 1.5, 1.16), (1.0, 1.4, 1.22)], RED, cx=sx * 2.05, cy=2.35))
    z = 1.20
    # dreistufiger, sich verjüngender Sockel
    s.add(stack([(2.55, 2.55, z), (2.55, 2.55, z + 0.30), (2.30, 2.30, z + 0.36), (2.24, 2.24, z + 1.62),
                 (2.36, 2.36, z + 1.68), (2.36, 2.36, z + 1.98), (2.44, 2.44, z + 2.02), (2.44, 2.44, z + 2.10),
                 (1.80, 1.80, z + 2.16), (1.74, 1.74, z + 3.20), (1.92, 1.92, z + 3.26), (1.92, 1.92, z + 3.36),
                 (1.52, 1.52, z + 3.42), (1.40, 1.40, z + 4.62), (1.56, 1.56, z + 4.68), (1.56, 1.56, z + 4.80)], RED))
    for k in range(4):       # je Seite: Relief, Jahresband, Schrifttafel, Emblem
        g = Soup()
        g.add(cb(0, 1.135, z + 0.98, 1.86, 0.05, 1.02, BRONZE))                          # Relieftafel
        g.add(cb(0, 1.13, z + 0.47, 1.30, 0.04, 0.10, BRONZE))                           # Lorbeerzweig darunter
        g.add(cb(0, 1.186, z + 1.83, 1.10, 0.012, 0.13, BRONZE))                         # 1941 – 1945
        g.add(cb(0, 0.90, z + 2.68, 1.36, 0.05, 0.72, BRONZE))                           # Schrifttafel
        if k == 0:           # vorn: Sowjetstern im Lorbeerkranz
            g.add(wreath(0.36, 0.07, n=14).move(0, 0.75, z + 4.02))
            g.add(lathe([(0.20, 0.0), (0.0, 0.05)], 5, BRONZE).rot((1, 0, 0), -90).move(0, 0.735, z + 4.02))
        else:                # Seiten: Ehrenzeichen (Schild mit Schwert)
            g.add(cb(0, 0.745, z + 4.02, 0.34, 0.04, 0.48, BRONZE))
            g.add(rod(V((0, 0.77, z + 3.62)), V((0, 0.77, z + 4.42)), 0.022))
        s.add(g.rot((0, 0, 1), -90 * k))
    zt = z + 4.80
    s.add(stack([(1.36, 1.30, zt), (1.36, 1.30, zt + 0.10)], BRONZE))
    # Bronzegruppe
    g = Soup()
    a, j = fig("sov_a")
    a.add(robe([(0.34, 0, 0.04, 0.31, 0.33, 0.07), (0.70, 0, 0.02, 0.255, 0.23, 0.05), (1.00, 0, 0.0, 0.205, 0.155, 0.0),
                (1.06, 0, 0.0, 0.215, 0.165, 0.0), (1.10, 0, 0.0, 0.205, 0.15, 0.0), (1.38, 0, 0.0, 0.215, 0.15, 0.0),
                (1.47, 0, 0.0, 0.11, 0.10, 0.0)], n=14, nf=5))                             # Mantel mit Koppel
    for side in "LR":
        a.add(sleeve(j, side, (0.072, 0.07, 0.06)))
    a.add(helmet(j))
    hr, dr = hand(j, "R")
    a.add(rod(hr - dr * 0.02, hr + dr * 0.10, 0.045, n=7, r1=0.035))                      # Handgranate
    a.add(rod(V((0.24, 0.20, 1.06)), V((-0.02, 0.215, 1.34)), 0.035, n=5))                # MPi: Kolben
    a.add(rod(V((-0.02, 0.215, 1.34)), V((-0.24, 0.20, 1.58)), 0.022, n=6))               # Laufmantel
    a.add(rod(V((0.0, 0.25, 1.24)), V((0.02, 0.25, 1.22)), 0.075, n=8).rot((1, 0, 0), 90, (0.01, 0.25, 1.23)))  # Trommel
    for sx in (-1, 1):
        a.add(rod(V((0.06 + sx * 0.05, 0.19, 0.93)), V((0.06 + sx * 0.05, 0.19, 1.04)), 0.045, n=7))   # Magazintaschen
    g.add(a.move(0.24, 0.10, 0))
    b, jb = fig("sov_b")
    b.add(robe([(0.36, 0, 0.0, 0.29, 0.25, 0.06), (0.70, 0, 0.0, 0.25, 0.21, 0.04), (1.03, 0, 0.0, 0.21, 0.16, 0.0),
                (1.38, 0, 0.0, 0.21, 0.15, 0.0), (1.47, 0, 0.0, 0.11, 0.10, 0.0)], n=12, nf=4))
    for side in "LR":
        b.add(sleeve(jb, side, (0.072, 0.07, 0.06)))
    b.add(helmet(jb))
    b = decimate(b, 0.6)
    g.add(b.move(-0.36, -0.20, 0))
    # Fahne: Schaft vom Sockelrand schräg nach hinten links, Tuch in schweren Falten herabhängend
    p0, p1 = V((0.02, 0.50, 0.0)), V((-0.50, 0.02, 2.42))
    g.add(rod(p0, p1, 0.028, n=6))
    g.add(stack([(0.0, 0.0, 0.0), (0.10, 0.02, 0.07), (0.0, 0.0, 0.20)], BRONZE).move(p1.x, p1.y, p1.z))   # Spitze
    g.add(loft([ring(zz, cx, cy, rx, ry, fd, n=12, nf=4, ph=ph) for zz, cx, cy, rx, ry, fd, ph in (
        (0.92, -0.70, -0.16, 0.05, 0.05, 0.0, 0.0), (1.08, -0.68, -0.14, 0.15, 0.10, 0.30, 0.3),
        (1.40, -0.66, -0.08, 0.23, 0.13, 0.38, 0.9), (1.72, -0.68, -0.05, 0.25, 0.13, 0.38, 1.5),
        (2.00, -0.66, -0.02, 0.21, 0.11, 0.34, 2.0), (2.22, -0.60, 0.02, 0.13, 0.08, 0.25, 2.4),
        (2.36, -0.53, 0.03, 0.06, 0.05, 0.10, 2.6), (2.42, -0.50, 0.02, 0.035, 0.035, 0.0, 2.6))], BRONZE,
        orient=V((0, 0, 1))))
    k = 1.145
    s.add(g.scale(k, k, k).move(0, -0.22, zt + 0.10))
    return s, ("Sowjetisches Ehrenmal (Olbrichtplatz): Bronzegruppe zweier Rotarmisten (vorn Soldat mit Stahlhelm, Mantel, "
               "MPi und Handgranate; dahinter Fahnenträger mit herabhängender Fahne; Blick +Y) auf dreistufigem Sockel "
               "aus rotem Meißner Granit mit Bronzereliefs, Schrifttafeln und Stern im Kranz; Stufenbau mit Freitreppe "
               "und zwei Wangenblöcken nach +Y. Gesamthöhe ca. 9,1 m (geschätzt).")


@model
def mon_moreau():
    """Moreau-Denkmal (Thormeyer/Kühn 1814), Räcknitzhöhe. Gesamthöhe geschätzt 2,65 m."""
    w, d, h = 1.38, 1.10, 1.60
    s = stack([(w, d, 0), (w, d, h - 0.03), (w - 0.06, d - 0.06, h)], GRANITE, r=0.04)
    for i, (x, y, r) in enumerate(((-0.62, 0.62, 0.34), (-0.18, 0.72, 0.26), (0.26, 0.70, 0.30), (0.66, 0.60, 0.33),
                                   (0.84, 0.10, 0.28), (-0.84, 0.05, 0.30), (-0.70, -0.55, 0.30), (0.70, -0.58, 0.32),
                                   (0.0, -0.70, 0.30))):
        s.add(rock(r, GRANITE, 2.3 + i * 1.9, 1.0, 0.8, 1.0).move(x, y, r * 0.35).warp(lambda c: (c.x, c.y, max(c.z, 0.0))))
    for sy, lines in ((1, ((1.30, 0.62, 0.11), (1.10, 0.42, 0.07), (0.94, 0.86, 0.06), (0.76, 0.78, 0.10), (0.58, 0.66, 0.06),
                           (0.42, 0.46, 0.07))),):
        for zz, lw, lh in lines:                                                          # eingehauene Inschrift
            s.add(cb(0, sy * (d / 2 + 0.004), zz, lw, 0.008, lh, DARK))
    # gusseiserne Platte mit Helm, Schwert und Lorbeerkranz
    s.add(stack([(1.06, 0.86, h), (1.06, 0.86, h + 0.11)], IRON))
    z0 = h + 0.11
    g = Soup()
    g.add(wreath(0.30, 0.075, IRON, n=12).rot((1, 0, 0), 90).scale(1.0, 0.85, 1.0).move(0, 0, 0.06))   # Kranz liegend
    # Helm: Glocke mit Nackenschirm, vorn offene Wangen und Nasenschutz, hoher nach vorn schwingender Kamm
    dome = lathe([(0.235, 0.0), (0.25, 0.10), (0.25, 0.22), (0.22, 0.33), (0.15, 0.42), (0.06, 0.465), (0.0, 0.47)], 12, IRON)
    dome.warp(lambda c: (c.x, c.y * 1.22 - 0.03 - (0.10 * (1 - c.z / 0.2) if (c.y < 0 and c.z < 0.2) else 0.0), c.z))
    g.add(dome.move(0, 0, 0.10))
    g.add(cb(0, 0.30, 0.26, 0.035, 0.03, 0.26, IRON))                                    # Nasenschutz
    crest = [(-0.20, 0.40), (-0.30, 0.56), (-0.33, 0.74), (-0.26, 0.90), (-0.10, 0.955), (0.02, 0.93), (-0.06, 0.82),
             (-0.10, 0.68), (-0.06, 0.58), (0.06, 0.555), (0.02, 0.50)]
    cr = loft([[V((x, y, zz)) for y, zz in crest] for x in (-1, 1)], IRON)
    cr.warp(lambda c: (c.x * (0.035 + 0.11 * max(0.0, (c.z - 0.5) / 0.45)), c.y, c.z))    # nach oben breiter
    g.add(cr)
    g.add(rod(V((0.50, 0.36, 0.035)), V((-0.34, -0.30, 0.05)), 0.03, IRON, n=5))           # Schwertklinge unter dem Helm
    g.add(rod(V((0.50, 0.36, 0.035)), V((0.66, 0.485, 0.035)), 0.035, IRON, n=6))          # Griff
    g.add(ico(0.05, IRON, 1).move(0.69, 0.51, 0.04))                                      # Knauf
    g.add(rod(V((0.42, 0.44, 0.035)), V((0.56, 0.27, 0.035)), 0.028, IRON, n=5))           # Parierstange
    kk = (HEIGHT["mon_moreau"] - z0) / 0.955
    s.add(g.scale(kk, kk, kk).move(0, -0.02, z0))
    # Eisengitter im Quadrat
    R = 1.55
    pts = []
    for a_, b_ in (((-R, R), (R, R)), ((R, R), (R, -R)), ((R, -R), (-R, -R)), ((-R, -R), (-R, R))):
        pts += [V((a_[0] + (b_[0] - a_[0]) * t, a_[1] + (b_[1] - a_[1]) * t, 0)) for t in (0.0, 1 / 3, 2 / 3)]
    s.add(fence(pts, 1.05, IRON, bars=3, closed=True))
    return s, ("Moreau-Denkmal (Räcknitzhöhe): Granitblock mit Inschrift (vorn, +Y), darauf Gusseisenplatte mit antikem "
               "Helm mit Kamm, Schwert und Lorbeerkranz; Feldsteine am Fuß, quadratisches Eisengitter 3,1 m. Ohne die "
               "drei Eichen. Gesamthöhe ca. 2,65 m (geschätzt).")


@model
def mon_ludwig_richter():
    """Ludwig-Richter-Denkmal (Kircheisen 1898, Neuguss 2013), Brühlsche Terrasse. Gesamthöhe geschätzt 4,5 m."""
    s = stack([(2.5, 2.5, 0), (2.5, 2.5, 0.12), (1.95, 1.95, 0.12), (1.95, 1.95, 0.40), (1.75, 1.75, 0.48),
               (1.62, 1.62, 0.56), (1.56, 1.56, 0.56), (1.56, 1.56, 2.00), (1.70, 1.70, 2.06), (1.70, 1.70, 2.17)], RED)
    for i, lw in enumerate((0.92,)):
        s.add(cb(0, 0.78 + 0.005, 1.42, lw, 0.01, 0.09, GOLD))                             # LUDWIG RICHTER
    # Flügelmauern (schräg nach vorn) mit Endpfeilern
    for sx in (-1, 1):
        a_, b_ = V((sx * 0.78, 0.25, 0)), V((sx * 4.75, 2.05, 0))
        n = V((-(b_ - a_).y, (b_ - a_).x, 0)).normalized() * 0.19
        rings = []
        for p, hh in ((a_, 1.50), (b_, 1.12)):
            rings.append([p - n, p + n, p + n + V((0, 0, hh)), p - n + V((0, 0, hh))])
        s.add(loft(rings, RED))
        rings = []
        n2 = n * 1.3
        for p, hh in ((a_, 1.50), (b_, 1.12)):
            rings.append([p - n2 + V((0, 0, hh)), p + n2 + V((0, 0, hh)), p + n2 + V((0, 0, hh + 0.08)),
                          p - n2 + V((0, 0, hh + 0.08))])
        s.add(loft(rings, RED))
        s.add(stack([(0.95, 0.95, 0), (0.95, 0.95, 0.18), (0.82, 0.82, 0.22), (0.82, 0.82, 1.14), (0.96, 0.96, 1.18),
                     (0.96, 0.96, 1.28), (0.80, 0.80, 1.33)], RED, cx=sx * 5.1, cy=2.22))
    # Zaunbogen zwischen den Pfeilern, davor flache Granitstufe
    arc = []
    N = 18
    for i in range(N + 1):
        t = i / N
        x = -4.62 + 9.24 * t
        arc.append(V((x, 2.30 + 1.25 * (1 - (2 * t - 1) ** 2), 0)))
    s.add(fence(arc, 1.0, IRON, z0=0.10, bars=2, tip=0.14))
    step_o = [V((p.x * 1.12, p.y + 0.55, 0)) for p in arc]
    step_i = [V((p.x, p.y - 0.10, 0)) for p in arc]
    for a0_, a1_, b0_, b1_ in zip(step_i, step_i[1:], step_o, step_o[1:]):
        s.add(loft([[a0_, b0_, b1_, a1_], [q + V((0, 0, 0.10)) for q in (a0_, b0_, b1_, a1_)]], GRANITE,
                   orient=V((0, 0, 1))))
    # Sitzfigur auf dem Baumstumpf
    f, j = fig("richter")
    stump = lathe([(0.50, 0.20), (0.46, 0.30), (0.38, 0.48), (0.33, 0.68), (0.31, 0.80), (0.27, 0.83)], 10, BRONZE, cy=-0.10)
    stump.warp(lambda c: (c.x * (1 + 0.18 * noise.noise(Vector((c.x * 3, c.y * 3, c.z * 2)))),
                          (c.y + 0.10) * (1 + 0.18 * noise.noise(Vector((c.y * 3, c.x * 3 + 5, c.z * 2)))) - 0.10
                          + 0.22 * max(0.0, 0.5 - c.z), c.z))
    f.add(stump)
    f.add(robe([(0.74, 0, -0.06, 0.30, 0.24, 0.05), (0.90, 0, -0.03, 0.26, 0.20, 0.03), (1.20, 0, 0.0, 0.225, 0.165, 0.0),
                (1.40, 0, 0.02, 0.215, 0.15, 0.0), (1.47, 0, 0.03, 0.11, 0.10, 0.0)], n=12, nf=4))   # Rock
    f.add(robe([(0.70, 0.0, 0.26, 0.27, 0.26, 0.05), (0.84, 0.0, 0.20, 0.25, 0.27, 0.0), (0.90, 0, 0.10, 0.20, 0.22, 0.0)],
               n=12, nf=5))                                                                # Rockschöße über den Schenkeln
    for side in "LR":
        f.add(sleeve(j, side, (0.075, 0.07, 0.06)))
    f.add(hair(j, 0.118, 0.125, 0.10, 0.03, -0.035))
    c = j["Head"][0].lerp(j["Head"][1], 0.95)
    for sx in (-1, 1):
        f.add(ico(1.0, BRONZE, 1).scale(0.045, 0.075, 0.10).move(c.x + sx * 0.095, c.y - 0.04, c.z - 0.07))   # langes Haar
    hl, _ = hand(j, "L")
    hr, _ = hand(j, "R")
    f.add(cb(hl.x + 0.12, hl.y - 0.02, hl.z - 0.03, 0.36, 0.26, 0.04, BRONZE).rot((1, 0, 0), 14, tuple(hl)))   # Skizzenbuch
    f.add(rod(hr + V((0.0, 0.0, 0.07)), hr + V((-0.03, 0.03, -0.09)), 0.008, n=4))        # Stift
    f.add(lathe([(0.20, 0.0), (0.21, 0.02), (0.12, 0.05), (0.105, 0.13), (0.08, 0.15), (0.0, 0.155)], 10, BRONZE,
                cx=0.02, cy=0.62).move(0, 0, 0.20))                                        # Hut zu Füßen
    s.add(stack([(1.50, 1.56, 2.17), (1.50, 1.56, 2.29)], BRONZE))
    f.warp(lambda c: (c.x, c.y, max(c.z, 0.20)))
    place(f, 2.29, HEIGHT["mon_ludwig_richter"] - 2.29, y=-0.12)
    s.add(f)
    return s, ("Ludwig-Richter-Denkmal (Brühlsche Terrasse, Zustand seit 2013): Bronzesitzfigur auf Baumstumpf mit "
               "Skizzenbuch und Stift, Hut zu Füßen (Blick +Y), roter Granitsockel mit Goldinschrift; nach vorn "
               "ausschwingende Flügelmauern mit Endpfeilern, Eisenzaun im Bogen und Granitstufe davor. Ursprung = "
               "Sockelmitte; Anlage 11 m breit, reicht 4,2 m nach +Y. Gesamthöhe ca. 4,5 m (geschätzt).")


def _kid(pose, smock=True, ratio=0.6):
    f, j = fig(pose)
    H = max(v.z for v in A.FIG["k_rest"][0].v)
    if smock:
        f.add(robe([(0.36 * H, 0, 0.0, 0.175 * H, 0.14 * H, 0.06), (0.56 * H, 0, 0.0, 0.14 * H, 0.105 * H, 0.03),
                    (0.80 * H, 0, 0.0, 0.125 * H, 0.09 * H, 0.0), (0.84 * H, 0, 0.0, 0.065 * H, 0.06 * H, 0.0)], n=10, nf=5))
    f = decimate(f, ratio)
    c = j["Head"][0].lerp(j["Head"][1], 0.95)
    f.add(ico(1.0, BRONZE, 1).scale(0.072 * H, 0.078 * H, 0.062 * H).move(c.x, c.y - 0.012 * H, c.z + 0.012 * H))   # Pagenkopf
    return f, j, H


@model
def mon_julius_otto():
    """Julius-Otto-Denkmal (G. Kietz 1886, Kindergruppe Neuguss 2011), An der Kreuzkirche. Gesamthöhe geschätzt 4,0 m."""
    s = stack([(4.4, 4.4, 0), (4.4, 4.4, 0.40)], GRANITE, cy=0.35)
    s.add(stack([(3.3, 3.3, 0.40), (3.3, 3.3, 0.58), (3.1, 3.1, 0.70), (3.02, 3.02, 0.74), (3.02, 3.02, 0.84)], GRANITE,
                cy=0.25))
    s.add(stack([(2.25, 2.35, 0.84), (2.25, 2.35, 0.96), (2.10, 2.20, 1.06), (2.04, 2.14, 1.08), (2.04, 2.14, 1.15)],
                GRANITE, cy=0.25))
    py = -0.22
    s.add(stack([(1.10, 1.00, 1.15), (1.10, 1.00, 1.42), (0.98, 0.88, 1.50), (0.88, 0.78, 1.50), (0.86, 0.76, 2.72),
                 (0.94, 0.84, 2.77), (1.12, 1.02, 2.85), (1.12, 1.02, 2.93), (0.92, 0.82, 2.97), (0.92, 0.82, 3.03),
                 (0.84, 0.74, 3.03), (0.84, 0.74, 3.08)], GRANITE, cy=py))
    # Tafel im Lorbeerkranz: JULIUS OTTO
    s.add(cb(0, py + 0.38 + 0.02, 2.36, 0.62, 0.04, 0.58, BRONZE))
    s.add(wreath(0.24, 0.045, n=12).scale(1, 0.6, 1.1).move(0, py + 0.38 + 0.05, 2.36))
    # Büste in Hermenform
    b = clip(fig("rest")[0], [((0, 0, 1.20), (0, 0, -1)), ((0.21, 0, 0), (1, 0, 0)), ((-0.21, 0, 0), (-1, 0, 0))])
    b.add(hair(A.FIG["rest"][1], 0.112, 0.118, 0.085, 0.045, -0.04))
    b.move(0, 0, -1.20)
    kb = (HEIGHT["mon_julius_otto"] - 3.08) / max(v.z for v in b.v)
    s.add(b.scale(kb * 1.12, kb * 1.12, kb).move(0, py + 0.02, 3.08))
    # Kindergruppe: zwei sitzende Sänger mit Notenbuch, zwei stehende
    zk = 1.15
    s.add(stack([(1.70, 0.95, zk), (1.70, 0.95, zk + 0.05)], BRONZE, cy=0.62))
    s.add(stack([(1.00, 0.44, zk + 0.05), (1.00, 0.44, zk + 0.40), (1.06, 0.48, zk + 0.44)], BRONZE, cy=0.46))   # Sitzbank
    for sx in (-1, 1):
        f, j, H = _kid("k_sit", smock=False)
        f.add(robe([(0.52 * H, 0, 0.0, 0.135 * H, 0.10 * H, 0.03), (0.80 * H, 0, 0.0, 0.125 * H, 0.09 * H, 0.0),
                    (0.84 * H, 0, 0.0, 0.065 * H, 0.06 * H, 0.0)], n=10, nf=5))
        lo = min(v.z for v in f.v)
        hi = max(v.z for v in f.v)
        kk = 1.02 / (hi - lo)
        f.move(0, 0, -lo).scale(kk, kk, kk).rot((0, 0, 1), sx * 8)
        s.add(f.move(sx * 0.25, 0.52, zk + 0.05))
    s.add(cb(0, 0, 0, 0.36, 0.30, 0.03, BRONZE).rot((0, 1, 0), 9).rot((1, 0, 0), 16).move(-0.19, 0.93, zk + 0.62))   # Notenbuch
    s.add(cb(0, 0, 0, 0.36, 0.30, 0.03, BRONZE).rot((0, 1, 0), -9).rot((1, 0, 0), 16).move(0.19, 0.93, zk + 0.62))
    f, j, H = _kid("k_chest")
    place(f, zk + 0.05, 1.36, 0.70, 0.36, rz=18)
    s.add(f)
    f, j, H = _kid("k_hips")
    place(f, zk + 0.05, 1.30, -0.70, 0.50, rz=-28)
    s.add(f)
    return s, ("Julius-Otto-Denkmal (An der Kreuzkirche): Bronzebüste in Hermenform auf Granitpfeiler mit Namenstafel im "
               "Kranz, davor vier Kruzianer in Bronze (zwei sitzend mit Notenbuch, zwei stehend; Blick +Y), dreistufiger "
               "Granitunterbau. Gesamthöhe ca. 4,0 m (geschätzt).")


@model
def mon_mutter_anna():
    """Denkmal der Kurfürstin Anna (R. Henze 1869), vor der Annenkirche. Gesamthöhe geschätzt 5,5 m."""
    s = stack([(4.3, 4.3, 0), (4.3, 4.3, 0.18), (2.9, 2.9, 0.18), (2.9, 2.9, 0.36)], GRANITE)
    z = 0.36
    s.add(cstack([(1.95, 1.95, z), (1.95, 1.95, z + 0.12), (1.50, 1.50, z + 0.34), (1.42, 1.42, z + 0.36),
                  (1.42, 1.42, z + 0.98), (1.50, 1.50, z + 1.02), (1.66, 1.66, z + 1.10), (1.66, 1.66, z + 1.18),
                  (1.50, 1.50, z + 1.26), (1.22, 1.22, z + 1.36), (1.18, 1.18, z + 1.38), (1.18, 1.18, z + 2.36),
                  (1.26, 1.26, z + 2.40), (1.50, 1.50, z + 2.50), (1.50, 1.50, z + 2.58), (1.30, 1.30, z + 2.62)], DARK, 0.10))
    for zz, lw, lh in ((2.02, 0.42, 0.10), (1.84, 0.74, 0.07), (1.70, 0.20, 0.05), (1.56, 0.50, 0.07)):   # ANNA / CHURFÜRSTIN / VON / SACHSEN
        s.add(cb(0, 0.59 + 0.005, z + zz, lw, 0.01, lh, GOLD))
    zb = z + 2.62
    s.add(cstack([(1.22, 1.22, zb), (1.22, 1.22, zb + 0.06), (1.08, 1.08, zb + 0.12), (1.04, 1.04, zb + 0.24),
                  (1.10, 1.10, zb + 0.28), (1.10, 1.10, zb + 0.32)], BRONZE, 0.10))
    f, j = fig("anna")
    f = clip(f, [((0, 0, 1.0), (0, 0, -1))])
    f.add(robe([(0.0, 0, 0.0, 0.285, 0.265, 0.08), (0.45, 0, 0.0, 0.255, 0.225, 0.06), (0.95, 0, 0.0, 0.215, 0.175, 0.03),
                (1.10, 0, 0.0, 0.185, 0.14, 0.0), (1.20, 0, 0.0, 0.19, 0.14, 0.0)], n=16, nf=5))   # Rock
    f.add(cloak([(1.47, -0.01, 0.235, 0.16), (1.25, -0.02, 0.27, 0.19), (0.75, -0.03, 0.285, 0.25), (0.04, -0.04, 0.315, 0.29)],
                BRONZE, half=112, k=10, th=0.045))                                          # offene Schaube mit Pelzbesatz
    for sx in (-1, 1):
        f.add(tube([V((sx * 0.09, 0.12, 1.43)), V((sx * 0.11, 0.15, 1.10)), V((sx * 0.14, 0.20, 0.55)),
                    V((sx * 0.15, 0.235, 0.05))], 0.05, 6, BRONZE, rs=[0.04, 0.045, 0.045, 0.04]))   # Pelzkanten vorn
        f.add(ico(1.0, BRONZE, 1).scale(0.085, 0.085, 0.085).move(sx * 0.205, 0.0, 1.41))  # Puffärmel
    for side in "LR":
        f.add(sleeve(j, side, (0.07, 0.065, 0.055)))
    c = j["Head"][0].lerp(j["Head"][1], 0.95)
    f.add(ico(1.0, BRONZE, 1).scale(0.112, 0.125, 0.112).move(c.x, c.y - 0.045, c.z + 0.015))   # Haube
    nk = j["Neck"][0]
    f.add(lathe([(0.075, 0.0), (0.10, 0.02), (0.10, 0.045), (0.07, 0.06)], 10, BRONZE, cx=nk.x, cy=nk.y + 0.01).move(0, 0, nk.z + 0.03))   # Halskrause
    hl, _ = hand(j, "L")
    f.add(cb(hl.x + 0.015, hl.y + 0.0, hl.z + 0.07, 0.13, 0.045, 0.19, BRONZE).rot((1, 0, 0), -10, tuple(hl)))   # Gebetbuch
    hr, _ = hand(j, "R")
    f.add(rod(hr + V((-0.02, 0.03, 0.0)), hr + V((-0.03, 0.04, -0.20)), 0.016, n=4))      # Schlüsselbund
    place(f, zb + 0.32, HEIGHT["mon_mutter_anna"] - zb - 0.32)
    s.add(f)
    return s, ("Mutter-Anna-Denkmal (Kurfürstin Anna, vor der Annenkirche): Bronzefigur mit Haube, Halskrause und "
               "pelzbesetzter Schaube, Gebetbuch an der Brust, Schlüsselbund (Blick +Y) auf dunklem poliertem "
               "Syenitsockel mit Goldinschrift, zwei graue Granitstufen. Gesamthöhe ca. 5,5 m (geschätzt).")


@model
def mon_bismarcksaeule():
    """Bismarcksäule Räcknitz (W. Kreis 1906, Typ »Götterdämmerung«). Gesamthöhe 23 m (Wikipedia)."""
    m = SDARK
    s = stack([(16.0, 16.0, 0), (16.0, 16.0, 1.10), (12.6, 12.6, 1.10), (12.6, 12.6, 2.00)], m)
    s.add(stack([(10.1, 10.1, 2.00), (9.9, 9.9, 4.80), (10.15, 10.15, 4.92), (10.15, 10.15, 5.20), (8.2, 8.2, 5.35)], m))
    # Kern und vier Dreiviertelsäulen an den Ecken
    s.add(stack([(7.5, 7.5, 5.20), (7.2, 7.2, 14.9)], m))
    for sx in (-1, 1):
        for sy in (-1, 1):
            s.add(lathe([(1.78, 5.20), (1.78, 5.60), (1.66, 5.75), (1.58, 13.55), (1.74, 13.70), (1.92, 13.95),
                         (1.96, 14.30), (1.86, 14.62), (1.66, 14.80), (1.66, 14.95)], 14, m, cx=sx * 3.05, cy=sy * 3.05))
    # Wulst auf Kämpferhöhe zwischen den Säulen und mächtiger Architrav mit runden Ecken

    def rr(side, r, zz):
        return rrect(side, side, r, 4, zz)
    s.add(loft([rr(7.6, 0.4, 13.75), rr(8.0, 0.6, 14.0), rr(8.0, 0.6, 14.4), rr(7.6, 0.4, 14.7)], m, orient=V((0, 0, 1))))
    s.add(loft([rr(8.6, 1.9, 14.9), rr(9.4, 2.2, 15.25), rr(9.75, 2.35, 15.9), rr(9.75, 2.35, 16.9), rr(9.5, 2.25, 17.5),
                rr(8.9, 2.0, 17.9), rr(8.3, 1.0, 18.0)], m, orient=V((0, 0, 1))))
    # dreifach gestufter Aufsatz mit Feuerschale
    s.add(stack([(8.3, 8.3, 18.0), (8.1, 8.1, 19.5), (7.5, 7.5, 19.5), (7.3, 7.3, 21.0), (6.7, 6.7, 21.0), (6.5, 6.5, 22.6),
                 (6.6, 6.6, 22.6), (6.6, 6.6, 22.75)], m))
    s.add(stack([(4.0, 4.0, 22.75), (4.0, 4.0, 23.0)], "Stahl"))
    # Eingang und Freitreppen an der Vorderseite (+Y)
    s.add(box(-0.75, 4.93, 2.0, 0.75, 5.06, 4.3, IRON))
    s.add(box(-1.05, 4.9, 2.0, 1.05, 5.02, 4.55, m))
    for k in range(6):
        s.add(box(-1.6, 6.3, 1.10 + 0.15 * k, 1.6, 6.3 + 0.30 * (6 - k), 1.10 + 0.15 * (k + 1), m))
    for k in range(7):
        s.add(box(-1.8, 8.0, 0.157 * k, 1.8, 8.0 + 0.30 * (7 - k), 0.157 * (k + 1), m))
    return s, ("Bismarcksäule Räcknitz (Wilhelm Kreis, Entwurf »Götterdämmerung«): dunkler Sandsteinturm auf quadratischem "
               "Grundriss mit vier Dreiviertelsäulen an den Ecken, wulstigem Architrav und dreifach gestuftem Aufsatz, "
               "zweistufige Terrasse 16 m mit Freitreppe und Eingang nach +Y. Gesamthöhe 23 m (belegt).")


@model
def mon_rosa_luxemburg():
    """Rosa-Luxemburg-Denkmal, Rosa-Luxemburg-Platz (heutige Stele mit Bronzerelief). Gesamthöhe geschätzt 2,5 m."""
    w, d, h = 1.08, 0.44, HEIGHT["mon_rosa_luxemburg"]
    s = stack([(w, d, 0), (w, d, h)], STONE)
    yf = d / 2
    pw, ph, zc = 0.86, 1.10, h - 0.12 - 0.55
    s.add(cb(0, yf + 0.0175, zc, pw, 0.035, ph, BRONZE))
    # Profilbildnis nach links (vom Betrachter aus) als flaches Relief: Büstenabschnitt, Hals, Kopf, Haarknoten
    prof = [(-0.34, -0.36), (0.30, -0.36), (0.27, -0.28), (0.13, -0.12), (0.10, -0.02), (0.17, 0.02), (0.20, 0.07),
            (0.26, 0.13), (0.20, 0.20), (0.21, 0.30), (0.14, 0.40), (0.0, 0.44), (-0.14, 0.40), (-0.24, 0.31),
            (-0.27, 0.21), (-0.21, 0.12), (-0.10, 0.07), (-0.08, -0.04), (-0.22, -0.12), (-0.33, -0.24)]
    s.add(loft([[V((x * k, y, zc + 0.02 + 0.04 + (zz - 0.04) * k)) for x, zz in prof]
                for y, k in ((yf + 0.03, 1.0), (yf + 0.055, 1.0), (yf + 0.085, 0.86))], BRONZE))
    s.add(cb(0, yf + 0.037, zc - 0.40, 0.68, 0.006, 0.055, BRONZE))                       # ROSA LUXEMBURG
    return s, ("Rosa-Luxemburg-Denkmal (Rosa-Luxemburg-Platz, heutiger Zustand): hochrechteckige helle Steinstele mit "
               "Bronzerelief (Profilbildnis, vorn = +Y). Gesamthöhe ca. 2,5 m (geschätzt).")


@model
def mon_kaestner():
    """Erich-Kästner-Denkmal (M. Malolepszy 1990), Mauer am Kästner-Museum, Albertplatz. Gesamthöhe geschätzt 2,6 m."""
    hw = 1.80
    s = stack([(2.6, 0.50, 0), (2.6, 0.50, hw)], STONE, r=0.24)
    s.add(stack([(2.72, 0.62, hw), (2.72, 0.62, hw + 0.07), (2.64, 0.54, hw + 0.09)], STONE, r=0.28))   # Abdeckplatte
    for i in range(1, 5):                                                                 # Lagerfugen des Quadermauerwerks
        s.add(stack([(2.605, 0.505, i * 0.36 - 0.008), (2.605, 0.505, i * 0.36 + 0.008)], SDARK, r=0.24))
    s.add(cb(-0.55, 0.25 + 0.004, 0.98, 0.42, 0.012, 1.36, GLASS))                        # Glasfeld mit Texten
    s.add(cb(-0.05, 0.25 + 0.01, 0.42, 0.24, 0.02, 0.34, BRONZE))                         # Tafel
    f, j = fig("kaestner")
    H = max(v.z for v in A.FIG["k_rest"][0].v)
    c = j["Head"][0].lerp(j["Head"][1], 0.95)
    f.add(ico(1.0, BRONZE, 1).scale(0.088 * H, 0.094 * H, 0.070 * H).move(c.x, c.y - 0.016 * H, c.z + 0.028 * H))   # Haar
    lo = min(v.z for v in f.v)
    k = 1.50 / H                                                                          # Junge, stehend etwa 1,5 m
    f.move(0, 0, -lo).scale(k, k, k)
    xs = [v.x for v in f.v]
    f.move(-(min(xs) + max(xs)) / 2 - 0.42, 0.0, hw + 0.09 - 0.03)
    ys = [v.y for v in f.v if v.z < hw + 0.3]
    f.move(0, -(min(ys) + max(ys)) / 2, 0)
    top = max(v.z for v in f.v)
    f.scale(1, 1, (HEIGHT["mon_kaestner"] - hw - 0.06) / (top - hw - 0.06), (0, 0, hw + 0.06))
    s.add(f)
    return s, ("Erich-Kästner-Denkmal (Albertplatz, am Kästner-Museum): Bronzefigur des Jungen, seitlich auf der Mauer "
               "sitzend und auf den linken Arm gestützt (Brust nach +Y, Beine nach +X), auf einem 2,6 m langen Stück "
               "Sandsteinmauer mit Abdeckplatte, Glasfeld und Tafel. Gesamthöhe ca. 2,6 m (geschätzt).")


HEIGHT.update({"mon_sowjetisches_ehrenmal": 9.1, "mon_moreau": 2.65, "mon_ludwig_richter": 4.5, "mon_julius_otto": 4.0,
               "mon_mutter_anna": 5.5, "mon_bismarcksaeule": 23.0, "mon_rosa_luxemburg": 2.5, "mon_kaestner": 2.6})
VIEWS.update({n: ((12, 6), (62, 12)) for n in HEIGHT})
VIEWS["mon_sowjetisches_ehrenmal"] = ((20, 8), (-50, 14))
VIEWS["mon_moreau"] = ((10, 10), (80, 14))
VIEWS["mon_ludwig_richter"] = ((0, 12), (35, 22))
VIEWS["mon_bismarcksaeule"] = ((45, 5), (10, 12))
VIEWS["mon_kaestner"] = ((8, 8), (115, 14))
# Nahansichten (--dev): Teil oberhalb dieser Höhe
FOCUS = {"mon_sowjetisches_ehrenmal": 6.0, "mon_moreau": 1.6, "mon_ludwig_richter": 2.2, "mon_julius_otto": 1.15,
         "mon_mutter_anna": 3.2, "mon_bismarcksaeule": 13.0, "mon_rosa_luxemburg": 1.2, "mon_kaestner": 1.7}


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
