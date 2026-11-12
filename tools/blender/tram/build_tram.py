"""DVB-Straßenbahn NGT D12DD (Bombardier Flexity Classic, 45 m) – prozedural, geschlossen, maßstäblich.

Ausgabe: godot/assets/models/props/tram_sections.glb mit Knoten Section_0 … Section_4 (Ursprung = Abschnittsmitte,
Front = Blender +Y = Godot -Z, z = 0 = Schienenoberkante). Je Abschnitt Leerknoten Bogie_<n> an den Drehgestell-
mitten: tram_unit.gd führt Abschnitte mit zwei Drehgestellen über deren Gleispunkte, Sänften ohne Drehgestell hängen
zwischen den Gelenken der Nachbarn. Leerknoten Display_<name> markieren die Zielanzeigen (Mitte, Normale = lokale -Z
des Knotens nach dem Import, Breite/Höhe im Namen nicht nötig: siehe DISPLAYS in tram_unit.gd).

Materialnamen (Godot wertet sie aus): TramPaint, TramBlack, TramWindow (nachts leicht beleuchtet), TramGrey, Bellows,
Steel, HeadlightEmit, TaillightEmit, DisplayEmit.

Aufruf: flatpak run --filesystem=host org.blender.Blender -b --python build_tram.py -- <ausgabe.glb>
Maße: data/research/dvb_tram.md (Datenblätter/Fotos, Wikimedia Commons). Keine fremden Modelle/Texturen verwendet.
"""
import bpy, bmesh, sys, math
from mathutils import Vector

OUT = sys.argv[sys.argv.index("--") + 1]

# ---------------------------------------------------------------------------------------------------------------
# Maße (Meter, z über Schienenoberkante)
HW = 1.325               # halbe Wagenkastenbreite (2,65 m)
Z_BOT = 0.24             # Unterkante Schürze
Z_SKIRT = 0.42           # Oberkante schwarzer Schürzenstreifen
Z_SILL = 0.98            # Fensterunterkante (Fensterband schwarz)
Z_WTOP = 2.42            # Fensteroberkante
Z_EAVE = 2.86            # Beginn der Dachrundung
Z_ROOF = 3.26            # Dach Mitte
R_ROOF = 0.34            # Radius Dachkante
TUMBLE = 0.025           # Einzug oberhalb der Fenster
GAP = 0.36               # Abstand zwischen Wagenkästen (Gelenk/Faltenbalg)
GAUGE = 1.450            # Dresdner Spurweite

# Abschnitte von vorn nach hinten: Länge, Art, Drehgestelle (lokal, + = vorn), Türen (Mitte lokal, Breite)
SECTIONS = [
    {"len": 11.93, "kind": "front", "bogies": [3.55, -3.85], "doors": [(2.55, 0.80), (-2.15, 1.30)], "panto": False},
    {"len": 3.90, "kind": "mid", "bogies": [], "doors": [(0.0, 1.30)], "panto": False},
    {"len": 11.93, "kind": "mid", "bogies": [3.85, -3.85], "doors": [(0.0, 1.30)], "panto": True},
    {"len": 3.90, "kind": "mid", "bogies": [], "doors": [(0.0, 1.30)], "panto": False},
    {"len": 11.93, "kind": "rear", "bogies": [3.85, -3.55], "doors": [(2.15, 1.30), (-3.6, 1.30)], "panto": False},
]
DOOR_SIDES = (1,)        # +1 = rechts (Einrichtungsfahrzeug: Türen nur rechts)


def srgb(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def mat(name, hexc, rough=0.5, metal=0.0, emit=None, coat=0.0):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*srgb(hexc), 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if coat > 0.0:
        b.inputs["Coat Weight"].default_value = coat
        b.inputs["Coat Roughness"].default_value = 0.08
    if emit:
        b.inputs["Emission Color"].default_value = (*srgb(emit), 1.0)
        b.inputs["Emission Strength"].default_value = 1.0
    return m


bpy.ops.wm.read_factory_settings(use_empty=True)
M = {
    "paint": mat("TramPaint", "#F2B700", rough=0.32, coat=0.6),
    "black": mat("TramBlack", "#16181A", rough=0.42),
    "window": mat("TramWindow", "#0A0E12", rough=0.04),
    "screen": mat("TramWindscreen", "#080B0E", rough=0.03),
    "grey": mat("TramGrey", "#7E8388", rough=0.55, metal=0.2),
    "bellows": mat("Bellows", "#141414", rough=0.9),
    "steel": mat("Steel", "#5E6064", rough=0.35, metal=1.0),
    "head": mat("HeadlightEmit", "#F4F1E8", rough=0.1, emit="#FFF6E0"),
    "tail": mat("TaillightEmit", "#7A0A06", rough=0.2, emit="#FF1A0A"),
    "disp": mat("DisplayEmit", "#050505", rough=0.25),
}
MAT_ORDER = list(M.keys())


class MB:
    """Einfacher Mesh-Bauer: Vertices, Flächen, Material je Fläche."""

    def __init__(self):
        self.v, self.f, self.m = [], [], []

    def vert(self, p):
        self.v.append((float(p[0]), float(p[1]), float(p[2])))
        return len(self.v) - 1

    def face(self, idx, mk, outward=None):
        if outward is not None:
            # Wicklung prüfen: Normale soll in Richtung outward zeigen
            a, b, c = (Vector(self.v[i]) for i in idx[:3])
            n = (b - a).cross(c - a)
            if n.length > 1e-12 and n.dot(Vector(outward)) < 0.0:
                idx = list(reversed(idx))
        self.f.append(tuple(idx))
        self.m.append(MAT_ORDER.index(mk))

    def build(self, name, parent=None, smooth_angle=35.0, recalc=False):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.v, [], self.f)
        for k in MAT_ORDER:
            me.materials.append(M[k])
        for i, p in enumerate(me.polygons):
            p.material_index = self.m[i]
        me.update()
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        if recalc:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        for f in bm.faces:
            f.smooth = True
        lim = math.radians(smooth_angle)
        for e in bm.edges:
            if len(e.link_faces) == 2:
                f1, f2 = e.link_faces
                if f1.normal.angle(f2.normal, 0.0) > lim or f1.material_index != f2.material_index:
                    e.smooth = False
        bm.to_mesh(me)
        bm.free()
        # ungenutzte Materialslots entfernen (Blender verschiebt die Flächenindizes dabei selbst)
        used = set(p.material_index for p in me.polygons)
        for i in reversed(range(len(me.materials))):
            if i not in used:
                me.materials.pop(index=i)
        ob = bpy.data.objects.new(name, me)
        bpy.context.collection.objects.link(ob)
        if parent is not None:
            ob.parent = parent
        return ob


# ---------------------------------------------------------------------------------------------------------------
# Querschnitt (geschlossene Schleife, gegen den Uhrzeigersinn von vorn gesehen: rechts unten -> rechts oben -> links)
def profile(shrink=0.0):
    hw = HW - shrink
    half = []
    half.append((0.0, Z_BOT + shrink))
    half.append((hw - 0.06, Z_BOT + shrink))
    half.append((hw - 0.015, Z_BOT + shrink + 0.02))
    half.append((hw, Z_BOT + shrink + 0.07))
    for z in (Z_SKIRT, 0.7, Z_SILL, 1.7, Z_WTOP):
        half.append((hw, z))
    half.append((hw - TUMBLE * 0.6, Z_EAVE - 0.18))
    xe = hw - TUMBLE
    half.append((xe, Z_EAVE))
    zr = Z_ROOF - 0.03 - shrink
    cx, cz = xe - R_ROOF, Z_EAVE
    rz = zr - Z_EAVE
    for k in range(1, 8):
        a = math.radians(90.0 * k / 7.0)
        half.append((cx + R_ROOF * math.cos(a), cz + rz * math.sin(a)))
    half.append((0.55, Z_ROOF - 0.01 - shrink))
    half.append((0.0, Z_ROOF - shrink))
    right = half[:-1]
    left = [(-x, z) for x, z in reversed(half[1:])]
    loop = right + [half[-1]] + left[1:-1]
    return loop


PROF = profile()
ZC = 1.65                # Mitte der Kopfflächen-Ringe


def ray_scale(prof, x, z, cz=ZC):
    """s in [0, 1]: Lage von (x, z) zwischen Ringmitte (0, cz) und Querschnittsrand."""
    dx, dz = x, z - cz
    if abs(dx) < 1e-9 and abs(dz) < 1e-9:
        return 0.0
    best = None
    n = len(prof)
    for i in range(n):
        ax, az = prof[i]
        bx, bz = prof[(i + 1) % n]
        ex, ez = bx - ax, bz - az
        den = dx * ez - dz * ex
        if abs(den) < 1e-12:
            continue
        lam = ((ax) * ez - (az - cz) * ex) / den
        mu = ((ax) * dz - (az - cz) * dx) / den
        if lam > 0 and -1e-9 <= mu <= 1 + 1e-9:
            if best is None or lam < best:
                best = lam
    return 1.0 / best if best else 1.0


# Kopfform: Rückversatz r(x, z) gegenüber der Spitze (Front) bzw. dem Heck
def r_front(x, z):
    u = min(abs(x) / HW, 1.0)
    if z < 0.92:
        a = 0.04 + 0.11 * ((0.92 - z) / 0.68) ** 2
    elif z < 2.50:
        a = 0.04 + 0.30 * ((z - 0.92) / 1.58) ** 1.15
    else:
        a = 0.34 + 0.36 * ((z - 2.50) / (Z_ROOF - 2.50)) ** 1.7
    b = 0.40 + 0.06 * max(0.0, (z - 2.5) / 0.8)
    return a + b * u ** 2.3


def r_rear(x, z):
    u = min(abs(x) / HW, 1.0)
    if z < 0.92:
        a = 0.03 + 0.08 * ((0.92 - z) / 0.68) ** 2
    elif z < 2.55:
        a = 0.03 + 0.10 * ((z - 0.92) / 1.63) ** 1.3
    else:
        a = 0.13 + 0.30 * ((z - 2.55) / (Z_ROOF - 2.55)) ** 1.7
    return a + 0.34 * u ** 2.3


R_EDGE = 0.10
S0 = 0.86
RINGS = [0.0, 0.12, 0.25, 0.38, 0.5, 0.62, 0.72, 0.8, 0.86, 0.9, 0.935, 0.962, 0.982, 0.994, 1.0]


def nose_y(rfun, x, z, s):
    t = min(max((s - S0) / (1.0 - S0), 0.0), 1.0)
    return rfun(x, z) + R_EDGE * (1.0 - math.sqrt(max(1.0 - t * t, 0.0)))


def nose_point(rfun, y_tip, sign, x, z):
    """Punkt auf der Kopffläche über (x, z); sign = +1 Front (+Y), -1 Heck."""
    s = min(ray_scale(PROF, x, z), 1.0)
    return Vector((x, y_tip - sign * nose_y(rfun, x, z, s), z))


def nose_normal(rfun, y_tip, sign, x, z):
    e = 0.004
    p = nose_point(rfun, y_tip, sign, x, z)
    px = nose_point(rfun, y_tip, sign, x + e, z)
    pz = nose_point(rfun, y_tip, sign, x, z + e)
    n = (px - p).cross(pz - p)
    if n.dot(Vector((0, sign, 0))) < 0:
        n = -n
    return n.normalized()


def body(sec, y0, y1, front_fn, rear_fn):
    """Wagenkasten: Röhre aus PROF zwischen y0 (hinten) und y1 (vorn); Enden: Kopf (Funktion) oder flach."""
    mb = MB()
    N = len(PROF)

    def band(z):
        return "black" if z < Z_SKIRT - 1e-6 else "paint"

    def end_rings(fn, y_end, sign):
        rings = []
        if fn is None:
            ring = [mb.vert((x, y_end, z)) for x, z in PROF]
            c = mb.vert((0.0, y_end, ZC))
            for j in range(N):
                mb.face([c, ring[j], ring[(j + 1) % N]], "black", outward=(0, sign, 0))
            return ring
        cpt = nose_point(fn, y_end, sign, 0.0, ZC)
        c = mb.vert(cpt)
        prev = None
        for s in RINGS[1:]:
            ring = []
            for x, z in PROF:
                px, pz = s * x, ZC + s * (z - ZC)
                ring.append(mb.vert((px, y_end - sign * nose_y(fn, px, pz, s), pz)))
            if prev is None:
                for j in range(N):
                    zz = PROF[j][1]
                    mb.face([c, ring[j], ring[(j + 1) % N]], "paint", outward=(0, sign, 0))
            else:
                for j in range(N):
                    k = (j + 1) % N
                    mk = "paint"           # Schürzenstreifen am Kopf als Aufkleber (gerade Kante)
                    out = Vector(mb.v[ring[j]]) - Vector((0, y_end - sign * 1.5, ZC))
                    mb.face([prev[j], prev[k], ring[k], ring[j]], mk, outward=out)
            prev = ring
        return prev

    rf = end_rings(front_fn, y1, +1)
    rr = end_rings(rear_fn, y0, -1)
    for j in range(N):
        k = (j + 1) % N
        zm = 0.5 * (PROF[j][1] + PROF[k][1])
        xm = 0.5 * (PROF[j][0] + PROF[k][0])
        mk = band(zm)
        mb.face([rr[j], rr[k], rf[k], rf[j]], mk, outward=(xm, 0, zm - 1.6))
    return mb


def rrect(cx, cz, w, h, rad, nseg=4):
    """Umriss eines abgerundeten Rechtecks in (u, v), gegen den Uhrzeigersinn."""
    rad = min(rad, w * 0.5 - 1e-4, h * 0.5 - 1e-4)
    pts = []
    for (ux, uz, a0) in ((cx + w / 2 - rad, cz - h / 2 + rad, -90), (cx + w / 2 - rad, cz + h / 2 - rad, 0),
                         (cx - w / 2 + rad, cz + h / 2 - rad, 90), (cx - w / 2 + rad, cz - h / 2 + rad, 180)):
        for k in range(nseg + 1):
            a = math.radians(a0 + 90.0 * k / nseg)
            pts.append((ux + rad * math.cos(a), uz + rad * math.sin(a)))
    return pts


def decal(mb, outline, mapf, mk, outward, rings=(1.0, 0.8, 0.55, 0.3)):
    """Fläche aus Umriss (u, v) mit konzentrischen Ringen; mapf(u, v) -> Vector (auf/über der Oberfläche)."""
    # Umriss fein unterteilen (gewölbte Flächen: lange Sehnen würden in den Wagenkasten schneiden)
    fine = []
    for i in range(len(outline)):
        a, b = outline[i], outline[(i + 1) % len(outline)]
        n_sub = max(1, int(math.ceil(math.dist(a, b) / 0.07))) if rings != (1.0,) else 1   # ebene Flächen: keine
        for k in range(n_sub):
            t = k / n_sub
            fine.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    cu = sum(p[0] for p in outline) / len(outline)
    cv = sum(p[1] for p in outline) / len(outline)
    outline = fine
    if rings != (1.0,):
        # Ringabstand <= ~0,1 m (größter Abstand Umriss-Mitte)
        rmax = max(math.dist(p, (cu, cv)) for p in outline)
        nr = max(2, int(math.ceil(rmax / 0.1)))
        rings = tuple(1.0 - k / nr for k in range(nr))
    prev = None
    n = len(outline)
    for s in rings:
        ring = [mb.vert(mapf(cu + s * (u - cu), cv + s * (v - cv))) for u, v in outline]
        if prev is not None:
            for j in range(n):
                k = (j + 1) % n
                mb.face([prev[j], prev[k], ring[k], ring[j]], mk, outward=outward(prev[j]))
        prev = ring
    c = mb.vert(mapf(cu, cv))
    for j in range(n):
        mb.face([prev[j], prev[(j + 1) % n], c], mk, outward=outward(c))


def side_map(side, off):
    """Seitenwand: u = y (längs), v = z; leicht eingezogen oberhalb Z_WTOP."""
    def f(u, v):
        x = HW
        if v > Z_WTOP:
            x = HW - TUMBLE * 0.6 * min((v - Z_WTOP) / (Z_EAVE - 0.18 - Z_WTOP), 1.0)
        return Vector((side * (x + off), u, v))
    return f


def box(mb, c, size, mk):
    cx, cy, cz = c
    sx, sy, sz = (s / 2 for s in size)
    v = [mb.vert((cx + dx * sx, cy + dy * sy, cz + dz * sz)) for dx in (-1, 1) for dy in (-1, 1) for dz in (-1, 1)]
    # Indizes: (dx, dy, dz) -> 4*ix + 2*iy + iz
    def q(a, b, c_, d, o):
        mb.face([v[a], v[b], v[c_], v[d]], mk, outward=o)
    q(0, 1, 3, 2, (-1, 0, 0)); q(4, 6, 7, 5, (1, 0, 0))
    q(0, 4, 5, 1, (0, -1, 0)); q(2, 3, 7, 6, (0, 1, 0))
    q(0, 2, 6, 4, (0, 0, -1)); q(1, 5, 7, 3, (0, 0, 1))


def beam(mb, a, b, th, mk, tw=None):
    """Quader von a nach b (Querschnitt th x tw)."""
    a, b = Vector(a), Vector(b)
    d = b - a
    ax = d.normalized()
    up = Vector((1, 0, 0)) if abs(ax.x) < 0.9 else Vector((0, 0, 1))
    u = ax.cross(up).normalized() * ((tw or th) / 2)
    w = ax.cross(u).normalized() * (th / 2)
    v = [mb.vert(p + su * u + sw * w) for p in (a, b) for su in (-1, 1) for sw in (-1, 1)]
    def q(i0, i1, i2, i3, o):
        mb.face([v[i0], v[i1], v[i2], v[i3]], mk, outward=o)
    q(0, 1, 5, 4, -u); q(2, 6, 7, 3, u); q(0, 4, 6, 2, -w); q(1, 3, 7, 5, w)
    q(0, 2, 3, 1, -ax); q(4, 5, 7, 6, ax)


def cylinder_x(mb, c, r, w, mk, seg=14):
    cx, cy, cz = c
    a_ring, b_ring = [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        a_ring.append(mb.vert((cx - w / 2, cy + r * math.cos(a), cz + r * math.sin(a))))
        b_ring.append(mb.vert((cx + w / 2, cy + r * math.cos(a), cz + r * math.sin(a))))
    for i in range(seg):
        j = (i + 1) % seg
        a = 2 * math.pi * (i + 0.5) / seg
        mb.face([a_ring[i], a_ring[j], b_ring[j], b_ring[i]], mk, outward=(0, math.cos(a), math.sin(a)))
    mb.face(list(a_ring), mk, outward=(-1, 0, 0))
    mb.face(list(b_ring), mk, outward=(1, 0, 0))


# ---------------------------------------------------------------------------------------------------------------
def free_intervals(y0, y1, blocks):
    """Freie Intervalle in [y0, y1] ohne die Blöcke [(a, b), ...]."""
    out, cur = [], y0
    for a, b in sorted(blocks):
        if a > cur:
            out.append((cur, min(a, y1)))
        cur = max(cur, b)
    if cur < y1:
        out.append((cur, y1))
    return [(a, b) for a, b in out if b - a > 0.25]


SIDE_DISP_W = [1.0, 0.0]


def side_details(mb, sec, side, y_lo, y_hi, has_doors, display_y=None):
    """Fensterband, Fenster, Türen einer Wagenseite. y_lo/y_hi: Bereich der ebenen Seitenwand."""
    out = (side, 0, 0)
    sm0 = side_map(side, 0.004)
    sm1 = side_map(side, 0.008)
    sm2 = side_map(side, 0.012)
    doors = sec["doors"] if has_doors else []
    blocks = [(dy - w / 2 - 0.09, dy + w / 2 + 0.09) for dy, w in doors]
    # schwarzes Fensterband (durchgehend zwischen den Türen)
    for a, b in free_intervals(y_lo, y_hi, blocks):
        decal(mb, rrect((a + b) / 2, (Z_SILL + Z_WTOP) / 2, b - a, Z_WTOP - Z_SILL + 0.06, 0.03), sm0, "black",
              lambda i: out, rings=(1.0,))
        # Scheiben: Teilung ~1,25 m, Holme 0,10 m
        L = b - a - 0.12
        n = max(1, round(L / 1.25))
        pw = (L - (n - 1) * 0.10) / n
        for k in range(n):
            cy = a + 0.06 + pw / 2 + k * (pw + 0.10)
            top = Z_WTOP - 0.03
            if display_y is not None and abs(cy - display_y) < pw / 2 + 0.06:
                # Seitenzielanzeige hinter der Scheibe oben
                dw = min(pw - 0.1, 1.05)
                SIDE_DISP_W[:] = [dw, cy]
                decal(mb, rrect(cy, top - 0.15, dw, 0.24, 0.02), side_map(side, 0.010), "disp",
                      lambda i: out, rings=(1.0,))
            decal(mb, rrect(cy, (Z_SILL + top) / 2 + 0.01, pw, top - Z_SILL - 0.02, 0.06), sm1, "window",
                  lambda i: out, rings=(1.0,))
    # Türen
    for dy, w in doors:
        z0, z1 = Z_BOT + 0.10, Z_WTOP + 0.10
        decal(mb, rrect(dy, (z0 + z1) / 2, w + 0.14, z1 - z0, 0.05), sm0, "black", lambda i: out, rings=(1.0,))
        leaves = 2 if w > 1.0 else 1
        lw = (w - 0.02 * (leaves - 1)) / leaves
        for k in range(leaves):
            cy = dy - w / 2 + lw / 2 + k * (lw + 0.02)
            decal(mb, rrect(cy, (z0 + 0.04 + z1 - 0.04) / 2, lw - 0.03, z1 - z0 - 0.08, 0.04), sm1, "paint",
                  lambda i: out, rings=(1.0,))
            decal(mb, rrect(cy, 1.66, lw - 0.16, 1.32, 0.07), sm2, "window", lambda i: out, rings=(1.0,))
            decal(mb, rrect(cy, 0.62, lw - 0.16, 0.36, 0.05), sm2, "window", lambda i: out, rings=(1.0,))


def nose_map(fn, y_tip, sign, off):
    def f(u, v):
        p = nose_point(fn, y_tip, sign, u, v)
        return p + nose_normal(fn, y_tip, sign, u, v) * off
    return f


def cab_details(mb, y_tip):
    fn, sg = r_front, +1
    o = lambda i: (0, 1, 0)
    # schwarze Maske um Frontscheibe und Zielanzeige
    decal(mb, rrect(0.0, 1.98, 2.38, 1.94, 0.22, 6), nose_map(fn, y_tip, sg, 0.004), "black", o,
          rings=(1.0, 0.9, 0.75, 0.55, 0.3))
    # Frontscheibe
    decal(mb, rrect(0.0, 1.72, 2.22, 1.30, 0.16, 6), nose_map(fn, y_tip, sg, 0.009), "screen", o,
          rings=(1.0, 0.9, 0.75, 0.55, 0.3))
    # Zielanzeige über der Scheibe
    decal(mb, rrect(0.0, 2.62, 1.70, 0.30, 0.03), nose_map(fn, y_tip, sg, 0.009), "disp", o,
          rings=(1.0, 0.6))
    # Scheinwerfer (je zwei Leuchten in schwarzem Band) und Begrenzungsleuchten
    for sx in (-1, 1):
        decal(mb, rrect(sx * 0.86, 0.80, 0.52, 0.17, 0.06), nose_map(fn, y_tip, sg, 0.006), "black", o,
              rings=(1.0, 0.5))
        decal(mb, rrect(sx * 0.98, 0.80, 0.18, 0.11, 0.05), nose_map(fn, y_tip, sg, 0.010), "head", o,
              rings=(1.0, 0.5))
        decal(mb, rrect(sx * 0.74, 0.80, 0.16, 0.10, 0.05), nose_map(fn, y_tip, sg, 0.010), "head", o,
              rings=(1.0, 0.5))
    # schwarzer Schürzenstreifen und Kupplungsabdeckung unten
    decal(mb, rrect(0.0, (Z_BOT + Z_SKIRT) / 2 + 0.03, 2 * HW - 0.02, Z_SKIRT - Z_BOT + 0.06, 0.02),
          nose_map(fn, y_tip, sg, 0.004), "black", o)
    decal(mb, rrect(0.0, 0.47, 1.10, 0.18, 0.05), nose_map(fn, y_tip, sg, 0.008), "black", o, rings=(1.0, 0.5))


def rear_details(mb, y_tip):
    fn, sg = r_rear, -1
    o = lambda i: (0, -1, 0)
    decal(mb, rrect(0.0, 1.86, 2.20, 1.62, 0.18, 6), nose_map(fn, y_tip, sg, 0.004), "black", o,
          rings=(1.0, 0.85, 0.6, 0.3))
    decal(mb, rrect(0.0, 1.70, 1.96, 1.10, 0.14, 6), nose_map(fn, y_tip, sg, 0.009), "window", o,
          rings=(1.0, 0.85, 0.6, 0.3))
    decal(mb, rrect(0.0, 2.48, 0.70, 0.26, 0.03), nose_map(fn, y_tip, sg, 0.009), "disp", o, rings=(1.0, 0.6))
    for sx in (-1, 1):
        decal(mb, rrect(sx * 0.92, 0.82, 0.30, 0.14, 0.05), nose_map(fn, y_tip, sg, 0.008), "tail", o,
              rings=(1.0, 0.5))
    decal(mb, rrect(0.0, (Z_BOT + Z_SKIRT) / 2 + 0.03, 2 * HW - 0.02, Z_SKIRT - Z_BOT + 0.06, 0.02),
          nose_map(fn, y_tip, sg, 0.004), "black", o)


def display_empty(parent, kind, w, h, pos, normal):
    """Leerknoten für die Zielanzeige: Godot +Z (= Blender -Y lokal) zeigt entlang der Anzeigenormale."""
    e = bpy.data.objects.new("Display_%s_%d_%d" % (kind, round(w * 100), round(h * 100)), None)
    e.location = pos
    e.rotation_mode = "QUATERNION"
    e.rotation_quaternion = Vector(normal).normalized().to_track_quat("-Y", "Z")
    e.parent = parent
    bpy.context.collection.objects.link(e)


def bellows(mb, y_end):
    """Faltenbalg hinter dem Wagenkasten (von y_end um GAP nach hinten)."""
    N = None
    rings = []
    k = 7
    for i in range(k + 1):
        y = y_end - GAP * i / k
        sh = 0.07 if i % 2 == 0 else 0.11
        if i in (0, k):
            sh = 0.09
        pr = profile(sh)
        N = len(pr)
        rings.append([mb.vert((x, y, z)) for x, z in pr])
    for i in range(k):
        for j in range(N):
            jj = (j + 1) % N
            x, z = PROF[j]
            mb.face([rings[i][j], rings[i][jj], rings[i + 1][jj], rings[i + 1][j]], "bellows",
                    outward=(x, 0, z - 1.6))


def bogie(mb, by):
    box(mb, (0.0, by, 0.42), (GAUGE + 0.34, 2.3, 0.30), "black")
    for ay in (by - 0.9, by + 0.9):
        for sx in (-1, 1):
            cylinder_x(mb, (sx * (GAUGE / 2 + 0.03), ay, 0.30), 0.30, 0.11, "steel")
            cylinder_x(mb, (sx * (GAUGE / 2 + 0.12), ay, 0.30), 0.12, 0.08, "black", seg=8)


def roof(mb, sec):
    L = sec["len"]
    zr = Z_ROOF - 0.02
    if sec["len"] > 8.0:
        # Dachaufbauten: Klima-/Stromrichtergehäuse (Mitte frei für Stromabnehmer)
        spots = [-L / 2 + 2.3, L / 2 - 2.3] if sec["panto"] else [-L / 2 + 2.6, 0.0, L / 2 - 2.6]
        for cy in spots:
            box(mb, (0.0, cy, zr + 0.17), (1.80, 2.6, 0.34), "grey")
            box(mb, (0.0, cy, zr + 0.36), (1.60, 2.4, 0.06), "grey")
    if sec["panto"]:
        # Einholmstromabnehmer, gehoben bis an den Fahrdraht (5,70 m)
        box(mb, (0.0, 0.0, zr + 0.10), (1.3, 1.6, 0.2), "grey")
        for sx in (-0.55, 0.55):
            box(mb, (sx, 0.0, zr + 0.28), (0.12, 0.12, 0.16), "black")
        top = 5.66
        zb = zr + 0.34
        # Unterarm (Doppelrohr) vom Grundrahmen zum Knie, Oberarm zurück zur Wippe, Kuppelstange
        base = Vector((0.0, -0.55, zb))
        knee = Vector((0.0, 1.05, zb + 1.05))
        head = Vector((0.0, -0.10, top - 0.10))
        for sx in (-0.22, 0.22):
            beam(mb, base + Vector((sx, 0, 0)), knee + Vector((sx * 0.3, 0, 0)), 0.055, "steel")
        beam(mb, knee, head, 0.045, "steel")
        beam(mb, base + Vector((0, 0.25, 0.02)), knee + Vector((0, -0.2, -0.12)), 0.025, "steel")
        beam(mb, (-0.3, -0.55, zb), (0.3, -0.55, zb), 0.08, "steel")
        box(mb, (0.0, -0.55, zb - 0.05), (0.7, 0.3, 0.12), "black")
        # Wippe mit zwei Schleifleisten
        beam(mb, head, head + Vector((0, 0, 0.06)), 0.05, "steel")
        for dy in (-0.14, 0.14):
            beam(mb, (-0.62, head.y + dy, top - 0.01), (0.62, head.y + dy, top - 0.01), 0.04, "steel", 0.06)
            for sx in (-1, 1):
                beam(mb, (sx * 0.62, head.y + dy, top - 0.01), (sx * 0.86, head.y + dy, top - 0.12), 0.03, "steel")
        beam(mb, (0.0, head.y - 0.14, top - 0.04), (0.0, head.y + 0.14, top - 0.04), 0.04, "steel")
        for sx in (-0.45, 0.45):
            box(mb, (sx, 0.0, zr + 0.24), (0.10, 0.10, 0.12), "black")


# ---------------------------------------------------------------------------------------------------------------
y_front = 0.0
for i, sec in enumerate(SECTIONS):
    L = sec["len"]
    yc = y_front - L / 2
    emp = bpy.data.objects.new("Section_%d" % i, None)
    emp.location = (0.0, yc, 0.0)
    bpy.context.collection.objects.link(emp)
    front_fn = r_front if sec["kind"] == "front" else None
    rear_fn = r_rear if sec["kind"] == "rear" else None
    b = body(sec, -L / 2, L / 2, front_fn, rear_fn)
    b.build("Body_%d" % i, emp, recalc=True)
    det = MB()
    # ebener Seitenwandbereich (ohne Kopfrundung)
    y_lo = -L / 2 + (0.62 if rear_fn else 0.12)
    y_hi = L / 2 - (0.72 if front_fn else 0.12)
    disp_y = (L / 2 - 4.3) if sec["kind"] == "front" else None
    for side in (1, -1):
        side_details(det, sec, side, y_lo, y_hi, side in DOOR_SIDES, disp_y if side == 1 else None)
    if front_fn:
        cab_details(det, L / 2)
        n = nose_normal(r_front, L / 2, +1, 0.0, 2.62)
        display_empty(emp, "front", 1.66, 0.28, nose_point(r_front, L / 2, +1, 0.0, 2.62) + n * 0.012, n)
    if rear_fn:
        rear_details(det, -L / 2)
        n = nose_normal(r_rear, -L / 2, -1, 0.0, 2.48)
        display_empty(emp, "rear", 0.66, 0.24, nose_point(r_rear, -L / 2, -1, 0.0, 2.48) + n * 0.012, n)
    if disp_y is not None:
        display_empty(emp, "side", SIDE_DISP_W[0] - 0.04, 0.22, (HW + 0.012, SIDE_DISP_W[1], Z_WTOP - 0.18), (1, 0, 0))
    if i < len(SECTIONS) - 1:
        bellows(det, -L / 2)
    for k, by in enumerate(sec["bogies"]):
        bogie(det, by)
        e2 = bpy.data.objects.new("Bogie_%d_%d" % (i, k), None)
        e2.location = (0.0, by, 0.0)
        e2.parent = emp
        bpy.context.collection.objects.link(e2)
    roof(det, sec)
    det.build("Detail_%d" % i, emp, smooth_angle=30.0)
    y_front -= L + GAP

bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", export_yup=True, export_apply=True)
print("TRAM fertig:", OUT, "Länge %.2f m" % (-y_front - GAP))
