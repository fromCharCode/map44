class_name AICar
extends AnimatableBody3D
## Verkehrsteilnehmer: folgt einer Route entlang des Straßengraphen (kinematisch), hält Abstand, beachtet
## Ampeln, Vorfahrt/rechts vor links und Stoppschilder (Kreuzungsdaten aus tools/junctions.py), blinkt,
## bremst sichtbar. Bei einem Zusammenstoß mit dem Spieler wird das Auto zu einem echten Physikkörper
## (Wrack-Modus) und fährt danach – wenn es wieder ordentlich steht – weiter.

enum Move { STRAIGHT, LEFT, RIGHT, UTURN }
const MASS := 1300.0

var traffic: Traffic
var uid := 0
var model_file := "hatchback.glb"
var length := 4.3
var width := 1.8
var is_bus := false
var front_ext := 2.2          # Ursprung -> Frontstoßfänger (m)
var rear_ext := 2.2           # Ursprung -> Heckstoßfänger (m)
var axle_f := 1.4             # Ursprung -> Vorderachse (Neigungsabtastung)
var axle_r := 1.4
var route: Array = []         # Vector3
var route_i := 0              # aktuelles Segment
var markers: Array = []       # Kreuzungsmarken (Dictionary)
var cur_edge := 0
var cur_dir := 1
var cur_node := -1            # Zielknoten der zuletzt angehängten Kante
var last_tangent := Vector2(0, -1)
var heading := 0.0            # Gier: Vorwärtsvektor = (-sin, 0, -cos)
var speed := 0.0
var v_cruise := 11.0
var route_v: Array = []       # Tempolimit (m/s) je Routenpunkt (gilt ab diesem Punkt)
var drive_fac := 1.0          # persönlicher Fahrstil (0,88 .. 1,05 des Limits)
var accel := 2.4
var wheels := {}
var wheel_roll := 0.0
var wheel_r := 0.32
var lights: Array = []        # MeshInstance3D mit Instanz-Uniforms (car_lights.gdshader)
var model_root: Node3D
var dead := false
var death := ""               # Grund fürs Entfernen (Statistik)
var pos := Vector3.ZERO
var on_bridge := false
var ghost_t := 0.0
var blocked_t := 0.0
var _chk_t := 0.0
var _chk_pos := Vector3.ZERO
var _limit := ""              # was die Geschwindigkeit zuletzt begrenzt hat ("", "junction", "obstacle")
var _brake := false
var _ind := 0                 # -1 links, 1 rechts, 2 Warnblinker
var _light_t := 0.0
const THINK := 0.1
var _think_t := -1.0
var _since_think := 0.0
var _vt_c := INF
var _limit_c := ""
# Wrack-Modus
var wreck: RigidBody3D
var wreck_t := 0.0
var wrecked := false
var _box_size := Vector3(1.8, 1.3, 4.3)


func setup(t: Traffic, model: String, color: Color, edge: int, dir: int, s: float) -> void:
	traffic = t
	uid = t.next_id()
	model_file = model
	length = Traffic.LENGTHS.get(model, 4.4)
	collision_layer = 4
	collision_mask = 0
	sync_to_physics = sync_phys
	var made := CarModel.make_ai(model, color)
	model_root = made["root"]
	add_child(model_root)
	wheels = made["wheels"]
	lights = made["lights"]
	if made.has("size"):
		_box_size = made["size"]
	else:
		_box_size = Vector3(1.8, 1.3 if model != "van.glb" else 2.2, length)
	width = _box_size.x
	front_ext = length * 0.5
	rear_ext = length * 0.5
	axle_f = length * 0.32
	axle_r = length * 0.32
	_configure()
	_make_shapes()
	_think_t = float(uid % 6) * THINK / 6.0
	_start_route(edge, dir, s)


func _configure() -> void:
	pass                           # Busse: Maße aus dem Manifest


func _make_shapes() -> void:
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = _box_size
	cs.shape = bs
	cs.position = Vector3(0, 0.35 + _box_size.y * 0.5, (rear_ext - front_ext) * 0.5)
	add_child(cs)


func _start_route(edge: int, dir: int, s: float) -> void:
	cur_edge = edge
	cur_dir = dir
	var pts := traffic.edge_points(edge, dir)
	var acc := 0.0
	var start_i := 0
	for i in pts.size() - 1:
		var l := Vector2(pts[i + 1].x - pts[i].x, pts[i + 1].z - pts[i].z).length()
		if acc + l >= s:
			start_i = i
			break
		acc += l
	var seg := maxf(Vector2(pts[start_i + 1].x - pts[start_i].x, pts[start_i + 1].z - pts[start_i].z).length(), 0.001)
	var p0 := (pts[start_i] as Vector3).lerp(pts[start_i + 1], clampf((s - acc) / seg, 0.0, 1.0))
	var e: Dictionary = traffic.edges[edge]
	drive_fac = traffic.rng.randf_range(0.88, 1.05)
	var vl := _cruise_for(e)
	route = [p0]
	route_v = [vl]
	for i in range(start_i + 1, pts.size()):
		route.append(pts[i])
		route_v.append(vl)
	if route.size() < 2:
		route.append(pts[pts.size() - 1] + Vector3(0.01, 0, 0.01))
		route_v.append(vl)
	cur_node = int(e["b"]) if dir == 1 else int(e["a"])
	_add_marker(edge, dir)
	var d := Vector2(route[1].x - route[0].x, route[1].z - route[0].z)
	last_tangent = d.normalized()
	heading = atan2(-d.x, -d.y)
	pos = p0
	v_cruise = _cruise_for(e)
	speed = v_cruise * 0.7
	_apply_transform()
	_extend_route()


func _cruise_for(e: Dictionary) -> float:
	var limit := float(e["speed"]) / 3.6
	return clampf(limit * drive_fac, 3.5, 17.0)


func release() -> void:
	## Beim Entfernen: Kreuzungsanmeldungen lösen, Wrack-Körper aufräumen.
	for m in markers:
		traffic.unregister(int(m["node"]), self)
	markers.clear()
	if wreck != null and is_instance_valid(wreck):
		wreck.queue_free()
	wreck = null


# --- Route und Kreuzungsmarken ---------------------------------------------------------------------
func _add_marker(edge: int, dir: int) -> void:
	var nd: Dictionary = traffic.nodes[cur_node]
	if (nd["app"] as Array).is_empty() and traffic.degree(cur_node) < 3 and not nd.get("signal", false):
		return
	var last: Vector3 = route[route.size() - 1]
	markers.append({
		"node": cur_node, "ridx": route.size() - 1, "np": Vector2(last.x, last.z), "in_e": edge, "in_d": dir,
		"app": traffic.approach(cur_node, edge, dir), "ang_in": traffic.entry_angle(edge, dir),
		"jr": float(nd["jr"]), "exit_e": -1, "exit_d": 0, "ang_out": 0.0, "move": Move.STRAIGHT,
		"path": PackedVector2Array(), "entered": false, "passed": false, "eta": 99.0, "d_stop": 99.0,
		"waiting": false, "wait_t": 0.0, "stop_t": 0.0, "stop_done": false, "sig": -1, "uid": uid,
	})


func marker_for(node_id: int) -> Dictionary:
	for m in markers:
		if int(m["node"]) == node_id:
			return m
	return {}


func _set_exit(m: Dictionary, ei: int, dir: int) -> void:
	m["exit_e"] = ei
	m["exit_d"] = dir
	var ang_out := traffic.exit_angle(ei, dir)
	m["ang_out"] = ang_out
	var dlt := wrapf(ang_out - float(m["ang_in"]), -PI, PI)
	if absf(dlt) < 0.55:
		m["move"] = Move.STRAIGHT
	elif absf(dlt) > 2.6:
		m["move"] = Move.UTURN
	elif dlt > 0.0:
		m["move"] = Move.RIGHT      # (x Ost, z Süd: positiver Winkel = im Uhrzeigersinn = rechts)
	else:
		m["move"] = Move.LEFT
	m["path"] = _conflict_path(m, ei, dir)


func _conflict_path(m: Dictionary, ei: int, dir: int) -> PackedVector2Array:
	## Fahrlinie durch die Kreuzung: Haltelinie -> Ausfahrt (quadratische Bézier über den Schnittpunkt der Spuren)
	var app: Array = m["app"]
	var stop_d: float = float(app[6]) if not app.is_empty() else minf(float(m["jr"]) * 0.8, 6.0)
	var pin := traffic.edge_points(int(m["in_e"]), int(m["in_d"]))
	var pout := traffic.edge_points(ei, dir)
	var a := _along_back(pin, stop_d)
	var b := _along(pout, float(m["jr"]) + 1.5)
	var da := Vector2(cos(float(m["ang_in"])), sin(float(m["ang_in"])))
	var db := Vector2(cos(float(m["ang_out"])), sin(float(m["ang_out"])))
	var c := (a + b) * 0.5
	var den := da.cross(db)
	if absf(den) > 0.15:
		var t := (b - a).cross(db) / den
		if t > 0.0 and t < 40.0:
			c = a + da * t
	var path := PackedVector2Array()
	for k in 7:
		var u := float(k) / 6.0
		path.append(a * (1.0 - u) * (1.0 - u) + c * 2.0 * u * (1.0 - u) + b * u * u)
	return path


func _along(pts: Array, s: float) -> Vector2:
	var acc := 0.0
	for i in pts.size() - 1:
		var p: Vector3 = pts[i]
		var q: Vector3 = pts[i + 1]
		var l := Vector2(q.x - p.x, q.z - p.z).length()
		if acc + l >= s and l > 0.001:
			var t := (s - acc) / l
			return Vector2(lerpf(p.x, q.x, t), lerpf(p.z, q.z, t))
		acc += l
	var e: Vector3 = pts[pts.size() - 1]
	return Vector2(e.x, e.z)


func _along_back(pts: Array, s: float) -> Vector2:
	var rev: Array = pts.duplicate()
	rev.reverse()
	return _along(rev, s)


func _choose_next() -> Array:
	return traffic.pick_next(cur_node, cur_edge, last_tangent)


func _extend_route() -> void:
	# Hängt Kanten an, bis die Route ca. 100 m voraus reicht
	var guard := 0
	while _route_remaining() < 100.0 and guard < 5:
		guard += 1
		var nxt := _choose_next()
		if nxt.is_empty():
			break
		var ei: int = nxt[0]
		var dir: int = nxt[1]
		var pts := traffic.edge_points(ei, dir)
		var last: Vector3 = route[route.size() - 1]
		var uturn := ei == cur_edge          # Wende (Sackgasse): Rückwärtspunkte zulassen
		var added := 0
		var vl := _cruise_for(traffic.edges[ei])
		var tan := last_tangent
		for i in pts.size():
			var p: Vector3 = pts[i]
			var dd := Vector2(p.x - last.x, p.z - last.z)
			if dd.length() < 1.5 or (not uturn and dd.dot(tan) < 0.3):
				continue
			route.append(p)
			route_v.append(vl)
			tan = dd.normalized()
			last = p
			added += 1
		if added == 0:
			break                             # Kante bringt keinen Fortschritt: nicht als befahren werten
		var m := marker_for(cur_node)
		if not m.is_empty() and int(m["exit_e"]) < 0:
			_set_exit(m, ei, dir)
		cur_edge = ei
		cur_dir = dir
		var e: Dictionary = traffic.edges[ei]
		cur_node = int(e["b"]) if dir == 1 else int(e["a"])
		var n := route.size()
		if n >= 2:
			last_tangent = Vector2(route[n - 1].x - route[n - 2].x, route[n - 1].z - route[n - 2].z).normalized()
		_add_marker(ei, dir)
		_on_edge_added(e)


func _on_edge_added(_e: Dictionary) -> void:
	pass


func _route_remaining() -> float:
	var tot := 0.0
	for i in range(route_i, route.size() - 1):
		tot += Vector2(route[i + 1].x - route[i].x, route[i + 1].z - route[i].z).length()
	return tot


func _lookahead_point(dist: float) -> Vector3:
	var acc := 0.0
	var i := route_i
	var prev := Vector3(pos.x, 0, pos.z)
	while i < route.size() - 1:
		var b: Vector3 = route[i + 1]
		var l := Vector2(b.x - prev.x, b.z - prev.z).length()
		if acc + l >= dist:
			return prev.lerp(Vector3(b.x, b.y, b.z), (dist - acc) / maxf(l, 0.001))
		acc += l
		prev = Vector3(b.x, b.y, b.z)
		i += 1
	return route[route.size() - 1]


func _marker_dist(m: Dictionary) -> float:
	## Routenentfernung bis zum Knotenpunkt der Marke (negativ = schon vorbei)
	var idx := int(m["ridx"])
	if idx > route_i:
		return _dist_to_index(idx)
	var np: Vector2 = m["np"]
	var fwd := Vector2(-sin(heading), -cos(heading))
	return -(Vector2(pos.x, pos.z) - np).dot(fwd)


## Logische Position (die Knotenposition hinkt bei sync_to_physics einen Physikschritt nach)
func world_pos() -> Vector3:
	if wrecked and wreck != null and is_instance_valid(wreck):
		return wreck.global_position
	return pos


func mass_kg() -> float:
	return 11000.0 if is_bus else MASS


func _dist_to_index(idx: int) -> float:
	## Routenentfernung bis Routenpunkt idx (negativ, wenn schon vorbei)
	if idx <= route_i:
		var p := Vector2(route[maxi(idx, 0)].x, route[maxi(idx, 0)].z)
		var seg := Vector2(route[mini(idx + 1, route.size() - 1)].x, route[mini(idx + 1, route.size() - 1)].z) - p
		var me := Vector2(pos.x, pos.z) - p
		return -me.dot(seg.normalized()) if seg.length() > 0.01 else -me.length()
	var tot := 0.0
	var prev := Vector2(pos.x, pos.z)
	for i in range(route_i + 1, mini(idx + 1, route.size())):
		var p := Vector2(route[i].x, route[i].z)
		tot += prev.distance_to(p)
		prev = p
	return tot


# --- Fahren ----------------------------------------------------------------------------------------
static var prof_us := 0
static var sync_phys := true
static var prof_parts := {}


static func _pp(k: String, us: int) -> void:
	prof_parts[k] = int(prof_parts.get(k, 0)) + us
static var prof_think_us := 0


var _lod_acc := 0.0
var _lod_phase := false


func _physics_process(delta: float) -> void:
	var _t0 := Time.get_ticks_usec()
	# Detailstufe: fern der Kamera (> 120 m) nur jeden zweiten Schritt rechnen (mit doppeltem Zeitschritt)
	var far := false
	var cam := traffic.cam if traffic else null
	if cam != null and not wrecked:
		far = pos.distance_squared_to(cam.global_position) > 120.0 * 120.0
	if far:
		_lod_acc += delta
		_lod_phase = not _lod_phase
		if _lod_phase:
			prof_us += Time.get_ticks_usec() - _t0
			return
		_drive(_lod_acc)
		_lod_acc = 0.0
	else:
		if _lod_acc > 0.0:
			delta += _lod_acc
			_lod_acc = 0.0
		_drive(delta)
	prof_us += Time.get_ticks_usec() - _t0


func _drive(delta: float) -> void:
	if traffic == null or dead:
		return
	if wrecked:
		_wreck_process(delta)
		return
	# Segmentfortschritt
	while route_i < route.size() - 2:
		var a: Vector3 = route[route_i]
		var b: Vector3 = route[route_i + 1]
		var ab := Vector2(b.x - a.x, b.z - a.z)
		var ap := Vector2(pos.x - a.x, pos.z - a.z)
		if ap.dot(ab) / maxf(ab.length_squared(), 0.0001) >= 1.0:
			route_i += 1
		else:
			break
	if route_i > 6:
		route = route.slice(route_i)
		route_v = route_v.slice(route_i)
		for m in markers:
			m["ridx"] = int(m["ridx"]) - route_i
		route_i = 0
	var _te := Time.get_ticks_usec()
	_extend_route()
	_pp("extend", Time.get_ticks_usec() - _te)
	if route.size() - route_i < 2:
		dead = true
		death = "routenende"
		return

	# Schutz: zu weit von der Route entfernt -> entfernen
	var ra: Vector3 = route[route_i]
	var rb: Vector3 = route[route_i + 1]
	var rab := Vector2(rb.x - ra.x, rb.z - ra.z)
	var rap := Vector2(pos.x - ra.x, pos.z - ra.z)
	var rt := clampf(rap.dot(rab) / maxf(rab.length_squared(), 0.0001), 0.0, 1.0)
	var off_lim := 7.0
	if absf(wrapf(atan2(-rab.x, -rab.y) - heading, -PI, PI)) > 1.4:
		off_lim = 14.0                       # mitten im Wenden
	if (rap - rab * rt).length() > off_lim:
		dead = true
		death = "abseits"
		if traffic.ignore_player and int(traffic.stats.get("abseits", 0)) < 6:
			var want_h := atan2(-rab.x, -rab.y)
			print("DBG abseits uid %d pos %s v %.1f dh %.2f seg %.1f route_i %d/%d ghost %.1f bus %s" % [uid, str(pos), speed, wrapf(want_h - heading, -PI, PI), rab.length(), route_i, route.size(), ghost_t, str(is_bus)])
		return
	_chk_t += delta
	if _chk_t > 14.0:
		if Vector2(pos.x - _chk_pos.x, pos.z - _chk_pos.z).length() < 6.0 and _limit == "obstacle" and ghost_t <= 0.0 and not _queued() \
				and pos.distance_to(traffic.player.global_position) > 80.0:
			dead = true
			death = "festgefahren"
			return
		_chk_t = 0.0
		_chk_pos = pos

	# Zielgeschwindigkeit: Tempolimit hier und vorausschauend, Kurven aus der Routengeometrie
	v_cruise = float(route_v[mini(route_i, route_v.size() - 1)])
	var vt := v_cruise
	_limit = ""
	var acc_s := 0.0
	for i in range(route_i + 1, mini(route_i + 30, route.size() - 1)):
		acc_s += Vector2(route[i].x - route[i - 1].x, route[i].z - route[i - 1].z).length()
		if acc_s > 45.0:
			break
		var va := float(route_v[i])
		if va < vt:
			vt = minf(vt, sqrt(va * va + 2.0 * 2.2 * acc_s))
	var look := clampf(speed * 0.9, 4.5 + length * 0.15, 14.0 + length * 0.2)
	var tp := _lookahead_point(look)
	var d := Vector2(tp.x - pos.x, tp.z - pos.z)
	var fwd0 := Vector2(-sin(heading), -cos(heading))
	if d.dot(fwd0) < 0.0 and d.length() > 0.5:
		tp = _lookahead_point(look + 10.0)
		d = Vector2(tp.x - pos.x, tp.z - pos.z)
	# Kurvenradius aus drei Routenpunkten (unabhängig vom seitlichen Versatz des Fahrzeugs)
	var c0 := _lookahead_point(minf(look * 0.5, 6.0))
	var c1 := _lookahead_point(look + 6.0)
	var c2 := _lookahead_point(look + 18.0)
	var u1 := Vector2(c1.x - c0.x, c1.z - c0.z)
	var u2 := Vector2(c2.x - c1.x, c2.z - c1.z)
	if u1.length() > 1.0 and u2.length() > 1.0:
		var turn := absf(u1.angle_to(u2))
		if turn > 0.08:
			var radius := (u1.length() + u2.length()) * 0.5 / turn
			vt = minf(vt, maxf(sqrt(2.6 * radius), 3.6))     # Querbeschleunigung ~2,6 m/s²

	# Kreuzungen, Haltestellen, Hindernisse: alle THINK s neu bewerten (versetzt je Fahrzeug)
	_since_think += delta
	_think_t -= delta
	if _think_t <= 0.0:
		var _tt := Time.get_ticks_usec()
		var dt := _since_think
		_since_think = 0.0
		_think_t += THINK
		var lim := INF
		_limit_c = ""
		var jcap := _junctions(dt)
		if jcap < lim:
			lim = jcap
			_limit_c = "junction"
		lim = minf(lim, _special_limit(dt))
		if ghost_t <= 0.0:
			var ocap := _obstacle_cap()
			if ocap < lim:
				lim = ocap
				_limit_c = "obstacle"
		_vt_c = lim
		prof_think_us += Time.get_ticks_usec() - _tt
	if _vt_c < vt:
		vt = _vt_c
		_limit = _limit_c

	# Beschleunigung
	var prev_speed := speed
	if vt > speed:
		speed = minf(speed + accel * delta, vt)
	else:
		speed = maxf(speed - (7.5 if speed - vt > 4.0 else 4.5) * delta, vt)
	speed = maxf(speed, 0.0)
	_brake = speed < prev_speed - 0.02 * delta * 60.0 or (speed < 0.2 and vt < 0.5)
	# Steckenbleiben hinter Hindernissen (nicht an Ampeln/Kreuzungen) -> kurz Geistmodus
	if speed < 0.25 and _limit == "obstacle" and not _queued():
		blocked_t += delta
		if blocked_t > 25.0 and pos.distance_to(traffic.player.global_position) > 90.0 \
				and (traffic.cam == null or not _in_view()):
			dead = true
			death = "festgefahren"
	else:
		blocked_t = maxf(blocked_t - delta, 0.0)
	ghost_t = maxf(ghost_t - delta, 0.0)
	# Kreuzungs-Patt/Stau auflösen: sehr lange an einer Kreuzung wartend, Spieler sieht es nicht -> entfernen
	if speed < 0.3 and _limit == "junction":
		_jwait_t += delta
		if _jwait_t > 50.0 and pos.distance_to(traffic.player.global_position) > 40.0 and (traffic.cam == null or not _in_view()):
			dead = true
			death = "patt"
			return
	else:
		_jwait_t = 0.0

	# Lenkung (Pure Pursuit, kinematisch)
	if d.length() > 0.2:
		var want := atan2(-d.x, -d.y)
		var diff := wrapf(want - heading, -PI, PI)
		var max_rate := maxf(speed, 1.0) / (4.2 + length * 0.08)
		if absf(diff) > 2.0:
			# Wenden (Sackgasse): Schrittgeschwindigkeit, enger Bogen
			speed = minf(speed, 1.6)
			max_rate = 1.1
		heading += clampf(diff * 3.2, -max_rate, max_rate) * delta
	pos.x += -sin(heading) * speed * delta
	pos.z += -cos(heading) * speed * delta
	wheel_roll += speed / wheel_r * delta
	var _ta := Time.get_ticks_usec()
	_apply_transform()
	var _tb := Time.get_ticks_usec()
	_update_lights(delta)
	_pp("transform", _tb - _ta)
	_pp("lights", Time.get_ticks_usec() - _tb)


func _special_limit(_delta: float) -> float:
	return INF                     # Busse: Haltestellen


# --- Kreuzungslogik --------------------------------------------------------------------------------
func _junctions(delta: float) -> float:
	var cap := INF
	var drop: Array = []
	for m in markers:
		var d_node := _marker_dist(m)
		if d_node < -(float(m["jr"]) + 4.0):
			drop.append(m)
			continue
		if d_node > 95.0:
			break
		traffic.register(int(m["node"]), self)
		var c := _junction_cap(m, d_node, delta)
		cap = minf(cap, c)
		if not bool(m["entered"]):
			break
	for m in drop:
		traffic.unregister(int(m["node"]), self)
		markers.erase(m)
	return cap


func _junction_cap(m: Dictionary, d_node: float, delta: float) -> float:
	var app: Array = m["app"]
	var stop_d: float = float(app[6]) if not app.is_empty() else minf(float(m["jr"]) * 0.8, 6.0)
	var d_stop := d_node - stop_d
	m["d_stop"] = d_stop
	m["eta"] = 0.0 if (d_stop < 3.0 and speed < 0.5) else maxf(d_stop, 0.0) / maxf(speed, 1.0)
	if d_stop < -0.6 and not bool(m["entered"]):
		m["entered"] = true
		var ap0: Array = m["app"]
		m["enter_st"] = SignalCtl.state(ap0[7], int(ap0[5])) if not ap0.is_empty() and int(ap0[5]) >= 0 else -1
	if bool(m["entered"]):
		m["waiting"] = false
		return INF
	var cap := INF
	var ph: int = int(app[5]) if not app.is_empty() else -1
	var must := false
	if ph >= 0:
		var st := SignalCtl.state(app[7], ph)
		m["sig"] = st
		if st == SignalCtl.RED or st == SignalCtl.RED_YELLOW:
			must = true
		elif st == SignalCtl.YELLOW and d_stop > speed * speed / (2.0 * 3.5) + 1.5:
			must = true
	else:
		var lvl: int = Traffic.LVL[int(app[3])] if not app.is_empty() else 2
		if lvl <= 2 and ph == -1:
			# gleichrangig/wartepflichtig: langsam heranfahren und schauen
			cap = maxf(4.2, sqrt(2.0 * 1.6 * maxf(d_stop, 0.0)) + 3.6)
		if not app.is_empty() and int(app[4]) == 2 and not bool(m["stop_done"]):
			must = true                          # Stoppschild: einmal ganz anhalten
			if speed < 0.3 and d_stop < 2.5:
				m["stop_t"] = float(m["stop_t"]) + delta
				if float(m["stop_t"]) > 1.0:
					m["stop_done"] = true
					must = false
	if not must and int(m["exit_e"]) >= 0:
		must = _must_yield(m, ph >= 0 or ph == -2)
	if not must and d_stop < 30.0 and _exit_blocked(m, d_node):
		must = true                              # Kreuzung nicht blockieren
	if must:
		cap = minf(cap, _stop_speed(d_stop - (1.0 if ph < 0 else 0.0)))
		var waiting := speed < 0.5 and d_stop < 5.0
		m["waiting"] = waiting
		if waiting:
			m["wait_t"] = float(m["wait_t"]) + delta
	else:
		m["waiting"] = false
		m["wait_t"] = 0.0
	return cap


func _exit_blocked(m: Dictionary, d_node: float) -> bool:
	## Ist hinter der Kreuzung Platz für dieses Fahrzeug? (stehendes Fahrzeug auf der Ausfahrt)
	var need := float(m["jr"]) + length + 2.5
	var dn := maxf(d_node, 0.0)
	var a3 := _lookahead_point(dn)
	var m3 := _lookahead_point(dn + need * 0.5)
	var b3 := _lookahead_point(dn + need)
	var a := Vector2(a3.x, a3.z)
	var mm := Vector2(m3.x, m3.z)
	var b := Vector2(b3.x, b3.z)
	for o in traffic.nearby_obstacles(pos, dn + need + 12.0):
		if o == self or not (o is AICar):
			continue
		var oc := o as AICar
		if oc.speed > 1.5 or oc.wrecked:
			continue
		var op3 := oc.world_pos()
		var op := Vector2(op3.x, op3.z)
		var d1 := op.distance_to(Geometry2D.get_closest_point_to_segment(op, a, mm))
		var d2 := op.distance_to(Geometry2D.get_closest_point_to_segment(op, mm, b))
		if minf(d1, d2) < 1.8:
			# nur Fahrzeuge in meiner Fahrtrichtung (nicht Querverkehr, der gerade die Kreuzung räumt)
			var of := Vector2(-sin(oc.heading), -cos(oc.heading))
			var my_dir := (b - mm).normalized() if b.distance_to(mm) > 0.5 else (mm - a).normalized()
			if of.dot(my_dir) > 0.5:
				return true
	return false


func _in_view() -> bool:
	var c := traffic.cam
	var to_p := (pos - c.global_position)
	return to_p.length() < 200.0 and to_p.normalized().dot(-c.global_transform.basis.z) > 0.4


func _stop_speed(d_stop: float) -> float:
	if d_stop < 0.6:
		return 0.0
	return sqrt(2.0 * 3.2 * (d_stop - 0.6))


func _lvl(m: Dictionary) -> int:
	var app: Array = m["app"]
	return Traffic.LVL[int(app[3])] if not app.is_empty() else 2


func _must_yield(m: Dictionary, signalized: bool) -> bool:
	## Muss ich an Kreuzung m warten? Sammelt alle Fahrzeuge mit Vorrang, die vor meinem Räumen ankommen
	## (oder schon in der Kreuzung sind). Patt: stehen alle diese selbst und warte ich > 5 s, fährt die
	## kleinere Nummer.
	var node := int(m["node"])
	var blockers: Array = []
	var clear_d := maxf(float(m["d_stop"]), 0.0) + float(m["jr"]) * 2.0 + length
	var my_clear := float(m["eta"]) + sqrt(2.0 * clear_d / maxf(accel, 1.0)) + 1.0
	for o in traffic.jreg.get(node, []):
		if o == self or not is_instance_valid(o) or (o as AICar).dead or (o as AICar).wrecked:
			continue
		var oc := o as AICar
		var om := oc.marker_for(node)
		if om.is_empty() or int(om["exit_e"]) < 0:
			continue
		if int(om["in_e"]) == int(m["in_e"]) and int(om["in_d"]) == int(m["in_d"]):
			continue                              # gleiche Zufahrt: Folgefahren regelt das
		if not _paths_conflict(m, om):
			continue
		if bool(om["entered"]):
			blockers.append(oc)                   # steht/fährt schon in der Kreuzung
			continue
		var inner := not (m["app"] as Array).is_empty() and int((m["app"] as Array)[5]) == -2
		if inner:
			# innerhalb einer Ampelgruppe: wer zuerst ankommt, fährt zuerst
			if float(om["eta"]) < float(m["eta"]) or (is_equal_approx(float(om["eta"]), float(m["eta"])) and oc.uid < uid):
				blockers.append(oc)
			continue
		if not _has_priority(om, m, signalized):
			continue
		if float(om["eta"]) < my_clear and float(om["eta"]) < 10.0:
			blockers.append(oc)
	# Spieler
	var pl := traffic.player_at(node)
	if not pl.is_empty():
		var a: Vector2 = pl["a"]
		var b: Vector2 = pl["b"]
		if bool(pl["inside"]):
			if _path_near_segment(m["path"], a, b, 2.4):
				return true
		elif float(pl["eta"]) < my_clear and float(pl["eta"]) < 7.0:
			var rel := wrapf(float(pl["ang"]) - float(m["ang_in"]), -PI, PI)
			var pri := false
			if signalized:
				pri = absf(rel) > 2.4 and int(m["move"]) == Move.LEFT
			elif int(pl["lvl"]) != _lvl(m):
				pri = int(pl["lvl"]) > _lvl(m)
			else:
				pri = (rel < -0.6 and rel > -2.4) or (absf(rel) > 2.4 and int(m["move"]) == Move.LEFT)
			if pri and _path_near_segment(m["path"], a, b, 2.4):
				return true
	if blockers.is_empty():
		return false
	if float(m["wait_t"]) > 5.0:
		# Patt? Nur wenn alle Vorrang-Fahrzeuge selbst stehen; dann fährt die kleinste Nummer
		var all_stuck := true
		var smallest := true
		for oc in blockers:
			var c := oc as AICar
			if c.speed > 0.3:
				all_stuck = false
				break
			if c.uid < uid:
				smallest = false
		if all_stuck and smallest:
			return false
	return true


func _has_priority(om: Dictionary, m: Dictionary, signalized: bool) -> bool:
	## Hat das andere Fahrzeug (om) Vorrang vor mir (m)?
	var rel := wrapf(float(om["ang_in"]) - float(m["ang_in"]), -PI, PI)
	var oncoming := absf(rel) > 2.4
	var from_right := rel < -0.6 and rel > -2.4
	var same_exit := int(m["exit_e"]) == int(om["exit_e"]) and int(m["exit_d"]) == int(om["exit_d"])
	var mv := int(m["move"])
	var omv := int(om["move"])
	if same_exit:
		# Einmünden in dieselbe Fahrbahn: wer stärker abbiegt, wartet; gleich: rechts vor links
		var tm := absf(wrapf(float(m["ang_out"]) - float(m["ang_in"]), -PI, PI))
		var to := absf(wrapf(float(om["ang_out"]) - float(om["ang_in"]), -PI, PI))
		if not signalized and _lvl(om) != _lvl(m):
			return _lvl(om) > _lvl(m)
		if absf(tm - to) > 0.25:
			return tm > to
		return from_right or (not (rel > 0.6 and rel < 2.4) and om.get("uid", 0) < uid)
	if signalized:
		if oncoming and mv == Move.LEFT and omv != Move.LEFT:
			return true
		return false
	var lm := _lvl(m)
	var lo := _lvl(om)
	if lo != lm:
		return lo > lm
	if oncoming:
		return mv == Move.LEFT and omv != Move.LEFT
	if same_exit and mv != Move.STRAIGHT and omv == Move.STRAIGHT and not from_right:
		return true
	return from_right


func _paths_conflict(m: Dictionary, om: Dictionary) -> bool:
	if int(m["exit_e"]) == int(om["exit_e"]) and int(m["exit_d"]) == int(om["exit_d"]):
		return true
	var p: PackedVector2Array = m["path"]
	var q: PackedVector2Array = om["path"]
	for i in p.size() - 1:
		for j in q.size() - 1:
			if Geometry2D.segment_intersects_segment(p[i], p[i + 1], q[j], q[j + 1]) != null:
				return true
	return false


func _path_near_segment(path: PackedVector2Array, a: Vector2, b: Vector2, r: float) -> bool:
	for i in path.size() - 1:
		if Geometry2D.segment_intersects_segment(path[i], path[i + 1], a, b) != null:
			return true
		var c := Geometry2D.get_closest_points_between_segments(path[i], path[i + 1], a, b)
		if (c[0] as Vector2).distance_to(c[1]) < r:
			return true
	return false


# --- Hindernisse ------------------------------------------------------------------------------------
var blocker: Object = null     # Fahrzeug, das mich zuletzt begrenzt hat
var _jwait_t := 0.0


func _queued() -> bool:
	## Stehe ich in einem Rückstau vor einer Kreuzung/Ampel? (Kette der Vordermänner endet an einer Haltelinie)
	var b: Object = blocker
	for i in 12:
		if b == null or not is_instance_valid(b) or not (b is AICar):
			return false
		var ac := b as AICar
		if ac._limit == "junction" or (ac is BusCar and (ac as BusCar).at_stop):
			return true
		if ac.speed > 0.5:
			return true                # Vordermann rollt: zähfließend, nicht festgefahren
		b = ac.blocker
	return false


func _obstacle_cap() -> float:
	var vt := INF
	blocker = null
	var fwd := Vector3(-sin(heading), 0, -cos(heading))
	var right := Vector3(-fwd.z, 0, fwd.x)
	var obstacles: Array = traffic.nearby_obstacles(pos, 42.0)
	if not traffic.ignore_player:
		obstacles.append(traffic.player)
	for o in obstacles:
		if o == self:
			continue
		var op: Vector3 = (o as AICar).world_pos() if o is AICar else (o as Node3D).global_position
		var ovel := Vector3.ZERO
		var olen := 4.5
		var ow := 1.9
		var o_rear := 2.25
		if o is AICar:
			var oc := o as AICar
			olen = oc.length
			ow = oc.width
			o_rear = oc.rear_ext
			if oc.wrecked and oc.wreck != null:
				ovel = oc.wreck.linear_velocity
			else:
				ovel = Vector3(-sin(oc.heading), 0, -cos(oc.heading)) * oc.speed
		elif o is RigidBody3D:
			ovel = (o as RigidBody3D).linear_velocity
		var rel := op - pos
		var f := rel.dot(fwd)
		if f < -olen or f > 40.0:
			continue
		var along := ovel.dot(fwd)
		var lat_v := ovel.dot(right)
		var corridor := (width + ow) * 0.5 + 0.35 + clampf(f * 0.04, 0.0, 0.8)
		var lat := rel.dot(right)
		# Gegenverkehr auf eigener Spur ignorieren, wenn er seitlich deutlich versetzt ist
		if absf(lat) < corridor and f > 0.3:
			if along < -1.0 and absf(lat) > corridor * 0.55:
				continue
			var gap := f - (o_rear + front_ext) - 1.9
			var ov := maxf(along, 0.0)
			var allowed := ov + maxf(gap, 0.0) * 0.8
			if gap < 1.0:
				allowed = minf(allowed, ov * 0.5)
			if gap < 0.0:
				allowed = 0.0
			if allowed < vt:
				vt = allowed
				blocker = o
			continue
		# nebeneinander (zusammenlaufende Spuren): Reißverschluss – wer weiter hinten ist (bzw. größere Nummer), lässt vor
		if absf(f) < (olen + length) * 0.5 and absf(lat) < (width + ow) * 0.5 + 0.25 and along > -1.0:
			if f > 0.0 or (absf(f) < 0.5 and o is AICar and (o as AICar).uid < uid):
				vt = minf(vt, maxf(along - 1.0, 0.0))
			continue
		# Querverkehr: wo ist das Hindernis in 0,4 / 0,8 / 1,6 s?
		if absf(lat_v) > 0.5:
			for t in [0.4, 0.8, 1.6]:
				var lt: float = lat + lat_v * t
				var ft: float = f + along * t
				var mine: float = speed * t
				if absf(lt) < corridor and ft > 0.0 and ft - mine < (olen + length) * 0.5 + 2.5:
					var gap2: float = ft - (olen + length) * 0.5 - 2.0
					vt = minf(vt, sqrt(2.0 * 4.5 * maxf(gap2, 0.0)))
					break
	return vt


# --- Licht -----------------------------------------------------------------------------------------
static var no_light_params := OS.has_environment("DRESDEN_NOLIGHTPARAMS")


func _update_lights(delta: float) -> void:
	_light_t -= delta
	if _light_t > 0.0 or no_light_params:
		return
	_light_t = 0.12
	var ind := 0
	if wrecked:
		ind = 2
	else:
		for m in markers:
			if bool(m["passed"]):
				continue
			var d_node := _marker_dist(m)
			if d_node < 42.0 and d_node > -float(m["jr"]):
				var mv := int(m["move"])
				ind = -1 if mv == Move.LEFT or mv == Move.UTURN else (1 if mv == Move.RIGHT else 0)
			break
	_ind = ind
	var on := 1.0 if traffic.night > 0.3 or traffic.rain > 0.5 else 0.0
	for li in lights:
		var mi := li as MeshInstance3D
		mi.set_instance_shader_parameter("lights_on", on)
		mi.set_instance_shader_parameter("brake_on", 1.0 if _brake else 0.0)
		mi.set_instance_shader_parameter("ind_l", 1.0 if ind == -1 or ind == 2 else 0.0)
		mi.set_instance_shader_parameter("ind_r", 1.0 if ind == 1 or ind == 2 else 0.0)


func _apply_transform() -> void:
	var gy: float = traffic.terrain.height_at(pos.x, pos.z)
	# Fahrbahnprofil (Route) und Gelände stimmen abseits von Brücken überein (build_city: Längsprofil + conform).
	# Auf Brücken liegt die Route über dem Gelände -> immer die höhere Fläche nehmen.
	var ry := _route_y()
	# im Tunnel liegt die Route tief unter dem Gelände -> Routenhöhe (Vorprüfung billig, inside() nur dann)
	var in_tunnel := ry < gy - 2.0 and Tunnels.inside(Vector3(pos.x, ry, pos.z))
	var on_deck := in_tunnel or ry > gy + 0.08
	var y := ry if in_tunnel else maxf(gy, ry)
	pos.y = y
	var fwd := Vector3(-sin(heading), 0, -cos(heading))
	var front_y: float
	var rear_y: float
	if on_deck:
		front_y = _route_y_at(pos + fwd * axle_f)
		rear_y = _route_y_at(pos - fwd * axle_r)
	else:
		var fp := pos + fwd * axle_f
		var rp := pos - fwd * axle_r
		front_y = float(traffic.terrain.height_at(fp.x, fp.z))
		rear_y = float(traffic.terrain.height_at(rp.x, rp.z))
	var pitch := atan2(front_y - rear_y, axle_f + axle_r)
	var basis := Basis(Vector3.UP, heading) * Basis(Vector3.RIGHT, pitch)
	global_transform = Transform3D(basis, Vector3(pos.x, pos.y, pos.z))
	for k in wheels:
		var w: Node3D = wheels[k]
		w.transform.basis = Basis(Vector3.RIGHT, -wheel_roll)


func _route_y_at(p: Vector3) -> float:
	## Höhe der Route am Lotpunkt von p (aktuelles und nächstes Teilstück).
	if route_i + 1 >= route.size():
		return pos.y
	var best_d := INF
	var best_y := pos.y
	for i in range(maxi(route_i - 1, 0), mini(route_i + 2, route.size() - 1)):
		var a: Vector3 = route[i]
		var b: Vector3 = route[i + 1]
		var ab := Vector2(b.x - a.x, b.z - a.z)
		var t := clampf(Vector2(p.x - a.x, p.z - a.z).dot(ab) / maxf(ab.length_squared(), 0.0001), 0.0, 1.0)
		var q := Vector2(a.x, a.z) + ab * t
		var d := q.distance_squared_to(Vector2(p.x, p.z))
		if d < best_d:
			best_d = d
			best_y = lerpf(a.y, b.y, t)
	return best_y


func _route_y() -> float:
	if route_i + 1 >= route.size():
		return pos.y
	var a: Vector3 = route[route_i]
	var b: Vector3 = route[route_i + 1]
	var ab := Vector2(b.x - a.x, b.z - a.z)
	var t := clampf(Vector2(pos.x - a.x, pos.z - a.z).dot(ab) / maxf(ab.length_squared(), 0.0001), 0.0, 1.0)
	return lerpf(a.y, b.y, t)


# --- Zusammenstoß / Wrack-Modus -------------------------------------------------------------------
func velocity() -> Vector3:
	if wrecked and wreck != null:
		return wreck.linear_velocity
	return Vector3(-sin(heading), 0, -cos(heading)) * speed


## Vom Spieler gemeldeter Stoß: dv = Geschwindigkeitsänderung dieses Autos, w_y = Drehimpuls-Anteil (rad/s).
func player_impact(dv: Vector3, w_y: float) -> void:
	if wrecked:
		if wreck != null:
			wreck.apply_central_impulse(dv * MASS)
		return
	_make_wreck(velocity() + dv, w_y)


func _make_wreck(v: Vector3, w_y: float) -> void:
	for m in markers:
		traffic.unregister(int(m["node"]), self)
	wreck = RigidBody3D.new()
	wreck.name = "Wrack"
	wreck.mass = mass_kg()
	wreck.collision_layer = 4
	wreck.collision_mask = 1 | 2 | 4
	wreck.linear_damp = 0.12
	wreck.angular_damp = 1.6
	wreck.center_of_mass_mode = RigidBody3D.CENTER_OF_MASS_MODE_CUSTOM
	wreck.center_of_mass = Vector3(0, 0.55, 0)
	var pm := PhysicsMaterial.new()
	pm.friction = 0.8
	pm.bounce = 0.05
	wreck.physics_material_override = pm
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = _box_size
	cs.shape = bs
	cs.position = Vector3(0, 0.35 + _box_size.y * 0.5, (rear_ext - front_ext) * 0.5)
	wreck.add_child(cs)
	traffic.add_child(wreck)
	wreck.global_transform = global_transform.translated(Vector3(0, 0.03, 0))
	model_root.reparent(wreck, true)
	wreck.linear_velocity = v
	wreck.angular_velocity = Vector3(0, w_y, 0)
	collision_layer = 0
	wrecked = true
	wreck_t = 0.0
	speed = 0.0
	_brake = false


func _wreck_process(delta: float) -> void:
	if wreck == null or not is_instance_valid(wreck):
		dead = true
		death = "wrack"
		return
	wreck_t += delta
	global_transform = wreck.global_transform
	_update_lights(delta)
	if wreck_t < 2.5:
		return
	if wreck.linear_velocity.length() > 0.6 or wreck.angular_velocity.length() > 0.35:
		return
	var b := wreck.global_transform.basis
	var upright := b.y.y > 0.85
	var h := atan2(b.z.x, b.z.z)
	var wp := wreck.global_position
	# zurück auf die Route?
	var best := INF
	var best_t := Vector2.ZERO
	for i in range(route_i, mini(route_i + 6, route.size() - 1)):
		var a: Vector3 = route[i]
		var c: Vector3 = route[i + 1]
		var ab := Vector2(c.x - a.x, c.z - a.z)
		var t := clampf(Vector2(wp.x - a.x, wp.z - a.z).dot(ab) / maxf(ab.length_squared(), 0.0001), 0.0, 1.0)
		var dd := (Vector2(a.x, a.z) + ab * t).distance_to(Vector2(wp.x, wp.z))
		if dd < best:
			best = dd
			best_t = ab.normalized()
	var want := atan2(-best_t.x, -best_t.y)
	if upright and best < 2.6 and absf(wrapf(want - h, -PI, PI)) < 0.8 and wreck_t > 3.0:
		# weiterfahren
		model_root.reparent(self, true)
		global_transform = Transform3D(Basis(Vector3.UP, h), wp)
		model_root.transform = Transform3D.IDENTITY
		pos = Vector3(wp.x, wp.y, wp.z)
		heading = h
		speed = 0.0
		wreck.queue_free()
		wreck = null
		wrecked = false
		collision_layer = 4
		blocked_t = 0.0
		_chk_t = 0.0
		return
	# bleibt liegen (Warnblinker), verschwindet, wenn der Spieler weit weg ist
	if wreck_t > 90.0 and global_position.distance_to(traffic.player.global_position) > 140.0:
		dead = true
		death = "wrack"
