class_name TunnelTest
extends Node
## Entwickler: Durchfahrt durch einen Tunnel mit echter Fahrphysik.
##   godot --path . -- --tunneltest=<kachel>:<index> [--tunnelgas=0.5] [--shot=<png>]
## Setzt das Auto 25 m vor das Anfangsportal der Tunnelkette (city["tunnels"][index] der Kachel), fährt mit
## Pure-Pursuit-Lenkung entlang der Kette und meldet je Sekunde Ort, Höhe über Fahrbahn und Tempo; am Ende, ob
## die Röhre ohne Rücksetzen/Absturz durchfahren wurde.

var main: Node
var pts: Array = []
var _t := 0.0
var _started := false
var _resets := 0
var _last := Vector3.ZERO
var _min_dy := 99.0
var _max_dy := -99.0
var _s := 0.0
var _gas := 0.5
var _tile := ""
var _idx := 0
var _shot := ""
var _shot_done := false
var _ai_max := 0


func start(m: Node, args: Dictionary) -> void:
	main = m
	var spec := String(args.get("tunneltest", "")).split(":")
	_tile = spec[0]
	_idx = int(spec[1]) if spec.size() > 1 else 0
	_gas = float(args.get("tunnelgas", 0.5))
	_shot = String(args.get("tunnelshot", ""))


func _physics_process(delta: float) -> void:
	if main.get("player") == null:
		return
	var player: PlayerCar = main.player
	if not _started:
		var t = main.world.tiles.get(_tile)
		if t == null:
			return
		var tl: Array = (t as Tile).city.get("tunnels", [])
		if _idx >= tl.size():
			print("TUNNELTEST: keine Kette ", _idx, " in ", _tile)
			main.get_tree().quit()
			return
		for p in tl[_idx]["pts"]:
			pts.append(Vector3(float(p[0]), float(p[2]), float(p[1])))
		# Fortsetzung in Nachbarkacheln anhängen (Teilketten überlappen um ±30 m)
		var grew := true
		while grew:
			grew = false
			var last: Vector3 = pts[pts.size() - 1]
			for tk in main.world.tiles:
				if tk == _tile:
					continue
				for tn in (main.world.tiles[tk] as Tile).city.get("tunnels", []):
					var q: Array = tn["pts"]
					var bi := -1
					for i in q.size():
						if Vector2(float(q[i][0]) - last.x, float(q[i][1]) - last.z).length() < 1.5:
							bi = i
					if bi >= 0 and bi < q.size() - 3:
						for i in range(bi + 1, q.size()):
							pts.append(Vector3(float(q[i][0]), float(q[i][2]), float(q[i][1])))
						grew = true
						break
				if grew:
					break
		var a: Vector3 = pts[0]
		var b: Vector3 = pts[3]
		var dir := (b - a)
		dir.y = 0.0
		dir = dir.normalized()
		var start := a - dir * 25.0
		start.y = maxf(main.world.height_at(start.x, start.z), a.y) + 0.9     # Anfahrt kann eine Brücke sein (A17)
		player.global_transform = Transform3D(Basis(Vector3.UP, atan2(-dir.x, -dir.z)), start)
		player.linear_velocity = Vector3.ZERO
		player.override_input = true
		_started = true
		_last = start
		print("TUNNELTEST Start %s #%d: %s (%d Stützpunkte, %.0f m)" % [_tile, _idx, tl[_idx].get("name", ""), pts.size(), (pts.size() - 1) * 2.0])
		return
	_t += delta
	var p := player.global_position
	if p.distance_to(_last) > 12.0 * maxf(delta, 0.02) * 10.0:
		_resets += 1                                  # Sprung = Rücksetzen durch das Hauptprogramm
	_last = p
	# nächster Kettenpunkt und Zielpunkt 10 m voraus
	var best := 0
	var bd := INF
	for i in pts.size():
		var d := Vector2(pts[i].x - p.x, pts[i].z - p.z).length()
		if d < bd:
			bd = d
			best = i
	_s = best * 2.0
	var tgt: Vector3 = pts[mini(best + 5, pts.size() - 1)]
	var fwd := -player.global_transform.basis.z
	var to := (tgt - p)
	to.y = 0.0
	var ang := atan2(fwd.cross(to.normalized()).y, fwd.dot(to.normalized()))
	player.in_steer = clampf(-ang * 2.0, -1.0, 1.0)
	player.in_throttle = _gas if player.linear_velocity.length() < 16.0 else 0.0
	player.in_brake = 0.0
	if bd < 8.0 and best > 0 and best < pts.size() - 1:
		var dy: float = p.y - (pts[best] as Vector3).y
		_min_dy = minf(_min_dy, dy)
		_max_dy = maxf(_max_dy, dy)
	if int(_t * 60.0) % 60 == 0:
		print("  t=%4.1f s  s=%5.0f m  Abstand Achse %4.1f m  Höhe über Fahrbahn %+5.2f m  %4.0f km/h  im Tunnel %s" % [
			_t, _s, bd, p.y - pts[best].y, player.linear_velocity.length() * 3.6, str(Tunnels.inside(p))])
	if int(_t * 60.0) % 300 == 0 and main.get("traffic") != null:
		var n_in := 0
		var bad := 0
		for c in main.traffic.cars:
			if is_instance_valid(c) and Tunnels.inside((c as Node3D).global_position):
				n_in += 1
		_ai_max = maxi(_ai_max, n_in)
		print("  KI-Autos im Tunnel: %d" % n_in)
	if _shot != "" and not _shot_done and _t > 12.0:
		_shot_done = true
		main.get_viewport().get_texture().get_image().save_png(_shot)
	var done := best >= pts.size() - 2 and bd < 8.0
	if done or _t > 240.0:
		print("TUNNELTEST %s: %.0f m von %.0f m, Rücksetzen %d, Höhe über Fahrbahn %.2f … %.2f m, KI im Tunnel max %d" % [
			"DURCHFAHREN" if done else "ABBRUCH", _s, (pts.size() - 1) * 2.0, _resets, _min_dy, _max_dy, _ai_max])
		main.get_tree().quit()
