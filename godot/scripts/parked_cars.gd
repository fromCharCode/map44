class_name ParkedCars
extends Node3D
## Geparkte Autos am Straßenrand, Gullydeckel und Entwässerungsgitter (MultiMesh je Zelle, mit Kollision).

const CELL := 125.0
const MODELS := ["hatchback.glb", "sedan.glb", "van.glb", "citycar.glb"]
const SIZES := {"hatchback.glb": Vector3(1.8, 1.4, 4.3), "sedan.glb": Vector3(1.8, 1.4, 4.7), "van.glb": Vector3(2.0, 2.3, 5.9), "citycar.glb": Vector3(1.65, 1.45, 3.6)}
const COLORS := [
	Color(0.9, 0.9, 0.88), Color(0.72, 0.73, 0.76), Color(0.1, 0.1, 0.11), Color(0.15, 0.2, 0.32),
	Color(0.5, 0.07, 0.09), Color(0.33, 0.34, 0.36), Color(0.14, 0.28, 0.2), Color(0.82, 0.78, 0.65),
	Color(0.55, 0.57, 0.6), Color(0.78, 0.3, 0.08),
]

var terrain: Terrain
var _parts := {}


func build(t: Terrain, city: Dictionary) -> void:
	terrain = t
	_cars(city["parked"])
	_details(city["manholes"], city["grates"])


static var _static_parts := {}


## Im Haupt-Thread vor dem ersten Kachelaufbau aufrufen: Fahrzeugmodelle einmal zerlegen. Der Kachel-Thread
## liest danach nur noch (gleichzeitiges Instanziieren derselben Szene in zwei Threads führte zu Abstürzen).
static func prewarm() -> void:
	var tmp := ParkedCars.new()
	for f in MODELS:
		_static_parts[f] = tmp._build_parts(f)
	tmp.free()


func _model_parts(file: String) -> Array:
	if _static_parts.has(file):
		return _static_parts[file]
	if _parts.has(file):
		return _parts[file]
	_parts[file] = _build_parts(file)
	return _parts[file]


func _build_parts(file: String) -> Array:
	var res: Array = []
	var ps := load(CarModel.DIR + file) as PackedScene
	var root := ps.instantiate()
	var paint := StandardMaterial3D.new()
	paint.vertex_color_use_as_albedo = true
	paint.metallic = 0.45
	paint.metallic_specular = 0.6
	paint.roughness = 0.32
	paint.clearcoat_enabled = true
	paint.clearcoat = 1.0
	paint.clearcoat_roughness = 0.05
	var stack: Array = [[root, Transform3D.IDENTITY]]
	while not stack.is_empty():
		var it: Array = stack.pop_back()
		var n: Node = it[0]
		var xf: Transform3D = it[1]
		if n is Node3D and n != root:
			xf = xf * (n as Node3D).transform
		if n is MeshInstance3D:
			var mesh := (n as MeshInstance3D).mesh.duplicate() as Mesh
			for i in mesh.get_surface_count():
				var m := mesh.surface_get_material(i)
				if m == null:
					continue
				match String(m.resource_name):
					"CarPaint":
						mesh.surface_set_material(i, paint)
					"Glass":
						mesh.surface_set_material(i, CarModel.glass_material())
			res.append({"mesh": mesh, "xf": xf})
		for c in n.get_children():
			stack.append([c, xf])
	root.free()
	return res


func _cell(x: float, z: float) -> Vector2i:
	return Vector2i(floori((x + 1000.0) / CELL), floori((z + 1000.0) / CELL))


func _cars(parked: Array) -> void:
	var groups := {}   # [file, cell] -> Array[[xf, color]]
	for pk in parked:
		var file: String = MODELS[int(pk[3]) % MODELS.size()]
		if file == "van.glb" and int(pk[3]) % 7 != 0:
			file = "hatchback.glb"
		var pos := Vector3(pk[0], 0, pk[1])
		var xf := _fit_ground(pos, float(pk[2]), SIZES.get(file, Vector3(1.8, 1.4, 4.4)))
		var color: Color = COLORS[(int(pk[3]) / 3) % COLORS.size()]
		var key := [file, _cell(pos.x, pos.z)]
		if not groups.has(key):
			groups[key] = []
		groups[key].append([xf, color])
	var bodies := {}
	for key in groups:
		var file: String = key[0]
		var list: Array = groups[key]
		var mms: Array = []
		_group_mms[key] = mms
		for part in _model_parts(file):
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			mm.use_colors = true
			mm.mesh = part["mesh"]
			var px: Array = []
			var pc: Array = []
			for it in list:
				px.append(it[0])
				pc.append(it[1])
			RenderUtil.fill_multimesh(mm, px, part["xf"], pc)
			mms.append([mm, part["xf"]])
			var inst := MultiMeshInstance3D.new()
			inst.multimesh = mm
			inst.visibility_range_end = 190.0
			inst.visibility_range_end_margin = 25.0
			inst.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
			add_child(inst)
		# Kollision: eine Box je Auto
		var cell: Vector2i = key[1]
		if not bodies.has(cell):
			var body := StaticBody3D.new()
			body.collision_layer = 1
			body.set_meta("parked_owner", self)
			add_child(body)
			bodies[cell] = body
		for li in list.size():
			var e: Array = list[li]
			var cs := CollisionShape3D.new()
			cs.set_meta("pk", [key, li])
			var bs := BoxShape3D.new()
			var sz: Vector3 = SIZES[file]
			bs.size = Vector3(sz.x, sz.y - 0.35, sz.z)
			cs.shape = bs
			var xf: Transform3D = e[0]
			cs.global_transform = xf * Transform3D(Basis(), Vector3(0, 0.35 + (sz.y - 0.35) * 0.5, 0))
			bodies[cell].add_child(cs)


var _group_mms := {}     # [file, cell] -> [[MultiMesh, Teil-Transform], ...]


func _fit_ground(pos: Vector3, yaw: float, size: Vector3) -> Transform3D:
	## Auto auf das Gelände stellen: Höhe und Neigung aus den vier Radaufstandspunkten (halb auf dem Bordstein!)
	var b := Basis(Vector3.UP, yaw)
	var hx := size.x * 0.42
	var hz := size.z * 0.32
	var pts := [Vector3(-hx, 0, -hz), Vector3(hx, 0, -hz), Vector3(-hx, 0, hz), Vector3(hx, 0, hz)]
	var ys: Array = []
	for q in pts:
		var w: Vector3 = pos + b * q
		ys.append(terrain.height_at(w.x, w.z))
	var front := (float(ys[0]) + float(ys[1])) * 0.5
	var back := (float(ys[2]) + float(ys[3])) * 0.5
	var left := (float(ys[0]) + float(ys[2])) * 0.5
	var right := (float(ys[1]) + float(ys[3])) * 0.5
	var pitch := atan2(front - back, hz * 2.0)
	var roll := atan2(left - right, hx * 2.0)
	var y := (float(ys[0]) + float(ys[1]) + float(ys[2]) + float(ys[3])) * 0.25
	return Transform3D(b * Basis(Vector3.RIGHT, pitch) * Basis(Vector3.BACK, roll), Vector3(pos.x, y, pos.z))


## Vom Spieler angestoßen: Auto aus dem MultiMesh nehmen und als Physikkörper weiterführen.
func knock(shape_node: Node, dv: Vector3, w_y: float) -> void:
	if not is_instance_valid(shape_node) or not shape_node.has_meta("pk"):
		return
	var cs := shape_node as CollisionShape3D
	if cs.disabled:
		return
	var meta: Array = shape_node.get_meta("pk")
	var key: Array = meta[0]
	var li: int = meta[1]
	var file: String = key[0]
	var xf := cs.global_transform * Transform3D(Basis(), -cs.position)
	# Transform der Autoinstanz aus dem ersten Teil-MultiMesh rekonstruieren
	var mms: Array = _group_mms.get(key, [])
	var color := Color.WHITE
	if not mms.is_empty():
		var mm0: MultiMesh = mms[0][0]
		var part_xf: Transform3D = mms[0][1]
		xf = mm0.get_instance_transform(li) * part_xf.affine_inverse()
		color = mm0.get_instance_color(li)
		for it in mms:
			(it[0] as MultiMesh).set_instance_transform(li, Transform3D(Basis().scaled(Vector3.ZERO), xf.origin))
	cs.set_deferred("disabled", true)
	var body := RigidBody3D.new()
	body.name = "ParkedWreck"
	body.physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_ON     # Kachel selbst ist OFF
	body.mass = 1250.0
	body.collision_layer = 4
	body.collision_mask = 1 | 2 | 4
	body.linear_damp = 0.12
	body.angular_damp = 1.6
	body.center_of_mass_mode = RigidBody3D.CENTER_OF_MASS_MODE_CUSTOM
	body.center_of_mass = Vector3(0, 0.55, 0)
	var pm := PhysicsMaterial.new()
	pm.friction = 0.8
	pm.bounce = 0.05
	body.physics_material_override = pm
	var sz: Vector3 = SIZES.get(file, Vector3(1.8, 1.4, 4.4))
	var shape := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = Vector3(sz.x, sz.y - 0.35, sz.z)
	shape.shape = bs
	shape.position = Vector3(0, 0.35 + (sz.y - 0.35) * 0.5, 0)
	body.add_child(shape)
	var made := CarModel.make_ai(file, Color(color.r, color.g, color.b))
	body.add_child(made["root"])
	add_child(body)
	body.global_transform = xf.translated(Vector3(0, 0.02, 0))
	body.linear_velocity = dv
	body.angular_velocity = Vector3(0, w_y, 0)


func _details(manholes: Array, grates: Array) -> void:
	## Gullydeckel und Entwässerungsgitter, je 125-m-Zelle ein MultiMesh (die Sichtweite misst Godot zur
	## Zellmitte – ein MultiMesh je Kachel war nur nahe der Kachelmitte sichtbar).
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.09, 0.09, 0.1)
	mat.metallic = 0.7
	mat.roughness = 0.5
	var disc := CylinderMesh.new()
	disc.top_radius = 0.36
	disc.bottom_radius = 0.36
	disc.height = 0.03
	disc.radial_segments = 14
	disc.rings = 1
	var box := BoxMesh.new()
	box.size = Vector3(0.55, 0.03, 0.34)
	var cells := {}
	for m in manholes:
		var key := [0, _cell(m[0], m[1])]
		if not cells.has(key):
			cells[key] = []
		cells[key].append(Transform3D(Basis(), Vector3(m[0], terrain.height_at(m[0], m[1]) + 0.012, m[1])))
	for g in grates:
		var key := [1, _cell(g[0], g[1])]
		if not cells.has(key):
			cells[key] = []
		cells[key].append(Transform3D(Basis(Vector3.UP, g[2]), Vector3(g[0], terrain.height_at(g[0], g[1]) + 0.012, g[1])))
	for key in cells:
		var xfs: Array = cells[key]
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = disc if key[0] == 0 else box
		RenderUtil.fill_multimesh(mm, xfs)
		var inst := MultiMeshInstance3D.new()
		inst.multimesh = mm
		inst.material_override = mat
		inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		inst.visibility_range_end = 180.0
		inst.visibility_range_end_margin = 20.0
		inst.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
		add_child(inst)
