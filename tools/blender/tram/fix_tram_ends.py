"""Schließt die offenen Führerstand-Enden der Straßenbahn (tram_sections.glb):
Frontscheibe (Material Glass) und Frontmaske (PlasticBlack) in Section_0 (vorn) und Section_4 (hinten).
Die Umrisse werden an einer verschmolzenen Kopie ermittelt; die Deckel kommen als eigene neue Geometrie hinzu
(das Original-Mesh mit seinen Nähten/Normalen bleibt unverändert).
Aufruf: flatpak run --filesystem=host org.blender.Blender -b --python fix_tram_ends.py -- <in.glb> <out.glb>"""
import bpy, bmesh, sys
from collections import defaultdict
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
src, dst = args[0], args[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)


def outlines(me):
    """Geordnete Umrisse (Listen von Positionen) aller Randschleifen einer verschmolzenen Kopie."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
    bnd = [e for e in bm.edges if len(e.link_faces) == 1]
    adj = defaultdict(list)
    for e in bnd:
        a, b = e.verts
        adj[a].append(b)
        adj[b].append(a)
    seen = set()
    res = []
    for v0 in list(adj):
        if v0 in seen:
            continue
        path = [v0]
        seen.add(v0)
        prev, cur = None, v0
        while True:
            nxt = [w for w in adj[cur] if w is not prev and w not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            seen.add(cur)
            path.append(cur)
        if len(path) >= 3:
            res.append([v.co.copy() for v in path])
    center = sum((v.co for v in bm.verts), Vector()) / len(bm.verts)
    bm.free()
    return res, center


for name, end_sign in (("Section_0_mesh", 1.0), ("Section_4_mesh", -1.0)):
    ob = bpy.data.objects[name]
    me = ob.data
    mats = [m.name for m in me.materials]
    gi = mats.index("Glass")
    bi = mats.index("PlasticBlack") if "PlasticBlack" in mats else gi
    outs, center = outlines(me)
    bm = bmesh.new()
    bm.from_mesh(me)
    filled = 0
    for pts in outs:
        xs = [p.x for p in pts]
        ys = [p.y for p in pts]
        zs = [p.z for p in pts]
        if max(xs) - min(xs) < 1.2 or len(pts) < 8:
            continue
        ymid = (max(ys) + min(ys)) * 0.5
        if ymid * end_sign < 3.7:
            continue                       # Wagenübergänge (|y| 3.55/4.30 auf der Kupplungsseite) offen lassen
        sloped = (max(ys) - min(ys)) > 0.3
        vs = [bm.verts.new(p) for p in pts]
        try:
            f = bm.faces.new(vs)
        except ValueError as ex:
            print("FEHLER", name, ex)
            continue
        # vorn liegt die Maske vor den Scheinwerfern -> ebenfalls Glas (Lampen leuchten durch)
        f.material_index = gi if (sloped or end_sign > 0) else bi
        bm.normal_update()
        out = f.calc_center_median() - center
        if not sloped:
            out.z = 0.0
        if f.normal.dot(out) < 0.0:
            f.normal_flip()
        f.smooth = False
        res = bmesh.ops.triangulate(bm, faces=[f])
        # UVs der neuen Flächen: einfache Projektion (Glas/Maske sind einfarbig)
        uv = bm.loops.layers.uv.active
        if uv is not None:
            for tf in res["faces"]:
                for lp in tf.loops:
                    lp[uv].uv = (lp.vert.co.x * 0.2, lp.vert.co.z * 0.2)
        filled += 1
        print("gefüllt", name, "Glas" if sloped else "Maske", "Punkte", len(pts), "y %.2f..%.2f z %.2f..%.2f" % (min(ys), max(ys), min(zs), max(zs)))
    bm.to_mesh(me)
    me.update()
    bm.free()
    print(name, "Öffnungen geschlossen:", filled)

bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", export_apply=False, export_yup=True)
print("EXPORT", dst)
