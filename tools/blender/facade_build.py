"""Fassadenteile für LoD2-Gebäudewände.

Aufruf:
  .venv/bin/python tools/blender/facade_textures.py         # Texturen (einmalig)
  flatpak run org.blender.Blender -b --python tools/blender/facade_build.py [-- name ...]

Konvention (Blender, Meter):
  Ursprung = Mitte der Unterkante auf der Wandfläche (x=0, y=0, z=0 = tiefster Punkt),
  Breite entlang X, Teil ragt nach +Y aus der Wand (= Godot -Z), Z oben (= Godot +Y).
  Ausnahme awning_shop_sign_board: Ursprung = Mitte der Rückseite (laut Vorgabe).
  Flächen, die an der Wand anliegen (y=0), werden weggelassen, wo sie nie sichtbar sind.

Materialien: Sandstone, Iron, Concrete, Wood, Glass (opak, dunkel spiegelnd),
GlassClear / ShopGlass (transparent, Alpha-Blend), Steel, Paint, SignBoard.
UVs: Welt-Box-Projektion, 1 UV-Einheit = 1 m (Waschbeton: 0.5 m).
"""
from __future__ import annotations

import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veg_facade_lib as L  # noqa: E402

OUT = os.path.join(L.MODELS, "facade")
os.makedirs(OUT, exist_ok=True)


# ---------------------------------------------------------------- Materialien
def mat_sandstone():
    return L.material("Sandstone", col="facade_sandstone_col.png", nrm="facade_sandstone_nrm.png", rough=0.88)


def mat_concrete(washed=False):
    if washed:
        return L.material("Concrete", col="facade_waschbeton_col.png", nrm="facade_waschbeton_nrm.png", rough=0.92)
    return L.material("Concrete", col="facade_concrete_col.png", nrm="facade_concrete_nrm.png", rough=0.9)


def mat_iron_rail():
    return L.material("Iron", col="facade_iron_rail_col.png", nrm="facade_iron_rail_nrm.png", clip=0.5,
                      double=True, rough=0.5, metal=0.3)


def mat_iron(color=(0.10, 0.105, 0.11, 1), rough=0.45, metal=0.5):
    return L.material("Iron", color=color, rough=rough, metal=metal)


def mat_wood():
    return L.material("Wood", col="facade_wood_col.png", nrm="facade_wood_nrm.png", rough=0.55)


def mat_glass():
    """Opak, dunkel, glatt: Reflexionen über Godot-Probes/SSR; kein Durchblick auf die Wand dahinter."""
    return L.material("Glass", color=(0.035, 0.045, 0.055, 1), rough=0.05, metal=0.0, specular=0.6)


def mat_glass_clear(name="GlassClear", alpha=0.22, color=(0.72, 0.80, 0.82, 1)):
    m = L.material(name, color=color, rough=0.04, metal=0.0, alpha=alpha, specular=0.6)
    return m


def mat_steel():
    return L.material("Steel", color=(0.62, 0.63, 0.64, 1), rough=0.32, metal=1.0)


# ---------------------------------------------------------------- Hilfen
def iron_solid_uv(p, k):
    """UV in den massiven Bereich des Eisen-Atlas (Blender-v 0..0.25)."""
    n = {"-x": Vector((-1, 0, 0)), "+x": Vector((1, 0, 0)), "-y": Vector((0, -1, 0)),
         "+y": Vector((0, 1, 0)), "-z": Vector((0, 0, -1)), "+z": Vector((0, 0, 1))}[k]
    u, v = L.box_uv(p, n, 1.0)
    return (u * 0.25, 0.02 + min(2.0, abs(v)) * 0.1)


def fquad(mb, x0, x1, y, z0, z1, mat, uv=None):
    """Senkrechtes Rechteck in der Ebene y, Vorderseite +Y (von der Wand weg)."""
    a, b = min(x0, x1), max(x0, x1)
    mb.poly([(b, y, z0), (a, y, z0), (a, y, z1), (b, y, z1)], mat, uv=uv)


def rail_card(mb, p0, p1, z0, z1, motif=0.6):
    """Geländerfeld (Alpha-Karte) von p0 nach p1 (Grundriss), Höhe z0..z1.
    U: ganze/halbe Motive (Atlas: 2 Motive je U), V: 0.25..1."""
    p0 = Vector((p0[0], p0[1], 0))
    p1 = Vector((p1[0], p1[1], 0))
    ln = (p1 - p0).length
    n = max(0.5, round(ln / motif * 2) / 2)
    u1 = n / 2.0
    pts = [p0 + Vector((0, 0, z0)), p1 + Vector((0, 0, z0)), p1 + Vector((0, 0, z1)), p0 + Vector((0, 0, z1))]
    mb.poly(pts, "Iron", uv=[(0, 0.25), (u1, 0.25), (u1, 1.0), (0, 1.0)])


def tube_x(mb, x0, x1, y, z, r, sides, mat, caps=True, **kw):
    mb.tube([(x0, y, z), (x1, y, z)], [r, r], sides, mat, cap0=caps, cap1=caps, **kw)


def finish(name, mb, mats):
    return mb.build(name, mats)


# =====================================================================
# Balkone
# =====================================================================
def balcony_gruenderzeit(name):
    mb = L.MB()
    W, D = 2.4, 1.0
    zc = 0.55                   # Konsolenoberkante = Plattenunterseite
    floor = 0.76
    # Platte, dreifach gestuft (Wassernase oben)
    mb.box((-1.16, 0, zc), (1.16, 0.96, 0.62), "Sandstone", skip=("-y",))
    mb.box((-1.20, 0, 0.62), (1.20, 1.00, 0.70), "Sandstone", skip=("-y",))
    mb.box((-1.22, 0, 0.70), (1.22, 1.02, floor), "Sandstone", skip=("-y",))
    # Konsolen mit Volutenprofil
    prof = [(0.0, 0.0), (0.11, 0.0)]
    for i in range(1, 8):
        t = i / 7
        y = 0.11 + 0.70 * t
        z = 0.05 + 0.33 * (t * t * (3 - 2 * t)) ** 0.85
        prof.append((y, z))
    prof += [(0.84, 0.45), (0.84, zc), (0.0, zc)]
    for x in (-0.86, 0.0, 0.86):
        mb.extrude_x(prof, x - 0.1, x + 0.1, "Sandstone")
        tube_x(mb, x - 0.105, x + 0.105, 0.76, 0.455, 0.075, 10, "Sandstone",
               u_range=(0, 0.47), v_scale=1.0)
        tube_x(mb, x - 0.105, x + 0.105, 0.10, 0.065, 0.06, 8, "Sandstone",
               u_range=(0, 0.38), v_scale=1.0)
    # Geländer
    yf = 0.95
    zr0, zr1 = floor + 0.03, floor + 0.95
    hr = floor + 0.99
    for x, y in ((-1.13, yf), (1.13, yf), (-1.13, 0.04), (1.13, 0.04), (0.0, yf)):
        mb.box((x - 0.02, y - 0.02, floor), (x + 0.02, y + 0.02, hr - 0.04), "Iron", skip=("-z",),
               uvmap=iron_solid_uv)
    mb.box((-1.16, yf - 0.03, hr - 0.04), (1.16, yf + 0.03, hr), "Iron", uvmap=iron_solid_uv)
    for sx in (-1, 1):
        x0, x1 = sorted((sx * 1.10, sx * 1.16))
        mb.box((x0, 0.0, hr - 0.04), (x1, yf - 0.03, hr), "Iron", skip=("-y",), uvmap=iron_solid_uv)
    rail_card(mb, (1.11, yf), (0.02, yf), zr0, zr1)
    rail_card(mb, (-0.02, yf), (-1.11, yf), zr0, zr1)
    rail_card(mb, (-1.13, yf - 0.02), (-1.13, 0.06), zr0, zr1)
    rail_card(mb, (1.13, 0.06), (1.13, yf - 0.02), zr0, zr1)
    mats = {"Sandstone": mat_sandstone(), "Iron": mat_iron_rail()}
    ob = finish(name, mb, mats)
    return ob, dict(floor_y=floor, rail_top_y=hr,
                    notes="Gründerzeit-Balkon 2.4 x 1.0 m: Sandsteinplatte (3-fach gestuft) auf 3 Volutenkonsolen, "
                          "Schmiedeeisengeländer ~1 m (Alpha-Karten, Material Iron doppelseitig mit Alpha-Scissor). "
                          "floor_y = Gehfläche über Ursprung (Ursprung = Konsolenunterkante).")


def balcony_modern(name):
    mb = L.MB()
    W, D = 3.0, 1.4
    t = 0.18
    mb.box((-1.5, 0, 0), (1.5, D, t), "Concrete", skip=("-y",))
    # Attika-/Stirnblech
    mb.box((-1.52, D, 0.08), (1.52, D + 0.02, t + 0.03), "Iron", skip=())
    for sx in (-1, 1):
        x0, x1 = sorted((sx * 1.5, sx * 1.52))
        mb.box((x0, 0, 0.08), (x1, D, t + 0.03), "Iron", skip=("-y",))
    floor = t
    hr = floor + 1.0
    yp = D - 0.05
    xp = 1.45
    posts = [(-xp, yp), (-0.49, yp), (0.49, yp), (xp, yp), (-xp, 0.70), (xp, 0.70), (-xp, 0.05), (xp, 0.05)]
    for x, y in posts:
        if abs(y - yp) < 1e-6:
            mb.box((x - 0.03, y - 0.006, floor), (x + 0.03, y + 0.006, hr - 0.02), "Iron", skip=("-z",))
        else:
            mb.box((x - 0.006, y - 0.03, floor), (x + 0.006, y + 0.03, hr - 0.02), "Iron", skip=("-z",))
    # Handlauf (Rundrohr) + Fußprofil
    r = 0.022
    mb.tube([(-xp, 0.0, hr), (-xp, yp, hr), (xp, yp, hr), (xp, 0.0, hr)], [r] * 4, 8, "Iron",
            cap0=False, cap1=False)
    mb.box((-xp, yp - 0.015, floor + 0.02), (xp, yp + 0.015, floor + 0.05), "Iron", skip=("-z",))
    for sx in (-1, 1):
        x0, x1 = sorted((sx * xp - 0.015, sx * xp + 0.015))
        mb.box((x0, 0.0, floor + 0.02), (x1, yp, floor + 0.05), "Iron", skip=("-z", "-y"))
    # Glasfüllungen
    g0, g1 = floor + 0.08, hr - 0.07
    fx = [-xp, -0.49, 0.49, xp]
    for a, b in zip(fx[:-1], fx[1:]):
        fquad(mb, a + 0.04, b - 0.04, yp, g0, g1, "GlassClear")
    for sx in (-1, 1):
        for a, b in ((0.08, 0.66), (0.74, yp - 0.04)):
            pts = [(sx * xp, a, g0), (sx * xp, b, g0), (sx * xp, b, g1), (sx * xp, a, g1)]
            if sx < 0:
                pts = pts[::-1]
            mb.poly(pts, "GlassClear")
    mats = {"Concrete": mat_concrete(), "Iron": mat_iron(), "GlassClear": mat_glass_clear()}
    mats["GlassClear"].use_backface_culling = False
    ob = finish(name, mb, mats)
    return ob, dict(floor_y=floor, rail_top_y=round(hr + r, 3),
                    notes="Moderner Balkon 3.0 x 1.4 m: Betonplatte 18 cm mit Stirnblech, Flachstahlpfosten, "
                          "Rundrohr-Handlauf, Glasfüllungen (GlassClear: Alpha-Blend, doppelseitig).")


def loggia_platte(name):
    mb = L.MB()
    h, d = 1.10, 0.10
    c = 0.02
    prof = [(0.0, 0.0), (d - c, 0.0), (d, c), (d, h - c), (d - c, h), (0.0, h)]
    _extrude_no_back(mb, prof, -1.49, 1.49, "Concrete", uvscale=2.0)
    mats = {"Concrete": mat_concrete(washed=True)}
    ob = finish(name, mb, mats)
    return ob, dict(notes="DDR-Plattenbau-Loggiabrüstung (WBS 70) als Vorsatz: Waschbetonplatte 2.98 x 1.10 m, "
                          "10 cm Vorsprung, gefaste Kanten; bei 3.0 m Raster bleibt eine 2-cm-Plattenfuge. "
                          "Concrete-Textur = Waschbeton, Kachel 0.5 m.")


def loggia_platte_riffel(name):
    mb = L.MB()
    h, d0, d = 1.10, 0.07, 0.10
    xa, xb = -1.49, 1.49
    band = 0.07
    # Bänder oben/unten in voller Stärke
    mb.box((xa, 0, 0), (xb, d, band), "Concrete", skip=("-y",))
    mb.box((xa, 0, h - band), (xb, d, h), "Concrete", skip=("-y",))
    # Grundplatte zwischen den Bändern
    fquad(mb, xa, xb, d0, band, h - band, "Concrete")
    for sx in (xa, xb):
        pts = [(sx, 0, band), (sx, d0, band), (sx, d0, h - band), (sx, 0, h - band)]
        if sx < 0:
            pts = pts[::-1]
        mb.poly(pts, "Concrete")
    # Senkrechte Trapezrippen, Raster 6 cm
    pitch = 0.06
    n = int((xb - xa) / pitch)
    x0 = xa + ((xb - xa) - n * pitch) / 2
    za, zb = band, h - band
    for i in range(n):
        xc = x0 + pitch * (i + 0.5)
        bl, br = xc - 0.0175, xc + 0.0175
        tl, tr = xc - 0.009, xc + 0.009
        # linke Flanke, Front, rechte Flanke
        mb.poly([(bl, d0, za), (tl, d, za), (tl, d, zb), (bl, d0, zb)][::-1], "Concrete")
        mb.poly([(tl, d, za), (tr, d, za), (tr, d, zb), (tl, d, zb)][::-1], "Concrete")
        mb.poly([(tr, d, za), (br, d0, za), (br, d0, zb), (tr, d, zb)][::-1], "Concrete")
    mats = {"Concrete": L.material("Concrete", col="facade_concrete_col.png", nrm="facade_concrete_nrm.png",
                                   rough=0.9, color=(0.8, 0.8, 0.8, 1))}
    ob = finish(name, mb, mats)
    return ob, dict(notes="Variante: Loggiabrüstung mit senkrechten Trapezrippen (Riffelbeton, Raster 6 cm), "
                          "2.98 x 1.10 m, 10 cm Vorsprung, glatte Bänder oben/unten.")


def _extrude_no_back(mb, prof, x0, x1, mat, uvscale=1.0):
    """Wie MB.extrude_x, aber ohne die an der Wand (y=0) liegende Fläche."""
    m = len(prof)
    a = [mb.vert((x0, y, z)) for y, z in prof]
    b = [mb.vert((x1, y, z)) for y, z in prof]
    for i in range(m):
        j = (i + 1) % m
        if prof[i][0] == 0.0 and prof[j][0] == 0.0:
            continue
        mb.face([a[i], a[j], b[j], b[i]], mat, uvscale=uvscale)
    mb.face(list(b), mat, uvscale=uvscale)
    mb.face(list(a[::-1]), mat, uvscale=uvscale)


def balcony_rail_french(name):
    mb = L.MB()
    y = 0.10
    top = 0.96
    mb.box((-0.62, y - 0.015, 0.0), (0.62, y + 0.015, 0.03), "Iron", uvmap=iron_solid_uv)
    for sx in (-1, 1):
        x0, x1 = sorted((sx * 0.58, sx * 0.62))
        mb.box((x0, y - 0.02, 0.0), (x1, y + 0.02, top - 0.04), "Iron", skip=("-z",), uvmap=iron_solid_uv)
        for zb in (0.06, 0.82):
            xa, xb = sorted((sx * 0.585, sx * 0.615))
            mb.box((xa, 0.0, zb), (xb, y - 0.02, zb + 0.03), "Iron", skip=("-y",), uvmap=iron_solid_uv)
    mb.box((-0.64, y - 0.03, top - 0.04), (0.64, y + 0.03, top), "Iron", uvmap=iron_solid_uv)
    rail_card(mb, (0.58, y), (-0.58, y), 0.02, top - 0.04, motif=0.58)
    mats = {"Iron": mat_iron_rail()}
    ob = finish(name, mb, mats)
    return ob, dict(rail_top_y=top,
                    notes="Französischer Balkon: nur Schmiedeeisengeländer 1.2 m breit, 0.10 m vor der Wand, "
                          "4 Wandhalter; Ursprung = Unterkante Geländer (auf Fensterbrüstung/Boden setzen).")


# =====================================================================
# Markise + Schild
# =====================================================================
def awning(name):
    mb = L.MB()
    z_fb = 0.26          # Unterkante Ausfallprofil = Oberkante Volant
    y_fb = 1.30
    z_w = 0.67           # Tuch-Ansatz an der Kassette
    y_w = 0.12
    V_tuch = 0.75
    # Tuch (4 Segmente, leichter Durchhang)
    segs = 4
    rows = []
    for i in range(segs + 1):
        t = i / segs
        y = y_w + (y_fb - 0.04 - y_w) * t
        z = z_w + ((z_fb + 0.05) - z_w) * t - 0.03 * math.sin(math.pi * t)
        rows.append((y, z, V_tuch * t))
    for i in range(segs):
        y0, z0, v0 = rows[i]
        y1, z1, v1 = rows[i + 1]
        mb.poly([(-0.5, y0, z0), (-0.5, y1, z1), (0.5, y1, z1), (0.5, y0, z0)], "Paint",
                uv=[(1, v0), (1, v1), (0, v1), (0, v0)])
    # Volant mit Bogenkante (4 Bögen je Modul)
    nx = 24
    yv = y_fb + 0.035
    for k in range(nx):
        xa, xb = -0.5 + k / nx, -0.5 + (k + 1) / nx

        def zb(x):
            f = ((x + 0.5) * 4) % 1.0
            if abs(x - 0.5) < 1e-9:
                f = 1.0
            return 0.045 * (1 - math.sin(math.pi * f))
        za_, zb_ = zb(xa), zb(xb)
        vt = V_tuch
        pts = [(xa, yv, za_), (xb, yv, zb_), (xb, yv, z_fb + 0.01), (xa, yv, z_fb + 0.01)]
        uv = [(0.5 - xa, 1.0 - za_ / 1.04), (0.5 - xb, 1.0 - zb_ / 1.04), (0.5 - xb, vt), (0.5 - xa, vt)]
        mb.poly(pts[::-1], "Paint", uv=uv[::-1])
    # Ausfallprofil, Kassette, Arme, Konsolen
    mb.box((-0.5, y_fb - 0.04, z_fb), (0.5, y_fb + 0.03, z_fb + 0.07), "Iron")
    cas = [(0.0, z_w - 0.06), (0.11, z_w - 0.06), (0.17, z_w), (0.17, z_w + 0.10), (0.0, z_w + 0.10)]
    _extrude_no_back(mb, cas, -0.5, 0.5, "Iron")
    for sx in (-1, 1):
        x = sx * 0.455
        p0 = Vector((x, 0.06, 0.56))
        p2 = Vector((x, y_fb - 0.03, z_fb + 0.03))
        pm = (p0 + p2) * 0.5 + Vector((0, 0, -0.03))
        mb.tube([p0, pm, p2], [0.017] * 3, 4, "Iron", squash=(1.0, 0.7), rot0=math.pi / 4)
        mb.box((x - 0.025, pm.y - 0.035, pm.z - 0.03), (x + 0.025, pm.y + 0.035, pm.z + 0.03), "Iron")
        mb.box((x - 0.035, 0.0, 0.50), (x + 0.035, 0.07, 0.62), "Iron", skip=("-y",))
    mats = {"Paint": L.material("Paint", color=(0.92, 0.92, 0.92, 1), rough=0.85, double=True),
            "Iron": mat_iron(color=(0.16, 0.165, 0.17, 1))}
    ob = finish(name, mb, mats)
    return ob, dict(mount_top_y=round(z_w + 0.10, 3), projection=round(y_fb + 0.035, 3),
                    notes="Gelenkarm-Markise ausgefahren, 1.0-m-Modul (in X skalieren), Ausfall 1.3 m, Neigung ~17°, "
                          "Bogen-Volant 0.26 m. Paint (Stoff, doppelseitig): U = 0..1 über die Modulbreite (aus Straßensicht links -> rechts, also lokal +X -> -X), "
                          "V = 0 an der Wand .. 0.75 Vorderkante Tuch .. 1.0 Volant-Unterkante. "
                          "Arme sitzen bei x=±0.455 und wandern beim Skalieren mit an die Enden. "
                          "Ursprung = tiefster Volantpunkt; mount_top_y = Oberkante Kassette über Ursprung.")


def sign_board(name):
    mb = L.MB()
    w, h, d = 1.0, 0.6, 0.06
    x0, x1, z0, z1 = -w / 2, w / 2, -h / 2, h / 2
    # U wächst aus Sicht des Betrachters vor der Tafel nach rechts (= -X), V nach oben
    e = 0.01
    mb.poly([(x0, d, z0), (x0, d, z1), (x1, d, z1), (x1, d, z0)], "SignBoard",
            uv=[(1, 0), (1, 1), (0, 1), (0, 0)])                                   # vorn (+Y)
    mb.poly([(x0, 0, z1), (x1, 0, z1), (x1, d, z1), (x0, d, z1)], "SignBoard",
            uv=[(1, 1 - e), (0, 1 - e), (0, 1), (1, 1)])                           # oben
    mb.poly([(x0, 0, z0), (x0, d, z0), (x1, d, z0), (x1, 0, z0)], "SignBoard",
            uv=[(1, e), (1, 0), (0, 0), (0, e)])                                   # unten
    mb.poly([(x0, 0, z0), (x0, 0, z1), (x0, d, z1), (x0, d, z0)], "SignBoard",
            uv=[(1 - e, 0), (1 - e, 1), (1, 1), (1, 0)])                           # -X
    mb.poly([(x1, 0, z0), (x1, d, z0), (x1, d, z1), (x1, 0, z1)], "SignBoard",
            uv=[(e, 0), (0, 0), (0, 1), (e, 1)])                                   # +X
    mb.poly([(x0, 0, z0), (x1, 0, z0), (x1, 0, z1), (x0, 0, z1)], "SignBoard",
            uv=[(0, 0), (1, 0), (1, 1), (0, 1)])                                   # Rückseite
    mats = {"SignBoard": L.material("SignBoard", color=(0.93, 0.93, 0.92, 1), rough=0.55)}
    ob = finish(name, mb, mats)
    return ob, dict(origin="Mitte Rückseite", front_z=-d,
                    notes="Ladenschild-Tafel 1.0 x 0.6 x 0.06 m, Material SignBoard, Vorderseite +Y(Blender) = -Z(Godot) "
                          "mit UV 0..1 (u wächst aus Sicht des Betrachters vor der Tafel nach rechts = lokal -X, v nach oben); Ränder mappen auf schmale Randstreifen. "
                          "Ursprung = Mitte der Rückseite (Höhe -0.3..0.3, Vorderseite bei Godot z=-0.06). In X skalieren.")


# =====================================================================
# Türen
# =====================================================================
def door_portal(name):
    mb = L.MB()
    S, W, G, I = "Sandstone", "Wood", "Glass", "Iron"
    # Stufen
    mb.box((-0.95, 0, 0.0), (0.95, 0.64, 0.16), S, skip=("-y", "-z"))
    mb.box((-0.95, 0, 0.16), (0.95, 0.32, 0.32), S, skip=("-y", "-z"))
    z0 = 0.32
    # Gewände
    for sx in (-1, 1):
        a, b = sorted((sx * 0.65, sx * 0.80))
        mb.box((a, 0, z0 + 0.24), (b, 0.15, 3.0), S, skip=("-y", "-z"))
        a2, b2 = sorted((sx * 0.64, sx * 0.81))
        mb.box((a2, 0, z0), (b2, 0.17, z0 + 0.24), S, skip=("-y", "-z"))           # Sockel
        mb.box((a2, 0, 2.62), (b2, 0.17, 2.70), S, skip=("-y",))                  # Kämpferprofil
    mb.box((-0.80, 0, 3.0), (0.80, 0.15, 3.12), S, skip=("-y",))                  # Sturz
    mb.box((-0.08, 0, 2.94), (0.08, 0.175, 3.16), S, skip=("-y",))                # Schlussstein
    mb.box((-0.86, 0, 3.12), (0.86, 0.19, 3.17), S, skip=("-y",))                 # Verdachung
    mb.box((-0.90, 0, 3.17), (0.90, 0.23, 3.27), S, skip=("-y",))
    mb.box((-0.87, 0, 3.27), (0.87, 0.20, 3.32), S, skip=("-y",))
    # Türblatt-Grundplatte, Kämpferholz, Oberlicht
    mb.box((-0.65, 0, z0), (0.65, 0.05, 2.62), W, skip=("-y", "-z", "-x", "+x"))
    mb.box((-0.65, 0, 2.62), (0.65, 0.09, 2.72), W, skip=("-y", "-x", "+x"), uvrot=True)
    fquad(mb, -0.65, 0.65, 0.03, 2.72, 3.0, G)
    for x in (-0.33, 0.0, 0.33):
        mb.box((x - 0.02, 0.0, 2.72), (x + 0.02, 0.07, 3.0), W, skip=("-y", "-z", "+z"))
    for sx in (-1, 1):
        cx = sx * 0.325
        # Füllungen (Kassetten)
        for (za, zb) in ((z0 + 0.15, 1.15), (1.25, 1.45)):
            mb.box((cx - 0.22, 0.05, za), (cx + 0.22, 0.062, zb), W, skip=("-y",))
            mb.box((cx - 0.17, 0.062, za + 0.05), (cx + 0.17, 0.072, zb - 0.05), W, skip=("-y",))
        # Glasfeld mit Kittleisten und Sprossen
        ga, gb = 1.55, 2.47
        fquad(mb, cx - 0.22, cx + 0.22, 0.052, ga, gb, G)
        mb.box((cx - 0.245, 0.05, ga - 0.025), (cx + 0.245, 0.072, ga), W, skip=("-y",), uvrot=True)
        mb.box((cx - 0.245, 0.05, gb), (cx + 0.245, 0.072, gb + 0.025), W, skip=("-y",), uvrot=True)
        mb.box((cx - 0.245, 0.05, ga), (cx - 0.22, 0.072, gb), W, skip=("-y", "-z", "+z"))
        mb.box((cx + 0.22, 0.05, ga), (cx + 0.245, 0.072, gb), W, skip=("-y", "-z", "+z"))
        mb.box((cx - 0.01, 0.052, ga), (cx + 0.01, 0.066, gb), W, skip=("-y", "-z", "+z"))
        for zz in (1.86, 2.16):
            mb.box((cx - 0.22, 0.052, zz - 0.01), (cx + 0.22, 0.066, zz + 0.01), W, skip=("-y", "-x", "+x"), uvrot=True)
    mb.box((-0.02, 0.05, z0), (0.02, 0.078, 2.62), W, skip=("-y", "-z"))         # Schlagleiste
    # Beschläge: Langschild + Knauf rechts, Klingel/Briefschlitz-Andeutung
    mb.box((0.055, 0.05, 1.00), (0.095, 0.058, 1.28), I, skip=("-y",))
    mb.box((0.06, 0.058, 1.10), (0.09, 0.10, 1.13), I, skip=("-y",))
    mb.box((0.15, 0.062, 1.20), (0.50, 0.066, 1.23), I, skip=("-y",))
    mats = {"Sandstone": mat_sandstone(), "Wood": mat_wood(), "Glass": mat_glass(),
            "Iron": mat_iron(color=(0.32, 0.26, 0.15, 1), rough=0.35, metal=0.9)}
    ob = finish(name, mb, mats)
    return ob, dict(threshold_y=z0, door_opening_wh=[1.3, 2.68],
                    notes="Gründerzeit-Hauseingang: zweiflügelige Eichentür mit Kassetten, Glasfeldern und "
                          "Oberlicht, Sandsteingewände 1.6 x 3.0 m (ab Schwelle) mit Verdachung und Schlussstein, "
                          "15 cm Vorsprung (Verdachung 23 cm), 2 Sandsteinstufen davor (1.9 m breit, 0.64 m tief). "
                          "Ursprung = Gehweg vor der untersten Stufe; Schwelle bei threshold_y. "
                          "Glass = opak/dunkel spiegelnd; Iron hier = Messing-Beschlag.")


def door_modern(name):
    mb = L.MB()
    I, G, C, St = "Iron", "Glass", "GlassClear", "Steel"
    # Blendrahmen
    for sx in (-1, 1):
        a, b = sorted((sx * 0.53, sx * 0.60))
        mb.box((a, 0, 0), (b, 0.09, 2.30), I, skip=("-y", "-z"))
    mb.box((-0.60, 0, 2.23), (0.60, 0.09, 2.30), I, skip=("-y",))
    mb.box((-0.53, 0, 0.0), (0.53, 0.06, 0.02), St, skip=("-y", "-z"))
    # Flügelrahmen
    mb.box((-0.53, 0, 0.02), (0.53, 0.065, 0.30), I, skip=("-y", "-x", "+x"))
    mb.box((-0.53, 0, 2.15), (0.53, 0.065, 2.23), I, skip=("-y", "-x", "+x", "+z"))
    for sx in (-1, 1):
        a, b = sorted((sx * 0.45, sx * 0.53))
        mb.box((a, 0, 0.30), (b, 0.065, 2.15), I, skip=("-y", "-z", "+z"))
    fquad(mb, -0.45, 0.45, 0.035, 0.30, 2.15, G)
    # Stoßgriff
    mb.tube([(0.36, 0.115, 0.85), (0.36, 0.115, 1.65)], [0.016, 0.016], 8, St, cap0=True, cap1=True)
    for zz in (0.95, 1.55):
        mb.tube([(0.36, 0.065, zz), (0.36, 0.115, zz)], [0.009, 0.009], 6, St)
    # Klingeltableau rechts neben der Tür
    mb.box((0.66, 0, 1.12), (0.80, 0.025, 1.56), St, skip=("-y",))
    for k in range(5):
        zz = 1.20 + k * 0.07
        mb.box((0.755, 0.025, zz), (0.775, 0.032, zz + 0.02), I, skip=("-y",))
    # Vordach: Glasplatte auf Wandschiene mit Zugstangen
    zc = 2.55
    mb.box((-0.8, 0, zc - 0.05), (0.8, 0.05, zc + 0.04), I, skip=("-y",))
    mb.box((-0.8, 0.05, zc), (0.8, 0.98, zc + 0.016), C)
    mb.box((-0.8, 0.98, zc - 0.012), (0.8, 1.0, zc + 0.03), I)
    for sx in (-1, 1):
        x = sx * 0.66
        mb.box((x - 0.04, 0, 3.0), (x + 0.04, 0.02, 3.12), St, skip=("-y",))
        mb.tube([(x, 0.02, 3.06), (x, 0.95, zc + 0.03)], [0.009, 0.009], 6, St)
    mats = {"Iron": mat_iron(), "Glass": mat_glass(), "GlassClear": mat_glass_clear(alpha=0.3),
            "Steel": mat_steel()}
    ob = finish(name, mb, mats)
    return ob, dict(door_opening_wh=[1.06, 2.21], canopy_y=zc,
                    notes="Moderne Haustür Alu (anthrazit) mit Glasfüllung 1.2 x 2.3 m, Edelstahl-Stoßgriff, "
                          "Klingeltableau rechts, Glasvordach 1.6 x 1.0 m auf Höhe 2.55 m (canopy_y) mit zwei Zugstangen. "
                          "Glass opak/dunkel, GlassClear (Vordach) transparent.")


def shop_window_frame(name):
    mb = L.MB()
    I, G = "Iron", "ShopGlass"
    W2 = 1.25
    f = 0.08
    for sx in (-1, 1):
        a, b = sorted((sx * (W2 - f), sx * W2))
        mb.box((a, 0, 0), (b, f, 2.6), I, skip=("-y", "-z"))
    mb.box((-W2, 0, 2.52), (W2, f, 2.6), I, skip=("-y",))
    mb.box((-W2 + f, 0, 0), (W2 - f, 0.06, 0.38), I, skip=("-y", "-z", "-x", "+x"))      # Sockelpaneel
    mb.box((-W2 + f - 0.02, 0, 0.38), (W2 - f + 0.02, 0.10, 0.41), I, skip=("-y",))       # Abdeckung
    mb.box((-W2 + f, 0, 2.06), (W2 - f, 0.07, 2.12), I, skip=("-y", "-x", "+x"))          # Kämpfer
    for x in (-0.39, 0.39):
        mb.box((x - 0.025, 0, 2.12), (x + 0.025, 0.06, 2.52), I, skip=("-y", "-z", "+z"))
    # Glashalteleisten Hauptscheibe
    gi = W2 - f
    mb.box((-gi, 0.035, 0.41), (gi, 0.05, 0.43), I, skip=("-y", "-x", "+x", "-z"))
    mb.box((-gi, 0.035, 2.04), (gi, 0.05, 2.06), I, skip=("-y", "-x", "+x", "+z"))
    for sx in (-1, 1):
        a, b = sorted((sx * gi, sx * (gi - 0.02)))
        mb.box((a, 0.035, 0.43), (b, 0.05, 2.04), I, skip=("-y", "-z", "+z"))
    # Scheiben
    fquad(mb, -gi, gi, 0.035, 0.41, 2.06, G)
    xs = [-gi, -0.415, -0.365, 0.365, 0.415, gi]
    for a, b in ((xs[0], xs[1]), (xs[2], xs[3]), (xs[4], xs[5])):
        fquad(mb, a, b, 0.03, 2.12, 2.52, G)
    mats = {"Iron": mat_iron(color=(0.07, 0.075, 0.08, 1), rough=0.4, metal=0.5),
            "ShopGlass": mat_glass_clear(name="ShopGlass", alpha=0.16, color=(0.78, 0.84, 0.86, 1))}
    ob = finish(name, mb, mats)
    return ob, dict(glass_main_x0y0x1y1=[-gi, 0.41, gi, 2.06],
                    notes="Schaufenster-Modul 2.5 x 2.6 m, 8 cm Vorsprung: dunkler Metallrahmen, Sockelpaneel 0.38 m "
                          "mit Abdeckung, Kämpfer bei 2.06 m, dreiteiliges Oberlicht. ShopGlass = transparent "
                          "(Alpha-Blend, einseitig) 3.5 cm vor der Wand; glass_main_x0y0x1y1 = Hauptscheibe in m (Godot x/y).")


MODELS = {
    "balcony_gruenderzeit": balcony_gruenderzeit,
    "balcony_modern": balcony_modern,
    "loggia_platte": loggia_platte,
    "loggia_platte_riffel": loggia_platte_riffel,
    "balcony_rail_french": balcony_rail_french,
    "awning": awning,
    "awning_shop_sign_board": sign_board,
    "door_portal": door_portal,
    "door_modern": door_modern,
    "shop_window_frame": shop_window_frame,
}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    names = argv or list(MODELS)
    L.reset()
    entries = []
    for name in names:
        L.clear_scene_objects()
        ob, extra = MODELS[name](name)
        tris = L.tri_count(ob)
        path = os.path.join(OUT, name + ".glb")
        size = L.export_glb(ob, path, vcol=False)
        mn, mx = L.bbox_godot(ob)
        notes = extra.pop("notes")
        e = dict(file=name + ".glb", height=round(mx[1] - mn[1], 3), width=round(mx[0] - mn[0], 3),
                 depth=round(mx[2] - mn[2], 3), bbox_min=mn, bbox_max=mx, tris=tris,
                 materials=[m.name for m in ob.data.materials])
        e.update(extra)
        e["notes"] = notes
        e["size_bytes"] = size
        entries.append(e)
        print(f"[facade] {name}: {tris} tris, bbox {mn} .. {mx}, {e['materials']}, {size} B")
    L.write_manifest(OUT, entries)


if __name__ == "__main__":
    main()
