"""Baut benannte Dresdner Standbilder nach Fotovorlagen: godot/assets/models/monuments/mon_<name>.glb.

Aufruf (Projektordner, immer nur ein Blender gleichzeitig):
  flatpak run --filesystem=host org.blender.Blender -b --python "$PWD/tools/blender/monuments_named_a.py" [-- name ...] [--nopreview]

Bausteine und Konventionen stammen aus monuments_build.py / furniture_lib.py (Blender Z-up, Meter, Ursprung =
Bodenmitte, Vorderseite +Y). Die Figuren sind gepostete, eingebackene Fußgänger (ped_m / ped_f) mit gelofteten
Gewändern; rechts der Figur = +X. Die echte Gesamthöhe ist direkt eingebaut (Maßstab im Spiel 1,0).
Vorlagen: Wikimedia-Commons-Fotos in data/research/denkmal_fotos/ (nur Vorlage, siehe QUELLEN.txt).
Zusätzliche reine Farbmaterialien neben Sandstein/Bronze/Gold/Granit: GranitRot, GranitDunkel, Ziegel.
"""
import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import monuments_build as B  # noqa: E402
from monuments_build import (L, V, Soup, mat, loft, lathe, cbox, tube, rrect, build, finish, ico,  # noqa: E402
                             M_T, M_R, TAU, stack, plaque, cloak, STONE, BRONZE, GOLD, GRANITE)
from furniture_lib import box  # noqa: E402

RED, DARK, BRICK = "GranitRot", "GranitDunkel", "Ziegel"
PED_M = B.PED
PED_F = os.path.join(os.path.dirname(B.PED), "ped_f.glb")


def mats():
    B.mats()
    mat(RED, "#8C574B", 0.55)       # roter Meißner/Lausitzer Granit, poliert
    mat(DARK, "#3A3F3E", 0.45)      # dunkler polierter Syenit
    mat(BRICK, "#8A4B37", 0.9)      # Trümmerziegel


# ====================================================================== Figuren
def figures(poses):
    """poses = {Name: (Fußgängerdatei, [(Knochen, Richtung[, Drehung um die Knochenachse in Grad]), ...])}.
    Liefert {Name: (Soup, Gelenke {Knochen: (Kopf, Ende)})} – wie monuments_build._figures, zusätzlich mit Drehung
    um die Knochenachse (Kopf wenden) und wählbarem Fußgänger."""
    out = {}
    by = {}
    for name, (ped, pose) in poses.items():
        by.setdefault(ped, []).append((name, pose))
    for ped, lst in by.items():
        L.reset()
        bpy.ops.import_scene.gltf(filepath=ped)
        arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
        bodies = [o for o in bpy.data.objects if o.type == "MESH" and o.parent == arm]
        arm.animation_data_clear()
        for name, pose in lst:
            for pb in arm.pose.bones:
                pb.matrix_basis = Matrix.Identity(4)
            bpy.context.view_layer.update()
            for item in pose:
                pb = arm.pose.bones[item[0]]
                h = pb.head.copy()
                q = (pb.tail - pb.head).normalized().rotation_difference(Vector(item[1]).normalized())
                pb.matrix = Matrix.Translation(h) @ q.to_matrix().to_4x4() @ Matrix.Translation(-h) @ pb.matrix
                bpy.context.view_layer.update()
                if len(item) > 2 and item[2]:
                    ax = (pb.tail - pb.head).normalized()
                    pb.matrix = (Matrix.Translation(h) @ Matrix.Rotation(math.radians(item[2]), 4, ax)
                                 @ Matrix.Translation(-h) @ pb.matrix)
                    bpy.context.view_layer.update()
            dg = bpy.context.evaluated_depsgraph_get()
            s = Soup()
            for body in bodies:
                eo = body.evaluated_get(dg)
                me = eo.to_mesh()
                off = len(s.v)
                for v in me.vertices:
                    s.vert(eo.matrix_world @ v.co)
                skip = {i for i, ms in enumerate(me.materials) if ms and ms.name.startswith("Accessory")}
                hair = {i for i, ms in enumerate(me.materials) if ms and ms.name.startswith("Hair")}
                rest = [body.matrix_world @ v.co for v in body.data.vertices]
                for p in me.polygons:
                    if p.material_index in skip:
                        continue
                    if p.material_index in hair and len(rest) == len(me.vertices):
                        zs = [rest[i].z for i in p.vertices]      # Augenbrauen (dünne Balken) wirken in Bronze wie eine Brille
                        if min(rest[i].y for i in p.vertices) > 0.08 and 1.6 < min(zs) and max(zs) < 1.72:
                            continue
                    s.face([i + off for i in p.vertices], BRONZE)
                eo.to_mesh_clear()
            joints = {pb.name: (arm.matrix_world @ pb.head, arm.matrix_world @ pb.tail) for pb in arm.pose.bones}
            out[name] = (s, joints)
    return out


FIG = {}


def fig(name, m=BRONZE):
    s, j = FIG[name]
    return s.copy().setmat(m), j


def _bm(s):
    bm = bmesh.new()
    vs = [bm.verts.new(co) for co in s.v]
    for idx, _, _ in s.f:
        try:
            bm.faces.new([vs[i] for i in idx])
        except ValueError:
            pass
    return bm


def _soup(bm, m):
    out = Soup()
    bm.verts.index_update()
    for v in bm.verts:
        out.vert(v.co)
    for f in bm.faces:
        out.face([v.index for v in f.verts], m)
    bm.free()
    return out


def clip(s, cuts, m=BRONZE):
    """Schneidet je (Punkt, Normale) die Seite weg, in die die Normale zeigt; Schnittflächen werden geschlossen."""
    bm = _bm(s)
    for co, no in cuts:
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no, clear_outer=True)
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return _soup(bm, m)


def decimate(s, ratio, m=BRONZE):
    """Vereinfacht eine Figur (Nebenfiguren) auf den Anteil ratio der Dreiecke."""
    bm = _bm(s)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    me = bpy.data.meshes.new("_dec")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("_dec", me)
    bpy.context.scene.collection.objects.link(ob)
    mod = ob.modifiers.new("d", "DECIMATE")
    mod.ratio = ratio
    dg = bpy.context.evaluated_depsgraph_get()
    eo = ob.evaluated_get(dg)
    m2 = eo.to_mesh()
    out = Soup()
    for v in m2.vertices:
        out.vert(v.co)
    for p in m2.polygons:
        out.face(list(p.vertices), m)
    eo.to_mesh_clear()
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    return out


def ring(z, cx, cy, rx, ry, fold=0.0, n=14, nf=4, ph=0.0):
    pts = []
    for i in range(n):
        a = TAU * i / n
        f = 1.0 + fold * math.cos(nf * a + ph)
        pts.append(V((cx + math.cos(a) * rx * f, cy + math.sin(a) * ry * f, z)))
    return pts


def robe(levels, m=BRONZE, n=14, nf=4, ph=0.0, cap0=True, cap1=True):
    """Gewand als Schlauch aus Ellipsenringen: levels = [(z, cx, cy, rx, ry[, Faltentiefe]), ...] von unten nach oben."""
    levels = sorted(levels, key=lambda lv: lv[0])
    return loft([ring(*lv, n=n, nf=nf, ph=ph) for lv in levels], m, orient=V((0, 0, 1)), cap0=cap0, cap1=cap1)


def sleeve(j, side, rs, m=BRONZE, n=8):
    a, b, c = j["UpperArm_" + side][0], j["LowerArm_" + side][0], j["Hand_" + side][0]
    return tube([a, a.lerp(b, 0.8), b.lerp(c, 0.22), c + (c - b).normalized() * 0.02], rs[0], n, m,
                rs=[rs[0], rs[1], rs[1], rs[2]])


def hand(j, side):
    """Handmitte (etwas hinter dem Handgelenk) und Richtung des Unterarms."""
    b, c = j["LowerArm_" + side][0], j["Hand_" + side][0]
    d = (c - b).normalized()
    return c + d * 0.07, d


def cb(cx, cy, cz, w, d, h, m):
    """Quader, um (cx, cy, cz) zentriert."""
    return box(cx - w / 2, cy - d / 2, cz - h / 2, cx + w / 2, cy + d / 2, cz + h / 2, m)


def rod(p, q, r, m=BRONZE, n=6, r1=None):
    return tube([V(p), V(q)], r, n, m, rs=[r, r if r1 is None else r1])


def wreath(r, t, m=BRONZE, n=14):
    """Kranz in der XZ-Ebene (Blick von +Y), Mitte im Ursprung."""
    pts = [V((math.cos(TAU * i / n) * r, 0, math.sin(TAU * i / n) * r)) for i in range(n)]
    return tube(pts, t, 6, m, closed_path=True, up=(0, 1, 0))


def cstack(levels, m, c=0.0, cx=0.0, cy=0.0):
    """Wie stack, aber mit gefasten (abgeschrägten) Ecken der Breite c."""
    return loft([rrect(w, d, c, 1, z, cx, cy) for w, d, z in levels], m, orient=V((0, 0, 1)))


def place(f, z0, height, x=0.0, y=0.0, rz=0.0):
    """Skaliert eine Figur (Füße bei z = 0) auf die Höhe height und stellt sie auf z0."""
    lo = min(v.z for v in f.v)
    hi = max(v.z for v in f.v)
    k = height / (hi - lo)
    f.move(0, 0, -lo).scale(k, k, k)
    if rz:
        f.rot((0, 0, 1), rz)
    return f.move(x, y, z0)


def _legs_sit(dy=(0.0, 0.0), spread=0.12):
    p = []
    for side, sg, d in (("L", -1, dy[0]), ("R", 1, dy[1])):
        p += [("UpperLeg_" + side, (sg * spread, 1.0, -0.03)), ("LowerLeg_" + side, (sg * 0.02, d, -1.0)),
              ("Foot_" + side, (sg * 0.12, 1.0, -0.2))]
    return p


POSES = {
    # Luther: Bibel links vor der Brust, rechte Hand darauf, Kopf erhoben, rechter Fuß vor
    "rest": (PED_M, []),
    "luther": (PED_M, [
        ("UpperLeg_R", (0.04, 0.13, -1.0)), ("LowerLeg_R", (0.02, -0.03, -1.0)), ("Foot_R", (0.3, 1.0, -0.2)),
        ("Neck", (0.02, -0.04, 1.0)), ("Head", (0.05, -0.22, 1.0), -12),
        ("UpperArm_L", (-0.14, -0.05, -1.0)), ("LowerArm_L", (0.38, 0.90, 0.02)), ("Hand_L", (0.6, 0.5, 0.6)),
        ("UpperArm_R", (0.14, 0.10, -0.95)), ("LowerArm_R", (-0.80, 0.52, 0.28)), ("Hand_R", (-0.9, 0.3, 0.2))]),
    # König, thronend: Zepter rechts auf dem Schenkel, Gesetzbuch links
    "throne": (PED_M, _legs_sit((0.02, 0.14)) + [
        ("Head", (0.0, 0.10, 1.0), -8),
        ("UpperArm_R", (0.22, 0.12, -1.0)), ("LowerArm_R", (-0.10, 1.0, -0.12)),
        ("UpperArm_L", (-0.26, 0.08, -1.0)), ("LowerArm_L", (-0.05, 1.0, 0.12))]),
    # Allegorie stehend (Frau im Gewand): rechter Arm angewinkelt mit Attribut, linker Arm gesenkt
    "alleg": (PED_F, [
        ("Head", (0.0, 0.08, 1.0)),
        ("UpperArm_R", (0.18, 0.12, -1.0)), ("LowerArm_R", (-0.25, 0.75, 0.55)),
        ("UpperArm_L", (-0.20, 0.05, -1.0)), ("LowerArm_L", (-0.05, 0.45, -0.85))]),
    # Allegorie sitzend: Hände im Schoß bzw. Attribut haltend
    "alleg_sit": (PED_F, _legs_sit((0.05, 0.10), 0.10) + [
        ("Head", (0.0, 0.06, 1.0)),
        ("UpperArm_R", (0.20, 0.15, -1.0)), ("LowerArm_R", (-0.20, 1.0, 0.05)),
        ("UpperArm_L", (-0.22, 0.10, -1.0)), ("LowerArm_L", (0.10, 1.0, 0.25))]),
    # Friedrich August II.: rechtes Bein vor, Urkunde in der gesenkten Rechten, Linke am Säbelgriff
    "fa2": (PED_M, [
        ("UpperLeg_R", (0.07, 0.18, -1.0)), ("LowerLeg_R", (0.0, -0.03, -1.0)), ("Foot_R", (0.3, 1.0, -0.2)),
        ("Head", (0.0, -0.04, 1.0), -10),
        ("UpperArm_R", (0.24, 0.02, -1.0)), ("LowerArm_R", (0.10, 0.42, -0.9)),
        ("UpperArm_L", (-0.30, -0.04, -1.0)), ("LowerArm_L", (0.22, 0.62, -0.62))]),
    # Weber: linker Ellbogen auf dem Notenpult, Hand erhoben; Rechte mit Kranz vor dem Leib
    "weber": (PED_M, [
        ("UpperLeg_L", (-0.05, 0.16, -1.0)), ("LowerLeg_L", (0.0, -0.03, -1.0)), ("Foot_L", (-0.3, 1.0, -0.2)),
        ("Neck", (-0.03, -0.02, 1.0)), ("Head", (-0.05, -0.16, 1.0), 22),
        ("UpperArm_R", (0.22, 0.06, -1.0)), ("LowerArm_R", (-0.78, 0.62, -0.02)),
        ("UpperArm_L", (-0.42, 0.14, -0.9)), ("LowerArm_L", (-0.04, 0.62, 0.78)), ("Hand_L", (0.05, 0.3, 1.0))]),
    # Semper: linker Fuß auf einem Kapitellblock, Bauplan in beiden Händen vor der Hüfte
    "semper": (PED_M, [
        ("UpperLeg_L", (-0.06, 0.90, -0.40)), ("LowerLeg_L", (0.0, 0.08, -1.0)), ("Foot_L", (-0.12, 1.0, -0.2)),
        ("Head", (0.06, 0.12, 1.0), -14),
        ("UpperArm_R", (0.20, 0.08, -1.0)), ("LowerArm_R", (0.12, 0.75, -0.62)),
        ("UpperArm_L", (-0.14, 0.24, -0.95)), ("LowerArm_L", (0.40, 0.72, -0.55))]),
    # Jüngling am Rietschel-Denkmal: hockend sitzend, Hände vor der Brust arbeitend
    "youth": (PED_M, [
        ("UpperLeg_L", (-0.22, 0.90, 0.30)), ("LowerLeg_L", (-0.02, 0.30, -1.0)), ("Foot_L", (-0.12, 1.0, -0.2)),
        ("UpperLeg_R", (0.20, 1.0, 0.02)), ("LowerLeg_R", (0.05, 0.55, -0.85)), ("Foot_R", (0.12, 1.0, -0.1)),
        ("Spine2", (0.0, 0.16, 1.0)), ("Head", (0.0, 0.25, 1.0)),
        ("UpperArm_R", (0.15, 0.45, -0.9)), ("LowerArm_R", (-0.30, 0.80, 0.35)),
        ("UpperArm_L", (-0.15, 0.40, -0.9)), ("LowerArm_L", (0.28, 0.85, 0.15))]),
    # Körner: rechtes Bein vor, Schriftrolle in der gesenkten Rechten, Linke drückt das Schwert an die Brust
    "koerner": (PED_M, [
        ("UpperLeg_R", (0.06, 0.20, -1.0)), ("LowerLeg_R", (0.0, -0.04, -1.0)), ("Foot_R", (0.3, 1.0, -0.2)),
        ("Neck", (-0.02, -0.03, 1.0)), ("Head", (-0.04, -0.12, 1.0), 24),
        ("UpperArm_R", (0.30, 0.0, -1.0)), ("LowerArm_R", (0.16, 0.40, -0.9)),
        ("UpperArm_L", (-0.22, 0.10, -1.0)), ("LowerArm_L", (0.55, 0.62, 0.55)), ("Hand_L", (0.5, 0.4, 0.75))]),
    # Trümmerfrau: aufrecht, Beine leicht gespreizt, Arme gestreckt abgespreizt, Kopf nach rechts
    "truemmerfrau": (PED_F, [
        ("UpperLeg_L", (-0.10, 0.06, -1.0)), ("LowerLeg_L", (-0.02, -0.02, -1.0)), ("Foot_L", (-0.15, 1.0, -0.2)),
        ("UpperLeg_R", (0.10, -0.02, -1.0)), ("LowerLeg_R", (0.02, -0.02, -1.0)), ("Foot_R", (0.2, 1.0, -0.2)),
        ("Head", (0.0, -0.05, 1.0), -28),
        ("UpperArm_R", (0.40, 0.02, -0.9)), ("LowerArm_R", (0.42, 0.14, -0.9)),
        ("UpperArm_L", (-0.40, -0.02, -0.9)), ("LowerArm_L", (-0.44, 0.08, -0.9))]),
}

SIT_DZ = 0.40      # Sitzende: Fußsohle liegt 0,40 über dem Ursprung des Fußgängers


def seated_draped(pose, mantle=True, ratio=None):
    """Sitzende Gewandfigur in Fußgängermaßen, Sohlen auf z = 0, Blick +Y; Sitzfläche bei z ≈ 0,42."""
    f, j = fig(pose)
    if ratio:
        f = decimate(f, ratio)
    f.move(0, 0, -SIT_DZ)
    j = {k: (a - V((0, 0, SIT_DZ)), b - V((0, 0, SIT_DZ))) for k, (a, b) in j.items()}
    # Schoßgewand: fällt von den Knien bis auf die Füße
    f.add(robe([(0.0, 0, 0.40, 0.25, 0.14, 0.09), (0.34, 0, 0.36, 0.255, 0.17, 0.07), (0.50, 0, 0.22, 0.25, 0.30, 0.02),
                (0.58, 0, 0.13, 0.21, 0.31, 0.0)], n=14, nf=5))
    if mantle:      # Mantel über Schultern und Rücken
        f.add(robe([(0.40, 0, -0.04, 0.29, 0.21, 0.06), (0.74, 0, -0.03, 0.26, 0.18, 0.04), (1.0, 0, -0.01, 0.215, 0.145, 0.0),
                    (1.07, 0, 0.0, 0.10, 0.09, 0.0)], n=12, nf=4))
    return f, j


# ====================================================================== Modelle
MODELS = {}
HEIGHT = {}     # Sollhöhe je Modell (zur Kontrolle in der Ausgabe)


def model(fn):
    MODELS[fn.__name__] = fn
    return fn


@model
def mon_luther():
    """Lutherdenkmal Neumarkt (Donndorf/Rietschel 1885). Gesamthöhe geschätzt 6,85 m."""
    s = stack([(3.25, 3.25, 0), (3.25, 3.25, 0.40), (2.95, 2.95, 0.56), (2.80, 2.80, 0.56), (2.80, 2.80, 0.80)], GRANITE)
    s.add(stack([(2.50, 2.50, 0.80), (2.50, 2.50, 1.12), (2.36, 2.36, 1.12), (2.36, 2.36, 1.32), (2.06, 2.06, 1.50),
                 (2.06, 2.06, 1.62), (1.80, 1.80, 1.74), (1.76, 1.76, 1.74), (1.56, 1.56, 2.95), (1.60, 1.60, 3.00),
                 (1.86, 1.86, 3.12), (1.86, 1.86, 3.30), (1.74, 1.74, 3.34), (1.74, 1.74, 3.40)], DARK))
    s.add(cbox(0, 0.83 + 0.006, 2.44, 1.00, 0.012, 0.11, GOLD))                      # MARTIN LUTHER
    s.add(stack([(1.52, 1.52, 3.40), (1.52, 1.52, 3.52)], BRONZE))                    # Plinthe
    # Rosenkranz mit Schleife am Sockelfuß
    w = wreath(0.30, 0.075).rot((1, 0, 0), -12).move(0, 1.27, 1.06)
    s.add(w).add(cb(0, 1.33, 1.36, 0.36, 0.08, 0.13, BRONZE))
    for sx in (-1, 1):
        s.add(tube([V((sx * 0.25, 1.36, 0.86)), V((sx * 0.55, 1.42, 0.82)), V((sx * 0.72, 1.40, 0.84))], 0.035, 5, BRONZE))
    # Figur im Talar
    f, j = fig("luther")
    f.add(robe([(0.02, 0, 0.02, 0.38, 0.32, 0.11), (0.22, 0, 0.02, 0.33, 0.28, 0.10), (0.55, 0, 0.01, 0.29, 0.245, 0.08),
                (0.90, 0, 0.0, 0.27, 0.22, 0.05), (1.18, 0, 0.0, 0.26, 0.195, 0.02), (1.36, 0, -0.01, 0.235, 0.16, 0.0),
                (1.455, 0, -0.01, 0.12, 0.105, 0.0)], n=16, nf=4))
    for side in "LR":
        f.add(sleeve(j, side, (0.10, 0.125, 0.115)))
        b, c = j["LowerArm_" + side][0], j["Hand_" + side][0]
        p = b.lerp(c, 0.45)
        f.add(tube([p, p + V((0, -0.02, -0.20)), p + V((0, -0.03, -0.36))], 0.1, 6, BRONZE, rs=[0.10, 0.085, 0.03]))
    hl, _ = hand(j, "L")
    bible = cb(0, 0, 0, 0.17, 0.065, 0.25, BRONZE).rot((0, 1, 0), -32).rot((1, 0, 0), -12)
    f.add(bible.move(hl.x + 0.02, hl.y + 0.01, hl.z + 0.07))
    place(f, 3.52, HEIGHT["mon_luther"] - 3.52, y=-0.03)
    s.add(f)
    return s, ("Martin-Luther-Denkmal Neumarkt: Bronzefigur im Talar mit Bibel vor der Brust (Blick +Y), dunkler "
               "Syenitsockel mit Goldinschrift und Kranz auf grauem Granitstufenbau. Gesamthöhe 6,85 m (geschätzt).")


def _alleg(attr):
    """Stehende Gewandfigur (Tugend) mit Attribut, Fußgängermaße, Sohlen z = 0."""
    f, j = fig("alleg")
    f = clip(f, [((0, 0, 1.0), (0, 0, -1))])
    f.add(robe([(0.0, 0, 0.0, 0.27, 0.23, 0.10), (0.5, 0, 0.0, 0.235, 0.195, 0.08), (0.95, 0, 0.0, 0.20, 0.16, 0.03),
                (1.12, 0, 0.0, 0.185, 0.145, 0.0)], n=12, nf=4))
    f.add(cloak([(1.50, -0.01, 0.17, 0.13), (1.25, -0.03, 0.26, 0.18), (0.7, -0.05, 0.29, 0.23), (0.12, -0.06, 0.31, 0.25)],
                BRONZE, k=6))
    h, d = hand(j, "R")
    if attr == "sword":
        f.add(rod(h + V((0, 0, -0.75)), h + V((0, 0, 0.22)), 0.022)).add(cb(h.x, h.y, h.z + 0.10, 0.20, 0.03, 0.03, BRONZE))
    elif attr == "cross":
        f.add(rod(h + V((0, 0, -0.30)), h + V((0, 0, 0.42)), 0.022)).add(cb(h.x, h.y, h.z + 0.26, 0.26, 0.035, 0.04, BRONZE))
    elif attr == "book":
        f.add(cb(h.x, h.y + 0.02, h.z + 0.02, 0.20, 0.06, 0.27, BRONZE))
    else:           # Zweig / Palme
        f.add(tube([h + V((0, 0, -0.1)), h + V((0.04, 0.0, 0.25)), h + V((0.12, 0.0, 0.45))], 0.03, 5, BRONZE,
                   rs=[0.015, 0.035, 0.01]))
    return f


@model
def mon_friedrich_august_gerechte():
    """König Friedrich August I. „der Gerechte“ (Rietschel 1843), Schloßplatz. Gesamthöhe geschätzt 8,5 m."""
    s = stack([(5.7, 6.1, 0), (5.7, 6.1, 0.25), (5.1, 5.5, 0.25), (5.1, 5.5, 0.50), (4.5, 4.9, 0.50), (4.5, 4.9, 0.75)], RED)
    s.add(stack([(3.95, 4.35, 0.75), (3.95, 4.35, 0.92), (3.75, 4.15, 0.96), (3.75, 4.15, 1.55), (3.90, 4.30, 1.60),
                 (3.90, 4.30, 1.68)], RED))
    # Bronzepostament: Ornamentfries, Schaft mit Feldern, Gesims, Attika mit Inschrift
    w, d = 2.5, 2.9
    s.add(stack([(3.62, 4.02, 1.68), (3.62, 4.02, 1.78), (3.50, 3.90, 1.82), (3.50, 3.90, 2.12), (3.62, 4.02, 2.16),
                 (3.62, 4.02, 2.26), (w + 0.25, d + 0.25, 2.26), (w + 0.25, d + 0.25, 2.40), (w, d, 2.46), (w, d, 4.20),
                 (w + 0.12, d + 0.12, 4.26), (w + 0.12, d + 0.12, 4.34), (w + 0.95, d + 0.95, 4.52),
                 (w + 0.95, d + 0.95, 4.62), (w + 0.80, d + 0.80, 4.70), (w + 0.35, d + 0.35, 4.74),
                 (w + 0.35, d + 0.35, 4.84), (w + 0.18, d + 0.18, 4.88), (w + 0.18, d + 0.18, 5.42),
                 (w + 0.34, d + 0.34, 5.48), (w + 0.34, d + 0.34, 5.58), (w + 0.10, d + 0.10, 5.62)], BRONZE))
    # Zahnschnitt unter dem Gesims (ein Band) und Felder am Schaft
    s.add(stack([(w + 0.40, d + 0.40, 4.36), (w + 0.40, d + 0.40, 4.44)], BRONZE))
    for sy in (-1, 1):
        for i in (-1, 0, 1):
            s.add(cb(i * 0.62, sy * (d / 2 + 0.015), 3.30, 0.54, 0.03, 1.50, BRONZE))
            s.add(cb(sy * (w / 2 + 0.015), i * 0.74, 3.30, 0.03, 0.64, 1.50, BRONZE))
    for sy in (-1, 1):       # goldene Inschriftzeilen
        for z in (5.26, 5.06):
            s.add(cb(0, sy * (d / 2 + 0.09 + 0.006), z, 2.0 if z > 5.1 else 1.7, 0.012, 0.11, GOLD))
            s.add(cb(sy * (w / 2 + 0.09 + 0.006), 0, z, 0.012, 2.3 if z > 5.1 else 2.0, 0.11, GOLD))
    # vier Tugenden vor den Ecken, diagonal nach außen blickend
    for (sx, sy), attr in zip(((1, 1), (-1, 1), (-1, -1), (1, -1)), ("sword", "branch", "cross", "book")):
        a = _alleg(attr)
        x, y = sx * (w / 2 + 0.33), sy * (d / 2 + 0.33)
        s.add(cstack([(0.62, 0.62, 2.26), (0.62, 0.62, 2.36)], BRONZE, 0.15, x, y))
        place(a, 2.36, 1.95, x, y, rz=-math.degrees(math.atan2(sx, sy)))
        s.add(a)
    # Thron und König im Krönungsmantel
    f, j = fig("throne")
    f.move(0, 0, -SIT_DZ)
    j = {k: (a - V((0, 0, SIT_DZ)), b - V((0, 0, SIT_DZ))) for k, (a, b) in j.items()}
    f.add(box(-0.36, -0.34, 0.0, 0.36, 0.20, 0.42, BRONZE))                               # Sitz
    f.add(box(-0.40, -0.40, 0.0, 0.40, -0.28, 1.02, BRONZE))                              # Lehne
    for sx in (-1, 1):
        f.add(box(sx * 0.31 - 0.07, -0.34, 0.42, sx * 0.31 + 0.07, 0.22, 0.60, BRONZE))  # Armlehnen
    f.add(robe([(0.0, 0, 0.40, 0.31, 0.18, 0.09), (0.34, 0, 0.36, 0.30, 0.20, 0.07), (0.50, 0, 0.22, 0.29, 0.33, 0.02),
                (0.60, 0, 0.13, 0.24, 0.33, 0.0)], n=14, nf=5))
    f.add(robe([(0.02, 0, -0.10, 0.46, 0.36, 0.07), (0.45, 0, -0.06, 0.42, 0.31, 0.06), (0.78, 0, -0.03, 0.34, 0.24, 0.04),
                (1.0, 0, -0.01, 0.26, 0.17, 0.0), (1.07, 0, 0.0, 0.11, 0.10, 0.0)], n=14, nf=5))
    hr, dr = hand(j, "R")
    f.add(rod(hr + V((0.03, -0.06, 0.0)), hr + V((-0.10, 0.22, 0.07)), 0.016))            # Zepter
    f.add(ico(0.03, BRONZE, 1).move(hr.x - 0.105, hr.y + 0.235, hr.z + 0.075))
    hl, _ = hand(j, "L")
    f.add(cb(hl.x - 0.02, hl.y + 0.02, hl.z + 0.10, 0.07, 0.20, 0.27, BRONZE))            # Gesetzbuch, hochkant
    s.add(stack([(2.3, 2.7, 5.62), (2.3, 2.7, 5.72)], BRONZE))
    place(f, 5.72, HEIGHT["mon_friedrich_august_gerechte"] - 5.72, y=-0.25)
    s.add(f)
    return s, ("Friedrich August I. der Gerechte (Schloßplatz): thronender König im Krönungsmantel mit Zepter (Blick +Y) "
               "auf Bronzepostament mit vier Tugenden an den Ecken, Goldinschrift, roter Granitunterbau mit drei "
               "Stufen. Gesamthöhe 8,5 m (geschätzt).")


def _alleg_sit(attr):
    f, j = seated_draped("alleg_sit", ratio=0.55)
    f.add(cloak([(1.50 - SIT_DZ, -0.01, 0.17, 0.14), (1.38 - SIT_DZ, -0.02, 0.21, 0.17), (1.10 - SIT_DZ, -0.04, 0.24, 0.20)],
                BRONZE, k=6))                                                              # Schleier
    h, d = hand(j, "R")
    hl, _ = hand(j, "L")
    if attr == "cross":
        f.add(rod(h + V((0.10, 0.0, -0.30)), h + V((-0.10, 0.0, 0.45)), 0.022))
        c = h + V((-0.055, 0.0, 0.26))
        f.add(rod(c + V((-0.13, 0, -0.05)), c + V((0.13, 0, 0.05)), 0.022))
    elif attr == "sword":
        f.add(rod(h + V((0.02, 0.0, 0.10)), h + V((0.30, 0.25, -0.55)), 0.02))
        f.add(cb(h.x + 0.03, h.y + 0.02, h.z + 0.05, 0.18, 0.03, 0.03, BRONZE))
    elif attr == "tablet":
        f.add(cb(hl.x + 0.05, hl.y + 0.03, hl.z - 0.02, 0.26, 0.20, 0.035, BRONZE).rot((1, 0, 0), 20, tuple(hl)))
    else:           # Keule / Säulenstumpf der Stärke
        f.add(rod(V((0.30, 0.30, 0.0)), V((0.26, 0.26, 0.62)), 0.07, r1=0.045))
    return f


@model
def mon_friedrich_august_ii():
    """König Friedrich August II. (Hähnel 1866), Neumarkt. Gesamthöhe geschätzt 8,0 m."""
    s = cstack([(5.6, 5.6, 0), (5.6, 5.6, 0.24), (5.0, 5.0, 0.24), (5.0, 5.0, 0.48)], RED, 0.9)
    # roter Granitsockel: Kern mit vier vorspringenden Postamenten für die Sitzfiguren
    s.add(stack([(3.3, 3.3, 0.48), (3.3, 3.3, 0.62), (3.1, 3.1, 0.66), (3.1, 3.1, 1.24), (3.3, 3.3, 1.30),
                 (3.3, 3.3, 1.40)], RED))
    for k in range(4):
        p = stack([(1.9, 0.75, 0.48), (1.9, 0.75, 0.62), (1.75, 0.68, 0.66), (1.75, 0.68, 1.24), (1.9, 0.75, 1.30),
                   (1.9, 0.75, 1.40)], RED, cy=1.65 + 0.30)
        s.add(p.rot((0, 0, 1), 90 * k))
    # Bronzepfeiler mit Eckpilastern, Gesims, Attika
    w = 1.60
    s.add(stack([(w + 0.5, w + 0.5, 1.40), (w + 0.5, w + 0.5, 1.95), (w + 0.3, w + 0.3, 2.02), (w + 0.3, w + 0.3, 2.12),
                 (w, w, 2.20), (w, w, 3.62), (w + 0.10, w + 0.10, 3.66), (w + 0.10, w + 0.10, 3.74),
                 (w + 0.80, w + 0.80, 3.90), (w + 0.80, w + 0.80, 3.99), (w + 0.66, w + 0.66, 4.05),
                 (w + 0.05, w + 0.05, 4.09), (w - 0.05, w - 0.05, 4.14), (w - 0.05, w - 0.05, 4.58),
                 (w + 0.06, w + 0.06, 4.62), (w + 0.06, w + 0.06, 4.70)], BRONZE))
    for sx in (-1, 1):
        for sy in (-1, 1):       # kannelierte Eckpilaster (als Vorlage)
            s.add(cb(sx * (w / 2 - 0.10), sy * (w / 2 + 0.02), 2.91, 0.24, 0.05, 1.42, BRONZE))
            s.add(cb(sx * (w / 2 + 0.02), sy * (w / 2 - 0.10), 2.91, 0.05, 0.24, 1.42, BRONZE))
    s.add(cb(0, (w - 0.05) / 2 + 0.006, 4.36, 1.15, 0.012, 0.26, GOLD))                    # FRIEDRICH AUGUST II
    s.add(cb(0, -(w - 0.05) / 2 - 0.006, 4.36, 1.15, 0.012, 0.26, GOLD))
    # Sitzfiguren: Frömmigkeit (vorn, Kreuz), Weisheit, Stärke, Gerechtigkeit (Schwert)
    for k, attr in enumerate(("cross", "tablet", "club", "sword")):
        a = _alleg_sit(attr)
        seat = cb(0, 0, 0, 1.15, 0.72, 0.62, BRONZE).move(0, 1.42, 1.71)
        place(a, 1.40, 1.82, 0, 1.62)
        g = Soup().add(seat).add(a)
        s.add(g.rot((0, 0, 1), -90 * k))
    # König in Generalsuniform mit Mantel
    f, j = fig("fa2")
    f.add(cloak([(1.47, -0.01, 0.24, 0.16), (1.22, -0.04, 0.31, 0.22), (0.80, -0.08, 0.35, 0.28), (0.30, -0.12, 0.39, 0.33),
                 (0.02, -0.13, 0.41, 0.34)], BRONZE, half=118, k=9))
    el, wl = j["LowerArm_L"][0], j["Hand_L"][0]
    f.add(tube([j["UpperArm_L"][0] + V((0, 0, 0.03)), el, el.lerp(wl, 0.7)], 0.1, 7, BRONZE, rs=[0.10, 0.10, 0.09]))
    f.add(tube([el.lerp(wl, 0.4), el + V((-0.04, 0.05, -0.38)), el + V((-0.05, 0.03, -0.75))], 0.1, 6, BRONZE,
               rs=[0.10, 0.11, 0.05]))                                                     # Mantelbausch über dem linken Arm
    for sx in (-1, 1):
        f.add(cb(sx * 0.205, 0.0, 1.445, 0.10, 0.11, 0.025, BRONZE))                        # Epauletten
    f.add(robe([(0.62, 0, 0.0, 0.215, 0.17, 0.03), (0.95, 0, 0.0, 0.20, 0.155, 0.0), (1.06, 0, 0.0, 0.185, 0.14, 0.0)],
               n=10))                                                                      # Rockschoß
    hl, _ = hand(j, "L")
    f.add(tube([hl + V((0.0, 0.03, 0.10)), hl + V((-0.03, 0.0, -0.10)), hl + V((-0.10, -0.12, -0.80))], 0.02, 5, BRONZE))
    hr, dr = hand(j, "R")
    f.add(rod(hr - dr * 0.10, hr + dr * 0.22, 0.035))                                      # Verfassungsurkunde
    s.add(stack([(1.50, 1.50, 4.70), (1.50, 1.50, 4.82)], BRONZE))
    place(f, 4.82, HEIGHT["mon_friedrich_august_ii"] - 4.82, y=0.02)
    s.add(f)
    return s, ("Friedrich August II. (Neumarkt): Standfigur in Uniform mit Mantel und Urkunde (Blick +Y) auf "
               "Bronzepfeiler mit vier sitzenden Tugenden, roter Granitsockel mit Stufen. Gesamthöhe 8,0 m (geschätzt).")


@model
def mon_weber():
    """Carl Maria von Weber (Rietschel 1860), am Zwinger/Semperoper. Gesamthöhe geschätzt 5,75 m."""
    s = cstack([(3.7, 3.7, 0), (3.7, 3.7, 0.20), (2.75, 2.75, 0.20), (2.75, 2.75, 0.42)], RED, 0.55)
    s.add(B.stack([(2.10, 2.10, 0.42), (2.10, 2.10, 1.22), (2.16, 2.16, 1.26), (2.16, 2.16, 1.34), (1.96, 1.96, 1.40),
                   (1.84, 1.84, 1.40), (1.84, 1.84, 1.78), (1.74, 1.74, 1.84), (1.68, 1.68, 1.84), (1.64, 1.64, 2.72),
                   (1.74, 1.74, 2.78), (2.02, 2.02, 2.88), (2.02, 2.02, 2.97), (1.90, 1.90, 3.00)], RED, r=0.16))
    s.add(plaque(0.82, 0.42, 2.44, 0.83, t=0.04))                                         # CARL MARIA V. WEBER
    f, j = fig("weber")
    # Mantel: von der rechten Schulter über den Rücken, vorn als Schurz bis zu den Knöcheln
    f.add(cloak([(1.47, -0.01, 0.23, 0.15), (1.20, -0.05, 0.32, 0.22), (0.60, -0.09, 0.37, 0.28), (0.06, -0.10, 0.39, 0.30)],
                BRONZE, half=105, k=8).move(0.05, 0, 0))
    f.add(robe([(0.14, 0.02, 0.05, 0.34, 0.27, 0.09), (0.60, 0.02, 0.04, 0.30, 0.24, 0.07), (0.98, 0.02, 0.02, 0.26, 0.20, 0.03),
                (1.10, 0.01, 0.0, 0.22, 0.165, 0.0)], n=14, nf=5))
    sr = j["UpperArm_R"][0]
    f.add(tube([sr + V((-0.04, 0, 0.06)), sr + V((0.06, -0.02, -0.25)), sr + V((0.10, -0.03, -0.75))], 0.1, 7, BRONZE,
               rs=[0.10, 0.13, 0.11]))                                                     # Mantelmasse an der rechten Schulter
    hr, dr = hand(j, "R")
    f.add(wreath(0.10, 0.045, n=10).rot((1, 0, 0), 55).move(hr.x - 0.10, hr.y + 0.04, hr.z))   # Blumengebinde
    # Notenpult links neben der Figur
    px, py = -0.43, 0.12
    f.add(stack([(0.30, 0.30, 0.0), (0.30, 0.30, 0.05), (0.25, 0.25, 0.08), (0.25, 0.25, 0.40), (0.30, 0.30, 0.43),
                 (0.30, 0.30, 0.46), (0.17, 0.17, 0.50), (0.15, 0.15, 0.90), (0.20, 0.20, 0.94)], BRONZE, cx=px, cy=py))
    f.add(cb(0, 0, 0, 0.34, 0.035, 0.30, BRONZE).rot((1, 0, 0), -38).rot((0, 0, 1), -25).move(px + 0.02, py + 0.02, 1.03))
    s.add(stack([(1.72, 1.50, 3.00), (1.72, 1.50, 3.08)], BRONZE, cx=-0.12))
    place(f, 3.08, HEIGHT["mon_weber"] - 3.08, x=0.10, y=-0.05)
    s.add(f)
    return s, ("Carl-Maria-von-Weber-Denkmal: Bronzefigur im Mantel, linker Arm auf dem Notenpult erhoben, Blumengebinde "
               "in der Rechten (Blick +Y), roter Granitsockel mit Bronzetafel auf zwei Stufen. Gesamthöhe 5,75 m (geschätzt).")


@model
def mon_semper():
    """Gottfried Semper (Schilling 1892), Brühlsche Terrasse. Gesamthöhe geschätzt 5,6 m."""
    s = stack([(3.7, 3.7, 0), (3.7, 3.7, 0.20), (2.9, 2.9, 0.20), (2.9, 2.9, 0.42)], RED)
    s.add(stack([(1.92, 1.92, 0.42), (1.92, 1.92, 1.12), (1.80, 1.80, 1.18), (1.72, 1.72, 1.22), (1.78, 1.78, 1.27),
                 (1.72, 1.72, 1.32), (1.56, 1.56, 1.38), (1.52, 1.52, 1.38), (1.44, 1.44, 2.60), (1.50, 1.50, 2.64),
                 (1.76, 1.76, 2.72), (1.76, 1.76, 2.81), (1.66, 1.66, 2.84)], RED))
    s.add(plaque(0.74, 0.34, 2.28, 0.735, t=0.04))                                        # GOTTFRIED SEMPER
    s.add(stack([(1.46, 1.46, 2.84), (1.46, 1.46, 2.91), (1.34, 1.34, 2.94), (1.34, 1.34, 3.03)], BRONZE))
    f, j = fig("semper")
    f.add(robe([(0.52, 0, -0.03, 0.25, 0.19, 0.05), (0.80, 0, -0.02, 0.23, 0.175, 0.03), (1.08, 0, 0.0, 0.20, 0.15, 0.0)],
               n=12, nf=4))                                                                # Gehrock
    hr, dr = hand(j, "R")
    hl, dl = hand(j, "L")
    a, b = hr + V((0.04, 0.02, 0.0)), hl + V((-0.04, 0.03, 0.02))
    path = [a.lerp(b, t) + V((0, 0.07, -0.05)) * (4 * t * (1 - t)) for t in (-0.32, -0.15, 0, 0.25, 0.5, 0.75, 1, 1.10)]
    f.add(tube(path, 1.0, 4, BRONZE, prof=[(0.006, -0.07), (0.006, 0.07), (-0.006, 0.07), (-0.006, -0.07)]))   # Bauplan
    f.add(rod(path[0] + V((0, 0, -0.085)), path[0] + V((0, 0, 0.085)), 0.028))                # aufgerolltes Ende
    fl = j["Foot_L"][0]
    f.add(stack([(0.32, 0.38, 0.0), (0.32, 0.38, 0.04), (0.26, 0.32, 0.06), (0.26, 0.32, fl.z - 0.14),
                 (0.33, 0.39, fl.z - 0.10), (0.33, 0.39, fl.z - 0.075)], BRONZE, cx=fl.x - 0.02, cy=fl.y + 0.14))   # Kapitell
    place(f, 3.03, HEIGHT["mon_semper"] - 3.03, x=0.06, y=-0.22)
    s.add(f)
    return s, ("Gottfried-Semper-Denkmal (Brühlsche Terrasse): Bronzefigur im Gehrock, linker Fuß auf einem Kapitell, "
               "Bauplan in den Händen (Blick +Y), roter Granitsockel mit Bronzetafel auf zwei Stufen. Gesamthöhe 5,6 m (geschätzt).")


@model
def mon_rietschel():
    """Ernst-Rietschel-Denkmal (Schilling 1876), Brühlsche Terrasse. Gesamthöhe geschätzt 4,3 m."""
    a6 = math.pi / 6       # Sechseck mit einer Fläche nach vorn (+Y)
    s = lathe([(1.62, 0), (1.62, 0.16), (1.52, 0.22), (1.44, 0.22), (1.44, 0.36), (1.36, 0.40)], 6, GRANITE, a0=0)
    s.add(lathe([(1.34, 0.40), (1.34, 0.52), (1.24, 0.58), (1.22, 1.10), (1.30, 1.16), (1.30, 1.24), (1.20, 1.28)], 6,
                BRONZE, a0=0))
    del a6
    s.add(wreath(0.24, 0.06, n=12).move(0, 1.22 * math.cos(math.pi / 6) + 0.05, 0.84))
    # Säule mit Reliefband, darauf die Büste
    s.add(lathe([(0.50, 1.28), (0.50, 1.38), (0.38, 1.44), (0.29, 1.50), (0.27, 2.20), (0.30, 2.22), (0.30, 2.86),
                 (0.27, 2.88), (0.27, 3.00), (0.31, 3.04), (0.39, 3.10), (0.39, 3.17), (0.31, 3.20), (0.26, 3.20),
                 (0.22, 3.26)], 14, BRONZE))
    b = clip(fig("rest")[0], [((0, 0, 1.24), (0, 0, -1)), ((0.19, 0, 0), (1, 0, 0)), ((-0.19, 0, 0), (-1, 0, 0))])

    def taper(co):
        t = min(max((co.z - 1.24) / 0.20, 0.0), 1.0)
        t = t * t * (3 - 2 * t)
        return (co.x * (0.55 + 0.45 * t), co.y * (0.75 + 0.25 * t), co.z)
    b.warp(taper)
    # wallendes Haar
    b.add(ico(1.0, BRONZE, 2).scale(0.115, 0.12, 0.085).move(0, -0.035, 1.725))
    for sx in (-1, 1):
        b.add(ico(1.0, BRONZE, 1).scale(0.045, 0.07, 0.085).move(sx * 0.095, -0.04, 1.645))
    FIGB = b.move(0, 0, -1.24)
    k = (HEIGHT["mon_rietschel"] - 3.24) / max(v.z for v in FIGB.v)
    s.add(FIGB.scale(k * 1.25, k * 1.15, k).move(0, 0.02, 3.24))
    # drei sitzende Jünglinge (Zeichnen, Modellieren, Meißeln) rund um die Säule
    for ang, attr in ((60, "tablet"), (180, "bust"), (-60, "mallet")):
        f, j = fig("youth")
        f = decimate(f, 0.5)
        lo = min(v.z for v in f.v)
        f.add(cb(0, -0.02, lo + 0.14, 0.40, 0.34, 0.28, BRONZE))                           # Sitzblock
        hr, _ = hand(j, "R")
        hl, _ = hand(j, "L")
        if attr == "tablet":
            f.add(cb(0, 0, 0, 0.30, 0.03, 0.24, BRONZE).rot((1, 0, 0), -50).move(hl.x + 0.08, hl.y + 0.04, hl.z - 0.02))
        elif attr == "bust":
            f.add(ico(0.10, BRONZE, 1).scale(0.9, 1.0, 1.2).move(0.02, hl.y + 0.10, hl.z + 0.02))
            f.add(rod(V((0.02, hl.y + 0.10, lo)), V((0.02, hl.y + 0.10, hl.z - 0.08)), 0.05))
        else:
            f.add(rod(hr + V((0, 0, -0.04)), hr + V((0.02, 0.0, 0.20)), 0.018))
            f.add(cb(hr.x + 0.02, hr.y, hr.z + 0.22, 0.07, 0.14, 0.07, BRONZE))
        place(f, 1.28, 1.12, 0, 0.56)
        s.add(f.rot((0, 0, 1), ang))
    return s, ("Ernst-Rietschel-Denkmal (Brühlsche Terrasse): Bronzebüste (Blick +Y) auf Säule mit Reliefband, drei "
               "sitzende Jünglinge auf sechseckigem Bronzesockel mit Kranz, Granitstufe. Gesamthöhe 4,3 m (geschätzt).")


@model
def mon_koerner():
    """Theodor Körner (Hähnel 1871), Georgplatz. Statue 2,83 m, Postament ca. 2,5 m (Wikipedia), gesamt ca. 5,7 m."""
    s = stack([(3.5, 3.5, 0), (3.5, 3.5, 0.10), (2.7, 2.7, 0.10), (2.7, 2.7, 0.32), (2.5, 2.5, 0.40)], GRANITE)
    s.add(stack([(1.80, 1.80, 0.40), (1.80, 1.80, 1.12), (1.90, 1.90, 1.16), (1.90, 1.90, 1.22), (1.78, 1.78, 1.26),
                 (1.86, 1.86, 1.33), (1.78, 1.78, 1.40), (1.56, 1.56, 1.46), (1.50, 1.50, 1.46), (1.46, 1.46, 2.52),
                 (1.52, 1.52, 2.56), (1.82, 1.82, 2.66), (1.82, 1.82, 2.74), (1.50, 1.50, 2.80), (1.30, 1.30, 2.80),
                 (1.30, 1.30, 2.90)], GRANITE))
    # Leier und Schwert im Eichenkranz, darunter der Name
    yf = 0.74
    s.add(wreath(0.30, 0.05, n=12).scale(1, 1, 1.12).move(0, yf + 0.04, 2.12))
    s.add(wreath(0.15, 0.03, n=10).scale(1, 1, 1.25).move(0, yf + 0.04, 2.12))             # Leier
    s.add(rod(V((-0.30, yf + 0.05, 1.82)), V((0.30, yf + 0.05, 2.42)), 0.025))             # Schwert
    s.add(cb(0, yf + 0.006, 1.66, 0.95, 0.012, 0.08, BRONZE))                              # THEODOR KOERNER
    f, j = fig("koerner")
    f.add(cloak([(1.47, -0.01, 0.24, 0.16), (1.22, -0.05, 0.32, 0.23), (0.80, -0.09, 0.37, 0.29), (0.30, -0.13, 0.41, 0.34),
                 (0.02, -0.14, 0.43, 0.35)], BRONZE, half=112, k=9))
    f.add(robe([(0.52, 0, 0.0, 0.25, 0.20, 0.05), (0.90, 0, 0.0, 0.215, 0.17, 0.02), (1.08, 0, 0.0, 0.195, 0.15, 0.0)],
               n=12, nf=4))                                                                # Litewka bis zum Knie
    hl, dl = hand(j, "L")
    f.add(tube([hl + V((0.05, 0.02, 0.12)), hl + V((0.0, 0.02, 0.0)), hl + V((-0.13, 0.03, -0.40)),
                hl + V((-0.20, 0.02, -0.72)), hl + V((-0.22, 0.0, -0.86))], 0.02, 5, BRONZE,
               rs=[0.022, 0.022, 0.018, 0.014, 0.006]))                                    # Säbel
    f.add(cb(hl.x + 0.035, hl.y + 0.025, hl.z + 0.07, 0.09, 0.03, 0.025, BRONZE))
    hr, dr = hand(j, "R")
    f.add(rod(hr - dr * 0.12, hr + dr * 0.20, 0.038))                                      # Schriftrolle
    f.add(lathe([(0.15, 0.0), (0.12, 0.25), (0.11, 0.46)], 7, BRONZE, cx=0.14, cy=-0.24))  # Baumstumpf
    s.add(stack([(1.20, 1.20, 2.90), (1.20, 1.20, 3.00)], BRONZE))
    place(f, 3.00, 2.83, y=0.0)
    s.add(f)
    return s, ("Theodor-Körner-Denkmal (Georgplatz): Bronzefigur mit Mantel, Schwert an der Brust und Schriftrolle "
               "(Blick +Y), Granitpostament mit Leier und Schwert im Kranz. Statue 2,83 m, Postament 2,5 m, gesamt ca. 5,8 m.")


@model
def mon_truemmerfrau():
    """Trümmerfrau (W. Reinhold 1952), vor dem Neuen Rathaus. Gesamthöhe geschätzt 4,0 m."""
    s = stack([(1.9, 1.7, 0), (1.9, 1.7, 0.06)], GRANITE)
    s.add(stack([(1.50, 1.30, 0.06), (1.50, 1.30, 1.16)], BRICK))
    s.add(plaque(0.30, 0.20, 0.90, 0.65, t=0.02))
    s.add(stack([(1.24, 1.02, 1.16), (1.24, 1.02, 1.21), (1.02, 0.84, 1.23), (1.02, 0.84, 1.28)], BRONZE))
    f, j = fig("truemmerfrau")
    f.add(robe([(0.50, 0, 0.0, 0.245, 0.185, 0.03), (0.80, 0, 0.0, 0.22, 0.17, 0.02), (1.08, 0, 0.0, 0.19, 0.145, 0.0),
                (1.30, 0, 0.0, 0.19, 0.135, 0.0), (1.42, 0, 0.0, 0.14, 0.10, 0.0)], n=12, nf=3))   # Kittelschürze
    hd = j["Head"][0]
    ht = j["Head"][1]
    c = hd.lerp(ht, 0.95)
    f.add(ico(1.0, BRONZE, 1).scale(0.118, 0.128, 0.125).move(c.x, c.y - 0.03, c.z + 0.02))        # Kopftuch
    f.add(ico(0.045, BRONZE, 1).move(c.x, c.y - 0.15, c.z - 0.08))                         # Knoten im Nacken
    hr, dr = hand(j, "R")
    f.add(rod(hr + V((0, -0.10, 0.0)), hr + V((0, 0.26, 0.02)), 0.018))                    # Hammerstiel
    f.add(cb(hr.x, hr.y + 0.27, hr.z + 0.02, 0.05, 0.06, 0.16, BRONZE))                    # Hammerkopf
    place(f, 1.28, HEIGHT["mon_truemmerfrau"] - 1.28)
    s.add(f)
    return s, ("Trümmerfrau (Neues Rathaus): Bronzefigur mit Kopftuch und Schürze, Hammer in der rechten Hand, Arme "
               "abgespreizt (Blick +Y), auf Sockel aus Trümmerziegeln. Gesamthöhe 4,0 m (geschätzt).")


HEIGHT.update({"mon_luther": 6.85, "mon_friedrich_august_gerechte": 8.5, "mon_friedrich_august_ii": 8.0,
               "mon_weber": 5.75, "mon_semper": 5.6, "mon_rietschel": 4.3, "mon_koerner": 5.83,
               "mon_truemmerfrau": 4.0})
VIEWS = {n: ((12, 6), (62, 12)) for n in HEIGHT}
VIEWS["mon_rietschel"] = ((0, 8), (60, 14))


FOCUS = {"mon_luther": 3.4, "mon_friedrich_august_gerechte": 5.6, "mon_friedrich_august_ii": 4.7, "mon_weber": 3.0,
         "mon_semper": 2.9, "mon_rietschel": 1.2, "mon_koerner": 2.9, "mon_truemmerfrau": 1.3}


FOCUS2 = {"mon_friedrich_august_gerechte": (2.2, 4.3), "mon_friedrich_august_ii": (1.3, 3.6)}


def dev_render(ob, name, z0, zmax=None, tag="fig"):
    """Nur zur Kontrolle beim Bauen (--dev): Nahansicht des Teils über z0 aus drei Richtungen, 640 px je Ansicht."""
    import numpy as np
    cam = L._setup_preview_scene()
    sc = bpy.context.scene
    sc.render.resolution_x = sc.render.resolution_y = 640
    vs = [v.co for v in ob.data.vertices if v.co.z >= z0 and (zmax is None or v.co.z <= zmax)]
    lo = V((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = V((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    c, R = (lo + hi) / 2, (hi - lo).length / 2
    D = R / math.sin(cam.data.angle / 2) * 0.95
    out_dir = os.path.join(HERE, "monuments_named_dev")
    os.makedirs(out_dir, exist_ok=True)
    tiles = []
    for k, (az, el) in enumerate(((0, 4), (45, 8), (-60, 8))):
        a, e = math.radians(az), math.radians(el)
        d = V((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
        cam.location = c + d * D
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        fp = os.path.join(out_dir, f"_{name}_{k}.png")
        sc.render.filepath = fp
        bpy.ops.render.render(write_still=True)
        im = bpy.data.images.load(fp)
        tiles.append(np.array(im.pixels[:], dtype=np.float32).reshape(im.size[1], im.size[0], 4))
        bpy.data.images.remove(im)
        os.remove(fp)
    arr = np.concatenate(tiles, axis=1)
    img = bpy.data.images.new(name + "_dev", arr.shape[1], arr.shape[0], alpha=True)
    img.pixels.foreach_set(arr.ravel())
    img.filepath_raw = os.path.join(out_dir, f"{name}_{tag}.png")
    img.file_format = "PNG"
    img.save()


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    dev = "--dev" in argv
    L.NOPREVIEW = "--nopreview" in argv
    names = [a for a in argv if not a.startswith("--")] or list(MODELS)
    FIG.update(figures(POSES))
    for name in names:
        L.reset()
        mats()
        soup, notes = MODELS[name]()
        ob = build(soup, name, smooth_angle=42, merge=True)
        if dev:
            mat(BRONZE).node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.25, 0.33, 0.27, 1)
            mat(BRONZE).node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 0.2
            dev_render(ob, name, FOCUS[name])
            if name in FOCUS2:
                dev_render(ob, name, *FOCUS2[name], tag="mid")
            continue
        e = finish(name, [ob], notes, views=VIEWS.get(name))
        print(f"[named] {name}: Höhe {e['height']} (Soll {HEIGHT[name]}), {e['tris']} Dreiecke")
    try:
        os.rmdir(L.TMP)
    except OSError:
        pass


if __name__ == "__main__":
    main()
