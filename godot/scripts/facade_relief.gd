class_name FacadeRelief
extends RefCounted
## Plastischer Fassadenschmuck für Gründerzeit-, Klinker- und Barock-/Sandsteinbauten: Fensterbänke, Gewände,
## Verdachungen (gerade, Dreiecks- und Segmentgiebel), Schlusssteine, Pilaster/Lisenen mit Basis und Kapitell und
## Konsolen unter dem Kranzgesims. Die Bauteile sind kleine Module, die als MultiMesh-Instanzen an das Fensterraster
## des Fassaden-Shaders gesetzt werden (gleiche Achsen und Geschosshöhen wie shaders/facade.gdshader).
##
## Modellraum: Ursprung an der Wand, +X entlang der Wand, +Y oben, −Z nach außen (wie die Balkonmodelle).

const MODELS := ["sill", "jamb", "lintel", "cornice", "ped_tri", "ped_seg", "key", "console", "pil", "cap", "base"]

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
	match tone:
		"s":                                     # Elbsandstein, leicht patiniert
			m.albedo_color = Color(0.70, 0.63, 0.51)
		"k":                                     # Putzgliederung an Klinkerbauten: heller Kunststein
			m.albedo_color = Color(0.80, 0.76, 0.68)
		_:                                       # Stuck, gebrochenes Weiß
			m.albedo_color = Color(0.86, 0.84, 0.78)
	m.roughness = 0.92
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
	## schräges Gesimsstück von a nach b (Unterkante), Stärke th, Ausladung dep
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


static func _build(model: String) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	match model:
		"sill":
			# Fensterbank, Breite 1 (wird auf die Fensterbreite skaliert): Platte mit kleiner Unterstufe
			_box(st, -0.5, 0.5, 0.0, 0.07, 0.15)
			_box(st, -0.46, 0.46, -0.07, 0.0, 0.07)
		"jamb":
			# Gewände/Fasche, Höhe 1 (auf die Fensterhöhe skaliert)
			_box(st, -0.065, 0.065, 0.0, 1.0, 0.055)
		"lintel":
			# Sturzfeld über dem Fenster, Breite 1
			_box(st, -0.5, 0.5, 0.0, 0.24, 0.05)
		"cornice":
			# gerade Verdachung, Breite 1: zwei Stufen
			_box(st, -0.47, 0.47, 0.0, 0.05, 0.10)
			_box(st, -0.5, 0.5, 0.05, 0.12, 0.19)
		"ped_tri":
			# Dreiecksgiebel, Breite 1 (gleichmäßig skaliert): Giebelfeld + Schräggesimse + waagerechtes Gesims
			_box(st, -0.5, 0.5, 0.0, 0.06, 0.17)
			_q(st, Vector3(-0.46, 0.06, -0.06), Vector3(0.46, 0.06, -0.06), Vector3(0.0, 0.30, -0.06), Vector3(0.0, 0.30, -0.06), Vector3(0, 0, -1))
			_rake(st, Vector2(-0.5, 0.06), Vector2(0.0, 0.31), 0.055, 0.17)
			_rake(st, Vector2(0.0, 0.31), Vector2(0.5, 0.06), 0.055, 0.17)
		"ped_seg":
			# Segmentgiebel, Breite 1
			_box(st, -0.5, 0.5, 0.0, 0.06, 0.17)
			var prev := Vector2(-0.5, 0.06)
			for i in range(1, 9):
				var t := float(i) / 8.0
				var x := -0.5 + t
				var cur := Vector2(x, 0.06 + 0.22 * sin(t * PI))
				_rake(st, prev, cur, 0.055, 0.17)
				_q(st, Vector3(prev.x, 0.06, -0.06), Vector3(cur.x, 0.06, -0.06), Vector3(cur.x, cur.y, -0.06), Vector3(prev.x, prev.y, -0.06), Vector3(0, 0, -1))
				prev = cur
		"key":
			# Schlussstein (feste Größe): nach oben breiter
			var zf := -0.11
			_q(st, Vector3(-0.09, 0.0, zf), Vector3(0.09, 0.0, zf), Vector3(0.13, 0.34, zf), Vector3(-0.13, 0.34, zf), Vector3(0, 0, -1))
			_q(st, Vector3(-0.09, 0.0, 0), Vector3(-0.13, 0.34, 0), Vector3(-0.13, 0.34, zf), Vector3(-0.09, 0.0, zf), Vector3(-1, 0, 0))
			_q(st, Vector3(0.09, 0.0, 0), Vector3(0.13, 0.34, 0), Vector3(0.13, 0.34, zf), Vector3(0.09, 0.0, zf), Vector3(1, 0, 0))
			_q(st, Vector3(-0.13, 0.34, 0), Vector3(0.13, 0.34, 0), Vector3(0.13, 0.34, zf), Vector3(-0.13, 0.34, zf), Vector3.UP)
			_q(st, Vector3(-0.09, 0.0, 0), Vector3(0.09, 0.0, 0), Vector3(0.09, 0.0, zf), Vector3(-0.09, 0.0, zf), Vector3.DOWN)
		"console":
			# Konsole unter dem Kranzgesims (feste Größe): oben tief, unten flach (S-Form vereinfacht in drei Stufen)
			_box(st, -0.07, 0.07, -0.10, 0.0, 0.26)
			_box(st, -0.07, 0.07, -0.22, -0.10, 0.17)
			_box(st, -0.07, 0.07, -0.34, -0.22, 0.08)
		"pil":
			# Pilaster-/Lisenenschaft, Höhe 1 (auf die Höhe skaliert), mit vertieftem Spiegel
			_box(st, -0.22, -0.15, 0.0, 1.0, 0.09)
			_box(st, 0.15, 0.22, 0.0, 1.0, 0.09)
			_box(st, -0.15, 0.15, 0.0, 1.0, 0.06)
		"cap":
			# Kapitell (feste Größe): Halsring, Echinus, Deckplatte
			_box(st, -0.24, 0.24, 0.0, 0.05, 0.11)
			_box(st, -0.27, 0.27, 0.05, 0.17, 0.14)
			_box(st, -0.31, 0.31, 0.17, 0.25, 0.18)
		"base":
			# Basis/Sockel des Pilasters (feste Größe)
			_box(st, -0.29, 0.29, 0.0, 0.16, 0.15)
			_box(st, -0.25, 0.25, 0.16, 0.24, 0.12)
		_:
			return null
	return st.commit()


# --- Verteilung an einer Wandkante -------------------------------------------------------------------
static func _h11(p: float) -> float:
	p = fposmod(p * 0.1031, 1.0)
	p *= p + 33.33
	p *= p + p
	return fposmod(p, 1.0)


static func edge(out: Dictionary, cell_of: Callable, levels_f: float, height: float, style: int, seed: float,
		p0: Vector2, p1: Vector2, ln: float, acc: float, nrm: Vector3, ref: float) -> void:
	## Trägt die Bauteile einer Straßenfassade in out ein: Schlüssel [modell, zelle] -> Array[Transform3D]
	## (gleiches Format wie die Balkone in buildings.gd). Stile: 0 Gründerzeit, 1 Barock/Sandstein, 6 Klinker.
	if not enabled or not (style in [0, 1, 6]) or height < 7.5 or ln < 4.0:
		return
	var tone := "s" if style == 1 else ("k" if style == 6 else "w")
	var levels := maxf(levels_f, 1.0)
	var fh := clampf(height / levels, 2.7, 4.6)
	var rows := int(floor(height / fh))
	var h1 := _h11(seed * 91.7)
	var h2 := _h11(seed * 13.1)
	var h3 := _h11(seed * 7.7)
	var pitch := 2.6
	var ww := 1.2
	var wh := 1.7
	var wy := 0.7
	match style:
		0:
			pitch = lerpf(2.3, 3.1, h1)
			ww = pitch * lerpf(0.40, 0.46, h2)
			wh = fh * 0.66
			wy = fh * 0.19
		1:
			pitch = lerpf(3.0, 4.2, h1)
			ww = pitch * 0.44
			wh = fh * 0.72
			wy = fh * 0.17
		6:
			pitch = lerpf(2.4, 3.0, h1)
			ww = pitch * 0.40
			wh = fh * 0.62
			wy = fh * 0.22
	var e := (p1 - p0) / ln
	var basis := Basis(Vector3.UP.cross(-nrm).normalized(), Vector3.UP, -nrm)
	var put := func(model: String, along: float, y: float, sx: float, sy: float) -> void:
		var wp := p0 + e * along
		var key := ["fr_%s_%s" % [model, tone], cell_of.call(wp)]
		if not out.has(key):
			out[key] = []
		(out[key] as Array).append(Transform3D(basis.scaled_local(Vector3(sx, sy, 1.0)), Vector3(wp.x, y, wp.y) + nrm * 0.01))
	# Fensterachsen
	var c0 := int(floor(acc / pitch))
	var c1 := int(floor((acc + ln) / pitch))
	for col in range(c0, c1 + 1):
		var along := float(col) * pitch + pitch * 0.5 - acc
		if along - ww * 0.5 - 0.3 < 0.0 or along + ww * 0.5 + 0.3 > ln:
			continue
		for r in range(1, rows):
			var y0 := ref + float(r) * fh + wy
			if float(r) * fh + wy + wh > height - 0.75:
				continue
			put.call("sill", along, y0 - 0.07, ww + 0.26, 1.0)
			put.call("jamb", along - ww * 0.5 - 0.065, y0, 1.0, wh)
			put.call("jamb", along + ww * 0.5 + 0.065, y0, 1.0, wh)
			var yl := y0 + wh + 0.03
			put.call("lintel", along, yl, ww + 0.26, 1.0)
			if style == 1:
				put.call("key", along, yl - 0.02, 1.0, 1.0)
				if r == 1:
					put.call("ped_seg", along, yl + 0.26, ww + 0.36, ww + 0.36)
				elif r == 2:
					put.call("cornice", along, yl + 0.26, ww + 0.36, 1.0)
			elif r == 1:
				# Beletage: Dreiecks- oder Segmentgiebel, je Haus einheitlich
				put.call("ped_tri" if h3 < 0.55 else "ped_seg", along, yl + 0.26, ww + 0.36, ww + 0.36)
			elif r == 2 or (r == 3 and rows >= 5):
				put.call("cornice", along, yl + 0.26, ww + 0.36, 1.0)
	# Pilaster (Barock: zwischen allen Achsen; Gründerzeit/Klinker: Lisenen an den Hausecken)
	var y_p0 := ref + fh + 0.12
	var ch := 0.85 if style == 1 else 0.65            # Höhe des Kranzgesimses (buildings.gd _trim_strip)
	var y_p1 := ref + height - ch - 0.27
	if y_p1 - y_p0 > 3.0:
		var xs: Array = []
		if style == 1:
			for col in range(c0, c1 + 2):
				var x := float(col) * pitch - acc
				if x > 0.35 and x < ln - 0.35:
					xs.append(x)
		elif ln >= 7.0:
			xs = [0.3, ln - 0.3]
		for x in xs:
			put.call("base", x, y_p0, 1.0, 1.0)
			put.call("pil", x, y_p0 + 0.24, 1.0, y_p1 - y_p0 - 0.24)
			put.call("cap", x, y_p1, 1.0, 1.0)
	# Konsolen unter dem Kranzgesims
	var nc := int(floor(ln / 0.95))
	if nc >= 2:
		var step := ln / float(nc)
		for i in nc:
			put.call("console", (float(i) + 0.5) * step, ref + height - ch, 1.0, 1.0)
