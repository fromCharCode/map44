"""Setzt die Godot-Importoptionen der Unterholz-Modelle (nach dem ersten Godot-Import ausführen).

  .venv/bin/python tools/blender/veg_set_import.py && ~/.local/bin/godot --headless --path godot --import

* import_script/path -> veg_post_import.gd (Vertexfarbe = AO einheitlich als Albedo-Faktor)
* meshes/generate_lods=false für Kartenmodelle (Auto-LOD zerstört einzelne Alpha-Karten)
"""
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
VEG = os.path.join(HERE, "..", "..", "godot", "assets", "models", "vegetation")
CARDS = {"bush_a", "bush_b", "bush_young_tree", "fern", "grass_tuft", "grass_tall", "heather"}
SCRIPT = 'import_script/path="res://assets/models/vegetation/veg_post_import.gd"'

for p in sorted(glob.glob(os.path.join(VEG, "*.glb.import"))):
    name = os.path.basename(p)[:-len(".glb.import")]
    s = open(p).read()
    s2 = re.sub(r'^import_script/path=.*$', SCRIPT, s, flags=re.M)
    lods = "false" if name in CARDS else "true"
    s2 = re.sub(r'^meshes/generate_lods=.*$', f"meshes/generate_lods={lods}", s2, flags=re.M)
    if s2 != s:
        open(p, "w").write(s2)
        print("angepasst:", name)
