class_name PlayerCar
extends RigidBody3D
## Spielerfahrzeug: Raycast-Fahrwerk (Feder/Dämpfer), Reifenreibung mit Reibkreis,
## Motorkennlinie mit Automatikgetriebe, Handbremse, Lichter.

# Geometrie (Taxi-Modell)
const WHEEL_X := 0.79
const WHEEL_Z := 1.46
const WHEEL_R := 0.34
const HUB_REST := 0.34          # Radmitte über Boden im Ruhezustand
const SUSP_REST := 0.26         # Länge Strahlursprung -> Radmitte in Ruhe
const SUSP_DROOP := 0.20        # zusätzlicher Ausfederweg
# Fahrwerk „GTA-4/BeamNG-Gefühl“: weicher (1,4 Hz statt 1,85 Hz), sichtbare Gewichtsverlagerung (Wanken ~4°/g,
# Eintauchen beim Bremsen, Aufbäumen beim Anfahren), getrennte Zug-/Druckstufe. Vorspannung hält die Fahrhöhe.
const SPRING_K := 30000.0
const SPRING_PRE := 0.057       # Vorspannweg (m): statischer Einfederweg bleibt wie beim alten 52-kN-Fahrwerk
const DAMP_BUMP := 2300.0       # Druckstufe (Einfedern)  ζ ≈ 0,34
const DAMP_REB := 3600.0        # Zugstufe (Ausfedern)    ζ ≈ 0,53
const BUMP_START := 0.12        # Anschlagpuffer ab diesem Einfederweg
const ARB_F := 8000.0           # Wankstütze vorn  (vorn steifer -> sicheres Untersteuern im Grenzbereich)
const ARB_R := 3000.0           # Wankstütze hinten
const A_AXLE := 1.36            # Schwerpunkt -> Vorderachse (m)
const B_AXLE := 1.56            # Schwerpunkt -> Hinterachse (m)
const RELAX_LEN := 0.35         # Einlauflänge der Seitenkraft (m)
const LAT_GAIN := 0.32       # Seitenführung: kleiner = ruhiger, größer = direkter (zu groß: Zittern)

# Antrieb
const GEARS := [3.35, 2.25, 1.65, 1.28, 1.02, 0.80]
const NGEARS := 6
const REVERSE := 3.3
const FINAL := 3.3
const IDLE_RPM := 850.0
const REDLINE := 6200.0
const SPEED_LIMIT := 95.0       # m/s
const DRAG_K := 0.40            # 0.5*rho*Cd*A  [N/(m/s)^2]
const ROLL_RES := 140.0         # N
# Reifen
const MU := 1.08
const KAPPA_PEAK := 0.12        # Längsschlupf bei maximaler Kraft
const ALPHA_PEAK := 0.15        # tan(Schlupfwinkel) bei maximaler Seitenkraft (~8.5°)
const I_WHEEL := 1.3            # kg m² (Rad + Bremse)
const I_ENG_REFL := 0.26        # kg m² Motor-Trägheit je Antriebsrad bei Übersetzung 1:1 (wird mit i² skaliert)
const BRAKE_FORCE := 15800.0    # N maximale Bremskraft gesamt (≈1.04 g)
const BRAKE_FRONT := 0.64

var wheels := {}                # "FL" -> {node, local, steer, drive, rear, ...}
var model: Node3D
var emit := {}
var paint_mat: StandardMaterial3D

var in_throttle := 0.0
var in_brake := 0.0
var in_steer := 0.0
var in_handbrake := false

var steer_angle := 0.0
var gear := 1                    # 0 = Rückwärts, 1..5 vorwärts
var rpm := IDLE_RPM
var speed := 0.0                 # m/s vorwärts (vorzeichenbehaftet)
var grip := 1.0                  # Haftungsfaktor (nass < 1), von main aus der Nässe gesetzt
var world_ref: Node = null       # World (Untergrund je Rad)
var offroad := 0.0               # Anteil der Räder abseits befestigter Flächen
var roughness := 0.0             # Unebenheit des Untergrunds (Kopfsteinpflaster 1.0)
var _surf_t := 0.0
var lights_on := false
var braking := false
var reversing := false
var grounded := 0
var horn_pressed := false
var slip := 0.0
var jitter := 0.0          # Messwert für Testzwecke: Ø Änderung der Quergeschwindigkeit je Physikschritt
var _prev_vlat := 0.0
var _jit_n := 0
var _jit_sum := 0.0
var override_input := false
var _slip_acc := 0.0
var _wheel_roll := {"FL": 0.0, "FR": 0.0, "RL": 0.0, "RR": 0.0}
var _comp := {"FL": 0.0, "FR": 0.0, "RL": 0.0, "RR": 0.0}
var _headlights: Array[SpotLight3D] = []
var _taxi_sign := true
var _shift_cd := 0.0
var manual := false
var _shift_req := 0
var _last_pos := Vector3.ZERO
var _stuck_t := 0.0
var abs_on := true
var abs_active := false
var esp_on := true
var esp_active := false
var tc_active := false
var _torque_cut := 0.0
var engine_health := 1.0
var tc_on := true
var steer_assist := 1.0         # Lenkhilfe (0 = aus, 1 = voll)
var damage: CarDamage
var damage_enabled := true
var _hits: Array = []
var _smoke: GPUParticles3D
var _last_reset_t := -10.0
static var debug := false
var dbg := ""
var _fsum := Vector3.ZERO
var _dbg_contacts := ""
var _prev_v := Vector3.ZERO
var _dbg := {}
var _kappa_rear := 0.0


func setup(paint: Color = Color(0.93, 0.89, 0.74)) -> void:
	mass = 1550.0
	can_sleep = false
	collision_layer = 2
	collision_mask = 1 | 4
	continuous_cd = true
	linear_damp_mode = RigidBody3D.DAMP_MODE_REPLACE
	angular_damp_mode = RigidBody3D.DAMP_MODE_REPLACE
	linear_damp = 0.0
	angular_damp = 0.5
	center_of_mass_mode = RigidBody3D.CENTER_OF_MASS_MODE_CUSTOM
	center_of_mass = Vector3(0, 0.52, -0.10)
	inertia = Vector3(750, 2700, 2900)

	var cs1 := CollisionShape3D.new()
	var b1 := BoxShape3D.new()
	b1.size = Vector3(1.8, 0.62, 4.55)
	cs1.shape = b1
	cs1.position = Vector3(0, 0.62, 0)
	add_child(cs1)
	var cs2 := CollisionShape3D.new()
	var b2 := BoxShape3D.new()
	b2.size = Vector3(1.55, 0.52, 2.2)
	cs2.shape = b2
	cs2.position = Vector3(0, 1.18, 0.15)
	add_child(cs2)

	var made := CarModel.make("taxi_player.glb", paint, true)
	model = made["root"]
	emit = made["emit"]
	paint_mat = made["paint"]
	add_child(model)
	for k in ["FL", "FR", "RL", "RR"]:
		var w: Node3D = made["wheels"].get(k)
		if w == null:
			continue
		wheels[k] = {
			"node": w,
			"local": Vector3(w.position.x, HUB_REST, w.position.z),
			"steer": k.begins_with("F"),
			"rear": k.begins_with("R"),
			"left": k.ends_with("L"),
			"contact": false,
			"comp": 0.0,
			"omega": 0.0,
			"dmg_grip": 1.0,
		}
	paint_mat.vertex_color_use_as_albedo = true
	var wl := {}
	for k in wheels:
		wl[k] = wheels[k]["local"]
	damage = CarDamage.new()
	damage.setup(self, model, wl)
	contact_monitor = true
	max_contacts_reported = 8
	_make_smoke()
	for sx in [-0.62, 0.62]:
		var sl := SpotLight3D.new()
		sl.position = Vector3(sx, 0.72, -2.3)
		sl.spot_range = 60.0
		sl.spot_angle = 32.0
		sl.spot_angle_attenuation = 0.7
		sl.light_energy = 0.0
		sl.light_color = Color(1.0, 0.94, 0.82)
		sl.shadow_enabled = false
		sl.rotation_degrees = Vector3(-2.5, 0, 0)
		add_child(sl)
		_headlights.append(sl)


func _torque(r: float) -> float:
	if r < 1100.0:
		return lerpf(210.0, 390.0, clampf((r - 700.0) / 400.0, 0.0, 1.0))
	if r < 3600.0:
		return 415.0
	return lerpf(415.0, 300.0, clampf((r - 3600.0) / 2600.0, 0.0, 1.0))


static func _tire_curve(s: float) -> float:
	## Normierte Reifenkennlinie nach Pacejka (Spitze bei s = 1). Straßenreifen: nach der Spitze nur flacher
	## Abfall (s=2: 0.97, s=3: 0.94, Grenzwert 0.85) -> kein "Abreißen" in den Dauerdrift.
	var x := 2.86 * s
	return sin(1.35 * atan(x - 0.3 * (x - atan(x))))


func _integrate_forces(state: PhysicsDirectBodyState3D) -> void:
	# Einschläge einsammeln (Verformung passiert später im Render-Frame)
	var n := state.get_contact_count()
	if debug:
		var sumi := Vector3.ZERO
		for j in n:
			sumi += state.get_contact_impulse(j)
		_dbg_contacts = "contacts=%d imp=%.0f" % [n, sumi.length()]
	for i in n:
		var col := state.get_contact_collider_object(i)
		if col is AICar:
			_vehicle_contact(state, i, col, (col as AICar).mass_kg())
		elif col is StaticBody3D and (col as Node).has_meta("parked_owner"):
			_vehicle_contact(state, i, col, 1250.0)
	var dv_max := 0.0
	for i in n:
		dv_max = maxf(dv_max, state.get_contact_impulse(i).length() / mass)
	if dv_max > 0.8 and impact_events.size() < 8:
		impact_events.append(dv_max)
	if dv_max > 0.8:
		cam_kick = maxf(cam_kick, dv_max)
	for i in n:
		var imp := state.get_contact_impulse(i).length()
		var dv := imp / mass
		if dv < 2.4 or not damage_enabled:
			continue
		var cp: Vector3 = state.get_contact_local_position(i)
		var lp := global_transform.affine_inverse() * cp
		var com_l := center_of_mass
		var dir_in := (com_l - lp)
		dir_in.y *= 0.35
		if _hits.size() < 6:
			_hits.append({"pos": lp, "dir": dir_in, "sev": dv * 1.05})
		if dv >= 1.5:
			_crash_rumble = maxf(_crash_rumble, clampf(dv / 9.0, 0.25, 1.0))
	_v_before = state.linear_velocity


var _rumble_t := 0.0
var _crash_rumble := 0.0
var _rr_extra := 0.0
var impact_events: Array = []
var cam_kick := 0.0              # Stoßstärke für die Kamera (CamRig liest und setzt zurück)
var _v_before := Vector3.ZERO    # Geschwindigkeit vor dem letzten Physikschritt (Stoßberechnung)
var _veh_cd := {}


func _vehicle_contact(state: PhysicsDirectBodyState3D, i: int, col: Object, m2: float) -> void:
	## Stoß gegen ein kinematisches KI-Auto bzw. geparktes Auto: der Löser reagiert wie gegen eine Wand (unendliche
	## Masse) und meldet dafür keinen brauchbaren Impuls. Deshalb hier der Stoß entlang der Kontaktnormalen nach
	## Impulserhaltung (teilelastisch, e = 0,15) aus den Geschwindigkeiten VOR dem Kontakt; das andere Fahrzeug
	## bekommt seinen Anteil und wird zum Physikkörper.
	var key := col.get_instance_id()
	var now := Time.get_ticks_msec()
	if _veh_cd.get(key, 0) > now:
		return
	var cp := state.get_contact_collider_position(i)
	var other_pos: Vector3
	var other_v := Vector3.ZERO
	var shape_node: Node = null
	if col is AICar:
		other_pos = (col as AICar).world_pos()
		other_v = (col as AICar).velocity()
	else:
		var body := col as CollisionObject3D
		var sidx := state.get_contact_collider_shape(i)
		var owner_id := body.shape_find_owner(sidx)
		shape_node = body.shape_owner_get_owner(owner_id) as Node
		other_pos = (shape_node as Node3D).global_position if shape_node is Node3D else body.global_position
	var n := global_position - other_pos
	n.y = 0.0
	if n.length() < 0.01:
		return
	n = n.normalized()                               # vom anderen Fahrzeug zu mir
	var v1 := _v_before
	var v1n := v1.dot(n)
	var v2n := other_v.dot(n)
	var closing := v2n - v1n                         # > 0: wir nähern uns
	if closing < 0.8:
		return
	_veh_cd[key] = now + 400
	var m1 := mass
	var e := 0.15
	var v1n_new := (m1 * v1n + m2 * v2n + m2 * e * (v2n - v1n)) / (m1 + m2)
	var v2n_new := (m1 * v1n + m2 * v2n + m1 * e * (v1n - v2n)) / (m1 + m2)
	var lv := state.linear_velocity
	if OS.has_environment("DRESDEN_TRACE"):
		print("STOSS mit %s closing %.1f v1n %.1f v2n %.1f -> %.1f / %.1f, lv %s" % [col.get_class(), closing, v1n, v2n, v1n_new, v2n_new, str(lv)])
	# Normalanteil des Spielers auf das Stoßergebnis setzen (Tangential- und Vertikalanteil bleiben)
	state.linear_velocity = lv + n * (v1n_new - lv.dot(n))
	var dv_other := n * (v2n_new - v2n)
	var r := cp - other_pos
	var Iy := m2 * (4.5 * 4.5 + 1.8 * 1.8) / 12.0
	var w_y := r.cross(dv_other * m2).y / Iy
	if impact_events.size() < 8:
		impact_events.append(closing)
	cam_kick = maxf(cam_kick, closing)
	if col is AICar:
		(col as AICar).player_impact(dv_other, w_y)
	elif shape_node != null:
		var owner_obj: Object = (col as Node).get_meta("parked_owner")
		if owner_obj != null and owner_obj.has_method("knock"):
			owner_obj.call_deferred("knock", shape_node, other_v + dv_other, w_y)


func _process(delta: float) -> void:
	_update_rumble(delta)
	if damage == null:
		return
	if not _hits.is_empty():
		var h: Dictionary = _hits.pop_front()
		# nahe, gleichzeitige Treffer zusammenfassen
		for o in _hits.duplicate():
			if (o["pos"] as Vector3).distance_to(h["pos"]) < 0.8:
				h["sev"] = maxf(h["sev"], o["sev"])
				_hits.erase(o)
		damage.impact(h["pos"], h["dir"], h["sev"])
		_apply_damage_effects()


func _update_rumble(delta: float) -> void:
	## Vibration (Steam Controller: Haptik): Reifenschlupf/ABS schwach, Zusammenstoß stark.
	_rumble_t -= delta
	if _rumble_t > 0.0:
		return
	_rumble_t = 0.08
	if get_tree().paused or Input.get_connected_joypads().is_empty():
		return
	var weak := clampf((slip - 1.5) / 6.0, 0.0, 0.6)
	if abs_active:
		weak = maxf(weak, 0.35)
	if grounded < 4 and grounded > 0:
		weak = maxf(weak, 0.15)
	if roughness > 0.0:
		weak = maxf(weak, roughness * clampf(absf(speed) / 12.0, 0.0, 1.0) * 0.3)
	var strong := _crash_rumble
	_crash_rumble = maxf(_crash_rumble - 0.35, 0.0)
	if weak > 0.02 or strong > 0.02:
		Controls.vibrate(weak, strong, 0.12)


func _apply_damage_effects() -> void:
	engine_health = clampf(1.0 - 0.7 * damage.front - 0.1 * damage.total, 0.2, 1.0)
	for k in wheels:
		var w: Dictionary = wheels[k]
		w["dmg_grip"] = 1.0 - 0.3 * float(damage.wheel_dmg[k])
		w["broken"] = bool(damage.wheel_lost[k])
		(w["node"] as Node3D).visible = not w["broken"]
	if _smoke:
		_smoke.emitting = damage.front > 0.4
		_smoke.amount = 14 + int(damage.front * 40.0)


func _make_smoke() -> void:
	_smoke = GPUParticles3D.new()
	_smoke.position = Vector3(0, 0.95, -1.5)
	_smoke.amount = 20
	_smoke.lifetime = 1.8
	_smoke.emitting = false
	_smoke.local_coords = false
	_smoke.visibility_aabb = AABB(Vector3(-5, -2, -5), Vector3(10, 8, 10))
	var pm := ParticleProcessMaterial.new()
	pm.direction = Vector3(0, 1, 0)
	pm.spread = 25.0
	pm.initial_velocity_min = 1.2
	pm.initial_velocity_max = 2.4
	pm.gravity = Vector3(0, 0.3, 0)
	pm.scale_min = 0.5
	pm.scale_max = 1.4
	var curve := Curve.new()
	curve.add_point(Vector2(0, 0.3))
	curve.add_point(Vector2(1, 2.2))
	var ct := CurveTexture.new()
	ct.curve = curve
	pm.scale_curve = ct
	_smoke.process_material = pm
	var q := QuadMesh.new()
	q.size = Vector2(1.0, 1.0)
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	m.albedo_color = Color(0.12, 0.12, 0.13, 0.55)
	m.albedo_texture = Boats._puff_tex()
	q.material = m
	_smoke.draw_pass_1 = q
	add_child(_smoke)


func repair() -> void:
	if damage:
		damage.repair()
		_apply_damage_effects()
		engine_health = 1.0


func _read_input(delta: float) -> void:
	if override_input:
		return
	var st := Input.get_axis("steer_left", "steer_right")
	var digital := absf(st) > 0.98 or st == 0.0
	if not digital:
		# Gamepad: feinfühlig um die Mitte, voller Einschlag außen (wie Forza/GTA)
		st = signf(st) * pow(absf(st), 1.45)
	in_steer = move_toward(in_steer, st, (4.2 if digital else 14.0) * delta)
	in_throttle = move_toward(in_throttle, Input.get_action_strength("throttle"), 7.0 * delta)
	in_brake = move_toward(in_brake, Input.get_action_strength("brake"), 9.0 * delta)
	in_handbrake = Input.is_action_pressed("handbrake")
	horn_pressed = Input.is_action_pressed("horn")
	if Input.is_action_just_pressed("gear_up"):
		_shift_req = 1
	if Input.is_action_just_pressed("gear_down"):
		_shift_req = -1
	if Input.is_action_just_pressed("toggle_manual"):
		manual = not manual


func _physics_process(delta: float) -> void:
	_read_input(delta)
	_slip_acc = 0.0
	var space := get_world_3d().direct_space_state
	var up_body := global_transform.basis.y
	var fwd_body := -global_transform.basis.z
	var com_world := global_transform * center_of_mass
	var v_cm := linear_velocity
	speed = v_cm.dot(fwd_body)
	var spd_abs := absf(speed)

	# Eingaben -> Motor/Bremse
	var throttle := in_throttle
	var brake := in_brake
	reversing = false
	if brake > 0.05 and throttle < 0.05 and speed < 1.2:
		reversing = true
		throttle = brake
		brake = 0.0
	elif throttle > 0.05 and brake < 0.05 and speed > -1.2 and gear == 0:
		gear = 1
	braking = brake > 0.05

	# Lenkwinkel (geschwindigkeitsabhängig, griplimitiert)
	var wb := 2.92
	var max_a := atan(10.0 * wb / maxf(spd_abs * spd_abs, 1.0)) * 2.3
	max_a = clampf(max_a, deg_to_rad(2.5), deg_to_rad(34.0))
	var target := -in_steer * max_a   # +Y-Drehung = nach links, daher Vorzeichen umkehren
	# Lenkhilfe (wie GTA/Rennspiele): Lenkwinkel so begrenzen, dass der Schräglauf vorn den Haftungsgipfel nicht
	# überschreitet. Das Fenster richtet sich nach der tatsächlichen Bewegungsrichtung der Vorderachse ->
	# bricht das Heck aus, wird automatisch gegengelenkt.
	if steer_assist > 0.0 and spd_abs > 4.0:
		var bx := global_transform.basis
		var vx_b := -linear_velocity.dot(bx.z)
		var vy_b := linear_velocity.dot(bx.x)
		var r_b := angular_velocity.dot(bx.y)
		var th_f := atan2(vy_b - r_b * A_AXLE, maxf(absf(vx_b), 1.0))
		var a_lim := atan(ALPHA_PEAK) * 1.08
		var lo := -a_lim - th_f
		var hi := a_lim - th_f
		var w_as := clampf((spd_abs - 4.0) / 5.0, 0.0, 1.0) * steer_assist
		target = lerpf(target, clampf(target, lo, hi), w_as)
	if damage:
		target += (float(damage.wheel_dmg["FL"]) - float(damage.wheel_dmg["FR"])) * 0.07 + (damage.left - damage.right) * 0.012
	var rate := 3.2 if absf(target) > absf(steer_angle) else 5.5
	steer_angle = move_toward(steer_angle, target, rate * delta * (0.35 + 0.65 * (1.0 - clampf(spd_abs / 40.0, 0.0, 0.8))))

	# --- Antriebsstrang -----------------------------------------------------
	if reversing:
		gear = 0
	var ratio: float = REVERSE if gear == 0 else GEARS[gear - 1]
	var om_rl: float = wheels["RL"]["omega"] if wheels.has("RL") else 0.0
	var om_rr: float = wheels["RR"]["omega"] if wheels.has("RR") else 0.0
	var w_rear := 0.5 * (absf(om_rl) + absf(om_rr))
	var rpm_w := w_rear * ratio * FINAL * 9.5493
	var launch := clampf(1.0 - spd_abs / 4.5, 0.0, 1.0)
	var free_rpm := lerpf(IDLE_RPM, IDLE_RPM + throttle * 3000.0, launch)
	rpm = lerpf(rpm, maxf(rpm_w, free_rpm), clampf(delta * 16.0, 0.0, 1.0))
	rpm = clampf(rpm, IDLE_RPM * 0.8, REDLINE + 200.0)
	_shift_cd -= delta
	_torque_cut = maxf(_torque_cut - delta, 0.0)
	if gear >= 1 and _shift_cd <= 0.0 and not manual:
		var up_rpm := lerpf(2900.0, 5700.0, pow(throttle, 0.7))
		var dn_rpm := 1250.0 + throttle * 1500.0
		if gear < NGEARS and rpm_w > up_rpm and rpm_w * GEARS[gear] / GEARS[gear - 1] > 1700.0:
			gear += 1
			_shift_cd = 0.4
			_torque_cut = 0.14
		elif gear > 1 and rpm_w < dn_rpm and rpm_w * GEARS[gear - 2] / GEARS[gear - 1] < 5600.0:
			gear -= 1
			_shift_cd = 0.3
			_torque_cut = 0.08
	if _shift_req != 0:
		if not manual:
			manual = true
		if not reversing and _shift_cd <= 0.0:
			if _shift_req > 0 and gear < NGEARS:
				gear = gear + 1 if gear > 0 else 1
				_shift_cd = 0.2
				_torque_cut = 0.12
			elif _shift_req < 0 and gear > 1:
				gear -= 1
				_shift_cd = 0.2
				_torque_cut = 0.1
		_shift_req = 0
	if manual and gear >= 1 and rpm_w < 700.0 and spd_abs < 2.5 and gear > 1:
		gear = 1
	var te := _torque(rpm) * 1.12 * throttle * engine_health
	if tc_on:
		te *= clampf(1.0 - maxf(_kappa_rear - 0.10, 0.0) * 8.0, 0.2, 1.0)
	if rpm > REDLINE or _torque_cut > 0.0 or spd_abs > SPEED_LIMIT:
		te = 0.0
	var eb := 0.0
	if throttle < 0.15 and launch < 0.6 and gear >= 1:
		eb = -(28.0 + 0.010 * rpm) * (1.0 - throttle / 0.15)
	var t_total := (te + eb) * ratio * FINAL * 0.9
	if reversing:
		t_total = -t_total * 0.7
		if speed < -9.0:
			t_total = 0.0

	# Bremsmomente
	var brk_front := 0.0
	var brk_rear := 0.0
	if braking:
		brk_front = in_brake * BRAKE_FORCE * BRAKE_FRONT * 0.5 * WHEEL_R
		brk_rear = in_brake * BRAKE_FORCE * (1.0 - BRAKE_FRONT) * 0.5 * WHEEL_R

	# Aero
	if spd_abs > 0.3:
		apply_central_force(-v_cm.normalized() * (DRAG_K * v_cm.length_squared() + ROLL_RES * minf(spd_abs, 1.0)))
	apply_central_force(-up_body * v_cm.length_squared() * 0.35)

	# --- Fahrwerk und Reifenkräfte --------------------------------------------
	grounded = 0
	abs_active = false
	tc_active = false
	var comps: Dictionary = {}
	var loads: Dictionary = {}
	for k in wheels:
		var w: Dictionary = wheels[k]
		var local: Vector3 = w["local"]
		var origin := global_transform * (local + Vector3(0, SUSP_REST, 0))
		var ray_len := SUSP_REST + SUSP_DROOP + WHEEL_R
		var q := PhysicsRayQueryParameters3D.create(origin, origin - up_body * ray_len, 1)
		q.exclude = [get_rid()]
		var hit := space.intersect_ray(q)
		var c := -SUSP_DROOP
		if hit:
			var dist := origin.distance_to(hit["position"])
			c = SUSP_REST - (dist - WHEEL_R)
			w["contact"] = true
			w["pos"] = hit["position"]
			w["normal"] = hit["normal"]
		else:
			w["contact"] = false
		comps[k] = c
		loads[k] = 0.0
	# Untergrund je Rad (alle 0,1 s): Reibwert und Rollwiderstand
	_surf_t -= delta
	if _surf_t <= 0.0 and world_ref != null:
		_surf_t = 0.1
		var off := 0.0
		var rr := 0.0
		var rough := 0.0
		for k in wheels:
			var w: Dictionary = wheels[k]
			var wp: Vector3 = w["pos"] if w["contact"] else global_transform * (w["local"] as Vector3)
			var sf: Vector3 = world_ref.surface_at(wp.x, wp.z)
			w["surf"] = sf.x
			rr += sf.y
			rough += sf.z
			if sf.x < 0.95:
				off += 1.0
		offroad = off / maxf(float(wheels.size()), 1.0)
		roughness = rough / maxf(float(wheels.size()), 1.0)
		_rr_extra = rr / maxf(float(wheels.size()), 1.0)
	if spd_abs > 0.4 and _rr_extra > 0.0:
		apply_central_force(-v_cm.normalized() * mass * 9.81 * _rr_extra * minf(spd_abs, 3.0) / 3.0)
	var arb_f: float = ARB_F * (comps.get("FL", 0.0) - comps.get("FR", 0.0))
	var arb_r: float = ARB_R * (comps.get("RL", 0.0) - comps.get("RR", 0.0))
	var omega_avg_rear := 0.5 * (om_rl + om_rr)
	var kappa_acc := 0.0
	var kappa_n := 0
	for k in wheels:
		var w: Dictionary = wheels[k]
		var c: float = comps[k]
		var prev: float = w["comp"]
		var c_vel := (c - prev) / delta
		w["comp"] = c
		_comp[k] = c
		var rear: bool = w["rear"]
		var om: float = w["omega"]
		if w.get("broken", false):
			w["contact"] = false
		var t_drive := 0.0
		if rear:
			var other: float = om_rr if k == "RL" else om_rl
			t_drive = t_total * 0.5 + clampf((other - om) * 40.0, -350.0, 350.0)
		var t_brk: float = brk_rear if rear else brk_front
		if in_handbrake and rear:
			t_brk = maxf(t_brk, 3600.0)
		var iw := I_WHEEL + (I_ENG_REFL * ratio * ratio * FINAL * FINAL * 0.5 if rear and gear >= 1 and absf(t_total) > 1.0 else 0.0)
		if not w["contact"]:
			var om_air := om + delta * t_drive / iw
			if t_brk > 0.0:
				var dec_a := delta * t_brk / iw
				om_air = 0.0 if absf(om_air) <= dec_a else om_air - signf(om_air) * dec_a
			w["omega"] = om_air * (1.0 - 0.2 * delta)
			_wheel_roll[k] = _wheel_roll[k] + w["omega"] * delta
			continue
		grounded += 1
		var n: Vector3 = w["normal"]
		var pos: Vector3 = w["pos"]
		var arb := 0.0
		if k.begins_with("F"):
			arb = arb_f if k.ends_with("L") else -arb_f
		else:
			arb = arb_r if k.ends_with("L") else -arb_r
		var bump := maxf(c - BUMP_START, 0.0)
		var damp := (DAMP_BUMP if c_vel > 0.0 else DAMP_REB) * c_vel
		var fs := maxf(SPRING_K * maxf(c + SPRING_PRE, 0.0) + 120000.0 * bump + 2.5e6 * bump * bump + damp + arb, 0.0)
		fs = minf(fs, 30000.0)
		loads[k] = fs
		var wv := v_cm + angular_velocity.cross(pos - com_world)
		var f_dir := fwd_body
		if w["steer"]:
			f_dir = f_dir.rotated(up_body, steer_angle)
		f_dir = (f_dir - n * f_dir.dot(n)).normalized()
		var s_dir := f_dir.cross(n).normalized()
		var vf := wv.dot(f_dir)
		var vs := wv.dot(s_dir)
		_slip_acc += absf(vs)
		# ABS: Bremsmoment zurücknehmen, wenn das Rad zu blockieren droht
		var kappa_pre := (om * WHEEL_R - vf) / maxf(absf(vf), 2.0)
		if abs_on and t_brk > 0.0 and not (in_handbrake and rear) and absf(vf) > 3.0 and kappa_pre < -0.17:
			t_brk *= 0.25
			abs_active = true
		# Schlupf
		var kappa := (om * WHEEL_R - vf) / maxf(absf(vf), 2.5)
		var alpha_raw := vs / maxf(absf(vf), 3.5)
		# Einlaufverhalten: Seitenkraft baut sich über ~RELAX_LEN Rollweg auf (glättet, verhindert Zittern)
		var a_prev: float = w.get("alpha_f", alpha_raw)
		var alpha := a_prev + (alpha_raw - a_prev) * clampf(absf(vf) * delta / RELAX_LEN + 0.12, 0.0, 1.0)
		w["alpha_f"] = alpha
		var sk := kappa / KAPPA_PEAK
		var sa := alpha / ALPHA_PEAK
		var sl := sqrt(sk * sk + sa * sa)
		var mu := MU * grip * float(w.get("surf", 1.0)) * float(w.get("dmg_grip", 1.0)) * clampf(1.0 - 0.000045 * (fs - 4200.0), 0.75, 1.15)
		var fmag := mu * fs * _tire_curve(sl)
		var fx := 0.0
		var fy := 0.0
		if sl > 0.0001:
			fx = fmag * sk / sl
			fy = -fmag * sa / sl * 0.96
		# kein Überschwingen bei kleinen Geschwindigkeiten (Impulsgrenze)
		var m4 := mass * 0.25
		fy = clampf(fy, -m4 * absf(vs) / delta * 0.8, m4 * absf(vs) / delta * 0.8)
		if fx * vf < 0.0:
			fx = clampf(fx, -m4 * absf(vf) / delta * 0.8, m4 * absf(vf) / delta * 0.8)
		# Haltekraft im Stand (Hang)
		if spd_abs < 0.9 and throttle < 0.03 and in_brake < 0.03:
			fx += clampf(-vf * m4 / delta * 0.5, -mu * fs * 0.9, mu * fs * 0.9)
		# Rad-Drehzahl integrieren
		# halb-implizit: Reifen-Längssteifigkeit dämpft die Raddrehzahl-Dynamik (verhindert Aufschwingen)
		var c_kappa := mu * fs * 2.85 / KAPPA_PEAK * WHEEL_R / maxf(absf(vf), 2.5)
		var om_new := om + delta * (t_drive - fx * WHEEL_R) / (iw + delta * c_kappa * WHEEL_R * WHEEL_R)
		if t_brk > 0.0:
			var dec := delta * t_brk / iw
			om_new = 0.0 if absf(om_new) <= dec else om_new - signf(om_new) * dec
		if in_handbrake and rear:
			om_new = 0.0
		var k_new := om_new * WHEEL_R - vf
		if t_brk <= 0.0 and k_new * (om * WHEEL_R - vf) < 0.0 and absf(t_drive) < 1.0:
			om_new = vf / WHEEL_R
		if rear:
			kappa_acc += maxf(kappa, absf(alpha) / ALPHA_PEAK * 0.12)
			kappa_n += 1
			if tc_on and kappa > 0.12 and t_drive > 50.0:
				tc_active = true
		w["omega"] = om_new
		w["kappa"] = kappa                 # für Reifenspuren/Qualm (SkidFX)
		if debug:
			_dbg[k] = "a=%.1f k=%.2f fz=%.0f fy=%.0f fx=%.0f" % [rad_to_deg(atan(alpha)), kappa, fs, fy, fx]
		var total := n * fs + f_dir * fx + s_dir * fy
		_fsum += total
		apply_force(total, pos - global_position)
		_wheel_roll[k] = _wheel_roll[k] + om_new * delta

	if debug:
		dbg = "FL[%s] FR[%s] RL[%s] RR[%s] esp=%s tc=%s" % [_dbg.get("FL", ""), _dbg.get("FR", ""), _dbg.get("RL", ""), _dbg.get("RR", ""), esp_active, tc_active]
	if debug:
		var a_meas := (linear_velocity - _prev_v) / delta
		dbg += " " + _dbg_contacts + " | a_meas=%.2f a_calc=%.2f fsumx=%.0f" % [a_meas.dot(fwd_body), (_fsum / mass + Vector3(0, -9.81, 0)).dot(fwd_body), _fsum.dot(fwd_body)]
		_prev_v = linear_velocity
	_fsum = Vector3.ZERO
	_kappa_rear = kappa_acc / maxf(kappa_n, 1)

	# Stabilitätskontrolle (leichter Eingriff gegen Schleudern)
	esp_active = false
	if esp_on and grounded >= 3 and spd_abs > 6.0 and not in_handbrake:
		# Soll-Gierrate: kinematisch, aber höchstens was die Reifen tragen (µ·g/v)
		var r_max := MU * grip * 9.81 * 0.9 / maxf(spd_abs, 1.0)
		var yaw_target := clampf(speed * tan(steer_angle) / 2.92, -r_max, r_max)
		var yaw_err := angular_velocity.y - yaw_target
		var bx2 := global_transform.basis
		var beta := atan2(linear_velocity.dot(bx2.x), maxf(absf(speed), 1.0))
		# Übersteuern = Gierrate größer als Soll in Drehrichtung oder wachsender Schwimmwinkel
		var over := absf(angular_velocity.y) > absf(yaw_target) + 0.05 and signf(angular_velocity.y) == signf(yaw_target)
		# Eingriff erst ab ~8° Schwimmwinkel: das Heck darf spürbar kommen (GTA-artig), Dreher werden verhindert
		var thr := 0.14 if over else 0.28
		var b_lim := deg_to_rad(8.0)
		if absf(yaw_err) > thr or absf(beta) > b_lim:
			var corr := (maxf(absf(yaw_err) - thr, 0.0)) * signf(yaw_err)
			corr += -signf(beta) * maxf(absf(beta) - b_lim, 0.0) * 1.6 * signf(speed)
			apply_torque(Vector3.UP * (-corr * 4600.0 * clampf(spd_abs / 15.0, 0.0, 1.0)))
			esp_active = true

	slip = _slip_acc / maxf(grounded, 1)
	var vlat_b := linear_velocity.dot(global_transform.basis.x)
	_jit_sum += absf(vlat_b - _prev_vlat)
	_jit_n += 1
	_prev_vlat = vlat_b
	jitter = _jit_sum / maxf(_jit_n, 1)

	# Aufstellhilfe in der Luft / gekippt
	if grounded == 0:
		apply_torque(-angular_velocity * 800.0)
	_update_visuals(delta)

	# Festgefahren/auf dem Dach: automatisch zurücksetzen nach einer Weile
	if up_body.y < 0.2 and linear_velocity.length() < 1.5:
		_stuck_t += delta
		if _stuck_t > 3.0:
			reset_upright()
	else:
		_stuck_t = 0.0


func _update_visuals(delta: float) -> void:
	for k in wheels:
		var w: Dictionary = wheels[k]
		var node: Node3D = w["node"]
		var c: float = _comp[k]
		node.position = Vector3(w["local"].x, HUB_REST + clampf(c, -SUSP_DROOP, 0.14), w["local"].z)
		var st := steer_angle if w["steer"] else 0.0
		node.transform.basis = Basis(Vector3.UP, st) * Basis(Vector3.RIGHT, -_wheel_roll[k])
	# Leuchten
	var head := (1.0 if lights_on else 0.0) * (1.0 - (damage.head_dmg if damage else 0.0))
	_set_emit("HeadlightEmit", head * 3.0)
	_set_emit("IndicatorEmit", 0.0)
	var tail := (0.8 if lights_on else 0.0)
	_set_emit("TaillightEmit", tail + (0.0 if not braking else 3.0) + (0.0))
	_set_emit("BrakeLightEmit", 4.0 if braking else tail * 0.5)
	_set_emit("TaxiSignEmit", (1.6 if lights_on else 0.35) * (1.0 if _taxi_sign else 0.0))
	for sl in _headlights:
		sl.light_energy = (6.0 if lights_on else 0.0) * (1.0 - (damage.head_dmg if damage else 0.0))


func _set_emit(nm: String, v: float) -> void:
	if emit.has(nm):
		(emit[nm] as StandardMaterial3D).emission_energy_multiplier = v


func reset_upright() -> void:
	var now := Time.get_ticks_msec() / 1000.0
	if now - _last_reset_t < 1.6:
		repair()
	_last_reset_t = now
	var p := global_position + Vector3(0, 1.2, 0)
	var yaw := global_transform.basis.get_euler().y
	linear_velocity = Vector3.ZERO
	angular_velocity = Vector3.ZERO
	global_transform = Transform3D(Basis(Vector3.UP, yaw), p)
	_stuck_t = 0.0


func get_speed_kmh() -> float:
	return linear_velocity.length() * 3.6
