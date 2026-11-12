class_name Dressing
extends Node3D
## Straßenausstattung: Bäume, Laternen, Ampeln, Bänke usw. (MultiMesh je Zelle und Modell).

const PROPS := "res://assets/models/props/"
const CELL := 125.0
const ALTMARKT := Vector2(494.0, 12.0)
const BROAD := ["tree_linden", "tree_linden_b", "tree_maple", "tree_maple_b", "tree_plane", "tree_plane_b"]
const NEEDLE := ["tree_pine", "tree_pine_b"]
const SMALL := ["tree_small", "tree_small_b"]

var terrain: Terrain
var index: RoadIndex
var lamp_mats: Array = []
var lamp_heads: Array[Vector3] = []
var signal_sets := [{}, {}]        # je Gruppe: {"red": Mat, "yellow": Mat, "green": Mat}
var signal_nodes: Array = []        # {pos: Vector2, group: int}
var lights: Array[SpotLight3D] = []
static var _part_cache := {}   # statisch: einmal im Haupt-Thread vorgeladen (prewarm), Kachel-Thread liest nur
static var _model_h := {}
static var _sig_parts: Array = []


## Im Haupt-Thread vor dem ersten Kachelaufbau: alle Modelle einmal zerlegen (gleichzeitiges Instanziieren
## derselben Szene im Kachel-Thread und im Haupt-Thread (TreeLOD, KI) führte zu Abstürzen).
static func prewarm() -> void:
	var d := Dressing.new()
	for nm in BROAD + NEEDLE + SMALL + ["tree_linden", "tree_pine", "tree_small"] + LAMP_MODELS + [
			"traffic_light", "bench", "bin", "bike_rack"]:
		d._parts(nm)
	d._signal_head_parts()
	far_material()
	d.free()
var _light_timer := 0.0
var night := 0.0
static var clock := 0.0     # gemeinsame Ampeluhr (vom World-Manager gesetzt)


func build(t: Terrain, city: Dictionary, idx: RoadIndex) -> void:
	terrain = t
	index = idx
	if OS.has_environment("DRESDEN_TRACE"): print("  T _trees")
	_trees(city["trees"])
	if OS.has_environment("DRESDEN_TRACE"): print("  T _lamps")
	_lamps(city["lamps"])
	if city.has("signal_heads"):
		if OS.has_environment("DRESDEN_TRACE"): print("  T _signal_heads")
		_signal_heads(city["signal_heads"], city.get("graph", {}).get("ctls", []))
	else:
		_signals(city["signals"])
	# Bänke/Mülleimer/Radständer setzt bei vorhandenem Straßenleben street_life.gd (sonst doppelt)
	if city.get("life", {}).get("furniture", []).is_empty():
		_props(city["props"])
	for i in 6:
		var sl := SpotLight3D.new()
		sl.visible = false
		sl.spot_range = 26.0
		sl.spot_angle = 75.0
		sl.spot_angle_attenuation = 0.8
		sl.light_color = Color(1.0, 0.78, 0.5)
		sl.light_energy = 0.0
		sl.shadow_enabled = false
		sl.rotation_degrees = Vector3(-90, 0, 0)
		add_child(sl)
		lights.append(sl)


func _parts(name: String) -> Array:
	if _part_cache.has(name):
		return _part_cache[name]
	var res: Array = []
	var ps := load(PROPS + name + ".glb") as PackedScene
	if ps == null:
		_part_cache[name] = res
		return res
	var root := ps.instantiate()
	var top := 0.0
	var stack: Array = [[root, Transform3D.IDENTITY]]
	while not stack.is_empty():
		var it: Array = stack.pop_back()
		var n: Node = it[0]
		var xf: Transform3D = it[1]
		if n is Node3D and n != root:
			xf = xf * (n as Node3D).transform
		if n is MeshInstance3D and (n as MeshInstance3D).mesh != null:
			var mi := n as MeshInstance3D
			res.append({"mesh": mi.mesh, "xf": xf})
			top = maxf(top, (xf * mi.get_aabb()).end.y)
		for c in n.get_children():
			stack.append([c, xf])
	root.free()
	_model_h[name] = maxf(top, 0.1)
	_part_cache[name] = res
	return res


func _cell(x: float, z: float) -> Vector2i:
	return Vector2i(floori((x + 1000.0) / CELL), floori((z + 1000.0) / CELL))


func _spawn(name: String, by_cell: Dictionary, range_end: float, shadows: bool = true, parts_override: Array = []) -> void:
	var parts := parts_override if not parts_override.is_empty() else _parts(name)
	for key in by_cell:
		var xfs: Array = by_cell[key]
		for part in parts:
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			mm.mesh = part["mesh"]
			RenderUtil.fill_multimesh(mm, xfs, part["xf"])
			var inst := MultiMeshInstance3D.new()
			inst.multimesh = mm
			inst.visibility_range_end = range_end
			inst.visibility_range_end_margin = range_end * 0.15
			inst.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
			if not shadows:
				inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			add_child(inst)


func _hash01(a: float, b: float) -> float:
	return fposmod(sin(a * 12.9898 + b * 78.233) * 43758.5453, 1.0)


const SPECIES := ["tree_linden", "tree_linden_b", "tree_maple", "tree_maple_b", "tree_plane", "tree_plane_b", "tree_pine", "tree_pine_b", "tree_small", "tree_small_b"]
var tree_data := {}     # für TreeLOD: pos, sp, xf, mm, mi, grid
static var _blob_cache := {}
static var _blob_mat: Material


static func far_material() -> Material:
	## Fernkronen: Laubklumpen-Shader (shaders/tree_far.gdshader), im Haupt-Thread vorgewärmt (prewarm)
	if _blob_mat == null:
		var m := ShaderMaterial.new()
		m.shader = load("res://shaders/tree_far.gdshader")
		_blob_mat = m
	return _blob_mat


func _blob_for(name: String, needle: bool) -> ArrayMesh:
	## Einfache Krone (Ellipsoid/Kegel + Stamm) in den Maßen des Baummodells, für die Ferne.
	if _blob_cache.has(name):
		return _blob_cache[name]
	var parts := _parts(name)
	var bb := AABB()
	var first := true
	for p in parts:
		var ab: AABB = (p["xf"] as Transform3D) * (p["mesh"] as Mesh).get_aabb()
		bb = ab if first else bb.merge(ab)
		first = false
	var rxz := maxf(bb.size.x, bb.size.z) * 0.5
	var top := bb.end.y
	var verts := PackedVector3Array()
	var norms := PackedVector3Array()
	var cols := PackedColorArray()
	var idx := PackedInt32Array()
	var base_col := Color(0.17, 0.30, 0.10)
	if name.begins_with("tree_pine"):
		base_col = Color(0.07, 0.19, 0.09)
	elif name.begins_with("tree_small"):
		base_col = Color(0.20, 0.33, 0.12)
	var cm: Mesh
	if needle:
		var cone := CylinderMesh.new()
		cone.top_radius = 0.0
		cone.bottom_radius = rxz * 0.85
		cone.height = top * 0.8
		cone.radial_segments = 8
		cone.rings = 1
		cm = cone
	else:
		var sp := SphereMesh.new()
		sp.radius = 1.0
		sp.height = 2.0
		sp.radial_segments = 12
		sp.rings = 6
		cm = sp
	var arrs: Array = cm.get_mesh_arrays()
	var pv: PackedVector3Array = arrs[Mesh.ARRAY_VERTEX]
	var pn: PackedVector3Array = arrs[Mesh.ARRAY_NORMAL]
	var pi: PackedInt32Array = arrs[Mesh.ARRAY_INDEX]
	var cy := top * (0.5 if needle else 0.66)
	# knubbeliger Umriss: Radius je Richtung mit einigen Beulen (Laubballen) und abgeflachter Unterseite;
	# gleiche Richtung = gleicher Versatz (Nahtstellen der Kugel bleiben geschlossen)
	var ph := float(name.hash() % 997) * 0.37
	for i in pv.size():
		var v := pv[i]
		var dn := v.normalized() if v.length() > 1e-4 else Vector3.UP
		if not needle:
			var lump := 0.16 * sin(dn.x * 4.1 + ph) * sin(dn.z * 3.7 - ph * 0.6) + 0.1 * sin(dn.y * 5.3 + dn.x * 2.9 + ph * 1.3) \
				+ 0.07 * sin((dn.x + dn.z) * 7.9 + ph * 2.1)
			var rr := 1.0 + lump - (0.12 if dn.y < -0.3 else 0.0)
			v = Vector3(dn.x * rxz * rr, dn.y * top * 0.36 * rr, dn.z * rxz * rr)
		else:
			var jag := 1.0 + 0.12 * sin(v.y * 9.0 + atan2(v.z, v.x) * 4.0 + ph)
			v = Vector3(v.x * jag, v.y, v.z * jag)
		var noise := 0.85 + 0.3 * fposmod(sin(v.x * 7.3 + v.y * 3.1 + v.z * 5.7) * 43758.5, 1.0)
		verts.append(v + Vector3(0, cy, 0))
		norms.append(pn[i])
		cols.append(Color(base_col.r * noise, base_col.g * noise, base_col.b * noise, 1.0))
	idx.append_array(pi)
	# Stamm
	var tr := CylinderMesh.new()
	tr.top_radius = 0.18
	tr.bottom_radius = 0.28
	tr.height = top * 0.45
	tr.radial_segments = 5
	tr.rings = 1
	var ta: Array = tr.get_mesh_arrays()
	var tv: PackedVector3Array = ta[Mesh.ARRAY_VERTEX]
	var tn: PackedVector3Array = ta[Mesh.ARRAY_NORMAL]
	var ti: PackedInt32Array = ta[Mesh.ARRAY_INDEX]
	var k := verts.size()
	for i in tv.size():
		verts.append(tv[i] + Vector3(0, top * 0.225, 0))
		norms.append(tn[i])
		cols.append(Color(0.2, 0.15, 0.1, 0.0))     # Alpha 0 = Stamm (tree_far.gdshader)
	for i in ti:
		idx.append(i + k)
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = verts
	arr[Mesh.ARRAY_NORMAL] = norms
	arr[Mesh.ARRAY_COLOR] = cols
	arr[Mesh.ARRAY_INDEX] = idx
	# Normalen der verbeulten Krone neu berechnen (sonst Beleuchtung wie Kugel)
	var st := SurfaceTool.new()
	st.create_from_arrays(arr)
	st.generate_normals()
	var mesh := st.commit()
	mesh.surface_set_material(0, far_material())
	_blob_cache[name] = mesh
	return mesh


func _trees(trees: Array) -> void:
	var pos := PackedVector3Array()
	var sp := PackedInt32Array()
	var xfs: Array = []
	var mm_ref: Array = []
	var mm_idx := PackedInt32Array()
	var cls_groups := {}    # [klasse, zelle] -> Array [entry, blob_xf]
	var ref_h := {}
	for cl in 3:
		var nm: String = ["tree_linden", "tree_pine", "tree_small"][cl]
		_parts(nm)
		ref_h[cl] = float(_model_h.get(nm, 15.0))
	for t in trees:
		var h: float = t[3]
		var r := _hash01(t[0], t[1])
		var name: String
		var cl := 0
		var hint := String(t[6]) if t.size() > 6 else ""
		if int(t[4]) == 1:
			name = NEEDLE[int(r * 2) % 2]
			cl = 1
		elif hint in SMALL or (hint == "" and h < 6.5):
			name = hint if hint in SMALL else SMALL[int(r * 2) % 2]
			cl = 2
		elif hint in BROAD:
			name = hint                    # Baumart aus dem Dresdner Baumkataster
		else:
			name = BROAD[int(r * 6) % 6]
		_parts(name)
		var mh: float = _model_h.get(name, 15.0)
		var s := clampf(h / mh, 0.5, 2.4)
		var yaw := r * TAU
		var p := Vector3(t[0], t[2] - 0.1, t[1])
		var xf := Transform3D(Basis(Vector3.UP, yaw).scaled(Vector3.ONE * s), p)
		var entry := pos.size()
		pos.append(p)
		sp.append(SPECIES.find(name))
		xfs.append(xf)
		mm_ref.append(null)
		mm_idx.append(0)
		var bxf := Transform3D(Basis(Vector3.UP, yaw).scaled(Vector3.ONE * s * mh / float(ref_h[cl])), p)
		var key := [cl, _cell(t[0], t[1])]
		if not cls_groups.has(key):
			cls_groups[key] = []
		cls_groups[key].append([entry, bxf])
	for key in cls_groups:
		var list: Array = cls_groups[key]
		var cl: int = key[0]
		var blob := _blob_for(["tree_linden", "tree_pine", "tree_small"][cl], cl == 1)
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = blob
		var bx: Array = []
		for i in list.size():
			bx.append(list[i][1])
			mm_ref[list[i][0]] = mm
			mm_idx[list[i][0]] = i
		RenderUtil.fill_multimesh(mm, bx)
		var inst := MultiMeshInstance3D.new()
		inst.multimesh = mm
		inst.visibility_range_end = 420.0
		inst.visibility_range_end_margin = 40.0
		inst.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_DISABLED
		inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(inst)
	# räumliches Gitter (32 m) für TreeLOD
	var grid := {}
	for i in pos.size():
		var gk := Vector2i(floori(pos[i].x / 32.0), floori(pos[i].z / 32.0))
		if not grid.has(gk):
			grid[gk] = []
		grid[gk].append(i)
	var xf_far: Array = []
	xf_far.resize(pos.size())
	for key in cls_groups:
		for it in cls_groups[key]:
			xf_far[it[0]] = it[1]
	tree_data = {"pos": pos, "sp": sp, "xf": xfs, "xf_far": xf_far, "mm": mm_ref, "mi": mm_idx, "grid": grid, "near": {}}


func _yaw_arm_neg_z(d: Vector2) -> float:
	return atan2(-d.x, -d.y)


# Leuchtentypen (Pipeline build_lamps): 0 moderne Mastleuchte (LED), 1 historischer Kandelaber, 2 Gaslaterne,
# 3 DDR-Peitschenmast (Natriumdampf). Kopf = Lichtpunkt im Modell (Ausleger zeigt nach -Z zur Fahrbahn).
const LAMP_MODELS := ["streetlamp", "streetlamp_old", "streetlamp_gas", "streetlamp_whip"]
const LAMP_HEAD := [Vector3(0, 7.6, -2.5), Vector3(0, 3.9, 0), Vector3(0, 3.4, 0), Vector3(0, 8.9, -2.29)]
const LAMP_COLOR := [Color(0.98, 0.95, 0.88), Color(1.0, 0.82, 0.55), Color(1.0, 0.86, 0.62), Color(1.0, 0.66, 0.3)]


func _lamps(lamps: Array) -> void:
	var groups := {}
	for nm in LAMP_MODELS:
		groups[nm] = {}
	for l in lamps:
		var p := Vector2(l[0], l[1])
		var hit := index.nearest(p.x, p.y, 30.0)
		var yaw := _hash01(l[0], l[1]) * TAU
		if not hit.is_empty():
			var d := Vector2(hit["px"] - p.x, hit["pz"] - p.y)
			if d.length() > 0.1:
				yaw = _yaw_arm_neg_z(d.normalized())
		var lt := int(l[3]) if l.size() > 3 and int(l[3]) >= 0 else (1 if p.distance_to(ALTMARKT) < 380.0 else 0)
		if lt >= LAMP_MODELS.size() or not ResourceLoader.exists(PROPS + String(LAMP_MODELS[lt]) + ".glb"):
			lt = 0
		var name: String = LAMP_MODELS[lt]
		var xf := Transform3D(Basis(Vector3.UP, yaw), Vector3(l[0], l[2], l[1]))
		var cell := _cell(p.x, p.y)
		if not groups[name].has(cell):
			groups[name][cell] = []
		groups[name][cell].append(xf)
		lamp_heads.append(xf * (LAMP_HEAD[lt] as Vector3))
	for name in groups:
		if (groups[name] as Dictionary).is_empty():
			continue
		var parts := _parts(name)
		var col: Color = LAMP_COLOR[LAMP_MODELS.find(name)]
		for part in parts:
			var mesh: Mesh = part["mesh"]
			for s in mesh.get_surface_count():
				var m := mesh.surface_get_material(s)
				if m is StandardMaterial3D and m.resource_name == "LampEmit":
					m.emission_enabled = true
					m.emission = col
					m.emission_energy_multiplier = 0.0
					if not lamp_mats.has(m):
						lamp_mats.append(m)
		# dünne Masten: keine Schatten (tausende Leuchten je Kachel)
		_spawn(name, groups[name], 300.0, false)
	_light_pools()


func _light_pools() -> void:
	## Weicher Lichtfleck unter jeder Laterne (nur nachts sichtbar, kostet fast nichts)
	if lamp_heads.is_empty():
		return
	var quad := PlaneMesh.new()
	quad.size = Vector2(1, 1)
	var m := ShaderMaterial.new()
	m.shader = load("res://shaders/light_pool.gdshader")
	quad.material = m
	var by_cell := {}
	for h in lamp_heads:
		var c := _cell(h.x, h.z)
		if not by_cell.has(c):
			by_cell[c] = []
		by_cell[c].append(h)
	for c in by_cell:
		var list: Array = by_cell[c]
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = quad
		var lx: Array = []
		for i in list.size():
			var h: Vector3 = list[i]
			var gy := terrain.height_at(h.x, h.z)
			var r := clampf((h.y - gy) * 0.75, 2.5, 6.5)
			lx.append(Transform3D(Basis().scaled(Vector3(r * 2.0, 1.0, r * 2.0)), Vector3(h.x, gy + 0.05, h.z)))
		RenderUtil.fill_multimesh(mm, lx)
		var inst := MultiMeshInstance3D.new()
		inst.multimesh = mm
		inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		inst.visibility_range_end = 260.0
		inst.visibility_range_end_margin = 30.0
		inst.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
		add_child(inst)


func _signal_parts(group: int) -> Array:
	var base := _parts("traffic_light")
	var out: Array = []
	for part in base:
		var mesh: Mesh = (part["mesh"] as Mesh).duplicate()
		for s in mesh.get_surface_count():
			var m := mesh.surface_get_material(s)
			if m is StandardMaterial3D:
				var mm := m.duplicate() as StandardMaterial3D
				var rn := String(m.resource_name)
				mesh.surface_set_material(s, mm)
				var key := ""
				match rn:
					"LightRed": key = "red"
					"LightYellow": key = "yellow"
					"LightGreen": key = "green"
				if key != "":
					mm.emission_enabled = true
					mm.emission = {"red": Color(1, 0.1, 0.05), "yellow": Color(1, 0.7, 0.05), "green": Color(0.1, 1, 0.3)}[key]
					mm.emission_energy_multiplier = 0.0
					signal_sets[group][key] = mm
		out.append({"mesh": mesh, "xf": part["xf"]})
	return out


static var _lamp_mats := {}


static func _lamp_mat(key: String) -> ShaderMaterial:
	if not _lamp_mats.has(key):
		var m := ShaderMaterial.new()
		m.shader = load("res://shaders/signal_lamp.gdshader")
		var idx := {"red": 0, "yellow": 1, "green": 2}[key] as int
		m.set_shader_parameter("lamp", idx)
		m.set_shader_parameter("lamp_col", [Vector3(1.0, 0.1, 0.05), Vector3(1.0, 0.68, 0.05), Vector3(0.12, 1.0, 0.35)][idx])
		_lamp_mats[key] = m
	return _lamp_mats[key]


func _signal_head_parts() -> Array:
	if not _sig_parts.is_empty():
		return _sig_parts
	var res: Array = []
	for part in _parts("traffic_light"):
		var mesh: Mesh = (part["mesh"] as Mesh).duplicate()
		for si in mesh.get_surface_count():
			var m := mesh.surface_get_material(si)
			if m == null:
				continue
			match String(m.resource_name):
				"LightRed": mesh.surface_set_material(si, _lamp_mat("red"))
				"LightYellow": mesh.surface_set_material(si, _lamp_mat("yellow"))
				"LightGreen": mesh.surface_set_material(si, _lamp_mat("green"))
		res.append({"mesh": mesh, "xf": part["xf"]})
	_sig_parts = res
	return res


func _signal_heads(heads: Array, ctls: Array) -> void:
	## Ampelmasten je Zufahrt (tools/junctions.py): Leuchtzustand berechnet der Shader aus dem Umlauf der
	## Steuerung (INSTANCE_CUSTOM) und der Ampeluhr – synchron zur KI (SignalCtl.state).
	var parts := _signal_head_parts()
	if parts.is_empty() or heads.is_empty():
		return
	var by_cell := {}
	for h in heads:
		var ci := int(h[5])
		if ci < 0 or ci >= ctls.size():
			continue
		var c: Array = ctls[ci]
		var xf := Transform3D(Basis(Vector3.UP, float(h[3])), Vector3(float(h[0]), terrain.height_at(float(h[0]), float(h[1])), float(h[1])))
		var cell := _cell(float(h[0]), float(h[1]))
		if not by_cell.has(cell):
			by_cell[cell] = []
		by_cell[cell].append([xf, Color(float(c[0]), float(h[4]), float(c[1]), float(c[2]) if c.size() > 2 else 9.0)])
	for cell in by_cell:
		var list: Array = by_cell[cell]
		for part in parts:
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			mm.use_custom_data = true
			mm.mesh = part["mesh"]
			var sx: Array = []
			var sc: Array = []
			for it in list:
				sx.append(it[0])
				sc.append(it[1])
			RenderUtil.fill_multimesh(mm, sx, part["xf"], [], sc)
			var inst := MultiMeshInstance3D.new()
			inst.multimesh = mm
			inst.visibility_range_end = 260.0
			inst.visibility_range_end_margin = 30.0
			inst.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
			add_child(inst)
		# Kollision: Mast als dünner Zylinder
		var body := StaticBody3D.new()
		body.collision_layer = 1
		add_child(body)
		for e in list:
			var cs := CollisionShape3D.new()
			var cy := CylinderShape3D.new()
			cy.radius = 0.09
			cy.height = 4.0
			cs.shape = cy
			cs.transform = (e[0] as Transform3D) * Transform3D(Basis(), Vector3(0, 2.0, 0))
			body.add_child(cs)


func _signals(sigs: Array) -> void:
	var groups := [{}, {}]
	for sgn in sigs:
		var p := Vector2(sgn[0], sgn[1])
		var hit := index.nearest(p.x, p.y, 8.0)
		if hit.is_empty():
			continue
		var t := Vector2(hit["tx"], hit["tz"])
		var n := Vector2(-t.y, t.x)
		var w: float = hit["road"]["width"]
		var pos := Vector2(hit["px"], hit["pz"]) + n * (w * 0.5 + 0.9)
		var d := -n
		var yaw := atan2(-d.y, d.x)
		var group := 0 if absf(t.x) > absf(t.y) else 1
		var xf := Transform3D(Basis(Vector3.UP, yaw), Vector3(pos.x, terrain.height_at(pos.x, pos.y), pos.y))
		var cell := _cell(pos.x, pos.y)
		if not groups[group].has(cell):
			groups[group][cell] = []
		groups[group][cell].append(xf)
		signal_nodes.append({"pos": p, "group": group})
	for g in 2:
		_spawn("traffic_light", groups[g], 260.0, true, _signal_parts(g))


func _props(props: Array) -> void:
	var groups := {}
	var names := {"bench": "bench", "waste_basket": "bin", "bicycle_parking": "bike_rack"}
	for pr in props:
		var name: String = names.get(pr[3], "")
		if name == "":
			continue
		var p := Vector2(pr[0], pr[1])
		var hit := index.nearest(p.x, p.y, 25.0)
		var yaw := _hash01(p.x, p.y) * TAU
		if not hit.is_empty():
			var d := Vector2(hit["px"] - p.x, hit["pz"] - p.y)
			if d.length() > 0.1:
				yaw = _yaw_arm_neg_z(d.normalized())
		var xf := Transform3D(Basis(Vector3.UP, yaw), Vector3(p.x, pr[2], p.y))
		if not groups.has(name):
			groups[name] = {}
		var cell := _cell(p.x, p.y)
		if not groups[name].has(cell):
			groups[name][cell] = []
		groups[name][cell].append(xf)
	for name in groups:
		_spawn(name, groups[name], 140.0)


func set_night(n: float) -> void:
	night = n
	for m in lamp_mats:
		(m as StandardMaterial3D).emission_energy_multiplier = n * 7.0


func signal_state(group: int) -> String:
	## "green", "yellow" oder "red" für die jeweilige Gruppe (0: Ost-West, 1: Nord-Süd).
	var t := fposmod(Dressing.clock, 40.0)
	var a := t
	if group == 1:
		a = fposmod(t - 20.0, 40.0)
	if a < 16.0:
		return "green"
	if a < 19.0:
		return "yellow"
	return "red"


func _process(delta: float) -> void:
	for g in 2:
		var st := signal_state(g)
		var set_: Dictionary = signal_sets[g]
		if set_.has("red"):
			(set_["red"] as StandardMaterial3D).emission_energy_multiplier = 4.0 if st == "red" else 0.0
			(set_["yellow"] as StandardMaterial3D).emission_energy_multiplier = 4.0 if st == "yellow" else 0.0
			(set_["green"] as StandardMaterial3D).emission_energy_multiplier = 4.0 if st == "green" else 0.0


func update_lights(focus: Vector3, delta: float) -> void:
	_light_timer -= delta
	if _light_timer > 0.0:
		return
	_light_timer = 0.4
	var e := night
	# Die nächsten Laternen zum Fokus bekommen echtes Licht
	var cands: Array = []
	for h in lamp_heads:
		var d := h.distance_squared_to(focus)
		if d < 120.0 * 120.0:
			cands.append([d, h])
	cands.sort_custom(func(a, b): return a[0] < b[0])
	for i in lights.size():
		if i < cands.size() and e > 0.02:
			lights[i].visible = true
			lights[i].global_position = cands[i][1]
			lights[i].light_energy = e * 14.0
		else:
			lights[i].visible = false
