class_name CarDamage
extends RefCounted
## Schadensmodell: verformt die Karosserie-Meshes an Einschlagstellen (CPU-Vertexverschiebung mit
## Normalenkorrektur), dunkelt den Lack ab, bricht Glas/Scheinwerfer und liefert mechanische Schäden.

const PARTS := ["Body", "Glass", "Interior", "Lights"]
const MAX_DISP := 0.85            # maximale Gesamtverformung eines Vertex in Metern

var car: Node3D
var parts: Array = []             # {mi, surfaces: [{arrays, mat, prev}], orig: [PackedVector3Array]}
var total := 0.0                  # 0..1 Gesamtschaden
var front := 0.0                  # Schaden vorn (Motor)
var rear := 0.0
var left := 0.0
var right := 0.0
var glass_level := 0              # 0 heil, 1 Risse, 2 zerbrochen
var glass_dmg := 0.0
var head_dmg := 0.0               # Scheinwerfer/Rückleuchten kaputt (0..1)
var wheel_dmg := {"FL": 0.0, "FR": 0.0, "RL": 0.0, "RR": 0.0}
var wheel_lost := {"FL": false, "FR": false, "RL": false, "RR": false}
var wheel_pos := {}               # k -> Vector3 (Fahrzeug-Koordinaten)
var _crack_mat: StandardMaterial3D
var _noise := FastNoiseLite.new()


func setup(c: Node3D, model: Node3D, wheel_locals: Dictionary) -> void:
	car = c
	wheel_pos = wheel_locals
	_noise.seed = 11
	_noise.frequency = 1.0
	for nm in PARTS:
		var mi := model.find_child(nm, true, false) as MeshInstance3D
		if mi == null or mi.mesh == null:
			continue
		var mesh := mi.mesh as ArrayMesh
		if mesh == null:
			continue
		var p := {"mi": mi, "surfaces": [], "orig": []}
		for i in mesh.get_surface_count():
			var arrays := mesh.surface_get_arrays(i)
			var mat := mesh.surface_get_material(i)
			var pos: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var cols := PackedColorArray()
			cols.resize(pos.size())
			cols.fill(Color(1, 1, 1, 1))
			arrays[Mesh.ARRAY_COLOR] = cols
			p["surfaces"].append({"arrays": arrays, "mat": mat, "prev": pos.duplicate()})
			p["orig"].append(pos.duplicate())
			p["orig_n"] = p.get("orig_n", [])
			p["orig_n"].append((arrays[Mesh.ARRAY_NORMAL] as PackedVector3Array).duplicate())
		parts.append(p)


func repair() -> void:
	total = 0.0
	front = 0.0
	rear = 0.0
	left = 0.0
	right = 0.0
	glass_level = 0
	glass_dmg = 0.0
	head_dmg = 0.0
	for k in wheel_dmg:
		wheel_dmg[k] = 0.0
		wheel_lost[k] = false
	for p in parts:
		var surfs: Array = p["surfaces"]
		for i in surfs.size():
			var arrays: Array = surfs[i]["arrays"]
			var orig: PackedVector3Array = p["orig"][i]
			arrays[Mesh.ARRAY_VERTEX] = orig.duplicate()
			arrays[Mesh.ARRAY_NORMAL] = (p["orig_n"][i] as PackedVector3Array).duplicate()
			var cols := PackedColorArray()
			cols.resize(orig.size())
			cols.fill(Color(1, 1, 1, 1))
			arrays[Mesh.ARRAY_COLOR] = cols
			surfs[i]["prev"] = orig.duplicate()
		_rebuild(p)
	_set_glass_level(0)


## Einschlag in Fahrzeug-Koordinaten. dir = Richtung, in die die Karosserie gedrückt wird (nach innen).
func impact(local_pos: Vector3, local_dir: Vector3, sev: float) -> void:
	sev = clampf(sev, 0.0, 30.0)
	var radius := clampf(0.40 + 0.075 * sev, 0.4, 1.25)
	var depth := clampf(0.028 * sev, 0.02, 0.5)
	var dir := local_dir.normalized()
	var r2 := radius * radius
	for p in parts:
		var surfs: Array = p["surfaces"]
		var changed := false
		for i in surfs.size():
			var arrays: Array = surfs[i]["arrays"]
			var pos: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var orig: PackedVector3Array = p["orig"][i]
			var prev: PackedVector3Array = surfs[i]["prev"]
			var nrm: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
			var cols: PackedColorArray = arrays[Mesh.ARRAY_COLOR]
			var idx: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			var moved := PackedByteArray()
			moved.resize(pos.size())
			var any := false
			for v in pos.size():
				var d := pos[v] - local_pos
				var dd := d.length_squared()
				if dd >= r2:
					continue
				var w := 1.0 - sqrt(dd) / radius
				w = w * w
				var crumple := 0.7 + 0.6 * (_noise.get_noise_3dv(pos[v] * 3.1) + 1.0) * 0.5
				var np := pos[v] + dir * depth * w * crumple
				var off := np - orig[v]
				if off.length() > MAX_DISP:
					np = orig[v] + off.normalized() * MAX_DISP
				if np != pos[v]:
					pos[v] = np
					moved[v] = 1
					any = true
					var c := cols[v]
					var dark := clampf(w * 1.8, 0.0, 1.0)
					cols[v] = Color(c.r * (1.0 - 0.5 * dark), c.g * (1.0 - 0.55 * dark), c.b * (1.0 - 0.6 * dark), 1.0)
			if not any:
				continue
			changed = true
			var delta_n := PackedVector3Array()
			delta_n.resize(pos.size())
			for t in range(0, idx.size(), 3):
				var a := idx[t]
				var b := idx[t + 1]
				var c2 := idx[t + 2]
				if moved[a] == 0 and moved[b] == 0 and moved[c2] == 0:
					continue
				var fn_new := (pos[b] - pos[a]).cross(pos[c2] - pos[a])
				var fn_old := (prev[b] - prev[a]).cross(prev[c2] - prev[a])
				if fn_new.length_squared() < 1e-12 or fn_old.length_squared() < 1e-12:
					continue
				var dn := fn_new.normalized() - fn_old.normalized()
				delta_n[a] += dn
				delta_n[b] += dn
				delta_n[c2] += dn
			for v in pos.size():
				if moved[v] == 1:
					nrm[v] = (nrm[v] + delta_n[v] * 0.8).normalized()
			arrays[Mesh.ARRAY_VERTEX] = pos
			arrays[Mesh.ARRAY_NORMAL] = nrm
			arrays[Mesh.ARRAY_COLOR] = cols
			surfs[i]["prev"] = pos.duplicate()
		if changed:
			_rebuild(p)
	_accumulate(local_pos, sev)


func _rebuild(p: Dictionary) -> void:
	var mi: MeshInstance3D = p["mi"]
	var mesh := ArrayMesh.new()
	var surfs: Array = p["surfaces"]
	for i in surfs.size():
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, surfs[i]["arrays"])
		mesh.surface_set_material(i, surfs[i]["mat"])
	mi.mesh = mesh


func _accumulate(lp: Vector3, sev: float) -> void:
	var s := sev / 60.0
	total = clampf(total + s * 0.8, 0.0, 1.0)
	if lp.z < -0.9:
		front = clampf(front + s * 1.6, 0.0, 1.0)
		head_dmg = clampf(head_dmg + s * 2.2, 0.0, 1.0)
	elif lp.z > 0.9:
		rear = clampf(rear + s * 1.4, 0.0, 1.0)
		head_dmg = clampf(head_dmg + s * 0.8, 0.0, 1.0)
	if lp.x < -0.5:
		left = clampf(left + s * 1.4, 0.0, 1.0)
	elif lp.x > 0.5:
		right = clampf(right + s * 1.4, 0.0, 1.0)
	glass_dmg += sev if lp.y > 0.85 else sev * 0.25
	if glass_level == 0 and glass_dmg > 14.0:
		glass_level = 1
		_set_glass_level(1)
	if glass_level == 1 and glass_dmg > 38.0:
		glass_level = 2
		_set_glass_level(2)
	for k in wheel_dmg:
		var wl: Vector3 = wheel_pos.get(k, Vector3.ZERO)
		if wl == Vector3.ZERO:
			continue
		if Vector2(lp.x - wl.x, lp.z - wl.z).length() < 0.95 and lp.y < 0.9:
			wheel_dmg[k] = clampf(wheel_dmg[k] + sev / 22.0, 0.0, 1.0)
			if wheel_dmg[k] >= 1.0:
				wheel_lost[k] = true


func _set_glass_level(level: int) -> void:
	for p in parts:
		var mi: MeshInstance3D = p["mi"]
		if mi.name != "Glass":
			continue
		if level == 0:
			mi.visible = true
			mi.set_surface_override_material(0, CarModel.glass_material())
		elif level == 1:
			mi.set_surface_override_material(0, _cracked_glass())
		else:
			mi.visible = false


func _cracked_glass() -> StandardMaterial3D:
	if _crack_mat == null:
		var img := Image.create(256, 256, false, Image.FORMAT_RGBA8)
		img.fill(Color(0.1, 0.12, 0.14, 0.38))
		var r := RandomNumberGenerator.new()
		r.seed = 99
		for n in 5:
			var cx := r.randf_range(60, 196)
			var cy := r.randf_range(60, 196)
			for ray in 9:
				var ang := r.randf() * TAU
				var length := r.randf_range(40, 140)
				for t in int(length):
					var x := int(cx + cos(ang) * t + r.randf_range(-1.5, 1.5))
					var y := int(cy + sin(ang) * t + r.randf_range(-1.5, 1.5))
					if x >= 0 and x < 256 and y >= 0 and y < 256:
						img.set_pixel(x, y, Color(0.85, 0.9, 0.95, 0.85))
		img.generate_mipmaps()
		_crack_mat = StandardMaterial3D.new()
		_crack_mat.albedo_texture = ImageTexture.create_from_image(img)
		_crack_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		_crack_mat.roughness = 0.1
		_crack_mat.uv1_triplanar = true
		_crack_mat.uv1_scale = Vector3(0.9, 0.9, 0.9)
		_crack_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	return _crack_mat
