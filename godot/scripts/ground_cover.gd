class_name GroundCover
extends Node3D
## Bodenbewuchs um die Kamera: Unterholz im Wald (Farn, Büsche, Jungbäume, Totholz, Steine, Heidekraut),
## Gras auf Wiesen. Zellen à 16 m im Umkreis RADIUS um den Fokus, deterministisch je Zelle (gleiche Pflanzen
## an gleicher Stelle beim Wiederkommen), mitwandernd. Grundlage: Terrain.cover (R Wiese, G Wald, B frei).

const CELL := 16.0
const RADIUS := 96.0
const BUILD_PER_FRAME := 6
# Modell -> [Sichtweite, Schatten]
const MODELS := {
	"fern": [75.0, false], "bush_a": [120.0, false], "bush_b": [100.0, false], "bush_young_tree": [130.0, false],
	"deadwood": [70.0, false], "stump": [60.0, false], "rock_small": [80.0, false], "grass_tuft": [42.0, false],
	"grass_tall": [55.0, false], "heather": [50.0, false],
}
# Wald: (Modell, Gewicht je Kandidat) ; Wiese: dto.
const FOREST_MIX := [["fern", 0.22], ["heather", 0.16], ["grass_tall", 0.12], ["bush_b", 0.07], ["bush_a", 0.05],
	["bush_young_tree", 0.025], ["deadwood", 0.03], ["stump", 0.012], ["rock_small", 0.006]]
const MEADOW_MIX := [["grass_tuft", 0.55], ["grass_tall", 0.06], ["bush_b", 0.006]]
const CANDIDATES := 70

var terrains: Array = []          # Terrain-Knoten der geladenen Kacheln
var focus := Vector3.ZERO
var enabled := true
var _cells := {}                  # Vector2i -> Node3D
var _queue: Array = []
var _timer := 0.0


func add_terrain(t: Terrain) -> void:
	if t != null and t.cover != null and not terrains.has(t):
		terrains.append(t)


func remove_terrain(t: Terrain) -> void:
	terrains.erase(t)
	# Zellen dieser Kachel entfernen (werden bei Bedarf mit der neuen Kachel neu gebaut)
	for k in _cells.keys():
		var c := Vector2(k.x * CELL + CELL * 0.5, k.y * CELL + CELL * 0.5)
		if t.contains(c.x, c.y):
			(_cells[k] as Node).queue_free()
			_cells.erase(k)


func _terrain_at(x: float, z: float) -> Terrain:
	for t in terrains:
		if is_instance_valid(t) and (t as Terrain).contains(x, z):
			return t
	return null


func _process(delta: float) -> void:
	if not enabled or terrains.is_empty():
		return
	_timer -= delta
	if _timer <= 0.0:
		_timer = 0.25
		_update_set()
	var n := 0
	while n < BUILD_PER_FRAME and not _queue.is_empty():
		var k: Vector2i = _queue.pop_front()
		if not _cells.has(k):
			_build_cell(k)
		n += 1


func _update_set() -> void:
	var cx := floori(focus.x / CELL)
	var cz := floori(focus.z / CELL)
	var r := int(ceil(RADIUS / CELL))
	var want := {}
	for ix in range(cx - r, cx + r + 1):
		for iz in range(cz - r, cz + r + 1):
			var c := Vector2(ix * CELL + CELL * 0.5, iz * CELL + CELL * 0.5)
			var d := c.distance_to(Vector2(focus.x, focus.z))
			if d < RADIUS:
				want[Vector2i(ix, iz)] = d
	for k in _cells.keys():
		if not want.has(k):
			var c2 := Vector2(k.x * CELL + CELL * 0.5, k.y * CELL + CELL * 0.5)
			if c2.distance_to(Vector2(focus.x, focus.z)) > RADIUS + CELL * 1.5:
				(_cells[k] as Node).queue_free()
				_cells.erase(k)
	var missing: Array = []
	for k in want:
		if not _cells.has(k) and not _queue.has(k):
			missing.append([want[k], k])
	missing.sort_custom(func(a, b): return a[0] < b[0])
	for m in missing:
		_queue.append(m[1])


func _hash(ix: int, iz: int, i: int) -> int:
	var h := ix * 73856093 ^ iz * 19349663 ^ i * 83492791
	h = (h ^ (h >> 13)) * 1274126177
	return h ^ (h >> 16)


var built := 0
var placed := 0


func _build_cell(k: Vector2i) -> void:
	built += 1
	var node := Node3D.new()
	node.name = "GC_%d_%d" % [k.x, k.y]
	add_child(node)
	_cells[k] = node
	var x0 := k.x * CELL
	var z0 := k.y * CELL
	var t := _terrain_at(x0 + CELL * 0.5, z0 + CELL * 0.5)
	if t == null:
		return
	var rng := RandomNumberGenerator.new()
	rng.seed = _hash(k.x, k.y, 1)
	var groups := {}
	for i in CANDIDATES:
		var x := x0 + rng.randf() * CELL
		var z := z0 + rng.randf() * CELL
		var r := rng.randf()
		var c := t.cover_at(x, z)
		if c.b < 0.5:
			continue
		var mix: Array = []
		if c.g > 0.45:
			mix = FOREST_MIX
		elif c.r > 0.5:
			mix = MEADOW_MIX
		else:
			continue
		var acc := 0.0
		var pick := ""
		for m in mix:
			acc += float(m[1])
			if r < acc:
				pick = m[0]
				break
		if pick == "" or StreetLife.parts(pick).is_empty():
			continue
		var y := t.height_at(x, z)
		var s := rng.randf_range(0.7, 1.35)
		var xf := Transform3D(Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3(s, s * rng.randf_range(0.85, 1.15), s)), Vector3(x, y - 0.03, z))
		if not groups.has(pick):
			groups[pick] = []
		groups[pick].append(xf)
		placed += 1
	for model in groups:
		var list: Array = groups[model]
		var cfg: Array = MODELS[model]
		for part in StreetLife.parts(model):
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			mm.mesh = part["mesh"]
			RenderUtil.fill_multimesh(mm, list, part["xf"])
			var inst := MultiMeshInstance3D.new()
			inst.multimesh = mm
			inst.visibility_range_end = float(cfg[0])
			inst.visibility_range_end_margin = float(cfg[0]) * 0.15
			inst.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
			if not bool(cfg[1]):
				inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			inst.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
			node.add_child(inst)
