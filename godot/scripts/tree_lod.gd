class_name TreeLOD
extends Node3D
## Baum-Detailstufen pro Baum: nahe Bäume (< NEAR m) als volles Modell, alle anderen als einfache Krone.
## Die Fernkronen liegen als MultiMesh je Kachelzelle in Dressing; hier wird pro Baum zwischen beiden getauscht.
##
## Nahe Bäume liegen in MultiMeshes je 40-m-Zelle und Art (früher ein riesiges MultiMesh je Art rund um die
## Kamera): so greifen Sichtkegel-Culling (auch in den Schattenkaskaden) und Godots automatische Mesh-LODs aus
## dem Import – ein Baum in 120 m Entfernung wird mit wenigen hundert statt 15 000 Dreiecken gezeichnet.
## Der Knoten läuft ohne Physik-Interpolation (sonst gleiten umgesetzte Instanzen einen Physikschritt lang).

var NEAR := 150.0
var NEAR_OUT := 170.0
const MAXN := 1600              # je Art
const CELL := 40.0

var tiles := {}                 # Dressing -> true
var focus := Vector3.ZERO
var _parts: Array = []          # je Art: Array[{mesh, xf}]
var _timer := 0.0
var _last_focus := Vector3(1e9, 0, 1e9)
var _dirty := false
var _cells := {}                # Vector3i(cx, cz, Art) -> {"trees": {key: [Dressing, e]}, "insts": Array}
var _cell_of := {}              # key -> Vector3i
var _dirty_cells := {}


func setup() -> void:
	var d := Dressing.new()
	for nm in Dressing.SPECIES:
		_parts.append(d._parts(nm))
	d.free()


func register(d: Dressing) -> void:
	if d.tree_data.is_empty():
		return
	tiles[d] = true
	_dirty = true


func unregister(d: Dressing) -> void:
	if tiles.has(d):
		var near: Dictionary = d.tree_data.get("near", {})
		for e in near:
			_cell_remove(_key(d, e))
		near.clear()
		tiles.erase(d)
		_rebuild_dirty()
	_dirty = true


func _key(d: Dressing, e: int) -> int:
	return d.get_instance_id() * 32768 + e


func set_quality(q: int) -> void:
	var n: float = [70.0, 110.0, 150.0][clampi(q, 0, 2)]
	if n != NEAR:
		NEAR = n
		NEAR_OUT = n + 20.0
		_dirty = true


func _process(delta: float) -> void:
	_timer -= delta
	if _timer > 0.0:
		return
	_timer = 0.25
	if focus.distance_to(_last_focus) < 2.0 and not _dirty:
		return
	_last_focus = focus
	_dirty = false
	_refresh()


func _cell_add(d: Dressing, e: int, p: Vector3, si: int) -> void:
	var ck := Vector3i(floori(p.x / CELL), floori(p.z / CELL), si)
	var k := _key(d, e)
	if not _cells.has(ck):
		_cells[ck] = {"trees": {}, "insts": []}
	(_cells[ck]["trees"] as Dictionary)[k] = [d, e]
	_cell_of[k] = ck
	_dirty_cells[ck] = true


func _cell_remove(k: int) -> void:
	if not _cell_of.has(k):
		return
	var ck: Vector3i = _cell_of[k]
	_cell_of.erase(k)
	if _cells.has(ck):
		(_cells[ck]["trees"] as Dictionary).erase(k)
		_dirty_cells[ck] = true


func _rebuild_dirty() -> void:
	for ck in _dirty_cells:
		_rebuild(ck)
	_dirty_cells.clear()


func _rebuild(ck: Vector3i) -> void:
	if not _cells.has(ck):
		return
	var c: Dictionary = _cells[ck]
	var trees: Dictionary = c["trees"]
	var insts: Array = c["insts"]
	var xfs: Array = []
	for k in trees:
		var de: Array = trees[k]
		if is_instance_valid(de[0]):
			xfs.append(((de[0] as Dressing).tree_data["xf"] as Array)[int(de[1])])
	if xfs.is_empty():
		for inst in insts:
			(inst as Node).queue_free()
		_cells.erase(ck)
		return
	var parts: Array = _parts[ck.z]
	if insts.is_empty():
		for part in parts:
			var inst := MultiMeshInstance3D.new()
			inst.gi_mode = GeometryInstance3D.GI_MODE_DISABLED   # Laub nicht in SDFGI rastern
			add_child(inst)
			insts.append(inst)
	for pi in parts.size():
		# neues MultiMesh statt Umbelegen: keine falschen Bewegungsvektoren (TAA/FSR2) für umgesetzte Indizes
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = parts[pi]["mesh"]
		RenderUtil.fill_multimesh(mm, xfs, parts[pi]["xf"])
		(insts[pi] as MultiMeshInstance3D).multimesh = mm


func _refresh() -> void:
	var fx := focus.x
	var fz := focus.z
	var r_cells := ceili(NEAR_OUT / 32.0) + 1
	var cx := floori(fx / 32.0)
	var cz := floori(fz / 32.0)
	# 1) Kandidaten aus allen Kacheln sammeln (mit Hysterese NEAR/NEAR_OUT)
	var cand: Array = []           # [dist, tile, entry, species]
	for d in tiles.keys():
		if not is_instance_valid(d):
			tiles.erase(d)
			continue
		var td: Dictionary = d.tree_data
		var pos: PackedVector3Array = td["pos"]
		var near: Dictionary = td["near"]
		var grid: Dictionary = td["grid"]
		var sp: Array = td["sp"]
		for ix in range(cx - r_cells, cx + r_cells + 1):
			for iz in range(cz - r_cells, cz + r_cells + 1):
				var arr = grid.get(Vector2i(ix, iz))
				if arr == null:
					continue
				for e in arr:
					var p: Vector3 = pos[e]
					var dd := Vector2(p.x - fx, p.z - fz).length()
					if dd < NEAR or (dd < NEAR_OUT and near.has(e)):
						cand.append([dd, d, e, int(sp[e])])
	# 2) die nächsten zuerst: je Art höchstens MAXN volle Modelle, der Rest bleibt Fernkrone
	cand.sort_custom(func(x, y): return x[0] < y[0])
	var per_sp: Array = []
	per_sp.resize(_parts.size())
	per_sp.fill(0)
	var want := {}                 # tile -> {entry: true}
	for c in cand:
		var si: int = c[3]
		if si < 0 or si >= _parts.size() or per_sp[si] >= MAXN:
			continue
		per_sp[si] += 1
		var d2: Dressing = c[1]
		if not want.has(d2):
			want[d2] = {}
		want[d2][c[2]] = true
	# 3) erst freigeben (Fernkrone zurück), dann neu vergeben (Fernkrone aus)
	for d in tiles.keys():
		var td: Dictionary = d.tree_data
		var near: Dictionary = td["near"]
		var w: Dictionary = want.get(d, {})
		for e in near.keys():
			if w.has(e):
				continue
			_cell_remove(_key(d, e))
			var mm2: MultiMesh = td["mm"][e]
			mm2.set_instance_transform(td["mi"][e], td["xf_far"][e])
			near.erase(e)
	for d in want:
		var td: Dictionary = d.tree_data
		var near: Dictionary = td["near"]
		var pos: PackedVector3Array = td["pos"]
		for e in want[d]:
			if near.has(e):
				continue
			var si: int = td["sp"][e]
			_cell_add(d, e, pos[e], si)
			var mm: MultiMesh = td["mm"][e]
			mm.set_instance_transform(td["mi"][e], Transform3D(Basis().scaled(Vector3.ZERO), pos[e]))
			near[e] = true
	_rebuild_dirty()
