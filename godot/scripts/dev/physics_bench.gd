extends SceneTree
## Fahrphysik-Teststand (ohne Stadt, ohne Fenster):
##   godot --headless --path . -s res://scripts/dev/physics_bench.gd [-- --only=C,D]
## Fährt Normmanöver mit dem echten PlayerCar auf einer ebenen Fläche und gibt Messwerte aus:
##   A Beschleunigung 0-100     B Bremsen 100-0          C Kreisfahrt mit Lenkrampe (60 km/h)
##   D Lenkwinkelsprung 80 km/h E Spurwechsel 70 km/h    F Lastwechsel in der Kurve
##   G Tastatur-Volleinschlag 60 km/h   H Handbremse in der Kurve 50 km/h   I Vollgas aus enger Kurve
## "Rutschen" = Schwimmwinkel β (Winkel zwischen Fahrzeuglängsachse und Bewegungsrichtung am Schwerpunkt)
## und Schräglaufwinkel vorn/hinten.

const A_AXLE := 1.36    # Schwerpunkt -> Vorderachse (m)
const B_AXLE := 1.56    # Schwerpunkt -> Hinterachse (m)

var car: PlayerCar
var driver: Node
var tests: Array = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
var ti := -1
var t := 0.0
var phase := 0
var rec := {}
var results: Array = []


func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--only="):
			tests = a.substr(7).split(",")
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
	car.global_transform = Transform3D(Basis.IDENTITY, Vector3(0, 0.62, 0))
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
	var name: String = tests[ti]
	match name:
		"A": _reset(0.0)
		"B": _reset(27.78)
		"C": _reset(16.67)
		"D": _reset(22.22)
		"E": _reset(19.44)
		"F": _reset(19.44)
		"G": _reset(16.67)
		"H": _reset(13.89)
		"I": _reset(6.0)


func _hold_speed(v_target: float) -> void:
	var v := -car.linear_velocity.dot(car.global_transform.basis.z)
	var e := v_target - v
	car.in_throttle = clampf(0.15 + e * 0.6, 0.0, 1.0)
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
			if t < 4.0:
				rec["pitch_max"] = maxf(rec.get("pitch_max", 0.0), absf(m["pitch"]))
			if not rec.has("t100") and m["vx"] >= 27.78:
				rec["t100"] = t
			if t > 22.0:
				results.append("A Beschleunigung: 0-100 km/h %s s, nach 22 s %.0f km/h, Aufbäumen max %.1f°" % [("%.1f" % rec["t100"]) if rec.has("t100") else "—", m["vx"] * 3.6, rec.get("pitch_max", 0.0)])
				_next()
		"B":
			car.in_throttle = 0.0
			car.in_brake = 1.0
			if not rec.has("x0"):
				rec["x0"] = car.global_position
			_track(m)
			if m["vx"] < 0.3 or t > 10.0:
				var d: float = car.global_position.distance_to(rec["x0"])
				results.append("B Bremsen 100-0: %.1f m (%.2f g mittel), Schwimmwinkel max %.1f°, Eintauchen max %.1f°" % [d, 27.78 * 27.78 / (2.0 * d) / 9.81, rec["beta_max"], rec.get("pitch_max", 0.0)])
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
