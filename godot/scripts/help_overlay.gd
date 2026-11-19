class_name HelpOverlay
extends CanvasLayer
## Übersicht aller Befehle (Taste H): Tastatur und Gamepad nebeneinander, nach Bereichen geordnet.

const SECTIONS := [
	["Fahren", [
		["Gas / Bremse und Rückwärts", "W / S  oder  ↑ / ↓", "RT / LT"],
		["Lenken", "A / D  oder  ← / →", "linker Stick"],
		["Handbremse", "Leertaste", "RB"],
		["Hupe", "X", "L3"],
		["Licht", "L", "Steuerkreuz ↑"],
		["Hoch- / Runterschalten", "E / Q", "A / X"],
		["Automatik / Handschaltung", "F", "R3"],
		["Tempomat an/aus, ±5 km/h", "V,  . / ,  oder  Num + / −", "Steuerkreuz ↓, ← / →"],
		["Wagen zurücksetzen", "R", "B"],
		["Reparieren", "F5", "B zweimal"],
	]],
	["Kamera und Karte", [
		["Kamera wechseln", "C", "Y"],
		["Umsehen", "–", "rechter Stick"],
		["Zurückschauen (halten)", "B", "LB"],
		["Karte", "M", "Back/View"],
		["Routenspur an/aus", "F7", "–"],
	]],
	["Taxi", [
		["Taxi-Modus / freie Fahrt", "K", "–"],
		["Auftrag 1 / 2 / 3 annehmen", "1 / 2 / 3", "LB + A / X / Y"],
		["Andere Aufträge / Auftrag abbrechen", "N", "LB + B"],
	]],
	["Welt und Anzeige", [
		["Uhrzeit vor / zurück", "T / G", "Steuerkreuz → / ← (ohne Tempomat)"],
		["Wetter wechseln", "F6", "–"],
		["Grafikqualität", "F2", "–"],
		["Schaden an/aus", "F4", "–"],
		["Straße wählen (Teleport)", "F3", "–"],
		["Eingabe-Anzeige", "F1", "–"],
		["Pause / Menü", "Esc", "Start"],
		["Diese Hilfe", "H", "–"],
	]],
]

var _root: Control


func _ready() -> void:
	layer = 60
	process_mode = Node.PROCESS_MODE_ALWAYS
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.visible = false
	add_child(_root)
	var dim := ColorRect.new()
	dim.color = Color(0.02, 0.03, 0.05, 0.72)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(dim)
	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(center)
	var panel := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.09, 0.12, 0.94)
	sb.border_color = Color(0.36, 0.76, 1.0, 0.7)
	sb.set_border_width_all(2)
	sb.set_corner_radius_all(10)
	sb.set_content_margin_all(22)
	panel.add_theme_stylebox_override("panel", sb)
	center.add_child(panel)
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 10)
	panel.add_child(vb)
	var title := Label.new()
	title.text = "Befehle"
	title.add_theme_font_size_override("font_size", 26)
	title.add_theme_color_override("font_color", Color(0.36, 0.76, 1.0))
	vb.add_child(title)
	var hb := HBoxContainer.new()
	hb.add_theme_constant_override("separation", 34)
	vb.add_child(hb)
	var cols := [VBoxContainer.new(), VBoxContainer.new()]
	for c in cols:
		(c as VBoxContainer).add_theme_constant_override("separation", 8)
		hb.add_child(c)
	for si in SECTIONS.size():
		var sec: Array = SECTIONS[si]
		var col: VBoxContainer = cols[0] if si == 0 else cols[1]
		var head := Label.new()
		head.text = String(sec[0])
		head.add_theme_font_size_override("font_size", 18)
		head.add_theme_color_override("font_color", Color(1.0, 0.86, 0.45))
		col.add_child(head)
		var grid := GridContainer.new()
		grid.columns = 3
		grid.add_theme_constant_override("h_separation", 22)
		grid.add_theme_constant_override("v_separation", 3)
		col.add_child(grid)
		for txt in ["", "Tastatur", "Gamepad"]:
			var hl := Label.new()
			hl.text = txt
			hl.add_theme_font_size_override("font_size", 12)
			hl.add_theme_color_override("font_color", Color(0.6, 0.65, 0.7))
			grid.add_child(hl)
		for row in sec[1]:
			for k in 3:
				var l := Label.new()
				l.text = String(row[k])
				l.add_theme_font_size_override("font_size", 15)
				l.add_theme_color_override("font_color", Color(0.93, 0.94, 0.95) if k == 0 else Color(0.75, 0.88, 1.0))
				grid.add_child(l)
	var foot := Label.new()
	foot.text = "H oder Esc schließt diese Übersicht"
	foot.add_theme_font_size_override("font_size", 13)
	foot.add_theme_color_override("font_color", Color(0.6, 0.65, 0.7))
	vb.add_child(foot)
	if OS.has_environment("DRESDEN_HELP"):
		_root.visible = true                       # Diagnose: Übersicht von Anfang an zeigen


func toggle() -> void:
	_root.visible = not _root.visible


func is_open() -> bool:
	return _root != null and _root.visible


func close() -> void:
	if _root:
		_root.visible = false
