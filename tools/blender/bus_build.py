"""Stadtbusse für die KI-Verkehrssimulation: bus_solo.glb (12 m) und bus_articulated.glb (18 m).

Aufruf:
  .venv/bin/python tools/blender/bus_textures.py
  flatpak run org.blender.Blender -b --python tools/blender/bus_build.py [-- solo|articulated]

Konventionen wie godot/assets/models/cars (sedan.glb, van.glb):
  Godot: vorn = -Z, rechts = +X, oben = +Y, Meter; Ursprung am Boden (y=0) in der Mitte
  zwischen den Achsen (Gelenkbus: zwischen Vorder- und Mittelachse).
  Blender (hier): vorn = +Y, rechts = +X, oben = +Z (Export Y-up).
  Wheel_*: unrotierte Leerknoten im Radmittelpunkt, Kinder Rim_*/Tire_*; links um 180° gedreht.
"""
from __future__ import annotations

import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veg_facade_lib as L  # noqa: E402

OUT = os.path.join(L.MODELS, "cars")

# ---------------------------------------------------------------- Maße
WH = 1.275          # halbe Breite (2.55 m)
R = 0.20            # Rundung senkrechte Ecken + Dachschulter
T = 0.045           # Wandstärke (Innenhaut)
Z_BOT, Z_FLOOR, Z_SKIRT, Z_BUMPER, Z_HL = 0.28, 0.34, 0.42, 0.62, 0.84
Z_WS, Z_SILL, Z_DISP, Z_WTOP, Z_SH, ZT = 0.98, 1.12, 2.12, 2.42, 2.68, 2.88
LEVELS = [Z_BOT, Z_FLOOR, Z_SKIRT, Z_BUMPER, Z_HL, Z_WS, Z_SILL, Z_DISP, Z_WTOP, Z_SH]
ROOF_UNIT_H = 0.17
WHEEL_R, WHEEL_W = 0.48, 0.28
ARCH_R, ARCH_Z, ARCH_IN = 0.58, 0.48, 0.72
TRACK_F, TRACK_M, TRACK_R, TWIN = 2.10, 2.10, 1.82, 0.165
NT, NP, NA = 6, 5, 18
DOOR_W = 1.25
LEAF_W = DOOR_W / 2 - 0.005
LEAF_H = Z_WTOP - Z_FLOOR - 0.02
DOOR_OUT, DOOR_SLIDE = 0.10, LEAF_W + 0.02
LED_TILE = 0.16

EMIT = {"HeadlightEmit", "TaillightEmit", "BrakeLightEmit", "IndicatorEmit", "DestinationEmit"}
INTERIOR = {"Interior", "InteriorFloor", "InteriorSeat", "Handrail", "InteriorEmit"}
UVS = {"InteriorSeat": 4.0, "InteriorFloor": 2.0}


def arch_samples(ya):
    """Stützstellen des Radausschnitts (gleichmäßig im Winkel -> dichter an den senkrechten Enden)."""
    return [ya - ARCH_R * math.cos(math.pi * k / NA) for k in range(NA + 1)]


def clip_above(poly, a, b):
    """Polygon (u,z) auf die Halbebene oberhalb der Geraden a->b beschneiden (Sutherland-Hodgman)."""
    (ua, za), (ub, zb) = a, b

    def f(p):
        t = (p[0] - ua) / (ub - ua) if abs(ub - ua) > 1e-9 else 0.0
        return p[1] - (za + (zb - za) * t)
    out = []
    for i in range(len(poly)):
        p, q = poly[i], poly[(i + 1) % len(poly)]
        fp, fq = f(p), f(q)
        if fp >= -1e-9:
            out.append(p)
        if (fp >= -1e-9) != (fq >= -1e-9):
            t = fp / (fp - fq)
            out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return out


def sstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def route(mat):
    if mat == "Glass":
        return "glass"
    if mat in EMIT:
        return "lights"
    if mat in INTERIOR:
        return "interior"
    return "body"


def gd(v):
    """Blender -> Godot-Koordinaten."""
    return [round(v[0], 4), round(v[2], 4), round(-v[1], 4)]


# =====================================================================
# Materialien
# =====================================================================
def materials():
    M = {}

    def m(name, **kw):
        M[name] = L.material(name, **kw)
        return M[name]

    m("CarPaint", color=(0.89, 0.54, 0.0, 1), rough=0.3, metal=0.3)
    m("BlackGloss", color=(0.006, 0.006, 0.007, 1), rough=0.12)
    m("PlasticBlack", color=(0.0085, 0.0085, 0.0093, 1), rough=0.6)
    m("Chrome", color=(0.71, 0.71, 0.75, 1), rough=0.12, metal=1.0)
    m("Glass", color=(0.010, 0.0153, 0.0174, 1), rough=0.03, alpha=0.25)
    m("Interior", color=(0.42, 0.42, 0.40, 1), rough=0.7)
    m("InteriorFloor", col="bus_floor.png", rough=0.6)
    m("InteriorSeat", col="bus_seat.png", rough=0.9)
    m("Handrail", color=(0.80, 0.50, 0.0, 1), rough=0.35, metal=0.1)
    e = m("InteriorEmit", color=(0.9, 0.9, 0.86, 1), rough=0.5)
    _emission(e, (1.0, 0.96, 0.88, 1), 1.0)
    m("HeadlightEmit", color=(0.342, 0.393, 0.448, 1), rough=0.1)
    m("IndicatorEmit", color=(0.692, 0.133, 0.0023, 1), rough=0.2)
    m("TaillightEmit", color=(0.171, 0.0015, 0.0023, 1), rough=0.2)
    m("BrakeLightEmit", color=(0.319, 0.0023, 0.0023, 1), rough=0.2)
    d = m("DestinationEmit", col="bus_led_col.png", rough=0.4)
    _emission(d, None, 1.0, tex="bus_led_emit.png")
    m("RoofUnit", color=(0.45, 0.46, 0.47, 1), rough=0.5)
    m("Rim", color=(0.342, 0.355, 0.393, 1), rough=0.35, metal=0.6)
    m("BrakeDisc", color=(0.10, 0.095, 0.089, 1), rough=0.6)
    m("Rubber", color=(0.0049, 0.0049, 0.0049, 1), rough=0.9)
    m("Plate", color=(0.848, 0.848, 0.848, 1), rough=0.5)
    m("PlateBlue", color=(0.0039, 0.0196, 0.3185, 1), rough=0.5)
    m("Bellows", color=(0.025, 0.025, 0.027, 1), rough=0.85, double=True)
    return M


def _emission(mat, color, strength, tex=None):
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    if tex:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = L.image(tex)
        t.location = (-700, -600)
        nt.links.new(t.outputs["Color"], bsdf.inputs["Emission Color"])
    else:
        bsdf.inputs["Emission Color"].default_value = color
    bsdf.inputs["Emission Strength"].default_value = strength


# =====================================================================
# Wagenkasten
# =====================================================================
class Car:
    def __init__(self, y_rear, y_front, front_closed, rear_closed, axles, doors, side_display=None,
                 driver=False, rear_podest=False, roof_units=(), mpa=None):
        self.y_rear, self.y_front = y_rear, y_front
        self.fc, self.rc = front_closed, rear_closed
        self.axles = sorted(axles)
        self.doors = doors              # [(index, y_center)]
        self.side_display = side_display  # (y0, y1) rechts
        self.driver = driver
        self.rear_podest = rear_podest
        self.roof_units = roof_units
        self.mpa = mpa                  # Mehrzweckfläche links (y0, y1)
        self.mb = {k: L.MB() for k in ("body", "glass", "lights", "interior")}
        self.ys0 = y_rear + (R if rear_closed else 0.0)
        self.ys1 = y_front - (R if front_closed else 0.0)
        self.displays = {}
        self.front_xs = [-(WH - R), -1.045, -1.02, -0.95, -0.62, 0.0, 0.62, 0.95, 1.02, 1.045, WH - R]
        self.rear_xs = [-(WH - R), -1.04, -0.84, -0.75, -0.55, 0.0, 0.55, 0.75, 0.84, 1.04, WH - R]

    # ---------------------------------------------------------- Grundfunktionen
    def add(self, pts, mat, out=None, uv=None, n=None, key=None):
        P = [Vector(p) for p in pts]
        U = list(uv) if uv is not None else None
        N = [Vector(x) for x in n] if n is not None else None
        keep = []
        for i, p in enumerate(P):
            if keep and (p - P[keep[-1]]).length < 1e-7:
                continue
            keep.append(i)
        if len(keep) > 2 and (P[keep[0]] - P[keep[-1]]).length < 1e-7:
            keep.pop()
        if len(keep) < 3:
            return
        P = [P[i] for i in keep]
        U = [U[i] for i in keep] if U else None
        N = [N[i] for i in keep] if N else None
        if out is not None:
            fn = L.face_normal(P)
            if fn.dot(Vector(out)) < 0:
                P, U, N = P[::-1], (U[::-1] if U else None), (N[::-1] if N else None)
        self.mb[key or route(mat)].poly(P, mat, uv=U, n=N, uvscale=UVS.get(mat, 1.0))

    def cuboid(self, x0, x1, y0, y1, z0, z1, mat, faces=None, skip=(), nx=1):
        """Quader; faces = {'+y': 'HeadlightEmit', ...} überschreibt einzelne Seiten."""
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        z0, z1 = sorted((z0, z1))
        faces = faces or {}
        xs = [x0 + (x1 - x0) * i / nx for i in range(nx + 1)]
        for i in range(nx):
            a, b = xs[i], xs[i + 1]
            for k, pts, out in (
                ("+y", [(a, y1, z0), (b, y1, z0), (b, y1, z1), (a, y1, z1)], (0, 1, 0)),
                ("-y", [(a, y0, z0), (b, y0, z0), (b, y0, z1), (a, y0, z1)], (0, -1, 0)),
                ("+z", [(a, y0, z1), (b, y0, z1), (b, y1, z1), (a, y1, z1)], (0, 0, 1)),
                ("-z", [(a, y0, z0), (b, y0, z0), (b, y1, z0), (a, y1, z0)], (0, 0, -1)),
            ):
                if k not in skip:
                    self.add(pts, faces.get(k, mat), out)
        for k, x, out in (("-x", x0, (-1, 0, 0)), ("+x", x1, (1, 0, 0))):
            if k not in skip:
                self.add([(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)], faces.get(k, mat), out)

    def tube(self, path, r, sides, mat, cap0=False, cap1=False):
        self.mb[route(mat)].tube(path, [r] * len(path), sides, mat, cap0=cap0, cap1=cap1)

    # ---------------------------------------------------------- Seitenwand
    def band_layout(self, sx):
        blocks = []
        if sx > 0:
            for (_, yc) in self.doors:
                blocks.append((yc - DOOR_W / 2, yc + DOOR_W / 2, "door"))
            if self.side_display:
                blocks.append((self.side_display[0], self.side_display[1], "display"))
        blocks.sort()
        segs = []
        PIL = 0.10

        def fill(a, b, lead, trail):
            ln = b - a
            if ln <= 1e-6:
                return
            if ln < lead + trail + 0.45:
                segs.append((a, b, "pillar"))
                return
            n = max(1, round((ln - lead - trail + PIL) / 1.45))
            wl = (ln - lead - trail - (n - 1) * PIL) / n
            y = a
            segs.append((y, y + lead, "pillar"))
            y += lead
            for i in range(n):
                segs.append((y, y + wl, "window"))
                y += wl
                if i < n - 1:
                    segs.append((y, y + PIL, "pillar"))
                    y += PIL
            segs.append((y, b, "pillar"))

        end_r = 0.06 if self.rc else 0.16
        end_f = 0.06 if self.fc else 0.16
        prev, prev_end = self.ys0, True
        for (a, b, k) in blocks:
            fill(prev, a, end_r if prev_end else 0.08, 0.08)
            segs.append((a, b, k))
            prev, prev_end = b, False
        fill(prev, self.ys1, end_r if prev_end else 0.08, end_f)
        return [s for s in segs if s[1] - s[0] > 1e-6]

    def side_breaks(self, segs):
        ys = {round(self.ys0, 5), round(self.ys1, 5)}
        for a, b, _ in segs:
            ys.add(round(a, 5))
            ys.add(round(b, 5))
        for ya in self.axles:
            for y in arch_samples(ya):
                ys.add(round(y, 5))
        # im Neigungsbereich der Front etwas feiner
        if self.fc:
            for k in range(1, 4):
                ys.add(round(self.ys1 - 0.35 * k / 4, 5))
        if self.rc:
            for k in range(1, 4):
                ys.add(round(self.ys0 + 0.35 * k / 4, 5))
        return sorted(y for y in ys if self.ys0 - 1e-6 <= y <= self.ys1 + 1e-6)

    def arch_z(self, y, ya):
        d = y - ya
        return ARCH_Z + math.sqrt(max(0.0, ARCH_R * ARCH_R - d * d))

    def side(self, sx):
        segs = self.band_layout(sx)
        ys = self.side_breaks(segs)
        kinds, arches = [], []
        for c in range(len(ys) - 1):
            ym = (ys[c] + ys[c + 1]) / 2
            k = next((s[2] for s in segs if s[0] - 1e-6 <= ym <= s[1] + 1e-6), "pillar")
            kinds.append(k)
            arches.append(next((ya for ya in self.axles if abs(ym - ya) < ARCH_R), None))

        def cell(c, um, za, zt):
            k = kinds[c]
            if k == "door":
                if zt <= Z_FLOOR + 1e-6:
                    return "PlasticBlack"
                if za >= Z_WTOP - 1e-6:
                    return "CarPaint"
                return ("omit", "door")
            if k == "window" and za >= Z_SILL - 1e-6 and zt <= Z_WTOP + 1e-6:
                return ("omit", "window")
            if k == "display":
                if za >= Z_SILL - 1e-6 and zt <= Z_DISP + 1e-6:
                    return ("omit", "window")
                if za >= Z_DISP - 1e-6 and zt <= Z_WTOP + 1e-6:
                    return "DestinationEmit"
            if zt <= Z_SKIRT + 1e-6:
                return "PlasticBlack"
            if za >= Z_SILL - 1e-6 and zt <= Z_WTOP + 1e-6:
                return "BlackGloss"
            return "CarPaint"

        def clip(c, y):
            ya = arches[c]
            return None if ya is None else self.arch_z(y, ya)

        def P(u, z, inner):
            return Vector((sx * (WH - (T if inner else 0.0)), u, z))

        disp = None
        if sx > 0 and self.side_display:
            d0, d1 = self.side_display
            disp = (d0, Z_DISP)
            self.displays["side_right"] = [Vector((WH, d0, Z_DISP)), Vector((WH, d1, Z_DISP)),
                                           Vector((WH, d1, Z_WTOP)), Vector((WH, d0, Z_WTOP))]
        self.panel(P, ys, (sx, 0, 0), cell, clip, disp)
        # Seitenscheiben
        xg = sx * (WH - 0.012)
        for a, b, k in segs:
            if k in ("window", "display"):
                top = Z_WTOP if k == "window" else Z_DISP
                self.add([(xg, a, Z_SILL), (xg, b, Z_SILL), (xg, b, top), (xg, a, top)], "Glass", (sx, 0, 0))
        return ys, segs

    # ---------------------------------------------------------- Front/Heck
    def front(self):
        y = self.y_front

        def cell(c, x, za, zt):
            ax = abs(x)
            if zt <= Z_BUMPER + 1e-6:
                return "PlasticBlack"
            if zt <= Z_HL + 1e-6:
                return "BlackGloss" if 0.62 <= ax <= 1.02 else "CarPaint"
            if zt <= Z_WS + 1e-6:
                return "CarPaint"
            if zt <= Z_WTOP + 1e-6:
                return ("omit", "window") if ax < 1.045 else "BlackGloss"
            return "DestinationEmit" if ax < 0.95 else "BlackGloss"

        def P(u, z, inner):
            return Vector((u, y - (T if inner else 0.0), z))

        self.panel(P, self.front_xs, (0, 1, 0), cell, None, (-0.95, Z_WTOP))
        self.displays["front"] = [Vector((0.95, y, Z_WTOP)), Vector((-0.95, y, Z_WTOP)),
                                  Vector((-0.95, y, Z_SH)), Vector((0.95, y, Z_SH))]
        # Frontscheibe (fein unterteilt, folgt Neigung/Wölbung)
        xs = [-1.045 + 2.09 * i / 8 for i in range(9)]
        zs = [Z_WS, 1.3, 1.7, 2.06, Z_WTOP]
        yg = y - 0.012
        for i in range(8):
            for j in range(4):
                self.add([(xs[i], yg, zs[j]), (xs[i + 1], yg, zs[j]), (xs[i + 1], yg, zs[j + 1]),
                          (xs[i], yg, zs[j + 1])], "Glass", (0, 1, 0))
        self.front_details()

    def rear(self):
        y = self.y_rear

        def cell(c, x, za, zt):
            ax = abs(x)
            if zt <= Z_BUMPER + 1e-6:
                return "PlasticBlack"
            if zt <= Z_SILL + 1e-6:
                return "CarPaint"
            if zt <= Z_WTOP + 1e-6:
                return ("omit", "window") if ax < 0.75 else "BlackGloss"
            return "DestinationEmit" if ax < 0.55 else "BlackGloss"

        def P(u, z, inner):
            return Vector((u, y + (T if inner else 0.0), z))

        self.panel(P, self.rear_xs, (0, -1, 0), cell, None, (0.55, Z_WTOP), flip_u=True)
        self.displays["rear"] = [Vector((-0.55, y, Z_WTOP)), Vector((0.55, y, Z_WTOP)),
                                 Vector((0.55, y, Z_SH)), Vector((-0.55, y, Z_SH))]
        yg = y + 0.012
        self.add([(-0.75, yg, Z_SILL), (0.75, yg, Z_SILL), (0.75, yg, Z_WTOP), (-0.75, yg, Z_WTOP)], "Glass",
                 (0, -1, 0))
        self.rear_details()

    # ---------------------------------------------------------- allgemeines Panel
    def panel(self, P, us, out, cell_fn, clip=None, disp=None, flip_u=False):
        rows = LEVELS
        nC, nR = len(us) - 1, len(rows) - 1
        st, gb = {}, {}
        for c in range(nC):
            ul, ur = us[c], us[c + 1]
            um = (ul + ur) / 2
            for r in range(nR):
                za, zt = rows[r], rows[r + 1]
                rect = [(ul, za), (ur, za), (ur, zt), (ul, zt)]
                poly = rect
                if clip:
                    cl, cr = clip(c, ul), clip(c, ur)
                    if cl is not None and max(cl, cr) > za + 1e-6:
                        poly = clip_above(rect, (ul, cl), (ur, cr))
                        if len(poly) < 3:
                            st[(c, r)] = ("omit", "arch")
                            continue
                st[(c, r)] = cell_fn(c, um, za, zt)
                gb[(c, r)] = poly
        outv = Vector(out)
        for (c, r), m in st.items():
            if isinstance(m, tuple):
                continue
            ul, ur = us[c], us[c + 1]
            za, zt = rows[r], rows[r + 1]
            corners = gb[(c, r)]
            bl = br = za
            uv = None
            if m == "DestinationEmit" and disp:
                sgn = -1.0 if flip_u else 1.0
                uv = [((u - disp[0]) * sgn / LED_TILE, (z - disp[1]) / LED_TILE) for (u, z) in corners]
            self.add([P(u, z, False) for u, z in corners], m, outv, uv=uv)
            self.add([P(u, z, True) for u, z in corners], "Interior", -outv)
            for dc, dr, e in ((-1, 0, "l"), (1, 0, "r"), (0, -1, "b"), (0, 1, "t")):
                nb = st.get((c + dc, r + dr))
                if not (isinstance(nb, tuple) and nb[1] in ("window", "door")):
                    continue
                a, b = {"l": ((ul, bl), (ul, zt)), "r": ((ur, br), (ur, zt)),
                        "b": ((ul, bl), (ur, br)), "t": ((ul, zt), (ur, zt))}[e]
                pts = [P(*a, False), P(*b, False), P(*b, True), P(*a, True)]
                cu = (us[c + dc] + us[c + dc + 1]) / 2 if dc else (ul + ur) / 2
                cz = (rows[r + dr] + rows[r + dr + 1]) / 2 if dr else (za + zt) / 2
                d = P(cu, cz, False) - P((ul + ur) / 2, (za + zt) / 2, False)
                self.add(pts, "PlasticBlack" if nb[1] == "door" else "BlackGloss", d)

    # ---------------------------------------------------------- Rundungen, Dach
    def corner(self, sx, sy):
        yc = (self.y_front - R) if sy > 0 else (self.y_rear + R)
        cx = sx * (WH - R)

        def mat(za, zt):
            if zt <= Z_SKIRT + 1e-6 or zt <= Z_BUMPER + 1e-6:
                return "PlasticBlack"
            lim = Z_WS if sy > 0 else Z_SILL
            if za >= lim - 1e-6:
                return "BlackGloss"
            return "CarPaint"

        for k in range(NT):
            t0, t1 = (math.pi / 2) * k / NT, (math.pi / 2) * (k + 1) / NT
            for r in range(len(LEVELS) - 1):
                za, zt = LEVELS[r], LEVELS[r + 1]

                def p(t, z, rad):
                    return Vector((cx + sx * rad * math.cos(t), yc + sy * rad * math.sin(t), z))

                def nv(t):
                    return Vector((sx * math.cos(t), sy * math.sin(t), 0))
                tm = (t0 + t1) / 2
                self.add([p(t0, za, R), p(t1, za, R), p(t1, zt, R), p(t0, zt, R)], mat(za, zt), nv(tm),
                         n=[nv(t0), nv(t1), nv(t1), nv(t0)])
                self.add([p(t0, za, R - T), p(t1, za, R - T), p(t1, zt, R - T), p(t0, zt, R - T)], "Interior",
                         -nv(tm))

    def shoulder(self, sx, ys):
        cx, cz = sx * (WH - R), ZT - R

        def p(f, y, rad):
            return Vector((cx + sx * rad * math.cos(f), y, cz + rad * math.sin(f)))

        def nv(f):
            return Vector((sx * math.cos(f), 0, math.sin(f)))
        for j in range(len(ys) - 1):
            y0, y1 = ys[j], ys[j + 1]
            for k in range(NP):
                f0, f1 = (math.pi / 2) * k / NP, (math.pi / 2) * (k + 1) / NP
                fm = (f0 + f1) / 2
                self.add([p(f0, y0, R), p(f0, y1, R), p(f1, y1, R), p(f1, y0, R)], "CarPaint", nv(fm),
                         n=[nv(f0), nv(f0), nv(f1), nv(f1)])
                self.add([p(f0, y0, R - T), p(f0, y1, R - T), p(f1, y1, R - T), p(f1, y0, R - T)], "Interior",
                         -nv(fm))

    def roof_edge(self, sy, xs):
        yc = (self.y_front - R) if sy > 0 else (self.y_rear + R)
        cz = ZT - R

        def p(f, x, rad):
            return Vector((x, yc + sy * rad * math.cos(f), cz + rad * math.sin(f)))

        def nv(f):
            return Vector((0, sy * math.cos(f), math.sin(f)))
        for j in range(len(xs) - 1):
            for k in range(NP):
                f0, f1 = (math.pi / 2) * k / NP, (math.pi / 2) * (k + 1) / NP
                fm = (f0 + f1) / 2
                self.add([p(f0, xs[j], R), p(f0, xs[j + 1], R), p(f1, xs[j + 1], R), p(f1, xs[j], R)], "CarPaint",
                         nv(fm), n=[nv(f0), nv(f0), nv(f1), nv(f1)])
                self.add([p(f0, xs[j], R - T), p(f0, xs[j + 1], R - T), p(f1, xs[j + 1], R - T),
                          p(f1, xs[j], R - T)], "Interior", -nv(fm))

    def octant(self, sx, sy):
        yc = (self.y_front - R) if sy > 0 else (self.y_rear + R)
        c = Vector((sx * (WH - R), yc, ZT - R))

        def d(t, f):
            return Vector((sx * math.cos(f) * math.cos(t), sy * math.cos(f) * math.sin(t), math.sin(f)))
        for k in range(NT):
            t0, t1 = (math.pi / 2) * k / NT, (math.pi / 2) * (k + 1) / NT
            for m in range(NP):
                f0, f1 = (math.pi / 2) * m / NP, (math.pi / 2) * (m + 1) / NP
                ds = [d(t0, f0), d(t1, f0), d(t1, f1), d(t0, f1)]
                outv = d((t0 + t1) / 2, (f0 + f1) / 2)
                self.add([c + x * R for x in ds], "CarPaint", outv, n=ds)
                self.add([c + x * (R - T) for x in ds], "Interior", -outv)

    def roof(self, ys_r, ys_l):
        xi = WH - R
        for z, mat, out in ((ZT, "CarPaint", (0, 0, 1)), (ZT - T, "Interior", (0, 0, -1))):
            pts = [(xi, y, z) for y in ys_r]
            if self.fc:
                pts += [(x, self.y_front - R, z) for x in reversed(self.front_xs)]
            pts += [(-xi, y, z) for y in reversed(ys_l)]
            if self.rc:
                pts += [(x, self.y_rear + R, z) for x in self.rear_xs]
            self.add(pts, mat, out)

    def open_end(self, y, sy):
        out = (0, sy, 0)
        for sx in (-1, 1):
            for r in range(len(LEVELS) - 1):
                za, zt = LEVELS[r], LEVELS[r + 1]
                self.add([(sx * WH, y, za), (sx * WH, y, zt), (sx * (WH - T), y, zt), (sx * (WH - T), y, za)],
                         "PlasticBlack", out)
            for k in range(NP):
                f0, f1 = (math.pi / 2) * k / NP, (math.pi / 2) * (k + 1) / NP

                def p(f, rad):
                    return (sx * (WH - R + rad * math.cos(f)), y, ZT - R + rad * math.sin(f))
                self.add([p(f0, R), p(f1, R), p(f1, R - T), p(f0, R - T)], "PlasticBlack", out)
        self.add([(-(WH - R), y, ZT), (WH - R, y, ZT), (WH - R, y, ZT - T), (-(WH - R), y, ZT - T)], "PlasticBlack",
                 out)
        self.add([(-(WH - T), y, Z_BOT), (WH - T, y, Z_BOT), (WH - T, y, Z_FLOOR), (-(WH - T), y, Z_FLOOR)],
                 "PlasticBlack", out)
        # Gummirahmen (leicht vorstehend) für den Übergang zum Faltenbalg
        for sx in (-1, 1):
            self.cuboid(sx * (WH - 0.005), sx * (WH + 0.012), y - sy * 0.06, y, Z_BOT, Z_SH, "PlasticBlack")
        self.cuboid(-(WH - R), WH - R, y - sy * 0.06, y, ZT - 0.005, ZT + 0.012, "PlasticBlack")

    def outline(self, inset, notches):
        pts = []
        rad = R - inset

        def arc(sx, sy, t_from, t_to):
            yc = (self.y_front - R) if sy > 0 else (self.y_rear + R)
            for k in range(NT + 1):
                t = t_from + (t_to - t_from) * k / NT
                pts.append((sx * (WH - R) + sx * rad * math.cos(t), yc + sy * rad * math.sin(t)))

        def side_pts(sx, forward):
            seq = []
            if notches:
                for ya in self.axles:
                    seq += [(sx * (WH - inset), ya - ARCH_R), (sx * (WH - ARCH_IN), ya - ARCH_R),
                            (sx * (WH - ARCH_IN), ya + ARCH_R), (sx * (WH - inset), ya + ARCH_R)]
            if not forward:
                seq = seq[::-1]
            pts.extend(seq)
        # rechts hinten -> rechts vorn -> links vorn -> links hinten
        if self.rc:
            arc(1, -1, math.pi / 2, 0.0)
        else:
            pts.append((WH - inset, self.y_rear))
        side_pts(1, True)
        if self.fc:
            arc(1, 1, 0.0, math.pi / 2)
            arc(-1, 1, math.pi / 2, 0.0)
        else:
            pts.append((WH - inset, self.y_front))
            pts.append((-(WH - inset), self.y_front))
        side_pts(-1, False)
        if self.rc:
            arc(-1, -1, 0.0, math.pi / 2)
        else:
            pts.append((-(WH - inset), self.y_rear))
        return pts

    def underbody(self):
        self.add([(x, y, Z_BOT) for x, y in self.outline(0.0, True)], "PlasticBlack", (0, 0, -1))
        for ya in self.axles:
            for sx in (-1, 1):
                curve = [(ya - ARCH_R, Z_BOT)]
                curve += [(y, self.arch_z(y, ya)) for y in arch_samples(ya)]
                curve += [(ya + ARCH_R, Z_BOT)]
                xo, xi = sx * (WH - 0.003), sx * (WH - ARCH_IN)
                for i in range(len(curve) - 1):
                    (y0, z0), (y1, z1) = curve[i], curve[i + 1]
                    if abs(y0 - y1) < 1e-7 and abs(z0 - z1) < 1e-7:
                        continue
                    cen = Vector(((xo + xi) / 2, ya, ARCH_Z))
                    fc = Vector(((xo + xi) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
                    self.add([(xo, y0, z0), (xo, y1, z1), (xi, y1, z1), (xi, y0, z0)], "PlasticBlack", cen - fc)
                self.add([(xi, y, z) for y, z in curve], "PlasticBlack", (sx, 0, 0))

    # ---------------------------------------------------------- Anbauteile
    def front_details(self):
        y = self.y_front
        for sx in (-1, 1):
            self.cuboid(sx * 0.66, sx * 0.90, y, y + 0.018, 0.655, 0.80, "PlasticBlack", faces={"+y": "HeadlightEmit"})
            self.cuboid(sx * 0.915, sx * 1.005, y, y + 0.016, 0.655, 0.80, "PlasticBlack",
                        faces={"+y": "IndicatorEmit"})
            self.cuboid(sx * 0.66, sx * 1.005, y, y + 0.012, 0.807, 0.826, "PlasticBlack",
                        faces={"+y": "HeadlightEmit"})
            self.cuboid(sx * 0.72, sx * 0.88, y + 0.05, y + 0.058, 0.40, 0.46, "PlasticBlack",
                        faces={"+y": "HeadlightEmit"})
            self.cuboid(sx * WH, sx * (WH + 0.008), y - 0.80, y - 0.70, 0.70, 0.755, "PlasticBlack",
                        faces={"+x" if sx > 0 else "-x": "IndicatorEmit"})
            # Spiegel ("Hörner" vom Dach)
            arm = [(sx * 1.12, y - 0.30, ZT - 0.02), (sx * 1.40, y - 0.12, ZT - 0.06),
                   (sx * 1.47, y + 0.08, 2.62), (sx * 1.47, y + 0.12, 2.36)]
            self.tube(arm, 0.022, 6, "PlasticBlack", cap1=True)
            self.cuboid(sx * 1.34, sx * 1.58, y + 0.08, y + 0.17, 1.92, 2.36, "PlasticBlack", faces={"-y": "Chrome"})
            # Wischer in Ruhelage
            x0, x1 = (-0.98, -0.10) if sx < 0 else (0.02, 0.86)
            self.cuboid(x0, x1, y + 0.002, y + 0.022, 1.00, 1.022, "PlasticBlack", nx=4)
            self.cuboid(x0 - 0.02 if sx < 0 else x0, x0 + 0.05 if sx < 0 else x0 + 0.07, y, y + 0.035, 0.985, 1.03,
                        "PlasticBlack")
        self.cuboid(-(WH - 0.10), WH - 0.10, y - 0.02, y + 0.05, 0.30, 0.56, "PlasticBlack", nx=8)
        self.cuboid(-0.26, 0.26, y + 0.05, y + 0.054, 0.36, 0.47, "PlasticBlack", faces={"+y": "Plate"})
        self.cuboid(-0.26, -0.225, y + 0.054, y + 0.056, 0.36, 0.47, "PlateBlue")

    def rear_details(self):
        y = self.y_rear
        for sx in (-1, 1):
            for z0, z1, mat in ((0.66, 0.76, "Chrome"), (0.76, 0.98, "TaillightEmit"), (0.98, 1.18, "BrakeLightEmit"),
                                (1.18, 1.34, "IndicatorEmit")):
                self.cuboid(sx * 0.84, sx * 1.04, y - 0.018, y, z0, z1, "PlasticBlack", faces={"-y": mat})
        for k in range(5):
            z = 0.72 + k * 0.07
            self.cuboid(-0.70, 0.70, y - 0.012, y, z, z + 0.03, "PlasticBlack")
        self.cuboid(-(WH - 0.10), WH - 0.10, y - 0.05, y + 0.02, 0.30, 0.56, "PlasticBlack", nx=8)
        self.cuboid(-0.26, 0.26, y - 0.054, y - 0.05, 0.36, 0.47, "PlasticBlack", faces={"-y": "Plate"})
        self.cuboid(0.225, 0.26, y - 0.056, y - 0.054, 0.36, 0.47, "PlateBlue")
        self.cuboid(-0.25, 0.25, y + 0.03, y + 0.06, 2.33, 2.37, "PlasticBlack", faces={"-y": "BrakeLightEmit"})

    def roof_box(self, x0, x1, y0, y1, h, ch=0.05, fans=0):
        z0, z1 = ZT - 0.01, ZT + h
        prof = [(x0, z0), (x1, z0), (x1, z1 - ch), (x1 - ch, z1), (x0 + ch, z1), (x0, z1 - ch)]
        for i in range(len(prof)):
            (a, b), (c, d) = prof[i], prof[(i + 1) % len(prof)]
            if i == 0:
                continue
            mx, mz = (a + c) / 2, (b + d) / 2
            self.add([(a, y0, b), (c, y0, d), (c, y1, d), (a, y1, b)], "RoofUnit",
                     (mx - (x0 + x1) / 2, 0, mz - z0))
        for yy, sgn in ((y0, -1), (y1, 1)):
            self.add([(x, yy, z) for x, z in prof], "RoofUnit", (0, sgn, 0))
        for k in range(fans):
            cy = y0 + (y1 - y0) * (k + 0.5) / fans
            for cx in ((x0 + x1) / 2 - 0.42, (x0 + x1) / 2 + 0.42):
                pts = [(cx + 0.2 * math.cos(a), cy + 0.2 * math.sin(a), z1 + 0.004)
                       for a in [2 * math.pi * i / 14 for i in range(14)]]
                self.add(pts, "PlasticBlack", (0, 0, 1))

    # ---------------------------------------------------------- Innenraum
    def interior(self):
        self.add([(x, y, Z_FLOOR) for x, y in self.outline(T, True)], "InteriorFloor", (0, 0, 1))
        yc0 = self.y_rear + (R + 0.05 if self.rc else 0.0)
        yc1 = self.y_front - (R + 0.40 if self.fc else 0.0)
        zc = Z_WTOP
        self.add([(-(WH - T), yc0, zc), (WH - T, yc0, zc), (WH - T, yc1, zc), (-(WH - T), yc1, zc)], "Interior",
                 (0, 0, -1))
        for sx in (-1, 1):
            xa, xb = sorted((sx * 0.60, sx * 0.76))
            self.add([(xa, yc0 + 0.25, zc - 0.004), (xb, yc0 + 0.25, zc - 0.004), (xb, yc1 - 0.25, zc - 0.004),
                      (xa, yc1 - 0.25, zc - 0.004)], "InteriorEmit", (0, 0, -1))
        for ya in self.axles:
            for sx in (-1, 1):
                self.cuboid(sx * (WH - T), sx * (WH - ARCH_IN - 0.02), ya - ARCH_R - 0.04, ya + ARCH_R + 0.04, Z_FLOOR,
                            1.10, "Interior", skip=("-z", "+x" if sx > 0 else "-x"))
        # gelbe Trittkanten in den Türen
        for (_, yc) in self.doors:
            self.add([(WH - T - 0.08, yc - DOOR_W / 2, Z_FLOOR + 0.002), (WH - T, yc - DOOR_W / 2, Z_FLOOR + 0.002),
                      (WH - T, yc + DOOR_W / 2, Z_FLOOR + 0.002), (WH - T - 0.08, yc + DOOR_W / 2, Z_FLOOR + 0.002)],
                     "Handrail", (0, 0, 1))
        y_pod = None
        if self.rear_podest:
            lim = min([yc - DOOR_W / 2 for _, yc in self.doors if yc - DOOR_W / 2 > self.y_rear] + [self.y_front])
            y_pod = min(self.y_rear + 1.25, lim - 0.06)
            self.cuboid(-(WH - T - 0.01), WH - T - 0.01, self.y_rear + 0.22, y_pod, Z_FLOOR, 0.70, "Interior",
                        skip=("-z",))
            yb = (self.y_rear + 0.22 + y_pod) / 2 + 0.06
            for x in (-0.92, -0.46, 0.0, 0.46, 0.92):
                self.seat(x, yb, 0.70)
        if self.driver:
            self.driver_area()
        self.seats_and_poles(y_pod)

    def seat(self, x, y, z, f=1, wide=1.0):
        hw = 0.215 * wide
        self.cuboid(x - hw, x + hw, y - 0.20 * f, y + 0.22 * f, z + 0.40, z + 0.47, "InteriorSeat")
        b0 = Vector((0, y - 0.21 * f, z + 0.46))
        b1 = Vector((0, y - 0.29 * f, z + 1.00))
        th = 0.065
        pts = {}
        for i, xx in enumerate((x - hw, x + hw)):
            for j, (yy, zz) in enumerate(((b0.y, b0.z), (b1.y, b1.z))):
                pts[(i, j, 0)] = Vector((xx, yy, zz))
                pts[(i, j, 1)] = Vector((xx, yy - th * f, zz))
        cen = sum(pts.values(), Vector()) / 8
        for face, mat in ((((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)), "InteriorSeat"),
                          (((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)), "Interior"),
                          (((0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)), "Interior"),
                          (((0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)), "Interior"),
                          (((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)), "Interior")):
            P = [pts[k] for k in face]
            fc = sum(P, Vector()) / 4
            self.add(P, mat, fc - cen)
        self.cuboid(x - 0.05, x + 0.05, y - 0.10, y + 0.10, z, z + 0.40, "PlasticBlack", skip=("-z", "+z"))

    def driver_area(self):
        y = self.y_front
        xl = -(WH - T)
        self.cuboid(xl, -0.10, y - 2.05, y - 0.60, Z_FLOOR, 0.52, "Interior", skip=("-z",))
        self.cuboid(xl, 0.35, y - 0.72, y - 0.42, 0.52, 1.02, "PlasticBlack", nx=3)
        c = Vector((-0.62, y - 0.95, 1.10))
        n = Vector((0, -0.42, 0.91)).normalized()
        e1 = Vector((1, 0, 0))
        e2 = n.cross(e1).normalized()
        ring = [c + (e1 * math.cos(a) + e2 * math.sin(a)) * 0.23 for a in [2 * math.pi * i / 16 for i in range(17)]]
        self.tube(ring, 0.018, 6, "PlasticBlack")
        self.tube([c, c - n * 0.05 + Vector((0, 0.35, -0.25))], 0.03, 6, "PlasticBlack")
        self.seat(-0.62, y - 1.45, 0.52, wide=1.25)
        self.cuboid(xl, -0.22, y - 2.10, y - 2.05, 0.52, 1.50, "Interior")
        self.cuboid(-0.22, -0.02, y - 2.13, y - 1.95, 0.95, 1.40, "PlasticBlack")

    def seats_and_poles(self, y_pod):
        pitch = 0.78
        rails = {}
        for sx in (-1, 1):
            blocked = []
            if sx > 0:
                for _, yc in self.doors:
                    blocked.append((yc - DOOR_W / 2 - 0.30, yc + DOOR_W / 2 + 0.30))
            for ya in self.axles:
                blocked.append((ya - ARCH_R - 0.08, ya + ARCH_R + 0.08))
            if self.driver and sx < 0:
                blocked.append((self.y_front - 2.25, self.y_front))
            if self.mpa and sx < 0:
                blocked.append(self.mpa)
            front_lim = self.y_front - (0.7 if self.fc else 0.55)
            rear_lim = self.y_rear + (0.35 if self.rc else 0.55)
            if y_pod is not None:
                rear_lim = max(rear_lim, y_pod + 0.05)
            blocked.sort()
            free, cur = [], rear_lim
            for a, b in blocked:
                if a > cur:
                    free.append((cur, min(a, front_lim)))
                cur = max(cur, b)
            if cur < front_lim:
                free.append((cur, front_lim))
            for a, b in free:
                n = int((b - a - 0.5) / pitch) + 1 if b - a >= 0.5 else 0
                if n <= 0:
                    continue
                ys = [b - 0.25 - k * pitch for k in range(n)]
                for k, yy in enumerate(ys):
                    for xx in (sx * (WH - T - 0.25), sx * (WH - T - 0.70)):
                        self.seat(xx, yy, Z_FLOOR)
                    if k % 2 == 0:
                        px = sx * 0.30
                        self.tube([(px, yy + 0.28, Z_FLOOR), (px, yy + 0.28, 1.92)], 0.018, 8, "Handrail")
                rails.setdefault(sx, []).append((min(ys) - 0.1, max(ys) + 0.3))
        for sx, spans in rails.items():
            for a, b in spans:
                self.tube([(sx * 0.30, a, 1.92), (sx * 0.30, b, 1.92)], 0.017, 8, "Handrail", cap0=True, cap1=True)
        for _, yc in self.doors:
            for yy in (yc - DOOR_W / 2 - 0.12, yc + DOOR_W / 2 + 0.12):
                self.tube([(WH - 0.32, yy, Z_FLOOR), (WH - 0.32, yy, Z_WTOP)], 0.018, 8, "Handrail")
            self.tube([(0.35, yc, Z_FLOOR), (0.35, yc, Z_WTOP)], 0.018, 8, "Handrail")
            self.cuboid(WH - 0.36, WH - 0.28, yc + DOOR_W / 2 + 0.06, yc + DOOR_W / 2 + 0.10, 1.15, 1.40,
                        "PlasticBlack")
            self.tube([(WH - 0.32, yc - DOOR_W / 2 - 0.12, 1.92), (WH - 0.32, yc + DOOR_W / 2 + 0.12, 1.92)], 0.017,
                      8, "Handrail")
        if self.mpa:
            a, b = self.mpa
            self.tube([(-(WH - T - 0.06), a + 0.1, 0.92), (-(WH - T - 0.06), b - 0.1, 0.92)], 0.018, 8, "Handrail",
                      cap0=True, cap1=True)
            self.cuboid(-(WH - T), -(WH - T - 0.03), a + 0.15, b - 0.15, 0.55, 0.90, "Interior")

    # ---------------------------------------------------------- Zusammenbau
    def build_shell(self):
        ys_r, _ = self.side(1)
        ys_l, _ = self.side(-1)
        self.shoulder(1, ys_r)
        self.shoulder(-1, ys_l)
        self.roof(ys_r, ys_l)
        if self.fc:
            self.front()
            self.roof_edge(1, self.front_xs)
            for sx in (-1, 1):
                self.corner(sx, 1)
                self.octant(sx, 1)
        else:
            self.open_end(self.y_front, 1)
        if self.rc:
            self.rear()
            self.roof_edge(-1, self.rear_xs)
            for sx in (-1, 1):
                self.corner(sx, -1)
                self.octant(sx, -1)
        else:
            self.open_end(self.y_rear, -1)
        self.underbody()
        for spec in self.roof_units:
            self.roof_box(*spec)
        self.interior()

    def D(self, p):
        q = Vector(p)
        if self.fc:
            w = sstep(self.y_front - R - 0.35, self.y_front - R, p.y)
            q.y -= w * (0.16 * sstep(Z_BUMPER, ZT, p.z) + 0.055 * (p.x / WH) ** 2)
        if self.rc:
            w = sstep(self.y_rear + R + 0.35, self.y_rear + R, p.y)
            q.y += w * (0.05 * sstep(Z_BUMPER, ZT, p.z) + 0.04 * (p.x / WH) ** 2)
        return q

    def deform(self):
        for mb in self.mb.values():
            mb.v = [self.D(v) for v in mb.v]

    def display_info(self):
        out = {}
        for name, cs in self.displays.items():
            P = [self.D(c) for c in cs]
            cen = sum(P, Vector()) / 4
            w = (P[1] - P[0]).length
            h = ((P[3] - P[0]).length + (P[2] - P[1]).length) / 2
            n = L.face_normal(P)
            out[name] = dict(center=cen, width=w, height=h, normal=n)
        return out


# =====================================================================
# Räder, Türen, Faltenbalg
# =====================================================================
TIRE_PROF = [(-0.118, 0.292), (-0.132, 0.33), (-0.140, 0.38), (-0.139, 0.43), (-0.128, 0.462), (-0.105, 0.477),
             (-0.07, 0.480), (0.0, 0.481), (0.07, 0.480), (0.105, 0.477), (0.128, 0.462), (0.139, 0.43),
             (0.140, 0.38), (0.132, 0.33), (0.118, 0.292)]
RIM_PROF = [(0.118, 0.292), (0.108, 0.272), (0.080, 0.262), (0.062, 0.245), (0.058, 0.165), (0.066, 0.140),
            (0.095, 0.128), (0.105, 0.10), (0.108, 0.0)]
SEG = 24


def revolve(mb, prof, x_off, ref, mat_fn, smooth):
    segn = []
    for i in range(len(prof) - 1):
        (x0, r0), (x1, r1) = prof[i], prof[i + 1]
        n2 = Vector((r1 - r0, -(x1 - x0)))
        if n2.length < 1e-9:
            n2 = Vector((1, 0))
        n2.normalize()
        mx, mr = (x0 + x1) / 2, (r0 + r1) / 2
        if n2.dot(Vector((mx - ref[0], mr - ref[1]))) < 0:
            n2 = -n2
        segn.append(n2)
    vn = []
    for i in range(len(prof)):
        a = segn[max(0, i - 1)]
        b = segn[min(len(segn) - 1, i)]
        vn.append((a + b).normalized())
    for i in range(len(prof) - 1):
        for k in range(SEG):
            a0, a1 = 2 * math.pi * k / SEG, 2 * math.pi * (k + 1) / SEG

            def P(j, a):
                x, r = prof[j]
                return Vector((x + x_off, r * math.cos(a), r * math.sin(a)))

            def N(nn, a):
                return Vector((nn.x, nn.y * math.cos(a), nn.y * math.sin(a)))
            pts = [P(i, a0), P(i, a1), P(i + 1, a1), P(i + 1, a0)]
            am = (a0 + a1) / 2
            out = N(segn[i], am)
            nl = [N(vn[i], a0), N(vn[i], a1), N(vn[i + 1], a1), N(vn[i + 1], a0)] if smooth else None
            _addq(mb, pts, mat_fn(i), out, nl)


def _addq(mb, pts, mat, out, n=None):
    P = [Vector(p) for p in pts]
    N = [Vector(x) for x in n] if n else None
    keep = []
    for i, p in enumerate(P):
        if keep and (p - P[keep[-1]]).length < 1e-8:
            continue
        keep.append(i)
    if len(keep) > 2 and (P[keep[0]] - P[keep[-1]]).length < 1e-8:
        keep.pop()
    if len(keep) < 3:
        return
    P = [P[i] for i in keep]
    N = [N[i] for i in keep] if N else None
    if L.face_normal(P).dot(Vector(out)) < 0:
        P = P[::-1]
        N = N[::-1] if N else None
    mb.poly(P, mat, n=N)


def wheel_meshes(twin):
    tire, rim = L.MB(), L.MB()
    offs = (-TWIN, TWIN) if twin else (0.0,)
    for xo in offs:
        revolve(tire, TIRE_PROF, xo, (0.0, 0.385), lambda i: "Rubber", True)
    xo = offs[-1]
    revolve(rim, RIM_PROF, xo, (-0.4, 0.2), lambda i: "Rim" if i < 5 else "Chrome", False)
    for k in range(10):
        a = 2 * math.pi * (k + 0.5) / 10
        c = Vector((xo + 0.0615, 0.205 * math.cos(a), 0.205 * math.sin(a)))
        t = Vector((0, -math.sin(a), math.cos(a)))
        rr = Vector((0, math.cos(a), math.sin(a)))
        pts = [c - t * 0.024 - rr * 0.018, c + t * 0.024 - rr * 0.018, c + t * 0.024 + rr * 0.018,
               c - t * 0.024 + rr * 0.018]
        _addq(rim, pts, "BrakeDisc", (1, 0, 0))
        a2 = 2 * math.pi * k / 10
        cy, cz = 0.118 * math.cos(a2), 0.118 * math.sin(a2)
        rim.tube([(xo + 0.085, cy, cz), (xo + 0.118, cy, cz)], [0.013, 0.013], 6, "Chrome", cap1=True)
    return tire, rim


def door_leaf(meet_sign):
    """Türflügel in lokalen Koordinaten: Ursprung = Unterkante Mitte, Außenfläche x=0, Breite entlang y.
    meet_sign: +1 = Stoßkante bei +y (hinterer Flügel), -1 = bei -y (vorderer Flügel)."""
    c = Car(0, 1, False, False, [], [])
    w, h, t = LEAF_W, LEAF_H, 0.04
    y0, y1 = -w / 2, w / 2
    fr = 0.07
    c.cuboid(-t, 0.0, y0, y0 + fr, 0.0, h, "BlackGloss")
    c.cuboid(-t, 0.0, y1 - fr, y1, 0.0, h, "BlackGloss")
    c.cuboid(-t, 0.0, y0 + fr, y1 - fr, h - 0.08, h, "BlackGloss")
    c.cuboid(-t, 0.0, y0 + fr, y1 - fr, 0.0, 0.40, "BlackGloss")
    c.cuboid(-t + 0.004, -0.004, y0 + fr, y1 - fr, 0.40, h - 0.08, "PlasticBlack", skip=("+x", "-x"))
    c.add([(-0.006, y0 + fr, 0.40), (-0.006, y1 - fr, 0.40), (-0.006, y1 - fr, h - 0.08), (-0.006, y0 + fr, h - 0.08)],
          "Glass", (1, 0, 0))
    ym = y1 if meet_sign > 0 else y0
    c.cuboid(-t, 0.008, ym - 0.012, ym + 0.012, 0.0, h, "PlasticBlack")
    c.tube([(-t - 0.05, 0.0, 0.90), (-t - 0.05, 0.0, 1.55)], 0.016, 8, "Handrail", cap0=True, cap1=True)
    c.tube([(-t, 0.0, 0.95), (-t - 0.05, 0.0, 0.95)], 0.012, 6, "Handrail")
    c.tube([(-t, 0.0, 1.50), (-t - 0.05, 0.0, 1.50)], 0.012, 6, "Handrail")
    mb = L.MB()
    for part in c.mb.values():
        off = len(mb.v)
        mb.v += part.v
        for f in part.faces:
            g = dict(f)
            g["idx"] = [i + off for i in f["idx"]]
            g["mat"] = mb.mat(part.mats[f["mat"]])
            mb.faces.append(g)
    return mb


def bellows_mesh():
    mb = L.MB()
    wb, zt, rb = WH - 0.06, ZT - 0.06, 0.30
    zl = Z_FLOOR - 0.02
    prof = [(-wb, zl), (-wb, 1.2), (-wb, zt - rb)]
    for k in range(1, 7):
        a = math.pi - (math.pi / 2) * k / 6
        prof.append((-wb + rb + rb * math.cos(a), zt - rb + rb * math.sin(a)))
    prof.append((0.0, zt))
    for k in range(0, 7):
        a = math.pi / 2 - (math.pi / 2) * k / 6
        prof.append((wb - rb + rb * math.cos(a), zt - rb + rb * math.sin(a)))
    prof += [(wb, 1.2), (wb, zl)]
    nr = 21
    rings = []
    for k in range(nr):
        y = -0.5 + k / (nr - 1)
        ins = 0.0 if k % 2 == 0 else 0.065
        ring = []
        for (x, z) in prof:
            d = Vector((x, 0, z - 1.4))
            if abs(x) >= wb - 1e-6 and z <= zt - rb + 1e-6:
                d = Vector((math.copysign(1, x), 0, 0))
            elif abs(x) < wb - rb + 1e-6:
                d = Vector((0, 0, 1))
            else:
                d = Vector((x - math.copysign(wb - rb, x), 0, z - (zt - rb)))
            d.normalize()
            ring.append(Vector((x, y, z)) - d * ins)
        rings.append(ring)
    for k in range(nr - 1):
        for i in range(len(prof) - 1):
            pts = [rings[k][i], rings[k][i + 1], rings[k + 1][i + 1], rings[k + 1][i]]
            cen = sum(pts, Vector()) / 4
            _addq(mb, pts, "Bellows", Vector((cen.x, 0, cen.z - 1.2)))
    disc = [(1.02 * math.cos(a), 1.02 * math.sin(a), Z_FLOOR + 0.004) for a in [2 * math.pi * i / 28 for i in range(28)]]
    _addq(mb, disc, "InteriorFloor", (0, 0, 1))
    disc2 = [(1.1 * math.cos(a), 1.1 * math.sin(a), Z_BOT) for a in [2 * math.pi * i / 28 for i in range(28)]]
    _addq(mb, disc2, "PlasticBlack", (0, 0, -1))
    for i in range(28):
        a0, a1 = 2 * math.pi * i / 28, 2 * math.pi * (i + 1) / 28
        p = [(1.02 * math.cos(a0), 1.02 * math.sin(a0), Z_FLOOR + 0.004),
             (1.02 * math.cos(a1), 1.02 * math.sin(a1), Z_FLOOR + 0.004),
             (1.07 * math.cos(a1), 1.07 * math.sin(a1), Z_FLOOR + 0.004),
             (1.07 * math.cos(a0), 1.07 * math.sin(a0), Z_FLOOR + 0.004)]
        _addq(mb, p, "PlasticBlack", (0, 0, 1))
    return mb


# =====================================================================
# Objekte, Hierarchie, Export
# =====================================================================
def make_empty(name, loc, parent=None):
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = 0.3
    bpy.context.scene.collection.objects.link(e)
    e.location = loc
    if parent is not None:
        e.parent = parent
    return e


def mesh_obj(name, mb, mats, parent, origin=(0, 0, 0)):
    if not mb.faces:
        return None
    o = Vector(origin)
    mb.v = [v - o for v in mb.v]
    ob = mb.build(name, mats)
    ob.parent = parent
    ob.location = o - (parent.matrix_world.translation if parent is not None else Vector())
    return ob


def add_car_objects(prefix, car, mats, parent, origin):
    names = {"body": "Body", "glass": "Glass", "interior": "Interior", "lights": "Lights"}
    for k, nm in names.items():
        mesh_obj(prefix + nm, car.mb[k], mats, parent, origin)


def add_wheel(key, x, y, twin, mats, parent):
    w = make_empty("Wheel_" + key, Vector((x, y, WHEEL_R)) - parent.matrix_world.translation, parent)
    bpy.context.view_layer.update()
    tire, rim = wheel_meshes(twin)
    for nm, mb in (("Tire_", tire), ("Rim_", rim)):
        ob = mb.build(nm + key, mats)
        ob.parent = w
        ob.location = (0, 0, 0)
        if x < 0:
            ob.rotation_euler = (0, 0, math.pi)
    return w


def add_doors(doors, mats, parent):
    info = []
    for (idx, yc) in doors:
        leaves = {}
        for side, sgn in (("R", 1), ("L", -1)):        # R = vorderer Flügel (aus Sicht von außen rechts)
            yl = yc + sgn * (DOOR_W / 4)
            mb = door_leaf(meet_sign=-1 if sgn > 0 else 1)
            ob = mb.build("Door_%d_%s" % (idx, side), mats)
            ob.parent = parent
            loc = Vector((WH - 0.004, yl, Z_FLOOR + 0.01))
            ob.location = loc - parent.matrix_world.translation
            leaves[ob.name] = dict(closed_local=gd(ob.location), closed_root=gd(loc),
                                   open_offset=[DOOR_OUT, 0.0, round(-sgn * DOOR_SLIDE, 4)])
        info.append(dict(index=idx, center_z=round(-yc, 4), width=DOOR_W, height=round(Z_WTOP - Z_FLOOR, 3),
                         floor_y=Z_FLOOR, side="+X (rechts)", parent=parent.name, leaves=leaves))
    return info


def tri_total(root):
    tot = 0
    for ob in bpy.data.objects:
        if ob.type == "MESH":
            tot += L.tri_count(ob)
    return tot


def bbox_all():
    pts = []
    for ob in bpy.data.objects:
        if ob.type == "MESH":
            mw = ob.matrix_world
            pts += [mw @ v.co for v in ob.data.vertices]
    g = [(p.x, p.z, -p.y) for p in pts]
    return ([round(min(p[i] for p in g), 3) for i in range(3)], [round(max(p[i] for p in g), 3) for i in range(3)])


def export(path):
    for o in bpy.context.scene.objects:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_texcoords=True, export_normals=True,
                              export_materials="EXPORT", export_image_format="AUTO", export_vertex_color="NONE",
                              export_animations=False, export_cameras=False, export_lights=False)
    return os.path.getsize(path)


def disp_json(dinfo, origin=Vector()):
    out = []
    for name in ("front", "side_right", "rear"):
        if name not in dinfo:
            continue
        d = dinfo[name]
        out.append(dict(name=name, center=gd(d["center"] - origin), width=round(d["width"], 3),
                        height=round(d["height"], 3), normal=gd(d["normal"])))
    return out


# =====================================================================
# Busse
# =====================================================================
AX_F, AX_R = 2.9225, -2.9225
Y_FRONT = AX_F + 2.805


def build_solo():
    L.reset()
    L._img_cache.clear()
    mats = materials()
    y_rear = AX_R - 3.35
    doors = [(1, 4.45), (2, 0.0), (3, -4.45)]
    d1r = 4.45 - DOOR_W / 2
    car = Car(y_rear, Y_FRONT, True, True, [AX_F, AX_R], doors, side_display=(d1r - 1.10, d1r - 0.10),
              driver=True, rear_podest=True, mpa=(-1.0, 1.0),
              roof_units=[(-0.95, 0.95, 0.55, 3.15, ROOF_UNIT_H, 0.05, 2), (-0.82, 0.82, -2.35, -0.55, 0.15, 0.04, 0)])
    car.build_shell()
    car.deform()
    root = make_empty("Bus", (0, 0, 0))
    add_car_objects("", car, mats, root, (0, 0, 0))
    bpy.context.view_layer.update()
    for key, x, y, twin in (("FL", -TRACK_F / 2, AX_F, False), ("FR", TRACK_F / 2, AX_F, False),
                            ("RL", -TRACK_R / 2, AX_R, True), ("RR", TRACK_R / 2, AX_R, True)):
        add_wheel(key, x, y, twin, mats, root)
    doors_info = add_doors(doors, mats, root)
    bpy.context.view_layer.update()
    tris = tri_total(root)
    path = os.path.join(OUT, "bus_solo.glb")
    size = export(path)
    mn, mx = bbox_all()
    e = dict(file="bus_solo.glb", length=round(Y_FRONT - y_rear, 3), width=2 * WH, height=round(ZT + ROOF_UNIT_H, 3),
             bbox_length=round(mx[2] - mn[2], 3), bbox_width_with_mirrors=round(mx[0] - mn[0], 3),
             bbox_min=mn, bbox_max=mx,
             wheelbase=round(AX_F - AX_R, 4), axle_z=dict(front=-AX_F, rear=-AX_R),
             track_width=TRACK_F, track_width_rear=TRACK_R, twin_tire_offset=TWIN,
             wheel_radius=WHEEL_R, wheel_width=WHEEL_W, center_of_mass_height_hint=1.05,
             floor_height=Z_FLOOR, front_overhang=2.805, rear_overhang=3.35,
             doors=doors_info, door_motion=DOOR_MOTION, destination_displays=disp_json(car.display_info()),
             materials=sorted(mats), tris=tris, size_bytes=size,
             notes="Niederflur-Solobus 12 m, 3 Doppeltüren rechts (+X). Hinterachse Zwillingsreifen: Wheel_RL/RR "
                   "sitzt in der Zwillingsmitte (track_width_rear), Reifen bei ±twin_tire_offset. "
                   "Knoten: Bus/{Body,Glass,Interior,Lights,Wheel_*,Door_*}. Ursprung Mitte zwischen den Achsen.")
    print("[bus] solo:", tris, "tris", mn, mx, size)
    return e


def build_articulated():
    L.reset()
    L._img_cache.clear()
    mats = materials()
    AX_M = AX_R
    Y_J = AX_M - 1.55
    AX_RR = AX_M - 5.99
    y_rear = AX_RR - 3.435
    front_doors = [(1, 4.45), (2, 0.0)]
    rear_doors = [(3, -6.45), (4, -10.45)]
    d1r = 4.45 - DOOR_W / 2
    fcar = Car(Y_J + 0.45, Y_FRONT, True, False, [AX_F, AX_M], front_doors,
               side_display=(d1r - 1.10, d1r - 0.10), driver=True, mpa=(-1.0, 1.0),
               roof_units=[(-0.95, 0.95, 0.55, 3.15, ROOF_UNIT_H, 0.05, 2), (-0.82, 0.82, -2.6, -1.0, 0.15, 0.04, 0)])
    rcar = Car(y_rear, Y_J - 0.45, False, True, [AX_RR], rear_doors, rear_podest=True, mpa=(-7.2, -5.7),
               roof_units=[(-0.95, 0.95, -8.0, -5.6, ROOF_UNIT_H, 0.05, 2), (-0.82, 0.82, -11.4, -9.9, 0.15, 0.04, 0)])
    for c in (fcar, rcar):
        c.build_shell()
        c.deform()
    root = make_empty("Bus", (0, 0, 0))
    front = make_empty("Front", (0, 0, 0), root)
    rear = make_empty("Rear", (0, Y_J, 0), root)
    bel = make_empty("Bellows", (0, Y_J, 0), root)
    bpy.context.view_layer.update()
    add_car_objects("Front_", fcar, mats, front, (0, 0, 0))
    add_car_objects("Rear_", rcar, mats, rear, (0, Y_J, 0))
    bmb = bellows_mesh()
    ob = bmb.build("Bellows_Mesh", mats)
    ob.parent = bel
    ob.location = (0, 0, 0)
    for key, x, y, twin, par in (("FL", -TRACK_F / 2, AX_F, False, front), ("FR", TRACK_F / 2, AX_F, False, front),
                                 ("ML", -TRACK_M / 2, AX_M, False, front), ("MR", TRACK_M / 2, AX_M, False, front),
                                 ("RL", -TRACK_R / 2, AX_RR, True, rear), ("RR", TRACK_R / 2, AX_RR, True, rear)):
        add_wheel(key, x, y, twin, mats, par)
    doors_info = add_doors(front_doors, mats, front) + add_doors(rear_doors, mats, rear)
    bpy.context.view_layer.update()
    tris = tri_total(root)
    path = os.path.join(OUT, "bus_articulated.glb")
    size = export(path)
    mn, mx = bbox_all()
    disp = disp_json(fcar.display_info()) + disp_json(rcar.display_info())
    for d in disp:
        d["parent"] = "Rear" if d["name"] == "rear" else "Front"
        if d["name"] == "rear":
            d["center_local"] = [d["center"][0], d["center"][1], round(d["center"][2] - (-Y_J), 4)]
    e = dict(file="bus_articulated.glb", length=round(Y_FRONT - y_rear, 3), width=2 * WH,
             height=round(ZT + ROOF_UNIT_H, 3), bbox_length=round(mx[2] - mn[2], 3),
             bbox_width_with_mirrors=round(mx[0] - mn[0], 3), bbox_min=mn, bbox_max=mx,
             wheelbase=round(AX_F - AX_M, 4), wheelbase_rear=round(AX_M - AX_RR, 4),
             axle_z=dict(front=-AX_F, middle=-AX_M, rear=round(-AX_RR, 4)),
             joint_z=round(-Y_J, 4), joint_note="Rear und Bellows haben ihren Ursprung im Gelenkdrehpunkt "
                                                 "(x=0, y=0, z=joint_z); Drehteller-Höhe ca. 0.45 m.",
             middle_axle_to_joint=1.55, joint_to_rear_axle=round(Y_J - AX_RR, 4),
             front_body_end_z=round(-(Y_J + 0.45), 4), rear_body_start_z=round(-(Y_J - 0.45), 4),
             track_width=TRACK_F, track_width_middle=TRACK_M, track_width_rear=TRACK_R, twin_tire_offset=TWIN,
             wheel_radius=WHEEL_R, wheel_width=WHEEL_W, center_of_mass_height_hint=1.05, floor_height=Z_FLOOR,
             doors=doors_info, door_motion=DOOR_MOTION, destination_displays=disp,
             materials=sorted(mats), tris=tris, size_bytes=size,
             notes="Gelenkbus 18.1 m (Schubgelenk), 4 Doppeltüren rechts (+X). Knoten: Bus/Front (Vorderwagen, "
                   "Wheel_FL/FR, Wheel_ML/MR, Door_1/2), Bus/Rear (Nachläufer, Ursprung = Gelenk, Wheel_RL/RR "
                   "Zwilling, Door_3/4), Bus/Bellows (Faltenbalg + Drehteller, Ursprung = Gelenk, halben "
                   "Knickwinkel mitdrehen). Ursprung der Wurzel: Mitte zwischen Vorder- und Mittelachse.")
    print("[bus] articulated:", tris, "tris", mn, mx, size)
    return e


DOOR_MOTION = ("Schwenkschiebetür: Knoten Door_<n>_L/R sitzt geschlossen bündig in der Öffnung (Ursprung = "
               "Unterkante Mitte des Flügels, Außenfläche). Öffnen = Verschieben im Elternraum um open_offset "
               "(Godot-Achsen): Phase 1 (0-30 Prozent) nur x += 0.10 (ausschwenken nach außen), Phase 2 "
               "(30-100 Prozent) z um +-" + f"{DOOR_SLIDE:.3f}" + " (L = hinterer Flügel nach +Z, R = vorderer "
               "Flügel nach -Z). Schließen umgekehrt. Dauer real ca. 2-3 s. L/R = aus Sicht von außen links/rechts.")


def write_manifest(entries):
    p = os.path.join(OUT, "MANIFEST.json")
    m = json.load(open(p))
    for e in entries:
        m[e["file"]] = e
    with open(p, "w") as fh:
        json.dump(m, fh, indent=2, ensure_ascii=False)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    which = argv or ["solo", "articulated"]
    entries = []
    if "solo" in which:
        entries.append(build_solo())
    if "articulated" in which:
        entries.append(build_articulated())
    write_manifest(entries)


if __name__ == "__main__":
    main()
