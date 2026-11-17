class_name Breakables
## Umfahrbare Objekte (Mülleimer, Poller, Schilder, Ampelmasten, Schutzgitter …).
## Die Objekte bleiben feste Hindernisse (Kollisionsebene 1) und liegen zusätzlich auf Ebene LAYER. Fährt das
## Spielerauto schneller als die Bruchgeschwindigkeit des Objekts darauf zu, wird es kurz vor dem Kontakt gelöst:
## MultiMesh-Instanz ausblenden, feste Form abschalten, dafür ein RigidBody mit denselben Meshes, das wegfliegt;
## das Auto verliert den Impuls des Objekts. Darunter wirkt das Objekt wie bisher als festes Hindernis.

const LAYER := 16
const DEBRIS_LAYER := 32
const MAX_DEBRIS := 60
const LIFE := 45.0

static var _debris: Array = []
static var _q: PhysicsShapeQueryParameters3D
static var broken := 0                 # Zähler (Taxi-Abrechnung: Sachschaden)
static var last_cost := 0.0


static func tag(cs: CollisionShape3D, mms: Array, idx: int, meshes: Array, inst_xf: Transform3D, mass: float, vmin_kmh: float, cost: float = 0.0) -> void:
	## mms: MultiMeshes, in denen das Objekt Instanz idx ist; meshes: [{mesh, xf}] der Modellteile
	cs.set_meta("brk", [mms, idx, meshes, inst_xf, mass, vmin_kmh / 3.6, cost])


static var tree_bodies := {}           # Körper-RID (kleine Bäume) -> [Dressing, PackedInt32Array Baumindex je Form]


static func check(car: RigidBody3D, delta: float) -> void:
	var v := car.linear_velocity
	var sp := v.length()
	if sp < 1.2:
		return
	if _q == null:
		_q = PhysicsShapeQueryParameters3D.new()
		var bs := BoxShape3D.new()
		bs.size = Vector3(2.0, 1.3, 4.9)
		_q.shape = bs
		_q.collision_mask = LAYER
	var xf := car.global_transform
	xf.origin += xf.basis.y * 0.25 + v * (delta * 2.5)
	_q.transform = xf
	var hits := car.get_world_3d().direct_space_state.intersect_shape(_q, 8)
	for h in hits:
		var body := h["collider"] as CollisionObject3D
		if body == null:
			# kleine Bäume: Körper direkt im PhysicsServer (Dressing._tree_bodies), ab 30 km/h umfahrbar
			var tb = tree_bodies.get(h["rid"])
			if tb != null and sp >= 30.0 / 3.6 and is_instance_valid(tb[0]):
				(tb[0] as Dressing).fell_tree(h["rid"], int(h["shape"]), car, v, sp)
			continue
		var cs := body.shape_owner_get_owner(body.shape_find_owner(int(h["shape"]))) as CollisionShape3D
		if cs == null or not cs.has_meta("brk"):
			continue
		var d: Array = cs.get_meta("brk")
		if sp < float(d[5]):
			continue
		_break(car, cs, d, v, sp)


static func _break(car: RigidBody3D, cs: CollisionShape3D, d: Array, v: Vector3, sp: float) -> void:
	var idx := int(d[1])
	for mm in d[0]:
		if mm != null and idx < (mm as MultiMesh).instance_count:
			(mm as MultiMesh).set_instance_transform(idx, Transform3D(Basis.from_scale(Vector3(0.0001, 0.0001, 0.0001)), Vector3(0, -2000, 0)))
	var shape_xf := cs.global_transform
	var shape := cs.shape
	cs.remove_meta("brk")
	cs.set_deferred("disabled", true)
	spawn(car, shape, shape_xf, d[2], d[3], float(d[4]), v, sp, float(d[6]))


static func spawn(car: RigidBody3D, shape: Shape3D, shape_xf: Transform3D, meshes: Array, inst_xf: Transform3D, mass: float, v: Vector3, sp: float, cost: float) -> void:
	## Trümmerkörper mit den Modellteilen; Auto verliert den Impuls
	var rb := RigidBody3D.new()
	rb.mass = mass
	rb.collision_layer = DEBRIS_LAYER
	rb.collision_mask = 1
	rb.physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_ON
	var rcs := CollisionShape3D.new()
	rcs.shape = shape
	rb.add_child(rcs)
	var inv := shape_xf.affine_inverse() * inst_xf
	for m in meshes:
		var mi := MeshInstance3D.new()
		mi.mesh = m["mesh"]
		mi.transform = inv * (m["xf"] as Transform3D)
		rb.add_child(mi)
	var tree := car.get_tree()
	(tree.current_scene if tree.current_scene != null else tree.root).add_child(rb)
	rb.global_transform = shape_xf
	var dir := v / sp
	# Stoß: leichte Teile fliegen voraus, schwere kippen eher um
	var k := clampf(1.15 - mass / 500.0, 0.45, 1.1)
	rb.linear_velocity = v * k + Vector3(0, minf(1.0 + sp * 0.12, 4.5), 0) + Vector3(randf_range(-1, 1), 0, randf_range(-1, 1)) * 0.6
	rb.angular_velocity = Vector3.UP.cross(dir) * minf(sp * 0.5, 9.0) + Vector3(randf_range(-1, 1), randf_range(-1, 1), randf_range(-1, 1))
	# Auto verliert den Impuls, den das Objekt bekommt (gedeckelt)
	car.apply_central_impulse(-dir * minf(mass * sp * k, car.mass * sp * 0.35))
	if "cam_kick" in car:
		car.cam_kick = maxf(car.cam_kick, clampf(mass * sp / 4000.0, 0.15, 1.0))
	broken += 1
	last_cost = cost
	_debris.append([rb, Time.get_ticks_msec()])
	var now := Time.get_ticks_msec()
	while not _debris.is_empty() and (_debris.size() > MAX_DEBRIS or now - int(_debris[0][1]) > LIFE * 1000.0):
		var old: Array = _debris.pop_front()
		if is_instance_valid(old[0]):
			(old[0] as Node).queue_free()
