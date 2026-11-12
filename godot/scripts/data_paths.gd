class_name DataPaths
extends RefCounted
## Basisordner der Spieldaten (Kacheln, Bus-/Bahnlinien, Straßenliste, Elbe).
## Entwicklung (Editor-Binary, `godot --path godot`): res://data/ (Symlink tiles -> data/processed/tiles).
## Exportiertes Spiel: Ordner "data" neben der Programmdatei (vom Installer entpackt), ersatzweise
## user://data. Überschreibbar mit der Umgebungsvariablen MAP44_DATA=<ordner>.

static var _root := ""


static func root() -> String:
	if _root != "":
		return _root
	var env := OS.get_environment("MAP44_DATA")
	if env != "":
		_root = env.trim_suffix("/").trim_suffix("\\") + "/"
	elif not OS.has_feature("template"):
		_root = "res://data/"
	else:
		_root = OS.get_executable_path().get_base_dir() + "/data/"
		for c in [_root, OS.get_user_data_dir() + "/data/"]:
			if DirAccess.dir_exists_absolute(c + "tiles"):
				_root = c
				break
	return _root


static func file(rel: String) -> String:
	return root() + rel
