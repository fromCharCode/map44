import bpy, sys
from mathutils.bvhtree import BVHTree
from mathutils import Vector
src = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
dg = bpy.context.evaluated_depsgraph_get()
body = bpy.data.objects["Body_0"]; det = bpy.data.objects["Detail_0"]
bvh = BVHTree.FromObject(body, dg)
me = det.data
mw = det.matrix_world; bi = body.matrix_world.inverted()
neg = []
yt = max(v.co.y for v in body.data.vertices)
for p in me.polygons:
    c = bi @ (mw @ p.center)
    mat = me.materials[p.material_index].name
    loc, nrm, idx, d = bvh.find_nearest(c)
    if loc is None: continue
    sd = (c - loc).dot(nrm)
    if sd < -0.001 and d < 0.3 and c.y > 5.0 and c.z > 0.6:
        neg.append((round(sd,4), mat, tuple(round(x,2) for x in c), tuple(round(x,2) for x in (bi @ (mw @ p.normal) - bi @ (mw @ Vector())))))
print("Flächen gesamt", len(me.polygons), "unter/auf Körper", len(neg))
for n in neg[:25]: print(n)
# Normale der Detailflächen vs. Körpernormale
flip = 0
for p in me.polygons:
    c = bi @ (mw @ p.center)
    loc, nrm, idx, d = bvh.find_nearest(c)
    if loc is not None and d < 0.05 and (det.matrix_world.to_3x3() @ p.normal).dot(body.matrix_world.to_3x3() @ nrm) < 0:
        flip += 1
print("Detailflächen mit umgekehrter Normale:", flip)
