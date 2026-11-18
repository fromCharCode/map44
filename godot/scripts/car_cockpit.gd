class_name CarCockpit
extends Node3D
## Cockpit des Spielerautos (Fahrerperspektive): lädt assets/models/cars/interior/<auto>_cockpit.glb
## (gebaut von tools/blender/interior_build.py), dreht das Lenkrad mit dem Lenkwinkel und zeichnet die Anzeigen
## (Kombiinstrument, Mittelbildschirm, Taxameter) in kleine SubViewports, die als Textur auf den Bildschirmflächen
## liegen. Sichtbar nur in der Cockpit-Kamera (CamRig schaltet um); dann wird der einfache Innenraum des
## Karosseriemodells ausgeblendet.

const DIR := "res://assets/models/cars/interior/"
const LIGHT_LAYER := 1 << 10         # eigene Lichtebene: das Innenlicht beleuchtet nur das Cockpit
const CLUSTER_SIZE := Vector2i(1024, 356)
const CENTER_SIZE := Vector2i(880, 360)
const METER_SIZE := Vector2i(512, 100)

var car: PlayerCar
var eye := Vector3(-0.37, 1.23, -0.12)      # Augpunkt des Fahrers (Fahrzeugkoordinaten)
var active := false
var wheel: Node3D
var _wheel_base := Transform3D.IDENTITY
var _wheel_ang := 0.0
var _old_interior: Node3D
var _light: OmniLight3D
var _vps: Array[SubViewport] = []
var _panels: Array[Control] = []
var _screen_mats: Array[StandardMaterial3D] = []
var _ambient_mat: StandardMaterial3D
var _slow_t := 0.0
var _main: Node


## Baut das Cockpit zu einem Karosseriemodell; null, wenn es dafür keines gibt (dann bleibt alles wie bisher).
static func create(p_car: PlayerCar, model_file: String, model_root: Node3D) -> CarCockpit:
	# Dateiname folgt dem Karosseriemodell (<modell>_cockpit.glb), sonst Rückfall auf taxi_cockpit.glb
	var base := model_file.get_basename()
	if not ResourceLoader.exists(DIR + base + "_cockpit.glb"):
		base = "taxi"
	var path := DIR + base + "_cockpit.glb"
	if not ResourceLoader.exists(path):
		return null
	var ps := load(path) as PackedScene
	if ps == null:
		return null
	var ck := CarCockpit.new()
	ck.name = "Cockpit"
	ck.car = p_car
	ck._old_interior = model_root.find_child("Interior", true, false) as Node3D
	ck._build(ps, DIR + base + "_cockpit.json")
	return ck


func _build(ps: PackedScene, info_path: String) -> void:
	var root := ps.instantiate() as Node3D
	add_child(root)
	if FileAccess.file_exists(info_path):
		var info: Variant = JSON.parse_string(FileAccess.get_file_as_string(info_path))
		if info is Dictionary and (info as Dictionary).has("eye"):
			var e: Array = info["eye"]
			eye = Vector3(float(e[0]), float(e[1]), float(e[2]))
	wheel = root.find_child("SteeringWheel", true, false) as Node3D
	if wheel:
		_wheel_base = wheel.transform
	# Anzeigen
	var screens := {
		"ScreenCluster": _make_screen(CLUSTER_SIZE, ClusterPanel.new()),
		"ScreenCenter": _make_screen(CENTER_SIZE, CenterPanel.new()),
		"ScreenMeter": _make_screen(METER_SIZE, MeterPanel.new()),
	}
	var grain := _grain(0.9, 5)
	var weave := _grain(2.2, 9)
	var stack: Array = [root]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		for c in n.get_children():
			stack.append(c)
		var mi := n as MeshInstance3D
		if mi == null:
			continue
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mi.layers = 1 | LIGHT_LAYER
		mi.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
		mi.extra_cull_margin = 2.0
		for i in mi.mesh.get_surface_count():
			var m := mi.mesh.surface_get_material(i) as StandardMaterial3D
			if m == null:
				continue
			var nm := String(m.resource_name)
			if screens.has(nm):
				mi.set_surface_override_material(i, screens[nm])
				continue
			match nm:
				"DashSoft", "DashLower", "SeatLeather", "WheelLeather", "DoorInsert":
					_set_grain(m, grain, 26.0, 0.45)
				"Headliner", "Carpet", "SeatInsert":
					_set_grain(m, weave, 60.0, 0.7)
				"MirrorGlass":
					m.metallic = 1.0
					m.roughness = 0.04
				"TrimAlu":
					m.anisotropy_enabled = true
					m.anisotropy = 0.6
				"AmbientLight":
					m.emission_enabled = true
					m.emission = Color(0.25, 0.65, 1.0)
					m.emission_energy_multiplier = 0.0
					_ambient_mat = m
	# schwaches Innenlicht (Streulicht am Tag, Ambientebeleuchtung bei Nacht) – nur auf der Cockpit-Ebene
	_light = OmniLight3D.new()
	_light.position = Vector3(0.0, 1.22, 0.25)
	_light.omni_range = 2.6
	_light.omni_attenuation = 0.7
	_light.light_energy = 0.5
	_light.light_specular = 0.15
	_light.shadow_enabled = false
	_light.light_cull_mask = LIGHT_LAYER
	add_child(_light)
	visible = false
	set_process(false)
	set_physics_process(false)


func _make_screen(size: Vector2i, panel: Control) -> StandardMaterial3D:
	var vp := SubViewport.new()
	vp.size = size
	vp.disable_3d = true
	vp.transparent_bg = false
	vp.gui_disable_input = true
	vp.msaa_2d = Viewport.MSAA_4X
	vp.render_target_update_mode = SubViewport.UPDATE_DISABLED
	add_child(vp)
	panel.set("ck", self)
	panel.size = Vector2(size)
	vp.add_child(panel)
	_vps.append(vp)
	_panels.append(panel)
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_texture = vp.get_texture()
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR
	_screen_mats.append(m)
	return m


static func _grain(freq: float, seed_v: int) -> NoiseTexture2D:
	var nz := FastNoiseLite.new()
	nz.noise_type = FastNoiseLite.TYPE_CELLULAR if freq < 1.5 else FastNoiseLite.TYPE_SIMPLEX
	nz.frequency = 0.09 * freq
	nz.seed = seed_v
	var t := NoiseTexture2D.new()
	t.width = 256
	t.height = 256
	t.seamless = true
	t.as_normal_map = true
	t.bump_strength = 5.0
	t.generate_mipmaps = true
	t.noise = nz
	return t


static func _set_grain(m: StandardMaterial3D, tex: Texture2D, scale: float, strength: float) -> void:
	m.normal_enabled = true
	m.normal_texture = tex
	m.normal_scale = strength
	m.uv1_triplanar = true
	m.uv1_scale = Vector3(scale, scale, scale)


## Von CamRig: Cockpit ein-/ausblenden (nur in der Fahrerperspektive sichtbar).
func set_active(on: bool) -> void:
	if on == active:
		return
	active = on
	visible = on
	set_process(on)
	set_physics_process(on)
	if _old_interior:
		_old_interior.visible = not on
	for vp in _vps:
		vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS if on else SubViewport.UPDATE_DISABLED


func _process(delta: float) -> void:
	if car == null:
		return
	if _main == null:
		_main = car.get_parent()
	var night := night_value()
	# Anzeigen dimmen bei Nacht, Innenlicht: tags Streulicht, nachts gedämpfte Ambientebeleuchtung
	var bright := lerpf(1.0, 0.62, night)
	for m in _screen_mats:
		m.albedo_color = Color(bright, bright, bright)
	_light.light_energy = lerpf(0.38, 0.07, night)
	_light.light_color = Color(1.0, 0.97, 0.92).lerp(Color(0.6, 0.8, 1.0), night)
	if _ambient_mat:
		_ambient_mat.emission_energy_multiplier = lerpf(0.0, 2.4, night)
	_panels[0].queue_redraw()
	_slow_t -= delta
	if _slow_t <= 0.0:
		_slow_t = 0.2
		_panels[1].queue_redraw()
		_panels[2].queue_redraw()


func _physics_process(delta: float) -> void:
	# Lenkrad folgt dem Radlenkwinkel über die Lenkübersetzung (im Physiktakt, damit die Interpolation es glättet)
	if wheel and car:
		var want := car.steer_angle * PlayerCar.STEER_RATIO
		_wheel_ang = lerpf(_wheel_ang, want, 1.0 - exp(-22.0 * delta))
		wheel.transform = _wheel_base * Transform3D(Basis(Vector3.UP, _wheel_ang), Vector3.ZERO)


func night_value() -> float:
	var env: Variant = _main.get("env_mgr") if _main else null
	return clampf(float(env.night_value), 0.0, 1.0) if env is EnvManager else 0.0


func clock_text() -> String:
	var env: Variant = _main.get("env_mgr") if _main else null
	var h := 12.0
	if env is EnvManager:
		h = (env as EnvManager).hours
	return "%02d:%02d" % [int(h) % 24, int((h - floorf(h)) * 60.0)]


func taxi_game() -> TaxiGame:
	var t: Variant = _main.get("taxi") if _main else null
	return t as TaxiGame if t is TaxiGame else null


func street() -> String:
	var h: Variant = _main.get("hud") if _main else null
	return String((h as Hud).street_name) if h is Hud else ""


# ------------------------------------------------------------------------------------------------------
# Anzeigen (2D, in SubViewports gezeichnet)
# ------------------------------------------------------------------------------------------------------
class Panel2D extends Control:
	var ck: CarCockpit
	var font: Font = ThemeDB.fallback_font

	func text(s: String, pos: Vector2, px: int, col: Color, align := 0) -> void:
		## align: 0 mittig, -1 linksbündig, 1 rechtsbündig (pos = Grundlinie)
		var w := font.get_string_size(s, HORIZONTAL_ALIGNMENT_LEFT, -1, px).x
		var p := pos - Vector2(w * 0.5 if align == 0 else (w if align == 1 else 0.0), 0.0)
		draw_string(font, p, s, HORIZONTAL_ALIGNMENT_LEFT, -1, px, col)

	func bold(s: String, pos: Vector2, px: int, col: Color, align := 0) -> void:
		text(s, pos + Vector2(0.7, 0.0), px, col, align)
		text(s, pos, px, col, align)


class ClusterPanel extends Panel2D:
	const A0 := deg_to_rad(140.0)
	const A1 := deg_to_rad(400.0)
	const ACCENT := Color(0.45, 0.78, 1.0)
	var _spd := 0.0
	var _rpm := 800.0
	var _blink := 0.0

	func _dial(c: Vector2, r: float, frac: float, n_major: int, minor: int, labels: Array, red_from: float) -> void:
		draw_circle(c, r + 10.0, Color(0.035, 0.04, 0.05))
		draw_arc(c, r + 10.0, 0.0, TAU, 96, Color(0.22, 0.24, 0.28), 2.5, true)
		draw_arc(c, r, A0, A1, 96, Color(0.55, 0.6, 0.66, 0.55), 2.0, true)
		if red_from < 1.0:
			draw_arc(c, r - 4.0, lerpf(A0, A1, red_from), A1, 24, Color(0.95, 0.18, 0.12), 7.0, true)
		var total := n_major * minor
		for i in total + 1:
			var a := lerpf(A0, A1, float(i) / float(total))
			var d := Vector2(cos(a), sin(a))
			var major := i % minor == 0
			draw_line(c + d * (r - (16.0 if major else 8.0)), c + d * r, Color(0.92, 0.94, 0.96, 1.0 if major else 0.55), 3.0 if major else 1.5, true)
			if major and (i / minor) < labels.size() and String(labels[i / minor]) != "":
				text(String(labels[i / minor]), c + d * (r - 36.0) + Vector2(0, 8), 21, Color(0.9, 0.92, 0.95))
		# aktiver Bogen und Zeiger
		draw_arc(c, r + 5.0, A0, lerpf(A0, A1, frac), 64, ACCENT, 4.0, true)
		var an := lerpf(A0, A1, frac)
		var dn := Vector2(cos(an), sin(an))
		var nn := Vector2(-dn.y, dn.x)
		draw_colored_polygon(PackedVector2Array([c + dn * (r - 6.0), c + nn * 5.0 - dn * 22.0, c - nn * 5.0 - dn * 22.0]), Color(1.0, 0.36, 0.2))
		draw_circle(c, 15.0, Color(0.1, 0.11, 0.13))
		draw_arc(c, 15.0, 0.0, TAU, 32, Color(0.4, 0.42, 0.46), 2.0, true)

	func _draw() -> void:
		var car := ck.car
		var w := size.x
		var h := size.y
		draw_rect(Rect2(Vector2.ZERO, size), Color(0.012, 0.014, 0.018))
		var dt := get_process_delta_time()
		_blink = fmod(_blink + dt, 1.0)
		_spd = lerpf(_spd, car.get_speed_kmh(), 1.0 - exp(-14.0 * dt))
		_rpm = lerpf(_rpm, car.rpm, 1.0 - exp(-16.0 * dt))
		var r := h * 0.40
		var cl := Vector2(h * 0.56, h * 0.53)
		var cr := Vector2(w - h * 0.56, h * 0.53)
		var sp_labels := []
		for i in 14:
			sp_labels.append(str(i * 20) if i % 2 == 0 else "")
		_dial(cl, r, clampf(_spd / 260.0, 0.0, 1.0), 13, 2, sp_labels, 2.0)
		text("km/h", cl + Vector2(0, r * 0.52), 19, Color(0.7, 0.74, 0.8))
		_dial(cr, r, clampf(_rpm / 7000.0, 0.0, 1.0), 7, 5, ["0", "1", "2", "3", "4", "5", "6", "7"], PlayerCar.REDLINE / 7000.0)
		text("×1000/min", cr + Vector2(0, r * 0.52), 17, Color(0.7, 0.74, 0.8))
		# Tempomat-Marke am Tacho
		if car.cruise_on:
			var ca := lerpf(A0, A1, clampf(car.cruise_target * 3.6 / 260.0, 0.0, 1.0))
			var cd := Vector2(cos(ca), sin(ca))
			draw_line(cl + cd * (r - 4.0), cl + cd * (r + 14.0), Color(0.3, 1.0, 0.45), 5.0, true)
		# Mitte: Geschwindigkeit digital, Gang, Tempomat
		var cx := w * 0.5
		bold(str(int(round(car.get_speed_kmh()))), Vector2(cx, h * 0.50), 96, Color.WHITE)
		text("km/h", Vector2(cx, h * 0.60), 20, Color(0.7, 0.74, 0.8))
		var g := "D"
		var sub := str(car.gear)
		if car.gear == 0 or car.reversing:
			g = "R"
			sub = ""
		elif absf(car.speed) < 0.3 and car.in_throttle < 0.05 and car.in_brake < 0.05:
			g = "P"
			sub = ""
		elif car.manual:
			g = "M"
		var gy := h * 0.80
		for i in 4:
			var nm: String = ["P", "R", "N", "D"][i]
			var on: bool = nm == g or (nm == "D" and g == "M")
			text("M" if (nm == "D" and g == "M") else nm, Vector2(cx - 66.0 + 36.0 * i, gy), 30, Color.WHITE if on else Color(0.35, 0.37, 0.4))
		if sub != "":
			text(sub, Vector2(cx + 78.0, gy), 30, ACCENT)
		if car.cruise_on:
			bold("TEMPOMAT %d" % int(round(car.cruise_target * 3.6)), Vector2(cx, h * 0.17), 24, Color(0.3, 1.0, 0.45))
		else:
			text(ck.clock_text(), Vector2(cx, h * 0.17), 24, Color(0.8, 0.83, 0.88))
		# Tank
		var ff := clampf(car.fuel_l / PlayerCar.FUEL_CAP, 0.0, 1.0)
		var bx := cx - 90.0
		var by := h * 0.90
		draw_rect(Rect2(bx, by, 180.0, 10.0), Color(0.2, 0.22, 0.25))
		draw_rect(Rect2(bx, by, 180.0 * ff, 10.0), Color(1.0, 0.3, 0.2) if ff < 0.12 else Color(0.85, 0.88, 0.92))
		for i in 5:
			draw_line(Vector2(bx + 45.0 * i, by - 3.0), Vector2(bx + 45.0 * i, by + 13.0), Color(0.012, 0.014, 0.018), 2.0)
		text("0", Vector2(bx - 14.0, by + 11.0), 16, Color(0.7, 0.74, 0.8))
		text("1/1", Vector2(bx + 200.0, by + 11.0), 16, Color(0.7, 0.74, 0.8))
		text("%d l" % int(round(car.fuel_l)), Vector2(cx, by - 8.0), 17, Color(1.0, 0.45, 0.3) if ff < 0.12 else Color(0.7, 0.74, 0.8))
		# Kontrollleuchten oben
		var lamps := [
			["LICHT", car.lights_on, Color(0.3, 1.0, 0.45)],
			["ABS", car.abs_active, Color(1.0, 0.75, 0.1)],
			["ESP", (car.esp_active or car.tc_active) and _blink < 0.5, Color(1.0, 0.75, 0.1)],
			["(P)", car.in_handbrake, Color(1.0, 0.25, 0.2)],
			["TANK", ff < 0.12, Color(1.0, 0.75, 0.1)],
			["MOTOR", car.engine_health < 0.75, Color(1.0, 0.75, 0.1)],
		]
		var lx := cx - 150.0
		for l in lamps:
			text(String(l[0]), Vector2(lx, h * 0.07 + 10.0), 17, (l[2] as Color) if bool(l[1]) else Color(0.16, 0.17, 0.19))
			lx += 60.0


class CenterPanel extends Panel2D:
	func _draw() -> void:
		var car := ck.car
		var w := size.x
		var h := size.y
		draw_rect(Rect2(Vector2.ZERO, size), Color(0.02, 0.025, 0.035))
		draw_rect(Rect2(0, 0, w, 54.0), Color(0.05, 0.06, 0.08))
		text(ck.clock_text(), Vector2(w - 24.0, 39.0), 32, Color(0.92, 0.94, 0.97), 1)
		text("NAVIGATION", Vector2(24.0, 37.0), 24, Color(0.45, 0.78, 1.0), -1)
		var taxi := ck.taxi_game()
		var tg := taxi.target() if taxi and taxi.enabled else Vector3.ZERO
		var c := Vector2(150.0, h * 0.60)
		draw_circle(c, 96.0, Color(0.05, 0.065, 0.09))
		draw_arc(c, 96.0, 0.0, TAU, 64, Color(0.2, 0.26, 0.34), 3.0, true)
		var fwd := -car.global_transform.basis.z
		if tg != Vector3.ZERO:
			var to := tg - car.global_position
			var dist := Vector2(to.x, to.z).length()
			var ang := atan2(fwd.x * to.z - fwd.z * to.x, fwd.x * to.x + fwd.z * to.z)   # + = Ziel rechts
			var d := Vector2(sin(ang), -cos(ang))
			var n := Vector2(-d.y, d.x)
			var col := Color(1.0, 0.85, 0.1) if taxi.state != TaxiGame.BESETZT else Color(0.3, 1.0, 0.45)
			draw_colored_polygon(PackedVector2Array([c + d * 74.0, c - d * 44.0 + n * 42.0, c - d * 18.0, c - d * 44.0 - n * 42.0]), col)
			bold(("%d m" % int(dist)) if dist < 1000.0 else ("%.1f km" % (dist / 1000.0)), Vector2(290.0, h * 0.50), 56, Color.WHITE, -1)
			text(taxi.status_line(), Vector2(290.0, h * 0.66), 26, Color(0.8, 0.84, 0.9), -1)
		else:
			# Kompass: Norden = −Z
			var head := atan2(fwd.x, -fwd.z)
			for i in 8:
				var a := -head + i * TAU / 8.0 - PI * 0.5
				var d2 := Vector2(cos(a), sin(a))
				draw_line(c + d2 * 78.0, c + d2 * 92.0, Color(0.6, 0.66, 0.74), 3.0, true)
				if i % 2 == 0:
					text(["N", "O", "S", "W"][i / 2], c + d2 * 58.0 + Vector2(0, 10), 28, Color(1.0, 0.4, 0.3) if i == 0 else Color(0.85, 0.88, 0.93))
			draw_colored_polygon(PackedVector2Array([c + Vector2(0, -34), c + Vector2(20, 24), c + Vector2(0, 12), c + Vector2(-20, 24)]), Color(0.45, 0.78, 1.0))
			text(taxi.status_line() if taxi and taxi.enabled else "Freie Fahrt", Vector2(290.0, h * 0.50), 30, Color(0.8, 0.84, 0.9), -1)
		var st := ck.street()
		if st != "":
			bold(st, Vector2(290.0, h * 0.86), 34, Color(0.95, 0.96, 0.98), -1)
		draw_rect(Rect2(270.0, h * 0.73, w - 300.0, 2.0), Color(0.16, 0.2, 0.26))


class MeterPanel extends Panel2D:
	func _draw() -> void:
		var h := size.y
		draw_rect(Rect2(Vector2.ZERO, size), Color(0.03, 0.006, 0.006))
		var taxi := ck.taxi_game()
		if taxi == null or not taxi.enabled or not taxi.mode_taxi:
			bold("AUS", Vector2(size.x * 0.5, h * 0.74), 60, Color(0.35, 0.05, 0.04))
			return
		if taxi.state == TaxiGame.BESETZT or taxi.state == TaxiGame.AUSSTEIGEN:
			bold(TaxiGame.eur(taxi.fare), Vector2(size.x - 20.0, h * 0.76), 68, Color(1.0, 0.16, 0.1), 1)
			text("%.1f km" % taxi.fare_km, Vector2(18.0, h * 0.72), 34, Color(0.85, 0.14, 0.1), -1)
		else:
			bold("FREI", Vector2(size.x * 0.5, h * 0.76), 68, Color(0.25, 1.0, 0.35))
