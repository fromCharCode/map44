class_name Buildings
extends Node3D
## Gebäude: Wände (Fassaden-Shader mit Stilen), Dächer, Gesims/Sockel, Gauben, Kollision.
## Zusammengefasst in 250-m-Zellen.

const CELL := 250.0

var facade_mat: ShaderMaterial
var roof_mat: ShaderMaterial
var trim_mat: StandardMaterial3D
var world_half := 1000.0
var count := 0
var passages: Array = []          # city["passages"]: Durchfahrten durch Gebäude (vor build() setzen)
var _pass_by_b := {}             # Bauteil-id -> Durchfahrten, die seine Wände queren (Öffnungen)
var _tun_by_b := {}              # Bauteil-id -> Durchfahrten, deren Tunnel es zeichnet
var shops: Array = []             # city["life"]["shops"] (vor build() setzen)
var _shops_by_b := {}
var _deco := {}                   # [Modell, Zelle] -> Array[Transform3D] (Balkone, Loggien, Portale)
const SHOP_CATS := ["food", "super", "fashion", "service", "home", "gastro", "bank", "health", "culture", "hotel", "other", "vacant"]


func build(blds: Array, noise: ImageTexture) -> void:
	# Materialien sind für alle Kacheln gleich -> einmal bauen, dann geteilt (TexLib-Cache)
	facade_mat = TexLib.get_shared("bld_facade") as ShaderMaterial
	if facade_mat == null:
		var fm := ShaderMaterial.new()
		fm.shader = load("res://shaders/facade.gdshader")
		fm.set_shader_parameter("plaster_albedo", TexLib.texture("plaster_a", "albedo"))
		fm.set_shader_parameter("plaster_normal", TexLib.texture("plaster_a", "normal"))
		fm.set_shader_parameter("plaster_rough", TexLib.texture("plaster_a", "rough"))
		fm.set_shader_parameter("brick_albedo", TexLib.texture("brick", "albedo"))
		fm.set_shader_parameter("brick_normal", TexLib.texture("brick", "normal"))
		fm.set_shader_parameter("concrete_albedo", TexLib.texture("concrete", "albedo"))
		fm.set_shader_parameter("concrete_normal", TexLib.texture("concrete", "normal"))
		fm.set_shader_parameter("noise_tex", noise)
		fm.set_shader_parameter("plaster_tile", TexLib.tile_size("plaster_a"))
		fm.set_shader_parameter("brick_tile", TexLib.tile_size("brick"))
		fm.set_shader_parameter("concrete_tile", TexLib.tile_size("concrete"))
		if ResourceLoader.exists("res://assets/textures/street/graffiti.png"):
			fm.set_shader_parameter("graffiti_atlas", load("res://assets/textures/street/graffiti.png"))
			fm.set_shader_parameter("has_graffiti", true)
		facade_mat = TexLib.shared_material("bld_facade", fm) as ShaderMaterial

	roof_mat = TexLib.get_shared("bld_roof") as ShaderMaterial
	if roof_mat == null:
		var rm := ShaderMaterial.new()
		rm.shader = load("res://shaders/roof.gdshader")
		rm.set_shader_parameter("roof_albedo", TexLib.texture("roof_tiles", "albedo"))
		rm.set_shader_parameter("roof_normal", TexLib.texture("roof_tiles", "normal"))
		rm.set_shader_parameter("roof_rough", TexLib.texture("roof_tiles", "rough"))
		rm.set_shader_parameter("tile_m", TexLib.tile_size("roof_tiles"))
		roof_mat = TexLib.shared_material("bld_roof", rm) as ShaderMaterial

	# Gesims/Sockel: feine Putz-/Steinstruktur, Farbe über Vertex-Color
	trim_mat = TexLib.get_shared("bld_trim") as StandardMaterial3D
	if trim_mat == null:
		var tm := StandardMaterial3D.new()
		tm.albedo_texture = TexLib.texture("plaster_a", "albedo")
		tm.normal_enabled = true
		tm.normal_texture = TexLib.texture("plaster_a", "normal")
		tm.vertex_color_use_as_albedo = true
		tm.uv1_triplanar = true
		tm.uv1_world_triplanar = true
		var sc := 1.0 / TexLib.tile_size("plaster_a")
		tm.uv1_scale = Vector3(sc, sc, sc)
		tm.roughness = 0.85
		trim_mat = TexLib.shared_material("bld_trim", tm) as StandardMaterial3D

	_pass_by_b.clear()
	_tun_by_b.clear()
	for ps in passages:
		var owner: String = str(ps["b"])
		if not _tun_by_b.has(owner):
			_tun_by_b[owner] = []
		_tun_by_b[owner].append(ps)
		var ids: Array = ps.get("bs", [ps["b"]])
		for bid in ids:
			var k: String = str(bid)
			if not _pass_by_b.has(k):
				_pass_by_b[k] = []
			_pass_by_b[k].append(ps)
	_shops_by_b.clear()
	for sh in shops:
		var bid: String = str(sh[0])
		if not _shops_by_b.has(bid):
			_shops_by_b[bid] = []
		_shops_by_b[bid].append([Vector2(sh[1], sh[2]), Vector2(sh[3], sh[4]), float(SHOP_CATS.find(String(sh[9])) + 1)])
	_deco.clear()
	var cells := {}
	for b in blds:
		var p: Array = b["pos"]
		var key := Vector2i(floori((p[0] + world_half) / CELL), floori((p[1] + world_half) / CELL))
		if not cells.has(key):
			cells[key] = []
		cells[key].append(b)
	for key in cells:
		_build_cell(key, cells[key])
	_flush_deco()
	count = blds.size()


static func _front_normal(a: Vector3, b: Vector3, c: Vector3) -> Vector3:
	# Godot: Vorderseite = im Uhrzeigersinn; Rechte-Hand-Normale zeigt von der Vorderseite weg.
	return -(b - a).cross(c - a)


## Sammler für einen Mesh-Abschnitt
class Surf:
	var v := PackedVector3Array()
	var n := PackedVector3Array()
	var c := PackedColorArray()
	var uv := PackedVector2Array()
	var uv2 := PackedVector2Array()
	var t := PackedFloat32Array()
	var i := PackedInt32Array()
	var faces := PackedVector3Array()
	var collide := false
	var cu := PackedFloat32Array()        # CUSTOM0 je Vertex (x = Ladenkategorie)
	var cur := Color(0, 0, 0, 0)

	func tri(p0: Vector3, p1: Vector3, p2: Vector3, nrm: Vector3, col: Color, uvs: Array, uv2v: Vector2, tang: Vector3) -> void:
		var k := v.size()
		var pts := [p0, p1, p2]
		for q in 3:
			v.append(pts[q])
			n.append(nrm)
			c.append(col)
			uv.append(uvs[q])
			uv2.append(uv2v)
			t.append_array([tang.x, tang.y, tang.z, -1.0])
			cu.append_array([cur.r, cur.g, cur.b, cur.a])
		var o := [0, 1, 2]
		if Buildings._front_normal(p0, p1, p2).dot(nrm) < 0.0:
			o = [0, 2, 1]
		for a in o:
			i.append(k + a)
			if collide:
				faces.append(pts[a])

	func quad(p0: Vector3, p1: Vector3, p2: Vector3, p3: Vector3, nrm: Vector3, col: Color, uvs: Array, uv2v: Vector2, tang: Vector3) -> void:
		var k := v.size()
		var pts := [p0, p1, p2, p3]
		for q in 4:
			v.append(pts[q])
			n.append(nrm)
			c.append(col)
			uv.append(uvs[q])
			uv2.append(uv2v)
			t.append_array([tang.x, tang.y, tang.z, -1.0])
			cu.append_array([cur.r, cur.g, cur.b, cur.a])
		var tri1 := [0, 1, 2]
		var tri2 := [0, 2, 3]
		if Buildings._front_normal(p0, p1, p2).dot(nrm) < 0.0:
			tri1 = [0, 2, 1]
			tri2 = [0, 3, 2]
		for a in tri1 + tri2:
			i.append(k + a)
			if collide:
				faces.append(pts[a])


func _build_cell(key: Vector2i, items: Array) -> void:
	var walls := Surf.new()
	walls.collide = true
	var trim := Surf.new()
	var tun := Surf.new()
	tun.collide = true
	var rv := PackedVector3Array()
	var rn := PackedVector3Array()
	var rc := PackedColorArray()
	var ri := PackedInt32Array()

	for b in items:
		var ref: float = b["ref"]
		var y_top: float = ref + float(b["eave"])
		var y_bot: float = float(b["base"])
		var style: int = int(b.get("style", 0))
		var seed01 := float(hash(b["id"]) & 0xFFFF) / 65535.0
		var col := Color.from_string(b["wall"], Color(0.85, 0.8, 0.7))
		col.a = float(style) + 0.02 + 0.96 * seed01
		# Stil und Zufallswert gehen über CUSTOM0 (32-Bit-Float) an den Fassaden-Shader: Vertexfarben speichert
		# Godot als 8 Bit (0..1) – COLOR.a > 1 wurde abgeschnitten, alle Stile >= 1 erschienen als Barock
		walls.cur = Color(0.0, float(style), seed01, 0.0)
		var uv2 := Vector2(float(b["levels"]), float(b["eave"]))
		var v0 := y_bot - ref
		var v1 := y_top - ref
		var trim_col := col.lerp(Color(0.9, 0.88, 0.84), 0.45)
		trim_col.a = 1.0
		if style == 4:
			trim_col = Color(0.35, 0.37, 0.4, 1.0)
		var eave_h: float = b["eave"]

		var rings: Array = b["rings"]
		var door_edge := -1
		var best_len := 5.0
		if rings.size() > 0 and not b.get("stacked", false) and not b.get("elev", false):
			var r0: Array = rings[0]
			for ei in r0.size():
				var qa := Vector2(r0[ei][0], r0[ei][1])
				var qb := Vector2(r0[(ei + 1) % r0.size()][0], r0[(ei + 1) % r0.size()][1])
				if qa.distance_to(qb) > best_len and not _is_party(b, qa, qb):
					best_len = qa.distance_to(qb)
					door_edge = ei
		for ri_idx in rings.size():
			var pts: Array = []
			for p in rings[ri_idx]:
				pts.append(Vector2(p[0], p[1]))
			var area := 0.0
			for i in pts.size():
				var p0: Vector2 = pts[i]
				var p1: Vector2 = pts[(i + 1) % pts.size()]
				area += p0.x * p1.y - p1.x * p0.y
			var want_pos := ri_idx == 0
			if (area > 0.0) != want_pos:
				pts.reverse()
			var acc := 0.0
			for i in pts.size():
				var p0: Vector2 = pts[i]
				var p1: Vector2 = pts[(i + 1) % pts.size()]
				var d := p1 - p0
				var ln := d.length()
				if ln < 0.05:
					continue
				var tdir := d / ln
				var nrm := Vector3(d.y, 0.0, -d.x) / ln
				var tang := Vector3(tdir.x, 0.0, tdir.y)
				var openings := _openings(b, p0, p1, ln)
				var shop_iv := _shop_intervals(b, p0, p1, ln) if ri_idx == 0 else []
				if openings.is_empty() and shop_iv.is_empty():
					walls.quad(
						Vector3(p0.x, y_bot, p0.y), Vector3(p1.x, y_bot, p1.y),
						Vector3(p1.x, y_top, p1.y), Vector3(p0.x, y_top, p0.y),
						nrm, col, [Vector2(acc, v0), Vector2(acc + ln, v0), Vector2(acc + ln, v1), Vector2(acc, v1)], uv2, tang)
					# Gesims und Sockel als echte Geometrie (Silhouette, Schattenwurf)
					if ln > 1.2 and ri_idx == 0 and style != 5:
						_trim_strip(trim, p0, p1, tdir, nrm, ref, y_top, eave_h, style, trim_col)
				elif openings.is_empty():
					# Ladenfronten: Wandstücke mit Kategorie in CUSTOM0 (Shader zeichnet Schaufenster)
					var tp := 0.0
					for iv in shop_iv:
						walls.cur = Color(0.0, float(style), seed01, 0.0)
						_wall_piece(walls, trim, p0, p1, ln, tp, iv[0], y_bot, y_top, nrm, col, acc, v0, ref, uv2, tang, style != 5, tdir, eave_h, style, trim_col)
						walls.cur = Color(iv[2], float(style), seed01, 0.0)
						_wall_piece(walls, trim, p0, p1, ln, iv[0], iv[1], y_bot, y_top, nrm, col, acc, v0, ref, uv2, tang, false, tdir, eave_h, style, trim_col)
						tp = iv[1]
					walls.cur = Color(0.0, float(style), seed01, 0.0)
					_wall_piece(walls, trim, p0, p1, ln, tp, 1.0, y_bot, y_top, nrm, col, acc, v0, ref, uv2, tang, style != 5, tdir, eave_h, style, trim_col)
				else:
					# Wand mit Durchfahrt(en): volle Abschnitte daneben, darüber nur der Sturz
					var t_prev := 0.0
					for op in openings:
						_wall_piece(walls, trim, p0, p1, ln, t_prev, op[0], y_bot, y_top, nrm, col, acc, v0, ref, uv2, tang, ri_idx == 0 and style != 5, tdir, eave_h, style, trim_col)
						var qa := p0.lerp(p1, op[0])
						var qb := p0.lerp(p1, op[1])
						var yo: float = op[2]
						if yo < y_top - 0.05:
							walls.quad(Vector3(qa.x, yo, qa.y), Vector3(qb.x, yo, qb.y), Vector3(qb.x, y_top, qb.y), Vector3(qa.x, y_top, qa.y),
								nrm, col, [Vector2(acc + ln * op[0], yo - ref), Vector2(acc + ln * op[1], yo - ref), Vector2(acc + ln * op[1], v1), Vector2(acc + ln * op[0], v1)], uv2, tang)
						t_prev = op[1]
					_wall_piece(walls, trim, p0, p1, ln, t_prev, 1.0, y_bot, y_top, nrm, col, acc, v0, ref, uv2, tang, ri_idx == 0 and style != 5, tdir, eave_h, style, trim_col)
				if ri_idx == 0 and ln >= 4.0 and not b.get("stacked", false) and not b.get("elev", false) and not _is_party(b, p0, p1):
					_deco_edge(b, style, seed01, p0, p1, ln, acc, nrm, ref, shop_iv)
					if _edge_is(rings[0], p0, p1, door_edge):
						_door(b, style, seed01, p0, p1, ln, acc, nrm, ref, shop_iv)
				acc += ln

		# Durchfahrt: Seitenwände und Decke (Putz, mit Kollision)
		for ps in _tun_by_b.get(str(b["id"]), []):
			_tunnel(tun, ps, trim_col.darkened(0.1))

		# Giebelflächen oberhalb der Traufe (LoD2)
		var gb = b.get("gables")
		if gb != null and gb.size() >= 11:
			var g: Array = gb
			for q in range(0, g.size() - 10, 11):
				var gn := Vector3(g[q], 0.0, g[q + 1])
				var a3 := Vector3(g[q + 2], ref + g[q + 3], g[q + 4])
				var b3 := Vector3(g[q + 5], ref + g[q + 6], g[q + 7])
				var c3 := Vector3(g[q + 8], ref + g[q + 9], g[q + 10])
				var tg := Vector3(-gn.z, 0.0, gn.x)
				var ua := a3.dot(tg)
				walls.tri(a3, b3, c3, gn, col,
					[Vector2(ua, a3.y - ref), Vector2(b3.dot(tg), b3.y - ref), Vector2(c3.dot(tg), c3.y - ref)], uv2, tg)

		# --- Dach ---
		var rcol := Color.from_string(b["roof_col"], Color(0.5, 0.35, 0.3))
		var roof = b["roof"]
		if roof != null and roof.size() >= 9:
			var rf: Array = roof
			var centroid := Vector3.ZERO
			var nv := rf.size() / 3
			for q in nv:
				centroid += Vector3(rf[q * 3], ref + rf[q * 3 + 1], rf[q * 3 + 2])
			centroid /= nv
			var ref_pt := centroid - Vector3(0, 1.5, 0)
			for t in range(0, nv, 3):
				var a := Vector3(rf[t * 3], ref + rf[t * 3 + 1], rf[t * 3 + 2])
				var bb := Vector3(rf[t * 3 + 3], ref + rf[t * 3 + 4], rf[t * 3 + 5])
				var c := Vector3(rf[t * 3 + 6], ref + rf[t * 3 + 7], rf[t * 3 + 8])
				var fn := _front_normal(a, bb, c)
				var tc := (a + bb + c) / 3.0
				if not b.has("lod2") and fn.dot(tc - ref_pt) < 0.0:
					var tmp := bb
					bb = c
					c = tmp
				var n := _front_normal(a, bb, c).normalized()
				var k := rv.size()
				rv.append(a)
				rv.append(bb)
				rv.append(c)
				for q in 3:
					rn.append(n)
					rc.append(rcol)
				ri.append_array([k, k + 1, k + 2])
			# Gauben auf Altbau-/Barock-/Zeilenbau-Dächern
			var rinfo = b.get("rinfo")
			if rinfo != null and style in [0, 1, 3, 6] and float(rinfo["rh"]) >= 2.0 and float(rinfo["L"]) >= 9.0:
				_dormers(walls, rv, rn, rc, ri, rinfo, ref, eave_h, col, rcol, seed01)
		else:
			var top: Array = b["top"]
			if top.size() >= 3:
				var base_k := rv.size()
				for r in rings:
					for p in r:
						rv.append(Vector3(p[0], y_top, p[1]))
						rn.append(Vector3.UP)
						rc.append(rcol)
				for t in range(0, top.size(), 3):
					var i0: int = base_k + top[t]
					var i1: int = base_k + top[t + 1]
					var i2: int = base_k + top[t + 2]
					if _front_normal(rv[i0], rv[i1], rv[i2]).y < 0.0:
						var tmp := i1
						i1 = i2
						i2 = tmp
					ri.append_array([i0, i1, i2])

	if walls.v.is_empty():
		return
	var mesh := ArrayMesh.new()
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = walls.v
	arr[Mesh.ARRAY_NORMAL] = walls.n
	arr[Mesh.ARRAY_COLOR] = walls.c
	arr[Mesh.ARRAY_TEX_UV] = walls.uv
	arr[Mesh.ARRAY_TEX_UV2] = walls.uv2
	arr[Mesh.ARRAY_TANGENT] = walls.t
	arr[Mesh.ARRAY_INDEX] = walls.i
	arr[Mesh.ARRAY_CUSTOM0] = walls.cu
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr, [], {}, Mesh.ARRAY_CUSTOM_RGBA_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT)
	mesh.surface_set_material(0, facade_mat)
	if not rv.is_empty():
		var arr2 := []
		arr2.resize(Mesh.ARRAY_MAX)
		arr2[Mesh.ARRAY_VERTEX] = rv
		arr2[Mesh.ARRAY_NORMAL] = rn
		arr2[Mesh.ARRAY_COLOR] = rc
		arr2[Mesh.ARRAY_INDEX] = ri
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr2)
		mesh.surface_set_material(mesh.get_surface_count() - 1, roof_mat)
	if not tun.v.is_empty():
		var arr4 := []
		arr4.resize(Mesh.ARRAY_MAX)
		arr4[Mesh.ARRAY_VERTEX] = tun.v
		arr4[Mesh.ARRAY_NORMAL] = tun.n
		arr4[Mesh.ARRAY_COLOR] = tun.c
		arr4[Mesh.ARRAY_INDEX] = tun.i
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr4)
		mesh.surface_set_material(mesh.get_surface_count() - 1, trim_mat)
	if not trim.v.is_empty():
		var arr3 := []
		arr3.resize(Mesh.ARRAY_MAX)
		arr3[Mesh.ARRAY_VERTEX] = trim.v
		arr3[Mesh.ARRAY_NORMAL] = trim.n
		arr3[Mesh.ARRAY_COLOR] = trim.c
		arr3[Mesh.ARRAY_INDEX] = trim.i
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr3)
		mesh.surface_set_material(mesh.get_surface_count() - 1, trim_mat)

	var mi := MeshInstance3D.new()
	mi.name = "Cell_%d_%d" % [key.x, key.y]
	mi.mesh = mesh
	mi.visibility_range_end = 1500.0
	add_child(mi)

	var body := StaticBody3D.new()
	body.collision_layer = 1
	var cs := CollisionShape3D.new()
	var shape := ConcavePolygonShape3D.new()
	shape.backface_collision = true
	var all_faces := walls.faces
	all_faces.append_array(tun.faces)
	shape.set_faces(all_faces)
	cs.shape = shape
	body.add_child(cs)
	mi.add_child(body)


func _shop_intervals(b: Dictionary, p0: Vector2, p1: Vector2, ln: float) -> Array:
	## Ladenfronten (aus city["life"]) auf dieser Wandkante: [[t0, t1, kategorie], ...] sortiert.
	var res: Array = []
	var lst: Array = _shops_by_b.get(str(b["id"]), [])
	if lst.is_empty():
		return res
	var e := (p1 - p0) / ln
	var nrm2 := Vector2(-e.y, e.x)
	for sh in lst:
		var a: Vector2 = sh[0]
		var c: Vector2 = sh[1]
		if absf((a - p0).dot(nrm2)) > 0.35 or absf((c - p0).dot(nrm2)) > 0.35:
			continue
		var ta := (a - p0).dot(e) / ln
		var tc := (c - p0).dot(e) / ln
		var t0 := clampf(minf(ta, tc), 0.0, 1.0)
		var t1 := clampf(maxf(ta, tc), 0.0, 1.0)
		if (t1 - t0) * ln > 1.0:
			res.append([t0, t1, sh[2]])
	res.sort_custom(func(x, y): return x[0] < y[0])
	return res


# --- Fassadenteile (Balkone, Loggien, Portale) ---------------------------------
static func _fract(x: float) -> float:
	return x - floorf(x)


static func _h11(p: float) -> float:
	## identisch zu hash11() im Fassaden-Shader
	p = _fract(p * 0.1031)
	p *= p + 33.33
	p *= p + p
	return _fract(p)


static func _h21(px: float, py: float) -> float:
	## identisch zu hash21() im Fassaden-Shader
	var p3 := Vector3(_fract(px * 0.1031), _fract(py * 0.1031), _fract(px * 0.1031))
	var dd := p3.dot(Vector3(p3.y, p3.z, p3.x) + Vector3(33.33, 33.33, 33.33))
	p3 += Vector3(dd, dd, dd)
	return _fract((p3.x + p3.y) * p3.z)


func _deco_edge(b: Dictionary, style: int, seed: float, p0: Vector2, p1: Vector2, ln: float, acc: float, nrm: Vector3, ref: float, shop_iv: Array) -> void:
	var levels := maxf(float(b["levels"]), 1.0)
	var height := maxf(float(b["eave"]), 3.0)
	if height < 7.5:
		return
	var fh := clampf(height / levels, 2.7, 4.6)
	var rows := int(floor(height / fh))
	var h1 := _h11(seed * 91.7)
	var pitch := 0.0
	var model := ""
	match style:
		0, 6:
			pitch = lerpf(2.3, 3.1, h1) if style == 0 else lerpf(2.4, 3.0, h1)
			model = "balcony_gruenderzeit"
		1:
			pitch = lerpf(3.0, 4.2, h1)
			model = "balcony_rail_french"
		2:
			pitch = 3.0
			model = "loggia_platte"
		3:
			pitch = lerpf(2.2, 2.8, h1)
			model = "balcony_modern"
		_:
			return
	if StreetLife.parts(model).is_empty():
		return
	var e := (p1 - p0) / ln
	var basis := Basis(Vector3.UP.cross(-nrm).normalized(), Vector3.UP, -nrm)   # Modell -Z = nach außen
	var c0 := int(ceil((acc - pitch * 0.5) / pitch))
	var c1 := int(floor((acc + ln - pitch * 0.5) / pitch))
	for col in range(c0, c1 + 1):
		var xc := col * pitch + pitch * 0.5
		var along := xc - acc
		if along < 1.4 or along > ln - 1.4:
			continue
		var pick := false
		match style:
			0, 6:
				pick = _h21(float(col) * 1.37, seed * 57.0) > 0.74
			1:
				pick = _h21(float(col) * 0.91, seed * 13.0) > 0.45
			2:
				# wie die Loggia-Bedingung im Shader (je 3-m-Platte)
				pick = _h21(floor(xc / 3.0), floor(seed * 40.0)) > 0.62
			3:
				pick = _h21(float(col) * 2.11, seed * 31.0) > 0.62
		if not pick:
			continue
		var r0 := 1
		var r1 := rows - (2 if rows >= 5 and style in [0, 6] else 1)
		if style == 1:
			r1 = 1
		var wp := p0 + e * along
		# Modell-Ursprung -> Geschossboden (MANIFEST floor_y): Gründerzeit-Konsole 0,76 m, Betonplatte 0,18 m,
		# französischer Balkon auf Brüstungshöhe des Fensters
		var y_off := 0.0
		var m2 := model
		match model:
			"balcony_gruenderzeit":
				y_off = -0.76
			"balcony_modern":
				y_off = -0.18
			"balcony_rail_french":
				y_off = fh * 0.17 - 0.02
			"loggia_platte":
				if _h21(float(col) * 0.7, seed * 5.0) > 0.5 and not StreetLife.parts("loggia_platte_riffel").is_empty():
					m2 = "loggia_platte_riffel"
		for r in range(r0, r1 + 1):
			var y := ref + r * fh + y_off
			var xf := Transform3D(basis, Vector3(wp.x, y, wp.y) + nrm * 0.02)
			var key := [m2, Vector2i(floori((wp.x + world_half) / CELL), floori((wp.y + world_half) / CELL))]
			if not _deco.has(key):
				_deco[key] = []
			_deco[key].append(xf)


func _edge_is(ring: Array, p0: Vector2, p1: Vector2, idx: int) -> bool:
	## Ist die (evtl. umgedrehte) Kante p0-p1 die Kante idx des Original-Rings?
	if idx < 0:
		return false
	var a := Vector2(ring[idx][0], ring[idx][1])
	var b := Vector2(ring[(idx + 1) % ring.size()][0], ring[(idx + 1) % ring.size()][1])
	return (a.distance_squared_to(p0) < 0.01 and b.distance_squared_to(p1) < 0.01) or (a.distance_squared_to(p1) < 0.01 and b.distance_squared_to(p0) < 0.01)


func _is_party(b: Dictionary, p0: Vector2, p1: Vector2) -> bool:
	## Brandwand (Kante grenzt an Nachbarhaus/-teil): Kantenmitten aus build_city ("pw").
	var pw: Array = b.get("pw", [])
	if pw.is_empty():
		return false
	var m := (p0 + p1) * 0.5
	for q in pw:
		if absf(float(q[0]) - m.x) < 0.08 and absf(float(q[1]) - m.y) < 0.08:
			return true
	return false


func _door(b: Dictionary, style: int, seed: float, p0: Vector2, p1: Vector2, ln: float, acc: float, nrm: Vector3, ref: float, shop_iv: Array) -> void:
	## Hauseingang (Portal) auf einer Fensterachse nahe der Kantenmitte, nicht vor einem Laden; dazu Hausnummer.
	var model := "door_portal" if style in [0, 1, 6] else "door_modern"
	if StreetLife.parts(model).is_empty() or style == 5:
		return
	var h1 := _h11(seed * 91.7)
	var pitch := 2.6
	match style:
		0:
			pitch = lerpf(2.3, 3.1, h1)
		1:
			pitch = lerpf(3.0, 4.2, h1)
		2:
			pitch = 1.5
		3:
			pitch = lerpf(2.2, 2.8, h1)
		4:
			pitch = 1.5
		6:
			pitch = lerpf(2.4, 3.0, h1)
	var e := (p1 - p0) / ln
	var best := -1.0
	var best_d := 1e9
	var c0 := int(ceil((acc - pitch * 0.5) / pitch))
	var c1 := int(floor((acc + ln - pitch * 0.5) / pitch))
	for col in range(c0, c1 + 1):
		var along := col * pitch + pitch * 0.5 - acc
		if along < 1.5 or along > ln - 1.5:
			continue
		var t := along / ln
		var in_shop := false
		for iv in shop_iv:
			if t > float(iv[0]) - 1.2 / ln and t < float(iv[1]) + 1.2 / ln:
				in_shop = true
		if in_shop:
			continue
		var d := absf(along - ln * 0.5)
		if d < best_d:
			best_d = d
			best = along
	if best < 0.0:
		return
	var wp := p0 + e * best
	var basis := Basis(Vector3.UP.cross(-nrm).normalized(), Vector3.UP, -nrm)
	var xf := Transform3D(basis, Vector3(wp.x, ref, wp.y) + nrm * 0.02)
	var key := [model, Vector2i(floori((wp.x + world_half) / CELL), floori((wp.y + world_half) / CELL))]
	if not _deco.has(key):
		_deco[key] = []
	_deco[key].append(xf)
	var hn: String = b.get("hn", "")
	if hn != "":
		# Dresdner Hausnummer: weiße Ziffern auf blauem Emailleschild, rechts neben der Tür
		var side := -basis.x          # vom Betrachter aus rechts
		var pos := Vector3(wp.x, ref + 2.55, wp.y) + side * 1.05 + nrm * 0.035
		_hn_plates.append([pos, basis, hn])


var _hn_plates: Array = []


func _flush_numbers() -> void:
	if _hn_plates.is_empty():
		return
	var font := load("res://assets/fonts/NotoSans-CondensedBold.ttf") as FontFile
	var mesh := BoxMesh.new()
	mesh.size = Vector3(0.24, 0.18, 0.015)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.1, 0.22, 0.52)
	mat.roughness = 0.35
	mesh.material = mat
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = mesh
	var hx: Array = []
	for e in _hn_plates:
		hx.append(Transform3D(e[1], e[0]))
	RenderUtil.fill_multimesh(mm, hx)
	for e in _hn_plates:
		var lb := {}
		lb.text = e[2]
		lb.font = font
		lb.font_size = 48
		lb.pixel_size = 0.0026
		lb.modulate = Color(0.96, 0.96, 0.96)
		lb.shaded = true
		lb.double_sided = false
		lb.visibility_range_end = 30.0
		var face: Basis = e[1]
		# Schild-Vorderseite zeigt nach außen (= -basis.z); Label3D ist von +Z lesbar -> um 180° drehen
		var fb := face * Basis(Vector3.UP, PI)
		lb.transform = Transform3D(fb, (e[0] as Vector3) - face.z * 0.01)
		_label_specs.append(lb)
	var inst := MultiMeshInstance3D.new()
	inst.multimesh = mm
	inst.visibility_range_end = 60.0
	inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(inst)
	_hn_plates.clear()


func _flush_deco() -> void:
	_flush_numbers()
	for key in _deco:
		var model: String = key[0]
		var list: Array = _deco[key]
		for part in StreetLife.parts(model):
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			mm.mesh = part["mesh"]
			RenderUtil.fill_multimesh(mm, list, part["xf"])
			var inst := MultiMeshInstance3D.new()
			inst.multimesh = mm
			inst.visibility_range_end = 420.0
			inst.visibility_range_end_margin = 40.0
			inst.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
			add_child(inst)
	_deco.clear()


func _openings(b: Dictionary, p0: Vector2, p1: Vector2, ln: float) -> Array:
	## Öffnungen in der Wandkante p0->p1 durch Durchfahrten dieses Gebäudes: [[t0, t1, y_oben], ...] sortiert.
	var res: Array = []
	var lst: Array = _pass_by_b.get(str(b["id"]), [])
	if lst.is_empty():
		return res
	var e := (p1 - p0) / ln
	for ps in lst:
		var pts: Array = ps["pts"]
		var w: float = ps["w"]
		var h: float = ps["h"]
		var n_seg := pts.size() - 1
		for i in n_seg:
			var a := Vector2(pts[i][0], pts[i][1])
			var c := Vector2(pts[i + 1][0], pts[i + 1][1])
			# Enden verlängern: das Tunnelstück endet genau an der Fassade
			var sd := (c - a).normalized()
			if i == 0:
				a -= sd * 0.8
			if i == n_seg - 1:
				c += sd * 0.8
			var hit = Geometry2D.segment_intersects_segment(p0, p1, a, c)
			if hit == null:
				continue
			var q: Vector2 = hit
			var dvec := (c - a).normalized()
			var sin_t := absf(e.cross(dvec))
			var half := (w * 0.5) / maxf(sin_t, 0.35)
			var tc := (q - p0).dot(e) / ln
			var t0 := clampf(tc - half / ln, 0.0, 1.0)
			var t1 := clampf(tc + half / ln, 0.0, 1.0)
			var seg_t := clampf((q - a).length() / maxf((c - a).length(), 0.001), 0.0, 1.0)
			var yf := lerpf(float(pts[i][2]), float(pts[i + 1][2]), seg_t)
			res.append([t0, t1, yf + h])
	res.sort_custom(func(x, y): return x[0] < y[0])
	# Überlappungen zusammenfassen
	var merged: Array = []
	for o in res:
		if not merged.is_empty() and o[0] <= merged[-1][1]:
			merged[-1][1] = maxf(merged[-1][1], o[1])
			merged[-1][2] = maxf(merged[-1][2], o[2])
		else:
			merged.append(o)
	return merged


func _wall_piece(walls: Surf, trim: Surf, p0: Vector2, p1: Vector2, ln: float, ta: float, tb: float, y_bot: float, y_top: float,
		nrm: Vector3, col: Color, acc: float, v0: float, ref: float, uv2: Vector2, tang: Vector3, do_trim: bool,
		tdir: Vector2, eave_h: float, style: int, trim_col: Color) -> void:
	if tb - ta < 0.01:
		return
	var qa := p0.lerp(p1, ta)
	var qb := p0.lerp(p1, tb)
	var v1 := y_top - ref
	walls.quad(Vector3(qa.x, y_bot, qa.y), Vector3(qb.x, y_bot, qb.y), Vector3(qb.x, y_top, qb.y), Vector3(qa.x, y_top, qa.y),
		nrm, col, [Vector2(acc + ln * ta, v0), Vector2(acc + ln * tb, v0), Vector2(acc + ln * tb, v1), Vector2(acc + ln * ta, v1)], uv2, tang)
	if do_trim and (tb - ta) * ln > 1.2:
		_trim_strip(trim, qa, qb, tdir, nrm, ref, y_top, eave_h, style, trim_col)


func _tunnel(tun: Surf, ps: Dictionary, col: Color) -> void:
	## Seitenwände (nach innen) und Decke (nach unten) entlang einer Durchfahrt.
	var pts: Array = ps["pts"]
	var hw: float = float(ps["w"]) * 0.5
	var h: float = ps["h"]
	for i in pts.size() - 1:
		var a := Vector3(pts[i][0], pts[i][2], pts[i][1])
		var c := Vector3(pts[i + 1][0], pts[i + 1][2], pts[i + 1][1])
		var d := Vector3(c.x - a.x, 0.0, c.z - a.z)
		if d.length() < 0.05:
			continue
		d = d.normalized()
		var left := Vector3(-d.z, 0.0, d.x)
		var top := maxf(a.y, c.y) + h
		var la := a + left * hw
		var lc := c + left * hw
		var ra := a - left * hw
		var rc := c - left * hw
		var z0 := Vector2.ZERO
		var uvs := [z0, z0, z0, z0]
		tun.quad(Vector3(la.x, a.y - 0.3, la.z), Vector3(lc.x, c.y - 0.3, lc.z), Vector3(lc.x, top, lc.z), Vector3(la.x, top, la.z), -left, col, uvs, Vector2.ZERO, d)
		tun.quad(Vector3(ra.x, a.y - 0.3, ra.z), Vector3(rc.x, c.y - 0.3, rc.z), Vector3(rc.x, top, rc.z), Vector3(ra.x, top, ra.z), left, col, uvs, Vector2.ZERO, d)
		tun.quad(Vector3(la.x, top, la.z), Vector3(lc.x, top, lc.z), Vector3(rc.x, top, rc.z), Vector3(ra.x, top, ra.z), Vector3.DOWN, col.darkened(0.15), uvs, Vector2.ZERO, d)


func _trim_strip(trim: Surf, p0: Vector2, p1: Vector2, tdir: Vector2, nrm: Vector3, ref: float, y_top: float, eave_h: float, style: int, col: Color) -> void:
	## Kranzgesims oben und Sockel unten als vorspringende Streifen.
	var ext := Vector3(tdir.x, 0.0, tdir.y)
	var a := Vector3(p0.x, 0, p0.y)
	var b := Vector3(p1.x, 0, p1.y)
	# Kranzgesims (alle außer Glas/Plattenbau flach)
	var ch := 0.5
	var cp := 0.32
	if style == 2:
		ch = 0.3
		cp = 0.12
	elif style == 4:
		ch = 0.35
		cp = 0.08
	elif style == 1:
		ch = 0.85
		cp = 0.5
	elif style == 0 or style == 6:
		ch = 0.65
		cp = 0.38
	elif style == 3:
		ch = 0.4
		cp = 0.22
	if eave_h > 4.0:
		_box_strip(trim, a - ext * cp * 0.6, b + ext * cp * 0.6, nrm, y_top - ch, y_top + 0.04, cp, col)
	# Sockel
	if style in [0, 1, 3, 6] and eave_h > 5.0:
		# Sockel: dunklerer, grauerer Naturstein als die Gesimse
		var sc := col.darkened(0.24).lerp(Color(0.5, 0.49, 0.47), 0.25)
		_box_strip(trim, a, b, nrm, ref - 0.35, ref + 0.95, 0.07, sc)
	# Geschossband (Gründerzeit/Barock): dünn, jedes Geschoss
	if style in [0, 1] and eave_h > 7.5:
		var floors := int(eave_h / 3.4)
		for f in range(1, floors):
			var yb := ref + f * (eave_h / floors) - 0.05
			_box_strip(trim, a, b, nrm, yb, yb + 0.16, 0.05, col)


func _box_strip(s: Surf, a: Vector3, b: Vector3, nrm: Vector3, y0: float, y1: float, prot: float, col: Color) -> void:
	var o := nrm * prot
	var tdir := (b - a).normalized()
	var ua := Vector2(0, 0)
	# Vorderseite
	s.quad(Vector3(a.x, y0, a.z) + o, Vector3(b.x, y0, b.z) + o, Vector3(b.x, y1, b.z) + o, Vector3(a.x, y1, a.z) + o, nrm, col, [ua, ua, ua, ua], Vector2.ZERO, tdir)
	# Oberseite
	s.quad(Vector3(a.x, y1, a.z), Vector3(b.x, y1, b.z), Vector3(b.x, y1, b.z) + o, Vector3(a.x, y1, a.z) + o, Vector3.UP, col, [ua, ua, ua, ua], Vector2.ZERO, tdir)
	# Unterseite
	s.quad(Vector3(a.x, y0, a.z) + o, Vector3(b.x, y0, b.z) + o, Vector3(b.x, y0, b.z), Vector3(a.x, y0, a.z), Vector3.DOWN, col, [ua, ua, ua, ua], Vector2.ZERO, tdir)
	# Stirnseiten (sonst wirkt der Streifen am Ende wie eine lose Platte)
	var ce := col.darkened(0.12)
	s.quad(Vector3(a.x, y0, a.z), Vector3(a.x, y0, a.z) + o, Vector3(a.x, y1, a.z) + o, Vector3(a.x, y1, a.z), -tdir, ce, [ua, ua, ua, ua], Vector2.ZERO, nrm)
	s.quad(Vector3(b.x, y0, b.z), Vector3(b.x, y1, b.z), Vector3(b.x, y1, b.z) + o, Vector3(b.x, y0, b.z) + o, tdir, ce, [ua, ua, ua, ua], Vector2.ZERO, nrm)


func _dormers(walls: Surf, rv: PackedVector3Array, rn: PackedVector3Array, rc: PackedColorArray, ri: PackedInt32Array, rinfo: Dictionary, ref: float, eave: float, wall_col: Color, roof_col: Color, seed01: float) -> void:
	var c: Array = rinfo["c"]
	var u := Vector2(rinfo["u"][0], rinfo["u"][1])
	var L: float = rinfo["L"]
	var S: float = rinfo["S"]
	var rh: float = rinfo["rh"]
	var shape: String = rinfo["shape"]
	var vdir := Vector2(-u.y, u.x)
	var spacing := 5.2 + 1.6 * fposmod(seed01 * 13.0, 1.0)
	var count := int((L - 4.0) / spacing)
	if count < 1:
		return
	var start := -spacing * (count - 1) * 0.5
	var dcol := wall_col
	dcol.a = 7.0 + 0.02 + 0.96 * seed01
	var cur_prev: Color = walls.cur
	walls.cur = Color(0.0, 7.0, seed01, 0.0)          # Gaube (Stil 7) über CUSTOM0
	var uvh := Vector2(1.0, 2.6)
	for side_v in [1.0, -1.0]:
		var side: float = side_v
		for k in count:
			var a_pos: float = start + spacing * k
			# bei Walmdach keine Gauben im Firstbereich der Stirnseiten
			if shape == "hipped" and absf(a_pos) > L * 0.5 - S * 0.5 - 0.8:
				continue
			var frac := 0.62
			var b_front: float = side * (S * 0.5) * frac
			var y_r := ref + eave + rh * (1.0 - frac)
			var w := 1.25
			var hh := 1.45
			var depth := 1.35
			var base := Vector2(c[0], c[1]) + u * a_pos + vdir * b_front
			var out := vdir * side
			var Lw := u * (w * 0.5)
			var front_l := base + Lw
			var front_r := base - Lw
			var back_l := front_l - out * depth
			var back_r := front_r - out * depth
			var yb := y_r - 0.25
			var yt := y_r + hh
			var n_out := Vector3(out.x, 0, out.y)
			var tang := Vector3(-u.x, 0, -u.y)
			var tu := 50.0 - w * 0.5
			# Stirnwand mit Fenster (Stil 7)
			walls.quad(Vector3(front_l.x, yb, front_l.y), Vector3(front_r.x, yb, front_r.y),
				Vector3(front_r.x, yt, front_r.y), Vector3(front_l.x, yt, front_l.y),
				n_out, dcol, [Vector2(tu, 0), Vector2(tu + w, 0), Vector2(tu + w, hh + 0.25), Vector2(tu, hh + 0.25)], uvh, tang)
			# Seitenwände
			var nl := Vector3(u.x, 0, u.y)
			walls.quad(Vector3(front_l.x, yb, front_l.y), Vector3(back_l.x, yb, back_l.y), Vector3(back_l.x, yt, back_l.y), Vector3(front_l.x, yt, front_l.y),
				nl, dcol, [Vector2(0, 0), Vector2(1, 0), Vector2(1, 1), Vector2(0, 1)], uvh, Vector3(-n_out.x, 0, -n_out.z))
			walls.quad(Vector3(front_r.x, yb, front_r.y), Vector3(back_r.x, yb, back_r.y), Vector3(back_r.x, yt, back_r.y), Vector3(front_r.x, yt, front_r.y),
				-nl, dcol, [Vector2(0, 0), Vector2(1, 0), Vector2(1, 1), Vector2(0, 1)], uvh, Vector3(-n_out.x, 0, -n_out.z))
			# Satteldach der Gaube (First nach hinten)
			var ridge_f := Vector3(base.x, yt + 0.62, base.y)
			var ridge_b := Vector3(base.x - out.x * depth, yt + 0.62, base.y - out.y * depth)
			var fl := Vector3(front_l.x, yt, front_l.y)
			var fr := Vector3(front_r.x, yt, front_r.y)
			var bl := Vector3(back_l.x, yt, back_l.y)
			var br := Vector3(back_r.x, yt, back_r.y)
			_roof_quad(rv, rn, rc, ri, fl, bl, ridge_b, ridge_f, roof_col)
			_roof_quad(rv, rn, rc, ri, fr, ridge_f, ridge_b, br, roof_col)
			# Giebeldreieck vorn
			_roof_tri(rv, rn, rc, ri, fl, ridge_f, fr, wall_col)
	walls.cur = cur_prev


func _roof_quad(rv: PackedVector3Array, rn: PackedVector3Array, rc: PackedColorArray, ri: PackedInt32Array, a: Vector3, b: Vector3, c: Vector3, d: Vector3, col: Color) -> void:
	_roof_tri(rv, rn, rc, ri, a, b, c, col)
	_roof_tri(rv, rn, rc, ri, a, c, d, col)


func _roof_tri(rv: PackedVector3Array, rn: PackedVector3Array, rc: PackedColorArray, ri: PackedInt32Array, a: Vector3, b: Vector3, c: Vector3, col: Color) -> void:
	# Orientierung: Normale nach oben/außen (grob: y>=0 bevorzugt)
	var fn := _front_normal(a, b, c)
	var k := rv.size()
	if fn.y < -0.05 or (absf(fn.y) <= 0.05 and false):
		var tmp := b
		b = c
		c = tmp
		fn = _front_normal(a, b, c)
	var nn := fn.normalized()
	rv.append(a)
	rv.append(b)
	rv.append(c)
	for q in 3:
		rn.append(nn)
		rc.append(col)
	ri.append_array([k, k + 1, k + 2])


# --- Beschriftungen erst im Haupt-Thread erzeugen ---------------------------------------------
# Label3D/Schriftarten im Kachel-Thread anzulegen ist nicht threadsicher (Text-Server/Theme-Signale laufen
# über /root). Der Kachel-Thread sammelt daher nur Eigenschaften; erzeugt wird nach dem Einhängen.
var _label_specs: Array = []


func _ready() -> void:
	set_process(not _label_specs.is_empty())


static var label_ms := 0.0     # Diagnose: Zeit für Beschriftungen in diesem Bild (DriveBench liest/leert)


func _process(_delta: float) -> void:
	var n := 0
	var t0 := Time.get_ticks_usec()
	while n < 120 and not _label_specs.is_empty():
		var spec: Dictionary = _label_specs.pop_back()
		var lb := Label3D.new()
		for k in spec:
			lb.set(k, spec[k])
		add_child(lb)
		n += 1
	label_ms += (Time.get_ticks_usec() - t0) / 1000.0
	if _label_specs.is_empty():
		set_process(false)
