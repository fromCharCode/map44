class_name LedSign
extends RefCounted
## LED-Zielanzeige wie bei der DVB (Bus und Straßenbahn): Liniennummer groß links, Ziel daneben (bei langen
## Zielen zweizeilig); number_only = nur die Nummer (Heckanzeige). Texte als Label3D (bernsteinfarben, unbeleuchtet).

const COLOR := Color(1.0, 0.62, 0.1)


static func clean_dest(to: String) -> String:
	var dest := to
	for pre in ["Dresden, ", "Dresden "]:
		if dest.begins_with(pre) and dest.length() > pre.length() + 3:
			dest = dest.substr(pre.length())
	return dest


## Baut die Texte einer Anzeige. basis: +Z = Anzeigenormale (lesbar von dort), +X = rechts aus Sicht des
## Betrachters. center: Anzeigemitte (bereits vor der Fläche). Gibt die erzeugten Label3D zurück.
static func make(parent: Node3D, ref: String, dest: String, basis: Basis, center: Vector3, w: float, hgt: float,
		number_only := false, vis_range := 120.0, color := COLOR) -> Array:
	var res: Array = []
	if ref == "" and dest == "":
		return res
	if number_only or dest == "":
		res.append(_label(parent, ref, basis, center, w * 0.9, hgt * 0.86, vis_range, color))
		return res
	var num_w := clampf(hgt * 0.5 * maxf(float(ref.length()), 2.0) + 0.04, 0.16, w * 0.34)
	if ref != "":
		res.append(_label(parent, ref, basis, center + basis * Vector3(-w * 0.5 + num_w * 0.5 + 0.02, 0, 0), num_w, hgt * 0.86, vis_range, color))
	else:
		num_w = 0.0
	var avail := w - num_w - 0.06
	var dc := center + basis * Vector3(w * 0.5 - avail * 0.5 - 0.02, 0, 0)
	# einzeilig, solange die Schrift dabei nicht auf unter 70 % der vollen Zeilenhöhe schrumpft
	var one := fit(dest, avail, hgt * 0.62) / fit("X", 1000.0, hgt * 0.62)
	if one >= 0.7 or not dest.contains(" "):
		res.append(_label(parent, dest, basis, dc, avail, hgt * 0.62, vis_range, color))
	else:
		# zweizeilig: an Leerzeichen nahe der Mitte trennen
		var best := -1
		for i in dest.length():
			if dest[i] == " " and (best < 0 or absi(i - dest.length() / 2) < absi(best - dest.length() / 2)):
				best = i
		var l1 := dest.substr(0, best).strip_edges()
		var l2 := dest.substr(best + 1).strip_edges()
		res.append(_label(parent, l1 + "\n" + l2, basis, dc, avail, hgt * 0.84, vis_range, color))
	return res


static func fit(txt: String, w: float, h: float) -> float:
	## Pixelgröße, mit der txt (Schriftgröße 64, ggf. mehrzeilig) exakt in w x h passt
	var f: Font = ThemeDB.fallback_font
	var sz := f.get_multiline_string_size(txt, HORIZONTAL_ALIGNMENT_CENTER, -1, 64)
	return minf(w / maxf(sz.x, 1.0), h / maxf(sz.y, 1.0))


static func _label(parent: Node3D, txt: String, basis: Basis, pos: Vector3, w: float, h: float, vis_range: float,
		color := COLOR) -> Label3D:
	var lb := Label3D.new()
	lb.text = txt
	lb.font_size = 64
	lb.outline_size = 0
	lb.line_spacing = -6.0
	lb.pixel_size = fit(txt, w, h)
	lb.modulate = color
	lb.shaded = false
	lb.double_sided = false
	lb.alpha_cut = Label3D.ALPHA_CUT_DISCARD
	lb.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	lb.visibility_range_end = vis_range
	lb.transform = Transform3D(basis, pos)
	parent.add_child(lb)
	return lb
