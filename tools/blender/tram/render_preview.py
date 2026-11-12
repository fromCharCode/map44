"""Vorschau-Renderings eines Bahn-GLB (Workbench): render_preview.py -- <in.glb> <out_prefix>"""
import bpy, sys, math
from mathutils import Vector
a = sys.argv[sys.argv.index("--") + 1:]
src, pre = a[0], a[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"
sc.display.shading.color_type = "MATERIAL"
sc.display.shading.show_specular_highlight = True
sc.display.shading.show_cavity = True
sc.render.resolution_x, sc.render.resolution_y = 1600, 900
sc.world = bpy.data.worlds.new("W")
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
sc.collection.objects.link(cam)
sc.camera = cam
L = float(a[2]) if len(a) > 2 else 45.0
views = {
    "front34": ((6.0, 8.0, 2.2), (0.0, -4.0, 1.6), 50),
    "front": ((0.0, 9.0, 1.9), (0.0, 0.0, 1.8), 40),
    "side": ((24.0, -L / 2, 2.0), (0.0, -L / 2, 1.6), 45),
    "sideL": ((-10.0, -6.0, 2.0), (0.0, -6.0, 1.6), 50),
    "rear34": ((-6.0, -L - 8.0, 2.4), (0.0, -L + 4.0, 1.6), 50),
    "roof": ((8.0, -6.0, 8.0), (0.0, -12.0, 3.0), 45),
}
for nm, (p, t, fov) in views.items():
    cam.location = p
    d = Vector(t) - Vector(p)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    cam.data.angle = math.radians(fov)
    sc.render.filepath = f"{pre}_{nm}.png"
    bpy.ops.render.render(write_still=True)
