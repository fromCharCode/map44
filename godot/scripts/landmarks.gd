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
	# Loschwitzer Brücke (tools/blender/blaueswunder/): Stahlüberbau; befahrbar bleibt das LoD2-Deck. Lage/Höhe/Drehung
	# aus blaues_wunder.json (Fahrbahnhöhe, nicht Boden)
	{"file": "blaues_wunder.glb", "json": "blaues_wunder.json", "x": 0.0, "z": 0.0, "yaw": 0.0, "w": 0.0, "d": 0.0,
		"name": "Blaues Wunder", "no_collision": true, "trimesh_kind": "bridge"},
]

# Echte Wandbilder als Fototextur vor der LoD2-Wand: Bild von links nach rechts = a -> b (vom Betrachter aus gesehen),
# h = dargestellte Wandhöhe. Der Fürstenzug (Augustusstraße, 102 m Meißner Porzellan): Foto Gerd Eichmann,
# CC BY-SA 4.0 (Wikimedia Commons, Dresden-Fuerstenzug-ganz-01-gje.jpg), in vier Teile geschnitten.
const TEX_DIR := "res://assets/textures/landmarks/"
# Liste in assets/textures/landmarks/walls.json (schreibt tools/photo_wall.py)

var terrain: Terrain
var mats := {}

static var _walls = null


static func photo_walls() -> Array:
	if _walls == null:
		var wf := TEX_DIR + "walls.json"
		var j = JSON.parse_string(FileAccess.get_file_as_string(wf)) if FileAccess.file_exists(wf) else null
		_walls = j if j is Array else []
	return _walls


static func on_photo_wall(p: Vector2) -> bool:
	## Liegt der Punkt (Mitte einer Fassadenkante) an einer Fotowand? Dort keine Balkone/Gitter davorsetzen.
	for pw in photo_walls():
		var a := Vector2(pw["a"][0], pw["a"][1])
		var b := Vector2(pw["b"][0], pw["b"][1])
		if Geometry2D.get_closest_point_to_segment(p, a, b).distance_to(p) < 0.8:
			return true
	return false


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


func _photo_walls(t: Terrain) -> void:
	for pw in photo_walls():
		var a := Vector2(pw["a"][0], pw["a"][1])
		var b := Vector2(pw["b"][0], pw["b"][1])
		var mid := (a + b) * 0.5
		if not t.contains(mid.x, mid.y):
			continue
		var texs: Array = pw["tex"]
		var dir := (b - a).normalized()
		# a -> b ist für den Betrachter „nach rechts“; die Wandnormale zeigt zu ihm: n = dir x up
		var n3 := Vector3(dir.x, 0.0, dir.y).cross(Vector3.UP).normalized()
		var y0 := INF
		for k in 9:
			var q := a.lerp(b, float(k) / 8.0)
			y0 = minf(y0, terrain.height_at(q.x + n3.x * 1.5, q.y + n3.z * 1.5))
		y0 += float(pw.get("y0", 0.0)) - 0.15
		var h := float(pw["h"])
		for i in texs.size():
			var path: String = TEX_DIR + String(texs[i])
			if not ResourceLoader.exists(path):
				continue
			var p0 := a.lerp(b, float(i) / float(texs.size()))
			var p1 := a.lerp(b, float(i + 1) / float(texs.size()))
			var off := n3 * 0.09
			var v0 := Vector3(p0.x, y0, p0.y) + off
			var v1 := Vector3(p1.x, y0, p1.y) + off
			var st := SurfaceTool.new()
			st.begin(Mesh.PRIMITIVE_TRIANGLES)
			var vs := [v0, v1, v1 + Vector3(0, h, 0), v0 + Vector3(0, h, 0)]
			var uvs := [Vector2(0, 1), Vector2(1, 1), Vector2(1, 0), Vector2(0, 0)]
			for idx in [0, 2, 1, 0, 3, 2]:        # im Uhrzeigersinn vom Betrachter aus = Vorderseite
				st.set_normal(n3)
				st.set_uv(uvs[idx])
				st.add_vertex(vs[idx])
			st.generate_tangents()
			var m := StandardMaterial3D.new()
			m.albedo_texture = load(path)
			m.roughness = float(pw.get("rough", 0.6))
			m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
			var mi := MeshInstance3D.new()
			mi.mesh = st.commit()
			mi.material_override = m
			mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			mi.visibility_range_end = 700.0
			mi.name = "%s_%d" % [String(pw["name"]), i]
			add_child(mi)


func build(t: Terrain, noise: ImageTexture) -> void:
	terrain = t
	_make_materials()
	_photo_walls(t)
	for lm in LIST:
		var path: String = DIR + lm["file"]
		if not ResourceLoader.exists(path):
			continue
		var x: float = lm["x"]
		var z: float = lm["z"]
		var fixed_y = null
		var yaw_deg: float = lm["yaw"]
		if lm.has("json"):
			var jp: String = DIR + String(lm["json"])
			if not FileAccess.file_exists(jp):
				continue
			var j = JSON.parse_string(FileAccess.get_file_as_string(jp))
			if not (j is Dictionary):
				continue
			x = float(j.get("x", 0.0))
			z = float(j.get("z", 0.0))
			fixed_y = float(j.get("y", 0.0))
			yaw_deg = float(j.get("yaw_deg", 0.0))
		if not t.contains(x, z):
			continue
		var root := (load(path) as PackedScene).instantiate() as Node3D
		var hw: float = lm["w"] * 0.5
		var hd: float = lm["d"] * 0.5
		var gy := 0.0
		for off in [Vector2(-hw, -hd), Vector2(hw, -hd), Vector2(-hw, hd), Vector2(hw, hd), Vector2(0, 0)]:
			gy += terrain.height_at(x + off.x * 0.8, z + off.y * 0.8)
		gy /= 5.0
		root.position = Vector3(x, gy - 0.25 if fixed_y == null else float(fixed_y), z)
		root.rotation.y = deg_to_rad(yaw_deg)
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
		if lm.has("trimesh_kind"):
			# Kollision aus den Modelldreiecken (Träger, Pylone, Pfeiler, Geländer); Fahrbahn bleibt das LoD2-Deck
			_trimesh_body(root, String(lm["trimesh_kind"]))
		if lm.get("no_collision", false):
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


func _trimesh_body(root: Node3D, kind: String) -> void:
	var faces := PackedVector3Array()
	var stack: Array = [[root, root.transform]]
	while not stack.is_empty():
		var it: Array = stack.pop_back()
		var n: Node = it[0]
		var xf: Transform3D = it[1]
		for c in n.get_children():
			if c is Node3D:
				stack.append([c, xf * (c as Node3D).transform])
		if n is MeshInstance3D and (n as MeshInstance3D).mesh != null:
			var f := (n as MeshInstance3D).mesh.get_faces()
			for i in f.size():
				f[i] = xf * f[i]
			faces.append_array(f)
	if faces.is_empty():
		return
	var body := StaticBody3D.new()
	body.collision_layer = 1
	body.set_meta("kind", kind)
	var cs := CollisionShape3D.new()
	var sh := ConcavePolygonShape3D.new()
	sh.backface_collision = true
	sh.set_faces(faces)
	cs.shape = sh
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


static var _night_last := -1.0


static func set_night(v: float) -> void:
	## Wahrzeichen werden nachts angestrahlt: Stein und Putz leuchten warm (wie von Strahlern am Boden), stufenlos
	## mit der Dämmerung. Ab 1 Uhr nachts wird die Anstrahlung abgeschaltet (wie in echt).
	var late := Timetable.hours >= 1.0 and Timetable.hours < 5.0
	var k := clampf(v, 0.0, 1.0) * (0.0 if late else 1.0)
	if absf(k - _night_last) < 0.02:
		return
	_night_last = k
	_shared_lock.lock()
	for nm in ["Sandstone", "SandstoneDark", "Plaster"]:
		if _shared_mats.has(nm):
			var m: StandardMaterial3D = _shared_mats[nm]
			m.emission_enabled = k > 0.03
			if k > 0.03:
				m.emission = Color(1.0, 0.80, 0.52) * m.albedo_color
				m.emission_texture = m.albedo_texture
				m.emission_energy_multiplier = 0.035 * k      # Nachtbelichtung ist sehr empfindlich: wenig genügt
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
