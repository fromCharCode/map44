"""Motor-Loops bauen (Spielerauto: Mercedes-Benz 190E-16V, Dyno-Session; KI-Autos: BMW 120d).

Ausgabe: godot/assets/audio/engine/*.ogg + Teil-Manifest tools/audio/out/engine_manifest.json
Diagnose (optional, --diag): Spektrogramme der Loops (3x hintereinander) im Scratch-Ordner.

Drehzahl-Messung: Zuendfrequenz f (Hz) der Auspuff-/Motorraumaufnahme; Viertakt-Vierzylinder
-> rpm = f * 60 / 2 = 30 * f. Konstantaufnahmen: Kammfilter-Suche um die Erwartung
(firing_freq_near). Sweeps: Verfolgung der staerksten Linie (= Zuendfrequenz) ab einem
manuell verifizierten Saatpunkt (track_peak), danach Ausschnitt flach gerechnet.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import alib  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "raw" / "audio_src"
OUT = ROOT / "godot" / "assets" / "audio" / "engine"
MAN = Path(__file__).resolve().parent / "out" / "engine_manifest.json"
DIAG = None
if "--diag" in sys.argv:
    DIAG = Path(sys.argv[sys.argv.index("--diag") + 1])
    DIAG.mkdir(parents=True, exist_ok=True)

TARGET_LUFS = -16.0
M190 = "fs_chippy569_190e"
BMW = "fs_giocosound_bmw120d"


def src(d, sid):
    return SRC / d / f"{sid}.ogg"


def meta(d, sid):
    m = json.loads((SRC / d / "sources.json").read_text())[str(sid)]
    return {k: m[k] for k in ("freesound_id", "title", "author", "source_url", "license", "license_url")}


def measure_rpm(loop, f_guess, rel=0.08, cyl_factor=30.0):
    f, _ = alib.firing_freq_near(loop, f_guess, rel=rel, nharm=8, seg=min(1.0, len(loop) / alib.SR))
    return f, f * cyl_factor


def finish(y, name, entry, sources, extra_note=None):
    y = alib.hp(y, 22.0)
    src_lufs = alib.lufs(y)
    y = alib.norm_lufs(y, TARGET_LUFS)
    # Loop-Naht bleibt erhalten: Filter/Gain sind zeitinvariant bzw. nullphasig auf dem
    # zyklischen Signal -> Rand per zyklischer Faltung (Padding) behandeln
    alib.save_ogg(y, OUT / f"{name}.ogg")
    entry.update({
        "file": f"engine/{name}.ogg",
        "loop": True,
        "duration": round(len(y) / alib.SR, 4),
        "lufs": round(alib.lufs(y), 2),
        "peak_dbfs": round(alib.peak_db(y), 2),
        "source_lufs": round(src_lufs, 2),
        "sources": sources,
    })
    if extra_note:
        entry["note"] = extra_note
    if DIAG is not None:
        alib.spectrogram_png(np.tile(y, 3), DIAG / f"{name}.png", fmax=1200, hop=0.005)
    return entry


def cyclic_hp(y, fc):
    """Hochpass ohne Naht-Artefakt: Loop zyklisch erweitern, filtern, Mitte nehmen."""
    n = len(y)
    z = np.concatenate([y, y, y])
    z = alib.hp(z, fc)
    return z[n:2 * n]


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    entries = []

    # ------------------------------------------------ Spielerauto, Konstantaufnahmen (D6, Auspuff)
    consts = [
        # sid, Saat-Linie (Hz), Harmonische k der Saat-Linie, load, detail, Namens-Praefix
        (162506, 86.0, 2, "on", "full_load_dyno", "player_on"),
        (162509, 85.2, 1, "on", "full_load_dyno", "player_on"),
        (162512, 206.9, 1, "on", "full_load_dyno", "player_on"),
        (162515, 35.6, 1, "off", "idle_neutral", "player_idle"),
        (162518, 81.0, 1, "off", "no_load_neutral", "player_neutral"),
        (162521, 209.9, 1, "off", "no_load_neutral", "player_neutral"),
    ]
    for sid, seed, k, load, detail, pre in consts:
        x = alib.load(src(M190, sid))
        dur = len(x) / alib.SR
        flat, f_mean, finfo = alib.stable_flat_region(x, seed, k, region_len=min(2.6, dur - 0.1))
        loop, info = alib.constant_loop(flat, f_mean, loop_len=2.0, xfade=0.15)
        f2, rpm = measure_rpm(loop, f_mean, rel=0.04)
        name = f"{pre}" if pre == "player_idle" else f"{pre}_{int(round(rpm / 10.0) * 10)}"
        e = {"kind": "engine_idle" if pre == "player_idle" else "engine_loop", "vehicle": "player",
             "engine": "Mercedes-Benz 190E-16V (R4, Benzin)", "mic": "Audix D6, ca. 30 cm hinter Auspuff",
             "rpm": int(round(rpm)), "firing_hz": round(f2, 2), "load": load, "load_detail": detail,
             "rpm_range_in_source": [int(round(finfo["f_min"] * 30)), int(round(finfo["f_max"] * 30))],
             "method": (f"konstant aufgenommen; ruhigster Abschnitt {finfo['t0']:.2f}-{finfo['t1']:.2f} s "
                        f"(Drehzahlschwankung {finfo['rel_std_pct']:.2f} % rms) auf mittlere Zuendfrequenz "
                        f"geglaettet, Loop aus ganzen Arbeitsspielen, Kreuzblende 0,15 s")}
        y = cyclic_hp(loop, 22.0)
        entries.append(finish_cyclic(y, name, e, [meta(M190, sid)]))
        print(f"{name:24s} rpm={rpm:6.0f} corr={info['corr']:.3f} dur={len(loop)/alib.SR:.2f} "
              f"std={finfo['rel_std_pct']:.2f}% src={finfo['f_min']*30:.0f}-{finfo['f_max']*30:.0f}")

    # ------------------------------------------------ Spielerauto, Sweeps
    sweeps = [
        # sid, seed_t, seed_f, t_from, t_to, load, detail, targets(rpm), half_span
        (162501, 2.1, 232.0, 0.0, 2.38, "on", "full_load_dyno_sweep", [3500, 4500, 5500], 0.12),
        (162504, 3.4, 132.0, 0.7, 7.75, "off", "overrun_dyno_sweep",
         [(1500, 0.10), (2500, 0.07), 3500, 4500, 5500], 0.06),
    ]
    for sid, ts, fs, t0, t1, load, detail, targets, hs in sweeps:
        x = alib.load(src(M190, sid))
        T, F = alib.track_peak(x, ts, fs, t_from=t0, t_to=t1)
        for tgt in targets:
            rpm_t, hs_t = tgt if isinstance(tgt, tuple) else (tgt, hs)
            ft = rpm_t / 30.0
            loop, info = alib.cycle_loop(x, T, F, ft, half_span=hs_t, loop_len=2.0, seed=rpm_t)
            f2, rpm = measure_rpm(loop, info["f_eff"], rel=0.04)
            pre = "player_on" if load == "on" else "player_off"
            name = f"{pre}_{int(round(rpm / 10.0) * 10)}"
            e = {"kind": "engine_loop", "vehicle": "player",
                 "engine": "Mercedes-Benz 190E-16V (R4, Benzin)", "mic": "Audix D6, ca. 30 cm hinter Auspuff",
                 "rpm": int(round(rpm)), "firing_hz": round(f2, 2), "load": load, "load_detail": detail,
                 "method": (f"aus Sweep geschnitten: Fenster {info['t0']:.2f}-{info['t1']:.2f} s "
                            f"(+-{info['span_pct']:.0f} % Drehzahl) auf konstante Zuendfrequenz "
                            f"umgerechnet, {info['grains']} Arbeitsspiele in zufaelliger Nachbar-Abfolge "
                            f"zirkulaer ueberblendet")}
            y = cyclic_hp(loop, 22.0)
            entries.append(finish_cyclic(y, name, e, [meta(M190, sid)]))
            print(f"{name:24s} rpm={rpm:6.0f} grains={info['grains']} win={info['t0']:.2f}-{info['t1']:.2f}")

    # ------------------------------------------------ KI-Autos: BMW 120d (Diesel R4), aussen
    bmw = [
        # sid, Saat (Hz), Hochpass (Hz), Stufe
        (401552, 27.9, 20.0, "idle"),
        (401556, 49.1, 22.0, "low"),
        (401555, 67.0, 22.0, "mid"),
        (401551, 85.0, 45.0, "high"),
    ]
    for sid, seed, hpf, tag in bmw:
        x = alib.load(src(BMW, sid))
        dur = len(x) / alib.SR
        flat, f_mean, finfo = alib.stable_flat_region(x, seed, 1, region_len=min(2.6, dur - 0.3))
        loop, info = alib.constant_loop(flat, f_mean, loop_len=2.0, xfade=0.15)
        f2, rpm = measure_rpm(loop, f_mean, rel=0.04)
        name = "ai_idle" if tag == "idle" else f"ai_{int(round(rpm / 10.0) * 10)}"
        e = {"kind": "engine_idle" if tag == "idle" else "engine_loop", "vehicle": "ai",
             "engine": "BMW 120d (R4, Diesel)", "mic": "Earthworks QTC30 + Rode NT4, aussen (Stereo -> Mono)",
             "rpm": int(round(rpm)), "firing_hz": round(f2, 2), "load": "off",
             "load_detail": "idle_neutral" if tag == "idle" else "no_load_neutral",
             "rpm_range_in_source": [int(round(finfo["f_min"] * 30)), int(round(finfo["f_max"] * 30))],
             "method": (f"Standgas/Konstantdrehzahl im Stand; Abschnitt {finfo['t0']:.2f}-{finfo['t1']:.2f} s "
                        f"geglaettet (Schwankung {finfo['rel_std_pct']:.2f} % rms), Loop aus ganzen "
                        f"Arbeitsspielen, Kreuzblende 0,15 s, Hochpass {hpf:.0f} Hz")}
        y = cyclic_hp(loop, hpf)
        entries.append(finish_cyclic(y, name, e, [meta(BMW, sid)]))
        print(f"{name:24s} rpm={rpm:6.0f} corr={info['corr']:.3f} dur={len(loop)/alib.SR:.2f} "
              f"std={finfo['rel_std_pct']:.2f}%")

    MAN.parent.mkdir(parents=True, exist_ok=True)
    MAN.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n")


def finish_cyclic(y, name, entry, sources):
    src_lufs = alib.lufs(y)
    g = 10 ** ((TARGET_LUFS - src_lufs) / 20)
    y = y * g
    ceil = 10 ** (-1.0 / 20)
    if np.max(np.abs(y)) > ceil:
        y = alib.soft_limit(y, ceil)
    alib.save_ogg(y, OUT / f"{name}.ogg")
    pre = alib.seam_report(y)
    post = alib.seam_report(alib.load_ogg_exact(OUT / f"{name}.ogg"))
    print(f"    seam pre-enc flux={pre['flux_z']:.2f} lvl={pre['level_z']:.2f} | "
          f"post-enc flux={post['flux_z']:.2f} lvl={post['level_z']:.2f}")
    entry.update({
        "file": f"engine/{name}.ogg",
        "loop": True,
        "duration": round(len(y) / alib.SR, 4),
        "lufs": round(alib.lufs(y), 2),
        "peak_dbfs": round(alib.peak_db(y), 2),
        "source_lufs": round(src_lufs, 2),
        "sources": sources,
        "seam_check": {"flux": round(post["flux_z"], 2), "level": round(post["level_z"], 2)},
    })
    if DIAG is not None:
        alib.spectrogram_png(np.tile(y, 3), DIAG / f"{name}.png", fmax=1200, hop=0.005)
    return entry


if __name__ == "__main__":
    build()
