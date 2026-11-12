class_name CarAudio
extends Node
## Fahrzeugklang des Spielers aus echten Aufnahmen (assets/audio, CC0/CC-BY, siehe LICENSES.md):
## Motor als Drehzahl-Mixer (je Lastzustand die zwei benachbarten Drehzahlstufen gleichleistungs-überblendet und
## auf die aktuelle Drehzahl umgestimmt), dazu Abrollen (Asphalt/Kopfstein), Fahrtwind, Reifenquietschen, Hupe,
## Schalten und Aufprall.

const MAN := "res://assets/audio/MANIFEST.json"
const ENGINE_GAIN := 0.85

var car: PlayerCar
var volume := 1.0
var _muted := false
var sets := {}                 # "on"/"off"/"neutral" -> Array[{rpm, p}]
var _loops := {}               # Name -> AudioStreamPlayer
var _oneshots: Array = []      # Pool für Kurzklänge
var _shot_i := 0
var _streams := {}             # Art -> Array[AudioStream]
var _load := 0.0
var _prev_gear := 1
var _horn := false
var _rng := RandomNumberGenerator.new()
# Altlast: main.gd greift ggf. auf .player zu
var player: AudioStreamPlayer


func setup(c: PlayerCar) -> void:
	car = c
	_rng.seed = 11
	GameSettings.load_settings()
	if not FileAccess.file_exists(MAN):
		push_warning("CarAudio: keine Audiodateien")
		return
	var man = JSON.parse_string(FileAccess.get_file_as_string(MAN))
	if not (man is Dictionary):
		return
	var es: Dictionary = man.get("engine_sets", {})
	sets["on"] = _make_set(es.get("player_on", []))
	sets["off"] = _make_set(es.get("player_off_overrun", []))
	sets["neutral"] = _make_set(es.get("player_off_neutral", []))
	for e in man.get("sounds", []):
		var kind := String(e.get("kind", ""))
		var path := String(e.get("res_path", "res://assets/audio/" + String(e.get("file", ""))))
		if not ResourceLoader.exists(path):
			continue
		if not _streams.has(kind):
			_streams[kind] = []
		(_streams[kind] as Array).append(path)
	_loop("roll", "res://assets/audio/car/roll_asphalt_loop.ogg")
	_loop("cobble", "res://assets/audio/car/roll_cobble_loop.ogg")
	_loop("wind", "res://assets/audio/car/wind_loop.ogg")
	_loop("squeal", "res://assets/audio/car/tire_squeal_loop_1.ogg")
	_loop("horn", "res://assets/audio/car/horn_loop.ogg", false)
	for i in 6:
		var p := AudioStreamPlayer.new()
		p.bus = GameSettings.VEHICLE_BUS
		add_child(p)
		_oneshots.append(p)
	player = _oneshots[0]
	_prev_gear = car.gear


func set_muted(m: bool) -> void:
	_muted = m
	AudioServer.set_bus_mute(AudioServer.get_bus_index(GameSettings.VEHICLE_BUS), m)


func _make_set(lst: Array) -> Array:
	var res: Array = []
	for e in lst:
		var path := "res://assets/audio/" + String(e["file"])
		if not ResourceLoader.exists(path):
			continue
		var p := AudioStreamPlayer.new()
		p.stream = _looped(path)
		p.bus = GameSettings.VEHICLE_BUS
		p.volume_db = -80.0
		add_child(p)
		p.play(_rng.randf() * 0.5)
		res.append({"rpm": float(e["rpm"]), "p": p})
	res.sort_custom(func(a, b): return a["rpm"] < b["rpm"])
	return res


func _loop(name: String, path: String, autoplay: bool = true) -> void:
	if not ResourceLoader.exists(path):
		return
	var p := AudioStreamPlayer.new()
	p.stream = _looped(path)
	p.bus = GameSettings.VEHICLE_BUS
	p.volume_db = -80.0
	add_child(p)
	if autoplay:
		p.play(_rng.randf() * 1.0)
	_loops[name] = p


static func _looped(path: String) -> AudioStream:
	var st = load(path)
	if st is AudioStreamOggVorbis:
		(st as AudioStreamOggVorbis).loop = true
	elif st is AudioStreamWAV:
		(st as AudioStreamWAV).loop_mode = AudioStreamWAV.LOOP_FORWARD
	return st


func _shot(kind: String, vol: float = 1.0, pitch: float = 1.0) -> void:
	var lst: Array = _streams.get(kind, [])
	if lst.is_empty() or _oneshots.is_empty():
		return
	var p: AudioStreamPlayer = _oneshots[_shot_i % _oneshots.size()]
	_shot_i += 1
	p.stream = load(lst[_rng.randi() % lst.size()])
	p.volume_db = linear_to_db(maxf(vol, 0.0001))
	p.pitch_scale = pitch
	p.play()


func _set_vol(p: AudioStreamPlayer, v: float) -> void:
	p.volume_db = linear_to_db(maxf(v * volume, 0.00005))


func _mix_set(arr: Array, rpm: float, mix: float) -> void:
	var n := arr.size()
	if n == 0:
		return
	var i0 := 0
	var i1 := 0
	var t := 0.0
	if rpm <= float(arr[0]["rpm"]):
		i0 = 0
		i1 = 0
	elif rpm >= float(arr[n - 1]["rpm"]):
		i0 = n - 1
		i1 = n - 1
	else:
		for i in n - 1:
			if rpm < float(arr[i + 1]["rpm"]):
				i0 = i
				i1 = i + 1
				t = (rpm - float(arr[i]["rpm"])) / (float(arr[i + 1]["rpm"]) - float(arr[i]["rpm"]))
				break
	for k in n:
		var w := 0.0
		if k == i0 and k == i1:
			w = 1.0
		elif k == i0:
			w = cos(t * PI * 0.5)
		elif k == i1:
			w = sin(t * PI * 0.5)
		var p: AudioStreamPlayer = arr[k]["p"]
		var v := w * mix * ENGINE_GAIN
		_set_vol(p, v)
		if v > 0.001:
			p.pitch_scale = clampf(rpm / float(arr[k]["rpm"]), 0.5, 2.0)


func _process(delta: float) -> void:
	if car == null or sets.is_empty():
		return
	var rpm := maxf(car.rpm, 700.0)
	var thr := car.in_throttle
	var spd := absf(car.speed)
	_load = move_toward(_load, thr, delta * 5.0)
	var in_gear := (car.gear >= 1 or car.reversing) and spd > 1.2
	var on_mix := clampf(0.15 + 0.85 * _load, 0.0, 1.0) if _load > 0.02 else 0.0
	var rest := 1.0 - on_mix
	var off_mix := rest if in_gear and rpm > 1350.0 else 0.0
	var neu_mix := rest - off_mix
	_mix_set(sets["on"], rpm, on_mix)
	_mix_set(sets["off"], rpm, off_mix * 0.85)
	_mix_set(sets["neutral"], rpm, neu_mix * 0.9)
	# Abrollen, Wind, Reifen
	var rough: float = car.roughness if "roughness" in car else 0.0
	var roll_v := pow(clampf(spd / 25.0, 0.0, 1.0), 0.8) * 0.55
	if _loops.has("roll"):
		_set_vol(_loops["roll"], roll_v * (1.0 - clampf(rough, 0.0, 1.0)) * (1.0 if car.grounded > 0 else 0.2))
		(_loops["roll"] as AudioStreamPlayer).pitch_scale = 0.8 + clampf(spd / 40.0, 0.0, 0.7)
	if _loops.has("cobble"):
		_set_vol(_loops["cobble"], roll_v * 1.4 * clampf(rough, 0.0, 1.0))
		(_loops["cobble"] as AudioStreamPlayer).pitch_scale = 0.75 + clampf(spd / 30.0, 0.0, 0.8)
	if _loops.has("wind"):
		_set_vol(_loops["wind"], pow(clampf(spd / 45.0, 0.0, 1.2), 2.0) * 0.6)
		(_loops["wind"] as AudioStreamPlayer).pitch_scale = 0.85 + clampf(spd / 90.0, 0.0, 0.5)
	if _loops.has("squeal"):
		var sq := clampf((car.slip - 2.2) / 5.0, 0.0, 1.0) if car.grounded > 0 else 0.0
		_set_vol(_loops["squeal"], sq * 0.7)
		(_loops["squeal"] as AudioStreamPlayer).pitch_scale = 0.9 + sq * 0.2
	# Hupe: Anfang, Schleife, Ende
	if car.horn_pressed != _horn:
		_horn = car.horn_pressed
		if _horn:
			var starts: Array = (_streams.get("horn", []) as Array).filter(func(p): return String(p).ends_with("horn_start.ogg"))
			if not starts.is_empty() and not _oneshots.is_empty():
				var sp: AudioStreamPlayer = _oneshots[_shot_i % _oneshots.size()]
				_shot_i += 1
				sp.stream = load(starts[0])
				sp.volume_db = linear_to_db(0.9 * volume)
				sp.play()
			if _loops.has("horn"):
				(_loops["horn"] as AudioStreamPlayer).play()
				_set_vol(_loops["horn"], 0.85)
		else:
			if _loops.has("horn"):
				(_loops["horn"] as AudioStreamPlayer).stop()
			var ends: Array = (_streams.get("horn", []) as Array).filter(func(p): return String(p).ends_with("horn_end.ogg"))
			if not ends.is_empty() and not _oneshots.is_empty():
				var p: AudioStreamPlayer = _oneshots[_shot_i % _oneshots.size()]
				_shot_i += 1
				p.stream = load(ends[0])
				p.volume_db = linear_to_db(0.85 * volume)
				p.play()
	# Schalten
	if car.gear != _prev_gear:
		_prev_gear = car.gear
		_shot("gear_shift", 0.45, _rng.randf_range(0.95, 1.05))
	# Aufprall
	while not car.impact_events.is_empty():
		var dv: float = car.impact_events.pop_front()
		if dv > 6.0:
			_shot("impact_heavy", clampf(dv / 12.0, 0.6, 1.0))
			if dv > 9.0:
				_shot("glass", 0.8)
		elif dv > 2.0:
			_shot("impact_light", clampf(dv / 6.0, 0.35, 0.9))
		else:
			_shot("bump", clampf(dv / 2.5, 0.25, 0.6))
