"""Moderne Pkw-Modelle (Stil europäischer Fahrzeuge ca. 2018–2025, ohne Marken/Logos) als GLB.

  flatpak run org.blender.Blender -b --python "<absoluter Pfad>/tools/blender/cars_build.py" -- [Namen …]
        [--no-preview] [--debug <Ordner>] [--old <Ordner>]

Ohne Namen werden alle Modelle gebaut. Ausgabe: godot/assets/models/cars/<name>.glb, Vorschaubilder
…/previews/<name>_front34.png und …_rear34.png, Einträge in …/MANIFEST.json (nur die eigenen Schlüssel).
--debug schreibt zusätzlich Seiten-/Front-/Heckansicht in den angegebenen Ordner, --old rendert die
alten Modelle (sedan.glb, taxi_player.glb …) zum Vergleich dorthin.

Konvention der GLBs (identisch zu hatchback.glb/sedan.glb/…, siehe godot/scripts/car_model.gd):
  Wurzel "Car" mit den Kindern Body, Glass, Interior, Lights (je ein Mesh) und Wheel_FL/FR/RL/RR
  (Leerknoten in Radmitte, Kinder Rim_xx + Tire_xx, linke Räder 180° um die Hochachse gedreht).
  Fahrzeug schaut nach −Z, rechts = +X, Ursprung am Boden mittig zwischen den Achsen.
  Materialnamen: CarPaint, Glass, HeadlightEmit, IndicatorEmit, TaillightEmit, BrakeLightEmit,
  TaxiSignEmit (nur Taxi), dazu PlasticBlack, BlackGloss, Chrome, Plate, PlateBlue, Interior,
  InteriorSeat, Rim, BrakeDisc, Rubber.
"""
from __future__ import annotations

import json
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cars_lib as CL  # noqa: E402
from cars_lib import Car, MeshB, lerp  # noqa: E402


# --------------------------------------------------------------------------------------------------
# Gestaltungshelfer
# --------------------------------------------------------------------------------------------------
def _cum(poly):
    c = [0.0]
    for i in range(1, len(poly)):
        c.append(c[-1] + math.hypot(poly[i][0] - poly[i - 1][0], poly[i][1] - poly[i - 1][1]))
    return c


def _ev(poly, t):
    c = _cum(poly)
    if c[-1] <= 0:
        return poly[0]
    s = t * c[-1]
    for i in range(1, len(poly)):
        if s <= c[i] or i == len(poly) - 1:
            q = 0.0 if c[i] == c[i - 1] else min(max((s - c[i - 1]) / (c[i] - c[i - 1]), 0.0), 1.0)
            return (lerp(poly[i - 1][0], poly[i][0], q), lerp(poly[i - 1][1], poly[i][1], q))


def sub(top, bot, s0, s1, v0, v1, n=6):
    """Teilfläche eines Bandes in normierten Koordinaten (s längs 0..1, v von oben 0 nach unten 1)."""
    T, B = [], []
    for k in range(n + 1):
        s = lerp(s0, s1, k / n)
        a, b = _ev(top, s), _ev(bot, s)
        T.append((lerp(a[0], b[0], v0), lerp(a[1], b[1], v0)))
        B.append((lerp(a[0], b[0], v1), lerp(a[1], b[1], v1)))
    return T, B


class Design:
    """Zeichnet Flicken auf die Haut. Umfangsmaße an Bug/Heck sind für 1,88 m Fahrzeugbreite angegeben und
    werden auf die tatsächliche Breite skaliert."""

    def __init__(self, car, body, lights, spec):
        self.car, self.body, self.lights, self.spec = car, body, lights, spec
        self.k = car.W_nominal / 1.88

    def _s(self, where, poly):
        if where in ("front", "rear"):
            return [(u * self.k, z) for u, z in poly]
        return list(poly)

    def _mb(self, mat):
        return self.lights if mat.endswith("Emit") else self.body

    def band(self, mat, where, top, bot, level=1, mirror=True, **kw):
        return self.car.band(self._mb(mat), mat, where, self._s(where, top), self._s(where, bot), level=level,
                             mirror=mirror, **kw)

    def ribbon(self, mat, where, pts, width, level=1, mirror=True, **kw):
        return self.car.ribbon(self._mb(mat), mat, where, self._s(where, pts), width, level=level, mirror=mirror, **kw)

    def lamp(self, where, top, bot, housing, parts, level=1, mirror=True):
        """Leuchte: Gehäusefläche + Leuchtelemente parts = [(Material, s0, s1, v0, v1), …]."""
        self.band(housing, where, top, bot, level=level, mirror=mirror)
        for mat, s0, s1, v0, v1 in parts:
            t, b = sub(top, bot, s0, s1, v0, v1)
            self.band(mat, where, t, b, level=level + 1, mirror=mirror)

    def outline(self, mat, where, top, bot, width=0.012, level=2, mirror=False):
        self.ribbon(mat, where, list(top) + list(reversed(bot)) + [top[0]], width, level=level, mirror=mirror)

    def hbars(self, mat, where, top, bot, n, width=0.01, level=2, margin=0.04, mirror=False):
        for k in range(1, n + 1):
            v = k / (n + 1)
            t, _b = sub(top, bot, margin, 1 - margin, v, v, n=8)
            self.ribbon(mat, where, t, width, level=level, mirror=mirror)

    def vbars(self, mat, where, top, bot, n, width=0.008, level=2, mirror=False):
        for k in range(1, n + 1):
            s = k / (n + 1)
            a, b = _ev(top, s), _ev(bot, s)
            self.ribbon(mat, where, [(a[0], a[1] - 0.012), (b[0], b[1] + 0.012)], width, level=level, mirror=mirror)

    def plate(self, where, z):
        CL.add_plate(self.car, self.body, where, z, self.spec["plate"])

    def seam(self, where, pts, mirror=True):
        self.ribbon("PlasticBlack", where, pts, 0.008, level=0, mirror=mirror)

    # ---- Seiten: Türfugen, Schweller, Griffe, Haubenfuge ----
    def side(self, handle="Chrome", sill=0.05):
        car = self.car
        zs = car.gc + 0.085
        d1 = max(car.axles[0] + car.Ra + 0.07, car.d_cowl - 0.20)             # Vorderkante Vordertür
        zb = lambda d: car.f_belt(d) - 0.004
        dB = (car.sw[0][1] + car.sw[1][0]) / 2 if len(car.sw) > 1 else car.sw[0][1] + 0.04
        self.seam("side", [(d1, zb(d1)), (d1 + 0.01, zs)])
        self.seam("side", [(dB, zb(dB)), (dB, zs)])
        dc = car.axles[1]
        R = car.Ra + 0.055
        d_end = car.door_end
        pts = [(d_end, zb(d_end))]
        if d_end > dc - R:                                                    # Fuge läuft um den hinteren Radlauf
            ph1 = math.acos(max(-1.0, min(1.0, (dc - d_end) / R)))
            ph0 = math.asin(max(-1.0, min(1.0, (zs - car.zca) / R)))
            for k in range(8):
                ph = lerp(ph1, ph0, k / 7)
                q = (dc - R * math.cos(ph), car.zca + R * math.sin(ph))
                if q[1] < pts[0][1] - 0.02:
                    pts.append(q)
        else:
            pts.append((d_end, zs))
        self.seam("side", pts)
        self.seam("side", [(d1 + 0.01, zs), (pts[-1][0], zs)])
        if sill:
            da, db = car.axles[0] + car.Ra + 0.02, car.axles[1] - car.Ra - 0.02
            self.band("PlasticBlack", "side", [(da, car.gc + sill), (db, car.gc + sill)],
                      [(da, car.gc - 0.01), (db, car.gc - 0.01)], level=1, seg=0.25, nv=1)
        if handle:
            hz = lambda d: car.f_belt(d) - car.f_sh(d) * 0.55
            for d in (dB - 0.13, min(d_end, dc - R * 0.2) - 0.16):
                self.band(handle, "side", [(d - 0.085, hz(d) + 0.011), (d + 0.085, hz(d) + 0.011)],
                          [(d - 0.085, hz(d) - 0.011), (d + 0.085, hz(d) - 0.011)], level=1)
        self.hood_seam()

    def hood_seam(self, d0=0.30):
        car = self.car
        pts = []
        for k in range(9):
            d = lerp(d0, car.d_cowl - 0.03, k / 8)
            pts.append((d, car.half_section(d)[6][0] * 0.90))
        self.seam("top", pts)


def build_extras(car, body, lights, spec):
    """Dachreling, Haifischflosse, dritte Bremsleuchte."""
    if spec.get("rails"):
        d0, d1 = car.d_head + 0.12, car.d_rend - 0.10
        n = 8
        for side in (-1, 1):
            top, base = [], []
            for k in range(n + 1):
                d = lerp(d0, d1, k / n)
                p = car.pt(d, 10, side)
                lift = 0.042 if 0 < k < n else 0.004
                base.append(p)
                top.append(p + Vector((-side * 0.004, 0, lift)))
            for off in (-0.012, 0.012):
                G = [[q + Vector((off, 0, 0)) for q in base], [q + Vector((off, 0, 0)) for q in top]]
                body.grid(G, "Chrome", smooth=False)
            G = [[q + Vector((-0.012, 0, 0)) for q in top], [q + Vector((0.012, 0, 0)) for q in top]]
            body.grid(G, "Chrome", smooth=False)
    if spec.get("fin", True):
        d = car.d_rend - 0.22
        p = car.pt(d, 14)
        z = p.z - 0.004
        a, b, c = Vector((0, p.y + 0.12, z)), Vector((-0.032, p.y - 0.06, z)), Vector((0.032, p.y - 0.06, z))
        t = Vector((0, p.y - 0.05, z + 0.045))
        mat = spec.get("fin_mat", "CarPaint")
        cen = (a + b + c + t) / 4
        for q in ((a, c, t), (b, a, t), (c, b, t)):
            f = body.face(list(q), mat, smooth=False)
            f.normal_update()
            if f.normal.dot(f.calc_center_median() - cen) < 0:
                f.normal_flip()
    if car.rear_glass:                                   # dritte Bremsleuchte an der Dachhinterkante
        d = car.d_rend + 0.03
        p = car.pt(d, 14)
        loc, nr, _i, _d = car.bvh.find_nearest(Vector((0, p.y, p.z + 0.05)))
        r = Vector((1, 0, 0))
        up = nr.cross(r).normalized()
        o = loc + nr * 0.006
        w = 0.20
        lights.face([o - r * w - up * 0.011, o + r * w - up * 0.011, o + r * w + up * 0.011, o - r * w + up * 0.011],
                    "BrakeLightEmit", smooth=False)


# --------------------------------------------------------------------------------------------------
# Modelle
# --------------------------------------------------------------------------------------------------
def spec_limousine():
    L = 4.95
    return dict(
        klass="Obere Mittelklasse, Stufenheck", L=L, W=1.88, H=1.465, wb=2.96, fo=0.86, track=1.62,
        rw=0.345, tw=0.235, rim_r=0.255, gc=0.165, Rn=0.62, nn=2.5, Rt=0.44, nt=3.8,
        e_nose=(0.10, 0.03, 0.0, 0.0, 0.015, 0.05, 0.12),
        e_tail=(0.12, 0.05, 0.0, 0.0, 0.012, 0.03, 0.036), tail_edge=0.5,
        wheel="double", paint="#5C6368", plate="DD MK 4180",
        belt=[(0, 0.735), (0.22, 0.80), (0.8, 0.90), (1.60, 0.985), (2.8, 0.975), (4.30, 1.03), (4.75, 1.01), (L, 0.95)],
        roof=[(2.25, 1.405), (2.80, 1.465), (3.30, 1.455), (3.75, 1.395)],
        low=[(0, 0.20), (0.45, 0.17), (1.3, 0.165), (3.4, 0.165), (4.3, 0.22), (L, 0.31)],
        taper=[(0, 0.94), (0.86, 0.985), (2.4, 1.0), (3.82, 0.995), (L, 0.93)],
        shoulder=[(0, 0.11), (1.0, 0.085), (1.6, 0.10), (4.2, 0.10), (L, 0.12)],
        tumble=[(1.58, 0.11), (2.8, 0.14), (4.4, 0.20)],
        crown=[(0, 0.0), (0.25, 0.04), (1.58, 0.055), (4.42, 0.03), (4.8, 0.025), (L, 0.0)],
        d_cowl=1.58, d_head=2.28, d_rend=3.72, d_bl=4.42, rw_pow=1.45,
        sw=[(1.74, 2.80), (2.88, 3.70), (3.77, 4.00)], door_end=3.735,
        d_seat=2.62, d_rseat=3.50, chrome_trim=True, pano=(2.45, 3.45), design=design_limousine,
    )


def design_limousine(D):
    # Front: flache, geschwungene Scheinwerfer mit Lichtbraue, breiter Grill mit Querlamellen
    ht = [(0.40, 0.712), (0.70, 0.728), (0.99, 0.762)]
    hb = [(0.45, 0.632), (0.72, 0.622), (0.97, 0.672)]
    D.lamp("front", ht, hb, "BlackGloss", [
        ("HeadlightEmit", 0.03, 0.97, 0.06, 0.20), ("HeadlightEmit", 0.10, 0.36, 0.40, 0.86),
        ("HeadlightEmit", 0.42, 0.66, 0.40, 0.86), ("IndicatorEmit", 0.72, 0.95, 0.44, 0.62)])
    gt = [(-0.44, 0.555), (-0.37, 0.655), (0.37, 0.655), (0.44, 0.555)]
    gb = [(-0.44, 0.555), (-0.39, 0.44), (0.39, 0.44), (0.44, 0.555)]
    D.band("BlackGloss", "front", gt, gb, mirror=False)
    D.outline("Chrome", "front", gt, gb[1:-1], width=0.014)
    D.hbars("Chrome", "front", gt[1:-1], gb[1:-1], 3, width=0.012, margin=0.02)
    D.band("PlasticBlack", "front", [(-0.50, 0.35), (0.50, 0.35)], [(-0.44, 0.235), (0.44, 0.235)], mirror=False)
    D.band("PlasticBlack", "front", [(0.62, 0.40), (0.90, 0.42)], [(0.64, 0.27), (0.86, 0.30)])
    D.ribbon("Chrome", "front", [(0.66, 0.305), (0.85, 0.33)], 0.012, level=2)
    D.plate("front", 0.335)
    D.seam("front", [(-0.38, 0.69), (0.38, 0.69)], mirror=False)
    # Heck: schmale, umgreifende Leuchten, Chromspange
    tt = [(0.26, 0.895), (0.70, 0.905), (1.02, 0.895)]
    tb = [(0.26, 0.835), (0.70, 0.815), (1.00, 0.845)]
    D.lamp("rear", tt, tb, "TaillightEmit", [
        ("BrakeLightEmit", 0.04, 0.46, 0.22, 0.50), ("BrakeLightEmit", 0.52, 0.96, 0.22, 0.50),
        ("IndicatorEmit", 0.06, 0.94, 0.68, 0.86)])
    D.band("BlackGloss", "rear", [(-0.26, 0.885), (0.26, 0.885)], [(-0.26, 0.845), (0.26, 0.845)], mirror=False)
    D.ribbon("Chrome", "rear", [(-0.26, 0.865), (0.26, 0.865)], 0.012, level=2, mirror=False)
    D.plate("rear", 0.665)
    D.band("PlasticBlack", "rear", [(-0.66, 0.42), (0.66, 0.42)], [(-0.58, 0.315), (0.58, 0.315)], mirror=False)
    D.band("Chrome", "rear", [(0.36, 0.39), (0.58, 0.39)], [(0.37, 0.345), (0.56, 0.345)], level=2)
    D.band("TaillightEmit", "rear", [(0.70, 0.475), (0.92, 0.485)], [(0.70, 0.455), (0.92, 0.465)])
    D.seam("rear", [(-0.62, 0.565), (0.62, 0.565)], mirror=False)
    D.side()
    CL.add_mirrors(D.car, D.body)


def spec_taxi():
    s = spec_limousine()
    s.update(klass="Taxi (obere Mittelklasse, Stufenheck)", paint="#E1CC9F", plate="DD TX 2025", taxi=True,
             wheel="multi", pano=None)
    return s


def spec_kombi():
    L = 4.94
    return dict(
        klass="Großer Kombi nordischer Art", L=L, W=1.88, H=1.48, wb=2.94, fo=0.90, track=1.63,
        rw=0.345, tw=0.235, rim_r=0.255, gc=0.17, Rn=0.52, nn=3.1, Rt=0.36, nt=4.4,
        e_nose=(0.10, 0.03, 0.0, 0.0, 0.01, 0.035, 0.09), e_tail=(0.12, 0.05, 0.0, 0.0, 0.015, 0.045, 0.085),
        tail_edge=0.3, wheel="ystar", paint="#3B5169", plate="DD NK 9020",
        belt=[(0, 0.78), (0.2, 0.84), (0.8, 0.925), (1.62, 0.995), (2.9, 0.99), (4.5, 1.02), (L, 1.0)],
        roof=[(2.30, 1.42), (2.90, 1.48), (4.00, 1.455), (4.50, 1.40)],
        low=[(0, 0.21), (0.45, 0.18), (1.3, 0.17), (3.4, 0.17), (4.3, 0.23), (L, 0.33)],
        taper=[(0, 0.95), (0.90, 0.99), (2.4, 1.0), (3.84, 0.995), (L, 0.95)],
        shoulder=[(0, 0.11), (1.0, 0.09), (1.6, 0.10), (L, 0.11)],
        tumble=[(1.62, 0.11), (2.9, 0.14), (4.5, 0.17)],
        crown=[(0, 0.0), (0.25, 0.03), (1.62, 0.045), (4.8, 0.02), (L, 0.0)],
        d_cowl=1.62, d_head=2.30, d_rend=4.48, d_bl=4.80, rw_pow=1.15, rw_bow=0.05,
        sw=[(1.78, 2.82), (2.90, 3.78), (3.86, 4.40)], door_end=3.80,
        d_seat=2.66, d_rseat=3.56, chrome_trim=True, rails=True, design=design_kombi,
    )


def design_kombi(D):
    # Front: aufrechter Grill mit senkrechten Stäben, kantige Scheinwerfer mit waagerechter Lichtklinge
    ht = [(0.50, 0.758), (0.80, 0.768), (0.99, 0.795)]
    hb = [(0.50, 0.682), (0.80, 0.682), (0.975, 0.715)]
    D.lamp("front", ht, hb, "BlackGloss", [
        ("HeadlightEmit", 0.03, 0.97, 0.42, 0.58), ("HeadlightEmit", 0.10, 0.42, 0.10, 0.34),
        ("HeadlightEmit", 0.10, 0.42, 0.66, 0.90), ("IndicatorEmit", 0.50, 0.94, 0.68, 0.88)])
    gt = [(-0.41, 0.752), (0.41, 0.752)]
    gb = [(-0.36, 0.50), (0.36, 0.50)]
    D.band("BlackGloss", "front", gt, gb, mirror=False)
    D.outline("Chrome", "front", gt, gb, width=0.016)
    D.vbars("Chrome", "front", gt, gb, 13, width=0.007)
    D.band("PlasticBlack", "front", [(-0.56, 0.41), (0.56, 0.41)], [(-0.50, 0.265), (0.50, 0.265)], mirror=False)
    D.band("PlasticBlack", "front", [(0.68, 0.47), (0.93, 0.49)], [(0.70, 0.31), (0.89, 0.34)])
    D.ribbon("Chrome", "front", [(0.72, 0.345), (0.88, 0.37)], 0.012, level=2)
    D.plate("front", 0.345)
    D.seam("front", [(-0.44, 0.775), (0.44, 0.775)], mirror=False)
    # Heck: senkrechte Leuchten, die an der D-Säule bis zum Dach laufen
    car = D.car
    tt = [(0.50, 0.925), (0.76, 0.985), (1.03, 0.985)]
    tb = [(0.50, 0.835), (0.76, 0.82), (1.03, 0.82)]
    D.lamp("rear", tt, tb, "TaillightEmit", [
        ("BrakeLightEmit", 0.06, 0.96, 0.30, 0.55), ("IndicatorEmit", 0.06, 0.60, 0.70, 0.88)])
    car.skin_band(D.lights, "TaillightEmit", car.d_rend + 0.05, car.d_bl + 0.02, 7.55, 9.75, level=1)
    car.skin_band(D.lights, "BrakeLightEmit", car.d_rend + 0.09, car.d_bl, 8.3, 9.2, level=2, nr=2)
    D.band("BlackGloss", "rear", [(-0.34, 0.80), (0.34, 0.80)], [(-0.34, 0.66), (0.34, 0.66)], mirror=False)
    D.plate("rear", 0.73)
    D.ribbon("Chrome", "rear", [(-0.52, 0.815), (0.52, 0.815)], 0.012, level=2, mirror=False)
    D.band("PlasticBlack", "rear", [(-0.70, 0.45), (0.70, 0.45)], [(-0.62, 0.335), (0.62, 0.335)], mirror=False)
    D.band("TaillightEmit", "rear", [(0.74, 0.50), (0.95, 0.51)], [(0.74, 0.478), (0.95, 0.488)])
    D.band("Chrome", "rear", [(0.34, 0.42), (0.56, 0.42)], [(0.35, 0.375), (0.54, 0.375)], level=2)
    D.seam("rear", [(-0.66, 0.60), (0.66, 0.60)], mirror=False)
    D.side()
    CL.add_mirrors(D.car, D.body)


def spec_suv_kompakt():
    L = 4.50
    return dict(
        klass="Kompakt-SUV", L=L, W=1.84, H=1.65, wb=2.68, fo=0.91, track=1.59,
        rw=0.355, tw=0.235, rim_r=0.25, gc=0.21, arch_gap=0.065, flare=0.022, clad=1,
        Rn=0.50, nn=3.0, Rt=0.36, nt=4.2,
        e_nose=(0.10, 0.03, 0.0, 0.0, 0.02, 0.05, 0.10), e_tail=(0.12, 0.05, 0.0, 0.0, 0.02, 0.05, 0.08),
        tail_edge=0.3, wheel="five_dark", paint="#E7E8E8", plate="DD SK 3311",
        belt=[(0, 0.90), (0.2, 0.96), (0.8, 1.04), (1.50, 1.11), (2.6, 1.10), (3.9, 1.15), (L, 1.11)],
        roof=[(2.10, 1.585), (2.60, 1.65), (3.50, 1.63), (4.02, 1.57)],
        low=[(0, 0.27), (0.45, 0.225), (1.3, 0.21), (3.0, 0.21), (3.9, 0.26), (L, 0.38)],
        taper=[(0, 0.95), (0.91, 0.99), (2.2, 1.0), (3.59, 0.995), (L, 0.95)],
        shoulder=[(0, 0.13), (1.5, 0.11), (L, 0.12)],
        tumble=[(1.46, 0.10), (2.6, 0.13), (4.3, 0.16)],
        crown=[(0, 0.0), (0.25, 0.03), (1.46, 0.05), (4.36, 0.02), (L, 0.0)],
        d_cowl=1.46, d_head=2.08, d_rend=4.02, d_bl=4.36, rw_pow=1.15, rw_bow=0.05,
        sw=[(1.60, 2.60), (2.68, 3.46), (3.54, 3.94)], door_end=3.50,
        d_seat=2.42, d_rseat=3.26, seat_lift=0.12, rails=True, fin_mat="BlackGloss", design=design_suv_kompakt,
    )


def design_suv_kompakt(D):
    ht = [(0.46, 0.878), (0.80, 0.888), (0.985, 0.91)]
    hb = [(0.48, 0.805), (0.80, 0.802), (0.97, 0.835)]
    D.lamp("front", ht, hb, "BlackGloss", [
        ("HeadlightEmit", 0.04, 0.96, 0.08, 0.26), ("HeadlightEmit", 0.14, 0.58, 0.44, 0.86),
        ("IndicatorEmit", 0.66, 0.95, 0.50, 0.72)])
    D.band("BlackGloss", "front", [(-0.47, 0.874), (0.47, 0.874)], [(-0.48, 0.806), (0.48, 0.806)], mirror=False)
    D.ribbon("HeadlightEmit", "front", [(-0.46, 0.858), (0.46, 0.858)], 0.012, level=2, mirror=False)
    gt = [(-0.53, 0.70), (-0.46, 0.79), (0.46, 0.79), (0.53, 0.70)]
    gb = [(-0.53, 0.70), (-0.43, 0.56), (0.43, 0.56), (0.53, 0.70)]
    D.band("BlackGloss", "front", gt, gb, mirror=False)
    D.hbars("Chrome", "front", gt[1:-1], gb[1:-1], 3, width=0.012, margin=0.03)
    D.band("PlasticBlack", "front", [(-0.58, 0.52), (0.58, 0.52)], [(-0.52, 0.40), (0.52, 0.40)], mirror=False)
    D.band("Chrome", "front", [(-0.42, 0.385), (0.42, 0.385)], [(-0.36, 0.29), (0.36, 0.29)], mirror=False)
    D.band("BlackGloss", "front", [(0.68, 0.585), (0.92, 0.605)], [(0.70, 0.50), (0.90, 0.52)])
    D.ribbon("HeadlightEmit", "front", [(0.72, 0.55), (0.88, 0.565)], 0.016, level=2)
    D.plate("front", 0.46)
    D.seam("front", [(-0.50, 0.895), (0.50, 0.895)], mirror=False)
    tt = [(0.30, 1.045), (0.75, 1.055), (1.02, 1.045)]
    tb = [(0.30, 0.99), (0.75, 0.965), (1.00, 0.985)]
    D.lamp("rear", tt, tb, "TaillightEmit", [
        ("BrakeLightEmit", 0.05, 0.95, 0.15, 0.42), ("IndicatorEmit", 0.40, 0.95, 0.66, 0.86)])
    D.band("BlackGloss", "rear", [(-0.30, 1.04), (0.30, 1.04)], [(-0.30, 0.995), (0.30, 0.995)], mirror=False)
    D.ribbon("TaillightEmit", "rear", [(-0.30, 1.018), (0.30, 1.018)], 0.014, level=2, mirror=False)
    D.plate("rear", 0.82)
    D.band("Chrome", "rear", [(-0.44, 0.47), (0.44, 0.47)], [(-0.38, 0.40), (0.38, 0.40)], mirror=False)
    D.band("TaillightEmit", "rear", [(0.70, 0.60), (0.93, 0.61)], [(0.70, 0.578), (0.93, 0.588)])
    D.seam("rear", [(-0.66, 0.70), (0.66, 0.70)], mirror=False)
    D.side(sill=0)
    CL.add_mirrors(D.car, D.body)


def spec_suv_gross():
    L = 4.95
    return dict(
        klass="Großer SUV", L=L, W=1.95, H=1.76, wb=2.98, fo=0.90, track=1.68,
        rw=0.385, tw=0.27, rim_r=0.28, gc=0.22, arch_gap=0.065, flare=0.022, clad=1,
        Rn=0.50, nn=3.4, Rt=0.36, nt=4.5,
        e_nose=(0.10, 0.03, 0.0, 0.0, 0.015, 0.04, 0.085), e_tail=(0.12, 0.05, 0.0, 0.0, 0.02, 0.05, 0.08),
        tail_edge=0.3, wheel="multi", paint="#2E3D3A", plate="DD GS 7007",
        belt=[(0, 0.98), (0.2, 1.04), (0.9, 1.12), (1.60, 1.18), (2.8, 1.17), (4.3, 1.20), (L, 1.16)],
        roof=[(2.22, 1.69), (2.80, 1.76), (3.90, 1.745), (4.50, 1.69)],
        low=[(0, 0.29), (0.45, 0.24), (1.3, 0.22), (3.3, 0.22), (4.3, 0.28), (L, 0.40)],
        taper=[(0, 0.955), (0.90, 0.99), (2.4, 1.0), (3.88, 0.995), (L, 0.955)],
        shoulder=[(0, 0.13), (1.6, 0.12), (L, 0.12)],
        tumble=[(1.56, 0.11), (2.8, 0.14), (4.6, 0.17)],
        crown=[(0, 0.0), (0.25, 0.03), (1.56, 0.05), (4.82, 0.02), (L, 0.0)],
        d_cowl=1.56, d_head=2.20, d_rend=4.50, d_bl=4.82, rw_pow=1.15, rw_bow=0.05,
        sw=[(1.70, 2.72), (2.80, 3.68), (3.77, 4.42)], door_end=3.72,
        d_seat=2.56, d_rseat=3.46, seat_lift=0.20, rails=True, chrome_trim=True, pano=(2.40, 3.90),
        design=design_suv_gross,
    )


def design_suv_gross(D):
    ht = [(0.52, 0.958), (0.82, 0.968), (0.995, 0.99)]
    hb = [(0.54, 0.862), (0.82, 0.858), (0.98, 0.895)]
    D.lamp("front", ht, hb, "BlackGloss", [
        ("HeadlightEmit", 0.04, 0.96, 0.07, 0.20), ("HeadlightEmit", 0.04, 0.10, 0.20, 0.90),
        ("HeadlightEmit", 0.18, 0.44, 0.36, 0.84), ("HeadlightEmit", 0.50, 0.74, 0.36, 0.84),
        ("IndicatorEmit", 0.20, 0.94, 0.88, 0.97)])
    gt = [(-0.46, 0.955), (0.46, 0.955)]
    gb = [(-0.41, 0.665), (0.41, 0.665)]
    D.band("BlackGloss", "front", gt, gb, mirror=False)
    D.outline("Chrome", "front", gt, gb, width=0.02)
    D.hbars("Chrome", "front", gt, gb, 5, width=0.016, margin=0.03)
    D.band("PlasticBlack", "front", [(-0.60, 0.60), (0.60, 0.60)], [(-0.54, 0.44), (0.54, 0.44)], mirror=False)
    D.band("Chrome", "front", [(-0.46, 0.42), (0.46, 0.42)], [(-0.40, 0.315), (0.40, 0.315)], mirror=False)
    D.band("BlackGloss", "front", [(0.70, 0.66), (0.93, 0.68)], [(0.71, 0.50), (0.90, 0.53)])
    D.ribbon("HeadlightEmit", "front", [(0.73, 0.62), (0.90, 0.64)], 0.016, level=2)
    D.plate("front", 0.525)
    D.seam("front", [(-0.52, 0.975), (0.52, 0.975)], mirror=False)
    tt = [(0.36, 1.125), (0.76, 1.135), (1.03, 1.125)]
    tb = [(0.36, 1.06), (0.76, 1.005), (1.01, 0.985)]
    D.lamp("rear", tt, tb, "TaillightEmit", [
        ("BrakeLightEmit", 0.05, 0.95, 0.12, 0.34), ("BrakeLightEmit", 0.55, 0.95, 0.34, 0.60),
        ("IndicatorEmit", 0.50, 0.95, 0.72, 0.88)])
    D.ribbon("Chrome", "rear", [(-0.36, 1.09), (0.36, 1.09)], 0.022, level=1, mirror=False)
    D.plate("rear", 0.90)
    D.band("PlasticBlack", "rear", [(-0.70, 0.58), (0.70, 0.58)], [(-0.64, 0.46), (0.64, 0.46)], mirror=False)
    D.band("Chrome", "rear", [(-0.48, 0.48), (0.48, 0.48)], [(-0.42, 0.415), (0.42, 0.415)], level=2, mirror=False)
    D.band("BlackGloss", "rear", [(0.50, 0.55), (0.70, 0.55)], [(0.51, 0.495), (0.69, 0.495)], level=2)
    D.band("TaillightEmit", "rear", [(0.74, 0.66), (0.96, 0.67)], [(0.74, 0.638), (0.96, 0.648)])
    D.seam("rear", [(-0.68, 0.76), (0.68, 0.76)], mirror=False)
    D.side(sill=0)
    CL.add_mirrors(D.car, D.body, scale=1.08)


def spec_kompakt():
    L = 4.29
    return dict(
        klass="Kompaktklasse, Schrägheck", L=L, W=1.79, H=1.46, wb=2.63, fo=0.86, track=1.54,
        rw=0.32, tw=0.215, rim_r=0.235, gc=0.165, Rn=0.52, nn=2.6, Rt=0.38, nt=3.8,
        e_nose=(0.10, 0.03, 0.0, 0.0, 0.015, 0.05, 0.12), e_tail=(0.12, 0.05, 0.0, 0.0, 0.015, 0.04, 0.075),
        tail_edge=0.3, wheel="ystar", paint="#8C1C24", plate="DD KM 2408",
        belt=[(0, 0.70), (0.2, 0.77), (0.75, 0.87), (1.42, 0.95), (2.5, 0.955), (3.8, 1.01), (L, 0.975)],
        roof=[(2.02, 1.395), (2.50, 1.46), (3.30, 1.44), (3.74, 1.385)],
        low=[(0, 0.20), (0.45, 0.17), (1.2, 0.165), (2.9, 0.165), (3.7, 0.22), (L, 0.32)],
        taper=[(0, 0.945), (0.86, 0.99), (2.1, 1.0), (3.49, 0.995), (L, 0.945)],
        shoulder=[(0, 0.10), (1.0, 0.085), (1.4, 0.10), (L, 0.11)],
        tumble=[(1.40, 0.10), (2.5, 0.13), (4.1, 0.17)],
        crown=[(0, 0.0), (0.25, 0.035), (1.40, 0.05), (4.1, 0.02), (L, 0.0)],
        d_cowl=1.40, d_head=2.02, d_rend=3.74, d_bl=4.10, rw_pow=1.2,
        sw=[(1.55, 2.50), (2.58, 3.32), (3.39, 3.60)], door_end=3.35,
        d_seat=2.36, d_rseat=3.16, design=design_kompakt,
    )


def design_kompakt(D):
    # Front: schmale Scheinwerfer, durchgehende Lichtleiste, großer unterer Lufteinlass
    ht = [(0.36, 0.678), (0.66, 0.692), (0.955, 0.728)]
    hb = [(0.40, 0.622), (0.68, 0.616), (0.94, 0.658)]
    D.lamp("front", ht, hb, "BlackGloss", [
        ("HeadlightEmit", 0.03, 0.97, 0.08, 0.26), ("HeadlightEmit", 0.12, 0.38, 0.44, 0.86),
        ("HeadlightEmit", 0.44, 0.68, 0.44, 0.86), ("IndicatorEmit", 0.74, 0.95, 0.50, 0.70)])
    D.band("BlackGloss", "front", [(-0.37, 0.676), (0.37, 0.676)], [(-0.41, 0.624), (0.41, 0.624)], mirror=False)
    D.ribbon("HeadlightEmit", "front", [(-0.36, 0.664), (0.36, 0.664)], 0.009, level=2, mirror=False)
    gt = [(-0.66, 0.47), (0.66, 0.47)]
    gb = [(-0.54, 0.24), (0.54, 0.24)]
    D.band("PlasticBlack", "front", gt, gb, mirror=False)
    D.hbars("BlackGloss", "front", gt, gb, 3, width=0.02, margin=0.05)
    D.band("BlackGloss", "front", [(0.76, 0.52), (0.90, 0.54)], [(0.74, 0.30), (0.86, 0.32)])
    D.ribbon("HeadlightEmit", "front", [(0.80, 0.49), (0.86, 0.50)], 0.022, level=2)
    D.ribbon("Chrome", "front", [(-0.56, 0.262), (0.56, 0.262)], 0.012, level=2, mirror=False)
    D.plate("front", 0.36)
    D.seam("front", [(-0.36, 0.695), (0.36, 0.695)], mirror=False)
    tt = [(0.28, 0.905), (0.68, 0.915), (0.98, 0.905)]
    tb = [(0.31, 0.835), (0.68, 0.82), (0.965, 0.85)]
    D.lamp("rear", tt, tb, "TaillightEmit", [
        ("BrakeLightEmit", 0.05, 0.95, 0.14, 0.36), ("BrakeLightEmit", 0.05, 0.40, 0.36, 0.84),
        ("IndicatorEmit", 0.50, 0.95, 0.62, 0.84)])
    D.band("BlackGloss", "rear", [(-0.29, 0.90), (0.29, 0.90)], [(-0.31, 0.84), (0.31, 0.84)], mirror=False)
    D.plate("rear", 0.68)
    D.band("PlasticBlack", "rear", [(-0.74, 0.46), (0.74, 0.46)], [(-0.62, 0.325), (0.62, 0.325)], mirror=False)
    D.band("BlackGloss", "rear", [(-0.40, 0.44), (0.40, 0.44)], [(-0.36, 0.35), (0.36, 0.35)], level=2, mirror=False)
    D.band("TaillightEmit", "rear", [(0.76, 0.52), (0.95, 0.53)], [(0.76, 0.498), (0.95, 0.508)])
    D.seam("rear", [(-0.64, 0.585), (0.64, 0.585)], mirror=False)
    D.side(handle="BlackGloss")
    CL.add_mirrors(D.car, D.body)


def spec_kleinwagen():
    L = 4.05
    return dict(
        klass="Kleinwagen, Schrägheck", L=L, W=1.75, H=1.45, wb=2.55, fo=0.82, track=1.50,
        rw=0.305, tw=0.195, rim_r=0.22, gc=0.16, Rn=0.48, nn=2.5, Rt=0.36, nt=3.6,
        e_nose=(0.10, 0.03, 0.0, 0.0, 0.015, 0.05, 0.11), e_tail=(0.12, 0.05, 0.0, 0.0, 0.015, 0.04, 0.07),
        tail_edge=0.3, wheel="five", paint="#2D7D8A", plate="DD KW 615",
        belt=[(0, 0.70), (0.2, 0.77), (0.7, 0.87), (1.32, 0.95), (2.4, 0.96), (3.6, 1.03), (L, 0.99)],
        roof=[(1.92, 1.39), (2.40, 1.45), (3.10, 1.435), (3.54, 1.385)],
        low=[(0, 0.20), (0.45, 0.165), (1.2, 0.16), (2.8, 0.16), (3.5, 0.22), (L, 0.32)],
        taper=[(0, 0.945), (0.82, 0.99), (2.0, 1.0), (3.37, 0.995), (L, 0.945)],
        shoulder=[(0, 0.10), (1.0, 0.085), (1.3, 0.10), (L, 0.11)],
        tumble=[(1.30, 0.10), (2.4, 0.13), (3.9, 0.17)],
        crown=[(0, 0.0), (0.25, 0.035), (1.30, 0.05), (3.9, 0.02), (L, 0.0)],
        d_cowl=1.30, d_head=1.92, d_rend=3.54, d_bl=3.88, rw_pow=1.2,
        sw=[(1.45, 2.38), (2.46, 3.18)], door_end=3.20,
        d_seat=2.24, d_rseat=3.02, roof_black=True, fin_mat="BlackGloss", design=design_kleinwagen,
    )


def design_kleinwagen(D):
    ht = [(0.36, 0.70), (0.64, 0.74), (0.955, 0.782)]
    hb = [(0.44, 0.625), (0.68, 0.63), (0.94, 0.69)]
    D.lamp("front", ht, hb, "BlackGloss", [
        ("HeadlightEmit", 0.05, 0.95, 0.72, 0.90), ("HeadlightEmit", 0.20, 0.56, 0.16, 0.60),
        ("IndicatorEmit", 0.64, 0.94, 0.20, 0.48)])
    D.band("BlackGloss", "front", [(-0.34, 0.672), (0.34, 0.672)], [(-0.38, 0.628), (0.38, 0.628)], mirror=False)
    D.ribbon("Chrome", "front", [(-0.33, 0.650), (0.33, 0.650)], 0.01, level=2, mirror=False)
    gt = [(-0.50, 0.50), (0.50, 0.50)]
    gb = [(-0.60, 0.26), (0.60, 0.26)]
    D.band("PlasticBlack", "front", gt, gb, mirror=False)
    D.hbars("BlackGloss", "front", gt, gb, 3, width=0.02, margin=0.05)
    D.band("BlackGloss", "front", [(0.72, 0.50), (0.90, 0.52)], [(0.74, 0.38), (0.88, 0.40)])
    D.ribbon("HeadlightEmit", "front", [(0.77, 0.45), (0.86, 0.46)], 0.02, level=2)
    D.plate("front", 0.39)
    D.seam("front", [(-0.34, 0.693), (0.34, 0.693)], mirror=False)
    tt = [(0.50, 0.955), (0.80, 0.965), (0.985, 0.95)]
    tb = [(0.54, 0.815), (0.80, 0.80), (0.97, 0.83)]
    D.lamp("rear", tt, tb, "TaillightEmit", [
        ("BrakeLightEmit", 0.08, 0.92, 0.10, 0.28), ("BrakeLightEmit", 0.08, 0.92, 0.72, 0.90),
        ("BrakeLightEmit", 0.08, 0.22, 0.28, 0.72), ("IndicatorEmit", 0.40, 0.86, 0.40, 0.60)])
    D.plate("rear", 0.70)
    D.band("PlasticBlack", "rear", [(-0.66, 0.44), (0.66, 0.44)], [(-0.58, 0.33), (0.58, 0.33)], mirror=False)
    D.band("TaillightEmit", "rear", [(0.68, 0.50), (0.90, 0.51)], [(0.68, 0.478), (0.90, 0.488)])
    D.seam("rear", [(-0.50, 0.60), (0.50, 0.60)], mirror=False)
    D.side(handle="BlackGloss")
    CL.add_mirrors(D.car, D.body, cap="BlackGloss")


def spec_elektro():
    L = 4.72
    return dict(
        klass="Elektro-Limousine, Fließheck", L=L, W=1.85, H=1.44, wb=2.88, fo=0.84, track=1.60,
        rw=0.335, tw=0.235, rim_r=0.25, gc=0.15, Rn=0.66, nn=2.3, Rt=0.42, nt=3.6,
        e_nose=(0.10, 0.03, 0.0, 0.0, 0.02, 0.07, 0.16), e_tail=(0.12, 0.05, 0.0, 0.0, 0.012, 0.03, 0.03),
        tail_edge=0.3, wheel="aero", paint="#1E3759", plate="DD EL 1E",
        belt=[(0, 0.66), (0.2, 0.73), (0.7, 0.84), (1.30, 0.93), (2.6, 0.95), (4.2, 1.03), (4.6, 1.035), (L, 1.0)],
        roof=[(2.15, 1.385), (2.65, 1.44), (3.20, 1.42), (3.55, 1.375)],
        low=[(0, 0.19), (0.45, 0.155), (1.2, 0.15), (3.3, 0.15), (4.2, 0.21), (L, 0.30)],
        taper=[(0, 0.93), (0.84, 0.985), (2.3, 1.0), (3.72, 0.995), (L, 0.93)],
        shoulder=[(0, 0.10), (1.0, 0.085), (1.3, 0.10), (L, 0.11)],
        tumble=[(1.30, 0.10), (2.6, 0.14), (4.4, 0.21)],
        crown=[(0, 0.0), (0.25, 0.04), (1.30, 0.055), (4.40, 0.03), (L, 0.0)],
        d_cowl=1.30, d_head=2.15, d_rend=3.55, d_bl=4.40, ws_pow=1.3, rw_pow=1.5,
        sw=[(1.52, 2.62), (2.70, 3.52), (3.59, 3.92)], door_end=3.56,
        d_seat=2.50, d_rseat=3.40, pano=(2.28, 3.48), design=design_elektro,
    )


def design_elektro(D):
    # glatte Front ohne Grill, durchgehendes Lichtband
    lt = [(-0.97, 0.672), (-0.55, 0.642), (0.55, 0.642), (0.97, 0.672)]
    lb = [(-0.96, 0.632), (-0.55, 0.606), (0.55, 0.606), (0.96, 0.632)]
    D.band("BlackGloss", "front", lt, lb, mirror=False)
    t, b = sub(lt, lb, 0.01, 0.99, 0.30, 0.70, n=12)
    D.band("HeadlightEmit", "front", t, b, level=2, mirror=False)
    ht = [(0.58, 0.598), (0.94, 0.624)]
    hb = [(0.62, 0.548), (0.92, 0.572)]
    D.lamp("front", ht, hb, "BlackGloss", [
        ("HeadlightEmit", 0.08, 0.32, 0.2, 0.8), ("HeadlightEmit", 0.40, 0.64, 0.2, 0.8),
        ("IndicatorEmit", 0.72, 0.95, 0.3, 0.7)])
    D.band("PlasticBlack", "front", [(-0.56, 0.31), (0.56, 0.31)], [(-0.48, 0.215), (0.48, 0.215)], mirror=False)
    D.band("PlasticBlack", "front", [(0.76, 0.46), (0.84, 0.47)], [(0.74, 0.27), (0.82, 0.28)])
    D.plate("front", 0.41)
    # Heck: durchgehendes Leuchtenband
    tt = [(-1.02, 0.975), (-0.60, 0.985), (0.60, 0.985), (1.02, 0.975)]
    tb = [(-1.00, 0.90), (-0.60, 0.945), (0.60, 0.945), (1.00, 0.90)]
    D.band("TaillightEmit", "rear", tt, tb, mirror=False)
    t, b = sub(tt, tb, 0.01, 0.99, 0.25, 0.55, n=14)
    D.band("BrakeLightEmit", "rear", t, b, level=2, mirror=False)
    D.band("IndicatorEmit", "rear", [(0.80, 0.935), (0.99, 0.925)], [(0.80, 0.915), (0.985, 0.905)], level=2)
    D.plate("rear", 0.64)
    D.band("PlasticBlack", "rear", [(-0.74, 0.47), (0.74, 0.47)], [(-0.62, 0.30), (0.62, 0.30)], mirror=False)
    D.hbars("BlackGloss", "rear", [(-0.74, 0.47), (0.74, 0.47)], [(-0.62, 0.30), (0.62, 0.30)], 2, width=0.02, margin=0.1)
    D.band("TaillightEmit", "rear", [(0.84, 0.52), (0.875, 0.522)], [(0.83, 0.38), (0.865, 0.382)])
    D.seam("rear", [(-0.70, 0.57), (0.70, 0.57)], mirror=False)
    D.seam("rear", [(0.70, 0.57), (0.76, 0.90)])
    D.side(handle="BlackGloss")
    CL.add_mirrors(D.car, D.body, scale=0.92)


def spec_transporter():
    L = 5.14
    return dict(
        klass="Transporter, Kastenwagen", L=L, W=1.93, H=1.97, wb=3.20, fo=0.95, track=1.66,
        rw=0.345, tw=0.215, rim_r=0.215, gc=0.24, arch_gap=0.07, flare=0.016, clad=1,
        Rn=0.40, nn=3.4, Rt=0.22, nt=5.0, rc=0.035, rail_drop=0.17,
        e_nose=(0.10, 0.03, 0.0, 0.0, 0.02, 0.06, 0.13), e_tail=(0.10, 0.03, 0.0, 0.0, 0.0, 0.012, 0.02),
        tail_edge=0.15, wheel="steel", paint="#E4E5E6", plate="DD TR 5040",
        mats={"Rim": {"col": "#7C8086", "rough": 0.45}},
        belt=[(0, 0.98), (0.15, 1.05), (0.55, 1.13), (1.0, 1.20), (2.0, 1.20), (4.8, 1.20), (L, 1.185)],
        roof=[(1.74, 1.90), (2.30, 1.97), (4.60, 1.97), (5.00, 1.955)],
        low=[(0, 0.31), (0.4, 0.265), (1.4, 0.24), (3.8, 0.24), (4.6, 0.27), (L, 0.36)],
        taper=[(0, 0.955), (0.95, 0.99), (2.0, 1.0), (4.6, 1.0), (L, 0.975)],
        shoulder=[(0, 0.16), (1.0, 0.14), (L, 0.14)],
        tumble=[(0.95, 0.075), (2.0, 0.085), (5.0, 0.085)],
        crown=[(0, 0.0), (0.2, 0.03), (0.95, 0.045), (2.0, 0.0), (L, 0.0)],
        d_cowl=0.95, d_head=1.74, d_rend=L - 0.15, d_bl=L - 0.035, ws_pow=1.15, rw_pow=1.0, rw_bow=0.02,
        ws_bow=0.12, rear_glass=False, sw=[(1.13, 1.98)], door_end=None,
        d_seat=1.80, seat_rows=1, seat_lift=0.34, cargo=True, d_bulk=2.16, fin=False, design=design_transporter,
    )


def design_transporter(D):
    car = D.car
    ht = [(0.54, 0.985), (0.80, 1.02), (0.975, 1.07)]
    hb = [(0.58, 0.845), (0.80, 0.835), (0.965, 0.885)]
    D.lamp("front", ht, hb, "BlackGloss", [
        ("HeadlightEmit", 0.05, 0.95, 0.06, 0.18), ("HeadlightEmit", 0.05, 0.13, 0.18, 0.9),
        ("HeadlightEmit", 0.22, 0.62, 0.34, 0.82), ("IndicatorEmit", 0.68, 0.94, 0.40, 0.70)])
    gt = [(-0.52, 0.965), (0.52, 0.965)]
    gb = [(-0.56, 0.85), (0.56, 0.85)]
    D.band("BlackGloss", "front", gt, gb, mirror=False)
    D.hbars("Chrome", "front", gt, gb, 2, width=0.014, margin=0.03)
    D.band("PlasticBlack", "front", [(-1.04, 0.74), (1.04, 0.74)], [(-1.04, 0.40), (1.04, 0.40)], mirror=False)
    D.band("BlackGloss", "front", [(-0.56, 0.70), (0.56, 0.70)], [(-0.50, 0.50), (0.50, 0.50)], level=2, mirror=False)
    D.plate("front", 0.60)
    D.seam("front", [(-0.56, 0.99), (0.56, 0.99)], mirror=False)
    # Heck: hohe senkrechte Leuchten, zwei Hecktüren mit dunklen Fenstern
    ti = [(0.83, 0.96), (0.83, 1.46)]
    to = [(1.00, 0.96), (0.985, 1.46)]
    D.lamp("rear", ti, to, "TaillightEmit", [
        ("BrakeLightEmit", 0.08, 0.50, 0.2, 0.8), ("IndicatorEmit", 0.58, 0.92, 0.2, 0.8)])
    D.band("BlackGloss", "rear", [(0.07, 1.78), (0.74, 1.78)], [(0.07, 1.34), (0.74, 1.34)])
    D.seam("rear", [(0.0, 0.50), (0.0, 1.90)], mirror=False)
    D.seam("rear", [(-0.80, 0.50), (0.80, 0.50)], mirror=False)
    D.band("Chrome", "rear", [(-0.14, 1.12), (-0.03, 1.12)], [(-0.14, 1.08), (-0.03, 1.08)], mirror=False)
    D.plate("rear", 0.78)
    D.band("TaillightEmit", "rear", [(0.60, 0.44), (0.84, 0.45)], [(0.60, 0.42), (0.84, 0.43)])
    # Seite: Fahrertür um den Radlauf, Schiebetür mit Laufschiene
    zs = car.gc + 0.10
    zb = car.f_belt(2.0) - 0.004
    dc, R = car.axles[0], car.Ra + 0.05
    pts = [(1.08, zb)]
    for k in range(7):
        ph = lerp(math.acos((1.08 - dc) / R), math.asin((zs - car.zca) / R), k / 6)
        pts.append((dc + R * math.cos(ph), car.zca + R * math.sin(ph)))
    D.seam("side", pts)
    dB, dS = 2.04, 3.28
    D.seam("side", [(dB, 1.80), (dB, zs)])
    D.seam("side", [(dS, 1.80), (dS, zs)])
    D.seam("side", [(dB, 1.80), (dS, 1.80)])
    D.seam("side", [(pts[-1][0], zs), (dS, zs)])
    D.band("PlasticBlack", "side", [(dS - 0.1, 1.215), (4.75, 1.215)], [(dS - 0.1, 1.185), (4.75, 1.185)], seg=0.3)
    for d in (dB - 0.14, dB + 0.14):
        D.band("PlasticBlack", "side", [(d - 0.08, 1.11), (d + 0.08, 1.11)], [(d - 0.08, 1.07), (d + 0.08, 1.07)])
    D.band("PlasticBlack", "side", [(1.5, 0.62), (3.6, 0.62)], [(1.5, 0.54), (3.6, 0.54)], seg=0.3)
    D.hood_seam(d0=0.2)
    CL.add_mirrors(car, D.body, cap="PlasticBlack", scale=1.3)


SPECS = {
    "kombi_nord": spec_kombi,
    "limousine_ober": spec_limousine,
    "suv_kompakt": spec_suv_kompakt,
    "suv_gross": spec_suv_gross,
    "kompakt_modern": spec_kompakt,
    "kleinwagen_modern": spec_kleinwagen,
    "elektro_limo": spec_elektro,
    "transporter_modern": spec_transporter,
    "taxi_limousine": spec_taxi,
}


# --------------------------------------------------------------------------------------------------
# Bauen, Export, Vorschau
# --------------------------------------------------------------------------------------------------
def build(name, preview=True, debug=None):
    spec = SPECS[name]()
    CL.reset_scene()
    over = {"CarPaint": {"col": spec["paint"]}}
    over.update(spec.get("mats", {}))
    mats = CL.make_materials(over)
    car = Car(spec)
    body, glass = car.build_skin(mats)
    car.build_wells(body)
    lights = MeshB("Lights", mats)
    interior = car.build_interior(mats)
    spec["design"](Design(car, body, lights, spec))
    build_extras(car, body, lights, spec)
    if spec.get("taxi"):
        CL.add_taxi_sign(car, body, lights)
    tris = {m.name: m.tris() for m in (body, glass, interior, lights)}
    xs = [v.co.x for v in body.bm.verts]
    ys = [v.co.y for v in body.bm.verts]
    zs = [v.co.z for v in body.bm.verts] + [v.co.z for v in lights.bm.verts]
    skin_x = max(abs(p[0]) for d in car.S for p in car.half_section(d))
    skin_z = max(p[2] for d in car.S for p in car.half_section(d))
    obs = [body.finish(50.0, uv=True), glass.finish(None), interior.finish(60.0), lights.finish(50.0)]
    wheels, wtris = CL.wheel_objects(mats, car, spec.get("wheel", "multi"))
    tris["Wheels"] = wtris
    root = bpy.data.objects.new("Car", None)
    bpy.context.scene.collection.objects.link(root)
    for o in obs + wheels:
        o.parent = root
    allobs = [root] + obs + wheels + [c for w in wheels for c in w.children]
    path = os.path.join(CL.CARS, name + ".glb")
    size = CL.export_glb(path, allobs)
    total = sum(tris.values())
    entry = {
        "file": name + ".glb",
        "class": spec["klass"],
        "length": round(car.L, 3),
        "width": round(2 * skin_x, 3),
        "height": round(skin_z if not spec.get("taxi") else max(zs), 3),
        "bbox_length": round(max(ys) - min(ys), 3),
        "bbox_width_with_mirrors": round(max(xs) - min(xs), 3),
        "bbox_min": [round(min(xs), 3), round(min(zs), 3), round(-max(ys), 3)],
        "bbox_max": [round(max(xs), 3), round(max(zs), 3), round(-min(ys), 3)],
        "wheelbase": round(car.wb, 3),
        "axle_z": {"front": round(-car.wb / 2, 4), "rear": round(car.wb / 2, 4)},
        "front_overhang": round(car.fo, 3),
        "rear_overhang": round(car.L - car.fo - car.wb, 3),
        "track_width": round(car.track, 3),
        "wheel_radius": round(car.rw, 3),
        "wheel_width": round(car.tw, 3),
        "center_of_mass_height_hint": round(0.30 * max(zs) + 0.02, 2),
        "tris": total,
        "tris_parts": tris,
        "size_bytes": size,
        "preview_paint": spec["paint"],
        "materials": sorted(set(sum((list(o.data.materials.keys()) for o in allobs if o.type == "MESH"), []))),
        "notes": "Knoten Car/{Body,Glass,Interior,Lights,Wheel_FL|FR|RL|RR/{Rim_*,Tire_*}}; schaut nach -Z, rechts +X, "
                 "Ursprung am Boden mittig zwischen den Achsen. Gebaut mit tools/blender/cars_build.py.",
    }
    print("[cars] %-20s L %.2f B %.2f H %.2f  Radstand %.2f  %d Dreiecke %s  %d kB" % (
        name, car.L, entry["width"], entry["height"], car.wb, total, tris, size // 1024))
    if preview or debug:
        CL.set_preview_glow(mats, True)
        sc, co = CL.preview_setup()
        tgt = (0, (max(ys) + min(ys)) / 2, max(zs) * 0.42)
        dist = car.L * 0.92 + 2.3 + 0.8 * max(zs)
        if preview:
            os.makedirs(CL.PREV, exist_ok=True)
            CL.preview_render(sc, co, tgt, (0.62, 0.74, 0.20), dist, os.path.join(CL.PREV, name + "_front34.png"))
            CL.preview_render(sc, co, tgt, (0.62, -0.74, 0.22), dist, os.path.join(CL.PREV, name + "_rear34.png"))
        if debug:
            os.makedirs(debug, exist_ok=True)
            CL.preview_render(sc, co, tgt, (1.0, 0.0, 0.04), dist + 3.0, os.path.join(debug, name + "_side.png"), lens=70)
            CL.preview_render(sc, co, tgt, (0.0, 1.0, 0.06), dist, os.path.join(debug, name + "_front.png"), lens=70)
            CL.preview_render(sc, co, tgt, (0.0, -1.0, 0.08), dist, os.path.join(debug, name + "_rear.png"), lens=70)
            CL.preview_render(sc, co, tgt, (0.35, 0.5, 0.8), dist, os.path.join(debug, name + "_top.png"), lens=60)
            sc.render.resolution_x, sc.render.resolution_y = 1400, 875
            CL.preview_render(sc, co, tgt, (0.62, 0.74, 0.20), dist, os.path.join(debug, name + "_big_f.png"))
            CL.preview_render(sc, co, tgt, (0.62, -0.74, 0.22), dist, os.path.join(debug, name + "_big_r.png"))
    return entry


def render_old(folder):
    for fn in ("sedan.glb", "hatchback.glb", "taxi_player.glb", "van.glb", "citycar.glb"):
        p = os.path.join(CL.CARS, fn)
        if not os.path.exists(p):
            continue
        CL.reset_scene()
        bpy.ops.import_scene.gltf(filepath=p)
        sc, co = CL.preview_setup()
        os.makedirs(folder, exist_ok=True)
        CL.preview_render(sc, co, (0, 0, 0.62), (0.62, 0.74, 0.20), 9.0, os.path.join(folder, "alt_" + fn[:-4] + "_front34.png"))
        CL.preview_render(sc, co, (0, 0, 0.62), (0.62, -0.74, 0.22), 9.0, os.path.join(folder, "alt_" + fn[:-4] + "_rear34.png"))


def write_manifest(entries):
    p = os.path.join(CL.CARS, "MANIFEST.json")
    man = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            man = json.load(f)
    for e in entries:
        man[e["file"]] = e
    with open(p, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1, ensure_ascii=False)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    preview, debug, old, names = True, None, None, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--no-preview":
            preview = False
        elif a == "--debug":
            i += 1
            debug = argv[i]
        elif a == "--old":
            i += 1
            old = argv[i]
        else:
            names.append(a)
        i += 1
    if old:
        render_old(old)
        if not names:
            return
    entries = [build(n, preview, debug) for n in (names or list(SPECS))]
    write_manifest(entries)


if __name__ == "__main__":
    main()
