extends Node3D
## Dresden – Hauptprogramm: lädt die Welt, startet das Spiel.
##
## Entwickler-Optionen (nach "--"):
##   --shot=<pfad.png>        Screenshot nach N Frames, dann beenden
##   --frames=<n>             Frames bis zum Screenshot (Standard 120)
##   --cam=x,z,yaw,pitch,h    freie Kamera statt Spiel (Spielkoordinaten, Grad, Höhe über Boden)
##   --drive=x,z              Spielerstart an Position (nächste Straße)
##   --autodrive=<gas>        Gas-Test ohne Eingabe (nur mit --shot)
##   --time=<h>               Tageszeit, --quality=<0..2>, --traffic=<n>
##   --drivebench=<s>         Fahr-Leistungstest (scripts/dev/drive_bench.gd; --benchspeed, --benchabl, --attachtrace,
##                            --nostream, --nosdfgi), z. B. mit --resolution 3840x2160
##   --vehshot=<ordner>      Nahaufnahmen von Bussen/Bahnen (scripts/dev/veh_shot.gd; --vehkind=bus|tram)
##   --skidtest               Reifenspuren-Test (Vollgas, dann Handbremse + Einschlag), mit --shot/--street
##   --scale=<0.5..1>         3D-Auflösung (FSR2); ohne Angabe automatisch nach Bildschirmgröße

var world: World
var trams: Trams
var boats: Boats
var peds: Peds
var tree_lod: TreeLOD
var ground_cover: GroundCover
var pending_graphs: Array = []
var last_safe := Vector3.ZERO
var street_picker: StreetPicker
var _teleporting := false
var env_mgr: EnvManager
var traffic: Traffic
var player: PlayerCar
var cam_rig: CamRig
var hud: Hud
var audio: CarAudio
var world_audio: WorldAudio
var noise: ImageTexture
var args := {}
var frame := 0
var ready_to_play := false

var fly_cam: Camera3D
var fly_yaw := 0.0
var fly_pitch := 0.0

var loading_layer: CanvasLayer
var loading_label: Label
var loading_bar: ProgressBar
var pause_layer: CanvasLayer
var pause_buttons := {}
var pause_sliders := {}
var paused_menu := false
var auto_lights := true
var _was_night := false
var traffic_levels := [0, 25, 55, 90]
var traffic_i := 2
var test_t := 0.0
var ft: PackedFloat32Array = PackedFloat32Array()
var test_log_t := 0.0


func _ready() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.lstrip("-").split("=", true, 1)
		args[kv[0]] = kv[1] if kv.size() > 1 else "1"
	Controls.setup()
	PlayerCar.debug = args.has("dbg")
	_make_loading()
	await get_tree().process_frame
	await get_tree().process_frame
	await _build()


func _make_loading() -> void:
	loading_layer = CanvasLayer.new()
	loading_layer.layer = 100
	add_child(loading_layer)
	var bg := ColorRect.new()
	bg.color = Color(0.05, 0.06, 0.08)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	loading_layer.add_child(bg)
	var title := Label.new()
	title.text = "DRESDEN"
	title.add_theme_font_size_override("font_size", 72)
	title.set_anchors_preset(Control.PRESET_CENTER)
	title.position = Vector2(-140, -110)
	title.add_theme_color_override("font_color", Color(0.95, 0.9, 0.75))
	loading_layer.add_child(title)
	loading_label = Label.new()
	loading_label.text = "Lade ..."
	loading_label.add_theme_font_size_override("font_size", 22)
	loading_label.set_anchors_preset(Control.PRESET_CENTER)
	loading_label.position = Vector2(-200, 10)
	loading_label.custom_minimum_size = Vector2(400, 30)
	loading_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	loading_layer.add_child(loading_label)
	loading_bar = ProgressBar.new()
	loading_bar.set_anchors_preset(Control.PRESET_CENTER)
	loading_bar.position = Vector2(-200, 50)
	loading_bar.custom_minimum_size = Vector2(400, 14)
	loading_bar.show_percentage = false
	loading_bar.max_value = 100
	loading_layer.add_child(loading_bar)


func _stage(text: String, pct: float) -> void:
	loading_label.text = text
	loading_bar.value = pct
	await get_tree().process_frame


func _build() -> void:
	var t0 := Time.get_ticks_msec()
	EnvManager.register_globals()
	noise = TexLib.noise_texture(512, 0.02, 3)

	await _stage("Himmel und Licht ...", 12)
	env_mgr = EnvManager.new()
	env_mgr.name = "Env"
	add_child(env_mgr)
	env_mgr.hours = float(args.get("time", 17.0))
	env_mgr.quality = int(args.get("quality", 2))
	GameSettings.load_settings()
	env_mgr.render_scale = float(args.get("scale", GameSettings.render_scale))
	env_mgr.setup(noise)
	if args.has("weather"):
		env_mgr.set_weather(int(args["weather"]))
		env_mgr._wet = float(EnvManager.WEATHER[env_mgr.weather][0])

	await _stage("Modelle vorbereiten ...", 8)
	TexLib.prewarm()              # gemeinsame, komprimierte Texturen (Plattencache user://texcache)
	ParkedCars.prewarm()          # Modelle einmal im Haupt-Thread zerlegen; der Kachel-Thread liest nur
	Dressing.prewarm()
	StreetLife.prewarm()
	Stops.prewarm()
	CarModel.glass_material()
	world = World.new()
	world.name = "World"
	# Physik-Interpolation nur für Körper, die im Physikschritt bewegt werden. Statische Kachelinhalte und alles,
	# was in _process umgesetzt wird (Baum-LOD-Plätze, Fußgänger, Dampfer), sonst gleitet ein umgesetzter
	# MultiMesh-Platz einen Physikschritt lang quer durchs Bild (Baum „auf der Straße“ bei hoher Geschwindigkeit).
	world.physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_OFF
	add_child(world)
	world.setup(noise)
	trams = Trams.new()
	trams.name = "Trams"
	add_child(trams)
	trams.init(int(args.get("trams", 8)))
	boats = Boats.new()
	boats.name = "Boats"
	boats.physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_OFF
	add_child(boats)
	boats.setup(int(args.get("boats", 6)))
	tree_lod = TreeLOD.new()
	tree_lod.name = "TreeLOD"
	tree_lod.physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_OFF
	add_child(tree_lod)
	tree_lod.setup()
	ground_cover = GroundCover.new()
	ground_cover.name = "GroundCover"
	ground_cover.physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_OFF
	add_child(ground_cover)
	peds = Peds.new()
	peds.name = "Peds"
	peds.physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_OFF
	add_child(peds)
	peds.setup(world)
	peds.target_count = int(args.get("peds", 80))
	world.tile_added.connect(_on_tile_added)
	world.tile_removed.connect(_on_tile_removed)

	if args.has("street"):
		var found := _find_street(String(args["street"]))
		if found.size() == 2:
			args["drive"] = "%f,%f" % [found[0], found[1]]
	var sx := 494.0
	var sz := 60.0
	if args.has("cam"):
		var c0: PackedStringArray = String(args["cam"]).split(",")
		sx = float(c0[0])
		sz = float(c0[1])
	elif args.has("drive") and String(args["drive"]).contains(","):
		var d0: PackedStringArray = String(args["drive"]).split(",")
		sx = float(d0[0])
		sz = float(d0[1])
	world.focus = Vector3(sx, 0.0, sz)
	await _stage("Stadtteil laden ...", 30)
	var k0 := Tile.key_at(sx, sz)
	if not world.available.has(k0):
		push_error("Keine Kachel %s unter dem Startpunkt" % k0)
	await world.load_now(k0)

	if args.has("cam"):
		_setup_fly()
		if args.has("perf"):
			var pr := PerfRun.new()
			pr.name = "PerfRun"
			add_child(pr)
			pr.call_deferred("start", self, fly_cam, env_mgr, args)
	else:
		await _stage("Taxi und Verkehr bereitstellen ...", 92)
		_setup_game()
		if args.has("trafficbench"):
			var tb := TrafficBench.new()
			tb.name = "TrafficBench"
			add_child(tb)
			tb.start(self, traffic, float(args["trafficbench"]))
			if args.has("crashai"):
				tb.crash_at = float(args["crashai"])
			if args.has("benchcam"):
				tb.setup_cam(String(args["benchcam"]), String(args.get("benchshots", "")))
				tb.shot_every = float(args.get("shotevery", 20.0))

	if args.has("crashtest") and player:
		var fw := -player.global_transform.basis.z
		fw.y = 0.0
		fw = fw.normalized()
		var dist := float(args.get("crashdist", 45.0))
		var wall := StaticBody3D.new()
		wall.collision_layer = 1
		var wcs := CollisionShape3D.new()
		var wbs := BoxShape3D.new()
		wbs.size = Vector3(14.0, 5.0, 1.0)
		wcs.shape = wbs
		wall.add_child(wcs)
		add_child(wall)
		var ppos := player.global_position
		wall.global_transform = Transform3D(Basis.looking_at(fw, Vector3.UP), ppos + fw * dist + Vector3(0, 2.0, 0))
		var vis := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = wbs.size
		vis.mesh = bm
		wall.add_child(vis)
		player.linear_velocity = fw * float(args["crashtest"])
		player.in_throttle = 0.0
		player.override_input = true
		print("Crash-Test: Wand bei ", wall.global_position)
	if args.has("dmgtest") and player:
		var lvl := float(args["dmgtest"])
		player.damage.impact(Vector3(0.35, 0.65, -2.35), Vector3(0, 0, 1), 7.0 * lvl)
		player.damage.impact(Vector3(-0.5, 0.7, -2.2), Vector3(0.3, 0, 1), 9.0 * lvl)
		player.damage.impact(Vector3(1.0, 0.75, 0.3), Vector3(-1, 0, 0), 8.0 * lvl)
		player.damage.impact(Vector3(-0.9, 0.9, -0.4), Vector3(1, 0, 0), 6.0 * lvl)
		player.damage.impact(Vector3(0.3, 0.7, 2.3), Vector3(0, 0, -1), 6.0 * lvl)
		player._apply_damage_effects()
		var dc := Camera3D.new()
		add_child(dc)
		dc.global_position = player.global_transform * Vector3(-3.4, 1.7, -4.2)
		dc.look_at(player.global_position + Vector3(0, 0.7, 0), Vector3.UP)
		dc.make_current()
	if args.has("bridgetest"):
		await _bridge_test()
	await _stage("Fertig", 100)
	print("Aufbau gesamt: %d ms" % (Time.get_ticks_msec() - t0))
	loading_layer.queue_free()
	ready_to_play = true


func _setup_fly() -> void:
	fly_cam = Camera3D.new()
	fly_cam.name = "FlyCam"
	fly_cam.far = 4000.0
	fly_cam.fov = 70.0
	add_child(fly_cam)
	fly_cam.make_current()
	var c: PackedStringArray = String(args.get("cam", "494,60,180,-8,1.8")).split(",")
	var cx := float(c[0])
	var cz := float(c[1])
	fly_yaw = deg_to_rad(float(c[2]) if c.size() > 2 else 0.0)
	fly_pitch = deg_to_rad(float(c[3]) if c.size() > 3 else 0.0)
	var h_off := float(c[4]) if c.size() > 4 else 1.8
	fly_cam.position = Vector3(cx, world.height_at(cx, cz) + h_off, cz)
	fly_cam.rotation = Vector3(fly_pitch, fly_yaw, 0.0)
	if args.has("tramcam") and trams.trams.size() > 0:
		var tu: TramUnit = trams.trams[0]
		var hp := trams.way_point(tu.way, tu.s)
		var ahead := Vector3(tu.system.way_dir(tu.way, tu.s, tu.dir).x, 0, tu.system.way_dir(tu.way, tu.s, tu.dir).y)
		var side := Vector3(-ahead.z, 0, ahead.x)
		fly_cam.global_position = hp + ahead * 16.0 + side * 9.0 + Vector3(0, 2.4, 0)
		fly_cam.look_at(hp - ahead * 14.0 + Vector3(0, 1.8, 0), Vector3.UP)
		print("Tram bei ", hp, " Abschnitte: ", tu.bodies.size(), " Offsets: ", tu.offsets)
	if not args.has("shot") and not args.has("perf"):
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _find_street(q: String) -> Array:
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(DataPaths.file("streets.json")))
	if not (parsed is Array):
		return []
	var ql := q.to_lower()
	var best: Array = []
	var best_d := 1e9
	for s in parsed:
		var nl: String = String(s[0]).to_lower()
		if nl == ql or nl.contains(ql):
			var d: float = float(s[3]) + (0.0 if nl == ql else 1000.0)
			if d < best_d:
				best_d = d
				best = [float(s[1]), float(s[2])]
	return best


func _teleport_to(x: float, z: float, label: String) -> void:
	if _teleporting or player == null:
		return
	_teleporting = true
	var cover := ColorRect.new()
	cover.color = Color(0.05, 0.06, 0.08, 0.92)
	cover.set_anchors_preset(Control.PRESET_FULL_RECT)
	var lab := Label.new()
	lab.text = "Lade %s ..." % label
	lab.add_theme_font_size_override("font_size", 28)
	lab.set_anchors_preset(Control.PRESET_CENTER)
	lab.position = Vector2(-160, -20)
	cover.add_child(lab)
	var cl := CanvasLayer.new()
	cl.layer = 90
	cl.add_child(cover)
	add_child(cl)
	await get_tree().process_frame
	await get_tree().process_frame
	world.enabled = false
	while world.is_busy() or not world._attaching.is_empty():
		await get_tree().process_frame
	var k := Tile.key_at(x, z)
	if world.available.has(k) and not world.tiles.has(k):
		await world.load_now(k)
	world.focus = Vector3(x, 0.0, z)
	var sp := _spawn_point_near(Vector2(x, z), label)
	player.linear_velocity = Vector3.ZERO
	player.angular_velocity = Vector3.ZERO
	player.global_transform = Transform3D(Basis(Vector3.UP, sp[1]), sp[0])
	player.reset_physics_interpolation()
	last_safe = player.global_position
	cam_rig._started = false
	world.enabled = true
	cl.queue_free()
	_teleporting = false
	if hud:
		hud.message("Hier: " + label, 3.0)


func _bridge_test() -> void:
	## Entwicklertest: schiebt ein autogroßes Kollisionsvolumen über jede Fahrbrücke der geladenen Kacheln.
	var keys: Array = world.available.keys()
	keys.sort_custom(func(a, b): return world._dist_to_tile(a, Vector3.ZERO) < world._dist_to_tile(b, Vector3.ZERO))
	var maxn := int(args.get("bridgetest", 12))
	var bad_total := 0
	var count := 0
	for k in keys.slice(0, maxn):
		if not world.tiles.has(k):
			await world.load_now(k)
		var tile: Tile = world.tiles.get(k)
		if tile == null:
			continue
		await get_tree().physics_frame
		await get_tree().physics_frame
		var space := get_viewport().world_3d.direct_space_state
		var tl: Array = []
		for r in tile.city["roads"]:
			if r["bridge"] and String(r["cls"]) not in ["footway", "path", "cycleway", "steps", "pedestrian", "bridleway"]:
				tl.append(r)
		for b in tl:
			count += 1
			var pts: Array = b["pts"]
			var blocked := 0
			var first := ""
			var acc := 0.0
			for i in pts.size() - 1:
				var a := Vector3(pts[i][0], pts[i][2], pts[i][1])
				var c := Vector3(pts[i + 1][0], pts[i + 1][2], pts[i + 1][1])
				var seg := a.distance_to(c)
				var dir := (c - a).normalized()
				var n := int(seg / 2.0) + 1
				for j in n:
					var p := a.lerp(c, float(j) / n)
					var bs := BoxShape3D.new()
					bs.size = Vector3(1.8, 0.7, 4.0)
					var q := PhysicsShapeQueryParameters3D.new()
					q.shape = bs
					q.collision_mask = 1
					var basis := Basis.looking_at(Vector3(dir.x, 0, dir.z).normalized(), Vector3.UP)
					q.transform = Transform3D(basis, p + Vector3(0, 0.75, 0))
					var hits := space.intersect_shape(q, 4)
					if hits.size() > 0:
						blocked += 1
						if first == "":
							var col: Object = hits[0]["collider"]
							first = "bei (%.0f,%.0f,y=%.1f) %s" % [p.x, p.z, p.y, String(col.get_parent().name) + "/" + String(col.name)]
					# Boden unter dem Fahrzeug: Deck muss tragen
					var rq := PhysicsRayQueryParameters3D.create(p + Vector3(0, 1.5, 0), p - Vector3(0, 2.0, 0), 1)
					var rh := space.intersect_ray(rq)
					if rh.is_empty() or absf(rh["position"].y - p.y) > 0.5:
						blocked += 1
						if first == "":
							first = "kein Boden bei (%.0f,%.0f) Soll y=%.1f ist %s" % [p.x, p.z, p.y, "keiner" if rh.is_empty() else "%.1f" % rh["position"].y]
				acc += seg
			if blocked > 0:
				bad_total += 1
				print("BRÜCKE KAPUTT %s id=%s Länge %.0f m, %d Stellen, erste: %s" % [k, str(b["id"]), acc, blocked, first])
	print("BRÜCKENTEST: %d Brücken geprüft, %d auffällig" % [count, bad_total])
	get_tree().quit()


func _on_tile_added(tile: Tile) -> void:
	var t0 := Time.get_ticks_usec()
	var tr := OS.get_cmdline_user_args().has("--attachtrace")
	peds.add_tile(tile)
	if tr: print("tile_added %s: peds %.1f ms" % [tile.key, (Time.get_ticks_usec() - t0) / 1000.0])
	t0 = Time.get_ticks_usec()
	tree_lod.register(tile.dressing)
	ground_cover.add_terrain(tile.terrain)
	var stops: Array = []
	for fu in tile.city.get("life", {}).get("furniture", []):
		if String(fu[0]) == "stop_pole":
			stops.append(Vector2(float(fu[1]), float(fu[2])))
	for m in tile.city.get("stops", {}).get("masts", []):
		if String(m[6]) == "tram":
			stops.append(Vector2(float(m[0]), float(m[1])))
	trams.add_rails(tile.terrain, tile.city["rails"], tile.tram_container, tile.city.get("tram_poles", []), stops)
	if tr: print("tile_added %s: tram %.1f ms" % [tile.key, (Time.get_ticks_usec() - t0) / 1000.0])
	t0 = Time.get_ticks_usec()
	if traffic:
		traffic.add_graph(tile.city["graph"], tile.key)
	else:
		pending_graphs.append([tile.city["graph"], tile.key])
	if tr: print("tile_added %s: graph %.1f ms" % [tile.key, (Time.get_ticks_usec() - t0) / 1000.0])


func _on_tile_removed(tile: Tile) -> void:
	peds.remove_tile(tile)
	tree_lod.unregister(tile.dressing)
	ground_cover.remove_terrain(tile.terrain)


func _spawn_point() -> Array:
	var start := Vector2(494.0, 60.0)
	if args.has("drive") and String(args["drive"]).contains(","):
		var d: PackedStringArray = String(args["drive"]).split(",")
		start = Vector2(float(d[0]), float(d[1]))
	var hit: Dictionary = world.nearest(start.x, start.y, 120.0, String(args.get("street", "")))
	if hit.is_empty():
		return [Vector3(start.x, world.height_at(start.x, start.y) + 1.0, start.y), 0.0]
	var t := Vector2(hit["tx"], hit["tz"])
	var n := Vector2(-t.y, t.x)
	var p := Vector2(hit["px"], hit["pz"]) + n * minf(float(hit["road"]["width"]) * 0.22, 1.8)
	var yaw := atan2(-t.x, -t.y)
	var py: float = float(hit["py"]) + 0.9 if bool(hit["bridge"]) else world.height_at(p.x, p.y) + 0.9
	return [Vector3(p.x, py, p.y), yaw]


func _setup_game() -> void:
	player = PlayerCar.new()
	player.name = "Taxi"
	add_child(player)
	player.setup()
	var sp := _spawn_point()
	player.global_transform = Transform3D(Basis(Vector3.UP, sp[1]), sp[0])
	if args.has("autodrive"):
		player.override_input = true
		player.in_throttle = float(args["autodrive"])
		player.in_steer = float(args.get("steerval", 0.0))
	cam_rig = CamRig.new()
	cam_rig.name = "CamRig"
	add_child(cam_rig)
	cam_rig.setup(player)
	cam_rig.cam.make_current()
	var skid := SkidFX.new()
	skid.name = "SkidFX"
	add_child(skid)
	skid.setup(player)
	cam_rig.mode = int(args.get("camera", 0))

	traffic = Traffic.new()
	traffic.name = "Traffic"
	add_child(traffic)
	traffic.setup(world, Dressing.new(), player, cam_rig.cam)
	Departures.traffic = traffic
	Departures.trams = trams
	for g in pending_graphs:
		traffic.add_graph(g[0], g[1])
	pending_graphs.clear()
	traffic.target_count = int(args.get("traffic", traffic_levels[traffic_i]))
	traffic.bus_target = int(args.get("buses", 7))
	if args.has("aisync"):
		AICar.sync_phys = args["aisync"] == "1"
	traffic.trams = trams

	audio = CarAudio.new()
	audio.name = "Audio"
	add_child(audio)
	audio.setup(player)
	world_audio = WorldAudio.new()
	world_audio.name = "WorldAudio"
	add_child(world_audio)
	world_audio.setup(traffic, trams, cam_rig.cam, env_mgr, world)
	if args.has("drivebench"):
		var db := DriveBench.new()
		db.name = "DriveBench"
		add_child(db)
		db.start(self, player, traffic, world, args)
		AudioServer.set_bus_mute(0, true)
	if args.has("vehshot"):
		var vs := VehShot.new()
		vs.name = "VehShot"
		add_child(vs)
		vs.start(self, args)
		AudioServer.set_bus_mute(0, true)
	if args.has("shot") or args.has("trafficbench"):
		audio.volume = 0.0
		audio.set_muted(true)

	var layer := CanvasLayer.new()
	layer.layer = 5
	add_child(layer)
	hud = Hud.new()
	layer.add_child(hud)
	hud.car = player
	hud.env_mgr = env_mgr
	hud.traffic = traffic
	hud.index = world
	hud.world = world
	hud.cam_rig = cam_rig
	street_picker = StreetPicker.new()
	street_picker.name = "StreetPicker"
	add_child(street_picker)
	street_picker.chosen.connect(_teleport_to)
	_make_pause_menu()
	if not args.has("shot"):
		hud.message("Los geht's!  R = zurücksetzen · C = Kamera · L = Licht · M = Karte", 5.0)
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
		if Controls.steam_controller_desktop_mode():
			hud.message("Steam Controller im Desktop-Modus: Spiel über Steam mit Layout „Gamepad“ starten (F1 zeigt wie) · Notbehelf RT/LT = Gas/Bremse", 9.0)


func _make_pause_menu() -> void:
	pause_layer = CanvasLayer.new()
	pause_layer.layer = 50
	pause_layer.process_mode = Node.PROCESS_MODE_ALWAYS
	pause_layer.visible = false
	add_child(pause_layer)
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.55)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	pause_layer.add_child(dim)
	var panel := PanelContainer.new()
	panel.set_anchors_preset(Control.PRESET_CENTER)
	panel.position = Vector2(-200, -330)
	panel.custom_minimum_size = Vector2(400, 660)
	pause_layer.add_child(panel)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	panel.add_child(box)
	var title := Label.new()
	title.text = "Pause"
	title.add_theme_font_size_override("font_size", 34)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(title)
	for def in [["resume", "Weiter"], ["time", ""], ["weather", ""], ["quality", ""], ["scale", ""], ["traffic", ""], ["damage", ""], ["repair", "Auto reparieren (F5)"], ["input", "Eingabetest (Controller)"], ["quit", "Beenden"]]:
		var b := Button.new()
		b.text = def[1]
		b.custom_minimum_size = Vector2(0, 46)
		b.add_theme_font_size_override("font_size", 22)
		box.add_child(b)
		pause_buttons[def[0]] = b
		b.pressed.connect(_on_pause_button.bind(def[0]))
		if def[0] == "resume":
			# Lautstärke direkt unter "Weiter"
			GameSettings.load_settings()
			for sdef in [["master", "Lautstärke gesamt", GameSettings.master_volume], ["vehicle", "Lautstärke Fahrzeug", GameSettings.vehicle_volume]]:
				var row := HBoxContainer.new()
				var lb := Label.new()
				lb.custom_minimum_size = Vector2(190, 0)
				lb.add_theme_font_size_override("font_size", 18)
				row.add_child(lb)
				var sl := HSlider.new()
				sl.min_value = 0
				sl.max_value = 100
				sl.step = 5
				sl.value = roundf(float(sdef[2]) * 100.0)
				sl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
				sl.custom_minimum_size = Vector2(0, 32)
				sl.focus_mode = Control.FOCUS_ALL
				row.add_child(sl)
				box.add_child(row)
				pause_sliders[sdef[0]] = [sl, lb, sdef[1]]
				sl.value_changed.connect(_on_volume.bind(sdef[0]))
				_on_volume(sl.value, sdef[0], false)
	var hint := Label.new()
	hint.text = "RT Gas · LT Bremse/Rückwärts · linker Stick lenken · rechter Stick umsehen · RB Handbremse · LB zurückschauen\nA/X hoch-/runterschalten · B Reset (2× = reparieren) · Y Kamera · L3 Hupe · R3 Automatik/Manuell\nSteuerkreuz ↑ Licht · ↓ Karte · ←/→ Tageszeit · Start Pause"
	hint.add_theme_font_size_override("font_size", 13)
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD
	box.add_child(hint)
	_refresh_pause_labels()


func _on_volume(v: float, id: String, save: bool = true) -> void:
	if id == "master":
		GameSettings.master_volume = v / 100.0
	else:
		GameSettings.vehicle_volume = v / 100.0
	GameSettings.apply_audio()
	var e: Array = pause_sliders.get(id, [])
	if not e.is_empty():
		(e[1] as Label).text = "%s: %d %%" % [e[2], int(v)]
	if save:
		GameSettings.save_settings()


func _refresh_pause_labels() -> void:
	var h := int(env_mgr.hours)
	pause_buttons["time"].text = "Tageszeit: %02d:00  (+3 Std.)" % h
	pause_buttons["quality"].text = "Grafik: " + ["Niedrig", "Mittel", "Hoch"][env_mgr.quality]
	pause_buttons["weather"].text = "Wetter: " + EnvManager.WEATHER_NAMES[env_mgr.weather] + " (F6)"
	var esc := env_mgr.effective_scale()
	pause_buttons["scale"].text = "Auflösung: %s%d %%%s" % ["Auto " if env_mgr.render_scale <= 0.0 else "", int(round(esc * 100.0)), " (FSR2)" if esc < 0.99 else " (nativ)"]
	pause_buttons["traffic"].text = "Verkehr: " + ["Leer", "Wenig", "Normal", "Dicht"][traffic_i]
	pause_buttons["damage"].text = "Schaden: " + ("An" if player.damage_enabled else "Aus") + " (F4)"


func _on_pause_button(id: String) -> void:
	match id:
		"resume":
			_toggle_pause()
		"time":
			env_mgr.set_time(floorf(env_mgr.hours) + 3.0)
		"quality":
			env_mgr.apply_quality((env_mgr.quality + 1) % 3)
		"weather":
			env_mgr.set_weather(env_mgr.weather + 1)
		"scale":
			var steps := [-1.0, 1.0, 0.85, 0.77, 0.67, 0.5]
			var cur := 0
			for i in steps.size():
				if absf(steps[i] - env_mgr.render_scale) < 0.01:
					cur = i
			env_mgr.set_render_scale(steps[(cur + 1) % steps.size()])
			GameSettings.render_scale = env_mgr.render_scale
			GameSettings.save_settings()
		"traffic":
			traffic_i = (traffic_i + 1) % 4
			traffic.target_count = traffic_levels[traffic_i]
		"damage":
			player.damage_enabled = not player.damage_enabled
		"repair":
			player.repair()
			hud.message("Auto repariert", 2.0)
		"input":
			hud.show_input = true
			_toggle_pause()
		"quit":
			get_tree().quit()
	_refresh_pause_labels()


func _toggle_pause() -> void:
	paused_menu = not paused_menu
	get_tree().paused = paused_menu
	pause_layer.visible = paused_menu
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE if paused_menu else Input.MOUSE_MODE_CAPTURED
	if paused_menu:
		_refresh_pause_labels()
		(pause_buttons["resume"] as Button).grab_focus()


func _process(delta: float) -> void:
	if env_mgr:
		Departures.hours = env_mgr.hours
	frame += 1
	if not ready_to_play:
		return
	world.set_night(env_mgr.night_value)
	var focus := Vector3.ZERO
	if player:
		focus = player.global_position
	elif fly_cam:
		focus = fly_cam.global_position
	if Input.is_action_just_pressed("street_picker") and street_picker and not paused_menu:
		street_picker.toggle()
	world.focus = focus
	world.update_lights(focus, delta)
	trams.focus = focus
	boats.focus = focus
	peds.focus = focus
	# Detailstufen in Fahrtrichtung vorausschauen (bei 120 km/h ~40 m), damit nahe Bäume/Bewuchs nicht nachhinken
	var ahead := focus
	if player:
		var hv := Vector3(player.linear_velocity.x, 0.0, player.linear_velocity.z) * 1.2
		ahead = focus + hv.limit_length(45.0)
	tree_lod.focus = ahead
	tree_lod.set_quality(env_mgr.quality)
	ground_cover.focus = ahead
	ground_cover.enabled = env_mgr.quality >= 1

	if args.has("skidtest") and player:
		# Entwicklertest Reifenspuren: 3 s Vollgas, dann Handbremse + voller Einschlag, Bild aus der Verfolgerkamera
		test_t += delta
		player.override_input = true
		player.in_throttle = 1.0 if test_t < 3.5 else 0.3
		player.in_steer = 0.0 if test_t < 3.5 else 1.0
		player.in_handbrake = test_t >= 3.5 and test_t < 5.0
	if args.has("shot") and frame >= int(args.get("frames", 120)) + 30 and world.all_loaded():
		if args.has("probe"):
			Probe.run(self, String(args["probe"]))
		var img := get_viewport().get_texture().get_image()
		img.save_png(String(args["shot"]))
		var extra := ""
		if player:
			var moving := 0
			var vsum := 0.0
			for c in traffic.cars:
				vsum += (c as AICar).speed
				if (c as AICar).speed > 1.0:
					moving += 1
			extra = " v=%.1f km/h gear=%d rpm=%d grounded=%d cars=%d (fahrend %d, Ø %.1f km/h)" % [player.get_speed_kmh(), player.gear, player.rpm, player.grounded, traffic.cars.size(), moving, vsum / maxf(traffic.cars.size(), 1) * 3.6]
			extra += " peds=%d pfade=%d" % [peds.peds.size(), peds.cells.size()]
			if player.damage:
				extra += " SCHADEN=%.2f vorn=%.2f glas=%d" % [player.damage.total, player.damage.front, player.damage.glass_level]
		print("Screenshot gespeichert: ", args["shot"], " FPS: ", Engine.get_frames_per_second(), extra, "  GroundCover: Zellen ", ground_cover.built, " Pflanzen ", ground_cover.placed, " Kacheln ", ground_cover.terrains.size())
		get_tree().quit()
		return

	if args.has("coltest"):
		_collision_test()
		return
	if fly_cam:
		_fly(delta)
		return
	if player == null:
		return
	if args.has("drivetest"):
		_drive_test(delta)
		return

	if Input.is_action_just_pressed("inputtest"):
		hud.show_input = not hud.show_input
	_check_player_bounds()
	# Spiel-Eingaben
	if Input.is_action_just_pressed("pause"):
		_toggle_pause()
	if Input.is_action_just_pressed("weather") and hud:
		env_mgr.set_weather(env_mgr.weather + 1)
		hud.message("Wetter: " + EnvManager.WEATHER_NAMES[env_mgr.weather], 2.0)
	if paused_menu:
		return
	if Input.is_action_just_pressed("camera"):
		cam_rig.cycle_mode()
		hud.message(CamRig.MODE_NAMES[cam_rig.mode], 1.2)
	if Input.is_action_just_pressed("lights"):
		player.lights_on = not player.lights_on
		auto_lights = false
	if Input.is_action_just_pressed("reset"):
		player.reset_upright()
	if Input.is_action_just_pressed("repair"):
		player.repair()
		hud.message("Auto repariert", 2.0)
	if Input.is_action_just_pressed("damage_toggle"):
		player.damage_enabled = not player.damage_enabled
		hud.message("Schaden: " + ("an" if player.damage_enabled else "aus"), 2.0)
	if Input.is_action_just_pressed("map"):
		hud.minimap.big = not hud.minimap.big
	if Input.is_action_pressed("time_forward"):
		env_mgr.set_time(env_mgr.hours + delta * 1.2)
	if Input.is_action_pressed("time_back"):
		env_mgr.set_time(env_mgr.hours - delta * 1.2)
	if Input.is_action_just_pressed("quality"):
		env_mgr.apply_quality((env_mgr.quality + 1) % 3)
		hud.message("Grafik: " + ["Niedrig", "Mittel", "Hoch"][env_mgr.quality], 1.5)
	var night := env_mgr.night_value > 0.35
	if night != _was_night:
		_was_night = night
		if auto_lights:
			player.lights_on = night
		else:
			auto_lights = true
			player.lights_on = night
	traffic.set_night(env_mgr.night_value)
	traffic.rain = env_mgr._wet
	if player:
		player.world_ref = world
		player.grip = lerpf(1.0, 0.78, clampf(env_mgr._wet, 0.0, 1.0))
	trams.set_night(env_mgr.night_value)


func _fly(delta: float) -> void:
	if args.has("shot"):
		return
	var v := Vector3.ZERO
	if Input.is_key_pressed(KEY_W): v.z -= 1
	if Input.is_key_pressed(KEY_S): v.z += 1
	if Input.is_key_pressed(KEY_A): v.x -= 1
	if Input.is_key_pressed(KEY_D): v.x += 1
	if Input.is_key_pressed(KEY_E): v.y += 1
	if Input.is_key_pressed(KEY_Q): v.y -= 1
	var spd := 12.0 * (4.0 if Input.is_key_pressed(KEY_SHIFT) else 1.0)
	fly_cam.position += fly_cam.global_transform.basis * v * spd * delta
	if Input.is_key_pressed(KEY_T):
		env_mgr.set_time(env_mgr.hours + delta * 2.0)


func _unhandled_input(event: InputEvent) -> void:
	if fly_cam and event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		fly_yaw -= event.relative.x * 0.003
		fly_pitch = clampf(fly_pitch - event.relative.y * 0.003, -1.5, 1.5)
		fly_cam.rotation = Vector3(fly_pitch, fly_yaw, 0.0)
	if fly_cam and event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED else Input.MOUSE_MODE_CAPTURED


func _drive_test(delta: float) -> void:
	## Automatischer Fahrtest: Gas, Kurve, Vollbremsung, Rückwärts. Ausgabe als Zahlen.
	test_t += delta
	player.override_input = true
	var t := test_t
	var thr := 0.0
	var brk := 0.0
	var st := 0.0
	if args.has("straight"):
		thr = 0.9 if t < 14.0 else 0.0
		if t >= 16.0:
			_print_frame_stats()
			get_tree().quit()
		player.in_throttle = thr
		player.in_steer = 0.0
		if int(t * 2.0) != int((t - delta) * 2.0) and int(t * 2.0) % 2 == 0:
			print("S t=%4.1f v=%6.1f km/h gang=%d rpm=%d kr=%.2f" % [t, player.get_speed_kmh(), player.gear, player.rpm, player._kappa_rear])
			if args.has("dbg"):
				print("   ", player.dbg)
		if t > 3.0:
			ft.append(delta)
			if delta > 0.025:
				print("SPIKE t=%.2f %.0f ms busy=%s attaching=%d tiles=%d" % [t, delta * 1000.0, world.is_busy(), world._attaching.size(), world.tiles.size()])
		return
	if t < 6.0:
		thr = 1.0
	elif t < 10.0:
		thr = 0.55
		st = 0.45
	elif t < 12.0:
		thr = 0.7
		st = -0.9
	elif t < 15.0:
		brk = 1.0
	elif t < 18.0:
		brk = 1.0          # Rückwärts
	else:
		print("JITTER=%.5f m/s je Physikschritt" % player.jitter)
		get_tree().quit()
	player.in_throttle = thr
	player.in_brake = brk
	player.in_steer = st
	test_log_t -= delta
	if test_log_t <= 0.0:
		test_log_t = 0.5
		var b := player.global_transform.basis
		var roll := rad_to_deg(asin(clampf(b.x.y, -1.0, 1.0)))
		var pitch := rad_to_deg(asin(clampf(-b.z.y, -1.0, 1.0)))
		var lat := player.linear_velocity.dot(b.x)
		print("t=%4.1f v=%6.1f km/h  vlat=%5.2f  gier=%6.1f°/s  roll=%5.1f°  nick=%5.1f°  gang=%d  rpm=%4d  räder=%d  y=%.2f" % [t, player.get_speed_kmh() * signf(player.speed), lat, rad_to_deg(player.angular_velocity.y), roll, pitch, player.gear, player.rpm, player.grounded, player.global_position.y])
		if args.has("dbg"):
			print("   ", player.dbg)


func _print_frame_stats() -> void:
	var a := Array(ft)
	a.sort()
	if a.is_empty():
		return
	var sum := 0.0
	for v in a:
		sum += v
	print("FRAMEZEIT: Ø %.2f ms · p99 %.2f ms · max %.2f ms · Ausreißer(>25ms): %d von %d" % [sum / a.size() * 1000.0, a[int(a.size() * 0.99)] * 1000.0, a[a.size() - 1] * 1000.0, a.filter(func(x): return x > 0.025).size(), a.size()])


var _coltest_done := false
func _collision_test() -> void:
	## Vergleicht die Physik-Oberfläche mit der Geländehöhe an vielen Punkten.
	if _coltest_done or frame < 20:
		return
	_coltest_done = true
	var space := get_world_3d().direct_space_state
	var rng := RandomNumberGenerator.new()
	rng.seed = 5
	var bad := 0
	var total := 0
	var worst := 0.0
	var pts: Array = []
	for i in 400:
		pts.append(Vector2(rng.randf_range(-990, 990), rng.randf_range(-990, 990)))
	for p in pts:
		var q := PhysicsRayQueryParameters3D.create(Vector3(p.x, 200.0, p.y), Vector3(p.x, -200.0, p.y), 1)
		var hit := space.intersect_ray(q)
		if hit.is_empty():
			print("KEIN TREFFER bei ", p)
			bad += 1
			continue
		total += 1
		var vis := world.height_at(p.x, p.y)
		var phys: float = hit["position"].y
		# Treffer auf Gebäuden/Mauern ignorieren (liegen über dem Gelände)
		if phys > vis + 0.5:
			continue
		var diff := absf(phys - vis)
		worst = maxf(worst, diff)
		if diff > 0.35:
			bad += 1
			if bad <= 12:
				print("ABWEICHUNG bei (%.0f, %.0f): sichtbar %.2f  Physik %.2f" % [p.x, p.y, vis, phys])
	print("KOLLISIONSTEST: %d Punkte, %d auffällig, größte Abweichung %.2f m" % [total, bad, worst])
	get_tree().quit()


func _check_player_bounds() -> void:
	if player == null:
		return
	var p := player.global_position
	var has := world.has_ground(p.x, p.z)
	if has and p.y > world.height_at(p.x, p.z) - 6.0 and p.y < 600.0:
		last_safe = p
		return
	var target := last_safe if last_safe != Vector3.ZERO else p
	var sp := _spawn_point_near(Vector2(target.x, target.z))
	player.linear_velocity = Vector3.ZERO
	player.angular_velocity = Vector3.ZERO
	player.global_transform = Transform3D(Basis(Vector3.UP, sp[1]), sp[0])
	if hud:
		hud.message("Zurück auf die Straße gesetzt", 2.5)


func _spawn_point_near(start: Vector2, pref_name: String = "") -> Array:
	var hit: Dictionary = world.nearest(start.x, start.y, 250.0, pref_name)
	if hit.is_empty():
		return [Vector3(start.x, world.height_at(start.x, start.y) + 1.0, start.y), 0.0]
	var t := Vector2(hit["tx"], hit["tz"])
	var n := Vector2(-t.y, t.x)
	var pp := Vector2(hit["px"], hit["pz"]) + n * minf(float(hit["road"]["width"]) * 0.22, 1.8)
	var py: float = float(hit["py"]) + 0.9 if bool(hit["bridge"]) else world.height_at(pp.x, pp.y) + 0.9
	return [Vector3(pp.x, py, pp.y), atan2(-t.x, -t.y)]


func _exit_tree() -> void:
	_release_statics()


static func _release_statics() -> void:
	## Statische Caches leeren, bevor die Engine herunterfährt: halten statische Felder beim Beenden noch
	## Texturen/Materialien, gibt Godot sie erst nach dem RenderingServer frei -> Absturz beim Beenden
	## (im exportierten Spiel beobachtet). Kindknoten (World samt Worker-Thread) sind hier schon raus.
	TexLib._tex.clear()
	TexLib._mats.clear()
	Terrain._arrays_cache.clear()
	Terrain._grid_cache.clear()
	Trams.emit_mats.clear()
	TramUnit._glass = null
	Dressing._part_cache.clear()
	Dressing._sig_parts.clear()
	Dressing._blob_cache.clear()
	Dressing._blob_mat = null
	Dressing._lamp_mats.clear()
	Landmarks._shared_mats.clear()
	Peds._tint_cache.clear()
	SkidFX._dot = null
	Boats._puff = null
	CarModel._glass = null
	CarModel.shared_emit.clear()
	CarModel._ai_paint.clear()
	CarModel._ai_light.clear()
	CarModel.ai_emit.clear()
	StreetLife._parts.clear()
	StreetLife._font = null
	StreetLife._serif_font = null
	StreetLife._sign_cells.clear()
	StreetLife._sign_plates.clear()
	StreetLife._mat_cache.clear()
	ParkedCars._static_parts.clear()
