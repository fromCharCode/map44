class_name StreetLife
extends Node3D
## Straßenleben einer Kachel (city["life"], erzeugt von tools/street_life.py):
## Stadtmöbel, Haltestellen, Verkehrszeichen, Straßennamensschilder, Läden (Schild, Name, Markise),
## Café-Außenplätze und Müll-Decals. Alles je 125-m-Zelle und Modell als MultiMesh (Sichtweite misst Godot zur
## Zellmitte -> Zellen klein halten), Texte als Label3D mit eigener Sichtweite.

const CELL := 125.0
const DIRS := ["res://assets/models/street/", "res://assets/models/furniture/", "res://assets/models/props/",
	"res://assets/models/facade/", "res://assets/models/vegetation/"]
# fehlt ein neues Modell, wird ein vorhandenes genommen (oder das Objekt übersprungen)
const FALLBACK := {"bin_public": "bin", "stop_pole": "sign_pole", "sign_post": "", "glass_containers": "",
	"paper_container": "", "litfass": "", "billboard": "", "post_box": "", "hydrant": "", "street_cabinet": "",
	"parking_meter": "", "cafe_set": "", "cafe_parasol": "", "bicycle": "", "e_scooter": "", "cardboard": "",
	"trash_bags": "", "planter": "", "sandwich_board": ""}
# Sichtweite je Modell (m) und Kollision ("box"/"cyl"/"")
const RANGE := {"litfass": 380.0, "billboard": 380.0, "bus_stop": 320.0, "stop_pole": 260.0, "street_cabinet": 160.0,
	"glass_containers": 220.0, "paper_container": 200.0, "cafe_parasol": 220.0, "sign_post": 240.0}
const COLLIDE := {"litfass": "cyl", "billboard": "box", "bus_stop": "box", "glass_containers": "box",
	"paper_container": "box", "street_cabinet": "box", "post_box": "box", "hydrant": "cyl", "parking_meter": "box",
	"bin_public": "cyl", "bollard": "cyl", "stop_pole": "cyl", "sign_post": "cyl"}
const PAINT := {
	"cafe_parasol": [Color(0.93, 0.9, 0.82), Color(0.62, 0.12, 0.1), Color(0.12, 0.3, 0.2), Color(0.15, 0.22, 0.42),
		Color(0.95, 0.95, 0.95), Color(0.2, 0.2, 0.22)],
	"bicycle": [Color(0.1, 0.1, 0.11), Color(0.75, 0.75, 0.78), Color(0.6, 0.08, 0.07), Color(0.1, 0.2, 0.45),
		Color(0.2, 0.4, 0.25), Color(0.9, 0.9, 0.88), Color(0.85, 0.5, 0.1), Color(0.35, 0.36, 0.4)],
	"e_scooter": [Color(0.1, 0.55, 0.3), Color(0.08, 0.08, 0.09), Color(0.9, 0.35, 0.1), Color(0.2, 0.35, 0.8)],
}
# Farbschema Ladenschild je Kategorie: [Tafel, Schrift]
const SHOP_COL := {
	"food": [Color(0.42, 0.24, 0.12), Color(0.98, 0.92, 0.78)], "super": [Color(0.85, 0.1, 0.08), Color(1, 1, 1)],
	"fashion": [Color(0.08, 0.08, 0.09), Color(0.95, 0.95, 0.95)], "service": [Color(0.92, 0.92, 0.9), Color(0.1, 0.1, 0.12)],
	"home": [Color(0.18, 0.32, 0.25), Color(0.95, 0.93, 0.85)], "gastro": [Color(0.24, 0.12, 0.1), Color(0.97, 0.85, 0.6)],
	"bank": [Color(0.1, 0.2, 0.45), Color(1, 1, 1)], "health": [Color(0.12, 0.5, 0.25), Color(1, 1, 1)],
	"culture": [Color(0.5, 0.08, 0.12), Color(1, 0.95, 0.85)], "hotel": [Color(0.12, 0.12, 0.2), Color(0.95, 0.82, 0.45)],
	"other": [Color(0.3, 0.3, 0.33), Color(1, 1, 1)], "vacant": [Color(0.96, 0.96, 0.94), Color(0.75, 0.1, 0.08)],
}
const AWNING_COL := [Color(0.62, 0.1, 0.08), Color(0.14, 0.32, 0.2), Color(0.86, 0.82, 0.7), Color(0.12, 0.2, 0.4),
	Color(0.85, 0.45, 0.1), Color(0.3, 0.3, 0.32)]

static var _parts := {}
static var _mutex := Mutex.new()          # Kachelaufbau (Worker-Thread) und GroundCover (Haupt-Thread) teilen den Cache
static var _font: FontFile
static var _serif_font: FontFile
static var _sign_cells := {}
static var _sign_plates := {}
static var _mat_cache := {}

var terrain: Terrain
var _groups := {}          # [model, cell] -> Array[[Transform3D, Color, cell_idx]]
var _bodies := {}          # cell -> StaticBody3D


func build(t: Terrain, life: Dictionary) -> void:
	terrain = t
	if life.is_empty():
		return
	_load_sign_cells()
	for f in life.get("furniture", []):
		var model := String(f[0])
		var v := int(f[5])
		# typische Dresdner Säule mit Laterne und Kugel: in Alt- und Neustadt etwa jede vierte
		if model == "litfass" and Vector2(float(f[1]), float(f[2])).length() < 3200.0 and posmod(v * 7 + int(absf(float(f[1]))), 4) == 0:
			model = "litfass_dresden"
		if model == "stop_pole" and f.size() > 6 and String(f[6]) != "":
			_stop_name(float(f[1]), float(f[2]), float(f[3]), String(f[6]))
		var cell := 0.0
		if model == "billboard":
			cell = float(posmod(v + int(absf(float(f[1])) * 0.37), 9))
		elif model in ["litfass", "litfass_dresden", "sandwich_board"]:
			cell = float(posmod(v + int(absf(float(f[2])) * 0.29), 8))
		_add(model, float(f[1]), float(f[2]), float(f[3]), v, 0.0, cell)
	for s in life.get("signs", []):
		_traffic_sign(s)
	if OS.has_environment("DRESDEN_TRACE"): print("  T _street_names")
	_street_names(life.get("names", []))      # vor _flush: Pfosten/Tafeln sind MultiMesh-Gruppen
	if OS.has_environment("DRESDEN_TRACE"): print("  T _flush")
	_flush()
	if OS.has_environment("DRESDEN_TRACE"): print("  T _shops")
	_shops(life.get("shops", []))
	if OS.has_environment("DRESDEN_TRACE"): print("  T _litter")
	_litter(life.get("litter", []))


# --- Modelle -----------------------------------------------------------------
static func _model_path(name: String) -> String:
	for d in DIRS:
		var p: String = d + name + ".glb"
		if ResourceLoader.exists(p):
			return p
	var fb: String = FALLBACK.get(name, "")
	if fb != "":
		for d in DIRS:
			var p2: String = d + fb + ".glb"
			if ResourceLoader.exists(p2):
				return p2
	return ""


## Im Haupt-Thread vor dem ersten Kachelaufbau: alle Straßen-, Möbel-, Fassaden- und Vegetationsmodelle laden.
static func prewarm() -> void:
	for d in ["res://assets/models/street/", "res://assets/models/furniture/", "res://assets/models/facade/",
			"res://assets/models/vegetation/"]:
		# ResourceLoader.list_directory: im exportierten Paket heißen die Einträge sonst "*.glb.import"
		for f in ResourceLoader.list_directory(d):
			if f.ends_with(".glb"):
				parts(f.get_basename())
	for nm in ["bus_stop", "bench", "bike_rack", "bin", "bollard", "sign_pole", "traffic_light_ped"]:
		parts(nm)
	for nm in FALLBACK:
		parts(nm)
	_font = load("res://assets/fonts/NotoSans-CondensedSemiBold.ttf") as FontFile
	_serif_font = load("res://assets/fonts/NotoSerif-SemiBold.ttf") as FontFile
	load("res://assets/fonts/NotoSans-CondensedBold.ttf")


static func parts(name: String) -> Array:
	## Thread-sicher. Die Sperre schützt nur die Wörterbücher – geladen wird außerhalb, denn Laden/Duplizieren
	## von Meshes ruft synchron den RenderingServer (Haupt-Thread) auf; mit gehaltener Sperre gäbe das einen
	## Deadlock, sobald der Haupt-Thread gleichzeitig auf die Sperre wartet.
	_mutex.lock()
	var res_c: Array = _parts.get(name, [])
	var known := _parts.has(name)
	_mutex.unlock()
	if known:
		return res_c
	var out := _load_parts(name)
	_mutex.lock()
	if _parts.has(name):
		out = _parts[name]          # anderer Thread war schneller
	else:
		_parts[name] = out
	_mutex.unlock()
	return out


static func _cache_get(k: String) -> Material:
	_mutex.lock()
	var m: Material = _mat_cache.get(k, null)
	_mutex.unlock()
	return m


static func _cache_put(k: String, m: Material) -> Material:
	_mutex.lock()
	if _mat_cache.has(k):
		m = _mat_cache[k]
	else:
		_mat_cache[k] = m
	_mutex.unlock()
	return m


static func _load_parts(name: String) -> Array:
	var res: Array = []
	var path := _model_path(name)
	if path == "":
		return res
	var ps := load(path) as PackedScene
	if ps == null:
		push_warning("StreetLife: Modell nicht ladbar: " + path)
		return res
	var root := ps.instantiate()
	var stack: Array = [[root, Transform3D.IDENTITY]]
	while not stack.is_empty():
		var it: Array = stack.pop_back()
		var n: Node = it[0]
		var xf: Transform3D = it[1]
		if n is Node3D and n != root:
			xf = xf * (n as Node3D).transform
		if n is MeshInstance3D and (n as MeshInstance3D).mesh != null:
			var mesh := (n as MeshInstance3D).mesh.duplicate() as Mesh
			var special := ""
			for i in mesh.get_surface_count():
				var m := mesh.surface_get_material(i)
				if m == null:
					continue
				var nm := String(m.resource_name)
				if nm.begins_with("Paint"):
					mesh.surface_set_material(i, _paint_mat(m))
				elif nm.begins_with("SignFace"):
					mesh.surface_set_material(i, _atlas_mat("signs", "res://assets/textures/street/traffic_signs.png", Vector2(8, 4), true))
					special = "atlas"
				elif nm.begins_with("Poster"):
					if name == "billboard":
						mesh.surface_set_material(i, _atlas_mat("billboard", "res://assets/textures/street/billboard_posters.png", Vector2(3, 3), false))
					elif name == "litfass" or name == "litfass_dresden":
						var lm := _atlas_mat("litfass", "res://assets/textures/street/posters.png", Vector2(4, 2), false) as ShaderMaterial
						lm.set_shader_parameter("litfass", true)
						mesh.surface_set_material(i, lm)
					else:
						mesh.surface_set_material(i, _atlas_mat("posters", "res://assets/textures/street/posters.png", Vector2(4, 2), false))
					special = "atlas"
			res.append({"mesh": mesh, "xf": xf, "special": special})
		for c in n.get_children():
			stack.append([c, xf])
	root.free()
	return res


static func _paint_mat(src: Material) -> Material:
	var k := "paint_" + str(src.get_instance_id())
	var c := _cache_get(k)
	if c != null:
		return c
	var m := StandardMaterial3D.new()
	if src is StandardMaterial3D:
		var s := src as StandardMaterial3D
		m.roughness = s.roughness
		m.metallic = s.metallic
		m.albedo_texture = s.albedo_texture
	m.vertex_color_use_as_albedo = true
	return _cache_put(k, m)


static func _atlas_mat(key: String, tex_path: String, grid: Vector2, cut: bool) -> Material:
	var c := _cache_get(key)
	if c != null:
		return c
	var sm := ShaderMaterial.new()
	sm.shader = load("res://shaders/atlas_cell.gdshader")
	if ResourceLoader.exists(tex_path):
		var tex = load(tex_path)
		if tex is Texture2D:
			sm.set_shader_parameter("atlas", tex)
		else:
			push_warning("StreetLife: Textur nicht ladbar: " + tex_path)
	sm.set_shader_parameter("grid", grid)
	sm.set_shader_parameter("alpha_cut", cut)
	return _cache_put(key, sm)


static func _load_sign_cells() -> void:
	if not _sign_cells.is_empty():
		return
	var p := "res://assets/textures/street/traffic_signs.json"
	if not FileAccess.file_exists(p):
		return
	var j = JSON.parse_string(FileAccess.get_file_as_string(p))
	if j is Dictionary:
		var d: Dictionary = j.get("cells", j)
		for k in d:
			var v = d[k]
			if v is Dictionary:
				_sign_cells[String(k)] = int(v.get("index", v.get("cell", 0)))
				if v.has("plate"):
					_sign_plates[String(k)] = String(v["plate"])
			else:
				_sign_cells[String(k)] = int(v)


func _cell(x: float, z: float) -> Vector2i:
	return Vector2i(floori((x + 1000.0) / CELL), floori((z + 1000.0) / CELL))


func _add(model: String, x: float, z: float, yaw: float, variant: int, y_off: float = 0.0, custom: float = 0.0, xf_extra := Transform3D.IDENTITY) -> void:
	if parts(model).is_empty():
		return
	var pos := Vector3(x, terrain.height_at(x, z) + y_off, z)
	var xf := Transform3D(Basis(Vector3.UP, yaw), pos) * xf_extra
	var col := Color.WHITE
	if PAINT.has(model):
		var pal: Array = PAINT[model]
		col = pal[variant % pal.size()]
	var key := [model, _cell(x, z)]
	if not _groups.has(key):
		_groups[key] = []
	_groups[key].append([xf, col, custom])


func _flush() -> void:
	for key in _groups:
		var model: String = key[0]
		var list: Array = _groups[key]
		var range_end: float = RANGE.get(model, 120.0)
		for part in parts(model):
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			mm.use_colors = true
			mm.use_custom_data = part["special"] == "atlas"
			mm.mesh = part["mesh"]
			var fx: Array = []
			var fc: Array = []
			var fd: Array = []
			for it in list:
				fx.append(it[0])
				fc.append(it[1])
				if mm.use_custom_data:
					fd.append(Color(float(it[2]), 0, 0, 0))
			RenderUtil.fill_multimesh(mm, fx, part["xf"], fc, fd)
			var inst := MultiMeshInstance3D.new()
			inst.multimesh = mm
			inst.visibility_range_end = range_end
			inst.visibility_range_end_margin = range_end * 0.12
			inst.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
			if range_end < 130.0:
				inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			add_child(inst)
		var kind: String = COLLIDE.get(model, "")
		if kind != "":
			_collide(model, kind, key[1], list)
	_groups.clear()


func _collide(model: String, kind: String, cell: Vector2i, list: Array) -> void:
	var aabb := AABB()
	var first := true
	for part in parts(model):
		var a: AABB = (part["xf"] as Transform3D) * (part["mesh"] as Mesh).get_aabb()
		aabb = a if first else aabb.merge(a)
		first = false
	if aabb.size.y < 0.3:
		return
	if not _bodies.has(cell):
		var body := StaticBody3D.new()
		body.collision_layer = 1
		add_child(body)
		_bodies[cell] = body
	var shape: Shape3D
	if kind == "cyl":
		var cy := CylinderShape3D.new()
		cy.radius = maxf(maxf(aabb.size.x, aabb.size.z) * 0.5, 0.06)
		cy.height = aabb.size.y
		shape = cy
	else:
		var bx := BoxShape3D.new()
		bx.size = aabb.size
		shape = bx
	for e in list:
		var cs := CollisionShape3D.new()
		cs.shape = shape
		cs.transform = (e[0] as Transform3D) * Transform3D(Basis(), aabb.get_center())
		(_bodies[cell] as StaticBody3D).add_child(cs)


# --- Verkehrszeichen ---------------------------------------------------------
func _traffic_sign(s: Array) -> void:
	var plate: String = s[0]
	var atlas: String = s[1]
	var x: float = s[2]
	var z: float = s[3]
	var yaw: float = s[4]
	_add("sign_post", x, z, yaw, 0)
	if _sign_cells.is_empty() or not _sign_cells.has(atlas):
		return
	plate = _sign_plates.get(atlas, plate)
	var h := 2.6 if plate in ["plate_triangle", "plate_triangle_down"] else 2.65
	# Platte 5 cm vor dem Pfosten (zur Schildseite)
	_add(plate, x, z, yaw, 0, h, float(_sign_cells[atlas]), Transform3D(Basis(), Vector3(0, 0, -0.06)))


# --- Straßennamensschilder ------------------------------------------------------
func _font_file() -> FontFile:
	if _font == null:
		_font = load("res://assets/fonts/NotoSans-CondensedSemiBold.ttf") as FontFile
	return _font


func _serif() -> FontFile:
	if _serif_font == null:
		_serif_font = load("res://assets/fonts/NotoSerif-SemiBold.ttf") as FontFile
	return _serif_font


func _street_names(names: Array) -> void:
	## Dresdner Straßennamensschild: dunkelblaues Email, weiße Antiqua, weiße Zierlinie (Modelle street_name_post/_plate)
	if names.is_empty():
		return
	var have_models := not parts("street_name_post").is_empty() and not parts("street_name_plate").is_empty()
	var plates := Surf.new()
	for nm in names:
		var x: float = nm[0]
		var z: float = nm[1]
		var yaw: float = nm[2]
		var gy := terrain.height_at(x, z)
		_add("street_name_post" if have_models else "sign_post", x, z, yaw, 0)
		var basis := Basis(Vector3.UP, yaw)
		for k in 2:
			var text: String = nm[4 + k]
			if text == "":
				continue
			var b := basis * Basis(Vector3.UP, PI * 0.5 * k)
			var cy := 2.70 + 0.25 * k
			var need := 0.075 * 0.62 * float(text.length()) + 0.14
			var w := clampf(need, 0.7, 1.26)          # Tafel höchstens 1,4-fach strecken
			var fit := clampf((w - 0.12) / maxf(need - 0.14, 0.01), 0.55, 1.0)   # sonst Schrift verkleinern
			if have_models:
				_add("street_name_plate", x, z, yaw + PI * 0.5 * k, 0, cy, 0.0, Transform3D(Basis().scaled(Vector3(w / 0.9, 1, 1)), Vector3.ZERO))
			else:
				plates.box(Vector3(x, gy + cy, z), b, Vector3(w + 0.03, 0.25, 0.022), Color(0.94, 0.94, 0.92))
				plates.box(Vector3(x, gy + cy, z), b, Vector3(w, 0.22, 0.026), Color(0.1, 0.16, 0.41))
			var c := Vector3(x, gy + cy, z)
			for side in [1.0, -1.0]:
				var lb := {}
				lb.text = text
				lb.font = _serif()
				lb.font_size = 64
				lb.pixel_size = 0.075 / 45.0 * fit    # Versalhöhe ~7,5 cm
				lb.modulate = Color(0.95, 0.95, 0.93)
				lb.outline_size = 0
				lb.double_sided = false
				lb.shaded = true
				lb.visibility_range_end = 70.0
				# Tafel-Vorderseite zeigt -Z (z = -0,0125), Rückseite +Z; Label3D ist von +Z lesbar
				var face := b * Basis(Vector3.UP, PI if side > 0.0 else 0.0)
				lb.transform = Transform3D(face, c + b * Vector3(0, 0, -0.022 * side))
				_label_specs.append(lb)
	plates.commit(self, 140.0)


func _stop_name(x: float, z: float, yaw: float, text: String) -> void:
	## Haltestellenname im Namensfeld der gelben Fahne (Mitte ±0,011 / 2,835 / -0,305, 0,40 × 0,15 m)
	var gy := terrain.height_at(x, z)
	var basis := Basis(Vector3.UP, yaw)
	var tw := 0.62 * 64.0 * 0.55 * float(text.length())
	for side in [1.0, -1.0]:
		var lb := {}
		lb.text = text
		lb.font = _font_file()
		lb.font_size = 64
		lb.pixel_size = clampf(0.38 / maxf(tw, 1.0), 0.0006, 0.0016)
		lb.modulate = Color(0.05, 0.05, 0.05)
		lb.shaded = true
		lb.double_sided = false
		lb.visibility_range_end = 45.0
		# Fahne steht senkrecht zur Fahrbahn: Flächennormale = ±X des Modells
		var face := basis * Basis(Vector3.UP, PI * 0.5 * side)
		lb.transform = Transform3D(face, Vector3(x, gy, z) + basis * Vector3(0.013 * side, 2.835, -0.305))
		_label_specs.append(lb)


# --- Läden ---------------------------------------------------------------------
func _shops(shops: Array) -> void:
	if shops.is_empty():
		return
	var boards := Surf.new()
	var awn := Surf.new()
	for s in shops:
		var a := Vector3(s[1], 0, s[2])
		var b := Vector3(s[3], 0, s[4])
		var n := Vector3(s[5], 0, s[6])
		var cat: String = s[9]
		var name: String = s[8]
		var mid := (a + b) * 0.5
		var gy := terrain.height_at(mid.x, mid.z)
		var w := a.distance_to(b)
		var t := (b - a).normalized()
		# rechtshändige Basis: x entlang der Wand, y oben, z = nach außen (Label3D ist von +Z aus lesbar)
		if t.cross(Vector3.UP).dot(n) < 0.0:
			t = -t
		var basis := Basis(t, Vector3.UP, t.cross(Vector3.UP).normalized())
		var cols: Array = SHOP_COL.get(cat, SHOP_COL["other"])
		var bw := clampf(w * 0.86, 1.6, 9.0)
		var center := mid + n * 0.07 + Vector3(0, gy + 3.35, 0)
		var text := name
		if cat == "vacant":
			text = "ZU VERMIETEN"
		if text != "":
			# Tafel nur mit Namen (leere Tafeln wirken wie Fremdkörper)
			boards.box(center, basis, Vector3(bw, 0.52, 0.08), cols[0])
			var lb := {}
			lb.text = text
			lb.font = _font_file()
			lb.font_size = 72
			var tw := 0.62 * 72.0 * float(text.length()) * 0.55
			lb.pixel_size = clampf((bw * 0.9) / maxf(tw, 1.0), 0.0018, 0.0052)
			lb.modulate = cols[1]
			lb.shaded = false
			lb.double_sided = false
			lb.visibility_range_end = 110.0
			lb.transform = Transform3D(basis, center + n * 0.045)
			_label_specs.append(lb)
		# Markise
		if int(s[10]) == 1:
			var ac: Color = AWNING_COL[int(absf(mid.x * 7.0 + mid.z * 3.0)) % AWNING_COL.size()]
			var aw := clampf(w * 0.92, 1.5, 9.0)
			var top := mid + n * 0.05 + Vector3(0, gy + 2.95, 0)
			var out := top + n * 1.35 + Vector3(0, -0.55, 0)
			var hx := t * (aw * 0.5)
			awn.quad4(top - hx, top + hx, out + hx, out - hx, ac)
			var vb := Vector3(0, -0.22, 0)
			awn.quad4(out - hx, out + hx, out + hx + vb, out - hx + vb, ac.darkened(0.15))
			awn.quad4(top - hx, out - hx, out - hx + vb, top - hx + Vector3(0, -0.05, 0), ac.darkened(0.25))
			awn.quad4(top + hx, out + hx, out + hx + vb, top + hx + Vector3(0, -0.05, 0), ac.darkened(0.25))
	boards.commit(self, 220.0)
	awn.commit(self, 240.0, true)


# --- Müll ------------------------------------------------------------------------
func _litter(items: Array) -> void:
	if items.is_empty() or not ResourceLoader.exists("res://assets/textures/street/litter.png"):
		return
	var quad := PlaneMesh.new()
	quad.size = Vector2(1, 1)
	var mat := _atlas_mat("litter", "res://assets/textures/street/litter.png", Vector2(4, 4), true)
	quad.material = mat
	var by_cell := {}
	for it in items:
		var x: float = it[1]
		var z: float = it[2]
		var c := _cell(x, z)
		if not by_cell.has(c):
			by_cell[c] = []
		by_cell[c].append(it)
	for c in by_cell:
		var list: Array = by_cell[c]
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.use_custom_data = true
		mm.mesh = quad
		var dx: Array = []
		var dd: Array = []
		for i in list.size():
			var it: Array = list[i]
			var x: float = it[1]
			var z: float = it[2]
			var sc: float = it[4]
			dx.append(Transform3D(Basis(Vector3.UP, float(it[3])).scaled(Vector3(sc, 1, sc)), Vector3(x, terrain.height_at(x, z) + 0.018, z)))
			dd.append(Color(float(it[0]), 0, 0, 0))
		RenderUtil.fill_multimesh(mm, dx, Transform3D.IDENTITY, [], dd)
		var inst := MultiMeshInstance3D.new()
		inst.multimesh = mm
		inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		inst.visibility_range_end = 70.0
		inst.visibility_range_end_margin = 10.0
		inst.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
		add_child(inst)


## Einfacher Sammler für prozedurale Geometrie mit Vertexfarben (Tafeln, Markisen)
class Surf:
	var v := PackedVector3Array()
	var n := PackedVector3Array()
	var c := PackedColorArray()

	func quad4(a: Vector3, b: Vector3, cc: Vector3, d: Vector3, col: Color, nrm := Vector3.ZERO) -> void:
		var nn := nrm if nrm != Vector3.ZERO else (b - a).cross(d - a).normalized()
		# Godot: Vorderseite im Uhrzeigersinn (Front-Normale = -(b-a)x(c-a))
		var order := [a, b, cc, a, cc, d]
		if (-(b - a).cross(cc - a)).dot(nn) < 0.0:
			order = [a, cc, b, a, d, cc]
		for p in order:
			v.append(p)
			n.append(nn)
			c.append(col)

	func box(center: Vector3, basis: Basis, size: Vector3, col: Color) -> void:
		var hx := basis.x * size.x * 0.5
		var hy := basis.y * size.y * 0.5
		var hz := basis.z * size.z * 0.5
		var corners := []
		for sx in [-1, 1]:
			for sy in [-1, 1]:
				for sz in [-1, 1]:
					corners.append(center + hx * sx + hy * sy + hz * sz)
		# Flächen: (Ecken-Indizes gegen den Uhrzeigersinn von außen)
		var faces := [[1, 3, 7, 5], [4, 6, 2, 0], [2, 6, 7, 3], [0, 1, 5, 4], [4, 5, 7, 6], [0, 2, 3, 1]]
		var shade := [1.0, 0.85, 1.0, 0.7, 0.9, 0.9]
		for fi in faces.size():
			var f: Array = faces[fi]
			var fc: Vector3 = (corners[f[0]] + corners[f[1]] + corners[f[2]] + corners[f[3]]) * 0.25
			var col2: Color = col * float(shade[fi])
			col2.a = 1.0
			quad4(corners[f[0]], corners[f[1]], corners[f[2]], corners[f[3]], col2, (fc - center).normalized())

	func commit(parent: Node3D, range_end: float, double_sided := false) -> void:
		if v.is_empty():
			return
		var arr := []
		arr.resize(Mesh.ARRAY_MAX)
		arr[Mesh.ARRAY_VERTEX] = v
		arr[Mesh.ARRAY_NORMAL] = n
		arr[Mesh.ARRAY_COLOR] = c
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
		var m := StandardMaterial3D.new()
		m.vertex_color_use_as_albedo = true
		m.roughness = 0.7
		if double_sided:
			m.cull_mode = BaseMaterial3D.CULL_DISABLED
		mesh.surface_set_material(0, m)
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		mi.visibility_range_end = range_end
		parent.add_child(mi)


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
