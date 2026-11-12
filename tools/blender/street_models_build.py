"""Straßenmodelle (Schildträger, Platten, Straßennamensschild, Haltestellenmast, Litfaßsäule, Plakatwand).

Aufruf (Blender 5.2, headless):
    flatpak run org.blender.Blender -b --python tools/blender/street_models_build.py [-- name1 name2 ...]
Vorher: make_traffic_signs.py, make_posters.py, make_street_textures.py, street_preview_inputs.py (PIL).

Konventionen: Meter, Ursprung = Bodenmitte (bzw. Plattenmitte bei plate_*), Vorderseite nach Blender +Y
(= Godot -Z), Export glTF binär, Y-up, Transformationen angewandt.
UV: Blender v=0 unten -> nach glTF/Godot UV.y = 1 - v (UV.y=0 oben); Texturen erscheinen aufrecht.
"""
import bpy
import bmesh
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sign_shapes import PLATES, outline, round_corners  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "godot", "assets", "models", "street")
PREV = os.path.join(OUT, "previews")
TEX = os.path.join(ROOT, "godot", "assets", "textures", "street")
TMP = os.path.join(HERE, "street_tmp")

POST_R = 0.0302       # Rohrpfosten Ø 60,3 mm
CLAMP_Y = -0.06       # Pfostenachse hinter Plattenmitte (passt zu street_life.gd: Platte 6 cm vor Pfosten)


# ---------------------------------------------------------------------------
# Materialien
# ---------------------------------------------------------------------------
def lin(c):
    def f(x):
        x = x / 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    return (f(c[0]), f(c[1]), f(c[2]), 1.0)


_MATS = {}


def mat(name, srgb=(200, 200, 200), rough=0.6, metal=0.0, image=None, emission=None):
    if name in _MATS:
        return _MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = lin(srgb)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if image:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(image, check_existing=True)
        tex.interpolation = "Linear"
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = lin(emission)
        bsdf.inputs["Emission Strength"].default_value = 0.0
    m.diffuse_color = lin(srgb)
    _MATS[name] = m
    return m


def preview_mat(name, image):
    m = bpy.data.materials.new(name + "_preview")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(image, check_existing=True)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    nt.nodes.active = tex
    return m


# ---------------------------------------------------------------------------
# Geometrie-Baukasten (bmesh)
# ---------------------------------------------------------------------------
class Builder:
    def __init__(self):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.mats = []

    def mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def face(self, cos, m, uvs=None, smooth=False, hint=None):
        """Polygon anlegen; hint = gewünschte Normalenrichtung (dreht die Reihenfolge bei Bedarf um)."""
        if hint is not None:
            nx = ny = nz = 0.0
            for i in range(len(cos)):
                a, c = cos[i], cos[(i + 1) % len(cos)]
                nx += (a[1] - c[1]) * (a[2] + c[2])
                ny += (a[2] - c[2]) * (a[0] + c[0])
                nz += (a[0] - c[0]) * (a[1] + c[1])
            if nx * hint[0] + ny * hint[1] + nz * hint[2] < 0:
                cos = cos[::-1]
                uvs = uvs[::-1] if uvs else uvs
        vs = [self.bm.verts.new(c) for c in cos]
        f = self.bm.faces.new(vs)
        f.material_index = self.mi(m)
        f.smooth = smooth
        if uvs:
            for loop, uv in zip(f.loops, uvs):
                loop[self.uv].uv = uv
        return f

    def box(self, x0, y0, z0, x1, y1, z1, m, skip=(), uv_scale=1.0):
        P = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        faces = {"-z": (0, 3, 2, 1), "+z": (4, 5, 6, 7), "-y": (0, 1, 5, 4), "+y": (2, 3, 7, 6),
                 "-x": (3, 0, 4, 7), "+x": (1, 2, 6, 5)}
        for k, idx in faces.items():
            if k in skip:
                continue
            cos = [P[i] for i in idx]
            # einfache planare UV in Metern
            ax = {"-z": (0, 1), "+z": (0, 1), "-y": (0, 2), "+y": (0, 2), "-x": (1, 2), "+x": (1, 2)}[k]
            uvs = [(c[ax[0]] * uv_scale, c[ax[1]] * uv_scale) for c in cos]
            hint = {"-z": (0, 0, -1), "+z": (0, 0, 1), "-y": (0, -1, 0), "+y": (0, 1, 0), "-x": (-1, 0, 0),
                    "+x": (1, 0, 0)}[k]
            self.face(cos, m, uvs, hint=hint)

    def lathe(self, profile, seg, cx=0.0, cy=0.0, u0=0.0, u_scale=1.0):
        """Rotationskörper um Z. profile: Liste (r, z, mat, smooth, v) – Segment i nutzt mat/smooth von Punkt i."""
        rings = []
        for (r, z, *_rest) in profile:
            rings.append([(cx + r * math.cos(2 * math.pi * k / seg), cy + r * math.sin(2 * math.pi * k / seg), z)
                          for k in range(seg + 1)])
        for i in range(len(profile) - 1):
            ra, za, m, smooth, va = profile[i]
            rb, zb, _m2, _s2, vb = profile[i + 1]
            for k in range(seg):
                ua, ub = u0 + u_scale * k / seg, u0 + u_scale * (k + 1) / seg
                if ra < 1e-6 and rb < 1e-6:
                    continue
                if ra < 1e-6:
                    self.face([rings[i][k], rings[i + 1][k + 1], rings[i + 1][k]], m, [(ua, va), (ub, vb), (ua, vb)],
                              smooth)
                    continue
                if rb < 1e-6:
                    self.face([rings[i][k], rings[i][k + 1], rings[i + 1][k]], m, [(ua, va), (ub, va), (ua, vb)], smooth)
                    continue
                self.face([rings[i][k], rings[i][k + 1], rings[i + 1][k + 1], rings[i + 1][k]], m,
                          [(ua, va), (ub, va), (ub, vb), (ua, vb)], smooth)

    def cylinder(self, r, z0, z1, seg, m, cx=0.0, cy=0.0, top=True, bottom=True, cap_m=None, smooth=True, v_scale=1.0):
        prof = []
        if bottom:
            prof.append((0.0, z0, cap_m or m, False, 0.0))
        prof.append((r, z0, m, smooth, z0 * v_scale))
        prof.append((r, z1, cap_m or m, False, z1 * v_scale))
        if top:
            prof.append((0.0, z1, cap_m or m, False, 0.0))
        self.lathe(prof, seg, cx, cy)

    def finish(self, name):
        bm = self.bm
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        # Kanten zwischen glatt/flach oder mit Knick > 50° hart markieren
        for e in bm.edges:
            if len(e.link_faces) == 2:
                f1, f2 = e.link_faces
                if f1.smooth != f2.smooth or f1.normal.angle(f2.normal, 0) > math.radians(50) or \
                        f1.material_index != f2.material_index:
                    e.smooth = False
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        for m in self.mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        return ob


# ---------------------------------------------------------------------------
# Modelle
# ---------------------------------------------------------------------------
def m_galv():
    return mat("MetalGalv", (168, 172, 170), rough=0.42, metal=0.75)


def m_cap():
    return mat("Cap", (52, 54, 56), rough=0.55)


def m_dark():
    return mat("MetalDark", (52, 57, 60), rough=0.45, metal=0.5)   # RAL 7016 anthrazit


def build_sign_post():
    b = Builder()
    g, cap = m_galv(), m_cap()
    b.cylinder(POST_R, -0.15, 2.995, 16, g, bottom=False, top=False, v_scale=1 / 3.0)
    b.lathe([(POST_R + 0.0025, 2.990, cap, True, 0), (POST_R + 0.0025, 3.012, cap, True, 0),
             (POST_R * 0.75, 3.022, cap, True, 0), (0.0, 3.025, cap, True, 0)], 16)
    b.lathe([(0.0, 2.990, cap, False, 0), (POST_R + 0.0025, 2.990, cap, False, 0)], 16)
    ob = b.finish("sign_post")
    return ob, {"notes": "Verzinkter Rohrpfosten Ø 60,3 mm, 3,0 m über Boden (+0,15 m im Boden, bbox_min.y=-0.15) mit "
                         "Kunststoffkappe. Achse = Ursprung. Materialien MetalGalv, Cap. Platten (plate_*.glb) "
                         "6 cm vor der Achse montieren (Platte +Y Blender / -Z Godot)."}


def build_plate(name):
    p = PLATES[name]
    w, h = p["w"], p["h"]
    b = Builder()
    face_m = mat("SignFace", (245, 245, 245), rough=0.35)
    back_m = mat("SignBack", (150, 153, 156), rough=0.5, metal=0.6)
    clamp_m = mat("Clamp", (160, 164, 162), rough=0.45, metal=0.75)
    T = 0.010
    o = outline(name, 0.0, seg=3 if name == "plate_octagon" else 6, circle_seg=40)
    front = [(x, T, y) for x, y in o]
    back = [(x, -T, y) for x, y in o]
    # Von vorn (+Y) gesehen liegt +X links -> u = (w/2 - x) / w, damit die Zelle seitenrichtig erscheint
    uvf = [((w / 2 - x) / w, (y + h / 2) / h) for x, y in o]
    b.face(front, face_m, uvf, hint=(0, 1, 0))
    b.face(back, back_m, [(1 - u, v) for u, v in uvf], hint=(0, -1, 0))
    n = len(o)
    for i in range(n):
        j = (i + 1) % n
        mx, mz = (o[i][0] + o[j][0]) / 2, (o[i][1] + o[j][1]) / 2
        b.face([front[i], back[i], back[j], front[j]], back_m, [(0, 0), (0, 0.02), (0.05, 0.02), (0.05, 0)],
               hint=(mx, 0, mz))
    # Montageschiene + Rohrschellen
    zc = {"plate_round": (-0.17, 0.17), "plate_triangle": (-0.22, 0.16), "plate_triangle_down": (-0.16, 0.22),
          "plate_octagon": (-0.17, 0.17), "plate_diamond": (-0.22, 0.22), "plate_square": (-0.17, 0.17),
          "plate_rect": (-0.30, 0.30), "plate_rect_wide": (-0.17, 0.17), "plate_oneway": (-0.075, 0.075)}[name]
    b.box(-0.018, -0.030, zc[0] - 0.045, 0.018, -T, zc[1] + 0.045, back_m, skip=("+y",))
    for z in zc:
        rr = POST_R + 0.0045
        b.lathe([(POST_R, z - 0.02, clamp_m, False, 0), (rr, z - 0.02, clamp_m, True, 0),
                 (rr, z + 0.02, clamp_m, False, 0), (POST_R, z + 0.02, clamp_m, False, 0)], 12, cx=0.0, cy=CLAMP_Y)
        b.box(-0.03, -0.036, z - 0.02, 0.03, -0.030, z + 0.02, clamp_m)
    ob = b.finish(name)
    desc = {"plate_round": "rund Ø 0,60 m", "plate_triangle": "Dreieck Seitenlänge 0,90 m, Spitze oben",
            "plate_triangle_down": "Dreieck 0,90 m, Spitze unten (Zeichen 205)", "plate_octagon": "Achteck 0,60 m (Schlüsselweite)",
            "plate_diamond": "Raute, Seitenlänge 0,60 m (Diagonale 0,85 m) wie Zeichen 306",
            "plate_square": "Quadrat 0,60 m", "plate_rect": "Rechteck 0,60 x 0,90 m hochkant",
            "plate_rect_wide": "Rechteck 0,90 x 0,60 m quer (Zeichen 325.1/325.2)",
            "plate_oneway": "Rechteck 0,90 x 0,30 m quer (Zeichen 220)"}[name]
    return ob, {"notes": f"Verkehrszeichen-Platte {desc}, Dicke 2 cm (Kantung), Ursprung = Mitte der Umrissbox "
                         f"({w:.3f} x {h:.3f} m). Material SignFace = Vorderseite (+Y Blender / -Z Godot) mit UV 0..1 über "
                         f"die Umrissbox (Godot-UV.y=0 oben) -> Atlaszelle traffic_signs.png. SignBack = Rückseite/Kante/"
                         f"Schiene (Alu grau). Clamp = 2 Rohrschellen bei Höhe {zc[0]:+.3f}/{zc[1]:+.3f} m um einen Ø-60-mm-"
                         f"Pfosten, dessen Achse 0,06 m hinter der Plattenmitte liegt (Godot z=+0.06). Ohne Pfosten Clamp "
                         f"ausblenden."}


def rounded_rect(w, h, r, seg=5):
    pts = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    return round_corners(pts, r, seg)


def street_plate_geom(b, zc, w=0.90, h=0.22, t=0.025):
    """Doppelseitige Dresdner Straßennamenstafel (dunkelblau Email), Mitte (0, 0, zc)."""
    sm = mat("StreetSign", (26, 40, 104), rough=0.25, image=os.path.join(TEX, "street_sign.png"))
    o = rounded_rect(w, h, 0.018, seg=4)
    front = [(x, t / 2, zc + y) for x, y in o]
    back = [(x, -t / 2, zc + y) for x, y in o]
    uv = [((w / 2 - x) / w, (y + h / 2) / h) for x, y in o]     # von +Y gesehen liegt +X links
    b.face(front, sm, uv, hint=(0, 1, 0))
    b.face(back, sm, [(1 - u, v) for u, v in uv], hint=(0, -1, 0))
    n = len(o)
    for i in range(n):
        j = (i + 1) % n
        mx, mz = (o[i][0] + o[j][0]) / 2, (o[i][1] + o[j][1]) / 2
        b.face([front[i], back[i], back[j], front[j]], sm, [(0.5, 0.5)] * 4, hint=(mx, 0, mz))
    return sm


def build_street_name_sign():
    b = Builder()
    g, cap, cl = m_galv(), m_cap(), mat("Clamp", (160, 164, 162), rough=0.45, metal=0.75)
    b.cylinder(POST_R, -0.15, 2.52, 16, g, bottom=False, top=False, v_scale=1 / 2.8)
    # Aufsteckhalter: Hülse + Sattel + seitliche Klemmlaschen
    b.cylinder(POST_R + 0.004, 2.48, 2.565, 16, cl, bottom=True, top=True)
    b.box(-0.15, -0.020, 2.565, 0.15, 0.020, 2.590, cl)
    for x in (-0.14, 0.11):
        b.box(x, -0.0165, 2.585, x + 0.03, 0.0165, 2.64, cl, skip=("-z",))
    zc = 2.590 + 0.11
    street_plate_geom(b, zc)
    ob = b.finish("street_name_sign")
    return ob, {"notes": "Pfosten Ø 60 mm (MetalGalv) mit Aufsteckhalter (Clamp) und leerer, doppelseitiger Dresdner "
                         "Straßennamenstafel 0,90 x 0,22 m, 2,5 cm dick, dunkelblau emailliert mit weißer Zierlinie "
                         "(Material StreetSign, Textur street_sign.png, Vorder- und Rückseite je UV 0..1, Kante UV=(0.5,0.5)). "
                         "Mitte der Schildfläche: Höhe y=2.700 m, Vorderseite z=-0.0125 (Godot, zeigt -Z), Rückseite "
                         "z=+0.0125 (zeigt +Z); Label3D ~2 mm davor. Schrift weiß #F2F2EE, Antiqua/Serifen "
                         "(z. B. NotoSerif-SemiBold), Versalhöhe ca. 0,075 m, nutzbare Textbreite ca. 0,80 m. "
                         "Zweite Tafel (Kreuzung): street_name_plate.glb 90° gedreht mit Mitte auf y=2.950 stapeln."}


def build_street_name_post():
    b = Builder()
    g, cl = m_galv(), mat("Clamp", (160, 164, 162), rough=0.45, metal=0.75)
    b.cylinder(POST_R, -0.15, 2.52, 16, g, bottom=False, top=False, v_scale=1 / 2.8)
    b.cylinder(POST_R + 0.004, 2.48, 2.565, 16, cl, bottom=True, top=True)
    b.box(-0.15, -0.020, 2.565, 0.15, 0.020, 2.590, cl)
    ob = b.finish("street_name_post")
    return ob, {"notes": "Pfosten Ø 60 mm (MetalGalv) mit Aufsteckhalter/Sattel (Clamp), Oberkante Sattel 2,59 m, ohne Tafel. "
                         "Für variable Tafelbreiten: street_name_plate.glb mit Mitte auf 2,700 m (in X skalieren), "
                         "zweite Tafel 90° gedreht auf 2,950 m."}


def build_street_name_plate():
    b = Builder()
    cl = mat("Clamp", (160, 164, 162), rough=0.45, metal=0.75)
    # Verbinder zur darunterliegenden Tafel (Unterkante -0.11, Abstand 3 cm)
    b.cylinder(0.018, -0.142, -0.108, 12, cl)
    b.box(-0.15, -0.020, -0.12, 0.15, 0.020, -0.108, cl)
    street_plate_geom(b, 0.0)
    ob = b.finish("street_name_plate")
    return ob, {"notes": "Nur die doppelseitige Straßennamenstafel 0,90 x 0,22 m (StreetSign wie street_name_sign) mit kurzem "
                         "Verbinder nach unten (Clamp, bis -0,142 m). Ursprung = Tafelmitte. Zum Stapeln auf "
                         "street_name_sign: Mitte auf 2,950 m, um 90° gedreht. Für längere Namen in X skalierbar "
                         "(bis ca. 1,4-fach, die weiße Zierlinie wird an den Schmalseiten etwas breiter)."}


def build_stop_pole():
    b = Builder()
    dark = m_dark()
    frame = mat("FrameAlu", (118, 122, 126), rough=0.4, metal=0.7)
    stop = mat("StopSign", (240, 202, 0), rough=0.35, image=os.path.join(TEX, "stop_sign.png"))
    ttm = mat("Timetable", (236, 236, 230), rough=0.15, image=os.path.join(TEX, "timetable.png"))
    R = 0.038
    b.cylinder(R, -0.15, 3.40, 16, dark, bottom=False, top=False, v_scale=1 / 3.4)
    b.lathe([(R + 0.002, 3.395, dark, True, 0), (R * 0.8, 3.425, dark, True, 0), (0.0, 3.435, dark, True, 0)], 16)
    b.lathe([(0.0, 3.395, dark, False, 0), (R + 0.002, 3.395, dark, False, 0)], 16)
    # Fahne 0,45 x 1,08 m in der YZ-Ebene, ragt zur Fahrbahn (+Y), Flächen zeigen +-X
    y0, y1, z0, z1 = 0.080, 0.530, 2.250, 3.330
    W, H = y1 - y0, z1 - z0
    yc, zc = (y0 + y1) / 2, (z0 + z1) / 2
    fo = 0.016  # Rahmenbreite
    outer = rounded_rect(W + 2 * fo, H + 2 * fo, 0.045, seg=5)
    inner = rounded_rect(W, H, 0.032, seg=5)
    tx, fx = 0.010, 0.020
    n = len(outer)
    for sx in (1, -1):
        # Plattenfläche (von +X gesehen liegt +Y rechts)
        pts = [(sx * tx, yc + u, zc + v) for u, v in inner]
        uv = [((u + W / 2) / W if sx > 0 else 1 - (u + W / 2) / W, (v + H / 2) / H) for u, v in inner]
        b.face(pts, stop, uv, hint=(sx, 0, 0))
        for i in range(n):
            j = (i + 1) % n
            q = [(sx * fx, yc + outer[i][0], zc + outer[i][1]), (sx * fx, yc + outer[j][0], zc + outer[j][1]),
                 (sx * fx, yc + inner[j][0], zc + inner[j][1]), (sx * fx, yc + inner[i][0], zc + inner[i][1])]
            b.face(q, frame, [(0, 0), (1, 0), (1, 1), (0, 1)], hint=(sx, 0, 0))
            mi_y, mi_z = (inner[i][0] + inner[j][0]) / 2, (inner[i][1] + inner[j][1]) / 2
            qi = [(sx * fx, yc + inner[i][0], zc + inner[i][1]), (sx * fx, yc + inner[j][0], zc + inner[j][1]),
                  (sx * tx, yc + inner[j][0], zc + inner[j][1]), (sx * tx, yc + inner[i][0], zc + inner[i][1])]
            b.face(qi, frame, [(0, 0), (1, 0), (1, 1), (0, 1)], hint=(0, -mi_y, -mi_z))
    for i in range(n):
        j = (i + 1) % n
        mo_y, mo_z = (outer[i][0] + outer[j][0]) / 2, (outer[i][1] + outer[j][1]) / 2
        q = [(fx, yc + outer[i][0], zc + outer[i][1]), (-fx, yc + outer[i][0], zc + outer[i][1]),
             (-fx, yc + outer[j][0], zc + outer[j][1]), (fx, yc + outer[j][0], zc + outer[j][1])]
        b.face(q, frame, [(0, 0), (0, 1), (1, 1), (1, 0)], hint=(0, mo_y, mo_z))
    # Ausleger + Schellen
    for z in (2.42, 3.16):
        b.box(-0.014, R - 0.004, z - 0.03, 0.014, y0 - fo + 0.004, z + 0.03, dark)
        b.cylinder(R + 0.005, z - 0.04, z + 0.04, 16, dark)
    # Fahrplankasten auf der +X-Seite des Masts (zeigt +X)
    bx0, bx1 = R - 0.004, R + 0.050
    by0, by1 = -0.165, 0.165
    bz0, bz1 = 1.22, 1.68
    b.box(bx0, by0, bz0, bx1, by1, bz1, dark, skip=("+x",))
    fr = 0.014
    X = (1, 0, 0)
    b.face([(bx1, by0, bz0), (bx1, by1, bz0), (bx1, by1, bz0 + fr), (bx1, by0, bz0 + fr)], dark, hint=X)
    b.face([(bx1, by0, bz1 - fr), (bx1, by1, bz1 - fr), (bx1, by1, bz1), (bx1, by0, bz1)], dark, hint=X)
    b.face([(bx1, by0, bz0 + fr), (bx1, by0 + fr, bz0 + fr), (bx1, by0 + fr, bz1 - fr), (bx1, by0, bz1 - fr)], dark, hint=X)
    b.face([(bx1, by1 - fr, bz0 + fr), (bx1, by1, bz0 + fr), (bx1, by1, bz1 - fr), (bx1, by1 - fr, bz1 - fr)], dark, hint=X)
    gx = bx1 - 0.004
    b.face([(gx, by0 + fr, bz0 + fr), (gx, by1 - fr, bz0 + fr), (gx, by1 - fr, bz1 - fr), (gx, by0 + fr, bz1 - fr)], ttm,
           [(0, 0), (1, 0), (1, 1), (0, 1)], hint=X)
    for yy, hy in ((by0 + fr, 1), (by1 - fr, -1)):
        b.face([(bx1, yy, bz0 + fr), (gx, yy, bz0 + fr), (gx, yy, bz1 - fr), (bx1, yy, bz1 - fr)], dark, hint=(0, hy, 0))
    for zz, hz in ((bz0 + fr, 1), (bz1 - fr, -1)):
        b.face([(bx1, by0 + fr, zz), (gx, by0 + fr, zz), (gx, by1 - fr, zz), (bx1, by1 - fr, zz)], dark, hint=(0, 0, hz))
    # Schellen des Kastens
    for z in (1.30, 1.60):
        b.cylinder(R + 0.004, z - 0.02, z + 0.02, 16, dark)
    ob = b.finish("stop_pole")
    return ob, {"notes": "DVB-artiger Haltestellenmast Ø 76 mm anthrazit (MetalDark, RAL 7016) 3,4 m (+0,15 m im Boden). "
                         "Fahne 0,45 x 1,08 m (Unterkante 2,25 m, Oberkante 3,33 m) mit Alu-Rahmen (FrameAlu) seitlich am "
                         "Mast, steht senkrecht zur Fahrbahn: sie ragt von y=0,08 bis 0,53 m nach +Y Blender (= -Z Godot "
                         "= zur Fahrbahn, passend zu facing_road_yaw) und ist beidseitig (Flächen zeigen +-X) mit "
                         "Material StopSign (stop_sign.png: Zeichen 224 grün/gelb, leeres Namensfeld, 4 Linienfelder, "
                         "ohne Logos) belegt. Namensfeld für Label3D: Mitte Godot (±0.011, 2.835, -0.305), Breite 0,40 m, "
                         "Höhe 0,15 m, Schrift schwarz. Fahrplankasten (Timetable, 0,30 x 0,43 m) bei 1,22–1,68 m auf der "
                         "+X-Seite des Masts, zeigt +X."}


def build_litfass():
    b = Builder()
    green = mat("MetalGreen", (38, 58, 46), rough=0.5, metal=0.35)
    poster = mat("Poster", (235, 232, 225), rough=0.8)
    seg = 32
    R = 0.60
    C = 2 * math.pi * R
    h1 = C / 3 * math.sqrt(2)       # untere Reihe: 3 Plakate im A-Format
    h2 = C / 6 * math.sqrt(2)       # obere Reihe: 6 Plakate
    z0 = 0.25
    z1 = z0 + h1 + h2
    S, F = True, False
    # Sockel
    b.lathe([(0.0, 0.0, green, F, 0), (0.66, 0.0, green, F, 0), (0.66, 0.08, green, S, 0), (0.645, 0.11, green, S, 0),
             (0.62, 0.13, green, F, 0), (0.62, z0, green, F, 0), (R, z0, poster, S, 0)], seg)
    # Mantel (Poster): u = Umfang 0..1, v = Höhe 0..1
    b.lathe([(R, z0, poster, S, 0.0), (R, z0 + h1, poster, S, h1 / (h1 + h2)), (R, z1, green, F, 1.0)], seg)
    # Abschlussring, Gesims, Kuppel, Knauf
    dome = []
    for k in range(6):
        a = math.radians(90 * k / 5)
        dome.append((0.64 * math.cos(a) if k < 5 else 0.0, 3.06 + 0.24 * math.sin(a), green, S, 0))
    prof = [(R, z1, green, F, 0), (0.625, z1, green, S, 0), (0.625, 2.975, green, F, 0), (0.685, 2.985, green, S, 0),
            (0.695, 3.015, green, S, 0), (0.685, 3.045, green, F, 0), (0.64, 3.06, green, S, 0)] + dome[1:]
    b.lathe(prof, seg)
    # Knauf
    ball = []
    for k in range(7):
        a = math.radians(-90 + 180 * k / 6)
        ball.append((0.045 * math.cos(a) if 0 < k < 6 else 0.0, 3.355 + 0.045 * math.sin(a), green, S, 0))
    b.lathe([(0.0, 3.29, green, F, 0), (0.018, 3.29, green, S, 0), (0.018, 3.312, green, S, 0)] + ball[1:], 12)
    ob = b.finish("litfass")
    return ob, {"notes": f"Litfaßsäule Ø 1,20 m (Sockel Ø 1,32), Höhe 3,40 m inkl. Kuppel und Knauf, dunkelgrün "
                         f"(MetalGreen). Material Poster = Mantel von y={z0:.3f} bis {z1:.4f} m. GODOT-UV (gemessen): "
                         f"UV.y = 0 an der OBERKANTE der Plakatfläche (y={z1:.3f}), UV.y = 1 an der UNTERKANTE "
                         f"(y={z0:.3f}) -> Textur direkt gesampelt steht aufrecht. UV.x = Umfang 0..1 (Naht bei Godot +X, "
                         f"wächst von +X Richtung -Z, von außen gesehen nach rechts -> Schrift seitenrichtig). "
                         f"Maße so gewählt, dass im Shader exakt A-Format entsteht: untere Reihe (UV.y > 1/3) "
                         f"Höhe {h1:.4f} m, UV.x*3 kacheln; obere Reihe (UV.y <= 1/3) Höhe {h2:.4f} m, UV.x*6 kacheln; "
                         f"Feld-UV unten: (fract(UV.x*3), (UV.y-1/3)*1.5), oben: (fract(UV.x*6), UV.y*3). "
                         f"Kollision: Zylinder r 0,66 m."}


def build_litfass_dresden():
    """Dresdner Litfaßsäule mit Glaslaterne, Zackenfries und Glaskugel (Gestaltung wie Güntzplatz/Sachsenplatz)."""
    b = Builder()
    green = mat("MetalGreen", (38, 58, 46), rough=0.5, metal=0.35)
    poster = mat("Poster", (235, 232, 225), rough=0.8)
    glass = mat("LanternGlass", (236, 233, 218), rough=0.2, image=os.path.join(TEX, "lantern_glass.png"),
                emission=(255, 236, 200))
    trim = mat("LanternTrim", (226, 200, 70), rough=0.4, image=os.path.join(TEX, "lantern_trim.png"))
    seg = 32
    S, F = True, False
    R = 0.55
    C = 2 * math.pi * R
    H = C * math.sqrt(2) / 2          # 3 + 6 A-Format-Plakate exakt (wie litfass.glb)
    z0 = 0.25
    z1 = z0 + H
    b.lathe([(0.0, 0.0, green, F, 0), (0.62, 0.0, green, F, 0), (0.62, 0.08, green, S, 0), (0.60, 0.11, green, S, 0),
             (0.575, 0.13, green, F, 0), (0.575, z0, green, F, 0), (R, z0, poster, S, 0)], seg)
    b.lathe([(R, z0, poster, S, 0.0), (R, z1, green, F, 1.0)], seg)
    # Gesims + Zackenfries
    b.lathe([(R, z1, green, F, 0), (0.575, z1, green, S, 0), (0.575, z1 + 0.05, green, F, 0),
             (0.60, z1 + 0.06, green, S, 0), (0.60, z1 + 0.09, green, F, 0), (0.585, z1 + 0.10, trim, S, 0.0),
             (0.585, z1 + 0.26, green, F, 1.0)], seg, u_scale=8)
    zl0 = z1 + 0.26
    # Laterne: 16 Glasfelder, leicht nach außen geneigt
    b.lathe([(0.585, zl0, green, F, 0), (0.60, zl0, glass, S, 0.0), (0.64, zl0 + 0.52, green, F, 1.0)], 16, u_scale=16)
    zd = zl0 + 0.52
    b.lathe([(0.64, zd, green, F, 0), (0.67, zd + 0.02, green, S, 0), (0.67, zd + 0.06, green, F, 0),
             (0.63, zd + 0.07, glass, S, 0.0)], 16)
    # Kuppel aus Glasfeldern
    prof = []
    for k in range(6):
        a = math.radians(90 * k / 6)
        r = 0.14 + 0.49 * math.cos(a)
        prof.append((r, zd + 0.07 + 0.40 * math.sin(a), glass if k < 5 else green, S, k / 5 * 2))
    prof.append((0.13, zd + 0.48, green, F, 0))
    b.lathe(prof, 16, u_scale=16)
    zn = zd + 0.48
    b.lathe([(0.13, zn, green, F, 0), (0.10, zn + 0.02, green, S, 0), (0.10, zn + 0.10, green, S, 0),
             (0.16, zn + 0.13, green, F, 0)], 16)
    # Glaskugel
    Rg, zg = 0.44, zn + 0.13 + 0.42
    prof = []
    for k in range(10):
        a = math.radians(-72 + 160 * k / 9)
        prof.append((Rg * math.cos(a), zg + Rg * math.sin(a), glass, S, k / 9 * 6))
    b.lathe([(0.16, zn + 0.13, glass, S, 0)] + prof[1:] + [(0.0, zg + Rg * 0.99, green, F, 0)], 16, u_scale=8)
    zt = zg + Rg
    b.lathe([(0.0, zt - 0.02, green, F, 0), (0.03, zt - 0.02, green, S, 0), (0.03, zt + 0.03, green, S, 0),
             (0.0, zt + 0.08, green, S, 0)], 10)
    ob = b.finish("litfass_dresden")
    return ob, {"notes": f"Dresdner Litfaßsäule (Gestaltung wie Güntzplatz/Sachsenplatz): Plakatsäule Ø 1,10 m, "
                         f"Zackenfries (LanternTrim), Glaslaterne + Glaskuppel + Glaskugel (LanternGlass, Textur mit "
                         f"Sprossen, Emission-Farbe gesetzt, Stärke 0 -> nachts einschalten), Rest MetalGreen. "
                         f"Höhe {zt + 0.08:.2f} m. Poster-Mantel y={z0:.3f}..{z1:.4f} m, UV wie litfass.glb: "
                         f"GODOT-UV.y = 0 an der OBERKANTE (y={z1:.3f}), 1 an der UNTERKANTE (y={z0:.3f}); UV.x = Umfang; "
                         f"untere Reihe UV.y > 1/3 (UV.x*3), obere UV.y <= 1/3 (UV.x*6) ergeben exakt A-Format. "
                         f"Kollision Zylinder r 0,62 m."}


def build_billboard():
    b = Builder()
    frame = mat("Frame", (46, 54, 52), rough=0.45, metal=0.4)
    back = mat("BillboardBack", (120, 124, 126), rough=0.6, metal=0.3)
    poster = mat("Poster", (235, 232, 225), rough=0.75)
    dark = m_dark()
    lamp = mat("LampEmit", (235, 235, 225), rough=0.3, emission=(255, 244, 220))
    W, H = 3.56, 2.52
    zb = 1.20
    fw = 0.08
    yf, yp, yb = 0.075, 0.040, -0.060
    x0, x1, z0, z1 = -W / 2, W / 2, zb, zb + H
    X0, X1, Z0, Z1 = x0 - fw, x1 + fw, z0 - fw, z1 + fw
    # Bildfläche
    # von vorn (+Y) gesehen liegt +X links -> u = 1 bei x0
    b.face([(x0, yp, z0), (x1, yp, z0), (x1, yp, z1), (x0, yp, z1)], poster, [(1, 0), (0, 0), (0, 1), (1, 1)],
           hint=(0, 1, 0))
    # Rahmen vorn (4 Trapeze)
    ring_o = [(X0, Z0), (X1, Z0), (X1, Z1), (X0, Z1)]
    ring_i = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
    for i in range(4):
        j = (i + 1) % 4
        q = [(ring_o[i][0], yf, ring_o[i][1]), (ring_o[j][0], yf, ring_o[j][1]), (ring_i[j][0], yf, ring_i[j][1]),
             (ring_i[i][0], yf, ring_i[i][1])]
        b.face(q, frame, hint=(0, 1, 0))
        qi = [(ring_i[i][0], yf, ring_i[i][1]), (ring_i[j][0], yf, ring_i[j][1]), (ring_i[j][0], yp, ring_i[j][1]),
              (ring_i[i][0], yp, ring_i[i][1])]
        mxi, mzi = (ring_i[i][0] + ring_i[j][0]) / 2, (ring_i[i][1] + ring_i[j][1]) / 2 - (z0 + z1) / 2
        b.face(qi, frame, hint=(-mxi, 0, -mzi))
        qo = [(ring_o[i][0], yf, ring_o[i][1]), (ring_o[i][0], yb, ring_o[i][1]), (ring_o[j][0], yb, ring_o[j][1]),
              (ring_o[j][0], yf, ring_o[j][1])]
        mxo, mzo = (ring_o[i][0] + ring_o[j][0]) / 2, (ring_o[i][1] + ring_o[j][1]) / 2 - (z0 + z1) / 2
        b.face(qo, frame, hint=(mxo, 0, mzo))
    # Rückwand
    b.face([(X0, yb, Z0), (X1, yb, Z0), (X1, yb, Z1), (X0, yb, Z1)], back, [(0, 0), (1, 0), (1, 1), (0, 1)],
           hint=(0, -1, 0))
    # Stützen (Vierkant 0,14 m) hinter der Tafel
    for xs in (-1.15, 1.15):
        b.box(xs - 0.07, yb - 0.14, -0.15, xs + 0.07, yb, Z1 - 0.12, dark, skip=("-z",))
        # Querriegel als Verstärkung
    b.box(-1.15, yb - 0.11, 0.62, 1.15, yb - 0.03, 0.70, dark)
    # Leuchten oben (Ausleger + Leuchtenkopf)
    for xs in (-0.95, 0.95):
        b.box(xs - 0.02, yf - 0.03, Z1, xs + 0.02, 0.62, Z1 + 0.04, dark)
        b.box(xs - 0.18, 0.50, Z1 + 0.00, xs + 0.18, 0.72, Z1 + 0.07, dark, skip=("-z",))
        b.face([(xs - 0.17, 0.51, Z1 - 0.001), (xs + 0.17, 0.51, Z1 - 0.001), (xs + 0.17, 0.71, Z1 - 0.001),
                (xs - 0.17, 0.71, Z1 - 0.001)], lamp, [(0, 0), (1, 0), (1, 1), (0, 1)], hint=(0, 0, -1))
    ob = b.finish("billboard")
    return ob, {"notes": "Großfläche 18/1: Bildfläche 3,56 x 2,52 m (Material Poster, UV 0..1, Godot-UV.y=0 Oberkante / 1 Unterkante, UV.x=0 links von vorn gesehen -> aufrecht und seitenrichtig; zeigt +Y Blender = -Z Godot, "
                         "Unterkante 1,20 m, Oberkante 3,72 m), 8-cm-Rahmen (Frame, dunkelgrün-grau), Rückwand "
                         "(BillboardBack), zwei Vierkantstützen 0,14 m (MetalDark, +0,15 m im Boden) hinter der Tafel, "
                         "zwei Aufsatzleuchten mit Material LampEmit (Unterseite, Emission 0 – nachts einschalten). "
                         "Bildfläche ist quer (√2:1) -> Atlas billboard_posters.png (Raster 3x3) verwenden, "
                         "nicht posters.png (hochkant)."}


# ---------------------------------------------------------------------------
# Export, Kennzahlen, Vorschau
# ---------------------------------------------------------------------------
def godot_bbox(ob):
    xs = [v.co.x for v in ob.data.vertices]
    ys = [v.co.y for v in ob.data.vertices]
    zs = [v.co.z for v in ob.data.vertices]
    # Godot: x = x, y = z, z = -y
    mn = [min(xs), min(zs), -max(ys)]
    mx = [max(xs), max(zs), -min(ys)]
    return [round(v, 3) for v in mn], [round(v, 3) for v in mx]


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def export(ob, path):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_texcoords=True, export_normals=True, export_materials="EXPORT",
                              export_image_format="AUTO", export_tangents=False, export_extras=False)


def setup_render():
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.color_type = "TEXTURE"
    sh.show_cavity = True
    sh.cavity_type = "WORLD"
    sh.show_shadows = True
    sh.shadow_intensity = 0.35
    sh.show_specular_highlight = True
    sc.display.render_aa = "16"
    if sc.world is None:
        sc.world = bpy.data.worlds.new("W")
    sc.world.color = (0.62, 0.67, 0.74)
    sh.studio_light = "outdoor.sl" if "outdoor.sl" in [l.name for l in bpy.context.preferences.studio_lights] else sh.studio_light
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "Standard"


def render_preview(objs, path, direction=(0.75, 1.6, 0.55), res=(720, 720), extra_ground=True):
    sc = bpy.context.scene
    for o in sc.objects:
        o.hide_render = o not in objs and o.type == "MESH" and o.name != "PreviewGround"
    pts = []
    for o in objs:
        pts += [o.matrix_world @ v.co for v in o.data.vertices]
    mn = [min(p[i] for p in pts) for i in range(3)]
    mx = [max(p[i] for p in pts) for i in range(3)]
    c = [(mn[i] + mx[i]) / 2 for i in range(3)]
    rad = max(math.dist(mn, mx) / 2, 0.2)
    g = bpy.data.objects.get("PreviewGround")
    if g is not None:
        g.hide_render = True
    if extra_ground:
        if g is None:
            gm = bpy.data.meshes.new("PreviewGround")
            s = 6.0
            gm.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
            g = bpy.data.objects.new("PreviewGround", gm)
            gmat = bpy.data.materials.new("PreviewGroundMat")
            gmat.diffuse_color = (0.30, 0.30, 0.29, 1)
            gm.materials.append(gmat)
            sc.collection.objects.link(g)
        g.hide_render = mn[2] > 0.5
        g.location = (c[0], c[1], 0)
    cam = bpy.data.objects.get("PreviewCam")
    if cam is None:
        cd = bpy.data.cameras.new("PreviewCam")
        cam = bpy.data.objects.new("PreviewCam", cd)
        sc.collection.objects.link(cam)
    cam.data.lens = 50
    cam.data.sensor_width = 36
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = res
    d = direction
    L = math.sqrt(sum(x * x for x in d))
    d = [x / L for x in d]
    fov = 2 * math.atan(18 / 50) * min(1.0, res[1] / res[0] if res[0] > res[1] else 1.0)
    dist = rad / math.sin(fov / 2) * 1.02
    cam.location = (c[0] + d[0] * dist, c[1] + d[1] * dist, c[2] + d[2] * dist)
    from mathutils import Vector
    look = Vector(c) - cam.location
    cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_start = 0.01
    cam.data.clip_end = 100
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def swap_for_preview(ob, mapping):
    for i, m in enumerate(ob.data.materials):
        if m and m.name in mapping:
            ob.data.materials[i] = mapping[m.name]


MODELS = {
    "sign_post": build_sign_post,
    "street_name_sign": build_street_name_sign,
    "street_name_plate": build_street_name_plate,
    "street_name_post": build_street_name_post,
    "stop_pole": build_stop_pole,
    "litfass": build_litfass,
    "litfass_dresden": build_litfass_dresden,
    "billboard": build_billboard,
}
for _p in PLATES:
    MODELS[_p] = (lambda nm: (lambda: build_plate(nm)))(_p)

PLATE_PREVIEW = {"plate_round": "274_30", "plate_triangle": "123", "plate_triangle_down": "205", "plate_octagon": "206",
                 "plate_diamond": "306", "plate_square": "350", "plate_rect": "314", "plate_rect_wide": "325.1",
                 "plate_oneway": "220"}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    names = argv or list(MODELS.keys())
    bpy.ops.wm.read_factory_settings(use_empty=True)
    os.makedirs(PREV, exist_ok=True)
    setup_render()
    man_path = os.path.join(OUT, "MANIFEST.json")
    manifest = {}
    if os.path.exists(man_path):
        for e in json.load(open(man_path, encoding="utf-8")):
            manifest[e["file"]] = e
    built = {}
    for nm in names:
        ob, info = MODELS[nm]()
        path = os.path.join(OUT, nm + ".glb")
        export(ob, path)
        mn, mx = godot_bbox(ob)
        height = round(mx[1] - mn[1], 3) if nm.startswith("plate_") else round(mx[1], 3)
        manifest[nm + ".glb"] = {"file": nm + ".glb", "height": height, "bbox_min": mn, "bbox_max": mx,
                                 "tris": tri_count(ob), "materials": [m.name for m in ob.data.materials],
                                 "notes": info["notes"], "size_bytes": os.path.getsize(path)}
        built[nm] = ob
        print("EXPORT", nm, tri_count(ob), mn, mx)
    # Vorschauen
    for nm, ob in built.items():
        mapping = {}
        if nm in PLATE_PREVIEW:
            mapping["SignFace"] = preview_mat("SignFace", os.path.join(TMP, "cells", PLATE_PREVIEW[nm] + ".png"))
        if nm in ("litfass", "litfass_dresden"):
            mapping["Poster"] = preview_mat("PosterL", os.path.join(TMP, "litfass_mantle.png"))
        if nm == "billboard":
            mapping["Poster"] = preview_mat("PosterB", os.path.join(TMP, "billboard_poster.png"))
        swap_for_preview(ob, mapping)
        tall = (manifest[nm + ".glb"]["bbox_max"][1] - manifest[nm + ".glb"]["bbox_min"][1]) > 1.5
        direction = (0.75, 1.6, 0.45)
        if nm == "stop_pole":
            direction = (1.6, 0.9, 0.35)
        if nm.startswith("plate_") or nm == "street_name_plate":
            direction = (0.55, 1.6, 0.35)
        render_preview([ob], os.path.join(PREV, nm + ".png"), direction=direction,
                       res=(560, 800) if tall and nm not in ("billboard",) else (800, 640),
                       extra_ground=not nm.startswith("plate_") and nm != "street_name_plate")
        ob.hide_render = True
    # Kombi-Vorschau: Pfosten mit drei Platten wie in street_life.gd montiert
    if all(k in built for k in ("sign_post", "plate_round", "plate_triangle_down", "plate_square")):
        sp = built["sign_post"]
        combo = [sp]
        for k, (pl, z) in enumerate((("plate_triangle_down", 2.45), ("plate_round", 1.85))):
            o2 = built[pl].copy()
            o2.data = built[pl].data.copy()
            o2.location = (0, -CLAMP_Y, z)
            bpy.context.scene.collection.objects.link(o2)
            combo.append(o2)
        for o in combo:
            o.hide_render = False
        render_preview(combo, os.path.join(PREV, "_combo_post_plates.png"), direction=(1.0, 1.4, 0.35), res=(560, 800))
        render_preview(combo, os.path.join(PREV, "_combo_post_plates_back.png"), direction=(-0.9, -1.2, 0.25),
                       res=(560, 800))
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(sorted(manifest.values(), key=lambda e: e["file"]), f, ensure_ascii=False, indent=2)
    print("FERTIG", len(built))


if __name__ == "__main__":
    main()
