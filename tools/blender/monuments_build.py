"""Baut Denkmäler, Standbilder und Brunnen nach godot/assets/models/monuments/mon_*.glb.

Aufruf (Projektordner, immer nur ein Blender gleichzeitig):
  flatpak run org.blender.Blender -b --python "$PWD/tools/blender/monuments_build.py" [-- name ...] [--nopreview]

Konvention wie bei den Stadtmöbeln: Blender Z-up, Meter, Ursprung = Bodenmitte, Vorderseite +Y (= Godot -Z).
Die Figuren stammen vom geriggten Fußgänger godot/assets/models/peds/ped_m.glb (gepost, eingebacken, ohne Armatur);
das Pferd entsteht aus gelofteten Ellipsenringen. Materialien sind reine PBR-Farben ohne Texturen.
Vorschaubilder (EEVEE, 512 px je Ansicht) landen in godot/assets/models/monuments/previews/.
"""
import math
import os
import sys
import tempfile

import bpy
import bmesh
from mathutils import Matrix, Vector, noise

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_had_tmp = os.path.isdir(os.path.join(HERE, "furniture_tmp"))
import furniture_lib as L  # noqa: E402
from furniture_lib import (V, Soup, mat, loft, lathe, cyl, cbox, tube, circle, rrect, rect,  # noqa: E402
                           build, finish, ico, M_T, M_R, TAU)

# Die Bibliothek schreibt sonst in den Möbel-Ordner: auf den Denkmal-Ordner umbiegen.
if not _had_tmp:
    try:
        os.rmdir(os.path.join(HERE, "furniture_tmp"))
    except OSError:
        pass
L.OUT = os.path.join(L.ROOT, "godot", "assets", "models", "monuments")
L.PREV = os.path.join(L.OUT, "previews")
L.TMP = tempfile.mkdtemp(prefix="monuments_")
for _d in (L.OUT, L.PREV):
    os.makedirs(_d, exist_ok=True)
PED = os.path.join(L.ROOT, "godot", "assets", "models", "peds", "ped_m.glb")

_setup_orig = L._setup_preview_scene


def _setup_512():
    cam = _setup_orig()
    bpy.context.scene.render.resolution_x = 512
    bpy.context.scene.render.resolution_y = 512
    return cam


L._setup_preview_scene = _setup_512

STONE, BRONZE, GOLD, GRANITE, WATER, STEEL = "Sandstein", "Bronze", "Gold", "Granit", "Wasser", "Stahl"


def mats():
    mat(STONE, "#B8A888", 0.85)
    mat(BRONZE, "#4A5A4A", 0.5, 0.9)
    mat(GOLD, "#D4A63A", 0.3, 1.0)
    mat(GRANITE, "#7A7A78", 0.75)
    mat(WATER, "#3A5A60", 0.1)
    mat(STEEL, "#9A9FA3", 0.35, 0.9)


# ====================================================================== Figur (Fußgänger posen und einbacken)
def _figures(poses):
    """Importiert den Fußgänger einmal und liefert je Pose (Soup, Gelenke {Knochen: (Kopf, Ende)}).
    Pose = Liste (Knochen, Richtung) in Eltern-vor-Kind-Reihenfolge: der Knochen wird auf die Richtung gedreht."""
    L.reset()
    bpy.ops.import_scene.gltf(filepath=PED)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    body = next(o for o in bpy.data.objects if o.type == "MESH" and o.parent == arm)
    arm.animation_data_clear()
    out = {}
    for name, pose in poses.items():
        for pb in arm.pose.bones:
            pb.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
        for bone, d in pose:
            pb = arm.pose.bones[bone]
            h = pb.head.copy()
            q = (pb.tail - pb.head).normalized().rotation_difference(Vector(d).normalized())
            pb.matrix = Matrix.Translation(h) @ q.to_matrix().to_4x4() @ Matrix.Translation(-h) @ pb.matrix
            bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        eo = body.evaluated_get(dg)
        me = eo.to_mesh()
        s = Soup()
        for v in me.vertices:
            s.vert(eo.matrix_world @ v.co)
        skip = {i for i, ms in enumerate(me.materials) if ms and ms.name.startswith("Accessory")}   # Rucksack o. Ä.
        for p in me.polygons:
            if p.material_index not in skip:
                s.face(list(p.vertices), BRONZE)
        eo.to_mesh_clear()
        joints = {pb.name: (arm.matrix_world @ pb.head, arm.matrix_world @ pb.tail) for pb in arm.pose.bones}
        out[name] = (s, joints)
    return out


def _sit(extra):
    """Reitersitz: Schenkel gespreizt nach vorn, Unterschenkel hängen; extra = Armhaltung."""
    p = []
    for side, sg in (("L", -1), ("R", 1)):   # im Modell liegt _L bei -X
        p += [("UpperLeg_" + side, (sg * 0.50, 0.70, -0.50)), ("LowerLeg_" + side, (sg * 0.10, -0.22, -1.0)),
              ("Foot_" + side, (sg * 0.15, 1.0, -0.12))]
    return p + extra


POSES = {
    "rest": [],
    # Standbild: Spielbein leicht vor, rechte Hand vor der Brust (Schriftrolle), Kopf gedreht
    "stand": [("UpperLeg_L", (-0.03, 0.17, -1.0)), ("LowerLeg_L", (-0.02, -0.04, -1.0)), ("Foot_L", (-0.2, 1.0, -0.2)),
              ("Neck", (0.0, 0.05, 1.0)), ("Head", (0.10, 0.06, 1.0)),
              ("UpperArm_R", (0.22, 0.12, -0.95)), ("LowerArm_R", (-0.45, 0.78, 0.35)), ("Hand_R", (-0.5, 0.6, 0.6)),
              ("UpperArm_L", (-0.25, -0.05, -0.95)), ("LowerArm_L", (-0.12, 0.25, -0.95))],
    # König: Zügel links, Zepter rechts auf den Schenkel gestützt
    "king": _sit([("UpperArm_L", (-0.15, 0.35, -0.92)), ("LowerArm_L", (0.28, 0.85, -0.40)),
                  ("UpperArm_R", (0.30, 0.20, -0.92)), ("LowerArm_R", (0.10, 0.90, -0.15))]),
    # Imperator: Zügel links, rechter Arm mit Feldherrnstab weit ausgestreckt
    "imperator": _sit([("UpperArm_L", (-0.15, 0.35, -0.92)), ("LowerArm_L", (0.28, 0.85, -0.40)),
                       ("UpperArm_R", (0.70, 0.45, -0.50)), ("LowerArm_R", (0.65, 0.70, 0.05)),
                       ("Hand_R", (0.6, 0.75, 0.1))]),
}
FIG = {}


def fig(name, m=BRONZE):
    s, j = FIG[name]
    return s.copy().setmat(m), j


def crescent(z, cy, rx, ry, th=0.035, half=115.0, k=8):
    """Offener Mantelquerschnitt hinter der Figur (Rücken = -Y), als geschlossene Sichel."""
    outer, inner = [], []
    for i in range(k + 1):
        a = math.radians(-90.0 - half + 2 * half * i / k)
        outer.append(V((math.cos(a) * rx, cy + math.sin(a) * ry, z)))
        inner.append(V((math.cos(a) * (rx - th), cy + math.sin(a) * (ry - th), z)))
    return outer + inner[::-1]


def cloak(levels, m, **kw):
    return loft([crescent(*lv, **kw) for lv in levels], m)


def bust_soup():
    """Fußgänger oberhalb der Brust, Arme gekappt, Schnittflächen geschlossen."""
    s, _ = fig("rest")
    bm = bmesh.new()
    vs = [bm.verts.new(co) for co in s.v]
    for idx, _, _ in s.f:
        try:
            bm.faces.new([vs[i] for i in idx])
        except ValueError:
            pass
    for co, no in (((0, 0, 1.24), (0, 0, -1)), ((0.19, 0, 0), (1, 0, 0)), ((-0.19, 0, 0), (-1, 0, 0))):
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no, clear_outer=True)
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    out = Soup()
    bm.verts.index_update()
    for v in bm.verts:
        out.vert(v.co)
    for f in bm.faces:
        out.face([v.index for v in f.verts], BRONZE)
    bm.free()

    def taper(co):      # klassische Büstenform: von den Schultern zum Fuß hin eingezogen
        t = min(max((co.z - 1.24) / 0.20, 0.0), 1.0)
        t = t * t * (3 - 2 * t)
        return (co.x * (0.50 + 0.50 * t), co.y * (0.72 + 0.28 * t), co.z)
    return out.warp(taper)


# ====================================================================== Stein-Bausteine
def stack(levels, m, r=0.0, cx=0.0, cy=0.0):
    """Gestapeltes Rechteckprofil: levels = [(Breite X, Tiefe Y, z), ...] von unten nach oben."""
    if r > 0:
        rings = [rrect(w, d, r, 2, z, cx, cy) for w, d, z in levels]
    else:
        rings = [rect(w, d, z, cx, cy) for w, d, z in levels]
    return loft(rings, m, orient=V((0, 0, 1)))


def pedestal(w, d, h, m=STONE, step=0.22, z0=0.0, r=0.0):
    """Profilierter Sockel: Stufe, Plinthe, Fußprofil, Schaft, Gesims. w/d = Schaftmaß, h = Gesamthöhe."""
    p = 0.10 + 0.03 * h      # Ausladung der Profile
    zb = z0 + step
    zs = zb + 0.14 * h       # Schaftbeginn
    zc = z0 + h - 0.13 * h   # Gesimsbeginn
    lv = [(w + 6 * p, d + 6 * p, z0), (w + 6 * p, d + 6 * p, zb),
          (w + 3 * p, d + 3 * p, zb), (w + 3 * p, d + 3 * p, zb + (zs - zb) * 0.6),
          (w + 1.6 * p, d + 1.6 * p, zb + (zs - zb) * 0.75), (w, d, zs),
          (w, d, zc), (w + 0.8 * p, d + 0.8 * p, zc + (z0 + h - zc) * 0.25),
          (w + 2.2 * p, d + 2.2 * p, zc + (z0 + h - zc) * 0.55), (w + 2.2 * p, d + 2.2 * p, z0 + h - 0.04),
          (w + 1.4 * p, d + 1.4 * p, z0 + h)]
    return stack(lv, m, r=r), zs, zc


def plaque(w, h, zc, y, m=BRONZE, t=0.03, back=False):
    """Tafel auf einer Fläche bei y (Vorderseite +Y; back: Rückseite)."""
    if back:
        return cbox(0, y - t / 2, zc - h / 2, w, t, h, m)
    return cbox(0, y + t / 2, zc - h / 2, w, t, h, m)


def prism_y(xz, y0, y1, m):
    return loft([[V((x, y, z)) for x, z in xz] for y in (y0, y1)], m)


# ====================================================================== Pferd
def _cr(p0, p1, p2, p3, t):
    return tuple(0.5 * ((2 * b) + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t * t + (-a + 3 * b - 3 * c + d) * t ** 3)
                 for a, b, c, d in zip(p0, p1, p2, p3))


def spline(cps, sub=3):
    out = []
    n = len(cps)
    for i in range(n - 1):
        p0, p1, p2, p3 = cps[max(i - 1, 0)], cps[i], cps[i + 1], cps[min(i + 2, n - 1)]
        for k in range(sub):
            out.append(_cr(p0, p1, p2, p3, k / sub))
    out.append(tuple(cps[-1]))
    return out


def limb(cps, n, m, x0=0.0, sub=3):
    """Schlauch in einer Ebene parallel zu YZ: cps = [(y, z, rx, rn)], rn = Halbmesser quer zur Bahn."""
    pts = spline(cps, sub)
    rings = []
    for i, (y, z, rx, rn) in enumerate(pts):
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, len(pts) - 1)]
        t = V((0, b[0] - a[0], b[1] - a[1])).normalized()
        nn = V((0, -t.z, t.y))
        rings.append([V((x0 + math.cos(TAU * k / n) * rx, y, z)) + nn * (math.sin(TAU * k / n) * rn)
                      for k in range(n)])
    return loft(rings, m)


def horse(m, rearing=False):
    """Pferd in Lebensgröße (Widerrist ~1,6 m), Kopf nach +Y. Liefert (Soup, Matrix für Aufsitzendes)."""
    front = Soup()   # alles, was beim Steigen mitdreht
    # Rumpf: Stationen (y, z unten, z oben, halbe Breite)
    st = [(-0.99, 1.22, 1.36, 0.05), (-0.92, 1.02, 1.50, 0.21), (-0.66, 0.89, 1.58, 0.30), (-0.30, 0.86, 1.53, 0.30),
          (0.05, 0.82, 1.50, 0.31), (0.40, 0.84, 1.57, 0.29), (0.62, 0.94, 1.55, 0.25), (0.79, 1.08, 1.46, 0.17),
          (0.85, 1.18, 1.38, 0.05)]
    rings = []
    for y, zb, zt, hw in spline(st, 3):
        zc, rz = (zb + zt) / 2, (zt - zb) / 2
        # oben etwas schmaler (Rückenlinie), unten voller Bauch
        rings.append([V((math.cos(a) * hw * (1.0 - 0.18 * max(math.sin(a), 0.0)), y, zc + math.sin(a) * rz))
                      for a in (TAU * k / 14 for k in range(14))])
    front.add(loft(rings, m))
    # Satteldecke
    front.add(loft([[V((math.cos(a) * 0.325, y, 1.17 + math.sin(a) * 0.355)) for a in (TAU * k / 14 for k in range(14))]
                    for y in (-0.36, -0.33, 0.24, 0.27)], m))
    neck = [(0.42, 1.28, 0.20, 0.33), (0.62, 1.52, 0.17, 0.29), (0.80, 1.78, 0.13, 0.22), (0.95, 1.99, 0.105, 0.17),
            (1.02, 2.10, 0.09, 0.13)]
    if rearing:      # Hals stärker gewölbt, Kopf angezogen
        neck = [(0.42, 1.28, 0.20, 0.33), (0.60, 1.56, 0.17, 0.29), (0.74, 1.84, 0.13, 0.22), (0.90, 2.04, 0.105, 0.17),
                (1.00, 2.10, 0.09, 0.13)]
    front.add(limb(neck, 12, m))
    px, pz = neck[-1][0], neck[-1][1]
    head = [(px - 0.07, pz + 0.02, 0.09, 0.12), (px + 0.03, pz - 0.04, 0.115, 0.165), (px + 0.17, pz - 0.21, 0.10, 0.145),
            (px + 0.30, pz - 0.38, 0.075, 0.10), (px + 0.385, pz - 0.48, 0.07, 0.09), (px + 0.42, pz - 0.525, 0.045, 0.055)]
    if rearing:
        head = [(px - 0.07, pz + 0.02, 0.09, 0.12), (px + 0.02, pz - 0.05, 0.115, 0.165), (px + 0.12, pz - 0.24, 0.10, 0.145),
                (px + 0.20, pz - 0.43, 0.075, 0.10), (px + 0.25, pz - 0.55, 0.07, 0.09), (px + 0.27, pz - 0.60, 0.045, 0.055)]
    front.add(limb(head, 10, m))
    for sx in (-1, 1):
        front.add(lathe([(0.045, 0.0), (0.04, 0.07), (0.0, 0.17)], 6, m).rot((0, 1, 0), sx * 14)
                  .move(sx * 0.07, px - 0.05, pz + 0.08))
    # Mähne: schmaler Kamm auf der Halsoberseite
    mane = []
    for i, (y, z, rx, rn) in enumerate(neck):
        a, b = neck[max(i - 1, 0)], neck[min(i + 1, len(neck) - 1)]
        t = V((0, b[0] - a[0], b[1] - a[1])).normalized()
        mane.append((y - t.z * (rn - 0.015), z + t.y * (rn - 0.015), 0.045, 0.05 if 0 < i < len(neck) - 1 else 0.025))
    front.add(limb(mane, 8, m))
    # Vorderbeine (y, z, rx, rn)
    fl_stand = [(0.56, 1.18, 0.11, 0.17), (0.56, 0.92, 0.08, 0.115), (0.58, 0.54, 0.06, 0.07), (0.58, 0.28, 0.042, 0.048),
                (0.58, 0.15, 0.055, 0.06), (0.62, 0.075, 0.05, 0.055), (0.65, 0.0, 0.068, 0.08)]
    fl_lift = [(0.56, 1.18, 0.11, 0.17), (0.63, 0.92, 0.08, 0.115), (0.90, 0.70, 0.06, 0.07), (0.86, 0.46, 0.042, 0.048),
               (0.83, 0.34, 0.055, 0.06), (0.80, 0.27, 0.05, 0.055), (0.77, 0.19, 0.068, 0.08)]
    fl_tuck = [(0.56, 1.18, 0.11, 0.17), (0.66, 0.92, 0.08, 0.115), (1.00, 0.80, 0.06, 0.07), (0.92, 0.56, 0.042, 0.048),
               (0.87, 0.45, 0.055, 0.06), (0.82, 0.40, 0.05, 0.055), (0.75, 0.36, 0.068, 0.08)]
    fl_tuck2 = [(0.56, 1.18, 0.11, 0.17), (0.70, 0.94, 0.08, 0.115), (1.08, 0.90, 0.06, 0.07), (1.04, 0.64, 0.042, 0.048),
                (1.00, 0.52, 0.055, 0.06), (0.96, 0.46, 0.05, 0.055), (0.90, 0.40, 0.068, 0.08)]
    if rearing:
        front.add(limb(fl_tuck, 10, m, x0=-0.17)).add(limb(fl_tuck2, 10, m, x0=0.17))
    else:
        front.add(limb(fl_stand, 10, m, x0=-0.17)).add(limb(fl_lift, 10, m, x0=0.17))
    s = Soup()
    M = Matrix.Identity(4)
    if rearing:
        piv = (0, -0.62, 1.12)
        M = M_T(0, 0, -0.12) @ M_T(*piv) @ M_R("X", 36) @ M_T(-piv[0], -piv[1], -piv[2])
        front.xf(M)
        hind_a = [(-0.60, 1.02, 0.15, 0.24), (-0.36, 0.80, 0.11, 0.16), (-0.80, 0.52, 0.06, 0.075),
                  (-0.72, 0.28, 0.045, 0.052), (-0.66, 0.15, 0.055, 0.06), (-0.60, 0.075, 0.05, 0.055),
                  (-0.56, 0.0, 0.068, 0.08)]
        hind_b = [(y + 0.12 if i > 1 else y, z, a, b) for i, (y, z, a, b) in enumerate(hind_a)]
        s.add(limb(hind_a, 10, m, x0=-0.19)).add(limb(hind_b, 10, m, x0=0.19))
        r0 = M @ V((0, -0.95, 1.40))
        tail = [(r0.y + 0.05, r0.z, 0.05, 0.05), (r0.y - 0.16, r0.z - 0.02, 0.075, 0.075),
                (r0.y - 0.36, r0.z - 0.30, 0.095, 0.11), (r0.y - 0.42, 0.45, 0.085, 0.11), (r0.y - 0.36, 0.06, 0.05, 0.07)]
        s.add(limb(tail, 10, m))
    else:
        hind_a = [(-0.64, 1.16, 0.15, 0.24), (-0.55, 0.86, 0.11, 0.16), (-0.78, 0.58, 0.06, 0.075),
                  (-0.74, 0.30, 0.045, 0.052), (-0.72, 0.15, 0.055, 0.06), (-0.68, 0.075, 0.05, 0.055),
                  (-0.65, 0.0, 0.068, 0.08)]
        hind_b = [(-0.64, 1.16, 0.15, 0.24), (-0.50, 0.86, 0.11, 0.16), (-0.60, 0.58, 0.06, 0.075),
                  (-0.50, 0.30, 0.045, 0.052), (-0.46, 0.15, 0.055, 0.06), (-0.42, 0.075, 0.05, 0.055),
                  (-0.39, 0.0, 0.068, 0.08)]
        s.add(limb(hind_a, 10, m, x0=0.19)).add(limb(hind_b, 10, m, x0=-0.19))
        tail = [(-0.93, 1.42, 0.05, 0.05), (-1.08, 1.40, 0.075, 0.075), (-1.22, 1.15, 0.095, 0.11),
                (-1.26, 0.80, 0.085, 0.11), (-1.22, 0.48, 0.04, 0.05)]
        s.add(limb(tail, 10, m))
    s.add(front)
    return s, M


def rider_group(pose, m, rearing):
    """Pferd mit Reiter in Lebensgröße, Hufe auf z = 0, Mitte etwa im Ursprung."""
    s, M = horse(m, rearing)
    f, j = fig(pose, m)
    f.add(cloak([(1.45, -0.02, 0.23, 0.15), (1.25, -0.08, 0.30, 0.22), (1.00, -0.20, 0.36, 0.30),
                 (0.84, -0.36, 0.40, 0.36), (0.80, -0.44, 0.38, 0.34)], m))
    hand, tip = j["Hand_R"]
    d = (tip - hand).normalized()
    if pose == "imperator":      # Feldherrnstab in Armrichtung
        f.add(tube([hand + d * 0.05, hand + d * 0.50], 0.025, 6, m))
    else:                        # Zepter, schräg nach oben
        u = (d + V((0.25, 0.0, 1.0))).normalized()
        f.add(tube([hand + d * 0.12 - u * 0.12, hand + d * 0.12 + u * 0.55], 0.02, 6, m))
        f.add(ico(0.045, m, 1).move(*(hand + d * 0.12 + u * 0.58)))
    seat = V((0, -0.06, 1.50))
    S = M_T(seat.x, seat.y, seat.z - 0.86)
    if rearing:                  # Reiter sitzt aufrechter, als das Pferd steigt
        S = M_T(*seat) @ M_R("X", -22) @ M_T(*(-seat)) @ S
    f.xf(M @ S)
    s.add(f)
    return s


# ====================================================================== Modelle
MODELS = {}


def model(fn):
    MODELS[fn.__name__] = fn
    return fn


@model
def mon_statue():
    s, zs, zc = pedestal(1.05, 1.05, 1.8)
    s.add(plaque(0.7, 0.55, (zs + zc) / 2, 0.525))
    k = 2.4 / 1.78
    f, j = fig("stand")
    f.add(cloak([(1.46, -0.01, 0.235, 0.155), (1.20, -0.04, 0.27, 0.20), (0.80, -0.07, 0.31, 0.25),
                 (0.38, -0.10, 0.36, 0.30), (0.30, -0.10, 0.355, 0.295)], BRONZE))
    hand, tip = j["Hand_R"]
    d = (tip - hand).normalized()
    c = hand + d * 0.13
    f.add(tube([c - V((0.16, 0, -0.03)), c + V((0.16, 0, -0.03))], 0.032, 6, BRONZE))   # Schriftrolle
    f.add(cbox(0, 0.03, -0.04, 0.62, 0.60, 0.04, BRONZE))                                # Plinthe der Figur
    f.scale(k, k, k).move(0, -0.02, 1.8 + 0.04 * k)
    s.add(f)
    return s, "Standbild: Bronzefigur mit Mantel auf profiliertem Sandsteinsockel, Tafel vorn (+Y)."


@model
def mon_bust():
    s = stack([(0.80, 0.70, 0), (0.80, 0.70, 0.12), (0.62, 0.54, 0.12), (0.62, 0.54, 0.26), (0.50, 0.42, 0.32),
               (0.44, 0.38, 1.26), (0.52, 0.44, 1.31), (0.58, 0.48, 1.36), (0.58, 0.48, 1.42), (0.50, 0.42, 1.44)], STONE)
    s.add(plaque(0.30, 0.42, 0.95, 0.205, t=0.02))
    k = 1.42
    b = bust_soup()
    b.move(0, 0, -1.24).scale(k, k, k).move(0, 0.0, 1.52)
    s.add(b)
    s.add(stack([(0.40, 0.30, 1.44), (0.34, 0.26, 1.48), (0.44, 0.34, 1.53)], BRONZE, r=0.05))   # Büstenfuß
    return s, "Büste (Kopf und Schultern in Bronze) auf schlanker Sandsteinstele, Tafel vorn (+Y)."


@model
def mon_obelisk():
    s = stack([(3.0, 3.0, 0), (3.0, 3.0, 0.2), (2.4, 2.4, 0.2), (2.4, 2.4, 0.4), (1.8, 1.8, 0.4), (1.8, 1.8, 0.6)], STONE)
    p, zs, zc = pedestal(1.0, 1.0, 1.25, step=0.0, z0=0.6)
    s.add(p)
    s.add(stack([(0.82, 0.82, 1.85), (0.82, 0.82, 1.95), (0.74, 0.74, 1.98), (0.46, 0.46, 5.55), (0.0, 0.0, 6.0)], STONE))
    s.add(plaque(0.62, 0.42, (zs + zc) / 2, 0.5, t=0.025))
    return s, "Sandstein-Obelisk auf dreistufigem Unterbau mit Postament, Tafel vorn (+Y)."


@model
def mon_stele():
    s = stack([(1.5, 0.75, 0), (1.5, 0.75, 0.16), (1.25, 0.55, 0.16), (1.25, 0.55, 0.30), (1.05, 0.38, 0.34),
               (0.98, 0.34, 1.95)], STONE)
    # Giebelabschluss
    s.add(prism_y([(-0.56, 1.95), (0.56, 1.95), (0.56, 2.04), (0.0, 2.2), (-0.56, 2.04)], -0.21, 0.21, STONE))
    s.add(plaque(0.72, 0.95, 1.25, 0.178, t=0.025))
    s.add(plaque(0.50, 0.30, 0.62, 0.188, t=0.02))
    return s, "Gedenkstele aus Sandstein mit Giebel, Bronzetafeln vorn (+Y)."


@model
def mon_stone():
    s = ico(1.0, GRANITE, 3)

    def w(co):
        n = noise.noise(co * 1.3 + Vector((3.1, 7.7, 1.3))) * 0.22 + noise.noise(co * 3.1) * 0.07
        p = co * (1.0 + n)
        return (p.x * 0.80, p.y * 0.50, max(p.z * 0.62 + 0.46, 0.0))
    s.warp(w)
    top = max(v.z for v in s.v)
    s.scale(1, 1, 1.1 / top)
    # Tafel vorn, leicht geneigt, ein Stück in den Stein eingelassen
    yf = max(v.y for v in s.v if abs(v.x) < 0.3 and 0.4 < v.z < 0.8)
    s.add(cbox(0, 0, 0, 0.48, 0.03, 0.30, BRONZE).rot((1, 0, 0), -10).move(0, yf - 0.02, 0.45))
    s.add(stack([(1.9, 1.3, 0), (1.8, 1.2, 0.06)], GRANITE, r=0.3))
    return s, "Gedenkstein: Granitfindling mit kleiner Bronzetafel vorn (+Y) auf flacher Platte."


@model
def mon_war():
    s = stack([(3.2, 2.8, 0), (3.2, 2.8, 0.2), (2.6, 2.2, 0.2), (2.6, 2.2, 0.4), (2.0, 1.6, 0.4), (2.0, 1.6, 0.6),
               (1.55, 1.15, 0.6), (1.55, 1.15, 0.95), (1.38, 0.98, 1.02), (1.25, 0.88, 2.55), (1.38, 0.98, 2.62),
               (1.50, 1.08, 2.70), (1.50, 1.08, 2.80), (1.0, 0.7, 2.92)], STONE)
    yf = 0.47
    # Kranz vorn
    ring = [V((math.cos(TAU * i / 16) * 0.33, yf + 0.03, 2.02 + math.sin(TAU * i / 16) * 0.33)) for i in range(16)]
    s.add(tube(ring, 0.06, 6, BRONZE, closed_path=True, up=(0, 1, 0)))
    s.add(cbox(0, yf + 0.035, 1.62, 0.14, 0.05, 0.14, BRONZE))                      # Schleife
    s.add(plaque(0.85, 0.42, 1.30, yf + 0.03, t=0.025))
    s.add(plaque(0.85, 1.0, 1.75, -yf - 0.02, t=0.025, back=True))
    # Eisernes Kreuz obenauf (Stein), Tatzenform aus vier Trapezen
    cz, a, b, r = 3.21, 0.07, 0.17, 0.29
    for k in range(4):
        ca, sa = math.cos(TAU * k / 4), math.sin(TAU * k / 4)
        pts = [(0.02, -a), (r, -b), (r, b), (0.02, a)]
        s.add(prism_y([(x * ca - z * sa, cz + x * sa + z * ca) for x, z in pts], -0.09, 0.09, STONE))
    s.add(cbox(0, 0, cz - 0.08, 0.16, 0.18, 0.16, STONE))
    return s, "Kriegerdenkmal: Stufenunterbau, Sandsteinpfeiler mit Bronzekranz und Tafeln, Kreuz obenauf."


@model
def mon_sculpture():
    s = stack([(1.9, 1.5, 0), (1.9, 1.5, 0.22), (1.8, 1.4, 0.25)], GRANITE)
    n, K = 12, 26
    for sgn, ph in ((1, 0.0), (-1, 2.2)):      # zwei gegenläufig verdrehte Flammenkörper
        rings = []
        for k in range(K + 1):
            t = k / K
            z = 0.25 + (2.15 if sgn > 0 else 1.55) * t
            rx = 0.42 * (1 - t) ** 0.7 * (0.55 + 0.45 * math.sin(math.pi * min(t * 1.6, 1.0))) + 0.012
            ry = 0.12 * (1 - 0.6 * t) + 0.01
            tw = ph + sgn * math.radians(230) * t
            cx = sgn * 0.26 * (1 - t) + 0.10 * math.sin(3.0 * t + ph)
            cy = 0.12 * math.sin(4.0 * t + ph) * sgn
            ring = []
            for i in range(n):
                a = TAU * i / n
                x, y = math.cos(a) * rx, math.sin(a) * ry
                ring.append(V((cx + x * math.cos(tw) - y * math.sin(tw), cy + x * math.sin(tw) + y * math.cos(tw), z)))
            rings.append(ring)
        s.add(loft(rings, BRONZE, orient=V((0, 0, 1))))
    # schräger Stahlring
    ring = [V((math.cos(TAU * i / 24) * 0.62, math.sin(TAU * i / 24) * 0.62, 0)) for i in range(24)]
    r = tube(ring, 0.045, 8, STEEL, closed_path=True, up=(0, 0, 1))
    r.rot((1, 0, 0), 62).rot((0, 0, 1), 25).move(0.02, 0.0, 1.05)
    s.add(r)
    return s, "Moderne Plastik: zwei verdrehte Bronzekörper mit Stahlring auf flachem Granitsockel."


@model
def mon_fountain():
    s = Soup()
    s.add(lathe([(3.12, 0), (3.12, 0.12), (3.02, 0.16), (3.0, 0.50), (3.08, 0.56), (3.08, 0.64), (2.74, 0.64),
                 (2.72, 0.40)], 32, STONE, cap0=False, cap1=False))
    s.poly(circle(2.73, 32, 0.50, a0=math.pi / 32), WATER)
    s.add(lathe([(0.75, 0.40), (0.75, 0.70), (0.62, 0.76), (0.40, 0.90), (0.30, 1.05), (0.27, 1.30), (0.36, 1.40),
                 (0.80, 1.50), (1.18, 1.60), (1.22, 1.68), (1.12, 1.68), (1.08, 1.58)], 24, STONE, cap0=False, cap1=False))
    s.poly(circle(1.10, 24, 1.63, a0=math.pi / 24), WATER)
    s.add(lathe([(0.24, 1.58), (0.18, 1.72), (0.15, 1.98), (0.22, 2.05), (0.50, 2.12), (0.62, 2.17), (0.64, 2.22),
                 (0.57, 2.22), (0.55, 2.16)], 16, STONE, cap0=False, cap1=False))
    s.poly(circle(0.56, 16, 2.19, a0=math.pi / 16), WATER)
    s.add(lathe([(0.12, 2.16), (0.09, 2.28), (0.15, 2.34), (0.15, 2.38), (0.08, 2.43), (0.0, 2.52)], 10, STONE,
                cap0=False))
    # vier Wasserstrahlen von der oberen in die mittlere Schale
    for k in range(4):
        a = TAU * k / 4 + TAU / 8
        path = [V((math.cos(a) * r, math.sin(a) * r, z)) for r, z in ((0.60, 2.20), (0.74, 2.16), (0.84, 1.98), (0.90, 1.64))]
        s.add(tube(path, 0.03, 5, WATER, rs=[0.035, 0.03, 0.028, 0.04]))
    return s, "Zierbrunnen: rundes Sandsteinbecken Ø 6,2 m mit Wasserfläche, zwei Schalen, Bekrönung."


@model
def mon_fountain_small():
    a0 = math.pi / 8
    s = lathe([(0.40, 0), (0.40, 0.08), (0.28, 0.12), (0.26, 0.20), (0.21, 0.24), (0.20, 0.78), (0.25, 0.84),
               (0.40, 0.95), (0.44, 1.0), (0.44, 1.06), (0.37, 1.06), (0.35, 0.99)], 8, STONE, a0=a0, cap1=False)
    s.poly(circle(0.36, 8, 1.03, a0=a0), WATER)
    s.add(tube([V((0, -0.10, 1.0)), V((0, -0.10, 1.15)), V((0, -0.07, 1.195)), V((0, 0.0, 1.20)), V((0, 0.05, 1.17))],
               0.02, 6, BRONZE))
    s.add(cyl(0.035, 0.03, 8, BRONZE, z0=0.55, a0=0).rot((1, 0, 0), -90, (0, 0, 0.565)).move(0, 0.20, 0))  # Druckknopf
    return s, "Trinkbrunnen: achteckiger Sandsteinpfeiler mit Schale und Bronzeauslauf, Knopf vorn (+Y)."


def _reiter(m, pose, rearing, ped_h, total_h, pw, pd):
    s, zs, zc = pedestal(pw, pd, ped_h, r=0.12)
    g = rider_group(pose, m, rearing)
    lo = min(v.z for v in g.v)
    hi = max(v.z for v in g.v)
    k = (total_h - ped_h - 0.12) / (hi - lo)
    ys = [v.y for v in g.v]
    g.move(0, -(min(ys) + max(ys)) / 2, -lo).scale(k, k, k)
    ly = (max(ys) - min(ys)) * k
    # Plinthe unter den Hufen
    s.add(stack([(pw + 0.1, min(ly + 0.2, pd + 0.3), ped_h), (pw + 0.05, min(ly + 0.15, pd + 0.25), ped_h + 0.12)], m, r=0.1))
    g.move(0, 0, ped_h + 0.12)
    s.add(g)
    return s, zs, zc, pw, pd


@model
def mon_reiter():
    s, zs, zc, pw, pd = _reiter(BRONZE, "king", False, 5.2, 9.0, 1.9, 3.7)
    # umlaufender Bronzefries am Sockel und Inschrifttafel vorn
    h = (zc - zs) * 0.34
    z0 = zs + (zc - zs) * 0.50
    s.add(stack([(pw + 0.05, pd + 0.05, z0), (pw + 0.05, pd + 0.05, z0 + h)], BRONZE, r=0.13))
    s.add(plaque(1.3, 0.7, zs + (zc - zs) * 0.25, pd / 2, t=0.04))
    return s, ("Reiterstandbild (Vorbild König Johann): schreitendes Pferd mit Reiter in Bronze, Mantel und Zepter, "
               "hoher Sandsteinsockel mit Bronzefries. Pferdekopf zeigt nach +Y.")


@model
def mon_reiter_gold():
    s, zs, zc, pw, pd = _reiter(GOLD, "imperator", True, 5.0, 8.5, 1.8, 3.2)
    s.add(plaque(1.2, 1.5, (zs + zc) / 2, pd / 2, m=GOLD, t=0.04))
    s.add(plaque(1.2, 1.5, (zs + zc) / 2, -pd / 2, m=GOLD, t=0.04, back=True))
    return s, ("Goldener Reiter (Vorbild August der Starke): steigendes Pferd, Reiter mit Umhang und ausgestrecktem "
               "Feldherrnstab, vergoldet, Sandsteinsockel 5 m mit goldenen Inschrifttafeln. Pferdekopf zeigt nach +Y.")


VIEWS = {"mon_reiter": ((35, 12), (270, 8)), "mon_reiter_gold": ((35, 12), (270, 8)),
         "mon_fountain": ((35, 28), (0, 8)), "mon_statue": ((25, 12), (215, 12)), "mon_bust": ((25, 10), (215, 10))}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    L.NOPREVIEW = "--nopreview" in argv
    names = [a for a in argv if not a.startswith("--")] or list(MODELS)
    FIG.update(_figures(POSES))
    for name in names:
        L.reset()
        mats()
        soup, notes = MODELS[name]()
        ob = build(soup, name, smooth_angle=24 if name == "mon_stone" else 42, merge=True)
        finish(name, [ob], notes, views=VIEWS.get(name))
    try:
        os.rmdir(L.TMP)
    except OSError:
        pass


if __name__ == "__main__":
    main()
