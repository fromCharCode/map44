class_name Tile
extends Node3D
## Eine 2x2-km-Kachel der Stadt: Gelände, Gebäude, Wasser, Straßendetails, Bäume usw.
## Wird im Worker-Thread gebaut (Knoten noch nicht im Baum) und dann vom World-Manager eingehängt.

const SIZE := 2000.0
const ORIGIN_E := 411000.0
const ORIGIN_N := 5656200.0

var key := ""            # "410_5656"
var e_km := 0
var n_km := 0
var city: Dictionary
var terrain: Terrain
var buildings: Buildings
var water: Water
var roads_node: Roads
var walls: Walls
var dressing: Dressing
var parked: ParkedCars
var landmarks: Landmarks
var road_index: RoadIndex
var tram_container: Node3D
var ok := false
static var build_step := ""     # aktueller Bauschritt im Kachel-Thread (Diagnose)
var _mods: Array = []     # Module, die der World-Manager nach und nach einhängt


static func key_of(e_km_: int, n_km_: int) -> String:
	return "%d_%d" % [e_km_, n_km_]


static func center_of(e_km_: int, n_km_: int) -> Vector2:
	## Mitte der Kachel in Spielkoordinaten (x, z).
	return Vector2((e_km_ + 1) * 1000.0 - ORIGIN_E, -((n_km_ + 1) * 1000.0 - ORIGIN_N))


static func key_at(x: float, z: float) -> String:
	var e := x + ORIGIN_E
	var n := ORIGIN_N - z
	return key_of(int(floorf(e / 2000.0)) * 2, int(floorf(n / 2000.0)) * 2)


func build(k: String, noise: ImageTexture) -> void:
	key = k
	var p := k.split("_")
	e_km = int(p[0])
	n_km = int(p[1])
	name = "Tile_" + k
	var dir := DataPaths.file("tiles/%s/" % k)
	city = JSON.parse_string(FileAccess.get_file_as_string(dir + "city.json"))
	if city == null:
		return
	var meta = JSON.parse_string(FileAccess.get_file_as_string(dir + "terrain.json"))
	terrain = Terrain.new()
	terrain.name = "Terrain"
	_mods.append(terrain)
	if World.quitting:
		return
	build_step = "terrain"
	var _t_terrain := Time.get_ticks_msec()
	terrain.build(meta, noise, dir, center_of(e_km, n_km))
	if Time.get_ticks_msec() - _t_terrain > 150: print("Kachel %s: terrain %d ms" % [k, Time.get_ticks_msec() - _t_terrain])

	buildings = Buildings.new()
	buildings.name = "Buildings"
	_mods.append(buildings)
	if World.quitting:
		return
	buildings.passages = city.get("passages", [])
	buildings.shops = city.get("life", {}).get("shops", [])
	build_step = "buildings"
	var _t_buildings := Time.get_ticks_msec()
	buildings.build(Landmarks.filter_buildings(city["buildings"]), noise)
	if Time.get_ticks_msec() - _t_buildings > 150: print("Kachel %s: buildings %d ms" % [k, Time.get_ticks_msec() - _t_buildings])
	landmarks = Landmarks.new()
	landmarks.name = "Landmarks"
	_mods.append(landmarks)
	if World.quitting:
		return
	build_step = "landmarks"
	var _t_landmarks := Time.get_ticks_msec()
	landmarks.build(terrain, noise)
	if Time.get_ticks_msec() - _t_landmarks > 150: print("Kachel %s: landmarks %d ms" % [k, Time.get_ticks_msec() - _t_landmarks])

	water = Water.new()
	water.name = "Water"
	_mods.append(water)
	if World.quitting:
		return
	build_step = "water"
	var _t_water := Time.get_ticks_msec()
	water.build(city["water"], noise)
	if Time.get_ticks_msec() - _t_water > 150: print("Kachel %s: water %d ms" % [k, Time.get_ticks_msec() - _t_water])

	road_index = RoadIndex.new()
	build_step = "road_index"
	var _t_road_index := Time.get_ticks_msec()
	road_index.build(city["roads"])
	if Time.get_ticks_msec() - _t_road_index > 150: print("Kachel %s: road_index %d ms" % [k, Time.get_ticks_msec() - _t_road_index])
	roads_node = Roads.new()
	roads_node.name = "Roads"
	_mods.append(roads_node)
	if World.quitting:
		return
	build_step = "roads_node"
	var _t_roads_node := Time.get_ticks_msec()
	roads_node.build(terrain, city, road_index)
	if Time.get_ticks_msec() - _t_roads_node > 150: print("Kachel %s: roads_node %d ms" % [k, Time.get_ticks_msec() - _t_roads_node])

	if not (city.get("tunnels", []) as Array).is_empty() and not OS.has_environment("DRESDEN_NOTUNNELS"):
		var tunnels := Tunnels.new()
		tunnels.name = "Tunnels"
		_mods.append(tunnels)
		tunnels.build(terrain, city["tunnels"], center_of(e_km, n_km))
		var tm := tunnels.mask_image()
		if tm != null and not OS.has_environment("DRESDEN_NOTUNMASK"):
			terrain.set_tunnel_mask(tm)

	walls = Walls.new()
	walls.name = "Walls"
	_mods.append(walls)
	if World.quitting:
		return
	build_step = "walls"
	var _t_walls := Time.get_ticks_msec()
	walls.build(terrain, city)
	if Time.get_ticks_msec() - _t_walls > 150: print("Kachel %s: walls %d ms" % [k, Time.get_ticks_msec() - _t_walls])

	dressing = Dressing.new()
	dressing.name = "Dressing"
	_mods.append(dressing)
	if World.quitting:
		return
	build_step = "dressing"
	var _t_dressing := Time.get_ticks_msec()
	if OS.has_environment("DRESDEN_TRACE"): print("Kachel %s: %s start" % [k, "dressing"])
	dressing.build(terrain, city, road_index)
	if OS.has_environment("DRESDEN_TRACE"): print("Kachel %s: %s ende" % [k, "dressing"])
	if Time.get_ticks_msec() - _t_dressing > 150: print("Kachel %s: dressing %d ms" % [k, Time.get_ticks_msec() - _t_dressing])

	var life := StreetLife.new()
	life.name = "StreetLife"
	_mods.append(life)
	if World.quitting:
		return
	build_step = "life"
	var _t_life := Time.get_ticks_msec()
	if OS.has_environment("DRESDEN_TRACE"): print("Kachel %s: %s start" % [k, "life"])
	life.build(terrain, city.get("life", {}))
	if OS.has_environment("DRESDEN_TRACE"): print("Kachel %s: %s ende" % [k, "life"])
	if Time.get_ticks_msec() - _t_life > 150: print("Kachel %s: life %d ms" % [k, Time.get_ticks_msec() - _t_life])

	var stops := Stops.new()
	stops.name = "Stops"
	_mods.append(stops)
	if World.quitting:
		return
	build_step = "stops"
	var _t_stops := Time.get_ticks_msec()
	stops.build(terrain, city.get("stops", {}))
	if Time.get_ticks_msec() - _t_stops > 150: print("Kachel %s: stops %d ms" % [k, Time.get_ticks_msec() - _t_stops])
	RenderUtil.gi_off(stops)

	parked = ParkedCars.new()
	parked.name = "Parked"
	_mods.append(parked)
	if World.quitting:
		return
	build_step = "parked"
	var _t_parked := Time.get_ticks_msec()
	if OS.has_environment("DRESDEN_TRACE"): print("Kachel %s: %s start" % [k, "parked"])
	parked.build(terrain, city)
	if OS.has_environment("DRESDEN_TRACE"): print("Kachel %s: %s ende" % [k, "parked"])
	if Time.get_ticks_msec() - _t_parked > 150: print("Kachel %s: parked %d ms" % [k, Time.get_ticks_msec() - _t_parked])

	tram_container = Node3D.new()
	tram_container.name = "TramRails"
	_mods.append(tram_container)
	if World.quitting:
		return
	# Kleinteile und Wasser aus der globalen Beleuchtung nehmen (siehe RenderUtil.gi_off)
	for gm in [dressing, life, parked, water, tram_container]:
		RenderUtil.gi_off(gm)
	# Kinder vorübergehend lösen: der Manager hängt sie zeitbudgetiert wieder ein
	var lst: Array = []
	for m in _mods:
		var kids: Array = m.get_children()
		for c in kids:
			m.remove_child(c)
		lst.append([m, kids])
	_mods = lst
	ok = true
