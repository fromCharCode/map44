import bpy, sys
src = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
from collections import Counter
for ob in bpy.data.objects:
    if ob.type != "MESH": continue
    me = ob.data
    c = Counter(me.materials[p.material_index].name for p in me.polygons)
    print("MATS", ob.name, dict(c))
