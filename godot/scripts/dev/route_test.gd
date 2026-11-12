class_name RouteTest
extends Node
## Entwickler: Durchfahrt einer Straße (z. B. unter einer Brücke) mit echter Fahrphysik.
##   godot --path . -- --drive=x,z --routetest=<kachel>:<weg-id>[:<richtung 1|-1>] [--routegas=0.45]
##   godot --path . -- --drive=x,z --routelist=<json: [[kachel, weg-id, richtung], …]> [--routeout=<json>]
## Setzt das Auto 12 m vor den Anfang des Weges (city["roads"], alle Stücke mit dieser id, aneinandergehängt),
## lenkt per Pure Pursuit auf der rechten Fahrspur entlang und meldet am Ende DURCHFAHREN/ABBRUCH mit Rücksetzern,
## Hängenbleiben (< 1 m/s über 4 s) und Höhe über dem Profil.

var main: Node
var pts: Array = []
var _t := 0.0
var _started := false
var _resets := 0
var _last := Vector3.ZERO
var _stuck_t := 0.0
var _min_dy := 99.0
var _max_dy := -99.0
var _gas := 0.45
var _tile := ""
var _wid := 0
var _dir := 1
var _best := 0
var _why := ""
var _list: Array = []
var _li := -1
var _active := false
var _results: Array = []
var _out := ""


func start(m: Node, args: Dictionary) -> void:
	main = m
	_gas = float(args.get("routegas", 0.45))
	_out = String(args.get("routeout", ""))
	if args.has("routelist"):
		var j = JSON.parse_string(FileAccess.get_file_as_string(String(args["routelist"])))
		_list = j if j is Array else []
		call_deferred("_next")
		return
	var spec := String(args.get("routetest", "")).split(":")
	_list = [[spec[0], int(spec[1]) if spec.size() > 1 else 0, int(spec[2]) if spec.size() > 2 else 1]]
	call_deferred("_next")


func _next() -> void:
	_li += 1
	if _li >= _list.size():
		var ok := _results.filter(func(r): return r["ok"]).size()
		print("ROUTETEST FERTIG: %d von %d durchfahren" % [ok, _results.size()])
		if _out != "":
			var f := FileAccess.open(_out, FileAccess.WRITE)
			f.store_string(JSON.stringify(_results, " "))
			f.close()
		main.get_tree().quit()
		return
	var e: Array = _list[_li]
	_tile = String(e[0])
	_wid = int(e[1])
	_dir = int(e[2]) if e.size() > 2 else 1
	pts.clear()
	_t = 0.0
	_started = false
	_resets = 0
	_stuck_t = 0.0
	_min_dy = 99.0
	_max_dy = -99.0
	_best = 0
	_why = ""
	main.world.enabled = false
	await main.world.load_now(_tile)
	for i in 3:
		await get_tree().physics_frame
	_active = true


func _finish(ok: bool, msg: String) -> void:
	_active = false
	print(msg)
	_results.append({"tile": _tile, "id": _wid, "dir": _dir, "ok": ok, "msg": msg})
	# übrige Kacheln weit weg entladen (Speicher)
	for k in main.world.tiles.keys():
		if k != _tile and _li + 1 < _list.size() and k != String(_list[_li + 1][0]):
			var t: Tile = main.world.tiles[k]
			main.world.tiles.erase(k)
			main.world.tile_removed.emit(t)
			main.world._unload(t)
	call_deferred("_next")


func _physics_process(delta: float) -> void:
	if main.get("player") == null or not _active:
		return
	var player: PlayerCar = main.player
	if not _started:
		var t = main.world.tiles.get(_tile)
		if t == null:
			return
		var pieces: Array = []
		for r in (t as Tile).city["roads"]:
			if int(r["id"]) == _wid:
				pieces.append(r)
		if pieces.is_empty():
			_finish(false, "ROUTETEST %s:%d: Weg nicht gefunden" % [_tile, _wid])
			return
		# Stücke in Reihenfolge verketten
		var chain: Array = (pieces[0]["pts"] as Array).duplicate()
		pieces.remove_at(0)
		var grew := true
		while grew and not pieces.is_empty():
			grew = false
			for i in pieces.size():
				var q: Array = pieces[i]["pts"]
				var e: Array = chain[chain.size() - 1]
				var s0: Array = chain[0]
				if Vector2(q[0][0] - e[0], q[0][1] - e[1]).length() < 0.5:
					chain.append_array(q.slice(1))
				elif Vector2(q[q.size() - 1][0] - s0[0], q[q.size() - 1][1] - s0[1]).length() < 0.5:
					chain = q.slice(0, q.size() - 1) + chain
				else:
					continue
				pieces.remove_at(i)
				grew = true
				break
		if _dir < 0:
			chain.reverse()
		var road: Dictionary = (t as Tile).city["roads"].filter(func(r): return int(r["id"]) == _wid)[0]
		var off: float = 0.0 if int(road["oneway"]) != 0 else minf(float(road["width"]) * 0.25, 1.8)
		for i in chain.size():
			var a: Array = chain[maxi(i - 1, 0)]
			var b: Array = chain[mini(i + 1, chain.size() - 1)]
			var d := Vector2(b[0] - a[0], b[1] - a[1]).normalized()
			var n := Vector2(-d.y, d.x)
			pts.append(Vector3(float(chain[i][0]) + n.x * off, float(chain[i][2]), float(chain[i][1]) + n.y * off))
		var p0: Vector3 = pts[0]
		var p1: Vector3 = pts[mini(3, pts.size() - 1)]
		var dir := p1 - p0
		dir.y = 0.0
		dir = dir.normalized()
		var st := p0 - dir * 12.0
		st.y = main.world.height_at(st.x, st.z) + 0.9
		if absf(st.y - p0.y) > 3.0:
			st = p0 + dir * 0.5
			st.y = p0.y + 0.9
		pts.push_front(Vector3(st.x, st.y - 0.9, st.z))
		player.global_transform = Transform3D(Basis(Vector3.UP, atan2(-dir.x, -dir.z)), st)
		player.linear_velocity = Vector3.ZERO
		player.override_input = true
		_started = true
		_last = st
		var L := 0.0
		for i in pts.size() - 1:
			L += Vector2(pts[i + 1].x - pts[i].x, pts[i + 1].z - pts[i].z).length()
		print("ROUTETEST Start %s:%d %s (%.0f m)" % [_tile, _wid, String(road["name"]), L])
		return
	_t += delta
	var p := player.global_position
	if p.distance_to(_last) > 12.0 * maxf(delta, 0.02) * 10.0:
		_resets += 1
		if _why == "":
			_why = "Rücksetzen bei (%.0f,%.0f)" % [_last.x, _last.z]
	_last = p
	var best := _best
	var bd := INF
	for i in range(maxi(_best - 5, 0), mini(_best + 30, pts.size())):
		var d := Vector2(pts[i].x - p.x, pts[i].z - p.z).length()
		if d < bd:
			bd = d
			best = i
	_best = best
	# Zielpunkt ~8 m voraus
	var acc := 0.0
	var k := best
	while k < pts.size() - 1 and acc < 8.0:
		acc += Vector2(pts[k + 1].x - pts[k].x, pts[k + 1].z - pts[k].z).length()
		k += 1
	var tgt: Vector3 = pts[k]
	var fwd := -player.global_transform.basis.z
	var to := tgt - p
	to.y = 0.0
	var ang := atan2(fwd.cross(to.normalized()).y, fwd.dot(to.normalized()))
	player.in_steer = clampf(-ang * 2.0, -1.0, 1.0)
	var v := player.linear_velocity.length()
	player.in_throttle = _gas if v < 14.0 else 0.0
	player.in_brake = 0.0
	if bd < 6.0 and best > 0:
		var dy: float = p.y - (pts[best] as Vector3).y
		_min_dy = minf(_min_dy, dy)
		_max_dy = maxf(_max_dy, dy)
	if v < 1.0 and _t > 3.0:
		_stuck_t += delta
	else:
		_stuck_t = 0.0
	var done := best >= pts.size() - 2 and bd < 6.0
	var fail := _stuck_t > 4.0 or _t > 90.0
	if fail and _why == "":
		_why = "steckt fest bei (%.1f,%.1f,y=%.1f)" % [p.x, p.z, p.y] if _stuck_t > 4.0 else "Zeit abgelaufen"
	if done or fail:
		_finish(done and _resets == 0, "ROUTETEST %s %s:%d: %d/%d Punkte, Rücksetzen %d, Höhe über Profil %.2f … %.2f m %s" % [
			"DURCHFAHREN" if done and _resets == 0 else "ABBRUCH", _tile, _wid, best, pts.size(), _resets, _min_dy, _max_dy, _why])
