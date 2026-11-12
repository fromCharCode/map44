"""DVB-Haltestellenausstattung (Dresden), prozedural und maßstäblich.

Ausgaben (godot/assets/models/stops/):
  dvb_mast.glb          H-Mast (Rundrohr Ø 76 mm, 3,40 m) mit Schildfahne der aktuellen Generation (weißer Kopf,
                        gelber Schwung, Zeichen 224), modular: Knoten Head (Kopf + Namensfeld), LineRow (eine
                        Linienzeile, im Spiel je Linie duplizieren), Footer (Fußzeile DVB/VVO), Timetable (A4-Kasten)
  dfi_small.glb         LED-Anzeigemodul für die Fahne (wird zwischen Linienzeilen und Fußzeile eingesetzt)
  dfi_large.glb         große Abfahrtstafel am L-Mast („Galgen“), doppelseitig, Uhrfeld
  wall_shelter.glb      Wartehalle Wall/JCDecaux W1 (Flachdach-Glashalle 4,0 x 1,5 m)
  wall_shelter_long.glb dieselbe in 6,0 m
  platform_rail.glb     Schutzgitter-Segment (2 m Raster) wie an Dresdner Haltestelleninseln
  stop_bin.glb          Edelstahl-Abfallbehälter mit schrägem Deckel (Tram-Bahnsteige)
  stop_bin_city.glb     Stadtreinigungs-Behälter grau mit orangem Deckel
  MANIFEST.json         Anker (Godot-Koordinaten + Normale), Flächengrößen, Zeilenraster, Fußabdruck je Modell

Konventionen: Meter, Ursprung am Fußpunkt (Boden), Vorderseite (Gleis/Fahrbahn) = Blender +Y = Godot -Z.
Leerknoten Anchor_*: lokale Godot +Z = Blickrichtung (Flächennormale), lokale +Y = oben (passt für Label3D).
Maße/Farben: data/research/dvb_haltestellen.md (Fotos Wikimedia Commons nur zur Analyse). Keine fremden Modelle
oder Texturen; Texturen von make_stop_textures.py (selbst gezeichnet).

Aufruf: flatpak run --filesystem=host org.blender.Blender -b --python <abs>/build_stops.py [-- <ausgabeordner>]
"""
import bpy, bmesh, sys, os, math, json
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = ARGS[0] if ARGS else os.path.join(ROOT, "godot", "assets", "models", "stops")
TEX = os.path.join(HERE, "tex")
os.makedirs(OUT, exist_ok=True)

# Atlas dvb_sign.png (identisch mit make_stop_textures.py)
ATLAS = 1024
S_HEAD = 1100.0
S_A4 = 1500.0
REG = {"head": (0, 0), "foot": (0, 700), "a4": (640, 0)}


# ----------------------------------------------------------------------------------------------- Materialien
def srgb(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


MAT_SPECS = {
    # Mast / Fahne
    "StopPole": dict(col="#33363A", rough=0.45, metal=0.5),            # anthrazit, ≈ RAL 7021 / DB 703
    "SignFrame": dict(col="#1C1C1C", rough=0.4, metal=0.3),
    "SignPrint": dict(col="#FFFFFF", rough=0.35, tex="dvb_sign.png"),   # Kopf, Fußzeile, Fahrplanaushang
    "SignYellow": dict(col="#F2B01E", rough=0.35),                      # Namens-/Linienmodule
    "TimetableFrame": dict(col="#3C3F3A", rough=0.5, metal=0.3),
    "StopGlass": dict(col="#DDE6E8", rough=0.05, alpha=0.15, double=True),
    # Anzeigen
    "DfiEmit": dict(col="#050505", rough=0.25),
    "DfiHousing": dict(col="#F2B01E", rough=0.4),                       # gelbes Gehäuse (Schillerplatz)
    "DfiPanel": dict(col="#FFFFFF", rough=0.35, tex="dfi_panel.png"),
    # Wartehalle
    "StopSteel": dict(col="#3D4241", rough=0.45, metal=0.5),
    "NameBlende": dict(col="#F2A93B", rough=0.35),
    "CityLightFrame": dict(col="#1E1E1E", rough=0.4, metal=0.3),
    "PosterEmit": dict(col="#ECEAE3", rough=0.2, emit="#FFF8EC"),
    "BenchSeat": dict(col="#8E9296", rough=0.35, metal=0.7),
    "ShelterLightEmit": dict(col="#F4F2EC", rough=0.3, emit="#FFF4E0"),
    "InfoBoard": dict(col="#FFFFFF", rough=0.3, tex="info_board.png"),
    # Geländer
    "RailSteel": dict(col="#2F3234", rough=0.45, metal=0.5),
    "RailPanel": dict(col="#7E8487", rough=0.5, metal=0.4),
    # Abfallbehälter
    "BinSteel": dict(col="#B8BCC0", rough=0.3, metal=1.0),
    "BinLid": dict(col="#D6D8D9", rough=0.35, metal=0.3),
    "BinInside": dict(col="#101010", rough=0.9),
    "BinBase": dict(col="#2A2B2C", rough=0.6, metal=0.3),
    "BinGrey": dict(col="#8E9192", rough=0.5, metal=0.2),
    "BinLidOrange": dict(col="#D35A22", rough=0.45),
}
_MATS = {}


def mat(name):
    if name in _MATS:
        return _MATS[name]
    sp = MAT_SPECS[name]
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    col = srgb(sp["col"])
    b.inputs["Base Color"].default_value = (*col, 1.0)
    b.inputs["Roughness"].default_value = sp.get("rough", 0.5)
    b.inputs["Metallic"].default_value = sp.get("metal", 0.0)
    a = sp.get("alpha")
    m.diffuse_color = (*col, a if a is not None else 1.0)
    if sp.get("tex"):
        img = bpy.data.images.load(os.path.join(TEX, sp["tex"]), check_existing=True)
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = img
        tn.location = (-400, 250)
        nt.links.new(tn.outputs["Color"], b.inputs["Base Color"])
    if a is not None:
        b.inputs["Alpha"].default_value = a
        try:
            m.surface_render_method = "BLENDED"
        except Exception:
            m.blend_method = "BLEND"
    if sp.get("emit"):
        b.inputs["Emission Color"].default_value = (*srgb(sp["emit"]), 1.0)
        b.inputs["Emission Strength"].default_value = 1.0
    m.use_backface_culling = not sp.get("double", False)
    _MATS[name] = m
    return m


def new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _MATS.clear()
    ANCHORS.clear()


# ----------------------------------------------------------------------------------------------- Mesh-Bauer
def newell(pts):
    n = Vector((0, 0, 0))
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        n.x += (a.y - b.y) * (a.z + b.z)
        n.y += (a.z - b.z) * (a.x + b.x)
        n.z += (a.x - b.x) * (a.y + b.y)
    return n


class MB:
    """Vertices, Flächen, Material und UV je Fläche."""

    def __init__(self):
        self.v, self.f, self.m, self.uv = [], [], [], []

    def vert(self, p):
        self.v.append(Vector((float(p[0]), float(p[1]), float(p[2]))))
        return len(self.v) - 1

    def face(self, idx, mk, uvs=None, outward=None):
        idx = list(idx)
        if outward is not None:
            n = newell([self.v[i] for i in idx])
            if n.dot(Vector(outward)) < 0.0:
                idx.reverse()
                if uvs is not None:
                    uvs = list(reversed(uvs))
        self.f.append(idx)
        self.m.append(mk)
        self.uv.append(uvs)

    def poly(self, pts, mk, uvs=None, outward=None):
        self.face([self.vert(p) for p in pts], mk, uvs, outward)

    def build(self, name, origin=(0, 0, 0), parent=None, smooth_angle=35.0):
        o = Vector(origin)
        me = bpy.data.meshes.new(name)
        me.from_pydata([v - o for v in self.v], [], self.f)
        used = []
        for k in self.m:
            if k not in used:
                used.append(k)
        for k in used:
            me.materials.append(mat(k))
        uvl = me.uv_layers.new(name="UVMap")
        for i, p in enumerate(me.polygons):
            p.material_index = used.index(self.m[i])
            uvs = self.uv[i]
            for j, li in enumerate(p.loop_indices):
                uvl.data[li].uv = uvs[j] if uvs is not None else (0.0, 0.0)
        me.update()
        bm = bmesh.new()
        bm.from_mesh(me)
        for f in bm.faces:
            f.smooth = True
        lim = math.radians(smooth_angle)
        for e in bm.edges:
            if len(e.link_faces) == 2:
                f1, f2 = e.link_faces
                if f1.normal.angle(f2.normal, 0.0) > lim or f1.material_index != f2.material_index:
                    e.smooth = False
            else:
                e.smooth = False
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        ob.location = o
        bpy.context.collection.objects.link(ob)
        if parent is not None:
            ob.parent = parent
            ob.location = o - parent.location
        return ob


def box(mb, lo, hi, mk, skip=()):
    """Achsparalleler Quader von lo bis hi; skip: Seiten weglassen ('-x','+x','-y','+y','-z','+z')."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    c = Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    P = [Vector((x, y, z)) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    sides = {
        "-x": (0, 1, 3, 2), "+x": (4, 6, 7, 5), "-y": (0, 4, 5, 1),
        "+y": (2, 3, 7, 6), "-z": (0, 2, 6, 4), "+z": (1, 5, 7, 3),
    }
    for k, q in sides.items():
        if k in skip:
            continue
        pts = [P[i] for i in q]
        fc = sum(pts, Vector()) / 4
        mb.poly(pts, mk, outward=fc - c)


def bx(mb, c, s, mk, skip=()):
    box(mb, (c[0] - s[0] / 2, c[1] - s[1] / 2, c[2] - s[2] / 2), (c[0] + s[0] / 2, c[1] + s[1] / 2, c[2] + s[2] / 2),
        mk, skip)


def dedup(path, eps=1e-6):
    out = []
    for p in path:
        p = Vector(p)
        if not out or (p - out[-1]).length > eps:
            out.append(p)
    return out


def tube(mb, path, r, mk, seg=8, cap0=False, cap1=False, closed=False):
    """Rohr entlang eines Polygonzugs (paralleler Transport des Rings)."""
    path = dedup(path)
    n = len(path)
    tans = []
    for i in range(n):
        if closed:
            t = (path[(i + 1) % n] - path[i]).normalized() + (path[i] - path[i - 1]).normalized()
        elif i == 0:
            t = path[1] - path[0]
        elif i == n - 1:
            t = path[-1] - path[-2]
        else:
            t = (path[i + 1] - path[i]).normalized() + (path[i] - path[i - 1]).normalized()
        tans.append(t.normalized())
    ref = Vector((0, 0, 1)) if abs(tans[0].z) < 0.9 else Vector((1, 0, 0))
    nrm = tans[0].cross(ref).normalized()
    rings = []
    for i in range(n):
        if i > 0:
            q = tans[i - 1].rotation_difference(tans[i])
            nrm = (q @ nrm).normalized()
        bin_ = tans[i].cross(nrm).normalized()
        # Gehrung: Radius an Knicken etwas vergrößern
        sc = 1.0
        if 0 < i < n - 1 or closed:
            a = (path[(i + 1) % n] - path[i]).normalized()
            b = (path[i] - path[i - 1]).normalized()
            sc = 1.0 / max(0.5, math.cos(a.angle(b, 0.0) / 2))
        ring = []
        for k in range(seg):
            ang = 2 * math.pi * k / seg
            d = nrm * math.cos(ang) + bin_ * math.sin(ang)
            ring.append(mb.vert(path[i] + d * r * sc))
        rings.append((ring, path[i]))
    m = n if closed else n - 1
    for i in range(m):
        (ra, ca), (rb, cb) = rings[i], rings[(i + 1) % n]
        for k in range(seg):
            k2 = (k + 1) % seg
            idx = [ra[k], ra[k2], rb[k2], rb[k]]
            fc = sum((mb.v[j] for j in idx), Vector()) / 4
            mb.face(idx, mk, outward=fc - (ca + cb) / 2)
    if cap0 and not closed:
        mb.face(rings[0][0], mk, outward=-tans[0])
    if cap1 and not closed:
        mb.face(rings[-1][0], mk, outward=tans[-1])


def cyl(mb, a, b, r, mk, seg=8, caps=True):
    tube(mb, [a, b], r, mk, seg, caps, caps)


def arc2(cy, cz, r, a0, a1, n):
    """Kreisbogen in der (y, z)-Ebene, Winkel in Grad."""
    return [(cy + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cz + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def lathe(mb, prof, mk, seg=12, center=(0, 0)):
    """Rotationskörper um die Z-Achse aus [(r, z), ...] (von unten nach oben)."""
    rings = []
    for r, z in prof:
        if r < 1e-6:
            rings.append([mb.vert((center[0], center[1], z))])
        else:
            rings.append([mb.vert((center[0] + r * math.cos(2 * math.pi * k / seg),
                                   center[1] + r * math.sin(2 * math.pi * k / seg), z)) for k in range(seg)])
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        zc = (prof[i][1] + prof[i + 1][1]) / 2
        for k in range(seg):
            k2 = (k + 1) % seg
            if len(A) == 1:
                idx = [A[0], B[k2], B[k]]
            elif len(B) == 1:
                idx = [A[k], A[k2], B[0]]
            else:
                idx = [A[k], A[k2], B[k2], B[k]]
            fc = sum((mb.v[j] for j in idx), Vector()) / len(idx)
            out = fc - Vector((center[0], center[1], zc))
            if len(A) == 1:
                out = Vector((0, 0, -1)) + 0.01 * out
            if len(B) == 1:
                out = Vector((0, 0, 1)) + 0.01 * out
            mb.face(idx, mk, outward=out)


def yz_face(mb, x, pts_yz, mk, side, uvf=None):
    """Ebene Fläche bei x mit Umriss in (y, z); side = +1/-1 gibt die Normale ±X; uvf(y, z, side) -> (u, v)."""
    pts = [(x, y, z) for y, z in pts_yz]
    uvs = [uvf(y, z, side) for y, z in pts_yz] if uvf else None
    mb.poly(pts, mk, uvs, outward=(side, 0, 0))


def xz_face(mb, y, pts_xz, mk, side, uvf=None):
    pts = [(x, y, z) for x, z in pts_xz]
    uvs = [uvf(x, z, side) for x, z in pts_xz] if uvf else None
    mb.poly(pts, mk, uvs, outward=(0, side, 0))


# ----------------------------------------------------------------------------------------------- Anker / Manifest
ANCHORS = []


def g(v):
    """Blender -> Godot (Y oben, -Z vorn)."""
    return [round(v[0], 4), round(v[2], 4), round(-v[1], 4)]


def anchor(name, pos, normal, parent=None, size=None, note=None):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "ARROWS"
    e.empty_display_size = 0.1
    e.rotation_mode = "QUATERNION"
    e.rotation_quaternion = Vector(normal).normalized().to_track_quat("-Y", "Z")
    bpy.context.collection.objects.link(e)
    p = Vector(pos)
    if parent is not None:
        e.parent = parent
        e.location = p - parent.location
    else:
        e.location = p
    rec = {"name": name, "parent": parent.name if parent else None, "position": g(p), "normal": g(Vector(normal)),
           "local_position": g(e.location)}
    if size:
        rec["size"] = [round(size[0], 4), round(size[1], 4)]
    if note:
        rec["note"] = note
    ANCHORS.append(rec)
    return e


def stats():
    tris = 0
    lo = Vector((1e9, 1e9, 1e9))
    hi = -lo
    mats = set()
    for ob in bpy.context.scene.objects:
        if ob.type != "MESH":
            continue
        mw = ob.matrix_world
        for p in ob.data.polygons:
            tris += len(p.vertices) - 2
        for v in ob.data.vertices:
            w = mw @ v.co
            lo = Vector((min(lo[i], w[i]) for i in range(3)))
            hi = Vector((max(hi[i], w[i]) for i in range(3)))
        for m in ob.data.materials:
            mats.add(m.name)
    gl, gh = g(lo), g(hi)
    bmin = [min(gl[i], gh[i]) for i in range(3)]
    bmax = [max(gl[i], gh[i]) for i in range(3)]
    return {
        "tris": tris,
        "bbox_min": bmin, "bbox_max": bmax,
        "height": round(bmax[1], 3),
        "footprint": {"width_x": round(bmax[0] - bmin[0], 3), "depth_z": round(bmax[2] - bmin[2], 3)},
        "materials": sorted(mats),
    }


MANIFEST = {}


def export(fname, extra):
    bpy.context.view_layer.update()
    path = os.path.join(OUT, fname)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_yup=True, export_apply=True)
    rec = {"file": fname}
    rec.update(stats())
    rec["anchors"] = {a["name"]: {k: v for k, v in a.items() if k != "name"} for a in ANCHORS}
    rec.update(extra)
    rec["size_bytes"] = os.path.getsize(path)
    MANIFEST[fname] = rec
    print("[stops] %-22s %5d Tris  %s" % (fname, rec["tris"], rec["footprint"]))


# =============================================================================================== 1. H-Mast
MAST_R = 0.038           # Rundrohr Ø 76 mm
MAST_H = 3.40
SIGN_W = 0.60            # Fahne Außenbreite inkl. Rahmen
TUBE_R = 0.015           # Rahmenrohr Ø 30 mm
CORNER = 0.08            # Eckradius außen
GAP = 0.06               # Abstand Mastoberfläche - Fahne
Y_NEAR = -(MAST_R + GAP)             # Fahne hängt auf Blender -Y (vom Gleis weg, Godot +Z)
Y_FAR = Y_NEAR - SIGN_W
YC = (Y_NEAR + Y_FAR) / 2
PANEL_IN = 0.022                     # Plattenrand unter dem Rohr
PANEL_W = SIGN_W - 2 * PANEL_IN      # 0.556
VIS_IN = 0.030                       # sichtbarer Rand innen (Rohr außen)
TEXT_W = SIGN_W - 2 * VIS_IN         # 0.54 sichtbare Breite
FACE_X = 0.012                       # Schildfläche bei x = ±FACE_X
Z_TOP = 3.37                         # Oberkante Fahne (Mast steht 3 cm darüber)
HIDE = 0.008
HEAD_WHITE = 0.43
NAME_H = 0.18
Z_PANEL_TOP = Z_TOP - PANEL_IN
Z_STACK = Z_PANEL_TOP - HIDE - HEAD_WHITE - NAME_H     # Unterkante Namensfeld = Oberkante Linienzeile 0
ROW_P = 0.10             # Linienzeilen-Raster
SEP = 0.004              # Trennlinie
FOOT_H = 0.09
FOOT_OUT = FOOT_H + VIS_IN           # Fußzeile inkl. Rahmen unten
DFI_H = 0.28             # LED-Modul (dfi_small)
YC_TUBE_FAR = Y_FAR + TUBE_R
YC_TUBE_NEAR = Y_NEAR - TUBE_R
TT_Z = 1.30              # Mitte Fahrplankasten
TT_W, TT_H, TT_D = 0.25, 0.34, 0.045
TT_PITCH = 0.38


def atlas_uv(region, scale, u_m, v_m):
    x0, y0 = REG[region]
    return ((x0 + u_m * scale) / ATLAS, 1.0 - (y0 + v_m * scale) / ATLAS)


def sign_u(y, side):
    """Meter vom linken Plattenrand aus Sicht des Betrachters (side +1: Blick von +X, rechts = +Y)."""
    return (y - (Y_FAR + PANEL_IN)) if side > 0 else ((Y_NEAR - PANEL_IN) - y)


def head_uv(y, z, side):
    return atlas_uv("head", S_HEAD, sign_u(y, side), Z_PANEL_TOP - z)


def collar(mb, z, h=0.045):
    lathe(mb, [(0.0, z - h / 2), (MAST_R + 0.005, z - h / 2), (MAST_R + 0.005, z + h / 2), (0.0, z + h / 2)],
          "StopPole", seg=12)


def stub(mb, z):
    cyl(mb, (0, -0.02, z), (0, YC_TUBE_NEAR + 0.004, z), 0.011, "StopPole", seg=8, caps=False)
    collar(mb, z)


def side_tubes(mb, z0, z1):
    for y in (YC_TUBE_FAR, YC_TUBE_NEAR):
        cyl(mb, (0, y, z0), (0, y, z1), TUBE_R, "SignFrame", seg=8, caps=False)


def build_head():
    mb = MB()
    cf, cn = Y_FAR + CORNER, Y_NEAR - CORNER
    cz = Z_TOP - CORNER
    rc = CORNER - TUBE_R
    path = [(YC_TUBE_FAR, Z_STACK), (YC_TUBE_FAR, cz)] + arc2(cf, cz, rc, 180, 90, 6) + \
           arc2(cn, cz, rc, 90, 0, 6) + [(YC_TUBE_NEAR, cz), (YC_TUBE_NEAR, Z_STACK)]
    tube(mb, [(0, y, z) for y, z in path], TUBE_R, "SignFrame", seg=8)
    rp = CORNER - PANEL_IN
    outline = [(Y_FAR + PANEL_IN, Z_STACK), (Y_NEAR - PANEL_IN, Z_STACK)] + \
              arc2(cn, cz, rp, 0, 90, 6) + arc2(cf, cz, rp, 90, 180, 6)
    outline = [tuple(p) for p in dedup([(0, y, z) for y, z in outline])]
    outline = [(p[1], p[2]) for p in outline]
    for side in (1, -1):
        yz_face(mb, side * FACE_X, outline, "SignPrint", side, head_uv)
    # Plattenkante oben/seitlich liegt im Rohr; unten (Fuge zur Zeile) schließen
    stub(mb, Z_TOP - 0.10)
    stub(mb, Z_STACK + 0.10)
    ob = mb.build("Head", origin=(0, YC, Z_STACK))
    zc = Z_STACK + NAME_H / 2 + SEP / 2
    for side, nm in ((1, "Anchor_Name"), (-1, "Anchor_Name_Back")):
        anchor(nm, (side * (FACE_X + 0.002), YC, zc), (side, 0, 0), ob, (TEXT_W, NAME_H - SEP),
               "Haltestellenname, 1-2 Zeilen, schwarz, Versalhöhe 45-55 mm")
    # „Steig n“ rechts oben im weißen Kopf (aus Sicht des Betrachters)
    u = PANEL_W - 0.02 - 0.08
    zs = Z_PANEL_TOP - HIDE - 0.025
    for side, nm in ((1, "Anchor_Platform"), (-1, "Anchor_Platform_Back")):
        y = (Y_FAR + PANEL_IN + u) if side > 0 else (Y_NEAR - PANEL_IN - u)
        anchor(nm, (side * (FACE_X + 0.002), y, zs), (side, 0, 0), ob, (0.16, 0.035),
               "„Steig n“, dunkelgrau #4A4A4A, Versalhöhe 25-30 mm, rechtsbündig")
    return ob


def build_row(z_top, name="LineRow"):
    mb = MB()
    z0 = z_top - ROW_P
    y0, y1 = Y_FAR + PANEL_IN, Y_NEAR - PANEL_IN
    for side in (1, -1):
        x = side * FACE_X
        yz_face(mb, x, [(y0, z0), (y1, z0), (y1, z_top), (y0, z_top)], "SignYellow", side)
        xs = side * (FACE_X + 0.0006)
        yz_face(mb, xs, [(y0, z0), (y1, z0), (y1, z0 + SEP), (y0, z0 + SEP)], "SignFrame", side)
    side_tubes(mb, z0, z_top)
    ob = mb.build(name, origin=(0, YC, z_top))
    zc = z_top - (ROW_P - SEP) / 2
    for side, nm in ((1, "Anchor_Row0"), (-1, "Anchor_Row0_Back")):
        anchor(nm, (side * (FACE_X + 0.002), YC, zc), (side, 0, 0), ob, (TEXT_W, ROW_P - SEP),
               "Linienzeile: Nummer fett links (Versalhöhe 55-60 mm), Ziel rechts daneben (22-28 mm)")
    return ob


def build_footer(z_top):
    mb = MB()
    cf, cn = Y_FAR + CORNER, Y_NEAR - CORNER
    cz = z_top - FOOT_OUT + CORNER
    rc = CORNER - TUBE_R
    path = [(YC_TUBE_FAR, z_top), (YC_TUBE_FAR, cz)] + arc2(cf, cz, rc, 180, 270, 6) + \
           arc2(cn, cz, rc, 270, 360, 6) + [(YC_TUBE_NEAR, cz), (YC_TUBE_NEAR, z_top)]
    tube(mb, [(0, y, z) for y, z in path], TUBE_R, "SignFrame", seg=8)
    rp = CORNER - PANEL_IN
    outline = [(Y_NEAR - PANEL_IN, z_top), (Y_FAR + PANEL_IN, z_top)] + \
              arc2(cf, cz, rp, 180, 270, 6) + arc2(cn, cz, rp, 270, 360, 6)
    outline = [(p[1], p[2]) for p in dedup([(0, y, z) for y, z in outline])]

    def fuv(y, z, side):
        return atlas_uv("foot", S_HEAD, sign_u(y, side), z_top - z)

    for side in (1, -1):
        yz_face(mb, side * FACE_X, outline, "SignPrint", side, fuv)
    stub(mb, z_top - 0.025)
    return mb.build("Footer", origin=(0, YC, z_top))


def build_timetable():
    mb = MB()
    xb = MAST_R + 0.012
    xf = xb + TT_D
    y0, y1 = -TT_W / 2, TT_W / 2
    z0, z1 = TT_Z - TT_H / 2, TT_Z + TT_H / 2
    box(mb, (xb, y0, z0), (xf, y1, z1), "TimetableFrame")
    bz = 0.02
    # Rahmenleisten vorn
    for lo, hi in (((xf, y0, z0), (xf + 0.006, y1, z0 + bz)), ((xf, y0, z1 - bz), (xf + 0.006, y1, z1)),
                   ((xf, y0, z0 + bz), (xf + 0.006, y0 + bz, z1 - bz)),
                   ((xf, y1 - bz, z0 + bz), (xf + 0.006, y1, z1 - bz))):
        box(mb, lo, hi, "TimetableFrame", skip=("-x",))
    # A4-Aushang (Atlas) und Glas
    pw, ph = 0.210, 0.297
    pz0, pz1 = TT_Z - ph / 2, TT_Z + ph / 2
    py0, py1 = -pw / 2, pw / 2

    def a4uv(y, z, side):
        return atlas_uv("a4", S_A4, y - py0, pz1 - z)

    yz_face(mb, xf + 0.0008, [(py0, pz0), (py1, pz0), (py1, pz1), (py0, pz1)], "SignPrint", 1, a4uv)
    yz_face(mb, xf + 0.004, [(y0 + bz, z0 + bz), (y1 - bz, z0 + bz), (y1 - bz, z1 - bz), (y0 + bz, z1 - bz)],
            "StopGlass", 1)
    # Schellen am Mast
    for dz in (-0.10, 0.10):
        collar(mb, TT_Z + dz, 0.035)
        box(mb, (MAST_R - 0.005, -0.02, TT_Z + dz - 0.0175), (xb, 0.02, TT_Z + dz + 0.0175), "StopPole")
    return mb.build("Timetable", origin=(xb + TT_D / 2, 0.0, TT_Z))


def build_mast():
    new_scene()
    mb = MB()
    lathe(mb, [(0.0, 0.0), (MAST_R, 0.0), (MAST_R, MAST_H), (MAST_R - 0.003, MAST_H + 0.008),
               (0.024, MAST_H + 0.016), (0.0, MAST_H + 0.018)], "StopPole", seg=12)
    mb.build("Mast")
    build_head()
    build_row(Z_STACK)
    build_footer(Z_STACK - ROW_P)
    build_timetable()

    def sign_bottom(n, dfi=False):
        return round(Z_STACK - n * ROW_P - (DFI_H if dfi else 0.0) - FOOT_OUT, 4)

    extra = {
        "notes": "DVB-Haltestellenmast mit Schildfahne (Generation ab ca. 2021: weißer Kopf mit gelbem Schwung, "
                 "Zeichen 224, Name/Linien auf Gelb). Fahne doppelseitig, Fläche in der Godot-YZ-Ebene "
                 "(Normalen ±X), hängt auf der +Z-Seite des Masts (vom Gleis weg, freier Lichtraum). Für die andere "
                 "Seite die Instanz um 180° um Y drehen. Material SignYellow der LineRow kann für rote "
                 "Sonderlinien (#C8312A) überschrieben werden.",
        "sign": {
            "outer_width": SIGN_W,
            "text_width": round(TEXT_W, 4),
            "center_z": round(-YC, 4),
            "face_x": FACE_X,
            "top_y": Z_TOP,
            "stack_top_y": round(Z_STACK, 4),
            "row_pitch": ROW_P,
            "row_text_height": round(ROW_P - SEP, 4),
            "footer_height": round(FOOT_OUT, 4),
            "dfi_module_height": DFI_H,
            "module_origins": "Head: Unterkante Namensfeld; LineRow/Footer/DfiModule: jeweilige Oberkante; "
                              "alle bei (x=0, z=center_z)",
            "row_rule": "Zeile i (0-basiert): LineRow duplizieren, position = (0, stack_top_y - i*row_pitch, "
                        "center_z). Anchor_Row0/_Back wandern als Kinder mit.",
            "footer_rule": "Footer.position.y = stack_top_y - n_rows*row_pitch - (dfi ? dfi_module_height : 0)",
            "dfi_rule": "dfi_small.glb als Kind der Mast-Instanz (Identität), Knoten DfiModule.position.y = "
                        "stack_top_y - n_rows*row_pitch",
            "bottom_y_examples": {"1": sign_bottom(1), "2": sign_bottom(2), "3": sign_bottom(3),
                                  "4": sign_bottom(4), "6": sign_bottom(6), "3+dfi": sign_bottom(3, True)},
            "note_height": "Unterkante soll >= 2,20 m bleiben (Lichtraum Gehweg); ab 5 Zeilen ggf. ganze Fahne "
                           "anheben oder zweite Fahne/Stele verwenden",
        },
        "timetable": {"center_y": TT_Z, "size": [TT_W, TT_H], "face": "+X", "stack_pitch": TT_PITCH,
                      "note": "weitere Kästen: Timetable duplizieren, position.y -= stack_pitch (Mitte 1,2-1,4 m)"},
        "mast": {"diameter": 2 * MAST_R, "height": MAST_H},
        "ground_footprint": {"width_x": 2 * MAST_R, "depth_z": 2 * MAST_R, "note": "nur das Rohr steht am Boden"},
    }
    export("dvb_mast.glb", extra)


# =============================================================================================== 2. dfi_small
def build_dfi_small():
    new_scene()
    mb = MB()
    zt = Z_STACK - ROW_P          # Standardlage: direkt unter Linienzeile 0
    z0 = zt - DFI_H
    y0, y1 = Y_FAR + PANEL_IN, Y_NEAR - PANEL_IN
    ww, wh = 0.46, 0.19
    wzc = zt - DFI_H / 2 + 0.005
    wy0, wy1 = YC - ww / 2, YC + ww / 2
    wz0, wz1 = wzc - wh / 2, wzc + wh / 2
    bz = 0.012
    for side in (1, -1):
        x = side * FACE_X
        yz_face(mb, x, [(y0, z0), (y1, z0), (y1, zt), (y0, zt)], "SignYellow", side)
        xs = side * (FACE_X + 0.0006)
        yz_face(mb, xs, [(y0, z0), (y1, z0), (y1, z0 + SEP), (y0, z0 + SEP)], "SignFrame", side)
        # Rahmen um das Fenster (leicht erhaben)
        xb = side * (FACE_X + 0.004)
        for a, b in (((wy0 - bz, wz0 - bz), (wy1 + bz, wz0)), ((wy0 - bz, wz1), (wy1 + bz, wz1 + bz)),
                     ((wy0 - bz, wz0), (wy0, wz1)), ((wy1, wz0), (wy1 + bz, wz1))):
            yz_face(mb, xb, [(a[0], a[1]), (b[0], a[1]), (b[0], b[1]), (a[0], b[1])], "SignFrame", side)
        # Fenster (UV 0..1 in Leserichtung)

        def wuv(y, z, sd):
            u = (y - wy0) / ww if sd > 0 else (wy1 - y) / ww
            return (u, (z - wz0) / wh)

        yz_face(mb, side * (FACE_X + 0.0025), [(wy0, wz0), (wy1, wz0), (wy1, wz1), (wy0, wz1)], "DfiEmit", side, wuv)
        # Seitenwände des erhabenen Rahmens
        for (ya, za), (yb, zb) in (((wy0 - bz, wz0 - bz), (wy1 + bz, wz0 - bz)),
                                   ((wy0 - bz, wz1 + bz), (wy1 + bz, wz1 + bz))):
            mb.poly([(x, ya, za), (x, yb, zb), (xb, yb, zb), (xb, ya, za)], "SignFrame",
                    outward=(0, 0, 1 if za > wzc else -1))
        for (ya, za), (yb, zb) in (((wy0 - bz, wz0 - bz), (wy0 - bz, wz1 + bz)),
                                   ((wy1 + bz, wz0 - bz), (wy1 + bz, wz1 + bz))):
            mb.poly([(x, ya, za), (x, yb, zb), (xb, yb, zb), (xb, ya, za)], "SignFrame",
                    outward=(0, 1 if ya > YC else -1, 0))
    side_tubes(mb, z0, zt)
    ob = mb.build("DfiModule", origin=(0, YC, zt))
    for side, nm in ((1, "Anchor_Display"), (-1, "Anchor_Display_Back")):
        anchor(nm, (side * (FACE_X + 0.0035), YC, wzc), (side, 0, 0), ob, (ww, wh),
               "LED amber #FFA51F auf Schwarz, 3-4 Zeilen (Linie, Ziel, Minuten)")
    extra = {
        "notes": "Kleine LED-Abfahrtsanzeige als Modul der Haltestellenfahne (wie Cotta, Gottfried-Keller-Str.). "
                 "Gleiches Koordinatensystem wie dvb_mast.glb: als Kind der Mast-Instanz einsetzen, dann "
                 "DfiModule.position.y = sign.stack_top_y - n_rows*row_pitch und Footer zusätzlich um "
                 "module_height absenken. Doppelseitig. DfiEmit-Fläche hat UV 0..1 in Leserichtung.",
        "module_height": DFI_H,
        "display": {"width": ww, "height": wh},
        "default_position_y": round(zt, 4),
    }
    export("dfi_small.glb", extra)


# =============================================================================================== 3. dfi_large
def build_dfi_large():
    new_scene()
    mb = MB()
    R = 0.065                # Mastrohr Ø 130 mm
    Z_ARM = 3.62
    RB = 0.28                # Biegeradius
    ARM_L = 1.45             # Auslegerende (Achse) von der Mastachse; Gehäuse steht am Ende etwas über
    BX = 0.08                # halbe Gehäusetiefe
    BY0, BY1 = -1.63, -0.19  # Gehäuse in y (1,44 m)
    BZ0, BZ1 = 2.60, 3.40
    # Fußflansch und Mast mit Bogen
    lathe(mb, [(0.0, 0.0), (0.13, 0.0), (0.13, 0.025), (0.09, 0.03), (0.0, 0.03)], "StopPole", seg=12)
    path = [(0, 0, 0.03), (0, 0, Z_ARM - RB)]
    for i in range(1, 8):
        a = math.radians(90 * i / 8)
        path.append((0, -RB + RB * math.cos(a), Z_ARM - RB + RB * math.sin(a)))
    path.append((0, -RB, Z_ARM))
    path.append((0, -ARM_L, Z_ARM))
    tube(mb, path, R, "StopPole", seg=12, cap1=False)
    # Endkappe des Auslegers (Halbkugel grob)
    cap = []
    ring_c = Vector((0, -ARM_L, Z_ARM))
    seg = 12
    prev = None
    for j, (rr, dy) in enumerate(((R, 0.0), (R * 0.8, -0.03), (R * 0.4, -0.05), (0.0, -0.055))):
        if rr < 1e-6:
            cur = [mb.vert(ring_c + Vector((0, dy, 0)))]
        else:
            # Ring in der xz-Ebene, gleiche Orientierung wie tube(): Startvektor beliebig
            cur = [mb.vert(ring_c + Vector((rr * math.cos(2 * math.pi * k / seg), dy,
                                            rr * math.sin(2 * math.pi * k / seg)))) for k in range(seg)]
        if prev is not None:
            for k in range(seg):
                k2 = (k + 1) % seg
                idx = [prev[k], prev[k2], cur[0]] if len(cur) == 1 else [prev[k], prev[k2], cur[k2], cur[k]]
                fc = sum((mb.v[i] for i in idx), Vector()) / len(idx)
                mb.face(idx, "StopPole", outward=fc - ring_c + Vector((0, -0.01, 0)))
        prev = cur
    # Abhänger
    for yh in (-1.30, BY1 - 0.22):
        box(mb, (-0.025, yh - 0.03, BZ1), (0.025, yh + 0.03, Z_ARM - R + 0.01), "StopPole")
        box(mb, (-0.05, yh - 0.05, BZ1 + 0.005), (0.05, yh + 0.05, BZ1 + 0.025), "StopPole")
    # Gehäuse mit Regendach
    box(mb, (-BX, BY0, BZ0), (BX, BY1, BZ1), "DfiHousing")
    box(mb, (-BX - 0.01, BY0 - 0.01, BZ1), (BX + 0.01, BY1 + 0.01, BZ1 + 0.012), "DfiHousing")
    # Frontflächen je Seite: Anzeige am Mastende, Uhrfeld am freien Ende
    bez = 0.04
    DW, DH = 0.80, 0.70
    dz0, dz1 = BZ0 + 0.05, BZ0 + 0.05 + DH
    dy1 = BY1 - bez
    dy0 = dy1 - DW
    cy1 = dy0 - 0.03
    cy0 = BY0 + 0.03
    cz0, cz1 = BZ0 + 0.04, BZ1 - 0.04
    for side in (1, -1):
        x = side * (BX + 0.0015)

        def duv(y, z, sd):
            u = (y - dy0) / DW if sd > 0 else (dy1 - y) / DW
            return (u, (z - dz0) / DH)

        def cuv(y, z, sd):
            w = cy1 - cy0
            u = (y - cy0) / w if sd > 0 else (cy1 - y) / w
            return (u, (z - cz0) / (cz1 - cz0))

        yz_face(mb, x, [(dy0, dz0), (dy1, dz0), (dy1, dz1), (dy0, dz1)], "DfiEmit", side, duv)
        yz_face(mb, x, [(cy0, cz0), (cy1, cz0), (cy1, cz1), (cy0, cz1)], "DfiPanel", side, cuv)
    mb.build("DfiLarge")
    yc = (dy0 + dy1) / 2
    zc = (dz0 + dz1) / 2
    anchor("Anchor_Display", (BX + 0.003, yc, zc), (1, 0, 0), None, (DW, DH),
           "LED amber #FFA51F, Kopfzeile + 6 Zeilen: Linie | Ziel | Minuten (sofort)")
    anchor("Anchor_Display_Back", (-BX - 0.003, yc, zc), (-1, 0, 0), None, (DW, DH),
           "Rückseite, gleicher Inhalt")
    extra = {
        "notes": "Große LED-Abfahrtstafel am L-Mast (Bestand wie Schillerplatz): gelbes Gehäuse 1,44 x 0,80 x "
                 "0,16 m, Unterkante 2,60 m, schwarze Anzeige am Mastende, Analoguhr am freien Ende. "
                 "Doppelseitig, Anzeigeflächen in der Godot-YZ-Ebene (Normalen ±X). Mast (Ø 140 mm) steht am "
                 "Ursprung (Bahnsteigkante), Ausleger zeigt nach Godot +Z (vom Gleis weg).",
        "display": {"width": DW, "height": DH, "uv": "0..1 in Leserichtung je Seite"},
        "ground_footprint": {"width_x": 0.26, "depth_z": 0.26, "note": "Fußflansch; Ausleger in 2,6-3,7 m Höhe"},
        "housing": {"width": round(BY1 - BY0, 3), "height": round(BZ1 - BZ0, 3), "depth": 2 * BX,
                    "bottom_y": BZ0},
    }
    export("dfi_large.glb", extra)


# =============================================================================================== 4. Wartehalle
def build_shelter(L, fname, n_fields, front_mid=False, benches=((0.55, 1.6),)):
    new_scene()
    mb = MB()
    D0, D1 = -0.75, 0.75      # Dach in y
    YB = -0.66                # Rückwand (Pfostenmitte)
    YF = 0.47                 # Frontpfosten
    ZR0, ZR1 = 2.40, 2.50     # Dachrand
    PW, PD = 0.06, 0.08       # Pfosten 60 x 80 mm
    xs = [-L / 2 + 0.05 + (L - 0.10) * i / n_fields for i in range(n_fields + 1)]
    # Pfosten
    for x in xs:
        bx(mb, (x, YB, ZR0 / 2), (PW, PD, ZR0), "StopSteel", skip=("-z", "+z"))
    fxs = [xs[0], xs[-1]] + ([0.0] if front_mid else [])
    for x in fxs:
        bx(mb, (x, YF, ZR0 / 2), (PW, PD, ZR0), "StopSteel", skip=("-z", "+z"))
    # Dachrand (Stirnband 100 mm) und Querträger
    t = 0.06
    box(mb, (-L / 2, D1 - t, ZR0), (L / 2, D1, ZR1), "StopSteel")
    box(mb, (-L / 2, D0, ZR0), (L / 2, D0 + t, ZR1), "StopSteel")
    box(mb, (-L / 2, D0 + t, ZR0), (-L / 2 + t, D1 - t, ZR1), "StopSteel")
    box(mb, (L / 2 - t, D0 + t, ZR0), (L / 2, D1 - t, ZR1), "StopSteel")
    for x in xs[1:-1]:
        box(mb, (x - 0.025, D0 + t, ZR0 + 0.02), (x + 0.025, D1 - t, ZR0 + 0.07), "StopSteel")
    # Glasdach
    for zz, sd in ((ZR0 + 0.075, 1),):
        mb.poly([(-L / 2 + t, D0 + t, zz), (L / 2 - t, D0 + t, zz), (L / 2 - t, D1 - t, zz), (-L / 2 + t, D1 - t, zz)],
                "StopGlass", outward=(0, 0, 1))
    # LED-Leiste unter dem vorderen Dachrand
    box(mb, (-L / 2 + t, D1 - t - 0.07, ZR0 - 0.03), (L / 2 - t, D1 - t, ZR0), "StopSteel")
    zl = ZR0 - 0.0305
    mb.poly([(-L / 2 + 0.3, D1 - t - 0.06, zl), (L / 2 - 0.3, D1 - t - 0.06, zl),
             (L / 2 - 0.3, D1 - t - 0.01, zl), (-L / 2 + 0.3, D1 - t - 0.01, zl)],
            "ShelterLightEmit", outward=(0, 0, -1))
    # Rückwand: Glasfelder, Riegel bei 1,05 m, Kopfriegel, Glashalter
    GZ0, GZ1 = 0.10, 2.30
    for i in range(n_fields):
        x0, x1 = xs[i] + PW / 2 + 0.01, xs[i + 1] - PW / 2 - 0.01
        mb.poly([(x0, YB, GZ0), (x1, YB, GZ0), (x1, YB, GZ1), (x0, YB, GZ1)], "StopGlass", outward=(0, 1, 0))
        for xx in (x0 + 0.15, x1 - 0.15):
            box(mb, (xx - 0.02, YB - 0.015, 0.0), (xx + 0.02, YB + 0.015, GZ0 + 0.03), "StopSteel", skip=("-z",))
    box(mb, (xs[0], YB - 0.02, 1.03), (xs[-1], YB + 0.02, 1.07), "StopSteel")
    box(mb, (xs[0], YB - 0.03, GZ1), (xs[-1], YB + 0.03, ZR0), "StopSteel")
    # Glasseitenwand am -X-Ende
    xw = xs[0]
    mb.poly([(xw, YB + PD / 2 + 0.01, GZ0), (xw, YF - PD / 2 - 0.01, GZ0), (xw, YF - PD / 2 - 0.01, GZ1),
             (xw, YB + PD / 2 + 0.01, GZ1)], "StopGlass", outward=(1, 0, 0))
    box(mb, (xw - 0.02, YB, 1.03), (xw + 0.02, YF, 1.07), "StopSteel")
    box(mb, (xw - 0.03, YB, GZ1), (xw + 0.03, YF, ZR0), "StopSteel")
    # City-Light-Vitrine am anderen Ende (doppelseitig, 4/1-Plakat 1,19 x 1,75)
    VX0, VX1 = L / 2 - 0.24, L / 2 - 0.09
    VY0, VY1 = -0.60, 0.70
    VZ0, VZ1 = 0.12, 2.02
    for fy in (VY0 + 0.15, VY1 - 0.15):
        box(mb, (VX0 + 0.04, fy - 0.03, 0.0), (VX1 - 0.04, fy + 0.03, VZ0), "CityLightFrame", skip=("-z",))
    box(mb, (VX0, VY0, VZ0), (VX1, VY1, VZ1), "CityLightFrame")
    vyc = (VY0 + VY1) / 2
    PWD, PHT = 1.19, 1.75
    py0, py1 = vyc - PWD / 2, vyc + PWD / 2
    pz0 = VZ0 + 0.08
    pz1 = pz0 + PHT
    for side, xx in ((1, VX1 + 0.002), (-1, VX0 - 0.002)):
        def puv(y, z, sd):
            u = (y - py0) / PWD if sd > 0 else (py1 - y) / PWD
            return (u, (z - pz0) / PHT)
        yz_face(mb, xx, [(py0, pz0), (py1, pz0), (py1, pz1), (py0, pz1)], "PosterEmit", side, puv)
        # Glas vor dem Plakat
        yz_face(mb, xx + side * 0.006, [(py0, pz0), (py1, pz0), (py1, pz1), (py0, pz1)], "StopGlass", side)
    # Infovitrine an der Rückwand (innen), im mittleren Feld
    centers = [(xs[i] + xs[i + 1]) / 2 for i in range(n_fields)]
    ix = min(centers, key=lambda c: (abs(c + 0.3), c))
    IW, IH, ID = 0.98, 0.74, 0.05
    iz = 1.50
    iy0 = YB + 0.02
    box(mb, (ix - IW / 2, iy0, iz - IH / 2), (ix + IW / 2, iy0 + ID, iz + IH / 2), "CityLightFrame")
    vw, vh = 0.92, 0.68
    xz_face(mb, iy0 + ID + 0.001, [(ix - vw / 2, iz - vh / 2), (ix + vw / 2, iz - vh / 2), (ix + vw / 2, iz + vh / 2),
                                   (ix - vw / 2, iz + vh / 2)], "InfoBoard", 1, lambda x, z, s: (
        (ix + vw / 2 - x) / vw, (z - (iz - vh / 2)) / vh))
    # Sitzbank(e): Sitzbrett Edelstahl auf zwei Stahlfüßen
    for bxc, bl in benches:
        box(mb, (bxc - bl / 2, -0.55, 0.42), (bxc + bl / 2, -0.23, 0.46), "BenchSeat")
        for lx in (bxc - bl / 2 + 0.2, bxc + bl / 2 - 0.2):
            box(mb, (lx - 0.03, -0.48, 0.0), (lx + 0.03, -0.30, 0.42), "StopSteel", skip=("-z",))
    # Namensblende auf dem Dach, vorn am Glas-Seitenwand-Ende
    NL = 2.0
    nx0 = -L / 2 + 0.10
    nx1 = nx0 + NL
    NY0, NY1 = D1 - 0.09, D1 - 0.01
    NZ0, NZ1 = ZR1, ZR1 + 0.16
    box(mb, (nx0, NY0, NZ0), (nx1, NY1, NZ1), "NameBlende")
    for ex in (nx0 - 0.03, nx1):
        box(mb, (ex, NY0 - 0.005, NZ0), (ex + 0.03, NY1 + 0.005, NZ1 + 0.005), "StopSteel")
    mb.build("Shelter")
    ncx = (nx0 + nx1) / 2
    nzc = (NZ0 + NZ1) / 2
    anchor("Anchor_Name", (ncx, NY1 + 0.002, nzc), (0, 1, 0), None, (NL - 0.10, 0.13),
           "Haltestellenname schwarz, Grotesk, Versalhöhe ≈ 70 mm, linksbündig")
    anchor("Anchor_Name_Back", (ncx, NY0 - 0.002, nzc), (0, -1, 0), None, (NL - 0.10, 0.13),
           "Rückseite (Gehweg)")
    anchor("Anchor_Light", (0.0, 0.0, ZR0 - 0.05), (0, 0, -1), None, None,
           "Lichtquelle der Dach-LED (nachts OmniLight/SpotLight nach unten)")
    for side, nm in ((1, "Anchor_Poster"), (-1, "Anchor_Poster_Back")):
        xx = VX1 + 0.01 if side > 0 else VX0 - 0.01
        anchor(nm, (xx, vyc, (pz0 + pz1) / 2), (side, 0, 0), None, (PWD, PHT),
               "City-Light-Plakat 4/1 (UV 0..1 auf PosterEmit, z. B. Zelle aus posters.png)")
    extra = {
        "notes": "Wall/JCDecaux-Wartehalle Typ W1 (Flachdach-Glashalle): anthrazit #3D4241, Glasdach, "
                 "Glasrückwand mit Riegel bei 1,05 m, offene Front zum Gleis (Godot -Z). Godot -X-Ende: "
                 "Glasseitenwand + gelb-orange Namensblende auf dem Dach; +X-Ende: doppelseitige City-Light-"
                 "Vitrine (PosterEmit, nachts leuchtend). Infovitrine (InfoBoard) innen an der Rückwand, "
                 "Edelstahlsitzbank. ShelterLightEmit = LED-Leiste unter dem Dach.",
        "length": L,
        "fields": n_fields,
        "name_blende": {"width": NL, "height": round(NZ1 - NZ0, 3), "text_area": [NL - 0.10, 0.13]},
        "poster": {"width": PWD, "height": PHT, "uv": "0..1 in Leserichtung je Seite"},
    }
    export(fname, extra)


# =============================================================================================== 5. Schutzgitter
def build_rail():
    new_scene()
    mb = MB()
    SEGL = 2.0
    HX = 0.95                 # Pfostenachse
    H = 1.00
    RT = 0.025                # Rohr Ø 50 mm
    RBD = 0.14                # Biegeradius oben
    path = [(-HX, 0, 0.0), (-HX, 0, H - RBD)]
    for i in range(1, 6):
        a = math.radians(90 * i / 6)
        path.append((-HX + RBD - RBD * math.cos(a), 0, H - RBD + RBD * math.sin(a)))
    path.append((HX - RBD, 0, H))
    for i in range(1, 6):
        a = math.radians(90 * i / 6)
        path.append((HX - RBD + RBD * math.sin(a), 0, H - RBD + RBD * math.cos(a)))
    path.append((HX, 0, 0.0))
    tube(mb, path, RT, "RailSteel", seg=8)
    cyl(mb, (-HX, 0, 0.12), (HX, 0, 0.12), 0.02, "RailSteel", seg=8, caps=False)
    for x in (-HX, HX):
        box(mb, (x - 0.07, -0.07, 0.0), (x + 0.07, 0.07, 0.012), "RailSteel", skip=("-z",))
    # Füllplatte (Blech) mit Haltern
    px0, px1 = -HX + 0.06, HX - 0.06
    pz0, pz1 = 0.18, H - 0.07
    box(mb, (px0, -0.002, pz0), (px1, 0.002, pz1), "RailPanel")
    for x in (px0 + 0.01, px1 - 0.01):
        for z in (pz0 + 0.08, pz1 - 0.08):
            sgn = -1 if x < 0 else 1
            box(mb, (min(x, sgn * (HX - 0.01)), -0.008, z - 0.02), (max(x, sgn * (HX - 0.01)), 0.008, z + 0.02),
                "RailSteel")
    mb.build("Rail")
    extra = {
        "notes": "Schutzgitter-Segment wie an Dresdner Haltestelleninseln (z. B. Julius-Vahlteich-Straße): "
                 "Rundrohrrahmen Ø 50 mm anthrazit mit gebogenen oberen Ecken, graue Blech-Füllplatte, "
                 "Fußplatten. Länge entlang Godot X, im Raster segment_length aneinanderreihen (10 cm Fuge "
                 "zwischen den Rahmen ist Absicht). Symmetrisch, Vorderseite (Fahrbahn) = Godot -Z.",
        "segment_length": SEGL,
        "height": H,
    }
    export("platform_rail.glb", extra)


# =============================================================================================== 6. Abfallbehälter
def build_bin_steel():
    new_scene()
    mb = MB()
    R = 0.175
    seg = 16
    Z0 = 0.04

    def ztop(y):
        return 0.975 - 0.45 * y      # vorn (+Y) niedrig, hinten hoch (≈ 24°)

    # Sockel
    lathe(mb, [(0.0, 0.0), (R - 0.01, 0.0), (R - 0.01, Z0), (0.0, Z0)], "BinBase", seg=seg)
    # Mantel mit schrägem Abschluss; vorderes Segment unterhalb des Deckels = Einwurföffnung (dunkel)
    ring_lo, ring_mid, ring_hi = [], [], []
    for k in range(seg):
        a = 2 * math.pi * (k + 0.5) / seg
        x, y = R * math.cos(a), R * math.sin(a)
        zt = ztop(y)
        ring_lo.append(mb.vert((x, y, Z0)))
        ring_mid.append(mb.vert((x, y, zt - 0.075)))
        ring_hi.append(mb.vert((x, y, zt)))
    for k in range(seg):
        k2 = (k + 1) % seg
        a = 2 * math.pi * (k + 1.0) / seg
        out = Vector((math.cos(a), math.sin(a), 0))
        mb.face([ring_lo[k], ring_lo[k2], ring_mid[k2], ring_mid[k]], "BinSteel", outward=out)
        front = math.sin(a) > 0.55
        mb.face([ring_mid[k], ring_mid[k2], ring_hi[k2], ring_hi[k]], "BinInside" if front else "BinSteel",
                outward=out)
    # Deckel: elliptische Scheibe in der Schrägebene, leicht überstehend
    ring_t, ring_b = [], []
    for k in range(seg):
        a = 2 * math.pi * (k + 0.5) / seg
        x, y = (R + 0.008) * math.cos(a), (R + 0.008) * math.sin(a)
        ring_b.append(mb.vert((x, y, ztop(y) - 0.004)))
        ring_t.append(mb.vert((x, y, ztop(y) + 0.018)))
    for k in range(seg):
        k2 = (k + 1) % seg
        a = 2 * math.pi * (k + 1.0) / seg
        mb.face([ring_b[k], ring_b[k2], ring_t[k2], ring_t[k]], "BinLid", outward=(math.cos(a), math.sin(a), 0))
    mb.face(ring_t, "BinLid", outward=(0, 0.45, 1))
    mb.face(ring_b, "BinLid", outward=(0, -0.45, -1))
    mb.build("Bin", smooth_angle=50.0)
    extra = {"notes": "Edelstahl-Abfallbehälter Ø 0,35 m mit schräg abgeschnittenem Deckel (Tram-Bahnsteige, "
                      "z. B. Walpurgisstraße). Einwurf (dunkel) unter der niedrigen Deckelkante vorn = Godot -Z."}
    export("stop_bin.glb", extra)


def build_bin_city():
    new_scene()
    mb = MB()
    # leicht nach unten verjüngter Korpus
    bw0, bd0, bw1, bd1 = 0.40, 0.30, 0.45, 0.35
    Z0, Z1 = 0.02, 0.86
    lo = [(-bw0 / 2, -bd0 / 2), (bw0 / 2, -bd0 / 2), (bw0 / 2, bd0 / 2), (-bw0 / 2, bd0 / 2)]
    hi = [(-bw1 / 2, -bd1 / 2), (bw1 / 2, -bd1 / 2), (bw1 / 2, bd1 / 2), (-bw1 / 2, bd1 / 2)]
    for i in range(4):
        j = (i + 1) % 4
        pts = [(lo[i][0], lo[i][1], Z0), (lo[j][0], lo[j][1], Z0), (hi[j][0], hi[j][1], Z1), (hi[i][0], hi[i][1], Z1)]
        c = Vector(((lo[i][0] + lo[j][0]) / 2, (lo[i][1] + lo[j][1]) / 2, 0))
        mb.poly(pts, "BinGrey", outward=c)
    mb.poly([(x, y, Z0) for x, y in lo], "BinGrey", outward=(0, 0, -1))
    box(mb, (-bw0 / 2 + 0.03, -bd0 / 2 + 0.03, 0.0), (bw0 / 2 - 0.03, bd0 / 2 - 0.03, Z0), "BinBase", skip=("-z",))
    # Deckel orange mit Einwurfhaube vorn
    box(mb, (-0.25, -0.20, Z1), (0.25, 0.20, Z1 + 0.05), "BinLidOrange")
    box(mb, (-0.17, -0.12, Z1 + 0.05), (0.17, 0.10, Z1 + 0.09), "BinLidOrange")
    xz_face(mb, 0.1005, [(-0.13, Z1 + 0.055), (0.13, Z1 + 0.055), (0.13, Z1 + 0.085), (-0.13, Z1 + 0.085)],
            "BinInside", 1)
    mb.build("Bin", smooth_angle=20.0)
    extra = {"notes": "Abfallbehälter der Stadtreinigung: grauer, nach unten verjüngter Korpus, oranger Deckel "
                      "mit Einwurfhaube vorn (Godot -Z), ≈ 0,45 x 0,35 x 0,95 m (z. B. Fritz-Förster-Platz)."}
    export("stop_bin_city.glb", extra)


# =============================================================================================== Ablauf
build_mast()
build_dfi_small()
build_dfi_large()
build_shelter(4.0, "wall_shelter.glb", 3)
build_shelter(6.0, "wall_shelter_long.glb", 4, front_mid=True, benches=((-1.35, 1.6), (0.95, 1.6)))
build_rail()
build_bin_steel()
build_bin_city()

man = {
    "generator": "tools/blender/stops/build_stops.py (Texturen: make_stop_textures.py)",
    "coordinates": "Godot-Koordinaten in Metern, +Y oben, Vorderseite (Gleis/Fahrbahn) = -Z, Ursprung am "
                   "Fußpunkt. footprint = Bodenprojektion der Bounding-Box. Anker: position = Modellraum, local_position = relativ zum Elternknoten, normal = "
                   "Blickrichtung (lokale +Z des Leerknotens), size = [Breite, Höhe] der Text-/Anzeigefläche.",
    "models": MANIFEST,
}
with open(os.path.join(OUT, "MANIFEST.json"), "w", encoding="utf-8") as fh:
    json.dump(man, fh, ensure_ascii=False, indent=2)
print("[stops] fertig:", OUT)
