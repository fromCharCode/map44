@tool
extends EditorScenePostImport
## Post-Import für das Unterholz (in den .glb.import-Dateien als import_script eingetragen).
##
## COLOR_0 der Modelle enthält Umgebungsverdeckung (grau). Godot 4.7 setzt beim
## glTF-Import vertex_color_use_as_albedo nur für Oberflächen NACH der ersten –
## hier wird es für jede Oberfläche mit Vertexfarben einheitlich eingeschaltet.


func _post_import(scene: Node) -> Object:
	_fix(scene)
	return scene


func _fix(n: Node) -> void:
	var mi := n as MeshInstance3D
	if mi != null and mi.mesh != null:
		for s in mi.mesh.get_surface_count():
			var m := mi.mesh.surface_get_material(s) as BaseMaterial3D
			if m != null and (mi.mesh.surface_get_format(s) & Mesh.ARRAY_FORMAT_COLOR) != 0:
				m.vertex_color_use_as_albedo = true
	for c in n.get_children():
		_fix(c)
