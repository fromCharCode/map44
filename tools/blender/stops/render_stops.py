"""Workbench-Vorschauen der Haltestellenmodelle (importiert die exportierten GLBs, prüft so auch Achsen/Anker).

Aufruf: flatpak run --filesystem=host org.blender.Blender -b --python <abs>/render_stops.py [-- <name> ...]
Ausgabe: tools/blender/stops/out/<modell>_<ansicht>.png und ensemble_*.png (Mast mit 3 Linienzeilen + LED-Modul
nach den Stapelregeln aus MANIFEST.json, Wartehalle, Tafel, Gitter, Behälter auf einer Bahnsteigfläche).
"""
import bpy, sys, os, math, json
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SRC = os.path.join(ROOT, "godot", "assets", "models", "stops")
OUT = os.path.join(HERE, "out")
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
MAN = json.load(open(os.path.join(SRC, "MANIFEST.json"), encoding="utf-8"))["models"]


def setup(res=(1200, 900)):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.color_type = "TEXTURE"
    sh.show_specular_highlight = True
    sh.show_cavity = True
    sh.cavity_type = "WORLD"
    sh.show_shadows = True
    sh.shadow_intensity = 0.35
    sc.display.shadow_focus = 0.2
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.view_settings.view_transform = "Standard"
    sc.render.film_transparent = False
    sc.world = bpy.data.worlds.new("W")
    sc.world.color = (0.62, 0.68, 0.74)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    return sc, cam


def fix_colors():
    """Workbench zeigt diffuse_color; aus Principled-Basisfarbe übernehmen (Alpha für Glas)."""
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        b = m.node_tree.nodes.get("Principled BSDF")
        if not b:
            continue
        c = b.inputs["Base Color"].default_value
        a = b.inputs["Alpha"].default_value
        m.diffuse_color = (c[0], c[1], c[2], a)
        if a < 0.99:
            m.diffuse_color = (c[0], c[1], c[2], 0.25)
            try:
                m.surface_render_method = "BLENDED"
            except Exception:
                pass


def imp(name, loc=(0, 0, 0), rot_z=0.0):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(SRC, name))
    new = [o for o in bpy.data.objects if o not in before]
    roots = [o for o in new if o.parent is None]
    for o in roots:
        o.location = Vector(o.location) + Vector(loc)
        o.rotation_mode = "XYZ"
        o.rotation_euler.z += rot_z
    return {o.name: o for o in new}


def ground(size=12.0, col=(0.55, 0.55, 0.53)):
    me = bpy.data.meshes.new("Ground")
    s = size / 2
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    m = bpy.data.materials.new("GroundMat")
    m.diffuse_color = (*col, 1.0)
    me.materials.append(m)
    ob = bpy.data.objects.new("Ground", me)
    bpy.context.collection.objects.link(ob)


def shot(cam, name, pos, tgt, lens=50.0, ortho=None, light="STUDIO"):
    bpy.context.scene.display.shading.light = light
    cam.location = pos
    d = Vector(tgt) - Vector(pos)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho
    else:
        cam.data.type = "PERSP"
        cam.data.lens = lens
    sc = bpy.context.scene
    sc.render.filepath = os.path.join(OUT, name + ".png")
    bpy.ops.render.render(write_still=True)
    print("[render]", name)


def want(n):
    return not ARGS or n in ARGS


def stack_sign(objs, n_rows, dfi_objs=None):
    """Stapelregeln aus dem Manifest anwenden (in Blender-Koordinaten: Godot y = Blender z)."""
    sg = MAN["dvb_mast.glb"]["sign"]
    row = objs["LineRow"]
    top = sg["stack_top_y"]
    for i in range(1, n_rows):
        cp = row.copy()
        cp.data = row.data
        bpy.context.collection.objects.link(cp)
        cp.location.z = top - i * sg["row_pitch"]
        for ch in row.children:
            c2 = ch.copy()
            bpy.context.collection.objects.link(c2)
            c2.parent = cp
    extra = 0.0
    if dfi_objs:
        dfi_objs["DfiModule"].location.z = top - n_rows * sg["row_pitch"]
        extra = sg["dfi_module_height"]
    objs["Footer"].location.z = top - n_rows * sg["row_pitch"] - extra


os.makedirs(OUT, exist_ok=True)

if want("mast"):
    sc, cam = setup((900, 1200))
    o = imp("dvb_mast.glb")
    d = imp("dfi_small.glb")
    stack_sign(o, 3, d)
    t2 = o["Timetable"].copy()
    bpy.context.collection.objects.link(t2)
    t2.location.z -= MAN["dvb_mast.glb"]["timetable"]["stack_pitch"]
    fix_colors()
    ground(6)
    shot(cam, "mast_front", (5.8, -0.35, 1.85), (0, -0.35, 1.8), lens=50)
    shot(cam, "mast_34", (3.4, 3.0, 2.2), (0, -0.35, 2.0), lens=40)
    shot(cam, "mast_sign_close", (2.4, -0.40, 2.75), (0, -0.40, 2.75), lens=50, light="FLAT")
    shot(cam, "mast_sign_back", (-2.4, -0.40, 2.75), (0, -0.40, 2.75), lens=50, light="FLAT")

if want("mast1"):
    sc, cam = setup((900, 1200))
    o = imp("dvb_mast.glb")
    fix_colors()
    ground(6)
    shot(cam, "mast_default_1row", (3.4, 1.6, 2.2), (0, -0.4, 2.0), lens=40)

if want("shelter"):
    sc, cam = setup()
    imp("wall_shelter.glb")
    fix_colors()
    ground(14)
    shot(cam, "shelter_front34", (-3.2, 6.0, 2.0), (0, 0, 1.25), lens=35)
    shot(cam, "shelter_front", (0, 7.5, 1.5), (0, 0, 1.3), lens=35)
    shot(cam, "shelter_back34", (4.0, -5.5, 2.4), (0, 0, 1.2), lens=35)
    shot(cam, "shelter_inside", (-1.2, 1.6, 1.6), (0.6, -0.6, 1.2), lens=24)
    shot(cam, "shelter_citylight", (5.5, 2.5, 1.4), (1.9, 0.0, 1.1), lens=35, light="FLAT")

if want("shelter_long"):
    sc, cam = setup()
    imp("wall_shelter_long.glb")
    fix_colors()
    ground(16)
    shot(cam, "shelter_long_front34", (-4.0, 8.0, 2.2), (0, 0, 1.25), lens=35)

if want("dfi"):
    sc, cam = setup()
    imp("dfi_large.glb")
    fix_colors()
    ground(8)
    shot(cam, "dfi_large_side", (-4.5, -0.9, 2.4), (0, -0.9, 2.6), lens=45)
    shot(cam, "dfi_large_34", (3.2, 2.6, 2.0), (0, -0.8, 2.4), lens=40)

if want("small"):
    sc, cam = setup((1200, 800))
    for i, (f, x) in enumerate((("platform_rail.glb", 0.0), ("platform_rail.glb", 2.0), ("stop_bin.glb", 3.6),
                                ("stop_bin_city.glb", 4.4))):
        imp(f, (x, 0, 0))
    fix_colors()
    ground(12)
    shot(cam, "rail_bins_front34", (1.0, 5.0, 1.6), (2.2, 0, 0.6), lens=35)
    shot(cam, "rail_bins_back34", (4.5, -3.2, 1.4), (2.6, 0, 0.6), lens=35)

if want("ensemble"):
    sc, cam = setup((1600, 900))
    # Bahnsteig: Kante bei Blender y = +1.5 (Gleis davor), Mast 0.6 m hinter der Kante
    o = imp("dvb_mast.glb", (-4.0, 0.9, 0))
    stack_sign(o, 3)
    imp("wall_shelter.glb", (0.5, 0.0, 0))
    imp("dfi_large.glb", (4.2, 1.2, 0))
    for k in range(4):
        imp("platform_rail.glb", (-3.0 + 2.0 * k, -1.3, 0))
    imp("stop_bin.glb", (-2.6, 0.6, 0))
    fix_colors()
    ground(20)
    shot(cam, "ensemble_track", (-1.0, 9.0, 1.8), (0.0, 0.0, 1.5), lens=28)
    shot(cam, "ensemble_along", (-9.5, 2.6, 1.7), (2.0, 0.2, 1.8), lens=35)
