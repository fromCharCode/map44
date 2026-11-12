"""Vorschaubilder der Busse (Eevee, headless) -> godot/assets/models/cars/previews/<bus>_*.png

  flatpak run org.blender.Blender -b --python tools/blender/bus_preview.py [-- solo articulated]

Importiert die exportierte .glb. Ansicht "open": Türen per open_offset aus MANIFEST.json geöffnet,
Gelenkbus um 28° geknickt (Rear) und Faltenbalg um den halben Winkel gedreht.
"""
from __future__ import annotations

import json
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veg_facade_lib as L  # noqa: E402

CARS = os.path.join(L.MODELS, "cars")
PREV = os.path.join(CARS, "previews")


def scene():
    L.reset()
    L._img_cache.clear()
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    try:
        sc.eevee.taa_render_samples = 48
    except Exception:
        pass
    sc.view_settings.view_transform = "AgX"
    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.55, 0.62, 0.72, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = 3.5
    sun.angle = math.radians(1.5)
    so = bpy.data.objects.new("Sun", sun)
    so.rotation_euler = (math.radians(48), 0, math.radians(140))
    sc.collection.objects.link(so)
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 0, 0))
    g = bpy.context.active_object
    g.data.materials.append(L.material("Ground", color=(0.30, 0.30, 0.31, 1), rough=0.9))
    return sc


def cam(sc, target, d, dist, lens=40):
    c = bpy.data.cameras.new("Cam")
    c.lens = lens
    co = bpy.data.objects.new("Cam", c)
    sc.collection.objects.link(co)
    d = Vector(d).normalized()
    co.location = target + d * dist
    co.rotation_euler = (target - co.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = co
    return co


def render(sc, path):
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def preview(which):
    fn = "bus_%s.glb" % which
    man = json.load(open(os.path.join(CARS, "MANIFEST.json")))[fn]
    length = man["length"]
    views = [("front34", (0.62, 0.78, 0.22), 1.02, False, 0), ("rear34", (-0.62, -0.78, 0.22), 1.02, False, 0),
             ("side", (1.0, 0.0, 0.06), 1.0, False, 0), ("open", (0.70, 0.30, 0.80), 1.05, True, 28)]
    for name, d, f, opened, bend in views:
        sc = scene()
        bpy.ops.import_scene.gltf(filepath=os.path.join(CARS, fn))
        obs = {o.name: o for o in bpy.data.objects}
        if opened:
            for door in man["doors"]:
                for leaf, info in door["leaves"].items():
                    o = obs[leaf]
                    dx, dy, dz = info["open_offset"]
                    o.location = o.location + Vector((dx, -dz, dy))
            if bend and "Rear" in obs:
                for nm, ang in (("Rear", bend), ("Bellows", bend / 2)):
                    o = obs[nm]
                    o.rotation_mode = "XYZ"
                    o.rotation_euler = (o.rotation_euler.x, o.rotation_euler.y, math.radians(ang))
        bpy.context.view_layer.update()
        zc = -(man["bbox_min"][2] + man["bbox_max"][2]) / 2       # Godot z -> Blender y
        tgt = Vector((0, zc, 1.3))
        cam(sc, tgt, d, length * f + 3.0)
        render(sc, os.path.join(PREV, "bus_%s_%s.png" % (which, name)))
        print("[preview]", which, name)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    os.makedirs(PREV, exist_ok=True)
    for w in (argv or ["solo", "articulated"]):
        preview(w)


if __name__ == "__main__":
    main()
