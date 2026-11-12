class_name GameSettings
extends RefCounted
## Dauerhafte Spieleinstellungen (user://settings.cfg) und Audiobusse.

const PATH := "user://settings.cfg"
const VEHICLE_BUS := "Fahrzeug"

static var master_volume := 0.8      # 0..1
static var vehicle_volume := 0.45    # 0..1 (Motor, Reifen, Wind, Hupe)
static var render_scale := -1.0      # 3D-Auflösung (FSR2 unter 1.0); -1 = automatisch nach Bildschirmauflösung
static var _loaded := false


static func load_settings() -> void:
	if _loaded:
		return
	_loaded = true
	var cf := ConfigFile.new()
	if cf.load(PATH) == OK:
		master_volume = clampf(float(cf.get_value("audio", "master", master_volume)), 0.0, 1.0)
		vehicle_volume = clampf(float(cf.get_value("audio", "vehicle", vehicle_volume)), 0.0, 1.0)
		var rs := float(cf.get_value("graphics", "render_scale", render_scale))
		render_scale = -1.0 if rs <= 0.0 else clampf(rs, 0.5, 1.0)
	_ensure_buses()
	apply_audio()


static func save_settings() -> void:
	var cf := ConfigFile.new()
	cf.load(PATH)
	cf.set_value("audio", "master", master_volume)
	cf.set_value("audio", "vehicle", vehicle_volume)
	cf.set_value("graphics", "render_scale", render_scale)
	cf.save(PATH)


static func _ensure_buses() -> void:
	if AudioServer.get_bus_index(VEHICLE_BUS) == -1:
		AudioServer.add_bus()
		var i := AudioServer.bus_count - 1
		AudioServer.set_bus_name(i, VEHICLE_BUS)
		AudioServer.set_bus_send(i, "Master")


static func apply_audio() -> void:
	_ensure_buses()
	_set_bus("Master", master_volume)
	_set_bus(VEHICLE_BUS, vehicle_volume)


static func _set_bus(name: String, v: float) -> void:
	var i := AudioServer.get_bus_index(name)
	if i < 0:
		return
	AudioServer.set_bus_mute(i, v <= 0.001)
	# quadratische Kurve: der Regler fühlt sich gleichmäßiger an als linear
	AudioServer.set_bus_volume_db(i, linear_to_db(maxf(v * v, 0.0001)))
