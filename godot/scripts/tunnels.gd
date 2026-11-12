class_name Tunnels
extends Node3D
## Befahrbare Straßentunnel einer Kachel (Pipeline tools/tunnels.py -> city["tunnels"]).
##
## Je Tunnelkette: Fahrbahnplatte mit Randlinien, Röhre (Innenwände, Decke, Lichtband), an flach überdeckten
## Abschnitten ("box") ein Betonkasten mit Außenwänden und Decke, an den Portalen die Portalwand um die Öffnung.
## Das sichtbare Gelände bleibt unverändert; der Gelände-Shader blendet es im Lichtraum der Röhre aus
## (mask_image -> Terrain.set_tunnel_mask). Das Kollisionsraster ist im Tunnelband abgesenkt (Pipeline); über der
## Röhre liegt hier ein Kollisionsdeckel in Geländehöhe, damit man oben auf dem Hang nicht einbricht.
## Tunnels.inside(p) sagt dem Hauptprogramm, dass der Spieler im Tunnel ist (sonst "unter dem Gelände" -> Rücksetzen).

const CLEAR := 4.8
const ROOF := 0.6
const WALL := 1.2
const SLAB := 0.5

static var _registry := {}          # instance_id -> Array [[Vector2 a, Vector2 b, float hw, float ya, float yb]]
static var _grid := {}              # Vector2i (32-m-Zelle) -> Array derselben Einträge (für inside() je Bild)
static var _mats := {}
const CELL := 32.0

var terrain: Terrain
var _cor: Array = []
var _lights: Array = []              # Leuchtenpositionen (alle 24 m in der Röhre)
# Kollisionsflächen als Member: Packed*Arrays werden in GDScript als Wert übergeben (Anhängen an einen
# Parameter ginge an einer Kopie verloren)
var _faces := PackedVector3Array()
var _lid := PackedVector3Array()


static func inside(p: Vector3) -> bool:
	## Liegt p im Lichtraum einer geladenen Tunnelröhre? (Spieler-Rücksetzen, KI-Höhe)
	var cell: Array = _grid.get(Vector2i(floori(p.x / CELL), floori(p.z / CELL)), [])
	if cell.is_empty():
		return false
	var q := Vector2(p.x, p.z)
	for c in cell:
		var a: Vector2 = c[0]
		var b: Vector2 = c[1]
		var ab := b - a
		var l2 := ab.length_squared()
		if l2 < 1e-6:
			continue
		var t := clampf((q - a).dot(ab) / l2, 0.0, 1.0)
		if q.distance_to(a + ab * t) > float(c[2]):
			continue
		var y: float = lerpf(float(c[3]), float(c[4]), t)
		if p.y > y - 3.0 and p.y < y + CLEAR + 1.0:
			return true
	return false


static func _rebuild_grid() -> void:
	_grid.clear()
	for k in _registry:
		for c in _registry[k]:
			var a: Vector2 = c[0]
			var b: Vector2 = c[1]
			var r: float = float(c[2])
			for cx in range(floori((minf(a.x, b.x) - r) / CELL), floori((maxf(a.x, b.x) + r) / CELL) + 1):
				for cz in range(floori((minf(a.y, b.y) - r) / CELL), floori((maxf(a.y, b.y) + r) / CELL) + 1):
					var key := Vector2i(cx, cz)
					if not _grid.has(key):
						_grid[key] = []
					(_grid[key] as Array).append(c)


func _enter_tree() -> void:
	if not _cor.is_empty():
		_registry[get_instance_id()] = _cor
		_rebuild_grid()


func _exit_tree() -> void:
	if _registry.erase(get_instance_id()):
		_rebuild_grid()


static func _mat(key: String) -> Material:
	if _mats.has(key):
		return _mats[key]
	var m: Material
	match key:
		"road":
			m = TexLib.tri_material("asphalt_new", 1.4)     # wie Brückendecks (roads.gd deck_mat)
		"wall":
			var sm := TexLib.tri_material("concrete", 1.15).duplicate() as StandardMaterial3D
			sm.uv1_scale = Vector3(0.5, 0.5, 0.5)
			m = sm
		"outer":
			m = TexLib.tri_material("concrete", 0.95)
		"lamp":
			var lm := StandardMaterial3D.new()
			lm.albedo_color = Color(1.0, 0.92, 0.75)
			lm.emission_enabled = true
			lm.emission = Color(1.0, 0.88, 0.65)
			lm.emission_energy_multiplier = 3.0
			m = lm
		"line":
			var ln := StandardMaterial3D.new()
			ln.albedo_color = Color(0.85, 0.85, 0.82)
			ln.roughness = 0.6
			m = ln
	_mats[key] = m
	return m


func build(t: Terrain, data: Array, ctr: Vector2) -> void:
	terrain = t
	if data.is_empty():
		return
	var x0 := ctr.x - 1000.0
	var z0 := ctr.y - 1000.0
	for tn in data:
		_tunnel(tn, x0, z0)
	for lp in _lights:
		var ol := OmniLight3D.new()
		ol.position = lp
		ol.omni_range = 15.0
		ol.light_energy = 1.6
		ol.light_color = Color(1.0, 0.86, 0.62)
		ol.shadow_enabled = false
		ol.distance_fade_enabled = true
		ol.distance_fade_begin = 70.0
		ol.distance_fade_length = 20.0
		add_child(ol)
	var body := StaticBody3D.new()
	body.collision_layer = 1
	for fc in [_faces, _lid]:
		if (fc as PackedVector3Array).is_empty():
			continue
		var cs := CollisionShape3D.new()
		var sh := ConcavePolygonShape3D.new()
		sh.backface_collision = true
		sh.set_faces(fc)
		cs.shape = sh
		body.add_child(cs)
	add_child(body)


const KINDS := ["road", "wall", "outer", "lamp", "line"]
const CHUNK := 80                    # Stützpunkte je Mesh-Abschnitt (160 m): Culling + Sichtweite je Abschnitt


static func _new_st() -> Dictionary:
	var st := {}
	for k in KINDS:
		var s := SurfaceTool.new()
		s.begin(Mesh.PRIMITIVE_TRIANGLES)
		st[k] = s
	return st


func _flush_st(st: Dictionary) -> void:
	var mesh := ArrayMesh.new()
	for k in KINDS:
		var arr := (st[k] as SurfaceTool).commit_to_arrays()
		# leerer Abschnitt (z. B. Teil der Nachbarkachel): commit liefert ein leeres Array
		if arr.size() <= Mesh.ARRAY_VERTEX or not (arr[Mesh.ARRAY_VERTEX] is PackedVector3Array) \
				or (arr[Mesh.ARRAY_VERTEX] as PackedVector3Array).is_empty():
			continue
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
		mesh.surface_set_material(mesh.get_surface_count() - 1, _mat(k))
	if mesh.get_surface_count() == 0:
		return
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.visibility_range_end = 700.0
	# Decke/Wände sind einseitig: beidseitig Schatten werfen, sonst scheint die Sonne durch den Hang in die Röhre
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_DOUBLE_SIDED
	add_child(mi)


func _q(s: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, d: Vector3, n: Vector3, solid := false) -> void:
	## Viereck a-b-c-d (Vorderseite n); solid = auch Kollisionsfläche
	for v in [a, b, c, a, c, d]:
		s.set_normal(n)
		s.add_vertex(v)
	if solid:
		_faces.append_array(PackedVector3Array([a, b, c, a, c, d]))


func _tunnel(tn: Dictionary, x0: float, z0: float) -> void:
	var st := _new_st()
	var pts: Array = tn["pts"]
	var box: Array = tn["box"]
	var n := pts.size()
	if n < 2:
		return
	var hw := float(tn["w"]) * 0.5
	var ow := hw + WALL
	var P: Array = []
	var N: Array = []
	for i in n:
		P.append(Vector3(float(pts[i][0]), float(pts[i][2]), float(pts[i][1])))
	for i in n:
		var a: Vector3 = P[maxi(i - 1, 0)]
		var b: Vector3 = P[mini(i + 1, n - 1)]
		var tg := Vector3(b.x - a.x, 0, b.z - a.z).normalized()
		N.append(Vector3(-tg.z, 0, tg.x))          # links der Laufrichtung
	var up := Vector3.UP
	for i in n - 1:
		var a: Vector3 = P[i]
		var b: Vector3 = P[i + 1]
		var mid := (a + b) * 0.5
		if mid.x < x0 or mid.x >= x0 + 2000.0 or mid.z < z0 or mid.z >= z0 + 2000.0:
			continue                                   # gehört zur Nachbarkachel
		if i > 0 and i % CHUNK == 0:
			_flush_st(st)
			st = _new_st()
		var na: Vector3 = N[i]
		var nb: Vector3 = N[i + 1]
		var dir := (b - a)
		dir.y = 0.0
		dir = dir.normalized()
		var lA := a + na * hw
		var rA := a - na * hw
		var lB := b + nb * hw
		var rB := b - nb * hw
		var sl := Vector3(0, 0.02, 0)
		# Fahrbahn (oben), Plattenkante unten nicht nötig (liegt im Erdreich)
		_q(st["road"], rA + sl, rB + sl, lB + sl, lA + sl, up, true)
		# Randlinien und Mittellinie (gestrichelt)
		for side in [1.0, -1.0]:
			var o0: Vector3 = (na if side > 0 else -na) * (hw - 0.35)
			var o1: Vector3 = (nb if side > 0 else -nb) * (hw - 0.35)
			var wv0: Vector3 = (na if side > 0 else -na) * 0.15
			var wv1: Vector3 = (nb if side > 0 else -nb) * 0.15
			var l := Vector3(0, 0.035, 0)
			if side > 0:
				_q(st["line"], a + o0 - wv0 + l, b + o1 - wv1 + l, b + o1 + l, a + o0 + l, up)
			else:
				_q(st["line"], a + o0 + l, b + o1 + l, b + o1 - wv1 + l, a + o0 - wv0 + l, up)
		if hw >= 3.5 and i % 3 == 0:
			var l2 := Vector3(0, 0.035, 0)
			_q(st["line"], a - na * 0.06 + l2, b - nb * 0.06 + l2, b + nb * 0.06 + l2, a + na * 0.06 + l2, up)
		# Innenwände (Normalen zur Röhrenmitte), Decke (nach unten), Lichtband
		var h := Vector3(0, CLEAR, 0)
		_q(st["wall"], lA, lB, lB + h, lA + h, -na, true)
		_q(st["wall"], rB, rA, rA + h, rB + h, na, true)
		_q(st["wall"], lA + h, lB + h, rB + h, rA + h, -up, true)
		var lw := Vector3(0, CLEAR - 0.03, 0)
		if i % 12 == 0:
			_lights.append(mid + Vector3(0, CLEAR - 0.4, 0))
		_q(st["lamp"], a + na * 0.18 + lw, b + nb * 0.18 + lw, b - nb * 0.18 + lw, a - na * 0.18 + lw, -up)
		var is_box: bool = int(box[i]) == 1 or int(box[i + 1]) == 1
		if is_box:
			# Betonkasten: Außenwände bis unter Gelände, Decke oben
			var top := Vector3(0, CLEAR + ROOF, 0)
			var dn := Vector3(0, -SLAB - 0.6, 0)
			var oLA := a + na * ow
			var oLB := b + nb * ow
			var oRA := a - na * ow
			var oRB := b - nb * ow
			_q(st["outer"], oLB + dn, oLA + dn, oLA + top, oLB + top, na, true)
			_q(st["outer"], oRA + dn, oRB + dn, oRB + top, oRA + top, -na, true)
			_q(st["outer"], oRA + top, oRB + top, oLB + top, oLA + top, up, true)
		else:
			# Kollisionsdeckel über der Röhre in Geländehöhe (Kollisionsraster ist im Band abgesenkt)
			var k := 4
			for j in k:
				var u0 := -ow - 1.0 + (2.0 * ow + 2.0) * float(j) / k
				var u1 := -ow - 1.0 + (2.0 * ow + 2.0) * float(j + 1) / k
				var c00 := a + na * u0
				var c01 := a + na * u1
				var c10 := b + nb * u0
				var c11 := b + nb * u1
				# nie unter das Röhrendach (am Röhrenanfang liegt das Gelände im Anfahrtstrog auf Fahrbahnhöhe)
				var ya := a.y + CLEAR + ROOF
				var yb := b.y + CLEAR + ROOF
				c00.y = maxf(terrain.height_at(c00.x, c00.z), ya)
				c01.y = maxf(terrain.height_at(c01.x, c01.z), ya)
				c10.y = maxf(terrain.height_at(c10.x, c10.z), yb)
				c11.y = maxf(terrain.height_at(c11.x, c11.z), yb)
				_lid.append_array(PackedVector3Array([c00, c10, c11, c00, c11, c01]))
		_cor.append([Vector2(a.x, a.z), Vector2(b.x, b.z), ow + 0.5, a.y, b.y])
	# Portalwände um die Öffnung (Kettenanfang/-ende in dieser Kachel)
	for e in [[bool(tn.get("p0", false)), 0, 1], [bool(tn.get("p1", false)), n - 1, n - 2]]:
		if not e[0]:
			continue
		var p: Vector3 = P[int(e[1])]
		var q: Vector3 = P[int(e[2])]
		var out := Vector3(p.x - q.x, 0, p.z - q.z).normalized()
		var side := Vector3(-out.z, 0, out.x)
		var y0 := Vector3(0, -SLAB - 0.6, 0)
		var yc := Vector3(0, CLEAR, 0)
		var yt := Vector3(0, CLEAR + ROOF + 0.35, 0)
		# von außen gesehen: Normale = out; Viereck gegen den Uhrzeigersinn
		_q(st["outer"], p - side * ow + y0, p - side * hw + y0, p - side * hw + yt, p - side * ow + yt, out, true)
		_q(st["outer"], p + side * hw + y0, p + side * ow + y0, p + side * ow + yt, p + side * hw + yt, out, true)
		_q(st["outer"], p - side * hw + yc, p + side * hw + yc, p + side * hw + yt, p - side * hw + yt, out, true)
		# Brüstungskante oben
		_q(st["outer"], p - side * ow + yt, p + side * ow + yt, p + side * ow + yt - out * 0.6, p - side * ow + yt - out * 0.6, Vector3.UP)

	_flush_st(st)


func mask_image() -> Image:
	## Maske für den Gelände-Shader (1000 × 1000, 2 m/px): R = Fahrbahnhöhe, G = 1 im Tunnelband
	if _cor.is_empty():
		return null
	var img := Image.create(1000, 1000, false, Image.FORMAT_RGF)
	var x0 := terrain.center.x - 1000.0
	var z0 := terrain.center.y - 1000.0
	for c in _cor:
		var a: Vector2 = c[0]
		var b: Vector2 = c[1]
		var rad: float = float(c[2]) + 2.0            # Rand für die bilineare Filterung
		var lo := Vector2(minf(a.x, b.x), minf(a.y, b.y)) - Vector2(rad, rad)
		var hi := Vector2(maxf(a.x, b.x), maxf(a.y, b.y)) + Vector2(rad, rad)
		var ab := b - a
		var l2 := maxf(ab.length_squared(), 1e-6)
		for py in range(maxi(int((lo.y - z0) / 2.0), 0), mini(int((hi.y - z0) / 2.0) + 1, 1000)):
			for px in range(maxi(int((lo.x - x0) / 2.0), 0), mini(int((hi.x - x0) / 2.0) + 1, 1000)):
				var q := Vector2(x0 + px * 2.0 + 1.0, z0 + py * 2.0 + 1.0)
				var tu := (q - a).dot(ab) / l2
				if tu < -0.05 or tu > 1.05:
					continue                            # keine runden Kappen (sonst Loch vor dem Portal)
				var t := clampf(tu, 0.0, 1.0)
				var d := q.distance_to(a + ab * t)
				if d > rad:
					continue
				var y: float = lerpf(float(c[3]), float(c[4]), t)
				var old := img.get_pixel(px, py)
				var g := 1.0 if d <= float(c[2]) - 0.5 else maxf(old.g, 0.0)
				if old.g >= 1.0 and g < 1.0:
					continue
				img.set_pixel(px, py, Color(y, maxf(g, old.g), 0.0))
	return img
