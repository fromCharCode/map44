class_name VehShot
extends Node
## Entwickler: Fahrzeug-Nahaufnahmen (Busse/Straßenbahnen) als Bilderserie.
##   godot --path . -- --vehshot=<ordner> [--vehkind=bus|tram] [--buses=20] [--trams=8] [--drive=x,z] [--time=h]
## Wartet, bis Fahrzeuge da sind, setzt dann eine eigene Kamera nacheinander vor/neben/hinter bis zu 4 Fahrzeuge
## und speichert je Ansicht ein PNG (<ordner>/<art>_<n>_<ansicht>.png). Druckt Linie/Ziel bzw. Anzeigentexte.

var main: Node
var out := ""
var kind := "bus"
var cam: Camera3D
var _t := 0.0
var _busy := false


func start(m: Node, args: Dictionary) -> void:
	main = m
	out = String(args.get("vehshot", "user://vehshot"))
	kind = String(args.get("vehkind", "bus"))
	DirAccess.make_dir_recursive_absolute(out)


func _process(delta: float) -> void:
	if _busy or main.get("traffic") == null:
		return
	_t += delta
	var vehicles := _vehicles()
	if (vehicles.size() >= 4 and _t > (20.0 if kind == "stop" else 12.0)) or _t > 40.0:
		_busy = true
		_run(vehicles)


func _vehicles() -> Array:
	var res: Array = []
	if kind == "stop":
		# Abfahrtsanzeiger nahe dem Spieler (Label der ersten Zeile, Spalte Ziel)
		var pp: Vector3 = main.player.global_position
		var cand: Array = []
		for t in main.world.tiles.values():
			var st = (t as Node).get_node_or_null("Stops")
			if st == null:
				continue
			for d in st._dfis:
				var lb: Label3D = d[3][0][1]
				if is_instance_valid(lb) and lb.is_inside_tree():
					cand.append([lb.global_position.distance_to(pp), lb])
		cand.sort_custom(func(a, b): return a[0] < b[0])
		for c in cand:
			res.append(c[1])
		return res
	if kind == "bus":
		for c in main.traffic.cars:
			if c is BusCar and is_instance_valid(c):
				res.append(c)
	else:
		for u in main.trams.trams:
			if is_instance_valid(u) and not (u as TramUnit).dead:
				res.append(u)
	return res


func _run(vehicles: Array) -> void:
	cam = Camera3D.new()
	cam.far = 2000.0
	cam.fov = 55.0
	main.add_child(cam)
	cam.make_current()
	main.get_tree().paused = false
	var n := 0
	if kind == "stop":
		await _stop_shots(vehicles)
		return
	for v in vehicles.slice(0, 4):
		if not is_instance_valid(v):
			continue
		var views := [["front", Vector3(1.5, 2.3, -11.0)], ["side", Vector3(9.0, 2.0, 0.0)], ["rear", Vector3(-1.5, 2.3, 11.0)]]
		if kind == "tram":
			views = [["front", Vector3(2.0, 2.6, -13.0)], ["front34", Vector3(7.5, 2.4, -9.0)], ["side", Vector3(13.0, 2.4, 12.0)], ["rear", Vector3(-2.0, 2.6, 13.0)]]
		for vw in views:
			var xf := _xf_of(v, String(vw[0]))
			var p: Vector3 = xf * (vw[1] as Vector3)
			var look: Vector3 = xf * Vector3(0, 1.9, (vw[1] as Vector3).z * 0.15)
			cam.global_position = p
			cam.look_at(look, Vector3.UP)
			for i in 4:
				await main.get_tree().process_frame
			var img := main.get_viewport().get_texture().get_image()
			var fn := "%s/%s_%d_%s.png" % [out, kind, n, vw[0]]
			img.save_png(fn)
		print("VEHSHOT %s %d: %s" % [kind, n, _info(v)])
		n += 1
	print("VEHSHOT fertig: %d Fahrzeuge" % n)
	main.get_tree().quit()


func _xf_of(v: Node, view: String) -> Transform3D:
	if v is TramUnit:
		var u := v as TramUnit
		var b: Node3D = u.bodies[0] if view != "rear" else u.bodies[u.bodies.size() - 1]
		var xf := b.global_transform
		if view == "rear":
			# hinterer Abschnitt: Kamera hinter dessen Ende, Blick auf das Heck
			return xf
		return xf
	return (v as Node3D).global_transform


func _info(v: Node) -> String:
	if v is BusCar:
		var b := v as BusCar
		var txt: Array = []
		for lb in b.labels:
			txt.append((lb as Label3D).text)
		var r: Dictionary = main.traffic.bus_routes[b.line] if b.line >= 0 else {}
		return "Modell %s Linie %s Ziel '%s' Anzeigen %s" % [b.model_file, r.get("ref", "?"), r.get("to", "?"), str(txt)]
	var u := v as TramUnit
	return "Abschnitte %d Offsets %s" % [u.bodies.size(), str(u.offsets)]


func _stop_shots(lbs: Array) -> void:
	var n := 0
	for lb in lbs.slice(0, 4):
		var l := lb as Label3D
		if not is_instance_valid(l):
			continue
		var xf := l.global_transform
		var nrm := xf.basis.z.normalized()
		for vw in [["dfi", 3.2, 0.2, 0.0], ["platz", 14.0, 2.5, 6.0]]:
			var side := xf.basis.x.normalized() * float(vw[3])
			cam.global_position = xf.origin + nrm * float(vw[1]) + Vector3(0, float(vw[2]), 0) + side
			cam.look_at(xf.origin - Vector3(0, 0.6 if vw[0] == "platz" else 0.0, 0), Vector3.UP)
			for i in 6:
				await main.get_tree().process_frame
			main.get_viewport().get_texture().get_image().save_png("%s/stop_%d_%s.png" % [out, n, vw[0]])
		print("VEHSHOT stop %d: %s" % [n, l.text])
		n += 1
	print("VEHSHOT fertig: %d Anzeiger" % n)
	main.get_tree().quit()
