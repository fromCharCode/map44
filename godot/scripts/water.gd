class_name Water
extends Node3D
## Wasserflächen (Elbe, Teiche) als flache Meshes auf Pegelhöhe.

var material: ShaderMaterial


func build(waters: Array, noise: ImageTexture) -> void:
	material = ShaderMaterial.new()
	material.shader = load("res://shaders/water.gdshader")
	material.set_shader_parameter("noise_tex", noise)
	for w in waters:
		var rings: Array = w["rings"]
		var level: float = w["level"] - 0.05
		var verts := PackedVector3Array()
		var norms := PackedVector3Array()
		for r in rings:
			for p in r:
				var yy := level
				if w.has("plane"):
					var pl: Array = w["plane"]
					yy = pl[0] * p[0] + pl[1] * p[1] + pl[2] - 0.05
				verts.append(Vector3(p[0], yy, p[1]))
				norms.append(Vector3.UP)
		var idx := PackedInt32Array()
		var tris: Array = w["tris"]
		for t in range(0, tris.size(), 3):
			var a: int = tris[t]
			var b: int = tris[t + 1]
			var c: int = tris[t + 2]
			# Vorderseite nach oben (Uhrzeigersinn von oben gesehen)
			var n := (verts[b] - verts[a]).cross(verts[c] - verts[a])
			if n.y > 0.0:
				var tmp := b
				b = c
				c = tmp
			idx.append_array([a, b, c])
		if idx.is_empty():
			continue
		var arr := []
		arr.resize(Mesh.ARRAY_MAX)
		arr[Mesh.ARRAY_VERTEX] = verts
		arr[Mesh.ARRAY_NORMAL] = norms
		arr[Mesh.ARRAY_INDEX] = idx
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		mi.material_override = material
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(mi)
