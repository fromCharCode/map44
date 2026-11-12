"""Modelle Teil C: Muellsaecke, Kartons, Sperrmuell, Bauzaun."""
import math
import random
from furniture_lib import (V, Soup, mat, loft, lathe, cyl, box, cbox, tube, circle, rrect,
                           rect, build, finish, grid_sphere, TAU)
from furniture_models_b import pnoise


def slab(w, d, t, m, top_uv, side_v, side_scale=1.0):
    """Quader mit expliziten UVs: Ober-/Unterseite -> top_uv (u0,v0,u1,v1), Seiten -> Streifen side_v."""
    s = Soup()
    x, y = w / 2, d / 2
    P = [(-x, -y, 0), (x, -y, 0), (x, y, 0), (-x, y, 0), (-x, -y, t), (x, -y, t), (x, y, t), (-x, y, t)]
    i = [s.vert(p) for p in P]
    u0, v0, u1, v1 = top_uv
    s.face([i[4], i[5], i[6], i[7]], m, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
    s.face([i[0], i[3], i[2], i[1]], m, [(u0, v0), (u0, v1), (u1, v1), (u1, v0)])
    a, b = side_v
    for f, L in (([0, 1, 5, 4], w), ([2, 3, 7, 6], w), ([3, 0, 4, 7], d), ([1, 2, 6, 5], d)):
        Ls = L * side_scale
        s.face([i[k] for k in f], m, [(0, a), (Ls, a), (Ls, b), (0, b)])
    return s


# ====================================================================== Muellsaecke
def _bag(r, h, seed, m):
    s = grid_sphere(r, 12, 8, m)

    def w(p):
        zn = p.z / r
        th = math.atan2(p.y, p.x)
        k = 1 + 0.12 * pnoise(p * 2.2, seed) + 0.05 * pnoise(p * 5.5, seed + 3) \
            + 0.06 * math.sin(3 * th + seed) * math.cos(zn * 2.0 + seed)
        neck = 1.0
        if zn > 0.68:
            neck = 1.0 - ((min(zn, 1.0) - 0.68) / 0.32) ** 0.6 * 0.86
        x, y = p.x * k * neck * 1.12, p.y * k * neck * 1.12
        z = p.z * h / r
        if zn > 0.68:
            z = 0.68 * h + (z - 0.68 * h) * 0.55
        if zn < -0.45:
            z = -0.45 * h + (z + 0.45 * h) * 0.3
            x *= 1.05
            y *= 1.05
        return V((x, y, z))
    s.warp(w)
    zmin = min(v.z for v in s.v)
    s.move(0, 0, -zmin)
    top = max(v.z for v in s.v)
    # Knoten: zwei Zipfel
    for sgn in (-1, 1):
        e = lathe([(0.03, 0.0), (0.016, 0.045), (0.022, 0.075), (0.0, 0.095)], 5, m, cap0=False)
        e.scale(1.0, 0.5, 1.0).rot((0, 1, 0), 40 * sgn).move(0, 0, top - 0.02)
        s.add(e)
    return s


def trash_bags():
    mat("BagBlack", "#121212", 0.3, spec=0.7)
    mat("BagGrey", "#4b4f53", 0.38, spec=0.6)
    mat("BagBlue", "#2a4b85", 0.33, spec=0.6)
    s = Soup()
    s.add(_bag(0.30, 0.36, 1.0, "BagBlack").rot((0, 0, 1), 20).move(-0.27, 0.04, 0))
    s.add(_bag(0.27, 0.33, 2.3, "BagBlack").rot((0, 0, 1), -40).move(0.30, -0.10, 0))
    s.add(_bag(0.23, 0.30, 3.7, "BagGrey").rot((0, 0, 1), 75).move(0.08, 0.36, 0))
    lean = _bag(0.22, 0.28, 5.1, "BagBlue")
    lean.rot((1, 0, 0), 38).rot((0, 0, 1), 15).move(0.03, -0.18, 0.13)
    s.add(lean)
    o = build(s, "trash_bags", smooth_angle=75)
    finish("trash_bags", [o], "Haufen aus 4 zugeknoteten Muellsaecken (2 schwarz, grau, blau), ca. 1.2 x 0.9 m, "
           "0.55 m hoch. Glaenzende Folienmaterialien BagBlack/BagGrey/BagBlue.")


# ====================================================================== Kartons
def cardboard():
    mat("Cardboard", "#ffffff", 0.85, tex="cardboard.png")
    s = Soup()
    r = random.Random(7)
    z = 0.0
    for k in range(6):
        w = r.uniform(0.55, 0.95)
        d = r.uniform(0.38, 0.62)
        t = r.uniform(0.014, 0.03)
        u0 = r.uniform(0.0, 0.3)
        v0 = r.uniform(0.13, 0.30)
        uv = (u0, v0, u0 + 0.7, v0 + 0.69)
        if r.random() < 0.5:
            uv = (uv[2], uv[1], uv[0], uv[3])
        sl = slab(w, d, t, "Cardboard", uv, (0.0, 0.125))
        sl.rot((0, 0, 1), r.uniform(-25, 25)).move(r.uniform(-0.07, 0.07), r.uniform(-0.05, 0.05), z)
        s.add(sl)
        z += t
    # obersten Karton schraeg ueber die Kante gelegt
    sl = slab(0.80, 0.50, 0.02, "Cardboard", (0.25, 0.30, 0.95, 0.99), (0.0, 0.125))
    sl.rot((0, 1, 0), -7).rot((0, 0, 1), 35).move(0.12, 0.02, z + 0.035)
    s.add(sl)
    o = build(s, "cardboard", smooth_angle=30)
    finish("cardboard", [o], "Stapel aus 7 flachgelegten Kartons (Wellpappe-Textur mit Klebeband/Piktogrammen, "
           "kein Text), ca. 1.0 x 0.8 m, 0.2 m hoch.")


# ====================================================================== Sperrmuell
def _wood_chair():
    c = Soup()
    W = "Wood"
    for sx in (-1, 1):
        c.add(cbox(sx * 0.18, 0.17, 0.0, 0.035, 0.035, 0.44, W))
        c.add(cbox(sx * 0.18, -0.17, 0.0, 0.035, 0.035, 0.92, W))
        c.add(cbox(sx * 0.18, 0.0, 0.18, 0.02, 0.32, 0.03, W))
    c.add(cbox(0, 0.0, 0.44, 0.42, 0.42, 0.03, W))
    for z in (0.62, 0.84):
        c.add(cbox(0, -0.17, z, 0.33, 0.02, 0.07, W))
    return c


def bulky_waste():
    mat("Mattress", "#ffffff", 0.9, tex="mattress.png")
    mat("Wood", "#6e4b2f", 0.7)
    mat("Cardboard", "#ffffff", 0.85, tex="cardboard.png")
    s = Soup()
    mt = slab(1.9, 0.9, 0.16, "Mattress", (0.0, 0.25, 1.0, 1.0), (0.0, 0.25))
    # Matratze mit einem Ende auf einem flachen Karton abgelegt
    mt.rot((0, 1, 0), 4.8, (0.95, 0, 0)).rot((0, 0, 1), 6).move(-0.15, 0.0, 0.0)
    s.add(mt)
    s.add(cbox(-0.95, -0.05, 0.0, 0.42, 0.40, 0.16, "Cardboard").rot((0, 0, 1), 12, (-0.95, -0.05, 0)))
    ch = _wood_chair()
    ch.rot((0, 0, 1), 115).move(1.15, 0.35, 0)
    s.add(ch)
    bx = cbox(0, 0, 0, 0.50, 0.38, 0.34, "Cardboard")
    bx.rot((0, 1, 0), 4.8).rot((0, 0, 1), -18).move(0.35, -0.10, 0.195)
    s.add(bx)
    pl = cbox(0, 0, 0, 1.05, 0.20, 0.02, "Wood")
    pl.rot((0, 1, 0), 4.5).rot((0, 0, 1), 32).move(-0.45, 0.12, 0.265)
    s.add(pl)
    o = build(s, "bulky_waste", uvmode={"Cardboard": ("box", 1.4)}, smooth_angle=30)
    finish("bulky_waste", [o], "Kleiner Sperrmuellhaufen ca. 2.4 x 1.3 m: Matratze 1.9 x 0.9 m (Flecken), alter "
           "Holzstuhl, Karton, Brett. Liegt frei, kann an eine Hauswand gestellt werden.")


# ====================================================================== Bauzaun
def construction_fence():
    mat("FenceMesh", "#ffffff", 0.45, 0.6, tex="fence_mesh.png", clip=0.5, double=True)
    mat("Galv", "#9a9fa1", 0.4, 0.75)
    mat("FenceFoot", "#ffffff", 0.9, tex="concrete.png")
    mat("Inside", "#0c0c0c", 1.0)
    s = Soup()
    X = 1.70
    s.add(tube([(-X, 0, 0.20), (X, 0, 0.20), (X, 0, 2.0), (-X, 0, 2.0)], 0.02, 8, "Galv", closed_path=True,
               up=(0, 1, 0)))
    for sx in (-1, 1):
        s.add(tube([(sx * X, 0, 0.09), (sx * X, 0, 0.20)], 0.02, 8, "Galv", caps=False))
    # Gitter (Kachel 1 m, doppelseitig)
    x0, x1, z0, z1 = -X + 0.015, X - 0.015, 0.215, 1.985
    s.poly([(x0, 0, z0), (x1, 0, z0), (x1, 0, z1), (x0, 0, z1)], "FenceMesh",
           [(x0, z0), (x1, z0), (x1, z1), (x0, z1)])
    # Fuesse (an beiden Enden, x = +-1.75; Nachbarelement teilt den Fuss deckungsgleich)
    for sx in (-1, 1):
        cx = sx * 1.75
        s.add(loft([rect(0.70, 0.22, 0.0, cx), rect(0.70, 0.22, 0.10, cx), rect(0.62, 0.16, 0.14, cx)],
                   "FenceFoot"))
        for hx in (-0.05, 0.05):
            s.add(cyl(0.024, 0.002, 8, "Inside", z0=0.14, cx=cx + hx, cap0=False))
        # Schelle oben
        s.add(cbox(cx, 0, 1.86, 0.16, 0.05, 0.07, "Galv"))
    o = build(s, "construction_fence", uvmode={"FenceFoot": ("box", 2.0)}, smooth_angle=40)
    finish("construction_fence", [o], "Bauzaun-Element 3.5 m (Achsmass, entlang X, Ursprung Mitte), 2.0 m hoch, "
           "Rohrrahmen Galv + Gittermatte FenceMesh (Alpha-Scissor, doppelseitig, UV in Metern => 1 Kachel/m). "
           "Betonfuesse an beiden Enden x=+-1.75; beim Aneinanderreihen im 3.5-m-Raster liegen Fuesse/Schellen "
           "deckungsgleich uebereinander.")
