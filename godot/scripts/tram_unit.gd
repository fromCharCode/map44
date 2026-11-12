class_name TramUnit
extends Node3D
## Eine Straßenbahn: Kopfposition auf dem Gleisgraph, Wagenabschnitte folgen der gefahrenen Spur.

var system: Trams
var way := 0
var dir := 1                   # +1: Richtung Gleisende, -1: Richtung Gleisanfang
var s := 0.0                   # Position des Kopfes entlang des Gleises
var speed := 0.0
var v_cruise := 11.0
var dist := 0.0                # gesamte zurückgelegte Strecke
var trail: Array = []          # [dist, Vector3]
var offsets: Array[float] = []
var bodies: Array = []         # AnimatableBody3D je Abschnitt
var dead := false
var dwell := 0.0
var next_dwell_at := 0.0
var _last_dir := Vector2(0, -1)
var sec_half: Array[float] = []   # halbe Wagenkastenlänge je Abschnitt
var sec_bogies: Array = []        # je Abschnitt: lokale z der Drehgestellmitten (vorn = kleineres z)
var labels: Array = []
var route := -1                # Index in system.routes (echte Linie) oder -1
var route_s := 0.0             # Bogenlänge des Kopfes auf der Linie
var _route_t := 0.0


func setup(sys: Trams, scene: String, multi: bool, offs: Array[float], wi: int, d: int, start_s: float) -> void:
	system = sys
	way = wi
	dir = d
	s = start_s
	offsets = offs
	next_dwell_at = dist + system.rng.randf_range(120.0, 320.0)
	var ps := load(scene) as PackedScene
	var root := ps.instantiate() as Node3D
	var secs: Array[Node3D] = []
	if multi:
		for i in offs.size():
			var n := root.find_child("Section_%d" % i, true, false) as Node3D
			if n:
				secs.append(n)
	else:
		secs.append(root)
	for i in secs.size():
		var sec := secs[i]
		var body := AnimatableBody3D.new()
		body.sync_to_physics = true
		body.collision_layer = 4
		body.collision_mask = 0
		if sec.get_parent():
			sec.get_parent().remove_child(sec)
		sec.owner = null
		body.add_child(sec)
		sec.position = Vector3.ZERO if multi else sec.position
		# Abschnittsdaten aus dem Modell: Länge (Wagenkasten-Mesh "Body_*"), Drehgestelle (Leerknoten "Bogie_*")
		var half := 44.5 / secs.size() * 0.5
		var bz: Array = []
		for ch in sec.get_children():
			var nm := String(ch.name)
			if nm.begins_with("Body") and ch is MeshInstance3D:
				var bb: AABB = (ch as MeshInstance3D).get_aabb()
				half = bb.size.z * 0.5
			elif nm.begins_with("Bogie") and ch is Node3D:
				bz.append((ch as Node3D).position.z)
		bz.sort()
		sec_half.append(half)
		sec_bogies.append(bz)
		var cs := CollisionShape3D.new()
		var bs := BoxShape3D.new()
		bs.size = Vector3(2.5, 3.2, half * 2.0 - 0.15)
		cs.shape = bs
		cs.position = Vector3(0, 1.9, 0)
		body.add_child(cs)
		add_child(body)
		bodies.append(body)
		_fix_materials(sec)
		RenderUtil.gi_off(sec)
	if multi:
		root.queue_free()
	_make_displays()
	# Anfangsspur: rückwärts entlang des Gleises auffüllen
	var d0 := system.way_dir(way, s, dir)
	_last_dir = d0
	var p0 := system.way_point(way, s)
	var back := 0.0
	trail.clear()
	while back <= 60.0:
		var q := Vector3(p0.x - d0.x * back, p0.y, p0.z - d0.y * back)
		trail.push_front([-back, q])
		back += 1.0
	dist = 0.0
	_update_bodies()


static var _glass: StandardMaterial3D


static func _tram_glass() -> StandardMaterial3D:
	## Bahnscheiben dunkler getönt als Autoglas: die großen Front-/Heckscheiben wirkten sonst wie offene Enden
	if _glass == null:
		_glass = StandardMaterial3D.new()
		_glass.albedo_color = Color(0.03, 0.04, 0.05, 0.7)
		_glass.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		_glass.roughness = 0.04
		_glass.metallic = 0.2
		_glass.metallic_specular = 1.0
		_glass.cull_mode = BaseMaterial3D.CULL_BACK
	return _glass


func _fix_materials(n: Node) -> void:
	var stack: Array = [n]
	while not stack.is_empty():
		var x: Node = stack.pop_back()
		for c in x.get_children():
			stack.append(c)
		if x is MeshInstance3D:
			var mi := x as MeshInstance3D
			for i in mi.mesh.get_surface_count():
				var m := mi.mesh.surface_get_material(i)
				if m == null:
					continue
				var nm := String(m.resource_name)
				if nm == "Glass":
					mi.set_surface_override_material(i, _tram_glass())
				elif nm == "LcdEmit":
					var lm := m as StandardMaterial3D
					lm.emission_enabled = true
					lm.emission = Color(0.55, 0.8, 0.42)
					lm.emission_energy_multiplier = 0.5
				elif nm == "TramWindow":
					# getönte Scheiben; nachts schimmert die Innenbeleuchtung durch (Trams.set_night)
					var wm := m as StandardMaterial3D
					wm.emission_enabled = true
					wm.emission = Color(1.0, 0.9, 0.72)
					wm.emission_energy_multiplier = 0.0
					if not Trams.emit_mats.has(wm):
						Trams.emit_mats.append(wm)
				elif nm == "HeadlightEmit" or nm == "TaillightEmit":
					var sm := m as StandardMaterial3D
					sm.emission_enabled = true
					sm.emission = Color(1.0, 0.95, 0.85) if nm == "HeadlightEmit" else Color(1.0, 0.1, 0.05)
					sm.emission_energy_multiplier = 0.4
					if not Trams.emit_mats.has(sm):
						Trams.emit_mats.append(sm)


func _physics_process(delta: float) -> void:
	if dead:
		return
	var w: Dictionary = system.ways[way]
	var L: float = w["len"]
	# Geschwindigkeit: Kurven abbremsen, gelegentlich halten
	var ahead := system.way_dir(way, clampf(s + 18.0 * dir, 0.0, L), dir)
	var here := system.way_dir(way, s, dir)
	var turn := absf(here.angle_to(ahead))
	var vt := lerpf(v_cruise, 4.0, clampf(turn / 0.5, 0.0, 1.0))
	var stops: Array = w.get("stops", [])
	if dwell > 0.0:
		dwell -= delta
		vt = 0.0
	elif not stops.is_empty():
		# echte Haltestelle voraus: Front hält ~3 m hinter dem Mast (vordere Tür am Mast)
		var ds := _stop_ahead(stops, L)
		if ds < 200.0:
			vt = minf(vt, sqrt(2.0 * 1.0 * maxf(ds - 0.3, 0.0)))
			if ds < 0.8 and speed < 0.4:
				dwell = system.rng.randf_range(12.0, 22.0)
				_served = "%d:%d" % [way, int(_stop_s)]
	elif dist > next_dwell_at:
		# keine Haltestellendaten: gelegentlich halten
		dwell = system.rng.randf_range(6.0, 12.0)
		next_dwell_at = dist + system.rng.randf_range(300.0, 600.0)
	# Hindernis voraus (z.B. Auto/Spieler auf den Gleisen)
	var head: Vector3 = system.way_point(way, s)
	var fwd3 := Vector3(here.x, 0, here.y)
	for o in _obstacles():
		var rel: Vector3 = o.global_position - head
		var f := rel.dot(fwd3)
		var lat := absf(rel.dot(Vector3(-fwd3.z, 0, fwd3.x)))
		if f > 1.0 and f < 28.0 and lat < 2.0:
			vt = minf(vt, maxf(0.0, (f - 6.0) * 0.7))
	if vt > speed:
		speed = minf(speed + 1.1 * delta, vt)
	else:
		speed = maxf(speed - 2.2 * delta, vt)
	var step := speed * delta
	s += dir * step
	dist += step
	# Gleisende erreicht -> Folgegleis suchen
	if s >= L or s <= 0.0:
		var end := 1 if s >= L else 0
		var nxt := system.next_way(way, end, here, route, route_s)
		if nxt.is_empty():
			dead = true
			return
		way = nxt[0]
		var start_end: int = nxt[1]
		if start_end == 0:
			s = 0.3
			dir = 1
		else:
			s = system.ways[way]["len"] - 0.3
			dir = -1
	var p := system.way_point(way, s)
	if route >= 0:
		_route_t -= delta
		if _route_t <= 0.0:
			_route_t = 0.3
			var pr := system.route_project(route, Vector2(p.x, p.z), route_s - 10.0, route_s + 40.0)
			if float(pr[1]) < 8.0:
				route_s = float(pr[0])
			var rl: PackedFloat32Array = system.routes[route]["cum"]
			if route_s > rl[rl.size() - 1] - 30.0:
				_turn_route(Vector2(p.x, p.z), here)
	var last: Array = trail[trail.size() - 1]
	if Vector2(p.x - last[1].x, p.z - last[1].z).length() >= 0.8:
		trail.append([dist, p])
		while trail.size() > 140:
			trail.pop_front()
	_update_bodies()


var _served := ""
var _stop_s := 0.0


func _stop_ahead(stops: Array, L: float) -> float:
	## Abstand der Front zum Haltepunkt (Mast + 3 m in Fahrtrichtung) der nächsten Haltestelle voraus
	var best := INF
	for st in stops:
		var target := float(st) + 3.0 * dir
		var d := (target - s) * dir
		if d < -0.5 or target < 0.0 or target > L:
			continue
		if _served == "%d:%d" % [way, int(float(st))]:
			continue
		if d < best:
			best = d
			_stop_s = float(st)
	return best


func _obstacles() -> Array:
	var res: Array = []
	var tr := system.get_parent().find_child("Taxi", false, false)
	if tr:
		res.append(tr)
	var traffic := system.get_parent().find_child("Traffic", false, false)
	if traffic:
		for c in (traffic as Traffic).cars:
			if (c as Node3D).global_position.distance_squared_to(global_position) < 3600.0:
				res.append(c)
	return res


func _sample(d_at: float) -> Vector3:
	## Position auf der Spur bei zurückgelegter Strecke d_at.
	for i in range(trail.size() - 1, 0, -1):
		if trail[i - 1][0] <= d_at:
			var a: Array = trail[i - 1]
			var b: Array = trail[i]
			var t := clampf((d_at - a[0]) / maxf(b[0] - a[0], 0.001), 0.0, 1.0)
			return (a[1] as Vector3).lerp(b[1], t)
	return trail[0][1]


func _turn_route(p2: Vector2, d2: Vector2) -> void:
	## Linienende (Endstelle): Gegenrichtung derselben Linie übernehmen, die hier beginnt; Anzeige umstellen
	var ref := String(system.routes[route]["ref"])
	for it in system.route_for(p2, d2):
		var ri: int = it[0]
		if ri != route and String(system.routes[ri]["ref"]) == ref and float(it[1]) < 400.0:
			route = ri
			route_s = float(it[1])
			for lb in labels:
				if is_instance_valid(lb):
					(lb as Node).queue_free()
			labels.clear()
			_make_displays()
			return


func _make_displays() -> void:
	## Zielanzeigen: Leerknoten "Display_<art>_<breite cm>_<höhe cm>" im Modell (+Z = Anzeigenormale)
	var ref := ""
	var dest := "Betriebsfahrt"
	if route >= 0:
		var r: Dictionary = system.routes[route]
		ref = String(r["ref"])
		dest = LedSign.clean_dest(String(r["to"]))
	for b in bodies:
		var stack: Array = [b]
		while not stack.is_empty():
			var n: Node = stack.pop_back()
			for c in n.get_children():
				stack.append(c)
			if not String(n.name).begins_with("Display_"):
				continue
			var parts := String(n.name).split("_")
			if parts.size() < 4:
				continue
			var w := float(parts[2]) / 100.0
			var h := float(parts[3]) / 100.0
			var col := LedSign.COLOR
			if parts[1] == "lcd":
				col = Color(0.08, 0.12, 0.06)          # D12DD-Seitenanzeige: grün hinterleuchtetes LCD, dunkle Schrift
			labels.append_array(LedSign.make(n as Node3D, ref, dest, Basis.IDENTITY, Vector3(0, 0, 0.004), w, h,
				parts[1] == "rear", 140.0, col))


func _track_point(d_at: float) -> Vector3:
	## Gleispunkt bei zurückgelegter Strecke d_at; vor dem Kopf linear verlängert
	if d_at <= dist:
		return _sample(d_at)
	var head := system.way_point(way, s)
	var hd := system.way_dir(way, s, dir)
	return head + Vector3(hd.x, 0, hd.y) * (d_at - dist)


func _update_bodies() -> void:
	if not sec_bogies.is_empty() and sec_bogies.size() == bodies.size():
		_update_bodies_bogies()
		return
	var head := system.way_point(way, s)
	for i in bodies.size():
		var off := offsets[i] if i < offsets.size() else 0.0
		var center_d := dist - off
		var c := _sample(center_d)
		var f := _sample(center_d + 2.2)
		var b := _sample(center_d - 2.2)
		if center_d + 2.2 > dist:
			f = head
		var fwd := f - b
		if fwd.length() < 0.01:
			fwd = Vector3(0, 0, -1)
		var basis := Basis.looking_at(fwd.normalized(), Vector3.UP)
		(bodies[i] as AnimatableBody3D).global_transform = Transform3D(basis, c)


func _update_bodies_bogies() -> void:
	## Wie beim echten Multigelenkwagen: Abschnitte mit zwei Drehgestellen folgen deren Gleispunkten (Überhang
	## in Kurven), Sänften ohne Drehgestell hängen zwischen den Gelenken ihrer Nachbarn.
	var n := bodies.size()
	var xfs: Array = []
	xfs.resize(n)
	for i in n:
		var bz: Array = sec_bogies[i]
		var off := offsets[i] if i < offsets.size() else 0.0
		if bz.size() >= 2:
			var zf: float = bz[0]
			var zr: float = bz[bz.size() - 1]
			var pf := _track_point(dist - off - zf)
			var pr := _track_point(dist - off - zr)
			var fwd := pf - pr
			if fwd.length() < 0.01:
				fwd = Vector3(0, 0, -1)
			fwd = fwd.normalized()
			xfs[i] = Transform3D(Basis.looking_at(fwd, Vector3.UP), pr + fwd * zr)
		elif bz.size() == 1:
			# kurzer Mittelwagen mit einem Laufwerk (NGT DX DD): Tangente am Drehgestell
			var zb: float = bz[0]
			var db := dist - off - zb
			var pb := _track_point(db)
			var fwd := _track_point(db + 1.5) - _track_point(db - 1.5)
			if fwd.length() < 0.01:
				fwd = Vector3(0, 0, -1)
			fwd = fwd.normalized()
			xfs[i] = Transform3D(Basis.looking_at(fwd, Vector3.UP), pb + fwd * zb)
	for i in n:
		if xfs[i] != null:
			continue
		var off := offsets[i] if i < offsets.size() else 0.0
		if i > 0 and i < n - 1 and xfs[i - 1] != null and xfs[i + 1] != null:
			var gap_f := (offsets[i] - offsets[i - 1]) - sec_half[i] - sec_half[i - 1]
			var gap_r := (offsets[i + 1] - offsets[i]) - sec_half[i] - sec_half[i + 1]
			var j1: Vector3 = (xfs[i - 1] as Transform3D) * Vector3(0, 0, sec_half[i - 1] + gap_f * 0.5)
			var j2: Vector3 = (xfs[i + 1] as Transform3D) * Vector3(0, 0, -(sec_half[i + 1] + gap_r * 0.5))
			var fwd := (j1 - j2)
			if fwd.length() < 0.01:
				fwd = Vector3(0, 0, -1)
			fwd = fwd.normalized()
			# Mitte so, dass die Gelenkabstände vorn/hinten gleich bleiben
			var c := (j1 + j2) * 0.5 + fwd * ((gap_r - gap_f) * 0.25)
			xfs[i] = Transform3D(Basis.looking_at(fwd, Vector3.UP), c)
		else:
			# Ersatz: Sehne ±2,2 m um die Mitte
			var center_d := dist - off
			var f := _track_point(center_d + 2.2)
			var b := _track_point(center_d - 2.2)
			var fwd := f - b
			if fwd.length() < 0.01:
				fwd = Vector3(0, 0, -1)
			xfs[i] = Transform3D(Basis.looking_at(fwd.normalized(), Vector3.UP), _track_point(center_d))
	for i in n:
		(bodies[i] as AnimatableBody3D).global_transform = xfs[i]
