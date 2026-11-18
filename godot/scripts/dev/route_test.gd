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
var _len := 0.0
var _recov := 0                   # Rangierversuche (zurücksetzen und neu ansetzen) auf dieser Strecke
var _recov_t := 0.0
var _trace := OS.get_environment("DRESDEN_ROUTETRACE") != ""


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
	_recov = 0
	_recov_t = 0.0
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
		# rechte Fahrspur im Fahrband (Parkstreifen pl/pr abgezogen, wie traffic.gd lane_offset)
		var pl := float(road.get("pl", 0.0))
		var pr := float(road.get("pr", 0.0))
		var wc := float(road["width"]) - pl - pr
		# einspurige Straßen (lanes=1, auch mit Gegenverkehr): mittig fahren
		var single := int(road.get("lanes", 2)) <= 1
		var off: float = (pl - pr) * 0.5 * float(_dir) + (0.0 if int(road["oneway"]) != 0 or single else minf(wc * 0.25, 1.8))
		for i in chain.size():
			var a: Array = chain[maxi(i - 1, 0)]
			var b: Array = chain[mini(i + 1, chain.size() - 1)]
			var d := Vector2(b[0] - a[0], b[1] - a[1]).normalized()
			var n := Vector2(-d.y, d.x)
			pts.append(Vector3(float(chain[i][0]) + n.x * off, float(chain[i][2]), float(chain[i][1]) + n.y * off))
		# Stützpunkte auf höchstens 3 m verdichten: bei langen Geraden sprang der „nächste Punkt“ sonst 20 m vor
		# einer Biegung auf den Knickpunkt, das Ziel lag dann schon hinter der Biegung und das Auto kürzte ab
		var dense: Array = []
		for i in pts.size() - 1:
			var pa: Vector3 = pts[i]
			var pb: Vector3 = pts[i + 1]
			var nseg := maxi(int(ceil(Vector2(pb.x - pa.x, pb.z - pa.z).length() / 3.0)), 1)
			for j in nseg:
				dense.append(pa.lerp(pb, float(j) / float(nseg)))
		dense.append(pts[pts.size() - 1])
		pts = dense
		# nur der Teil im Kachelinneren (8 m Rand): im Test ist nur diese Kachel geladen – am Rand hing das Auto
		# halb über dem Nichts und blieb stecken, ohne dass die Straße schuld war
		var ke := int(_tile.split("_")[0])
		var kn := int(_tile.split("_")[1])
		var bx0 := (ke - 411) * 1000.0 + 8.0
		var bx1 := (ke - 409) * 1000.0 - 8.0
		var bz0 := -((kn + 2) * 1000.0 - 5656200.0) + 8.0
		var bz1 := -(kn * 1000.0 - 5656200.0) - 8.0
		var best_a := 0
		var best_n := 0
		var a0 := -1
		for i in pts.size() + 1:
			var inside: bool = i < pts.size() and pts[i].x > bx0 and pts[i].x < bx1 and pts[i].z > bz0 and pts[i].z < bz1
			if inside and a0 < 0:
				a0 = i
			elif not inside and a0 >= 0:
				if i - a0 > best_n:
					best_n = i - a0
					best_a = a0
				a0 = -1
		if best_n < 2:
			_finish(false, "ROUTETEST %s:%d: Weg liegt nicht im Kachelinneren" % [_tile, _wid])
			return
		pts = pts.slice(best_a, best_a + best_n)
		# Start 5 m hinter dem Wegbeginn (am Beginn liegen Knoten, Portale, Plattenkanten – dort blieb das Auto beim
		# Absetzen teils hängen, ohne dass die Straße unfahrbar war)
		var acc0 := 0.0
		var i0 := 0
		while i0 < pts.size() - 2 and acc0 < 5.0:
			acc0 += Vector2(pts[i0 + 1].x - pts[i0].x, pts[i0 + 1].z - pts[i0].z).length()
			i0 += 1
		if i0 > 0 and pts.size() - i0 >= 3:
			pts = pts.slice(i0)
		var p0: Vector3 = pts[0]
		# Startrichtung: Tangente über die ersten ~6 m. Vorher zeigte das Auto auf den vierten Punkt – bei langen
		# Stücken lag der bis zu 130 m weit hinter einer Biegung, das Auto stand dann 15° schräg in der Fahrbahn
		var p1: Vector3 = pts[1]
		var acc1 := 0.0
		for i in range(1, pts.size()):
			acc1 += Vector2(pts[i].x - pts[i - 1].x, pts[i].z - pts[i - 1].z).length()
			p1 = pts[i]
			if acc1 >= 6.0:
				break
		var dir := p1 - p0
		dir.y = 0.0
		dir = dir.normalized()
		# Start auf der Fahrbahn selbst (1 m nach Wegbeginn, Profilhöhe): 12 m davor lag das Auto teils neben der
		# Straße (Böschung, Mauer) und blieb hängen, ohne dass die Straße unter der Brücke daran schuld war
		var st := p0 + dir * 1.0
		st.y = p0.y + 0.9
		player.global_transform = Transform3D(Basis(Vector3.UP, atan2(-dir.x, -dir.z)), st)
		player.linear_velocity = Vector3.ZERO
		player.angular_velocity = Vector3.ZERO
		# Fahrbarkeit prüfen, nicht Unfallschäden: das Absetzen (0,9 m) und Rempler früherer Strecken summierten
		# sich sonst (Motorleistung, verbogene/abgefallene Räder) – das Auto blieb dann auf freier Straße stehen
		player.damage_enabled = false
		player.repair()
		player.override_input = true
		_started = true
		_last = st
		var L := 0.0
		for i in pts.size() - 1:
			L += Vector2(pts[i + 1].x - pts[i].x, pts[i + 1].z - pts[i].z).length()
		_len = L
		print("ROUTETEST Start %s:%d %s (%.0f m)" % [_tile, _wid, String(road["name"]), L])
		return
	_t += delta
	var p := player.global_position
	if p.distance_to(_last) > 12.0 * maxf(delta, 0.02) * 10.0:
		_resets += 1
		if _why == "":
			_why = "Rücksetzen bei (%.0f,%.0f)" % [_last.x, _last.z]
	_last = p
	if _trace and Engine.get_physics_frames() % 30 == 0:
		print("ROUTETEST Spur (%.1f,%.1f,y=%.2f) v %.1f Lenk %.2f Punkt %d" % [p.x, p.z, p.y, player.linear_velocity.length(), player.in_steer, _best])
	var best := _best
	var bd := INF
	for i in range(maxi(_best - 5, 0), mini(_best + 30, pts.size())):
		var d := Vector2(pts[i].x - p.x, pts[i].z - p.z).length()
		if d < bd:
			bd = d
			best = i
	_best = best
	# Zielpunkt voraus: 8 m bei Fahrt, bei langsamer Fahrt kürzer (4 m) – mit festen 8 m schnitt das Auto enge
	# Ecken direkt hinter Pfeilern und an Geländern so stark, dass es daran hängen blieb
	var look := clampf(player.linear_velocity.length() * 0.9, 4.0, 8.0)
	var acc := 0.0
	var k := best
	while k < pts.size() - 1 and acc < look:
		acc += Vector2(pts[k + 1].x - pts[k].x, pts[k + 1].z - pts[k].z).length()
		k += 1
	var tgt: Vector3 = pts[k]
	var fwd := -player.global_transform.basis.z
	var to := tgt - p
	to.y = 0.0
	var ang := atan2(fwd.cross(to.normalized()).y, fwd.dot(to.normalized()))
	player.in_steer = clampf(-ang * 2.0, -1.0, 1.0)
	var v := player.linear_velocity.length()
	# vor engen Kurven langsamer (Richtungsänderung auf den nächsten ~18 m): sonst schoss das Auto mit 14 m/s
	# über eine 100°-Kehre in die Böschung
	var turn := 0.0
	var acc2 := 0.0
	var k2 := best
	while k2 < pts.size() - 2 and acc2 < 18.0:
		var d1 := Vector2(pts[k2 + 1].x - pts[k2].x, pts[k2 + 1].z - pts[k2].z)
		var d2 := Vector2(pts[k2 + 2].x - pts[k2 + 1].x, pts[k2 + 2].z - pts[k2 + 1].z)
		if d1.length() > 0.05 and d2.length() > 0.05:
			turn += absf(d1.angle_to(d2))
		acc2 += d1.length()
		k2 += 1
	var vmax := lerpf(14.0, 4.0, clampf((turn - 0.35) / 1.2, 0.0, 1.0))
	player.in_throttle = _gas if v < vmax else 0.0
	player.in_brake = 0.6 if v > vmax + 2.0 else 0.0
	if bd < 6.0 and best > 0:
		var dy: float = p.y - (pts[best] as Vector3).y
		_min_dy = minf(_min_dy, dy)
		_max_dy = maxf(_max_dy, dy)
	if v < 1.0 and _t > 3.0:
		_stuck_t += delta
	else:
		_stuck_t = 0.0
	# Rangieren: hängt das Auto an einem Objekt am Fahrbahnrand (Kurve geschnitten), setzt es wie ein Fahrer
	# höchstens zweimal zurück und fährt neu an. Ist die Straße wirklich versperrt, bleibt es wieder hängen.
	if _recov_t > 0.0:
		_recov_t -= delta
		player.in_throttle = 0.0
		player.in_brake = 0.7 if _recov_t > 0.6 else 0.0          # Bremse im Stand = rückwärts
		player.in_steer = clampf(ang * 2.0, -1.0, 1.0)
		_stuck_t = 0.0
		return
	if _stuck_t > 4.0 and _recov < 2:
		_recov += 1
		_recov_t = 3.2
		_stuck_t = 0.0
		return
	var done := best >= pts.size() - 2 and bd < 6.0
	var fail := _stuck_t > 4.0 or _t > maxf(90.0, 20.0 + _len / 9.0)
	if fail and _why == "":
		_why = "steckt fest bei (%.1f,%.1f,y=%.1f)" % [p.x, p.z, p.y] if _stuck_t > 4.0 else "Zeit abgelaufen"
		# seitliche Abweichung von der Sollspur (vorzeichenbehaftet, + = rechts)
		var j := mini(best, pts.size() - 2)
		var sd := Vector2(pts[j + 1].x - pts[j].x, pts[j + 1].z - pts[j].z).normalized()
		var rel := Vector2(p.x - pts[j].x, p.z - pts[j].z)
		_why += " Spurabweichung %+.2f m" % (rel.x * -sd.y + rel.y * sd.x)
	if fail:
		_why += " " + _blockers(player)
		var ds := PhysicsServer3D.body_get_direct_state(player.get_rid())
		for ci in ds.get_contact_count():
			var co := ds.get_contact_collider_object(ci)
			_why += " <K %s lokal %s n %s>" % [BridgeAudit.owner_of(co) if co != null else "RID", str((player.global_transform.affine_inverse() * ds.get_contact_collider_position(ci)).snappedf(0.01)), str(ds.get_contact_local_normal(ci).snappedf(0.01))]
		_why += " {Gas %.2f Bremse %.2f Lenk %.2f Gang %d %.0f/min vmax %.1f Kurve %.2f Rad-ω %s}" % [player.in_throttle, player.in_brake, player.in_steer, player.gear, player.rpm, vmax, turn, str([snappedf(player.wheels["FL"]["omega"], 0.1), snappedf(player.wheels["RL"]["omega"], 0.1)])]
	if done or fail:
		_finish(done and _resets == 0, "ROUTETEST %s %s:%d: %d/%d Punkte, Rücksetzen %d, Rangieren %d, Höhe über Profil %.2f … %.2f m %s" % [
			"DURCHFAHREN" if done and _resets == 0 else "ABBRUCH", _tile, _wid, best, pts.size(), _resets, _recov, _min_dy, _max_dy, _why])


func _blockers(car: RigidBody3D) -> String:
	## Fehlerbild: was das Auto berührt (Modul/Bauteil), worauf es steht und wie es liegt
	var space := car.get_world_3d().direct_space_state
	var q := PhysicsShapeQueryParameters3D.new()
	var bx := BoxShape3D.new()
	bx.size = Vector3(2.4, 1.4, 5.4)
	q.shape = bx
	q.transform = Transform3D(car.global_transform.basis, car.global_position + car.global_transform.basis.y * 0.4)
	q.exclude = [car.get_rid()]
	var seen := {}
	for h in space.intersect_shape(q, 24):
		var o := BridgeAudit.owner_of(h["collider"])
		if o.begins_with("?") and h["collider"] is Node:
			o += "(" + str((h["collider"] as Node).get_path()) + ")"
		seen[o] = true
	var rq := PhysicsRayQueryParameters3D.create(car.global_position + Vector3(0, 2.0, 0), car.global_position - Vector3(0, 6.0, 0))
	rq.exclude = [car.get_rid()]
	rq.hit_back_faces = true
	var g := space.intersect_ray(rq)
	var under := "–" if g.is_empty() else "%s y=%.2f" % [BridgeAudit.owner_of(g["collider"]), (g["position"] as Vector3).y]
	var pc := car as PlayerCar
	var dmg := ""
	if pc != null and pc.damage != null:
		dmg = "; Motor %.2f, Räder ab %s, Bodenkontakt %d" % [pc.engine_health, str(pc.damage.wheel_lost), pc.grounded]
	return "[berührt %s; Boden %s; oben %.2f; v %.1f%s]" % [",".join(seen.keys()), under,
		car.global_transform.basis.y.y, car.linear_velocity.length(), dmg]
