"""Baut alle Stadtmoebel-Modelle nach godot/assets/models/furniture/*.glb.

Aufruf (Projektordner):
  flatpak run org.blender.Blender -b --python tools/blender/furniture_build.py [-- name ...] [--nopreview]
Vorher Texturen erzeugen: .venv/bin/python tools/blender/furniture_textures.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import furniture_lib as L  # noqa: E402
from furniture_lib import (V, Soup, mat, loft, lathe, cyl, box, cbox, tube, circle, rrect,  # noqa: E402
                           rect, build, finish, quad_uv, ico, grid_sphere, M_T, M_R, TAU)

MODELS = {}


def model(fn):
    MODELS[fn.__name__] = fn
    return fn


# ====================================================================== Hilfen
def lathe_window(zs, angs, rfun, m_out, m_in, m_rev=None, cap_top=None, cap_bot=None):
    """Drehkoerper mit radialer Vertiefung. zs/angs: Gitter (angs in Grad, CCW ab +X),
    rfun(i, j) -> Radius; Flaechen mit allen Ecken innen -> m_in, gemischt -> m_rev."""
    s = Soup()
    ids = []
    rr = []
    for i, z in enumerate(zs):
        row, rrow = [], []
        for j, a in enumerate(angs):
            r = rfun(i, j)
            ar = math.radians(a)
            row.append(s.vert((math.cos(ar) * r, math.sin(ar) * r, z)))
            rrow.append(r)
        ids.append(row)
        rr.append(rrow)
    n = len(angs)
    rmax = max(max(r) for r in rr)
    for i in range(len(zs) - 1):
        for j in range(n):
            k = (j + 1) % n
            q = [ids[i][j], ids[i][k], ids[i + 1][k], ids[i + 1][j]]
            rs = [rr[i][j], rr[i][k], rr[i + 1][k], rr[i + 1][j]]
            if all(r < rmax - 1e-6 for r in rs):
                mm = m_in
            elif any(r < rmax - 1e-6 for r in rs):
                mm = m_rev or m_out
            else:
                mm = m_out
            s.face(q, mm)
    if cap_bot:
        s.face(ids[0][::-1], cap_bot)
    if cap_top:
        s.face(ids[-1], cap_top)
    return s


def angles_with_window(n, center, half, inset):
    """Regelmaessige Winkel + Zusatzwinkel an Fensterkanten (Grad)."""
    base = [360.0 * i / n for i in range(n)]
    extra = [center - half, center - half + inset, center + half - inset, center + half]
    out = sorted(set([round(a % 360, 4) for a in base + extra]))
    # zu nahe Winkel an den Fensterkanten entfernen
    keep = []
    ex = [e % 360 for e in extra]
    for a in out:
        if any(abs(a - e) < 1e-3 for e in ex) or all(abs(((a - e + 180) % 360) - 180) > 4 for e in ex):
            keep.append(a)
    return keep


def in_window(a, center, half):
    return abs(((a - center + 180) % 360) - 180) < half - 1e-3


# ====================================================================== Leitkegel
@model
def traffic_cone():
    mat("ConeOrange", "#e2531f", 0.5)
    mat("ConeWhite", "#efefea", 0.25, spec=0.8)
    mat("Rubber", "#1c1c1c", 0.9)
    s = Soup()
    # Fussplatte 0.40 x 0.40 mit abgerundeten Ecken
    s.add(loft([rrect(0.40, 0.40, 0.06, 2, 0.0), rrect(0.40, 0.40, 0.06, 2, 0.03),
                rrect(0.36, 0.36, 0.05, 2, 0.045)], "Rubber"))
    R0, R1, Z0, Z1 = 0.165, 0.028, 0.045, 0.75

    def r(z):
        return R0 + (R1 - R0) * (z - Z0) / (Z1 - Z0)
    zs = [Z0, 0.30, 0.40, 0.50, 0.62, 0.735]
    prof = [(r(z), z) for z in zs] + [(0.018, 0.75)]
    mats = ["ConeOrange", "ConeWhite", "ConeOrange", "ConeWhite", "ConeOrange", "ConeOrange"]
    s.add(lathe(prof, 18, "ConeOrange", mats=mats, cap0=False, cap1=True))
    o = build(s, "traffic_cone", smooth_angle=50)
    finish("traffic_cone", [o], "Leitkegel 0.75 m mit zwei weissen Reflexbaendern (ConeWhite) "
           "und schwarzer Gummi-Fussplatte 0.4x0.4 m. Rotationssymmetrisch.")


# ====================================================================== Papierkorb
@model
def bin_public():
    mat("BinBody", "#4b5053", 0.45, 0.35)
    mat("Steel", "#a8adb1", 0.32, 0.85)
    mat("Inside", "#0e0e0e", 1.0)
    mat("AshHoles", "#202020", 0.8)
    s = Soup()
    n = 20
    # Bodenplatte + Standfuss
    s.add(cyl(0.17, 0.02, n, "BinBody"))
    s.add(cyl(0.055, 0.10, 10, "BinBody", z0=0.02, cap0=False))
    # Korpus
    s.add(lathe([(0.06, 0.12), (0.18, 0.125), (0.205, 0.15), (0.21, 0.20), (0.21, 0.83),
                 (0.224, 0.835), (0.224, 0.855)], n, "BinBody", cap0=True, cap1=False))
    # Haube mit Einwurfoeffnung nach +Y (90 Grad)
    zs = [0.855, 0.885, 0.90, 0.985, 1.00, 1.02]
    angs = angles_with_window(n, 90, 48, 6)

    def rf(i, j):
        if i in (2, 3) and in_window(angs[j], 90, 48 - 6 + 0.01):
            return 0.13
        return 0.228
    s.add(lathe_window(zs, angs, rf, "Steel", "Inside", "Steel"))
    # Kuppel
    zs2 = [(0.228, 1.02), (0.215, 1.05), (0.17, 1.075), (0.09, 1.085)]
    # Ringe mit identischen Winkeln wie das Fenster-Gitter (sauberer Anschluss)
    rings = []
    for r_, z_ in zs2:
        rings.append([V((math.cos(math.radians(a)) * r_, math.sin(math.radians(a)) * r_, z_)) for a in angs])
    s.add(loft(rings, "Steel", cap0=False, cap1=True, orient=V((0, 0, 1))))
    # Ascher oben: kurzer Zylinder mit Lochblech
    s.add(cyl(0.075, 0.035, 14, "Steel", z0=1.083, cap1=False, cap0=False))
    s.add(cyl(0.075, 0.0, 14, "AshHoles", z0=1.118, cap0=False))
    # Schloss vorn am Korpus
    s.add(cbox(0.0, 0.212, 0.70, 0.03, 0.012, 0.04, "Steel"))
    o = build(s, "bin_public", smooth_angle=45)
    finish("bin_public", [o], "Papierkorb ca. 90 l (Dresdner Typ: runder Stahlkorpus in Eisenglimmer-Grau "
           "BinBody, Edelstahl-Haube Steel mit Einwurfoeffnung nach +Y(Blender)=-Z(Godot), "
           "Ascher mit Lochblech (AshHoles) oben). Inside = dunkles Innere.")


# ====================================================================== Hydrant
@model
def hydrant():
    mat("HydrantRed", "#b5161b", 0.45, 0.1)
    mat("Alu", "#b8bcbf", 0.35, 0.85)
    mat("Reflex", "#f0f0ec", 0.25, spec=0.8)
    mat("MetalDark", "#2b2d2f", 0.6, 0.5)
    s = Soup()
    n = 16
    prof = [(0.16, 0.0), (0.16, 0.025), (0.13, 0.035), (0.10, 0.045), (0.10, 0.56), (0.112, 0.58),
            (0.112, 0.60), (0.118, 0.61), (0.118, 0.84), (0.118, 0.875), (0.118, 0.90),
            (0.124, 0.915), (0.124, 0.93), (0.10, 0.975), (0.055, 0.995), (0.04, 1.0)]
    mats = ["HydrantRed"] * (len(prof) - 1)
    mats[8] = "Reflex"  # Reflexband 0.84..0.875
    s.add(lathe(prof, n, "HydrantRed", mats=mats, cap0=False, cap1=True))
    # Flanschschrauben
    for k in range(6):
        a = TAU * k / 6
        s.add(cyl(0.012, 0.015, 6, "MetalDark", z0=0.025, cx=math.cos(a) * 0.14, cy=math.sin(a) * 0.14,
                  cap0=False))
    # Betaetigungsmutter (Fuenfkant)
    s.add(cyl(0.028, 0.045, 5, "MetalDark", z0=0.995, cap0=False))

    def outlet(r, length, z, ang_deg, tilt=0.0, m_pipe="HydrantRed"):
        o = Soup()
        o.add(cyl(r * 0.85, 0.05, 12, m_pipe, z0=0.0, cap0=False, cap1=False))
        o.add(cyl(r, length, 12, "Alu", z0=0.05, cap0=False))
        # Klauen der Storz-Kupplung
        for sgn in (-1, 1):
            o.add(cbox(sgn * r * 1.0, 0, 0.06, 0.02, 0.03, length * 0.6, "Alu"))
        # Kette
        o.add(cbox(0, -r - 0.006, 0.02, 0.008, 0.008, 0.06, "MetalDark"))
        o.rot((1, 0, 0), -90 + tilt)  # Achse nach +Y
        o.move(0, 0.095, z)
        o.rot((0, 0, 1), ang_deg - 90)
        return o
    s.add(outlet(0.042, 0.045, 0.78, 0, tilt=-8))     # B-Abgang rechts (+X)
    s.add(outlet(0.042, 0.045, 0.78, 180, tilt=-8))   # B-Abgang links (-X)
    s.add(outlet(0.058, 0.05, 0.68, 90))              # A-Abgang vorn (+Y)
    o = build(s, "hydrant", smooth_angle=40)
    finish("hydrant", [o], "Ueberflurhydrant ~1.04 m, Feuerrot (HydrantRed), Reflexband weiss, "
           "zwei B-Abgaenge seitlich (+-X), A-Abgang vorn nach +Y(Blender)=-Z(Godot), Kupplungen Alu.")


# ====================================================================== weitere Modelle
import furniture_models_a as MA  # noqa: E402
import furniture_models_b as MB  # noqa: E402
import furniture_models_c as MC  # noqa: E402
for _mod, _names in ((MA, ("bin_wheelie", "glass_containers", "paper_container", "post_box",
                           "street_cabinet", "parking_meter")),
                     (MB, ("cafe_set", "cafe_parasol", "sandwich_board", "planter", "bicycle", "e_scooter")),
                     (MC, ("trash_bags", "cardboard", "bulky_waste", "construction_fence"))):
    for _n in _names:
        MODELS[_n] = getattr(_mod, _n)


# ====================================================================== main
def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    nopreview = "--nopreview" in argv
    names = [a for a in argv if not a.startswith("--")] or list(MODELS)
    for nm in names:
        L.reset()
        L.NOPREVIEW = nopreview
        MODELS[nm]()


main()
