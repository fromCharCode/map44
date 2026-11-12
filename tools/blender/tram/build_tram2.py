"""DVB-Straßenbahnen maßstäblich (prozedural): NGT D12DD (Bombardier Flexity Classic XXL, 45,09 m, 2,30 m breit)
und NGT DX DD (Alstom Flexity, 43,29 m, 2,65 m breit). Maße: data/research/dvb_tram.md (Abschnitt 5).

Ausgabe: GLB mit Knoten Section_0 … Section_4 (Ursprung = Modulmitte; Front = Blender +Y = Godot −Z; z = 0 =
Schienenoberkante). Je Modul Leerknoten Bogie_<i>_<k> an den Drehgestellmitten (tram_unit.gd: zwei Drehgestelle ->
Führung über deren Gleispunkte, eins -> Tangente am Drehgestell, keins -> Sänfte zwischen den Nachbargelenken) und
Display_<art>_<breite cm>_<höhe cm> an den Zielanzeigen (Godot +Z = Anzeigenormale; art: head = Linie+Ziel,
side = Linie+Ziel, lcd = grünes LCD mit dunkler Schrift).
Beide Enden haben einen vollständigen Kopf (Einrichtungswagen mit Hilfsführerstand hinten); Türen nur rechts.

Materialien: TramPaint, TramBlack (glänzend), TramBand (Fensterband), TramBumper, TramWindow (nachts innen hell),
TramWindscreen, TramGrey (Dachgeräte), Bellows, Steel, HeadlightEmit, TaillightEmit, LampOff, TailOff, Blinker,
DisplayEmit, LcdEmit.

Aufruf: flatpak run --filesystem=host org.blender.Blender -b --python build_tram2.py -- <ausgabe.glb> d12dd|dxdd
Keine fremden Modelle/Texturen; Logos/Löwengrafik bewusst weggelassen (Marken).
"""
import bpy, bmesh, sys, math
from mathutils import Vector

ARGS = sys.argv[sys.argv.index("--") + 1:]
OUT = ARGS[0]
TYPE = ARGS[1] if len(ARGS) > 1 else "d12dd"

# ---------------------------------------------------------------------------------------------------------------
# Spezifikationen (x ab Bugspitze nach hinten, z über SO; rechte Seite = Türseite)
SPECS = {
    "d12dd": dict(
        length=45.09,
        section=[(1.15, 0.27), (1.15, 3.05), (1.13, 3.22), (1.06, 3.34), (0.90, 3.42), (0.45, 3.44), (0.0, 3.44)],
        modules=[(0.00, 11.80), (12.22, 17.42), (17.84, 27.24), (27.66, 32.86), (33.28, 45.09)],
        bogies=[3.97, 9.47, 19.80, 25.30, 35.62, 41.12], wheelbase=1.80, bogie_open=False,
        cutouts=[],
        doors=[(1.05, 1.75, 0.38, 2.52, "cab"), (5.55, 7.15, 0.30, 2.65, "double"), (13.75, 15.35, 0.30, 2.65, "double"),
               (21.74, 23.34, 0.30, 2.65, "double"), (29.19, 30.79, 0.30, 2.65, "double"), (37.94, 39.54, 0.30, 2.65, "double")],
        band=(1.25, 2.60), glass=(1.29, 2.56),
        panes=[(1.75, 2.10), (2.15, 3.55), (3.75, 5.30), (7.35, 9.45), (9.60, 11.65), (12.32, 13.65), (15.45, 17.32),
               (17.95, 19.75), (19.85, 21.65), (23.43, 25.23), (25.33, 27.13), (27.76, 29.09), (30.89, 32.76),
               (33.43, 35.48), (35.63, 37.74), (39.79, 41.34), (41.54, 42.94), (42.99, 43.34)],
        head_profile=[(0.00, 0.27), (0.00, 0.60), (0.13, 0.68), (0.15, 0.95), (0.18, 1.16), (0.26, 1.30), (0.40, 2.15),
                      (0.54, 3.08), (0.56, 3.10), (0.70, 3.30), (0.97, 3.42), (1.10, 3.44)],
        head_b=0.10, head_redge=0.16,
        lcd=[(12.32, 13.65), (27.76, 29.09)],
        roof_boxes=[(2.2, 5.3, 1.5, 3.50), (6.0, 8.3, 1.5, 3.49), (18.6, 21.6, 1.6, 3.50), (23.5, 26.5, 1.6, 3.50),
                    (36.8, 39.1, 1.5, 3.49), (39.8, 42.9, 1.5, 3.50)],
        panto_x=9.3, bellows_hw=1.05, gap_rib=0.07,
    ),
    "dxdd": dict(
        length=43.29,
        section=[(1.15, 0.20), (1.325, 0.62), (1.325, 2.50), (1.30, 2.97), (1.27, 3.16), (1.21, 3.27), (1.05, 3.35),
                 (0.55, 3.38), (0.0, 3.38)],
        modules=[(0.00, 12.56), (13.58, 18.74), (19.75, 23.57), (24.57, 29.74), (30.74, 43.29)],
        bogies=[4.21, 10.72, 21.65, 32.57, 39.08], wheelbase=1.85, bogie_open=True,
        cutouts=[(3.2, 5.5), (9.5, 12.0), (20.4, 22.9), (31.3, 33.9), (37.8, 40.1)],
        doors=[(1.46, 2.25, 0.36, 2.51, "cab"), (6.20, 7.76, 0.25, 2.50, "double"), (13.92, 15.48, 0.25, 2.50, "double"),
               (16.84, 18.40, 0.25, 2.50, "double"), (24.90, 26.46, 0.25, 2.50, "double"),
               (27.82, 29.38, 0.25, 2.50, "double"), (34.59, 36.15, 0.25, 2.50, "double")],
        windows=[(2.68, 5.99), (8.92, 12.24), (15.70, 16.63), (20.04, 23.37), (26.69, 27.61), (31.06, 34.38),
                 (37.31, 40.62), (41.15, 41.89)],
        win_z=(1.19, 2.49),
        side_displays=[(3.69, 4.97), (21.05, 22.34), (32.08, 33.36)], side_display_z=(2.09, 2.45),
        head_profile=[(0.03, 0.20), (0.03, 0.47), (0.00, 0.64), (0.02, 0.77), (0.05, 0.90), (0.07, 1.03), (0.10, 1.16),
                      (0.20, 1.35), (0.26, 1.61), (0.31, 1.87), (0.36, 2.13), (0.40, 2.39), (0.46, 2.64), (0.49, 2.77),
                      (0.60, 2.97), (0.66, 3.10), (0.74, 3.16), (0.84, 3.23), (0.99, 3.29), (1.16, 3.36), (1.30, 3.38)],
        head_b=0.12, head_redge=0.22,
        roof_ac=[(5.96, 7.88), (20.70, 22.62), (35.42, 37.34)],
        roof_boxes=[(2.05, 2.47, 1.3, 3.43), (2.78, 3.96, 1.3, 3.43), (4.32, 5.51, 1.3, 3.43), (11.13, 11.61, 1.2, 3.43),
                    (31.70, 34.60, 1.3, 3.43), (37.79, 41.24, 1.3, 3.43)],
        panto_x=10.5, bellows_hw=1.25, gap_rib=0.06,
    ),
}
S = SPECS[TYPE]
LEN = S["length"]
HW = max(p[0] for p in S["section"])
Z_BOT = min(p[1] for p in S["section"])
Z_TOP = max(p[1] for p in S["section"])
ZC = 1.75
GAUGE = 1.450


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
        b.inputs["Coat Roughness"].default_value = 0.06
    if emit:
        b.inputs["Emission Color"].default_value = (*srgb(emit), 1.0)
        b.inputs["Emission Strength"].default_value = 1.0
    return m


bpy.ops.wm.read_factory_settings(use_empty=True)
M = {
    "paint": mat("TramPaint", "#F5B800", rough=0.25, coat=0.7),
    "black": mat("TramBlack", "#111213", rough=0.15, coat=0.5),
    "band": mat("TramBand", "#1E201E", rough=0.3),
    "bumper": mat("TramBumper", "#2F3234", rough=0.5),
    "window": mat("TramWindow", "#2A3236", rough=0.14),
    "screen": mat("TramWindscreen", "#1E2428", rough=0.12),
    "grey": mat("TramGrey", "#CBD0CC", rough=0.5),
    "bellows": mat("Bellows", "#1C1C1C" if TYPE == "d12dd" else "#4A4D50", rough=0.6),
    "steel": mat("Steel", "#5E6064", rough=0.35, metal=1.0),
    "bogie": mat("TramBogie", "#3A3A36", rough=0.7),
    "head": mat("HeadlightEmit", "#F4F1E8", rough=0.1, emit="#FFF6E0"),
    "tail": mat("TaillightEmit", "#7A0A06", rough=0.2, emit="#FF1A0A"),
    "lampoff": mat("LampOff", "#C9CCD0", rough=0.1, metal=0.3),
    "tailoff": mat("TailOff", "#5A0806", rough=0.15),
    "blinker": mat("Blinker", "#D98A10", rough=0.15),
    "disp": mat("DisplayEmit", "#050505", rough=0.25),
    "lcd": mat("LcdEmit", "#9CD27A", rough=0.3, emit="#9CD27A"),
}
MAT_ORDER = list(M.keys())


class MB:
    """Mesh-Bauer: Vertices, Flächen, Material je Fläche."""

    def __init__(self):
        self.v, self.f, self.m = [], [], []

    def vert(self, p):
        self.v.append((float(p[0]), float(p[1]), float(p[2])))
        return len(self.v) - 1

    def face(self, idx, mk, outward=None):
        if outward is not None:
            a, b, c = (Vector(self.v[i]) for i in idx[:3])
            n = (b - a).cross(c - a)
            if n.length < 1e-12 and len(idx) > 3:
                a, b, c = (Vector(self.v[i]) for i in (idx[0], idx[2], idx[3]))
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
        bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-6)
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
        used = set(p.material_index for p in me.polygons)
        for i in reversed(range(len(me.materials))):
            if i not in used:
                me.materials.pop(index=i)      # Blender verschiebt die Flächenindizes selbst
        ob = bpy.data.objects.new(name, me)
        bpy.context.collection.objects.link(ob)
        if parent is not None:
            ob.parent = parent
        return ob


# ---------------------------------------------------------------------------------------------------------------
# Querschnitt
def _right_half():
    """Rechte Hälfte (x >= 0) von unten Mitte nach oben Mitte, Dachkante geglättet."""
    pts = list(S["section"])
    # Chaikin-Glättung oberhalb der Fensteroberkante (gerundete Dachkante), unten scharf
    for _ in range(2):
        out = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            if a[1] < 2.9 and b[1] < 2.9:
                out.append(b)
                continue
            out.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            out.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        out.append(pts[-1])
        # Duplikate entfernen
        pts = [p for i, p in enumerate(out) if i == 0 or math.dist(p, out[i - 1]) > 1e-4]
    # Zwischenpunkte an der Seitenwand (glatte Normalen, Decal-Raster)
    res = [(0.0, Z_BOT), (pts[0][0] - 0.05, Z_BOT)]
    for a, b in zip(pts[:-1], pts[1:]):
        res.append(a)
        if math.dist(a, b) > 0.15:
            n = int(math.ceil(math.dist(a, b) / 0.12))
            for k in range(1, n):
                t = k / n
                res.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    res.append(pts[-1])
    out = []
    for p in res:
        if not out or math.dist(p, out[-1]) > 1e-4:
            out.append(p)
    return out


RIGHT = _right_half()


def hw_at(z):
    """Halbe Breite der Seitenwand auf Höhe z (aus dem Querschnitt)."""
    sec = S["section"]
    if z <= sec[0][1]:
        return sec[0][0]
    for a, b in zip(sec[:-1], sec[1:]):
        if a[1] <= z <= b[1]:
            t = (z - a[1]) / max(b[1] - a[1], 1e-6)
            return a[0] + (b[0] - a[0]) * t
    return sec[-1][0]


def profile(zbot=None, scale=1.0, zc=ZC):
    """Geschlossene Querschnittsschleife (rechts unten -> rechts oben -> links); zbot hebt die Unterkante an
    (Drehgestellausschnitt), scale schrumpft zur Mitte (Faltenbalg/Modulende). Gleiche Punktzahl für alle."""
    half = []
    for x, z in RIGHT[:-1]:
        if zbot is not None and z < zbot:
            x, z = (min(x, hw_at(zbot)) if x > 0.01 else 0.0), zbot
        half.append((x, z))
    top = RIGHT[-1]
    loop = half + [top] + [(-x, z) for x, z in reversed(half[1:])]
    if scale != 1.0:
        loop = [(x * scale, zc + (z - zc) * (1.0 - (1.0 - scale) * 1.6)) for x, z in loop]
    return loop


PROF = profile()


def ray_scale(prof, x, z, cz=ZC):
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
        lam = (ax * ez - (az - cz) * ex) / den
        mu = (ax * dz - (az - cz) * dx) / den
        if lam > 0 and -1e-9 <= mu <= 1 + 1e-9:
            if best is None or lam < best:
                best = lam
    return 1.0 / best if best else 1.0


# Kopfform: Rückversatz r(x, z) gegenüber der Bugspitze (Seitenprofil aus der Recherche + Draufsichtrundung)
HP = sorted(S["head_profile"], key=lambda p: p[1])


def a_head(z):
    if z <= HP[0][1]:
        return HP[0][0]
    for (x0, z0), (x1, z1) in zip(HP[:-1], HP[1:]):
        if z0 <= z <= z1:
            t = (z - z0) / max(z1 - z0, 1e-6)
            return x0 + (x1 - x0) * t
    return HP[-1][0]


def r_head(x, z):
    u = min(abs(x) / max(hw_at(z), 0.3), 1.0)
    return a_head(z) + S["head_b"] * u ** 2.2


S0 = 0.86
RINGS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.68, 0.75, 0.81, 0.86, 0.9, 0.935, 0.962, 0.982, 0.994, 1.0]


def nose_y(x, z, s):
    t = min(max((s - S0) / (1.0 - S0), 0.0), 1.0)
    return r_head(x, z) + S["head_redge"] * (1.0 - math.sqrt(max(1.0 - t * t, 0.0)))


def nose_point(y_tip, sign, x, z):
    s = min(ray_scale(PROF, x, z), 1.0)
    return Vector((x, y_tip - sign * nose_y(x, z, s), z))


def nose_normal(y_tip, sign, x, z):
    e = 0.004
    p = nose_point(y_tip, sign, x, z)
    px = nose_point(y_tip, sign, x + e, z)
    pz = nose_point(y_tip, sign, x, z + e)
    n = (px - p).cross(pz - p)
    if n.dot(Vector((0, sign, 0))) < 0:
        n = -n
    return n.normalized()


def nose_map(y_tip, sign, off):
    def f(u, v):
        return nose_point(y_tip, sign, u, v) + nose_normal(y_tip, sign, u, v) * off
    return f


def side_map(side, off):
    """Seitenwand: u = y (längs, lokal), v = z; folgt dem Querschnitt (Einzug unten/oben)."""
    def f(u, v):
        x = hw_at(v)
        # Normale im Querschnitt (für Abstand auf schrägen Flächen)
        dz = 0.01
        dx = hw_at(v + dz) - hw_at(v - dz)
        n = Vector((2 * dz, -dx)).normalized()
        return Vector((side * (x + off * n.x), u, v + off * n.y))
    return f


# ---------------------------------------------------------------------------------------------------------------
def rrect(cx, cz, w, h, rad, nseg=4):
    rad = min(rad, w * 0.5 - 1e-4, h * 0.5 - 1e-4)
    pts = []
    for (ux, uz, a0) in ((cx + w / 2 - rad, cz - h / 2 + rad, -90), (cx + w / 2 - rad, cz + h / 2 - rad, 0),
                         (cx - w / 2 + rad, cz + h / 2 - rad, 90), (cx - w / 2 + rad, cz - h / 2 + rad, 180)):
        for k in range(nseg + 1):
            a = math.radians(a0 + 90.0 * k / nseg)
            pts.append((ux + rad * math.cos(a), uz + rad * math.sin(a)))
    return pts


def decal(mb, outline, mapf, mk, outward, rings=None, step=0.07, rstep=0.1):
    """Fläche aus Umriss (u, v), fein unterteilt und mit Ringen zur Mitte; mapf(u, v) -> Punkt über der Fläche.
    rings=(1.0,) = ebene Fläche (eine Vieleckfläche, keine Unterteilung)."""
    flat = rings == (1.0,)
    fine = []
    for i in range(len(outline)):
        a, b = outline[i], outline[(i + 1) % len(outline)]
        n_sub = 1 if flat else max(1, int(math.ceil(math.dist(a, b) / step)))
        for k in range(n_sub):
            t = k / n_sub
            fine.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    cu = sum(p[0] for p in outline) / len(outline)
    cv = sum(p[1] for p in outline) / len(outline)
    if not flat and rings is None:
        rmax = max(math.dist(p, (cu, cv)) for p in fine)
        nr = max(2, int(math.ceil(rmax / rstep)))
        rings = tuple(1.0 - k / nr for k in range(nr))
    n = len(fine)
    prev = None
    for s in rings:
        ring = [mb.vert(mapf(cu + s * (u - cu), cv + s * (v - cv))) for u, v in fine]
        if prev is not None:
            for j in range(n):
                k = (j + 1) % n
                mb.face([prev[j], prev[k], ring[k], ring[j]], mk, outward=outward(mb.v[prev[j]]))
        prev = ring
    if flat:
        mb.face(prev, mk, outward=outward(mb.v[prev[0]]))
        return
    c = mb.vert(mapf(cu, cv))
    for j in range(n):
        mb.face([prev[j], prev[(j + 1) % n], c], mk, outward=outward(mb.v[c]))


def circle(cx, cz, r, n=14):
    return [(cx + r * math.cos(2 * math.pi * k / n), cz + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def box(mb, c, size, mk):
    cx, cy, cz = c
    sx, sy, sz = (s / 2 for s in size)
    v = [mb.vert((cx + dx * sx, cy + dy * sy, cz + dz * sz)) for dx in (-1, 1) for dy in (-1, 1) for dz in (-1, 1)]
    def q(a, b, c_, d, o):
        mb.face([v[a], v[b], v[c_], v[d]], mk, outward=o)
    q(0, 1, 3, 2, (-1, 0, 0)); q(4, 6, 7, 5, (1, 0, 0))
    q(0, 4, 5, 1, (0, -1, 0)); q(2, 3, 7, 6, (0, 1, 0))
    q(0, 2, 6, 4, (0, 0, -1)); q(1, 5, 7, 3, (0, 0, 1))


def beam(mb, a, b, th, mk, tw=None):
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


def cylinder_x(mb, c, r, w, mk, seg=16):
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
def body(x0, x1, head_front, head_rear):
    """Wagenkasten eines Moduls (lokal: y = xc - x). Köpfe als Ringflächen, sonst gerundete flache Enden.
    Drehgestellausschnitte (DX DD) über angehobene Unterkante an Zwischenstationen."""
    mb = MB()
    xc = 0.5 * (x0 + x1)
    yf, yr = xc - x0, xc - x1           # vorne (+), hinten (-)
    N = len(PROF)
    # Stationen entlang des Moduls (x, zbot)
    st = [(x0, None), (x1, None)]
    for c0, c1 in S["cutouts"]:
        if c0 > x0 + 0.3 and c1 < x1 - 0.3:
            st += [(c0, None), (c0 + 0.25, 0.63), (c1 - 0.25, 0.63), (c1, None)]
    st.sort()

    def ring_at(x, zb, scale=1.0):
        return [mb.vert((px, xc - x, pz)) for px, pz in profile(zb, scale)]

    def head(y_end, sign):
        c = mb.vert(nose_point(y_end, sign, 0.0, ZC))
        prev = None
        for s in RINGS[1:]:
            ring = []
            for x, z in PROF:
                px, pz = s * x, ZC + s * (z - ZC)
                ring.append(mb.vert((px, y_end - sign * nose_y(px, pz, s), pz)))
            if prev is None:
                for j in range(N):
                    mb.face([c, ring[j], ring[(j + 1) % N]], "paint", outward=(0, sign, 0))
            else:
                for j in range(N):
                    k = (j + 1) % N
                    out = Vector(mb.v[ring[j]]) - Vector((0, y_end - sign * 1.5, ZC))
                    mb.face([prev[j], prev[k], ring[k], ring[j]], "paint", outward=out)
            prev = ring
        return prev

    def flat_end(x, sign):
        """Modulende am Gelenk: kleine Rundung (R ~ 0,15) und dunkle Stirnfläche."""
        y = xc - x
        r_out = ring_at(x - sign * 0.0, None)
        r_mid = [mb.vert((px, y + sign * 0.06, pz)) for px, pz in profile(None, 0.975)]
        r_in = [mb.vert((px, y + sign * 0.10, pz)) for px, pz in profile(None, 0.93)]
        for ra, rb, mk in ((r_out, r_mid, "paint"), (r_mid, r_in, "paint")):
            for j in range(N):
                k = (j + 1) % N
                mb.face([ra[j], ra[k], rb[k], rb[j]], mk, outward=(PROF[j][0], sign, PROF[j][1] - ZC))
        cc = mb.vert((0.0, y + sign * 0.10, ZC))
        for j in range(N):
            mb.face([cc, r_in[j], r_in[(j + 1) % N]], "bellows", outward=(0, sign, 0))
        return r_out

    # Ringe der Stationen (Enden: Kopf oder gerundetes Modulende)
    rings = []
    for i, (x, zb) in enumerate(st):
        if i == 0:
            rings.append(head(yf, +1) if head_front else flat_end(x0, +1))
        elif i == len(st) - 1:
            rings.append(head(yr, -1) if head_rear else flat_end(x1, -1))
        else:
            rings.append(ring_at(x, zb))
    for a, b in zip(rings[:-1], rings[1:]):
        for j in range(N):
            k = (j + 1) % N
            xm = 0.5 * (PROF[j][0] + PROF[k][0])
            zm = 0.5 * (PROF[j][1] + PROF[k][1])
            mb.face([a[j], a[k], b[k], b[j]], "paint", outward=(xm, 0, zm - 1.6))
    return mb


def x2y(x, xc):
    return xc - x


def side_details(mb, xm0, xm1, side, head_f, head_r):
    """Fenster, Türen, Bänder einer Seite des Moduls [xm0, xm1]. side +1 = rechts (Türseite)."""
    xc = 0.5 * (xm0 + xm1)
    out = lambda p: (side, 0, 0)
    s0, s1, s2 = side_map(side, 0.004), side_map(side, 0.008), side_map(side, 0.012)
    lo = xm0 + (0.75 if head_f else 0.08)
    hi = xm1 - (0.75 if head_r else 0.08)
    doors = [d for d in S["doors"] if d[0] >= xm0 - 0.01 and d[1] <= xm1 + 0.01]
    if TYPE == "d12dd":
        z0, z1 = S["band"]
        g0, g1 = S["glass"]
        # schwarzes Fensterband, rechts von den Türportalen unterbrochen
        blocks = [(d[0] - 0.02, d[1] + 0.02) for d in doors] if side == 1 else []
        cur = lo
        for a, b in sorted(blocks) + [(hi, hi)]:
            if a > cur + 0.1:
                decal(mb, rrect(x2y((cur + min(a, hi)) / 2, xc), (z0 + z1) / 2, min(a, hi) - cur, z1 - z0, 0.04), s0,
                      "band", out, rings=(1.0,))
            cur = max(cur, b)
        panes = [p for p in S["panes"] if p[0] >= xm0 and p[1] <= xm1]
        if side == -1:
            # links: Fenster auch an den Türpositionen, hohes Fenster statt Fahrerraumtür
            panes = panes + [(d[0] + 0.08, d[1] - 0.08) for d in doors]
        for a, b in panes:
            decal(mb, rrect(x2y((a + b) / 2, xc), (g0 + g1) / 2, b - a, g1 - g0, 0.05), s1, "window", out, rings=(1.0,))
            # Kippflügel-Fuge
            decal(mb, rrect(x2y((a + b) / 2, xc), 2.25, b - a, 0.018, 0.005), s2, "band", out, rings=(1.0,))
        for i, (lc0, lc1) in enumerate(S.get("lcd", [])):
            if lc0 >= xm0 and lc1 <= xm1 and side == 1:
                cx = (lc0 + lc1) / 2
                decal(mb, rrect(x2y(cx, xc), 2.48, 1.1, 0.16, 0.01), side_map(side, 0.011), "lcd", out, rings=(1.0,))
                display_empty(None, "lcd", 1.1, 0.16, side_map(side, 0.014)(x2y(cx, xc), 2.48), (side, 0, 0), mb_parent=True)
        if side == 1:
            for x0, x1, dz0, dz1, typ in doors:
                cx = x2y((x0 + x1) / 2, xc)
                w = x1 - x0
                decal(mb, rrect(cx, (dz0 + dz1) / 2, w, dz1 - dz0, 0.06), s0, "band", out, rings=(1.0,))
                if typ == "cab":
                    decal(mb, rrect(cx, (dz0 + dz1) / 2, w - 0.08, dz1 - dz0 - 0.08, 0.05), s1, "paint", out, rings=(1.0,))
                    decal(mb, rrect(cx, 1.85, w - 0.2, 1.2, 0.06), s2, "window", out, rings=(1.0,))
                    continue
                lw = (w - 0.12) / 2
                for k in (-1, 1):
                    lx = cx + k * (lw / 2 + 0.01)
                    decal(mb, rrect(lx, (dz0 + dz1) / 2, lw - 0.02, dz1 - dz0 - 0.10, 0.04), s1, "paint", out, rings=(1.0,))
                    decal(mb, rrect(lx, 1.52, 0.50, 1.70, 0.249, 6), s2, "window", out, rings=(1.0,))
    else:
        wz0, wz1 = S["win_z"]
        wins = [w for w in S["windows"] if w[0] >= xm0 - 0.01 and w[1] <= xm1 + 0.01]
        if side == -1:
            wins = wins + [(d[0] + 0.05, d[1] - 0.05) for d in doors]
        for a, b in wins:
            cx = x2y((a + b) / 2, xc)
            decal(mb, rrect(cx, (wz0 + wz1) / 2, b - a, wz1 - wz0, 0.10), s0, "black", out, rings=(1.0,))
            decal(mb, rrect(cx, (wz0 + wz1) / 2, b - a - 0.12, wz1 - wz0 - 0.12, 0.07), s1, "window", out, rings=(1.0,))
        dz0, dz1 = S["side_display_z"]
        for a, b in S["side_displays"]:
            if a >= xm0 and b <= xm1:
                cx = x2y((a + b) / 2, xc)
                decal(mb, rrect(cx, (dz0 + dz1) / 2, b - a, dz1 - dz0, 0.02), s2, "disp", out, rings=(1.0,))
                display_empty(None, "side", b - a - 0.04, dz1 - dz0 - 0.03, side_map(side, 0.016)(cx, (dz0 + dz1) / 2),
                              (side, 0, 0), mb_parent=True)
        if side == 1:
            for x0, x1, dz0_, dz1_, typ in doors:
                cx = x2y((x0 + x1) / 2, xc)
                w = x1 - x0
                # Portal schwarz: oberer, senkrechter Teil und Trapez auf der Einzugsschräge
                decal(mb, rrect(cx, (0.62 + dz1_) / 2, w, dz1_ - 0.62, 0.10), s0, "black", out, rings=(1.0,))
                lo_pts = [(cx - w / 2 + 0.10, dz0_), (cx + w / 2 - 0.10, dz0_), (cx + w / 2, 0.62), (cx - w / 2, 0.62)]
                decal(mb, lo_pts, s0, "black", out, rings=(1.0,))
                if typ == "cab":
                    decal(mb, rrect(cx, 1.80, w - 0.14, 0.89, 0.06), s1, "window", out, rings=(1.0,))
                    continue
                for k in (-1, 1):
                    lx = cx + k * (w / 4)
                    decal(mb, rrect(lx, 1.77, 0.52, 0.96, 0.05), s1, "window", out, rings=(1.0,))
                    decal(mb, rrect(lx, 0.875, 0.52, 0.51, 0.04), s1, "window", out, rings=(1.0,))


PENDING_DISPLAYS = []


def display_empty(parent, kind, w, h, pos, normal, mb_parent=False):
    """Leerknoten Display_<art>_<cm>_<cm>; Godot +Z (= Blender lokal -Y) entlang der Normale."""
    PENDING_DISPLAYS.append((kind, w, h, Vector(pos), Vector(normal)))


def head_details(mb, y_tip, sign, front):
    """Kopf: Scheibe, Haube/Dachkappe, Zielanzeige, Leuchten, Stoßfänger. front = in Fahrtrichtung vorn."""
    o = lambda p: (0, sign, 0)
    # starke Wölbung an den Kopfecken: Aufkleber fein unterteilt und mit 1-2 cm Abstand (sonst schneiden die
    # Sehnen in den Wagenkasten und der Lack scheint durch)
    nm = lambda off: nose_map(y_tip, sign, off * 2.5 + 0.002)

    def hdecal(mb_, outline, mapf, mk, outward, rings=None, step=0.05, rstep=0.045):
        # Ringe dicht am Rand (dort liegt die starke Kopfrundung), zur Mitte grob: ~5x weniger Dreiecke
        rr = (1.0, 0.985, 0.965, 0.94, 0.905, 0.86, 0.8, 0.72, 0.62, 0.5, 0.36, 0.2)
        decal(mb_, outline, mapf, mk, outward, rings=rr, step=step, rstep=rstep)
    W = 2 * HW
    white = "head" if front else "lampoff"
    red = "tailoff" if front else "tail"
    if TYPE == "d12dd":
        # Frontscheibe (um die Ecken gezogen), oberes Drittel schwarz bedruckt, Dachkappe schwarz mit Leuchte
        hdecal(mb, rrect(0.0, 2.20, W - 0.04, 1.80, 0.16, 6), nm(0.004), "band", o)
        hdecal(mb, rrect(0.0, 1.95, W - 0.16, 1.42, 0.14, 6), nm(0.008), "screen", o)
        hdecal(mb, rrect(0.0, 3.27, W - 0.02, 0.34, 0.12, 6), nm(0.004), "black", o)
        hdecal(mb, circle(0.0, 3.30, 0.10), nm(0.009), white, o)
        hdecal(mb, rrect(0.0, 2.91, 1.36, 0.28, 0.03), nm(0.012), "disp", o, rings=(1.0, 0.5))
        dn = nose_normal(y_tip, sign, 0.0, 2.91)
        display_empty(None, "head", 1.30, 0.24, nose_point(y_tip, sign, 0.0, 2.91) + dn * 0.042, dn)
        for sx in (-1, 1):
            hdecal(mb, circle(sx * 0.63, 0.98, 0.09), nm(0.008), white, o)
            hdecal(mb, circle(sx * 0.63, 0.78, 0.07), nm(0.008), red, o)
            hdecal(mb, rrect(sx * 0.95, 1.06, 0.12, 0.20, 0.03), nm(0.008), "blinker", o)
            hdecal(mb, rrect(sx * 0.95, 0.84, 0.12, 0.20, 0.03), nm(0.008), red, o)
        hdecal(mb, rrect(0.0, 0.465, W - 0.02, 0.37, 0.05), nm(0.005), "bumper", o)
        if front:
            # Außenspiegel
            for sx in (-1, 1):
                base = nose_point(y_tip, sign, sx * (HW - 0.02), 2.45)
                tipp = base + Vector((sx * 0.32, -sign * 0.10, 0.0))
                beam(mb, base, tipp, 0.04, "black")
                box(mb, (tipp.x, tipp.y, 2.56), (0.07, 0.16, 0.42), "black")
    else:
        # schwarzer Glasbereich (mit A-Säulen), große Scheibe, Siebdruckband, Haube, Anzeige, Leuchten
        hdecal(mb, rrect(0.0, 2.01, W - 0.04, 1.70, 0.18, 6), nm(0.004), "black", o)
        hdecal(mb, rrect(0.0, 2.01, 1.95, 1.62, 0.14, 6), nm(0.008), "screen", o)
        hdecal(mb, rrect(0.0, 1.32, 1.95, 0.30, 0.06), nm(0.011), "black", o)
        hdecal(mb, rrect(0.0, 3.13, W - 0.02, 0.56, 0.16, 6), nm(0.004), "black", o)
        hdecal(mb, rrect(0.0, 3.00, 0.25, 0.08, 0.02), nm(0.009), white if front else "tail", o, rings=(1.0, 0.5))
        hdecal(mb, rrect(0.0, 2.675, 1.50, 0.27, 0.03), nm(0.012), "disp", o, rings=(1.0, 0.5))
        dn = nose_normal(y_tip, sign, 0.0, 2.675)
        display_empty(None, "head", 1.45, 0.23, nose_point(y_tip, sign, 0.0, 2.675) + dn * 0.042, dn)
        for sx in (-1, 1):
            hdecal(mb, [(sx * 0.55, 0.95), (sx * 0.85, 0.99), (sx * 0.85, 1.02), (sx * 0.55, 0.98)], nm(0.008),
                  "blinker" if front else red, o, rings=(1.0, 0.5))
            hdecal(mb, rrect(sx * 0.70, 0.90, 0.28, 0.05, 0.02), nm(0.008), white if front else red, o, rings=(1.0, 0.5))
            hdecal(mb, circle(sx * 1.00, 0.86, 0.06), nm(0.008), white if front else "tail", o)
        hdecal(mb, rrect(0.0, 0.335, W - 0.02, 0.27, 0.05), nm(0.005), "black", o)


def bellows(mb, y_from, gap, hw_b):
    """Faltenbalg: gerippter, eingezogener Ring über die Gelenklücke (lokal von y_from nach hinten)."""
    sc0 = hw_b / HW
    k = max(4, int(gap / S["gap_rib"]))
    rings = []
    for i in range(k + 1):
        y = y_from - gap * i / k
        sc = sc0 if i % 2 == 0 else sc0 - 0.025
        rings.append([mb.vert((x, y, z)) for x, z in profile(max(Z_BOT, 0.30), sc)])
    N = len(rings[0])
    for i in range(k):
        for j in range(N):
            jj = (j + 1) % N
            x, z = PROF[j]
            mb.face([rings[i][j], rings[i][jj], rings[i + 1][jj], rings[i + 1][j]], "bellows", outward=(x, 0, z - 1.6))


def bogie(mb, by):
    r = 0.30
    wb = S["wheelbase"]
    for ay in (by - wb / 2, by + wb / 2):
        for sx in (-1, 1):
            cylinder_x(mb, (sx * (GAUGE / 2 + 0.035), ay, r), r, 0.12, "steel")
            if S["bogie_open"]:
                cylinder_x(mb, (sx * (GAUGE / 2 + 0.16), ay, r), 0.22, 0.12, "bogie", seg=10)    # Bremsscheibe/Nabe
    box(mb, (0.0, by, 0.50), (GAUGE + 0.10, wb + 0.7, 0.22), "bogie")
    if S["bogie_open"]:
        # Motor-Getriebe-Blöcke außen
        for sx in (-1, 1):
            box(mb, (sx * (GAUGE / 2 + 0.33), by, 0.40), (0.26, wb - 0.2, 0.34), "bogie")


def roof(mb, x0, x1):
    xc = 0.5 * (x0 + x1)
    for a, b, w, top in S.get("roof_boxes", []):
        if a >= x0 and b <= x1:
            zr = Z_TOP - 0.03
            box(mb, (0.0, x2y((a + b) / 2, xc), (zr + top) / 2), (w, b - a, top - zr), "grey")
    for a, b in S.get("roof_ac", []):
        if a >= x0 and b <= x1:
            zr = Z_TOP - 0.03
            box(mb, (0.0, x2y((a + b) / 2, xc), (zr + 3.50) / 2), (1.70, b - a, 3.50 - zr), "grey")
            box(mb, (0.0, x2y((a + b) / 2, xc), 3.50), (1.50, b - a - 0.2, 0.03), "grey")
    px = S["panto_x"]
    if x0 < px < x1:
        zr = Z_TOP - 0.02
        yb = x2y(px, xc)
        top = 5.66
        box(mb, (0.0, yb, zr + 0.06), (1.2, 1.4, 0.12), "grey")
        for sx in (-0.5, 0.5):
            box(mb, (sx, yb, zr + 0.18), (0.10, 0.10, 0.14), "black")
        zb = zr + 0.28
        base = Vector((0.0, yb, zb))
        knee = Vector((0.0, yb + 0.9, 4.2))          # Knie nach vorn
        head = Vector((0.0, yb - 0.9, top - 0.10))
        for sx in (-0.22, 0.22):
            beam(mb, base + Vector((sx, 0, 0)), knee + Vector((sx * 0.3, 0, 0)), 0.055, "steel")
        beam(mb, knee, head, 0.045, "steel")
        beam(mb, base + Vector((0, -0.25, 0.02)), knee + Vector((0, 0.2, -0.12)), 0.025, "steel")
        beam(mb, (-0.3, yb, zb), (0.3, yb, zb), 0.08, "steel")
        beam(mb, head, head + Vector((0, 0, 0.06)), 0.05, "steel")
        for dy in (-0.14, 0.14):
            beam(mb, (-0.62, head.y + dy, top - 0.01), (0.62, head.y + dy, top - 0.01), 0.04, "steel", 0.06)
            for sx in (-1, 1):
                beam(mb, (sx * 0.62, head.y + dy, top - 0.01), (sx * 0.86, head.y + dy, top - 0.12), 0.03, "black")
        beam(mb, (0.0, head.y - 0.14, top - 0.04), (0.0, head.y + 0.14, top - 0.04), 0.04, "steel")


# ---------------------------------------------------------------------------------------------------------------
mods = S["modules"]
for i, (x0, x1) in enumerate(mods):
    xc = 0.5 * (x0 + x1)
    emp = bpy.data.objects.new("Section_%d" % i, None)
    emp.location = (0.0, -xc, 0.0)
    bpy.context.collection.objects.link(emp)
    hf, hr = i == 0, i == len(mods) - 1
    body(x0, x1, hf, hr).build("Body_%d" % i, emp, recalc=True)
    det = MB()
    PENDING_DISPLAYS.clear()
    for side in (1, -1):
        side_details(det, x0, x1, side, hf, hr)
    if hf:
        head_details(det, xc - x0, +1, True)
    if hr:
        head_details(det, xc - x1, -1, False)
    if i < len(mods) - 1:
        gap = mods[i + 1][0] - x1
        bellows(det, xc - x1, gap, S["bellows_hw"])
    k = 0
    for bx in S["bogies"]:
        if x0 < bx < x1:
            bogie(det, x2y(bx, xc))
            e2 = bpy.data.objects.new("Bogie_%d_%d" % (i, k), None)
            e2.location = (0.0, x2y(bx, xc), 0.0)
            e2.parent = emp
            bpy.context.collection.objects.link(e2)
            k += 1
    roof(det, x0, x1)
    det.build("Detail_%d" % i, emp, smooth_angle=30.0)
    for kind, w, h, pos, nrm in PENDING_DISPLAYS:
        e = bpy.data.objects.new("Display_%s_%d_%d" % (kind, round(w * 100), round(h * 100)), None)
        e.location = pos
        e.rotation_mode = "QUATERNION"
        e.rotation_quaternion = nrm.normalized().to_track_quat("-Y", "Z")
        e.parent = emp
        bpy.context.collection.objects.link(e)

bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", export_yup=True, export_apply=True)
print("TRAM %s fertig: %s, Länge %.2f m" % (TYPE, OUT, mods[-1][1]))
