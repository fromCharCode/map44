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
var _figure: MeshInstance3D
var rng := RandomNumberGenerator.new()
var enabled := true


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
	_figure = MeshInstance3D.new()
	var cap := CapsuleMesh.new()
	cap.radius = 0.24
	cap.height = 1.75
	_figure.mesh = cap
	var fm := StandardMaterial3D.new()
	fm.albedo_color = Color(0.75, 0.2, 0.18)
	_figure.material_override = fm
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


func save() -> void:
	var f := FileAccess.open(SAVE, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify({"money": snappedf(money, 0.01), "trips": trips, "km": snappedf(km_total, 0.01)}))


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
	match state:
		FREI:
			_timer -= delta
			if _timer <= 0.0:
				_timer = 2.0
				var a := _edge_point(pp, 120.0, 520.0, 30)
				if a.is_empty():
					return
				var b := _edge_point(a[0], 1200.0, 4200.0, 80)
				if b.is_empty():
					b = _edge_point(a[0], 500.0, 1500.0, 80)
				if b.is_empty() or String(b[1]) == String(a[1]):
					return
				pickup = a[0]
				pickup_name = a[1]
				dest = b[0]
				dest_name = b[1]
				state = ANFAHRT
				_offer_t = 240.0
				_show(pickup, Color(1.0, 0.85, 0.1, 0.28), true)
				hud.message("Fahrgast wartet: %s" % pickup_name, 4.0)
				if OS.has_environment("DRESDEN_TTDBG"):
					print("TAXIDBG Auftrag: %s %s -> %s %s, Luftlinie %.0f m, Tarif für diese Strecke ~%s" % [pickup_name, str(pickup.snappedf(0.1)), dest_name, str(dest.snappedf(0.1)), pickup.distance_to(dest), eur(price(pickup.distance_to(dest) * 1.3 / 1000.0, 60.0, night_tariff(Timetable.hours)))])
		ANFAHRT:
			_offer_t -= delta
			if _offer_t <= 0.0 or pp.distance_to(pickup) > 1500.0:
				hud.message("Fahrgast hat ein anderes Taxi genommen", 3.0)
				_reset(4.0)
			elif _flat_dist(pp, pickup) < 9.0 and v < 0.6:
				state = EINSTEIGEN
				_timer = 2.5
				_figure.visible = false
				hud.message("Fahrgast steigt ein – Ziel: %s" % dest_name, 4.0)
		EINSTEIGEN:
			_timer -= delta
			if _timer <= 0.0:
				state = BESETZT
				fare_km = 0.0
				fare_wait = 0.0
				damage_cost = 0.0
				comfort = 1.0
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
			if acc > 6.5:
				comfort = maxf(comfort - 0.15 * delta * (acc / 6.5), 0.0)
			if Breakables.broken > _broken0:
				damage_cost += minf(Breakables.last_cost, 250.0) * float(Breakables.broken - _broken0)
				comfort = maxf(comfort - 0.25, 0.0)
				_broken0 = Breakables.broken
			if _flat_dist(pp, dest) < 12.0 and v < 0.6:
				state = AUSSTEIGEN
				_timer = 2.5
				var tip := snappedf(fare * 0.12 * comfort, 0.1)
				var total := fare + tip - damage_cost
				money += total
				trips += 1
				save()
				hud.message("%s – Fahrpreis %s  Trinkgeld %s%s" % [dest_name, eur(fare), eur(tip),
					("  Sachschaden −" + eur(damage_cost)) if damage_cost > 0.0 else ""], 6.0)
		AUSSTEIGEN:
			_timer -= delta
			if _timer <= 0.0:
				_reset(rng.randf_range(4.0, 10.0))


func _flat_dist(a: Vector3, b: Vector3) -> float:
	return Vector2(a.x - b.x, a.z - b.z).length()


func _show(p: Vector3, col: Color, with_figure: bool) -> void:
	_beam.global_position = p + Vector3(0, 20.0, 0)
	(_beam.material_override as StandardMaterial3D).albedo_color = col
	_beam.visible = true
	_figure.visible = with_figure
	if with_figure:
		_figure.global_position = p + Vector3(0, 0.9, 0)


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
			return "Abholen: %s" % pickup_name
		EINSTEIGEN:
			return "Fahrgast steigt ein"
		BESETZT:
			return "Besetzt – Ziel: %s" % dest_name
		AUSSTEIGEN:
			return "Fahrgast steigt aus"
	return "Frei"
