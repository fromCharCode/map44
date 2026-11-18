class_name PhotoFacades
extends Node3D
## Echte Hausfassaden als Fototextur vor der Wand (tools/mly_photofacade.py: je Kachel facades.json + facades/*.dds,
## entzerrt aus Mapillary-Rundumbildern, CC BY-SA 4.0). Nah am Haus sieht man das Foto, in der Ferne die
## berechnete Fassade in der Farbe des Fotos.

const RANGE := 320.0

static var _segs := {}            # Kachel -> Array[[a: Vector2, b: Vector2]]
static var _mutex := Mutex.new()

var _key := ""


static func load_list(k: String, dir: String) -> Array:
	## Liste lesen und die Wandstrecken merken (vor dem Gebäudebau, damit dort keine Balkone davor gesetzt werden)
	var f := dir + "facades.json"
	var list: Array = []
	if FileAccess.file_exists(f):
		var j = JSON.parse_string(FileAccess.get_file_as_string(f))
		if j is Array:
			list = j
	var segs: Array = []
	for e in list:
		segs.append([Vector2(e["a"][0], e["a"][1]), Vector2(e["b"][0], e["b"][1])])
	_mutex.lock()
	_segs[k] = segs
	_mutex.unlock()
	return list


static func covers(k: String, p: Vector2) -> bool:
	## Liegt der Punkt (Mitte einer Fassadenkante) an einer Fotofassade dieser Kachel?
	_mutex.lock()
	var segs: Array = _segs.get(k, [])
	_mutex.unlock()
	for s in segs:
		if Geometry2D.get_closest_point_to_segment(p, s[0], s[1]).distance_to(p) < 0.7:
			return true
	return false


var _pending: Array = []        # [Image, a, b, n3, y0, h] – Textur und Mesh entstehen erst im Haupt-Thread


func build(terrain: Terrain, k: String, dir: String, list: Array) -> void:
	## Läuft im Kachel-Thread: nur Dateien lesen und Maße bestimmen. Texturen und Meshes im Thread anzulegen ließ das
	## Spiel sporadisch abstürzen – sie entstehen deshalb in _process (Haupt-Thread), wenige je Bild.
	_key = k
	for e in list:
		var path: String = dir + "facades/" + String(e["tex"])
		if not FileAccess.file_exists(path):
			continue
		var bytes := FileAccess.get_file_as_bytes(path)
		if bytes.is_empty():
			continue
		var a := Vector2(e["a"][0], e["a"][1])
		var b := Vector2(e["b"][0], e["b"][1])
		var dir2 := (b - a).normalized()
		var n3 := Vector3(dir2.x, 0.0, dir2.y).cross(Vector3.UP).normalized()      # zum Betrachter
		var y0 := INF
		for t in [0.0, 0.5, 1.0]:
			var q := a.lerp(b, t)
			y0 = minf(y0, terrain.height_at(q.x + n3.x * 0.8, q.y + n3.z * 0.8))
		_pending.append([bytes, a, b, n3, y0 - 0.1, float(e["h"]) + 0.1])
	set_process(not _pending.is_empty())


func _ready() -> void:
	set_process(not _pending.is_empty())


func _process(_delta: float) -> void:
	for _i in 3:
		if _pending.is_empty():
			set_process(false)
			return
		_make(_pending.pop_back())


func _make(p: Array) -> void:
	if DisplayServer.get_name() == "headless":
		return                       # ohne Grafikausgabe (Prüfläufe) keine Texturen: komprimierte Bilder ließen den Lauf abstürzen
	var img := Image.new()
	if img.load_dds_from_buffer(p[0]) != OK:
		return
	var a: Vector2 = p[1]
	var b: Vector2 = p[2]
	var n3: Vector3 = p[3]
	var y0: float = p[4]
	var h: float = p[5]
	var off := n3 * 0.07
	var v0 := Vector3(a.x, y0, a.y) + off
	var v1 := Vector3(b.x, y0, b.y) + off
	var vs := PackedVector3Array([v0, v1 + Vector3(0, h, 0), v1, v0, v0 + Vector3(0, h, 0), v1 + Vector3(0, h, 0)])
	var uvs := PackedVector2Array([Vector2(0, 1), Vector2(1, 0), Vector2(1, 1), Vector2(0, 1), Vector2(0, 0), Vector2(1, 0)])
	var ns := PackedVector3Array([n3, n3, n3, n3, n3, n3])
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = vs
	arr[Mesh.ARRAY_NORMAL] = ns
	arr[Mesh.ARRAY_TEX_UV] = uvs
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	var m := StandardMaterial3D.new()
	m.albedo_texture = ImageTexture.create_from_image(img)
	m.roughness = 0.88
	m.specular = 0.25
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = m
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mi.visibility_range_end = RANGE
	mi.visibility_range_end_margin = 30.0
	mi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
	add_child(mi)


func _exit_tree() -> void:
	if is_queued_for_deletion():
		_mutex.lock()
		_segs.erase(_key)
		_mutex.unlock()
