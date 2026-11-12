"""Kurzklaenge, Fahrgeraeusche, Aufpralle, Bus, Strassenbahn und Atmos bauen.

Ausgabe: godot/assets/audio/{car,impact,bus,tram,ambience}/*.ogg
         + Teil-Manifest tools/audio/out/sfx_manifest.json
Alle Schnittzeiten beziehen sich auf die Freesound-HQ-Vorschau in data/raw/audio_src/<quelle>/.
Positionsbezogene Klaenge mono, Atmos stereo; 44,1 kHz; Vorbis q6.
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
OUT = ROOT / "godot" / "assets" / "audio"
MAN = Path(__file__).resolve().parent / "out" / "sfx_manifest.json"
SR = alib.SR

ENTRIES = []
_cache = {}


def src_path(ref):
    d, sid = ref.split("/")
    return SRC / d / f"{sid}.ogg"


def meta(ref):
    d, sid = ref.split("/")
    m = json.loads((SRC / d / "sources.json").read_text())[sid]
    return {k: m[k] for k in ("freesound_id", "title", "author", "source_url", "license", "license_url")}


def load(ref):
    if ref not in _cache:
        _cache[ref] = alib.load(src_path(ref))
    return _cache[ref]


def emit(y, rel, kind, ref, loop, note, peak_target=None, lufs_target=None, extra=None,
         refs=None):
    """Normieren, als OGG schreiben, Manifest-Eintrag anlegen."""
    y = np.asarray(y, dtype=np.float64)
    if lufs_target is not None:
        cur = alib.lufs(y)
        y = y * 10 ** ((lufs_target - cur) / 20)
        ceil = 10 ** (-1.0 / 20)
        if np.max(np.abs(y)) > ceil:
            y = alib.soft_limit(y, ceil)
    elif peak_target is not None:
        y = y * (10 ** (peak_target / 20) / (np.max(np.abs(y)) + 1e-12))
    path = OUT / rel
    alib.save_ogg(y, path)
    e = {"file": rel, "kind": kind, "rpm": None, "load": "none", "loop": loop,
         "duration": round(len(y) / SR, 4), "channels": 1,
         "lufs": round(alib.lufs(y), 2), "peak_dbfs": round(alib.peak_db(y), 2),
         "sources": [meta(r) for r in (refs or [ref])], "note": note}
    if loop:
        dec = alib.load_ogg_exact(path)
        s = alib.seam_report(dec)
        e["seam_check"] = {"flux": round(s["flux_z"], 2), "level": round(s["level_z"], 2)}
    if extra:
        e.update(extra)
    ENTRIES.append(e)
    print(f"{rel:38s} {e['duration']:6.2f}s lufs={e['lufs']:6.1f} peak={e['peak_dbfs']:5.1f}"
          + (f" seam={e['seam_check']}" if loop else ""))
    return e


def emit_stereo(xy, rel, kind, ref, note, lufs_target):
    cur = alib.lufs_stereo(xy)
    g = 10 ** ((lufs_target - cur) / 20)
    xy = xy * g
    ceil = 10 ** (-1.0 / 20)
    if np.max(np.abs(xy)) > ceil:
        xy = np.stack([alib.soft_limit(xy[0], ceil), alib.soft_limit(xy[1], ceil)])
    path = OUT / rel
    alib.save_ogg_stereo(xy, path)
    mono = 0.5 * (alib.load_ogg_exact(path))  # nur fuer Nahtpruefung (Downmix)
    s = alib.seam_report(mono)
    e = {"file": rel, "kind": kind, "rpm": None, "load": "none", "loop": True,
         "duration": round(xy.shape[1] / SR, 4), "channels": 2,
         "lufs": round(alib.lufs_stereo(xy), 2), "peak_dbfs": round(alib.peak_db(xy.ravel()), 2),
         "sources": [meta(ref)], "note": note,
         "seam_check": {"flux": round(s["flux_z"], 2), "level": round(s["level_z"], 2)}}
    ENTRIES.append(e)
    print(f"{rel:38s} {e['duration']:6.2f}s lufs={e['lufs']:6.1f} peak={e['peak_dbfs']:5.1f} seam={e['seam_check']}")
    return e


def loop_mono(ref, length, xfade, t_from=0.0, t_to=None, hpf=None, lpf=None, start=None,
              max_jump_db=8.0):
    x = load(ref)
    if hpf:
        x = alib.hp(x, hpf, order=2)
    if lpf:
        x = alib.lp(x, lpf, order=2)
    if start is None:
        start, info = alib.pick_stationary(x, length, t_from=t_from, t_to=t_to, xfade=xfade,
                                           max_jump_db=max_jump_db)
    y = alib.noise_loop(x, start, length, xfade)
    return y, start


def loop_stereo(ref, length, xfade, t_from=0.0, t_to=None, hpf=None, max_jump_db=8.0, start=None):
    xy = alib.load_stereo(src_path(ref))
    if hpf:
        xy = np.stack([alib.hp(xy[0], hpf), alib.hp(xy[1], hpf)])
    if start is None:
        mono = 0.5 * (xy[0] + xy[1])
        start, info = alib.pick_stationary(mono, length, t_from=t_from, t_to=t_to, xfade=xfade,
                                           max_jump_db=max_jump_db, win=0.25, step=0.5)
    out = np.stack([alib.noise_loop(xy[c], start, length, xfade) for c in (0, 1)])
    return out, start


def shot(ref, t0, t1, fin=0.003, fout=0.05, hpf=None, lpf=None):
    x = load(ref)
    if hpf:
        x = alib.hp(x, hpf, order=2)
    if lpf:
        x = alib.lp(x, lpf, order=2)
    return alib.one_shot(x, t0, t1, fin=fin, fout=fout)


def periodic_loop(x, f0, length, xfade):
    """Loop fuer periodische Klaenge (Hupe): Laenge = ganze Perioden von f0."""
    loop, info = alib.constant_loop(x, f0, loop_len=length, xfade=xfade, cyc_per_grain=1)
    return loop


# ============================================================================ Auto: Kurzklaenge
def car_short():
    M = "fs_chippy569_190e"
    # Anlasser (gleicher Motor wie die Spieler-Loops, Mikro D6 am Auspuff)
    y = shot(f"{M}/162525", 0.25, 2.9, fout=0.6, hpf=25)
    emit(y, "car/starter_long.ogg", "starter", f"{M}/162525", False,
         "Anlasser 190E-16V: Orgeln, Anspringen, Gasstoss, Abfallen Richtung Leerlauf (D6 am Auspuff); "
         "Ende ausgeblendet -> in player_idle ueberblenden", peak_target=-1.0)
    y = shot(f"{M}/162528", 1.15, 3.4, fout=0.5, hpf=25)
    emit(y, "car/starter_short.ogg", "starter", f"{M}/162528", False,
         "Anlasser 190E-16V: Orgeln + Anspringen mit kleinem Gasstoss (D6); Ende ausgeblendet", peak_target=-1.0)

    # Blinker (BMW, Innenraum): Relais "tick" (an) und "tack" (aus) abwechselnd
    ref = "fs_the_cri/545322"
    x = load(ref)
    ev = alib.transients(alib.hp(x, 300), 24, min_sep=0.2, t_from=2.3, t_to=45.0)
    # abwechselnd laut/leise -> zwei Gruppen nach Spitzenpegel
    pk = np.array([e[2] for e in ev])
    thr = np.median(pk)
    loud = [e for e in ev if e[2] >= thr]
    soft = [e for e in ev if e[2] < thr]
    for name, grp, desc in (("blinker_tick", loud, "Blinker-Relais 'tick' (lauterer Schlag)"),
                            ("blinker_tack", soft, "Blinker-Relais 'tack' (leiserer Schlag)")):
        # Ereignis mit dem besten Abstand zum Grundrauschen
        best = max(grp, key=lambda e: e[1])
        y = shot(ref, best[0] - 0.01, best[0] + 0.14, fin=0.002, fout=0.04, hpf=200)
        emit(y, f"car/{name}.ogg", "blinker", ref, False,
             f"{desc}, BMW-Innenraum; Schnitt ab {best[0]-0.01:.2f} s; Intervall im Original ca. 0,32 s "
             f"(tick und tack abwechselnd im Takt abspielen)", peak_target=-3.0,
             extra={"source_time_s": round(best[0] - 0.01, 3)})

    # Schaltvorgang: Schalthebel-Klacken (stehendes Auto), drei Varianten + Kupplung
    ref = "fs_kougloff/117558"
    x = load(ref)
    ev = alib.transients(x, 12, min_sep=1.0, t_from=0.5, t_to=61.0)
    good = []
    for t, rise, peak in sorted(ev, key=lambda e: -e[1]):
        seg = x[int((t - 0.02) * SR):int((t + 0.40) * SR)]
        if alib.peak_db(seg) > -3.0:   # heisse/uebersteuerte Ereignisse auslassen
            continue
        good.append((t, rise, peak))
        if len(good) == 3:
            break
    for i, (t, rise, peak) in enumerate(sorted(good), 1):
        y = shot(ref, t - 0.02, t + 0.40, fin=0.002, fout=0.12, hpf=60)
        emit(y, f"car/gear_shift_{i}.ogg", "gear_shift", ref, False,
             f"Schalthebel-Klacken (Gang einlegen, stehendes Auto), Schnitt ab {t-0.02:.2f} s",
             peak_target=-3.0, extra={"source_time_s": round(t - 0.02, 3)})
    y = shot("fs_j1987/123016", 0.05, 1.30, fin=0.005, fout=0.15, hpf=40)
    emit(y, "car/clutch.ogg", "clutch", "fs_j1987/123016", False,
         "Kupplungspedal treten (Volvo 740, Innenraum)", peak_target=-3.0)

    # Hupe: 190E-Zweiklang (330 + 396 Hz -> gemeinsame Periode 1/66 s). Die Aussenaufnahme
    # (NTG2) ist im Original uebersteuert (Plateaus bei 0 dBFS), daher die saubere
    # Innenraumaufnahme (NT1a auf dem Beifahrersitz) als Hauptversion.
    horn_set("fs_chippy569_190e/162541", (10.15, 10.65), "car/horn",
             "Hupe Mercedes 190E-16V (Zweiklang 330/396 Hz), Innenraum (Beifahrerkopf-Position), sauber")
    horn_set("fs_chippy569_190e/162540", (10.15, 10.65), "car/horn_ext",
             "Hupe Mercedes 190E-16V (Zweiklang 330/396 Hz), aussen ca. 1,5 m vor dem Auto; Quelle "
             "uebersteuert (leicht verzerrt), heller als die Innenraumversion")


def horn_set(ref, win, prefix, desc):
    x = alib.hp(load(ref), 120)
    t0, t1 = win
    seg = x[int(t0 * SR):int(t1 * SR)]
    # Pegel mit 30-ms-Fenster (2 Schwebungsperioden) im 5-ms-Raster
    n30, n5 = int(0.03 * SR), int(0.005 * SR)
    lv = np.array([20 * np.log10(np.sqrt(np.mean(seg[i:i + n30] ** 2)) + 1e-9)
                   for i in range(0, len(seg) - n30, n5)])
    imax = int(np.argmax(lv))
    plateau = lv >= lv[imax] - 3.0
    a = imax
    while a > 0 and plateau[a - 1]:
        a -= 1
    b = imax
    while b < len(lv) - 1 and plateau[b + 1]:
        b += 1
    onset = a
    while onset > 0 and lv[onset - 1] > lv[imax] - 30:
        onset -= 1
    sus0 = t0 + (a + 2) * 0.005          # 10 ms nach Plateaubeginn
    sus1 = t0 + b * 0.005 + 0.03 - 0.005  # Fensterende des letzten Plateau-Frames
    body = x[int(sus0 * SR):int(sus1 * SR)]
    f0, _ = alib.firing_freq_near(body, 66.0, rel=0.03, nharm=12, seg=len(body) / SR)
    period = 1.0 / f0
    xf = 0.02
    usable = len(body) / SR - xf - 0.002
    nper = max(2, int(usable / period))
    loop = alib.make_loop_cycles(body, f0, target_len=nper * period, xfade=xf, start=int(xf * SR))
    loop_start_abs = sus0 + xf
    y_start = x[int((t0 + onset * 0.005 - 0.01) * SR):int(loop_start_abs * SR)].copy()
    y_start = alib.fade(y_start, 0.004, 0.0)
    rel0 = loop_start_abs + len(loop) / SR   # Ende in Originalzeit fortsetzen
    y_end = x[int(rel0 * SR):int(min(t1, t0 + b * 0.005 + 0.35) * SR)].copy()
    y_end = alib.fade(y_end, 0.0, 0.1)
    g = 10 ** (-3.0 / 20) / max(np.max(np.abs(y_start)), np.max(np.abs(loop)), np.max(np.abs(y_end)))
    note = (f"{desc}. Grundperiode {period*1000:.2f} ms ({f0:.2f} Hz). Abspielfolge: *_start -> *_loop "
            "(beliebig oft) -> *_end; die drei Teile haben gemeinsamen Pegel")
    emit(y_start * g, f"{prefix}_start.ogg", "horn", ref, False, note)
    emit(loop * g, f"{prefix}_loop.ogg", "horn", ref, True, note,
         extra={"tone_hz": [330, 396], "period_hz": round(f0, 3)})
    emit(y_end * g, f"{prefix}_end.ogg", "horn", ref, False, note)


# ============================================================================ Fahrgeraeusche
def driving():
    # Reifenquietschen: tonaler Anteil ~0,95-1,1 kHz; Motorrumpeln per Hochpass entfernt
    y, s = loop_mono("fs_audible_edge/76804", 1.0, 0.12, t_from=8.0, t_to=9.35, hpf=350,
                     max_jump_db=12)
    emit(y, "car/tire_squeal_loop_1.ogg", "tire_squeal", "fs_audible_edge/76804", True,
         f"Reifenquietschen Volvo 740 (Handbremswende), Ausschnitt ab {s:.2f} s, Hochpass 350 Hz",
         lufs_target=-18.0)
    y, s = loop_mono("fs_audible_edge/71738", 1.0, 0.12, t_from=9.6, t_to=11.0, hpf=350,
                     max_jump_db=12)
    emit(y, "car/tire_squeal_loop_2.ogg", "tire_squeal", "fs_audible_edge/71738", True,
         f"Reifenquietschen Chrysler LHS in Kurve, Ausschnitt ab {s:.2f} s, Hochpass 350 Hz",
         lufs_target=-18.0)

    # Abrollen Asphalt (Innenraum, Autobahn), Kopfsteinpflaster (Innenraum, Kleinwagen)
    y, s = loop_mono("fs_vivelevent/817389", 4.0, 0.6, t_from=1.0, t_to=43.0, hpf=30, max_jump_db=6)
    emit(y, "car/roll_asphalt_loop.ogg", "rolling", "fs_vivelevent/817389", True,
         f"Reifen-Abrollgeraeusch Asphalt (Autobahn, im Innenraum aufgenommen), ab {s:.2f} s; "
         "Lautstaerke/Tonhoehe mit Geschwindigkeit skalieren", lufs_target=-18.0)
    y, s = loop_mono("fs_orlandorizo/591078", 4.0, 0.4, t_from=1.0, t_to=42.0, hpf=30, max_jump_db=14)
    emit(y, "car/roll_cobble_loop.ogg", "rolling", "fs_orlandorizo/591078", True,
         f"Kopfsteinpflaster (Kleinwagen, Innenraum, Klappern/Stoesse), ab {s:.2f} s", lufs_target=-18.0)
    # Fahrtwind
    y, s = loop_mono("fs_funwithsound/439242", 5.0, 0.8, t_from=2.0, t_to=118.0, hpf=40, max_jump_db=8)
    emit(y, "car/wind_loop.ogg", "wind", "fs_funwithsound/439242", True,
         f"Fahrtwind am offenen Fenster bei hoher Geschwindigkeit, ab {s:.2f} s", lufs_target=-18.0)


# ============================================================================ Aufpralle
def impacts():
    # leicht: Hand auf leere Karosserie (echtes Blech), vier ruhige Schlaege
    ref = "fs_harrisonlace/798843"
    x = load(ref)
    ev = alib.transients(x, 17, min_sep=0.9, t_from=0.0, t_to=26.0)
    # die ersten 10 Schlaege sind Einzelaufnahmen (Rest geschichtet) -> nur t < 14 s
    cand = [e for e in ev if e[0] < 14.0]
    cand = sorted(cand, key=lambda e: e[2])  # leiseste zuerst = "leicht"
    picked = []
    for t, rise, peak in cand:
        seg = x[int(t * SR):int((t + 1.0) * SR)]
        if alib.clip_fraction(seg, 0.99) > 0:
            continue
        picked.append(t)
        if len(picked) == 4:
            break
    for i, t in enumerate(sorted(picked), 1):
        y = shot(ref, max(0, t - 0.01), t + 0.9, fin=0.001, fout=0.25, hpf=40)
        emit(y, f"impact/impact_light_{i}.ogg", "impact_light", ref, False,
             f"Leichter Blechschlag (Hand auf Karosserie), Schnitt ab {max(0, t-0.01):.2f} s",
             peak_target=-1.0, extra={"source_time_s": round(max(0, t - 0.01), 3)})

    heavy = [
        ("fs_squareal/237375", 0.0, 3.6, "Schwerer Crash (geschichtet: Blech, Splitt, Glas)"),
        ("fs_magnuswaker/592388", 0.0, 2.2, "Schwerer Crash mit Glas (Blechpaneele)"),
        ("fs_lpa134/329516", 0.20, 2.6, "Motorhaube zugeknallt (Tiefgarage, Nachhall gekuerzt)"),
        ("fs_softwalls/449062", 0.55, 2.4, "Echter Auffahrunfall, Innenraum (Original uebersteuert)"),
    ]
    for i, (ref, t0, t1, desc) in enumerate(heavy, 1):
        y = shot(ref, t0, t1, fin=0.002, fout=0.6, hpf=30)
        clip = alib.clip_fraction(load(ref)[int(t0 * SR):int(t1 * SR)], 0.99)
        emit(y, f"impact/impact_heavy_{i}.ogg", "impact_heavy", ref, False,
             desc + (f"; Clipping-Anteil Quelle {clip*100:.3f} %" if clip > 0 else ""), peak_target=-1.0)

    glass = [
        ("fs_unfa/221528", 0.25, 1.4, "Glasscheibe zerschlagen (Stein)"),
        ("fs_chewiesmissus/244238", 0.12, 1.55, "Glas zerschmettern"),
    ]
    for i, (ref, t0, t1, desc) in enumerate(glass, 1):
        y = shot(ref, t0, t1, fin=0.002, fout=0.3, hpf=150)
        emit(y, f"impact/glass_break_{i}.ogg", "glass", ref, False, desc, peak_target=-1.0)

    # Bordstein/Fahrwerk: tieffrequente Stoesse aus Innenraumfahrt (Schlagloch, Gullydeckel)
    ref = "fs_orlandorizo/591079"
    x = load(ref)
    ev = alib.transients(x, 3, band=(30, 250), min_sep=3.0, t_from=1.0, t_to=87.0)
    for i, (t, rise, peak) in enumerate(ev, 1):
        y = shot(ref, max(0, t - 0.05), t + 0.6, fin=0.01, fout=0.25, hpf=25)
        emit(y, f"impact/bump_{i}.ogg", "bump", ref, False,
             f"Fahrwerksschlag (Schlagloch/Gullydeckel, Innenraum Kleinwagen), Schnitt ab {max(0, t-0.05):.2f} s, "
             f"Anstieg {rise:.0f} dB", peak_target=-1.0, extra={"source_time_s": round(max(0, t - 0.05), 3)})
    # Viehgitter-Rumpeln als laengeres Bordstein-/Pflasterrumpeln
    y = shot("fs_soundtracvkradio/345595", 0.85, 2.6, fin=0.01, fout=0.4, hpf=25)
    emit(y, "impact/rumble_grid.ogg", "bump", "fs_soundtracvkradio/345595", False,
         "Ueberfahren eines Viehgitters (Rumpelserie, z. B. fuer Bordstein-/Schwellenrumpeln)",
         peak_target=-1.0)


# ============================================================================ KI-Autos siehe build_engine
# ============================================================================ Bus
def bus():
    ref = "fs_rabbydaw/504866"
    x = load(ref)
    # Leerlauf (stehend, aussen) 0,5-6,5 s
    y, s = loop_mono(ref, 3.0, 0.4, t_from=0.4, t_to=6.6, hpf=30, max_jump_db=6)
    emit(y, "bus/bus_idle_loop.ogg", "bus_idle", ref, True,
         f"Linienbus (Diesel) Leerlauf, aussen, ab {s:.2f} s", lufs_target=-18.0)
    # Fahrt: Anfahrt unter Last; Grundlinie ~76 Hz (2. Harm. 153 Hz) fast konstant 11,3-13,6 s
    seg = x[int(11.2 * SR):int(13.8 * SR)]
    flat, fm, finfo = alib.stable_flat_region(seg, 153.0, 2, region_len=2.2, rel=0.04)
    loop, info = alib.constant_loop(flat, fm, loop_len=1.8, xfade=0.2, cyc_per_grain=12)
    loop = alib.hp(np.concatenate([loop] * 3), 30)[len(loop):2 * len(loop)]
    emit(loop, "bus/bus_drive_loop.ogg", "bus_drive", ref, True,
         f"Linienbus beim Anfahren unter Last (aussen), 11,2-13,8 s, Grundlinie {fm:.1f} Hz auf konstant "
         f"geglaettet (Schwankung {finfo['rel_std_pct']:.2f} %); Drehzahl unbekannt (Zylinderzahl unbekannt)",
         lufs_target=-18.0, extra={"line_hz": round(fm, 2)})
    # Druckluft: Ablassen ("pssst") - fuer Tueren und Absenken (Kneeling)
    ref = "fs_kyles/454420"
    for i, (t0, t1) in enumerate([(4.15, 5.35), (10.85, 12.0)], 1):
        y = shot(ref, t0, t1, fin=0.01, fout=0.2, hpf=120)
        emit(y, f"bus/bus_air_release_{i}.ogg", "bus_air", ref, False,
             f"Reisebus aussen: Druckluft ablassen ({t0:.2f}-{t1:.2f} s); fuer Tuer-Zischen und Absenken "
             "(Kneeling) verwendbar", peak_target=-3.0)
    y = shot(ref, 0.05, 1.35, fin=0.01, fout=0.2, hpf=200)
    emit(y, "bus/bus_brake_squeal.ogg", "bus_brake", ref, False,
         "Reisebus aussen: Bremsenquietschen beim Anhalten (0,05-1,35 s)", peak_target=-3.0)
    # Tueren
    y = shot("fs_babelfishtank/534977", 0.70, 2.30, fin=0.01, fout=0.4, hpf=100)
    emit(y, "bus/bus_door_open.ogg", "bus_door", "fs_babelfishtank/534977", False,
         "Bustuer oeffnet (Druckluft), Haltestelle, ca. 1 m entfernt", peak_target=-3.0)
    y = shot("fs_am7/520753", 1.75, 6.55, fin=0.01, fout=0.3, hpf=60)
    emit(y, "bus/bus_door_close.ogg", "bus_door", "fs_am7/520753", False,
         "Bustuer schliesst: Druckluftzischen + Anschlag (im Bus aufgenommen)", peak_target=-3.0)


# ============================================================================ Strassenbahn
def tram():
    y = shot("fs_profispiesser/543825", 0.45, 1.6, fin=0.002, fout=0.3, hpf=300)
    emit(y, "tram/tram_bell_1.ogg", "tram_bell", "fs_profispiesser/543825", False,
         "Strassenbahnklingel Berlin (Alexanderplatz), ein Schlag", peak_target=-3.0)
    y = shot("fs_16hpanskawillheimova/497561", 0.18, 2.0, fin=0.002, fout=0.3, hpf=300)
    emit(y, "tram/tram_bell_2.ogg", "tram_bell", "fs_16hpanskawillheimova/497561", False,
         "Strassenbahnklingel (Prag), Klingelfolge", peak_target=-3.0)
    # Fahrgeraeusch: Essener Strassenbahn, ruhige Fahrtphase ohne Ansagen
    ref = "fs_lg/718062"
    y, s = loop_mono(ref, 6.0, 0.8, t_from=95.0, t_to=150.0, hpf=30, max_jump_db=5)
    emit(y, "tram/tram_drive_loop.ogg", "tram_drive", ref, True,
         f"Strassenbahn Essen, Fahrt (Innenraum: Fahrmotor + Schienenrollen), ab {s:.2f} s; fuer die "
         "Aussenwirkung mit Distanz-Tiefpass abspielen", lufs_target=-18.0)


# ============================================================================ Atmos (stereo)
def ambience():
    xy, s = loop_stereo("fs_garuda1982/852125", 45.0, 3.0, t_from=3.0, t_to=106.0, max_jump_db=12)
    emit_stereo(xy, "ambience/amb_city_day.ogg", "ambience", "fs_garuda1982/852125",
                f"Innenstadt Leipzig, Mittag im Fruehling (Verkehr, Stimmen, Vogel), ab {s:.1f} s", -20.0)
    xy, s = loop_stereo("fs_garuda1982/686798", 45.0, 3.0, t_from=5.0, t_to=300.0, max_jump_db=10)
    emit_stereo(xy, "ambience/amb_park_day.ogg", "ambience", "fs_garuda1982/686798",
                f"Stadtpark Leipzig mit Strasse im Hintergrund, Fruehling (Voegel), ab {s:.1f} s", -22.0)
    xy, s = loop_stereo("fs_leonelmail/427841", 45.0, 3.0, t_from=3.0, t_to=136.0, max_jump_db=8)
    emit_stereo(xy, "ambience/amb_city_night.ogg", "ambience", "fs_leonelmail/427841",
                f"Stadt nachts, ruhiger Grundton (ferner Verkehr), ab {s:.1f} s", -26.0)
    xy, s = loop_stereo("fs_nimlos/454822", 22.0, 2.5, t_from=0.5, t_to=27.4, max_jump_db=10)
    emit_stereo(xy, "ambience/amb_city_night_2.ogg", "ambience", "fs_nimlos/454822",
                f"Stadt nachts nahe Wohnhaus (semibinaural, DPA 4060), ab {s:.1f} s", -26.0)
    xy, s = loop_stereo("fs_unfa/177479", 40.0, 3.0, t_from=2.0, t_to=72.0, max_jump_db=10)
    emit_stereo(xy, "ambience/amb_rain.ogg", "ambience", "fs_unfa/177479",
                f"Regen auf Balkon, Stadt (Warschau), ab {s:.1f} s", -22.0)
    xy, s = loop_stereo("fs_maciekkubera/686343", 45.0, 3.0, t_from=10.0, t_to=600.0, max_jump_db=8)
    emit_stereo(xy, "ambience/amb_river.ogg", "ambience", "fs_maciekkubera/686343",
                f"Flussufer (Pilica, Polen): Voegel, Wind in Baeumen/Gras, ab {s:.1f} s", -24.0)


if __name__ == "__main__":
    only = sys.argv[1:] or ["car_short", "driving", "impacts", "bus", "tram", "ambience"]
    for name in only:
        print(f"== {name}")
        globals()[name]()
    MAN.parent.mkdir(parents=True, exist_ok=True)
    old = json.loads(MAN.read_text()) if (MAN.exists() and sys.argv[1:]) else []
    keep = [e for e in old if e["file"] not in {n["file"] for n in ENTRIES}]
    MAN.write_text(json.dumps(keep + ENTRIES, indent=2, ensure_ascii=False) + "\n")
