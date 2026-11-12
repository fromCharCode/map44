class_name Roads
extends Node3D
## Fahrbahnmarkierungen, Zebrastreifen, Brücken und Gleise.

const CELL := 250.0

var terrain: Terrain
var city: Dictionary
var index: RoadIndex
var mark_mat: StandardMaterial3D
var rail_mat: StandardMaterial3D
var deck_mat: StandardMaterial3D
var stone_mat: StandardMaterial3D
var concrete_mat: StandardMaterial3D
var concrete_dark_mat: StandardMaterial3D
var junctions: Dictionary = {}

# Sammler je Zelle
var _mk: Dictionary = {}
var _rl: Dictionary = {}


func build(t: Terrain, c: Dictionary, idx: RoadIndex) -> void:
	terrain = t
	city = c
	index = idx
	_materials()
	_find_junctions()
	for r in city["roads"]:
		_markings(r)
	_crossings()
	for rl in city["rails"]:
		if not rl["bridge"]:
			_rail(rl)
	_flush(_mk, mark_mat, 230.0)
	_flush(_rl, rail_mat, 260.0)
	for b in city["bridges"]:
		_bridge(b)
	var arches: Dictionary = city.get("bridge_arches", {})
	var stone_parts := {}
	for pid in arches.get("lod2", []):
		stone_parts[String(pid)] = true
	for bm in city.get("bridge_meshes", []):
		_lod2_bridge(bm, stone_parts.has(String(bm.get("id", ""))))
	var slab_ids := {}
	for b in city["bridges"]:
		slab_ids[b["id"]] = true
	for wid in arches.get("ways", []):
		slab_ids[int(wid)] = true                  # Bogenbrücken: Pfeiler kommen aus bridge_arches
	for r in city["roads"]:
		if r["bridge"] and not slab_ids.has(r["id"]):
			_piers(r["pts"], float(r["width"]) + 2.0, 1.0)
	_bridge_rails(city.get("bridge_rails", []))
	_curbs(city.get("curbs", []))
	_bridge_arches(city.get("bridge_arches", {}))


func _materials() -> void:
	mark_mat = StandardMaterial3D.new()
	mark_mat.albedo_color = Color(0.9, 0.9, 0.87)
	mark_mat.roughness = 0.5
	mark_mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	mark_mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_OPAQUE_ONLY
	rail_mat = StandardMaterial3D.new()
	rail_mat.albedo_color = Color(0.42, 0.42, 0.44)
	rail_mat.metallic = 0.85
	rail_mat.roughness = 0.35
	deck_mat = _tri_mat("asphalt_new", 4.0, 1.4)
	stone_mat = _tri_mat("sandstone", 2.0, 1.0)
	concrete_mat = _tri_mat("concrete", 2.0, 1.1)
	concrete_dark_mat = _tri_mat("concrete", 2.0, 0.6)


func _tri_mat(name: String, _tile: float, boost: float) -> StandardMaterial3D:
	return TexLib.tri_material(name, boost)     # gemeinsam für alle Kacheln (komprimiert, einmal geladen)


func _find_junctions() -> void:
	var cnt := {}
	for e in city["graph"]["edges"]:
		cnt[e["a"]] = cnt.get(e["a"], 0) + 1
		cnt[e["b"]] = cnt.get(e["b"], 0) + 1
	for n in city["graph"]["nodes"]:
		if cnt.get(n["id"], 0) >= 3:
			junctions[n["id"]] = Vector2(n["pos"][0], n["pos"][2])


var _jgrid := {}                 # Rasterzelle (16 m) -> Kreuzungspunkte


func _near_junction(x: float, z: float, rad: float) -> bool:
	## Raster statt Schleife über alle Kreuzungen (vorher ~80 Mio. Vergleiche je Kachel, 4–5 s)
	if _jgrid.is_empty() and not junctions.is_empty():
		for j in junctions.values():
			var k := Vector2i(floori(j.x / 16.0), floori(j.y / 16.0))
			if not _jgrid.has(k):
				_jgrid[k] = []
			_jgrid[k].append(j)
	var p := Vector2(x, z)
	var r := int(ceil(rad / 16.0))
	var cx := floori(x / 16.0)
	var cz := floori(z / 16.0)
	for ix in range(cx - r, cx + r + 1):
		for iz in range(cz - r, cz + r + 1):
			var lst = _jgrid.get(Vector2i(ix, iz))
			if lst == null:
				continue
			for j in lst:
				if p.distance_squared_to(j) < rad * rad:
					return true
	return false


func _cell(x: float, z: float) -> Vector2i:
	return Vector2i(floori((x + 1000.0) / CELL), floori((z + 1000.0) / CELL))


func _bucket(d: Dictionary, key: Vector2i) -> Dictionary:
	if not d.has(key):
		d[key] = {"v": PackedVector3Array(), "i": PackedInt32Array()}
	return d[key]


func _quad(b: Dictionary, p0: Vector3, p1: Vector3, p2: Vector3, p3: Vector3) -> void:
	## Vier Punkte, gegen den Uhrzeigersinn von oben; Vorderseite nach oben.
	var k: int = b["v"].size()
	b["v"].append(p0)
	b["v"].append(p1)
	b["v"].append(p2)
	b["v"].append(p3)
	var n := (p1 - p0).cross(p3 - p0)
	if n.y > 0.0:
		b["i"].append_array([k, k + 2, k + 1, k, k + 3, k + 2])
	else:
		b["i"].append_array([k, k + 1, k + 2, k, k + 2, k + 3])


func _gy(x: float, z: float) -> float:
	return terrain.height_at(x, z) + 0.05


func _line_strip(bucket_map: Dictionary, pts: Array, offset: float, width: float, dash_on: float, dash_off: float, skip_junction: float, on_deck: bool = false) -> void:
	## Streifen entlang einer Polylinie (seitlich versetzt), optional gestrichelt.
	var samples: Array = []   # [x, z]
	var tan_list: Array = []
	var y_list: Array = []
	var total := 0.0
	for i in pts.size() - 1:
		total += Vector2(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]).length()
	if total < 8.0:
		return
	var step := 1.0
	for i in pts.size() - 1:
		var a := Vector2(pts[i][0], pts[i][1])
		var b := Vector2(pts[i + 1][0], pts[i + 1][1])
		var l := a.distance_to(b)
		if l < 0.01:
			continue
		var t := (b - a) / l
		var n := Vector2(-t.y, t.x)
		var d := 0.0
		while d < l:
			var p := a + t * d + n * offset
			samples.append(p)
			tan_list.append(t)
			y_list.append(lerpf(float(pts[i][2]), float(pts[i + 1][2]), d / l))
			d += step
	if samples.size() < 3:
		return
	var period := dash_on + dash_off
	for i in samples.size() - 1:
		var p0: Vector2 = samples[i]
		var p1: Vector2 = samples[i + 1]
		if dash_off > 0.0:
			var ph := fposmod(float(i) * step, period)
			if ph > dash_on:
				continue
		if skip_junction > 0.0 and _near_junction(p0.x, p0.y, skip_junction):
			continue
		var t0: Vector2 = tan_list[i]
		var t1: Vector2 = tan_list[i + 1]
		var n0 := Vector2(-t0.y, t0.x) * width * 0.5
		var n1 := Vector2(-t1.y, t1.x) * width * 0.5
		var b := _bucket(bucket_map, _cell(p0.x, p0.y))
		if on_deck:
			var y0 := float(y_list[i]) + 0.05
			var y1 := float(y_list[i + 1]) + 0.05
			_quad(b, Vector3(p0.x - n0.x, y0, p0.y - n0.y), Vector3(p1.x - n1.x, y1, p1.y - n1.y),
				Vector3(p1.x + n1.x, y1, p1.y + n1.y), Vector3(p0.x + n0.x, y0, p0.y + n0.y))
			continue
		_quad(b,
			Vector3(p0.x - n0.x, _gy(p0.x - n0.x, p0.y - n0.y), p0.y - n0.y),
			Vector3(p1.x - n1.x, _gy(p1.x - n1.x, p1.y - n1.y), p1.y - n1.y),
			Vector3(p1.x + n1.x, _gy(p1.x + n1.x, p1.y + n1.y), p1.y + n1.y),
			Vector3(p0.x + n0.x, _gy(p0.x + n0.x, p0.y + n0.y), p0.y + n0.y))


func _markings(r: Dictionary) -> void:
	var cls: String = r["cls"]
	var w: float = r["width"]
	if cls in ["service", "living_street", "motorway_link", "trunk_link"] or w < 5.0:
		return
	var pts: Array = r["pts"]
	var deck: bool = bool(r["bridge"])
	var edge := cls in ["primary", "secondary", "tertiary", "trunk", "motorway"] and w >= 6.5
	if int(r["oneway"]) == 0 and w >= 5.4:
		_line_strip(_mk, pts, 0.0, 0.12, 3.0, 6.0, w * 0.5 + 3.0, deck)
	elif int(r["oneway"]) != 0 and int(r["lanes"]) >= 2:
		_line_strip(_mk, pts, 0.0, 0.12, 3.0, 6.0, w * 0.5 + 3.0, deck)
	if edge:
		_line_strip(_mk, pts, w * 0.5 - 0.3, 0.13, 0.0, 0.0, w * 0.5 + 2.5, deck)
		_line_strip(_mk, pts, -(w * 0.5 - 0.3), 0.13, 0.0, 0.0, w * 0.5 + 2.5, deck)


func _crossings() -> void:
	for c in city["crossings"]:
		var hit := index.nearest(c[0], c[1], 2.0)
		if hit.is_empty():
			continue
		var r: Dictionary = hit["road"]
		if r["cls"] == "service" and r["width"] < 4.0:
			continue
		var w: float = r["width"]
		var t := Vector2(hit["tx"], hit["tz"])
		var n := Vector2(-t.y, t.x)
		var ctr := Vector2(hit["px"], hit["pz"])
		var s := -w * 0.5 + 0.5
		while s < w * 0.5 - 0.3:
			var q := ctr + n * s
			var h := t * 1.6
			var hw := n * 0.25
			var b := _bucket(_mk, _cell(q.x, q.y))
			var corners: Array = [q - h - hw, q + h - hw, q + h + hw, q - h + hw]
			var vs: Array[Vector3] = []
			for cc in corners:
				vs.append(Vector3(cc.x, _gy(cc.x, cc.y) + 0.005, cc.y))
			_quad(b, vs[0], vs[1], vs[2], vs[3])
			s += 1.0


func _rail(rl: Dictionary) -> void:
	var pts: Array = rl["pts"]
	for off in [-0.7175, 0.7175]:
		_line_strip(_rl, pts, off, 0.075, 0.0, 0.0, 0.0)


func _flush(buckets: Dictionary, mat: Material, range_end: float) -> void:
	for key in buckets:
		var b: Dictionary = buckets[key]
		if b["v"].is_empty():
			continue
		var norms := PackedVector3Array()
		norms.resize(b["v"].size())
		norms.fill(Vector3.UP)
		var arr := []
		arr.resize(Mesh.ARRAY_MAX)
		arr[Mesh.ARRAY_VERTEX] = b["v"]
		arr[Mesh.ARRAY_NORMAL] = norms
		arr[Mesh.ARRAY_INDEX] = b["i"]
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		mi.material_override = mat
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mi.visibility_range_end = range_end
		mi.visibility_range_end_margin = 30.0
		mi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
		add_child(mi)


func _tris_to_surface(flat: Array, uv_mode: int) -> Dictionary:
	## flat: [x,y,z,...] je 3 Punkte = Dreieck. uv_mode 0: Draufsicht, 1: Seitenansicht.
	var v := PackedVector3Array()
	var n := PackedVector3Array()
	var uv := PackedVector2Array()
	var faces := PackedVector3Array()
	var cnt := flat.size() / 9
	for t in cnt:
		var a := Vector3(flat[t * 9], flat[t * 9 + 1], flat[t * 9 + 2])
		var b := Vector3(flat[t * 9 + 3], flat[t * 9 + 4], flat[t * 9 + 5])
		var c := Vector3(flat[t * 9 + 6], flat[t * 9 + 7], flat[t * 9 + 8])
		var fn := -(b - a).cross(c - a)
		if fn.length_squared() < 1e-10:
			continue
		fn = fn.normalized()
		for p in [a, b, c]:
			v.append(p)
			n.append(fn)
			faces.append(p)
			if uv_mode == 0:
				uv.append(Vector2(p.x, p.z) * 0.25)
			else:
				uv.append(Vector2(p.x + p.z, p.y) * 0.4)
	return {"v": v, "n": n, "uv": uv, "faces": faces}


static var _masonry: Material


static func masonry_mat() -> Material:
	## patinierter Elbsandstein der historischen Brücken (#7a6a5c, dunkler als Fassaden-Sandstein)
	if _masonry == null:
		_masonry = TexLib.tri_material("sandstone", 0.6)
	return _masonry


func _lod2_bridge(bm: Dictionary, stone := false) -> void:
	var mesh := ArrayMesh.new()
	var all_faces := PackedVector3Array()
	var mats: Array = [deck_mat, concrete_mat, concrete_dark_mat]
	if stone:
		mats = [deck_mat, masonry_mat(), masonry_mat()]
	var keys := ["top", "side", "bot"]
	for i in 3:
		var flat: Array = bm[keys[i]]
		if flat.size() < 9:
			continue
		var sf := _tris_to_surface(flat, 0 if i == 0 else 1)
		if (sf["v"] as PackedVector3Array).is_empty():
			continue
		var arr := []
		arr.resize(Mesh.ARRAY_MAX)
		arr[Mesh.ARRAY_VERTEX] = sf["v"]
		arr[Mesh.ARRAY_NORMAL] = sf["n"]
		arr[Mesh.ARRAY_TEX_UV] = sf["uv"]
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
		mesh.surface_set_material(mesh.get_surface_count() - 1, mats[i])
		all_faces.append_array(sf["faces"])
	if mesh.get_surface_count() == 0:
		return
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	add_child(mi)
	var body := StaticBody3D.new()
	body.collision_layer = 1
	var cs := CollisionShape3D.new()
	var sh := ConcavePolygonShape3D.new()
	sh.backface_collision = true
	sh.set_faces(all_faces)
	cs.shape = sh
	body.add_child(cs)
	mi.add_child(body)


func _bridge_rails(rails: Array) -> void:
	## Brückengeländer entlang der Deckkanten, Bauart je Brücke (Pipeline tools/bridge_styles.py, Recherche
	## data/research/bruecken.json): [ax, az, bx, bz, y, art, farbe]
	##   stone = Sandsteinbrüstung (1,05 m), concrete = Betonschutzwand (0,9 m),
	##   steel = Betonkappe + Stahlgeländer (Pfosten alle 2 m, Handlauf, Füllstäbe) in der Farbe der Brücke.
	if rails.is_empty():
		return
	var walls := {"stone": [], "concrete": []}
	var steel: Array = []
	for r in rails:
		var art := String(r[5]) if r.size() > 5 else "stone"
		if art == "steel" or art == "glass":
			steel.append(r)
		else:
			walls["concrete" if art == "concrete" else "stone"].append(r)
	var faces := PackedVector3Array()
	for art in walls:
		if not (walls[art] as Array).is_empty():
			_rail_walls(walls[art], 1.05 if art == "stone" else 0.9, 0.18, stone_mat if art == "stone" else _concrete_mat(), faces)
	if not steel.is_empty():
		_rail_steel(steel, faces)
	if faces.is_empty():
		return
	var body := StaticBody3D.new()
	body.collision_layer = 1
	var cs := CollisionShape3D.new()
	var sh := ConcavePolygonShape3D.new()
	sh.backface_collision = true
	sh.set_faces(faces)
	cs.shape = sh
	body.add_child(cs)
	add_child(body)


func _rail_walls(rails: Array, h: float, th: float, mat: Material, faces: PackedVector3Array) -> void:
	var v := PackedVector3Array()
	var n := PackedVector3Array()
	var uv := PackedVector2Array()
	for r in rails:
		var a := Vector2(r[0], r[1])
		var b := Vector2(r[2], r[3])
		var y: float = r[4]
		var d := b - a
		var L := d.length()
		if L < 0.5:
			continue
		var t := d / L
		var nn := Vector2(-t.y, t.x)
		var p0 := Vector3(a.x, y, a.y)
		var p1 := Vector3(b.x, y, b.y)
		var o := Vector3(nn.x, 0, nn.y) * th
		var up := Vector3(0, h, 0)
		var quads := [
			[p0 + o, p1 + o, p1 + o + up, p0 + o + up, Vector3(nn.x, 0, nn.y)],
			[p1 - o, p0 - o, p0 - o + up, p1 - o + up, Vector3(-nn.x, 0, -nn.y)],
			[p0 - o + up, p1 - o + up, p1 + o + up, p0 + o + up, Vector3.UP],
		]
		for q in quads:
			var qn: Vector3 = q[4]
			var pts := [q[0], q[1], q[2], q[3]]
			var order := [0, 1, 2, 0, 2, 3]
			if -(pts[1] - pts[0]).cross(pts[2] - pts[0]).dot(qn) < 0.0:
				order = [0, 2, 1, 0, 3, 2]
			for k in order:
				v.append(pts[k])
				n.append(qn)
				uv.append(Vector2(pts[k].x + pts[k].z, pts[k].y) * 0.4)
				faces.append(pts[k])
	if v.is_empty():
		return
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = v
	arr[Mesh.ARRAY_NORMAL] = n
	arr[Mesh.ARRAY_TEX_UV] = uv
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	mesh.surface_set_material(0, mat)
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	add_child(mi)


static var _rail_mats := {}
static var _bars_tex: ImageTexture


static func _concrete_mat() -> Material:
	if not _rail_mats.has("concrete"):
		_rail_mats["concrete"] = TexLib.tri_material("concrete", 0.92)
	return _rail_mats["concrete"]


static func _steel_mats(col: Color) -> Array:
	## [Rohre/Pfosten, Füllstäbe (Alpha-Schnitt)] in der Brückenfarbe, je Farbe geteilt
	var key := col.to_html(false)
	if _rail_mats.has(key):
		return _rail_mats[key]
	var m := StandardMaterial3D.new()
	m.albedo_color = col
	m.metallic = 0.55
	m.roughness = 0.45
	if _bars_tex == null:
		# senkrechte Füllstäbe: 16 mm Stab je 12 cm (Textur 64 px breit = 0,12 m)
		var img := Image.create_empty(64, 4, false, Image.FORMAT_RGBA8)
		for x in 64:
			var on := x < 10
			for yy in 4:
				img.set_pixel(x, yy, Color(1, 1, 1, 1.0 if on else 0.0))
		img.generate_mipmaps()
		_bars_tex = ImageTexture.create_from_image(img)
	var f := StandardMaterial3D.new()
	f.albedo_color = col
	f.albedo_texture = _bars_tex
	f.metallic = 0.5
	f.roughness = 0.5
	f.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	f.alpha_scissor_threshold = 0.5
	f.cull_mode = BaseMaterial3D.CULL_DISABLED
	f.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	_rail_mats[key] = [m, f]
	return _rail_mats[key]


func _rail_steel(rails: Array, faces: PackedVector3Array) -> void:
	var by_col := {}
	for r in rails:
		var c := String(r[6]) if r.size() > 6 else "#6E7378"
		if not by_col.has(c):
			by_col[c] = []
		by_col[c].append(r)
	var kappe := SurfaceTool.new()
	kappe.begin(Mesh.PRIMITIVE_TRIANGLES)
	for c in by_col:
		var tube := SurfaceTool.new()
		tube.begin(Mesh.PRIMITIVE_TRIANGLES)
		var fill := SurfaceTool.new()
		fill.begin(Mesh.PRIMITIVE_TRIANGLES)
		var glass_st := SurfaceTool.new()
		glass_st.begin(Mesh.PRIMITIVE_TRIANGLES)
		for r in by_col[c]:
			var a := Vector2(r[0], r[1])
			var b := Vector2(r[2], r[3])
			var y: float = r[4]
			var d := b - a
			var L := d.length()
			if L < 0.3:
				continue
			var t := d / L
			var t3 := Vector3(t.x, 0, t.y)
			var nn := Vector3(-t.y, 0, t.x)
			var p0 := Vector3(a.x, y, a.y)
			var p1 := Vector3(b.x, y, b.y)
			var glass: bool = r.size() > 5 and String(r[5]) == "glass"
			var top: float = clampf(float(r[7]) if r.size() > 7 else 1.1, 0.9, 4.5) + 0.22
			# Betonkappe 0,22 m hoch, 0,30 m breit
			_box_between(kappe, p0, p1, nn, 0.30, 0.0, 0.22)
			var y0 := 0.22
			# Handlauf/Oberholm und Untergurt
			_box_between(tube, p0 + Vector3(0, top - 0.06, 0), p1 + Vector3(0, top - 0.06, 0), nn, 0.07, 0.0, 0.06)
			_box_between(tube, p0 + Vector3(0, y0 + 0.08, 0), p1 + Vector3(0, y0 + 0.08, 0), nn, 0.05, 0.0, 0.05)
			# Pfosten alle 2 m
			var k := 0.0
			while k <= L + 0.01:
				var pp := p0 + t3 * minf(k, L)
				_box_between(tube, pp - t3 * 0.035, pp + t3 * 0.035, nn, 0.06 if not glass else 0.10, y0, top - 0.06)
				k += 2.0
			# Füllung: Stäbe (Alpha-Schnitt, 0,12 m je Wiederholung) bzw. Glas
			var q := [p0 + Vector3(0, y0 + 0.13, 0), p1 + Vector3(0, y0 + 0.13, 0), p1 + Vector3(0, top - 0.06, 0), p0 + Vector3(0, top - 0.06, 0)]
			var u1 := L / 0.12
			var uvs := [Vector2(0, 1), Vector2(u1, 1), Vector2(u1, 0), Vector2(0, 0)]
			var target: SurfaceTool = glass_st if glass else fill
			for idx in [0, 1, 2, 0, 2, 3]:
				target.set_normal(nn)
				target.set_uv(uvs[idx])
				target.add_vertex(q[idx])
			# Kollision: dünne Wand bis Oberkante
			var hv := Vector3(0, top, 0)
			for w in [p0, p1, p1 + hv, p0, p1 + hv, p0 + hv]:
				faces.append(w)
		var mats := _steel_mats(Color(c))
		var m1 := tube.commit()
		if m1.get_surface_count() > 0:
			m1.surface_set_material(0, mats[0])
			var mi := MeshInstance3D.new()
			mi.mesh = m1
			mi.visibility_range_end = 450.0
			add_child(mi)
		var mg := glass_st.commit()
		if mg.get_surface_count() > 0:
			if not _rail_mats.has("glass"):
				var gm := StandardMaterial3D.new()
				gm.albedo_color = Color(0.78, 0.86, 0.88, 0.22)
				gm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
				gm.roughness = 0.05
				gm.metallic_specular = 0.8
				gm.cull_mode = BaseMaterial3D.CULL_DISABLED
				_rail_mats["glass"] = gm
			mg.surface_set_material(0, _rail_mats["glass"])
			var mig := MeshInstance3D.new()
			mig.mesh = mg
			mig.visibility_range_end = 450.0
			mig.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			add_child(mig)
		var m2 := fill.commit()
		if m2.get_surface_count() > 0:
			m2.surface_set_material(0, mats[1])
			var mi2 := MeshInstance3D.new()
			mi2.mesh = m2
			mi2.visibility_range_end = 300.0
			mi2.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			add_child(mi2)
	var mk := kappe.commit()
	if mk.get_surface_count() > 0:
		mk.surface_set_material(0, _concrete_mat())
		var mi3 := MeshInstance3D.new()
		mi3.mesh = mk
		add_child(mi3)


static func _box_between(st: SurfaceTool, a: Vector3, b: Vector3, side: Vector3, w: float, y0: float, y1: float) -> void:
	## Quader von a nach b (horizontal), Breite w quer (side), Höhe y0..y1 über a/b
	var o := side.normalized() * (w * 0.5)
	var c := [a - o + Vector3(0, y0, 0), b - o + Vector3(0, y0, 0), b + o + Vector3(0, y0, 0), a + o + Vector3(0, y0, 0)]
	var hv := Vector3(0, y1 - y0, 0)
	var u := [c[0] + hv, c[1] + hv, c[2] + hv, c[3] + hv]
	var quads := [[c[0], c[1], u[1], u[0]], [c[2], c[3], u[3], u[2]], [c[1], c[2], u[2], u[1]], [c[3], c[0], u[0], u[3]], [u[0], u[1], u[2], u[3]]]
	for q in quads:
		var nrm: Vector3 = (q[1] - q[0]).cross(q[2] - q[0]).normalized()
		for idx in [0, 1, 2, 0, 2, 3, 0, 2, 1, 0, 3, 2]:
			st.set_normal(nrm)
			st.add_vertex(q[idx])


func _bridge(b: Dictionary) -> void:
	var pts: Array = b["pts"]
	if pts.size() < 2:
		return
	var w: float = max(b["width"], 2.5)
	if b["kind"] == "drive":
		w += 2.0   # Gehwege/Brüstung
	var verts := PackedVector3Array()
	var norms := PackedVector3Array()
	var uvs := PackedVector2Array()
	var idx := PackedInt32Array()
	var sv := PackedVector3Array()
	var sn := PackedVector3Array()
	var si := PackedInt32Array()
	var faces := PackedVector3Array()
	var acc := 0.0
	var thick := 0.9
	var prev_l := Vector3.ZERO
	var prev_r := Vector3.ZERO
	for i in pts.size():
		var p := Vector3(pts[i][0], pts[i][2], pts[i][1])
		var t2: Vector2
		if i == 0:
			t2 = Vector2(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
		elif i == pts.size() - 1:
			t2 = Vector2(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
		else:
			t2 = Vector2(pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1])
		t2 = t2.normalized()
		var n2 := Vector2(-t2.y, t2.x)
		var l := p + Vector3(n2.x, 0, n2.y) * (w * 0.5)
		var r := p - Vector3(n2.x, 0, n2.y) * (w * 0.5)
		if i > 0:
			acc += Vector2(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]).length()
			# Deckfläche oben
			_strip_quad(verts, norms, uvs, idx, faces, prev_l, prev_r, r, l, Vector3.UP)
			# Unterseite
			var d := Vector3(0, -thick, 0)
			_strip_quad(verts, norms, uvs, idx, faces, prev_r + d, prev_l + d, l + d, r + d, Vector3.DOWN)
			# Seitenwände (innen/außen) als Brüstung
			var hp := Vector3(0, 1.05, 0)
			var ml := (prev_l + l) * 0.5
			var mr := (prev_r + r) * 0.5
			if not _near_other_bridge(ml, b):
				_side_quad(sv, sn, si, faces, prev_l + d, l + d, l + hp, prev_l + hp, (prev_l - prev_r).normalized())
			if not _near_other_bridge(mr, b):
				_side_quad(sv, sn, si, faces, prev_r + hp, r + hp, r + d, prev_r + d, (prev_r - prev_l).normalized())
		prev_l = l
		prev_r = r
	var mesh := ArrayMesh.new()
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = verts
	arr[Mesh.ARRAY_NORMAL] = norms
	arr[Mesh.ARRAY_TEX_UV] = uvs
	arr[Mesh.ARRAY_INDEX] = idx
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	mesh.surface_set_material(0, deck_mat if b["kind"] == "drive" else stone_mat)
	if not sv.is_empty():
		var arr2 := []
		arr2.resize(Mesh.ARRAY_MAX)
		arr2[Mesh.ARRAY_VERTEX] = sv
		arr2[Mesh.ARRAY_NORMAL] = sn
		arr2[Mesh.ARRAY_INDEX] = si
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr2)
		mesh.surface_set_material(1, stone_mat)
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	add_child(mi)
	var body := StaticBody3D.new()
	body.collision_layer = 1
	var cs := CollisionShape3D.new()
	var sh := ConcavePolygonShape3D.new()
	sh.backface_collision = true
	sh.set_faces(faces)
	cs.shape = sh
	body.add_child(cs)
	mi.add_child(body)
	_piers(pts, w, thick)


func _near_other_bridge(p: Vector3, self_b: Dictionary) -> bool:
	## Brüstung weglassen, wo eine andere Brücke (Nachbarfahrbahn, Gehweg) direkt anschließt.
	for ob in city["bridges"]:
		if ob == self_b:
			continue
		var op: Array = ob["pts"]
		var hw: float = maxf(float(ob["width"]), 2.5) * 0.5 + 0.8
		for i in op.size() - 1:
			var ax: float = op[i][0]
			var az: float = op[i][1]
			var dx: float = op[i + 1][0] - ax
			var dz: float = op[i + 1][1] - az
			var l2 := dx * dx + dz * dz
			if l2 < 0.01:
				continue
			var t := clampf(((p.x - ax) * dx + (p.z - az) * dz) / l2, 0.0, 1.0)
			var qx := ax + dx * t
			var qz := az + dz * t
			if (p.x - qx) * (p.x - qx) + (p.z - qz) * (p.z - qz) < hw * hw:
				var qy: float = lerpf(float(op[i][2]), float(op[i + 1][2]), t)
				if absf(qy - p.y) < 3.0:
					return true
	return false


func _piers(pts: Array, w: float, thick: float) -> void:
	## Pfeiler alle ~30 m, wenn die Fahrbahn deutlich über dem Boden liegt.
	var total := 0.0
	for i in pts.size() - 1:
		total += Vector2(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]).length()
	if total < 40.0:
		return
	var n := int(total / 30.0)
	var spacing := total / float(n + 1)
	for k in range(1, n + 1):
		var target := spacing * k
		var acc := 0.0
		for i in pts.size() - 1:
			var a := Vector3(pts[i][0], pts[i][2], pts[i][1])
			var b := Vector3(pts[i + 1][0], pts[i + 1][2], pts[i + 1][1])
			var l := Vector2(b.x - a.x, b.z - a.z).length()
			if acc + l >= target:
				var p := a.lerp(b, (target - acc) / maxf(l, 0.001))
				var gy := terrain.height_at(p.x, p.z)
				var deck_bot := p.y - thick
				if deck_bot - gy < 1.5:
					break
				var dir := Vector3(b.x - a.x, 0, b.z - a.z).normalized()
				var h := deck_bot - (gy - 2.5)
				var bm := BoxMesh.new()
				bm.size = Vector3(w * 0.55, h, 2.4)
				var inst := MeshInstance3D.new()
				inst.mesh = bm
				inst.material_override = stone_mat
				inst.transform = Transform3D(Basis.looking_at(dir, Vector3.UP), Vector3(p.x, gy - 2.5 + h * 0.5, p.z))
				add_child(inst)
				var pb := StaticBody3D.new()
				pb.collision_layer = 1
				var pcs := CollisionShape3D.new()
				var bs := BoxShape3D.new()
				bs.size = bm.size
				pcs.shape = bs
				pb.add_child(pcs)
				inst.add_child(pb)
				break
			acc += l


func _strip_quad(verts: PackedVector3Array, norms: PackedVector3Array, uvs: PackedVector2Array, idx: PackedInt32Array, faces: PackedVector3Array, a: Vector3, b: Vector3, c: Vector3, d: Vector3, n: Vector3) -> void:
	var k := verts.size()
	for p in [a, b, c, d]:
		verts.append(p)
		norms.append(n)
		uvs.append(Vector2(p.x, p.z) * 0.25)
	var front := -(b - a).cross(c - a)
	var tri1: Array = [k, k + 1, k + 2]
	var tri2: Array = [k, k + 2, k + 3]
	if front.dot(n) < 0.0:
		tri1 = [k, k + 2, k + 1]
		tri2 = [k, k + 3, k + 2]
	idx.append_array(tri1)
	idx.append_array(tri2)
	for ii in tri1 + tri2:
		faces.append(verts[ii])


func _side_quad(sv: PackedVector3Array, sn: PackedVector3Array, si: PackedInt32Array, faces: PackedVector3Array, a: Vector3, b: Vector3, c: Vector3, d: Vector3, n: Vector3) -> void:
	var k := sv.size()
	for p in [a, b, c, d]:
		sv.append(p)
		sn.append(n)
	var front := -(b - a).cross(c - a)
	var tri1: Array = [k, k + 1, k + 2]
	var tri2: Array = [k, k + 2, k + 3]
	if front.dot(n) < 0.0:
		tri1 = [k, k + 2, k + 1]
		tri2 = [k, k + 3, k + 2]
	si.append_array(tri1)
	si.append_array(tri2)
	for ii in tri1 + tri2:
		faces.append(sv[ii])


func _curbs(curbs: Array) -> void:
	## Granit-Bordsteine (tools/curbs.py): Gehweg links der Laufrichtung; Stirnfläche 14 cm über Fahrbahn, Oberseite
	## 22 cm breit. Je 250-m-Zelle ein Mesh (Sichtweite 260 m), damit Entferntes nicht gezeichnet wird.
	if curbs.is_empty():
		return
	var cells := {}
	for c in curbs:
		if c.size() < 2:
			continue
		var p0: Array = c[0]
		var key := Vector2i(floori(float(p0[0]) / 250.0), floori(float(p0[1]) / 250.0))
		if not cells.has(key):
			var st := SurfaceTool.new()
			st.begin(Mesh.PRIMITIVE_TRIANGLES)
			cells[key] = st
		var st: SurfaceTool = cells[key]
		for i in c.size() - 1:
			var a: Array = c[i]
			var b: Array = c[i + 1]
			var pa := Vector3(float(a[0]), float(a[2]), float(a[1]))
			var pb := Vector3(float(b[0]), float(b[2]), float(b[1]))
			var d := Vector3(pb.x - pa.x, 0, pb.z - pa.z)
			var L := d.length()
			if L < 0.02 or L > 8.0 or absf(pb.y - pa.y) > 1.5:
				continue
			d /= L
			var lft := Vector3(-d.z, 0, d.x)            # Gehwegseite wie in tools/curbs.py: (−dz, dx)
			var lo := Vector3(0, -0.05, 0)
			var hi := Vector3(0, 0.14, 0)
			var w := lft * 0.22
			# Stirnfläche (zur Fahrbahn), Oberseite, Rückseite
			_curb_quad(st, pa + lo, pb + lo, pb + hi, pa + hi, -lft, L)
			_curb_quad(st, pa + hi, pb + hi, pb + hi + w, pa + hi + w, Vector3.UP, L)
			_curb_quad(st, pb + w + lo, pa + w + lo, pa + w + hi, pb + w + hi, lft, L)
	if not _rail_mats.has("curb"):
		var cm := (TexLib.tri_material("paving_sandstone", 0.72) as StandardMaterial3D).duplicate() as StandardMaterial3D
		cm.cull_mode = BaseMaterial3D.CULL_DISABLED          # Bordsteinflächen beidseitig
		_rail_mats["curb"] = cm
	var mat: Material = _rail_mats["curb"]
	for key in cells:
		var st: SurfaceTool = cells[key]
		var mesh := st.commit()
		if mesh.get_surface_count() == 0:
			continue
		mesh.surface_set_material(0, mat)
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		mi.visibility_range_end = 260.0
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mi.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
		add_child(mi)


static func _curb_quad(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, d: Vector3, n: Vector3, _L: float) -> void:
	# beide Umlaufrichtungen prüfen: Vorderseite muss zu n zeigen (Godot: Vorderseite im Uhrzeigersinn)
	var order := [0, 1, 2, 0, 2, 3]
	var q := [a, b, c, d]
	if (b - a).cross(c - a).dot(n) > 0.0:
		order = [0, 2, 1, 0, 3, 2]
	for k in order:
		st.set_normal(n)
		st.add_vertex(q[k])


func _bridge_arches(data: Dictionary) -> void:
	## Steinbögen historischer Brücken (tools/bridge_arches.py): Stirnwände mit Bogenöffnungen, Laibungen, Pfeiler.
	var t: Array = data.get("tris", [])
	var nn: Array = data.get("n", [])
	if t.size() < 9:
		return
	var v := PackedVector3Array()
	var n := PackedVector3Array()
	var uv := PackedVector2Array()
	var ntri := t.size() / 9
	for i in ntri:
		var a := Vector3(t[i * 9], t[i * 9 + 1], t[i * 9 + 2])
		var b := Vector3(t[i * 9 + 3], t[i * 9 + 4], t[i * 9 + 5])
		var c := Vector3(t[i * 9 + 6], t[i * 9 + 7], t[i * 9 + 8])
		var fn := Vector3(nn[i * 3], nn[i * 3 + 1], nn[i * 3 + 2]) if nn.size() >= (i + 1) * 3 else (b - a).cross(c - a).normalized()
		# Godot: Vorderseite im Uhrzeigersinn, von außen (Normale) gesehen
		var pts := [a, b, c] if (b - a).cross(c - a).dot(fn) < 0.0 else [a, c, b]
		for p in pts:
			v.append(p)
			n.append(fn)
			uv.append(Vector2(p.x + p.z, p.y) * 0.25)
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = v
	arr[Mesh.ARRAY_NORMAL] = n
	arr[Mesh.ARRAY_TEX_UV] = uv
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	mesh.surface_set_material(0, masonry_mat())
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.visibility_range_end = 1800.0
	add_child(mi)
