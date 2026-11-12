"""Gemeinsame Blender-Helfer für veg_build.py und facade_build.py (läuft IN Blender 5.2).

Koordinaten: Blender Z-up; Export als glTF Y-up (Blender +Y -> glTF/Godot -Z).
"""
from __future__ import annotations

import json
import math
import os

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TEX = os.path.join(HERE, "tex")
MODELS = os.path.join(ROOT, "godot", "assets", "models")


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


# =====================================================================
# Materialien
# =====================================================================
_img_cache = {}


def image(fname, noncolor=False):
    p = os.path.join(TEX, fname)
    key = (p, noncolor)
    if key in _img_cache and _img_cache[key].name in bpy.data.images:
        return _img_cache[key]
    img = bpy.data.images.load(p, check_existing=False)
    img.name = os.path.splitext(fname)[0]
    if noncolor:
        img.colorspace_settings.name = "Non-Color"
    _img_cache[key] = img
    return img


def material(name, col=None, nrm=None, color=(0.8, 0.8, 0.8, 1.0), rough=0.8, metal=0.0,
             clip=None, double=False, alpha=None, vcol=False, nrm_strength=1.0, specular=0.5):
    """Principled-BSDF-Material, glTF-tauglich verdrahtet.

    clip=0.5  -> Alpha-Scissor (glTF alphaMode MASK, alphaCutoff=clip)
    alpha=0.3 -> Alpha-Blend (glTF BLEND) mit konstantem Alpha
    vcol=True -> Basisfarbe = Textur x Farbattribut "Color" (glTF COLOR_0)
    """
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    bsdf = next(n for n in N if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    try:
        bsdf.inputs["Specular IOR Level"].default_value = specular
    except KeyError:
        pass
    if col:
        t = N.new("ShaderNodeTexImage")
        t.image = image(col)
        t.location = (-700, 300)
        out = t.outputs["Color"]
        if vcol:
            ca = N.new("ShaderNodeVertexColor")
            ca.layer_name = "Color"
            ca.location = (-700, 0)
            mix = N.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs[0].default_value = 1.0
            mix.location = (-400, 250)
            L.new(out, mix.inputs[6])
            L.new(ca.outputs["Color"], mix.inputs[7])
            out = mix.outputs[2]
        L.new(out, bsdf.inputs["Base Color"])
        if clip is not None:
            lt = N.new("ShaderNodeMath")
            lt.operation = "LESS_THAN"
            lt.inputs[1].default_value = clip
            lt.location = (-400, 0)
            L.new(t.outputs["Alpha"], lt.inputs[0])
            sub = N.new("ShaderNodeMath")
            sub.operation = "SUBTRACT"
            sub.inputs[0].default_value = 1.0
            sub.location = (-200, 0)
            L.new(lt.outputs[0], sub.inputs[1])
            L.new(sub.outputs[0], bsdf.inputs["Alpha"])
            m.surface_render_method = "DITHERED"
    if nrm:
        tn = N.new("ShaderNodeTexImage")
        tn.image = image(nrm, noncolor=True)
        tn.location = (-700, -300)
        nm = N.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = nrm_strength
        nm.location = (-400, -300)
        L.new(tn.outputs["Color"], nm.inputs["Color"])
        L.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if alpha is not None:
        bsdf.inputs["Alpha"].default_value = alpha
        m.surface_render_method = "BLENDED"
    m.use_backface_culling = not double
    m.diffuse_color = color
    return m


# =====================================================================
# Mesh-Baukasten
# =====================================================================
def _v(p):
    return Vector((float(p[0]), float(p[1]), float(p[2])))


def face_normal(pts):
    n = Vector((0, 0, 0))
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        n.x += (a.y - b.y) * (a.z + b.z)
        n.y += (a.z - b.z) * (a.x + b.x)
        n.z += (a.x - b.x) * (a.y + b.y)
    return n.normalized() if n.length > 1e-12 else Vector((0, 0, 1))


def box_uv(p, n, scale=1.0, rot=False, offset=(0.0, 0.0)):
    """Weltbezogene Box-Projektion (1/scale Meter je UV-Einheit)."""
    ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
    if az >= ax and az >= ay:
        u, v = p.x, p.y * (1 if n.z > 0 else -1)
    elif ay >= ax:      # U wächst nach rechts aus Sicht des Betrachters vor der Fläche
        u, v = -p.x if n.y > 0 else p.x, p.z
    else:
        u, v = p.y if n.x > 0 else -p.y, p.z
    if rot:
        u, v = v, u
    return (u * scale + offset[0], v * scale + offset[1])


class MB:
    """Sammelt Vertices/Faces mit UV, Material, optional Normalen, Farbe, UV2."""

    def __init__(self):
        self.v = []
        self.faces = []      # dict(idx, uv, mat, n, col, uv2, smooth)
        self.mats = []

    def mat(self, name):
        if name not in self.mats:
            self.mats.append(name)
        return self.mats.index(name)

    def vert(self, p):
        self.v.append(_v(p))
        return len(self.v) - 1

    def face(self, idx, mat, uv=None, n=None, col=None, uv2=None, smooth=False, uvscale=1.0,
             uvrot=False, uvoff=(0.0, 0.0)):
        pts = [self.v[i] for i in idx]
        if uv is None:
            fn = face_normal(pts)
            uv = [box_uv(p, fn, uvscale, uvrot, uvoff) for p in pts]
        self.faces.append(dict(idx=list(idx), uv=list(uv), mat=self.mat(mat), n=n, col=col,
                               uv2=uv2, smooth=smooth or n is not None))

    def poly(self, pts, mat, **kw):
        idx = [self.vert(p) for p in pts]
        self.face(idx, mat, **kw)
        return idx

    # ---- Grundkörper
    def box(self, mn, mx, mat, skip=(), uvscale=1.0, uvrot=False, uvmap=None):
        x0, y0, z0 = mn
        x1, y1, z1 = mx
        F = {
            "-x": [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)],
            "+x": [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)],
            "-y": [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
            "+y": [(x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)],
            "-z": [(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)],
            "+z": [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
        }
        for k, pts in F.items():
            if k in skip:
                continue
            uv = None
            if uvmap is not None:
                uv = [uvmap(_v(p), k) for p in pts]
            self.poly(pts, mat, uv=uv, uvscale=uvscale, uvrot=uvrot)

    def tube(self, path, radii, sides, mat, cap0=False, cap1=False, u_range=(0.0, 1.0),
             v_scale=1.0, v0=0.0, smooth=True, cols=None, uv2=None, cap_uv=None, rot0=0.0,
             squash=None):
        """Röhre entlang einer Polylinie (parallel transportierte Rahmen).

        radii: Liste je Pfadpunkt; cols: Liste von Farben je Pfadpunkt; uv2: Liste je Pfadpunkt.
        cap_uv: (cu, cv, r) Kreis im Atlas für Deckel.
        squash: (sx, sy) elliptischer Querschnitt.
        """
        P = [_v(p) for p in path]
        n = len(P)
        T = []
        for i in range(n):
            if i == 0:
                t = P[1] - P[0]
            elif i == n - 1:
                t = P[-1] - P[-2]
            else:
                t = (P[i + 1] - P[i]).normalized() + (P[i] - P[i - 1]).normalized()
            T.append(t.normalized())
        ref = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
        N0 = T[0].cross(ref).normalized()
        frames = []
        Ncur = N0
        for i in range(n):
            if i > 0:
                Ncur = (Ncur - T[i] * Ncur.dot(T[i]))
                if Ncur.length < 1e-6:
                    Ncur = T[i].cross(ref)
                Ncur.normalize()
            B = T[i].cross(Ncur).normalized()
            frames.append((Ncur.copy(), B))
        sx, sy = squash if squash else (1.0, 1.0)
        rings = []
        dist = [0.0]
        for i in range(1, n):
            dist.append(dist[-1] + (P[i] - P[i - 1]).length)
        for i in range(n):
            Nn, B = frames[i]
            ring = []
            for k in range(sides + 1):
                a = 2 * math.pi * k / sides + rot0
                d = Nn * math.cos(a) * sx + B * math.sin(a) * sy
                ring.append((P[i] + d * radii[i], d.normalized()))
            rings.append(ring)
        idx = [[self.vert(p) for p, _ in ring] for ring in rings]
        for i in range(n - 1):
            for k in range(sides):
                a, b = idx[i][k], idx[i][k + 1]
                c, d = idx[i + 1][k + 1], idx[i + 1][k]
                u0 = u_range[0] + (u_range[1] - u_range[0]) * k / sides
                u1 = u_range[0] + (u_range[1] - u_range[0]) * (k + 1) / sides
                va = v0 + dist[i] * v_scale
                vb = v0 + dist[i + 1] * v_scale
                uv = [(u0, va), (u1, va), (u1, vb), (u0, vb)]
                nn = [rings[i][k][1], rings[i][k + 1][1], rings[i + 1][k + 1][1], rings[i + 1][k][1]] if smooth else None
                col = [cols[i], cols[i], cols[i + 1], cols[i + 1]] if cols else None
                u2 = [uv2[i], uv2[i], uv2[i + 1], uv2[i + 1]] if uv2 else None
                # Ringe laufen gegen den Uhrzeigersinn um T -> (a,b,c,d) zeigt nach außen
                self.face([a, b, c, d], mat, uv=uv, n=nn, col=col, uv2=u2)
        for which, do in ((0, cap0), (n - 1, cap1)):
            if not do:
                continue
            ring = [idx[which][k] for k in range(sides)]
            if which == 0:
                ring = ring[::-1]
            if cap_uv:
                cu, cv, cr = cap_uv
                uvs = []
                for k in range(sides):
                    kk = k if which != 0 else (sides - 1 - k)
                    a = 2 * math.pi * kk / sides
                    uvs.append((cu + cr * math.cos(a), cv + cr * math.sin(a)))
            else:
                uvs = None
            colc = [cols[which]] * sides if cols else None
            u2c = [uv2[which]] * sides if uv2 else None
            self.face(ring, mat, uv=uvs, col=colc, uv2=u2c)
        return idx

    def extrude_x(self, prof, x0, x1, mat, caps=True, uvscale=1.0, smooth_strip=False):
        """Profil (Liste (y,z), gegen Uhrzeigersinn von +X gesehen) entlang X extrudieren."""
        m = len(prof)
        a = [self.vert((x0, y, z)) for y, z in prof]
        b = [self.vert((x1, y, z)) for y, z in prof]
        for i in range(m):
            j = (i + 1) % m
            self.face([a[i], a[j], b[j], b[i]], mat, uvscale=uvscale)
        if caps:
            # +X-Deckel: Profil gegen Uhrzeigersinn von +X gesehen
            self.face(list(b), mat, uvscale=uvscale)
            self.face(list(a[::-1]), mat, uvscale=uvscale)

    # ---- Objekt erzeugen
    def build(self, name, mats):
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(v) for v in self.v], [], [f["idx"] for f in self.faces])
        for mn in self.mats:
            me.materials.append(mats[mn])
        uvl = me.uv_layers.new(name="UVMap")
        need_col = any(f["col"] for f in self.faces)
        need_uv2 = any(f["uv2"] for f in self.faces)
        need_n = any(f["n"] for f in self.faces)
        col = me.color_attributes.new("Color", "FLOAT_COLOR", "CORNER") if need_col else None
        uv2 = me.uv_layers.new(name="UVWind") if need_uv2 else None
        normals = []
        for pi, (poly, f) in enumerate(zip(me.polygons, self.faces)):
            poly.material_index = f["mat"]
            poly.use_smooth = f["smooth"]
            fn = face_normal([self.v[i] for i in f["idx"]])
            for k, li in enumerate(range(poly.loop_start, poly.loop_start + poly.loop_total)):
                uvl.data[li].uv = f["uv"][k]
                if col is not None:
                    c = f["col"][k] if f["col"] else (1, 1, 1)
                    col.data[li].color = (c[0], c[1], c[2], 1.0)
                if uv2 is not None:
                    uv2.data[li].uv = f["uv2"][k] if f["uv2"] else (0.0, 0.0)
                normals.append(tuple(f["n"][k]) if f["n"] else tuple(fn))
        uvl.active_render = True
        if col is not None:
            me.color_attributes.active_color = col
            me.color_attributes.render_color_index = 0
        me.update()
        if need_n:
            me.normals_split_custom_set([Vector(n).normalized() for n in normals])
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        return ob


# =====================================================================
# Export / Kennzahlen
# =====================================================================
def tri_count(ob):
    me = ob.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def bbox_godot(ob):
    """BBox in glTF/Godot-Koordinaten (x, z, -y)."""
    vs = [ob.matrix_world @ v.co for v in ob.data.vertices]
    g = [(v.x, v.z, -v.y) for v in vs]
    mn = [round(min(p[i] for p in g), 3) for i in range(3)]
    mx = [round(max(p[i] for p in g), 3) for i in range(3)]
    return mn, mx


def export_glb(ob, path, vcol=True):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    kw = dict(filepath=path, export_format="GLB", use_selection=True, export_apply=True,
              export_yup=True, export_texcoords=True, export_normals=True, export_tangents=False,
              export_materials="EXPORT", export_image_format="AUTO", export_extras=False,
              export_vertex_color="MATERIAL" if vcol else "NONE", export_animations=False,
              export_cameras=False, export_lights=False)
    bpy.ops.export_scene.gltf(**kw)
    return os.path.getsize(path)


def write_manifest(folder, entries):
    p = os.path.join(folder, "MANIFEST.json")
    old = []
    if os.path.exists(p):
        try:
            old = json.load(open(p))
        except Exception:
            old = []
    byfile = {e["file"]: e for e in old}
    for e in entries:
        byfile[e["file"]] = e
    out = sorted(byfile.values(), key=lambda e: e["file"])
    with open(p, "w") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    return p


def clear_scene_objects():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)
    for m in list(bpy.data.materials):
        bpy.data.materials.remove(m)
    for im in list(bpy.data.images):
        bpy.data.images.remove(im)
    _img_cache.clear()
