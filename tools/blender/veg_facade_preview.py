"""Vorschaubilder für Unterholz- und Fassaden-Modelle (Eevee, headless).

Aufruf:
  flatpak run org.blender.Blender -b --python tools/blender/veg_facade_preview.py -- veg [name ...]
  flatpak run org.blender.Blender -b --python tools/blender/veg_facade_preview.py -- facade [name ...]
  ... -- veg_group     (alle Unterholz-Modelle nebeneinander -> previews/_all.png)

Importiert die exportierte .glb (prüft damit den Export) und rendert zwei Ansichten
nebeneinander nach <ordner>/previews/<name>.png.
"""
from __future__ import annotations

import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veg_facade_lib as L  # noqa: E402

TMP = os.path.join(L.HERE, "_tmp")
os.makedirs(TMP, exist_ok=True)
RES = 560


def new_scene():
    L.reset()
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES
    sc.render.film_transparent = False
    try:
        sc.eevee.taa_render_samples = 48
    except Exception:
        pass
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.55, 0.62, 0.72, 1.0)
    bg.inputs["Strength"].default_value = 0.9
    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = 3.2
    sun.angle = math.radians(2.0)
    so = bpy.data.objects.new("Sun", sun)
    so.rotation_euler = (math.radians(50), math.radians(8), math.radians(-35))
    sc.collection.objects.link(so)
    return sc


def plane(name, size, loc, rot, color, rough=0.9):
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc, rotation=rot)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (size[0], size[1], 1)
    m = L.material(name + "_m", color=color, rough=rough)
    ob.data.materials.append(m)
    return ob


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    obs = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    return obs


def bbox(obs):
    pts = [o.matrix_world @ Vector(c) for o in obs for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx


def camera(sc, target, az, el, dist, lens=50):
    cam = bpy.data.cameras.new("Cam")
    cam.lens = lens
    cam.clip_start = 0.02
    co = bpy.data.objects.new("Cam", cam)
    sc.collection.objects.link(co)
    d = Vector((math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el)))
    co.location = target + d * dist
    direction = target - co.location
    co.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    sc.camera = co
    return co


def render(sc, path):
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def stitch(paths, out):
    imgs = []
    for p in paths:
        im = bpy.data.images.load(p)
        a = np.array(im.pixels[:], dtype=np.float32).reshape(im.size[1], im.size[0], 4)
        imgs.append(a)
        bpy.data.images.remove(im)
    h = max(a.shape[0] for a in imgs)
    full = np.concatenate([a for a in imgs], axis=1)
    img = bpy.data.images.new("stitch", full.shape[1], h, alpha=True)
    img.pixels.foreach_set(full.ravel())
    img.filepath_raw = out
    img.file_format = "PNG"
    img.save()
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass


def views_for(kind, mn, mx):
    c = (mn + mx) * 0.5
    size = (mx - mn).length
    if kind == "veg":
        tgt = Vector((c.x, c.y, mn.z + (mx.z - mn.z) * 0.45))
        return [(tgt, math.radians(-30), math.radians(14), size * 1.55 + 0.3),
                (tgt, math.radians(60), math.radians(42), size * 1.55 + 0.3)]
    # Fassade: Wand bei y=0 (Blender), Teil ragt nach +Y (nach glTF-Import wieder +Y)
    tgt = Vector((c.x, c.y * 0.5, c.z))
    return [(tgt, math.radians(152), math.radians(8), size * 1.5 + 0.6),
            (tgt, math.radians(215), math.radians(-12), size * 1.45 + 0.6)]


def preview(kind, name):
    folder = os.path.join(L.MODELS, "vegetation" if kind == "veg" else "facade")
    sc = new_scene()
    if kind != "veg":
        # Sonne von vorn-oben-links auf die Wand (Licht läuft Richtung -Y)
        bpy.data.objects["Sun"].rotation_euler = (math.radians(-52), math.radians(0), math.radians(-38))
    obs = import_glb(os.path.join(folder, name + ".glb"))
    mn, mx = bbox(obs)
    if kind == "veg":
        plane("Ground", (12, 12), (0, 0, 0), (0, 0, 0), (0.20, 0.16, 0.11, 1))
    else:
        w = max(6.0, (mx.x - mn.x) + 4)
        h = max(5.0, mx.z + 2)
        plane("Wall", (w, h), (0, -0.001, h / 2 - 0.5), (math.radians(-90), 0, 0), (0.70, 0.66, 0.58, 1))
        plane("Ground", (w, 6), (0, 3 - 0.01, mn.z - 0.002 if name.startswith("door") else -0.6),
              (0, 0, 0), (0.35, 0.34, 0.33, 1))
    paths = []
    for i, (tgt, az, el, dist) in enumerate(views_for(kind, mn, mx)):
        camera(sc, tgt, az, el, dist)
        p = os.path.join(TMP, f"{name}_{i}.png")
        render(sc, p)
        paths.append(p)
    os.makedirs(os.path.join(folder, "previews"), exist_ok=True)
    stitch(paths, os.path.join(folder, "previews", name + ".png"))


def group_veg(names):
    sc = new_scene()
    sc.render.resolution_x = 1400
    sc.render.resolution_y = 600
    folder = os.path.join(L.MODELS, "vegetation")
    x = 0.0
    allobs = []
    for n in names:
        obs = import_glb(os.path.join(folder, n + ".glb"))
        mn, mx = bbox(obs)
        dx = x - mn.x
        for o in obs:
            o.location.x += dx
        x += (mx.x - mn.x) + 0.25
        allobs += obs
    for o in allobs:
        o.location.x -= x / 2
    plane("Ground", (40, 12), (0, 0, 0), (0, 0, 0), (0.20, 0.16, 0.11, 1))
    # horizontaler Bildwinkel bei 40 mm / 36 mm Sensor: 48.5 Grad
    camera(sc, Vector((0, 0, 0.9)), math.radians(0), math.radians(9), x * 0.5 / math.tan(math.radians(24.2)) * 1.08, lens=40)
    render(sc, os.path.join(folder, "previews", "_all.png"))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    kind = argv[0]
    names = argv[1:]
    folder = os.path.join(L.MODELS, "vegetation" if kind.startswith("veg") else "facade")
    if not names:
        names = sorted(f[:-4] for f in os.listdir(folder) if f.endswith(".glb"))
    if kind == "veg_group":
        group_veg(names)
        return
    for n in names:
        preview(kind, n)
        print("[preview]", n)


if __name__ == "__main__":
    main()
