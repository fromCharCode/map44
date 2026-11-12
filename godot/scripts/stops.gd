class_name Stops
extends Node3D
## Haltestellen einer Kachel (Pipeline: tools/stops.py -> city["stops"]): Bahnsteige (erhöht, Bordkante, Blinden-
## leitstreifen, Kollision), DVB-Masten mit Name und Linien, Wartehallen, Abfahrtsanzeiger (Departures) und Mülleimer.
## Aufbau im Kachel-Thread; Beschriftungen (Label3D) entstehen erst im Haupt-Thread (_process), Anzeiger werden alle
## paar Sekunden aktualisiert.

const DIR := "res://assets/models/stops/"
## Ersatz, solange die eigenen Modelle fehlen
const FALLBACK := {"dvb_mast": "", "wall_shelter": "res://assets/models/props/bus_stop.glb",
	"wall_shelter_long": "res://assets/models/props/bus_stop.glb", "dfi_large": "", "dfi_small": "", "stop_bin": ""}
const VIS := {"dvb_mast": 220.0, "wall_shelter": 300.0, "wall_shelter_long": 300.0, "dfi_large": 220.0, "dfi_small": 160.0,
	"stop_bin": 120.0}

static var _scenes := {}
static var _man := {}
static var _man_loaded := false
static var _mats := {}

var terrain: Terrain
var _label_specs: Array = []
var _dfi_specs: Array = []       # [Transform3D (Anzeigemitte), w, h, name, lines, pos2]
var _dfis: Array = []            # [name, pos2, lines, [ [Label3D linie, Label3D ziel, Label3D min] … ] ]
var _dfi_t := 0.0


static func manifest() -> Dictionary:
	if not _man_loaded:
		_man_loaded = true
		var p := DIR + "MANIFEST.json"
		if FileAccess.file_exists(p):
			var j = JSON.parse_string(FileAccess.get_file_as_string(p))
			if j is Dictionary:
				_man = j
	return _man


static func scene(model: String) -> PackedScene:
	if _scenes.has(model):
		return _scenes[model]
	var p := DIR + model + ".glb"
	if not ResourceLoader.exists(p):
		p = String(FALLBACK.get(model, ""))
	var ps: PackedScene = load(p) if p != "" and ResourceLoader.exists(p) else null
	_scenes[model] = ps
	return ps


static func prewarm() -> void:
	for m in FALLBACK:
		scene(m)
	manifest()


static func model_info(model: String) -> Dictionary:
	return manifest().get("models", {}).get(model + ".glb", {})


static func _anchor(model: String, key: String, def_pos: Vector3, def_size := Vector2(0.4, 0.15)) -> Dictionary:
	## Anker aus dem Manifest: {"pos": Vector3, "normal": Vector3, "w", "h", "found"}
	var a = model_info(model).get("anchors", {}).get(key, null)
	if a is Dictionary:
		var p: Array = a.get("position", [def_pos.x, def_pos.y, def_pos.z])
		var n: Array = a.get("normal", [0, 0, 1])
		var sz = a.get("size", null)
		var w := def_size.x
		var h := def_size.y
		if sz is Array and sz.size() >= 2:
			w = float(sz[0])
			h = float(sz[1])
		return {"pos": Vector3(float(p[0]), float(p[1]), float(p[2])), "normal": Vector3(float(n[0]), float(n[1]), float(n[2])),
			"w": w, "h": h, "found": true}
	return {"pos": def_pos, "normal": Vector3(0, 0, 1), "w": def_size.x, "h": def_size.y, "found": false}


func build(t: Terrain, data: Dictionary) -> void:
	terrain = t
	if data.is_empty():
		return
	_platforms(data.get("platforms", []))
	for m in data.get("masts", []):
		_mast(m)
	for s in data.get("shelters", []):
		_place(String(s[0]), float(s[1]), float(s[2]), float(s[3]), float(s[4]))
		_shelter_name(String(s[0]), float(s[1]), float(s[2]), float(s[3]), float(s[4]), String(s[5]))
	for d in data.get("dfis", []):
		_dfi(d)
	for b in data.get("bins", []):
		_place("stop_bin", float(b[0]), float(b[1]), float(b[2]), float(b[3]))
	set_process(not _label_specs.is_empty() or not _dfi_specs.is_empty())


func _place(model: String, x: float, z: float, yaw: float, y: float) -> Node3D:
	var ps := scene(model)
	if ps == null:
		return null
	var n := ps.instantiate() as Node3D
	n.transform = Transform3D(Basis(Vector3.UP, yaw), Vector3(x, y, z))
	var vr: float = VIS.get(model, 200.0)
	var stack: Array = [n]
	while not stack.is_empty():
		var c: Node = stack.pop_back()
		stack.append_array(c.get_children())
		if c is GeometryInstance3D:
			(c as GeometryInstance3D).visibility_range_end = vr
			(c as GeometryInstance3D).gi_mode = GeometryInstance3D.GI_MODE_DISABLED
		if c is MeshInstance3D:
			_fix_emit(c as MeshInstance3D)
	add_child(n)
	return n


static func _fix_emit(mi: MeshInstance3D) -> void:
	## Vitrinen/Anzeigen nachts beleuchtet (Material PosterEmit/DfiEmit: Emission dauerhaft schwach)
	if mi.mesh == null:
		return
	for i in mi.mesh.get_surface_count():
		var m := mi.mesh.surface_get_material(i) as StandardMaterial3D
		if m == null:
			continue
		var nm := String(m.resource_name)
		if nm.begins_with("PosterEmit") or nm.begins_with("ShelterLightEmit") or nm.begins_with("DfiEmit"):
			if not m.emission_enabled:
				m.emission_enabled = true
				m.emission = Color(1.0, 0.97, 0.9) if not nm.begins_with("DfiEmit") else Color(0.02, 0.02, 0.02)
				if nm.begins_with("PosterEmit"):
					m.emission_texture = m.albedo_texture
			if not Trams.emit_mats.has(m):
				Trams.emit_mats.append(m)       # nachts heller (Trams.set_night)


# --- Masten ------------------------------------------------------------------------------------------------
func _mast(m: Array) -> void:
	var x := float(m[0])
	var z := float(m[1])
	var yaw := float(m[2])
	var y := float(m[3])
	var name := String(m[4])
	var rows: Array = m[8] if m.size() > 8 else []
	if rows.is_empty():
		for l in String(m[5]).split(",", false):
			rows.append([l.strip_edges(), ""])
	var dfi := String(m[9]) if m.size() > 9 else ""
	var mast := _place("dvb_mast", x, z, yaw, y)
	var basis := Basis(Vector3.UP, yaw)
	var sign: Dictionary = model_info("dvb_mast").get("sign", {})
	var pitch := float(sign.get("row_pitch", 0.1))
	var nrows := mini(rows.size(), 7)
	for sfx in ["", "_Back"]:
		var an := _anchor("dvb_mast", "Anchor_Name" + sfx, Vector3(0.014, 2.822, 0.398), Vector2(0.54, 0.176))
		var ar := _anchor("dvb_mast", "Anchor_Row0" + sfx, Vector3(0.014, 2.682, 0.398), Vector2(0.54, 0.096))
		var nrm: Vector3 = an["normal"]
		var face := basis * Basis.looking_at(-nrm, Vector3.UP)
		var c0: Vector3 = Vector3(x, y, z) + basis * (an["pos"] + nrm * 0.004)
		_text_spec(name, Transform3D(face, c0), an["w"] * 0.94, an["h"] * 0.62, Color(0.06, 0.06, 0.06), 60.0)
		var rw: float = ar["w"]
		var rh: float = ar["h"]
		var right := face.x                     # Leserichtung auf dieser Seite
		for i in nrows:
			var r: Array = rows[i]
			var cr: Vector3 = Vector3(x, y, z) + basis * (ar["pos"] - Vector3(0, pitch * i, 0) + nrm * 0.004)
			# Nummer fett links (Feld ~0,14 m), Ziel rechts daneben, kleiner
			_text_spec(String(r[0]), Transform3D(face, cr + right * (-rw * 0.5 + 0.075)), 0.13, rh * 0.7, Color(0.04, 0.04, 0.04), 45.0)
			if String(r[1]) != "":
				_text_spec(String(r[1]), Transform3D(face, cr + right * (-rw * 0.5 + 0.165)), rw - 0.18, rh * 0.36,
					Color(0.08, 0.08, 0.08), 30.0, HORIZONTAL_ALIGNMENT_LEFT)
	if dfi != "" and mast != null:
		# LED-Modul unter den Linienzeilen (Manifest: position.y = stack_top_y - n*row_pitch)
		var top := float(sign.get("stack_top_y", 2.73)) - pitch * nrows
		var dy := top - float(model_info("dfi_small").get("default_position_y", 2.63))
		var mod := _place("dfi_small", x, z, yaw, y + dy)
		if mod != null:
			for sfx in ["", "_Back"]:
				var a := _anchor("dfi_small", "Anchor_Display" + sfx, Vector3(0.0155, 2.495, 0.398), Vector2(0.46, 0.19))
				var nrm: Vector3 = a["normal"]
				var face := basis * Basis.looking_at(-nrm, Vector3.UP)
				var c: Vector3 = Vector3(x, y + dy, z) + basis * (a["pos"] + nrm * 0.004)
				var dv := Vector2(float(m[10]), float(m[11])) if m.size() > 11 else Vector2.ZERO
				_dfi_specs.append([Transform3D(face, c), a["w"], a["h"], name, String(m[5]), Vector2(x, z), dv])


func _shelter_name(model: String, x: float, z: float, yaw: float, y: float, name: String) -> void:
	if name == "":
		return
	var basis := Basis(Vector3.UP, yaw)
	for sfx in ["", "_Back"]:
		var an := _anchor(model, "Anchor_Name" + sfx, Vector3(-0.9, 2.58, -0.742), Vector2(1.9, 0.13))
		if not an["found"] and sfx != "":
			continue
		var nrm: Vector3 = an["normal"] if an["found"] else Vector3(0, 0, -1)
		var face := basis * Basis.looking_at(-nrm, Vector3.UP)
		var c0: Vector3 = Vector3(x, y, z) + basis * (an["pos"] + nrm * 0.004)
		_text_spec(name, Transform3D(face, c0), an["w"] * 0.95, an["h"] * 0.8, Color(0.08, 0.08, 0.08), 80.0)


func _text_spec(txt: String, xf: Transform3D, w: float, h: float, col: Color, vis: float,
		align := HORIZONTAL_ALIGNMENT_CENTER) -> void:
	if txt == "":
		return
	var f: Font = ThemeDB.fallback_font
	var sz := f.get_string_size(txt, HORIZONTAL_ALIGNMENT_CENTER, -1, 64)
	var ps := minf(w / maxf(sz.x, 1.0), h / maxf(sz.y, 1.0))
	_label_specs.append({"text": txt, "font_size": 64, "pixel_size": ps, "modulate": col, "outline_size": 0,
		"shaded": true, "double_sided": false, "alpha_cut": Label3D.ALPHA_CUT_DISCARD, "visibility_range_end": vis,
		"horizontal_alignment": align, "transform": xf})


# --- Abfahrtsanzeiger ------------------------------------------------------------------------------------------
func _dfi(d: Array) -> void:
	var model := String(d[0])
	var x := float(d[1])
	var z := float(d[2])
	var yaw := float(d[3])
	var y := float(d[4])
	var n := _place(model, x, z, yaw, y)
	if n == null:
		return
	var basis := Basis(Vector3.UP, yaw)
	for sfx in ["", "_Back"]:
		var a := _anchor(model, "Anchor_Display" + sfx, Vector3(0.083, 3.0, 0.63), Vector2(0.8, 0.7))
		if not a["found"]:
			continue
		var nrm: Vector3 = a["normal"]
		var face := basis * Basis.looking_at(-nrm, Vector3.UP)
		var c: Vector3 = Vector3(x, y, z) + basis * (a["pos"] + nrm * 0.006)
		var dv := Vector2(float(d[7]), float(d[8])) if d.size() > 8 else Vector2.ZERO
		_dfi_specs.append([Transform3D(face, c), a["w"], a["h"], String(d[5]), String(d[6]), Vector2(x, z), dv])


static func _mat(key: String, c: Color) -> StandardMaterial3D:
	if _mats.has(key):
		return _mats[key]
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.roughness = 0.6
	_mats[key] = m
	return m


func _make_dfi(spec: Array) -> void:
	var xf: Transform3D = spec[0]
	var w: float = spec[1]
	var h: float = spec[2]
	var rows: Array = []
	var nrows := 6 if h > 0.5 else 3
	var rh := h / float(nrows)
	for i in nrows:
		var yv := h * 0.5 - rh * (i + 0.5)
		var row: Array = []
		for col in [[-w * 0.5 + w * 0.08, w * 0.14, HORIZONTAL_ALIGNMENT_CENTER], [-w * 0.5 + w * 0.17 + w * 0.29, w * 0.58, HORIZONTAL_ALIGNMENT_LEFT],
				[w * 0.5 - w * 0.11, w * 0.2, HORIZONTAL_ALIGNMENT_RIGHT]]:
			var lb := Label3D.new()
			lb.font_size = 48
			lb.pixel_size = rh * 0.62 / 48.0
			lb.modulate = LedSign.COLOR
			lb.outline_size = 0
			lb.shaded = false
			lb.double_sided = false
			lb.alpha_cut = Label3D.ALPHA_CUT_DISCARD
			lb.horizontal_alignment = col[2]
			lb.visibility_range_end = 60.0
			# Spaltenanker: links-/rechtsbündige Label3D haben ihren Ursprung an der linken/rechten Textkante
			var off := Vector3(float(col[0]), yv, 0.0)
			if col[2] == HORIZONTAL_ALIGNMENT_LEFT:
				off.x = -w * 0.5 + w * 0.17
			elif col[2] == HORIZONTAL_ALIGNMENT_RIGHT:
				off.x = w * 0.5 - w * 0.02
			lb.transform = Transform3D(xf.basis, xf.origin + xf.basis * off)
			add_child(lb)
			row.append(lb)
		rows.append(row)
	_dfis.append([String(spec[3]), spec[5], String(spec[4]).replace(" ", "").split(",", false), rows,
		spec[6] if spec.size() > 6 else Vector2.ZERO, w * 0.56])


func _update_dfis() -> void:
	for d in _dfis:
		var rows: Array = d[3]
		var dep := Departures.board(String(d[0]), d[1], d[2], rows.size(), d[4])
		for i in rows.size():
			var r: Array = rows[i]
			if i < dep.size():
				(r[0] as Label3D).text = String(dep[i][0])
				(r[1] as Label3D).text = _fit_text(String(dep[i][1]), r[1] as Label3D, float(d[5]))
				(r[2] as Label3D).text = Departures.fmt_min(float(dep[i][2]))
			else:
				for lb in r:
					(lb as Label3D).text = ""


static func _fit_text(txt: String, lb: Label3D, max_w: float) -> String:
	## Ziel kürzen, bis es in die Spalte passt (sonst überlappt es die Minutenangabe)
	var f: Font = ThemeDB.fallback_font
	var t := txt
	while t.length() > 3 and f.get_string_size(t, HORIZONTAL_ALIGNMENT_LEFT, -1, lb.font_size).x * lb.pixel_size > max_w:
		t = t.substr(0, t.length() - 2).strip_edges() + "."
		t = t.trim_suffix("..") + ("" if t.ends_with(".") else "")
	return t


func _process(delta: float) -> void:
	var n := 0
	while n < 60 and not _label_specs.is_empty():
		var spec: Dictionary = _label_specs.pop_back()
		var lb := Label3D.new()
		for k in spec:
			lb.set(k, spec[k])
		add_child(lb)
		n += 1
	while n < 80 and not _dfi_specs.is_empty():
		_make_dfi(_dfi_specs.pop_back())
		n += 6
	if _dfis.is_empty():
		if _label_specs.is_empty() and _dfi_specs.is_empty():
			set_process(false)
		return
	_dfi_t -= delta
	if _dfi_t <= 0.0:
		_dfi_t = 4.0
		var cam := get_viewport().get_camera_3d()
		if cam == null or _near(cam.global_position):
			_update_dfis()


func _near(p: Vector3) -> bool:
	for d in _dfis:
		if (d[1] as Vector2).distance_to(Vector2(p.x, p.z)) < 120.0:
			return true
	return false


# --- Bahnsteige ------------------------------------------------------------------------------------------------
func _platforms(plats: Array) -> void:
	if plats.is_empty():
		return
	var top := SurfaceTool.new()
	var side := SurfaceTool.new()
	var tact := SurfaceTool.new()
	for st in [top, side, tact]:
		st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var col := PackedVector3Array()
	for p in plats:
		var pts: Array = p["pts"]
		var h := float(p["h"])
		var n := pts.size()
		var v: Array = []
		for q in pts:
			v.append(Vector3(float(q[0]), float(q[2]), float(q[1])))
		var tris: Array = p["tris"]
		for i in range(0, tris.size(), 3):
			var a: Vector3 = v[int(tris[i])]
			var b: Vector3 = v[int(tris[i + 1])]
			var c: Vector3 = v[int(tris[i + 2])]
			var nn := (b - a).cross(c - a)
			if nn.y < 0.0:
				var tmp := b
				b = c
				c = tmp
			for q in [a, c, b]:
				top.set_normal(Vector3.UP)
				top.set_uv(Vector2(q.x, q.z) * 0.5)
				top.add_vertex(q)
				col.append(q)
		# Seitenflächen rundum (Bordstein), bis knapp unter Boden
		for i in n:
			var a: Vector3 = v[i]
			var b: Vector3 = v[(i + 1) % n]
			var ga := minf(terrain.height_at(a.x, a.z), a.y - h) - 0.06
			var gb := minf(terrain.height_at(b.x, b.z), b.y - h) - 0.06
			var a0 := Vector3(a.x, ga, a.z)
			var b0 := Vector3(b.x, gb, b.z)
			var nrm := (b - a).cross(Vector3.UP).normalized()
			var L := a.distance_to(b)
			var quad := [[a, Vector2(0, 0)], [b0, Vector2(L, h)], [a0, Vector2(0, h)],
					[a, Vector2(0, 0)], [b, Vector2(L, 0)], [b0, Vector2(L, h)]]
			# beidseitig (Umlaufsinn der Pipeline-Umrisse nicht garantiert)
			for sgn in [1.0, -1.0]:
				for k in 6:
					var q: Array = quad[k if sgn > 0.0 else 5 - k]
					side.set_normal(nrm * sgn)
					side.set_uv(q[1] * 2.0)
					side.add_vertex(q[0])
			for q in [a, b0, a0, a, b, b0]:
				col.append(q)
		# Leitstreifen (Rillenplatten) 0,30 m breit, 0,6 m hinter der Kante
		var edge: Array = p.get("edge", [])
		if edge.size() >= 2:
			for i in edge.size() - 1:
				var a: Vector3 = v[int(edge[i])]
				var b: Vector3 = v[int(edge[i + 1])]
				var dirv := (b - a)
				dirv.y = 0.0
				if dirv.length() < 0.01:
					continue
				var inward := Vector3(-dirv.z, 0, dirv.x).normalized()
				# nach innen zeigt die Richtung zum Bahnsteiginneren (gegenüber liegender Umrisspunkt)
				var opp: Vector3 = v[n - 1 - int(edge[i])]
				if inward.dot(opp - a) < 0.0:
					inward = -inward
				var o0 := inward * 0.6
				var o1 := inward * 0.9
				var lift := Vector3(0, 0.006, 0)
				var q := [a + o0 + lift, b + o0 + lift, b + o1 + lift, a + o1 + lift]
				for k in [0, 2, 1, 0, 3, 2, 0, 1, 2, 0, 2, 3]:
					tact.set_normal(Vector3.UP)
					tact.set_uv(Vector2(q[k].x, q[k].z) * 3.0)
					tact.add_vertex(q[k])
	var mesh := ArrayMesh.new()
	top.commit(mesh)
	mesh.surface_set_material(0, TexLib.tri_material("sidewalk", 1.0))
	side.commit(mesh)
	mesh.surface_set_material(1, TexLib.tri_material("paving_sandstone", 0.78))
	tact.commit(mesh)
	if mesh.get_surface_count() > 2:
		mesh.surface_set_material(2, _mat("tactile", Color(0.86, 0.86, 0.84)))
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	mi.visibility_range_end = 700.0
	add_child(mi)
	if col.size() >= 3:
		var body := StaticBody3D.new()
		var cs := CollisionShape3D.new()
		var shp := ConcavePolygonShape3D.new()
		shp.set_faces(col)
		cs.shape = shp
		body.add_child(cs)
		add_child(body)
