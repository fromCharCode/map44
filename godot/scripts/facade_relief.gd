class_name FacadeRelief
extends RefCounted
## Fassaden-Baukasten: plastischer Schmuck und Bauteile je Bauepoche (Recherche data/research/fassaden.json, mit
## Bildbelegen bestehender Dresdner Bauten). Die Bauteile sind kleine Module, die als MultiMesh-Instanzen an das
## Fensterraster des Fassaden-Shaders gesetzt werden – grid() rechnet die Achsen und Fensterformate genauso wie
## shaders/facade.gdshader.
##
## Epochen (tools/facade_eras.py, Feld "era"): 1 Barock, 2 Klassizismus, 3 Dresdner Schule, 4 Gründerzeit,
## 5 Würfelhaus, 6 Klinker, 7 Jugendstil/Reform, 8 Weimarer Zeit, 9 1933–45, 10 Wiederaufbau 1950er, 11 DDR,
## 12 nach 1990, 13 Villen, 14 Dorfkern, 15 Industrie/kommunal.
##
## Modellraum: Ursprung an der Wand, +X entlang der Wand, +Y oben, −Z nach außen (wie die Balkonmodelle).
## Töne (letzter Namensteil): w Stuck, s Sandstein, k Kunststein, r roter Klinker, y gelber Klinker, d dunkles Holz,
## g Fensterladen-Grün, b Laden-Braunrot, i Eisen, c Beton/Putz hell, gl Glas.

static var _parts := {}                  # "fr_<modell>_<ton>" -> [{"mesh", "xf"}]
static var _mutex := Mutex.new()
static var enabled := true


static func is_model(name: String) -> bool:
	return name.begins_with("fr_")


static func parts(name: String) -> Array:
	_mutex.lock()
	var known := _parts.has(name)
	var res: Array = _parts.get(name, [])
	_mutex.unlock()
	if known:
		return res
	var bits := name.split("_")              # fr, modell…, ton
	var tone := bits[bits.size() - 1]
	var model := "_".join(bits.slice(1, bits.size() - 1))
	var mesh := _build(model)
	var out: Array = []
	if mesh != null:
		mesh.surface_set_material(0, _material(tone))
		out = [{"mesh": mesh, "xf": Transform3D.IDENTITY}]
	_mutex.lock()
	if _parts.has(name):
		out = _parts[name]
	else:
		_parts[name] = out
	_mutex.unlock()
	return out


static func _material(tone: String) -> Material:
	var key := "facade_relief_" + tone
	var have := TexLib.get_shared(key)
	if have != null:
		return have
	var m := StandardMaterial3D.new()
	m.roughness = 0.92
	match tone:
		"s":
			m.albedo_color = Color(0.70, 0.63, 0.51)         # Elbsandstein, leicht patiniert
		"k":
			m.albedo_color = Color(0.80, 0.76, 0.68)         # heller Kunststein/Putzgliederung
		"r":
			m.albedo_color = Color(0.50, 0.24, 0.18)         # roter Klinker
		"y":
			m.albedo_color = Color(0.78, 0.62, 0.30)         # gelber Klinker
		"d":
			m.albedo_color = Color(0.20, 0.14, 0.10)         # dunkles Holz (Fachwerk, Sparrenköpfe)
		"g":
			m.albedo_color = Color(0.22, 0.34, 0.26)         # Fensterladen grün
		"b":
			m.albedo_color = Color(0.42, 0.20, 0.15)         # Fensterladen braunrot
		"i":
			m.albedo_color = Color(0.11, 0.12, 0.13)         # Eisen
			m.metallic = 0.5
			m.roughness = 0.6
		"c":
			m.albedo_color = Color(0.83, 0.81, 0.76)         # Beton/Glattputz hell
		"sl":
			m.albedo_color = Color(0.17, 0.18, 0.21)         # Schiefer (Turmhauben)
			m.roughness = 0.6
		"cu":
			m.albedo_color = Color(0.33, 0.53, 0.46)         # patiniertes Kupfer
			m.roughness = 0.55
			m.metallic = 0.3
		"gl":
			m.albedo_color = Color(0.10, 0.13, 0.16)         # Verglasung
			m.roughness = 0.12
			m.metallic = 0.4
		_:
			m.albedo_color = Color(0.86, 0.84, 0.78)         # Stuck, gebrochenes Weiß
	return TexLib.shared_material(key, m)


# --- Modulgeometrie -----------------------------------------------------------------------------------
static func _q(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, d: Vector3, n: Vector3) -> void:
	var pts := [a, b, c, a, c, d] if (b - a).cross(c - a).dot(n) < 0.0 else [a, c, b, a, d, c]
	for p in pts:
		st.set_normal(n)
		st.add_vertex(p)


static func _box(st: SurfaceTool, x0: float, x1: float, y0: float, y1: float, dep: float, z0 := 0.0) -> void:
	## Quader vor der Wand (Rückseite offen): von z0 bis z0 − dep nach außen
	var zf := z0 - dep
	_q(st, Vector3(x0, y0, zf), Vector3(x1, y0, zf), Vector3(x1, y1, zf), Vector3(x0, y1, zf), Vector3(0, 0, -1))
	_q(st, Vector3(x0, y1, z0), Vector3(x1, y1, z0), Vector3(x1, y1, zf), Vector3(x0, y1, zf), Vector3.UP)
	_q(st, Vector3(x0, y0, z0), Vector3(x1, y0, z0), Vector3(x1, y0, zf), Vector3(x0, y0, zf), Vector3.DOWN)
	_q(st, Vector3(x0, y0, z0), Vector3(x0, y1, z0), Vector3(x0, y1, zf), Vector3(x0, y0, zf), Vector3(-1, 0, 0))
	_q(st, Vector3(x1, y0, z0), Vector3(x1, y1, z0), Vector3(x1, y1, zf), Vector3(x1, y0, zf), Vector3(1, 0, 0))


static func _rake(st: SurfaceTool, a: Vector2, b: Vector2, th: float, dep: float) -> void:
	## schräges Gesims-/Bogenstück von a nach b (Unterkante), Stärke th, Ausladung dep
	var d := (b - a).normalized()
	var up := Vector2(-d.y, d.x)
	if up.y < 0.0:
		up = -up
	var a1 := a + up * th
	var b1 := b + up * th
	var zf := -dep
	_q(st, Vector3(a.x, a.y, zf), Vector3(b.x, b.y, zf), Vector3(b1.x, b1.y, zf), Vector3(a1.x, a1.y, zf), Vector3(0, 0, -1))
	_q(st, Vector3(a1.x, a1.y, 0), Vector3(b1.x, b1.y, 0), Vector3(b1.x, b1.y, zf), Vector3(a1.x, a1.y, zf), Vector3(up.x, up.y, 0))
	_q(st, Vector3(a.x, a.y, 0), Vector3(b.x, b.y, 0), Vector3(b.x, b.y, zf), Vector3(a.x, a.y, zf), Vector3(-up.x, -up.y, 0))


static func _prism(st: SurfaceTool, pts: Array, y0: float, y1: float, top := true) -> void:
	## senkrechtes Prisma über einem Linienzug (x, z; z negativ = außen), Enden an der Wand
	for i in pts.size() - 1:
		var a: Vector2 = pts[i]
		var b: Vector2 = pts[i + 1]
		var d := (b - a).normalized()
		var n := Vector3(d.y, 0, -d.x)
		if n.z > 0.0:
			n = -n
		_q(st, Vector3(a.x, y0, a.y), Vector3(b.x, y0, b.y), Vector3(b.x, y1, b.y), Vector3(a.x, y1, a.y), n)
	if top:
		for i in range(1, pts.size() - 2):
			var p0: Vector2 = pts[0]
			var p1: Vector2 = pts[i]
			var p2: Vector2 = pts[i + 1]
			_q(st, Vector3(p0.x, y1, p0.y), Vector3(p1.x, y1, p1.y), Vector3(p2.x, y1, p2.y), Vector3(p2.x, y1, p2.y), Vector3.UP)
			_q(st, Vector3(p0.x, y0, p0.y), Vector3(p1.x, y0, p1.y), Vector3(p2.x, y0, p2.y), Vector3(p2.x, y0, p2.y), Vector3.DOWN)


static func _build(model: String) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	match model:
		"box":
			# Einheitsquader (Breite, Höhe, Ausladung je 1): Bänder, Gesimse, Platten, Brüstungen, Läden, Quader
			_box(st, -0.5, 0.5, 0.0, 1.0, 1.0)
		"sill":
			_box(st, -0.5, 0.5, 0.0, 0.07, 0.15)
			_box(st, -0.46, 0.46, -0.07, 0.0, 0.07)
		"jamb":
			_box(st, -0.065, 0.065, 0.0, 1.0, 0.055)
		"lintel":
			_box(st, -0.5, 0.5, 0.0, 0.24, 0.05)
		"cornice":
			_box(st, -0.47, 0.47, 0.0, 0.05, 0.10)
			_box(st, -0.5, 0.5, 0.05, 0.12, 0.19)
		"ped_tri":
			_box(st, -0.5, 0.5, 0.0, 0.06, 0.17)
			_q(st, Vector3(-0.46, 0.06, -0.06), Vector3(0.46, 0.06, -0.06), Vector3(0.0, 0.30, -0.06), Vector3(0.0, 0.30, -0.06), Vector3(0, 0, -1))
			_rake(st, Vector2(-0.5, 0.06), Vector2(0.0, 0.31), 0.055, 0.17)
			_rake(st, Vector2(0.0, 0.31), Vector2(0.5, 0.06), 0.055, 0.17)
		"ped_seg":
			_box(st, -0.5, 0.5, 0.0, 0.06, 0.17)
			var prev := Vector2(-0.5, 0.06)
			for i in range(1, 9):
				var t := float(i) / 8.0
				var cur := Vector2(-0.5 + t, 0.06 + 0.22 * sin(t * PI))
				_rake(st, prev, cur, 0.055, 0.17)
				_q(st, Vector3(prev.x, 0.06, -0.06), Vector3(cur.x, 0.06, -0.06), Vector3(cur.x, cur.y, -0.06), Vector3(prev.x, prev.y, -0.06), Vector3(0, 0, -1))
				prev = cur
		"ped_broken":
			# gesprengter Giebel: zwei Schrägen ohne Spitze, in der Mitte ein Sockel mit Aufsatz
			_box(st, -0.5, 0.5, 0.0, 0.06, 0.17)
			_rake(st, Vector2(-0.5, 0.06), Vector2(-0.16, 0.24), 0.055, 0.17)
			_rake(st, Vector2(0.16, 0.24), Vector2(0.5, 0.06), 0.055, 0.17)
			_box(st, -0.07, 0.07, 0.06, 0.30, 0.12)
			_box(st, -0.10, 0.10, 0.30, 0.36, 0.15)
		"arch":
			# Rundbogen (Archivolte), Breite 1 gleichmäßig skaliert: Halbkreis über der Kämpferlinie y = 0
			var pa := Vector2(-0.5, 0.0)
			for i in range(1, 13):
				var ang := PI * (1.0 - float(i) / 12.0)
				var pb := Vector2(0.5 * cos(ang), 0.5 * sin(ang))
				_rake(st, pa, pb, 0.09, 0.07)
				pa = pb
		"arch_seg":
			# Segmentbogen (Entlastungsbogen, Stich 1:6), Breite 1 gleichmäßig skaliert
			var pc := Vector2(-0.5, 0.0)
			for i in range(1, 9):
				var t2 := float(i) / 8.0
				var pd := Vector2(-0.5 + t2, 0.17 * sin(t2 * PI))
				_rake(st, pc, pd, 0.10, 0.05)
				pc = pd
		"key":
			var zf := -0.11
			_q(st, Vector3(-0.09, 0.0, zf), Vector3(0.09, 0.0, zf), Vector3(0.13, 0.34, zf), Vector3(-0.13, 0.34, zf), Vector3(0, 0, -1))
			_q(st, Vector3(-0.09, 0.0, 0), Vector3(-0.13, 0.34, 0), Vector3(-0.13, 0.34, zf), Vector3(-0.09, 0.0, zf), Vector3(-1, 0, 0))
			_q(st, Vector3(0.09, 0.0, 0), Vector3(0.13, 0.34, 0), Vector3(0.13, 0.34, zf), Vector3(0.09, 0.0, zf), Vector3(1, 0, 0))
			_q(st, Vector3(-0.13, 0.34, 0), Vector3(0.13, 0.34, 0), Vector3(0.13, 0.34, zf), Vector3(-0.13, 0.34, zf), Vector3.UP)
			_q(st, Vector3(-0.09, 0.0, 0), Vector3(0.09, 0.0, 0), Vector3(0.09, 0.0, zf), Vector3(-0.09, 0.0, zf), Vector3.DOWN)
		"console":
			_box(st, -0.07, 0.07, -0.10, 0.0, 0.26)
			_box(st, -0.07, 0.07, -0.22, -0.10, 0.17)
			_box(st, -0.07, 0.07, -0.34, -0.22, 0.08)
		"bracket":
			# kleine Konsole unter Verdachung/Fensterbank
			_box(st, -0.045, 0.045, -0.07, 0.0, 0.15)
			_box(st, -0.045, 0.045, -0.16, -0.07, 0.08)
		"dentil":
			# Zahnschnitt, 0,9 m langes Stück mit sechs Zähnen
			for i in 6:
				var x := -0.45 + 0.075 + float(i) * 0.15
				_box(st, x - 0.04, x + 0.04, 0.0, 0.10, 0.09)
		"pil":
			_box(st, -0.22, -0.15, 0.0, 1.0, 0.09)
			_box(st, 0.15, 0.22, 0.0, 1.0, 0.09)
			_box(st, -0.15, 0.15, 0.0, 1.0, 0.06)
		"cap":
			_box(st, -0.24, 0.24, 0.0, 0.05, 0.11)
			_box(st, -0.27, 0.27, 0.05, 0.17, 0.14)
			_box(st, -0.31, 0.31, 0.17, 0.25, 0.18)
		"base":
			_box(st, -0.29, 0.29, 0.0, 0.16, 0.15)
			_box(st, -0.25, 0.25, 0.16, 0.24, 0.12)
		"panel":
			# Brüstungsfeld/Putzspiegel, Breite und Höhe 1 (skaliert): Rahmen mit vertieftem Feld
			_box(st, -0.5, 0.5, 0.0, 0.10, 0.045)
			_box(st, -0.5, 0.5, 0.90, 1.0, 0.045)
			_box(st, -0.5, -0.44, 0.10, 0.90, 0.045)
			_box(st, 0.44, 0.5, 0.10, 0.90, 0.045)
			_box(st, -0.44, 0.44, 0.10, 0.90, 0.015)
		"baluster":
			# Balusterbrüstung, Breite 1 (skaliert), Höhe 0,6
			_box(st, -0.5, 0.5, 0.0, 0.07, 0.10)
			_box(st, -0.5, 0.5, 0.53, 0.60, 0.11)
			for i in 5:
				var bx := -0.4 + float(i) * 0.2
				_box(st, bx - 0.035, bx + 0.035, 0.07, 0.53, 0.07, -0.015)
		"cart":
			# Kartusche/Medaillon: achteckiger Buckel, gleichmäßig skaliert
			var ring: Array = []
			for i in 8:
				var a := TAU * (float(i) + 0.5) / 8.0
				ring.append(Vector2(0.5 * cos(a), 0.5 + 0.5 * sin(a) * 0.72))
			for i in 8:
				var r0: Vector2 = ring[i]
				var r1: Vector2 = ring[(i + 1) % 8]
				_q(st, Vector3(0, 0.5, -0.07), Vector3(r0.x * 0.7, 0.5 + (r0.y - 0.5) * 0.7, -0.07), Vector3(r1.x * 0.7, 0.5 + (r1.y - 0.5) * 0.7, -0.07), Vector3(r1.x * 0.7, 0.5 + (r1.y - 0.5) * 0.7, -0.07), Vector3(0, 0, -1))
				_q(st, Vector3(r0.x * 0.7, 0.5 + (r0.y - 0.5) * 0.7, -0.07), Vector3(r1.x * 0.7, 0.5 + (r1.y - 0.5) * 0.7, -0.07), Vector3(r1.x, r1.y, 0), Vector3(r0.x, r0.y, 0), Vector3(r0.x + r1.x, r0.y + r1.y - 1.0, -0.6).normalized())
		"railing":
			# Geländer (Schmiedeeisen/Stahl), Breite 1 (skaliert), Höhe 1,0, flach vor der Wand
			_box(st, -0.5, 0.5, 0.94, 1.0, 0.04)
			_box(st, -0.5, 0.5, 0.06, 0.10, 0.03)
			for i in 9:
				var rx := -0.47 + float(i) * 0.1175
				_box(st, rx - 0.008, rx + 0.008, 0.10, 0.94, 0.016, -0.01)
		"diag":
			# Strebe (Fachwerk), von unten links nach oben rechts im Einheitsfeld
			_rake(st, Vector2(-0.5, 0.0), Vector2(0.5, 0.86), 0.14, 0.04)
		"gable":
			# Giebeldreieck über einer Achse (Frontispiz/Zwerchgiebel), Breite 1 gleichmäßig skaliert
			_q(st, Vector3(-0.5, 0.0, -0.10), Vector3(0.5, 0.0, -0.10), Vector3(0.0, 0.42, -0.10), Vector3(0.0, 0.42, -0.10), Vector3(0, 0, -1))
			_rake(st, Vector2(-0.56, -0.02), Vector2(0.0, 0.45), 0.06, 0.22)
			_rake(st, Vector2(0.0, 0.45), Vector2(0.56, -0.02), 0.06, 0.22)
		"erker":
			# polygonaler Erker, Höhe 1 (skaliert): Trapezgrundriss 2,3 m an der Wand, 1,4 m vorn, 0,8 m tief
			_prism(st, [Vector2(-1.15, 0.0), Vector2(-0.7, -0.8), Vector2(0.7, -0.8), Vector2(1.15, 0.0)], 0.0, 1.0)
		"erker_win":
			# Fenster eines Erkergeschosses (drei Scheiben), feste Höhe 1,5 m
			_box(st, -0.5, 0.5, 0.0, 1.5, 0.02, -0.80)
			var sx := Vector2(0.45, -0.8).normalized()
			for sgn in [-1.0, 1.0]:
				var c0: Vector2 = Vector2(sgn * 1.06, -0.16)
				var c1: Vector2 = Vector2(sgn * 0.79, -0.64)
				var nn := Vector3(sgn * 0.87, 0, -0.49)
				_q(st, Vector3(c0.x, 0.0, c0.y) + nn * 0.02, Vector3(c1.x, 0.0, c1.y) + nn * 0.02, Vector3(c1.x, 1.5, c1.y) + nn * 0.02, Vector3(c0.x, 1.5, c0.y) + nn * 0.02, nn)
		"turret":
			# Ecktürmchen/Eckerker, Höhe 1 (skaliert): achteckiger Schaft, Halbmesser 1,45 m
			for i in 8:
				var a0 := TAU * (float(i) + 0.5) / 8.0
				var a1 := TAU * (float(i) + 1.5) / 8.0
				var v0 := Vector3(cos(a0) * 1.45, 0, sin(a0) * 1.45)
				var v1 := Vector3(cos(a1) * 1.45, 0, sin(a1) * 1.45)
				_q(st, v0, v1, v1 + Vector3(0, 1, 0), v0 + Vector3(0, 1, 0), Vector3(cos((a0 + a1) * 0.5), 0, sin((a0 + a1) * 0.5)))
		"spire":
			# Turmhaube: achteckiger Helm, Höhe 1 (skaliert), mit Traufring
			for i in 8:
				var a0 := TAU * (float(i) + 0.5) / 8.0
				var a1 := TAU * (float(i) + 1.5) / 8.0
				var v0 := Vector3(cos(a0) * 1.75, 0, sin(a0) * 1.75)
				var v1 := Vector3(cos(a1) * 1.75, 0, sin(a1) * 1.75)
				var am := (a0 + a1) * 0.5
				_q(st, v0, v1, Vector3(0, 1, 0), Vector3(0, 1, 0), Vector3(cos(am), 0.6, sin(am)).normalized())
				_q(st, v0, v1, v1 * 0.83 + Vector3(0, -0.04, 0), v0 * 0.83 + Vector3(0, -0.04, 0), Vector3.DOWN)
		"onion":
			# Welsche Haube (geschweift), Höhe 1 (skaliert)
			var prof := [[1.75, 0.0], [1.85, 0.12], [1.55, 0.3], [0.95, 0.45], [0.55, 0.62], [0.42, 0.78], [0.0, 1.0]]
			for i in 8:
				var a0 := TAU * (float(i) + 0.5) / 8.0
				var a1 := TAU * (float(i) + 1.5) / 8.0
				var am := (a0 + a1) * 0.5
				for k in prof.size() - 1:
					var r0: float = prof[k][0]
					var r1: float = prof[k + 1][0]
					var y0: float = prof[k][1]
					var y1: float = prof[k + 1][1]
					_q(st, Vector3(cos(a0) * r0, y0, sin(a0) * r0), Vector3(cos(a1) * r0, y0, sin(a1) * r0),
						Vector3(cos(a1) * r1, y1, sin(a1) * r1), Vector3(cos(a0) * r1, y1, sin(a0) * r1), Vector3(cos(am), 0.5, sin(am)).normalized())
		"schweif":
			# geschweifter Zwerchgiebel (Jugendstil/Neobarock), Breite 1 gleichmäßig skaliert
			var half := [[0.5, 0.0], [0.5, 0.22], [0.40, 0.30], [0.34, 0.46], [0.22, 0.56], [0.13, 0.76], [0.0, 0.88]]
			for sgn: float in [-1.0, 1.0]:
				for k in half.size() - 1:
					var x0: float = half[k][0] * sgn
					var x1: float = half[k + 1][0] * sgn
					var y0: float = half[k][1]
					var y1: float = half[k + 1][1]
					_q(st, Vector3(0, 0, -0.06), Vector3(x0, y0, -0.06), Vector3(x1, y1, -0.06), Vector3(x1, y1, -0.06), Vector3(0, 0, -1))
					# Abdeckung entlang der Kontur (0,3 m tief nach hinten)
					var e := Vector2(x1 - x0, y1 - y0).normalized()
					var nn := Vector3(-e.y * sgn, e.x * sgn, 0)
					if nn.y < 0.0 and absf(nn.x) < 0.5:
						nn = -nn
					_q(st, Vector3(x0, y0, -0.10), Vector3(x1, y1, -0.10), Vector3(x1, y1, 0.25), Vector3(x0, y0, 0.25), nn)
		"erker_box":
			# Kastenerker (Reform/1950er), Höhe 1 (skaliert): 2,2 m breit, 0,6 m tief
			_box(st, -1.1, 1.1, 0.0, 1.0, 0.6)
		_:
			return null
	return st.commit()


# --- Raster wie im Shader -------------------------------------------------------------------------------
static func _h11(p: float) -> float:
	p = fposmod(p * 0.1031, 1.0)
	p *= p + 33.33
	p *= p + p
	return fposmod(p, 1.0)


static func _fr(x: float) -> float:
	return x - floor(x)


static func _h21(px: float, py: float) -> float:
	var p3 := Vector3(_fr(px * 0.1031), _fr(py * 0.1031), _fr(px * 0.1031))
	var dd := p3.dot(Vector3(p3.y, p3.z, p3.x) + Vector3(33.33, 33.33, 33.33))
	p3 += Vector3(dd, dd, dd)
	return _fr((p3.x + p3.y) * p3.z)


static func grid(style: int, era: int, seed: float, fh: float) -> Dictionary:
	## Achsmaß und Fensterformat – identisch zu den Stil- und Epochenwerten in shaders/facade.gdshader
	var h1 := _h11(seed * 91.7)
	var h2 := _h11(seed * 13.1)
	var g := {"pitch": 2.6, "ww": 1.2, "wh": 1.7, "wy": 0.7, "plain": false}
	match style:
		0:
			g = {"pitch": lerpf(2.3, 3.1, h1), "ww": lerpf(2.3, 3.1, h1) * lerpf(0.40, 0.46, h2), "wh": fh * 0.66, "wy": fh * 0.19, "plain": false}
		1:
			g = {"pitch": lerpf(3.0, 4.2, h1), "ww": lerpf(3.0, 4.2, h1) * 0.44, "wh": fh * 0.72, "wy": fh * 0.17, "plain": false}
		3:
			g = {"pitch": lerpf(2.2, 2.8, h1), "ww": lerpf(2.2, 2.8, h1) * 0.40, "wh": fh * 0.52, "wy": fh * 0.27, "plain": false}
		6:
			g = {"pitch": lerpf(2.4, 3.0, h1), "ww": lerpf(2.4, 3.0, h1) * 0.40, "wh": fh * 0.62, "wy": fh * 0.22, "plain": false}
	if era > 0 and style in [0, 1, 3, 6]:
		match era:
			2:
				g["pitch"] = lerpf(2.4, 3.0, h1); g["ww"] = 1.1; g["wh"] = fh * 0.60; g["wy"] = fh * 0.22
			3:
				g["pitch"] = lerpf(2.8, 3.6, h1); g["ww"] = 1.15; g["wh"] = fh * 0.66; g["wy"] = fh * 0.18
			5:
				g["pitch"] = lerpf(2.6, 3.4, h1); g["ww"] = float(g["pitch"]) * 0.42
			7:
				g["pitch"] = lerpf(2.4, 3.6, h1); g["ww"] = float(g["pitch"]) * 0.46; g["wh"] = fh * 0.58; g["wy"] = fh * 0.24
			8:
				g["pitch"] = lerpf(2.8, 3.8, h1); g["ww"] = float(g["pitch"]) * 0.50; g["wh"] = 1.38; g["wy"] = 0.90; g["plain"] = true
			9:
				g["pitch"] = lerpf(2.6, 3.4, h1); g["ww"] = 1.15; g["wh"] = 1.50; g["wy"] = 0.85; g["plain"] = true
			10:
				g["pitch"] = lerpf(2.8, 3.6, h1); g["ww"] = 1.30; g["wh"] = 1.65; g["wy"] = 0.80; g["plain"] = true
			11:
				g["plain"] = true
			12:
				g["pitch"] = lerpf(2.5, 4.0, h1); g["ww"] = 1.2; g["wh"] = fh - 0.85; g["wy"] = 0.14; g["plain"] = true
			13:
				g["pitch"] = lerpf(2.8, 3.8, h1); g["ww"] = 1.2
			14:
				g["pitch"] = lerpf(2.2, 3.0, h1); g["ww"] = 0.9; g["wh"] = 1.25; g["wy"] = 0.90; g["plain"] = true
	return g


# --- Verteilung an einer Wandkante -------------------------------------------------------------------
static func edge(out: Dictionary, cell_of: Callable, levels_f: float, height: float, style: int, era: int, pitched: bool,
		seed: float, p0: Vector2, p1: Vector2, ln: float, acc: float, nrm: Vector3, ref: float, has_shop: bool) -> void:
	## Trägt die Bauteile einer Straßenfassade in out ein: Schlüssel [modell, zelle] -> Array[Transform3D]
	## (gleiches Format wie die Balkone in buildings.gd).
	if not enabled or not (style in [0, 1, 3, 6]) or ln < 4.0 or era == 11 or era == 15:
		return
	if era == 0:
		era = 1 if style == 1 else (6 if style == 6 else (8 if style == 3 else 4))
	var low_ok := era >= 7                      # Siedlungs-, Dorf- und Reformbauten sind oft nur zweigeschossig
	if height < (4.8 if low_ok else 7.5):
		return
	var levels := maxf(levels_f, 1.0)
	var fh := clampf(height / levels, 2.7, 4.6)
	var rows := int(floor(height / fh))
	var g := grid(style, era, seed, fh)
	var pitch: float = g["pitch"]
	var ww: float = g["ww"]
	var wh: float = g["wh"]
	var wy: float = g["wy"]
	var h3 := _h11(seed * 7.7)
	var h4 := _h11(seed * 5.3)                  # Rezept
	var h5 := _h11(seed * 29.1)                 # Nebenmerkmale
	if era == 10 and style == 1:
		h4 = 0.2                                  # Sandsteinbauten der 1950er (Altmarkt): immer Nationale Tradition
	var e := (p1 - p0) / ln
	var basis := Basis(Vector3.UP.cross(-nrm).normalized(), Vector3.UP, -nrm)
	var put := func(model: String, tone: String, along: float, y: float, sx: float, sy: float, sz := 1.0, zoff := 0.0) -> void:
		var wp := p0 + e * along
		var key := ["fr_%s_%s" % [model, tone], cell_of.call(wp)]
		if not out.has(key):
			out[key] = []
		(out[key] as Array).append(Transform3D(basis.scaled_local(Vector3(sx, sy, sz)), Vector3(wp.x, y, wp.y) + nrm * (0.01 + zoff)))
	# Fensterachsen (Mitte, Spalte)
	var cols: Array = []
	var c0 := int(floor(acc / pitch))
	var c1 := int(floor((acc + ln) / pitch))
	for col in range(c0, c1 + 1):
		var along := float(col) * pitch + pitch * 0.5 - acc
		if along - ww * 0.5 - 0.3 >= 0.0 and along + ww * 0.5 + 0.3 <= ln:
			cols.append([along, col])
	if cols.is_empty():
		return
	var ncol := cols.size()
	var top_row := -1
	for r in range(1, rows):
		if float(r) * fh + wy + wh <= height - 0.75:
			top_row = r
	var ch := 0.85 if style == 1 else (0.4 if style == 3 else 0.65)     # Kranzgesims (buildings.gd _trim_strip)
	var y_eave := ref + height - ch
	var shop_all := has_shop or (style in [0, 3, 6] and _h11(seed * 3.3) > 0.88 and height > 6.0)
	var mid := ncol / 2

	# --- Erker (ersetzt die Fenster seiner Achse) ---
	var erker_col := -1
	var erker_kind := ""
	var erker_r1 := mini(2, top_row)
	if top_row >= 2 and ncol >= 4:
		if era in [4, 5, 13] and h5 > 0.72:
			erker_col = 1 if h3 < 0.5 else ncol - 2
			erker_kind = "erker"
		elif era == 7 and h5 > 0.45:
			erker_col = mid
			erker_kind = "erker" if h4 < 0.5 else "erker_box"
			erker_r1 = mini(3, top_row)
		elif era == 10 and h5 > 0.7 and h4 < 0.5:
			erker_col = mid
			erker_kind = "erker_box"
	if erker_col >= 0:
		var ea: float = cols[erker_col][0]
		var ey0 := ref + fh - 0.25
		var ey1 := ref + float(erker_r1 + 1) * fh - 0.15
		var etone := "s" if era in [3, 10] else ("k" if era == 7 else "w")
		put.call(erker_kind, etone, ea, ey0, 1.0, ey1 - ey0)
		var ed := 0.8 if erker_kind == "erker" else 0.6
		put.call("box", etone, ea, ey1, 2.6 if erker_kind == "erker" else 2.5, 0.12, ed + 0.12)          # Abdeckung
		put.call("box", etone, ea, ey0 - 0.30, 1.9, 0.30, ed * 0.55)                                     # Konsolfuß
		for r in range(1, erker_r1 + 1):
			var wy0 := ref + float(r) * fh + wy
			if erker_kind == "erker":
				put.call("erker_win", "gl", ea, wy0, 1.0, minf(wh, 1.9) / 1.5)
			else:
				put.call("box", "gl", ea, wy0, 1.7, minf(wh, 1.7), 0.02, ed)
			put.call("box", etone, ea, wy0 - 0.12, 2.35 if erker_kind == "erker" else 2.3, 0.10, ed + 0.05)   # Sohlbankband

	# --- Fenster je Achse und Geschoss ---
	for ci in ncol:
		var along: float = cols[ci][0]
		var col: int = cols[ci][1]
		var outer := ci == 0 or ci == ncol - 1
		for r in range(1, rows):
			if r > top_row or top_row < 0:
				continue
			if ci == erker_col and r <= erker_r1:
				continue
			var y0 := ref + float(r) * fh + wy
			var yl := y0 + wh + 0.03
			var wfull := ww + 0.26
			match era:
				1:      # Barock: Faschen, Putzspiegel unter dem Fenster, Schlussstein, Segmentgiebel in der Beletage
					put.call("sill", "w", along, y0 - 0.07, wfull, 1.0)
					put.call("jamb", "w", along - ww * 0.5 - 0.065, y0, 1.0, wh)
					put.call("jamb", "w", along + ww * 0.5 + 0.065, y0, 1.0, wh)
					put.call("lintel", "w", along, yl, wfull, 0.75)
					put.call("key", "w", along, yl - 0.04, 1.0, 1.0)
					if wy > 0.55:
						put.call("panel", "w", along, y0 - 0.07 - (wy - 0.22), ww + 0.1, wy - 0.3)
					if r == 1 and (h4 < 0.5 or ci == mid):
						put.call("ped_seg", "w", along, yl + 0.2, ww + 0.36, ww + 0.36)
					# Ohren am Gewände
					put.call("box", "w", along - ww * 0.5 - 0.16, yl - 0.02, 0.19, 0.2, 0.055)
					put.call("box", "w", along + ww * 0.5 + 0.16, yl - 0.02, 0.19, 0.2, 0.055)
				2:      # Klassizismus: sparsam – Fensterbank, flaches Gewände, gerade Verdachung nur in der Beletage
					put.call("sill", "w", along, y0 - 0.07, wfull, 1.0)
					put.call("jamb", "w", along - ww * 0.5 - 0.05, y0, 0.7, wh)
					put.call("jamb", "w", along + ww * 0.5 + 0.05, y0, 0.7, wh)
					if r == 1:
						put.call("cornice", "w", along, yl + 0.12, ww + 0.4, 1.0)
				3:      # Dresdner Schule: Sandstein, Rundbogenfenster in der Beletage mit Archivolte und Schlussstein
					put.call("sill", "s", along, y0 - 0.07, wfull, 1.0)
					put.call("jamb", "s", along - ww * 0.5 - 0.065, y0, 1.0, wh - (ww * 0.5 if r == 1 else 0.0))
					put.call("jamb", "s", along + ww * 0.5 + 0.065, y0, 1.0, wh - (ww * 0.5 if r == 1 else 0.0))
					if r == 1:
						put.call("arch", "s", along, y0 + wh - ww * 0.5, ww + 0.02, ww + 0.02)
						put.call("key", "s", along, y0 + wh - 0.02, 1.0, 1.0)
						put.call("baluster", "s", along, y0 - 0.07 - 0.62, ww + 0.2, minf(1.0, (wy - 0.1) / 0.6))
					else:
						put.call("lintel", "s", along, yl, wfull, 1.0)
						if r == 2:
							put.call("cornice", "s", along, yl + 0.26, ww + 0.36, 1.0)
				4, 5, 13:
					var t := "w"
					put.call("sill", t, along, y0 - 0.07, wfull, 1.0)
					put.call("jamb", t, along - ww * 0.5 - 0.065, y0, 1.0, wh)
					put.call("jamb", t, along + ww * 0.5 + 0.065, y0, 1.0, wh)
					put.call("lintel", t, along, yl, wfull, 1.0)
					var rich := h4 > 0.66
					var mid_rec := h4 > 0.33 and not rich
					if r == 1:
						if rich:
							put.call("ped_seg" if h3 < 0.5 else "ped_broken", t, along, yl + 0.26, ww + 0.36, ww + 0.36)
							put.call("key", t, along, yl - 0.02, 1.0, 1.0)
							put.call("baluster", t, along, y0 - 0.07 - 0.62, ww + 0.2, minf(1.0, (wy - 0.1) / 0.6))
						elif mid_rec:
							# Verdachung auf Konsolen, Brüstungsfeld
							put.call("cornice", t, along, yl + 0.26, ww + 0.4, 1.0)
							put.call("bracket", t, along - ww * 0.5 - 0.02, yl + 0.26, 1.0, 1.0)
							put.call("bracket", t, along + ww * 0.5 + 0.02, yl + 0.26, 1.0, 1.0)
							if wy > 0.5:
								put.call("panel", t, along, y0 - 0.1 - (wy - 0.24), ww, wy - 0.3)
						else:
							# spätklassizistisch: Dreiecksgiebel in den Außenachsen, sonst gerade Verdachung
							if outer or ncol < 4:
								put.call("ped_tri", t, along, yl + 0.26, ww + 0.36, ww + 0.36)
							else:
								put.call("cornice", t, along, yl + 0.26, ww + 0.36, 1.0)
							if wy > 0.5:
								put.call("panel", t, along, y0 - 0.1 - (wy - 0.24), ww, wy - 0.3)
					elif r == 2:
						if mid_rec:
							put.call("ped_tri" if (ci % 2 == 0) else "ped_seg", t, along, yl + 0.26, ww + 0.36, ww + 0.36)
							if wy > 0.5:
								put.call("cart", t, along, y0 - 0.1 - (wy - 0.2) * 0.9, (wy - 0.3) * 1.1, (wy - 0.3) * 1.1)
						else:
							put.call("cornice", t, along, yl + 0.26, ww + 0.36, 1.0)
					elif r == top_row and rows >= 4:
						# oberstes Geschoss: Fensterbank auf Konsölchen
						put.call("bracket", t, along - ww * 0.5 + 0.1, y0 - 0.14, 1.0, 1.0)
						put.call("bracket", t, along + ww * 0.5 - 0.1, y0 - 0.14, 1.0, 1.0)
					elif rows >= 5:
						put.call("cornice", t, along, yl + 0.26, ww + 0.36, 1.0)
				6:      # Klinker: helle Gliederung auf dem Verblender, Entlastungsbögen aus Formsteinen
					var kt := "k"
					var brick := "r" if h5 < 0.6 else "y"
					put.call("sill", kt, along, y0 - 0.07, wfull, 1.0)
					put.call("jamb", kt, along - ww * 0.5 - 0.065, y0, 1.0, wh)
					put.call("jamb", kt, along + ww * 0.5 + 0.065, y0, 1.0, wh)
					if r == 1:
						put.call("lintel", kt, along, yl, wfull, 1.0)
						put.call("ped_tri" if h3 < 0.55 else "ped_seg", kt, along, yl + 0.26, ww + 0.36, ww + 0.36)
					elif r == 2 and h4 > 0.4:
						put.call("lintel", kt, along, yl, wfull, 1.0)
						put.call("cornice", kt, along, yl + 0.26, ww + 0.36, 1.0)
					else:
						put.call("arch_seg", brick, along, yl - 0.02, ww + 0.3, ww + 0.3)
						put.call("key", kt, along, yl - 0.02, 0.8, 0.7)
				7:      # Jugendstil/Reform
					if h4 < 0.5:
						# Jugendstil: flache Putzrahmen, geschwungene Verdachung, Ornamentfeld
						put.call("sill", "k", along, y0 - 0.07, wfull, 1.0)
						put.call("jamb", "k", along - ww * 0.5 - 0.05, y0, 0.8, wh)
						put.call("jamb", "k", along + ww * 0.5 + 0.05, y0, 0.8, wh)
						if r == 1:
							put.call("ped_seg", "k", along, yl + 0.05, ww + 0.3, (ww + 0.3) * 0.7)
						if r == 2 and wy > 0.5:
							put.call("cart", "k", along, y0 - 0.1 - (wy - 0.2) * 0.9, (wy - 0.3) * 1.2, (wy - 0.3) * 1.2)
					else:
						# Reformarchitektur: schlicht, Fensterbank, Klappläden
						put.call("sill", "k", along, y0 - 0.07, wfull, 1.0)
						if h5 > 0.35:
							var lt := "g" if h3 < 0.6 else "b"
							put.call("box", lt, along - ww * 0.5 - ww * 0.26, y0, ww * 0.5, wh, 0.04)
							put.call("box", lt, along + ww * 0.5 + ww * 0.26, y0, ww * 0.5, wh, 0.04)
				8:      # Weimarer Zeit
					if pitched:
						# traditionalistische Siedlung: Klinkerfaschen oder Klappläden
						if h4 < 0.55:
							put.call("box", "r", along, y0 - 0.12, ww + 0.36, 0.12, 0.05)
							put.call("box", "r", along, y0 + wh, ww + 0.36, 0.16, 0.035)
							put.call("box", "r", along - ww * 0.5 - 0.09, y0, 0.18, wh, 0.035)
							put.call("box", "r", along + ww * 0.5 + 0.09, y0, 0.18, wh, 0.035)
						else:
							put.call("box", "c", along, y0 - 0.06, ww + 0.1, 0.06, 0.09)
							if h5 > 0.5 and ww < 1.7:
								put.call("box", "g", along - ww * 0.5 - ww * 0.26, y0, ww * 0.5, wh, 0.04)
								put.call("box", "g", along + ww * 0.5 + ww * 0.26, y0, ww * 0.5, wh, 0.04)
					else:
						# Neues Bauen: bündige Fenster, nur schmale Bank; Loggien mit massiver Brüstung
						put.call("box", "c", along, y0 - 0.05, ww + 0.06, 0.05, 0.07)
						if _h21(float(col) * 1.7, floor(seed * 23.0)) > 0.66 and ci != mid:
							var fy := ref + float(r) * fh
							put.call("box", "c", along, fy - 0.14, ww + 0.9, 0.14, 1.15)
							put.call("box", "c", along, fy, ww + 0.9, 0.95, 0.12, 1.03)
							put.call("box", "c", along - (ww + 0.9) * 0.5 + 0.06, fy, 0.12, 0.95, 1.03)
							put.call("box", "c", along + (ww + 0.9) * 0.5 - 0.06, fy, 0.12, 0.95, 1.03)
				9:      # 1933–45: Werksteinbank, Klappläden
					put.call("box", "s", along, y0 - 0.07, ww + 0.16, 0.07, 0.10)
					if h5 > 0.3:
						var lt2 := "g" if h3 < 0.5 else "d"
						put.call("box", lt2, along - ww * 0.5 - ww * 0.26, y0, ww * 0.5, wh, 0.04)
						put.call("box", lt2, along + ww * 0.5 + ww * 0.26, y0, ww * 0.5, wh, 0.04)
				10:     # Wiederaufbau 1950er
					if h4 < 0.5:
						# Nationale Tradition: Sandsteinrahmung, Brüstungsgitter, Bekrönung in der Beletage
						put.call("box", "s", along, y0 - 0.08, ww + 0.3, 0.08, 0.10)
						put.call("box", "s", along, y0 + wh, ww + 0.3, 0.14, 0.05)
						put.call("box", "s", along - ww * 0.5 - 0.07, y0, 0.14, wh, 0.05)
						put.call("box", "s", along + ww * 0.5 + 0.07, y0, 0.14, wh, 0.05)
						if r == 1:
							put.call("cornice", "s", along, y0 + wh + 0.16, ww + 0.4, 1.0)
						put.call("railing", "i", along, y0 - 0.02, ww, 0.5)
					else:
						# Zeilenbau: Fensterbank; Balkone mit Stabgeländer in jeder dritten Achse
						put.call("box", "c", along, y0 - 0.06, ww + 0.1, 0.06, 0.09)
						if _h21(float(col) * 1.3, floor(seed * 19.0)) > 0.62:
							var fy2 := ref + float(r) * fh
							put.call("box", "c", along, fy2 - 0.13, ww + 1.2, 0.13, 1.1)
							put.call("railing", "i", along, fy2, ww + 1.2, 1.0, 1.0, 1.05)
				12:     # nach 1990: bodentiefe Fenster mit Absturzsicherung
					put.call("railing", "i", along, y0, ww, 1.0)
				14:     # Dorfkern: Klappläden, schlichte Bank
					put.call("box", "c", along, y0 - 0.06, ww + 0.1, 0.06, 0.08)
					var lt3 := "g" if h3 < 0.5 else ("b" if h3 < 0.8 else "d")
					put.call("box", lt3, along - ww * 0.5 - ww * 0.26, y0, ww * 0.5, wh, 0.04)
					put.call("box", lt3, along + ww * 0.5 + ww * 0.26, y0, ww * 0.5, wh, 0.04)

	# --- waagerechte Gliederung ---
	if era in [1, 2, 3, 4, 5, 6, 13]:
		var bt := "s" if era == 3 else ("k" if era == 6 else "w")
		# Gurtgesims über dem Erdgeschoss, Sohlbankgesimse in den Obergeschossen
		put.call("box", bt, ln * 0.5, ref + fh - 0.10, ln, 0.20, 0.10)
		put.call("box", bt, ln * 0.5, ref + fh + 0.10, ln, 0.05, 0.14)
		if era in [4, 5, 6, 13] and top_row >= 2:
			for r in range(1, top_row + 1):
				put.call("box", bt, ln * 0.5, ref + float(r) * fh + wy - 0.16, ln, 0.07, 0.05)
		# Konsolen und Zahnschnitt unter dem Kranzgesims
		if era != 1:
			var nc := int(floor(ln / (1.2 if era == 2 else 0.95)))
			if nc >= 2 and era != 2:
				var step := ln / float(nc)
				for i in nc:
					put.call("console", bt, (float(i) + 0.5) * step, y_eave, 1.0, 1.0)
			var nd := int(floor(ln / 0.9))
			if nd >= 1 and (era in [2, 3] or h4 > 0.5):
				var dstep := ln / float(nd)
				for i in nd:
					put.call("dentil", "r" if era == 6 and h5 < 0.6 else bt, (float(i) + 0.5) * dstep, y_eave - (0.36 if era != 2 else 0.12), dstep / 0.9, 1.0)
		# Stuckfries unter der Traufe (reiche Gründerzeit)
		if era in [4, 5] and h4 > 0.66 and top_row >= 2:
			put.call("box", bt, ln * 0.5, y_eave - 0.85, ln, 0.06, 0.05)

	# --- Erdgeschoss: Bandrustika zwischen den Öffnungen (nicht bei Ladenfronten) ---
	if era in [3, 4, 5, 13] and not shop_all and fh > 3.0:
		var y_r0 := ref + 1.0
		var y_r1 := ref + fh - 0.22
		var nb := int(floor((y_r1 - y_r0) / 0.42))
		var bh := (y_r1 - y_r0) / float(maxi(nb, 1))
		var xs: Array = [0.0]
		for ci in ncol:
			var a2: float = cols[ci][0]
			xs.append(a2 - ww * 0.5 - 0.16)
			xs.append(a2 + ww * 0.5 + 0.16)
		xs.append(ln)
		var rt := "s" if era == 3 else "w"
		for k in range(0, xs.size() - 1, 2):
			var xa: float = xs[k]
			var xb: float = xs[k + 1]
			if xb - xa < 0.35:
				continue
			for j in nb:
				put.call("box", rt, (xa + xb) * 0.5, y_r0 + float(j) * bh + 0.03, xb - xa, bh - 0.06, 0.035)
		# Rundbogen über den Erdgeschossfenstern
		if h4 <= 0.33 or era == 3:
			for ci in ncol:
				put.call("arch", rt, cols[ci][0], ref + wy + wh - ww * 0.5, ww + 0.1, ww + 0.1)

	# --- senkrechte Gliederung ---
	var y_p0 := ref + fh + 0.16
	var y_p1 := y_eave - 0.27
	if y_p1 - y_p0 > 3.0:
		match era:
			1:
				# Barock: flache Lisenen zwischen allen Achsen
				for col in range(c0, c1 + 2):
					var x := float(col) * pitch - acc
					if x > 0.3 and x < ln - 0.3:
						put.call("box", "w", x, y_p0, 0.5, y_p1 - y_p0 + 0.2, 0.04)
			2:
				# Klassizismus: Kolossalpilaster an den Ecken
				if ln >= 8.0:
					for x in [0.32, ln - 0.32]:
						put.call("base", "w", x, y_p0, 1.0, 1.0)
						put.call("pil", "w", x, y_p0 + 0.24, 1.0, y_p1 - y_p0 - 0.24)
						put.call("cap", "w", x, y_p1, 1.0, 1.0)
			3, 4, 5, 13:
				if ln >= 7.0:
					if h4 > 0.33 and h4 <= 0.66:
						# Eckquaderung: abwechselnd lange und kurze Quader
						var nq := int(floor((y_p1 - ref - 1.0) / 0.45))
						for j in nq:
							var qw := 0.62 if j % 2 == 0 else 0.40
							put.call("box", "s" if era == 3 else "w", qw * 0.5, ref + 1.0 + float(j) * 0.45 + 0.03, qw, 0.39, 0.045)
							put.call("box", "s" if era == 3 else "w", ln - qw * 0.5, ref + 1.0 + float(j) * 0.45 + 0.03, qw, 0.39, 0.045)
					else:
						for x in [0.3, ln - 0.3]:
							put.call("base", "w", x, y_p0, 1.0, 1.0)
							put.call("pil", "w", x, y_p0 + 0.24, 1.0, y_p1 - y_p0 - 0.24)
							put.call("cap", "w", x, y_p1, 1.0, 1.0)
				# Mittelrisalit mit Giebel (Würfelhaus, reiche Gründerzeit)
				if (era == 5 or (era in [4, 13] and h4 > 0.66)) and ncol >= 3 and ncol % 2 == 1 and erker_col < 0:
					var ma: float = cols[mid][0]
					for x in [ma - pitch * 0.5, ma + pitch * 0.5]:
						put.call("base", "w", x, y_p0, 1.0, 1.0)
						put.call("pil", "w", x, y_p0 + 0.24, 1.0, y_p1 - y_p0 - 0.24)
						put.call("cap", "w", x, y_p1, 1.0, 1.0)
					put.call("gable", "w", ma, ref + height + 0.04, pitch + 0.5, pitch + 0.5)
			7:
				# Jugendstil: geschweifter Zwerchgiebel über der Mittelachse
				if h4 < 0.5 and ncol >= 3 and erker_col < 0 and ln >= 10.0:
					put.call("schweif", "k", cols[mid][0], ref + height - 0.05, pitch * 1.7, pitch * 1.7)
			6:
				# Klinker: Lisenen im Verblender an den Hausecken
				if ln >= 7.0:
					var brick2 := "r" if h5 < 0.6 else "y"
					for x in [0.28, ln - 0.28]:
						put.call("box", brick2, x, ref + 1.0, 0.5, y_eave - ref - 1.0, 0.06)

	# --- Epochen ab 1900: Sockel, Treppenhaus, Vordach, Traufe ---
	var door_a: float = cols[mid][0]
	match era:
		7:
			if h4 >= 0.5:
				put.call("box", "s", ln * 0.5, ref - 0.3, ln, 1.35, 0.06)           # Bruchstein-/Werksteinsockel
			put.call("box", "k", ln * 0.5, ref + fh - 0.06, ln, 0.12, 0.05)
		8:
			if pitched:
				if h4 < 0.55:
					put.call("box", "r", ln * 0.5, ref - 0.3, ln, 1.3, 0.05)       # Klinkersockel
					# Klinker-Treppenhausachse bis über die Traufe, mit stehendem Treppenhausfenster
					put.call("box", "r", door_a, ref + 1.0, 1.9, height - 0.6, 0.07)
					if top_row >= 1:
						put.call("box", "gl", door_a, ref + fh + 0.9, 0.9, float(top_row) * fh - 0.2, 0.09)
						for r in range(1, top_row + 1):
							put.call("box", "r", door_a, ref + float(r) * fh + fh * 0.5 + 0.8, 0.9, 0.08, 0.10)
				else:
					put.call("box", "c", ln * 0.5, ref - 0.3, ln, 1.2, 0.04)
			else:
				# Neues Bauen: Attikaband, Treppenhaus-Fensterband, Vordach
				put.call("box", "c", ln * 0.5, ref + height - 0.22, ln, 0.26, 0.05)
				if top_row >= 1:
					put.call("box", "gl", door_a, ref + fh + 0.6, 1.0, float(top_row) * fh, 0.04)
					for r in range(1, top_row + 2):
						put.call("box", "c", door_a, ref + float(r) * fh + 0.3, 1.1, 0.07, 0.06)
			put.call("box", "c", door_a, ref + 2.45, 2.0, 0.12, 1.0)               # Vordach als Kragplatte
		9:
			put.call("box", "s", ln * 0.5, ref - 0.3, ln, 1.2, 0.05)
			# Werksteinrahmung des Eingangs
			put.call("box", "s", door_a - 0.75, ref, 0.24, 2.5, 0.08)
			put.call("box", "s", door_a + 0.75, ref, 0.24, 2.5, 0.08)
			put.call("box", "s", door_a, ref + 2.5, 1.9, 0.26, 0.10)
			# Sparrenköpfe am Dachüberstand
			var ns := int(floor(ln / 0.8))
			for i in ns:
				put.call("box", "d", (float(i) + 0.5) * ln / float(ns), ref + height - 0.16, 0.10, 0.14, 0.45)
		10:
			if h4 < 0.5 and rows >= 5 and ln >= 12.0 and fh > 3.0:
				# Arkaden im Erdgeschoss (Altmarkt, Wilsdruffer Straße, Grunaer Straße): Sandsteinpfeiler mit Rundbögen
				# vor der Ladenzone
				var ah := fh - 0.35
				for col in range(c0, c1 + 2):
					var x := float(col) * pitch - acc
					if x > 0.4 and x < ln - 0.4:
						put.call("box", "s", x, ref - 0.2, 0.75, ah - (pitch - 0.75) * 0.5 + 0.2, 0.55)
				for ci in ncol:
					var ax: float = cols[ci][0]
					put.call("arch", "s", ax, ref + ah - (pitch - 0.75) * 0.5, pitch - 0.75, pitch - 0.75, 7.5)
				put.call("box", "s", ln * 0.5, ref + ah + 0.05, ln, 0.30, 0.58)
			if h4 < 0.5:
				put.call("box", "s", ln * 0.5, ref + fh - 0.12, ln, 0.22, 0.09)        # Gurtgesims über dem Erdgeschoss
				put.call("box", "s", ln * 0.5, ref - 0.3, ln, 1.3, 0.05)
				var nk := int(floor(ln / 1.1))
				for i in nk:
					put.call("bracket", "s", (float(i) + 0.5) * ln / float(nk), y_eave + 0.02, 1.4, 1.4)
			else:
				put.call("box", "c", ln * 0.5, ref - 0.3, ln, 1.1, 0.04)
				put.call("box", "c", door_a, ref + 2.45, 1.8, 0.10, 0.8)
		12:
			put.call("box", "c", ln * 0.5, ref - 0.3, ln, 0.9, 0.03)
		14:
			# Fachwerk-Obergeschoss (ein Teil der Dorfhäuser): Schwelle, Rähm, Ständer, Streben
			if h4 < 0.4 and rows == 2 and top_row >= 1:
				var fy0 := ref + fh
				var fy1 := ref + height - 0.25
				put.call("box", "d", ln * 0.5, fy0 - 0.08, ln, 0.18, 0.05)
				put.call("box", "d", ln * 0.5, fy1 - 0.16, ln, 0.16, 0.05)
				var np := maxi(2, int(round(ln / 1.3)))
				for i in np + 1:
					var x := clampf(float(i) * ln / float(np), 0.08, ln - 0.08)
					put.call("box", "d", x, fy0, 0.15, fy1 - fy0, 0.045)
				put.call("box", "d", ln * 0.5, ref + fh + wy - 0.14, ln, 0.13, 0.045)
				put.call("diag", "d", ln / float(np) * 0.5, fy0 + 0.1, ln / float(np) - 0.2, (wy - 0.3))
				put.call("diag", "d", ln - ln / float(np) * 0.5, fy0 + 0.1, -(ln / float(np) - 0.2), (wy - 0.3))
		13:
			# Villen: Zierfachwerk im obersten Geschoss bei einem Teil der Häuser
			if h5 > 0.75 and top_row >= 2:
				var zy0 := ref + float(top_row) * fh + 0.1
				var zy1 := y_eave - 0.2
				var nz := maxi(2, int(round(ln / 1.4)))
				put.call("box", "d", ln * 0.5, zy0 - 0.1, ln, 0.16, 0.05)
				for i in nz + 1:
					put.call("box", "d", clampf(float(i) * ln / float(nz), 0.08, ln - 0.08), zy0, 0.14, zy1 - zy0, 0.045)


static func corner(out: Dictionary, cell_of: Callable, pc: Vector2, bis: Vector2, levels_f: float, height: float, style: int,
		era: int, seed: float, ref: float) -> void:
	## Ecktürmchen an freien Hausecken (Gründerzeit, Jugendstil, Villen): achteckiger Eckerker ab dem 1. Obergeschoss
	## bis über die Traufe, mit Helm oder Welscher Haube. bis = Winkelhalbierende nach außen.
	if not enabled or not (style in [0, 1, 6]) or not (era in [4, 5, 7, 13]) or height < 10.0:
		return
	if _h11(seed * 41.3) < 0.55:
		return
	var levels := maxf(levels_f, 1.0)
	var fh := clampf(height / levels, 2.7, 4.6)
	var rows := int(floor(height / fh))
	var tone := "k" if era == 7 else ("s" if style == 1 else "w")
	var c := pc + bis * 0.25
	var cell: Vector2i = cell_of.call(c)
	var add := func(model: String, tn: String, xf: Transform3D) -> void:
		var key := ["fr_%s_%s" % [model, tn], cell]
		if not out.has(key):
			out[key] = []
		(out[key] as Array).append(xf)
	var y0 := ref + fh - 0.35
	var y1 := ref + height + 1.5
	var yaw := atan2(bis.x, bis.y)                       # Modell +Z -> Winkelhalbierende
	var b0 := Basis(Vector3.UP, yaw)
	var org := Vector3(c.x, 0, c.y)
	add.call("turret", tone, Transform3D(b0.scaled_local(Vector3(1, y1 - y0, 1)), org + Vector3(0, y0, 0)))
	add.call("turret", tone, Transform3D(b0.scaled_local(Vector3(0.6, 0.5, 0.6)), org + Vector3(0, y0 - 0.5, 0)))     # Konsolfuß
	add.call("turret", tone, Transform3D(b0.scaled_local(Vector3(1.08, 0.2, 1.08)), org + Vector3(0, y1 - 0.2, 0)))   # Traufgesims
	var onion := _h11(seed * 67.9) > 0.6 or era == 7
	var cap_h := 3.2 if onion else 4.2
	add.call("onion" if onion else "spire", "cu" if (onion and _h11(seed * 3.1) > 0.4) else "sl",
		Transform3D(b0.scaled_local(Vector3(1, cap_h, 1)), org + Vector3(0, y1, 0)))
	# Fenster auf den drei Außenflächen je Geschoss
	for r in range(1, rows + 1):
		var wy := ref + float(r) * fh + fh * 0.22
		if wy + fh * 0.55 > y1 - 0.3:
			continue
		for da in [-PI * 0.25, 0.0, PI * 0.25]:
			var bb := Basis(Vector3.UP, yaw + da)
			var outw := bb * Vector3(0, 0, 1)
			add.call("box", "gl", Transform3D(Basis(Vector3.UP, yaw + da + PI).scaled_local(Vector3(0.62, fh * 0.52, 0.03)),
				org + outw * 1.345 + Vector3(0, wy, 0)))
