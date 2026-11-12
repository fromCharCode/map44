"""Modelle Teil B: Cafe-Moebel, Aufsteller, Pflanzkuebel, Fahrrad, E-Scooter."""
import math
from mathutils import Matrix
from furniture_lib import (V, Soup, mat, loft, lathe, cyl, box, cbox, tube, circle, rrect,
                           rect, build, finish, quad_uv, grid_sphere, TAU)
from furniture_models_a import oquad, wheel_x


def pnoise(p, seed=0.0):
    x, y, z = p
    return (math.sin(x * 7.1 + seed * 1.7) * math.cos(y * 6.3 - seed)
            + 0.6 * math.sin(z * 8.7 + x * 3.3 + seed * 2.3)
            + 0.35 * math.sin((x - y + z) * 13.0 + seed)) / 1.95


# ====================================================================== Cafe
def _bistro_chair():
    c = Soup()
    hs = 0.45
    for sx in (-1, 1):
        c.add(tube([(sx * 0.19, 0.185, 0.0), (sx * 0.19, 0.175, hs - 0.02)], 0.012, 6, "Alu"))
        c.add(tube([(sx * 0.19, -0.20, 0.0), (sx * 0.19, -0.185, hs - 0.02), (sx * 0.18, -0.245, 0.87)],
                   0.012, 6, "Alu"))
        c.add(tube([(sx * 0.19, 0.175, 0.17), (sx * 0.19, -0.19, 0.17)], 0.008, 4, "Alu", caps=False))
    c.add(tube([(-0.18, -0.245, 0.87), (0.18, -0.245, 0.87)], 0.011, 6, "Alu", caps=False))
    c.add(tube([(-0.19, 0.18, 0.12), (0.19, 0.18, 0.12)], 0.008, 4, "Alu", caps=False))
    c.add(box(-0.205, -0.20, hs - 0.025, 0.205, 0.205, hs + 0.01, "Alu", mats={"pz": "Rattan"}))
    back = box(-0.18, -0.01, 0.0, 0.18, 0.01, 0.25, "Rattan")
    back.rot((1, 0, 0), 8.3).move(0, -0.205, 0.59)
    c.add(back)
    return c


def cafe_set():
    mat("Alu", "#b9bdc1", 0.35, 0.85)
    mat("MetalDark", "#2e3033", 0.5, 0.6)
    mat("Rattan", "#ffffff", 0.75, tex="rattan.png")
    mat("TableTop", "#cfccc4", 0.35)
    s = Soup()
    s.add(lathe([(0.30, 0.722), (0.30, 0.75)], 24, "Alu", capm=("Alu", "TableTop")))
    s.add(cyl(0.028, 0.67, 8, "Alu", z0=0.055, cap0=False, cap1=False))
    s.add(lathe([(0.22, 0.0), (0.22, 0.018), (0.13, 0.035), (0.04, 0.065), (0.04, 0.07)], 16, "MetalDark",
                cap0=False))
    for x, ang in ((0.58, 90 + 7), (-0.60, -90 - 5)):
        ch = _bistro_chair()
        ch.rot((0, 0, 1), ang).move(x, 0.03 if x > 0 else -0.04, 0)
        s.add(ch)
    o = build(s, "cafe_set", uvmode={"Rattan": ("box", 3.0)}, smooth_angle=40)
    finish("cafe_set", [o], "Runder Bistrotisch d=0.6 m, h=0.75 m (TableTop + Alu) mit 2 Bistrostuehlen "
           "(Alu-Rohr, Polyrattan-Sitz) links/rechts entlang X, zur Tischmitte gedreht.")


def cafe_parasol():
    mat("Paint", "#ffffff", 0.8, double=True)
    mat("Alu", "#b9bdc1", 0.35, 0.85)
    mat("MetalDark", "#2e3033", 0.55, 0.5)
    s = Soup()
    R, n = 1.25, 8
    prof = [(R, 2.20), (0.72, 2.43), (0.14, 2.585)]

    def ring(r, z, sag):
        pts = []
        for k in range(2 * n):
            a = TAU * k / (2 * n)
            if k % 2:
                rr = r * math.cos(math.pi / n) * 0.99
                pts.append(V((math.cos(a) * rr, math.sin(a) * rr, z - sag)))
            else:
                pts.append(V((math.cos(a) * r, math.sin(a) * r, z)))
        return pts
    rings = [ring(r, z, 0.035 * r) for r, z in prof] + [[V((0, 0, 2.62))] * (2 * n)]
    s.add(loft(rings, "Paint", cap0=False, cap1=False, orient=V((0, 0, 1))))
    # Volant
    rim = ring(R, 2.20, 0.035 * R)
    low = [V((p.x, p.y, p.z - 0.13)) for p in rim]
    s.add(loft([low, rim], "Paint", cap0=False, cap1=False, orient=V((0, 0, 1))))
    # Streben
    for k in range(n):
        a = TAU * k / n
        ca, sa = math.cos(a), math.sin(a)
        pts = [(ca * 0.10, sa * 0.10, 2.585), (ca * 0.72, sa * 0.72, 2.418), (ca * 1.22, sa * 1.22, 2.19)]
        s.add(tube(pts, 0.008, 4, "Alu", caps=False))
        s.add(tube([(ca * 0.03, sa * 0.03, 2.03), (ca * 0.62, sa * 0.62, 2.44)], 0.006, 4, "Alu", caps=False))
    s.add(cyl(0.024, 2.60, 8, "Alu", z0=0.06, cap0=False))
    s.add(cyl(0.036, 0.08, 8, "Alu", z0=1.99))
    s.add(lathe([(0.035, 2.62), (0.035, 2.66), (0.0, 2.69)], 8, "Alu", cap0=True))
    # Schirmstaender
    s.add(loft([rrect(0.52, 0.52, 0.04, 2, 0.0), rrect(0.52, 0.52, 0.04, 2, 0.05),
                rrect(0.40, 0.40, 0.04, 2, 0.07)], "MetalDark"))
    s.add(cyl(0.045, 0.28, 8, "MetalDark", z0=0.07, cap0=False))
    o = build(s, "cafe_parasol", smooth_angle=50)
    finish("cafe_parasol", [o], "Sonnenschirm d=2.5 m, Hoehe 2.69 m, 8 Streben, Bespannung + Volant Material Paint "
           "(weiss, doppelseitig, per Instanzfarbe einfaerben), Stahlfuss 0.52 x 0.52 m. Unterkante Volant 2.03 m.")


# ====================================================================== Kundenstopper
def sandwich_board():
    mat("Alu", "#b9bdc1", 0.35, 0.85)
    mat("Poster", "#ffffff", 0.45)
    mat("BoardBack", "#d9d9d6", 0.6)
    s = Soup()
    L = 1.0
    th = math.asin(0.29 / L)

    def panel():
        p = Soup()
        W, F = 0.64, 0.035
        # Rahmen (vier Profile) in der XZ-Ebene, Oberkante bei z=0, nach unten bis -L
        p.add(box(-W / 2, -0.012, -L, -W / 2 + F, 0.012, 0, "Alu"))
        p.add(box(W / 2 - F, -0.012, -L, W / 2, 0.012, 0, "Alu"))
        p.add(box(-W / 2 + F, -0.012, -F, W / 2 - F, 0.012, 0, "Alu"))
        p.add(box(-W / 2 + F, -0.012, -L + 0.06, W / 2 - F, 0.012, -L + 0.06 + F, "Alu"))
        x0, x1, z0, z1 = W / 2 - F, -W / 2 + F, -L + 0.06 + F, -F
        p.add(oquad([(x0, 0.006, z0), (x1, 0.006, z0), (x1, 0.006, z1), (x0, 0.006, z1)], "Poster", (0, 1, 0),
                    uv=[(0, 0), (1, 0), (1, 1), (0, 1)]))
        p.add(oquad([(x0, -0.006, z0), (x1, -0.006, z0), (x1, -0.006, z1), (x0, -0.006, z1)], "BoardBack",
                    (0, -1, 0)))
        p.rot((1, 0, 0), math.degrees(th))
        p.move(0, 0, L * math.cos(th))
        return p
    s.add(panel())
    s.add(panel().rot((0, 0, 1), 180))
    s.add(tube([(-0.30, 0, L * math.cos(th) + 0.01), (0.30, 0, L * math.cos(th) + 0.01)], 0.012, 6, "Alu"))
    o = build(s, "sandwich_board", smooth_angle=30)
    finish("sandwich_board", [o], "Kundenstopper/A-Aufsteller 0.64 m breit, 0.97 m hoch, Fussabstand 0.58 m. "
           "Zwei Plakatflaechen Material Poster (UV 0..1, aufrecht lesbar) vorn +Y(Blender)=-Z(Godot) und hinten "
           "-Y (gleiche UV), Rahmen Alu.")


# ====================================================================== Pflanzkuebel
def planter():
    mat("Concrete", "#ffffff", 0.9, tex="concrete.png")
    mat("Soil", "#3a2a1e", 1.0)
    mat("Foliage", "#ffffff", 0.8, tex="foliage.png")
    mat("Flowers", "#ffffff", 0.8, tex="flowers.png")
    s = Soup()
    s.add(loft([rrect(0.74, 0.74, 0.04, 2, 0.0), rrect(0.80, 0.80, 0.04, 2, 0.58),
                rrect(0.80, 0.80, 0.04, 2, 0.60), rrect(0.70, 0.70, 0.03, 2, 0.60),
                rrect(0.68, 0.68, 0.03, 2, 0.53)], "Concrete", capm=("Concrete", "Soil")))
    bush = grid_sphere(0.28, 14, 9, "Foliage")

    def wb(p, seed=1.0, sz=0.82):
        k = 1 + 0.10 * pnoise(p * 4, seed)
        q = V((p.x * k, p.y * k, p.z * k * sz))
        return q
    bush.warp(lambda p: wb(p)).move(0, 0, 0.75)
    s.add(bush)
    # Blumenkranz zwischen Kugel und Kuebelrand
    fl = loft([rrect(0.68, 0.68, 0.10, 3, 0.53), rrect(0.65, 0.65, 0.12, 3, 0.60),
               rrect(0.52, 0.52, 0.16, 3, 0.66), rrect(0.30, 0.30, 0.12, 3, 0.64)], "Flowers",
              cap0=False, cap1=False)
    fl.warp(lambda p: V((p.x, p.y, p.z + (0.025 * pnoise(p * 9, 7.0) if p.z > 0.55 else 0.0))))
    s.add(fl)
    o = build(s, "planter", uvmode={"Concrete": ("box", 1.5), "Foliage": ("box", 2.5),
                                    "Flowers": ("box", 4.0)}, smooth_angle=70)
    finish("planter", [o], "Pflanzkuebel 0.8 x 0.8 x 0.6 m (Waschbeton) mit Buchsbaum-Kugel (Foliage) und "
           "Blumenkranz (Flowers) ringsum, Gesamthoehe ~1.0 m.")


# ====================================================================== Fahrrad
def _torus_x(R, r, nu, nv, m, cy, cz):
    path = [(0, cy + math.cos(TAU * i / nu) * R, cz + math.sin(TAU * i / nu) * R) for i in range(nu)]
    return tube(path, r, nv, m, closed_path=True, up=(1, 0, 0))


def _arc_path(cy, cz, R, a0, a1, n, x=0.0):
    return [(x, cy + math.cos(math.radians(a0 + (a1 - a0) * k / n)) * R,
             cz + math.sin(math.radians(a0 + (a1 - a0) * k / n)) * R) for k in range(n + 1)]


def _bike_wheel(cy, cz, s):
    s.add(_torus_x(0.335, 0.021, 24, 6, "Tire", cy, cz))
    rim_prof = [(-1, -0.6), (1, -0.6), (1, 0.6), (-1, 0.6)]
    s.add(tube([(0, cy + math.cos(TAU * i / 24) * 0.31, cz + math.sin(TAU * i / 24) * 0.31) for i in range(24)],
               0.012, 4, "Rim", closed_path=True, up=(1, 0, 0), prof=rim_prof))
    Rs = 0.30
    s.add(oquad([(0, cy - Rs, cz - Rs), (0, cy + Rs, cz - Rs), (0, cy + Rs, cz + Rs), (0, cy - Rs, cz + Rs)],
                "Spokes", (1, 0, 0), uv=[(0, 0), (1, 0), (1, 1), (0, 1)]))
    s.add(tube([(-0.05, cy, cz), (0.05, cy, cz)], 0.022, 8, "Rim"))


def bicycle():
    mat("Paint", "#ffffff", 0.35, 0.3)
    mat("Tire", "#1d1d1d", 0.85)
    mat("Rim", "#b8bcc0", 0.3, 0.85)
    mat("Spokes", "#ffffff", 0.35, 0.8, tex="spokes.png", clip=0.5, double=True)
    mat("MetalDark", "#2a2b2d", 0.5, 0.6)
    mat("Saddle", "#2b2522", 0.6)
    mat("Rubber", "#1a1a1a", 0.9)
    mat("Fender", "#c0c3c6", 0.3, 0.8)
    mat("Lamp", "#e8e8e0", 0.2, emit=None)
    mat("RearRed", "#b0141a", 0.3)
    s = Soup()
    zA = 0.356
    RA, FA = (-0.53, zA), (0.55, zA)
    BB = (-0.10, 0.29)
    _bike_wheel(RA[0], RA[1], s)
    _bike_wheel(FA[0], FA[1], s)
    # Lenkachse (70 Grad), Gabel mit 45 mm Vorlauf
    u = V((0, -math.cos(math.radians(70)), math.sin(math.radians(70))))
    nf = V((0, u.z, -u.y))
    Q = V((0, FA[0], FA[1])) - nf * 0.045
    crown = Q + u * 0.40
    ht_b, ht_t, st_t = Q + u * 0.42, Q + u * 0.57, Q + u * 0.66

    def P(y, z, x=0.0):
        return (x, y, z)
    T = "Paint"
    s.add(tube([tuple(ht_b), tuple(ht_t)], 0.022, 8, T))                       # Steuerrohr
    s.add(tube([P(-0.255, 0.80), tuple(ht_t - u * 0.03)], 0.017, 6, T))       # Oberrohr
    s.add(tube([P(*BB), tuple(ht_b + u * 0.01)], 0.02, 6, T))                 # Unterrohr
    s.add(tube([P(*BB), P(-0.27, 0.84)], 0.017, 6, T))                        # Sitzrohr
    for sx in (-1, 1):
        s.add(tube([P(BB[0], BB[1], sx * 0.025), P(RA[0], RA[1], sx * 0.06)], 0.011, 6, T))   # Kettenstreben
        s.add(tube([P(-0.255, 0.80, sx * 0.022), P(RA[0], RA[1], sx * 0.06)], 0.010, 6, T))   # Sitzstreben
        mid = Q + u * 0.2 + nf * 0.02
        s.add(tube([tuple(crown + V((sx * 0.045, 0, 0))), tuple(mid + V((sx * 0.05, 0, 0))),
                    (sx * 0.05, FA[0], FA[1])], 0.011, 6, T))                 # Gabelscheiden
    s.add(tube([tuple(crown + V((-0.05, 0, 0))), tuple(crown + V((0.05, 0, 0)))], 0.016, 6, T))
    s.add(tube([P(BB[0], BB[1], -0.04), P(BB[0], BB[1], 0.04)], 0.022, 8, T))  # Tretlager
    # Vorbau + Lenker
    stem_end = (0, 0.345, 0.985)
    s.add(tube([tuple(ht_t), tuple(st_t), stem_end], 0.014, 6, "MetalDark"))
    bar = [(-0.29, 0.22, 1.0), (-0.25, 0.30, 1.0), (-0.12, 0.345, 0.985), (0.12, 0.345, 0.985),
           (0.25, 0.30, 1.0), (0.29, 0.22, 1.0)]
    s.add(tube(bar, 0.011, 6, "MetalDark"))
    for sx in (-1, 1):
        s.add(tube([(sx * 0.293, 0.212, 1.0), (sx * 0.262, 0.275, 1.0)], 0.017, 6, "Rubber"))
    # Sattelstuetze + Sattel
    s.add(tube([P(-0.27, 0.84), P(-0.295, 0.94)], 0.013, 6, "MetalDark"))
    sad = [(0.0, -0.44), (0.085, -0.43), (0.08, -0.36), (0.035, -0.24), (0.025, -0.17),
           (-0.025, -0.17), (-0.035, -0.24), (-0.08, -0.36), (-0.085, -0.43)]
    s.add(loft([[V((x, y, 0.94)) for x, y in sad], [V((x * 1.03, y, 0.975)) for x, y in sad],
                [V((x * 0.9, y, 0.99)) for x, y in sad]], "Saddle"))
    # Schutzbleche
    fprof = [(0.0, -1.0), (0.12, -1.0), (0.12, 1.0), (0.0, 1.0)]
    s.add(tube(_arc_path(FA[0], FA[1], 0.372, -15, 165, 10), 0.03, 4, "Fender", up=(1, 0, 0), prof=fprof))
    s.add(tube(_arc_path(RA[0], RA[1], 0.372, 30, 195, 10), 0.03, 4, "Fender", up=(1, 0, 0), prof=fprof))
    # Gepaecktraeger
    for sx in (-1, 1):
        x = sx * 0.07
        s.add(tube([(x, -0.29, 0.79), (x, -0.80, 0.79), (sx * 0.064, RA[0] - 0.02, RA[1] + 0.02)], 0.006, 4,
                   "MetalDark", caps=False))
        s.add(tube([(x, -0.62, 0.79), (sx * 0.064, RA[0] - 0.01, RA[1] + 0.03)], 0.005, 4, "MetalDark",
                   caps=False))
        s.add(tube([(x, -0.29, 0.79), (sx * 0.024, -0.262, 0.77)], 0.005, 4, "MetalDark", caps=False))
    for y in (-0.36, -0.55, -0.79):
        s.add(tube([(-0.07, y, 0.79), (0.07, y, 0.79)], 0.005, 4, "MetalDark", caps=False))
    s.add(cbox(0, -0.81, 0.755, 0.08, 0.02, 0.03, "RearRed"))
    # Licht vorn
    lamp = cyl(0.028, 0.06, 8, "Lamp", z0=0.0)
    lamp.rot((1, 0, 0), -90).move(0, crown.y + 0.03, crown.z + 0.0)
    s.add(lamp)
    # Antrieb: Kettenblatt, Ritzel, Kette, Kurbeln, Pedale
    for part, r_, y_, z_ in ((0.095, 0.095, BB[0], BB[1]), (0.04, 0.04, RA[0], RA[1])):
        d = cyl(r_, 0.004, 16 if r_ > 0.05 else 10, "MetalDark", z0=-0.002)
        d.rot((0, 1, 0), 90).move(0.07, y_, z_)
        s.add(d)
    chain = []
    for k in range(8):
        a = math.radians(90 - 180 * k / 7)
        chain.append((0.072, BB[0] + math.cos(a) * 0.097, BB[1] + math.sin(a) * 0.097))
    for k in range(6):
        a = math.radians(-90 - 180 * k / 5)
        chain.append((0.072, RA[0] + math.cos(a) * 0.042, RA[1] + math.sin(a) * 0.042))
    s.add(tube(chain, 0.004, 4, "MetalDark", closed_path=True, up=(1, 0, 0)))
    for sx, dy in ((1, 0.165), (-1, -0.165)):
        ce = (sx * 0.09, BB[0] + dy, BB[1] - 0.02)
        s.add(tube([(sx * 0.08, BB[0], BB[1]), ce], 0.01, 4, "MetalDark"))
        s.add(cbox(sx * 0.135, BB[0] + dy, BB[1] - 0.035, 0.09, 0.06, 0.025, "Rubber"))
    # Seitenstaender links + Schraeglage
    lean = -7.0
    Ry = Matrix.Rotation(math.radians(lean), 4, "Y")
    A = V((-0.045, -0.17, 0.275))
    A2 = Ry @ A
    F2 = V((A2.x - 0.11, A2.y - 0.07, 0.005))
    F = Ry.inverted() @ F2
    s.add(tube([tuple(A), tuple(F)], 0.009, 6, "MetalDark"))
    s.xf(Ry)
    o = build(s, "bicycle", smooth_angle=40)
    finish("bicycle", [o], "Abgestelltes Citybike (28 Zoll, Schutzbleche, Gepaecktraeger) auf Seitenstaender, "
           "7 Grad nach links (-X) geneigt. Fahrtrichtung/Vorderrad +Y(Blender)=-Z(Godot), Laenge 1.8 m. "
           "Rahmen + Gabel Material Paint (weiss, einfaerben). Speichen = Alpha-Scissor-Textur (Spokes, doppelseitig).",
           views=((70, 15), (250, 25)))


# ====================================================================== E-Scooter
def e_scooter():
    mat("Paint", "#ffffff", 0.35, 0.2)
    mat("Deck", "#1b1b1b", 0.9)
    mat("Tire", "#1d1d1d", 0.85)
    mat("MetalDark", "#2a2b2d", 0.5, 0.6)
    mat("Rubber", "#1a1a1a", 0.9)
    mat("Lamp", "#e8e8e0", 0.2)
    mat("RearRed", "#b0141a", 0.3)
    mat("Display", "#0c0f12", 0.15)
    s = Soup()
    zr = 0.125
    FA, RA = (0.40, zr), (-0.47, zr)
    for cy_, cz_ in (FA, RA):
        s.add(_torus_x(0.105, 0.021, 18, 6, "Tire", cy_, cz_))
        hub = cyl(0.086, 0.044, 14, "MetalDark", z0=-0.022)
        hub.rot((0, 1, 0), 90).move(0, cy_, cz_)
        s.add(hub)
    # Trittbrett
    s.add(loft([rrect(0.17, 0.74, 0.035, 2, 0.085, cy=-0.04), rrect(0.17, 0.74, 0.035, 2, 0.155, cy=-0.04)],
               "Paint", capm=("Paint", "Deck")))
    s.add(loft([rrect(0.12, 0.10, 0.02, 2, 0.09, cy=0.34), rrect(0.08, 0.08, 0.02, 2, 0.32, cy=0.385)], "Paint"))
    # Heck: Schutzblech + Ruecklicht
    fprof = [(0.0, -1.0), (0.1, -1.0), (0.1, 1.0), (0.0, 1.0)]
    s.add(tube(_arc_path(RA[0], RA[1], 0.145, 25, 175, 7), 0.035, 4, "Paint", up=(1, 0, 0), prof=fprof))
    s.add(cbox(0, -0.615, 0.12, 0.06, 0.02, 0.025, "RearRed"))
    # Gabel vorn + Schutzblech
    for sx in (-1, 1):
        s.add(tube([(sx * 0.038, 0.37, 0.33), (sx * 0.038, FA[0], FA[1])], 0.012, 6, "Paint"))
    s.add(tube(_arc_path(FA[0], FA[1], 0.145, 30, 150, 6), 0.03, 4, "Paint", up=(1, 0, 0), prof=fprof))
    # Lenkstange, Gelenk, Lenker, Display, Licht
    s.add(tube([(0, 0.385, 0.30), (0, 0.30, 1.07)], 0.025, 8, "Paint"))
    s.add(tube([(-0.035, 0.375, 0.38), (0.035, 0.375, 0.38)], 0.032, 8, "MetalDark"))
    s.add(tube([(-0.25, 0.297, 1.10), (0.25, 0.297, 1.10)], 0.014, 6, "MetalDark"))
    for sx in (-1, 1):
        s.add(tube([(sx * 0.17, 0.297, 1.10), (sx * 0.255, 0.297, 1.10)], 0.019, 6, "Rubber"))
        s.add(tube([(sx * 0.12, 0.31, 1.105), (sx * 0.19, 0.36, 1.09)], 0.005, 4, "MetalDark"))
    s.add(cbox(0, 0.30, 1.075, 0.12, 0.08, 0.05, "Paint", mats={"pz": "Display"}))
    lamp = cyl(0.025, 0.03, 8, "Lamp", z0=0.0)
    lamp.rot((1, 0, 0), -90).move(0, 0.325, 0.95)
    s.add(lamp)
    # Seitenstaender links + Schraeglage
    lean = -6.0
    Ry = Matrix.Rotation(math.radians(lean), 4, "Y")
    A = V((-0.07, -0.02, 0.095))
    A2 = Ry @ A
    F2 = V((A2.x - 0.10, A2.y - 0.05, 0.004))
    F = Ry.inverted() @ F2
    s.add(tube([tuple(A), tuple(F)], 0.008, 6, "MetalDark"))
    s.xf(Ry)
    o = build(s, "e_scooter", smooth_angle=40)
    finish("e_scooter", [o], "Leih-E-Scooter auf Seitenstaender (6 Grad nach links geneigt), ohne Logo. "
           "Fahrtrichtung +Y(Blender)=-Z(Godot), Laenge 1.12 m, Lenker 1.12 m hoch. Korpus Material Paint "
           "(Betreiberfarbe per Instanz), Trittflaeche Deck schwarz.", views=((70, 15), (250, 25)))
