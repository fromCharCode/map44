class_name Peds
extends Node3D
## Fußgänger: laufen auf Gehweg-Pfaden (versetzte Straßenlinien + Fußwege) rund um den Fokus.
## Nicht-physikalisch; spawnen/despawnen wie der Verkehr.

const MODELS := ["res://assets/models/peds/ped_m.glb", "res://assets/models/peds/ped_f.glb"]
const CELL := 100.0
const SKIN := [Color(0.93, 0.76, 0.64), Color(0.85, 0.66, 0.52), Color(0.70, 0.52, 0.40), Color(0.52, 0.37, 0.28), Color(0.96, 0.82, 0.72)]
const HAIR := [Color(0.08, 0.06, 0.05), Color(0.25, 0.16, 0.09), Color(0.45, 0.30, 0.15), Color(0.72, 0.60, 0.40), Color(0.55, 0.55, 0.55), Color(0.35, 0.10, 0.08)]
const TOP := [Color(0.12, 0.14, 0.18), Color(0.55, 0.12, 0.12), Color(0.82, 0.80, 0.74), Color(0.20, 0.32, 0.48), Color(0.15, 0.30, 0.20), Color(0.70, 0.55, 0.25), Color(0.30, 0.30, 0.32), Color(0.78, 0.40, 0.18), Color(0.55, 0.60, 0.68)]
const BOTTOM := [Color(0.10, 0.11, 0.14), Color(0.20, 0.25, 0.38), Color(0.32, 0.27, 0.20), Color(0.45, 0.45, 0.47), Color(0.07, 0.07, 0.08)]
const SHOES := [Color(0.08, 0.08, 0.08), Color(0.35, 0.22, 0.14), Color(0.85, 0.85, 0.82), Color(0.2, 0.2, 0.3)]

var world: World
var focus := Vector3.ZERO
var target_count := 55
var scenes: Array = []
var cells := {}          # Vector2i -> Array of paths  {pts: Array[Vector2], len: float, tile: String}
var peds: Array = []     # {node, path, s, dir, v, anim}
var rng := RandomNumberGenerator.new()
var enabled := true
var _spawn_t := 0.0
var _has_models := false
var hots := {}           # Vector2i -> Array of {p: Vector2, yaw: float, tile: String} (Läden, Cafés, Haltestellen)


func setup(w: World) -> void:
	world = w
	rng.seed = 4711
	for m in MODELS:
		if ResourceLoader.exists(m):
			scenes.append(load(m))
	_has_models = scenes.size() > 0


func add_tile(tile: Tile) -> void:
	var life: Dictionary = tile.city.get("life", {})
	for sh in life.get("shops", []):
		var mid := Vector2((float(sh[1]) + float(sh[3])) * 0.5, (float(sh[2]) + float(sh[4])) * 0.5)
		var n := Vector2(sh[5], sh[6])
		_add_hot(tile.key, mid + n * 1.3, atan2(n.x, n.y))      # schaut zum Schaufenster
	for f in life.get("furniture", []):
		var kind: String = f[0]
		if kind in ["stop_pole", "bus_stop", "cafe_set", "bench", "litfass"]:
			_add_hot(tile.key, Vector2(f[1], f[2]) + Vector2(0.9, 0.6), float(f[3]))
	for r in tile.city["roads"]:
		if r["bridge"]:
			continue
		var cls: String = r.get("cls", "")
		var pts: Array = r["pts"]
		if pts.size() < 2:
			continue
		var w: float = r["width"]
		if cls in ["footway", "pedestrian", "path"]:
			_add_path(tile.key, _pts2(pts, 0.0))
		elif cls in ["residential", "tertiary", "secondary", "primary", "unclassified", "living_street"]:
			var off: float = w * 0.5 + 1.4
			_add_path(tile.key, _pts2(pts, off))
			_add_path(tile.key, _pts2(pts, -off))


func _add_hot(tkey: String, p: Vector2, yaw: float) -> void:
	var key := Vector2i(floori(p.x / CELL), floori(p.y / CELL))
	if not hots.has(key):
		hots[key] = []
	hots[key].append({"p": p, "yaw": yaw, "tile": tkey})


func remove_tile(tile: Tile) -> void:
	for k in hots.keys():
		var arr2: Array = hots[k]
		for i in range(arr2.size() - 1, -1, -1):
			if arr2[i]["tile"] == tile.key:
				arr2.remove_at(i)
		if arr2.is_empty():
			hots.erase(k)
	for k in cells.keys():
		var arr: Array = cells[k]
		for i in range(arr.size() - 1, -1, -1):
			if arr[i]["tile"] == tile.key:
				arr.remove_at(i)
		if arr.is_empty():
			cells.erase(k)
	for i in range(peds.size() - 1, -1, -1):
		if peds[i]["path"]["tile"] == tile.key:
			_free_ped(i)


func _pts2(pts: Array, off: float) -> Array:
	var res: Array = []
	for i in pts.size():
		var p := Vector2(pts[i][0], pts[i][1])
		if off != 0.0:
			var t: Vector2
			if i == 0:
				t = Vector2(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
			elif i == pts.size() - 1:
				t = Vector2(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
			else:
				t = Vector2(pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1])
			t = t.normalized()
			p += Vector2(-t.y, t.x) * off
		res.append(p)
	return res


func _add_path(tkey: String, pts: Array) -> void:
	var L := 0.0
	for i in pts.size() - 1:
		L += (pts[i + 1] as Vector2).distance_to(pts[i])
	if L < 18.0:
		return
	var mid: Vector2 = pts[pts.size() / 2]
	var key := Vector2i(floori(mid.x / CELL), floori(mid.y / CELL))
	if not cells.has(key):
		cells[key] = []
	cells[key].append({"pts": pts, "len": L, "tile": tkey})


func _point_at(pts: Array, s: float) -> Vector2:
	var acc := 0.0
	for i in pts.size() - 1:
		var a: Vector2 = pts[i]
		var b: Vector2 = pts[i + 1]
		var l := a.distance_to(b)
		if acc + l >= s:
			return a.lerp(b, (s - acc) / maxf(l, 0.001))
		acc += l
	return pts[pts.size() - 1]


func _process(delta: float) -> void:
	if not enabled:
		return
	_spawn_t -= delta
	if peds.size() < target_count and _spawn_t <= 0.0:
		_spawn_t = 0.12
		_try_spawn()
	for i in range(peds.size() - 1, -1, -1):
		var p: Dictionary = peds[i]
		var n: Node3D = p["node"]
		if n.global_position.distance_to(focus) > 170.0:
			_free_ped(i)
			continue
		if p.get("stand", false):
			continue
		var path: Dictionary = p["path"]
		var s: float = p["s"] + p["dir"] * p["v"] * delta
		if s < 0.0 or s > path["len"]:
			p["dir"] = -p["dir"]
			s = clampf(s, 0.0, path["len"])
		p["s"] = s
		var pos2 := _point_at(path["pts"], s)
		var ahead := _point_at(path["pts"], clampf(s + p["dir"] * 1.2, 0.0, path["len"]))
		var d := ahead - pos2
		var yaw: float = p["yaw"]
		if d.length() > 0.01:
			var want := atan2(-d.x, -d.y)
			yaw = lerp_angle(yaw, want, 1.0 - exp(-6.0 * delta))
			p["yaw"] = yaw
		n.global_transform = Transform3D(Basis(Vector3.UP, yaw), Vector3(pos2.x, world.height_at(pos2.x, pos2.y), pos2.y))


func _try_spawn() -> void:
	if not hots.is_empty() and rng.randf() < 0.45 and _try_spawn_standing():
		return
	if cells.is_empty():
		return
	for attempt in 10:
		var ang := rng.randf() * TAU
		var rad := rng.randf_range(15.0, 120.0)
		var q := Vector2(focus.x + cos(ang) * rad, focus.z + sin(ang) * rad)
		var arr: Array = cells.get(Vector2i(floori(q.x / CELL), floori(q.y / CELL)), [])
		if arr.is_empty():
			continue
		var path: Dictionary = arr[rng.randi_range(0, arr.size() - 1)]
		var s := rng.randf_range(0.0, float(path["len"]))
		var pos2 := _point_at(path["pts"], s)
		if Vector2(pos2.x - focus.x, pos2.y - focus.z).length() < 12.0:
			continue
		_spawn_ped(path, s, pos2)
		return


func _try_spawn_standing() -> bool:
	## Stehende Menschen an Läden, Cafés, Haltestellen (einzeln oder in kleinen Gruppen)
	for attempt in 8:
		var ang := rng.randf() * TAU
		var rad := rng.randf_range(12.0, 110.0)
		var q := Vector2(focus.x + cos(ang) * rad, focus.z + sin(ang) * rad)
		var arr: Array = hots.get(Vector2i(floori(q.x / CELL), floori(q.y / CELL)), [])
		if arr.is_empty():
			continue
		var h: Dictionary = arr[rng.randi_range(0, arr.size() - 1)]
		var base: Vector2 = h["p"]
		if Vector2(base.x - focus.x, base.y - focus.z).length() < 10.0:
			continue
		var n := 1 + (rng.randi() % 3 if rng.randf() < 0.5 else 0)
		var yaw0: float = h["yaw"]
		for k in n:
			if peds.size() >= target_count + 20:
				break
			var off := Vector2(cos(float(k) * 2.1), sin(float(k) * 2.1)) * (0.0 if k == 0 else 0.75)
			var pos2 := base + off
			var yaw := yaw0
			if n > 1:
				var c := base + Vector2(0.25, 0.25)
				yaw = atan2(-(c.x - pos2.x), -(c.y - pos2.y))      # einander zugewandt
			_spawn_standing(pos2, yaw, "Talk" if n > 1 else "Idle")
		return true
	return false


func _spawn_standing(pos2: Vector2, yaw: float, anim_name: String) -> void:
	if not _has_models:
		return
	var n := (scenes[rng.randi() % scenes.size()] as PackedScene).instantiate() as Node3D
	_tint(n)
	RenderUtil.gi_off(n)
	add_child(n)
	n.global_transform = Transform3D(Basis(Vector3.UP, yaw), Vector3(pos2.x, world.height_at(pos2.x, pos2.y), pos2.y))
	var anim := n.find_child("AnimationPlayer", true, false) as AnimationPlayer
	if anim:
		var nm := anim_name if anim.has_animation(anim_name) else "Idle"
		if anim.has_animation(nm):
			var a := anim.get_animation(nm)
			a.loop_mode = Animation.LOOP_LINEAR
			anim.play(nm)
			anim.speed_scale = rng.randf_range(0.85, 1.1)
			anim.seek(rng.randf() * a.length)
	peds.append({"node": n, "path": {"tile": ""}, "s": 0.0, "dir": 1, "v": 0.0, "yaw": yaw, "stand": true})


func _spawn_ped(path: Dictionary, s: float, pos2: Vector2) -> void:
	var n: Node3D
	var anim: AnimationPlayer = null
	var v := rng.randf_range(1.0, 1.65)
	if _has_models:
		n = (scenes[rng.randi() % scenes.size()] as PackedScene).instantiate() as Node3D
		_tint(n)
		anim = n.find_child("AnimationPlayer", true, false) as AnimationPlayer
	else:
		var mi := MeshInstance3D.new()
		var cm := CapsuleMesh.new()
		cm.radius = 0.25
		cm.height = 1.75
		mi.mesh = cm
		mi.position.y = 0.88
		n = Node3D.new()
		n.add_child(mi)
	RenderUtil.gi_off(n)
	add_child(n)
	n.global_position = Vector3(pos2.x, world.height_at(pos2.x, pos2.y), pos2.y)
	if anim:
		var nm := "Walk"
		if anim.has_animation(nm):
			var a := anim.get_animation(nm)
			a.loop_mode = Animation.LOOP_LINEAR
			anim.play(nm)
			anim.speed_scale = v / 1.4
			anim.seek(rng.randf() * a.length)
	peds.append({"node": n, "path": path, "s": s, "dir": 1 if rng.randf() < 0.5 else -1, "v": v, "yaw": rng.randf() * TAU})


static var _tint_cache := {}


func _tint(root: Node) -> void:
	var cols := {"Skin": SKIN[rng.randi() % SKIN.size()], "Hair": HAIR[rng.randi() % HAIR.size()],
			"Top": TOP[rng.randi() % TOP.size()], "Bottom": BOTTOM[rng.randi() % BOTTOM.size()],
			"Shoes": SHOES[rng.randi() % SHOES.size()], "Accessory": TOP[rng.randi() % TOP.size()]}
	var stack: Array = [root]
	while not stack.is_empty():
		var x: Node = stack.pop_back()
		for c in x.get_children():
			stack.append(c)
		if x is MeshInstance3D:
			var mi := x as MeshInstance3D
			for i in mi.mesh.get_surface_count():
				var m := mi.mesh.surface_get_material(i)
				if m == null:
					continue
				var nm := String(m.resource_name)
				if cols.has(nm):
					# Geteilte Materialien je (Teil, Farbe) aus den festen Paletten: früher je Fußgänger 6 eigene
					# Kopien -> beim Freigeben las Godot die schon gelöschten Materialien (24 Fehler je Fußgänger,
					# Ruckler) und jede Kopie kostete einen eigenen Materialwechsel beim Zeichnen.
					var key := "%s|%s|%d" % [nm, (cols[nm] as Color).to_html(false), m.get_instance_id()]
					var nmat: StandardMaterial3D = _tint_cache.get(key)
					if nmat == null:
						nmat = (m as StandardMaterial3D).duplicate() as StandardMaterial3D
						nmat.albedo_color = cols[nm]
						_tint_cache[key] = nmat
					mi.set_surface_override_material(i, nmat)


func _free_ped(i: int) -> void:
	(peds[i]["node"] as Node).queue_free()
	peds.remove_at(i)
