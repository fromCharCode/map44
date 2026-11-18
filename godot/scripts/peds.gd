class_name Peds
extends Node3D
## Fußgänger: gehen auf Gehweg-Pfaden (um Fahrbahnbreite/2 + 1,4 m versetzte Straßenlinien) rund um den Fokus.
## Nicht-physikalisch; spawnen/despawnen wie der Verkehr.
##
## Verhalten (Kennwerte stehen an den Stellen im Code):
##  - Tempo: Erwachsene um 1,34 m/s (Streuung 0,17), Kinder um 1,10, Ältere um 0,92, etwa jeder Achte eilig
##    (1,7–2,05 m/s); die Animation läuft im Verhältnis Tempo / Gangart-Tempo der Figur (kein Gleiten).
##  - Spur: jeder hält seine Spur (rechts der Wegmitte), weicht festen Hindernissen (Bäume, Masten, Möbel, parkende
##    Autos) und anderen Menschen seitlich aus, überholt Langsamere, geht bei Gegenverkehr rechts vorbei und wird
##    langsamer, wenn kein Platz ist. Nie näher als 0,4 m an die Bordsteinkante.
##  - Fahrbahn: 1,25 m voraus wird geprüft, ob Fahrbahn kommt (Einmündung, Überweg, Kreuzung). Gequert wird nur, wenn
##    kein Fahrzeug die Querungslinie in Querungszeit + 2,5 s erreicht; an Ampelknoten zusätzlich nur, wenn alle
##    Zufahrten längs der gequerten Fahrbahn Rot zeigen (SignalCtl). Sonst am Rand warten und schauen ("Look").
##  - Wege: am Wegende weiter auf dem Anschlussweg, an Ecken auf den Gehweg der Querstraße, an Überwegen
##    (city["crossings"]) auf die andere Straßenseite; nur wenn nichts anschließt, umkehren.
##  - Aufenthalt: vor Schaufenstern stehen bleiben, an Haltestellen warten, aufs Handy schauen, in Gruppen reden;
##    etwa jeder Fünfte ist zu zweit unterwegs (Kinder meist mit Erwachsenen).
##  - Autos: fährt ein Fahrzeug auf jemanden zu, springt er seitlich weg; mitten auf der Fahrbahn rennt er hinüber.
##    Für den Verkehr stehen Peds.on_road_pts / Peds.zebra_waits bereit (Autos halten davor, siehe ai_car.gd).
##  - Anzahl: target_count x Tageszeit (DAY_CURVE) x Wetter (Regen 0,4) x Lage (Läden im Umkreis 160 m: 0,3 .. 1,3).
##  - Entfernungsstufen: bis 50 m jedes Bild, bis 100 m jedes zweite, darüber jedes vierte; Schatten bis 60 m;
##    Straßen- und Autoprüfungen nur bis 110 m; ab 170 m entfernt.
##
## Figuren: tools/blender/peds_build.py (je Figur ein Mesh, eine Oberfläche; Teilnummer und Helligkeit in der UV,
## Farben je Figur über Instanz-Uniforms des Shaders unten). Sichtprüfung: tools/blender/peds_check.gd.
## Entwickler-Optionen (nach "--"): --pedparade  alle Figuren in einer Reihe vor der Kamera,
##                                  --peddebug   alle 2 s Zustände und Rechenzeit, jede Querung mit Ampelstand,
##                                  --peddump=<datei>  alle 0,5 s Lagen aller Figuren und Fahrzeuge als JSON-Zeilen.

## Datei, Art (f Frau, m Mann, k Kind, a älter), Schrittzyklus Gehen (m), Laufen (m) – Ausgabe von peds_build.py
## (die Schrittzyklen liest setup() aus den Modellen selbst; die Zahlen hier gelten nur, wenn dort nichts steht)
const MODELS := [
	["ped_frau1", "f", 1.263, 1.903],
	["ped_frau2", "f", 1.233, 1.858],
	["ped_frau3", "f", 1.286, 1.937],
	["ped_frau4", "f", 1.248, 1.880],
	["ped_frau5", "f", 1.218, 1.835],
	["ped_frau6", "f", 1.301, 1.960],
	["ped_mann1", "m", 1.361, 2.050],
	["ped_mann2", "m", 1.331, 2.005],
	["ped_mann3", "m", 1.399, 2.107],
	["ped_mann4", "m", 1.316, 1.982],
	["ped_mann5", "m", 1.346, 2.028],
	["ped_kind1", "k", 0.897, 1.405],
	["ped_kind2", "k", 0.828, 1.297],
	["ped_seniorin", "a", 0.950, 1.801],
	["ped_senior", "a", 1.055, 1.937],
]
const DIR := "res://assets/models/peds/"
const CELL := 100.0          # Raster der Wege und Aufenthaltsorte
const ECELL := 20.0          # Raster der Wegenden
const OCELL := 4.0           # Raster fester Hindernisse
const PCELL := 3.0           # Raster der Fußgänger
const CCELL := 24.0          # Raster der Fahrzeuge
const SCELL := 60.0          # Raster der Ampelknoten
const FAR := 170.0           # ab hier wird entfernt
const PAIR_GAP := 0.72       # Abstand zweier nebeneinander Gehender
const MAX_PEDS := 110

enum { WALK, STAND, DODGE }

const SKIN := [Color(0.94, 0.78, 0.67), Color(0.90, 0.72, 0.60), Color(0.84, 0.65, 0.52), Color(0.96, 0.83, 0.74),
	Color(0.74, 0.55, 0.42), Color(0.58, 0.41, 0.30), Color(0.40, 0.27, 0.20), Color(0.88, 0.70, 0.56)]
const HAIR := [Color(0.07, 0.06, 0.05), Color(0.16, 0.11, 0.08), Color(0.27, 0.18, 0.11), Color(0.40, 0.27, 0.15),
	Color(0.58, 0.44, 0.26), Color(0.76, 0.64, 0.42), Color(0.45, 0.17, 0.09), Color(0.33, 0.31, 0.30)]
const HAIR_OLD := [Color(0.62, 0.61, 0.60), Color(0.80, 0.79, 0.77), Color(0.48, 0.47, 0.46), Color(0.88, 0.87, 0.84), Color(0.40, 0.35, 0.30)]
# gedeckte Stadtfarben; wenige kräftige Töne dazwischen
const TOP := [Color(0.09, 0.10, 0.13), Color(0.14, 0.17, 0.25), Color(0.22, 0.24, 0.27), Color(0.36, 0.37, 0.38), Color(0.55, 0.55, 0.53),
	Color(0.78, 0.76, 0.70), Color(0.87, 0.86, 0.83), Color(0.24, 0.30, 0.22), Color(0.36, 0.38, 0.26), Color(0.45, 0.33, 0.22),
	Color(0.62, 0.50, 0.36), Color(0.20, 0.32, 0.46), Color(0.38, 0.50, 0.62), Color(0.50, 0.14, 0.14), Color(0.66, 0.30, 0.16),
	Color(0.74, 0.60, 0.22), Color(0.30, 0.16, 0.24), Color(0.16, 0.36, 0.36), Color(0.70, 0.52, 0.56), Color(0.12, 0.22, 0.34)]
const BOTTOM := [Color(0.07, 0.07, 0.09), Color(0.11, 0.12, 0.16), Color(0.15, 0.20, 0.32), Color(0.24, 0.32, 0.46), Color(0.30, 0.30, 0.32),
	Color(0.44, 0.44, 0.44), Color(0.36, 0.30, 0.22), Color(0.58, 0.52, 0.40), Color(0.20, 0.23, 0.18), Color(0.42, 0.50, 0.60)]
const SKIRT := [Color(0.08, 0.08, 0.10), Color(0.16, 0.18, 0.28), Color(0.40, 0.12, 0.14), Color(0.52, 0.46, 0.36), Color(0.26, 0.30, 0.24),
	Color(0.62, 0.36, 0.30), Color(0.34, 0.34, 0.37), Color(0.70, 0.66, 0.56)]
const SHOES := [Color(0.05, 0.05, 0.05), Color(0.10, 0.09, 0.09), Color(0.26, 0.16, 0.10), Color(0.38, 0.26, 0.16), Color(0.82, 0.82, 0.80),
	Color(0.55, 0.55, 0.55), Color(0.16, 0.18, 0.26), Color(0.45, 0.10, 0.10)]
const ACC := [Color(0.07, 0.07, 0.08), Color(0.25, 0.16, 0.10), Color(0.42, 0.29, 0.17), Color(0.14, 0.18, 0.28), Color(0.50, 0.12, 0.12),
	Color(0.30, 0.34, 0.26), Color(0.62, 0.56, 0.46), Color(0.20, 0.36, 0.40), Color(0.72, 0.55, 0.18), Color(0.36, 0.36, 0.38)]
const TOP2 := [Color(0.90, 0.90, 0.88), Color(0.80, 0.84, 0.90), Color(0.62, 0.72, 0.84), Color(0.12, 0.12, 0.14), Color(0.55, 0.55, 0.55),
	Color(0.84, 0.78, 0.66), Color(0.50, 0.16, 0.16), Color(0.22, 0.28, 0.40)]
const TIGHTS := [Color(0.07, 0.07, 0.08), Color(0.14, 0.13, 0.14), Color(0.30, 0.22, 0.18), Color(0.20, 0.20, 0.24)]
## Menschen auf der Straße nach Uhrzeit (0..23 Uhr), 1 = Nachmittagsspitze
const DAY_CURVE := [0.10, 0.06, 0.04, 0.04, 0.05, 0.10, 0.25, 0.50, 0.65, 0.70, 0.78, 0.90, 1.0, 0.95, 0.92, 0.98,
	1.0, 1.0, 0.92, 0.78, 0.60, 0.42, 0.28, 0.16]

const SHADER := "
shader_type spatial;
render_mode cull_disabled, diffuse_burley;
// Teilfarben je Figur (linear); Teilnummer steckt in UV.x, Helligkeit in UV.y (siehe tools/blender/peds_build.py)
instance uniform vec3 c_skin = vec3(0.7, 0.5, 0.4);
instance uniform vec3 c_hair = vec3(0.05, 0.04, 0.03);
instance uniform vec3 c_top = vec3(0.1, 0.1, 0.15);
instance uniform vec3 c_bottom = vec3(0.05, 0.05, 0.08);
instance uniform vec3 c_shoes = vec3(0.02, 0.02, 0.02);
instance uniform vec3 c_acc = vec3(0.1, 0.06, 0.04);
instance uniform vec3 c_top2 = vec3(0.7, 0.7, 0.7);
void fragment() {
	int part = int(floor(UV.x * 8.0));
	float sh = (1.0 - UV.y) * 2.0;
	vec3 c = vec3(0.5);
	float rough = 0.92;
	if (part == 0) { c = c_skin; rough = 0.62; }
	else if (part == 1) { c = c_hair; rough = 0.55; }
	else if (part == 2) { c = c_top; }
	else if (part == 3) { c = c_bottom; }
	else if (part == 4) { c = c_shoes; rough = 0.6; }
	else if (part == 5) { c = c_acc; rough = 0.8; }
	else if (part == 7) { c = c_top2; }
	c = mix(vec3(dot(c, vec3(0.3, 0.55, 0.15))), c, 0.86);       // Stoffe im Sonnenlicht nicht bunter als die Stadt
	ALBEDO = c * sh * 0.92;
	ROUGHNESS = rough;
	SPECULAR = 0.3;
	if (!FRONT_FACING) { NORMAL = -NORMAL; }
}
"


class Ped:
	var node: Node3D
	var mesh: MeshInstance3D
	var anim: AnimationPlayer
	var mi := 0                  # Modellnummer
	var kind := "m"
	var hs := 1.0                # Größenfaktor
	var walk_v := 1.3            # Geschwindigkeit, bei der "Walk" ohne Gleiten passt (m/s)
	var run_v := 2.8
	var path := {}
	var s := 0.0
	var dir := 1
	var v0 := 1.3                # Wunschgeschwindigkeit
	var v := 0.0
	var slow := 1.0              # Bremsfaktor aus dem Ausweichen
	var lat := 0.0               # Seitenversatz rechts der Gehrichtung
	var lat0 := 0.3              # bevorzugte Spur
	var lat_t := 0.3
	var off := Vector2.ZERO      # freier Versatz zum Wegpunkt (Ausweichen, Schaufenster, Übergang auf anderen Weg)
	var off_t := Vector2.ZERO
	var pos := Vector2.ZERO
	var hv := Vector2(0, -1)     # Gehrichtung
	var yaw := 0.0
	var face := NAN              # feste Blickrichtung im Stand
	var state := 0
	var t := 0.0                 # Restzeit des Zustands
	var stand_anim := "Idle"
	var arrive := {}             # nach Erreichen von off_t: {yaw, anim, t}
	var wait := false            # steht am Fahrbahnrand
	var wait_t := 0.0
	var wait_max := 30.0
	var on_road := false
	var road_t := 0.0
	var cross := {}
	var run_t := 0.0
	var hurry := false
	var lead: Ped = null         # geht neben dieser Person her
	var mate: Ped = null
	var think_t := 0.0
	var shop_t := 20.0
	var phone_t := 200.0
	var stuck_t := 0.0
	var ghost_t := 0.0
	var dodge_to := Vector2.ZERO
	var cur := ""
	var cur_sp := -1.0
	var acc := 0.0
	var d2 := 0.0
	var fo := 0
	var shadow := true
	var dead := false
	var hot_kind := -1
	var zebra := Vector2.INF     # Fahrbahnpunkt des Überwegs, den die Person gerade nimmt
	var along_t := 0.0


var world: World
var focus := Vector3.ZERO
var target_count := 55       # Obergrenze für eine belebte Innenstadtlage am Nachmittag (main.gd: --peds)
var cells := {}              # Vector2i -> Array of paths {pts, cum, len, tile, rid, side, w, bad, dead, nx, xings}
var ends := {}               # Vector2i -> Array of [path, 0|1]
var hots := {}               # Vector2i -> Array of {p, yaw, tile, k}  (k: 0 Laden, 1 Haltestelle, 2 sonstiges)
var sigs := {}               # Vector2i -> Array of {p, tile, apps: [[ang, ph, ctl], ...]}
var peds: Array = []         # Ped
var rng := RandomNumberGenerator.new()
var enabled := true
var models: Array = []       # {scene, kind, walk, run, walk_T, run_T}
var by_kind := {}
var _has_models := false
var _spawn_t := 0.0
var _trim_t := 0.0
var _dens_t := 0.0
var _snap_t := 0.0
var _target := 0
var _frame := 0
var _warm := 3.0
var _last_focus := Vector3.ZERO
var _rid := {}               # Kachel -> {Straßen-ID: [Weg rechts, Weg links]}
var _obst := {}              # Vector2i -> Array[Vector3(x, z, Radius)]
var _obst_cells := {}        # Kachel -> Array[Vector2i]
var _obst_jobs: Array = []   # [Kachel, Liste, Art, Index]
var _pgrid := {}
var _cars: Array = []        # [pos, vel, speed, halbe Breite, halbe Länge, Sicherheitsabstand seitlich]
var _cgrid := {}
var _tram_last := {}
var _pool := {}              # Modellnummer -> Array[Node3D]
var _main: Node = null
var _debug := false
var _parade := false
var _dump: FileAccess = null
var _dump_t := 0.0
var _dbg_t := 0.0
var _dbg_us := 0
var _dbg_n := 0
var _sp := Vector2.ZERO      # Ergebnis von _sample
var _st := Vector2(0, 1)

## Fußgänger, die gerade auf einer Fahrbahn sind (x, y, z) – für den Verkehr, alle 0,1 s neu
static var on_road_pts := PackedVector3Array()
## Fahrbahnpunkte (Straßenmitte) von Überwegen ohne Ampel, an denen jemand am Rand wartet
static var zebra_waits := PackedVector3Array()
static var _tint_cache := {}


## Steht/geht im Umkreis r um pos ein Fußgänger auf der Fahrbahn? (für traffic/ai_car, falls Autos anhalten sollen)
static func crossing_near(pos: Vector3, r: float) -> bool:
	var r2 := r * r
	for q in on_road_pts:
		if (q.x - pos.x) * (q.x - pos.x) + (q.z - pos.z) * (q.z - pos.z) < r2:
			return true
	return false


static func material() -> ShaderMaterial:
	var m: ShaderMaterial = _tint_cache.get("mat")
	if m == null:
		var sh := Shader.new()
		sh.code = SHADER
		m = ShaderMaterial.new()
		m.shader = sh
		_tint_cache["mat"] = m
	return m


func setup(w: World) -> void:
	world = w
	rng.seed = 4711
	_main = get_parent()
	for a in OS.get_cmdline_user_args():
		if a == "--peddebug":
			_debug = true
		elif a == "--pedparade":
			_parade = true
		elif a.begins_with("--peddump="):
			_dump = FileAccess.open(a.trim_prefix("--peddump="), FileAccess.WRITE)
	for def in MODELS:
		var f: String = DIR + String(def[0]) + ".glb"
		if not ResourceLoader.exists(f):
			continue
		var ps := load(f) as PackedScene
		if ps == null:
			continue
		var inst := ps.instantiate()
		var ap := inst.find_child("AnimationPlayer", true, false) as AnimationPlayer
		var m := {"scene": ps, "kind": String(def[1]), "walk": float(def[2]), "run": float(def[3]), "walk_T": 1.06, "run_T": 0.7}
		# Schrittlängen stehen als glTF-"extras" an der Armatur (peds_build.py); die Tabelle oben ist nur Rückfall
		var armn := inst.find_child("Armature", true, false)
		if armn and armn.has_meta("extras"):
			var ex: Dictionary = armn.get_meta("extras")
			m["walk"] = float(ex.get("walk_len", m["walk"]))
			m["run"] = float(ex.get("run_len", m["run"]))
		if ap:
			for nm in ap.get_animation_list():
				ap.get_animation(nm).loop_mode = Animation.LOOP_LINEAR
			if ap.has_animation("Walk"):
				m["walk_T"] = ap.get_animation("Walk").length
			if ap.has_animation("Run"):
				m["run_T"] = ap.get_animation("Run").length
		inst.free()
		if not by_kind.has(m["kind"]):
			by_kind[m["kind"]] = []
		(by_kind[m["kind"]] as Array).append(models.size())
		models.append(m)
	_has_models = models.size() > 0


# --- Kacheln -------------------------------------------------------------------------------------
func add_tile(tile: Tile) -> void:
	var life: Dictionary = tile.city.get("life", {})
	for sh in life.get("shops", []):
		var mid := Vector2((float(sh[1]) + float(sh[3])) * 0.5, (float(sh[2]) + float(sh[4])) * 0.5)
		var n := Vector2(sh[5], sh[6])
		if sh.size() > 9 and String(sh[9]) == "vacant":
			continue
		_add_hot(tile.key, mid + n * 1.3, atan2(n.x, n.y), 0)      # schaut zum Schaufenster
	for f in life.get("furniture", []):
		var kind: String = f[0]
		if kind in ["stop_pole", "bus_stop"]:
			_add_hot(tile.key, Vector2(f[1], f[2]) + Vector2(0.9, 0.6), float(f[3]), 1)
		elif kind in ["cafe_set", "bench", "litfass"]:
			_add_hot(tile.key, Vector2(f[1], f[2]) + Vector2(0.9, 0.6), float(f[3]), 2)
	var rid := {}
	_rid[tile.key] = rid
	for r in tile.city["roads"]:
		if r["bridge"]:
			continue
		var cls: String = r.get("cls", "")
		var pts: Array = r["pts"]
		if pts.size() < 2:
			continue
		var w: float = r["width"]
		if cls in ["footway", "pedestrian", "path"]:
			_add_path(tile.key, _pts2(pts, 0.0), r, 0)
		elif cls in ["residential", "tertiary", "secondary", "primary", "unclassified", "living_street"]:
			var off: float = w * 0.5 + 1.4
			var a = _add_path(tile.key, _pts2(pts, off), r, 1)
			var b = _add_path(tile.key, _pts2(pts, -off), r, -1)
			if a != null and b != null:
				rid[int(r["id"])] = [a, b]
	# Überwege (Zebrastreifen, Furten): Wechsel auf die andere Straßenseite
	if tile.road_index:
		for c in tile.city.get("crossings", []):
			var hit: Dictionary = tile.road_index.nearest(c[0], c[1], 2.0)
			if hit.is_empty():
				continue
			var pair = rid.get(int(hit["road"]["id"]))
			if pair == null:
				continue
			var q := Vector2(hit["px"], hit["pz"])
			var sa := _project(pair[0], q)
			var sb := _project(pair[1], q)
			(pair[0]["xings"] as Array).append([sa, pair[1], sb, 0, 0.18, q])
			(pair[1]["xings"] as Array).append([sb, pair[0], sa, 0, 0.18, q])
	# Ampelknoten: Zufahrten mit Richtung, Phase und Steuerung
	var graph: Dictionary = tile.city.get("graph", {})
	var ctls: Array = graph.get("ctls", [])
	for nd in graph.get("nodes", []):
		if not nd.get("signal", false) or not nd.has("app"):
			continue
		var apps: Array = []
		for a in nd["app"]:
			var ci := int(a[7])
			if int(a[5]) >= 0 and ci >= 0 and ci < ctls.size():
				apps.append([float(a[2]), int(a[5]), ctls[ci]])
		if apps.is_empty():
			continue
		var p := Vector2(nd["pos"][0], nd["pos"][2])
		var key := Vector2i(floori(p.x / SCELL), floori(p.y / SCELL))
		if not sigs.has(key):
			sigs[key] = []
		(sigs[key] as Array).append({"p": p, "tile": tile.key, "apps": apps})
	# feste Hindernisse nach und nach einsortieren (viele tausend je Kachel)
	_obst_cells[tile.key] = []
	_obst_jobs.append([tile.key, tile.city.get("trees", []), 0, 0])
	_obst_jobs.append([tile.key, tile.city.get("lamps", []), 1, 0])
	_obst_jobs.append([tile.key, life.get("furniture", []), 2, 0])
	_obst_jobs.append([tile.key, tile.city.get("parked", []), 3, 0])
	_obst_jobs.append([tile.key, tile.city.get("signal_heads", []), 1, 0])


func _add_hot(tkey: String, p: Vector2, yaw: float, k: int) -> void:
	var key := Vector2i(floori(p.x / CELL), floori(p.y / CELL))
	if not hots.has(key):
		hots[key] = []
	hots[key].append({"p": p, "yaw": yaw, "tile": tkey, "k": k})


func remove_tile(tile: Tile) -> void:
	for grid in [hots, sigs]:
		for k in grid.keys():
			var arr2: Array = grid[k]
			for i in range(arr2.size() - 1, -1, -1):
				if arr2[i]["tile"] == tile.key:
					arr2.remove_at(i)
			if arr2.is_empty():
				grid.erase(k)
	for k in cells.keys():
		var arr: Array = cells[k]
		for i in range(arr.size() - 1, -1, -1):
			if arr[i]["tile"] == tile.key:
				arr[i]["dead"] = true
				arr[i]["nx"] = [null, null]
				arr[i]["xings"] = []
				arr.remove_at(i)
		if arr.is_empty():
			cells.erase(k)
	for k in ends.keys():
		var arr3: Array = ends[k]
		for i in range(arr3.size() - 1, -1, -1):
			if arr3[i][0]["tile"] == tile.key:
				arr3.remove_at(i)
		if arr3.is_empty():
			ends.erase(k)
	_rid.erase(tile.key)
	for k in _obst_cells.get(tile.key, []):
		_obst.erase(k)
	_obst_cells.erase(tile.key)
	for i in range(_obst_jobs.size() - 1, -1, -1):
		if _obst_jobs[i][0] == tile.key:
			_obst_jobs.remove_at(i)
	for i in range(peds.size() - 1, -1, -1):
		var p: Ped = peds[i]
		if p.path.get("dead", false) or (p.path.is_empty() and Tile.key_at(p.pos.x, p.pos.y) == tile.key):
			_free_ped(i)


## Linie um off nach rechts versetzen (Ecken auf Gehrung, damit der Gehweg in Kurven nicht in die Fahrbahn schneidet)
func _pts2(pts: Array, off: float) -> Array:
	var res: Array = []
	var n := pts.size()
	for i in n:
		var p := Vector2(pts[i][0], pts[i][1])
		if off != 0.0:
			var t0 := Vector2.ZERO
			var t1 := Vector2.ZERO
			if i > 0:
				t0 = Vector2(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]).normalized()
			if i < n - 1:
				t1 = Vector2(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]).normalized()
			if i == 0:
				t0 = t1
			elif i == n - 1:
				t1 = t0
			var t := (t0 + t1).normalized()
			if t == Vector2.ZERO:
				t = t1
			var miter := 1.0 / maxf(sqrt(maxf((1.0 + t0.dot(t1)) * 0.5, 0.0)), 0.6)
			p += Vector2(-t.y, t.x) * off * miter
		res.append(p)
	return res


func _add_path(tkey: String, pts: Array, r: Dictionary, side: int):
	var cum := PackedFloat32Array()
	cum.resize(pts.size())
	var L := 0.0
	cum[0] = 0.0
	for i in pts.size() - 1:
		L += (pts[i + 1] as Vector2).distance_to(pts[i])
		cum[i + 1] = L
	if L < 18.0:
		return null
	var mid: Vector2 = pts[pts.size() / 2]
	var key := Vector2i(floori(mid.x / CELL), floori(mid.y / CELL))
	if not cells.has(key):
		cells[key] = []
	var path := {"pts": pts, "cum": cum, "len": L, "tile": tkey, "rid": int(r["id"]), "side": side, "w": float(r["width"]),
			"bad": 0, "dead": false, "nx": [null, null], "xings": [], "r": r}
	cells[key].append(path)
	for e in 2:
		var q: Vector2 = pts[0] if e == 0 else pts[pts.size() - 1]
		var ek := Vector2i(floori(q.x / ECELL), floori(q.y / ECELL))
		if not ends.has(ek):
			ends[ek] = []
		(ends[ek] as Array).append([path, e])
	return path


## Punkt und Richtung auf dem Weg bei Bogenlänge s -> _sp, _st
func _sample(path: Dictionary, s: float) -> void:
	var cum: PackedFloat32Array = path["cum"]
	var pts: Array = path["pts"]
	var lo := 0
	var hi := cum.size() - 1
	while hi - lo > 1:
		var m := (lo + hi) >> 1
		if cum[m] <= s:
			lo = m
		else:
			hi = m
	var a: Vector2 = pts[lo]
	var b: Vector2 = pts[hi]
	var l := cum[hi] - cum[lo]
	_sp = a.lerp(b, clampf((s - cum[lo]) / maxf(l, 0.001), 0.0, 1.0))
	_st = (b - a) / maxf(l, 0.001)


## Bogenlänge des Wegpunkts, der q am nächsten liegt
func _project(path: Dictionary, q: Vector2) -> float:
	var pts: Array = path["pts"]
	var cum: PackedFloat32Array = path["cum"]
	var best := INF
	var bs := 0.0
	for i in pts.size() - 1:
		var a: Vector2 = pts[i]
		var b: Vector2 = pts[i + 1]
		var ab := b - a
		var l2 := ab.length_squared()
		var t := 0.0 if l2 < 1e-6 else clampf((q - a).dot(ab) / l2, 0.0, 1.0)
		var d := q.distance_squared_to(a + ab * t)
		if d < best:
			best = d
			bs = cum[i] + sqrt(l2) * t
	return bs


func _obst_step() -> void:
	## je Bild höchstens 500 Hindernisse einsortieren
	var budget := 500
	while budget > 0 and not _obst_jobs.is_empty():
		var job: Array = _obst_jobs[0]
		var list: Array = job[1]
		var kind: int = job[2]
		var i: int = job[3]
		var cl: Array = _obst_cells.get(job[0], [])
		while i < list.size() and budget > 0:
			var e: Array = list[i]
			i += 1
			budget -= 1
			match kind:
				0:
					_obst_add(cl, float(e[0]), float(e[1]), 0.32)
				1:
					_obst_add(cl, float(e[0]), float(e[1]), 0.2)
				2:
					var nm: String = e[0]
					var r := 0.0
					match nm:
						"bench", "bike_rack", "bicycle", "cafe_set", "glass_containers":
							r = 0.75
						"litfass", "street_cabinet", "construction_fence":
							r = 0.6
						"bin_public", "post_box", "trash_bags", "cardboard":
							r = 0.38
						"hydrant", "bollard", "parking_meter", "stop_pole", "billboard":
							r = 0.22
						"bus_stop":
							r = 1.1
					if r > 0.0:
						_obst_add(cl, float(e[1]), float(e[2]), r)
				3:
					var yw := float(e[2])
					var fx := -sin(yw) * 1.15
					var fz := -cos(yw) * 1.15
					_obst_add(cl, float(e[0]) + fx, float(e[1]) + fz, 1.0)
					_obst_add(cl, float(e[0]) - fx, float(e[1]) - fz, 1.0)
		job[3] = i
		if i >= list.size():
			_obst_jobs.remove_at(0)


## Steht an der Stelle q (Körperradius r) ein festes Hindernis?
func _obst_hit(q: Vector2, r: float) -> bool:
	var cx := floori(q.x / OCELL)
	var cz := floori(q.y / OCELL)
	for ix in range(cx - 1, cx + 2):
		for iz in range(cz - 1, cz + 2):
			var ol = _obst.get(Vector2i(ix, iz))
			if ol == null:
				continue
			for o in ol:
				var rr: float = o.z + r
				if (o.x - q.x) * (o.x - q.x) + (o.y - q.y) * (o.y - q.y) < rr * rr:
					return true
	return false


func _obst_add(cl: Array, x: float, z: float, r: float) -> void:
	var k := Vector2i(floori(x / OCELL), floori(z / OCELL))
	var a = _obst.get(k)
	if a == null:
		a = []
		_obst[k] = a
		cl.append(k)
	(a as Array).append(Vector3(x, z, r))


# --- Ablauf --------------------------------------------------------------------------------------
func _process(delta: float) -> void:
	if not enabled:
		return
	var t0 := Time.get_ticks_usec()
	_frame += 1
	if focus.distance_to(_last_focus) > 120.0:
		_warm = 2.5                      # Sprung (Start, Teleport): sofort auffüllen, auch im Blickfeld
	_last_focus = focus
	var playing: bool = _main == null or _main.get("ready_to_play") != false
	if playing and not cells.is_empty():
		_warm = maxf(_warm - delta, 0.0)
	_obst_step()
	_snap_t -= delta
	if _snap_t <= 0.0:
		_snapshot(0.1 - _snap_t)
		_snap_t = 0.1
	_dens_t -= delta
	if _dens_t <= 0.0:
		_dens_t = 1.5
		_update_target()
	if _parade:
		if playing and not cells.is_empty() and _has_models and get_viewport().get_camera_3d() != null:
			_parade = false
			_make_parade()
	_spawn_t -= delta
	if peds.size() < _target and _spawn_t <= 0.0:
		_spawn_t = 0.03 if _warm > 0.0 else 0.15
		_try_spawn()
	_trim_t -= delta
	if _trim_t <= 0.0:
		_trim_t = 0.4 if peds.size() < _target + 15 else 0.12
		_trim()
	var f2 := Vector2(focus.x, focus.z)
	for i in range(peds.size() - 1, -1, -1):
		var p: Ped = peds[i]
		p.d2 = p.pos.distance_squared_to(f2)
		if p.d2 > FAR * FAR:
			_free_ped(i)
			continue
		# Entfernungsstufen: nah jedes Bild, weiter weg jedes 2./4. Bild (Bewegung und Animation mit Summenzeit)
		var every := 1 if p.d2 < 2500.0 else (2 if p.d2 < 10000.0 else 4)
		if every > 1 and (_frame + p.fo) % every != 0:
			p.acc += delta
			continue
		var dt := delta + p.acc
		p.acc = 0.0
		if p.lead != null:
			_follow(p, dt)
		else:
			p.think_t -= dt
			if p.think_t <= 0.0:
				var td := 0.22 + rng.randf() * 0.06
				_think(p, td - p.think_t)
				p.think_t = td
			_step(p, dt)
		_apply(p, dt)
	if _dump != null:
		# Entwickler: jede halbe Sekunde alle Lagen als JSON-Zeile (Auswertung/Zeichnung außerhalb)
		_dump_t -= delta
		if _dump_t <= 0.0:
			_dump_t = 0.5
			var rows: Array = []
			for q in peds:
				var pp: Ped = q
				rows.append([snappedf(pp.pos.x, 0.01), snappedf(pp.pos.y, 0.01), pp.state, int(pp.wait), int(pp.on_road), snappedf(pp.v, 0.01),
						int(pp.lead != null), pp.kind, pp.get_instance_id() % 100000, pp.cur])
			var cs: Array = []
			for c in _cars:
				cs.append([snappedf(c[0].x, 0.1), snappedf(c[0].y, 0.1), snappedf(c[2], 0.1)])
			_dump.store_line(JSON.stringify({"t": snappedf(Time.get_ticks_msec() / 1000.0, 0.01), "f": [snappedf(focus.x, 0.1), snappedf(focus.z, 0.1)], "target": _target, "peds": rows, "cars": cs}))
			_dump.flush()
	if _debug:
		_dbg_us += Time.get_ticks_usec() - t0
		_dbg_n += 1
		_dbg_t -= delta
		if _dbg_t <= 0.0:
			_dbg_t = 2.0
			var st := [0, 0, 0]
			var nw := 0
			var nr := 0
			var nm := 0
			for q in peds:
				st[(q as Ped).state] += 1
				nw += int((q as Ped).wait)
				nr += int((q as Ped).on_road)
				nm += int((q as Ped).lead != null)
			print("PEDS n=%d ziel=%d gehen=%d stehen=%d ausweichen=%d | warten=%d fahrbahn=%d begleiter=%d | autos=%d | %.2f ms/Bild" % [
				peds.size(), _target, st[0], st[1], st[2], nw, nr, nm, _cars.size(), _dbg_us / 1000.0 / maxf(_dbg_n, 1)])
			_dbg_us = 0
			_dbg_n = 0


## Soll-Anzahl: Tageszeit x Wetter x Lage (Läden im Umkreis)
func _update_target() -> void:
	var hours := 15.0
	var weather := 0
	var em = _main.get("env_mgr") if _main else null
	if em != null:
		hours = float(em.hours)
		weather = int(em.weather)
	var h0 := int(floor(hours)) % 24
	var day: float = lerpf(DAY_CURVE[h0], DAY_CURVE[(h0 + 1) % 24], hours - floor(hours))
	var wet: float = [1.0, 0.95, 0.4, 0.8][clampi(weather, 0, 3)]
	var shops := 0
	var f2 := Vector2(focus.x, focus.z)
	var c0 := Vector2i(floori((f2.x - 160.0) / CELL), floori((f2.y - 160.0) / CELL))
	var c1 := Vector2i(floori((f2.x + 160.0) / CELL), floori((f2.y + 160.0) / CELL))
	for cx in range(c0.x, c1.x + 1):
		for cz in range(c0.y, c1.y + 1):
			for h in hots.get(Vector2i(cx, cz), []):
				if h["k"] == 0 and (h["p"] as Vector2).distance_squared_to(f2) < 25600.0:
					shops += 1
	var area := clampf(0.30 + shops / 45.0, 0.30, 1.3)
	_target = clampi(roundi(target_count * day * wet * area), 2, MAX_PEDS)


## Zu viele (Abend, Regen, ruhige Gegend): ferne bzw. nicht sichtbare Menschen nach und nach entfernen
func _trim() -> void:
	if peds.size() <= _target + 3:
		return
	for attempt in 6:
		var i := rng.randi_range(0, peds.size() - 1)
		var p: Ped = peds[i]
		if p.d2 < 1600.0 or p.on_road:
			continue
		if p.d2 > 12100.0 or not _in_view(p.pos, 200.0):
			if p.mate != null:
				continue
			_free_ped(i)
			return


func _in_view(q: Vector2, max_d: float) -> bool:
	var cam := get_viewport().get_camera_3d()
	if cam == null:
		return false
	var cp := cam.global_position
	var to := Vector2(q.x - cp.x, q.y - cp.z)
	var d := to.length()
	if d > max_d:
		return false
	var fw := -cam.global_transform.basis.z
	return to.dot(Vector2(fw.x, fw.z)) > 0.35 * d


## Momentaufnahme alle 0,1 s: Fahrzeuge (Spieler, Verkehr, Bahnen) und Fußgänger-Raster
func _snapshot(dt: float) -> void:
	_cars.clear()
	_cgrid.clear()
	var f2 := Vector2(focus.x, focus.z)
	if _main != null:
		var pl = _main.get("player")
		if pl != null and is_instance_valid(pl):
			var gp: Vector3 = pl.global_position
			var lv: Vector3 = pl.linear_velocity
			var v2 := Vector2(lv.x, lv.z)
			_cars.append([Vector2(gp.x, gp.z), v2, v2.length(), 0.95, 2.3, 0.5])
		var tr = _main.get("traffic")
		if tr != null:
			for c in tr.cars:
				var cp: Vector3 = c.world_pos()
				var q := Vector2(cp.x, cp.z)
				if q.distance_squared_to(f2) > 48400.0:
					continue
				var sp: float = absf(c.speed)
				var hd: float = c.heading
				_cars.append([q, Vector2(-sin(hd), -cos(hd)) * sp, sp, float(c.width) * 0.5, float(c.length) * 0.5, 0.5])
		var tm = _main.get("trams")
		if tm != null:
			var seen := {}
			for b in tm.section_bodies():
				var bp: Vector3 = (b as Node3D).global_position
				var q2 := Vector2(bp.x, bp.z)
				if q2.distance_squared_to(f2) > 48400.0:
					continue
				var id: int = (b as Node3D).get_instance_id()
				var vel := Vector2.ZERO
				if _tram_last.has(id):
					vel = (q2 - (_tram_last[id] as Vector2)) / maxf(dt, 0.01)
					if vel.length() > 30.0:
						vel = Vector2.ZERO
				seen[id] = q2
				_cars.append([q2, vel, vel.length(), 1.35, 7.5, 0.15])      # Bahn: am Bahnsteig steht man dicht daneben
			_tram_last = seen
	for c in _cars:
		var k := Vector2i(floori(c[0].x / CCELL), floori(c[0].y / CCELL))
		if not _cgrid.has(k):
			_cgrid[k] = []
		(_cgrid[k] as Array).append(c)
	_pgrid.clear()
	on_road_pts.clear()
	zebra_waits.clear()
	for q3 in peds:
		var p: Ped = q3
		var k2 := Vector2i(floori(p.pos.x / PCELL), floori(p.pos.y / PCELL))
		if not _pgrid.has(k2):
			_pgrid[k2] = []
		(_pgrid[k2] as Array).append(p)
		if p.on_road:
			on_road_pts.append(Vector3(p.pos.x, p.node.position.y, p.pos.y))
		elif p.wait and p.zebra != Vector2.INF and p.cross.get("sig") == null:
			zebra_waits.append(Vector3(p.zebra.x, p.node.position.y, p.zebra.y))


# --- Verhalten -----------------------------------------------------------------------------------
## Geht die Person gerade frei auf ihren Zielpunkt zu (anderer Weg, Schaufenster, zurück vom Ausweichen)?
## Kleine Versätze (< 1,6 m) werden stattdessen im Weitergehen abgebaut.
func _merging(p: Ped) -> bool:
	var l2 := (p.off_t - p.off).length_squared()
	return l2 > 2.56 or (l2 > 0.0016 and (not p.arrive.is_empty() or p.path.is_empty()))


func _heading(p: Ped) -> Vector2:
	var dv := p.off_t - p.off
	if _merging(p):
		return dv.normalized()
	if p.path.is_empty():
		return p.hv
	_sample(p.path, p.s)
	return _st * float(p.dir)


func _think(p: Ped, td: float) -> void:
	if p.state == DODGE:
		return
	var near := p.d2 < 12100.0
	p.ghost_t = maxf(p.ghost_t - td, 0.0)
	# Schatten nur in der Nähe
	var sh := p.d2 < 3600.0
	if sh != p.shadow and p.mesh != null:
		p.shadow = sh
		p.mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if sh else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	if near and not _cars.is_empty():
		var th := _threat(p)
		if not th.is_empty():
			if p.on_road:
				p.run_t = 1.6                               # mitten auf der Fahrbahn: zügig hinüber
			else:
				_start_dodge(p, th)
				return
	if p.state != WALK:
		return
	if not near:
		# weit weg: einfach gehen (dort hält auch kein Auto für sie an)
		p.slow = 1.0
		if p.on_road or p.wait:
			p.on_road = false
			p.wait = false
			p.cross = {}
			p.zebra = Vector2.INF
			p.stand_anim = "Idle"
		return
	var h := _heading(p)
	p.hv = h
	var ahead := p.pos + h * (1.25 + p.v * 0.3)
	if p.on_road:
		p.road_t += td
		var hr := _road_hit(ahead)
		if p.road_t > 1.5 and hr.is_empty() and _road_hit(p.pos).is_empty():
			p.on_road = false
			p.cross = {}
			p.zebra = Vector2.INF
			p.along_t = 0.0
			if p.arrive.is_empty():
				p.off_t = Vector2.ZERO
		elif not hr.is_empty() and not _merging(p) and not p.path.is_empty():
			# der Weg führt längs in einer Fahrbahn weiter (zweite Richtungsfahrbahn, Gleiskörper): umkehren
			if absf(h.x * float(hr["tz"]) - h.y * float(hr["tx"])) < 0.3:
				p.along_t += td
				if p.along_t > 1.2:
					p.along_t = -60.0                         # einmal umkehren und auf demselben Weg wieder hinaus
					p.path["bad"] = int(p.path["bad"]) + 1
					_turn(p)
			elif p.along_t > 0.0:
				p.along_t = 0.0
		if not _merging(p) and not p.path.is_empty():
			_avoid(p, h, td)                                # auch beim Queren aneinander vorbei, aber nicht stehen bleiben
		p.slow = 1.0
		return
	if p.wait:
		_wait_think(p, td)
		return
	var hit := _road_hit(ahead)
	if not hit.is_empty():
		if not _road_hit(p.pos).is_empty():
			p.on_road = true                                # steht schon auf der Fahrbahn (kam aus der Ferne): weiter
			p.road_t = 0.0
			return
		_begin_cross(p, hit, h)
		if p.wait or p.on_road:
			return
	_avoid(p, h, td)
	if not _merging(p) and p.arrive.is_empty() and not p.path.is_empty():
		# Abzweige: Überweg auf die andere Straßenseite, Gehweg der Querstraße an der Ecke
		for x in p.path["xings"]:
			var ds: float = (float(x[0]) - p.s) * p.dir
			if ds > 0.0 and ds < p.v * td + 0.25 and rng.randf() < float(x[4]) and not (x[1] as Dictionary)["dead"] and int((x[1] as Dictionary)["bad"]) < 2:
				_switch_path(p, x[1], float(x[2]), int(x[3]))
				p.zebra = x[5] if x[5] != null else Vector2.INF
				return
		p.shop_t -= td
		if p.shop_t <= 0.0:
			p.shop_t = rng.randf_range(4.0, 10.0)
			if p.lead == null and _try_window(p, h):
				p.shop_t = rng.randf_range(40.0, 120.0)
		p.phone_t -= td
		if p.phone_t <= 0.0:
			p.phone_t = rng.randf_range(90.0, 400.0)
			if p.kind != "k" and p.mate == null:
				p.state = STAND
				p.stand_anim = "Phone"
				p.t = rng.randf_range(6.0, 18.0)
				p.face = NAN


## Fahrbahn unter dem Punkt? Liefert den Straßentreffer oder {}
func _road_hit(q: Vector2) -> Dictionary:
	var hit := world.nearest(q.x, q.y, 9.0)
	if hit.is_empty() or hit["bridge"]:
		return {}
	if float(hit["d"]) < float(hit["road"]["width"]) * 0.5 - 0.15:
		return hit
	return {}


func _begin_cross(p: Ped, hit: Dictionary, h: Vector2) -> void:
	var t := Vector2(hit["tx"], hit["tz"])
	var sn := absf(h.x * t.y - h.y * t.x)
	var w: float = hit["road"]["width"]
	var merging := _merging(p)
	if sn < 0.3:
		if not merging and not p.path.is_empty():
			# der Weg läuft hier in einer Fahrbahn weiter (z. B. zweite Richtungsfahrbahn): umkehren
			p.path["bad"] = int(p.path["bad"]) + 1
			_turn(p)
			return
		sn = 0.3
	var L := minf(w / sn + 1.5, 26.0)
	var ang := atan2(t.y, t.x)
	var minor := String(hit["road"].get("cls", "")) == "service"      # Zufahrten, Parkplatzwege: nie ampelgeregelt
	p.wait_t = 0.0
	p.cross = {"a": p.pos, "h": h, "L": L, "T": L / (p.v0 * 1.15), "sig": null if minor else _signal_for(p.pos + h * (L * 0.5), ang),
			"minor": minor}
	if _cross_clear(p):
		p.on_road = true
		p.road_t = 0.0
		if _debug:
			_dbg_cross(p, "ohne Halt")
	else:
		p.wait = true
		p.wait_t = 0.0
		p.wait_max = rng.randf_range(90.0, 130.0) if p.cross["sig"] != null else rng.randf_range(25.0, 45.0)


## Wartende am Fahrbahnrand stellen sich nebeneinander statt ineinander (nur seitlich, nicht auf die Fahrbahn)
func _spread(p: Ped) -> void:
	var side := Vector2(-p.hv.y, p.hv.x)
	var ps := 0.0
	var px := floori(p.pos.x / PCELL)
	var pz := floori(p.pos.y / PCELL)
	for ix in range(px - 1, px + 2):
		for iz in range(pz - 1, pz + 2):
			var pl = _pgrid.get(Vector2i(ix, iz))
			if pl == null:
				continue
			for q0 in pl:
				var q: Ped = q0
				if q == p or q.v > 0.3 or q == p.mate or q.lead == p:
					continue
				var d := p.pos - q.pos
				var l := d.length()
				if l >= 0.7:
					continue
				var sd := d.dot(side)
				if absf(sd) < 0.12:
					# (fast) hintereinander oder aufeinander: die Reihenfolge der Objekte entscheidet die Seite
					sd = 0.12 if p.get_instance_id() > q.get_instance_id() else -0.12
				ps += signf(sd) * (0.7 - l)
	if ps != 0.0:
		var mv := side * clampf(ps * 0.6, -0.2, 0.2)
		var same := p.off == p.off_t
		p.off += mv
		if same:
			p.off_t = p.off
		if p.path.is_empty():
			p.pos += mv


func _wait_think(p: Ped, td: float) -> void:
	p.wait_t += td
	_spread(p)
	p.stand_anim = "Look" if p.wait_t < 3.4 or (p.cross.get("sig") == null and fmod(p.wait_t, 9.0) < 3.2) else "Idle"
	if p.wait_t > 0.7 and _cross_clear(p):
		p.wait = false
		p.on_road = true
		p.road_t = 0.0
		p.stand_anim = "Idle"
		if _debug:
			_dbg_cross(p, "nach %.1f s Warten" % p.wait_t)
		return
	if p.wait_t > p.wait_max:
		p.wait = false
		p.stand_anim = "Idle"
		if not _merging(p) and not p.path.is_empty():
			_turn(p)                                        # aufgeben und umkehren
		else:
			p.on_road = true                                # Übergang auf den anderen Weg: jetzt gehen
			p.road_t = 0.0


func _dbg_cross(p: Ped, how: String) -> void:
	var st := "keine Ampel"
	if p.cross.get("sig") != null:
		var names := ["Rot", "Rot-Gelb", "Grün", "Gelb"]
		st = "Ampel, Querverkehr:"
		for a in p.cross["sig"]:
			st += " " + names[SignalCtl.state(a[2], a[1])]
	print("PEDS quert bei (%.0f, %.0f) %s, %.1f m, %s%s%s" % [p.pos.x, p.pos.y, how, float(p.cross["L"]), st,
			", eilig" if p.hurry else "", ", Überweg" if p.zebra != Vector2.INF else ""])


func _signal_for(q: Vector2, ang: float):
	var best = null
	var bd := 484.0                     # Ampelknoten höchstens 22 m von der Querungsmitte
	var cx := floori(q.x / SCELL)
	var cz := floori(q.y / SCELL)
	for ix in range(cx - 1, cx + 2):
		for iz in range(cz - 1, cz + 2):
			for sg in sigs.get(Vector2i(ix, iz), []):
				var d := (sg["p"] as Vector2).distance_squared_to(q)
				if d < bd:
					bd = d
					best = sg
	if best == null:
		return null
	var res: Array = []
	for a in best["apps"]:
		if absf(cos(float(a[0]) - ang)) >= 0.6:           # Zufahrten längs der zu querenden Fahrbahn
			res.append(a)
	return res if not res.is_empty() else null


func _cross_clear(p: Ped) -> bool:
	var c := p.cross
	var T: float = c["T"]
	if c["sig"] != null:
		var red := true
		for a in c["sig"]:
			if SignalCtl.state(a[2], a[1]) != SignalCtl.RED or SignalCtl.state(a[2], a[1], SignalCtl.clock + minf(T * 0.7, 6.0)) != SignalCtl.RED:
				red = false
				break
		if not red:
			# Eilige gehen bei Rot, wenn weit und breit nichts kommt
			if not (p.hurry and p.wait_t > 4.0 and _gap_clear(c["a"], c["h"], c["L"], T + 6.0)):
				return false
	return _gap_clear(c["a"], c["h"], c["L"], T)


## Kommt in der Zeit T (plus Sicherheit) ein Fahrzeug über die Querungslinie a -> a + h * L?
## Gerechnet wird mit der Geradeausfahrt jedes Fahrzeugs: Schnittpunkt seiner Fahrlinie mit der Querungslinie.
## Wer parallel zur Gehrichtung fährt (Verkehr auf der Straße, an der man entlanggeht), kreuzt nicht.
func _gap_clear(a: Vector2, h: Vector2, L: float, T: float) -> bool:
	for c in _cars:
		var cp: Vector2 = c[0]
		var sp: float = c[2]
		var hl: float = c[4]
		var r := cp - a
		if r.length_squared() > 22500.0:
			continue
		if sp < 0.6:
			var al := r.dot(h)
			if al > -1.0 and al < L + 1.0 and absf(h.x * r.y - h.y * r.x) < hl + 0.8:
				return false                                # steht auf der Querung
			continue
		var vd: Vector2 = (c[1] as Vector2) / sp
		var den := vd.x * h.y - vd.y * h.x
		if absf(den) < 0.25:
			# fährt längs: nur gefährlich, wenn es auf der Querungslinie selbst entlangkommt
			var al2 := r.dot(h)
			if absf(h.x * r.y - h.y * r.x) < float(c[3]) + 1.0 and al2 > -sp * (T + 2.0) - hl and al2 < L + sp * (T + 2.0) + hl:
				return false
			continue
		var tc := (-r.x * h.y + r.y * h.x) / den            # Strecke des Fahrzeugs bis zur Querungslinie
		var u := (-r.x * vd.y + r.y * vd.x) / den           # Stelle auf der Querungslinie
		if u > -1.8 and u < L + 1.8 and tc > -(hl + 1.0) and tc < sp * (T + 2.5) + hl + 3.0:
			return false
	return true


## Fährt ein Fahrzeug auf die Person zu? -> [Fahrzeug, seitlicher Abstand mit Vorzeichen] oder []
func _threat(p: Ped) -> Array:
	var cx := floori(p.pos.x / CCELL)
	var cz := floori(p.pos.y / CCELL)
	for ix in range(cx - 1, cx + 2):
		for iz in range(cz - 1, cz + 2):
			var list = _cgrid.get(Vector2i(ix, iz))
			if list == null:
				continue
			for c in list:
				var sp: float = c[2]
				if sp < 1.5:
					continue
				var vd: Vector2 = (c[1] as Vector2) / sp
				var rel: Vector2 = p.pos - (c[0] as Vector2)
				var along := rel.dot(vd)
				var hl: float = c[4]
				if along < -hl or along > hl + sp * 1.3 + 2.0:
					continue
				var side := vd.x * rel.y - vd.y * rel.x
				if absf(side) < float(c[3]) + float(c[5]):
					return [c, side]
	return []


func _start_dodge(p: Ped, th: Array) -> void:
	var c: Array = th[0]
	var side: float = th[1]
	var vd: Vector2 = (c[1] as Vector2).normalized()
	var perp := Vector2(-vd.y, vd.x) * (1.0 if side >= 0.0 else -1.0)
	p.dodge_to = p.off + perp * (float(c[3]) + 1.4 - absf(side))
	p.state = DODGE
	p.t = 0.0
	p.wait = false
	p.arrive = {}
	p.off_t = Vector2.ZERO
	p.face = NAN


## Seitlich ausweichen: freie Spur zwischen Hindernissen und anderen Menschen suchen, sonst langsamer werden
func _avoid(p: Ped, h: Vector2, td: float) -> void:
	var right := Vector2(-h.y, h.x)
	var merging := _merging(p) or p.path.is_empty()
	var lo := -1.2
	var hi := 1.2
	var lo2 := -1.2                     # erweiterter Bereich, nur wenn sonst kein Durchkommen ist
	var hi2 := 1.2
	var wr := PAIR_GAP if p.mate != null else 0.0
	if not merging:
		var road_left: bool = int(p.path["side"]) * p.dir > 0
		if int(p.path["side"]) != 0:
			lo = -1.0
			hi = 1.0
			lo2 = -1.0 if road_left else -1.9          # zur Fahrbahn nie näher als 0,4 m an die Kante
			hi2 = 1.9 if road_left else 1.0
	hi -= wr
	hi2 -= wr
	var blocked: Array = []             # [a, b, v längs, fwd] in Verschiebung relativ zur jetzigen Lage
	var probe := p.pos + h * 1.3
	# feste Hindernisse
	var ox := floori(probe.x / OCELL)
	var oz := floori(probe.y / OCELL)
	for ix in range(ox - 1, ox + 2):
		for iz in range(oz - 1, oz + 2):
			var ol = _obst.get(Vector2i(ix, iz))
			if ol == null:
				continue
			for o in ol:
				var rel := Vector2(o.x - p.pos.x, o.y - p.pos.y)
				var fwd := rel.dot(h)
				var r: float = o.z
				if fwd < -0.2 or fwd > 3.6 + r:
					continue
				var sd := rel.dot(right)
				if absf(sd) > r + 2.6:
					continue
				blocked.append([sd - r - 0.34 - wr, sd + r + 0.34, 0.0, fwd - r])
	# andere Menschen
	if p.ghost_t <= 0.0:
		var px := floori(probe.x / PCELL)
		var pz := floori(probe.y / PCELL)
		for ix in range(px - 1, px + 2):
			for iz in range(pz - 1, pz + 2):
				var pl = _pgrid.get(Vector2i(ix, iz))
				if pl == null:
					continue
				for q0 in pl:
					var q: Ped = q0
					if q == p or q == p.mate or q.lead == p or q.dead:
						continue
					var rel2 := q.pos - p.pos
					var fwd2 := rel2.dot(h)
					if fwd2 < -0.2 or fwd2 > 2.8:
						continue
					var sd2 := rel2.dot(right)
					if absf(sd2) > 2.4:
						continue
					var qv := q.hv.dot(h) * q.v
					if qv >= p.v0 - 0.08 and fwd2 > 0.7:
						continue                            # geht vor mir mindestens so schnell: kein Hindernis
					var a := sd2 - 0.62 - wr
					var b := sd2 + 0.62
					if qv < -0.2:
						a -= 0.35                           # Gegenverkehr: rechts aneinander vorbei
					if q.mate != null and q.lead == null:
						var qr := Vector2(-q.hv.y, q.hv.x).dot(right) * PAIR_GAP
						a = minf(a, a + qr)
						b = maxf(b, b + qr)
					blocked.append([a, b, maxf(qv, 0.0), fwd2 - 0.3])
	var want := 0.0 if merging else clampf(p.lat0, lo, hi) - p.lat
	if blocked.is_empty():
		# freie Bahn: nur gemächlich zur gewohnten Spur zurück (sonst Schlangenlinien um jeden Mast)
		p.lat_t = move_toward(p.lat, p.lat + want, 0.07)
		p.slow = 1.0
		p.stuck_t = 0.0
		return
	var best := INF
	var bx := 0.0
	var cands: Array = [want, 0.0]
	for bl in blocked:
		cands.append(float(bl[0]) - 0.03)
		cands.append(float(bl[1]) + 0.03)
	if not merging:
		for pass_i in 2:
			var l0 := lo if pass_i == 0 else lo2
			var h0 := hi if pass_i == 0 else hi2
			for x in cands:
				var xv: float = x
				if p.lat + xv < l0 - 0.001 or p.lat + xv > h0 + 0.001:
					continue
				var free := true
				for bl in blocked:
					if xv > float(bl[0]) and xv < float(bl[1]):
						free = false
						break
				if not free:
					continue
				var cost := absf(xv) + 0.3 * absf(xv - want)
				if cost < best:
					best = cost
					bx = xv
			if best < INF:
				break
	if best < INF:
		p.lat_t = p.lat + bx
		p.stuck_t = 0.0
		# was jetzt noch direkt vor mir ist, gibt das Tempo vor, bis die Spur frei ist
		var vmax := p.v0
		for bl in blocked:
			if 0.0 > float(bl[0]) + 0.12 and 0.0 < float(bl[1]) - 0.12 and float(bl[3]) < 1.1:
				vmax = minf(vmax, float(bl[2]) + maxf(float(bl[3]) - 0.35, 0.0) * 1.2)
		p.slow = clampf(vmax / p.v0, 0.0, 1.0)
	else:
		# keine freie Spur: hinter dem Vordermann bleiben / kurz warten
		var vmax2 := p.v0
		for bl in blocked:
			if 0.0 > float(bl[0]) + 0.1 and 0.0 < float(bl[1]) - 0.1:
				vmax2 = minf(vmax2, float(bl[2]) + maxf(float(bl[3]) - 0.45, 0.0) * 1.0)
		p.slow = clampf(vmax2 / p.v0, 0.0, 1.0)
		if p.slow < 0.25:
			p.stuck_t += td
			if p.stuck_t > 3.0:
				p.ghost_t = 2.5                             # festgefahren: kurz aneinander vorbeidrängeln
				p.stuck_t = 0.0
		else:
			p.stuck_t = 0.0


## Schaufenster in der Nähe ansteuern
func _try_window(p: Ped, h: Vector2) -> bool:
	if rng.randf() > (0.5 if p.kind != "k" else 0.15) or p.hurry or p.mate != null:
		return false
	var arr: Array = hots.get(Vector2i(floori(p.pos.x / CELL), floori(p.pos.y / CELL)), [])
	for hot in arr:
		if hot["k"] != 0:
			continue
		var d: Vector2 = (hot["p"] as Vector2) - p.pos
		var l2 := d.length_squared()
		if l2 > 42.0 or l2 < 1.0 or d.dot(h) < 1.0:
			continue
		if not _road_hit(hot["p"]).is_empty() or not _road_hit(p.pos + d * 0.5).is_empty() or _obst_hit(hot["p"], 0.45):
			continue
		_sample(p.path, p.s)
		var right := Vector2(-_st.y, _st.x) * float(p.dir)
		p.off_t = (hot["p"] as Vector2) + Vector2(rng.randf_range(-0.5, 0.5), rng.randf_range(-0.5, 0.5)) - (_sp + right * p.lat)
		p.arrive = {"yaw": float(hot["yaw"]), "anim": "Idle" if rng.randf() < 0.75 else "Phone", "t": rng.randf_range(4.0, 14.0)}
		return true
	return false


func _turn(p: Ped) -> void:
	p.dir = -p.dir
	p.lat = -p.lat
	p.lat_t = p.lat
	p.wait = false


## Auf einen anderen Weg wechseln: Lage bleibt, der Versatz zum neuen Wegpunkt wird im Gehen abgebaut
func _switch_path(p: Ped, path: Dictionary, s: float, dir: int) -> void:
	_ensure(path)
	_sample(path, s)
	if dir == 2:
		dir = 1 if rng.randf() < 0.5 else -1
	elif dir == 0:
		dir = 1 if _st.dot(p.hv) >= 0.0 else -1
	var right := Vector2(-_st.y, _st.x) * float(dir)
	p.path = path
	p.s = s
	p.dir = dir
	p.lat = clampf(p.lat0, -0.9, 0.9 - (PAIR_GAP if p.mate != null else 0.0))
	p.lat_t = p.lat
	p.off = p.pos - (_sp + right * p.lat)
	p.off_t = Vector2.ZERO
	p.arrive = {}


func _ensure(path: Dictionary) -> void:
	for e in 2:
		if path["nx"][e] == null:
			_connect_end(path, e)


func _add_xing(path: Dictionary, s: float, o: Dictionary, so: float, dcode: int, prob: float) -> void:
	for x in path["xings"]:
		if x[1] == o and absf(float(x[0]) - s) < 1.5:
			return
	(path["xings"] as Array).append([s, o, so, dcode, prob, null])


## Anschlüsse eines Wegendes (einmal je Ende): Fortsetzung am selben Punkt, Gehwege der Querstraßen an der Ecke
## (Schnittpunkt der Gehweglinien, noch vor der Fahrbahn), sonst gegenüberliegender Gehweg.
func _connect_end(path: Dictionary, e: int) -> void:
	var nx: Array = []
	path["nx"][e] = nx
	var pts: Array = path["pts"]
	var cum: PackedFloat32Array = path["cum"]
	var n := pts.size()
	var E: Vector2 = pts[n - 1] if e == 1 else pts[0]
	var s_end: float = float(path["len"]) if e == 1 else 0.0
	var ck := Vector2i(floori(E.x / ECELL), floori(E.y / ECELL))
	for ix in range(ck.x - 1, ck.x + 2):
		for iz in range(ck.y - 1, ck.y + 2):
			for en in ends.get(Vector2i(ix, iz), []):
				var o: Dictionary = en[0]
				if o == path or o["dead"]:
					continue
				var op: Array = o["pts"]
				var oq: Vector2 = op[0] if en[1] == 0 else op[op.size() - 1]
				if oq.distance_squared_to(E) < 2.25:
					nx.append([o, 0.0 if en[1] == 0 else float(o["len"]), 1 if en[1] == 0 else -1])
	var cont := not nx.is_empty()
	var tile: Tile = world.tiles.get(path["tile"])
	var pairs: Dictionary = _rid.get(path["tile"], {})
	if tile != null and tile.road_index != null:
		var rp: Array = path["r"]["pts"]
		var N := Vector2(rp[rp.size() - 1][0], rp[rp.size() - 1][1]) if e == 1 else Vector2(rp[0][0], rp[0][1])
		var rids := {}
		var ri: RoadIndex = tile.road_index
		for seg in ri.cells.get(Vector2i(floori(N.x / RoadIndex.CELL), floori(N.y / RoadIndex.CELL)), []):
			var cp := Geometry2D.get_closest_point_to_segment(N, Vector2(seg[0], seg[1]), Vector2(seg[2], seg[3]))
			if cp.distance_squared_to(N) < 1.5:
				rids[int(ri.roads[seg[4]]["id"])] = true
		rids.erase(int(path["rid"]))
		# Endstück (18 m), ohne Fortsetzung um 14 m über das Ende hinaus verlängert (Gehweg gegenüber)
		var tail: Array = []            # [Punkt, s]
		var i := n - 1 if e == 1 else 0
		var stp := -1 if e == 1 else 1
		while i >= 0 and i < n:
			tail.append([pts[i], cum[i]])
			if absf(cum[i] - s_end) > 18.0:
				break
			i += stp
		var ext := Vector2.ZERO
		if not cont and tail.size() > 1:
			ext = E + ((E - (tail[1][0] as Vector2)).normalized()) * 14.0
		for rid in rids:
			var pair = pairs.get(rid)
			if pair == null:
				continue
			for o2 in pair:
				var o: Dictionary = o2
				var op: Array = o["pts"]
				var oc: PackedFloat32Array = o["cum"]
				var found := false
				for j in op.size() - 1:
					var a: Vector2 = op[j]
					var b: Vector2 = op[j + 1]
					if a.distance_squared_to(E) > 3600.0 and b.distance_squared_to(E) > 3600.0:
						continue
					for k in tail.size() - 1:
						var X = Geometry2D.segment_intersects_segment(tail[k][0], tail[k + 1][0], a, b)
						if X == null:
							continue
						var so: float = oc[j] + a.distance_to(X)
						var ms: float = float(tail[k][1]) + (float(tail[k + 1][1]) - float(tail[k][1])) * ((tail[k][0] as Vector2).distance_to(X) / maxf((tail[k][0] as Vector2).distance_to(tail[k + 1][0]), 0.001))
						var dcode := 1 if so < 18.0 else (-1 if so > float(o["len"]) - 18.0 else 2)
						_add_xing(path, ms, o, so, dcode, 0.3 if cont else 0.8)
						_add_xing(o, so, path, ms, -1 if e == 1 else 1, 0.25)
						found = true
						break
					if found:
						break
					if ext != Vector2.ZERO:
						var X2 = Geometry2D.segment_intersects_segment(E, ext, a, b)
						if X2 != null:
							var so2: float = oc[j] + a.distance_to(X2)
							nx.append([o, so2, 1 if so2 < 18.0 else (-1 if so2 > float(o["len"]) - 18.0 else 2)])
							break
	if nx.is_empty():
		var own = pairs.get(int(path["rid"]))
		if own != null:
			var o3: Dictionary = own[1] if own[0] == path else own[0]
			nx.append([o3, 0.0 if e == 0 else float(o3["len"]), 1 if e == 0 else -1])


## Wegende: auf den anschließenden Weg übergehen (Fortsetzung, andere Straßenseite), sonst umkehren
func _path_end(p: Ped) -> void:
	var path := p.path
	var e := 1 if p.dir > 0 else 0
	if path["nx"][e] == null:
		_connect_end(path, e)
	var opts: Array = []
	for c in path["nx"][e]:
		if not (c[0] as Dictionary)["dead"] and int((c[0] as Dictionary)["bad"]) < 2:
			opts.append(c)
	p.s = clampf(p.s, 0.0, float(path["len"]))
	if opts.is_empty():
		_turn(p)
		p.state = STAND                                     # kurz stehen bleiben, umsehen, zurück
		p.stand_anim = "Look"
		p.t = rng.randf_range(2.0, 5.0)
		p.face = NAN
		return
	var c2: Array = opts[rng.randi_range(0, opts.size() - 1)]
	_switch_path(p, c2[0], float(c2[1]), int(c2[2]))


func _step(p: Ped, dt: float) -> void:
	match p.state:
		STAND:
			p.v = move_toward(p.v, 0.0, 4.0 * dt)
			p.t -= dt
			if p.t <= 0.0:
				_leave_stand(p)
		DODGE:
			var dv := p.dodge_to - p.off
			var l := dv.length()
			if l > 0.05:
				p.v = 3.3
				var stp := minf(p.v * dt, l)
				p.off += dv / l * stp
				if p.path.is_empty():
					p.pos += dv / l * stp
				p.hv = dv / l
			else:
				p.v = 0.0
				p.stand_anim = "Look"
				p.t += dt
				if p.t > 1.3:
					p.stand_anim = "Idle"
					if p.path.is_empty():
						p.state = STAND
						p.t = rng.randf_range(5.0, 20.0)
					else:
						p.state = WALK
		_:
			var vt := p.v0 * p.slow
			if p.wait:
				vt = 0.0
			elif p.on_road:
				vt = p.v0 * 1.15
			if p.run_t > 0.0:
				p.run_t -= dt
				vt = maxf(vt, 3.0)
			p.v = move_toward(p.v, vt, (2.2 if vt > p.v else 3.5) * dt)
			var dv2 := p.off_t - p.off
			var l2 := dv2.length()
			var free_walk := _merging(p)
			if l2 > 0.04 and not free_walk and p.v > 0.2:
				p.off += dv2 / l2 * minf(0.6 * dt, l2)          # kleiner Versatz: im Weitergehen abbauen
			if free_walk:
				# freier Weg zum Zielpunkt (zurück auf den Gehweg, zum Schaufenster, auf den nächsten Weg)
				var stp2 := minf(p.v * dt, l2)
				p.off += dv2 / l2 * stp2
				p.hv = dv2 / l2
			elif not p.arrive.is_empty():
				p.off = p.off_t
				p.state = STAND
				p.face = float(p.arrive["yaw"])
				p.stand_anim = String(p.arrive["anim"])
				p.t = float(p.arrive["t"])
				p.arrive = {}
			elif not p.path.is_empty():
				p.s += float(p.dir) * p.v * dt
				if p.s < 0.0 or p.s > float(p.path["len"]):
					_path_end(p)
				if p.v > 0.2:
					p.lat = move_toward(p.lat, p.lat_t, 0.75 * dt)
	if not p.path.is_empty():
		_sample(p.path, p.s)
		var d := _st * float(p.dir)
		var right := Vector2(-d.y, d.x)
		p.pos = _sp + right * p.lat + p.off
		if p.state == WALK and not _merging(p):
			var dl := p.lat_t - p.lat
			var ov := p.off_t - p.off
			var side_v := right * clampf(dl, -0.75, 0.75)
			if ov.length_squared() > 0.0016:
				side_v += ov.normalized() * 0.6
			p.hv = (d * maxf(p.v, 0.3) + side_v * (1.0 if p.v > 0.2 else 0.0)).normalized()


## Nach dem Stehen: zurück auf den Weg bzw. (frisch Gesetzte) zum nächsten Gehweg gehen
func _leave_stand(p: Ped) -> void:
	if p.path.is_empty():
		var hit := world.nearest(p.pos.x, p.pos.y, 30.0)
		var pair = null
		if not hit.is_empty():
			pair = (_rid.get(Tile.key_at(float(hit["px"]), float(hit["pz"])), {}) as Dictionary).get(int(hit["road"]["id"]))
		if pair == null:
			p.t = rng.randf_range(15.0, 40.0)
			return
		var best: Dictionary = pair[0]
		var bs := _project(pair[0], p.pos)
		_sample(pair[0], bs)
		var bd := _sp.distance_squared_to(p.pos)
		var s2 := _project(pair[1], p.pos)
		_sample(pair[1], s2)
		if _sp.distance_squared_to(p.pos) < bd:
			best = pair[1]
			bs = s2
			bd = _sp.distance_squared_to(p.pos)
		if bd > 400.0 or best["dead"]:
			p.t = rng.randf_range(15.0, 40.0)
			return
		p.hv = Vector2(-sin(p.yaw), -cos(p.yaw))
		_switch_path(p, best, bs, 1 if rng.randf() < 0.5 else -1)
		p.off = p.pos - (_sp_for(p))
	p.state = WALK
	p.off_t = Vector2.ZERO
	p.face = NAN
	p.stand_anim = "Idle"
	p.hot_kind = -1


func _sp_for(p: Ped) -> Vector2:
	_sample(p.path, p.s)
	var d := _st * float(p.dir)
	return _sp + Vector2(-d.y, d.x) * p.lat


## Begleitung: geht rechts neben der führenden Person her
func _follow(p: Ped, dt: float) -> void:
	var L := p.lead
	if L.dead:
		p.lead = null
		return
	var right := Vector2(-L.hv.y, L.hv.x)
	var tgt := L.pos + right * PAIR_GAP
	var d := tgt - p.pos
	var l := d.length()
	if l > 3.0:
		p.pos = tgt
	elif l > 0.01:
		p.pos += d * minf(1.0, (1.0 - exp(-7.0 * dt)))
	p.v = move_toward(p.v, L.v, 3.0 * dt)
	p.hv = L.hv
	p.state = L.state
	p.on_road = L.on_road
	p.path = L.path
	p.face = L.face
	if L.state == STAND or L.wait:
		p.stand_anim = L.stand_anim if L.stand_anim != "Phone" else "Idle"
	if L.state == DODGE:
		p.stand_anim = "Look"
	p.think_t -= dt
	if p.think_t <= 0.0:
		p.think_t = 0.5
		var sh := p.d2 < 3600.0
		if sh != p.shadow and p.mesh != null:
			p.shadow = sh
			p.mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if sh else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF


func _apply(p: Ped, dt: float) -> void:
	var want := p.yaw
	if p.v > 0.12:
		want = atan2(-p.hv.x, -p.hv.y)
	elif not is_nan(p.face):
		want = p.face
	elif p.wait:
		want = atan2(-p.hv.x, -p.hv.y)
	var moved := p.v > 0.01 or absf(angle_difference(p.yaw, want)) > 0.01 or p.state == DODGE or p.lead != null
	if moved:
		p.yaw = lerp_angle(p.yaw, want, 1.0 - exp(-(7.0 if p.v > 0.12 else 4.0) * dt))
		var y := world.height_at(p.pos.x, p.pos.y)
		p.node.transform = Transform3D(Basis(Vector3.UP, p.yaw).scaled(Vector3(p.hs, p.hs, p.hs)), Vector3(p.pos.x, y, p.pos.y))
	if p.anim == null:
		return
	var nm := p.stand_anim
	var sp := 1.0
	if p.v > 0.12:
		if p.v > 2.3:
			nm = "Run"
			sp = p.v / p.run_v
		else:
			nm = "Walk"
			sp = p.v / p.walk_v
	if nm != p.cur:
		if p.anim.has_animation(nm):
			p.anim.play(nm, 0.25)
		p.cur = nm
	if absf(sp - p.cur_sp) > 0.02:
		p.cur_sp = sp
		p.anim.speed_scale = sp
	p.anim.advance(dt)


# --- Entstehen und Vergehen ----------------------------------------------------------------------
func _pick_kind(alone: bool) -> String:
	var hours := 15.0
	var em = _main.get("env_mgr") if _main else null
	if em != null:
		hours = float(em.hours)
	var dayt := hours >= 7.0 and hours < 20.0
	var r := rng.randf()
	var kid := (0.04 if alone else 0.10) if dayt else 0.0
	var old := 0.20 if dayt else 0.06
	if r < kid and by_kind.has("k"):
		return "k"
	if r < kid + old and by_kind.has("a"):
		return "a"
	return "f" if (rng.randf() < 0.5 and by_kind.has("f")) or not by_kind.has("m") else "m"


func _make(kind: String) -> Ped:
	var p := Ped.new()
	p.kind = kind
	p.fo = rng.randi() % 4
	p.think_t = rng.randf() * 0.25
	if not _has_models:
		var mi := MeshInstance3D.new()
		var cm := CapsuleMesh.new()
		cm.radius = 0.25
		cm.height = 1.75
		mi.mesh = cm
		mi.position.y = 0.88
		p.node = Node3D.new()
		p.node.add_child(mi)
		RenderUtil.gi_off(p.node)
		add_child(p.node)
	else:
		var list: Array = by_kind.get(kind, [])
		if list.is_empty():
			list = range(models.size())
		p.mi = list[rng.randi() % list.size()]
		var m: Dictionary = models[p.mi]
		var pool: Array = _pool.get(p.mi, [])
		if not pool.is_empty():
			p.node = pool.pop_back()
			p.node.visible = true
		else:
			p.node = (m["scene"] as PackedScene).instantiate() as Node3D
			RenderUtil.gi_off(p.node)
			add_child(p.node)
		p.anim = p.node.find_child("AnimationPlayer", true, false) as AnimationPlayer
		if p.anim:
			p.anim.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		var stack: Array = [p.node]
		while not stack.is_empty():
			var x: Node = stack.pop_back()
			if x is MeshInstance3D:
				p.mesh = x
				break
			for c in x.get_children():
				stack.append(c)
		p.hs = rng.randf_range(0.955, 1.045)
		p.walk_v = float(m["walk"]) * p.hs / float(m["walk_T"])
		p.run_v = float(m["run"]) * p.hs / float(m["run_T"])
		_dress(p)
		if p.mesh:
			p.mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	# Gehgeschwindigkeit: Erwachsene um 1,34 m/s, Kinder und Ältere langsamer, etwa jeder Achte eilig
	match kind:
		"k":
			p.v0 = clampf(rng.randfn(1.10, 0.15), 0.8, 1.45)
		"a":
			p.v0 = clampf(rng.randfn(0.92, 0.12), 0.65, 1.15)
		_:
			p.v0 = clampf(rng.randfn(1.34, 0.17), 0.95, 1.75)
			if rng.randf() < 0.12:
				p.hurry = true
				p.v0 = rng.randf_range(1.7, 2.05)
	p.lat0 = rng.randf_range(-0.1, 0.65)
	p.lat = p.lat0
	p.lat_t = p.lat0
	p.shop_t = rng.randf_range(3.0, 30.0)
	p.phone_t = rng.randf_range(30.0, 400.0)
	peds.append(p)
	return p


func _lin(c: Color) -> Vector3:
	var l := c.srgb_to_linear()
	return Vector3(l.r, l.g, l.b)


func _pick(pal: Array) -> Color:
	return pal[rng.randi() % pal.size()]


## Haut, Haar und Kleidung auswürfeln (Instanz-Uniforms: ein gemeinsames Material für alle Figuren)
func _dress(p: Ped) -> void:
	var mi := p.mesh
	if mi == null:
		return
	if mi.get_surface_override_material(0) != material():
		mi.set_surface_override_material(0, material())
	var name: String = MODELS[p.mi][0] if p.mi < MODELS.size() else ""
	var top := _pick(TOP)
	var bottom := _pick(BOTTOM)
	if name in ["ped_frau2", "ped_kind2", "ped_seniorin"]:
		bottom = _pick(SKIRT)
	if name == "ped_frau4" and rng.randf() < 0.6:
		top = [Color(0.62, 0.20, 0.22), Color(0.20, 0.30, 0.46), Color(0.80, 0.72, 0.52), Color(0.25, 0.42, 0.34), Color(0.10, 0.10, 0.12),
				Color(0.78, 0.50, 0.42)][rng.randi() % 6]
	if p.kind == "k" and rng.randf() < 0.6:
		top = [Color(0.72, 0.18, 0.16), Color(0.16, 0.38, 0.66), Color(0.86, 0.68, 0.14), Color(0.22, 0.52, 0.32), Color(0.80, 0.36, 0.52),
				Color(0.36, 0.62, 0.74)][rng.randi() % 6]
	var hair := _pick(HAIR_OLD) if p.kind == "a" else _pick(HAIR)
	if p.kind == "m" and rng.randf() < 0.12:
		hair = _pick(HAIR_OLD)
	var top2 := _pick(TIGHTS) if name in ["ped_frau2", "ped_seniorin"] else _pick(TOP2)
	var acc := _pick(ACC)
	if (acc.r - top.r) * (acc.r - top.r) + (acc.g - top.g) * (acc.g - top.g) + (acc.b - top.b) * (acc.b - top.b) < 0.006:
		acc = _pick(ACC)
	mi.set_instance_shader_parameter("c_skin", _lin(_pick(SKIN)))
	mi.set_instance_shader_parameter("c_hair", _lin(hair))
	mi.set_instance_shader_parameter("c_top", _lin(top))
	mi.set_instance_shader_parameter("c_bottom", _lin(bottom))
	mi.set_instance_shader_parameter("c_shoes", _lin(_pick(SHOES)))
	mi.set_instance_shader_parameter("c_acc", _lin(acc))
	mi.set_instance_shader_parameter("c_top2", _lin(top2))


func _place(p: Ped) -> void:
	p.node.transform = Transform3D(Basis(Vector3.UP, p.yaw).scaled(Vector3(p.hs, p.hs, p.hs)),
			Vector3(p.pos.x, world.height_at(p.pos.x, p.pos.y), p.pos.y))
	p.cur = ""
	p.cur_sp = -1.0
	if p.anim:
		var nm := "Walk" if p.state == WALK else p.stand_anim
		if p.anim.has_animation(nm):
			p.anim.play(nm)
			p.anim.seek(rng.randf() * p.anim.get_animation(nm).length, true)
			p.cur = nm


func _try_spawn() -> void:
	if not hots.is_empty() and rng.randf() < 0.2 and _try_spawn_standing():
		return
	if cells.is_empty():
		return
	for attempt in 10:
		var ang := rng.randf() * TAU
		var rad := lerpf(15.0, 125.0, pow(rng.randf(), 1.3))       # zur Mitte hin etwas dichter
		var q := Vector2(focus.x + cos(ang) * rad, focus.z + sin(ang) * rad)
		var arr: Array = cells.get(Vector2i(floori(q.x / CELL), floori(q.y / CELL)), [])
		if arr.is_empty():
			continue
		var path: Dictionary = arr[rng.randi_range(0, arr.size() - 1)]
		if int(path["bad"]) >= 2:
			continue
		var s := rng.randf_range(0.0, float(path["len"]))
		_sample(path, s)
		var pos2 := _sp
		var d2 := Vector2(pos2.x - focus.x, pos2.y - focus.z).length_squared()
		if d2 < 196.0 or d2 > 150.0 * 150.0:
			continue
		if _warm <= 0.0 and _in_view(pos2, 55.0):
			continue                                        # nicht vor den Augen des Spielers erscheinen
		if not _road_hit(pos2).is_empty():
			path["bad"] = int(path["bad"]) + 1
			continue
		var alone := rng.randf() > 0.22
		var kind := _pick_kind(alone)
		if kind == "k" and rng.randf() < 0.75:
			alone = false
		var lead_kind := kind
		if not alone and kind == "k":
			lead_kind = "f" if rng.randf() < 0.6 else "m"   # Kinder meist in Begleitung
		_ensure(path)
		var p := _make(lead_kind)
		p.path = path
		p.s = s
		p.dir = 1 if rng.randf() < 0.5 else -1
		p.state = WALK
		p.v = p.v0
		_sample(path, s)
		var d := _st * float(p.dir)
		p.hv = d
		p.yaw = atan2(-d.x, -d.y)
		if not alone and peds.size() < MAX_PEDS:
			p.lat0 = rng.randf_range(-0.3, 0.1)
			p.lat = p.lat0
			p.lat_t = p.lat0
			p.hurry = false
			var m := _make(kind if kind == "k" else _pick_kind(false))
			m.lead = p
			p.mate = m
			p.v0 = minf(minf(p.v0, m.v0 * 1.08), 1.45)
			p.v = p.v0
			m.v = p.v0
			m.state = WALK
			m.yaw = p.yaw
			m.pos = pos2 + Vector2(-d.y, d.x) * (p.lat + PAIR_GAP)
			_place(m)
		p.pos = pos2 + Vector2(-d.y, d.x) * p.lat
		_place(p)
		return


func _try_spawn_standing() -> bool:
	## Stehende Menschen an Läden, Cafés, Haltestellen (einzeln oder in kleinen Gruppen)
	for attempt in 8:
		var ang := rng.randf() * TAU
		var rad := rng.randf_range(12.0, 115.0)
		var q := Vector2(focus.x + cos(ang) * rad, focus.z + sin(ang) * rad)
		var arr: Array = hots.get(Vector2i(floori(q.x / CELL), floori(q.y / CELL)), [])
		if arr.is_empty():
			continue
		var h: Dictionary = arr[rng.randi_range(0, arr.size() - 1)]
		var base: Vector2 = h["p"]
		var bd := Vector2(base.x - focus.x, base.y - focus.z).length_squared()
		if bd < 100.0 or bd > 150.0 * 150.0:
			continue
		if _warm <= 0.0 and _in_view(base, 55.0):
			continue
		if not _road_hit(base).is_empty():
			continue
		# schon besetzt?
		var taken := false
		for q0 in _pgrid.get(Vector2i(floori(base.x / PCELL), floori(base.y / PCELL)), []):
			if ((q0 as Ped).pos).distance_squared_to(base) < 2.5:
				taken = true
				break
		if taken:
			continue
		var k: int = h["k"]
		var n := 1
		if rng.randf() < (0.6 if k == 1 else 0.4):
			n = 2 + rng.randi() % 2
		var yaw0: float = h["yaw"]
		var stay := rng.randf_range(40.0, 150.0) if k == 1 else rng.randf_range(12.0, 60.0)
		for i in n:
			if peds.size() >= MAX_PEDS:
				break
			var off := Vector2(cos(float(i) * 2.1 + yaw0), sin(float(i) * 2.1 + yaw0)) * (0.0 if i == 0 else 0.8)
			var spot := base + off
			if k == 1:
				spot = base + Vector2(cos(yaw0), -sin(yaw0)) * (float(i) * 0.9 - 0.4 * float(n - 1)) + Vector2(rng.randf_range(-0.2, 0.2), rng.randf_range(-0.2, 0.2))
			# nicht in Bank, Mülleimer, Mast oder Baum stellen: ein Stück weiterrücken, sonst weglassen
			var tries := 0
			while _obst_hit(spot, 0.3) and tries < 5:
				tries += 1
				spot += Vector2(cos(float(tries) * 2.4 + yaw0), sin(float(tries) * 2.4 + yaw0)) * 0.55
			if tries >= 5 or not _road_hit(spot).is_empty():
				continue
			var p := _make(_pick_kind(n == 1))
			p.pos = spot
			p.yaw = yaw0
			p.state = STAND
			p.hot_kind = k
			p.t = stay + rng.randf_range(0.0, 2.5) * float(i)
			if n > 1 and k != 1:
				var c := base + Vector2(0.27, 0.27)
				p.yaw = atan2(-(c.x - p.pos.x), -(c.y - p.pos.y))      # einander zugewandt
				p.stand_anim = "Talk" if rng.randf() < 0.7 else "Idle"
			else:
				var r := rng.randf()
				p.stand_anim = "Phone" if r < (0.4 if k == 1 else 0.25) and p.kind != "k" else ("Look" if r > 0.9 else "Idle")
				if k == 1:
					p.yaw = yaw0 + rng.randf_range(-0.5, 0.5)
			p.face = p.yaw
			p.hv = Vector2(-sin(p.yaw), -cos(p.yaw))
			_place(p)
		return true
	return false


## Entwickler: alle Figuren nebeneinander vor die Kamera stellen
func _make_parade() -> void:
	var cam := get_viewport().get_camera_3d()
	if cam == null:
		return
	var fw3 := -cam.global_transform.basis.z
	var fw := Vector2(fw3.x, fw3.z).normalized()
	var right := Vector2(-fw.y, fw.x)
	var c := Vector2(cam.global_position.x, cam.global_position.z) + fw * 6.5
	var anims := ["Idle", "Walk", "Talk", "Phone", "Look", "Walk", "Idle", "Run"]
	for i in models.size():
		var p := _make(String(models[i]["kind"]))
		if p.mi != i:
			# gewünschtes Modell erzwingen
			p.node.queue_free()
			p.mi = i
			p.node = (models[i]["scene"] as PackedScene).instantiate() as Node3D
			RenderUtil.gi_off(p.node)
			add_child(p.node)
			p.anim = p.node.find_child("AnimationPlayer", true, false) as AnimationPlayer
			p.anim.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
			p.mesh = null
			for x in p.node.find_children("*", "MeshInstance3D", true, false):
				p.mesh = x
				break
			_dress(p)
		p.hs = 1.0
		var row := i / 8
		p.pos = c + right * ((i % 8) - 3.5) * 0.95 + fw * (row * 2.2)
		p.yaw = atan2(fw.x, fw.y) + (0.5 if i % 3 == 1 else (-0.4 if i % 3 == 2 else 0.0))
		p.face = p.yaw
		p.state = STAND
		p.t = 1e9
		p.stand_anim = anims[i % anims.size()]
		p.hv = Vector2(-sin(p.yaw), -cos(p.yaw))
		_place(p)


func _free_ped(i: int) -> void:
	var p: Ped = peds[i]
	p.dead = true
	if p.mate != null:
		# Begleitung geht allein weiter
		var m := p.mate
		m.lead = null
		m.path = p.path
		m.s = p.s
		m.dir = p.dir
		m.lat = clampf(p.lat + PAIR_GAP, -1.0, 1.0)
		m.lat_t = m.lat
		m.lat0 = m.lat
		m.off = Vector2.ZERO
		m.off_t = Vector2.ZERO
		if m.path.is_empty():
			m.state = STAND
			m.t = 10.0
		p.mate = null
	if p.lead != null:
		p.lead.mate = null
		p.lead = null
	if _has_models and p.anim != null:
		p.node.visible = false
		if not _pool.has(p.mi):
			_pool[p.mi] = []
		if (_pool[p.mi] as Array).size() < 12:
			(_pool[p.mi] as Array).append(p.node)
		else:
			p.node.queue_free()
	else:
		p.node.queue_free()
	peds.remove_at(i)
