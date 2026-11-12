class_name CamRig
extends Node3D
## Kamera: Verfolger (nah/fern), Motorhaube, Stoßstange; Rechter Stick = umschauen.

var cam: Camera3D
var target: PlayerCar
var mode := 0                      # 0 nah, 1 fern, 2 Cockpit, 3 Stoßstange
var cam_yaw := 0.0
var look_yaw := 0.0
var look_pitch := 0.0
var _mouse_t := 0.0             # Zeit seit der letzten Mausbewegung (Maus/Trackpad-Umsehen)
var shake := 0.0
var _pos := Vector3.ZERO
var _off := Vector3.ZERO           # geglätteter Versatz Kamera <- Auto (Feder im mitbewegten System)
var _started := false
var _fov := 50.0
var _v_prev := 0.0
var _acc_s := 0.0                  # geglättete Längsbeschleunigung
var _t := 0.0
var _noise := FastNoiseLite.new()
var shake_scale := 1.0             # Entwickler: 0 = Rütteln aus (DriveBench --noshake)
var last_shake := 0.0              # Messwerte für DriveBench
var last_hit := false

const MODE_NAMES := ["Verfolger", "Verfolger weit", "Cockpit", "Stoßstange"]


func setup(t: PlayerCar) -> void:
	target = t
	cam = Camera3D.new()
	cam.name = "Camera"
	cam.near = 0.08
	cam.far = 4000.0
	cam.fov = 50.0
	cam.physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_OFF
	add_child(cam)
	cam.make_current()
	_noise.seed = 77
	_noise.frequency = 1.0


func cycle_mode() -> void:
	mode = (mode + 1) % 4
	_started = false


func _process(delta: float) -> void:
	if target == null:
		return
	var xf := target.get_global_transform_interpolated()
	var fwd := -xf.basis.z
	var heading := atan2(-fwd.x, -fwd.z)
	var vel := target.linear_velocity
	var spd := vel.length()
	var vel_h := Vector2(vel.x, vel.z)
	var want_yaw := heading
	if spd > 5.0 and vel_h.length() > 3.0 and target.speed > 0.0:
		var vyaw := atan2(-vel.x, -vel.z)
		want_yaw = heading + clampf(wrapf(vyaw - heading, -PI, PI), -0.6, 0.6) * 0.55
	if not _started:
		cam_yaw = heading
	cam_yaw = lerp_angle(cam_yaw, want_yaw, 1.0 - exp(-4.2 * delta))

	# Rechter Stick / Maus-ähnliches Umschauen mit Rückkehr
	var lx := Input.get_axis("look_left", "look_right")
	var ly := Input.get_axis("look_down", "look_up")
	_mouse_t += delta
	if absf(lx) > 0.01 or absf(ly) > 0.01:
		look_yaw -= lx * 2.4 * delta
		look_pitch = clampf(look_pitch + ly * 1.6 * delta, -0.5, 0.7)
	elif _mouse_t < 1.2:
		pass                       # Maus/Trackpad: Blick kurz halten, dann zurück
	else:
		look_yaw = lerpf(look_yaw, 0.0, 1.0 - exp(-3.0 * delta))
		look_pitch = lerpf(look_pitch, 0.0, 1.0 - exp(-3.0 * delta))
	look_yaw = clampf(look_yaw, -PI, PI)
	var back := PI if Input.is_action_pressed("look_back") else 0.0

	# senkrechter Bildwinkel: 50° (≈ 80° waagrecht bei 16:9) wirkt wie mit dem Auge – mit 62° (94° waagrecht) wirkten
	# entfernte Gebäude deutlich zu weit weg (Hochhaus Pirnaischer Platz vom Postplatz aus). Beim Fahren bis +14°.
	var want_fov := 50.0 + clampf(spd * 0.16, 0.0, 14.0)
	_fov = lerpf(_fov, want_fov, 1.0 - exp(-3.0 * delta))
	# Längsbeschleunigung (für Kamera-Trägheit) und Rütteln (Pflaster, hohe Geschwindigkeit)
	_t += delta
	var a_long := (target.speed - _v_prev) / maxf(delta, 0.001)
	_v_prev = target.speed
	_acc_s = lerpf(_acc_s, clampf(a_long, -12.0, 12.0), 1.0 - exp(-4.0 * delta))
	if target.cam_kick > 0.0:
		shake = maxf(shake, clampf(target.cam_kick * 0.006, 0.0, 0.06))
		target.cam_kick = 0.0
	# Nur Aufprall-Stöße rütteln die Kamera (kurz, abklingend, ~10 Hz). Kein Dauerrütteln bei Fahrt: das wirkte
	# als Bildvibrieren (gemessen: 70× mehr Winkelzittern als die Fahrt selbst).
	var shake_amp := shake
	shake = maxf(shake - delta * 2.0, 0.0)
	shake_amp *= shake_scale
	last_shake = shake_amp

	match mode:
		0, 1:
			# GTA-artige Verfolgerkamera: Abstand federt mit (Beschleunigen = Kamera bleibt zurück, Bremsen = sie
			# holt auf), bei Tempo etwas weiter weg und tiefer; geglättet wird der Versatz im mitbewegten System,
			# damit die Kamera bei konstanter Fahrt nicht geschwindigkeitsabhängig nachhinkt.
			var dist := (7.6 if mode == 0 else 11.0) + clampf(spd * 0.022, 0.0, 1.1) + clampf(_acc_s * 0.07, -0.45, 0.55)
			var height := (2.1 if mode == 0 else 3.2) - clampf(spd * 0.005, 0.0, 0.22)
			var yaw := cam_yaw + look_yaw + back
			var dir := Vector3(-sin(yaw), 0, -cos(yaw))
			var anchor := xf.origin + Vector3(0, 1.25, 0)
			var want_off := -dir * dist + Vector3(0, height - 1.25 + look_pitch * 3.0, 0)
			if not _started:
				_off = want_off
				_started = true
			_off = _off.lerp(want_off, 1.0 - exp(-7.0 * delta))
			var desired := anchor + _off
			# Kollisionsprüfung zur Kamera
			var space := get_world_3d().direct_space_state
			var q := PhysicsRayQueryParameters3D.create(anchor, desired, 1)
			var hit := space.intersect_ray(q)
			last_hit = not hit.is_empty()
			if hit:
				desired = hit["position"] + (anchor - desired).normalized() * 0.35
			_pos = desired
			cam.global_position = _pos
			var look_at := xf.origin + Vector3(0, 1.05, 0) + dir * 3.5
			cam.look_at(look_at, Vector3.UP)
			if shake_amp > 0.0001:
				var nx := _noise.get_noise_2d(_t * 10.0, 0.0)
				var ny := _noise.get_noise_2d(0.0, _t * 12.0 + 50.0)
				cam.rotate_object_local(Vector3.RIGHT, nx * shake_amp * 2.2)
				cam.rotate_object_local(Vector3.UP, ny * shake_amp * 1.4)
		2:
			var head := xf * Vector3(-0.36, 1.2, -0.15)
			cam.global_position = head
			var yaw_off := look_yaw + back
			var b := xf.basis * Basis(Vector3.UP, yaw_off) * Basis(Vector3.RIGHT, look_pitch)
			cam.global_transform.basis = b
			cam.near = 0.04
		3:
			var bp := xf * Vector3(0, 0.62, -2.5)
			cam.global_position = bp
			cam.global_transform.basis = xf.basis * Basis(Vector3.UP, look_yaw + back)
	if mode != 2:
		cam.near = 0.1
	cam.fov = _fov if mode != 2 else 62.0
	_started = true


func _unhandled_input(event: InputEvent) -> void:
	# Maus bzw. rechtes Trackpad des Steam Controllers (Desktop-Modus): umsehen
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED and not get_tree().paused:
		var rel: Vector2 = (event as InputEventMouseMotion).relative
		look_yaw = clampf(look_yaw - rel.x * 0.004, -PI, PI)
		look_pitch = clampf(look_pitch - rel.y * 0.003, -0.5, 0.7)
		_mouse_t = 0.0
