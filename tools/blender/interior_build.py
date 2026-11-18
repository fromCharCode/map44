"""Cockpit (Fahrerperspektive) für das Spielerauto: Armaturenbrett, Lenkrad, Kombiinstrument, Mittelkonsole,
Türverkleidungen, Sitze, Dachhimmel/Säulenverkleidung, Innenspiegel, Taxameter – ohne Markenlogos.

  flatpak run org.blender.Blender -b --python "<absoluter Pfad>/tools/blender/interior_build.py" -- [name] [--preview <Ordner>]

name = Karosserie-GLB ohne Endung aus godot/assets/models/cars (Standard: taxi_player).
Ausgabe: godot/assets/models/cars/interior/<name>_cockpit.glb und <name>_cockpit.json (Augpunkt, Lenkrad).

Das Cockpit wird an die Karosserie angepasst: Scheibenunterkante, Gürtellinie, Dachkante und Heckscheibe werden aus
den Knoten Body/Glass des Karosserie-GLB gemessen; Säulen- und Dachverkleidung entstehen als nach innen versetzte
Kopie der Karosserie oberhalb der Gürtellinie (passt damit immer zu den Fensteröffnungen).

Koordinaten hier (Blender): rechts = +X, vorn = +Y, oben = +Z. Export Y-up: Godot vorn = −Z.
Knoten im GLB: "Cockpit" (alles Feste), "SteeringWheel" (dreht um die lokale Hochachse des Knotens = Lenksäule).
Materialnamen "ScreenCluster", "ScreenCenter", "ScreenMeter" tragen UV 0..1 und werden im Spiel durch Anzeigen ersetzt
(godot/scripts/car_cockpit.gd); "MirrorGlass" ist die Spiegelfläche des Innenspiegels, "AmbientLight" die
Lichtleiste der Ambientebeleuchtung (leuchtet im Spiel bei Nacht).
"""
from __future__ import annotations

import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CARS = os.path.join(ROOT, "godot", "assets", "models", "cars")
OUT_DIR = os.path.join(CARS, "interior")

# Je Karosserie: Sitzposition des Fahrers (Augpunkt) – alles andere wird gemessen oder relativ dazu gebaut.
CFG = {
    "taxi_player": {"eye": (-0.37, 0.12, 1.23)},
}
DEFAULT_CFG = {"eye": (-0.37, 0.10, 1.22)}


def srgb(r, g, b):
    return tuple(pow(c, 2.2) for c in (r, g, b))


# Name: (Farbe sRGB, Rauheit, Metall)
MATERIALS = {
    "DashSoft": (srgb(0.21, 0.21, 0.22), 0.78, 0.0),
    "DashLower": (srgb(0.2, 0.2, 0.205), 0.7, 0.0),
    "Plastic": (srgb(0.17, 0.17, 0.18), 0.5, 0.0),
    "PianoBlack": (srgb(0.06, 0.06, 0.065), 0.1, 0.0),
    "WheelLeather": (srgb(0.15, 0.148, 0.145), 0.42, 0.0),
    "SeatLeather": (srgb(0.22, 0.215, 0.21), 0.5, 0.0),
    "SeatInsert": (srgb(0.30, 0.295, 0.29), 0.85, 0.0),
    "DoorInsert": (srgb(0.33, 0.32, 0.305), 0.6, 0.0),
    "Headliner": (srgb(0.60, 0.60, 0.585), 0.95, 0.0),
    "Carpet": (srgb(0.14, 0.14, 0.15), 1.0, 0.0),
    "TrimAlu": (srgb(0.56, 0.57, 0.59), 0.32, 1.0),
    "Chrome": (srgb(0.82, 0.82, 0.84), 0.12, 1.0),
    "ButtonGrey": (srgb(0.42, 0.42, 0.43), 0.5, 0.0),
    "MeterCase": (srgb(0.16, 0.16, 0.17), 0.35, 0.0),
    "ScreenCluster": (srgb(0.01, 0.01, 0.012), 0.15, 0.0),
    "ScreenCenter": (srgb(0.01, 0.01, 0.012), 0.15, 0.0),
    "ScreenMeter": (srgb(0.01, 0.01, 0.012), 0.15, 0.0),
    "MirrorGlass": (srgb(0.75, 0.77, 0.8), 0.03, 1.0),
    "AmbientLight": (srgb(0.45, 0.62, 0.72), 0.4, 0.0),
}
MAT_ORDER = list(MATERIALS.keys())


def make_materials():
    out = []
    for name in MAT_ORDER:
        col, rough, metal = MATERIALS[name]
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        b = m.node_tree.nodes.get("Principled BSDF")
        b.inputs["Base Color"].default_value = (*col, 1.0)
        b.inputs["Roughness"].default_value = rough
        b.inputs["Metallic"].default_value = metal
        m.use_backface_culling = True
        m.diffuse_color = (*col, 1.0)
        m.roughness = rough
        m.metallic = metal
        out.append(m)
    return out


# --------------------------------------------------------------------------------------------------
# Netzbaukasten
# --------------------------------------------------------------------------------------------------
def rot(axis, deg):
    return Matrix.Rotation(math.radians(deg), 4, axis)


def tr(x, y, z):
    return Matrix.Translation(Vector((x, y, z)))


def chaikin(pts, n=2):
    """Ecken eines offenen Linienzugs abrunden (Endpunkte bleiben)."""
    for _ in range(n):
        out = [pts[0]]
        for i in range(len(pts) - 1):
            a, b = Vector(pts[i]), Vector(pts[i + 1])
            out.append(tuple(a.lerp(b, 0.25)))
            out.append(tuple(a.lerp(b, 0.75)))
        out.append(pts[-1])
        pts = out
    return pts


class Mesh:
    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.bm.loops.layers.uv.new("UVMap")

    def _add(self, tmp, mat, M=None):
        idx = MAT_ORDER.index(mat)
        if M is not None:
            tmp.transform(M)
        me = bpy.data.meshes.new("tmp")
        tmp.to_mesh(me)
        tmp.free()
        n0 = len(self.bm.faces)
        self.bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        # Materialindex erst hier setzen (ein Mesh ohne Materialplätze verwirft ihn beim Umweg über to_mesh)
        self.bm.faces.ensure_lookup_table()
        for k in range(n0, len(self.bm.faces)):
            self.bm.faces[k].material_index = idx

    @staticmethod
    def _xf(c, M, R):
        """Gesamttransformation: Bezugssystem M, darin Mittelpunkt c, darin Eigendrehung R."""
        T = tr(*c)
        if R is not None:
            T = T @ R
        return M @ T if M is not None else T

    def box(self, c, size, mat, M=None, r=0.0, seg=2, taper=None, R=None):
        """Quader um c (im Bezugssystem M), Eigendrehung R; r = Kantenrundung; taper = (fx, fy) Verjüngung oben."""
        tmp = bmesh.new()
        bmesh.ops.create_cube(tmp, size=1.0)
        for v in tmp.verts:
            v.co.x *= size[0]
            v.co.y *= size[1]
            v.co.z *= size[2]
            if taper and v.co.z > 0:
                v.co.x *= taper[0]
                v.co.y *= taper[1]
        if r > 0:
            bmesh.ops.bevel(tmp, geom=tmp.edges[:], offset=min(r, min(size) * 0.49), segments=seg, affect="EDGES",
                            profile=0.5, clamp_overlap=True)
        bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
        self._add(tmp, mat, self._xf(c, M, R))

    def cyl(self, c, radius, depth, mat, M=None, n=24, r=0.0, r2=None, R=None):
        """Zylinder (Achse lokal Z) um c."""
        tmp = bmesh.new()
        bmesh.ops.create_cone(tmp, cap_ends=True, cap_tris=False, segments=n, radius1=radius,
                              radius2=radius if r2 is None else r2, depth=depth)
        if r > 0:
            edges = [e for e in tmp.edges if abs(e.verts[0].co.z - e.verts[1].co.z) < 1e-6]
            bmesh.ops.bevel(tmp, geom=edges, offset=r, segments=2, affect="EDGES", profile=0.5, clamp_overlap=True)
        bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
        self._add(tmp, mat, self._xf(c, M, R))

    def torus(self, c, R, rx, rz, mat, M=None, nu=56, nv=10, a0=0.0, a1=360.0):
        """Ring in der lokalen XY-Ebene, Querschnitt Ellipse (rx radial, rz axial)."""
        tmp = bmesh.new()
        full = abs(a1 - a0) >= 359.9
        rings = []
        cnt = nu if full else nu + 1
        for i in range(cnt):
            a = math.radians(a0 + (a1 - a0) * i / nu)
            ring = []
            for j in range(nv):
                b = 2 * math.pi * j / nv
                rr = R + rx * math.cos(b)
                ring.append(tmp.verts.new((rr * math.cos(a), rr * math.sin(a), rz * math.sin(b))))
            rings.append(ring)
        for i in range(cnt if full else cnt - 1):
            r0, r1 = rings[i], rings[(i + 1) % cnt]
            for j in range(nv):
                tmp.faces.new((r0[j], r1[j], r1[(j + 1) % nv], r0[(j + 1) % nv]))
        if not full:
            tmp.faces.new(list(reversed(rings[0])))
            tmp.faces.new(rings[-1])
        bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
        self._add(tmp, mat, self._xf(c, M, None))

    def loft(self, sections, mat, closed=False, caps=False, toward=None, M=None):
        """Fläche durch Schnitte (Listen gleich vieler Punkte). closed: Schnitt ist ein Ring; toward: Punkt, dem die
        Flächen zugewandt sein sollen (offene Flächen), sonst Normalen nach außen."""
        tmp = bmesh.new()
        vs = [[tmp.verts.new(p) for p in s] for s in sections]
        n = len(sections[0])
        for i in range(len(vs) - 1):
            for j in range(n if closed else n - 1):
                tmp.faces.new((vs[i][j], vs[i + 1][j], vs[i + 1][(j + 1) % n], vs[i][(j + 1) % n]))
        if caps:
            tmp.faces.new(list(reversed(vs[0])))
            tmp.faces.new(vs[-1])
        bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
        if toward is not None:
            tw = Vector(toward)
            for f in tmp.faces:
                if f.normal.dot(tw - f.calc_center_median()) < 0:
                    f.normal_flip()
        self._add(tmp, mat, M)

    def quad(self, pts, mat, uv=True):
        """Viereck (Punkte: unten links, unten rechts, oben rechts, oben links aus Betrachtersicht) mit UV 0..1."""
        layer = self.bm.loops.layers.uv["UVMap"]
        f = self.bm.faces.new([self.bm.verts.new(p) for p in pts])
        f.material_index = MAT_ORDER.index(mat)
        if uv:
            # glTF/Godot: v läuft von oben nach unten -> oben = 0 nach dem Export (Blender v = 1)
            for lp, t in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
                lp[layer].uv = t

    def finish(self, mats, angle=38.0, M=None):
        bm = self.bm
        sharp = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(angle)]
        bmesh.ops.split_edges(bm, edges=sharp)
        for f in bm.faces:
            f.smooth = True
        if M is not None:
            bm.transform(M)
        me = bpy.data.meshes.new(self.name)
        for m in mats:
            me.materials.append(m)          # vor to_mesh: sonst gehen die Materialindizes der Flächen verloren
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(ob)
        return ob


# --------------------------------------------------------------------------------------------------
# Karosserie vermessen
# --------------------------------------------------------------------------------------------------
def components(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    seen = set()
    out = []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack = [v]
        seen.add(v.index)
        comp = []
        while stack:
            a = stack.pop()
            comp.append(a.co.copy())
            for e in a.link_edges:
                b = e.other_vert(a)
                if b.index not in seen:
                    seen.add(b.index)
                    stack.append(b)
        out.append(comp)
    bm.free()
    return out


def measure(body, glass, eye):
    comps = [c for c in components(glass) if len(c) > 20]

    def span(c, k):
        return max(p[k] for p in c) - min(p[k] for p in c)

    wide = [c for c in comps if span(c, 0) > 1.0]
    ws = max(wide, key=lambda c: sum(p.y for p in c) / len(c))
    rw = min(wide, key=lambda c: sum(p.y for p in c) / len(c))
    side = [c for c in comps if span(c, 0) <= 1.0]
    near = [p for p in ws if abs(p.x - eye[0]) < 0.15]
    base = max(near, key=lambda p: p.y)
    top = max(near, key=lambda p: p.z)
    belt = min(p.z for c in side for p in c)
    wg = max(abs(p.x) for c in side for p in c if p.z < belt + 0.06)
    rb = min(rw, key=lambda p: p.y)
    floor = 0.21
    m = {
        "cowl_y": base.y, "cowl_z": base.z, "head_y": top.y, "head_z": top.z,
        "belt": belt, "wg": wg, "rear_y": rb.y, "rear_z": rb.z, "floor": floor,
        "roof": max(p.z for c in comps for p in c),
    }
    # B-Säule: Lücke zwischen den Seitenscheiben links
    left = sorted([c for c in side if sum(p.x for p in c) < 0], key=lambda c: -max(p.y for p in c))
    if len(left) >= 2:
        m["bpil"] = (max(p.y for p in left[1]), min(p.y for p in left[0]))
    return m


def inner_skin(ck, body, m):
    """Säulen-/Dachverkleidung: Karosserieflächen oberhalb der Gürtellinie, nach innen versetzt und gewendet."""
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.transform(body.matrix_world)
    bm.normal_update()
    z0 = m["belt"] - 0.03
    y0, y1 = m["rear_y"] - 0.06, m["cowl_y"] + 0.06
    xl = m["wg"] + 0.07
    drop = [f for f in bm.faces if not all(v.co.z > z0 and y0 < v.co.y < y1 and abs(v.co.x) < xl for v in f.verts)]
    bmesh.ops.delete(bm, geom=drop, context="FACES")
    # Vorn/hinten: Haube und Kofferraumdeckel liegen unter der Linie Scheibenunterkante -> Dach, wegschneiden
    def below_glass(f):
        c = f.calc_center_median()
        if c.y > m["head_y"]:
            t = (c.y - m["head_y"]) / max(m["cowl_y"] - m["head_y"], 0.01)
            return c.z < m["head_z"] + (m["cowl_z"] - m["head_z"]) * t - 0.10 and abs(c.x) < m["wg"] - 0.12
        return False
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if below_glass(f)], context="FACES")
    for v in bm.verts:
        v.co -= v.normal * 0.014
    for f in bm.faces:
        f.normal_flip()
    ck._add(bm, "Headliner")


# --------------------------------------------------------------------------------------------------
# Bauteile
# --------------------------------------------------------------------------------------------------
def build_dash(ck, m, eye):
    ex = eye[0]
    cy, cz = m["cowl_y"], m["cowl_z"]
    w = m["wg"] + 0.10
    top = cz - 0.022
    prof = [(cy + 0.05, top - 0.005), (cy - 0.12, top), (1.02, top - 0.004), (0.91, top - 0.012), (0.862, top - 0.03),
            (0.842, 0.905), (0.84, 0.86), (0.84, 0.80), (0.825, 0.765), (0.80, 0.70), (0.83, 0.56), (0.93, 0.38),
            (1.08, 0.2)]
    prof = chaikin(prof, 2)
    secs = [[(x, y, z) for y, z in prof] for x in (-w, w)]
    k_low = next(i for i, p in enumerate(prof) if p[1] < 0.79)
    ck.loft([s[:k_low + 1] for s in secs], "DashSoft", toward=(0, 0.0, 1.3))
    ck.loft([s[k_low:] for s in secs], "DashLower", toward=(0, 0.0, 0.6))
    # Lüftungsschlitz an der Scheibe
    ck.box((0.0, cy - 0.07, top + 0.001), (1.15, 0.045, 0.004), "PianoBlack")
    for i in range(22):
        ck.box((-0.55 + i * 0.0524, cy - 0.07, top + 0.004), (0.006, 0.04, 0.003), "Plastic")

    # --- Instrumententräger vor dem Fahrer (Hutze) -----------------------------------------------
    x0, x1 = ex - 0.245, ex + 0.225
    y_lip, y_full, y_end = 0.772, 0.90, 1.16
    h = 0.05
    nu, nv = 18, 12
    secs = []
    for j in range(nv + 1):
        y = y_lip + (y_end - y_lip) * j / nv
        hh = h if y < y_full else h * (0.5 + 0.5 * math.cos(math.pi * (y - y_full) / (y_end - y_full)))
        base_z = top - 0.012 if y < 0.9 else top - 0.004
        sec = []
        for i in range(nu + 1):
            u = i / nu
            a = pow(max(math.sin(math.pi * u), 0.0), 0.5)
            sec.append((x0 + (x1 - x0) * u, y, base_z - 0.02 + (hh + 0.02) * a))
        secs.append(sec)
    tmp = bmesh.new()
    vs = [[tmp.verts.new(p) for p in s] for s in secs]
    for j in range(nv):
        for i in range(nu):
            tmp.faces.new((vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]))
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    if tmp.faces[0].normal.z < 0:
        bmesh.ops.reverse_faces(tmp, faces=tmp.faces[:])
    bmesh.ops.solidify(tmp, geom=tmp.faces[:], thickness=0.012)
    ck._add(tmp, "DashSoft")
    # Rückwand und Anzeige (zum Auge geneigt)
    # Anzeige sitzt in einem Gehäuse vor der Armaturenbrettfront (sonst verdeckt die Front das Bild)
    zc = 0.886
    sw, sh = 0.36, 0.125
    tilt = math.radians(17)
    dy, dz = math.sin(tilt) * sh / 2, math.cos(tilt) * sh / 2
    yb = 0.812
    cx = ex - 0.01
    ck.box((cx, yb + 0.034, zc + 0.004), (x1 - x0 - 0.04, 0.06, sh + 0.05), "DashSoft", R=rot("X", -17), r=0.014)
    ck.quad([(cx - sw / 2, yb - dy, zc - dz), (cx + sw / 2, yb - dy, zc - dz), (cx + sw / 2, yb + dy, zc + dz),
             (cx - sw / 2, yb + dy, zc + dz)], "ScreenCluster")
    ck.box((cx, yb + 0.0035, zc), (sw + 0.014, 0.005, sh + 0.014), "PianoBlack", R=rot("X", -17))

    # --- Mittelbildschirm (frei stehend, leicht zum Fahrer gedreht) ----------------------------------
    scx, scy, scz = 0.03, 0.835, top + 0.035
    Ms = tr(scx, scy, scz) @ rot("Z", -9) @ rot("X", -12)
    ck.box((0, 0, 0), (0.31, 0.014, 0.135), "PianoBlack", M=Ms, r=0.006)
    ck.box((0, 0.02, -0.065), (0.10, 0.03, 0.03), "Plastic", M=Ms, r=0.006)
    q = [Ms @ Vector(p) for p in ((-0.147, -0.0075, -0.06), (0.147, -0.0075, -0.06), (0.147, -0.0075, 0.06),
                                   (-0.147, -0.0075, 0.06))]
    ck.quad([tuple(p) for p in q], "ScreenCenter")

    # --- Lüftungsdüsen ----------------------------------------------------------------------------
    def vent(xc, wv, hv=0.05, zc_=0.853):
        ck.box((xc, 0.834, zc_), (wv, 0.014, hv), "PianoBlack", r=0.004)
        ck.box((xc, 0.83, zc_), (wv - 0.012, 0.012, hv - 0.012), "Plastic")
        for i in range(4):
            ck.box((xc, 0.825, zc_ - (hv - 0.02) / 2 + (hv - 0.02) * i / 3), (wv - 0.016, 0.014, 0.0035), "Plastic",
                   R=rot("X", 18))
        ck.box((xc, 0.818, zc_), (0.008, 0.008, 0.016), "Chrome", r=0.002)

    vent(-m["wg"] + 0.085, 0.11)
    vent(m["wg"] - 0.085, 0.11)
    vent(-0.045, 0.125)
    vent(0.105, 0.125)
    # Lichtleiste der Ambientebeleuchtung unter der Polsterkante
    ck.box((0.0, 0.8405, 0.912), (2 * m["wg"] - 0.05, 0.004, 0.004), "AmbientLight")
    # Zierleiste Beifahrerseite, Handschuhfach-Fuge
    ck.box((0.445, 0.838, 0.853), (0.50, 0.008, 0.03), "TrimAlu", r=0.003)
    ck.box((0.445, 0.812, 0.70), (0.52, 0.004, 0.004), "PianoBlack")
    ck.box((0.445, 0.829, 0.60), (0.52, 0.004, 0.004), "PianoBlack")
    ck.box((0.445, 0.812, 0.685), (0.06, 0.008, 0.014), "Chrome", r=0.003)
    # Lichtschalter links, Startknopf rechts der Lenksäule
    ck.cyl((ex - 0.30, 0.812, 0.745), 0.024, 0.02, "Plastic", R=rot("X", 75), r=0.003)
    ck.cyl((ex - 0.30, 0.806, 0.747), 0.027, 0.004, "Chrome", R=rot("X", 75))
    ck.cyl((ex + 0.215, 0.812, 0.75), 0.017, 0.012, "Chrome", R=rot("X", 75), r=0.002)
    ck.cyl((ex + 0.215, 0.806, 0.752), 0.013, 0.004, "PianoBlack", R=rot("X", 75))
    # Klimabedienteil
    Mk = tr(0.03, 0.808, 0.742) @ rot("X", -17)
    ck.box((0, 0, 0), (0.32, 0.012, 0.062), "PianoBlack", M=Mk, r=0.004)
    for kx in (-0.115, 0.115):
        ck.cyl((kx, -0.012, 0), 0.019, 0.02, "Plastic", M=Mk, R=rot("X", 90), r=0.003)
        ck.cyl((kx, -0.021, 0), 0.021, 0.004, "Chrome", M=Mk, R=rot("X", 90))
    for i in range(5):
        ck.box((-0.056 + i * 0.028, -0.008, -0.012), (0.02, 0.006, 0.012), "ButtonGrey", M=Mk, r=0.002)
    ck.box((0, -0.007, 0.014), (0.13, 0.004, 0.018), "Plastic", M=Mk)

    # --- Taxameter auf dem Armaturenbrett ------------------------------------------------------------
    Mt = tr(0.43, 0.93, top + 0.03) @ rot("Z", -30) @ rot("X", -8)
    ck.box((0, 0, 0), (0.17, 0.055, 0.058), "MeterCase", M=Mt, r=0.006)
    ck.box((0, 0.0, -0.034), (0.05, 0.04, 0.012), "Plastic", M=Mt)
    q = [Mt @ Vector(p) for p in ((-0.072, -0.0285, -0.006), (0.072, -0.0285, -0.006), (0.072, -0.0285, 0.022),
                                   (-0.072, -0.0285, 0.022))]
    ck.quad([tuple(p) for p in q], "ScreenMeter")
    for i in range(4):
        ck.box((-0.054 + i * 0.036, -0.028, -0.017), (0.024, 0.006, 0.009), "ButtonGrey", M=Mt, r=0.002)
    return top


def build_console(ck, m):
    zf = m["floor"]
    path = [(0.83, 0.67), (0.70, 0.60), (0.56, 0.555), (0.40, 0.535), (0.16, 0.535), (0.15, 0.535), (-0.36, 0.535),
            (-0.37, 0.45)]
    hw = 0.135
    secs = [[(-hw, y, zf), (-hw, y, z - 0.012), (-hw + 0.012, y, z), (hw - 0.012, y, z), (hw, y, z - 0.012), (hw, y, zf)]
            for y, z in path]
    ck.loft(secs, "DashLower", closed=False, toward=(0, 0.3, 2.0))
    ck.loft([[(-hw, -0.37, zf), (hw, -0.37, zf)], [(-hw, -0.37, 0.535), (hw, -0.37, 0.535)]], "DashLower",
            toward=(0, -2.0, 0.5))
    # Bedieninsel: Wählhebel, Drehsteller, Becherhalter
    ck.box((0, 0.48, 0.547), (0.20, 0.20, 0.006), "PianoBlack", R=rot("X", 5.5), r=0.002)
    ck.box((-0.035, 0.50, 0.575), (0.036, 0.075, 0.05), "WheelLeather", r=0.012, taper=(0.8, 0.8))
    ck.box((-0.035, 0.50, 0.602), (0.03, 0.062, 0.006), "Chrome", r=0.003)
    ck.cyl((0.05, 0.47, 0.562), 0.027, 0.026, "Chrome", r=0.004)
    ck.cyl((0.05, 0.47, 0.577), 0.022, 0.004, "PianoBlack")
    for bx in (-0.055, 0.055):
        ck.cyl((bx, 0.28, 0.537), 0.043, 0.006, "Chrome")
        ck.cyl((bx, 0.28, 0.539), 0.039, 0.006, "Carpet")
    # Armlehne
    ck.box((0, -0.13, 0.575), (0.25, 0.44, 0.075), "SeatLeather", r=0.022)
    ck.box((0, -0.13, 0.612), (0.20, 0.38, 0.008), "SeatInsert", r=0.003)


def build_wheel(wheel, ck, eye, top):
    """Lenkrad im lokalen System (Z = Lenksäule zum Fahrer, Y = oben in der Radebene) + Mantelrohr/Hebel im Cockpit."""
    R = 0.185
    c = Vector((eye[0], eye[1] + 0.41, 0.895))
    tilt = 23.0
    Mw = tr(*c) @ rot("X", 90 - tilt)       # lokale Z-Achse -> nach hinten/oben zum Fahrer
    # Kranz (leicht abgeflachter Querschnitt), unten etwas dicker
    wheel.torus((0, 0, 0.035), R, 0.0155, 0.018, "WheelLeather", nu=64, nv=12)
    for a0 in (155.0, -25.0):
        wheel.torus((0, 0, 0.035), R, 0.0175, 0.02, "WheelLeather", nu=10, nv=12, a0=a0, a1=a0 + 50.0)
    # Prallplatte und Speichen
    wheel.box((0, -0.008, 0.028), (0.135, 0.10, 0.05), "Plastic", r=0.03, seg=4)
    wheel.torus((0, -0.006, 0.0535), 0.024, 0.003, 0.003, "Chrome", nu=28, nv=6)
    for s in (-1, 1):
        wheel.box((s * 0.118, 0.008, 0.03), (0.115, 0.05, 0.018), "Plastic", r=0.007, R=rot("Y", -s * 6))
        wheel.box((s * 0.112, 0.008, 0.0395), (0.07, 0.034, 0.004), "PianoBlack", R=rot("Y", -s * 6), r=0.002)
        for i in range(3):
            wheel.box((s * (0.091 + i * 0.021), 0.008, 0.0422), (0.013, 0.022, 0.003), "ButtonGrey", R=rot("Y", -s * 6),
                      r=0.001)
    wheel.box((0, -0.112, 0.03), (0.052, 0.14, 0.016), "Plastic", r=0.006)
    wheel.box((0, -0.118, 0.0385), (0.03, 0.085, 0.003), "TrimAlu", r=0.001)
    # Fest: Mantelrohr, Lenkstockhebel
    ck.box((0, -0.012, -0.10), (0.105, 0.10, 0.24), "Plastic", M=Mw, r=0.02)
    for s in (-1, 1):
        # Hebel liegen hinter den Querspeichen (aus Fahrersicht weitgehend verdeckt, bei Lenkeinschlag sichtbar)
        Ml = Mw @ tr(s * 0.05, 0.004, -0.05) @ rot("Y", s * 86)
        ck.cyl((0, 0, 0.04), 0.0075, 0.08, "Plastic", M=Ml, n=12)
        ck.cyl((0, 0, 0.098), 0.0125, 0.045, "Plastic", M=Ml, n=14, r=0.003)
        ck.cyl((0, 0, 0.079), 0.0128, 0.004, "Chrome", M=Ml, n=14)
    return Mw, c, tilt


def build_doors(ck, m):
    zf, belt = m["floor"], m["belt"]
    wd = m["wg"] - 0.035
    y0, y1 = m["rear_y"] + 0.12, m["cowl_y"] + 0.12
    bp = m.get("bpil", (0.30, 0.42))
    for s in (-1, 1):
        cab = (0.0, 0.0, 0.8)
        prof = [(wd, zf), (wd, 0.44)]
        ck.loft([[(s * x, y, z) for x, z in prof] for y in (y0, y1)], "Carpet", toward=cab)
        prof = [(wd, 0.44), (wd, belt - 0.045), (wd - 0.012, belt - 0.03), (wd - 0.014, belt - 0.012),
                (wd - 0.004, belt - 0.001), (wd + 0.03, belt + 0.004), (wd + 0.16, belt + 0.004)]
        prof = chaikin(prof, 1)
        ck.loft([[(s * x, y, z) for x, z in prof] for y in (y0, y1)], "DashSoft", toward=(0, 0, 1.5))
        # Zierleiste durchgehend (setzt die Linie des Armaturenbretts fort)
        ck.box((s * (wd - 0.004), (bp[1] + 0.92) / 2 + 0.02, 0.853), (0.008, 0.92 - bp[1] + 0.06, 0.03), "TrimAlu", r=0.003)
        ck.box((s * (wd - 0.004), (y0 + 0.25 + bp[0]) / 2, 0.853), (0.008, bp[0] - y0 - 0.25, 0.03), "TrimAlu", r=0.003)
        ck.box((s * (wd - 0.002), (bp[1] + 0.92) / 2 + 0.02, 0.834), (0.004, 0.92 - bp[1] + 0.06, 0.004), "AmbientLight")
        ck.box((s * (wd - 0.002), (y0 + 0.25 + bp[0]) / 2, 0.834), (0.004, bp[0] - y0 - 0.25, 0.004), "AmbientLight")
        # B-Säulenfuß
        ck.box((s * (wd - 0.008), (bp[0] + bp[1]) / 2, (zf + belt) / 2), (0.03, bp[1] - bp[0] + 0.03, belt - zf), "Plastic",
               r=0.008)
        for (ya, yb, front) in ((bp[1] + 0.03, 0.97, True), (y0 + 0.30, bp[0] - 0.03, False)):
            L = yb - ya
            yc = (ya + yb) / 2
            # Lederspiegel, Armlehne, Griff
            ck.box((s * (wd - 0.004), yc, 0.775), (0.012, L - 0.05, 0.11), "DoorInsert", r=0.005)
            ck.box((s * (wd - 0.035), yc - 0.02, 0.665), (0.085, L - 0.10, 0.06), "SeatLeather", r=0.018)
            ck.box((s * (wd - 0.04), yc - 0.02, 0.697), (0.06, L - 0.16, 0.006), "SeatInsert", r=0.002)
            ck.box((s * (wd - 0.045), yb - 0.16, 0.7), (0.05, 0.15, 0.008), "PianoBlack", r=0.002)
            for i in range(4 if (front and s < 0) else 1):
                ck.box((s * (wd - 0.045), yb - 0.11 - i * 0.03, 0.705), (0.03, 0.018, 0.005), "Chrome", r=0.0015)
            ck.box((s * (wd - 0.022), yb - 0.10, 0.80), (0.02, 0.09, 0.022), "Chrome", r=0.007)
            # Ablagefach und Lautsprecher
            ck.box((s * (wd - 0.02), yc, 0.33), (0.05, L - 0.12, 0.13), "Plastic", r=0.015)
            if front:
                ck.cyl((s * (wd - 0.004), yb - 0.07, 0.52), 0.07, 0.012, "Chrome", R=rot("Y", 90), n=28)
                ck.cyl((s * (wd - 0.008), yb - 0.07, 0.52), 0.064, 0.012, "Carpet", R=rot("Y", 90), n=28)


def build_seats(ck, m, eye):
    zf = m["floor"]

    def seat(xc, yhip, driver):
        zc = eye[2] - 0.72                      # Sitzfläche unter dem Augpunkt
        # Sitzkissen mit Wangen
        Mc = tr(xc, yhip + 0.21, zc) @ rot("X", 7)
        ck.box((0, 0, 0), (0.50, 0.50, 0.13), "SeatLeather", M=Mc, r=0.045, seg=3)
        ck.box((0, 0.0, 0.062), (0.30, 0.42, 0.012), "SeatInsert", M=Mc, r=0.005)
        ck.box((xc, yhip + 0.21, zc - 0.13), (0.44, 0.44, 0.14), "Plastic", r=0.02)
        # Lehne
        back_h = 0.50 if driver else 0.62
        Mb = tr(xc, yhip - 0.07, zc + 0.03) @ rot("X", 20)
        ck.box((0, 0, back_h / 2), (0.50, 0.13, back_h), "SeatLeather", M=Mb, r=0.05, seg=3, taper=(0.9, 0.8))
        ck.box((0, 0.062, back_h / 2), (0.28, 0.012, back_h - 0.12), "SeatInsert", M=Mb, r=0.005)
        if not driver:
            for px in (-0.06, 0.06):
                ck.cyl((px, 0.0, back_h + 0.04), 0.006, 0.10, "Chrome", M=Mb, n=10)
            ck.box((0, 0.012, back_h + 0.15), (0.27, 0.11, 0.17), "SeatLeather", M=Mb, r=0.04, seg=3)

    seat(eye[0], eye[1] - 0.10, True)
    seat(-eye[0], eye[1] - 0.10, False)
    # Rückbank
    ry = m["rear_y"]
    yb = ry + 0.36
    ws = m["wg"] - 0.10
    Mc = tr(0, yb + 0.30, 0.445) @ rot("X", 6)
    ck.box((0, 0, 0), (2 * ws, 0.52, 0.14), "SeatLeather", M=Mc, r=0.05, seg=3)
    for sx in (-1, 1):
        ck.box((sx * ws * 0.52, 0.0, 0.066), (ws * 0.72, 0.42, 0.012), "SeatInsert", M=Mc, r=0.005)
    ck.box((0, yb + 0.30, 0.31), (2 * ws, 0.48, 0.2), "Plastic")
    Mb = tr(0, yb + 0.06, 0.47) @ rot("X", 23)
    ck.box((0, 0, 0.30), (2 * ws, 0.14, 0.60), "SeatLeather", M=Mb, r=0.055, seg=3)
    for sx in (-1, 1):
        ck.box((sx * ws * 0.52, 0.066, 0.30), (ws * 0.72, 0.012, 0.46), "SeatInsert", M=Mb, r=0.005)
        ck.box((sx * ws * 0.55, 0.01, 0.66), (0.25, 0.10, 0.13), "SeatLeather", M=Mb, r=0.035, seg=3)
    ck.box((0, 0.01, 0.645), (0.22, 0.09, 0.10), "SeatLeather", M=Mb, r=0.03, seg=3)
    # Hutablage, Rückwand, Boden
    zt = m["rear_z"] - 0.02
    ck.loft([[(-m["wg"] - 0.1, yb - 0.12, zt), (m["wg"] + 0.1, yb - 0.12, zt)],
             [(-m["wg"] - 0.1, ry - 0.05, zt), (m["wg"] + 0.1, ry - 0.05, zt)]], "Carpet", toward=(0, 0, 3.0))
    ck.loft([[(-m["wg"] - 0.1, yb - 0.12, zf), (m["wg"] + 0.1, yb - 0.12, zf)],
             [(-m["wg"] - 0.1, yb - 0.12, zt), (m["wg"] + 0.1, yb - 0.12, zt)]], "Carpet", toward=(0, 2.0, 0.6))
    ck.loft([[(-m["wg"] - 0.1, yb - 0.2, zf), (m["wg"] + 0.1, yb - 0.2, zf)],
             [(-m["wg"] - 0.1, m["cowl_y"] + 0.1, zf), (m["wg"] + 0.1, m["cowl_y"] + 0.1, zf)]], "Carpet",
            toward=(0, 0, 3.0))


def build_roof_parts(ck, m, eye):
    hy, hz = m["head_y"], m["head_z"]
    # Innenspiegel am Scheibenkopf
    my, mz = hy + 0.035, hz - 0.085
    ck.cyl((0, hy + 0.045, hz - 0.055), 0.008, 0.05, "Plastic", R=rot("X", 35), n=12)
    to_eye = Vector((eye[0], eye[1], eye[2])) - Vector((0, my, mz))
    yaw = math.degrees(math.atan2(to_eye.x, -to_eye.y)) * 0.5
    Mm = tr(0, my, mz) @ rot("Z", yaw) @ rot("X", 4)
    ck.box((0, 0, 0), (0.25, 0.03, 0.07), "Plastic", M=Mm, r=0.012, seg=3)
    q = [Mm @ Vector(p) for p in ((-0.115, -0.0155, -0.027), (0.115, -0.0155, -0.027), (0.115, -0.0155, 0.027),
                                   (-0.115, -0.0155, 0.027))]
    ck.quad([tuple(p) for p in q], "MirrorGlass")
    # Sonnenblenden, Leseleuchte
    for sx in (eye[0], -eye[0]):
        ck.box((sx, hy - 0.115, hz - 0.035), (0.40, 0.16, 0.018), "Headliner", R=rot("X", -5), r=0.008)
        ck.box((sx + 0.19 * (1 if sx > 0 else -1), hy - 0.04, hz - 0.03), (0.02, 0.02, 0.02), "Plastic", r=0.004)
    ck.box((0, hy - 0.14, hz - 0.028), (0.20, 0.13, 0.025), "Headliner", r=0.01)
    for sx in (-0.045, 0.045):
        ck.box((sx, hy - 0.14, hz - 0.042), (0.06, 0.05, 0.004), "ButtonGrey", r=0.002)
    # Haltegriff Beifahrer
    ck.box((m["wg"] - 0.12, hy - 0.30, hz - 0.045), (0.02, 0.16, 0.02), "Headliner", r=0.007)


# --------------------------------------------------------------------------------------------------
def preview(folder, eye, name):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "MATERIAL"
    sc.display.shading.show_cavity = True
    sc.render.resolution_x, sc.render.resolution_y = 1600, 900
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.sensor_fit = "VERTICAL"
    cam.data.angle = math.radians(60)
    cam.data.clip_start = 0.04
    e = Vector(eye)
    views = {"vorn": (0, -6), "links": (70, -8), "rechts": (-55, -10), "hinten": (180, -5), "unten": (0, -35)}
    for key, (yaw, pitch) in views.items():
        cam.location = e
        cam.rotation_euler = (math.radians(90 + pitch), 0, math.radians(yaw))
        sc.render.filepath = os.path.join(folder, "%s_%s.png" % (name, key))
        bpy.ops.render.render(write_still=True)
    cam.data.angle = math.radians(45)
    cam.location = (1.6, -1.2, 1.9)
    d = Vector((-0.2, 0.6, 0.85)) - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    for ob in bpy.data.objects:
        if ob.name in ("Body", "Glass", "Lights", "Interior"):
            ob.hide_render = True
    sc.render.filepath = os.path.join(folder, "%s_aussen.png" % name)
    bpy.ops.render.render(write_still=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    name = "taxi_player"
    prev = None
    i = 0
    while i < len(argv):
        if argv[i] == "--preview":
            prev = argv[i + 1]
            i += 2
        else:
            name = argv[i]
            i += 1
    cfg = dict(DEFAULT_CFG)
    cfg.update(CFG.get(name, {}))
    eye = cfg["eye"]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(CARS, name + ".glb"))
    body = bpy.data.objects["Body"]
    glass = bpy.data.objects["Glass"]
    m = measure(body, glass, eye)
    print("MASSE", json.dumps({k: (round(v, 3) if isinstance(v, float) else [round(x, 3) for x in v]) for k, v in m.items()}))

    mats = make_materials()
    ck = Mesh("Cockpit")
    wheel = Mesh("SteeringWheel")
    inner_skin(ck, body, m)
    top = build_dash(ck, m, eye)
    build_console(ck, m)
    Mw, wc, tilt = build_wheel(wheel, ck, eye, top)
    build_doors(ck, m)
    build_seats(ck, m, eye)
    build_roof_parts(ck, m, eye)
    ob_ck = ck.finish(mats)
    ob_wh = wheel.finish(mats)
    ob_wh.matrix_world = Mw
    for ob in (ob_ck, ob_wh):
        # unbenutzte Materialplätze entfernen
        used = sorted({p.material_index for p in ob.data.polygons})
        remap = {old: new for new, old in enumerate(used)}
        keep = [ob.data.materials[i] for i in used]
        new_idx = [remap[p.material_index] for p in ob.data.polygons]
        ob.data.materials.clear()                # setzt die Indizes der Flächen zurück -> danach neu vergeben
        for mm in keep:
            ob.data.materials.append(mm)
        ob.data.polygons.foreach_set("material_index", new_idx)
        ob.data.update()
    print("DREIECKE", sum(len(p.vertices) - 2 for ob in (ob_ck, ob_wh) for p in ob.data.polygons))

    if prev:
        os.makedirs(prev, exist_ok=True)
        preview(prev, eye, name)

    os.makedirs(OUT_DIR, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    ob_ck.select_set(True)
    ob_wh.select_set(True)
    out = os.path.join(OUT_DIR, name + "_cockpit.glb")
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_normals=True, export_texcoords=True, export_materials="EXPORT")
    info = {
        "car": name + ".glb",
        "eye": [round(eye[0], 3), round(eye[2], 3), round(-eye[1], 3)],          # Godot: x, y, z (vorn = −z)
        "wheel_center": [round(wc.x, 3), round(wc.z, 3), round(-wc.y, 3)],
        "wheel_tilt_deg": tilt,
        "notes": "Knoten Cockpit (fest) und SteeringWheel (um lokale Y-Achse drehen); Materialien ScreenCluster/"
                 "ScreenCenter/ScreenMeter mit UV 0..1, MirrorGlass = Innenspiegel. Gebaut von tools/blender/interior_build.py.",
    }
    with open(os.path.join(OUT_DIR, name + "_cockpit.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=1, ensure_ascii=False)
    print("GESCHRIEBEN", out)


main()
