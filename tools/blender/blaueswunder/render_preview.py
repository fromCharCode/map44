"""Workbench-Vorschau des Blauen Wunders: render_preview.py -- <in.glb> <out_prefix> [ansicht,...]
Fügt nur für die Vorschau ein graues Fahrbahndeck (wie LoD2-Deck im Spiel, 1 m dick) und eine Wasser-/Bodenfläche hinzu.
Blender-Achsen: X quer (+X oberstrom), Y längs (+Y Loschwitz), Z oben."""
import bpy, sys, math
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
src, pre = a[0], a[1]
only = set(a[2].split(",")) if len(a) > 2 else None
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
for m in bpy.data.materials:
    try:
        b = m.node_tree.nodes.get("Principled BSDF")
        if b:
            c = b.inputs["Base Color"].default_value
            al = b.inputs["Alpha"].default_value
            m.diffuse_color = (c[0], c[1], c[2], al)
    except Exception:
        pass


def slab(name, mn, mx, col):
    me = bpy.data.meshes.new(name)
    x0, y0, z0 = mn
    x1, y1, z1 = mx
    vs = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    fs = [[3, 2, 1, 0], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    me.from_pydata(vs, [], fs)
    mt = bpy.data.materials.new(name)
    mt.diffuse_color = col
    me.materials.append(mt)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)


slab("Deck", (-11.0, -150, -1.0), (11.0, 150, 0.0), (0.33, 0.33, 0.34, 1))
slab("Ground", (-400, -400, -11.5), (400, 400, -11.4), (0.25, 0.32, 0.30, 1))

sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"
sc.display.shading.color_type = "MATERIAL"
sc.display.shading.show_specular_highlight = True
sc.display.shading.show_cavity = True
sc.display.shading.show_shadows = True
sc.display.shading.background_type = "VIEWPORT"
sc.display.shading.background_color = (0.62, 0.72, 0.82)
sc.render.resolution_x, sc.render.resolution_y = 1600, 900
sc.world = bpy.data.worlds.new("W")
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
sc.collection.objects.link(cam)
sc.camera = cam
views = {
    # name: (pos, target, fov, ortho_scale or None)
    "elev": ((-400.0, 0.0, 12.0), (0.0, 0.0, 12.0), 0, 290.0),
    "aerial": ((-170.0, -150.0, 75.0), (0.0, 10.0, 5.0), 50, None),
    "pylon": ((-75.0, -20.0, 8.0), (0.0, -66.0, 12.0), 40, None),
    "endon": ((0.0, -185.0, 2.0), (0.0, -73.0, 11.0), 45, None),
    "road": ((-2.0, -120.0, 1.6), (0.0, -60.0, 4.0), 70, None),
    "walk": ((-8.6, -112.0, 1.8), (-7.0, -70.0, 6.0), 70, None),
    "hinge": ((-9.0, -6.0, 1.9), (-6.2, 0.0, 1.5), 60, None),
    "under": ((-30.0, -95.0, -9.0), (0.0, -73.0, -1.0), 55, None),
    "top": ((0.0, 0.0, 400.0), (0.0, 0.0, 0.0), 0, 290.0),
}
for nm, (p, t, fov, ortho) in views.items():
    if only and nm not in only:
        continue
    cam.location = p
    d = Vector(t) - Vector(p)
    up = "Y" if abs(d.normalized().z) < 0.99 else "X"
    cam.rotation_euler = d.to_track_quat("-Z", up).to_euler()
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho
    else:
        cam.data.type = "PERSP"
        cam.data.angle = math.radians(fov)
    cam.data.clip_end = 2000
    sc.render.filepath = f"{pre}_{nm}.png"
    bpy.ops.render.render(write_still=True)
