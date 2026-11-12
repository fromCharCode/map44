class_name Probe
extends RefCounted
## Entwickler-Werkzeug: findet alle Geometrie in der Nähe eines Punktes (--probe=x,y,z[,r]).
## Gibt Knotenpfad, Vertexanzahl in Reichweite und Material aus. Nur mit Fenster (Dummy-Renderer hält keine Arrays).


static func run(root: Node, spec: String) -> void:
	var v := spec.split(",")
	var p := Vector3(float(v[0]), float(v[1]), float(v[2]))
	var r := float(v[3]) if v.size() > 3 else 0.8
	print("PROBE bei ", p, " r=", r)
	_walk(root, p, r)
	print("PROBE ende")


static func _walk(n: Node, p: Vector3, r: float) -> void:
	if n is MeshInstance3D:
		var mi := n as MeshInstance3D
		if mi.mesh and mi.is_visible_in_tree():
			var inv := mi.global_transform.affine_inverse()
			var lp := inv * p
			var ab := mi.mesh.get_aabb().grow(r)
			if ab.has_point(lp):
				_mesh_hits(str(mi.get_path()), mi.mesh, lp, r, mi)
	elif n is MultiMeshInstance3D:
		var mmi := n as MultiMeshInstance3D
		var mm := mmi.multimesh
		if mm and mm.mesh and mmi.is_visible_in_tree():
			var ab := mm.mesh.get_aabb().grow(r)
			for i in mm.instance_count:
				var xf := mmi.global_transform * mm.get_instance_transform(i)
				if absf(xf.basis.determinant()) < 1e-9:
					continue
				if ab.has_point(xf.affine_inverse() * p):
					print("  MM ", mmi.get_path(), " inst ", i, " mesh ", mm.mesh.resource_name, " pos ", xf.origin)
	elif n is Label3D:
		if (n as Label3D).global_position.distance_to(p) < r * 3.0:
			print("  LABEL ", n.get_path(), " '", (n as Label3D).text, "'")
	for c in n.get_children():
		_walk(c, p, r)


static func _mesh_hits(path: String, mesh: Mesh, lp: Vector3, r: float, mi: MeshInstance3D) -> void:
	for s in mesh.get_surface_count():
		var arr := mesh.surface_get_arrays(s)
		if arr.is_empty():
			continue
		var verts: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
		var idx: PackedInt32Array = arr[Mesh.ARRAY_INDEX] if arr[Mesh.ARRAY_INDEX] != null else PackedInt32Array()
		var near := 0
		var tri_hits := 0
		var sample := Vector3.ZERO
		if idx.is_empty():
			for k in range(0, verts.size() - 2, 3):
				if _tri_dist(lp, verts[k], verts[k + 1], verts[k + 2]) < r:
					tri_hits += 1
					sample = verts[k]
		else:
			for k in range(0, idx.size() - 2, 3):
				if _tri_dist(lp, verts[idx[k]], verts[idx[k + 1]], verts[idx[k + 2]]) < r:
					tri_hits += 1
					sample = verts[idx[k]]
		if tri_hits > 0:
			var mat := mi.get_active_material(s)
			var mname := ""
			if mat:
				mname = mat.resource_name
				if mat is ShaderMaterial and (mat as ShaderMaterial).shader:
					mname += " shader=" + (mat as ShaderMaterial).shader.resource_path
			print("  MESH ", path, " surf ", s, " tris ", tri_hits, " mat ", mname, " bsp ", mi.global_transform * sample)


static func _tri_dist(p: Vector3, a: Vector3, b: Vector3, c: Vector3) -> float:
	var n := (b - a).cross(c - a)
	if n.length_squared() < 1e-12:
		return 1e9
	n = n.normalized()
	var d := (p - a).dot(n)
	var q := p - n * d
	# Baryzentrisch prüfen
	var v0 := c - a
	var v1 := b - a
	var v2 := q - a
	var d00 := v0.dot(v0)
	var d01 := v0.dot(v1)
	var d11 := v1.dot(v1)
	var d20 := v2.dot(v0)
	var d21 := v2.dot(v1)
	var den := d00 * d11 - d01 * d01
	if absf(den) < 1e-12:
		return 1e9
	var u := (d11 * d20 - d01 * d21) / den
	var w := (d00 * d21 - d01 * d20) / den
	if u >= -0.05 and w >= -0.05 and u + w <= 1.1:
		return absf(d)
	return 1e9
