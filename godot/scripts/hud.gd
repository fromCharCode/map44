class_name Hud
extends Control
## Anzeige: Tacho, Gang, Uhrzeit, Straßenname, Minimap mit Verkehr.

var car: PlayerCar
var env_mgr: EnvManager
var traffic: Traffic
var index
var world: World
var cam_rig: CamRig
var street_name := ""
var show_map := true
var fps := 0
var info_msg := ""
var info_t := 0.0
var _name_t := 0.0
var _font: Font
var minimap: MiniMap
var show_input := false
var taxi: TaxiGame


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_font = ThemeDB.fallback_font
	minimap = MiniMap.new()
	minimap.name = "MiniMap"
	add_child(minimap)


func message(text: String, secs: float = 2.5) -> void:
	info_msg = text
	info_t = secs


var _engine_note := ""


func _process(delta: float) -> void:
	if car and car.engine_note != _engine_note:
		_engine_note = car.engine_note
		if _engine_note != "":
			message(_engine_note, 5.0)
	minimap.car = car
	minimap.traffic = traffic
	minimap.world = world
	minimap.visible = show_map
	info_t = maxf(info_t - delta, 0.0)
	_name_t -= delta
	if _name_t <= 0.0 and car and index:
		_name_t = 0.5
		var hit: Dictionary = index.nearest(car.global_position.x, car.global_position.z, 14.0)
		street_name = String(hit["road"]["name"]) if not hit.is_empty() else ""
	fps = Engine.get_frames_per_second()
	queue_redraw()


func _draw() -> void:
	if car == null:
		return
	var vp := get_viewport_rect().size
	var kmh := car.get_speed_kmh()
	# Tacho unten rechts
	var c := Vector2(vp.x - 150.0, vp.y - 140.0)
	var r := 92.0
	var a0 := deg_to_rad(135.0)
	var a1 := deg_to_rad(405.0)
	# in der Cockpit-Ansicht zeigt das Kombiinstrument Tempo, Gang und Tempomat – der Rundtacho wäre doppelt
	if not (cam_rig != null and cam_rig.mode == 2):
		draw_circle(c, r + 8.0, Color(0, 0, 0, 0.45))
		draw_arc(c, r, a0, a1, 48, Color(1, 1, 1, 0.18), 6.0, true)
		var frac := clampf(kmh / 220.0, 0.0, 1.0)
		var col := Color(0.95, 0.85, 0.3).lerp(Color(1.0, 0.3, 0.2), clampf((kmh - 130.0) / 90.0, 0.0, 1.0))
		draw_arc(c, r, a0, a0 + (a1 - a0) * frac, 48, col, 6.0, true)
		# Drehzahl innen
		var rf := clampf((car.rpm - 800.0) / 4200.0, 0.0, 1.0)
		draw_arc(c, r - 14.0, a0, a0 + (a1 - a0) * rf, 40, Color(0.5, 0.8, 1.0, 0.85), 3.0, true)
		var sp := str(int(round(kmh)))
		_text(sp, c + Vector2(0, 14), 52, Color.WHITE, true)
		_text("km/h", c + Vector2(0, 40), 16, Color(1, 1, 1, 0.7), true)
		if car.cruise_on:
			# Tempomat: grüne Marke am Tachobogen + gesetzter Wert
			var cf := clampf(car.cruise_target * 3.6 / 220.0, 0.0, 1.0)
			var ca := a0 + (a1 - a0) * cf
			var cd := Vector2(cos(ca), sin(ca))
			draw_line(c + cd * (r - 9.0), c + cd * (r + 9.0), Color(0.3, 1.0, 0.45), 4.0, true)
			_text("TEMPOMAT %d" % int(round(car.cruise_target * 3.6)), c + Vector2(0, 62), 15, Color(0.3, 1.0, 0.45), true)
		var g := "R" if car.gear == 0 else str(car.gear)
		if car.manual:
			g += "M"
		if absf(car.speed) < 0.3 and car.in_throttle < 0.05 and car.in_brake < 0.05:
			g = "N"
		_text(g, c + Vector2(0, -34), 30, Color(1, 1, 1, 0.9), true)
	if car.damage and car.damage.total > 0.01:
		var dx := c + Vector2(-60.0, -r - 52.0)
		draw_rect(Rect2(dx, Vector2(120.0, 7.0)), Color(0, 0, 0, 0.5))
		var dcol := Color(0.4, 0.9, 0.4).lerp(Color(1.0, 0.25, 0.15), clampf(car.damage.total * 1.6, 0.0, 1.0))
		draw_rect(Rect2(dx, Vector2(120.0 * clampf(car.damage.total, 0.0, 1.0), 7.0)), dcol)
		_text("Schaden %d %%" % int(car.damage.total * 100.0), dx + Vector2(60.0, -4.0), 13, Color(1, 1, 1, 0.75), true)
		if car.damage.front > 0.4:
			_text("MOTOR", dx + Vector2(60.0, -22.0), 14, Color(1.0, 0.4, 0.3), true)

	# Uhrzeit, Straße
	if env_mgr:
		var h := int(env_mgr.hours)
		var m := int((env_mgr.hours - h) * 60.0)
		_text("%02d:%02d" % [h, m], Vector2(vp.x - 80.0, 34.0), 24, Color(1, 1, 1, 0.9), true)
	if street_name != "":
		_text(street_name, Vector2(vp.x * 0.5, vp.y - 40.0), 26, Color(1, 1, 1, 0.92), true)
	if cam_rig:
		_text(CamRig.MODE_NAMES[cam_rig.mode], Vector2(vp.x * 0.5, 30.0), 16, Color(1, 1, 1, 0.45), true)
	_text("%d FPS" % fps, Vector2(60.0, 28.0), 14, Color(1, 1, 1, 0.4), true)
	if taxi and taxi.enabled:
		_draw_taxi(vp)
	if show_input:
		_draw_input_test()
	if info_t > 0.0:
		_text(info_msg, Vector2(vp.x * 0.5, vp.y * 0.18), 28, Color(1, 1, 1, clampf(info_t, 0.0, 1.0)), true)



func _draw_taxi(vp: Vector2) -> void:
	## Taxi: Kasse und Status oben links, Taxameter bei besetzter Fahrt, Richtungspfeil zum Ziel oben Mitte
	var x0 := 24.0
	var y0 := 52.0
	draw_rect(Rect2(Vector2(x0 - 10.0, y0 - 6.0), Vector2(330.0, 62.0)), Color(0, 0, 0, 0.45))
	_text("TAXI  " + TaxiGame.eur(taxi.money), Vector2(x0, y0 + 16.0), 20, Color(1.0, 0.85, 0.2))
	if taxi.rated > 0:
		_text("★ %.1f" % taxi.rating(), Vector2(x0 + 150.0, y0 + 16.0), 15, Color(1.0, 0.9, 0.5))
	_text("%s   (%d Fahrten)" % [taxi.status_line(), taxi.trips], Vector2(x0, y0 + 42.0), 15, Color(1, 1, 1, 0.85))
	if taxi.state == TaxiGame.BESETZT or taxi.state == TaxiGame.AUSSTEIGEN:
		draw_rect(Rect2(Vector2(x0 - 10.0, y0 + 62.0), Vector2(330.0, 44.0)), Color(0.05, 0.05, 0.05, 0.7))
		_text("Taxameter  %s" % TaxiGame.eur(taxi.fare), Vector2(x0, y0 + 92.0), 24, Color(1.0, 0.3, 0.2))
		_text("%.1f km" % taxi.fare_km, Vector2(x0 + 250.0, y0 + 92.0), 15, Color(1, 1, 1, 0.7))
	# Funkaufträge zur Auswahl
	if taxi.mode_taxi and taxi.state == TaxiGame.FREI and not taxi.offers.is_empty() and car:
		var oy := y0 + 74.0
		draw_rect(Rect2(Vector2(x0 - 10.0, oy - 8.0), Vector2(470.0, 26.0 + 44.0 * float(taxi.offers.size()))), Color(0, 0, 0, 0.5))
		_text("FUNK  –  1/2/3 annehmen (LB+A/X/Y), N andere (LB+B)", Vector2(x0, oy + 8.0), 12, Color(1, 1, 1, 0.6))
		for i in taxi.offers.size():
			var of: Dictionary = taxi.offers[i]
			var dp := int(car.global_position.distance_to(of["pickup"]))
			var yy := oy + 30.0 + 44.0 * float(i)
			var pt: Array = TaxiGame.PTYPES[int(of.get("ptype", 0))]
			_text("%d  %s  →  %s" % [i + 1, String(of["pname"]), String(of["dname"])], Vector2(x0, yy), 16, Color(1.0, 0.9, 0.4))
			_text(String(pt[0]) + ("  ⏱" if float(pt[4]) > 0.0 else ""), Vector2(x0 + 330.0, yy + 18.0), 12, Color(0.7, 0.9, 1.0, 0.9))
			_text("Anfahrt %s  ·  Fahrt ca. %.1f km  ·  ca. %s" % [("%d m" % dp) if dp < 1000 else ("%.1f km" % (dp / 1000.0)),
				float(of["trip_km"]), TaxiGame.eur(float(of["fare"]))], Vector2(x0 + 18.0, yy + 18.0), 13, Color(1, 1, 1, 0.8))
	# Tankanzeige
	if car:
		var fx := x0 + 200.0
		var ff := clampf(car.fuel_l / PlayerCar.FUEL_CAP, 0.0, 1.0)
		draw_rect(Rect2(Vector2(fx, y0 + 4.0), Vector2(110.0, 12.0)), Color(1, 1, 1, 0.18))
		draw_rect(Rect2(Vector2(fx, y0 + 4.0), Vector2(110.0 * ff, 12.0)), Color(1.0, 0.3, 0.2) if ff < 0.12 else Color(0.85, 0.85, 0.85))
		_text(("Tanken … %.0f l" % car.fuel_l) if taxi.fueling else ("%.0f l" % car.fuel_l), Vector2(fx, y0 + 30.0), 12, Color(1, 1, 1, 0.7))
	var tg := taxi.target()
	if tg != Vector3.ZERO and car:
		var to := tg - car.global_position
		var dist := Vector2(to.x, to.z).length()
		var fwd := -car.global_transform.basis.z
		var ang := atan2(fwd.x * to.z - fwd.z * to.x, fwd.x * to.x + fwd.z * to.z)   # + = Ziel rechts
		var c := Vector2(vp.x * 0.5, 78.0)
		var col := Color(1.0, 0.85, 0.1) if taxi.state != TaxiGame.BESETZT else Color(0.3, 1.0, 0.45)
		var d := Vector2(sin(ang), -cos(ang))
		var n := Vector2(-d.y, d.x)
		draw_circle(c, 30.0, Color(0, 0, 0, 0.45))
		draw_colored_polygon(PackedVector2Array([c + d * 24.0, c - d * 14.0 + n * 13.0, c - d * 6.0, c - d * 14.0 - n * 13.0]), col)
		_text(("%d m" % int(dist)) if dist < 1000.0 else ("%.1f km" % (dist / 1000.0)), c + Vector2(0, 52.0), 18, Color(1, 1, 1, 0.9), true)


func _text(s: String, pos: Vector2, size: int, color: Color, center: bool = false) -> void:
	var w := _font.get_string_size(s, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
	var p := pos - Vector2(w * 0.5 if center else 0.0, 0.0)
	draw_string(_font, p + Vector2(1.5, 1.5), s, HORIZONTAL_ALIGNMENT_LEFT, -1, size, Color(0, 0, 0, color.a * 0.6))
	draw_string(_font, p, s, HORIZONTAL_ALIGNMENT_LEFT, -1, size, color)


func _draw_input_test() -> void:
	var pads := Input.get_connected_joypads()
	var y := 90.0
	draw_rect(Rect2(20, 70, 620, 330), Color(0, 0, 0, 0.7))
	_text("EINGABETEST (F1 schließt)  –  verbundene Controller: %d" % pads.size(), Vector2(34, y), 20, Color(1, 0.9, 0.4))
	y += 28.0
	if pads.is_empty():
		var lines := ["Kein Gamepad erkannt." + (" Steam Controller im Desktop-Modus (Steam sendet Tastatur/Maus)." if Controls.steam_controller_desktop_mode() else ""),
			"So geht's: Steam > Spiele > 'Ein Nicht-Steam-Spiel hinzufügen' > 'Dresden' wählen,",
			"dann Rechtsklick auf Dresden > Eigenschaften > Controller > Steam Input aktivieren,",
			"Controller-Layout 'Gamepad' (Vorlage) wählen und das Spiel aus Steam starten.",
			"Notbehelf ohne Steam-Start: RT = Gas, LT = Bremse (Mausklicks), rechtes Trackpad = umsehen."]
		for ln in lines:
			_text(ln, Vector2(34, y), 16, Color(1, 0.6, 0.5))
			y += 22.0
		return
	for id in pads:
		_text("[%d] %s" % [id, Input.get_joy_name(id)], Vector2(34, y), 16, Color.WHITE)
		y += 22.0
		var ax := ""
		for a in 6:
			ax += "A%d:%+.2f  " % [a, Input.get_joy_axis(id, a)]
		_text(ax, Vector2(34, y), 16, Color(0.7, 0.9, 1.0))
		y += 22.0
		var bt := "Gedrückt: "
		for b in 21:
			if Input.is_joy_button_pressed(id, b):
				bt += "%d " % b
		_text(bt, Vector2(34, y), 16, Color(0.7, 1.0, 0.7))
		y += 28.0
	_text("Gas: %.2f  Bremse: %.2f  Lenkung: %+.2f" % [Input.get_action_strength("throttle"), Input.get_action_strength("brake"), Input.get_axis("steer_left", "steer_right")], Vector2(34, y), 18, Color.WHITE)
	y += 26.0
	_text("Erwartet: RT=A5 Gas  LT=A4 Bremse  linker Stick=A0  RB=10 Handbremse  LB=9 zurückschauen  L3=7 Hupe", Vector2(34, y), 14, Color(1, 1, 1, 0.6))
