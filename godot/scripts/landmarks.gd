class_name Landmarks
extends Node3D
## Handmodellierte Wahrzeichen an ihren echten Positionen (aus dem Luftbild bestimmt).

const DIR := "res://assets/models/landmarks/"

# file, x, z, yaw (Grad, Drehung um Y; Front = -Z), footprint w (x), d (z) nach der Drehung
const LIST := [
	{"file": "frauenkirche.glb", "x": 796.0, "z": -156.0, "yaw": 0.0, "w": 54.0, "d": 54.0, "name": "Frauenkirche"},
	{"file": "hofkirche.glb", "x": 503.0, "z": -333.0, "yaw": -90.0, "w": 89.0, "d": 55.0, "name": "Hofkirche"},
	{"file": "semperoper.glb", "x": 385.0, "z": -455.0, "yaw": -145.0, "w": 100.0, "d": 90.0, "name": "Semperoper"},
	# Modell enthält zusätzlich einen Schlossflügel (x 488–528) -> auf den Turm zuschneiden ("keep", Welt-x/z);
	# im Turmgrundriss ("core") werden alle LoD2-Teile entfernt, sonst nur solche >= min_h
	{"file": "hausmannsturm.glb", "x": 500.0, "z": -280.0, "yaw": 0.0, "w": 56.0, "d": 18.0, "name": "Hausmannsturm", "min_h": 40.0,
		"keep": [470.8, 489.2, -289.4, -270.6], "core": [480.0, -280.0, 17.0, 17.0]},
	{"file": "kreuzkirche.glb", "x": 628.0, "z": 190.0, "yaw": 90.0, "w": 91.0, "d": 40.0, "name": "Kreuzkirche"},
	# Hochhaus „Pirnaisches Tor“ (Grunaer Str. 5, P 27) im Zustand 2019–22 mit dem Graffito NADDL.UND.RONNY.SIEGT!
	# (data/research/pirnaischer_platz_hochhaus.md, Modell: tools/blender/hochhaus/). LoD2 zeigt die Baustelle
	# 2023/24 (Turm unvollständig) -> ganze GID entfernen; Modell enthält Turm, Stelzen und Flachbau.
	# boxes: Kollision in Modellkoordinaten [x0, x1, y0, y1, z0, z1]
	{"file": "hochhaus_pirnaischer.glb", "x": 1148.32, "z": 138.35, "yaw": 59.6, "w": 0.0, "d": 0.0,
		"name": "Hochhaus Pirnaischer Platz", "remove_gid": ["DESNATPU1000G316"],
		"boxes": [[-26.92, 26.92, 5.45, 45.0, -8.605, 8.605], [-14.06, 26.62, 0.0, 5.8, -8.1, 8.1],
			[-14.1, 40.3, 0.0, 5.1, -42.6, -8.6],
			[-25.96, -25.5, 0.0, 5.45, -6.0, -3.6], [-25.96, -25.5, 0.0, 5.45, 3.6, 6.0],
			[-20.99, -20.53, 0.0, 5.45, -6.0, -3.6], [-20.99, -20.53, 0.0, 5.45, 3.6, 6.0],
			[-16.03, -15.57, 0.0, 5.45, -6.0, -3.6], [-16.03, -15.57, 0.0, 5.45, 3.6, 6.0]]},
]

var terrain: Terrain
var mats := {}


static func filter_buildings(blds: Array) -> Array:
	## Entfernt OSM-Gebäude, deren Mittelpunkt in der Grundfläche eines Wahrzeichens liegt.
	var out: Array = []
	for b in blds:
		var p: Array = b["pos"]
		var inside := false
		for lm in LIST:
			if lm.has("remove_gid") and (lm["remove_gid"] as Array).has(str(b.get("gid", ""))):
				inside = true
				break
			if float(lm["w"]) <= 0.0:
				continue
			if lm.has("core"):
				var cr: Array = lm["core"]
				if absf(p[0] - cr[0]) < cr[2] * 0.5 and absf(p[1] - cr[1]) < cr[3] * 0.5:
					inside = true
					break
			if absf(p[0] - lm["x"]) < lm["w"] * 0.5 + 3.0 and absf(p[1] - lm["z"]) < lm["d"] * 0.5 + 3.0:
				# Wahrzeichen mit min_h: nur das hohe Gebäude ersetzen (der Rest, z. B. Schloßflügel, bleibt)
				if lm.has("min_h") and float(b["eave"]) < float(lm["min_h"]):
					continue
				inside = true
				break
		if not inside:
			out.append(b)
	return out


func build(t: Terrain, noise: ImageTexture) -> void:
	terrain = t
	_make_materials()
	for lm in LIST:
		var path: String = DIR + lm["file"]
		if not ResourceLoader.exists(path):
			continue
		var root := (load(path) as PackedScene).instantiate() as Node3D
		var x: float = lm["x"]
		var z: float = lm["z"]
		if not t.contains(x, z):
			continue
		var hw: float = lm["w"] * 0.5
		var hd: float = lm["d"] * 0.5
		var gy := 0.0
		for off in [Vector2(-hw, -hd), Vector2(hw, -hd), Vector2(-hw, hd), Vector2(hw, hd), Vector2(0, 0)]:
			gy += terrain.height_at(x + off.x * 0.8, z + off.y * 0.8)
		gy /= 5.0
		root.position = Vector3(x, gy - 0.25, z)
		root.rotation.y = deg_to_rad(lm["yaw"])
		root.name = lm["name"]
		if lm.has("keep"):
			_clip_to_box(root, lm["keep"])
		_apply_materials(root)
		add_child(root)
		if lm.has("boxes"):
			# Kollision aus Boxen im Modellsystem (gedreht wie das Modell)
			var bb := StaticBody3D.new()
			bb.collision_layer = 1
			bb.transform = root.transform
			for bx in lm["boxes"]:
				var c2 := CollisionShape3D.new()
				var s2 := BoxShape3D.new()
				s2.size = Vector3(bx[1] - bx[0], bx[3] - bx[2], bx[5] - bx[4])
				c2.shape = s2
				c2.position = Vector3((bx[0] + bx[1]) * 0.5, (bx[2] + bx[3]) * 0.5, (bx[4] + bx[5]) * 0.5)
				bb.add_child(c2)
			add_child(bb)
			continue
		# Kollision: einfache Box über der Grundfläche
		var body := StaticBody3D.new()
		body.collision_layer = 1
		var cs := CollisionShape3D.new()
		var bs := BoxShape3D.new()
		bs.size = Vector3(lm["w"] * 0.92, 30.0, lm["d"] * 0.92)
		cs.shape = bs
		cs.position = Vector3(x, gy + 15.0, z)
		if lm.has("keep"):
			var kb: Array = lm["keep"]
			bs.size = Vector3((kb[1] - kb[0]) * 0.92, 30.0, (kb[3] - kb[2]) * 0.92)
			cs.position = Vector3((kb[0] + kb[1]) * 0.5, gy + 15.0, (kb[2] + kb[3]) * 0.5)
		body.add_child(cs)
		add_child(body)


func _clip_to_box(root: Node3D, kb: Array) -> void:
	## Behält nur Dreiecke, deren Schwerpunkt (Weltkoordinaten x/z) in kb = [x0, x1, z0, z1] liegt.
	var stack: Array = [[root, root.transform]]
	while not stack.is_empty():
		var it: Array = stack.pop_back()
		var n: Node = it[0]
		var xf: Transform3D = it[1]
		for c in n.get_children():
			if c is Node3D:
				stack.append([c, xf * (c as Node3D).transform])
		if not (n is MeshInstance3D):
			continue
		var mi := n as MeshInstance3D
		var src := mi.mesh
		if src == null:
			continue
		var dst := ArrayMesh.new()
		for si in src.get_surface_count():
			var arr := src.surface_get_arrays(si)
			var verts: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
			var idx: PackedInt32Array = arr[Mesh.ARRAY_INDEX] if arr[Mesh.ARRAY_INDEX] != null else PackedInt32Array()
			if idx.is_empty():
				idx.resize(verts.size())
				for k in verts.size():
					idx[k] = k
			var keep := PackedInt32Array()
			for t in range(0, idx.size() - 2, 3):
				var cpos := xf * ((verts[idx[t]] + verts[idx[t + 1]] + verts[idx[t + 2]]) / 3.0)
				if cpos.x >= kb[0] and cpos.x <= kb[1] and cpos.z >= kb[2] and cpos.z <= kb[3]:
					keep.append_array([idx[t], idx[t + 1], idx[t + 2]])
			if keep.is_empty():
				continue
			arr[Mesh.ARRAY_INDEX] = keep
			dst.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
			dst.surface_set_material(dst.get_surface_count() - 1, src.surface_get_material(si))
		mi.mesh = dst


static var _shared_mats := {}
static var _shared_lock := Mutex.new()


func _make_materials() -> void:
	# Materialien sind für alle Kacheln gleich -> einmal bauen und teilen
	_shared_lock.lock()
	var have := not _shared_mats.is_empty()
	if have:
		mats = _shared_mats
	_shared_lock.unlock()
	if have:
		return
	_build_materials()
	_shared_lock.lock()
	if _shared_mats.is_empty():
		_shared_mats = mats
	mats = _shared_mats
	_shared_lock.unlock()


func _build_materials() -> void:
	var st_tex := TexLib.texture("sandstone", "albedo")
	var st_n := TexLib.texture("sandstone", "normal")
	var sc := 1.0 / TexLib.tile_size("sandstone")

	var sandstone := StandardMaterial3D.new()
	sandstone.albedo_texture = st_tex
	sandstone.normal_enabled = true
	sandstone.normal_texture = st_n
	sandstone.vertex_color_use_as_albedo = true
	sandstone.albedo_color = Color(0.82, 0.78, 0.72)
	sandstone.uv1_triplanar = true
	sandstone.uv1_world_triplanar = true
	sandstone.uv1_scale = Vector3(sc, sc, sc)
	sandstone.roughness = 0.9
	mats["Sandstone"] = sandstone

	var dark := sandstone.duplicate() as StandardMaterial3D
	dark.albedo_color = Color(0.5, 0.47, 0.43)
	mats["SandstoneDark"] = dark

	var pl := StandardMaterial3D.new()
	pl.albedo_texture = TexLib.texture("plaster_a", "albedo")
	pl.normal_enabled = true
	pl.normal_texture = TexLib.texture("plaster_a", "normal")
	pl.vertex_color_use_as_albedo = true
	pl.albedo_color = Color(0.9, 0.86, 0.76)
	pl.uv1_triplanar = true
	pl.uv1_world_triplanar = true
	var pc := 1.0 / TexLib.tile_size("plaster_a")
	pl.uv1_scale = Vector3(pc, pc, pc)
	pl.roughness = 0.9
	mats["Plaster"] = pl

	var glass := StandardMaterial3D.new()
	glass.albedo_color = Color(0.03, 0.045, 0.06)
	glass.roughness = 0.06
	glass.metallic = 0.3
	glass.metallic_specular = 0.9
	mats["Glass"] = glass

	var gold := StandardMaterial3D.new()
	gold.albedo_color = Color(0.9, 0.7, 0.25)
	gold.metallic = 1.0
	gold.roughness = 0.28
	mats["Gold"] = gold

	var copper := StandardMaterial3D.new()
	copper.albedo_color = Color(0.32, 0.55, 0.47)
	copper.metallic = 0.35
	copper.roughness = 0.55
	mats["CopperGreen"] = copper

	var slate := StandardMaterial3D.new()
	slate.albedo_color = Color(0.17, 0.18, 0.2)
	slate.roughness = 0.65
	mats["Slate"] = slate


func _apply_materials(root: Node) -> void:
	var stack: Array = [root]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		for c in n.get_children():
			stack.append(c)
		if n is MeshInstance3D:
			var mi := n as MeshInstance3D
			mi.visibility_range_end = 2500.0
			for i in mi.mesh.get_surface_count():
				var m := mi.mesh.surface_get_material(i)
				if m == null:
					continue
				var nm := String(m.resource_name)
				if mats.has(nm):
					mi.set_surface_override_material(i, mats[nm])
