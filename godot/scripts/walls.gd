class_name Walls
extends Node3D
## Mauern, Stützmauern (Brühlsche Terrasse), Zäune und Treppen aus OSM-Linien.

const CELL := 250.0

var terrain: Terrain
var mat_wall: StandardMaterial3D
var mat_brick: StandardMaterial3D
var mat_stone: StandardMaterial3D
var mat_fence: StandardMaterial3D
var _solid: Dictionary = {}     # Zelle -> {mat -> {v,n,i}} und faces
var _faces: Dictionary = {}


func build(t: Terrain, city: Dictionary) -> void:
	terrain = t
	mat_stone = _tri_mat("sandstone", 1.0)
	mat_wall = _tri_mat("plaster_b", 0.78)
	mat_brick = _tri_mat("brick", 1.0)
	mat_fence = _fence_material()
	var mats := {"stone": mat_stone, "wall": mat_wall, "brick": mat_brick}
	for b in city["barriers"]:
		_barrier(b)
	for st in city["steps"]:
		_steps(st)
	_flush(mats)


func _tri_mat(name: String, tint: float) -> StandardMaterial3D:
	return TexLib.tri_material(name, tint)      # gemeinsam für alle Kacheln (komprimiert, einmal geladen)


func _fence_material() -> StandardMaterial3D:
	var img := Image.create(64, 64, true, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 0))
	for x in 64:
		for y in 64:
			var bar := (x % 8) < 2
			var rail := y < 3 or y > 60 or (y > 30 and y < 33)
			if bar or rail:
				img.set_pixel(x, y, Color(0.08, 0.09, 0.1, 1.0))
	img.generate_mipmaps()
	var m := StandardMaterial3D.new()
	m.albedo_texture = ImageTexture.create_from_image(img)
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	m.alpha_scissor_threshold = 0.5
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	m.roughness = 0.55
	m.metallic = 0.6
	m.uv1_scale = Vector3(1.0 / 1.6, 1.0 / 1.4, 1.0)   # 1 Kachel = 8 Stäbe auf 1,6 m, 1,4 m hoch
	return m


func _cell(x: float, z: float) -> Vector2i:
	return Vector2i(floori((x + 1000.0) / CELL), floori((z + 1000.0) / CELL))


func _bucket(cell: Vector2i, key: String) -> Dictionary:
	if not _solid.has(cell):
		_solid[cell] = {}
		_faces[cell] = PackedVector3Array()
	var d: Dictionary = _solid[cell]
	if not d.has(key):
		d[key] = {"v": PackedVector3Array(), "n": PackedVector3Array(), "i": PackedInt32Array(), "uv": PackedVector2Array()}
	return d[key]


func _tri(b: Dictionary, a: Vector3, bb: Vector3, c: Vector3, n: Vector3, collide: bool, cell: Vector2i, uv: Vector2 = Vector2.ZERO) -> void:
	var front := -(bb - a).cross(c - a)
	var k: int = b["v"].size()
	b["v"].append(a)
	b["v"].append(bb)
	b["v"].append(c)
	for q in 3:
		b["n"].append(n)
		b["uv"].append(uv)
	if front.dot(n) < 0.0:
		b["i"].append_array([k, k + 2, k + 1])
	else:
		b["i"].append_array([k, k + 1, k + 2])
	if collide:
		(_faces[cell] as PackedVector3Array).append_array([a, bb, c])


func _quad(b: Dictionary, p0: Vector3, p1: Vector3, p2: Vector3, p3: Vector3, n: Vector3, collide: bool, cell: Vector2i) -> void:
	_tri(b, p0, p1, p2, n, collide, cell)
	_tri(b, p0, p2, p3, n, collide, cell)


func _barrier(bar: Dictionary) -> void:
	var kind: String = bar["kind"]
	var pts: Array = bar["pts"]
	if pts.size() < 2:
		return
	var key := "wall"
	var thick := 0.3
	var default_h := 1.9
	match kind:
		"retaining_wall":
			key = "stone"
			thick = 0.55
		"city_wall":
			key = "stone"
			thick = 0.9
			default_h = 5.0
		"fence":
			thick = 0.04
			default_h = 1.5
		_:
			var r := fposmod(float(pts[0][0]) * 7.1 + float(pts[0][1]) * 3.3, 1.0)
			var m: String = bar["mat"]
			if m == "brick" or r < 0.35:
				key = "brick"
			elif m == "stone" or m == "sandstone" or r < 0.6:
				key = "stone"
	var h: float = bar["h"] if bar["h"] != null else default_h
	h = clampf(h, 0.3, 12.0)
	for i in pts.size() - 1:
		var a := Vector2(pts[i][0], pts[i][1])
		var b := Vector2(pts[i + 1][0], pts[i + 1][1])
		var d := b - a
		var L := d.length()
		if L < 0.2:
			continue
		var t := d / L
		var nrm := Vector2(-t.y, t.x)
		var ga := terrain.height_at(a.x, a.y)
		var gb := terrain.height_at(b.x, b.y)
		var ya_bot := ga - 0.35
		var yb_bot := gb - 0.35
		var ya_top := ga + h
		var yb_top := gb + h
		if kind == "retaining_wall" or kind == "city_wall":
			# Stützmauer: Oberkante an der höheren Seite (+ Brüstung), Unterkante an der tieferen.
			# Stadtmauern sind meist Terrassen-/Bastionsmauern; freistehend nur bei ebenem Gelände.
			var la := terrain.height_at(a.x + nrm.x * 1.6, a.y + nrm.y * 1.6)
			var ra := terrain.height_at(a.x - nrm.x * 1.6, a.y - nrm.y * 1.6)
			var lb := terrain.height_at(b.x + nrm.x * 1.6, b.y + nrm.y * 1.6)
			var rb := terrain.height_at(b.x - nrm.x * 1.6, b.y - nrm.y * 1.6)
			var step_h := maxf(absf(la - ra), absf(lb - rb))
			if kind == "retaining_wall" or step_h > 1.2:
				var parapet := 1.0 if kind == "city_wall" else 0.2
				ya_top = maxf(la, ra) + parapet
				yb_top = maxf(lb, rb) + parapet
				ya_bot = minf(la, ra) - 0.4
				yb_bot = minf(lb, rb) - 0.4
				if kind == "retaining_wall" and bar["h"] != null:
					ya_top = maxf(ya_top, ga + 0.3)
		var cell := _cell(a.x, a.y)
		if kind == "fence":
			var f := _bucket(cell, "fence")
			var o := Vector3(0, 0, 0)
			var base_a := Vector3(a.x, ga, a.y)
			var base_b := Vector3(b.x, gb, b.y)
			var top_a := base_a + Vector3(0, 1.4, 0)
			var top_b := base_b + Vector3(0, 1.4, 0)
			var k: int = f["v"].size()
			f["v"].append_array([base_a, base_b, top_b, top_a])
			f["n"].append_array([Vector3(nrm.x, 0, nrm.y), Vector3(nrm.x, 0, nrm.y), Vector3(nrm.x, 0, nrm.y), Vector3(nrm.x, 0, nrm.y)])
			f["uv"].append_array([Vector2(0, 1), Vector2(L, 1), Vector2(L, 0), Vector2(0, 0)])
			f["i"].append_array([k, k + 1, k + 2, k, k + 2, k + 3])
			continue
		var bk := _bucket(cell, key)
		var n3 := Vector3(nrm.x, 0, nrm.y)
		var th := thick * 0.5
		var a_l := Vector3(a.x + nrm.x * th, 0, a.y + nrm.y * th)
		var a_r := Vector3(a.x - nrm.x * th, 0, a.y - nrm.y * th)
		var b_l := Vector3(b.x + nrm.x * th, 0, b.y + nrm.y * th)
		var b_r := Vector3(b.x - nrm.x * th, 0, b.y - nrm.y * th)
		# linke Seite
		_quad(bk, a_l + Vector3(0, ya_bot, 0), b_l + Vector3(0, yb_bot, 0), b_l + Vector3(0, yb_top, 0), a_l + Vector3(0, ya_top, 0), n3, true, cell)
		# rechte Seite
		_quad(bk, a_r + Vector3(0, ya_bot, 0), b_r + Vector3(0, yb_bot, 0), b_r + Vector3(0, yb_top, 0), a_r + Vector3(0, ya_top, 0), -n3, true, cell)
		# Oberseite
		_quad(bk, a_l + Vector3(0, ya_top, 0), b_l + Vector3(0, yb_top, 0), b_r + Vector3(0, yb_top, 0), a_r + Vector3(0, ya_top, 0), Vector3.UP, true, cell)
		# Stirnflächen an den Enden der Linie
		if i == 0:
			_quad(bk, a_l + Vector3(0, ya_bot, 0), a_r + Vector3(0, ya_bot, 0), a_r + Vector3(0, ya_top, 0), a_l + Vector3(0, ya_top, 0), -Vector3(t.x, 0, t.y), true, cell)
		if i == pts.size() - 2:
			_quad(bk, b_l + Vector3(0, yb_bot, 0), b_r + Vector3(0, yb_bot, 0), b_r + Vector3(0, yb_top, 0), b_l + Vector3(0, yb_top, 0), Vector3(t.x, 0, t.y), true, cell)


func _steps(st: Dictionary) -> void:
	var pts: Array = st["pts"]
	var w: float = clampf(st["width"], 1.2, 8.0)
	var first := Vector2(pts[0][0], pts[0][1])
	var last := Vector2(pts[pts.size() - 1][0], pts[pts.size() - 1][1])
	var y0 := terrain.height_at(first.x, first.y)
	var y1 := terrain.height_at(last.x, last.y)
	var dy := y1 - y0
	if absf(dy) < 0.35:
		return
	var n := clampi(int(round(absf(dy) / 0.17)), 2, 90)
	# Gesamtlänge und Parametrisierung entlang der Polylinie
	var lens: Array[float] = [0.0]
	for i in pts.size() - 1:
		lens.append(lens[i] + Vector2(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]).length())
	var total := lens[lens.size() - 1]
	if total < 1.2:
		return
	var cell := _cell(first.x, first.y)
	var bk := _bucket(cell, "stone")
	for s in n:
		var t0 := float(s) / n * total
		var t1 := float(s + 1) / n * total
		var p0 := _along(pts, lens, t0)
		var p1 := _along(pts, lens, t1)
		var tang := (p1 - p0).normalized()
		var nrm := Vector2(-tang.y, tang.x)
		var top_y := y0 + dy * float(s + 1) / n
		var prev_y := y0 + dy * float(s) / n
		var hw := w * 0.5
		var a_l := Vector3(p0.x + nrm.x * hw, top_y, p0.y + nrm.y * hw)
		var a_r := Vector3(p0.x - nrm.x * hw, top_y, p0.y - nrm.y * hw)
		var b_l := Vector3(p1.x + nrm.x * hw, top_y, p1.y + nrm.y * hw)
		var b_r := Vector3(p1.x - nrm.x * hw, top_y, p1.y - nrm.y * hw)
		# Trittfläche
		_quad(bk, a_l, b_l, b_r, a_r, Vector3.UP, false, cell)
		# Setzstufe (Stirn zur tiefer liegenden Seite)
		var low_dir := -Vector3(tang.x, 0, tang.y) * signf(dy)
		var ra_l := Vector3(a_l.x, minf(prev_y, top_y) - 0.1, a_l.z)
		var ra_r := Vector3(a_r.x, minf(prev_y, top_y) - 0.1, a_r.z)
		_quad(bk, ra_l, ra_r, a_r, a_l, low_dir, false, cell)
	# Wangen (seitliche Mauern), damit die Treppe nicht schwebt
	var steps_n := n
	for s in steps_n:
		var t0 := float(s) / steps_n * total
		var t1 := float(s + 1) / steps_n * total
		var p0 := _along(pts, lens, t0)
		var p1 := _along(pts, lens, t1)
		var tang := (p1 - p0).normalized()
		var nrm := Vector2(-tang.y, tang.x)
		var top_y := y0 + dy * float(s + 1) / steps_n
		var hw := w * 0.5
		var g0 := terrain.height_at(p0.x, p0.y) - 0.3
		var g1 := terrain.height_at(p1.x, p1.y) - 0.3
		for side in [1.0, -1.0]:
			var o0 := Vector3(p0.x + nrm.x * hw * side, 0, p0.y + nrm.y * hw * side)
			var o1 := Vector3(p1.x + nrm.x * hw * side, 0, p1.y + nrm.y * hw * side)
			var nn := Vector3(nrm.x * side, 0, nrm.y * side)
			_quad(bk, o0 + Vector3(0, minf(g0, top_y), 0), o1 + Vector3(0, minf(g1, top_y), 0), o1 + Vector3(0, top_y, 0), o0 + Vector3(0, top_y, 0), nn, false, cell)


func _along(pts: Array, lens: Array, t: float) -> Vector2:
	for i in pts.size() - 1:
		if t <= lens[i + 1] or i == pts.size() - 2:
			var seg: float = lens[i + 1] - lens[i]
			var f := 0.0 if seg < 0.0001 else clampf((t - lens[i]) / seg, 0.0, 1.0)
			return Vector2(pts[i][0], pts[i][1]).lerp(Vector2(pts[i + 1][0], pts[i + 1][1]), f)
	return Vector2(pts[0][0], pts[0][1])


func _flush(mats: Dictionary) -> void:
	for cell in _solid:
		var buckets: Dictionary = _solid[cell]
		var mesh := ArrayMesh.new()
		for key in buckets:
			var b: Dictionary = buckets[key]
			if b["v"].is_empty():
				continue
			var arr := []
			arr.resize(Mesh.ARRAY_MAX)
			arr[Mesh.ARRAY_VERTEX] = b["v"]
			arr[Mesh.ARRAY_NORMAL] = b["n"]
			arr[Mesh.ARRAY_TEX_UV] = b["uv"]
			arr[Mesh.ARRAY_INDEX] = b["i"]
			mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
			mesh.surface_set_material(mesh.get_surface_count() - 1, mat_fence if key == "fence" else mats[key])
		if mesh.get_surface_count() == 0:
			continue
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		mi.visibility_range_end = 700.0
		add_child(mi)
		var faces: PackedVector3Array = _faces[cell]
		if faces.size() > 0:
			var body := StaticBody3D.new()
			body.collision_layer = 1
			var cs := CollisionShape3D.new()
			var sh := ConcavePolygonShape3D.new()
			sh.backface_collision = true
			sh.set_faces(faces)
			cs.shape = sh
			body.add_child(cs)
			mi.add_child(body)
