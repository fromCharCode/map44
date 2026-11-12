"""Gemeinsame Bausteine fuer die Stadtmoebel-Modelle (Blender 5.2, headless).

Geometrie wird als "Soup" (Vertices + Faces mit Materialname und optionalen UVs)
zusammengesetzt und erst am Ende in ein Blender-Mesh verwandelt. Konventionen:
Blender Z-up, Meter, Ursprung = Bodenmitte, Vorderseite +Y (= Godot -Z).
"""
import bpy
import bmesh
import json
import math
import os
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "godot", "assets", "models", "furniture")
PREV = os.path.join(OUT, "previews")
TEX = os.path.join(HERE, "furniture_tex")
TMP = os.path.join(HERE, "furniture_tmp")
for d in (OUT, PREV, TMP):
    os.makedirs(d, exist_ok=True)

V = Vector
TAU = 2 * math.pi
NOPREVIEW = False


# ------------------------------------------------------------------ Farben/Materialien
def lin(c):
    if isinstance(c, str):
        h = c.lstrip("#")
        c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    out = []
    for x in c[:3]:
        out.append(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4)
    return (out[0], out[1], out[2], 1.0)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, col="#ffffff", rough=0.6, metal=0.0, tex=None, clip=None, double=False,
        spec=0.5, emit=None):
    """Principled-Material. tex = Dateiname in furniture_tex, clip = Alpha-Schwelle (MASK)."""
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = lin(col)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = spec
    m.diffuse_color = lin(col)
    if tex:
        img = bpy.data.images.load(os.path.join(TEX, tex), check_existing=True)
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = img
        tn.location = (-500, 200)
        nt.links.new(tn.outputs["Color"], b.inputs["Base Color"])
        if clip is not None:
            # glTF-Exporter erkennt "Greater Than" zwischen Textur-Alpha und BSDF -> alphaMode MASK
            mn = nt.nodes.new("ShaderNodeMath")
            mn.operation = "GREATER_THAN"
            mn.inputs[1].default_value = clip
            mn.location = (-250, -100)
            nt.links.new(tn.outputs["Alpha"], mn.inputs[0])
            nt.links.new(mn.outputs[0], b.inputs["Alpha"])
            try:
                m.surface_render_method = "DITHERED"
            except Exception:
                pass
    if emit is not None:
        b.inputs["Emission Color"].default_value = lin(emit)
        b.inputs["Emission Strength"].default_value = 1.0
    m.use_backface_culling = not double
    return m


# ------------------------------------------------------------------ Soup
class Soup:
    def __init__(self):
        self.v = []
        self.f = []  # (idx-liste, matname, uv-liste|None)

    def vert(self, co):
        self.v.append(V(co))
        return len(self.v) - 1

    def face(self, idx, m, uv=None):
        self.f.append((list(idx), m, uv))
        return self

    def poly(self, pts, m, uv=None):
        ids = [self.vert(p) for p in pts]
        return self.face(ids, m, uv)

    def add(self, other, M=None):
        off = len(self.v)
        flip = M is not None and M.to_3x3().determinant() < 0
        for co in other.v:
            self.v.append((M @ co) if M is not None else co.copy())
        for idx, m, uv in other.f:
            idx = [i + off for i in idx]
            if flip:
                idx = idx[::-1]
                uv = uv[::-1] if uv else uv
            self.f.append((idx, m, uv))
        return self

    def xf(self, M):
        flip = M.to_3x3().determinant() < 0
        self.v = [M @ co for co in self.v]
        if flip:
            self.f = [(i[::-1], m, (uv[::-1] if uv else uv)) for i, m, uv in self.f]
        return self

    def move(self, x=0, y=0, z=0):
        return self.xf(Matrix.Translation((x, y, z)))

    def rot(self, ax, deg, pivot=(0, 0, 0)):
        P = Matrix.Translation(pivot)
        return self.xf(P @ Matrix.Rotation(math.radians(deg), 4, ax) @ P.inverted())

    def scale(self, sx, sy, sz, pivot=(0, 0, 0)):
        P = Matrix.Translation(pivot)
        S = Matrix.Diagonal((sx, sy, sz, 1))
        return self.xf(P @ S @ P.inverted())

    def copy(self):
        s = Soup()
        s.add(self)
        return s

    def setmat(self, m):
        self.f = [(i, m, uv) for i, _, uv in self.f]
        return self

    def warp(self, fn):
        self.v = [V(fn(co)) for co in self.v]
        return self


def M_T(x=0, y=0, z=0):
    return Matrix.Translation((x, y, z))


def M_R(ax, deg):
    return Matrix.Rotation(math.radians(deg), 4, ax)


# ------------------------------------------------------------------ Ringe
def circle(r, n, z=0.0, cx=0.0, cy=0.0, a0=0.0, rx=None, ry=None):
    rx = r if rx is None else rx
    ry = r if ry is None else ry
    return [V((cx + math.cos(a0 + TAU * i / n) * rx, cy + math.sin(a0 + TAU * i / n) * ry, z))
            for i in range(n)]


def rrect(w, d, r, nc=3, z=0.0, cx=0.0, cy=0.0):
    """Rechteck w (X) x d (Y) mit Eckradius r, nc Segmente je Ecke, CCW von oben."""
    r = min(r, w / 2 - 1e-4, d / 2 - 1e-4)
    pts = []
    corners = [(w / 2 - r, d / 2 - r, 0), (-w / 2 + r, d / 2 - r, 90),
               (-w / 2 + r, -d / 2 + r, 180), (w / 2 - r, -d / 2 + r, 270)]
    for (x, y, a) in corners:
        for k in range(nc + 1):
            ang = math.radians(a + 90 * k / nc)
            pts.append(V((cx + x + math.cos(ang) * r, cy + y + math.sin(ang) * r, z)))
    # beginnend bei +X-Mitte waere schoener; Reihenfolge ist CCW
    return pts


def rect(w, d, z=0.0, cx=0.0, cy=0.0):
    return [V((cx + w / 2, cy - d / 2, z)), V((cx + w / 2, cy + d / 2, z)),
            V((cx - w / 2, cy + d / 2, z)), V((cx - w / 2, cy - d / 2, z))]


def _newell(ring):
    n = V((0, 0, 0))
    for i in range(len(ring)):
        a, b = ring[i], ring[(i + 1) % len(ring)]
        n.x += (a.y - b.y) * (a.z + b.z)
        n.y += (a.z - b.z) * (a.x + b.x)
        n.z += (a.x - b.x) * (a.y + b.y)
    return n


def _centroid(ring):
    c = V((0, 0, 0))
    for p in ring:
        c += p
    return c / len(ring)


def loft(rings, m, cap0=True, cap1=True, mats=None, capm=None, closed=True, uv=None,
         orient=None):
    """Mantelflaeche zwischen Ringen gleicher Punktzahl.

    mats: Material je Band (len(rings)-1), capm: (Material Anfang, Material Ende).
    uv: 'cyl' -> u = i/n, v = Bandindex anteilig ueber Laenge.
    Ringe werden automatisch so gedreht, dass die Normalen nach aussen zeigen.
    """
    s = Soup()
    rings = [[V(p) for p in r] for r in rings]
    n = len(rings[0])
    # Orientierung: Newell-Normale muss in Fortschrittsrichtung zeigen
    prog = orient
    if prog is None:
        prog = _centroid(rings[-1]) - _centroid(rings[0])
    if closed and prog.length > 1e-9:
        nn = V((0, 0, 0))
        for r in rings:
            if len(set((round(p.x, 6), round(p.y, 6), round(p.z, 6)) for p in r)) > 2:
                nn += _newell(r)
        if nn.dot(prog) < 0:
            rings = [r[::-1] for r in rings]
    ids = []
    for r in rings:
        ids.append([s.vert(p) for p in r])
    # Laenge fuer UV
    lens = [0.0]
    for k in range(1, len(rings)):
        lens.append(lens[-1] + (_centroid(rings[k]) - _centroid(rings[k - 1])).length
                    + abs(sum((rings[k][i] - _centroid(rings[k])).length for i in range(n)) / n
                          - sum((rings[k - 1][i] - _centroid(rings[k - 1])).length for i in range(n)) / n))
    L = lens[-1] if lens[-1] > 0 else 1.0
    seg = n if closed else n - 1
    for k in range(len(rings) - 1):
        mk = mats[k] if mats else m
        for i in range(seg):
            j = (i + 1) % n
            q = [ids[k][i], ids[k][j], ids[k + 1][j], ids[k + 1][i]]
            uvs = None
            if uv == "cyl":
                uvs = [(i / n, lens[k] / L), ((i + 1) / n, lens[k] / L),
                       ((i + 1) / n, lens[k + 1] / L), (i / n, lens[k + 1] / L)]
            # degenerierte Quads (Spitze) -> Dreieck
            pts = [s.v[x] for x in q]
            if (pts[2] - pts[3]).length < 1e-7:
                s.face([q[0], q[1], q[2]], mk, uvs[:3] if uvs else None)
            elif (pts[0] - pts[1]).length < 1e-7:
                s.face([q[0], q[2], q[3]], mk, [uvs[0], uvs[2], uvs[3]] if uvs else None)
            else:
                s.face(q, mk, uvs)
    cm0 = capm[0] if capm else m
    cm1 = capm[1] if capm else m
    if closed and cap0 and (_spread(rings[0]) > 1e-7):
        s.face(ids[0][::-1], cm0)
    if closed and cap1 and (_spread(rings[-1]) > 1e-7):
        s.face(ids[-1], cm1)
    return s


def _spread(r):
    c = _centroid(r)
    return max((p - c).length for p in r)


def cyl(r, h, n, m, z0=0.0, cx=0.0, cy=0.0, capm=None, cap0=True, cap1=True, uv=None, a0=None):
    a0 = (math.pi / n) if a0 is None else a0
    return loft([circle(r, n, z0, cx, cy, a0), circle(r, n, z0 + h, cx, cy, a0)], m,
                cap0=cap0, cap1=cap1, capm=capm, uv=uv)


def lathe(prof, n, m, mats=None, cx=0.0, cy=0.0, a0=None, cap0=True, cap1=True, capm=None, uv=None):
    """prof = [(r, z), ...] von unten nach oben."""
    a0 = (math.pi / n) if a0 is None else a0
    rings = [circle(max(r, 0.0), n, z, cx, cy, a0) for r, z in prof]
    return loft(rings, m, cap0=cap0, cap1=cap1, mats=mats, capm=capm, uv=uv,
                orient=V((0, 0, 1)))


def box(x0, y0, z0, x1, y1, z1, m, mats=None, skip=()):
    """Achsparalleler Quader. mats: dict Seite->Material (px,nx,py,ny,pz,nz)."""
    s = Soup()
    P = [V((x0, y0, z0)), V((x1, y0, z0)), V((x1, y1, z0)), V((x0, y1, z0)),
         V((x0, y0, z1)), V((x1, y0, z1)), V((x1, y1, z1)), V((x0, y1, z1))]
    ids = [s.vert(p) for p in P]
    F = {"nz": [0, 3, 2, 1], "pz": [4, 5, 6, 7], "ny": [0, 1, 5, 4],
         "py": [2, 3, 7, 6], "nx": [3, 0, 4, 7], "px": [1, 2, 6, 5]}
    for k, f in F.items():
        if k in skip:
            continue
        s.face([ids[i] for i in f], (mats or {}).get(k, m))
    return s


def cbox(cx, cy, cz, w, d, h, m, **kw):
    """Quader um (cx,cy) mit Unterkante cz."""
    return box(cx - w / 2, cy - d / 2, cz, cx + w / 2, cy + d / 2, cz + h, m, **kw)


def _frame(t, up_hint):
    t = t.normalized()
    up = V(up_hint)
    if abs(t.dot(up)) > 0.95:
        up = V((1, 0, 0)) if abs(t.x) < 0.9 else V((0, 1, 0))
    x = t.cross(up).normalized()
    y = x.cross(t).normalized()
    return x, y


def tube(path, r, n, m, caps=True, closed_path=False, up=(0, 0, 1), rs=None, prof=None):
    """Rohr entlang Polylinie (Gehrung an Knicken). rs = Radius je Punkt.
    prof = eigenes Querschnittsprofil [(a, b), ...] im Rahmen (x, y), CCW."""
    if prof is None:
        prof = [(math.cos(TAU * k / n), math.sin(TAU * k / n)) for k in range(n)]
    n = len(prof)
    pts = [V(p) for p in path]
    N = len(pts)
    rings = []
    # paralleler Transport des Rahmens
    t0 = (pts[1] - pts[0]).normalized()
    x, y = _frame(t0, up)
    prev_t = t0
    for i in range(N):
        if closed_path:
            tin = (pts[i] - pts[i - 1]).normalized()
            tout = (pts[(i + 1) % N] - pts[i]).normalized()
        else:
            tin = (pts[i] - pts[i - 1]).normalized() if i > 0 else (pts[1] - pts[0]).normalized()
            tout = (pts[i + 1] - pts[i]).normalized() if i < N - 1 else tin
        t = (tin + tout)
        if t.length < 1e-6:
            t = tout
        t.normalize()
        # Rahmen transportieren
        q = prev_t.rotation_difference(t)
        x = q @ x
        y = q @ y
        prev_t = t
        cosh = max(0.3, tin.dot(t))
        rr = (rs[i] if rs else r)
        ring = []
        for k in range(n):
            off = x * prof[k][0] * rr + y * prof[k][1] * rr
            # Gehrung: Anteil entlang Knickebene strecken
            d = off - t * off.dot(t)
            # Projektion auf Gehrungsebene: Punkt entlang tin verschieben
            if i > 0 and i < N - 1 or closed_path:
                bis = (tout - tin)
                if bis.length > 1e-6:
                    bis.normalize()
                    k_ = off.dot(bis)
                    off = off + bis * k_ * (1 / cosh - 1)
            ring.append(pts[i] + off)
        rings.append(ring)
    if _newell(rings[0]).dot(pts[1] - pts[0]) < 0:
        rings = [rg[::-1] for rg in rings]
    s = Soup()
    ids = [[s.vert(p) for p in rg] for rg in rings]
    segs = N if closed_path else N - 1
    for i in range(segs):
        a, b = ids[i], ids[(i + 1) % N]
        for k in range(n):
            j = (k + 1) % n
            s.face([a[k], a[j], b[j], b[k]], m)
    if caps and not closed_path:
        s.face(ids[0][::-1], m)
        s.face(ids[-1], m)
    return s


def quad_uv(p0, p1, p2, p3, m, uv=((0, 0), (1, 0), (1, 1), (0, 1))):
    s = Soup()
    s.poly([p0, p1, p2, p3], m, list(uv))
    return s


def ico(r, m, sub=1):
    """Ikosaeder (unterteilt) als Soup."""
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r)
    s = Soup()
    for v in bm.verts:
        s.vert(v.co)
    for f in bm.faces:
        s.face([v.index for v in f.verts], m)
    bm.free()
    return s


def grid_sphere(r, nu, nv, m, rz=None):
    """UV-Kugel (Pole als Dreiecke)."""
    rz = r if rz is None else rz
    rings = []
    for j in range(nv + 1):
        th = math.pi * j / nv - math.pi / 2
        rings.append(circle(r * math.cos(th), nu, rz * math.sin(th)))
    return loft(rings, m, cap0=False, cap1=False, orient=V((0, 0, 1)))


# ------------------------------------------------------------------ Mesh/Export
def _box_uv(co, n, sc):
    ax = max(range(3), key=lambda i: abs(n[i]))
    if ax == 0:
        return ((co.y if n.x > 0 else -co.y) * sc, co.z * sc)
    if ax == 1:
        return ((-co.x if n.y > 0 else co.x) * sc, co.z * sc)
    return (co.x * sc, (co.y if n.z > 0 else -co.y) * sc)


def build(soup, name, uvmode=None, smooth_angle=40, merge=False):
    """Soup -> Blender-Objekt. uvmode: dict Material -> ('box', scale) | ('face01',)."""
    uvmode = uvmode or {}
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bv = [bm.verts.new(co) for co in soup.v]
    bm.verts.ensure_lookup_table()
    mats = []
    for _, m, _ in soup.f:
        if m not in mats:
            mats.append(m)
    uvl = bm.loops.layers.uv.new("UVMap")
    for idx, m, uv in soup.f:
        if len(set(idx)) < 3:
            continue
        try:
            f = bm.faces.new([bv[i] for i in idx])
        except ValueError:
            continue  # doppelte Flaeche
        f.material_index = mats.index(m)
        f.normal_update()
        mode = uvmode.get(m, ("box", 1.0))
        if uv is not None:
            for lp, t in zip(f.loops, uv):
                lp[uvl].uv = t
        elif mode[0] == "face01":
            # jede Flaeche bekommt die ganze Textur; schmale Flaechen (< minw m) nur einen
            # Randstreifen u 0.02..0.06 (ohne Etikett)
            minw = mode[1] if len(mode) > 1 else 0.0
            us = [_box_uv(lp.vert.co, f.normal, 1.0) for lp in f.loops]
            u0, u1 = min(u for u, _ in us), max(u for u, _ in us)
            v0, v1 = min(v for _, v in us), max(v for _, v in us)
            for lp, (u, v) in zip(f.loops, us):
                fu = (u - u0) / max(u1 - u0, 1e-6)
                if u1 - u0 < minw:
                    fu = 0.02 + 0.04 * fu
                lp[uvl].uv = (fu, (v - v0) / max(v1 - v0, 1e-6))
        else:
            for lp in f.loops:
                lp[uvl].uv = _box_uv(lp.vert.co, f.normal, mode[1])
    if merge:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(bpy.data.materials.get(m) or mat(m))
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(smooth_angle))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def tri_count(objs):
    t = 0
    for ob in objs:
        ob.data.calc_loop_triangles()
        t += len(ob.data.loop_triangles)
    return t


def bbox(objs):
    lo = V((1e9, 1e9, 1e9))
    hi = V((-1e9, -1e9, -1e9))
    for ob in objs:
        for v in ob.data.vertices:
            co = ob.matrix_world @ v.co
            lo = V((min(lo.x, co.x), min(lo.y, co.y), min(lo.z, co.z)))
            hi = V((max(hi.x, co.x), max(hi.y, co.y), max(hi.z, co.z)))
    return lo, hi


def export(objs, name):
    bpy.ops.object.select_all(action="DESELECT")
    for ob in objs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    path = os.path.join(OUT, name + ".glb")
    kw = dict(filepath=path, export_format="GLB", use_selection=True, export_yup=True,
              export_apply=True, export_materials="EXPORT", export_texcoords=True, export_animations=False,
              export_normals=True, export_cameras=False, export_lights=False,
              export_extras=False)
    bpy.ops.export_scene.gltf(**kw)
    return path


# ------------------------------------------------------------------ Vorschau
def _setup_preview_scene():
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 560
    sc.render.resolution_y = 560
    sc.render.film_transparent = False
    try:
        sc.view_settings.view_transform = "Standard"
    except Exception:
        pass
    try:
        sc.eevee.taa_render_samples = 24
    except Exception:
        pass
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.55, 0.62, 0.72, 1)
    bg.inputs[1].default_value = 0.9
    sc.world = w
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.2
    sun.data.angle = math.radians(3)
    sun.rotation_euler = (math.radians(50), 0, math.radians(35))
    sc.collection.objects.link(sun)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.lens = 50
    sc.collection.objects.link(cam)
    sc.camera = cam
    gm = mat("_PrevGround", "#8a8d88", 0.9)
    me = bpy.data.meshes.new("_ground")
    me.from_pydata([(-60, -60, 0), (60, -60, 0), (60, 60, 0), (-60, 60, 0)], [], [(0, 1, 2, 3)])
    me.materials.append(gm)
    g = bpy.data.objects.new("_ground", me)
    sc.collection.objects.link(g)
    return cam


def preview(objs, name, views=((35, 22), (215, 22)), extra=None):
    """Zwei Ansichten nebeneinander (Azimut von +Y aus, Elevation)."""
    import numpy as np
    cam = _setup_preview_scene()
    lo, hi = bbox(objs)
    c = (lo + hi) / 2
    R = max((hi - lo).length / 2, 0.15)
    fov = cam.data.angle
    D = R / math.sin(fov / 2) * 1.02
    sc = bpy.context.scene
    tiles = []
    allv = list(views) + list(extra or [])
    for k, (az, el) in enumerate(allv):
        a = math.radians(az)
        e = math.radians(el)
        d = V((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
        cam.location = c + d * D
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        fp = os.path.join(TMP, f"{name}_v{k}.png")
        sc.render.filepath = fp
        bpy.ops.render.render(write_still=True)
        im = bpy.data.images.load(fp)
        arr = np.array(im.pixels[:], dtype=np.float32).reshape(im.size[1], im.size[0], 4)
        tiles.append(arr)
        bpy.data.images.remove(im)
    out = np.concatenate(tiles, axis=1)
    H, W = out.shape[:2]
    img = bpy.data.images.new(name + "_prev", W, H, alpha=True)
    img.pixels.foreach_set(out.ravel())
    img.filepath_raw = os.path.join(PREV, name + ".png")
    img.file_format = "PNG"
    img.save()
    for k in range(len(allv)):
        try:
            os.remove(os.path.join(TMP, f"{name}_v{k}.png"))
        except OSError:
            pass


# ------------------------------------------------------------------ Manifest
def manifest_update(entry):
    p = os.path.join(OUT, "MANIFEST.json")
    data = []
    if os.path.exists(p):
        with open(p) as fh:
            data = json.load(fh)
    data = [e for e in data if e.get("file") != entry["file"]]
    data.append(entry)
    data.sort(key=lambda e: e["file"])
    with open(p, "w") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def finish(name, objs, notes, materials_note=None, do_preview=True, views=None):
    lo, hi = bbox(objs)
    tris = tri_count(objs)
    path = export(objs, name)
    entry = {
        "file": name + ".glb",
        "height": round(hi.z, 3),
        # Godot-Koordinaten (x, y=hoch, z = -Blender-y)
        "bbox_min": [round(lo.x, 3), round(lo.z, 3), round(-hi.y, 3)],
        "bbox_max": [round(hi.x, 3), round(hi.z, 3), round(-lo.y, 3)],
        "tris": tris,
        "materials": sorted({ms.name for ob in objs for ms in ob.data.materials}),
        "notes": notes,
        "size_bytes": os.path.getsize(path),
    }
    manifest_update(entry)
    print(f"[furniture] {name}: {tris} tris, bbox {tuple(round(x, 3) for x in lo)} .. "
          f"{tuple(round(x, 3) for x in hi)}, {entry['size_bytes']} B")
    if do_preview and not NOPREVIEW:
        preview(objs, name, **({"views": views} if views else {}))
    return entry
