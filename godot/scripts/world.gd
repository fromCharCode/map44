class_name World
extends Node3D
## Kachel-Streaming: lädt/entlädt 2x2-km-Kacheln um den Fokus (Spieler/Kamera).
## Der Aufbau einer Kachel läuft in einem Worker-Thread (eine Kachel gleichzeitig).

signal tile_added(tile: Tile)
signal tile_removed(tile: Tile)

static var quitting := false
const LOAD_R := 1500.0      # Abstand Fokus -> Kachelrand, ab dem geladen wird
const UNLOAD_R := 2700.0
var ATTACH_PER_FRAME := int(OS.get_environment("DRESDEN_ATTACH_N")) if OS.has_environment("DRESDEN_ATTACH_N") else 120

var noise: ImageTexture
var tiles := {}             # key -> Tile
var available := {}         # key -> true
var focus := Vector3.ZERO
var night := 0.0
var _thread: Thread
var _pending := ""
var _attaching := {}
var attach_log: Array = []   # Diagnose: in diesem Bild eingehängte Teile (DriveBench liest und leert)
var _result: Tile
var _now := ""              # Kachel, die load_now gerade im Haupt-Thread baut
var _hold := 0               # > 0: load_now wartet/baut – der Worker startet solange keine neue Kachel
var _timer := 0.0
var enabled := true


func setup(n: ImageTexture) -> void:
	noise = n
	scan()


func scan() -> void:
	var d := DirAccess.open(DataPaths.file("tiles"))
	if d == null:
		return
	for sub in d.get_directories():
		if FileAccess.file_exists(DataPaths.file("tiles/%s/city.json" % sub)):
			available[sub] = true


## Lädt eine Kachel sofort (für den Start, blockierend).
## Baut der Worker-Thread dieselbe Kachel gerade, wird auf ihn gewartet (frameweise – blockierendes Warten
## könnte den Worker aussperren, der für Mesh-Aufrufe den Haupt-Thread braucht), sonst gäbe es sie doppelt.
func load_now(key: String) -> void:
	if not available.has(key):
		return
	# Nie zwei Kacheln gleichzeitig bauen: Haupt-Thread und Worker teilen sich Zwischenspeicher (Materialien,
	# zerlegte Modelle), die beim ersten Gebrauch gefüllt werden – gleichzeitiger Aufbau führte zu seltenen
	# Abstürzen beim Start (signal 11 in parked_cars/_cars). Erst den laufenden Worker fertig werden lassen,
	# solange keinen neuen starten (_hold).
	_hold += 1
	while _thread != null or _pending == key or _attaching.has(key) or _now != "":
		await get_tree().process_frame
	if tiles.has(key):
		_hold -= 1
		return
	_now = key
	var t := Tile.new()
	t.build(key, noise)
	_now = ""
	_hold -= 1
	await _attach(t)


func _attach(t: Tile) -> void:
	if not t.ok:
		return
	if tiles.has(t.key) or _attaching.has(t.key):
		# Doppelbau (sollte nicht mehr vorkommen) verwerfen, samt noch nicht eingehängter Module
		for entry in t._mods:
			for c in entry[1]:
				(c as Node).free()
			(entry[0] as Node).free()
		push_warning("World: Kachel %s doppelt gebaut – verworfen" % t.key)
		t._mods.clear()
		t.free()
		return
	_attaching[t.key] = true
	var t_root := Time.get_ticks_usec()
	add_child(t)
	if OS.get_cmdline_user_args().has("--attachtrace"):
		print("Anhängen %s Wurzel: %d ms" % [t.key, (Time.get_ticks_usec() - t_root) / 1000])
	# Module über mehrere Frames einhängen (vermeidet einen großen Ruckler)
	var t0 := Time.get_ticks_usec()
	var n_frame := 0
	var trace := OS.has_environment("DRESDEN_TRACE") or OS.get_cmdline_user_args().has("--attachtrace")
	for entry in t._mods:
		var m: Node = entry[0]
		var ta := Time.get_ticks_usec()
		t.add_child(m)
		if trace and Time.get_ticks_usec() - ta > 15000:
			print("Anhängen %s/%s: %d ms" % [t.key, m.name, (Time.get_ticks_usec() - ta) / 1000])
		for c in entry[1]:
			var tc := Time.get_ticks_usec()
			m.add_child(c)
			if trace:
				attach_log.append("%s/%s(%s)" % [m.name, c.name, c.get_class()])
				_last_att[String(m.name)] = int(_last_att.get(String(m.name), 0)) + 1
				att0.append("%s/%s" % [m.name, c.name])
			if trace and Time.get_ticks_usec() - tc > 15000:
				print("Anhängen %s/%s/%s (%s, %d Kinder): %d ms" % [t.key, m.name, c.name, c.get_class(), c.get_child_count(), (Time.get_ticks_usec() - tc) / 1000])
			# Geländestücke und geparkte Autos kosten den Renderer im Folgebild ein Vielfaches (gemessen: 120 Geländestücke
			# = 200–400 ms, 120 Parkgruppen = 100 ms) – sie zählen deshalb mehrfach
			n_frame += int(ATTACH_COST.get(String(m.name), 1))
			# Zeit- UND Mengenbudget: die Renderer-Arbeit für neue Instanzen fällt erst im nächsten Bild an
			# (1000+ Geländestücke in einem Bild = 150–200 ms Ruckler)
			if Time.get_ticks_usec() - t0 > 2500 or n_frame >= ATTACH_PER_FRAME:
				var ty := Time.get_ticks_usec()
				await get_tree().process_frame
				if trace and Time.get_ticks_usec() - ty > 80000:
					print("Bild nach Anhängen %d ms (%d Stück): %s" % [(Time.get_ticks_usec() - ty) / 1000, n_frame, str(_last_att)])
				_last_att.clear()
				t0 = Time.get_ticks_usec()
				n_frame = 0
	t._mods.clear()
	tiles[t.key] = t
	_attaching.erase(t.key)
	if t.dressing:
		t.dressing.set_night(night)
	mark("tile_added " + t.key)
	if trace:
		var te := Time.get_ticks_usec()
		for cn in tile_added.get_connections():
			var tc2 := Time.get_ticks_usec()
			(cn["callable"] as Callable).call(t)
			if Time.get_ticks_usec() - tc2 > 8000:
				print("tile_added %s -> %s: %d ms" % [t.key, str(cn["callable"]), (Time.get_ticks_usec() - tc2) / 1000])
		print("tile_added %s gesamt %d ms" % [t.key, (Time.get_ticks_usec() - te) / 1000])
	else:
		tile_added.emit(t)


var _last_att := {}
static var att0: Array = []
static var ev: Array = []          # Diagnose: [Bildnummer, Ereignis]


static func mark(what: String) -> void:
	ev.append([Engine.get_process_frames(), what])
	if ev.size() > 400:
		ev = ev.slice(200)
static var att1: Array = []
static var att2: Array = []
const ATTACH_COST := {}          # Gewichtung je Modul (Messung 11/2026: die Ruckler hängen nicht an der Stückzahl)


func _dist_to_tile(key: String, p: Vector3) -> float:
	var parts := key.split("_")
	var c := Tile.center_of(int(parts[0]), int(parts[1]))
	var dx := maxf(absf(p.x - c.x) - 1000.0, 0.0)
	var dz := maxf(absf(p.z - c.y) - 1000.0, 0.0)
	return sqrt(dx * dx + dz * dz)


func _process(delta: float) -> void:
	att2 = att1
	att1 = att0
	att0 = []
	Dressing.clock += delta
	SignalCtl.clock = Dressing.clock
	RenderingServer.global_shader_parameter_set("signal_clock", Dressing.clock)
	if _thread and not _thread.is_alive():
		_thread.wait_to_finish()
		_thread = null
		var t := _result
		_result = null
		_pending = ""
		if t:
			mark("bau fertig " + t.key)
			_attach(t)
	_timer -= delta
	if _timer > 0.0 or not enabled:
		return
	_timer = 0.5
	# Entladen
	for k in tiles.keys():
		if _dist_to_tile(k, focus) > UNLOAD_R:
			var t: Tile = tiles[k]
			mark("entladen " + k)
			tile_removed.emit(t)
			tiles.erase(k)
			_unload(t)
	# Nächste fehlende Kachel laden
	if _thread == null and _hold == 0:
		var best := ""
		var best_d := LOAD_R
		for k in available:
			if tiles.has(k) or _attaching.has(k) or k == _now:
				continue
			var d := _dist_to_tile(k, focus)
			if d < best_d:
				best_d = d
				best = k
		if best != "":
			_pending = best
			mark("bau start " + best)
			_thread = Thread.new()
			_thread.start(_job.bind(best), Thread.PRIORITY_LOW)


func _job(key: String) -> void:
	var t := Tile.new()
	t.build(key, noise)
	_result = t


func all_loaded() -> bool:
	if _thread != null or not _attaching.is_empty():
		return false
	for k in available:
		if not tiles.has(k) and _dist_to_tile(k, focus) < LOAD_R:
			return false
	return true


func is_busy() -> bool:
	return _thread != null


func tile_at(x: float, z: float) -> Tile:
	return tiles.get(Tile.key_at(x, z))


func has_ground(x: float, z: float) -> bool:
	return tiles.has(Tile.key_at(x, z))


## Untergrund für die Fahrphysik: x = Reibwertfaktor, y = zusätzlicher Rollwiderstandsbeiwert, z = Rauheit (Rütteln)
func surface_at(x: float, z: float) -> Vector3:
	var t := tile_at(x, z)
	if t == null or t.terrain == null:
		return Vector3(1.0, 0.0, 0.0)
	var c := t.terrain.cover_at(x, z)
	if c.b < 0.5:
		# befestigt: Belag der nächsten Straße (OSM surface)
		if t.road_index:
			var h := t.road_index.nearest(x, z, 7.0)
			if not h.is_empty():
				match String((h["road"] as Dictionary).get("surf", "")):
					"kopfstein":
						return Vector3(0.84, 0.012, 1.0)
					"pflaster":
						return Vector3(0.93, 0.006, 0.45)
					"unbefestigt":
						return Vector3(0.72, 0.04, 0.6)
		return Vector3(1.0, 0.0, 0.0)
	if c.g > 0.45:
		return Vector3(0.62, 0.07, 0.8)          # Waldboden
	if c.r > 0.5:
		return Vector3(0.68, 0.05, 0.6)          # Wiese
	return Vector3(0.8, 0.03, 0.5)               # Erde/Schotter


func height_at(x: float, z: float) -> float:
	var t := tile_at(x, z)
	if t == null or t.terrain == null:
		return 0.0
	return t.terrain.height_at(x, z)


func nearest(x: float, z: float, max_d: float, pref_name: String = "") -> Dictionary:
	var t := tile_at(x, z)
	if t and t.road_index:
		var h := t.road_index.nearest(x, z, max_d, pref_name)
		if not h.is_empty():
			return h
	var best := {}
	for k in tiles:
		var tt: Tile = tiles[k]
		if tt == t:
			continue
		var h2 := tt.road_index.nearest(x, z, max_d, pref_name)
		if not h2.is_empty() and (best.is_empty() or h2["d"] < best["d"]):
			best = h2
	return best


func set_night(n: float) -> void:
	night = n
	for k in tiles:
		(tiles[k] as Tile).dressing.set_night(n)


func update_lights(f: Vector3, delta: float) -> void:
	for k in tiles:
		(tiles[k] as Tile).dressing.update_lights(f, delta)


func _unload(t: Tile) -> void:
	## Knoten zeitbudgetiert freigeben (ein großer queue_free würde ruckeln).
	var t0 := Time.get_ticks_usec()
	var n := 0
	for m in t.get_children():
		for c in m.get_children():
			m.remove_child(c)
			c.queue_free()
			n += 1
			if Time.get_ticks_usec() - t0 > 2500 or n >= ATTACH_PER_FRAME:
				await get_tree().process_frame
				t0 = Time.get_ticks_usec()
				n = 0
		t.remove_child(m)
		m.queue_free()
	t.queue_free()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST or what == NOTIFICATION_PREDELETE:
		_finish_thread()


func _exit_tree() -> void:
	_finish_thread()


func _finish_thread() -> void:
	quitting = true
	if _thread:
		_thread.wait_to_finish()
		_thread = null
