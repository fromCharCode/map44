class_name DriveBench
extends Node
## Fahr-Leistungstest (Entwickler):
##   godot --path . -- --drivebench=90 [--benchspeed=100] [--drive=x,z] [--resolution …]
## Das Spielerauto fährt kinematisch mit fester Geschwindigkeit den Straßengraphen entlang (bevorzugt geradeaus
## und große Straßen), mit allem, was im Spiel läuft (Kachel-Streaming, Verkehr, Fußgänger, Ton). Gemessen werden
## Bildzeiten (Ø, Perzentile, Ausreißer), CPU (Process/Physik), GPU, Zeichenaufrufe und Speicher; die größten
## Ausreißer werden mit Zustand (Kachel im Bau/Anhängen) aufgelistet.

var main: Node
var player: PlayerCar
var traffic: Traffic
var world: World
var duration := 90.0
var speed := 100.0 / 3.6
var _rng := RandomNumberGenerator.new()
var _path: Array = []            # Vector3
var _cum: Array = []             # Bogenlänge je Punkt
var _s := 0.0
var _node := -1
var _edge := -1
var _started := false
var _t := 0.0
var _last_us := 0
var _frames: Array = []          # [dt_ms, proc_ms, phys_ms, gpu_ms, cpu_render_ms, draws, busy, attaching]
var _max_proc := 0.0
var _abl := false
var _exp := false
var _nostream := false
var _phys := false               # --benchphys: echte Fahrphysik mit Autopilot statt kinematisch
var _cam: CamRig
var _jit: Array = []             # je Bild: [dt, cam_pos, cam_fwd, car_pos, car_fwd, shake, hit]
var _noshake := false
var _stuck_t := 0.0
var _exp_stage := 0
var _exp_log := -1
var _exp_name := ""
var _exp_nodes: Array = []
var _prev_attach: Array = []
var _prev_lab := [0.0, 0.0]
var _abl_tests: Array = []       # [Name, Callable(on: bool)]
var _abl_win := -1
var _abl_data := {}              # Name -> [Summe aus, n aus, Summe Basis, n Basis]
const ABL_WIN := 1.5


func start(m: Node, p: PlayerCar, tr: Traffic, w: World, args: Dictionary) -> void:
	main = m
	player = p
	traffic = tr
	world = w
	duration = float(args.get("drivebench", 90))
	speed = float(args.get("benchspeed", 100)) / 3.6
	_rng.seed = int(args.get("benchseed", 7))
	_abl = args.has("benchabl")
	_exp = args.has("attachexp")
	_nostream = args.has("nostream")
	_phys = args.has("benchphys")
	_noshake = args.has("noshake")
	_cam = m.get("cam_rig")
	if _cam and _noshake:
		_cam.shake_scale = 0.0
	if args.has("nosdfgi"):
		m.env_mgr.env.sdfgi_enabled = false
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	Engine.max_fps = 0
	RenderingServer.viewport_set_measure_render_time(get_viewport().get_viewport_rid(), true)


func _physics_process(delta: float) -> void:
	if player == null or traffic == null:
		return
	if not _started:
		if traffic.edges.is_empty():
			return
		if not _init_path():
			return
		_started = true
		if _phys:
			player.override_input = true
			player.global_transform = _xf_at(_s)
			player.global_position += Vector3(0, 0.6, 0)
			player.linear_velocity = Vector3.ZERO
			player.angular_velocity = Vector3.ZERO
			player.reset_physics_interpolation()
		else:
			player.freeze_mode = RigidBody3D.FREEZE_MODE_KINEMATIC
			player.freeze = true
		print("DriveBench: Start bei ", player.global_position, " mit %.0f km/h" % (speed * 3.6), " (Physik)" if _phys else "")
		if _nostream:
			world.enabled = false
			print("DriveBench: Kachel-Nachladen aus")
	if _phys:
		_autopilot(delta)
	else:
		_s += speed * delta
	while _s > float(_cum[_cum.size() - 1]) - 60.0:
		if not _extend():
			break
	if not _phys:
		player.global_transform = _xf_at(_s)
	# hinter uns liegende Punkte abwerfen
	while _cum.size() > 4 and float(_cum[2]) < _s - 30.0:
		_path.pop_front()
		_cum.pop_front()


func _autopilot(delta: float) -> void:
	## Folgt dem Pfad mit echter Fahrphysik: Pure-Pursuit-Lenkung, Tempo nach Kurvenkrümmung voraus.
	var p := player.global_position
	# Bogenlänge: nächster Pfadpunkt in einem Fenster um _s
	var best_s := _s
	var best_d := 1e9
	var ss := _s - 4.0
	while ss < _s + 12.0:
		var q := _pos_at(ss, 0)
		var d := Vector2(q.x - p.x, q.z - p.z).length()
		if d < best_d:
			best_d = d
			best_s = ss
		ss += 0.5
	_s = maxf(_s, best_s)
	var v := absf(player.speed)
	if best_d > 9.0 or (v < 0.5 and _t > 6.0):
		_stuck_t += delta
	else:
		_stuck_t = 0.0
	if _stuck_t > 2.0:
		_stuck_t = 0.0
		_s += 15.0
		player.global_transform = _xf_at(_s)
		player.global_position += Vector3(0, 0.6, 0)
		player.linear_velocity = -player.global_transform.basis.z * minf(v, 8.0)
		player.angular_velocity = Vector3.ZERO
		player.reset_physics_interpolation()
		print("DriveBench: Autopilot zurückgesetzt bei t=%.1f" % _t)
		return
	var la := clampf(v * 0.55, 7.0, 24.0)
	var tgt := _pos_at(_s + la, 0)
	var fwd := -player.global_transform.basis.z
	var to := Vector2(tgt.x - p.x, tgt.z - p.z)
	var f2 := Vector2(fwd.x, fwd.z).normalized()
	var err := f2.angle_to(to.normalized())          # > 0: Ziel rechts (Godot-2D: +x nach rechts, +y = +z)
	# Pure Pursuit: Lenkwinkel = atan(2 L sin(err) / la); Lenkeingabe auf den maximalen Einschlag normieren
	var delta_w := atan(2.0 * 2.92 * sin(err) / la)
	var max_a := clampf(atan(10.0 * 2.92 / maxf(v * v, 1.0)) * 2.3, deg_to_rad(2.5), deg_to_rad(34.0))
	player.in_steer = clampf(delta_w / max_a, -1.0, 1.0)
	# Wunschtempo: Kurven voraus (Richtungsänderung über 40 m)
	var a0 := _pos_at(_s, 0)
	var a1 := _pos_at(_s + 20.0, 0)
	var a2 := _pos_at(_s + 40.0, 0)
	var t1 := Vector2(a1.x - a0.x, a1.z - a0.z).normalized()
	var t2 := Vector2(a2.x - a1.x, a2.z - a1.z).normalized()
	var turn := absf(t1.angle_to(t2))
	var v_want := minf(speed, maxf(6.0, sqrt(5.0 * 20.0 / maxf(turn, 0.01))))
	var dv := v_want - v
	player.in_throttle = clampf(dv * 0.35 + 0.25, 0.0, 1.0) if dv > -0.5 else 0.0
	player.in_brake = clampf(-dv * 0.15, 0.0, 1.0) if dv < -2.0 else 0.0


func _jit_sample(dt: float) -> void:
	if _cam == null or _cam.cam == null:
		return
	var ct := _cam.cam.global_transform
	var xf := player.get_global_transform_interpolated()
	_jit.append([dt, ct.origin, -ct.basis.z, xf.origin, -xf.basis.z, _cam.last_shake, 1 if _cam.last_hit else 0, absf(player.speed)])


func _jit_report() -> void:
	## Kamerazittern: zweite Differenz (Beschleunigung) von Kamera-Blickwinkeln und -Position je Bild, nach
	## Zeitnormierung; zum Vergleich das (interpolierte) Auto. Glatte Bewegung -> ~0, Rütteln -> groß.
	var n := _jit.size()
	if n < 10:
		return
	var cam_ang: Array = []
	var cam_pos: Array = []
	var car_pos: Array = []
	var car_ang: Array = []
	var hits := 0
	var sh := 0.0
	for i in range(2, n):
		var a: Array = _jit[i - 2]
		var b: Array = _jit[i - 1]
		var c: Array = _jit[i]
		var dt1 := float(b[0]) / 1000.0
		var dt2 := float(c[0]) / 1000.0
		if dt1 <= 0.0 or dt2 <= 0.0 or dt1 > 0.05 or dt2 > 0.05:
			continue
		# Winkelgeschwindigkeit (rad/s) aus Blickrichtungen
		var w1 := _ang((a[2] as Vector3), (b[2] as Vector3)) / dt1
		var w2 := _ang((b[2] as Vector3), (c[2] as Vector3)) / dt2
		cam_ang.append(((w2 - w1) / ((dt1 + dt2) * 0.5)).length())
		var v1 := ((b[1] as Vector3) - (a[1] as Vector3)) / dt1
		var v2 := ((c[1] as Vector3) - (b[1] as Vector3)) / dt2
		cam_pos.append(((v2 - v1) / ((dt1 + dt2) * 0.5)).length())
		var u1 := ((b[3] as Vector3) - (a[3] as Vector3)) / dt1
		var u2 := ((c[3] as Vector3) - (b[3] as Vector3)) / dt2
		car_pos.append(((u2 - u1) / ((dt1 + dt2) * 0.5)).length())
		var y1 := _ang((a[4] as Vector3), (b[4] as Vector3)) / dt1
		var y2 := _ang((b[4] as Vector3), (c[4] as Vector3)) / dt2
		car_ang.append(((y2 - y1) / ((dt1 + dt2) * 0.5)).length())
		hits += int(c[6])
		sh += float(c[5])
	var m := cam_ang.size()
	for arr in [cam_ang, cam_pos, car_pos, car_ang]:
		arr.sort()
	var vmean := 0.0
	for f in _jit:
		vmean += float(f[7])
	vmean /= n
	print("KAMERA-ZITTERN (%d Bilder, Ø %.0f km/h, Rütteln Ø %.4f, Kollisionsstrahl getroffen %d×)" % [m, vmean * 3.6, sh / maxf(m, 1), hits])
	print("  Kamera Winkelbeschl. rad/s²: p50 %.1f · p90 %.1f · p99 %.1f" % [_pct(cam_ang, 0.5), _pct(cam_ang, 0.9), _pct(cam_ang, 0.99)])
	print("  Kamera Positionsbeschl. m/s²: p50 %.1f · p90 %.1f · p99 %.1f" % [_pct(cam_pos, 0.5), _pct(cam_pos, 0.9), _pct(cam_pos, 0.99)])
	print("  Auto   Winkelbeschl. rad/s²: p50 %.1f · p90 %.1f · p99 %.1f" % [_pct(car_ang, 0.5), _pct(car_ang, 0.9), _pct(car_ang, 0.99)])
	print("  Auto   Positionsbeschl. m/s²: p50 %.1f · p90 %.1f · p99 %.1f" % [_pct(car_pos, 0.5), _pct(car_pos, 0.9), _pct(car_pos, 0.99)])


static func _ang(a: Vector3, b: Vector3) -> Vector3:
	## Drehvektor von Blickrichtung a nach b (klein): Achse * Winkel
	var c := a.cross(b)
	var s := c.length()
	if s < 1e-9:
		return Vector3.ZERO
	return c / s * atan2(s, a.dot(b))


func _process(_delta: float) -> void:
	if not _started:
		_last_us = Time.get_ticks_usec()
		return
	var now := Time.get_ticks_usec()
	var dt := float(now - _last_us) / 1000.0
	_last_us = now
	_t += dt / 1000.0
	if dt > 120.0:
		print("SPIKE t=%.1f s %.0f ms busy=%d (%s) anhängen=%d" % [_t, dt, 1 if world.is_busy() else 0, Tile.build_step if world.is_busy() else "-", world._attaching.size()])
		print("   Beschriftungen davor: Gebäude %.1f ms, Straßenleben %.1f ms" % [_prev_lab[0], _prev_lab[1]])
		if not _prev_attach.is_empty() or not world.attach_log.is_empty():
			print("   davor eingehängt: ", _summ(_prev_attach), " | dieses Bild: ", _summ(world.attach_log))
	_prev_attach = world.attach_log.duplicate()
	_prev_lab = [Buildings.label_ms, StreetLife.label_ms]
	Buildings.label_ms = 0.0
	StreetLife.label_ms = 0.0
	world.attach_log.clear()
	if _t < 3.0:
		return                     # Einschwingen
	if _phys:
		_jit_sample(_delta * 1000.0)
	var rid := get_viewport().get_viewport_rid()
	_frames.append([dt,
		Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0,
		Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0,
		RenderingServer.viewport_get_measured_render_time_gpu(rid),
		RenderingServer.viewport_get_measured_render_time_cpu(rid),
		Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
		1 if world.is_busy() else 0,
		world._attaching.size(),
		_t])
	if _abl:
		_ablate_step(float(_frames[_frames.size() - 1][3]))
	if _exp:
		_attach_experiment(dt)
	if _t >= duration + 3.0:
		if _abl:
			_set_abl(_abl_win, true)
		_report()
		if _phys:
			_jit_report()
		get_tree().quit()


func _init_path() -> bool:
	var p := player.global_position
	var fwd := -player.global_transform.basis.z
	var best: Array = traffic._edge_near(Vector2(p.x, p.z), Vector2(fwd.x, fwd.z).normalized(), 60.0)
	if best.is_empty():
		best = traffic._edge_near(Vector2(p.x, p.z), -Vector2(fwd.x, fwd.z).normalized(), 60.0)
	if best.is_empty():
		return false
	_path.clear()
	_cum.clear()
	_append_edge(int(best[0]), int(best[1]))
	_s = float(best[2])
	for i in 6:
		_extend()
	return true


func _append_edge(ei: int, dir: int) -> void:
	var pts := traffic.edge_points(ei, dir)
	var e: Dictionary = traffic.edges[ei]
	_edge = ei
	_node = int(e["b"]) if dir == 1 else int(e["a"])
	for q in pts:
		var v: Vector3 = q
		v.y = maxf(v.y, world.height_at(v.x, v.z)) if not bool(e.get("bridge", false)) else v.y
		if not _path.is_empty():
			var last: Vector3 = _path[_path.size() - 1]
			var d := Vector2(v.x - last.x, v.z - last.z).length()
			if d < 0.3:
				continue
			_cum.append(float(_cum[_cum.size() - 1]) + d)
		else:
			_cum.append(0.0)
		_path.append(v)


func _extend() -> bool:
	var opts: Array = traffic.out_edges.get(_node, [])
	if opts.is_empty():
		return false
	var n := _path.size()
	var t := Vector2(1, 0)
	if n >= 2:
		var a: Vector3 = _path[n - 2]
		var b: Vector3 = _path[n - 1]
		t = Vector2(b.x - a.x, b.z - a.z).normalized()
	var best: Array = []
	var best_w := -1.0
	for o in opts:
		var ei: int = o[0]
		if ei == _edge and opts.size() > 1:
			continue
		var e: Dictionary = traffic.edges[ei]
		var cls := String(e["cls"])
		var pts := traffic.edge_points(ei, int(o[1]))
		if pts.size() < 2:
			continue
		var p0: Vector3 = pts[0]
		var p1: Vector3 = pts[mini(2, pts.size() - 1)]
		var tt := Vector2(p1.x - p0.x, p1.z - p0.z).normalized()
		var dotv := tt.dot(t)
		if dotv < -0.5 and opts.size() > 1:
			continue
		var w := (dotv + 1.2) * (2.5 if cls in ["primary", "secondary", "trunk"] else (1.5 if cls == "tertiary" else 1.0))
		if cls == "service" or traffic._narrow(e):
			w *= 0.05
		if traffic._dead_end(ei, int(o[1])):
			w *= 0.02
		w *= _rng.randf_range(0.7, 1.3)
		if w > best_w:
			best_w = w
			best = o
	if best.is_empty():
		best = opts[0]
	_append_edge(int(best[0]), int(best[1]))
	return true


func _xf_at(s: float) -> Transform3D:
	var i := 0
	var n := _cum.size()
	while i < n - 2 and float(_cum[i + 1]) < s:
		i += 1
	var s0 := float(_cum[i])
	var s1 := float(_cum[i + 1])
	var a: Vector3 = _path[i]
	var b: Vector3 = _path[i + 1]
	var f := clampf((s - s0) / maxf(s1 - s0, 0.01), 0.0, 1.0)
	var p := a.lerp(b, f)
	# Blickrichtung geglättet über ±6 m
	var ahead := _pos_at(s + 6.0, i)
	var back := _pos_at(s - 6.0, 0)
	var dirv := (ahead - back)
	dirv.y = 0.0
	if dirv.length() < 0.01:
		dirv = Vector3(b.x - a.x, 0.0, b.z - a.z)
	dirv = dirv.normalized()
	var basis := Basis.looking_at(dirv, Vector3.UP)
	return Transform3D(basis, p + Vector3(0, 0.05, 0))


func _pos_at(s: float, start_i: int) -> Vector3:
	var n := _cum.size()
	var i := clampi(start_i, 0, n - 2)
	if s <= float(_cum[0]):
		return _path[0]
	while i < n - 2 and float(_cum[i + 1]) < s:
		i += 1
	var s0 := float(_cum[i])
	var s1 := float(_cum[i + 1])
	var f := clampf((s - s0) / maxf(s1 - s0, 0.01), 0.0, 1.0)
	return (_path[i] as Vector3).lerp(_path[i + 1], f)


func _pct(arr: Array, q: float) -> float:
	if arr.is_empty():
		return 0.0
	return float(arr[clampi(int(arr.size() * q), 0, arr.size() - 1)])


func _report() -> void:
	var n := _frames.size()
	if n == 0:
		print("DriveBench: keine Daten")
		return
	var dts: Array = []
	var procs: Array = []
	var phys: Array = []
	var gpus: Array = []
	var cpur: Array = []
	var draws := 0.0
	var sum := 0.0
	for f in _frames:
		dts.append(f[0])
		procs.append(f[1])
		phys.append(f[2])
		gpus.append(f[3])
		cpur.append(f[4])
		draws += float(f[5])
		sum += float(f[0])
	var sorted_dt := dts.duplicate()
	sorted_dt.sort()
	var avg := sum / n
	var lows: Array = sorted_dt.slice(int(n * 0.99))
	var low_avg := 0.0
	for v in lows:
		low_avg += float(v)
	low_avg /= maxf(lows.size(), 1)
	var sp25 := dts.filter(func(x): return x > 25.0).size()
	var sp50 := dts.filter(func(x): return x > 50.0).size()
	var sp100 := dts.filter(func(x): return x > 100.0).size()
	var s_proc := procs.duplicate()
	s_proc.sort()
	var s_phys := phys.duplicate()
	s_phys.sort()
	var s_gpu := gpus.duplicate()
	s_gpu.sort()
	var s_cpur := cpur.duplicate()
	s_cpur.sort()
	var vs := get_viewport().get_visible_rect().size
	print("DRIVEBENCH Auflösung %dx%d Skalierung %.2f · %d Bilder in %.0f s · Strecke %.0f m" % [vs.x, vs.y, get_viewport().scaling_3d_scale, n, _t - 3.0, _s])
	print("  Bildzeit Ø %.2f ms (%.1f FPS) · p50 %.2f · p95 %.2f · p99 %.2f · max %.1f ms · 1%%-Low %.1f FPS" % [avg, 1000.0 / avg, _pct(sorted_dt, 0.5), _pct(sorted_dt, 0.95), _pct(sorted_dt, 0.99), float(sorted_dt[n - 1]), 1000.0 / maxf(low_avg, 0.01)])
	print("  Ausreißer >25 ms: %d · >50 ms: %d · >100 ms: %d" % [sp25, sp50, sp100])
	print("  CPU Process Ø %.2f / p95 %.2f ms · Physik Ø %.2f / p95 %.2f ms · Render-CPU Ø %.2f / p95 %.2f ms" % [_avg(procs), _pct(s_proc, 0.95), _avg(phys), _pct(s_phys, 0.95), _avg(cpur), _pct(s_cpur, 0.95)])
	print("  GPU Ø %.2f / p95 %.2f ms · Zeichenaufrufe Ø %.0f" % [_avg(gpus), _pct(s_gpu, 0.95), draws / n])
	print("  Speicher: Video %.0f MB (Texturen %.0f MB, Puffer %.0f MB) · Objekte %d · Statisch %.0f MB" % [
		Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED) / 1048576.0,
		Performance.get_monitor(Performance.RENDER_TEXTURE_MEM_USED) / 1048576.0,
		Performance.get_monitor(Performance.RENDER_BUFFER_MEM_USED) / 1048576.0,
		Performance.get_monitor(Performance.OBJECT_COUNT),
		Performance.get_monitor(Performance.MEMORY_STATIC) / 1048576.0])
	if _abl:
		abl_report()
	print("  Verkehr %d Autos · Fußgänger %d · Kacheln %d" % [traffic.cars.size(), main.peds.peds.size() if main.peds else 0, world.tiles.size()])
	# größte Ausreißer
	var idx: Array = range(n)
	idx.sort_custom(func(a, b): return float(_frames[a][0]) > float(_frames[b][0]))
	var line := "  Top-Ausreißer:"
	for k in mini(10, n):
		var f: Array = _frames[idx[k]]
		line += "\n    t=%5.1f s %6.1f ms (proc %.1f, phys %.1f, gpu %.1f, rcpu %.1f, busy %d, anhängen %d)" % [f[8], f[0], f[1], f[2], f[3], f[4], f[6], f[7]]
	print(line)


func _avg(a: Array) -> float:
	if a.is_empty():
		return 0.0
	var s := 0.0
	for v in a:
		s += float(v)
	return s / a.size()



# --- A/B-Abschaltung während der Fahrt (--benchabl) ------------------------------------------------------
# Fenster à ABL_WIN s: gerade Fenster = Basis, ungerade = ein Test aus; Kosten = GPU(Basis-Nachbarn) - GPU(aus).
func _groups(mod: String) -> Array:
	var res: Array = []
	for k in world.tiles:
		var t: Node = world.tiles[k]
		var m := t.get_node_or_null(mod)
		if m is Node3D:
			res.append(m)
	return res


func _vis(nodes: Array, on: bool) -> void:
	for n in nodes:
		if is_instance_valid(n):
			(n as Node3D).visible = on


func _build_tests() -> void:
	var env: Environment = main.env_mgr.env
	var sun: DirectionalLight3D = main.env_mgr.sun
	_abl_tests = [
		["SDFGI", func(on): env.sdfgi_enabled = on],
		["SSIL", func(on): env.ssil_enabled = on],
		["SSAO", func(on): env.ssao_enabled = on],
		["SSR", func(on): env.ssr_enabled = on],
		["Glow", func(on): env.glow_enabled = on],
		["Vol. Nebel", func(on): env.volumetric_fog_enabled = on],
		["Sonnenschatten", func(on): sun.shadow_enabled = on],
		["Gebäude", func(on): _vis(_groups("Buildings"), on)],
		["Gelände", func(on): _vis(_groups("Terrain"), on)],
		["Straßen", func(on): _vis(_groups("Roads"), on)],
		["Dressing (Bäume fern, Laternen, Ampeln)", func(on): _vis(_groups("Dressing"), on)],
		["Straßenleben", func(on): _vis(_groups("StreetLife"), on)],
		["Parkende Autos", func(on): _vis(_groups("Parked"), on)],
		["Mauern", func(on): _vis(_groups("Walls"), on)],
		["Baum-LOD nah", func(on): main.tree_lod.visible = on],
		["Bodenbewuchs", func(on): main.ground_cover.visible = on],
		["KI-Verkehr", func(on): traffic.visible = on],
		["Fußgänger", func(on): main.peds.visible = on],
		["Straßenbahnen", func(on): main.trams.visible = on],
	]


func _set_abl(win: int, on: bool) -> void:
	if win < 0 or win % 2 == 0 or _abl_tests.is_empty():
		return
	var tdef: Array = _abl_tests[(win / 2) % _abl_tests.size()]
	(tdef[1] as Callable).call(on)


func _ablate_step(gpu: float) -> void:
	if _abl_tests.is_empty():
		_build_tests()
	var w := int((_t - 3.0) / ABL_WIN)
	if w != _abl_win:
		_set_abl(_abl_win, true)
		_abl_win = w
		_set_abl(_abl_win, false)
		return
	# erste 0,4 s eines Fensters verwerfen (GPU-Messung hinkt, Effekte bauen sich auf)
	if (_t - 3.0) - w * ABL_WIN < 0.4:
		return
	var idx := (w / 2) % _abl_tests.size()
	var name: String = _abl_tests[idx][0]
	if not _abl_data.has(name):
		_abl_data[name] = [0.0, 0, 0.0, 0]
	var d: Array = _abl_data[name]
	if w % 2 == 1:
		d[0] = float(d[0]) + gpu
		d[1] = int(d[1]) + 1
	else:
		# Basisfenster zählt für den vorigen und den nächsten Test
		d[2] = float(d[2]) + gpu
		d[3] = int(d[3]) + 1
		var prev: String = _abl_tests[(idx - 1 + _abl_tests.size()) % _abl_tests.size()][0]
		if w >= 2 and prev != name:
			if not _abl_data.has(prev):
				_abl_data[prev] = [0.0, 0, 0.0, 0]
			var dp: Array = _abl_data[prev]
			dp[2] = float(dp[2]) + gpu
			dp[3] = int(dp[3]) + 1


func abl_report() -> void:
	var rows: Array = []
	for k in _abl_data:
		var d: Array = _abl_data[k]
		if int(d[1]) == 0 or int(d[3]) == 0:
			continue
		var off := float(d[0]) / int(d[1])
		var base := float(d[2]) / int(d[3])
		rows.append([base - off, k, base, off, int(d[1])])
	rows.sort_custom(func(a, b): return a[0] > b[0])
	var line := "  GPU-Kosten je Gruppe (A/B während der Fahrt):"
	for r in rows:
		line += "\n    %6.2f ms  %-40s (Basis %.2f, aus %.2f, %d Bilder)" % [r[0], r[1], r[2], r[3], r[4]]
	print(line)


func _summ(lst: Array) -> String:
	## "Modul(Klasse) xN" zusammenfassen
	var cnt := {}
	for x in lst:
		var sx := String(x)
		var mod := sx.get_slice("/", 0)
		var cls := sx.get_slice("(", 1).trim_suffix(")")
		var k := mod + ":" + cls
		cnt[k] = int(cnt.get(k, 0)) + 1
	var parts: Array = []
	for k in cnt:
		parts.append("%s x%d" % [k, cnt[k]])
	return ", ".join(parts)


# --- Experiment: was kostet das Hochladen großer Texturen? (--attachexp) ---------------------------------
var _exp_img: Image
var _exp_img_c: Image
var _exp_tex: Texture2D
var _exp_thread: Thread


func _exp_prepare() -> void:
	_exp_img = Image.create_empty(4000, 4000, false, Image.FORMAT_RGBA8)
	_exp_img.fill(Color(0.3, 0.5, 0.2, 0.7))
	_exp_img.generate_mipmaps()
	_exp_img_c = _exp_img.duplicate() as Image
	_exp_img_c.compress(Image.COMPRESS_S3TC, Image.COMPRESS_SOURCE_GENERIC)


func _exp_worker(img: Image) -> void:
	var t0 := Time.get_ticks_usec()
	_exp_tex = ImageTexture.create_from_image(img)
	print("   EXP Thread: create_from_image %.1f ms" % ((Time.get_ticks_usec() - t0) / 1000.0))


func _attach_experiment(dt: float) -> void:
	if _exp_img == null:
		_exp_prepare()
	if _exp_log >= 0:
		if dt > 25.0 or _exp_log % 8 == 0:
			print("   EXP %s Bild -%d: %.1f ms" % [_exp_name, _exp_log, dt])
		_exp_log -= 1
		if _exp_log < 0:
			if _exp_thread:
				_exp_thread.wait_to_finish()
				_exp_thread = null
			for n in _exp_nodes:
				(n as Node).queue_free()
			_exp_nodes.clear()
		return
	var times := [12.0, 20.0, 28.0]
	if _exp_stage >= times.size() or _t < float(times[_exp_stage]):
		return
	if _exp_stage < 2:
		var names3 := ["Thread: 150 Meshes ohne Pause", "Thread: 150 Meshes mit 6 ms Pause"]
		_exp_name = names3[_exp_stage]
		_exp_thread = Thread.new()
		_exp_thread.start(_mesh_worker.bind(_exp_stage == 1))
		_exp_stage += 1
		_exp_log = 40
		return
	var stage := _exp_stage + 10
	_exp_stage += 1
	if stage >= 10:
		var names2 := ["120 Stücke 1,6 km entfernt (GI statisch)", "120 Stücke 1,6 km entfernt (GI aus)", "120 Stücke nah (GI statisch)", "120 Stücke nah (GI aus)", "120 Stücke 1,6 km entfernt, unsichtbar (GI statisch)"]
		_exp_name = names2[stage - 10]
		var src2: MeshInstance3D = null
		for k in world.tiles:
			var tr2: Node = (world.tiles[k] as Node).get_node_or_null("Terrain")
			if tr2:
				for c in tr2.get_children():
					if c is MeshInstance3D:
						src2 = c
						break
			if src2:
				break
		var cam := get_viewport().get_camera_3d()
		var base := cam.global_position
		var far := stage == 10 or stage == 11 or stage == 14
		var t1 := Time.get_ticks_usec()
		for i in 120:
			var mi := MeshInstance3D.new()
			mi.mesh = src2.mesh
			mi.material_override = src2.material_override
			mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			mi.custom_aabb = AABB(Vector3(0, -20, 0), Vector3(125, 60, 125))
			if stage == 11 or stage == 13:
				mi.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
			if stage == 14:
				mi.visible = false
			world.add_child(mi)
			var off := Vector3((i % 12) * 125.0 - 750.0, -30.0, (i / 12) * 125.0 - 600.0)
			if far:
				off += Vector3(1600.0, 0.0, 1600.0)
			mi.global_position = base + off
			_exp_nodes.append(mi)
		print("EXP %s: Aufruf %.1f ms" % [_exp_name, (Time.get_ticks_usec() - t1) / 1000.0])
		_exp_log = 6
		return
	var names := ["Thread: RGBA8 4000² (85 MB)", "Thread: DXT5 4000² (21 MB)", "Haupt: RGBA8 4000²", "Haupt: DXT5 4000²", "erste Nutzung neuer Textur (120 Stücke)"]
	_exp_name = names[stage]
	var t0 := Time.get_ticks_usec()
	match stage:
		0:
			_exp_thread = Thread.new()
			_exp_thread.start(_exp_worker.bind(_exp_img))
		1:
			_exp_thread = Thread.new()
			_exp_thread.start(_exp_worker.bind(_exp_img_c))
		2:
			_exp_tex = ImageTexture.create_from_image(_exp_img)
		3:
			_exp_tex = ImageTexture.create_from_image(_exp_img_c)
		4:
			var src: MeshInstance3D = null
			for k in world.tiles:
				var tr: Node = (world.tiles[k] as Node).get_node_or_null("Terrain")
				if tr:
					for c in tr.get_children():
						if c is MeshInstance3D:
							src = c
							break
				if src:
					break
			if src:
				var sm := (src.material_override as ShaderMaterial).duplicate() as ShaderMaterial
				sm.set_shader_parameter("splat0", _exp_tex)
				for i in 120:
					var mi := MeshInstance3D.new()
					mi.mesh = src.mesh
					mi.material_override = sm
					mi.custom_aabb = src.custom_aabb
					mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
					world.add_child(mi)
					mi.global_position = src.global_position + Vector3((i % 12) * 125.0 - 700.0, 0.0, (i / 12) * 125.0 - 600.0)
					_exp_nodes.append(mi)
	print("EXP %s: Aufruf %.1f ms" % [_exp_name, (Time.get_ticks_usec() - t0) / 1000.0])
	_exp_log = 6


func _mesh_worker(pause: bool) -> void:
	var t0 := Time.get_ticks_usec()
	var verts := PackedVector3Array()
	verts.resize(60000)
	for i in verts.size():
		verts[i] = Vector3(randf(), randf(), randf()) * 10.0
	var keep: Array = []
	for k in 150:
		var arr := []
		arr.resize(Mesh.ARRAY_MAX)
		arr[Mesh.ARRAY_VERTEX] = verts
		var m := ArrayMesh.new()
		m.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
		keep.append(m)
		if pause:
			OS.delay_msec(6)
	print("   EXP Thread fertig nach %.0f ms" % ((Time.get_ticks_usec() - t0) / 1000.0))
