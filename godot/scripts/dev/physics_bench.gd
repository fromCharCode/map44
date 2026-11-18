extends SceneTree
## Fahrphysik-Teststand (ohne Stadt, ohne Fenster):
##   godot --headless --path . -s res://scripts/dev/physics_bench.gd [-- --only=C,D]
## Fährt Normmanöver mit dem echten PlayerCar auf einer ebenen Fläche und gibt Messwerte aus:
##   A Beschleunigung 0-100     B Bremsen 100-0          C Kreisfahrt mit Lenkrampe (60 km/h)
##   D Lenkwinkelsprung 80 km/h E Spurwechsel 70 km/h    F Lastwechsel in der Kurve
##   G Tastatur-Volleinschlag 60 km/h   H Handbremse in der Kurve 50 km/h   I Vollgas aus enger Kurve
##   J Höchstgeschwindigkeit   K Tempomat   L/M umfahrbares Objekt
##   N Bremsweg 50-0   O Bremsweg 130-0   W Bremsweg 100-0 nass   P Kreisfahrt Ø 40 m (Querbeschleunigung)
##   Q Slalom 80 km/h (18-m-Raster)   R Bordstein 13 cm gerade 30/50 km/h   S Bordstein schräg 30 km/h
##   T Stand (Zittern)   U Berg 12 % (Halten, Anfahren)   V Geradeauslauf 200 km/h mit Lenkimpuls
##   X Automatik (Schaltruhe bei Konstantfahrt, Kickdown 80-120)   Y Lastwechsel/Bremsen in der Kurve 90 km/h
##   Z Kickdown in der Kurve 70 km/h (trocken und nass)   RW Rückwärtsfahren, Richtungswechsel, Ausrollen
## --grip=0.78 fährt alle Tests auf nasser Fahrbahn (Haftungsfaktor wie main.gd bei voller Nässe).
## Schnell (ohne Echtzeit): godot --headless --fixed-fps 90 --path . -s res://scripts/dev/physics_bench.gd
## "Rutschen" = Schwimmwinkel β (Winkel zwischen Fahrzeuglängsachse und Bewegungsrichtung am Schwerpunkt)
## und Schräglaufwinkel vorn/hinten.

const A_AXLE := PlayerCar.A_AXLE    # Schwerpunkt -> Vorderachse (m)
const B_AXLE := PlayerCar.B_AXLE    # Schwerpunkt -> Hinterachse (m)

var car: PlayerCar
var driver: Node
var tests: Array = ["A", "B", "N", "O", "W", "C", "P", "D", "E", "Q", "F", "Y", "Z", "G", "H", "I", "J", "V", "K", "X", "R", "S", "T", "U", "RW", "L", "M"]
var base_grip := 1.0             # --grip=0.78: alle Tests auf nasser Fahrbahn
var extra: Array = []            # zusätzliche Testkörper (Bordstein, Rampe), werden beim Testwechsel entfernt
var ti := -1
var t := 0.0
var phase := 0
var rec := {}
var results: Array = []


func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--only="):
			tests = a.substr(7).split(",")
		if a.begins_with("--grip="):
			base_grip = float(a.substr(7))
	var ground := StaticBody3D.new()
	ground.collision_layer = 1
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = Vector3(6000, 2, 6000)
	cs.shape = bs
	ground.add_child(cs)
	ground.position = Vector3(0, -1, 0)
	root.add_child(ground)
	car = PlayerCar.new()
	root.add_child(car)
	car.setup()
	car.override_input = true
	car.damage_enabled = false
	physics_frame.connect(_step)
	_next()


func _reset(speed_ms: float) -> void:
	car.global_transform = Transform3D(Basis.IDENTITY, Vector3(0, -0.05, 0))     # knapp über der Ruhelage (−0,07)
	car.linear_velocity = Vector3(0, 0, -speed_ms)
	car.angular_velocity = Vector3.ZERO
	for k in car.wheels:
		car.wheels[k]["omega"] = speed_ms / PlayerCar.WHEEL_R
	car.steer_angle = 0.0
	car.in_steer = 0.0
	car.in_throttle = 0.0
	car.in_brake = 0.0
	car.in_handbrake = false
	car.gear = 1 if speed_ms < 8.0 else (3 if speed_ms < 20.0 else 4)
	car.manual = false
	t = 0.0
	phase = 0
	rec = {"beta_max": 0.0, "alat_max": 0.0, "af_max": 0.0, "ar_max": 0.0, "spin": false}


func _next() -> void:
	ti += 1
	if ti >= tests.size():
		print("\n=== ERGEBNIS ===")
		for r in results:
			print(r)
		quit()
		return
	for e in extra:
		(e as Node).queue_free()
	extra.clear()
	car.grip = base_grip
	var name: String = tests[ti]
	match name:
		"N": _reset(13.89)
		"O": _reset(36.11)
		"W":
			_reset(27.78)
			car.grip = 0.78
		"P": _reset(8.0)
		"Q": _reset(22.22)
		"Y": _reset(25.0)
		"Z": _reset(19.44)
		"V": _reset(55.56)
		"X": _reset(8.33)
		"R":
			_reset(8.33)
			_add_box(Vector3(30, 0.13, 30), Vector3(0, 0.065, -35), 0.0)
		"S":
			_reset(8.33)
			_add_box(Vector3(60, 0.13, 30), Vector3(0, 0.065, -38), deg_to_rad(30.0))
		"T": _reset(0.0)
		"RW": _reset(0.0)
		"U":
			_reset(0.0)
			var ang := atan(0.12)
			var slab := _add_box(Vector3(40, 2, 600), Vector3(2000, 60, 0), 0.0)
			slab.rotation.x = ang
			var bs := Basis(Vector3.RIGHT, ang)
			car.global_transform = Transform3D(bs, Vector3(2000, 60, 0) + bs.y * 0.95)
		"A": _reset(0.0)
		"B": _reset(27.78)
		"J": _reset(58.0)
		"L": _reset(13.89)
		"M": _reset(2.5)
		"K": _reset(11.0)
		"C": _reset(16.67)
		"D": _reset(22.22)
		"E": _reset(19.44)
		"F": _reset(19.44)
		"G": _reset(16.67)
		"H": _reset(13.89)
		"I": _reset(6.0)


func _add_box(size: Vector3, pos: Vector3, yaw: float) -> StaticBody3D:
	var sb := StaticBody3D.new()
	sb.collision_layer = 1
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = size
	cs.shape = bs
	sb.add_child(cs)
	root.add_child(sb)
	sb.global_transform = Transform3D(Basis(Vector3.UP, yaw), pos)
	extra.append(sb)
	return sb


func _brake_test(name: String, label: String, v0: float, m: Dictionary) -> void:
	car.in_throttle = 0.0
	car.in_brake = 1.0
	if not rec.has("x0"):
		rec["x0"] = car.global_position
	_track(m)
	if car.abs_active:
		rec["abs"] = rec.get("abs", 0) + 1
	if m["vx"] < 0.3 or t > 14.0:
		var d: float = car.global_position.distance_to(rec["x0"])
		results.append("%s %s: %.1f m (%.2f g mittel), Schwimmwinkel max %.1f°, Eintauchen max %.1f°, ABS-Schritte %d" % [name, label, d, v0 * v0 / (2.0 * d) / 9.81, rec["beta_max"], rec.get("pitch_max", 0.0), rec.get("abs", 0)])
		_next()


func _kerb_test(name: String, label: String, m: Dictionary, dt: float) -> void:
	# Fahrt mit 30 km/h auf ein 13 cm hohes Podest (Bordstein), 20 m darauf, dann (R) Wiederholung mit 50 km/h
	var v_t: float = rec.get("v_t", 8.33)
	_hold_speed(v_t)
	if not rec.has("y0") and t > 1.0:
		rec["y0"] = car.global_position.y
		rec["vmin"] = 99.0
	if t > 1.0:
		rec["vmin"] = minf(rec["vmin"], m["vx"])
		rec["pitch_k"] = maxf(rec.get("pitch_k", 0.0), absf(m["pitch"]))
		rec["roll_k"] = maxf(rec.get("roll_k", 0.0), absf(m["roll"]))
		rec["vy_max"] = maxf(rec.get("vy_max", 0.0), car.linear_velocity.y)
		rec["y_max"] = maxf(rec.get("y_max", 0.0), car.global_position.y - float(rec["y0"]))
		if car.grounded < 3:
			rec["air"] = rec.get("air", 0.0) + dt
		rec["beta_k"] = maxf(rec.get("beta_k", 0.0), absf(m["beta"]))
		var ay := (car.linear_velocity.y - float(rec.get("vy_prev", 0.0))) / dt / 9.81
		rec["ay_max"] = maxf(rec.get("ay_max", 0.0), absf(ay))
	rec["vy_prev"] = car.linear_velocity.y
	if t > 4.5:
		results.append("%s %s %.0f km/h: Tempo min %.1f km/h, Nicken max %.1f°, Wanken max %.1f°, Aufbau hebt max %.2f m (Podest 0.13), v_hoch max %.2f m/s, a_vert max %.1f g, Zeit <3 Räder am Boden %.2f s, β max %.1f°, Kurs am Ende %.1f°" % [
			name, label, v_t * 3.6, rec["vmin"] * 3.6, rec.get("pitch_k", 0.0), rec.get("roll_k", 0.0), rec.get("y_max", 0.0), rec.get("vy_max", 0.0), rec.get("ay_max", 0.0), rec.get("air", 0.0), rec.get("beta_k", 0.0),
			rad_to_deg(car.global_transform.basis.get_euler().y)])
		if name == "R" and v_t < 10.0:
			_reset(13.89)
			rec["v_t"] = 13.89
		else:
			_next()


func _hold_speed(v_target: float) -> void:
	var v := -car.linear_velocity.dot(car.global_transform.basis.z)
	var e := v_target - v
	car.in_throttle = clampf(0.15 + e * 0.6, 0.0, 0.9)      # unter der Kickdown-Schwelle bleiben
	car.in_brake = clampf(-e * 0.4, 0.0, 1.0) if e < -1.0 else 0.0


func _measure() -> Dictionary:
	var b := car.global_transform.basis
	var v := car.linear_velocity
	var vx := -v.dot(b.z)             # vorwärts
	var vy := v.dot(b.x)              # rechts
	var r := car.angular_velocity.dot(b.y)   # Gierrate (+ = links)
	var beta := rad_to_deg(atan2(vy, maxf(absf(vx), 0.5)))
	# Schräglaufwinkel (vereinfachtes Einspurmodell): Querbewegung der Achsen relativ zur Radebene
	var vf_y := vy - r * A_AXLE          # Linksdrehung bewegt die Front nach links (= -x)
	var vr_y := vy + r * B_AXLE
	var af := rad_to_deg(atan2(vf_y, maxf(absf(vx), 0.5)) + car.steer_angle)
	var ar := rad_to_deg(atan2(vr_y, maxf(absf(vx), 0.5)))
	var alat := vx * r / 9.81
	var roll := rad_to_deg(asin(clampf(b.x.y, -1.0, 1.0)))
	var pitch := rad_to_deg(asin(clampf(-b.z.y, -1.0, 1.0)))
	return {"vx": vx, "beta": beta, "r": r, "af": af, "ar": ar, "alat": alat, "roll": roll, "pitch": pitch}


func _track(m: Dictionary) -> void:
	rec["beta_max"] = maxf(rec["beta_max"], absf(m["beta"]))
	rec["alat_max"] = maxf(rec["alat_max"], absf(m["alat"]))
	rec["af_max"] = maxf(rec["af_max"], absf(m["af"]))
	rec["ar_max"] = maxf(rec["ar_max"], absf(m["ar"]))
	if absf(m["beta"]) > 25.0:
		rec["spin"] = true
	rec["roll_max"] = maxf(rec.get("roll_max", 0.0), absf(m["roll"]))
	rec["pitch_max"] = maxf(rec.get("pitch_max", 0.0), absf(m["pitch"]))


func _step() -> void:
	var dt := 1.0 / float(Engine.physics_ticks_per_second)
	t += dt
	var m := _measure()
	var name: String = tests[ti]
	match name:
		"A":
			car.in_throttle = 1.0
			if OS.has_environment("BENCH_TRACE") and int(t * 90.0) % 9 == 0 and t < 5.0:
				print("A t=%.2f v=%.1f nick=%.2f gang=%d rpm=%.0f comp FL %.3f RL %.3f ωRL %.1f tc=%s y=%.3f" % [t, m["vx"], m["pitch"], car.gear, car.rpm, car.wheels["FL"]["comp"], car.wheels["RL"]["comp"], car.wheels["RL"]["omega"], car.tc_active, car.global_position.y])
			if t < 4.0:
				rec["pitch_max"] = maxf(rec.get("pitch_max", 0.0), absf(m["pitch"]))
			if not rec.has("t100") and m["vx"] >= 27.78:
				rec["t100"] = t
			if t > 22.0:
				results.append("A Beschleunigung: 0-100 km/h %s s, nach 22 s %.0f km/h, Aufbäumen max %.1f°" % [("%.1f" % rec["t100"]) if rec.has("t100") else "—", m["vx"] * 3.6, rec.get("pitch_max", 0.0)])
				_next()
		"L", "M":
			# Umfahrbares Objekt 12 m voraus: L Ampelmast (110 kg, ab 35 km/h) mit 50 km/h -> bricht;
			# M derselbe Mast mit 9 km/h -> bleibt stehen, Auto wird gestoppt
			if not rec.has("obj"):
				var sb := StaticBody3D.new()
				sb.collision_layer = 1 | Breakables.LAYER
				var cs := CollisionShape3D.new()
				var cy := CylinderShape3D.new()
				cy.radius = 0.09
				cy.height = 4.0
				cs.shape = cy
				sb.add_child(cs)
				root.add_child(sb)
				sb.global_position = Vector3(0.3, 2.0, -12.0)
				Breakables.tag(cs, [], 0, [], Transform3D(Basis(), Vector3(0.3, 0, -12.0)), 110.0, 35.0, 6000.0)
				rec["obj"] = sb
				rec["cs"] = cs
				rec["n0"] = Breakables.broken
				rec["v0"] = m["vx"]
			car.in_throttle = 0.0 if name == "L" else 0.12
			rec["vmin"] = minf(rec.get("vmin", 99.0), m["vx"])
			if t > (3.0 if name == "L" else 9.0):
				results.append("%s Objekt bei %.0f km/h: gebrochen %s, Form aus %s, Tempo danach min %.1f km/h, Position z %.1f" % [name, rec["v0"] * 3.6, str(Breakables.broken > rec["n0"]), str((rec["cs"] as CollisionShape3D).disabled), rec["vmin"] * 3.6, car.global_position.z])
				(rec["obj"] as Node).queue_free()
				_next()
		"J":
			# Höchstgeschwindigkeit: Vollgas ab 209 km/h, 40 s
			car.in_throttle = 1.0
			if t > 40.0:
				results.append("J Höchstgeschwindigkeit: %.0f km/h (Gang %d, %.0f/min)" % [m["vx"] * 3.6, car.gear, car.rpm])
				_next()
		"K":
			# Tempomat: von 40 auf 50 km/h setzen, nach 15 s auf 100; Überschwingen und Restabweichung
			if t < 0.05:
				car.cruise_on = true
				car.cruise_target = 50.0 / 3.6
			if t > 15.0:
				car.cruise_target = 100.0 / 3.6
			car.in_throttle = car.cruise_throttle(dt)
			if t < 15.0:
				rec["max50"] = maxf(rec.get("max50", 0.0), m["vx"] * 3.6)
				if t > 10.0:
					rec["lo50"] = minf(rec.get("lo50", 999.0), m["vx"] * 3.6)
			else:
				rec["max100"] = maxf(rec.get("max100", 0.0), m["vx"] * 3.6)
				if not rec.has("t100") and m["vx"] * 3.6 >= 99.0:
					rec["t100"] = t - 15.0
			if t > 45.0:
				results.append("K Tempomat: Soll 50 -> max %.1f, min (10–15 s) %.1f km/h; Soll 100 -> erreicht nach %s s, max %.1f, am Ende %.1f km/h" % [rec["max50"], rec["lo50"], ("%.1f" % rec["t100"]) if rec.has("t100") else "—", rec["max100"], m["vx"] * 3.6])
				car.cruise_on = false
				_next()
		"B":
			_brake_test("B", "Bremsen 100-0", 27.78, m)
		"N":
			_brake_test("N", "Bremsen 50-0", 13.89, m)
		"O":
			_brake_test("O", "Bremsen 130-0", 36.11, m)
		"W":
			_brake_test("W", "Bremsen 100-0 nass (grip 0.78)", 27.78, m)
		"R":
			_kerb_test("R", "Bordstein 13 cm gerade", m, dt)
		"S":
			_kerb_test("S", "Bordstein 13 cm schräg 30°", m, dt)
		"P":
			# Kreisfahrt Ø 40 m (R = 20 m) nach links, Tempo steigt langsam; Regler hält den Radius
			var vt := 8.0 + 0.3 * t
			_hold_speed(vt)
			var cpos := Vector3(-20.0, 0.0, 0.0)
			var rad := Vector2(car.global_position.x - cpos.x, car.global_position.z - cpos.z).length()
			var e := rad - 20.0
			var de: float = (e - float(rec.get("e_prev", e))) / dt
			rec["e_prev"] = e
			car.in_steer = clampf(car.in_steer - (e * 0.9 + de * 1.6) * dt, -1.0, 0.0)
			rec["al"] = lerpf(float(rec.get("al", 0.0)), absf(m["alat"]), dt / 0.4)
			if absf(e) < 1.5:
				if float(rec["al"]) > float(rec.get("al_max", 0.0)):
					rec["al_max"] = rec["al"]
					rec["p_at"] = "v %.0f km/h, δ %.1f°, β %.1f°, αv %.1f°, αh %.1f°, Wanken %.1f°" % [m["vx"] * 3.6, rad_to_deg(car.steer_angle), m["beta"], m["af"], m["ar"], m["roll"]]
				if not rec.has("d04") and float(rec["al"]) >= 0.4:
					rec["d04"] = rad_to_deg(car.steer_angle)
				if not rec.has("d08") and float(rec["al"]) >= 0.8:
					rec["d08"] = rad_to_deg(car.steer_angle)
			_track(m)
			if e > 3.0 or t > 30.0:
				results.append("P Kreisfahrt Ø 40 m: a_quer max %.2f g (%s); Lenkwinkel bei 0,4 g %.1f°, bei 0,8 g %.1f° (mehr = Untersteuern); Ende nach %.1f s: %s%s" % [
					rec.get("al_max", 0.0), rec.get("p_at", ""), rec.get("d04", 0.0), rec.get("d08", 0.0), t, "schiebt nach außen" if e > 3.0 else "Zeit", "  ** DREHER **" if rec["spin"] else ""])
				_next()
		"Q":
			# Slalom 80 km/h, Pylonen alle 18 m -> 0,62 Hz, 5 Perioden
			_hold_speed(22.22)
			var fq := 22.22 / 36.0
			if t > 0.5 and t < 0.5 + 5.0 / fq:
				car.in_steer = -0.42 * sin(TAU * fq * (t - 0.5))
			else:
				car.in_steer = 0.0
			_track(m)
			rec["x_max"] = maxf(rec.get("x_max", 0.0), absf(car.global_position.x))
			if t > 0.5 + 5.0 / fq + 2.0:
				results.append("Q Slalom 80 km/h: seitl. Ausschlag ±%.1f m, a_quer max %.2f g, β max %.1f°, αh max %.1f°, Wanken max %.1f°, Rest-Gierrate %.3f rad/s, v Ende %.0f km/h%s" % [
					rec["x_max"], rec["alat_max"], rec["beta_max"], rec["ar_max"], rec.get("roll_max", 0.0), absf(m["r"]), m["vx"] * 3.6, "  ** DREHER **" if rec["spin"] else ""])
				_next()
		"Y":
			# Kurve 90 km/h mit ~0,6 g, dann Gas weg + mittlere Bremsung (40 %): Eindrehen muss gutmütig bleiben
			if t < 4.0:
				_hold_speed(25.0)
				car.in_steer = -0.42
				rec["r0"] = absf(m["r"])
				rec["a0"] = absf(m["alat"])
			else:
				car.in_throttle = 0.0
				car.in_brake = 0.4
				car.in_steer = -0.42
				rec["b1"] = maxf(rec.get("b1", 0.0), absf(m["beta"]))
				rec["rk"] = maxf(rec.get("rk", 0.0), absf(m["r"]))
				rec["arh"] = maxf(rec.get("arh", 0.0), absf(m["ar"]))
			_track(m)
			if t > 7.0:
				results.append("Y Bremsen in der Kurve 90 km/h (%.2f g quer, 40 %% Pedal): β max %.1f°, αh max %.1f°, Gierrate %.2f -> max %.2f rad/s, v Ende %.0f km/h%s" % [
					rec.get("a0", 0.0), rec.get("b1", 0.0), rec.get("arh", 0.0), rec.get("r0", 0.0), rec.get("rk", 0.0), m["vx"] * 3.6, "  ** DREHER **" if rec["spin"] else ""])
				_next()
		"Z":
			# Kickdown in der Kurve: 70 km/h mit ~0,55 g, dann Vollgas (Automatik schaltet zurück) – trocken und nass
			if t < 4.0:
				_hold_speed(19.44)
				car.in_steer = -0.32
				rec["a0"] = absf(m["alat"])
			else:
				car.in_throttle = 1.0
				car.in_brake = 0.0
				car.in_steer = -0.32
				rec["b1"] = maxf(rec.get("b1", 0.0), absf(m["beta"]))
				rec["arh"] = maxf(rec.get("arh", 0.0), absf(m["ar"]))
				rec["gmin"] = mini(int(rec.get("gmin", 9)), car.gear)
				if car.tc_active:
					rec["tc"] = rec.get("tc", 0) + 1
				if car.esp_active:
					rec["esp"] = rec.get("esp", 0) + 1
			_track(m)
			if t > 7.5:
				results.append("Z Kickdown in der Kurve 70 km/h (%.2f g quer)%s: Gang %d, β max %.1f°, αh max %.1f°, TC-Schritte %d, ESP-Schritte %d, v Ende %.0f km/h%s" % [
					rec.get("a0", 0.0), " NASS" if car.grip < 0.9 else "", rec.get("gmin", 0), rec.get("b1", 0.0), rec.get("arh", 0.0), rec.get("tc", 0), rec.get("esp", 0), m["vx"] * 3.6, "  ** DREHER **" if rec["spin"] else ""])
				if car.grip > 0.9 and base_grip > 0.9:
					_reset(19.44)
					car.grip = 0.78
				else:
					_next()
					return
		"RW":
			# 1–5 s Bremse halten (= rückwärts), 5–9 s Vollgas (Richtungswechsel), 9–11 s halten, dann loslassen: Ausrollen
			if t < 1.0:
				car.in_throttle = 0.0
				car.in_brake = 0.0
			elif t < 5.0:
				car.in_brake = 1.0
				rec["v_back"] = minf(rec.get("v_back", 0.0), m["vx"])
			elif t < 9.0:
				car.in_brake = 0.0
				car.in_throttle = 1.0
				if not rec.has("t_fwd") and m["vx"] > 0.0:
					rec["t_fwd"] = t - 5.0
				rec["v_fwd"] = m["vx"]
			elif t < 14.0:
				car.in_throttle = 0.0
				car.in_brake = 0.35
				if not rec.has("t_stop") and absf(m["vx"]) < 1.3:
					rec["t_stop"] = t - 9.0
				if absf(m["vx"]) < 1.3:
					car.in_brake = 0.0      # wie ein Fahrer: bei Schritttempo Bremse lösen (sonst = Rückwärtsgang)
					rec["a_roll"] = maxf(rec.get("a_roll", 0.0), absf(m["vx"] - float(rec.get("v_prev", m["vx"]))) / dt)
				if OS.has_environment("BENCH_TRACE") and absf(m["vx"]) < 1.4 and int(rec.get("ntr", 0)) < 70:
					rec["ntr"] = int(rec.get("ntr", 0)) + 1
					PlayerCar.debug = true
					print("RW t=%.3f v=%.3f a=%.1f Bremse %.2f Gas %.2f Gang %d rück %s | %s" % [t, m["vx"], (m["vx"] - float(rec.get("v_prev", m["vx"]))) / dt, car.in_brake, car.in_throttle, car.gear, car.reversing, car.dbg])
				rec["v_prev"] = m["vx"]
			if t > 14.0:
				results.append("RW Rückwärts: v max %.1f km/h nach 4 s; Richtungswechsel mit Vollgas: vorwärts nach %s s, v nach 4 s %.0f km/h; Bremsen 35 %% bis Schritttempo %s s, Ausrollen max %.1f m/s², v Ende %.2f m/s, Gang %d" % [
					-float(rec.get("v_back", 0.0)) * 3.6, ("%.1f" % rec["t_fwd"]) if rec.has("t_fwd") else "—", float(rec.get("v_fwd", 0.0)) * 3.6, ("%.1f" % rec["t_stop"]) if rec.has("t_stop") else "—", rec.get("a_roll", 0.0), m["vx"], car.gear])
				_next()
		"T":
			# Stand: nach 2 s Setzen 6 s lang Bewegung messen (Zittern)
			if t > 2.0:
				rec["v_rms"] = rec.get("v_rms", 0.0) + car.linear_velocity.length_squared()
				rec["w_rms"] = rec.get("w_rms", 0.0) + car.angular_velocity.length_squared()
				rec["n"] = rec.get("n", 0) + 1
				if not rec.has("p0"):
					rec["p0"] = car.global_position
			if t > 8.0:
				var nn: float = maxf(float(rec["n"]), 1.0)
				results.append("T Stand: v_eff %.5f m/s, ω_eff %.5f rad/s, Drift in 6 s %.4f m, Fahrhöhe %.3f m" % [sqrt(rec["v_rms"] / nn), sqrt(rec["w_rms"] / nn), car.global_position.distance_to(rec["p0"]), car.global_position.y])
				_next()
		"U":
			# Berg 12 %: 4 s stehen (ohne Eingabe), dann 0,5 s Bremse lösen/halb Gas -> Zurückrollen messen, Zeit auf 30 km/h
			if not rec.has("p0") and t > 1.5:
				rec["p0"] = car.global_position
			if t < 4.0:
				car.in_throttle = 0.0
			else:
				if not rec.has("p1"):
					rec["p1"] = car.global_position
				car.in_throttle = minf((t - 4.0) / 0.4, 0.5)
				rec["back"] = minf(rec.get("back", 0.0), m["vx"])
				if not rec.has("t30") and m["vx"] > 8.33:
					rec["t30"] = t - 4.0
			if t > 12.0:
				results.append("U Berg 12 %%: Wegrollen im Stand (2,5 s) %.3f m, Zurückrollen beim Anfahren max %.2f m/s, 0-30 km/h bergauf mit Halbgas %s s, v Ende %.0f km/h" % [
					(rec["p1"] as Vector3).distance_to(rec["p0"]), -float(rec.get("back", 0.0)), ("%.1f" % rec["t30"]) if rec.has("t30") else "—", m["vx"] * 3.6])
				_next()
		"V":
			# Geradeauslauf 200 km/h: Lenkimpuls (20 % für 0,25 s), danach Hände ruhig -> Abklingen
			_hold_speed(55.56)
			car.in_steer = -0.2 if (t > 2.0 and t < 2.25) else 0.0
			_track(m)
			if t < 2.0:
				rec["r_pre"] = maxf(rec.get("r_pre", 0.0), absf(m["r"]))
			if t > 2.25:
				rec["r_pk"] = maxf(rec.get("r_pk", 0.0), absf(m["r"]))
				# Nulldurchgänge der Gierrate zählen (Pendeln)
				var sg := signf(m["r"]) if absf(m["r"]) > 0.004 else 0.0
				if sg != 0.0 and sg != float(rec.get("sg", sg)):
					rec["zc"] = rec.get("zc", 0) + 1
				if sg != 0.0:
					rec["sg"] = sg
			if t > 3.25 and not rec.has("r1s"):
				rec["r1s"] = absf(m["r"])
			if t > 8.0:
				results.append("V Geradeauslauf 200 km/h: Gierrate ohne Eingriff max %.4f rad/s; nach Lenkimpuls max %.3f rad/s, 1 s danach %.4f, am Ende %.4f rad/s, Vorzeichenwechsel %d, β max %.2f°, a_quer max %.2f g%s" % [
					rec.get("r_pre", 0.0), rec.get("r_pk", 0.0), rec.get("r1s", 0.0), absf(m["r"]), rec.get("zc", 0), rec["beta_max"], rec["alat_max"], "  ** DREHER **" if rec["spin"] else ""])
				_next()
		"X":
			# Automatik: je 8 s Konstantfahrt 30/50/70/100/130 km/h -> Schaltvorgänge nach dem Einschwingen (letzte 5 s);
			# danach Kickdown bei 80 km/h: Zeit 80-120 und gewählter Gang
			var stages := [8.33, 13.89, 19.44, 27.78, 36.11]
			var si := int(t / 10.0)
			if si < stages.size():
				_hold_speed(stages[si])
				var tl := fmod(t, 10.0)
				if tl > 5.0:
					if int(rec.get("g_prev", car.gear)) != car.gear:
						rec["sh%d" % si] = rec.get("sh%d" % si, 0) + 1
					rec["g%d" % si] = car.gear
					rec["rpm%d" % si] = car.rpm
				if OS.has_environment("BENCH_TRACE") and int(rec.get("g_prev", car.gear)) != car.gear:
					print("X t=%.2f Gang %d -> %d bei %.0f km/h, Gas %.2f, %.0f/min" % [t, rec.get("g_prev", 0), car.gear, m["vx"] * 3.6, car.in_throttle, car.rpm])
				rec["g_prev"] = car.gear
			elif t < 58.0:
				_hold_speed(22.22)
				rec["g_before"] = car.gear
			else:
				car.in_throttle = 1.0
				car.in_brake = 0.0
				if t < 59.0:
					rec["g_kd"] = mini(int(rec.get("g_kd", 9)), car.gear)
				if not rec.has("t120") and m["vx"] >= 33.33:
					rec["t120"] = t - 58.0
				if rec.has("t120") or t > 75.0:
					var line := "X Automatik:"
					for i in stages.size():
						line += " %d km/h Gang %d (%.0f/min, %d Wechsel)," % [int(round(stages[i] * 3.6)), rec.get("g%d" % i, 0), rec.get("rpm%d" % i, 0.0), rec.get("sh%d" % i, 0)]
					line += " Kickdown 80 km/h: Gang %d -> %d, 80-120 in %s s" % [rec.get("g_before", 0), rec.get("g_kd", 0), ("%.1f" % rec["t120"]) if rec.has("t120") else "—"]
					results.append(line)
					_next()
		"C":
			_hold_speed(16.67)
			car.in_steer = -clampf((t - 1.0) / 8.0, 0.0, 1.0)     # nach links (negativ = links? siehe PlayerCar)
			_track(m)
			if t > 1.0 and absf(m["alat"]) >= rec["alat_max"] - 0.001:
				rec["at_max"] = "Lenk %.2f δ=%.1f° β=%.1f° αv=%.1f° αh=%.1f°" % [car.in_steer, rad_to_deg(car.steer_angle), m["beta"], m["af"], m["ar"]]
			if t > 9.5:
				results.append("C Kreisfahrt 60 km/h, Lenkrampe: a_quer max %.2f g bei %s | Ende: β %.1f°, αv %.1f°, αh %.1f°, v %.0f km/h, Wanken max %.1f°%s" % [
					rec["alat_max"], rec.get("at_max", ""), m["beta"], m["af"], m["ar"], m["vx"] * 3.6, rec.get("roll_max", 0.0), "  ** DREHER **" if rec["spin"] else ""])
				_next()
		"D":
			_hold_speed(22.22)
			car.in_steer = -0.35 if t > 0.5 else 0.0
			_track(m)
			if t > 0.5:
				rec["r_peak"] = maxf(rec.get("r_peak", 0.0), absf(m["r"]))
			if t > 3.0 and t < 3.05:
				rec["r_ss"] = absf(m["r"])
			if t > 3.5:
				var ov: float = (rec["r_peak"] / maxf(rec.get("r_ss", 0.001), 0.001) - 1.0) * 100.0
				results.append("D Lenkwinkelsprung 80 km/h (35 %%): Gierrate stationär %.2f rad/s, Überschwingen %.0f %%, a_quer %.2f g, β max %.1f°%s" % [
					rec.get("r_ss", 0.0), ov, rec["alat_max"], rec["beta_max"], "  ** DREHER **" if rec["spin"] else ""])
				_next()
		"E":
			_hold_speed(19.44)
			if t > 0.5 and t < 4.5:
				car.in_steer = -0.55 * sin(TAU * 0.5 * (t - 0.5))
			else:
				car.in_steer = 0.0
			_track(m)
			if t > 7.0:
				results.append("E Doppelter Spurwechsel 70 km/h: β max %.1f°, αh max %.1f°, a_quer max %.2f g, Rest-Gierrate %.2f rad/s, Wanken max %.1f°%s" % [
					rec["beta_max"], rec["ar_max"], rec["alat_max"], absf(m["r"]), rec.get("roll_max", 0.0), "  ** DREHER **" if rec["spin"] else ""])
				_next()
		"F":
			if t < 4.0:
				_hold_speed(19.44)
				car.in_steer = -0.30
				rec["r0"] = absf(m["r"])
				rec["b0"] = m["beta"]
			else:
				car.in_throttle = 0.0
				car.in_brake = 0.0
				car.in_steer = -0.30
				rec["r1"] = maxf(rec.get("r1", 0.0), absf(m["r"]))
				rec["b1"] = maxf(rec.get("b1", 0.0), absf(m["beta"]))
			_track(m)
			if t > 6.0:
				results.append("F Lastwechsel (Gas weg in Kurve, 70 km/h): Gierrate %.2f -> max %.2f rad/s, β %.1f° -> max %.1f°%s" % [
					rec["r0"], rec.get("r1", 0.0), absf(rec["b0"]), rec.get("b1", 0.0), "  ** DREHER **" if rec["spin"] else ""])
				_next()
		"G":
			_hold_speed(16.67)
			# Tastatur: Lenkung läuft mit 4.2/s auf Vollausschlag (wie _read_input)
			if t > 0.5:
				car.in_steer = move_toward(car.in_steer, -1.0, 4.2 * dt)
			_track(m)
			if t > 3.5:
				results.append("G Tastatur-Volleinschlag 60 km/h: β max %.1f°, αv max %.1f°, αh max %.1f°, a_quer max %.2f g, v Ende %.0f km/h%s" % [
					rec["beta_max"], rec["af_max"], rec["ar_max"], rec["alat_max"], m["vx"] * 3.6, "  ** DREHER **" if rec["spin"] else ""])
				_next()
		"H":
			# Handbremse: soll das Heck kontrolliert herumholen (Drift), danach wieder fangen
			if t < 1.0:
				_hold_speed(13.89)
				car.in_steer = -0.5
			elif t < 2.0:
				car.in_throttle = 0.0
				car.in_handbrake = true
				car.in_steer = -1.0
			else:
				car.in_handbrake = false
				car.in_steer = 0.0
				car.in_throttle = 0.3
			if t > 1.0 and t < 2.2:
				rec["bh"] = maxf(rec.get("bh", 0.0), absf(m["beta"]))
			if t > 4.4:
				rec["bend"] = absf(m["beta"])
			_track(m)
			if t > 4.5:
				results.append("H Handbremse 50 km/h: β max %.1f° (Drift erwünscht 15-60°), β nach 2.5 s %.1f°, Gierrate Ende %.2f rad/s" % [
					rec.get("bh", 0.0), rec.get("bend", 0.0), absf(m["r"])])
				_next()
		"I":
			# Vollgas aus enger Kurve im 1./2. Gang (Traktionskontrolle an)
			car.in_steer = -0.8
			car.in_throttle = 1.0 if t > 0.5 else 0.2
			_track(m)
			if t > 4.0:
				results.append("I Vollgas aus enger Kurve: β max %.1f°, αh max %.1f°, v Ende %.0f km/h%s" % [
					rec["beta_max"], rec["ar_max"], m["vx"] * 3.6, "  ** DREHER **" if rec["spin"] else ""])
				_next()
