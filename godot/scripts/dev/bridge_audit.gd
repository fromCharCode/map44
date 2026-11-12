class_name BridgeAudit
extends Node
## Entwickler: prüft alle Brücken Kachel für Kachel mit Physikabfragen (kein Fahren nötig).
##   godot --path . -- --cam=0,0,0,-30,80 --bridgeaudit[=400_5654,410_5656] [--auditout=<json>]
## Auf der Brücke: autogroßer Körper frei, Deck trägt (Fahrbahnmitte und Spuren).
## Unter der Brücke: jede Kfz-Straße unter Brückenbauteilen wird alle 2 m (Mitte + äußere Spuren) geprüft:
##   - Hindernis im Lichtraum 0,4–1,65 m über der Fahrbahn (Pfeiler, Wände, Geländer, Möbel …)
##   - Durchfahrtshöhe (Strahl nach oben bis zum Bauwerk); < 2,2 m = unbefahrbar, < 3,5 m = auffällig
## Ergebnis als JSON (Standard user://bridge_audit.json) und Zusammenfassung auf stdout.

const WALK := ["footway", "path", "cycleway", "steps", "pedestrian", "bridleway", "corridor", "platform"]
const STEP := 2.0

var main: Node
var world: World
var keys: Array = []
var out_path := "user://bridge_audit.json"
var report := {"over": [], "under": [], "steps": [], "low": [], "under_all": [], "stats": {}}
var _box := BoxShape3D.new()
var _box_q := PhysicsShapeQueryParameters3D.new()
var _deck_box := BoxShape3D.new()
var _deck_q := PhysicsShapeQueryParameters3D.new()


func start(m: Node, args: Dictionary) -> void:
	main = m
	world = m.world
	var spec := String(args.get("bridgeaudit", ""))
	if spec != "" and spec != "true" and spec != "1":
		keys = Array(spec.split(","))
	else:
		keys = world.available.keys()
		keys.sort()
	out_path = String(args.get("auditout", out_path))
	_box.size = Vector3(1.7, 1.25, 1.6)
	_box_q.shape = _box
	_box_q.collision_mask = 1
	_deck_box.size = Vector3(1.8, 0.7, 4.0)
	_deck_q.shape = _deck_box
	_deck_q.collision_mask = 1


func run() -> void:
	world.enabled = false
	var t_all := Time.get_ticks_msec()
	for k in keys:
		# 3×3-Umfeld laden (LoD2-Brückenteile gehören nur der Kachel ihres Schwerpunkts, reichen aber hinüber),
		# alles andere entladen (Speicher)
		var need := {}
		var kp := String(k).split("_")
		for de in [-2, 0, 2]:
			for dn in [-2, 0, 2]:
				var nk := "%d_%d" % [int(kp[0]) + de, int(kp[1]) + dn]
				if world.available.has(nk):
					need[nk] = true
		for ok in world.tiles.keys():
			if not need.has(ok):
				var t: Tile = world.tiles[ok]
				world.tiles.erase(ok)
				world.tile_removed.emit(t)
				await world._unload(t)
		for nk in need:
			await world.load_now(nk)
		var tile: Tile = world.tiles.get(k)
		if tile == null:
			continue
		for i in 4:
			await get_tree().physics_frame
		var t0 := Time.get_ticks_msec()
		var st := {"over": 0, "under_pts": 0, "under_roads": 0, "blocked": 0, "low": 0}
		_check_over(tile, st)
		_check_under(tile, st)
		report["stats"][k] = st
		print("AUDIT %s: Brücken-Fahrbahnen %d auffällig, unter Brücken %d Straßen/%d Punkte, blockiert %d, Stufen %d, niedrig %d (%d ms)" % [
			k, st["over"], st["under_roads"], st["under_pts"], st["blocked"], int(st.get("steps", 0)), st["low"], Time.get_ticks_msec() - t0])
	var f := FileAccess.open(out_path, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(report, " "))
		f.close()
	print("AUDIT FERTIG: %d Kacheln, %d Brückenfahrbahnen auffällig, %d Straßen mit Hindernis unter Brücken, %d mit Stufe, %d zu niedrig (%d s) -> %s" % [
		keys.size(), report["over"].size(), report["under"].size(), report["steps"].size(), report["low"].size(),
		(Time.get_ticks_msec() - t_all) / 1000, ProjectSettings.globalize_path(out_path)])
	main.get_tree().quit()


static func owner_of(col: Object) -> String:
	## Modul der Kachel (Roads, Buildings, …) + Bauteilart (meta "kind") des getroffenen Körpers
	var n := col as Node
	var kind := ""
	while n != null:
		if kind == "" and n.has_meta("kind"):
			kind = String(n.get_meta("kind"))
		var par := n.get_parent()
		if par is Tile:
			return String(n.name) + ("/" + kind if kind != "" else "")
		n = par
	return "?" + ("/" + kind if kind != "" else "")


static func is_bridge_owner(o: String) -> bool:
	return o.begins_with("Roads") or o.begins_with("Landmarks/bridge")


func _offsets(r: Dictionary) -> Array:
	## Querlagen der Prüfung: Fahrbahnmitte und die Mitten der äußersten Fahrstreifen (dort fährt ein Auto; höchstens
	## 1,9 m vom Rand) – "befahrbar" heißt: ein Fahrzeug mittig in jeder Spur berührt nichts. Bordstein/Geländer an der
	## Fahrbahnkante sind kein Hindernis.
	var w := float(r["width"]) - float(r.get("pl", 0.0)) - float(r.get("pr", 0.0))
	if w < 5.0:
		return [0.0]
	var lanes := maxi(int(r.get("lanes", 1)), 1)
	var per := maxi(lanes / 2, 1) if int(r.get("oneway", 0)) == 0 else lanes
	var lane_w := (w * 0.5) / float(per) if int(r.get("oneway", 0)) == 0 else w / float(lanes)
	var o := w * 0.5 - minf(lane_w * 0.5, 1.9)
	if o < 0.6:
		return [0.0]
	return [0.0, -o, o]


func _check_over(tile: Tile, st: Dictionary) -> void:
	var space := get_viewport().world_3d.direct_space_state
	for r in tile.city["roads"]:
		if not r["bridge"] or String(r["cls"]) in WALK:
			continue
		var pts: Array = r["pts"]
		var bad := 0
		var first := ""
		for i in pts.size() - 1:
			var a := Vector3(pts[i][0], pts[i][2], pts[i][1])
			var c := Vector3(pts[i + 1][0], pts[i + 1][2], pts[i + 1][1])
			var seg := Vector2(c.x - a.x, c.z - a.z).length()
			if seg < 0.05:
				continue
			var dir := Vector3(c.x - a.x, 0, c.z - a.z) / seg
			var nrm := Vector3(-dir.z, 0, dir.x)
			var n := int(seg / STEP) + 1
			for j in n:
				var p0 := a.lerp(c, float(j) / n)
				for off in _offsets(r):
					var p: Vector3 = p0 + nrm * float(off)
					if Tunnels.inside(p + Vector3(0, 1, 0)):
						continue
					_deck_q.transform = Transform3D(Basis.looking_at(dir, Vector3.UP), p + Vector3(0, 0.75, 0))
					var hits := space.intersect_shape(_deck_q, 4)
					var msg := ""
					for h in hits:
						var o := owner_of(h["collider"])
						if o.begins_with("Terrain"):
							continue
						msg = "Hindernis %s" % o
						break
					if msg == "":
						var rq := PhysicsRayQueryParameters3D.create(p + Vector3(0, 1.5, 0), p - Vector3(0, 2.0, 0), 1)
						rq.hit_back_faces = false
						var rh := space.intersect_ray(rq)
						if rh.is_empty() or absf(float(rh["position"].y) - p.y) > 0.5:
							msg = "kein Boden (Soll %.1f, ist %s)" % [p.y, "–" if rh.is_empty() else "%.1f" % rh["position"].y]
					if msg != "":
						bad += 1
						if first == "":
							first = "(%.0f,%.0f,y=%.1f, quer %+.1f) %s" % [p.x, p.z, p.y, off, msg]
		if bad > 0:
			st["over"] += 1
			report["over"].append({"tile": tile.key, "id": int(r["id"]), "name": r["name"], "cls": r["cls"], "n": bad, "first": first})


func _check_under(tile: Tile, st: Dictionary) -> void:
	## Kfz-Straßen ohne Brückenflag: befahrbare Oberfläche per Strahl von oben (Profilhöhe + 1,3 m) bestimmen –
	## liegt dort ein Deck auf Fahrbahnhöhe, fährt man auf ihm (kein Unterführungspunkt). Darüber: Bauwerk?
	## Dann Lichtraum (Kasten 0,4–1,65 m) und Durchfahrtshöhe prüfen. Treffer werden eingeordnet:
	##   stufe   – Bauteil beginnt < 2 m über der Fahrbahn (Deckende/Kante auf Fahrbahnhöhe)
	##   hindernis – Pfeiler/Wand/Bogen/Geländer im Lichtraum unter einem höheren Bauwerk
	##   niedrig – Bauwerksunterkante 1,65–3,5 m über der Fahrbahn
	var space := get_viewport().world_3d.direct_space_state
	var terr := tile.terrain
	for r in tile.city["roads"]:
		if r["bridge"] or String(r["cls"]) in WALK:
			continue
		var pts: Array = r["pts"]
		var under := 0
		var blocked := 0
		var steps := 0
		var low := 0
		var min_h := 99.0
		var first_block := ""
		var first_step := ""
		var first_low := ""
		var pts_out: Array = []
		for i in pts.size() - 1:
			var a := Vector3(pts[i][0], pts[i][2], pts[i][1])
			var c := Vector3(pts[i + 1][0], pts[i + 1][2], pts[i + 1][1])
			var seg := Vector2(c.x - a.x, c.z - a.z).length()
			if seg < 0.05:
				continue
			var dir := Vector3(c.x - a.x, 0, c.z - a.z) / seg
			var nrm := Vector3(-dir.z, 0, dir.x)
			var n := int(seg / STEP) + 1
			for j in n:
				var q := a.lerp(c, float(j) / n)
				for off in _offsets(r):
					var x: float = q.x + nrm.x * float(off)
					var z: float = q.z + nrm.z * float(off)
					if not terr.contains(x, z):
						continue
					var yp: float = q.y
					if Tunnels.inside(Vector3(x, yp + 1.0, z)):
						continue
					# befahrbare Oberfläche
					var dn := PhysicsRayQueryParameters3D.create(Vector3(x, yp + 1.3, z), Vector3(x, yp - 3.0, z), 1)
					var dh := space.intersect_ray(dn)
					var ys := terr.height_at(x, z)
					if not dh.is_empty():
						ys = float(dh["position"].y)
						if is_bridge_owner(owner_of(dh["collider"])) and absf(ys - yp) < 0.6:
							continue                      # Deck auf Fahrbahnhöhe: man fährt darauf
					# Bauwerk über der Fahrbahn?
					var up := PhysicsRayQueryParameters3D.create(Vector3(x, ys + 0.3, z), Vector3(x, ys + 45.0, z), 1)
					up.hit_back_faces = true
					var uh := space.intersect_ray(up)
					var over_bridge := false
					var h := 99.0
					if not uh.is_empty():
						var o := owner_of(uh["collider"])
						if is_bridge_owner(o):
							over_bridge = true
							h = float(uh["position"].y) - ys
					_box_q.transform = Transform3D(Basis.looking_at(dir, Vector3.UP), Vector3(x, ys + 0.4 + 0.625, z))
					var hits := space.intersect_shape(_box_q, 6)
					var blk := ""
					for hh in hits:
						var o2 := owner_of(hh["collider"])
						if o2.begins_with("Terrain"):
							continue
						if is_bridge_owner(o2) or over_bridge:
							blk = o2
							break
					if not over_bridge and blk == "":
						continue
					under += 1
					min_h = minf(min_h, h)
					if blk != "":
						# Oberkante des Treffers: Strahl von 6 m über der Fahrbahn nach unten
						var tq := PhysicsRayQueryParameters3D.create(Vector3(x, ys + 6.0, z), Vector3(x, ys + 0.35, z), 1)
						var th := space.intersect_ray(tq)
						var dtop: float = (float(th["position"].y) - ys) if not th.is_empty() else 99.0
						var kind := "stufe" if dtop < 2.0 else "hindernis"
						if kind == "stufe":
							steps += 1
							if first_step == "":
								first_step = "(%.1f,%.1f,y=%.2f, quer %+.1f) Oberkante %+.2f %s" % [x, z, ys, off, dtop, blk]
						else:
							blocked += 1
							if first_block == "":
								first_block = "(%.1f,%.1f,y=%.2f, quer %+.1f) %s" % [x, z, ys, off, blk]
						if pts_out.size() < 60:
							pts_out.append([snappedf(x, 0.1), snappedf(z, 0.1), snappedf(ys, 0.01), off, kind, blk, snappedf(h, 0.01), snappedf(dtop, 0.01)])
					elif h < 3.5:
						low += 1
						if first_low == "":
							first_low = "(%.1f,%.1f,y=%.2f) %.2f m %s" % [x, z, ys, h, owner_of(uh["collider"])]
						if pts_out.size() < 60:
							pts_out.append([snappedf(x, 0.1), snappedf(z, 0.1), snappedf(ys, 0.01), off, "niedrig", owner_of(uh["collider"]), snappedf(h, 0.01), 0.0])
		if under == 0:
			continue
		st["under_roads"] += 1
		st["under_pts"] += under
		report["under_all"].append([tile.key, int(r["id"]), String(r["cls"]), under, snappedf(min_h, 0.01)])
		var rec := {"tile": tile.key, "id": int(r["id"]), "name": r["name"], "cls": r["cls"], "of": under, "min_h": min_h,
			"pts": pts_out}
		if blocked > 0:
			st["blocked"] += 1
			var e := rec.duplicate()
			e["n"] = blocked
			e["first"] = first_block
			report["under"].append(e)
		if steps > 0:
			st["steps"] = int(st.get("steps", 0)) + 1
			var e2 := rec.duplicate()
			e2["n"] = steps
			e2["first"] = first_step
			report["steps"].append(e2)
		if low > 0:
			st["low"] += 1
			var e3 := rec.duplicate()
			e3["n"] = low
			e3["first"] = first_low
			report["low"].append(e3)
