class_name Tunnels
extends Node3D
## Befahrbare Straßentunnel einer Kachel (Pipeline tools/tunnels.py -> city["tunnels"]).
##
## Je Tunnelkette: Fahrbahnplatte mit Randlinien, Röhre (Innenwände, Decke, Lichtband), an flach überdeckten
## Abschnitten ("box") ein Betonkasten mit Außenwänden und Decke, an den Portalen die Portalwand um die Öffnung.
## Das sichtbare Gelände ist über den Bauwerken geglättet (Pipeline); der Gelände-Shader blendet es im Lichtraum aus
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
var _axes := {}                      # Vector2i -> [[a, b, hw, kette], …] aller Ketten dieser Kachel
var _own := -1
var _pgroup := {}                    # "kette:ende" -> Gruppe (gemeinsame Stirnwand nebeneinanderliegender Portale)
var _groups: Array = []              # je Gruppe [[kette, ende], …]
var _portals: Array = []             # [Vector2 Portalmitte, Vector2 nach außen, float halbe Breite]


func _in_other(p: Vector3, margin := 0.3) -> bool:
	## Liegt p im Lichtraum einer anderen Tunnelkette dieser Kachel?
	var q := Vector2(p.x, p.z)
	for e in _axes.get(Vector2i(floori(p.x / CELL), floori(p.z / CELL)), []):
		if int(e[3]) == _own:
			continue
		var a: Vector2 = e[0]
		var ab: Vector2 = (e[1] as Vector2) - a
		var t := clampf((q - a).dot(ab) / maxf(ab.length_squared(), 1e-6), 0.0, 1.0)
		if q.distance_to(a + ab * t) < float(e[2]) - margin:
			return true
	return false


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
	# Achsen aller Ketten (Raster 32 m): Wände, die in einer anderen Röhre liegen, entfallen (Zwillingsröhren
	# dicht nebeneinander, Rampen mit gemeinsamem Portal wie am Waldschlößchen)
	for ci in data.size():
		var q: Array = data[ci]["pts"]
		var hw_o := float(data[ci]["w"]) * 0.5
		for i in q.size() - 1:
			var a2 := Vector2(float(q[i][0]), float(q[i][1]))
			var b2 := Vector2(float(q[i + 1][0]), float(q[i + 1][1]))
			var e := [a2, b2, hw_o, ci]
			for cx in range(floori((minf(a2.x, b2.x) - hw_o) / CELL), floori((maxf(a2.x, b2.x) + hw_o) / CELL) + 1):
				for cz in range(floori((minf(a2.y, b2.y) - hw_o) / CELL), floori((maxf(a2.y, b2.y) + hw_o) / CELL) + 1):
					var key := Vector2i(cx, cz)
					if not _axes.has(key):
						_axes[key] = []
					(_axes[key] as Array).append(e)
	_group_portals(data)
	for ci in data.size():
		_own = ci
		_tunnel(data[ci], x0, z0)
	_own = -1
	_group_faces(data)
	for lp in ([] if OS.has_environment("DRESDEN_NOTUNLIGHT") else _lights):
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


func _before_portal(p: Vector3) -> bool:
	## Liegt p in der Zufahrt (20 m) vor einer Portalöffnung dieser Kachel?
	var q := Vector2(p.x, p.z)
	for pt in _portals:
		var d: Vector2 = q - (pt[0] as Vector2)
		var s := d.dot(pt[1])
		if s > -0.5 and s < 20.0 and absf(d.cross(pt[1])) < float(pt[2]) - 0.2:
			return true
	return false


static func _in_trough(data: Array, own: int, p: Vector3) -> bool:
	## Liegt p auf der Fahrbahn (± 0,3 m) eines anderen Anfahrtstrogs?
	var q := Vector2(p.x, p.z)
	for ti in data.size():
		if ti == own:
			continue
		var pts: Array = data[ti]["pts"]
		var hw := float(data[ti]["w"]) * 0.5 + 0.3
		for i in pts.size() - 1:
			var a := Vector2(float(pts[i][0]), float(pts[i][1]))
			var ab := Vector2(float(pts[i + 1][0]), float(pts[i + 1][1])) - a
			if absf(q.x - a.x) > 30.0 or absf(q.y - a.y) > 30.0:
				continue
			var t := clampf((q - a).dot(ab) / maxf(ab.length_squared(), 1e-6), 0.0, 1.0)
			if q.distance_to(a + ab * t) < hw:
				return true
	return false


func build_troughs(data: Array) -> void:
	## Anfahrtströge vor den Portalen (tools/tunnels.py "troughs"): senkrechte Betonwände neben der Rampe,
	## [x, z, y, wand_links, wand_rechts] je Stützpunkt.
	_faces = PackedVector3Array()                    # Tunnelflächen sind schon als Kollision angelegt
	_own = -1                                        # _in_other: alle Röhren der Kachel
	for ti in data.size():
		var tr: Dictionary = data[ti]
		var st := _new_st()
		var pts: Array = tr["pts"]
		var e := float(tr["w"]) * 0.5 + 0.35
		var n := pts.size()
		for i in n - 1:
			var a := Vector3(float(pts[i][0]), float(pts[i][2]), float(pts[i][1]))
			var b := Vector3(float(pts[i + 1][0]), float(pts[i + 1][2]), float(pts[i + 1][1]))
			var tg := Vector3(b.x - a.x, 0, b.z - a.z).normalized()
			var nr := Vector3(-tg.z, 0, tg.x)
			for k in 2:
				var sd := -1.0 if k == 0 else 1.0
				var h0 := float(pts[i][3 + k])
				var h1 := float(pts[i + 1][3 + k])
				if h0 <= 0.0 and h1 <= 0.0:
					continue
				var o := nr * e * sd
				# Wand stünde in der Fahrbahn eines anderen Trogs oder im Lichtraum einer Röhre (zusammenlaufende
				# Rampen mit gemeinsamem Portal wie am Waldschlößchen): weglassen
				var wm := (a + b) * 0.5 + o
				if _in_other(wm) or _in_trough(data, ti, wm) or _before_portal(wm):
					continue
				var th := nr * 1.4 * sd
				var dn := Vector3(0, 0.4, 0)
				var a0 := a + o - dn
				var b0 := b + o - dn
				var a1 := a + o + Vector3(0, h0, 0)
				var b1 := b + o + Vector3(0, h1, 0)
				var s: SurfaceTool = st["outer"]
				if sd < 0.0:
					_q(s, b0, a0, a1, b1, -nr * sd, true)
				else:
					_q(s, a0, b0, b1, a1, -nr * sd, true)
				if sd > 0.0:
					_q(s, a1, b1, b1 + th, a1 + th, Vector3.UP)
				else:
					_q(s, b1, a1, a1 + th, b1 + th, Vector3.UP)
				# Rückseite (falls das Gelände dahinter abfällt)
				if sd < 0.0:
					_q(s, a0 + th, b0 + th, b1 + th, a1 + th, nr * sd)
				else:
					_q(s, b0 + th, a0 + th, a1 + th, b1 + th, nr * sd)
		_flush_st(st)
	if not _faces.is_empty():
		var body := StaticBody3D.new()
		body.collision_layer = 1
		var cs := CollisionShape3D.new()
		var sh := ConcavePolygonShape3D.new()
		sh.backface_collision = true
		sh.set_faces(_faces)
		cs.shape = sh
		body.add_child(cs)
		add_child(body)
		_faces = PackedVector3Array()


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
	var prev_skip := [null, null]                       # Wand links/rechts im vorigen Abschnitt weggelassen?
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
		var skip_l := _in_other((lA + lB) * 0.5) or _in_other((lA + lB) * 0.5 + (na + nb) * 0.5 * WALL)
		var skip_r := _in_other((rA + rB) * 0.5) or _in_other((rA + rB) * 0.5 - (na + nb) * 0.5 * WALL)
		if not skip_l:
			_q(st["wall"], lA, lB, lB + h, lA + h, -na, true)
		if not skip_r:
			_q(st["wall"], rB, rA, rA + h, rB + h, na, true)
		# Stirnseite der Trennwand, wo zwei Röhren auseinanderlaufen/zusammenkommen: zwischen der eigenen Wand und
		# dem Lichtraum der anderen Röhre läge sonst ein offener Spalt (Blick ins ausgeblendete Gelände)
		for k in 2:
			var sk: bool = skip_l if k == 0 else skip_r
			if prev_skip[k] != null and bool(prev_skip[k]) != sk:
				var o: Vector3 = na if k == 0 else -na
				var w0: Vector3 = a + o * hw
				var d := 0.0
				while d < 6.0 and not _in_other(w0 + o * (d + 0.2), 0.0):
					d += 0.2
				if d > 0.05:
					var w1 := w0 + o * (d + 0.2)
					var f := -dir if not sk else dir               # zur gemeinsamen Röhre hin
					# Umlaufsinn wie bei den Innenwänden: sichtbar ist -(p1 - p0) × up
					if (w1 - w0).cross(up).dot(f) < 0.0:
						_q(st["wall"], w0, w1, w1 + h, w0 + h, f, true)
					else:
						_q(st["wall"], w1, w0, w0 + h, w1 + h, f, true)
			prev_skip[k] = sk
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
			if not skip_l:
				_q(st["outer"], oLB + dn, oLA + dn, oLA + top, oLB + top, na, true)
			if not skip_r:
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
	# Stirnwand bis an das Gelände dahinter ("h0"/"h1" über der Fahrbahn, tools/tunnels.py _head)
	for e in [[bool(tn.get("p0", false)), 0, 1, "h0"], [bool(tn.get("p1", false)), n - 1, n - 2, "h1"]]:
		if not e[0]:
			continue
		var p: Vector3 = P[int(e[1])]
		var q: Vector3 = P[int(e[2])]
		var out := Vector3(p.x - q.x, 0, p.z - q.z).normalized()
		_portals.append([Vector2(p.x, p.z), Vector2(out.x, out.z), hw])
		var side := Vector3(-out.z, 0, out.x)
		var y0 := Vector3(0, -SLAB - 0.6, 0)
		var yc := Vector3(0, CLEAR, 0)
		var yt := Vector3(0, maxf(CLEAR + ROOF, float(tn.get(e[3], 0.0))) + 0.35, 0)
		var ap := out * 2.0
		var sl2 := Vector3(0, 0.015, 0)
		# Fahrbahnplatte 2 m über das Portal hinaus: das Kollisionsraster ist im Tunnelband bis 0,6 m hinter das
		# Portal abgesenkt (tools/tunnels.py _terrain) – dort fielen Räder in einen 1,2 m tiefen Schlitz
		_q(st["road"], p - side * hw + sl2, p - side * hw + ap + sl2, p + side * hw + ap + sl2, p + side * hw + sl2, Vector3.UP, true)
		if _pgroup.has("%d:%d" % [_own, int(e[1])]):
			continue                                   # gemeinsame Stirnwand der Gruppe (_group_faces)
		# von außen gesehen: Normale = out; Viereck gegen den Uhrzeigersinn
		if not _in_other(p - side * (hw + 0.6)):
			_q(st["outer"], p - side * ow + y0, p - side * hw + y0, p - side * hw + yt, p - side * ow + yt, out, true)
		if not _in_other(p + side * (hw + 0.6)):
			_q(st["outer"], p + side * hw + y0, p + side * ow + y0, p + side * ow + yt, p + side * hw + yt, out, true)
		_q(st["outer"], p - side * hw + yc, p + side * hw + yc, p + side * hw + yt, p - side * hw + yt, out, true)
		# Brüstungskante oben
		_q(st["outer"], p - side * ow + yt, p + side * ow + yt, p + side * ow + yt - out * 0.6, p - side * ow + yt - out * 0.6, Vector3.UP)

	_flush_st(st)


static func _portal_end(tn: Dictionary, end: int) -> Array:
	## [Portalmitte (Vector3), nach außen (Vector3, waagrecht), halbe Breite, Stirnwandhöhe über der Fahrbahn]
	var pts: Array = tn["pts"]
	var n := pts.size()
	var i := 0 if end == 0 else n - 1
	var j := 1 if end == 0 else n - 2
	var p := Vector3(float(pts[i][0]), float(pts[i][2]), float(pts[i][1]))
	var q := Vector3(float(pts[j][0]), float(pts[j][2]), float(pts[j][1]))
	var out := Vector3(p.x - q.x, 0, p.z - q.z).normalized()
	var h := maxf(CLEAR + ROOF, float(tn.get("h0" if end == 0 else "h1", 0.0)))
	return [p, out, float(tn["w"]) * 0.5, h]


func _group_portals(data: Array) -> void:
	## Portale, deren Öffnungen sich überlappen oder nur durch einen Wandpfeiler getrennt sind (Rampen und
	## Zwillingsröhren mit gemeinsamem Bauwerk), bekommen eine gemeinsame, gerade Stirnwand.
	var ends: Array = []
	for ci in data.size():
		var tn: Dictionary = data[ci]
		if (tn["pts"] as Array).size() < 2:
			continue
		for e in [[bool(tn.get("p0", false)), 0], [bool(tn.get("p1", false)), (tn["pts"] as Array).size() - 1]]:
			if e[0]:
				ends.append([ci, int(e[1]), _portal_end(tn, 0 if int(e[1]) == 0 else 1)])
	var root := range(ends.size())
	for i in ends.size():
		for j in range(i + 1, ends.size()):
			var a: Array = ends[i][2]
			var b: Array = ends[j][2]
			if (a[1] as Vector3).dot(b[1]) < 0.7:
				continue                               # andere Richtung
			var d: Vector3 = (b[0] as Vector3) - (a[0] as Vector3)
			d.y = 0.0
			var u := Vector3(-(a[1] as Vector3).z, 0, (a[1] as Vector3).x)
			if absf(d.dot(a[1])) < 4.0 and absf(d.dot(u)) < float(a[2]) + float(b[2]) + 2.0 * WALL + 0.5:
				var ri: int = i
				while root[ri] != ri:
					ri = root[ri]
				var rj: int = j
				while root[rj] != rj:
					rj = root[rj]
				root[ri] = rj
	var by := {}
	for i in ends.size():
		var r: int = i
		while root[r] != r:
			r = root[r]
		if not by.has(r):
			by[r] = []
		(by[r] as Array).append(ends[i])
	for r in by:
		var g: Array = by[r]
		if g.size() < 2:
			continue
		_groups.append(g)
		for m in g:
			_pgroup["%d:%d" % [m[0], m[1]]] = true


func _group_faces(data: Array) -> void:
	## Gemeinsame Stirnwand je Gruppe: eine Ebene quer zur mittleren Richtung an der vordersten Portalecke, Öffnungen
	## je Röhre, Pfeiler dazwischen, Außenpfeiler und Brüstung über die ganze Breite. Röhren, die hinter der Ebene
	## enden, werden bis an die Ebene verlängert (Wände, Decke, Fahrbahn) – sonst Spalt/Durchblick am Rahmen.
	var st := _new_st()
	for g in _groups:
		var out := Vector3.ZERO
		for m in g:
			out += (m[2][1] as Vector3)
		out = out.normalized()
		var u := Vector3(-out.z, 0, out.x)
		var o: Vector3 = g[0][2][0]
		var f := -INF
		for m in g:
			var su0 := Vector3(-(m[2][1] as Vector3).z, 0, (m[2][1] as Vector3).x)
			for sd in [-1.0, 1.0]:
				f = maxf(f, ((m[2][0] as Vector3) + su0 * float(m[2][2]) * sd - o).dot(out))
		var ivs: Array = []                            # [links, rechts, Fahrbahnhöhe]
		var top := -INF
		var bot := INF
		for m in g:
			var p0: Vector3 = m[2][0]
			var hw: float = m[2][2]
			var ou: Vector3 = m[2][1]
			var su := Vector3(-ou.z, 0, ou.x)
			var den := maxf(ou.dot(out), 0.3)
			# Verlängerung bis an die Ebene: Ecken entlang der Röhrenrichtung auf die Ebene projizieren
			var cl := p0 + su * hw
			var cr := p0 - su * hw
			var cl2 := cl + ou * ((f - (cl - o).dot(out)) / den)
			var cr2 := cr + ou * ((f - (cr - o).dot(out)) / den)
			if cl.distance_to(cl2) > 0.03 or cr.distance_to(cr2) > 0.03:
				var h := Vector3(0, CLEAR, 0)
				var sl := Vector3(0, 0.02, 0)
				_q(st["road"], cr + sl, cr2 + sl, cl2 + sl, cl + sl, Vector3.UP, true)
				if not _in_other((cl + cl2) * 0.5):
					_q(st["wall"], cl, cl2, cl2 + h, cl + h, -su, true)
				if not _in_other((cr + cr2) * 0.5):
					_q(st["wall"], cr2, cr, cr + h, cr2 + h, su, true)
				_q(st["wall"], cl + h, cl2 + h, cr2 + h, cr + h, Vector3.DOWN, true)
				# Außenseite/Dach bis zur Geländeoberkante (Stirnwandhöhe) dicht
				var tp := Vector3(0, float(m[2][3]) + 0.35, 0)
				_q(st["outer"], cl + h, cl2 + h, cl2 + tp, cl + tp, su, true)
				_q(st["outer"], cr2 + h, cr + h, cr + tp, cr2 + tp, -su, true)
				_q(st["outer"], cr + tp, cr2 + tp, cl2 + tp, cl + tp, Vector3.UP)
			var p := p0 + ou * ((f - (p0 - o).dot(out)) / den)
			var c := (p - o).dot(u)
			var half := hw / maxf(absf(ou.dot(out)), 0.5)
			ivs.append([c - half, c + half, p.y])
			top = maxf(top, p.y + float(m[2][3]) + 0.35)
			bot = minf(bot, p.y - SLAB - 0.6)
		ivs.sort_custom(func(x, y): return x[0] < y[0])
		var base := o + out * f
		var P := func(lat: float, y: float) -> Vector3:
			var v := base + u * lat
			return Vector3(v.x, y, v.z)
		var lo: float = float(ivs[0][0]) - WALL
		var hi: float = float(ivs[ivs.size() - 1][1]) + WALL
		# Pfeiler: links außen, zwischen den Öffnungen, rechts außen (Überlappungen ergeben keinen Pfeiler)
		var cur := lo
		for iv in ivs:
			if float(iv[0]) > cur + 0.05:
				_q(st["outer"], P.call(cur, bot), P.call(float(iv[0]), bot), P.call(float(iv[0]), top), P.call(cur, top), out, true)
			# Sturz über der Öffnung
			var a0 := maxf(float(iv[0]), cur)
			if float(iv[1]) > a0:
				var yc: float = float(iv[2]) + CLEAR
				_q(st["outer"], P.call(a0, yc), P.call(float(iv[1]), yc), P.call(float(iv[1]), top), P.call(a0, top), out, true)
			cur = maxf(cur, float(iv[1]))
		_q(st["outer"], P.call(cur, bot), P.call(hi, bot), P.call(hi, top), P.call(cur, top), out, true)
		# Brüstungskante oben
		var back := -out * 0.6
		_q(st["outer"], P.call(lo, top), P.call(hi, top), P.call(hi, top) + back, P.call(lo, top) + back, Vector3.UP)
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
