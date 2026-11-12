"""Teil-Manifeste (engine + sfx) zu godot/assets/audio/MANIFEST.json und LICENSES.md
zusammenfuehren und gegen die tatsaechlich vorhandenen OGG-Dateien pruefen."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import alib  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
AUD = ROOT / "godot" / "assets" / "audio"

ORDER = ["engine", "car", "impact", "bus", "tram", "ambience"]


def main():
    entries = []
    for part in ("engine_manifest.json", "sfx_manifest.json"):
        entries += json.loads((HERE / "out" / part).read_text())
    entries = [e for e in entries if "file" in e]
    files_on_disk = {p.relative_to(AUD).as_posix() for p in AUD.rglob("*.ogg")}
    listed = {e["file"] for e in entries}
    missing = listed - files_on_disk
    extra = files_on_disk - listed
    if missing or extra:
        raise SystemExit(f"Manifest/Dateien passen nicht: fehlend={sorted(missing)} unerwartet={sorted(extra)}")

    sounds = []
    for e in entries:
        src = e["sources"][0]
        path = AUD / e["file"]
        n = alib.ogg_length(path)
        out = {
            "file": e["file"],
            "res_path": f"res://assets/audio/{e['file']}",
            "kind": e["kind"],
            "rpm": e.get("rpm"),
            "load": e.get("load", "none"),
            "loop": bool(e["loop"]),
            "duration": round(n / alib.SR, 4) if n else e["duration"],
            "samples": n,
            "channels": e.get("channels", 1),
            "lufs": e["lufs"],
            "peak_dbfs": e["peak_dbfs"],
            "license": src["license"],
            "license_url": src["license_url"],
            "author": src["author"],
            "source_title": src["title"],
            "source_url": src["source_url"],
        }
        for k in ("vehicle", "engine", "mic", "firing_hz", "load_detail", "rpm_range_in_source",
                  "source_lufs", "line_hz", "tone_hz", "period_hz", "source_time_s", "seam_check",
                  "method", "note"):
            if k in e:
                out[k] = e[k]
        sounds.append(out)
    sounds.sort(key=lambda s: (ORDER.index(s["file"].split("/")[0]), s["file"]))

    def stage_list(pred):
        return sorted(({"rpm": s["rpm"], "file": s["file"]} for s in sounds if pred(s)),
                      key=lambda d: d["rpm"])

    eng = [s for s in sounds if s["kind"] in ("engine_loop", "engine_idle")]
    sets = {
        "player_idle": stage_list(lambda s: s in eng and s.get("vehicle") == "player" and s["kind"] == "engine_idle"),
        "player_on": stage_list(lambda s: s in eng and s.get("vehicle") == "player" and s["load"] == "on"),
        "player_off_overrun": stage_list(lambda s: s in eng and s.get("vehicle") == "player"
                                         and s.get("load_detail") == "overrun_dyno_sweep"),
        "player_off_neutral": stage_list(lambda s: s in eng and s.get("vehicle") == "player"
                                         and s.get("load_detail") in ("no_load_neutral", "idle_neutral")),
        "ai": stage_list(lambda s: s in eng and s.get("vehicle") == "ai"),
    }
    manifest = {
        "format": "OGG Vorbis q6, 44,1 kHz; positionsbezogene Klaenge mono, Atmos (ambience/) stereo",
        "loudness": ("Motor-Loops alle -16 LUFS (untereinander angeglichen; 'source_lufs' = Pegel vor der "
                     "Angleichung, nur innerhalb derselben Aufnahmesession vergleichbar), Fahr-/Bus-/Tram-"
                     "Loops -18 LUFS, Atmos -20 bis -26 LUFS, Kurzklaenge auf Spitzenpegel (-1 bzw. -3 dBFS)"),
        "rpm_method": ("Zuendfrequenz f gemessen (Kammfilter-Suche bzw. Verfolgung der staerksten Linie); "
                       "Viertakt-Vierzylinder: rpm = 30 * f. Sweep-Stufen sind auf die Zieldrehzahl flach "
                       "gerechnet (Toleranz < 0,1 %)."),
        "engine_sets": sets,
        "sounds": sounds,
    }
    (AUD / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")

    # ---------------------------------------------------------------- LICENSES.md
    srcs = {}
    for s in sounds:
        key = s["source_url"]
        srcs.setdefault(key, {"title": s["source_title"], "author": s["author"],
                              "license": s["license"], "license_url": s["license_url"], "files": []})
        srcs[key]["files"].append(s["file"])
    lic_set = sorted({v["license"] for v in srcs.values()})
    lines = [
        "# Audio-Lizenzen",
        "",
        "Alle Klaenge in diesem Ordner sind aus Aufnahmen von freesound.org geschnitten und bearbeitet",
        "(Schnitt, Loop-Kreuzblenden, Hoch-/Tiefpass, Pegelangleichung, Motor-Loops zusaetzlich auf",
        "konstante Drehzahl umgerechnet). Verwendet wurden die HQ-Vorschaudateien der Freesound-Seiten",
        "(gleiche Lizenz wie das Original).",
        "",
        f"Vorkommende Lizenzen: {', '.join(lic_set)}.",
        "",
    ]
    if lic_set == ["CC0 1.0"]:
        lines += [
            "Alle Quellen stehen unter **CC0 1.0** (Public Domain Dedication,",
            "https://creativecommons.org/publicdomain/zero/1.0/). Eine Namensnennung ist nicht",
            "erforderlich; die Urheber sind unten trotzdem vollstaendig aufgefuehrt.",
            "",
        ]
    else:
        lines += ["Quellen unter CC BY muessen mit Urheber, Titel, Link und Lizenz genannt werden (siehe unten).", ""]
    lines += ["| Quelle (Titel) | Urheber | Lizenz | Link | verwendet in |", "|---|---|---|---|---|"]
    for url, v in sorted(srcs.items(), key=lambda kv: (kv[1]["author"].lower(), kv[1]["title"])):
        files = "<br>".join(v["files"])
        title = v["title"].replace("|", "/")
        lines.append(f"| {title} | {v['author']} | [{v['license']}]({v['license_url']}) | {url} | {files} |")
    lines.append("")
    (AUD / "LICENSES.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(sounds)} Dateien, {len(srcs)} Quellen, Lizenzen: {lic_set}")
    for k, v in sets.items():
        print(f"  {k}: {[d['rpm'] for d in v]}")


if __name__ == "__main__":
    main()
