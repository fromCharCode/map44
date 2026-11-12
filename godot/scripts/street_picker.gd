class_name StreetPicker
extends CanvasLayer
## Straßenwahl (F3): Namen tippen, Enter -> Taxi wird auf diese Straße gesetzt.

signal chosen(x: float, z: float, label: String)

var streets: Array = []
var panel: PanelContainer
var edit: LineEdit
var list: ItemList
var _shown: Array = []


func _ready() -> void:
	layer = 60
	process_mode = Node.PROCESS_MODE_ALWAYS
	visible = false
	var txt := FileAccess.get_file_as_string(DataPaths.file("streets.json"))
	var parsed = JSON.parse_string(txt)
	if parsed is Array:
		streets = parsed
	panel = PanelContainer.new()
	panel.set_anchors_preset(Control.PRESET_CENTER)
	panel.custom_minimum_size = Vector2(520, 420)
	panel.position = Vector2(-260, -210)
	add_child(panel)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	panel.add_child(box)
	var title := Label.new()
	title.text = "Auf eine Straße setzen"
	title.add_theme_font_size_override("font_size", 24)
	box.add_child(title)
	edit = LineEdit.new()
	edit.placeholder_text = "Straßenname tippen (z. B. Prager Straße) …"
	edit.text_changed.connect(_refresh)
	edit.text_submitted.connect(func(_t): _pick(maxi(list.get_selected_items()[0] if list.get_selected_items().size() > 0 else 0, 0)))
	edit.gui_input.connect(_edit_input)
	box.add_child(edit)
	list = ItemList.new()
	list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	list.item_activated.connect(_pick)
	box.add_child(list)
	var hint := Label.new()
	hint.text = "↑/↓ wählen · Enter setzen · Esc abbrechen"
	hint.add_theme_color_override("font_color", Color(1, 1, 1, 0.6))
	box.add_child(hint)


func _edit_input(ev: InputEvent) -> void:
	if ev is InputEventKey and ev.pressed:
		var sel: PackedInt32Array = list.get_selected_items()
		var cur := sel[0] if sel.size() > 0 else -1
		if ev.keycode == KEY_DOWN and cur < list.item_count - 1:
			list.select(cur + 1)
			list.ensure_current_is_visible()
			edit.accept_event()
		elif ev.keycode == KEY_UP and cur > 0:
			list.select(cur - 1)
			list.ensure_current_is_visible()
			edit.accept_event()
		elif ev.keycode == KEY_ESCAPE:
			close()
			edit.accept_event()


func _refresh(q: String = "") -> void:
	var ql := q.strip_edges().to_lower()
	var hits: Array = []
	for s in streets:
		var nm: String = s[0]
		var nl := nm.to_lower()
		if ql == "":
			hits.append([2, s[3], s])
		elif nl.begins_with(ql):
			hits.append([0, s[3], s])
		elif nl.contains(ql):
			hits.append([1, s[3], s])
	hits.sort_custom(func(a, b): return a[0] < b[0] or (a[0] == b[0] and a[1] < b[1]))
	list.clear()
	_shown.clear()
	for i in mini(hits.size(), 60):
		var s: Array = hits[i][2]
		list.add_item("%s   (%.1f km vom Altmarkt)" % [s[0], s[3]])
		_shown.append(s)
	if list.item_count > 0:
		list.select(0)


func _pick(i: int) -> void:
	if i < 0 or i >= _shown.size():
		return
	var s: Array = _shown[i]
	close()
	chosen.emit(float(s[1]), float(s[2]), String(s[0]))


func toggle() -> void:
	if visible:
		close()
	else:
		open()


func open() -> void:
	visible = true
	get_tree().paused = true
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	edit.text = ""
	_refresh("")
	edit.grab_focus()


func close() -> void:
	visible = false
	get_tree().paused = false
	Input.mouse_mode = Input.MOUSE_MODE_HIDDEN
