"""Blaues Wunder (Loschwitzer Brücke, Dresden, 1891-93, Claus Koepcke) - prozeduraler Stahlüberbau.

Versteifte Hängebrücke / Hängefachwerk mit 3 Gelenken ohne Strompfeiler: je Hauptträger vier dreieckige
Fachwerkwände; die Pylone (senkrechte Dreieckskanten, Gitterstützen mit vorgesetzter Wendeltreppe und
Türmchen) stehen auf Sandsteinpfeilern an den Ufern, Mittelgelenk in Feldmitte, Gehwege (seit 1935) außen
auf Konsolen. Maße: Mittelöffnung 146,68 m, Fahrbahn 10,20 m (de.wikipedia); Obergurtverlauf, Pylonhöhe,
Trägerabstand und Gehwegbreiten aus GeoSN-DOM1 (dl-de/by-2.0) gemessen (siehe blaues_wunder.json "notes").

Koordinaten (Blender): X quer (+X = oberstrom/SO), Y längs (+Y = Loschwitz/NO, wird Godot -Z), Z oben.
Ursprung = Brückenmitte (Mittelgelenk) auf Fahrbahnoberkante. Fahrbahn selbst ist NICHT enthalten (Spiel nutzt
LoD2-Deck); Gehwegbeläge, Geländer, Leuchten, Pfeiler, Treppen und Türmchen sind enthalten.

Materialien: BridgeSteelBlue, BridgeRail, BridgeStone, BridgeWood, BridgeGlass, BridgeDark, BridgeLampGlass
(leuchtend), BridgeMesh (halbtransparent, Treppenkäfig).
Leerknoten LampLight_### an jeder Laterne (für Punktlichter im Spiel).

Aufruf: flatpak run --filesystem=host org.blender.Blender -b --python build_blaues_wunder.py -- <out.glb>
Keine fremden Modelle/Texturen.
"""
import bpy, sys, math
from mathutils import Vector

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = ARGS[0] if ARGS else "blaues_wunder.glb"

# ------------------------------------------------------------------------------------------------ Maße
XT = 6.18                 # halber Hauptträgerabstand (Trägerachsen bei ±6,18 m; DOM1: -6,0 / +6,35)
YP = 73.34                # Pylonachse = halbe Mittelöffnung (146,68 m)
PC = 73.34 / 12.0         # Feldweite Mittelöffnung (12 Felder je Hälfte, DOM-Querverbände ~6,1 m)
PS = 6.25                 # Feldweite Seitenöffnung (10 Felder)
YK = YP - 9 * PC          # Knick in der Mittelöffnung (Übergang ins niedrige Mittelstück, 18,34 m)
YKS = YP + 9 * PS         # Knick Seitenöffnung (Obergurt läuft in den Ankerkasten über)
YE = YP + 10 * PS         # Trägerende (135,84 m)
BC = 0.45                 # Oberkante Untergurt über Fahrbahn
TOP_LOW = 2.2             # Oberkante niedriges Mittelstück (DOM: 2,1-2,2 m)
TOP_END = 1.35            # Oberkante Ankerkasten am Ende (DOM: 1,3 m)
CH = 0.9                  # Obergurt-Höhe
SW_Z = 0.21               # Gehwegoberfläche über Fahrbahn (DOM: +0,21)
SW_IN = XT + 0.55         # Gehweg Innenkante
SW_OUT = 9.85             # Gehweg Außenkante (DOM 99%-Kante ±10,3 inkl. Pixelsaum)
CLEAR = 5.0               # Unterkante Querriegel über Fahrbahn


def top_h(a):
    """Oberkante Obergurt über Fahrbahn bei |Y| = a (aus DOM1 gefittet, Median-Abweichung 0,2 m)."""
    a = abs(a)
    if a <= YK:
        return TOP_LOW
    if a <= YP:
        x = YP - a
        return 24.2 - 0.521 * x + 0.0022 * x * x
    if a <= YKS:
        x = a - YP
        return 24.2 - 0.4906 * x + 0.0015 * x * x
    return TOP_END


def zc(a):
    """Obergurt-Schwerachse."""
    return top_h(a) - CH / 2


# ------------------------------------------------------------------------------------------------ Materialien
def srgb(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def mat(name, hexc, rough=0.5, metal=0.0, emit=None, alpha=1.0, double=False):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*srgb(hexc), 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = (*srgb(emit), 1.0)
        b.inputs["Emission Strength"].default_value = 1.0
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
        for attr, val in (("blend_method", "BLEND"), ("surface_render_method", "BLENDED")):
            try:
                setattr(m, attr, val)
            except Exception:
                pass
    m.use_backface_culling = not double
    m.diffuse_color = (*srgb(hexc), alpha)
    return m


bpy.ops.wm.read_factory_settings(use_empty=True)
MATS = {
    "steel": mat("BridgeSteelBlue", "#8CB3C7", rough=0.6),
    "rail": mat("BridgeRail", "#79AACB", rough=0.5, double=True),
    "stone": mat("BridgeStone", "#A39579", rough=0.92),
    "wood": mat("BridgeWood", "#71665A", rough=0.85),
    "glass": mat("BridgeGlass", "#24313A", rough=0.12),
    "dark": mat("BridgeDark", "#3B4449", rough=0.55),
    "lamp": mat("BridgeLampGlass", "#F4E7C8", rough=0.2, emit="#FFE2A6"),
    "mesh": mat("BridgeMesh", "#557A8C", rough=0.6, alpha=0.38, double=True),
}


# ------------------------------------------------------------------------------------------------ Geometrie-Sammler
class Geo:
    def __init__(self, name):
        self.name = name
        self.v = []
        self.f = []
        self.m = []

    def add(self, verts, faces, m):
        o = len(self.v)
        self.v.extend(tuple(p) for p in verts)
        for fc in faces:
            self.f.append([o + i for i in fc])
            self.m.append(m)


GEOS = {}


def geo(name):
    if name not in GEOS:
        GEOS[name] = Geo(name)
    return GEOS[name]


V = Vector
XA, YA, ZA = V((1, 0, 0)), V((0, 1, 0)), V((0, 0, 1))


def _frame(a, side):
    u = side - a * side.dot(a)
    if u.length < 1e-6:
        u = ZA - a * ZA.dot(a)
        if u.length < 1e-6:
            u = XA - a * XA.dot(a)
    u.normalize()
    return u, a.cross(u)


def box(g, m, p0, p1, w, d, side=XA, caps=True):
    """Stab von p0 nach p1, Breite w entlang 'side' (senkrecht zur Achse projiziert), Dicke d senkrecht dazu."""
    p0, p1 = V(p0), V(p1)
    ax = p1 - p0
    if ax.length < 1e-4:
        return
    a = ax.normalized()
    u, v = _frame(a, V(side))
    hw, hd = w / 2, d / 2
    ring = [u * hw + v * hd, -u * hw + v * hd, -u * hw - v * hd, u * hw - v * hd]
    vs = [p0 + r for r in ring] + [p1 + r for r in ring]
    fs = [[i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i] for i in range(4)]
    if caps:
        fs += [[3, 2, 1, 0], [4, 5, 6, 7]]
    g.add(vs, fs, m)


def aabb(g, m, mn, mx):
    x0, y0, z0 = mn
    x1, y1, z1 = mx
    vs = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    fs = [[3, 2, 1, 0], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    g.add(vs, fs, m)


def hexa(g, m, bot, top):
    """Quader aus 4 Unter- und 4 Oberecken (jeweils gegen den Uhrzeigersinn von oben)."""
    vs = list(bot) + list(top)
    fs = [[3, 2, 1, 0], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    g.add(vs, fs, m)


def sweep(g, m, pts, w, d, sides=None, side=XA, caps=True):
    """Kastenprofil entlang Polylinie mit Gehrung; w entlang side (je Punkt oder fest), d senkrecht dazu."""
    pts = [V(p) for p in pts]
    n = len(pts)
    if n < 2:
        return
    vs = []
    for i in range(n):
        if i == 0:
            t = (pts[1] - pts[0]).normalized()
            k = 1.0
        elif i == n - 1:
            t = (pts[-1] - pts[-2]).normalized()
            k = 1.0
        else:
            d0 = (pts[i] - pts[i - 1]).normalized()
            d1 = (pts[i + 1] - pts[i]).normalized()
            t = (d0 + d1)
            t = t.normalized() if t.length > 1e-6 else d1
            k = 1.0 / max(0.35, t.dot(d1))
        sd = V(sides[i]) if sides is not None else V(side)
        u, v = _frame(t, sd)
        hw, hd = w / 2, d / 2 * k
        vs += [pts[i] + u * hw + v * hd, pts[i] - u * hw + v * hd, pts[i] - u * hw - v * hd, pts[i] + u * hw - v * hd]
    fs = []
    for i in range(n - 1):
        o = 4 * i
        fs += [[o + j, o + (j + 1) % 4, o + 4 + (j + 1) % 4, o + 4 + j] for j in range(4)]
    if caps:
        o = 4 * (n - 1)
        fs += [[3, 2, 1, 0], [o, o + 1, o + 2, o + 3]]
    g.add(vs, fs, m)


def frustum(g, m, c, r0, r1, z0, z1, n=12, caps=(True, True), rot=0.0):
    cx, cy = c
    vs = []
    for z, r in ((z0, r0), (z1, r1)):
        for i in range(n):
            t = rot + 2 * math.pi * i / n
            vs.append((cx + r * math.cos(t), cy + r * math.sin(t), z))
    fs = [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    if caps[0]:
        fs.append(list(range(n - 1, -1, -1)))
    if caps[1] and r1 > 1e-4:
        fs.append(list(range(n, 2 * n)))
    g.add(vs, fs, m)


def prism_xy(g, m, poly, z0, z1):
    """Prisma aus Grundriss-Polygon (gegen Uhrzeigersinn von oben)."""
    n = len(poly)
    vs = [(x, y, z0) for x, y in poly] + [(x, y, z1) for x, y in poly]
    fs = [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    fs += [list(range(n - 1, -1, -1)), list(range(n, 2 * n))]
    g.add(vs, fs, m)


def prism_xz(g, m, poly, y0, y1):
    """Prisma aus Profil in der X-Z-Ebene (gegen Uhrzeigersinn mit X nach rechts, Z nach oben), längs Y."""
    n = len(poly)
    # Blick von -Y: X rechts, Z oben -> Normale -Y für die Fläche bei y0
    vs = [(x, y0, z) for x, z in poly] + [(x, y1, z) for x, z in poly]
    fs = [[i, n + i, n + (i + 1) % n, (i + 1) % n] for i in range(n)]
    fs += [list(range(n)), list(range(2 * n - 1, n - 1, -1))]
    g.add(vs, fs, m)


def quad(g, m, p0, p1, p2, p3):
    g.add([p0, p1, p2, p3], [[0, 1, 2, 3]], m)


def bar_quad(g, m, p, t, wdt, z0, z1):
    """Senkrechter Geländerstab als Fläche in der Geländerebene (doppelseitiges Material)."""
    a = V((p[0], p[1], 0)) - V(t) * (wdt / 2)
    b = V((p[0], p[1], 0)) + V(t) * (wdt / 2)
    quad(g, m, (a.x, a.y, z0), (b.x, b.y, z0), (b.x, b.y, z1), (a.x, a.y, z1))


def strip_quad(g, m, pa, pb, wdt):
    """Schmaler Streifen von pa nach pb in der senkrechten Ebene der beiden Punkte (Zierstäbe)."""
    pa, pb = V(pa), V(pb)
    ax = (pb - pa)
    hor = V((ax.x, ax.y, 0))
    if hor.length < 1e-6:
        hor = V((0, 1, 0))
    nrm = hor.normalized().cross(ZA)            # Normale der Geländerebene
    off = ax.normalized().cross(nrm) * (wdt / 2)
    quad(g, m, pa - off, pb - off, pb + off, pa + off)


S = "Superstructure"
STEEL = MATS["steel"]

# ------------------------------------------------------------------------------------------------ Knoten
SIGNS = (-1.0, 1.0)
CENTER_NODES = [YP - PC * k for k in range(10)]            # 0 = Pylon … 9 = Knick
SIDE_NODES = [YP + PS * k for k in range(11)]              # 0 = Pylon … 9 = Knick, 10 = Ende
LOW_NODES = [YK - j * PC / 2 for j in range(7)]            # Mittelstück, 6 = Mittelgelenk (0)
TALL = 7.3                                                 # ab dieser Gurt-Oberkante Querverband über Fahrbahn


def diag(g, ya, za, yb, zb, x, w=0.42, d=0.2):
    box(g, STEEL, (x, ya, za), (x, yb, zb), w, d, side=XA)


def truss_half(sx, sy):
    g = geo(S)
    x = sx * XT
    # --- Obergurt Seitenöffnung: Ende -> Knick -> Pylon (Ankerkasten = gleiches Profil, flach)
    pts = [(x, sy * YE, zc(YE))] + [(x, sy * a, zc(a)) for a in reversed(SIDE_NODES[1:10])]
    pts.append((x, sy * (YP + 0.55), zc(YP + 0.55)))
    sweep(g, STEEL, pts, 0.85, CH)
    # --- Obergurt Mittelöffnung: Pylon -> Knick
    pts = [(x, sy * (YP - 0.55), zc(YP - 0.55))] + [(x, sy * a, zc(a)) for a in CENTER_NODES[1:10]]
    sweep(g, STEEL, pts, 0.85, CH)
    # --- niedriger Obergurt Mittelstück (bis Mittelgelenk, Fuge 0,1 m)
    box(g, STEEL, (x, sy * YK, TOP_LOW - 0.22), (x, sy * 0.05, TOP_LOW - 0.22), 0.62, 0.45, side=XA)
    # --- Pfosten
    for a in SIDE_NODES[1:10] + CENTER_NODES[1:10]:
        box(g, STEEL, (x, sy * a, BC), (x, sy * a, zc(a)), 0.55, 0.42, side=XA, caps=False)
    for a in LOW_NODES[1:6]:
        box(g, STEEL, (x, sy * a, BC), (x, sy * a, TOP_LOW - 0.4), 0.34, 0.26, side=XA, caps=False)
    box(g, STEEL, (x, sy * 0.3, BC), (x, sy * 0.3, TOP_LOW - 0.1), 0.5, 0.4, side=XA)    # Gelenkpfosten
    # --- Streben: doppeltes Strebenfachwerk (Diagonalen über zwei Felder) + Hilfsriegel in hohen Feldern
    for nodes in (CENTER_NODES, SIDE_NODES[:10]):
        m = len(nodes) - 1
        zt = [zc(a) - 0.3 for a in nodes]
        zb = BC + 0.12
        for k in range(m - 1):
            if zt[k] - zb > 0.9:
                diag(g, sy * nodes[k], zt[k], sy * nodes[k + 2], zb, x)
            if zt[k + 2] - zb > 0.9:
                diag(g, sy * nodes[k + 2], zt[k + 2], sy * nodes[k], zb, x)
        diag(g, sy * nodes[m - 1], zt[m - 1], sy * nodes[m], zb, x, 0.36, 0.18)
        for k in range(m):
            hmin = min(zc(nodes[k]), zc(nodes[k + 1])) - CH / 2 - BC
            if hmin > 6.0:
                zh = BC + 0.55 * hmin
                box(g, STEEL, (x, sy * nodes[k], zh), (x, sy * nodes[k + 1], zh), 0.3, 0.24, side=XA, caps=False)
    # --- Mittelstück: Ständerfachwerk mit wechselnden Streben (Foto Mittelgelenk)
    for j in range(6):
        a0, a1 = LOW_NODES[j], LOW_NODES[j + 1]
        if j == 5:
            a1 = 0.45
        if j % 2 == 0:
            diag(g, sy * a0, TOP_LOW - 0.4, sy * a1, BC + 0.1, x, 0.3, 0.16)
        else:
            diag(g, sy * a0, BC + 0.1, sy * a1, TOP_LOW - 0.4, x, 0.3, 0.16)
    # --- Untergurt über Fahrbahn + Blechträger darunter (je Hälfte, Stoß in Feldmitte)
    box(g, STEEL, (x, 0, (BC - 0.1) / 2), (x, sy * YE, (BC - 0.1) / 2), 0.7, BC + 0.1, side=XA)
    box(g, STEEL, (x, 0, -0.95), (x, sy * YE, -0.95), 0.32, 1.7, side=XA, caps=False)        # Steg
    box(g, STEEL, (x, 0, -1.82), (x, sy * YE, -1.82), 0.62, 0.12, side=XA, caps=False)       # Unterflansch
    # Ende: Stirnblech
    aabb(g, STEEL, (x - 0.5, sy * YE - 0.2, -1.88), (x + 0.5, sy * YE + 0.2, TOP_END + 0.05))


def overhead(sy):
    """Querrahmen (Riegel über Lichtraum, Kopfbänder, Kreuze) und oberer Windverband."""
    g = geo(S)
    tall = [a for a in SIDE_NODES[1:10] + CENTER_NODES[1:10] if top_h(a) >= TALL]
    for a in tall:
        y = sy * a
        z = zc(a)
        box(g, STEEL, (-XT, y, CLEAR + 0.3), (XT, y, CLEAR + 0.3), 0.4, 0.6, side=YA)        # Riegel
        for sx in SIGNS:
            box(g, STEEL, (sx * XT, y, CLEAR - 1.3), (sx * (XT - 1.7), y, CLEAR), 0.22, 0.26, side=YA)   # Kopfband
        if z - 0.45 - (CLEAR + 0.6) > 1.4:
            for sx in SIGNS:
                box(g, STEEL, (sx * XT, y, CLEAR + 0.6), (-sx * XT, y, z - 0.4), 0.2, 0.22, side=YA, caps=False)
        box(g, STEEL, (-XT, y, z), (XT, y, z), 0.32, 0.38, side=YA)                         # oberer Riegel
    # oberer Windverband (Kreuze in Gurtebene) zwischen benachbarten hohen Knoten und vom Pylon aus
    for nodes in (CENTER_NODES, SIDE_NODES):
        seq = [YP] + [a for a in nodes[1:] if top_h(a) >= TALL]
        for a, b in zip(seq[:-1], seq[1:]):
            aa = a + (0.9 if b > a else -0.9) if a == YP else a
            za, zb = zc(aa) + 0.1, zc(b) + 0.1
            for sx in SIGNS:
                box(g, STEEL, (sx * XT, sy * aa, za), (-sx * XT, sy * b, zb), 0.18, 0.2, side=ZA, caps=False)


def underdeck(sy):
    """Querträger unter der Fahrbahn und Gehwegkonsolen."""
    g = geo(S)
    ys = sorted(set([round(a, 3) for a in SIDE_NODES[:11] + CENTER_NODES[:10] + LOW_NODES[:6]]))
    mids = [(ys[i] + ys[i + 1]) / 2 for i in range(len(ys) - 1)]
    for a in ys:
        if a < YE - 0.1:
            box(g, STEEL, (-XT, sy * a, -1.3), (XT, sy * a, -1.3), 0.3, 0.7, side=YA, caps=False)
    for a in ys + mids + [0.0]:
        if a > YE - 0.3 or (sy < 0 and a == 0.0):
            continue
        for sx in SIGNS:
            xo = sw_out(a) - 0.1
            prof = [(XT + 0.17, -1.7), (xo, -0.35), (xo, 0.05), (XT + 0.17, 0.05)]
            if sx < 0:
                prof = [(-px, pz) for px, pz in reversed(prof)]
            prism_xz(g, STEEL, prof, sy * a - 0.09, sy * a + 0.09)


# ------------------------------------------------------------------------------------------------ Gehwege
def sw_out(a):
    """Gehweg-Außenkante bei |Y| = a: Ausbuchtung um Pylon/Treppe (OSM-Umriss ±11,5 m) und in Feldmitte."""
    a = abs(a)
    x = SW_OUT
    d = abs(a - YP)
    if d < 4.2:
        x = 11.5
    elif d < 7.4:
        x = 11.5 + (SW_OUT - 11.5) * (d - 4.2) / 3.2
    if a < 2.2:
        x = max(x, 10.6)
    elif a < 3.6:
        x = max(x, 10.6 + (SW_OUT - 10.6) * (a - 2.2) / 1.4)
    return x


def edge_samples():
    ys = set([-YE, YE, 0.0])
    for s in SIGNS:
        for a in (YP - 7.4, YP - 4.2, YP + 4.2, YP + 7.4, 2.2, 3.6):
            ys.add(s * a)
    return sorted(ys)


def walkways():
    g = geo("Walkways")
    ys = edge_samples()
    for sx in SIGNS:
        outer = [(sw_out(y), y) for y in ys]
        poly_cw = [(SW_IN, -YE), (SW_IN, YE)] + [(xo, y) for xo, y in reversed(outer)]
        poly = list(reversed(poly_cw)) if sx > 0 else [(-px, py) for px, py in poly_cw]
        prism_xy(g, MATS["wood"], poly, SW_Z - 0.12, SW_Z)
        # Randträger (Blende) außen
        pts = [(sx * (xo + 0.08), y, -0.12) for xo, y in outer]
        sweep(g, STEEL, pts, 0.66, 0.18, side=ZA)


# ------------------------------------------------------------------------------------------------ Geländer
def polyline_samples(pts, step):
    """Punkte im Abstand step entlang Polylinie (x, y) mit Tangente."""
    out = []
    acc = 0.0
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        seg = V((x1 - x0, y1 - y0, 0))
        L = seg.length
        if L < 1e-6:
            continue
        t = seg / L
        s = step - acc if out else 0.0
        while s <= L:
            out.append(((x0 + t.x * s, y0 + t.y * s), t))
            s += step
        acc = L - (s - step)
    return out


def railing(g, m, path, z0, h, bar_step, post_step, rails, ornament=False):
    """Geländer entlang Polylinie path [(x, y)], Fuß bei z0, Höhe h."""
    for zr, rw, rd in rails:
        sweep(g, m, [(x, y, z0 + zr) for x, y in path], rd, rw, side=ZA)
    for (p, t) in polyline_samples(path, post_step):
        box(g, m, (p[0], p[1], z0), (p[0], p[1], z0 + h), 0.07, 0.07, side=XA, caps=False)
    zl = z0 + rails[-1][0]
    zh = z0 + rails[1][0] if len(rails) > 1 else z0 + h
    for (p, t) in polyline_samples(path, bar_step):
        bar_quad(g, m, p, t, 0.032, zl, zh)
    if ornament:   # Rautenband (Zick-Zack) zwischen zwei Bandstäben
        smp = polyline_samples(path, bar_step / 2)
        za, zb = z0 + 0.55, z0 + 0.85
        for i in range(len(smp) - 1):
            (pa, _), (pb, _) = smp[i], smp[i + 1]
            if i % 2 == 0:
                strip_quad(g, m, (pa[0], pa[1], za), (pb[0], pb[1], zb), 0.03)
            else:
                strip_quad(g, m, (pa[0], pa[1], zb), (pb[0], pb[1], za), 0.03)


def railings():
    g = geo("Railings")
    m = MATS["rail"]
    ys = edge_samples()
    for sx in SIGNS:
        # Außengeländer (folgt Ausbuchtungen)
        path = [(sx * (sw_out(y) - 0.1), y) for y in ys]
        railing(g, m, path, SW_Z, 1.15, 0.24, 2.4, [(1.12, 0.06, 0.09), (0.97, 0.05, 0.06), (0.12, 0.05, 0.06)])
        # Gehweg-Innengeländer und Fahrbahngeländer, am Pylon unterbrochen
        for xi, z0, h, step, rails, orn in (
                (XT + 0.62, SW_Z, 1.1, 0.42, [(1.07, 0.06, 0.08), (0.92, 0.05, 0.05), (0.12, 0.05, 0.05)], False),
                (XT - 0.62, 0.0, 1.0, 0.75, [(0.97, 0.06, 0.08), (0.85, 0.04, 0.04), (0.55, 0.04, 0.04), (0.1, 0.05, 0.05)], True)):
            cuts = [(-YE + 0.4, -YP - 1.4), (-YP + 1.4, YP - 1.4), (YP + 1.4, YE - 0.4)]
            for y0, y1 in cuts:
                railing(g, m, [(sx * xi, y0), (sx * xi, y1)], z0, h, step, 3.0, rails, ornament=orn)


# ------------------------------------------------------------------------------------------------ Pylone
def pylon(sx, sy):
    g = geo(S)
    cx, cy = sx * XT, sy * YP
    hw = 0.9
    corners = [(cx + hw, cy + hw), (cx - hw, cy + hw), (cx - hw, cy - hw), (cx + hw, cy - hw)]
    ztop = 24.3
    for px, py in corners:
        box(g, STEEL, (px, py, -1.9), (px, py, ztop - 0.5), 0.34, 0.34, side=XA, caps=False)
    levels = [BC + 0.15 + 2.2 * i for i in range(11)] + [ztop - 0.5]
    for i, zl in enumerate(levels):
        for k in range(4):
            p, q = corners[k], corners[(k + 1) % 4]
            box(g, STEEL, (p[0], p[1], zl), (q[0], q[1], zl), 0.14, 0.16, side=ZA, caps=False)
            if i + 1 < len(levels):
                zh = levels[i + 1]
                if (i + k) % 2:
                    box(g, STEEL, (p[0], p[1], zl), (q[0], q[1], zh), 0.13, 0.13, side=ZA, caps=False)
                else:
                    box(g, STEEL, (q[0], q[1], zl), (p[0], p[1], zh), 0.13, 0.13, side=ZA, caps=False)
    aabb(g, STEEL, (cx - 1.15, cy - 1.15, ztop - 0.5), (cx + 1.15, cy + 1.15, ztop))           # Kopf
    aabb(g, STEEL, (cx - 1.5, cy - 1.5, ztop), (cx + 1.5, cy + 1.5, ztop + 0.15))               # Plattform
    # Türmchen (Aussichtskanzel) mit Fensterband, Dach und Mast
    z0, z1 = ztop + 0.15, ztop + 1.75
    c = 1.2
    for px, py in ((cx + c, cy + c), (cx - c, cy + c), (cx - c, cy - c), (cx + c, cy - c)):
        box(g, STEEL, (px, py, z0), (px, py, z1), 0.14, 0.14, side=XA, caps=False)
    for (ax_, ay_), (bx_, by_) in (((cx - c, cy - c), (cx + c, cy - c)), ((cx + c, cy - c), (cx + c, cy + c)),
                                   ((cx + c, cy + c), (cx - c, cy + c)), ((cx - c, cy + c), (cx - c, cy - c))):
        box(g, STEEL, (ax_, ay_, z0 + 0.45), (bx_, by_, z0 + 0.45), 0.9, 0.06, side=ZA, caps=False)   # Brüstung
        box(g, MATS["glass"], (ax_, ay_, z0 + 1.22), (bx_, by_, z0 + 1.22), 0.62, 0.03, side=ZA, caps=False)
        box(g, STEEL, (ax_, ay_, z1 - 0.05), (bx_, by_, z1 - 0.05), 0.1, 0.1, side=ZA, caps=False)
    aabb(g, STEEL, (cx - 1.45, cy - 1.45, z1), (cx + 1.45, cy + 1.45, z1 + 0.12))
    rz = z1 + 0.12
    vs = [(cx + 1.45, cy + 1.45, rz), (cx - 1.45, cy + 1.45, rz), (cx - 1.45, cy - 1.45, rz), (cx + 1.45, cy - 1.45, rz),
          (cx, cy, rz + 0.4)]
    g.add(vs, [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]], MATS["dark"])
    box(g, MATS["dark"], (cx, cy, rz + 0.35), (cx, cy, rz + 4.6), 0.07, 0.07, side=XA)        # Mast/Fahnenstange
    # Wendeltreppe (vorgesetzt, außen am Pylon) mit Gitterkäfig
    tx, ty, r = sx * (XT + 2.0), cy, 1.05
    frustum(geo("StairCages"), MATS["mesh"], (tx, ty), r, r, SW_Z, ztop, n=12, caps=(False, False))
    for k in range(4):
        t = math.pi / 4 + k * math.pi / 2
        px, py = tx + r * math.cos(t), ty + r * math.sin(t)
        box(g, STEEL, (px, py, SW_Z), (px, py, ztop + 0.15), 0.09, 0.09, side=XA, caps=False)
    for zr in (SW_Z + 2.2, 8.0, 14.0, 20.0, ztop):
        pts = [(tx + r * math.cos(2 * math.pi * i / 12), ty + r * math.sin(2 * math.pi * i / 12), zr) for i in range(13)]
        sweep(g, STEEL, pts, 0.06, 0.08, side=ZA, caps=False)
    hel, sides = [], []
    n_steps = int((ztop - SW_Z) / 3.0 * 12)
    for i in range(n_steps + 1):
        t = 2 * math.pi * i / 12
        hel.append((tx + 0.72 * math.cos(t), ty + 0.72 * math.sin(t), SW_Z + 3.0 * i / 12))
        sides.append((math.cos(t), math.sin(t), 0.0))
    sweep(g, STEEL, hel, 0.62, 0.07, sides=sides, caps=False)
    box(g, STEEL, (tx, ty, SW_Z), (tx, ty, ztop), 0.16, 0.16, side=XA, caps=False)           # Spindel
    aabb(g, STEEL, (tx - 1.15, ty - 1.15, ztop), (tx + 1.15, ty + 1.15, ztop + 0.15))       # Austritt


def pylon_portal(sy):
    """Querrahmen zwischen den Pylonen (dichtes Gitter über dem Lichtraum) und Galerie oben."""
    g = geo(S)
    cy = sy * YP
    xi = XT - 0.9
    zl = [5.6 + 2.6 * i for i in range(7)] + [23.8]
    for fy in (cy - 0.8, cy + 0.8):
        for z in zl:
            box(g, STEEL, (-xi, fy, z), (xi, fy, z), 0.22, 0.3, side=YA, caps=False)
        box(g, STEEL, (0, fy, zl[0]), (0, fy, zl[-1]), 0.2, 0.2, side=YA, caps=False)
        for z0, z1 in zip(zl[:-1], zl[1:]):
            for xa, xb in ((-xi, 0.0), (0.0, xi)):
                box(g, STEEL, (xa, fy, z0), (xb, fy, z1), 0.14, 0.15, side=YA, caps=False)
                box(g, STEEL, (xb, fy, z0), (xa, fy, z1), 0.14, 0.15, side=YA, caps=False)
        for sx in SIGNS:
            box(g, STEEL, (sx * xi, fy, CLEAR - 1.6), (sx * (xi - 2.0), fy, zl[0]), 0.22, 0.26, side=YA)
    # Galerie zwischen den Türmchen
    zt = 24.3
    aabb(g, STEEL, (-XT + 1.2, cy - 0.65, zt - 0.1), (XT - 1.2, cy + 0.65, zt + 0.05))
    gr = geo("Railings")
    for fy in (cy - 0.62, cy + 0.62):
        railing(gr, MATS["rail"], [(-XT + 1.5, fy), (XT - 1.5, fy)], zt + 0.05, 1.0, 0.5, 1.6,
                [(0.98, 0.05, 0.06), (0.55, 0.04, 0.04), (0.1, 0.04, 0.04)])


# ------------------------------------------------------------------------------------------------ Pfeiler & Widerlager
def pier(sy):
    g = geo("Piers")
    m = MATS["stone"]
    cy = sy * YP
    zb, zt = -16.0, -2.35
    hexa(g, m, [(7.3, cy - 3.8, zb), (7.3, cy + 3.8, zb), (-7.3, cy + 3.8, zb), (-7.3, cy - 3.8, zb)],
         [(6.9, cy - 3.4, zt), (6.9, cy + 3.4, zt), (-6.9, cy + 3.4, zt), (-6.9, cy - 3.4, zt)])
    aabb(g, m, (-7.1, cy - 3.6, zt), (7.1, cy + 3.6, -1.92))                                     # Abdeckplatte
    aabb(g, m, (-7.2, cy - 3.7, -6.2), (7.2, cy + 3.7, -5.9))                                    # Gurtgesims
    for sx in SIGNS:
        c = (sx * 7.6, cy)
        frustum(g, m, c, 2.55, 2.35, zb, -3.4, n=16, caps=(False, False))
        frustum(g, m, c, 2.62, 2.62, -6.25, -5.9, n=16, caps=(False, True))
        for i in range(16):                                                                      # Bogenfries-Konsolen
            t = 2 * math.pi * (i + 0.5) / 16
            p0 = (c[0] + 2.3 * math.cos(t), c[1] + 2.3 * math.sin(t), -3.55)
            p1 = (c[0] + 2.62 * math.cos(t), c[1] + 2.62 * math.sin(t), -3.55)
            box(g, m, p0, p1, 0.45, 0.3, side=ZA)
        frustum(g, m, c, 2.68, 2.68, -3.35, -2.6, n=16, caps=(True, True))                       # Brüstung
        for i in range(8):                                                                       # Zinnen
            t = 2 * math.pi * i / 8
            p0 = (c[0] + 2.32 * math.cos(t), c[1] + 2.32 * math.sin(t), -2.32)
            p1 = (c[0] + 2.7 * math.cos(t), c[1] + 2.7 * math.sin(t), -2.32)
            box(g, m, p0, p1, 0.56, 0.75, side=ZA)


def abutment(sy):
    g = geo("Piers")
    m = MATS["stone"]
    y0, y1 = sorted((sy * (YE - 1.2), sy * (YE + 5.0)))
    aabb(g, m, (-10.4, y0, -9.0), (10.4, y1, -1.9))
    aabb(g, m, (-10.6, y0 - 0.15, -2.25), (10.6, y1 + 0.15, -1.88))


# ------------------------------------------------------------------------------------------------ Leuchten
LAMP_POS = []


def lamps():
    g = geo("Lamps")
    pos = [YP - PC * k for k in (1, 3, 5, 7, 9)] + [LOW_NODES[3]] + [YP + PS * k for k in (2, 4, 6, 8)]
    for sy in SIGNS:
        for a in pos:
            for sx in SIGNS:
                x, y = sx * (XT + 0.92), sy * a
                aabb(g, MATS["rail"], (x - 0.13, y - 0.13, SW_Z), (x + 0.13, y + 0.13, SW_Z + 0.55))
                frustum(g, MATS["rail"], (x, y), 0.075, 0.055, SW_Z + 0.55, 3.95, n=8, caps=(False, True))
                box(g, MATS["rail"], (x, y - 0.5, 3.95), (x, y + 0.5, 3.95), 0.07, 0.07, side=XA)
                for dy in (-0.42, 0.42):
                    frustum(g, MATS["dark"], (x, y + dy), 0.06, 0.1, 3.99, 4.06, n=6, caps=(True, False))
                    frustum(g, MATS["lamp"], (x, y + dy), 0.12, 0.17, 4.06, 4.46, n=6, caps=(False, False))
                    frustum(g, MATS["dark"], (x, y + dy), 0.22, 0.0, 4.46, 4.7, n=6, caps=(True, False))
                    box(g, MATS["dark"], (x, y + dy, 4.68), (x, y + dy, 4.82), 0.04, 0.04, side=XA)
                    LAMP_POS.append((x, y + dy, 4.26))


# ------------------------------------------------------------------------------------------------ Aufbau
for sy in SIGNS:
    for sx in SIGNS:
        truss_half(sx, sy)
        pylon(sx, sy)
    overhead(sy)
    underdeck(sy)
    pylon_portal(sy)
    pier(sy)
    abutment(sy)
aabb(geo(S), STEEL, (-XT - 0.45, -0.7, TOP_LOW), (-XT + 0.45, 0.7, TOP_LOW + 0.1))              # Gelenk-Laschen
aabb(geo(S), STEEL, (XT - 0.45, -0.7, TOP_LOW), (XT + 0.45, 0.7, TOP_LOW + 0.1))
walkways()
railings()
lamps()

col = bpy.context.scene.collection
root = bpy.data.objects.new("BlauesWunder", None)
col.objects.link(root)
total = 0
for name, gg in GEOS.items():
    me = bpy.data.meshes.new(name)
    me.from_pydata(gg.v, [], gg.f)
    used = []
    for mm in gg.m:
        if mm not in used:
            used.append(mm)
    for mm in used:
        me.materials.append(mm)
    idx = {mm.name: i for i, mm in enumerate(used)}
    for poly, mm in zip(me.polygons, gg.m):
        poly.material_index = idx[mm.name]
        poly.use_smooth = False
    me.validate(clean_customdata=False)
    me.update()
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    ob.parent = root
    me.calc_loop_triangles()
    tris = len(me.loop_triangles)
    total += tris
    print("  %-16s %7d Dreiecke  %s" % (name, tris, ", ".join(mm.name for mm in used)))
for i, p in enumerate(LAMP_POS):
    e = bpy.data.objects.new("LampLight_%03d" % i, None)
    e.location = p
    e.parent = root
    col.objects.link(e)
print("BLAUES WUNDER: %d Dreiecke, %d Laternen" % (total, len(LAMP_POS)))
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", export_yup=True, export_apply=True)
print("exportiert:", OUT)
