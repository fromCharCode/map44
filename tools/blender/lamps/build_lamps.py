"""Dresdner Straßenleuchten (prozedural):
  streetlamp_gas.glb   Gaslaterne (Gründerzeit-/Villenviertel: Striesen, Blasewitz, Loschwitz …): gusseiserner Mast
                       mit Sockel, Leiterstütze, vierseitige Laterne mit Dach und Spitze; Laternenhöhe ~3,6 m
  streetlamp_whip.glb  DDR-Peitschenmast (Plattenbaugebiete, Ausfallstraßen der 70er/80er): konischer Stahlmast 9 m,
                       oben zum Fahrbahnrand gebogen, flache Leuchte am Ende (Kopf bei z = -1.9)
Materialnamen wie die vorhandenen Leuchten: LampEmit (nachts leuchtend), dazu LampMetal/Steel.
Aufruf: flatpak run --filesystem=host org.blender.Blender -b --python build_lamps.py -- <ausgabeordner>"""
import bpy, bmesh, sys, math
from mathutils import Vector, Matrix

out = sys.argv[sys.argv.index("--") + 1]


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, col, metal=0.0, rough=0.6, emit=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*col, 1.0)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1.0)
        b.inputs["Emission Strength"].default_value = 1.0
    return m


def lathe(bm, prof, seg=12, z0=0.0):
    """Rotationskörper aus Profil [(r, h), ...] (h nach oben)."""
    rings = []
    for r, h in prof:
        ring = []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            ring.append(bm.verts.new((r * math.cos(a), r * math.sin(a), h + z0)))
        rings.append(ring)
    for k in range(len(rings) - 1):
        for i in range(seg):
            j = (i + 1) % seg
            bm.faces.new((rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]))
    # Deckel
    if prof[-1][0] > 0.001:
        bm.faces.new(list(reversed(rings[-1])) if False else rings[-1])
    return rings


def obj_from_bm(bm, name, material):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    me.materials.append(material)
    for p in me.polygons:
        p.use_smooth = True
    return ob


def box(bm, cx, cy, cz, sx, sy, sz):
    r = bmesh.ops.create_cube(bm, size=1.0)
    for v in r["verts"]:
        v.co = Vector((cx + v.co.x * sx, cy + v.co.y * sy, cz + v.co.z * sz))


def export(path):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_yup=True, export_apply=True)


# ---------------------------------------------------------------------------- Gaslaterne
reset()
iron = mat("LampMetal", (0.05, 0.075, 0.065), metal=0.6, rough=0.45)
glow = mat("LampEmit", (0.95, 0.88, 0.7), rough=0.2, emit=(1.0, 0.82, 0.55))
bm = bmesh.new()
# Sockel, kannelierter Schaft (als feines Profil), Kapitell
prof = [(0.17, 0.0), (0.17, 0.12), (0.13, 0.16), (0.13, 0.42), (0.10, 0.48), (0.075, 0.55), (0.065, 2.6),
        (0.075, 2.66), (0.09, 2.72), (0.06, 2.78), (0.045, 3.05), (0.07, 3.12), (0.0, 3.12)]
lathe(bm, prof, seg=10)
# Leiterstütze (Querstab)
box(bm, 0.0, 0.0, 2.92, 0.62, 0.035, 0.035)
obj_from_bm(bm, "Pole", iron)
# Laterne: vierseitig, unten schmal, oben breit; Glasflächen leuchten
bm = bmesh.new()
z0, z1 = 3.14, 3.62
rb, rt = 0.13, 0.22
corners_b = [Vector((rb * math.cos(a), rb * math.sin(a), z0)) for a in (math.pi / 4, 3 * math.pi / 4, 5 * math.pi / 4, 7 * math.pi / 4)]
corners_t = [Vector((rt * math.cos(a), rt * math.sin(a), z1)) for a in (math.pi / 4, 3 * math.pi / 4, 5 * math.pi / 4, 7 * math.pi / 4)]
vb = [bm.verts.new(c) for c in corners_b]
vt = [bm.verts.new(c) for c in corners_t]
for i in range(4):
    j = (i + 1) % 4
    bm.faces.new((vb[i], vb[j], vt[j], vt[i]))
bm.faces.new(list(reversed(vb)))
obj_from_bm(bm, "Lantern", glow)
# Rahmen, Dach (Pyramide) und Spitze
bm = bmesh.new()
for i in range(4):
    a = math.pi / 4 + i * math.pi / 2
    b0 = Vector((rb * math.cos(a), rb * math.sin(a), z0))
    t0 = Vector((rt * math.cos(a), rt * math.sin(a), z1))
    m = (b0 + t0) * 0.5
    d = (t0 - b0)
    L = d.length
    r = bmesh.ops.create_cube(bm, size=1.0)
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    for v in r["verts"]:
        v.co = m + (rot @ Vector((v.co.x * 0.03, v.co.y * 0.03, v.co.z * L)))
prof_roof = [(0.27, 3.62), (0.27, 3.66), (0.0, 3.86)]
lathe(bm, prof_roof, seg=4, z0=0.0)
lathe(bm, [(0.025, 3.84), (0.035, 3.9), (0.0, 3.98)], seg=8)
box(bm, 0.0, 0.0, 3.13, 0.3, 0.3, 0.03)
obj_from_bm(bm, "LanternFrame", iron)
export(out + "/streetlamp_gas.glb")

# ---------------------------------------------------------------------------- Peitschenmast
reset()
steel = mat("Steel", (0.52, 0.53, 0.52), metal=0.7, rough=0.5)
glow = mat("LampEmit", (0.9, 0.9, 0.85), rough=0.3, emit=(1.0, 0.85, 0.6))
dark = mat("LampMetal", (0.18, 0.19, 0.2), metal=0.5, rough=0.5)
bm = bmesh.new()
# gerader konischer Teil
H = 7.6
seg = 8
pts = []
for k in range(9):
    h = H * k / 8
    pts.append((Vector((0, 0, h)), 0.11 - 0.05 * k / 8, Vector((0, 0, 1))))
# Bogen (Radius 1.4 m) zur Fahrbahn: Blender +Y wird beim glTF-Export zu Godot -Z (Ausleger-Konvention -Z)
R = 1.4
for k in range(1, 13):
    a = (math.pi / 2) * k / 12
    c = Vector((0, R * (1 - math.cos(a)), H + R * math.sin(a)))
    t = Vector((0, math.sin(a), math.cos(a)))
    pts.append((c, 0.06 - 0.015 * k / 12, t))
# Ausleger-Ende horizontal
end = pts[-1][0]
for k in range(1, 4):
    pts.append((end + Vector((0, 0.18 * k, 0)), 0.045, Vector((0, 1, 0))))
rings = []
for c, r, t in pts:
    rot = Vector((0, 0, 1)).rotation_difference(t).to_matrix()
    ring = [bm.verts.new(c + rot @ Vector((r * math.cos(2 * math.pi * i / seg), r * math.sin(2 * math.pi * i / seg), 0))) for i in range(seg)]
    rings.append(ring)
for k in range(len(rings) - 1):
    for i in range(seg):
        j = (i + 1) % seg
        bm.faces.new((rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]))
bm.faces.new(rings[-1])
obj_from_bm(bm, "Mast", steel)
head_y = end.y + 0.54 + 0.35
head_z = end.z - 0.02
bm = bmesh.new()
box(bm, 0.0, head_y, head_z + 0.06, 0.34, 0.75, 0.14)
obj_from_bm(bm, "Housing", dark)
bm = bmesh.new()
box(bm, 0.0, head_y, head_z - 0.02, 0.28, 0.66, 0.03)
obj_from_bm(bm, "Lens", glow)
print("KOPF Peitschenmast (Godot):", 0.0, round(head_z - 0.03, 2), round(-head_y, 2))
export(out + "/streetlamp_whip.glb")
print("FERTIG")
