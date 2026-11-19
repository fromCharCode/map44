class_name TaxiGame
extends Node3D
## Taxi-Spiel: Fahrgäste abholen und ans Ziel bringen, Fahrpreis nach Dresdner Taxitarif.
##
## Ablauf: FREI -> ein Fahrgast winkt in der Nähe (gelbe Säule) -> hinfahren und anhalten -> EINSTEIGEN ->
## BESETZT: Taxameter läuft (Grundpreis + Kilometer, im Stand/Stau nach Zeit) -> am Ziel (grüne Säule) anhalten ->
## Kasse: Fahrpreis + Trinkgeld (ruhige Fahrt), abzüglich Sachschäden unterwegs.
## Tarif: Dresdner Taxitarif laut taxi-rechner.de (Stand 1. April 2026): Grundpreis 4,90 €; km 1–4 3,20 €,
## km 5–10 2,60 €, ab km 11 2,40 € (nachts 20–5 Uhr und sonntags je +0,10 €); Wartezeit 25 €/h.
## Speicherstand: user://taxi.json (Geld, Fahrten, Kilometer).

enum { FREI, ANFAHRT, EINSTEIGEN, BESETZT, AUSSTEIGEN }

const BASE := 4.90
const WAIT_PER_H := 25.0
const SAVE := "user://taxi.json"
const DRIVE_CLS := ["primary", "secondary", "tertiary", "residential", "unclassified", "living_street"]

var player: PlayerCar
var traffic: Traffic
var hud: Hud
var state := FREI
var money := 0.0
var trips := 0
var km_total := 0.0
var pickup := Vector3.ZERO
var dest := Vector3.ZERO
var pickup_name := ""
var dest_name := ""
var fare_km := 0.0            # besetzt gefahrene Strecke (km)
var fare_wait := 0.0          # Wartezeit (s) unterhalb der Umschaltgeschwindigkeit
var fare := 0.0
var damage_cost := 0.0        # Sachschäden während der Fahrt (Eigenanteil)
var comfort := 1.0            # 1 = ruhige Fahrt, sinkt bei Vollbremsungen/Stößen
var _timer := 3.0
var _offer_t := 0.0
var _broken0 := 0
var _prev_speed := 0.0
var _beam: MeshInstance3D
var _figure: Node3D
var _fig_type := -1
var rng := RandomNumberGenerator.new()
var enabled := true
var mode_taxi := true         # false = freier Modus (keine Aufträge, kein Taxameter)
var offers: Array = []        # Funkaufträge zur Auswahl: {pickup, pname, dest, dname, trip_km, fare, ptype}
var _offers_t := 0.0

# Fahrgasttypen: [Bezeichnung, Anteil tags, Anteil nachts, Trinkgeld (Anteil am Fahrpreis), Eile (0 = keine,
# sonst Faktor auf die Soll-Fahrzeit), Empfindlichkeit für ruppiges Fahren]
const PTYPES := [
	["Geschäftsreisende", 0.18, 0.06, 0.10, 0.90, 1.0],
	["Touristenpaar", 0.20, 0.08, 0.18, 0.0, 1.0],
	["Rentnerin", 0.16, 0.03, 0.08, 0.0, 2.2],
	["Student", 0.14, 0.14, 0.03, 0.0, 0.6],
	["Eilig zum Zug", 0.10, 0.04, 0.22, 0.78, 0.5],
	["Krankenfahrt", 0.10, 0.05, 0.10, 0.0, 2.6],
	["Familie mit Kind", 0.12, 0.02, 0.12, 0.0, 1.8],
	["Nachtschwärmer", 0.0, 0.58, 0.15, 0.0, 0.4],
]
var ptype := 0                # Typ des aktuellen Fahrgasts
var t_goal := 0.0             # Soll-Fahrzeit (s) bei eiligen Fahrgästen, 0 = keine Eile
var t_trip := 0.0             # bisherige Fahrzeit (s)
var rating_sum := 0.0         # Summe aller Bewertungen (Sterne)
var rated := 0
var last_rating := 0.0
var shift_money := 0.0        # Einnahmen seit Spielstart
var shift_t := 0.0
# Taxistände (tools/taxi_stands.py): Kachel -> [[pos, yaw, name, plätze]]
var stands := {}
var _stand_t := 0.0
var _stand_wait := 12.0
var at_stand := ""


func setup(p: PlayerCar, t: Traffic, h: Hud) -> void:
	player = p
	traffic = t
	hud = h
	rng.randomize()
	_load()
	_beam = MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = 1.6
	cyl.bottom_radius = 1.6
	cyl.height = 40.0
	cyl.radial_segments = 16
	_beam.mesh = cyl
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	m.albedo_color = Color(1.0, 0.85, 0.1, 0.28)
	_beam.material_override = m
	_beam.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_beam.visible = false
	add_child(_beam)
	# wartender Fahrgast: einfache Figur (Kapsel + Kopf), bis ein Fußgängermodell angebunden ist
	# wartender Fahrgast: Figur passend zum Fahrgasttyp (Fußgängermodelle), winkt nicht, steht am Fahrbahnrand
	_figure = Node3D.new()
	_figure.visible = false
	add_child(_figure)


func _load() -> void:
	if not FileAccess.file_exists(SAVE):
		return
	var j = JSON.parse_string(FileAccess.get_file_as_string(SAVE))
	if j is Dictionary:
		money = float(j.get("money", 0.0))
		trips = int(j.get("trips", 0))
		km_total = float(j.get("km", 0.0))
		mode_taxi = bool(j.get("taxi_mode", true))
		rating_sum = float(j.get("rating_sum", 0.0))
		rated = int(j.get("rated", 0))
		if player:
			player.fuel_l = float(j.get("fuel", player.fuel_l))


func save() -> void:
	var f := FileAccess.open(SAVE, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify({"money": snappedf(money, 0.01), "trips": trips, "km": snappedf(km_total, 0.01), "taxi_mode": mode_taxi,
			"rating_sum": snappedf(rating_sum, 0.1), "rated": rated,
			"fuel": snappedf(player.fuel_l, 0.1) if player else 45.0}))


static func night_tariff(hours: float, sunday := false) -> bool:
	return sunday or hours >= 20.0 or hours < 5.0


static func price(km: float, wait_s: float, night: bool) -> float:
	## Fahrpreis nach Tarif, auf 0,10 € gerundet (Taxameter schaltet in 10-Cent-Schritten)
	var add := 0.10 if night else 0.0
	var p := BASE
	p += minf(km, 4.0) * (3.20 + add)
	p += clampf(km - 4.0, 0.0, 6.0) * (2.60 + add)
	p += maxf(km - 10.0, 0.0) * (2.40 + add)
	p += wait_s / 3600.0 * WAIT_PER_H
	return snappedf(p, 0.1)


func _edge_point(center: Vector3, r0: float, r1: float, tries: int) -> Array:
	## Zufälliger Punkt am rechten Fahrbahnrand einer benannten Straße im Abstand r0..r1: [pos, name] oder []
	for attempt in tries:
		var ang := rng.randf() * TAU
		var rad := rng.randf_range(r0, r1)
		var ck := Vector2i(floori((center.x + cos(ang) * rad) / 100.0), floori((center.z + sin(ang) * rad) / 100.0))
		var cell: Array = traffic.edge_cells.get(ck, [])
		if cell.is_empty():
			continue
		var ei: int = cell[rng.randi_range(0, cell.size() - 1)]
		var e: Dictionary = traffic.edges[ei]
		if String(e.get("name", "")) == "" or not (String(e["cls"]) in DRIVE_CLS) or float(e["len"]) < 30.0 or bool(e.get("bridge", false)):
			continue
		var pts := traffic.edge_points(ei, 1)
		var s := rng.randf_range(10.0, float(e["len"]) - 10.0)
		var p: Vector3 = traffic._point_at(pts, s)
		var p2: Vector3 = traffic._point_at(pts, s + 2.0)
		var dir := Vector3(p2.x - p.x, 0, p2.z - p.z).normalized()
		var right := Vector3(-dir.z, 0, dir.x)
		# Fahrgast steht am rechten Rand (edge_points liefert die Spurmitte in Fahrtrichtung)
		return [p + right * 2.2, String(e["name"])]
	return []


func _process(delta: float) -> void:
	if not enabled or player == null or traffic == null or traffic.edges.is_empty():
		return
	var pp := player.global_position
	var v := absf(player.speed)
	if Input.is_action_just_pressed("taxi_mode"):
		toggle_mode()
	_fuel(delta, pp, v)
	shift_t += delta
	if OS.has_environment("DRESDEN_TAXI_FIG") and shift_t > 2.0 and not _beam.visible:
		# Diagnose: Fahrgastfigur neben dem Wagen zeigen
		ptype = int(OS.get_environment("DRESDEN_TAXI_FIG"))
		var bx := player.global_transform.basis
		_show(pp - bx.z * 6.0 + bx.x * 3.2, Color(1.0, 0.85, 0.1, 0.28), true)
	match state:
		FREI:
			if not mode_taxi:
				return
			# Taxistand: wer dort steht, bekommt nach kurzer Wartezeit einen Einsteiger (ohne Anfahrt)
			at_stand = ""
			for key in stands:
				for sd in stands[key]:
					if _flat_dist(pp, sd[0]) < 22.0:
						at_stand = String(sd[2])
			if at_stand != "" and v < 0.6:
				if _stand_t == 0.0:
					_stand_wait = rng.randf_range(8.0, 24.0)
					hud.message("Taxistand %s – warten auf Fahrgäste" % at_stand, 3.5)
				_stand_t += delta
				if _stand_t > _stand_wait:
					_stand_t = 0.0
					var b2 := _edge_point(pp, 900.0, 6500.0, 40)
					if not b2.is_empty():
						pickup = pp
						pickup_name = "Taxistand " + at_stand
						dest = b2[0]
						dest_name = b2[1]
						ptype = _pick_ptype()
						_set_goal(pp.distance_to(dest) * 1.3 / 1000.0)
						offers.clear()
						state = EINSTEIGEN
						_timer = 3.0
						hud.message("%s steigt ein – Ziel: %s" % [String(PTYPES[ptype][0]), dest_name], 5.0)
						return
			else:
				_stand_t = 0.0
			# Funkaufträge wie in der Taxizentrale: bis zu drei zur Auswahl, alle 75 s neue; Annahme mit 1/2/3
			# (Gamepad: LB halten + A/X/Y), N bzw. LB+B fordert andere an
			_offers_t -= delta
			_timer -= delta
			if (_offers_t <= 0.0 or offers.size() < 3) and _timer <= 0.0:
				_timer = 0.4
				if _offers_t <= 0.0:
					offers.clear()
					_offers_t = 75.0
				var o := _make_offer(pp)
				if not o.is_empty():
					offers.append(o)
			var pick := _pick_input()
			if pick == 9:
				offers.clear()
				_offers_t = 75.0
			elif pick >= 0 and pick < offers.size():
				var of: Dictionary = offers[pick]
				pickup = of["pickup"]
				pickup_name = of["pname"]
				dest = of["dest"]
				dest_name = of["dname"]
				ptype = int(of.get("ptype", 0))
				_set_goal(float(of["trip_km"]))
				offers.clear()
				state = ANFAHRT
				_offer_t = 300.0
				_show(pickup, Color(1.0, 0.85, 0.1, 0.28), true)
				hud.message("Auftrag angenommen – Fahrgast wartet: %s" % pickup_name, 4.0)
		ANFAHRT:
			_offer_t -= delta
			if _pick_input() == 9:
				hud.message("Auftrag abgegeben", 3.0)
				_reset(1.0)
			elif _offer_t <= 0.0 or pp.distance_to(pickup) > 6000.0:
				hud.message("Fahrgast hat ein anderes Taxi genommen", 3.0)
				_reset(4.0)
			elif _flat_dist(pp, pickup) < 9.0 and v < 0.6:
				state = EINSTEIGEN
				_timer = 2.5
				_figure.visible = false
				hud.message("%s steigt ein – Ziel: %s%s" % [String(PTYPES[ptype][0]), dest_name, ("  (eilig!)" if t_goal > 0.0 else "")], 4.5)
		EINSTEIGEN:
			_timer -= delta
			if _timer <= 0.0:
				state = BESETZT
				fare_km = 0.0
				fare_wait = 0.0
				damage_cost = 0.0
				comfort = 1.0
				t_trip = 0.0
				_broken0 = Breakables.broken
				_prev_speed = v
				_show(dest, Color(0.2, 1.0, 0.35, 0.28), false)
		BESETZT:
			# Taxameter: über der Umschaltgeschwindigkeit nach Strecke, darunter nach Zeit
			var night := night_tariff(Timetable.hours)
			var v_switch := WAIT_PER_H / (3.30 if night else 3.20) / 3.6
			if v > v_switch:
				fare_km += v * delta / 1000.0
			else:
				fare_wait += delta
			km_total += v * delta / 1000.0
			fare = price(fare_km, fare_wait, night)
			# Komfort: Vollbremsungen/Stöße (> 6 m/s²) und umgefahrene Objekte kosten Trinkgeld
			var acc := absf(v - _prev_speed) / maxf(delta, 0.001)
			_prev_speed = v
			t_trip += delta
			var sens := float(PTYPES[ptype][5])
			if acc > 6.5:
				comfort = maxf(comfort - 0.15 * delta * (acc / 6.5) * sens, 0.0)
			# deutlich zu schnell (über 25 km/h über dem Limit) stört empfindliche Fahrgäste
			if sens >= 1.5 and v * 3.6 > 75.0 and traffic.radio == "":
				comfort = maxf(comfort - 0.01 * delta * sens, 0.0)
			if Breakables.broken > _broken0:
				# Eigenanteil je Schaden höchstens 40 €, je Fahrt höchstens der halbe Fahrpreis – vorher fraßen
				# ein paar umgefahrene Schilder den Verdienst vieler Fahrten auf
				damage_cost += minf(Breakables.last_cost, 40.0) * float(Breakables.broken - _broken0)
				comfort = maxf(comfort - 0.25, 0.0)
				_broken0 = Breakables.broken
			if _flat_dist(pp, dest) < 12.0 and v < 0.6:
				state = AUSSTEIGEN
				_timer = 2.5
				# Bewertung in Sternen: ruhige Fahrt, Pünktlichkeit bei eiligen Fahrgästen, Schäden
				var stars := 5.0 - (1.0 - comfort) * 2.5
				var late := t_trip - t_goal if t_goal > 0.0 else 0.0
				var note := ""
				if t_goal > 0.0:
					if late > 0.0:
						stars -= minf(late / 60.0 * 0.8, 2.5)
						note = "zu spät (%d s)" % int(late)
					else:
						note = "pünktlich"
				if damage_cost > 0.0:
					stars -= 1.0
				stars = snappedf(clampf(stars, 1.0, 5.0), 0.5)
				last_rating = stars
				rating_sum += stars
				rated += 1
				# Trinkgeld: Typ-Anteil, skaliert mit der Bewertung; pünktliche Eilfahrt gibt den vollen Satz
				var tip_f := float(PTYPES[ptype][3]) * clampf((stars - 2.5) / 2.5, 0.0, 1.0)
				if ptype == 7 and rng.randf() < 0.3:
					tip_f = 0.0                          # Nachtschwärmer vergisst das Trinkgeld manchmal
				var tip := snappedf(fare * tip_f, 0.1)
				damage_cost = minf(damage_cost, fare * 0.5)
				var total := fare + tip - damage_cost
				money += total
				shift_money += total
				trips += 1
				save()
				hud.message("%s – %s  Trinkgeld %s%s   %s%s" % [dest_name, eur(fare), eur(tip),
					("  Schaden −" + eur(damage_cost)) if damage_cost > 0.0 else "", stars_text(stars),
					("  " + note) if note != "" else ""], 7.0)
		AUSSTEIGEN:
			_timer -= delta
			if _timer <= 0.0:
				_reset(rng.randf_range(4.0, 10.0))


var fueling := false
var _at_station := false
var _fuel_session := 0.0          # getankte Liter am Stück (Anzeige)
var _fuel_msg_t := 0.0


func _fuel(delta: float, pp: Vector3, v: float) -> void:
	## Verbrauch: Leerlauf 0,8 l/h, Volllast ~40 l/h (≈ 6–8 l/100 km im Stadtverkehr). Tanken: unter dem Dach einer
	## Tankstelle anhalten, 0,6 l/s (35 l/min wie eine echte Zapfsäule), bezahlt wird aus der Kasse.
	var lph := 0.8 + 38.0 * player.in_throttle * clampf(player.rpm / 6000.0, 0.15, 1.0)
	player.fuel_l = maxf(player.fuel_l - lph / 3600.0 * delta, 0.0)
	_fuel_msg_t -= delta
	if player.fuel_l <= 0.0 and _fuel_msg_t <= 0.0:
		_fuel_msg_t = 6.0
		hud.message("Tank leer!", 3.0)
	elif player.fuel_l < 6.0 and _fuel_msg_t <= 0.0:
		_fuel_msg_t = 45.0
		hud.message("Tankreserve – nächste Tankstelle anfahren", 3.0)
	var at := false
	if v < 0.5:
		for id in StreetLife.fuel_sites:
			for st in StreetLife.fuel_sites[id]:
				var loc: Vector3 = (st["basis"] as Basis).inverse() * (pp - (st["pos"] as Vector3))
				if absf(loc.x) < float(st["w"]) * 0.5 + 1.0 and absf(loc.z) < float(st["l"]) * 0.5 + 1.0:
					at = true
	if at and not _at_station and not fueling:
		hud.message("Tankstelle – stehen bleiben zum Tanken (%s/l)" % eur(StreetLife.FUEL_PRICE), 3.0)
	_at_station = at
	if OS.has_environment("DRESDEN_TTDBG") and Engine.get_process_frames() % 120 == 0:
		print("TANKDBG Tankstellen %d, an Tankstelle %s, v %.2f, Tank %.2f l, Kasse %.2f" % [StreetLife.fuel_sites.size(), str(at), v, player.fuel_l, money])
	# getankt wird immer (notfalls auf Rechnung): eine leere Kasse darf das Spiel nicht blockieren
	if at and player.fuel_l < PlayerCar.FUEL_CAP - 0.05:
		var add := minf(0.6 * delta, PlayerCar.FUEL_CAP - player.fuel_l)
		player.fuel_l += add
		money -= add * StreetLife.FUEL_PRICE
		_fuel_session += add
		fueling = true
	else:
		if fueling:
			hud.message("Getankt: %.1f l für %s" % [_fuel_session, eur(_fuel_session * StreetLife.FUEL_PRICE)], 4.0)
			save()
		fueling = false
		_fuel_session = 0.0


func _make_offer(pp: Vector3) -> Dictionary:
	## Ein Funkauftrag: Abholort 150–1500 m entfernt, Ziel 0,8–6 km weiter; Fahrpreis geschätzt (Luftlinie × 1,3)
	var a := _edge_point(pp, 150.0, 1500.0, 12)
	if a.is_empty():
		return {}
	var b := _edge_point(a[0], 800.0, 6000.0, 30)
	if b.is_empty() or String(b[1]) == String(a[1]):
		return {}
	for o in offers:
		if String(o["pname"]) == String(a[1]):
			return {}
	var trip := (a[0] as Vector3).distance_to(b[0]) * 1.3 / 1000.0
	return {"pickup": a[0], "pname": a[1], "dest": b[0], "dname": b[1], "trip_km": trip,
		"fare": price(trip, 45.0, night_tariff(Timetable.hours)), "ptype": _pick_ptype()}


func _pick_ptype() -> int:
	var night := night_tariff(Timetable.hours)
	var tot := 0.0
	for pt in PTYPES:
		tot += float(pt[2 if night else 1])
	var r := rng.randf() * tot
	for i in PTYPES.size():
		r -= float(PTYPES[i][2 if night else 1])
		if r <= 0.0:
			return i
	return 0


func _set_goal(trip_km: float) -> void:
	## Soll-Fahrzeit für eilige Fahrgäste: Strecke bei 27 km/h Stadtschnitt × Eilfaktor + 45 s
	var hurry := float(PTYPES[ptype][4])
	t_goal = (trip_km / 27.0 * 3600.0 * hurry + 45.0) if hurry > 0.0 else 0.0


static func stars_text(v: float) -> String:
	var full := int(floor(v))
	return "★".repeat(full) + ("½" if v - float(full) >= 0.5 else "") + "☆".repeat(5 - full - (1 if v - float(full) >= 0.5 else 0))


func rating() -> float:
	return rating_sum / float(rated) if rated > 0 else 0.0


func add_stands(tile: Tile) -> void:
	## Taxistände einer Kachel: Schild und wartende Kollegen; Liste für die Einsteiger-Logik
	var lst: Array = []
	for sd in tile.city.get("taxi_stands", []):
		var x := float(sd[0])
		var z := float(sd[1])
		var yaw := float(sd[2])
		var pos := Vector3(x, tile.terrain.height_at(x, z), z)
		lst.append([pos, yaw, String(sd[3]), int(sd[4])])
		var root := Node3D.new()
		root.position = pos
		root.rotation.y = yaw
		tile.add_child(root)
		# Schild „Taxenstand“ (Zeichen 229): Mast mit blauer Tafel
		var pole := MeshInstance3D.new()
		var cm := CylinderMesh.new()
		cm.top_radius = 0.03
		cm.bottom_radius = 0.03
		cm.height = 2.6
		pole.mesh = cm
		pole.position = Vector3(1.6, 1.3, -1.0)
		root.add_child(pole)
		var sign := Label3D.new()
		sign.text = "TAXI"
		sign.font_size = 48
		sign.pixel_size = 0.006
		sign.modulate = Color(1, 1, 1)
		sign.outline_size = 14
		sign.outline_modulate = Color(0.05, 0.25, 0.65)
		sign.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
		sign.position = Vector3(1.6, 2.45, -1.0)
		sign.visibility_range_end = 120.0
		root.add_child(sign)
		# wartende Kollegen hinter dem ersten Platz (der erste bleibt für den Spieler frei)
		var n := clampi(int(sd[4]) - 1, 1, 3)
		var mdl := "taxi_limousine.glb" if ResourceLoader.exists(CarModel.DIR + "taxi_limousine.glb") else "limousine_ober.glb"
		for i in n:
			if absf(fposmod(x * 0.37 + float(i) * 1.7, 1.0)) < 0.3:
				continue                                # nicht jeder Platz ist besetzt
			var made := CarModel.make_ai(mdl, Color(0.93, 0.87, 0.62))
			var car: Node3D = made["root"]
			var off := Vector3(0, 0, 6.0 + 5.6 * float(i))
			var wp := pos + Basis(Vector3.UP, yaw) * off
			car.position = off + Vector3(0, tile.terrain.height_at(wp.x, wp.z) - pos.y + 0.02, 0)
			root.add_child(car)
			var body := StaticBody3D.new()
			body.collision_layer = 1
			var cs := CollisionShape3D.new()
			var bs := BoxShape3D.new()
			bs.size = Vector3(1.85, 1.45, 4.9)
			cs.shape = bs
			cs.position = car.position + Vector3(0, 0.72, 0)
			body.add_child(cs)
			root.add_child(body)
	stands[tile.key] = lst


func remove_stands(tile: Tile) -> void:
	stands.erase(tile.key)


func _pick_input() -> int:
	## 0..2 = Auftrag annehmen, 9 = andere Aufträge/abbrechen, -1 = nichts
	var combo := Input.is_action_pressed("look_back")
	if Input.is_action_just_pressed("taxi_1") or (combo and Input.is_action_just_pressed("gear_up")):
		return 0
	if Input.is_action_just_pressed("taxi_2") or (combo and Input.is_action_just_pressed("gear_down")):
		return 1
	if Input.is_action_just_pressed("taxi_3") or (combo and Input.is_action_just_pressed("camera")):
		return 2
	if Input.is_action_just_pressed("taxi_new") or (combo and Input.is_action_just_pressed("reset")):
		return 9
	return -1


func toggle_mode() -> void:
	## Taxi-Modus <-> freier Modus (im freien Modus keine Aufträge; eine laufende Fahrt wird beendet)
	mode_taxi = not mode_taxi
	offers.clear()
	if not mode_taxi and state != FREI:
		_reset(1.0)
	hud.message("Taxi-Modus: Aufträge kommen über Funk" if mode_taxi else "Freier Modus: keine Aufträge", 3.5)
	save()


func _flat_dist(a: Vector3, b: Vector3) -> float:
	return Vector2(a.x - b.x, a.z - b.z).length()


func _show(p: Vector3, col: Color, with_figure: bool) -> void:
	_beam.global_position = p + Vector3(0, 20.0, 0)
	(_beam.material_override as StandardMaterial3D).albedo_color = col
	_beam.visible = true
	_figure.visible = with_figure
	if with_figure:
		_set_figure(ptype)
		_figure.global_position = p
		if player:
			var to := player.global_position - p
			_figure.rotation.y = atan2(to.x, to.z)          # schaut dem Taxi entgegen


func _reset(wait: float) -> void:
	state = FREI
	_timer = wait
	_beam.visible = false
	_figure.visible = false


static func eur(v: float) -> String:
	return ("%.2f €" % v).replace(".", ",")


func target() -> Vector3:
	## aktuelles Fahrziel für Pfeil und Karte (ZERO = keins)
	if state == ANFAHRT or state == EINSTEIGEN:
		return pickup
	if state == BESETZT:
		return dest
	return Vector3.ZERO


func status_line() -> String:
	match state:
		ANFAHRT:
			return "Abholen: %s  (N = abgeben)" % pickup_name
		EINSTEIGEN:
			return "Fahrgast steigt ein"
		BESETZT:
			if t_goal > 0.0:
				var left := int(t_goal - t_trip)
				return "%s – %s  (%s%d:%02d)" % [String(PTYPES[ptype][0]), dest_name, "" if left >= 0 else "−", absi(left) / 60, absi(left) % 60]
			return "%s – Ziel: %s" % [String(PTYPES[ptype][0]), dest_name]
		AUSSTEIGEN:
			return "Fahrgast steigt aus"
	return "Frei – Auftrag wählen" if mode_taxi else "Freier Modus (K = Taxi)"


const FIG_MODELS := ["ped_frau3", "ped_frau1", "ped_seniorin", "ped_mann2", "ped_mann4", "ped_senior", "ped_frau5", "ped_mann5"]


func _set_figure(t: int) -> void:
	## Figur des wartenden Fahrgasts aus den Fußgängermodellen (Kleidung passend zum Typ); ohne Modell eine Kapsel
	if t == _fig_type and _figure.get_child_count() > 0:
		return
	_fig_type = t
	for c in _figure.get_children():
		c.queue_free()
	var path := Peds.DIR + String(FIG_MODELS[clampi(t, 0, FIG_MODELS.size() - 1)]) + ".glb"
	if not ResourceLoader.exists(path):
		var mi := MeshInstance3D.new()
		var cap := CapsuleMesh.new()
		cap.radius = 0.24
		cap.height = 1.75
		mi.mesh = cap
		mi.position.y = 0.9
		_figure.add_child(mi)
		return
	var node := (load(path) as PackedScene).instantiate() as Node3D
	_figure.add_child(node)
	var stack: Array = [node]
	while not stack.is_empty():
		var x: Node = stack.pop_back()
		if x is MeshInstance3D:
			var m := x as MeshInstance3D
			m.set_surface_override_material(0, Peds.material())
			var tops := [Color(0.10, 0.11, 0.15), Color(0.62, 0.20, 0.22), Color(0.52, 0.46, 0.40), Color(0.20, 0.30, 0.46),
				Color(0.14, 0.17, 0.25), Color(0.36, 0.37, 0.38), Color(0.25, 0.42, 0.34), Color(0.09, 0.10, 0.13)]
			m.set_instance_shader_parameter("c_skin", Color(0.90, 0.72, 0.60).srgb_to_linear())
			m.set_instance_shader_parameter("c_hair", (Color(0.80, 0.79, 0.77) if t in [2, 5] else Color(0.16, 0.11, 0.08)).srgb_to_linear())
			m.set_instance_shader_parameter("c_top", (tops[t % tops.size()] as Color).srgb_to_linear())
			m.set_instance_shader_parameter("c_bottom", Color(0.11, 0.12, 0.16).srgb_to_linear())
			m.set_instance_shader_parameter("c_shoes", Color(0.05, 0.05, 0.05).srgb_to_linear())
			m.set_instance_shader_parameter("c_acc", Color(0.25, 0.16, 0.10).srgb_to_linear())
			m.set_instance_shader_parameter("c_top2", Color(0.90, 0.90, 0.88).srgb_to_linear())
		for c in x.get_children():
			stack.append(c)
	var ap := node.find_child("AnimationPlayer", true, false) as AnimationPlayer
	if ap and ap.has_animation("Idle"):
		ap.play("Idle")
