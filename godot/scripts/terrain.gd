class_name Terrain
extends Node3D
## Gelände: Höhenraster (float32, 1 m) wird im Vertex-Shader angewendet.
## Chunks von 64 m mit zwei Detailstufen; Kollision über HeightMapShape3D.

const CHUNK := 125.0  # 16×16 Stücke je Kachel (früher 62,5 m = 2048 Instanzen je Kachel: Ruckler beim Einhängen,
                      # ~1000 Zeichenaufrufe allein fürs Gelände)
const LOD0_N := 128  # 1 m Raster
const LOD1_N := 32   # 4 m Raster

var world_size := 2000.0
var material: ShaderMaterial
var heights: PackedFloat32Array
var grid_w := 2000
var center := Vector2.ZERO
var data_dir := "res://data/"
var ortho_tex: ImageTexture
var cover: Image                 # 1000² (2 m): R = Wiese, G = Wald, B = frei (kein Weg/keine Straße) – für GroundCover
static var _arrays_cache := {}
static var _grid_cache := {}


func build(meta: Dictionary, noise: ImageTexture, dir: String = "res://data/", ctr: Vector2 = Vector2.ZERO) -> void:
	data_dir = dir
	center = ctr
	grid_w = int(meta["width"])
	world_size = float(grid_w)
	var bytes := FileAccess.get_file_as_bytes(data_dir + "terrain.f32")
	heights = bytes.to_float32_array()
	var himg := Image.create_from_data(grid_w, grid_w, false, Image.FORMAT_RF, bytes)
	var hm := ImageTexture.create_from_image(himg)

	var s0 := Image.load_from_file(data_dir + "splat0.png")
	s0.generate_mipmaps()
	_make_cover(s0, null)
	var baked := load_baked(data_dir)
	var s1: Image
	var s2: Image
	var ortho: Image
	if not baked.is_empty():
		# vorgebacken (exportiertes Spiel; Datenpaket aus tools/package_release.sh)
		s1 = baked["s1"]
		s2 = baked["s2"]
		ortho = baked["ortho"]
	else:
		var imgs := prepare_images(data_dir)
		s1 = imgs["s1"]
		s2 = imgs["s2"]
		ortho = imgs["ortho"]
	if not _arrays_cache.has("a"):
		_arrays_cache["a"] = TexLib.build_arrays(TexLib.TERRAIN_LAYERS, 1024)
	var arrays: Dictionary = _arrays_cache["a"]
	material = ShaderMaterial.new()
	material.shader = load("res://shaders/terrain.gdshader")
	material.set_shader_parameter("heightmap", hm)
	material.set_shader_parameter("splat0", ImageTexture.create_from_image(s0))
	material.set_shader_parameter("splat1", ImageTexture.create_from_image(s1))
	material.set_shader_parameter("splat2", ImageTexture.create_from_image(s2))
	ortho_tex = ImageTexture.create_from_image(ortho)
	material.set_shader_parameter("ortho", ortho_tex)
	material.set_shader_parameter("noise_tex", noise)
	material.set_shader_parameter("albedo_arr", arrays["albedo"])
	material.set_shader_parameter("normal_arr", arrays["normal"])
	material.set_shader_parameter("rough_arr", arrays["rough"])
	var tiles: PackedFloat32Array = arrays["tiles"]
	tiles.resize(13)
	material.set_shader_parameter("tile_m", tiles)
	material.set_shader_parameter("world_size", world_size)
	material.set_shader_parameter("tile_center", center)

	if not _grid_cache.has(0):
		_grid_cache[0] = _grid(LOD0_N)
		_grid_cache[1] = _grid(LOD1_N)
	var mesh0: ArrayMesh = _grid_cache[0]
	var mesh1: ArrayMesh = _grid_cache[1]
	var n := int(world_size / CHUNK)
	var half := world_size * 0.5
	# Höhe wird im Vertex-Shader verschoben -> Begrenzungsbox muss die echte Höhe der Kachel umfassen
	# (Dresden reicht bis ~ +270 m über base_height; vorher fest -60..+140 m -> Geländestücke fielen weg)
	var hmin := float(meta.get("min", -60.0)) - 5.0
	var hmax := float(meta.get("max", 140.0)) + 15.0
	var chunk_aabb := AABB(Vector3(0, hmin, 0), Vector3(CHUNK, hmax - hmin, CHUNK))
	var cn := int(CHUNK)
	for j in n:
		for i in n:
			var pos := Vector3(i * CHUNK - half + center.x, 0.0, j * CHUNK - half + center.y)
			# Box je Stück aus den echten Höhen (grob alle 4 m + Rand) statt der Höhe der ganzen Kachel:
			# besseres Culling (auch Schatten) und weniger SDFGI-Arbeit
			var lo := 1e9
			var hi := -1e9
			var r0 := j * cn
			var c0 := i * cn
			for rr in range(r0, mini(r0 + cn + 1, grid_w), 4):
				var row := rr * grid_w
				for cc in range(c0, mini(c0 + cn + 1, grid_w), 4):
					var hv := heights[row + cc]
					lo = minf(lo, hv)
					hi = maxf(hi, hv)
			if lo > hi:
				lo = hmin
				hi = hmax
			chunk_aabb = AABB(Vector3(0, lo - 9.0, 0), Vector3(CHUNK, hi - lo + 13.0, CHUNK))
			var m0 := MeshInstance3D.new()
			m0.mesh = mesh0
			m0.position = pos
			m0.custom_aabb = chunk_aabb
			m0.material_override = material
			m0.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			# Sichtweite misst Godot zur Mitte der Box; Ränder mit Schürzen -> harter Wechsel ohne Überblenden
			# (Überblenden zeichnete im Randbereich beide Stufen mit Dither-Transparenz)
			m0.visibility_range_end = 300.0
			m0.visibility_range_end_margin = 30.0
			m0.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_DISABLED
			add_child(m0)
			var m1 := MeshInstance3D.new()
			m1.mesh = mesh1
			m1.position = pos
			m1.custom_aabb = chunk_aabb
			m1.material_override = material
			m1.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			m1.visibility_range_begin = 300.0
			m1.visibility_range_begin_margin = 30.0
			m1.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_DISABLED
			add_child(m1)

	# Kollision: 4x4 Felder (je 500 m), damit Jolt sie einzeln und über mehrere Frames aufbaut
	var col_path := data_dir + "terrain_col.f32"
	var W := grid_w + 1
	var col: PackedFloat32Array
	if FileAccess.file_exists(col_path):
		col = FileAccess.get_file_as_bytes(col_path).to_float32_array()
	if col.size() == W * W:
		var P := 4
		var S := (W - 1) / P          # Meter je Feld
		for pj in P:
			for pi in P:
				var data := PackedFloat32Array()
				data.resize((S + 1) * (S + 1))
				for r in S + 1:
					var src := (pj * S + r) * W + pi * S
					for c in S + 1:
						data[r * (S + 1) + c] = col[src + c]
				var sh := HeightMapShape3D.new()
				sh.map_width = S + 1
				sh.map_depth = S + 1
				sh.map_data = data
				var bd := StaticBody3D.new()
				bd.name = "TerrainBody_%d_%d" % [pi, pj]
				bd.collision_layer = 1
				bd.position = Vector3(center.x - world_size * 0.5 + (pi + 0.5) * S, 0.0, center.y - world_size * 0.5 + (pj + 0.5) * S)
				var cs2 := CollisionShape3D.new()
				cs2.shape = sh
				bd.add_child(cs2)
				add_child(bd)
	else:
		var body := StaticBody3D.new()
		body.name = "TerrainBody"
		body.collision_layer = 1
		var shape := HeightMapShape3D.new()
		shape.map_width = grid_w
		shape.map_depth = grid_w
		shape.map_data = heights
		body.position = Vector3(center.x, 0.0, center.y)
		var cs := CollisionShape3D.new()
		cs.shape = shape
		body.add_child(cs)
		add_child(body)


func _make_cover(_s0: Image, _s1: Image) -> void:
	## Bewuchsbild kommt fertig aus der Pipeline (tools/make_cover.py / vegetation.py): cover.png 1000² RGB
	var p := data_dir + "cover.png"
	if FileAccess.file_exists(p):
		cover = Image.load_from_file(p)


const BAKED := {"s1": "tex_splat1.res", "s2": "tex_splat2.res", "ortho": "tex_ortho.res"}


static func prepare_images(dir: String) -> Dictionary:
	## Splat1/Splat2/Luftbild laden und BC-komprimieren (nur mit Editor-Binary möglich, sonst unkomprimiert).
	# Speicher je Kachel (früher ~320 MB unkomprimiert): CPU-Komprimierung im Kachel-Thread. BC7 (BPTC) rechnet
	# Godot auf der GPU (Betsy) und blockierte dabei das Bild (Ruckler 120–330 ms je Splat) -> nicht verwenden.
	# splat0 (Straße/Gehweg/Pflaster, scharfe Kanten) bleibt unkomprimiert; splat1 BC3 (Alpha = Wassermaske; ein
	# Zwischenwert erzwingt BC3, sonst wählt Godot bei 0/255-Alpha BC1 mit Transparenz und löscht die Gewichte);
	# splat2 nutzt Alpha nicht -> RGB/BC1. Luftbild BC1.
	var s1 := Image.load_from_file(dir + "splat1.png")
	var s2 := Image.load_from_file(dir + "splat2.png")
	var ortho := Image.load_from_file(dir + "ortho.jpg")
	var c1 := s1.get_pixel(0, 0)
	s1.set_pixel(0, 0, Color(c1.r, c1.g, c1.b, maxf(c1.a, 1.0 / 255.0) if c1.a < 0.5 else 254.0 / 255.0))
	s1.generate_mipmaps()
	s1.compress(Image.COMPRESS_S3TC, Image.COMPRESS_SOURCE_GENERIC)
	s2.convert(Image.FORMAT_RGB8)
	s2.generate_mipmaps()
	s2.compress(Image.COMPRESS_S3TC, Image.COMPRESS_SOURCE_GENERIC)
	ortho.generate_mipmaps()
	ortho.compress(Image.COMPRESS_S3TC, Image.COMPRESS_SOURCE_SRGB)
	return {"s1": s1, "s2": s2, "ortho": ortho}


static func load_baked(dir: String) -> Dictionary:
	## Vorgebackene Kacheltexturen (nur, wenn nicht älter als die Quellbilder, falls diese daneben liegen)
	var res := {}
	var srcs := {"s1": "splat1.png", "s2": "splat2.png", "ortho": "ortho.jpg"}
	for k in BAKED:
		var p: String = dir + String(BAKED[k])
		if not FileAccess.file_exists(p):
			return {}
		var sp: String = dir + String(srcs[k])
		if FileAccess.file_exists(sp) and FileAccess.get_modified_time(sp) > FileAccess.get_modified_time(p):
			return {}
		var im = ResourceLoader.load(p, "Image", ResourceLoader.CACHE_MODE_IGNORE)
		if not (im is Image) or (im as Image).is_empty():
			return {}
		res[k] = im
	return res


func cover_at(x: float, z: float) -> Color:
	## Bewuchs an Spielkoordinate (R Wiese, G Wald, B frei)
	if cover == null:
		return Color(0, 0, 0)
	var half := world_size * 0.5
	var px := clampi(int((x - center.x + half) * 0.5), 0, 999)
	var py := clampi(int((z - center.y + half) * 0.5), 0, 999)
	return cover.get_pixel(px, py)


const TUNNEL_CUT := """	if (has_tunnel) {
		// Gelände im Lichtraum der Tunnelröhre ausblenden (Portalöffnung, flache Abschnitte unter dem Kastendach)
		vec2 tv = texture(tunnel_tex, huv).rg;
		if (tv.g > 0.5 && wpos.y < tv.r + 4.9 && wpos.y > tv.r - 3.0) {
			discard;
		}
	}
"""
static var _tun_shader: Shader = null


func set_tunnel_mask(img: Image) -> void:
	## Tunnelband (scripts/tunnels.gd): der Shader blendet Gelände im Lichtraum der Röhre aus. Nur Kacheln mit
	## Tunnel bekommen die Variante mit discard (discard kostet ~0,7 ms GPU, wenn er im Shader aller Kacheln steht).
	if _tun_shader == null:
		var code: String = material.shader.code
		_tun_shader = Shader.new()
		_tun_shader.code = code.replace("\t//@TUNNEL_CUT\n", TUNNEL_CUT)
	var vals := {}
	for u in material.shader.get_shader_uniform_list():
		vals[u["name"]] = material.get_shader_parameter(u["name"])
	material.shader = _tun_shader
	for k in vals:
		if vals[k] != null:
			material.set_shader_parameter(k, vals[k])
	material.set_shader_parameter("tunnel_tex", ImageTexture.create_from_image(img))
	material.set_shader_parameter("has_tunnel", true)


func height_at(x: float, z: float) -> float:
	## Bilinear aus dem Raster; x/z in Spielkoordinaten.
	var half := world_size * 0.5
	var c := clampf(x - center.x + half - 0.5, 0.0, grid_w - 1.001)
	var r := clampf(z - center.y + half - 0.5, 0.0, grid_w - 1.001)
	var c0 := int(c)
	var r0 := int(r)
	var fc := c - c0
	var fr := r - r0
	var i := r0 * grid_w + c0
	var top := heights[i] * (1.0 - fc) + heights[i + 1] * fc
	var bot := heights[i + grid_w] * (1.0 - fc) + heights[i + grid_w + 1] * fc
	return top * (1.0 - fr) + bot * fr


func _grid(n: int) -> ArrayMesh:
	var step := CHUNK / n
	var verts := PackedVector3Array()
	var norms := PackedVector3Array()
	var cols := PackedColorArray()
	var idx := PackedInt32Array()
	for j in n + 1:
		for i in n + 1:
			verts.append(Vector3(i * step, 0.0, j * step))
			norms.append(Vector3.UP)
			cols.append(Color(0, 0, 0, 1))
	var w := n + 1
	for j in n:
		for i in n:
			var a := j * w + i
			var b := a + 1
			var c := a + w
			var d := c + 1
			idx.append_array([a, b, c, b, d, c])
	# Schürzen gegen Risse zwischen Detailstufen
	var edges: Array = []
	for i in n:
		edges.append([i, i + 1])                          # Nord
		edges.append([n * w + i + 1, n * w + i])          # Süd
		edges.append([(i + 1) * w, i * w])                # West
		edges.append([i * w + n, (i + 1) * w + n])        # Ost
	for e in edges:
		var v0: Vector3 = verts[e[0]]
		var v1: Vector3 = verts[e[1]]
		var k := verts.size()
		verts.append(v0)
		norms.append(Vector3.UP)
		cols.append(Color(1, 0, 0, 1))
		verts.append(v1)
		norms.append(Vector3.UP)
		cols.append(Color(1, 0, 0, 1))
		idx.append_array([e[0], e[1], k, e[1], k + 1, k])
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = verts
	arr[Mesh.ARRAY_NORMAL] = norms
	arr[Mesh.ARRAY_COLOR] = cols
	arr[Mesh.ARRAY_INDEX] = idx
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	mesh.custom_aabb = AABB(Vector3(0, -60, 0), Vector3(CHUNK, 200, CHUNK))
	return mesh


func contains(x: float, z: float) -> bool:
	var h := world_size * 0.5
	return absf(x - center.x) < h and absf(z - center.y) < h
