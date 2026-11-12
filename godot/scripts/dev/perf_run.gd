class_name PerfRun
extends Node
## Leistungsmessung (Entwickler):  godot --path . -- --cam=0,0 --perf [--perfspots=1,4] [--perfabl]
## Fährt feste Kamerapunkte ab, wartet bis die Stadt geladen ist, misst GPU-/CPU-Zeit je Bild und
## Zeichenaufrufe; mit --perfabl zusätzlich die Kosten einzelner Effekte (jeweils abgeschaltet).

const SPOTS := [
	# name, x, z, yaw°, pitch°, Höhe über Boden
	["Altmarkt Straße", 20.0, -60.0, 0.0, 0.0, 1.7],
	["Schlossplatz", 560.0, -300.0, -150.0, 2.0, 1.7],
	["Augustusbrücke Blick Altstadt", 640.0, -560.0, 175.0, -2.0, 16.0],
	["Luftbild Altstadt", 300.0, 650.0, 0.0, -25.0, 150.0],
	["Großer Garten Wald", 2800.0, 1000.0, 90.0, 0.0, 1.7],
]
const FRAMES := 150

var main: Node
var fly: Camera3D
var env_mgr: EnvManager
var results: Array = []
var spot_list: Array = []
var ablate := false
var tour: Array = []            # [{name, x, z, yaw, pitch, h, time?, weather?}] aus --tour=<json>
var tour_dir := ""


func start(m: Node, cam: Camera3D, em: EnvManager, args: Dictionary) -> void:
	main = m
	fly = cam
	env_mgr = em
	ablate = args.has("perfabl")
	if args.has("tour"):
		var j = JSON.parse_string(FileAccess.get_file_as_string(String(args["tour"])))
		if j is Array:
			tour = j
		tour_dir = String(args.get("tourdir", "/tmp"))
	if args.has("perfspots"):
		for s in String(args["perfspots"]).split(","):
			spot_list.append(int(s) - 1)
	else:
		for i in SPOTS.size():
			spot_list.append(i)
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	RenderingServer.viewport_set_measure_render_time(get_viewport().get_viewport_rid(), true)
	_run()


func _wait(n: int) -> void:
	for i in n:
		await get_tree().process_frame


func _measure(label: String) -> Dictionary:
	var rid := get_viewport().get_viewport_rid()
	await _wait(20)
	var gpu: Array = []
	var cpu: Array = []
	var ft: Array = []
	var dc := 0.0
	var prim := 0.0
	var obj := 0.0
	var t_prev := Time.get_ticks_usec()
	for i in FRAMES:
		await get_tree().process_frame
		var t_now := Time.get_ticks_usec()
		ft.append((t_now - t_prev) / 1000.0)
		t_prev = t_now
		gpu.append(RenderingServer.viewport_get_measured_render_time_gpu(rid))
		cpu.append(RenderingServer.viewport_get_measured_render_time_cpu(rid) + RenderingServer.get_frame_setup_time_cpu())
		dc += Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)
		prim += Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)
		obj += Performance.get_monitor(Performance.RENDER_TOTAL_OBJECTS_IN_FRAME)
	gpu.sort()
	ft.sort()
	cpu.sort()
	var r := {
		"label": label,
		"gpu": _mean(gpu), "gpu95": gpu[int(gpu.size() * 0.95)],
		"cpu": _mean(cpu), "ft": _mean(ft), "ft95": ft[int(ft.size() * 0.95)],
		"dc": dc / FRAMES, "prim": prim / FRAMES / 1e6, "obj": obj / FRAMES,
	}
	var line := "%-44s GPU %5.1f ms (p95 %5.1f) | Bild %5.1f ms (p95 %5.1f, %3.0f FPS) | CPU-Render %4.1f ms | %5.0f Draws | %5.2f Mio Dreiecke | %5.0f Objekte" % [
		label, r["gpu"], r["gpu95"], r["ft"], r["ft95"], 1000.0 / maxf(r["ft"], 0.01), r["cpu"], r["dc"], r["prim"], r["obj"]]
	print("PERF ", line)
	results.append(line)
	return r


func _mean(a: Array) -> float:
	var s := 0.0
	for v in a:
		s += float(v)
	return s / maxf(a.size(), 1)


func _place(i: int) -> void:
	var s: Array = SPOTS[i]
	var w: World = main.world
	w.focus = Vector3(s[1], 0.0, s[2])
	fly.position = Vector3(s[1], w.height_at(s[1], s[2]) + float(s[5]), s[2])
	fly.rotation = Vector3(deg_to_rad(s[4]), deg_to_rad(s[3]), 0.0)


func _run_tour() -> void:
	## Rundgang: je Station Kamera setzen, Stadt laden lassen, Bild speichern
	for st in tour:
		var w: World = main.world
		var x := float(st["x"])
		var z := float(st["z"])
		if st.has("time"):
			env_mgr.set_time(float(st["time"]))
		if st.has("weather"):
			env_mgr.set_weather(int(st["weather"]))
			env_mgr._wet = float(EnvManager.WEATHER[env_mgr.weather][0])
		w.focus = Vector3(x, 0.0, z)
		await _wait(10)
		var t0 := Time.get_ticks_msec()
		while not w.all_loaded() and Time.get_ticks_msec() - t0 < 90000:
			fly.position = Vector3(x, w.height_at(x, z) + float(st.get("h", 1.7)), z)
			await _wait(5)
		fly.position = Vector3(x, w.height_at(x, z) + float(st.get("h", 1.7)), z)
		fly.rotation = Vector3(deg_to_rad(float(st.get("pitch", 0.0))), deg_to_rad(float(st.get("yaw", 0.0))), 0.0)
		await _wait(int(st.get("frames", 120)))
		var img := get_viewport().get_texture().get_image()
		var path := tour_dir.path_join(String(st["name"]) + ".png")
		img.save_png(path)
		print("TOUR gespeichert ", path, "  FPS ", Engine.get_frames_per_second())
	get_tree().quit()


func _run() -> void:
	var vp := get_viewport()
	while not main.ready_to_play:
		await _wait(5)
	if not tour.is_empty():
		await _run_tour()
		return
	print("PERF Fenster %s, 3D-Skalierung %.2f, Grafikstufe %d" % [vp.get_visible_rect().size, vp.scaling_3d_scale, env_mgr.quality])
	for i in spot_list:
		_place(i)
		# Stadt um die Kamera laden lassen
		await _wait(10)
		var t0 := Time.get_ticks_msec()
		while not main.world.all_loaded() and Time.get_ticks_msec() - t0 < 60000:
			await _wait(5)
		await _wait(90)
		await _measure(SPOTS[i][0])
		if ablate:
			var env: Environment = env_mgr.env
			var tests := [
				["ohne SDFGI", func(on): env.sdfgi_enabled = on],
				["ohne SSIL", func(on): env.ssil_enabled = on],
				["ohne SSAO", func(on): env.ssao_enabled = on],
				["ohne SSR", func(on): env.ssr_enabled = on],
				["ohne Vol. Nebel", func(on): env.volumetric_fog_enabled = on],
				["ohne Glow", func(on): env.glow_enabled = on],
				["ohne Sonnenschatten", func(on): env_mgr.sun.shadow_enabled = on],
				["ohne TAA", func(on): vp.use_taa = on],
				["ohne Post-FX-Ebene", func(on): (env_mgr.get_node("PostFX") as CanvasLayer).visible = on],
			]
			for tdef in tests:
				var fn: Callable = tdef[1]
				fn.call(false)
				await _measure("   " + String(tdef[0]))
				fn.call(true)
			RenderingServer.gi_set_use_half_resolution(true)
			await _measure("   GI halbe Auflösung")
			RenderingServer.gi_set_use_half_resolution(false)
			var sd := env_mgr.sun.directional_shadow_max_distance
			env_mgr.sun.directional_shadow_max_distance = 250.0
			await _measure("   Schatten 250 m")
			env_mgr.sun.directional_shadow_max_distance = sd
			RenderingServer.environment_set_ssr_roughness_quality(RenderingServer.ENV_SSR_ROUGHNESS_QUALITY_DISABLED)
			await _measure("   SSR ohne Rauheit")
			RenderingServer.environment_set_ssr_roughness_quality(RenderingServer.ENV_SSR_ROUGHNESS_QUALITY_LOW)
			var t_old := vp.use_taa
			vp.use_taa = false
			for sc in [0.67, 0.5]:
				vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_FSR2
				vp.scaling_3d_scale = sc
				await _measure("   FSR2 %d %% (statt TAA)" % int(sc * 100.0))
			vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
			vp.scaling_3d_scale = 1.0
			vp.use_taa = t_old
	print("\nPERF === ERGEBNIS ===")
	for r in results:
		print("PERF ", r)
	get_tree().quit()
