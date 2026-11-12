class_name TrafficBench
extends Node
## Verkehrs-Prüfstand (ohne Fenster): godot --headless --path godot --fixed-fps 60 -- --trafficbench=300 [--drive=x,z]
## Misst Überschneidungen zwischen KI-Fahrzeugen, Rotlichtverstöße, Kreuzungs-Patts und Fahrleistung.

var main: Node
var traffic: Traffic
var duration := 300.0
var t := 0.0
var frame := 0
var pairs := {}             # "a-b" -> true (bereits gezählt)
var overlaps: Array = []    # [t, pos]
var red_runs := 0
var yellow_runs := 0
var entered_seen := {}
var wait_long := {}         # uid -> Wartezeit an Kreuzung
var deadlocks := {}
var speed_sum := 0.0
var speed_n := 0
var max_cars := 0
var stops_served := 0
var last_stop := {}
var _report_t := 0.0
var bus_halts := 0
var phys_ms := 0.0
var phys_n := 0
var bus_at := {}
var bus_lost := {}


var shot_dir := ""
var shot_every := 20.0
var _shot_t := 0.0
var _shot_n := 0
var cams: Array = []          # [[x, z, yaw, pitch, h], ...] – reihum
var bench_cam: Camera3D


func setup_cam(spec: String, dir: String) -> void:
	for part in spec.split(";"):
		var v := part.split(",")
		if v.size() >= 5:
			cams.append([float(v[0]), float(v[1]), float(v[2]), float(v[3]), float(v[4])])
	shot_dir = dir
	if not cams.is_empty():
		bench_cam = Camera3D.new()
		bench_cam.fov = 70.0
		bench_cam.far = 3000.0
		add_child(bench_cam)
		_place_cam(0)
		bench_cam.make_current()


func _place_cam(i: int) -> void:
	var c: Array = cams[i % cams.size()]
	var w := traffic.terrain as World
	var y := (w.height_at(float(c[0]), float(c[1])) if w else 0.0) + float(c[4])
	bench_cam.global_position = Vector3(float(c[0]), y, float(c[1]))
	bench_cam.rotation = Vector3(deg_to_rad(float(c[3])), deg_to_rad(float(c[2])), 0.0)
	if w:
		w.focus = bench_cam.global_position


func start(m: Node, tr: Traffic, secs: float) -> void:
	main = m
	traffic = tr
	duration = secs
	traffic.ignore_player = true
	var p := traffic.player as RigidBody3D
	p.freeze = true
	p.global_position += Vector3(0, 60.0, 0)
	print("TRAFFICBENCH Start: %.0f s, Ziel %d Autos, %d Busse" % [duration, traffic.target_count, traffic.bus_target])


var own_us := 0


func _physics_process(delta: float) -> void:
	var _t0 := Time.get_ticks_usec()
	_bench(delta)
	own_us += Time.get_ticks_usec() - _t0


var crash_at := -1.0
var crash_target: AICar
var crash_log_t := 0.0


func _crash_test(delta: float) -> void:
	## --crashai=<s>: nach s Sekunden fährt der Spieler mit 15 m/s auf ein KI-Auto (Physik-Interaktion prüfen)
	var p := traffic.player as RigidBody3D
	if crash_target == null and t >= crash_at:
		var best: AICar = null
		for c in traffic.cars:
			var ac := c as AICar
			if not ac.is_bus and ac.speed > 6.0:
				best = ac
				break
		if best == null:
			return
		crash_target = best
		# Spieler steht quer auf der Route 25 m voraus; das KI-Auto sieht ihn nicht (Seitenaufprall)
		var q := best._lookahead_point(25.0)
		var q2 := best._lookahead_point(27.0)
		var dirv := Vector2(q2.x - q.x, q2.z - q.z).normalized()
		var yaw := atan2(-dirv.x, -dirv.y) + PI * 0.5
		traffic.ignore_player = true
		p.freeze = false
		p.global_transform = Transform3D(Basis(Vector3.UP, yaw), Vector3(q.x, q.y + 0.5, q.z))
		p.linear_velocity = Vector3.ZERO
		p.angular_velocity = Vector3.ZERO
		(p as PlayerCar)._v_before = Vector3.ZERO
		print("CRASHTEST Start: Ziel #%d v=%.1f fährt auf den querstehenden Spieler" % [best.uid, best.speed])
	if crash_target != null and crash_log_t < 6.0:
		crash_log_t += delta
		if int(crash_log_t * 10.0) != int((crash_log_t - delta) * 10.0) and int(crash_log_t * 10.0) % 5 == 0:
			var tv := crash_target.velocity()
			var touching := []
			for bdy in p.get_colliding_bodies():
				touching.append("%s(%s)" % [bdy.name, bdy.get_parent().name if bdy.get_parent() else ""])
			print("   berührt: ", touching)
			print("CRASHTEST t+%.1f Spieler %s frozen=%s v=%.1f | Ziel #%d wrack=%s v=%.1f ω=%.2f Abstand %.1f" % [crash_log_t, str(p.global_position), str(p.freeze), p.linear_velocity.length(), crash_target.uid, str(crash_target.wrecked), tv.length(), crash_target.wreck.angular_velocity.y if crash_target.wreck else 0.0, p.global_position.distance_to(crash_target.world_pos())])


func _bench(delta: float) -> void:
	if traffic == null:
		return
	t += delta
	frame += 1
	if crash_at >= 0.0:
		_crash_test(delta)
	phys_ms += Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0
	phys_n += 1
	var cars: Array = traffic.cars
	max_cars = maxi(max_cars, cars.size())
	for c in cars:
		var ac := c as AICar
		speed_sum += ac.speed
		speed_n += 1
		for m in ac.markers:
			if bool(m["entered"]) and m.has("enter_st"):
				var key := "%d-%d" % [ac.uid, int(m["node"])]
				if not entered_seen.has(key):
					entered_seen[key] = true
					var st := int(m["enter_st"])
					if st == SignalCtl.RED:
						red_runs += 1
					elif st == SignalCtl.YELLOW:
						yellow_runs += 1
		if ac._limit == "junction" and ac.speed < 0.3:
			wait_long[ac.uid] = float(wait_long.get(ac.uid, 0.0)) + delta
			if float(wait_long[ac.uid]) > 40.0 and not deadlocks.has(ac.uid):
				deadlocks[ac.uid] = ac.world_pos()
		else:
			wait_long[ac.uid] = 0.0
		if ac is BusCar:
			var b := ac as BusCar
			if last_stop.get(ac.uid, b.next_stop) != b.next_stop:
				stops_served += 1
			last_stop[ac.uid] = b.next_stop
			if b.at_stop and not bus_at.get(ac.uid, false):
				bus_halts += 1
			bus_at[ac.uid] = b.at_stop
			if b.line < 0 and not bus_lost.has(ac.uid):
				bus_lost[ac.uid] = b.world_pos()
	if frame % 6 == 0:
		_check_overlaps(cars)
	_report_t += delta
	if _report_t > 30.0:
		_report_t = 0.0
		_report(false)
	if shot_dir != "" and bench_cam != null:
		_shot_t += delta
		if _shot_t >= shot_every:
			_shot_t = 0.0
			var img := main.get_viewport().get_texture().get_image()
			var fn := "%s/bench_%02d.png" % [shot_dir, _shot_n]
			img.save_png(fn)
			print("BENCHSHOT ", fn, " t=", t)
			_shot_n += 1
			if cams.size() > 1:
				_place_cam(_shot_n)
	if t >= duration:
		_report(true)
		main.get_tree().quit()


func _check_overlaps(cars: Array) -> void:
	var P: Array = []
	for c in cars:
		P.append((c as AICar).world_pos())
	for i in cars.size():
		var a := cars[i] as AICar
		if a.ghost_t > 0.0 or a.wrecked:
			continue
		var pa: Vector3 = P[i]
		for j in range(i + 1, cars.size()):
			if pa.distance_squared_to(P[j]) > 400.0:
				continue
			var b := cars[j] as AICar
			if b.ghost_t > 0.0 or b.wrecked:
				continue
			if _obb(a, b):
				var key := "%d-%d" % [mini(a.uid, b.uid), maxi(a.uid, b.uid)]
				if not pairs.has(key):
					pairs[key] = true
					overlaps.append([t, a.world_pos(), a.speed, b.speed, _desc(a), _desc(b), rad_to_deg(wrapf(b.heading - a.heading, -PI, PI))])


func _desc(c: AICar) -> String:
	var mk := ""
	if not c.markers.is_empty():
		var m: Dictionary = c.markers[0]
		var app: Array = m["app"]
		mk = "K%d %s mv%d ds%.1f pri%s ph%s" % [int(m["node"]), "drin" if bool(m["entered"]) else "vor", int(m["move"]), float(m["d_stop"]), str(app[3]) if not app.is_empty() else "-", str(app[5]) if not app.is_empty() else "-"]
	return "%s#%d e%d/%d lim=%s %s" % ["Bus" if c.is_bus else "Auto", c.uid, c.cur_edge, c.cur_dir, c._limit, mk]


func _corners(c: AICar) -> PackedVector2Array:
	var f := Vector2(-sin(c.heading), -cos(c.heading))
	var r := Vector2(-f.y, f.x)
	var wp := c.world_pos()
	var p := Vector2(wp.x, wp.z)
	var hw := c.width * 0.5 - 0.15
	var fe := c.front_ext - 0.2
	var re := c.rear_ext - 0.2
	return PackedVector2Array([p + f * fe + r * hw, p + f * fe - r * hw, p - f * re - r * hw, p - f * re + r * hw])


func _obb(a: AICar, b: AICar) -> bool:
	var pa := _corners(a)
	var pb := _corners(b)
	for poly in [pa, pb]:
		for k in 4:
			var e: Vector2 = poly[(k + 1) % 4] - poly[k]
			var ax := Vector2(-e.y, e.x)
			var amin := INF
			var amax := -INF
			var bmin := INF
			var bmax := -INF
			for q in pa:
				var d := q.dot(ax)
				amin = minf(amin, d)
				amax = maxf(amax, d)
			for q in pb:
				var d := q.dot(ax)
				bmin = minf(bmin, d)
				bmax = maxf(bmax, d)
			if amax < bmin or bmax < amin:
				return false
	return true


func _report(final: bool) -> void:
	var avg := speed_sum / maxf(float(speed_n), 1.0) * 3.6
	var waiting := 0
	var buses := 0
	for c in traffic.cars:
		if (c as AICar).speed < 0.3:
			waiting += 1
		if (c as AICar).is_bus:
			buses += 1
	print("  FPS %d, Bild %.1f ms, Prozess %.1f ms" % [Engine.get_frames_per_second(), 1000.0 / maxf(Engine.get_frames_per_second(), 1.0), Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0])
	print("  Physik-Rechenzeit Ø %.2f ms/Schritt, davon KI-Fahrzeuge %.2f ms (Denken %.2f ms), Prüfstand %.2f ms" % [phys_ms / maxf(float(phys_n), 1.0), AICar.prof_us / 1000.0 / maxf(float(phys_n), 1.0), AICar.prof_think_us / 1000.0 / maxf(float(phys_n), 1.0), own_us / 1000.0 / maxf(float(phys_n), 1.0)])
	own_us = 0
	AICar.prof_us = 0
	AICar.prof_think_us = 0
	var mk := 0
	var rs := 0
	for c in traffic.cars:
		mk += (c as AICar).markers.size()
		rs += (c as AICar).route.size()
	var jr := 0
	for k in traffic.jreg:
		jr += (traffic.jreg[k] as Array).size()
	var parts := ""
	for k in AICar.prof_parts:
		parts += " %s %.2f" % [k, AICar.prof_parts[k] / 1000.0 / maxf(float(phys_n), 1.0)]
	AICar.prof_parts.clear()
	print("  Teile:%s | Marken %d Routenpunkte %d jreg %d Knoten %d Kanten %d" % [parts, mk, rs, jr, traffic.nodes.size(), traffic.edges.size()])
	phys_ms = 0.0
	phys_n = 0
	print("TRAFFICBENCH t=%.0f s Fahrzeuge %d (Busse %d, max %d) Ø %.1f km/h stehend %d | Überschneidungen %d | Rot %d Gelb %d | Patt>40s %d | Halte %d angefahren/%d weiter, Linie verloren %d | %s" % [
		t, traffic.cars.size(), buses, max_cars, avg, waiting, overlaps.size(), red_runs, yellow_runs, deadlocks.size(), bus_halts, stops_served, bus_lost.size(), str(traffic.stats)])
	for c in traffic.cars:
		if c is BusCar:
			var b := c as BusCar
			var ns := "-"
			if b.line >= 0 and b.next_stop < b.stops.size():
				ns = "%s in %.0f m" % [String(b.stops[b.next_stop][3]), float(b.stops[b.next_stop][0]) - b.line_s - b.length * 0.5]
			print("  Bus %s uid %d v %.1f s %.0f halt %s nächster %s grenze %s" % [traffic.bus_routes[b.line]["ref"] if b.line >= 0 else "?", b.uid, b.speed, b.line_s, str(b.at_stop), ns, b._limit])
	var tr: Trams = traffic.trams
	if tr:
		var pf := [0, 0, 0]
		var nst := 0
		for w in tr.ways:
			pf[int(w.get("pref", 0)) + 1] += 1
			nst += (w.get("stops", []) as Array).size()
		var ok := 0
		var bad := 0
		var free := 0
		var dw := 0
		for u in tr.trams:
			var tu := u as TramUnit
			if tu.dead:
				continue
			var pr: int = tr.ways[tu.way].get("pref", 0)
			if pr == 0:
				free += 1
			elif pr == tu.dir:
				ok += 1
			else:
				bad += 1
			if tu.dwell > 0.0:
				dw += 1
		var on_line := 0
		var lines := []
		for u in tr.trams:
			var tu := u as TramUnit
			if tu.dead or tu.route < 0:
				continue
			var hp := tr.way_point(tu.way, tu.s)
			var pr2 := tr.route_project(tu.route, Vector2(hp.x, hp.z), tu.route_s - 20.0, tu.route_s + 40.0)
			if float(pr2[1]) < 6.0:
				on_line += 1
			lines.append("%s→%s (%.0f m)" % [tr.routes[tu.route]["ref"], tr.routes[tu.route]["to"], float(pr2[1])])
		print("  Straßenbahn: Gleise mit Richtung +%d/−%d, ohne %d · Haltepunkte %d · Bahnen richtig %d, falsch %d, frei %d, halten %d" % [pf[2], pf[0], pf[1], nst, ok, bad, free, dw])
		print("  Bahnlinien: %d von %d auf ihrer Linie · %s" % [on_line, tr.trams.size(), ", ".join(lines)])
	if final:
		for o in overlaps.slice(0, 20):
			print("  Überschneidung t=%.1f bei %s (v %.1f / %.1f, Δψ %.0f°)\n      A: %s\n      B: %s" % [o[0], str(o[1]), o[2], o[3], o[6], o[4], o[5]])
		for k in deadlocks.keys().slice(0, 8):
			print("  Patt bei ", deadlocks[k])
