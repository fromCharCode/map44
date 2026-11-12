import bpy, bmesh, sys
from collections import defaultdict
src = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
for ob in bpy.context.scene.objects:
    print("OBJ", ob.name, ob.type, tuple(round(v, 3) for v in ob.location), ob.parent.name if ob.parent else "-")
    if ob.type != "MESH":
        continue
    me = ob.data
    print("   mats:", [m.name if m else None for m in me.materials], "verts", len(me.vertices), "faces", len(me.polygons))
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
    bnd = [e for e in bm.edges if len(e.link_faces) == 1]
    zs = [v.co.y for v in bm.verts]  # glTF Y-up -> Blender Z-up: Spiel-z = -Blender-y
    print("   Randkanten:", len(bnd), "y-Bereich", round(min(zs), 3), round(max(zs), 3))
    # Randschleifen
    adj = defaultdict(list)
    for e in bnd:
        a, b = e.verts
        adj[a].append(b); adj[b].append(a)
    seen = set(); loops = []
    for v in list(adj):
        if v in seen: continue
        comp = []; st = [v]
        while st:
            x = st.pop()
            if x in seen: continue
            seen.add(x); comp.append(x); st.extend(adj[x])
        loops.append(comp)
    for comp in sorted(loops, key=len, reverse=True)[:8]:
        xs = [v.co.x for v in comp]; ys = [v.co.y for v in comp]; zz = [v.co.z for v in comp]
        print("     Schleife %d Punkte: x %.2f..%.2f  y %.2f..%.2f  z %.2f..%.2f" % (len(comp), min(xs), max(xs), min(ys), max(ys), min(zz), max(zz)))
    bm.free()
