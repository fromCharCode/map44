## Prüft bus_solo.glb / bus_articulated.glb nach dem Godot-Import (nur lesend):
##   ~/.local/bin/godot --headless --path godot -s "$PWD/tools/blender/bus_check.gd"
extends SceneTree

const NEED_MATS := ["CarPaint", "Glass", "HeadlightEmit", "TaillightEmit", "BrakeLightEmit", "IndicatorEmit",
	"DestinationEmit", "InteriorEmit"]


func _xf(n: Node3D, root: Node3D) -> Transform3D:
	## Transformation relativ zur Wurzel (ohne Szenenbaum, daher manuell über die Eltern).
	var t := Transform3D.IDENTITY
	var c: Node = n
	while c != null and c != root:
		if c is Node3D:
			t = (c as Node3D).transform * t
		c = c.get_parent()
	return t


func _meshes(n: Node, out: Array) -> void:
	if n is MeshInstance3D:
		out.append(n)
	for c in n.get_children():
		_meshes(c, out)


func _check(file: String, nodes: Array) -> void:
	var errs: Array = []
	var ps := load("res://assets/models/cars/" + file) as PackedScene
	if ps == null:
		print("FEHLER: kann ", file, " nicht laden")
		return
	var root := ps.instantiate() as Node3D
	for nm in nodes:
		var n := root.find_child(nm, true, false) as Node3D
		if n == null:
			errs.append("Knoten fehlt: " + nm)
		elif nm.begins_with("Wheel_") and not n.transform.basis.is_equal_approx(Basis.IDENTITY):
			errs.append("Radknoten rotiert: " + nm)
	var mis: Array = []
	_meshes(root, mis)
	var aabb := AABB()
	var first := true
	var tris := 0
	var mats := {}
	for mi in mis:
		var m: MeshInstance3D = mi
		var box: AABB = _xf(m, root) * m.mesh.get_aabb()
		aabb = box if first else aabb.merge(box)
		first = false
		for s in m.mesh.get_surface_count():
			var arr: Array = m.mesh.surface_get_arrays(s)
			var idx: PackedInt32Array = arr[Mesh.ARRAY_INDEX]
			tris += idx.size() / 3
			var mat := m.mesh.surface_get_material(s)
			if mat:
				mats[String(mat.resource_name)] = true
	for k in NEED_MATS:
		if not mats.has(k):
			errs.append("Material fehlt: " + k)
	var line := "%s: %d Meshes, %d Dreiecke, AABB pos=%s size=%s" % [file, mis.size(), tris, aabb.position, aabb.size]
	print(line)
	for nm in nodes:
		var n := root.find_child(nm, true, false) as Node3D
		if n and (nm.begins_with("Wheel_") or nm in ["Front", "Rear", "Bellows"] or nm.ends_with("_R") and nm.begins_with("Door_1")):
			print("   %-10s pos=%s parent=%s" % [nm, _xf(n, root).origin, n.get_parent().name])
	# Kompatibilität mit scripts/car_model.gd
	var made: Dictionary = CarModel.make(file, Color(0.95, 0.75, 0.05), true, 0.3)
	print("   CarModel.make: wheels=%s emit=%s" % [made["wheels"].keys(), made["emit"].keys()])
	(made["root"] as Node).free()
	print("   Materialien: ", mats.keys())
	print("   ", "OK" if errs.is_empty() else "FEHLER: " + str(errs))
	root.free()


func _init() -> void:
	var base := ["Wheel_FL", "Wheel_FR", "Wheel_RL", "Wheel_RR"]
	var solo := base.duplicate()
	for n in range(1, 4):
		solo += ["Door_%d_L" % n, "Door_%d_R" % n]
	_check("bus_solo.glb", solo)
	var art := base + ["Wheel_ML", "Wheel_MR", "Front", "Rear", "Bellows"]
	for n in range(1, 5):
		art += ["Door_%d_L" % n, "Door_%d_R" % n]
	_check("bus_articulated.glb", art)
	quit()
