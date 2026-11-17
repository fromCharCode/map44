class_name Timetable
## Echter Soll-Fahrplan (godot/data/timetable.json aus tools/gtfs_timetable.py; Quelle gtfs.de / DELFI e.V.).
## Ordnet den OSM-Linienwegen (tram_routes/bus_routes: {ref, to, pts, cum}) die Fahrplan-Fahrwege zu und liefert
## für eine Uhrzeit, wo auf dem Linienweg gerade Fahrzeuge unterwegs sind. Damit erscheinen Bahnen und Busse im
## echten Takt statt zufällig.

static var loaded := false
static var stops: Array = []          # [name, x, z]
static var by_ref := {}               # ref -> Array Fahrwege {head, stops, t, dep{wt,sa,so}}
static var day := "wt"
static var clock_offset := 0.0        # Sekunden (laufende Echtzeit, wenn die Spieluhr steht)
static var hours := 15.0              # Spieluhr (main setzt sie je Bild)


static func load_data() -> void:
	if loaded:
		return
	loaded = true
	var p := DataPaths.file("timetable.json")
	if not FileAccess.file_exists(p):
		return
	var j = JSON.parse_string(FileAccess.get_file_as_string(p))
	if not (j is Dictionary):
		return
	stops = j.get("stops", [])
	for l in j.get("lines", []):
		var ref := String(l["ref"])
		if not by_ref.has(ref):
			by_ref[ref] = []
		by_ref[ref].append(l)
	print("Timetable: %d Linien, %d Halte" % [by_ref.size(), stops.size()])


static func now() -> float:
	## Sekunden seit Mitternacht (Spieluhr + laufende Sekunden, solange die Spieluhr steht)
	return fposmod(hours * 3600.0 + clock_offset, 86400.0)


static func _project(pts: PackedVector2Array, cum: PackedFloat32Array, q: Vector2) -> Vector2:
	## (Bogenlänge, Abstand) des nächsten Punktes auf dem Linienweg
	var best := Vector2(0.0, INF)
	for i in pts.size() - 1:
		var a := pts[i]
		var ab := pts[i + 1] - a
		var l2 := ab.length_squared()
		var t := clampf((q - a).dot(ab) / l2, 0.0, 1.0) if l2 > 0.0001 else 0.0
		var d := (a + ab * t).distance_to(q)
		if d < best.y:
			best = Vector2(cum[i] + sqrt(l2) * t, d)
	return best


static func attach(route: Dictionary) -> void:
	## Hängt an einen OSM-Linienweg die passenden Fahrplan-Fahrwege: route["tt"] = [{s, t, dep, id}]
	## Passend = gleiche Liniennummer, Halte liegen am Weg (≤ 90 m) und in Fahrtrichtung aufsteigend.
	load_data()
	var out: Array = []
	var pts: PackedVector2Array = route["pts"]
	var cum: PackedFloat32Array = route["cum"]
	var idx := 0
	for l in by_ref.get(String(route.get("ref", "")), []):
		idx += 1
		var st: Array = l["stops"]
		var tt: Array = l["t"]
		var s_arr := PackedFloat32Array()
		var t_arr := PackedFloat32Array()
		var miss := 0
		var last_s := -1.0
		for i in st.size():
			var sp: Array = stops[int(st[i])]
			var pr := _project(pts, cum, Vector2(float(sp[1]), float(sp[2])))
			if pr.y > 90.0 or pr.x <= last_s + 5.0:
				miss += 1
				continue
			last_s = pr.x
			s_arr.append(pr.x)
			t_arr.append(float(tt[i]))
		# mindestens 60 % der Halte am Weg, mindestens 3, sonst andere Richtung/anderer Linienast
		if s_arr.size() < 3 or float(s_arr.size()) < 0.6 * float(st.size()):
			continue
		out.append({"s": s_arr, "t": t_arr, "dep": l["dep"], "id": "%s|%s|%d" % [String(route.get("ref", "")), String(l["head"]), idx]})
	route["tt"] = out


static func active(route: Dictionary, now_s: float) -> Array:
	## Fahrzeuge, die laut Fahrplan gerade auf dem Linienweg unterwegs sind: [[schlüssel, Bogenlänge], ...]
	var res: Array = []
	for p in route.get("tt", []):
		var s_arr: PackedFloat32Array = p["s"]
		var t_arr: PackedFloat32Array = p["t"]
		var t0 := t_arr[0]
		var t1 := t_arr[t_arr.size() - 1]
		for d in (p["dep"] as Dictionary).get(day, []):
			var tau := now_s - float(d)
			if tau < -43200.0:
				tau += 86400.0                    # Fahrten über Mitternacht
			if tau < t0 or tau > t1:
				continue
			var k := 0
			while k < t_arr.size() - 2 and t_arr[k + 1] < tau:
				k += 1
			var f := clampf((tau - t_arr[k]) / maxf(t_arr[k + 1] - t_arr[k], 1.0), 0.0, 1.0)
			res.append(["%s|%d" % [String(p["id"]), int(d)], lerpf(s_arr[k], s_arr[k + 1], f)])
	return res
