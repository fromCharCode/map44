"""Bausteine für prozedurale, moderne Pkw-Modelle (Blender 5.x, headless) – wird von cars_build.py benutzt.

Aufbau einer Karosserie
-----------------------
Die Außenhaut ist ein Gitter aus Spanten („Stationen“, Abstand d von der Fahrzeugspitze) und 15 festen
Zeilen je Fahrzeughälfte:

    0      Rücksprung unter Schweller / Radlaufkante
    1..5   Seitenwand vom Schweller bis zur Schulterlinie (Zeile 5)
    6      Gürtellinie (Fensterunterkante bzw. Haubenkante)
    7      Scheibenunterkante       (vor/hinter der Kabine: Haubenrand)
    8      Scheibenoberkante/Dachholm
    9,10   Dachholm-Rundung
    11..14 Dach bis zur Mitte       (vor/hinter der Kabine: Haube/Heckdeckel)

Zwischen „Deck-Lage“ (Haube/Kofferraum) und „Dach-Lage“ wird über Front- und Heckscheibe überblendet;
so entstehen A-/C-Säule und die Scheibenflächen als saubere Gitterstreifen. Bug und Heck laufen über eine
Superellipse im Grundriss zusammen. Radläufe heben die Unterkante der Seitenwand an (Kreisbogen) und
stellen die Kante leicht aus.

Details (Leuchten, Grill, Fugen, Kennzeichen …) sind dünne Flicken, die auf die fertige Haut gelegt
werden (BVH: nächster Punkt + kleiner Abstand entlang der Normale).

Koordinaten in Blender: +Y = vorn, +X = rechts, +Z = oben, Ursprung am Boden mittig zwischen den Achsen.
Der glTF-Export (Y-up) macht daraus die Spielkonvention: Fahrzeug schaut nach −Z, rechts = +X.
"""
from __future__ import annotations

import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CARS = os.path.join(ROOT, "godot", "assets", "models", "cars")
PREV = os.path.join(CARS, "previews")


# --------------------------------------------------------------------------------------------------
# Kleine Mathehelfer
# --------------------------------------------------------------------------------------------------
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def lerp(a, b, t):
    return a + (b - a) * t


def sstep(a, b, x):
    if a == b:
        return 0.0 if x < a else 1.0
    t = clamp((x - a) / (b - a))
    return t * t * (3.0 - 2.0 * t)


def pchip(pts):
    """Monotone kubische Interpolation durch (x, y)-Stützpunkte; außerhalb konstant."""
    pts = sorted(pts)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    n = len(xs)
    if n == 1:
        return lambda x: ys[0]
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    dl = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    m[0], m[-1] = dl[0], dl[-1]
    for i in range(1, n - 1):
        if dl[i - 1] * dl[i] > 0:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / dl[i - 1] + w2 / dl[i])

    def f(x):
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        i = 0
        while x > xs[i + 1]:
            i += 1
        t = (x - xs[i]) / h[i]
        t2, t3 = t * t, t * t * t
        return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h[i] * m[i]
                + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h[i] * m[i + 1])
    return f


def srgb(hexstr, a=1.0):
    """'#RRGGBB' (sRGB) -> lineares RGBA für Principled/glTF."""
    hexstr = hexstr.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(hexstr[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (out[0], out[1], out[2], a)


# --------------------------------------------------------------------------------------------------
# Materialien – Namen wie in den vorhandenen Fahrzeug-GLBs (car_model.gd wertet sie aus)
# --------------------------------------------------------------------------------------------------
MAT_DEFS = {
    "CarPaint":       dict(col="#8A8D93", metal=0.40, rough=0.30, coat=1.0),
    "PlasticBlack":   dict(col="#19191A", rough=0.55),
    "BlackGloss":     dict(col="#0A0B0D", rough=0.08),
    "Chrome":         dict(col="#DCDDE2", metal=1.0, rough=0.10),
    "Plate":          dict(col="#EEEEEA", rough=0.45),
    "PlateBlue":      dict(col="#0F3BA0", rough=0.5),
    "Glass":          dict(col="#1A2125", rough=0.02, alpha=0.25),
    "Interior":       dict(col="#232325", rough=0.9),
    "InteriorSeat":   dict(col="#3A3836", rough=0.85),
    "HeadlightEmit":  dict(col="#C8D3DF", metal=0.2, rough=0.05),
    "IndicatorEmit":  dict(col="#DA6408", rough=0.10),
    "TaillightEmit":  dict(col="#74080C", rough=0.10),
    "BrakeLightEmit": dict(col="#9C0C0C", rough=0.10),
    "TaxiSignEmit":   dict(col="#F7C20A", rough=0.40),
    "Rim":            dict(col="#9FA3AA", metal=1.0, rough=0.28),
    "BrakeDisc":      dict(col="#5A5855", metal=1.0, rough=0.5),
    "Rubber":         dict(col="#121212", rough=0.85),
}


def make_materials(overrides=None):
    mats = {}
    for name, d0 in MAT_DEFS.items():
        d = dict(d0)
        d.update((overrides or {}).get(name, {}))
        m = bpy.data.materials.new(name)
        try:
            m.use_nodes = True
        except Exception:
            pass
        bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        col = srgb(d["col"])
        bsdf.inputs["Base Color"].default_value = col
        bsdf.inputs["Roughness"].default_value = d.get("rough", 0.5)
        bsdf.inputs["Metallic"].default_value = d.get("metal", 0.0)
        if d.get("coat"):
            bsdf.inputs["Coat Weight"].default_value = d["coat"]
            bsdf.inputs["Coat Roughness"].default_value = 0.04
        if d.get("alpha") is not None:
            bsdf.inputs["Alpha"].default_value = d["alpha"]
            m.surface_render_method = "BLENDED"
        m.use_backface_culling = False          # doubleSided wie bei den alten Modellen
        m.diffuse_color = col
        mats[name] = m
    return mats


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


# --------------------------------------------------------------------------------------------------
# Netz-Sammler
# --------------------------------------------------------------------------------------------------
class MeshB:
    def __init__(self, name, mats, bm=None):
        self.name = name
        self.mats = mats
        self.bm = bm or bmesh.new()
        self.slots = []

    def mi(self, mat):
        if mat not in self.slots:
            self.slots.append(mat)
        return self.slots.index(mat)

    def face(self, pts, mat, smooth=True):
        vs = []
        for p in pts:
            v = p if isinstance(p, bmesh.types.BMVert) else self.bm.verts.new(p)
            if v not in vs:
                vs.append(v)
        if len(vs) < 3:
            return None
        try:
            f = self.bm.faces.new(vs)
        except ValueError:
            return None
        f.material_index = self.mi(mat)
        f.smooth = smooth
        return f

    def grid(self, G, mat, smooth=True, flip=False):
        """G[i][j] = Punkt. Erzeugt Vierecke mit gemeinsamen Ecken."""
        V = [[self.bm.verts.new(p) for p in row] for row in G]
        fs = []
        for i in range(len(V) - 1):
            for j in range(len(V[i]) - 1):
                q = [V[i][j], V[i + 1][j], V[i + 1][j + 1], V[i][j + 1]]
                if flip:
                    q.reverse()
                f = self.face(q, mat, smooth)
                if f:
                    fs.append(f)
        return fs

    def box(self, c, size, mat, M=None, taper=1.0):
        """Quader um c; M = optionale Drehmatrix (3x3); taper staucht die Oberseite in x."""
        sx, sy, sz = size[0] / 2, size[1] / 2, size[2] / 2
        c = Vector(c)
        vs = []
        for dz in (-1, 1):
            t = taper if dz > 0 else 1.0
            for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = Vector((dx * sx * t, dy * sy, dz * sz))
                if M is not None:
                    p = M @ p
                vs.append(self.bm.verts.new(c + p))
        for q in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            self.face([vs[i] for i in q], mat, smooth=False)

    def lathe(self, prof, nseg, mats, M=None, close=True):
        """Rotationskörper um die lokale X-Achse. prof = [(x, radius)], mats = Name oder Liste je Streifen."""
        rings = []
        for x, r in prof:
            ring = []
            for k in range(nseg):
                a = 2 * math.pi * k / nseg
                p = Vector((x, r * math.cos(a), r * math.sin(a)))
                if M is not None:
                    p = M @ p
                ring.append(self.bm.verts.new(p))
            rings.append(ring)
        for i in range(len(rings) - 1):
            m = mats if isinstance(mats, str) else mats[i]
            for k in range(nseg):
                k2 = (k + 1) % nseg
                self.face([rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]], m)
        return rings

    def disc(self, x, r, nseg, mat, M=None, flip=False):
        vs = []
        for k in range(nseg):
            a = 2 * math.pi * k / nseg
            p = Vector((x, r * math.cos(a), r * math.sin(a)))
            if M is not None:
                p = M @ p
            vs.append(self.bm.verts.new(p))
        if flip:
            vs.reverse()
        return self.face(vs, mat, smooth=False)

    def tris(self):
        return sum(len(f.verts) - 2 for f in self.bm.faces)

    def finish(self, sharp_deg=50.0, recalc=False, uv=False):
        bm = self.bm
        if recalc:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.normal_update()
        if sharp_deg is not None:
            lim = math.radians(sharp_deg)
            for e in bm.edges:
                if len(e.link_faces) == 2 and not e.tag:
                    try:
                        if e.calc_face_angle() > lim:
                            e.smooth = False
                    except ValueError:
                        pass
        if uv:                                           # einfache Seitenprojektion (wie die alten Modelle: TEXCOORD_0)
            lay = bm.loops.layers.uv.new("UVMap")
            for f in bm.faces:
                for lp in f.loops:
                    lp[lay].uv = (lp.vert.co.y / 6.0 + 0.5, lp.vert.co.z / 2.5)
        me = bpy.data.meshes.new(self.name)
        bm.to_mesh(me)
        bm.free()
        for s in self.slots:
            me.materials.append(self.mats[s])
        ob = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(ob)
        return ob


# --------------------------------------------------------------------------------------------------
# Karosserie
# --------------------------------------------------------------------------------------------------
DECK_F = (0.975, 0.95, 0.915, 0.86, 0.66, 0.44, 0.22, 0.0)        # Zeilen 7..14 als Anteil der Gürtelbreite
ROOF_F = (0.72, 0.48, 0.24, 0.0)                                   # Zeilen 11..14 als Anteil der Dachbreite
BOW_W = (1.0, 0.96, 0.86, 0.86 * 0.72 ** 2, 0.86 * 0.48 ** 2, 0.86 * 0.24 ** 2, 0.0)
EDGE_SET = (0.012, 0.028, 0.048, 0.075)                            # Zeilen 7..10: Rundung der Haubenvorderkante

REG_PAINT, REG_PLASTIC, REG_GLOSS, REG_CHROME = 0, 1, 2, 3
REG_WS, REG_RW = 10, 11                                            # Front-/Heckscheibe; 20+n / 40+n Seitenscheiben
REG_MAT = {0: "CarPaint", 1: "PlasticBlack", 2: "BlackGloss", 3: "Chrome"}

DEFAULTS = dict(
    gc=0.17, arch_gap=0.045, flare=0.018, tuck=0.035, belt_inset=0.04, rail_drop=0.075, rc=0.03,
    roll=0.026, Rs=0.45, Rn=0.55, nn=2.8, Rt=0.5, nt=3.2,
    ws_pow=1.25, rw_pow=1.3, ws_bow=0.09, rw_bow=0.06,
    e_nose=(0.09, 0.03, 0.0, 0.0, 0.012, 0.035, 0.085), e_tail=(0.10, 0.04, 0.0, 0.0, 0.01, 0.025, 0.05),
    row_t=(0.0, 0.24, 0.5, 0.77, 1.0), clad=0, pano=None, roof_black=False, chrome_trim=False,
    rear_glass=True, crease=True, seat_rows=2, cargo=False, tail_edge=1.0, seat_lift=0.0,
)


class Car:
    def __init__(self, spec):
        self.__dict__.update(DEFAULTS)
        self.__dict__.update(spec)
        self.W_nominal = self.W
        self.W = self.W - 2 * self.flare                # Nennbreite gilt über die ausgestellten Radläufe
        self.yf = self.wb / 2 + self.fo                 # Blender-y der Fahrzeugspitze
        self.axles = (self.fo, self.fo + self.wb)
        self.Ra = self.rw + self.arch_gap
        self.zca = self.rw + 0.01                       # Mittelpunktshöhe des Radlaufbogens
        self.f_belt = pchip(self.belt)
        self.f_roof = pchip(self.roof)
        self.f_low = pchip(self.low)
        self.f_taper = pchip(self.taper)
        self.f_sh = pchip(self.shoulder)
        self.f_tumble = pchip(self.tumble)
        self.f_crown = pchip(self.crown)
        self.x_well = self.track / 2 - self.tw / 2 - 0.07   # Innenwand der Radhäuser
        self._perim = None
        self.bvh = None

    # ---- Grundfunktionen über d (Abstand von der Spitze) ----
    def plan(self, d):
        if d < self.Rn:
            t = clamp(1.0 - d / self.Rn)
            return (1.0 - t ** self.nn) ** (1.0 / self.nn)
        if d > self.L - self.Rt:
            t = clamp(1.0 - (self.L - d) / self.Rt)
            return (1.0 - t ** self.nt) ** (1.0 / self.nt)
        return 1.0

    def z_arch(self, d):
        for dc in self.axles:
            q = self.Ra ** 2 - (d - dc) ** 2
            if q > 0:
                return self.zca + math.sqrt(q)
        return -1.0

    def u(self, d):
        if d <= self.d_cowl or d >= self.d_bl:
            return 0.0
        if d < self.d_head:
            t = (d - self.d_cowl) / (self.d_head - self.d_cowl)
            return 1.0 - (1.0 - t) ** self.ws_pow
        if d <= self.d_rend:
            return 1.0
        t = (self.d_bl - d) / (self.d_bl - self.d_rend)
        return 1.0 - (1.0 - t) ** self.rw_pow

    def half_section(self, d):
        """15 Punkte (x >= 0, d_verschoben, z) der rechten Hälfte, Zeile 0..14."""
        pl = self.plan(d)
        wt = self.W * 0.5 * self.f_taper(d)
        zb = self.f_belt(d)
        zl0 = self.f_low(d)
        za = self.z_arch(d)
        zl = max(zl0, za)
        an = clamp((za - zl0) / 0.08)
        zs = max(zb - self.f_sh(d), zl + 0.07)
        span = zs - zl
        ins = (self.tuck * (1 - an), 0.012 * (1 - an), 0.0, 0.004, 0.012)
        pts = []
        for j in range(5):
            z = zl + self.row_t[j] * span
            if j == 1:
                z = max(z, zl + min(0.045, 0.4 * span))
            fl = self.flare * an * math.exp(-((z - zl) / 0.075) ** 2)
            pts.append(((wt - ins[j] + fl) * pl, z))
        pts.insert(0, (pts[0][0] - 0.05 * pl, pts[0][1]))
        x6 = (wt - self.belt_inset) * pl
        pts.append((x6, zb))
        cr = self.f_crown(d)
        zc = self.f_roof(d)
        rc = self.rc
        x8 = x6 - self.f_tumble(d) * pl
        x10 = x8 - 0.09
        R = [(x6 - 0.004 * pl, zb + 0.012), (x8, zc - rc - self.rail_drop), (x8 - 0.03, zc - rc - 0.03),
             (x10, zc - rc - 0.004)] + [(x10 * f, zc - rc * f * f) for f in ROOF_F]
        u = self.u(d)
        for k, f in enumerate(DECK_F):
            s = clamp((1.0 - f) / 0.14)
            dz = self.roll * math.sqrt(max(0.0, 1.0 - (1.0 - s) ** 2)) + cr * (1.0 - f ** 2.2)
            pts.append((lerp(f * x6, R[k][0], u), lerp(zb + dz, R[k][1], u)))
        fn = clamp(1.0 - d / self.Rs) ** 2
        ft = clamp(1.0 - (self.L - d) / self.Rs) ** 2
        bws = sstep(self.d_cowl - 0.4, self.d_cowl, d) * (1.0 - sstep(self.d_head, self.d_head + 0.35, d))
        brw = sstep(self.d_rend - 0.35, self.d_rend, d) * (1.0 - sstep(self.d_bl, self.d_bl + 0.3, d))
        out = []
        for j, (x, z) in enumerate(pts):
            e = min(j, 6)
            en, et = self.e_nose[e], self.e_tail[e]
            if j >= 7:
                ex = EDGE_SET[min(j - 7, 3)]
                en += ex
                et += ex * self.tail_edge
            dd = d + en * fn - et * ft
            if j >= 8:
                dd += (self.ws_bow * bws - self.rw_bow * brw) * BOW_W[j - 8]
            out.append((max(x, 0.0), dd, z))
        return out

    def pt(self, d, j, side=1):
        x, dd, z = self.half_section(d)[j]
        return Vector((side * x, self.yf - dd, z))

    # ---- Stationen ----
    def stations(self):
        S = []                                           # (d, Rang)
        kn = 10
        for k in range(kn + 1):
            th = k / kn * math.pi / 2
            S.append((self.Rn * (1.0 - math.cos(th) ** (2.0 / self.nn)), 2))
            S.append((self.L - self.Rt * (1.0 - math.cos(th) ** (2.0 / self.nt)), 2))
        keys = [self.d_cowl, self.d_head, self.d_rend, self.d_bl]
        for a, b in self.sw:
            keys += [a, b]
        if self.pano:
            keys += list(self.pano)
        keys += list(getattr(self, "extra_stations", ()))
        S += [(k, 3) for k in keys]
        nws = 5
        for k in range(1, nws):
            S.append((lerp(self.d_cowl, self.d_head, k / nws), 1))
        nrw = max(2, min(5, int(round((self.d_bl - self.d_rend) / 0.14))))
        for k in range(1, nrw):
            S.append((lerp(self.d_rend, self.d_bl, k / nrw), 1))
        na = 12
        for dc in self.axles:
            lo = max(self.f_low(dc - self.Ra), self.f_low(dc + self.Ra), self.gc)
            ph0 = math.asin(clamp((lo - self.zca) / self.Ra, -1, 1))
            for k in range(na + 1):
                ph = lerp(ph0, math.pi - ph0, k / na)
                S.append((dc - self.Ra * math.cos(ph), 1))
        S.sort()
        hard = [d for d, r in S if r >= 2]
        out = []
        for d, r in S:
            if r >= 2:
                if not out or d - out[-1][0] > 1e-5:
                    out.append((d, r))
                continue
            if any(abs(d - h) < 0.025 for h in hard):
                continue
            if out and out[-1][1] < 2 and d - out[-1][0] < 0.02:
                continue
            out.append((d, r))
        ds = [o[0] for o in out]
        full = [ds[0]]
        for d in ds[1:]:
            prev = full[-1]
            n = int(math.ceil((d - prev) / 0.24))
            for k in range(1, n):
                full.append(lerp(prev, d, k / n))
            full.append(d)
        self.key_d = sorted(set(round(k, 4) for k in keys))
        return full

    # ---- Flächenbereiche ----
    def region(self, d, k, side):
        in_cab = self.d_cowl < d < self.d_bl
        if k >= 10:
            if self.d_cowl < d < self.d_head:
                return REG_WS
            if self.d_rend < d < self.d_bl and self.rear_glass:
                return REG_RW
            if self.pano and k >= 11 and self.pano[0] < d < self.pano[1]:
                return REG_GLOSS
        if self.roof_black and k >= 8 and in_cab:
            return REG_GLOSS
        if k == 7:
            for n, (a, b) in enumerate(self.sw):
                if a < d < b:
                    return 20 + n + (0 if side < 0 else 20)
            if self.d_cowl < d < self.sw[-1][1]:
                return REG_GLOSS
        if k == 6 and self.d_cowl < d < self.sw[-1][1]:
            return REG_CHROME if self.chrome_trim else REG_GLOSS
        if k == 0 or k <= self.clad:
            return REG_PLASTIC
        return REG_PAINT

    # ---- Außenhaut + Glas ----
    def build_skin(self, mats):
        S = self.stations()
        self.S = S
        bm = bmesh.new()
        lrow = bm.verts.layers.int.new("row")
        reg = bm.faces.layers.int.new("reg")
        V = []
        for d in S:
            hs = self.half_section(d)
            ring = [(-x, dd, z, j) for j, (x, dd, z) in enumerate(hs)]
            ring += [(x, dd, z, j) for j, (x, dd, z) in reversed(list(enumerate(hs[:-1])))]
            row = []
            for x, dd, z, j in ring:
                v = bm.verts.new((x, self.yf - dd, z))
                v[lrow] = j
                row.append(v)
            V.append(row)
        for i in range(len(S) - 1):
            dm = (S[i] + S[i + 1]) / 2
            for c in range(28):
                k = c if c < 14 else 27 - c
                f = bm.faces.new((V[i][c], V[i + 1][c], V[i + 1][c + 1], V[i][c + 1]))
                f[reg] = self.region(dm, k, -1 if c < 14 else 1)
                f.smooth = True
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0008)
        bmesh.ops.dissolve_degenerate(bm, edges=bm.edges[:], dist=0.0002)
        # Scheiben mit Rahmen (schwarzer Rand) versehen
        codes = sorted(set(f[reg] for f in bm.faces if f[reg] >= 10))
        for code in codes:
            faces = [f for f in bm.faces if f[reg] == code]
            th = 0.034 if code in (REG_WS, REG_RW) else 0.02
            r = bmesh.ops.inset_region(bm, faces=faces, thickness=th, depth=0.0, use_boundary=True,
                                       use_even_offset=True)
            for f in r["faces"]:
                f[reg] = REG_GLOSS
                f.smooth = True
        bm.normal_update()
        bm.faces.ensure_lookup_table()
        self.bvh = BVHTree.FromBMesh(bm)
        # Fächer an Bug- und Heckmitte nie hart kanten (sonst Schattierungsfehler an den schmalen Dreiecken)
        for e in bm.edges:
            a, b = e.verts[0].co, e.verts[1].co
            if max(abs(a.x), abs(b.x)) < 0.36 * self.W and (min(a.y, b.y) > self.yf - 0.22 or max(a.y, b.y) < self.yf - self.L + 0.22):
                e.tag = True
        # Schulterkante als scharfe Lichtkante
        if self.crease:
            for e in bm.edges:
                if e.verts[0][lrow] == 5 and e.verts[1][lrow] == 5 and not e.tag:
                    e.smooth = False
        # Glas abtrennen
        glass = MeshB("Glass", mats)
        vmap = {}
        gl = [f for f in bm.faces if f[reg] >= 10]
        for f in gl:
            vs = []
            for v in f.verts:
                if v not in vmap:
                    vmap[v] = glass.bm.verts.new(v.co)
                vs.append(vmap[v])
            glass.face(vs, "Glass")
        bmesh.ops.delete(bm, geom=gl, context="FACES")
        body = MeshB("Body", mats, bm)
        for f in bm.faces:
            f.material_index = body.mi(REG_MAT.get(f[reg], "CarPaint"))
        return body, glass

    # ---- Radhäuser + Unterboden ----
    def build_wells(self, body):
        for dc in self.axles:
            ds = [d for d in self.S if abs(d - dc) < self.Ra - 1e-4]
            ds = [dc - self.Ra + 1e-3] + ds + [dc + self.Ra - 1e-3]
            for side in (-1, 1):
                outer = [self.pt(d, 0, side) for d in ds]
                zmin = min(self.f_low(ds[0]), self.f_low(ds[-1]))
                outer = [Vector((p.x, p.y, max(p.z, zmin))) for p in outer]
                inner = [Vector((side * self.x_well, p.y, p.z + 0.02)) for p in outer]
                fs = body.grid([outer, inner], "PlasticBlack", flip=(side > 0))
                cen = Vector((side * self.x_well, self.yf - dc, self.zca))
                for i in range(len(inner) - 1):
                    q = [inner[i], inner[i + 1], cen]
                    if side < 0:
                        q.reverse()
                    f = body.face(q, "PlasticBlack", smooth=False)
        # Unterboden
        cuts = [0.04, self.L - 0.04]
        for dc in self.axles:
            cuts += [dc - self.Ra - 0.01, dc - self.Ra + 0.01, dc + self.Ra - 0.01, dc + self.Ra + 0.01]
        cuts += [self.Rn * 0.3, self.Rn, self.L - self.Rt, self.L - self.Rt * 0.3, self.L * 0.5]
        cuts = sorted(c for c in cuts if 0.03 < c < self.L - 0.03)
        G = []
        for d in cuts:
            hs = self.half_section(d)
            x = hs[0][0]
            if any(abs(d - dc) < self.Ra + 0.005 for dc in self.axles):
                x = min(x, self.x_well)
            z = self.f_low(d) + 0.012
            G.append([Vector((-x, self.yf - hs[0][1], z)), Vector((x, self.yf - hs[0][1], z))])
        body.grid(G, "PlasticBlack", smooth=False, flip=True)

    # ---- Innenraum ----
    def build_interior(self, mats):
        it = MeshB("Interior", mats)
        zf = self.gc + 0.10
        d0 = self.d_cowl
        d1 = self.d_bulk if self.cargo else self.d_bl
        cand = [d for d in self.S if d0 - 1e-6 <= d <= d1 + 1e-6]
        keep = []
        for d in cand:
            if not keep or round(d, 4) in self.key_d or d - keep[-1] >= 0.2 or d == cand[-1]:
                keep.append(d)
        secs = []
        for d in keep:
            hs = self.half_section(d)
            xf = hs[5][0] - 0.04
            if any(abs(d - dc) < self.Ra for dc in self.axles):
                xf = min(xf, self.x_well - 0.02)
            q = [(0.0, hs[5][1], zf), (xf, hs[5][1], zf), (hs[5][0] - 0.03, hs[5][1], hs[5][2]),
                 (hs[6][0] - 0.03, hs[6][1], hs[6][2] - 0.012), (hs[8][0] - 0.028, hs[8][1], hs[8][2] - 0.012),
                 (hs[10][0] - 0.02, hs[10][1], hs[10][2] - 0.028), (hs[12][0], hs[12][1], hs[12][2] - 0.028),
                 (0.0, hs[14][1], hs[14][2] - 0.028)]
            secs.append(q)
        for side in (-1, 1):
            P = [[Vector((side * x, self.yf - dd, z)) for x, dd, z in q] for q in secs]
            for i in range(len(keep) - 1):
                dm = (keep[i] + keep[i + 1]) / 2
                for k in range(7):
                    if k == 3 and self.region(dm, 7, side) >= 20:
                        continue                         # Fensteröffnung
                    if k >= 5 and self.region(dm, 12, side) in (REG_WS, REG_RW):
                        continue                         # Front-/Heckscheibe
                    q = [P[i][k], P[i][k + 1], P[i + 1][k + 1], P[i + 1][k]]
                    if side > 0:
                        q.reverse()
                    it.face(q, "Interior")
        bmesh.ops.remove_doubles(it.bm, verts=it.bm.verts[:], dist=0.001)
        # Stirnwand, Armaturenbrett
        hs = self.half_section(d0)
        xw = hs[6][0] - 0.035
        zd = hs[6][2] - 0.02
        y0 = self.yf - d0
        it.face([(-xw, y0, zf), (xw, y0, zf), (xw, y0, zd), (-xw, y0, zd)], "Interior", smooth=False)
        dash_len = 0.50
        it.box((0, y0 - dash_len / 2 + 0.06, zd - 0.14), (2 * xw, dash_len + 0.12, 0.28), "Interior")
        it.box((0, y0 - dash_len - 0.25, zf + 0.16), (0.22, 1.0, 0.32), "Interior")          # Mittelkonsole
        # Lenkrad (links)
        ds_f = self.d_seat
        M = Matrix.Rotation(math.radians(-24), 3, "X") @ Matrix.Rotation(math.radians(90), 3, "Z")
        c = Vector((-0.37, self.yf - (ds_f - 0.40), zd - 0.02))
        it.lathe([(0.0, 0.165), (0.012, 0.185), (0.0, 0.2), (-0.012, 0.185), (0.0, 0.165)], 10, "Interior",
                 M=Matrix.Translation(c) @ M.to_4x4())
        it.box(c + Vector((0, 0.03, -0.01)), (0.06, 0.1, 0.36), "Interior", M=Matrix.Rotation(math.radians(-24), 3, "X"))
        # Sitze
        lift = self.seat_lift
        zs = zf + 0.20 + lift

        def seat(x, d, w, back_h, tilt, heads):
            it.box((x, self.yf - d, zs), (w, 0.50, 0.15), "InteriorSeat")
            Mx = Matrix.Rotation(math.radians(tilt), 3, "X")
            cb = Vector((x, self.yf - d - 0.27 - math.sin(math.radians(tilt)) * back_h / 2, zs + 0.05 + back_h / 2))
            it.box(cb, (w * 0.96, 0.12, back_h), "InteriorSeat", M=Mx, taper=0.86)
            for hx in heads:
                ch = Vector((x + hx, cb.y - math.sin(math.radians(tilt)) * (back_h / 2 + 0.10),
                             zs + 0.05 + back_h / 2 + math.cos(math.radians(tilt)) * (back_h / 2 + 0.10)))
                it.box(ch, (0.25, 0.09, 0.17), "InteriorSeat", M=Mx, taper=0.85)

        xs = min(0.39, xw * 0.5)
        seat(-xs, ds_f, 0.50, 0.60, 20, (0.0,))
        seat(xs, ds_f, 0.50, 0.60, 20, (0.0,))
        if self.seat_rows >= 2:
            seat(0.0, self.d_rseat, min(1.36, 2 * xw - 0.16), 0.56, 24, (-0.38, 0.38))
        # hintere Ablage / Laderaumabdeckung bzw. Trennwand
        if self.cargo:
            hb = self.half_section(self.d_bulk)
            yb = self.yf - self.d_bulk + 0.01
            xb = hb[5][0] - 0.035
            top = [(hb[j][0] - (0.03 if j < 12 else 0.0), yb, hb[j][2] - 0.02) for j in (8, 10, 12, 14)]
            it.face([(-xb, yb, zf), (xb, yb, zf)] + top + [(-x, y, z) for x, y, z in reversed(top[:-1])], "Interior",
                    smooth=False)
        else:
            dsh = self.d_rseat + 0.42 if self.seat_rows >= 2 else self.d_seat + 0.45
            ha, hb = self.half_section(dsh), self.half_section(d1)
            za_, zb_ = ha[6][2] - 0.04, hb[6][2] - 0.04
            ya, yb = self.yf - dsh, self.yf - d1
            xa, xb = ha[6][0] - 0.035, hb[6][0] - 0.035
            it.face([(-xa, ya, za_), (xa, ya, za_), (xb, yb, zb_), (-xb, yb, zb_)], "Interior", smooth=False)
            it.face([(-xa, ya, zf), (xa, ya, zf), (xa, ya, za_), (-xa, ya, za_)], "Interior", smooth=False)
            it.face([(-xb, yb, zf), (xb, yb, zf), (xb, yb, zb_), (-xb, yb, zb_)], "Interior", smooth=False)
        return it

    # ---- Umfangskoordinate für Flicken an Bug/Heck ----
    def perim(self):
        if self._perim is None:
            pts = []
            n = 60
            for k in range(n + 1):
                th = k / n * math.pi / 2
                d = self.Rn * (1.0 - math.cos(th) ** (2.0 / self.nn))
                pts.append((self.W * 0.5 * self.f_taper(d) * self.plan(d), d))
            d = self.Rn + 0.04
            while d < self.L - self.Rt:
                pts.append((self.W * 0.5 * self.f_taper(d), d))
                d += 0.04
            for k in range(n, -1, -1):
                th = k / n * math.pi / 2
                d = self.L - self.Rt * (1.0 - math.cos(th) ** (2.0 / self.nt))
                pts.append((self.W * 0.5 * self.f_taper(d) * self.plan(d), d))
            A = [0.0]
            for i in range(1, len(pts)):
                A.append(A[-1] + math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
            self._perim = (A, pts)
        return self._perim

    def perim_xy(self, a):
        A, pts = self.perim()
        a = clamp(a, 0.0, A[-1])
        lo, hi = 0, len(A) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if A[mid] <= a:
                lo = mid
            else:
                hi = mid
        t = 0.0 if A[hi] == A[lo] else (a - A[lo]) / (A[hi] - A[lo])
        return lerp(pts[lo][0], pts[hi][0], t), lerp(pts[lo][1], pts[hi][1], t)

    def a_of_d(self, d, rear=False):
        """Umfangskoordinate (ab Bugmitte, bzw. ab Heckmitte) des Seitenpunkts bei Abstand d von der Spitze."""
        A, pts = self.perim()
        best = min(range(len(pts)), key=lambda i: abs(pts[i][1] - d) + (0 if (pts[i][1] > self.L / 2) == rear else 99))
        return A[-1] - A[best] if rear else A[best]

    def proxy(self, where, u, z, side=1):
        if where == "side":
            return Vector((side * self.W * 0.5 * self.f_taper(u) * self.plan(u), self.yf - u, z))
        if where == "top":                              # (d, x) von oben auf Haube/Dach/Heckdeckel
            hs = self.half_section(u)
            return Vector((side * z, self.yf - u, max(hs[6][2], hs[14][2]) + 0.06))
        A, _ = self.perim()
        a = abs(u) if where == "front" else A[-1] - abs(u)
        x, d = self.perim_xy(a)
        sg = (1 if u >= 0 else -1) * side
        return Vector((sg * x, self.yf - d, z))

    def snap(self, p, level=1):
        loc, nrm, _i, _dist = self.bvh.find_nearest(p)
        off = 0.003 if level <= 0 else 0.005 + 0.004 * (level - 1)
        return loc + nrm * off, nrm

    # ---- Flicken ----
    def band(self, mb, mat, where, top, bot, level=1, mirror=True, seg=0.05, nv=None, side=1):
        """Fläche zwischen zwei Linienzügen top/bot [(u, z), …] auf der Haut. where: 'front' | 'rear' | 'side'
        (u = Umfangsmaß ab Mitte bzw. bei 'side' der Abstand d von der Spitze)."""
        def cum(poly):
            c = [0.0]
            for i in range(1, len(poly)):
                c.append(c[-1] + math.hypot(poly[i][0] - poly[i - 1][0], poly[i][1] - poly[i - 1][1]))
            return c

        def ev(poly, c, t):
            if c[-1] <= 0:
                return poly[0]
            s = t * c[-1]
            for i in range(1, len(poly)):
                if s <= c[i] or i == len(poly) - 1:
                    q = 0.0 if c[i] == c[i - 1] else clamp((s - c[i - 1]) / (c[i] - c[i - 1]))
                    return (lerp(poly[i - 1][0], poly[i][0], q), lerp(poly[i - 1][1], poly[i][1], q))

        ct, cb = cum(top), cum(bot)
        ts = set([0.0, 1.0])
        for c in (ct, cb):
            if c[-1] > 0:
                ts.update(round(x / c[-1], 4) for x in c)
        ts = sorted(ts)
        ln = max(ct[-1], cb[-1], 1e-6)
        full = [ts[0]]
        for t in ts[1:]:
            n = int(math.ceil((t - full[-1]) * ln / seg))
            t0 = full[-1]
            for k in range(1, n):
                full.append(lerp(t0, t, k / n))
            full.append(t)
        T = [ev(top, ct, t) for t in full]
        B = [ev(bot, cb, t) for t in full]
        h = max(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(T, B))
        if nv is None:
            nv = max(1, int(math.ceil(h / 0.07)))
        made = []
        for sg in ((1, -1) if mirror else (1,)):
            G, N = [], []
            for a, b in zip(T, B):
                col, ncol = [], []
                for k in range(nv + 1):
                    q = k / nv
                    uu, zz = lerp(a[0], b[0], q), lerp(a[1], b[1], q)
                    if where in ("side", "top"):
                        p = self.proxy(where, uu, zz, side * sg)
                    else:
                        p = self.proxy(where, uu * sg, zz, side)
                    sp, nr = self.snap(p, level)
                    if col and (sp - col[-1].co).length < 1e-5:
                        col.append(col[-1])
                    else:
                        col.append(mb.bm.verts.new(sp))
                    ncol.append(nr)
                G.append(col)
                N.append(ncol)
            for i in range(len(G) - 1):
                for k in range(nv):
                    f = mb.face([G[i][k], G[i + 1][k], G[i + 1][k + 1], G[i][k + 1]], mat)
                    if f is None:
                        continue
                    f.normal_update()
                    if f.normal.dot(N[i][k] + N[i + 1][k + 1]) < 0:
                        f.normal_flip()
                    made.append(f)
        return made

    def skin_band(self, mb, mat, d0, d1, r0, r1, level=1, nd=6, nr=4, mirror=True):
        """Flicken direkt in Hautkoordinaten: Abstand d0..d1, Zeilen r0..r1 (gebrochene Zeilennummern erlaubt;
        r0/r1 dürfen auch Funktionen von t = 0..1 längs d sein). Für Flächen an Säulen und Dach."""
        f0 = r0 if callable(r0) else (lambda t: r0)
        f1 = r1 if callable(r1) else (lambda t: r1)
        made = []
        for sg in ((1, -1) if mirror else (1,)):
            G, N = [], []
            for i in range(nd + 1):
                t = i / nd
                hs = self.half_section(lerp(d0, d1, t))
                col, ncol = [], []
                for k in range(nr + 1):
                    r = clamp(lerp(f0(t), f1(t), k / nr), 0.0, 14.0)
                    j = min(int(r), 13)
                    q = r - j
                    p = Vector((sg * lerp(hs[j][0], hs[j + 1][0], q), self.yf - lerp(hs[j][1], hs[j + 1][1], q),
                                lerp(hs[j][2], hs[j + 1][2], q)))
                    sp, nrm = self.snap(p, level)
                    col.append(mb.bm.verts.new(sp))
                    ncol.append(nrm)
                G.append(col)
                N.append(ncol)
            for i in range(nd):
                for k in range(nr):
                    f = mb.face([G[i][k], G[i + 1][k], G[i + 1][k + 1], G[i][k + 1]], mat)
                    if f is None:
                        continue
                    f.normal_update()
                    if f.normal.dot(N[i][k] + N[i + 1][k + 1]) < 0:
                        f.normal_flip()
                    made.append(f)
        return made

    def ribbon(self, mb, mat, where, pts, width, level=1, mirror=True, side=1, seg=0.06):
        top, bot = [], []
        for i, p in enumerate(pts):
            a = pts[max(i - 1, 0)]
            b = pts[min(i + 1, len(pts) - 1)]
            tx, tz = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(tx, tz) or 1.0
            nx, nz = -tz / ln * width / 2, tx / ln * width / 2
            top.append((p[0] + nx, p[1] + nz))
            bot.append((p[0] - nx, p[1] - nz))
        return self.band(mb, mat, where, top, bot, level, mirror, seg, 1, side)

    def frame_at(self, where, u, z, level=1):
        """Lokales Achsenkreuz auf der Haut: (Ursprung, rechts, oben, Normale) – 'rechts' aus Betrachtersicht."""
        p, n = self.snap(self.proxy(where, u, z), level)
        n = Vector((n.x, n.y, 0.0)).normalized() if abs(n.z) < 0.9 else n
        r = Vector((0, 0, 1)).cross(n).normalized()
        up = n.cross(r).normalized()
        return p, r, up, n


# --------------------------------------------------------------------------------------------------
# Schrift (Blender-Standardschrift) als flache Dreiecke
# --------------------------------------------------------------------------------------------------
def text_polys(s, height, max_width=None):
    """Liefert [[(x, y), …], …] – Polygone des Textes, zentriert, Versalhöhe = height."""
    cu = bpy.data.curves.new("txt", "FONT")
    cu.body = s
    cu.resolution_u = 2
    cu.fill_mode = "FRONT"
    ob = bpy.data.objects.new("txt", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    vs = [v.co.copy() for v in me.vertices]
    polys = [[(vs[i].x, vs[i].y) for i in p.vertices] for p in me.polygons]
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    bpy.data.meshes.remove(me)
    if not polys:
        return []
    xs = [p[0] for poly in polys for p in poly]
    ys = [p[1] for poly in polys for p in poly]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    sc = height / max(max(ys) - min(ys), 1e-6)
    sx = sc
    if max_width and (max(xs) - min(xs)) * sc > max_width:
        sx = max_width / (max(xs) - min(xs))
    return [[((x - cx) * sx, (y - cy) * sc) for x, y in poly] for poly in polys]


def put_text(mb, mat, s, height, origin, right, up, max_width=None):
    for poly in text_polys(s, height, max_width):
        mb.face([origin + right * x + up * y for x, y in poly], mat, smooth=False)


# --------------------------------------------------------------------------------------------------
# Räder
# --------------------------------------------------------------------------------------------------
def build_wheel(mats, r, tw, rim_r, style="multi", nseg=22):
    """Liefert (Felgen-Mesh, Reifen-Mesh); Achse = lokale X-Achse, Außenseite = +X."""
    tire = MeshB("Tire", mats)
    h = tw / 2
    tire.lathe([(-h * 0.80, rim_r), (-h, rim_r + 0.014), (-h, r - 0.03), (-h * 0.78, r), (h * 0.78, r),
                (h, r - 0.03), (h, rim_r + 0.014), (h * 0.80, rim_r)], nseg, "Rubber")
    rim = MeshB("Rim", mats)
    xo = h * 0.80
    dark = style in ("aero", "five_dark")
    barrel = "BlackGloss" if dark else "Rim"
    rim.lathe([(xo, rim_r), (xo + 0.006, rim_r - 0.012), (xo - 0.012, rim_r - 0.026), (-h * 0.7, rim_r - 0.03)],
              nseg, ["Rim", "Rim", barrel])
    rim.disc(-h * 0.55, rim_r - 0.03, nseg, "PlasticBlack")
    # Bremsscheibe
    rd = rim_r * 0.74
    rim.lathe([(0.012, 0.06), (0.012, rd), (-0.012, rd)], 16, "BrakeDisc")
    # Nabe
    xh = h * 0.42
    rim.lathe([(xh - 0.05, 0.062), (xh + 0.012, 0.058), (xh + 0.022, 0.04)], 10, "Rim")
    rim.disc(xh + 0.022, 0.04, 10, "Chrome")

    def spoke(ang, w0, w1, r0, r1, mat, x0=None, x1=None, dang=0.0):
        x0 = xh + 0.012 if x0 is None else x0
        x1 = xo - 0.016 if x1 is None else x1
        dep = 0.03
        ca, sa = math.cos(ang), math.sin(ang)
        cb, sb = math.cos(ang + dang), math.sin(ang + dang)
        def P(x, rad, off, c, s):
            return Vector((x, rad * c - off * s, rad * s + off * c))
        a0, a1 = P(x0, r0, -w0 / 2, ca, sa), P(x0, r0, w0 / 2, ca, sa)
        b0, b1 = P(x1, r1, -w1 / 2, cb, sb), P(x1, r1, w1 / 2, cb, sb)
        a0b, a1b = P(x0 - dep, r0, -w0 / 2, ca, sa), P(x0 - dep, r0, w0 / 2, ca, sa)
        b0b, b1b = P(x1 - dep, r1, -w1 / 2, cb, sb), P(x1 - dep, r1, w1 / 2, cb, sb)
        V = [rim.bm.verts.new(p) for p in (a0, a1, b1, b0, a0b, a1b, b1b, b0b)]
        rim.face([V[0], V[1], V[2], V[3]], mat, smooth=False)
        rim.face([V[1], V[5], V[6], V[2]], mat, smooth=False)
        rim.face([V[4], V[0], V[3], V[7]], mat, smooth=False)

    r0, r1 = 0.05, rim_r - 0.022
    if style == "multi":
        for k in range(10):
            spoke(2 * math.pi * k / 10, 0.036, 0.026, r0, r1, "Rim")
    elif style == "double":
        for k in range(5):
            a = 2 * math.pi * k / 5
            spoke(a - 0.10, 0.026, 0.022, r0, r1, "Rim", dang=-0.13)
            spoke(a + 0.10, 0.026, 0.022, r0, r1, "Rim", dang=0.13)
    elif style == "ystar":
        for k in range(5):
            a = 2 * math.pi * k / 5
            spoke(a, 0.05, 0.03, r0, r1 * 0.62, "Rim", x1=lerp(xh + 0.012, xo - 0.016, 0.6))
            for sg in (-1, 1):
                spoke(a + sg * 0.0, 0.026, 0.022, r1 * 0.55, r1, "Rim", x0=lerp(xh + 0.012, xo - 0.016, 0.55),
                      dang=sg * 0.26)
    elif style in ("five", "five_dark"):
        for k in range(5):
            spoke(2 * math.pi * k / 5, 0.075, 0.05, r0, r1, "Rim")
    elif style == "aero":
        for k in range(5):
            a = 2 * math.pi * k / 5
            spoke(a, 0.07, 0.19, r0, r1, "Rim", dang=0.12)
    elif style == "steel":
        for k in range(6):
            spoke(2 * math.pi * k / 6, 0.07, 0.08, r0, r1, "Rim")
    obs = []
    for mb in (rim, tire):
        obs.append(mb)
    return rim, tire


def wheel_objects(mats, car, style):
    """Erzeugt Wheel_FL/FR/RL/RR (Leerobjekte in Radmitte) mit Kindern Rim_xx/Tire_xx – wie in den alten GLBs:
    linke Räder um 180° um die Hochachse gedreht, Außenseite der Felge = lokales +X."""
    rim, tire = build_wheel(mats, car.rw, car.tw, car.rim_r, style)
    tr = rim.tris() + tire.tris()
    rim_ob = rim.finish(sharp_deg=40, recalc=True)
    tire_ob = tire.finish(sharp_deg=40, recalc=True)
    rim_me, tire_me = rim_ob.data, tire_ob.data
    bpy.data.objects.remove(rim_ob)
    bpy.data.objects.remove(tire_ob)
    out = []
    col = bpy.context.scene.collection
    for key, sx, sy in (("FL", -1, 1), ("FR", 1, 1), ("RL", -1, -1), ("RR", 1, -1)):
        w = bpy.data.objects.new("Wheel_" + key, None)
        w.location = (sx * car.track / 2, sy * car.wb / 2, car.rw)
        col.objects.link(w)
        for nm, me in (("Rim_", rim_me), ("Tire_", tire_me)):
            o = bpy.data.objects.new(nm + key, me)
            o.parent = w
            if sx < 0:
                o.rotation_euler = (0, 0, math.pi)
            col.objects.link(o)
        out.append(w)
    return out, tr * 4


# --------------------------------------------------------------------------------------------------
# Außenspiegel, Kennzeichen, Taxischild
# --------------------------------------------------------------------------------------------------
def add_mirrors(car, body, cap="CarPaint", scale=1.0):
    d = car.d_cowl + car.ws_bow + 0.10
    hs = car.half_section(d)
    for side in (-1, 1):
        base = Vector((side * hs[6][0], car.yf - d, hs[6][2] + 0.035))
        c = base + Vector((side * 0.085 * scale, -0.01, 0.05 * scale))
        sx, sy, sz = 0.085 * scale, 0.05 * scale, 0.062 * scale
        rings = []
        n = 8
        for i, (ph, rr) in enumerate(((-1.0, 0.0), (-0.72, 0.72), (0.0, 1.0), (0.72, 0.72), (1.0, 0.0))):
            ring = []
            for k in range(n):
                a = 2 * math.pi * k / n
                # Superellipse im Querschnitt (x–z), Tiefe nach vorn gewölbt, hinten flach (Spiegelglas)
                cx, cz = math.cos(a), math.sin(a)
                ex = abs(cx) ** 0.6 * (1 if cx >= 0 else -1)
                ez = abs(cz) ** 0.6 * (1 if cz >= 0 else -1)
                y = ph * sy if ph > 0 else ph * sy * 0.25
                ring.append(c + Vector((ex * sx * rr, y, ez * sz * rr)))
            rings.append(ring)
        V = [[body.bm.verts.new(p) for p in ring] for ring in rings]
        for i in range(4):
            for k in range(n):
                k2 = (k + 1) % n
                if i == 0:
                    mat = "Chrome"
                elif i == 1:
                    mat = "PlasticBlack"
                else:
                    mat = cap
                q = [V[i][k], V[i][k2], V[i + 1][k2], V[i + 1][k]]
                f = body.face(q, mat)
                if f:
                    f.normal_update()
                    if f.normal.dot(f.calc_center_median() - c) < 0:
                        f.normal_flip()
        # Fuß
        body.box((base + c) / 2 + Vector((0, 0.0, -0.02)), (0.10 * scale, 0.045, 0.03), "PlasticBlack")


def add_plate(car, body, where, z, text, level=3):
    p, r, up, n = car.frame_at(where, 0.0, z, level)
    p = p + n * 0.006
    w, h = 0.52, 0.112
    def q(x0, x1, y0, y1, off, mat):
        o = p + n * off
        body.face([o + r * x0 + up * y0, o + r * x1 + up * y0, o + r * x1 + up * y1, o + r * x0 + up * y1], mat,
                  smooth=False)
    q(-w / 2 - 0.012, w / 2 + 0.012, -h / 2 - 0.012, h / 2 + 0.012, 0.0, "PlasticBlack")
    q(-w / 2 + 0.045, w / 2, -h / 2, h / 2, 0.002, "Plate")
    q(-w / 2, -w / 2 + 0.045, -h / 2, h / 2, 0.002, "PlateBlue")
    put_text(body, "PlasticBlack", text, 0.072, p + n * 0.004 + r * 0.022, r, up, max_width=w - 0.085)


def add_taxi_sign(car, body, lights, d=None):
    d = car.d_head + 0.40 if d is None else d
    zr = car.half_section(d)[14][2]
    y = car.yf - d
    w, dep, h = 0.36, 0.13, 0.115
    body.box((0, y, zr + 0.012), (w + 0.04, dep + 0.03, 0.03), "PlasticBlack")
    c = Vector((0, y, zr + 0.027 + h / 2))
    lights.box(c, (w, dep, h), "TaxiSignEmit", taper=0.9)
    for sg in (1, -1):
        o = c + Vector((0, sg * (dep / 2 + 0.002), 0))
        put_text(lights, "PlasticBlack", "TAXI", 0.062, o, Vector((-sg, 0, 0)), Vector((0, 0, 1)), max_width=w * 0.8)


# --------------------------------------------------------------------------------------------------
# Export, Vorschau
# --------------------------------------------------------------------------------------------------
def export_glb(path, objects):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_texcoords=True, export_normals=True,
                              export_materials="EXPORT", export_image_format="AUTO", export_vertex_color="NONE",
                              export_animations=False, export_cameras=False, export_lights=False)
    return os.path.getsize(path)


def preview_setup(res=(640, 400)):
    sc = bpy.context.scene
    try:
        sc.render.engine = "BLENDER_EEVEE"
    except Exception:
        sc.render.engine = "BLENDER_EEVEE_NEXT"
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    try:
        sc.eevee.taa_render_samples = 32
    except Exception:
        pass
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    w = bpy.data.worlds.new("W")
    sc.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.60, 0.70, 0.86, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = 2.7
    sun.angle = math.radians(3)
    so = bpy.data.objects.new("Sun", sun)
    so.rotation_euler = Vector((0.75, 0.25, 0.9)).to_track_quat("Z", "Y").to_euler()
    sc.collection.objects.link(so)
    fill = bpy.data.lights.new("Fill", "SUN")
    fill.energy = 0.8
    fill.angle = math.radians(20)
    fo = bpy.data.objects.new("Fill", fill)
    fo.rotation_euler = Vector((0.3, -0.8, 0.5)).to_track_quat("Z", "Y").to_euler()
    sc.collection.objects.link(fo)
    gm = bpy.data.materials.new("Ground")
    try:
        gm.use_nodes = True
    except Exception:
        pass
    b = next(n for n in gm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (0.16, 0.16, 0.17, 1)
    b.inputs["Roughness"].default_value = 0.85
    me = bpy.data.meshes.new("Ground")
    me.from_pydata([(-40, -40, 0), (40, -40, 0), (40, 40, 0), (-40, 40, 0)], [], [(0, 1, 2, 3)])
    me.materials.append(gm)
    g = bpy.data.objects.new("Ground", me)
    sc.collection.objects.link(g)
    cam = bpy.data.cameras.new("Cam")
    co = bpy.data.objects.new("Cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    return sc, co


def preview_render(sc, co, target, direction, dist, path, lens=50):
    co.data.lens = lens
    d = Vector(direction).normalized()
    co.location = Vector(target) + d * dist
    co.rotation_euler = (Vector(target) - co.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def set_preview_glow(mats, on=True):
    glow = {"HeadlightEmit": ((1.0, 0.96, 0.88, 1), 2.2), "TaillightEmit": ((1.0, 0.03, 0.02, 1), 1.2),
            "BrakeLightEmit": ((1.0, 0.03, 0.02, 1), 0.5), "TaxiSignEmit": ((1.0, 0.75, 0.1, 1), 0.25)}
    for nm, (col, e) in glow.items():
        b = next(n for n in mats[nm].node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        b.inputs["Emission Color"].default_value = col
        b.inputs["Emission Strength"].default_value = e if on else 0.0
