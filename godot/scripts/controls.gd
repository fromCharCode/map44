class_name Controls
extends RefCounted
## Eingabe-Aktionen: Gamepad (Steam Controller über Steam Input "Gamepad", Xbox, PlayStation), Tastatur,
## und ein Notbehelf für den Steam-Controller-Desktop-Modus (Trigger = Mausklicks, Trackpad = Maus).
##
## Gamepad-Belegung (wie GTA/Forza):
##   RT Gas · LT Bremse/Rückwärts · linker Stick lenken · rechter Stick umsehen
##   RB Handbremse · LB zurückschauen (halten) · A hochschalten · X runterschalten · B zurücksetzen (2× reparieren)
##   Y Kamera · L3 Hupe · R3 Automatik/Manuell · Steuerkreuz ↑ Licht, ↓ Karte, ←/→ Tageszeit
##   Start Pause · Back/View Karte · hintere Griff-Tasten (falls in Steam belegt): Hupe, Handbremse, Reset, Kamera

static func setup() -> void:
	# --- Analoge Achsen -------------------------------------------------------
	_axis("steer_right", JOY_AXIS_LEFT_X, 1.0, 0.08)
	_axis("steer_left", JOY_AXIS_LEFT_X, -1.0, 0.08)
	_axis("throttle", JOY_AXIS_TRIGGER_RIGHT, 1.0, 0.03)
	_axis("brake", JOY_AXIS_TRIGGER_LEFT, 1.0, 0.03)
	_axis("look_right", JOY_AXIS_RIGHT_X, 1.0, 0.15)
	_axis("look_left", JOY_AXIS_RIGHT_X, -1.0, 0.15)
	_axis("look_up", JOY_AXIS_RIGHT_Y, -1.0, 0.15)
	_axis("look_down", JOY_AXIS_RIGHT_Y, 1.0, 0.15)
	# --- Gamepad-Tasten -------------------------------------------------------
	_btn("handbrake", JOY_BUTTON_RIGHT_SHOULDER)     # RB
	_btn("look_back", JOY_BUTTON_LEFT_SHOULDER)      # LB (halten)
	_btn("gear_up", JOY_BUTTON_A)
	_btn("gear_down", JOY_BUTTON_X)
	_btn("reset", JOY_BUTTON_B)
	_btn("camera", JOY_BUTTON_Y)
	_btn("horn", JOY_BUTTON_LEFT_STICK)              # L3 (wie GTA)
	_btn("toggle_manual", JOY_BUTTON_RIGHT_STICK)    # R3
	_btn("lights", JOY_BUTTON_DPAD_UP)
	_btn("map", JOY_BUTTON_DPAD_DOWN)
	_btn("time_back", JOY_BUTTON_DPAD_LEFT)
	_btn("time_forward", JOY_BUTTON_DPAD_RIGHT)
	_btn("pause", JOY_BUTTON_START)
	_btn("map", JOY_BUTTON_BACK)
	# Steam Controller / Elite: hintere Griff-Tasten (nur wenn in Steam Input als Paddles belegt)
	_btn("horn", JOY_BUTTON_PADDLE1)
	_btn("handbrake", JOY_BUTTON_PADDLE2)
	_btn("reset", JOY_BUTTON_PADDLE3)
	_btn("camera", JOY_BUTTON_PADDLE4)
	# --- Tastatur -------------------------------------------------------------
	_key("steer_left", KEY_A)
	_key("steer_right", KEY_D)
	_key("throttle", KEY_W)
	_key("brake", KEY_S)
	_key("steer_left", KEY_LEFT)
	_key("steer_right", KEY_RIGHT)
	_key("throttle", KEY_UP)
	_key("brake", KEY_DOWN)
	_key("handbrake", KEY_SPACE)
	_key("reset", KEY_R)
	_key("camera", KEY_C)
	_key("lights", KEY_L)
	_key("gear_up", KEY_E)
	_key("gear_down", KEY_Q)
	_key("toggle_manual", KEY_F)
	_key("horn", KEY_H)
	_key("pause", KEY_ESCAPE)
	_key("look_back", KEY_B)
	_key("time_forward", KEY_T)
	_key("time_back", KEY_G)
	_key("map", KEY_M)
	_key("quality", KEY_F2)
	_key("inputtest", KEY_F1)
	_key("street_picker", KEY_F3)
	_key("damage_toggle", KEY_F4)
	_key("repair", KEY_F5)
	_key("weather", KEY_F6)
	# --- Notbehelf: Steam Controller im Desktop-Modus (Steam-Standard: RT = Linksklick, LT = Rechtsklick) ---
	_mouse("throttle", MOUSE_BUTTON_LEFT)
	_mouse("brake", MOUSE_BUTTON_RIGHT)


static var _desktop_mode_cache := -1


static func steam_controller_desktop_mode() -> bool:
	## True, wenn ein Steam Controller angeschlossen ist, aber kein Gamepad ankommt (Steam emuliert dann
	## Tastatur/Maus, weil das Spiel nicht über Steam mit Gamepad-Layout gestartet wurde).
	if not Input.get_connected_joypads().is_empty():
		return false
	if _desktop_mode_cache == -1:
		_desktop_mode_cache = 0
		var f := FileAccess.open("/proc/bus/input/devices", FileAccess.READ)
		if f:
			var txt := f.get_as_text()
			if txt.contains("Steam Controller") or txt.contains("Valve Software"):
				_desktop_mode_cache = 1
	return _desktop_mode_cache == 1


static func vibrate(weak: float, strong: float, duration: float) -> void:
	for id in Input.get_connected_joypads():
		Input.start_joy_vibration(id, clampf(weak, 0.0, 1.0), clampf(strong, 0.0, 1.0), duration)


static func _ensure(action: String, deadzone: float = 0.2) -> void:
	if not InputMap.has_action(action):
		InputMap.add_action(action, deadzone)


static func _axis(action: String, axis: int, value: float, dz: float) -> void:
	_ensure(action, dz)
	var e := InputEventJoypadMotion.new()
	e.axis = axis
	e.axis_value = value
	InputMap.action_add_event(action, e)


static func _key(action: String, key: int) -> void:
	_ensure(action)
	var e := InputEventKey.new()
	e.physical_keycode = key
	InputMap.action_add_event(action, e)


static func _btn(action: String, button: int) -> void:
	_ensure(action)
	var e := InputEventJoypadButton.new()
	e.button_index = button
	InputMap.action_add_event(action, e)


static func _mouse(action: String, button: int) -> void:
	_ensure(action)
	var e := InputEventMouseButton.new()
	e.button_index = button
	InputMap.action_add_event(action, e)
