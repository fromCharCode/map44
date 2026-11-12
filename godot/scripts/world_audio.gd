class_name WorldAudio
extends Node3D
## Klänge der Welt: Motoren der nächsten KI-Autos und Busse (3D), Bustüren/Druckluft an Haltestellen,
## Straßenbahnen (Fahrgeräusch, Klingel) und die Stadt-Atmosphäre (Tag/Nacht, Regen, Grünflächen).
## Aufnahmen: assets/audio (Lizenzen in LICENSES.md).

const CAR_SLOTS := 8
const BUS_SLOTS := 3
const TRAM_SLOTS := 2
const A := "res://assets/audio/"

var traffic: Traffic
var trams: Trams
var listener: Node3D
var env: EnvManager
var world: World
var _car_slots: Array = []     # {idle, drive, car}
var _bus_slots: Array = []     # {idle, drive, car, at_stop, door}
var _tram_slots: Array = []    # {drive, tram, bell_t}
var _amb := {}
var _timer := 0.0
var _rng := RandomNumberGenerator.new()


func setup(tr: Traffic, tm: Trams, lis: Node3D, e: EnvManager, w: World) -> void:
	traffic = tr
	trams = tm
	listener = lis
	env = e
	world = w
	_rng.seed = 5
	for i in CAR_SLOTS:
		_car_slots.append({"idle": _p3(A + "engine/ai_idle.ogg", 5.0), "drive": _p3(A + "engine/ai_2010.ogg", 5.0), "car": null})
	for i in BUS_SLOTS:
		_bus_slots.append({"idle": _p3(A + "bus/bus_idle_loop.ogg", 8.0), "drive": _p3(A + "bus/bus_drive_loop.ogg", 8.0),
			"door": _p3("", 8.0), "car": null, "at_stop": false, "speed": 0.0})
	for i in TRAM_SLOTS:
		_tram_slots.append({"drive": _p3(A + "tram/tram_drive_loop.ogg", 10.0), "bell": _p3("", 12.0), "tram": null, "bell_t": 0.0})
	for k in ["amb_city_day", "amb_city_night", "amb_rain", "amb_park_day"]:
		var p := AudioStreamPlayer.new()
		var path: String = A + "ambience/" + String(k) + ".ogg"
		if ResourceLoader.exists(path):
			p.stream = CarAudio._looped(path)
			p.volume_db = -80.0
			add_child(p)
			p.play(_rng.randf() * 20.0)
			_amb[k] = p


func _p3(path: String, unit: float) -> AudioStreamPlayer3D:
	var p := AudioStreamPlayer3D.new()
	if path != "" and ResourceLoader.exists(path):
		p.stream = CarAudio._looped(path)
	p.unit_size = unit
	p.max_distance = 110.0
	p.volume_db = -80.0
	p.doppler_tracking = AudioStreamPlayer3D.DOPPLER_TRACKING_DISABLED
	add_child(p)
	return p


func _vol(p: Node, v: float) -> void:
	p.volume_db = linear_to_db(maxf(v, 0.00005))


func _process(delta: float) -> void:
	if listener == null or traffic == null:
		return
	var lp := listener.global_position
	_timer -= delta
	if _timer <= 0.0:
		_timer = 0.3
		_assign(lp)
	# KI-Autos
	for sl in _car_slots:
		var cv = sl["car"]
		if cv == null or not is_instance_valid(cv) or (cv as AICar).dead:
			sl["car"] = null
			_vol(sl["idle"], 0.0)
			_vol(sl["drive"], 0.0)
			continue
		var c: AICar = cv
		var pos := c.world_pos() + Vector3(0, 0.6, 0)
		(sl["idle"] as Node3D).global_position = pos
		(sl["drive"] as Node3D).global_position = pos
		var spd := c.speed
		var drive := clampf(spd / 4.0, 0.0, 1.0)
		var rpm := 850.0 + spd * 110.0 * (1.0 + 0.25 * float(c._brake == false))
		_vol(sl["idle"], (1.0 - drive) * 0.5)
		_vol(sl["drive"], drive * 0.55)
		(sl["drive"] as AudioStreamPlayer3D).pitch_scale = clampf(rpm / 2010.0, 0.55, 1.6)
		(sl["idle"] as AudioStreamPlayer3D).pitch_scale = clampf(rpm / 837.0, 0.9, 1.4)
		_ensure_playing(sl["idle"])
		_ensure_playing(sl["drive"])
	# Busse
	for sl in _bus_slots:
		var bv = sl["car"]
		if bv == null or not is_instance_valid(bv) or (bv as AICar).dead:
			sl["car"] = null
			_vol(sl["idle"], 0.0)
			_vol(sl["drive"], 0.0)
			continue
		var b: AICar = bv
		var pos := b.world_pos() + Vector3(0, 1.0, 0)
		for k in ["idle", "drive", "door"]:
			(sl[k] as Node3D).global_position = pos
		var drive := clampf(b.speed / 5.0, 0.0, 1.0)
		_vol(sl["idle"], (1.0 - drive) * 0.6)
		_vol(sl["drive"], drive * 0.75)
		(sl["drive"] as AudioStreamPlayer3D).pitch_scale = clampf(0.75 + b.speed / 18.0, 0.7, 1.4)
		_ensure_playing(sl["idle"])
		_ensure_playing(sl["drive"])
		if b is BusCar:
			var bc := b as BusCar
			if bc.at_stop and not bool(sl["at_stop"]):
				_once(sl["door"], ["bus/bus_door_open.ogg", "bus/bus_air_release_1.ogg"], 0.8)
			elif not bc.at_stop and bool(sl["at_stop"]):
				_once(sl["door"], ["bus/bus_door_close.ogg"], 0.7)
			elif float(sl["speed"]) > 3.0 and bc.speed < 2.0 and bc._brake and _rng.randf() < 0.02:
				_once(sl["door"], ["bus/bus_brake_squeal.ogg"], 0.5)
			sl["at_stop"] = bc.at_stop
		sl["speed"] = b.speed
	# Straßenbahnen
	for sl in _tram_slots:
		var tu = sl["tram"]
		if tu == null or not is_instance_valid(tu) or (tu as TramUnit).dead or (tu as TramUnit).bodies.is_empty():
			sl["tram"] = null
			_vol(sl["drive"], 0.0)
			continue
		var tram := tu as TramUnit
		var pos := (tram.bodies[0] as Node3D).global_position + Vector3(0, 1.5, 0)
		(sl["drive"] as Node3D).global_position = pos
		(sl["bell"] as Node3D).global_position = pos
		_vol(sl["drive"], clampf(tram.speed / 8.0, 0.0, 1.0) * 0.9)
		(sl["drive"] as AudioStreamPlayer3D).pitch_scale = clampf(0.7 + tram.speed / 20.0, 0.7, 1.3)
		_ensure_playing(sl["drive"])
		sl["bell_t"] = float(sl["bell_t"]) - delta
		if float(sl["bell_t"]) <= 0.0:
			sl["bell_t"] = _rng.randf_range(20.0, 60.0)
			if tram.speed > 2.0 and pos.distance_to(lp) < 60.0:
				_once(sl["bell"], ["tram/tram_bell_1.ogg", "tram/tram_bell_2.ogg"], 0.8)
	_ambience(lp, delta)


func _ensure_playing(p: AudioStreamPlayer3D) -> void:
	if p.stream != null and not p.playing:
		p.play(_rng.randf() * 1.0)


func _once(p: AudioStreamPlayer3D, files: Array, vol: float) -> void:
	var f: String = A + String(files[_rng.randi() % files.size()])
	if not ResourceLoader.exists(f):
		return
	p.stream = load(f)
	_vol(p, vol)
	p.play()


func _assign(lp: Vector3) -> void:
	## Nächste Fahrzeuge auf die Klangplätze verteilen (bestehende Zuordnungen bleiben, solange nah genug)
	var cars: Array = []
	var buses: Array = []
	for c in traffic.cars:
		var ac := c as AICar
		var d := ac.world_pos().distance_to(lp)
		if d > 80.0:
			continue
		if ac.is_bus:
			buses.append([d, ac])
		else:
			cars.append([d, ac])
	cars.sort_custom(func(a, b): return a[0] < b[0])
	buses.sort_custom(func(a, b): return a[0] < b[0])
	_fill(_car_slots, cars, "car")
	_fill(_bus_slots, buses, "car")
	if trams:
		var tl: Array = []
		for t in trams.trams:
			var tu := t as TramUnit
			if tu.dead or tu.bodies.is_empty():
				continue
			var d := (tu.bodies[0] as Node3D).global_position.distance_to(lp)
			if d < 120.0:
				tl.append([d, tu])
		tl.sort_custom(func(a, b): return a[0] < b[0])
		_fill(_tram_slots, tl, "tram")


func _fill(slots: Array, cand: Array, key: String) -> void:
	var want: Array = []
	for i in mini(slots.size(), cand.size()):
		want.append(cand[i][1])
	# Plätze, deren Fahrzeug nicht mehr gewollt ist, freigeben
	for sl in slots:
		if sl[key] != null and (not is_instance_valid(sl[key]) or not want.has(sl[key])):
			sl[key] = null
	for v in want:
		var have := false
		for sl in slots:
			if sl[key] == v:
				have = true
				break
		if have:
			continue
		for sl in slots:
			if sl[key] == null:
				sl[key] = v
				break


func _ambience(lp: Vector3, delta: float) -> void:
	var night := env.night_value if env else 0.0
	var wet := float(EnvManager.WEATHER[env.weather][0]) if env else 0.0     # Regen (Zielnässe), nicht die Restnässe
	var green := 0.0
	if world:
		var t := world.tile_at(lp.x, lp.z)
		if t and t.terrain:
			var c := t.terrain.cover_at(lp.x, lp.z)
			green = clampf(maxf(c.r, c.g) * c.b, 0.0, 1.0)
	if _amb.has("amb_city_day"):
		_vol(_amb["amb_city_day"], 0.35 * (1.0 - night) * (1.0 - 0.6 * green))
	if _amb.has("amb_city_night"):
		_vol(_amb["amb_city_night"], 0.3 * night)
	if _amb.has("amb_park_day"):
		_vol(_amb["amb_park_day"], 0.4 * green * (1.0 - night))
	if _amb.has("amb_rain"):
		_vol(_amb["amb_rain"], 0.55 * clampf(wet * 1.3 - 0.2, 0.0, 1.0))
