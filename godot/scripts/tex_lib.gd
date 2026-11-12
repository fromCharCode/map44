class_name TexLib
extends RefCounted
## Lädt PBR-Texturen (albedo/normal/roughness) zur Laufzeit und baut Texture2DArrays.

const TERRAIN_LAYERS: Array[String] = [
	"asphalt_new", "asphalt_worn", "sidewalk", "cobble", "paving_sandstone", "gravel",
	"grass", "grass_wild", "forest_floor", "mud_bank", "concrete", "sandstone",
]
const DEFAULT_TILE := 3.0
const ROOT := "res://assets/textures/"

static var _manifest: Dictionary = {}


static func tile_size(name: String) -> float:
	if _manifest.is_empty():
		var p := ROOT + "MANIFEST.json"
		if FileAccess.file_exists(p):
			var d = JSON.parse_string(FileAccess.get_file_as_string(p))
			if d is Dictionary:
				_manifest = d
			elif d is Array:
				for e in d:
					if e is Dictionary and e.has("name"):
						_manifest[e["name"]] = e
	var e = _manifest.get(name, null)
	if e is Dictionary and e.has("tile_size_m"):
		return float(e["tile_size_m"])
	if _manifest.has("materials") and _manifest["materials"] is Dictionary:
		var m = _manifest["materials"].get(name, null)
		if m is Dictionary and m.has("tile_size_m"):
			return float(m["tile_size_m"])
	return DEFAULT_TILE


static func _load(path: String, size: int, fallback: Color, fmt: int = Image.FORMAT_RGBA8) -> Image:
	var img := Image.new()
	if FileAccess.file_exists(path) and img.load(path) == OK:
		pass
	else:
		img = Image.create_empty(size, size, false, Image.FORMAT_RGBA8)
		img.fill(fallback)
	img.convert(fmt)
	if img.get_width() != size or img.get_height() != size:
		img.resize(size, size, Image.INTERPOLATE_LANCZOS)
	img.generate_mipmaps()
	return img


static func load_set(name: String, size: int = 1024) -> Dictionary:
	return {"albedo": image(name, "albedo", size), "normal": image(name, "normal", size), "rough": image(name, "rough", size)}


static func tex(img: Image) -> ImageTexture:
	return ImageTexture.create_from_image(img)


# --- Gemeinsame, GPU-komprimierte Texturen ------------------------------------------------------------
# Früher dekodierte jede Kachel ~40 JPGs (je ~200 ms für Dekodieren + Mipmaps) und legte eigene unkomprimierte
# Kopien an (5,6 MB je Textur). Jetzt: einmal laden, BC-komprimieren (Albedo BC1, Normalen BC5 = nur XY,
# Rauheit BC4), auf Platte zwischenspeichern (user://texcache) und von allen Kacheln teilen.
# Shader, die Normalen selbst auswerten, müssen Z rekonstruieren (BC5 liefert z = 0) – siehe unpack_normal.
const _FILES := {"albedo": "albedo.jpg", "normal": "normal.jpg", "rough": "roughness.jpg"}
const _FALLBACK := {"albedo": Color(0.5, 0.5, 0.5), "normal": Color(0.5, 0.5, 1.0), "rough": Color(0.8, 0.8, 0.8)}
const SHARED_SETS := ["plaster_a", "plaster_b", "brick", "concrete", "roof_tiles", "sandstone", "asphalt_new"]
const CACHE_DIR := "user://texcache/"
const CACHE_VER := 1
const BAKED_DIR := "res://texcache/"
static var bake_dir := ""            # nur beim Vorbacken gesetzt (scripts/dev/bake_textures.gd)
static var _tex := {}
static var _mats := {}
static var _lock := Mutex.new()


static func image(name: String, kind: String, size: int = 1024) -> Image:
	## Komprimiertes Bild mit Mipmaps (Plattencache, wird bei neuerer Quelldatei neu erzeugt).
	var src := ROOT + name + "/" + String(_FILES[kind])
	var fname := "%s_%s_%d_v%d.res" % [name, kind, size, CACHE_VER]
	var cp := (bake_dir if bake_dir != "" else CACHE_DIR) + fname
	# Exportiertes Spiel: vorgebackene Bilder im Paket (res://texcache, tools/package_release.sh) – die
	# Exportvorlagen können weder BC komprimieren noch die rohen JPGs lesen (im Paket liegen nur Importe)
	if bake_dir == "" and ResourceLoader.exists(BAKED_DIR + fname):
		var bim = ResourceLoader.load(BAKED_DIR + fname, "Image", ResourceLoader.CACHE_MODE_IGNORE)
		if bim is Image and not (bim as Image).is_empty():
			return bim
	if bake_dir == "" and FileAccess.file_exists(cp) and (not FileAccess.file_exists(src) or FileAccess.get_modified_time(cp) >= FileAccess.get_modified_time(src)):
		var im = ResourceLoader.load(cp, "Image", ResourceLoader.CACHE_MODE_IGNORE)
		if im is Image and not (im as Image).is_empty():
			return im
	var img := _load(src, size, _FALLBACK[kind], Image.FORMAT_R8 if kind == "rough" else Image.FORMAT_RGBA8)
	if kind == "albedo":
		img.compress(Image.COMPRESS_S3TC, Image.COMPRESS_SOURCE_SRGB)       # BC1
	elif kind == "normal":
		img.compress(Image.COMPRESS_S3TC, Image.COMPRESS_SOURCE_NORMAL)     # BC5 (RG)
	else:
		img.compress(Image.COMPRESS_S3TC, Image.COMPRESS_SOURCE_GENERIC)    # BC4 (R)
	DirAccess.make_dir_recursive_absolute(cp.get_base_dir())
	ResourceSaver.save(img, cp, ResourceSaver.FLAG_COMPRESS)
	return img


static func texture(name: String, kind: String, size: int = 1024) -> Texture2D:
	var key := "%s|%s|%d" % [name, kind, size]
	_lock.lock()
	var t = _tex.get(key)
	_lock.unlock()
	if t != null:
		return t
	# Laden/Erzeugen außerhalb der Sperre (RenderingServer-Aufrufe brauchen ggf. den Haupt-Thread)
	var nt := ImageTexture.create_from_image(image(name, kind, size))
	_lock.lock()
	if not _tex.has(key):
		_tex[key] = nt
	t = _tex[key]
	_lock.unlock()
	return t


static func tri_material(name: String, tint: float) -> StandardMaterial3D:
	## Gemeinsames Triplanar-Material (Welt-Koordinaten) einer Texturart, für alle Kacheln dasselbe.
	var key := "tri|%s|%.3f" % [name, tint]
	_lock.lock()
	var m = _mats.get(key)
	_lock.unlock()
	if m != null:
		return m
	var nm := StandardMaterial3D.new()
	nm.albedo_texture = texture(name, "albedo")
	nm.albedo_color = Color(tint, tint, tint)
	nm.normal_enabled = true
	nm.normal_texture = texture(name, "normal")
	nm.roughness_texture = texture(name, "rough")
	nm.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED
	nm.uv1_triplanar = true
	nm.uv1_world_triplanar = true
	var sc := 1.0 / tile_size(name)
	nm.uv1_scale = Vector3(sc, sc, sc)
	return shared_material(key, nm)


static func shared_material(key: String, made: Material) -> Material:
	## Legt ein Material unter key ab (erstes gewinnt) und gibt das geteilte zurück.
	_lock.lock()
	if not _mats.has(key):
		_mats[key] = made
	var r: Material = _mats[key]
	_lock.unlock()
	return r


static func get_shared(key: String) -> Material:
	_lock.lock()
	var r = _mats.get(key)
	_lock.unlock()
	return r


static func prewarm() -> void:
	## Im Haupt-Thread vor dem ersten Kachelbau: alle gemeinsamen Texturen bereitstellen.
	tile_size("asphalt_new")          # Manifest einmal im Haupt-Thread lesen
	for nm in SHARED_SETS:
		for kind in ["albedo", "normal", "rough"]:
			texture(nm, kind)


static func build_arrays(names: Array, size: int = 1024) -> Dictionary:
	var a: Array[Image] = []
	var n: Array[Image] = []
	var r: Array[Image] = []
	var tiles := PackedFloat32Array()
	for nm in names:
		var s := load_set(nm, size)
		a.append(s["albedo"])
		n.append(s["normal"])
		r.append(s["rough"])
		tiles.append(tile_size(nm))
	var ta := Texture2DArray.new()
	ta.create_from_images(a)
	var tn := Texture2DArray.new()
	tn.create_from_images(n)
	var tr := Texture2DArray.new()
	tr.create_from_images(r)
	return {"albedo": ta, "normal": tn, "rough": tr, "tiles": tiles}


static func noise_texture(size: int = 512, freq: float = 0.02, seed_v: int = 1) -> ImageTexture:
	var fn := FastNoiseLite.new()
	fn.seed = seed_v
	fn.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	fn.frequency = freq
	fn.fractal_type = FastNoiseLite.FRACTAL_FBM
	fn.fractal_octaves = 4
	var img := fn.get_seamless_image(size, size)
	img.convert(Image.FORMAT_RGBA8)
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)
