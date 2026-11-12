## Prüft die importierten Unterholz-/Fassadenmodelle (Godot headless):
##   ~/.local/bin/godot --headless --path godot -s "$PWD/tools/blender/veg_facade_check.gd"
extends SceneTree

func _walk(n: Node, out: Array) -> void:
	if n is MeshInstance3D:
		out.append(n)
	for c in n.get_children():
		_walk(c, out)

func _init() -> void:
	for folder in ["vegetation", "facade"]:
		var d := DirAccess.open("res://assets/models/" + folder)
		var files := []
		for f in d.get_files():
			if f.ends_with(".glb"):
				files.append(f)
		files.sort()
		for f in files:
			var ps: PackedScene = load("res://assets/models/%s/%s" % [folder, f])
			var inst := ps.instantiate()
			var mis := []
			_walk(inst, mis)
			var line := "%s: %d MeshInstance3D" % [f, mis.size()]
			for mi in mis:
				var mesh: Mesh = mi.mesh
				line += " aabb=%s" % [mesh.get_aabb()]
				for s in mesh.get_surface_count():
					var m: Material = mesh.surface_get_material(s)
					var fmt: int = mesh.surface_get_format(s)
					var info: String = m.resource_name
					if m is BaseMaterial3D:
						info += "(tr=%d cull=%d vcol=%s scissor=%.2f tex=%s nrm=%s)" % [m.transparency, m.cull_mode, m.vertex_color_use_as_albedo, m.alpha_scissor_threshold, m.albedo_texture != null, m.normal_enabled]
					info += " uv2=%s col=%s" % [(fmt & Mesh.ARRAY_FORMAT_TEX_UV2) != 0, (fmt & Mesh.ARRAY_FORMAT_COLOR) != 0]
					line += " | " + info
			print(line)
			inst.free()
	quit()
