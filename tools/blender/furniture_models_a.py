"""Modelle Teil A: Tonnen, Container, Briefkasten, Verteilerkasten, Parkscheinautomat."""
import math
from furniture_lib import (V, Soup, mat, loft, lathe, cyl, box, cbox, tube, circle, rrect,
                           rect, build, finish, quad_uv, M_T, M_R, TAU)


def oquad(pts, m, out, uv=None):
    """Viereck, Normale zeigt in Richtung `out`."""
    s = Soup()
    pts = [V(p) for p in pts]
    n = (pts[1] - pts[0]).cross(pts[2] - pts[0])
    if n.dot(V(out)) < 0:
        pts = pts[::-1]
        uv = uv[::-1] if uv else uv
    s.poly(pts, m, list(uv) if uv else None)
    return s


def wheel_x(r, w, n, m, hub_m=None, hub_r=None):
    """Rad mit Achse X, Mitte im Ursprung."""
    s = cyl(r, w, n, m, z0=-w / 2)
    if hub_m:
        s.add(cyl(hub_r or r * 0.45, w * 1.12, 8, hub_m, z0=-w * 0.56))
    return s.rot((0, 1, 0), 90)


def prism_x(yz, x0, x1, m, mats=None, capm=None):
    """Prisma: Profil [(y, z), ...] entlang X von x0 bis x1 extrudiert."""
    rings = [[V((x, y, z)) for (y, z) in yz] for x in (x0, x1)]
    return loft(rings, m, capm=capm)


def arc_yz(cy, cz, R, a0, a1, n):
    """Kreisbogen in der YZ-Ebene, Winkel ab +Y gegen den Uhrzeigersinn (Grad)."""
    out = []
    for k in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * k / n)
        out.append((cy + math.cos(a) * R, cz + math.sin(a) * R))
    return out


# ====================================================================== Muelltonne 240 l
def bin_wheelie():
    mat("Paint", "#ffffff", 0.55)
    mat("Lid", "#2a2c2e", 0.5)
    mat("Rubber", "#1c1c1c", 0.9)
    mat("MetalDark", "#3a3c3e", 0.5, 0.6)
    s = Soup()
    s.add(loft([rrect(0.46, 0.55, 0.05, 3, 0.05, cy=0.01), rrect(0.48, 0.575, 0.05, 3, 0.09, cy=0.01),
                rrect(0.555, 0.665, 0.06, 3, 0.925), rrect(0.58, 0.70, 0.06, 3, 0.945),
                rrect(0.58, 0.70, 0.06, 3, 0.99)], "Paint"))
    # Deckel (leicht gewoelbt) + Griffleiste vorn
    s.add(loft([rrect(0.60, 0.735, 0.06, 3, 0.99, cy=0.006), rrect(0.60, 0.735, 0.06, 3, 1.02, cy=0.006),
                rrect(0.575, 0.70, 0.05, 3, 1.042, cy=0.006)], "Lid"))
    s.add(cbox(0, 0.375, 0.965, 0.26, 0.03, 0.05, "Lid"))
    # Scharnierband + Schiebegriff hinten
    s.add(cbox(0, -0.352, 0.89, 0.52, 0.03, 0.09, "Paint"))
    for sx in (-1, 1):
        s.add(cbox(sx * 0.215, -0.375, 0.955, 0.05, 0.05, 0.06, "Lid"))
    s.add(tube([(-0.26, -0.395, 1.0), (0.26, -0.395, 1.0)], 0.019, 8, "Lid"))
    # Raeder + Achse + Radkaesten
    for sx in (-1, 1):
        w = wheel_x(0.10, 0.05, 14, "Rubber", "MetalDark", 0.045)
        s.add(w.move(sx * 0.27, -0.30, 0.10))
        s.add(cbox(sx * 0.205, -0.29, 0.03, 0.07, 0.16, 0.16, "Paint"))
        s.add(cbox(sx * 0.17, 0.235, 0.0, 0.08, 0.07, 0.06, "Paint"))  # Fuesse vorn
    s.add(tube([(-0.29, -0.30, 0.10), (0.29, -0.30, 0.10)], 0.012, 6, "MetalDark"))
    # Verstaerkungsrippen vorn
    for sx in (-1, 1):
        s.add(cbox(sx * 0.12, 0.315, 0.55, 0.035, 0.03, 0.36, "Paint"))
    o = build(s, "bin_wheelie", smooth_angle=40)
    finish("bin_wheelie", [o], "Muelltonne 240 l (0.58 x 0.74 x 1.05 m). Korpus Material Paint (weiss, "
           "per Instanzfarbe einfaerben: grau=Rest, braun=Bio, gelb=Verpackung, blau=Papier), Deckel Lid dunkel. "
           "Deckelgriff/Einwurf vorn = +Y(Blender)=-Z(Godot), Raeder + Schiebegriff hinten.")


# ====================================================================== Glascontainer
def _glass_container(cm, tm):
    s = Soup()
    s.add(loft([rrect(1.34, 1.24, 0.10, 3, 0.08), rrect(1.44, 1.34, 0.12, 3, 1.32),
                rrect(1.40, 1.30, 0.14, 3, 1.40), rrect(1.02, 0.96, 0.22, 3, 1.53),
                rrect(0.98, 0.92, 0.21, 3, 1.555)], cm, mats=[cm, tm, tm, tm], capm=(tm, tm)))
    # Einwurfoeffnungen vorn und hinten (Gummimanschette)
    for sy in (1, -1):
        ring = cyl(0.12, 0.014, 16, "Rubber", z0=0.0, cap0=False)
        hole = cyl(0.082, 0.016, 12, "Inside", z0=0.0, cap0=False)
        for part in (ring, hole):
            part.rot((1, 0, 0), -90)
            if sy < 0:
                part.rot((0, 0, 1), 180)
            part.move(0, sy * 0.655, 1.12)
            s.add(part)
    # Kranpilz
    s.add(cyl(0.035, 0.12, 8, "MetalGalv", z0=1.55, cap0=False, cap1=False))
    s.add(lathe([(0.035, 1.665), (0.09, 1.675), (0.09, 1.695), (0.05, 1.715), (0.0, 1.72)], 10, "MetalGalv",
                cap0=True))
    # Fuesse
    for sx in (-1, 1):
        for sy in (-1, 1):
            s.add(cbox(sx * 0.54, sy * 0.48, 0.0, 0.12, 0.12, 0.09, "MetalGalv"))
    return s


def glass_containers():
    mat("Rubber", "#1a1a1a", 0.85)
    mat("Inside", "#070707", 1.0)
    mat("MetalGalv", "#7f8487", 0.45, 0.7)
    cols = [("GlassWhite", "glass_white.png", "#dde0da"), ("GlassGreen", "glass_green.png", "#2b6536"),
            ("GlassBrown", "glass_brown.png", "#5f3d25")]
    s = Soup()
    uvm = {}
    for k, (nm, tex, top) in enumerate(cols):
        mat(nm, "#ffffff", 0.55, tex=tex)
        mat(nm + "Top", top, 0.55)
        uvm[nm] = ("face01", 0.4)
        c = _glass_container(nm, nm + "Top")
        c.move((k - 1) * 1.55, 0, 0)
        s.add(c)
    o = build(s, "glass_containers", uvmode=uvm, smooth_angle=35)
    finish("glass_containers", [o], "Altglas-Standplatz: 3 Container 1.44 x 1.34 x 1.72 m nebeneinander entlang X "
           "(Weiss x=-1.55, Gruen x=0, Braun x=+1.55). Einwuerfe vorn +Y(Blender)=-Z(Godot) und hinten. "
           "Materialien Glass<Farbe> (Textur mit Schmutz + Flaschen-Piktogramm, kein Text) und Glass<Farbe>Top.")


# ====================================================================== Papiercontainer 1100 l
def paper_container():
    mat("PaperBlue", "#ffffff", 0.5, tex="paper_blue.png")
    mat("LidBlue", "#1d4b94", 0.45)
    mat("MetalGalv", "#7f8487", 0.45, 0.7)
    mat("Rubber", "#1a1a1a", 0.85)
    mat("Inside", "#070707", 1.0)
    s = Soup()
    s.add(loft([rrect(1.20, 0.92, 0.08, 3, 0.24), rrect(1.30, 1.02, 0.09, 3, 1.24)], "PaperBlue",
               capm=("LidBlue", "LidBlue")))
    s.add(loft([rrect(1.355, 1.075, 0.08, 3, 1.235), rrect(1.37, 1.09, 0.08, 3, 1.31)], "LidBlue"))
    # gewoelbter Deckel (Kreisbogen, Sehne 1.12 m, Stich 0.15 m)
    R, cz = 1.12, 1.31 + 0.15 - 1.12
    arc = []
    for k in range(11):
        a = math.radians(-30 + 60 * k / 10)
        arc.append((math.sin(a) * R, cz + math.cos(a) * R))
    s.add(prism_x(arc, -0.695, 0.695, "LidBlue"))
    # Einwurfschlitz vorn auf dem Deckel
    def pt(x, a, off=0.004):
        a = math.radians(a)
        return (x, math.sin(a) * (R + off), cz + math.cos(a) * (R + off))
    for a0, a1 in ((10, 14), (14, 18)):
        s.add(oquad([pt(-0.38, a0), pt(0.38, a0), pt(0.38, a1), pt(-0.38, a1)], "Inside", (0, 1, 1)))
    s.add(cbox(0, 0.555, 1.27, 1.0, 0.04, 0.05, "LidBlue"))  # Griffleiste
    s.add(cbox(0, 0.52, 1.10, 1.2, 0.04, 0.08, "LidBlue"))   # Kammleiste
    # Zapfen seitlich
    for sx in (-1, 1):
        z = cyl(0.04, 0.075, 10, "MetalGalv", z0=0.0, cap0=False)
        z.rot((0, 1, 0), 90 * sx)
        z.move(sx * 0.635, 0, 1.08)
        s.add(z)
    # Lenkrollen
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * 0.50, sy * 0.36
            s.add(cbox(x, y, 0.20, 0.13, 0.13, 0.04, "MetalGalv"))
            for f in (-1, 1):
                s.add(cbox(x + f * 0.035, y, 0.07, 0.008, 0.09, 0.13, "MetalGalv"))
            s.add(wheel_x(0.10, 0.05, 14, "Rubber", "MetalGalv", 0.035).move(x, y, 0.10))
    o = build(s, "paper_container", uvmode={"PaperBlue": ("face01", 0.4)}, smooth_angle=35)
    finish("paper_container", [o], "Blauer 1100-l-Papiercontainer 1.37 x 1.09 x 1.46 m, gewoelbter Deckel mit "
           "Einwurfschlitz vorn +Y(Blender)=-Z(Godot), 4 Lenkrollen, seitliche Schuettzapfen. "
           "PaperBlue = Textur (Zeitungs-Piktogramm, Schmutz).")


# ====================================================================== Briefkasten
def post_box():
    mat("PostYellow", "#ffcc00", 0.4)
    mat("PostDark", "#232323", 0.7)
    mat("PostPole", "#3d4144", 0.5, 0.4)
    mat("PostPlate", "#ffffff", 0.4, tex="postbox_plate.png")
    s = Soup()
    s.add(box(-0.22, -0.14, 0.80, 0.22, 0.14, 1.30, "PostYellow", skip=("pz",)))
    # gewoelbtes Dach mit kleinem Ueberstand
    R = (0.15 ** 2 + 0.07 ** 2) / (2 * 0.07)
    cz = 1.295 + 0.07 - R
    arc = []
    for k in range(9):
        a = math.asin(0.15 / R)
        t = -a + 2 * a * k / 8
        arc.append((math.sin(t) * R, cz + math.cos(t) * R))
    s.add(prism_x(arc, -0.23, 0.23, "PostYellow"))
    # Einwurf: Schlitz + Klappe darueber
    s.add(oquad([(0.15, 0.1405, 1.15), (-0.15, 0.1405, 1.15), (-0.15, 0.1405, 1.185), (0.15, 0.1405, 1.185)],
                "PostDark", (0, 1, 0)))
    s.add(prism_x([(0.14, 1.185), (0.18, 1.19), (0.175, 1.215), (0.14, 1.25)], -0.17, 0.17, "PostYellow"))
    # Leerungstafel (UV 0..1, Blick von vorn: links = +X)
    s.add(oquad([(0.11, 0.1408, 0.95), (-0.11, 0.1408, 0.95), (-0.11, 0.1408, 1.10), (0.11, 0.1408, 1.10)],
                "PostPlate", (0, 1, 0), uv=[(0, 0), (1, 0), (1, 1), (0, 1)]))
    # Schloss
    lk = cyl(0.014, 0.01, 8, "PostDark", z0=0.0, cap0=False)
    lk.rot((1, 0, 0), -90).move(0.16, 0.14, 0.86)
    s.add(lk)
    # Saeule
    s.add(cyl(0.08, 0.015, 14, "PostPole"))
    s.add(cyl(0.045, 0.79, 12, "PostPole", z0=0.015, cap0=False, cap1=False))
    s.add(cbox(0, 0, 0.76, 0.13, 0.13, 0.04, "PostPole"))
    o = build(s, "post_box", smooth_angle=35)
    finish("post_box", [o], "Gelber Briefkasten (ohne Logo) auf Saeule, 1.37 m. Einwurfschlitz + Leerungstafel "
           "(PostPlate, UV 0..1) vorn +Y(Blender)=-Z(Godot).")


# ====================================================================== Verteilerkasten
def street_cabinet():
    mat("Cabinet", "#ffffff", 0.6, tex="cabinet_grey.png")
    mat("CabinetRoof", "#a9aba6", 0.6)
    mat("Concrete", "#ffffff", 0.9, tex="concrete.png")
    s = Soup()
    W, D, z0, z1 = 1.2, 0.4, 0.08, 1.25
    x, y = W / 2, D / 2
    faces = [  # (Punkte von links nach rechts von aussen gesehen), u-Bereich
        ([(x, y), (-x, y)], (0.0, 0.375)),
        ([(-x, y), (-x, -y)], (0.375, 0.5)),
        ([(-x, -y), (x, -y)], (0.5, 0.875)),
        ([(x, -y), (x, y)], (0.875, 1.0)),
    ]
    for (a, b), (u0, u1) in faces:
        s.poly([(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)], "Cabinet",
               [(u0, 0), (u1, 0), (u1, 1), (u0, 1)])
    # Dach mit Ueberstand und leichter Fase
    s.add(loft([rect(1.24, 0.44, 1.25), rect(1.24, 0.44, 1.29), rect(1.20, 0.40, 1.31)], "CabinetRoof"))
    # Sockel
    s.add(box(-0.59, -0.19, 0.0, 0.59, 0.19, 0.08, "Concrete", skip=("nz", "pz")))
    # Tuergriffe (Hebel) und Scharniere
    mat("MetalDark", "#3a3c3e", 0.5, 0.6)
    for gx in (0.06, -0.06):
        s.add(cbox(gx, 0.207, 0.60, 0.022, 0.014, 0.14, "MetalDark"))
    for hx in (0.575, -0.575):
        for hz in (0.25, 1.05):
            s.add(cbox(hx, 0.204, hz, 0.02, 0.01, 0.08, "MetalDark"))
    o = build(s, "street_cabinet", uvmode={"Concrete": ("box", 1.5)}, smooth_angle=30)
    finish("street_cabinet", [o], "Grauer Kabelverteilerschrank 1.24 x 0.44 x 1.31 m, Tueren (Fugen/Schloesser in "
           "Textur) vorn +Y(Blender)=-Z(Godot), Lueftungsschlitze seitlich, leichte Verschmutzung, Aufkleberreste, "
           "kleines Tag. Cabinet = Umfangs-Abwicklung (Front u 0..0.375).")


# ====================================================================== Parkscheinautomat
def parking_meter():
    mat("MeterBody", "#8d9296", 0.4, 0.55)
    mat("MeterFace", "#ffffff", 0.45, tex="meter_face.png")
    mat("MetalDark", "#2e3032", 0.55, 0.5)
    mat("Solar", "#16213b", 0.18, 0.3)
    s = Soup()
    x, y = 0.17, 0.13
    zf0, zf1 = 0.80, 1.54
    # Korpus ohne Front-Oberteil
    s.add(box(-x, -y, 0.06, x, y, 1.56, "MeterBody", skip=("py", "nz")))
    s.add(oquad([(x, y, 0.06), (-x, y, 0.06), (-x, y, zf0), (x, y, zf0)], "MeterBody", (0, 1, 0)))
    s.add(oquad([(x, y, zf0), (-x, y, zf0), (-x, y, zf1), (x, y, zf1)], "MeterFace", (0, 1, 0),
                uv=[(0, 0), (1, 0), (1, 1), (0, 1)]))
    s.add(oquad([(x, y, zf1), (-x, y, zf1), (-x, y, 1.56), (x, y, 1.56)], "MeterBody", (0, 1, 0)))
    # Regenschutz ueber dem Bedienfeld, Dach, Solarmodul
    s.add(cbox(0, 0.02, 1.56, 0.38, 0.34, 0.035, "MeterBody"))
    sol = cbox(0, 0, -0.01, 0.32, 0.24, 0.02, "MetalDark", mats={"pz": "Solar"})
    sol.rot((1, 0, 0), -18).move(0, -0.005, 1.635)
    s.add(sol)
    s.add(prism_x([(-0.115, 1.595), (0.11, 1.595), (-0.115, 1.66)], -0.14, 0.14, "MeterBody"))
    # Sockel
    s.add(cbox(0, 0, 0.0, 0.40, 0.32, 0.06, "MetalDark"))
    o = build(s, "parking_meter", smooth_angle=30)
    finish("parking_meter", [o], "Parkscheinautomat 1.67 m (silbergrau, blaues P-Band, Display, Tasten, Muenz-/"
           "Kartenschlitz, Infotafel, Ticketausgabe - alles in MeterFace-Textur, kein Herstellerlogo), "
           "Solarmodul oben. Bedienseite +Y(Blender)=-Z(Godot).")
