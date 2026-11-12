"""Audio-Hilfsfunktionen fuer die Sample-Aufbereitung (Motor-Loops, Kurzklaenge, Atmos).

Nur numpy/scipy + ffmpeg (Dekodieren/Enkodieren/Lautheit). Alle Signale float64, mono.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np
from scipy import signal

SR = 44100


def _find_vorbis_ffmpeg():
    """Ein ffmpeg mit libvorbis suchen (Homebrew-ffmpeg hat nur den experimentellen Encoder)."""
    import shutil
    cands = ["/usr/bin/ffmpeg", shutil.which("ffmpeg") or "ffmpeg"]
    for c in cands:
        try:
            out = subprocess.run([c, "-hide_banner", "-encoders"], capture_output=True,
                                 text=True, timeout=20).stdout
        except (OSError, subprocess.TimeoutExpired):
            continue
        if "libvorbis" in out:
            return c
    raise RuntimeError("kein ffmpeg mit libvorbis gefunden")


FFMPEG_ENC = None


# ---------------------------------------------------------------- Ein-/Ausgabe
def load(path, sr=SR, channel=None):
    """Datei per ffmpeg dekodieren -> mono float64 (oder einzelner Kanal)."""
    path = str(path)
    if channel is None:
        af = ["-ac", "1"]
    else:
        af = ["-af", f"pan=mono|c0=c{channel}"]
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, *af, "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def channels(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=channels", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return int(out or 1)


def save_ogg(x, path, sr=SR, q=6):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.asarray(x, dtype=np.float32)
    global FFMPEG_ENC
    if FFMPEG_ENC is None:
        FFMPEG_ENC = _find_vorbis_ffmpeg()
    subprocess.run(
        [FFMPEG_ENC, "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-",
         "-c:a", "libvorbis", "-q:a", str(q), "-map_metadata", "-1", str(path)],
        input=x.tobytes(), check=True,
    )


def save_wav(x, path, sr=SR):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.asarray(x, dtype=np.float32)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-",
         "-c:a", "pcm_s16le", str(path)],
        input=x.tobytes(), check=True,
    )


# ---------------------------------------------------------------- Pegel
def lufs(x, sr=SR):
    """Integrierte Lautheit (EBU R128) per ffmpeg ebur128. Kurze Signale werden
    fuer die Messung zyklisch auf >= 3 s verlaengert (sonst kein Messwert)."""
    x = np.asarray(x, dtype=np.float64)
    if len(x) < 3 * sr:
        reps = int(np.ceil(3 * sr / max(1, len(x))))
        x = np.tile(x, reps)
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-f", "f32le", "-ar", str(sr), "-ac", "1",
         "-i", "-", "-af", "ebur128=peak=true", "-f", "null", "-"],
        input=x.astype(np.float32).tobytes(), capture_output=True,
    )
    txt = p.stderr.decode("utf-8", "replace")
    m = re.findall(r"I:\s+(-?[\d.]+|-inf) LUFS", txt)
    if not m:
        return float("-inf")
    v = m[-1]
    return float("-inf") if v == "-inf" else float(v)


def peak_db(x):
    p = float(np.max(np.abs(x))) if len(x) else 0.0
    return 20 * np.log10(max(p, 1e-12))


def norm_lufs(x, target, sr=SR, peak_ceiling_db=-1.0):
    """Auf Ziel-LUFS bringen, Spitzen notfalls weich begrenzen (tanh-Knie)."""
    cur = lufs(x, sr)
    if not np.isfinite(cur):
        return x
    y = x * 10 ** ((target - cur) / 20)
    ceil = 10 ** (peak_ceiling_db / 20)
    if np.max(np.abs(y)) > ceil:
        y = soft_limit(y, ceil)
    return y


def soft_limit(x, ceil):
    """Weiche Saettigung oberhalb 70 % der Decke (nur bei echten Ueberschreitungen)."""
    knee = 0.7 * ceil
    a = np.abs(x)
    out = x.copy()
    m = a > knee
    span = ceil - knee
    out[m] = np.sign(x[m]) * (knee + span * np.tanh((a[m] - knee) / span))
    return out


# ---------------------------------------------------------------- Filter
def hp(x, fc, sr=SR, order=2):
    sos = signal.butter(order, fc, "highpass", fs=sr, output="sos")
    return signal.sosfiltfilt(sos, x)


def lp(x, fc, sr=SR, order=2):
    sos = signal.butter(order, fc, "lowpass", fs=sr, output="sos")
    return signal.sosfiltfilt(sos, x)


def fade(x, fin=0.005, fout=0.01, sr=SR):
    y = x.copy()
    ni, no = int(fin * sr), int(fout * sr)
    if ni > 0:
        y[:ni] *= np.sin(np.linspace(0, np.pi / 2, ni)) ** 2
    if no > 0:
        y[-no:] *= np.cos(np.linspace(0, np.pi / 2, no)) ** 2
    return y


def trim_silence(x, thresh_db=-50, pad=0.01, sr=SR):
    """Fuehrende/abschliessende Stille relativ zum Spitzenpegel abschneiden."""
    env = np.abs(x)
    thr = np.max(env) * 10 ** (thresh_db / 20)
    idx = np.where(env > thr)[0]
    if len(idx) == 0:
        return x
    a = max(0, idx[0] - int(pad * sr))
    b = min(len(x), idx[-1] + int(pad * sr))
    return x[a:b]


# ---------------------------------------------------------------- Drehzahl
def harmonic_f0(x, sr=SR, fmin=15.0, fmax=400.0, nharm=8, df=0.05, nfft_sec=None):
    """Grundfrequenz einer (quasi)periodischen Motorschwingung per Harmonischen-
    Summation im Leistungsspektrum (Welch). Liefert (f0, score, spec_freqs, spec_db)."""
    n = len(x)
    nper = int(min(n, (nfft_sec or 1.0) * sr))
    f, P = signal.welch(x, fs=sr, nperseg=nper, noverlap=nper // 2, nfft=max(nper, 1 << 18),
                        window="hann", detrend="constant")
    Pdb = 10 * np.log10(P + 1e-20)
    # Spektrum "weissen": gleitendes Minimum/Median abziehen, nur positive Ueberhoehung zaehlt
    med = signal.medfilt(Pdb, 2 * int(20 / (f[1] - f[0])) + 1) if len(Pdb) > 50 else Pdb
    prom = np.clip(Pdb - med, 0, None)
    cands = np.arange(fmin, fmax, df)
    score = np.zeros_like(cands)
    for k in range(1, nharm + 1):
        fk = cands * k
        ok = fk < f[-1]
        score[ok] += np.interp(fk[ok], f, prom) / np.sqrt(k)
    i = int(np.argmax(score))
    return float(cands[i]), float(score[i]), f, Pdb, cands, score


def comb_score(f, prom, f0, nharm=8):
    s = 0.0
    for k in range(1, nharm + 1):
        if f0 * k < f[-1]:
            s += float(np.interp(f0 * k, f, prom)) / np.sqrt(k)
    return s


def firing_freq_near(x, f_guess, sr=SR, rel=0.35, nharm=10, df=0.02, seg=1.0):
    """Zuendfrequenz in einem Fenster um f_guess (+-rel) suchen."""
    n = len(x)
    nper = int(min(n, seg * sr))
    f, P = signal.welch(x, fs=sr, nperseg=nper, noverlap=nper // 2, nfft=max(nper, 1 << 18),
                        window="hann")
    Pdb = 10 * np.log10(P + 1e-20)
    w = 2 * int(15 / (f[1] - f[0])) + 1
    med = signal.medfilt(Pdb, w)
    prom = np.clip(Pdb - med, 0, None)
    cands = np.arange(f_guess * (1 - rel), f_guess * (1 + rel), df)
    sc = np.array([comb_score(f, prom, c, nharm) for c in cands])
    i = int(np.argmax(sc))
    # Parabel-Verfeinerung
    if 0 < i < len(sc) - 1:
        a, b, c = sc[i - 1], sc[i], sc[i + 1]
        den = a - 2 * b + c
        off = 0.5 * (a - c) / den if den != 0 else 0.0
    else:
        off = 0.0
    return float(cands[i] + off * df), float(sc[i])


def track_firing(x, f_start, sr=SR, hop=0.025, win=0.12, rel=0.12, nharm=8, f_lo=10, f_hi=500):
    """Zuendfrequenz-Verlauf (Sweep) mit Kontinuitaetsbedingung verfolgen.
    Startwert f_start (Hz) am Anfang. Rueckgabe: t (s), f (Hz), score."""
    hopn, winn = int(hop * sr), int(win * sr)
    nfft = 1 << 16
    wnd = signal.windows.hann(winn)
    ts, fs, ss = [], [], []
    fcur = f_start
    freqs = np.fft.rfftfreq(nfft, 1 / sr)
    for start in range(0, len(x) - winn, hopn):
        seg = x[start:start + winn] * wnd
        S = np.abs(np.fft.rfft(seg, nfft)) ** 2
        Sdb = 10 * np.log10(S + 1e-20)
        w = 2 * int(15 / (freqs[1] - freqs[0])) + 1
        med = signal.medfilt(Sdb[: int(4000 / freqs[1])], w)
        prom = np.clip(Sdb[: len(med)] - med, 0, None)
        ff = freqs[: len(med)]
        cands = np.linspace(fcur * (1 - rel), fcur * (1 + rel), 241)
        cands = cands[(cands > f_lo) & (cands < f_hi)]
        sc = np.array([comb_score(ff, prom, c, nharm) for c in cands])
        i = int(np.argmax(sc))
        fcur = float(cands[i])
        ts.append((start + winn / 2) / sr)
        fs.append(fcur)
        ss.append(float(sc[i]))
    return np.array(ts), np.array(fs), np.array(ss)


# ---------------------------------------------------------------- Tonhoehe/Loop
def resample_ratio(x, ratio):
    """Tonhoehe um 'ratio' anheben (ratio>1 = hoeher, kuerzer) per Polyphasen-Resampling."""
    from fractions import Fraction
    fr = Fraction(1 / ratio).limit_denominator(2000)
    return signal.resample_poly(x, fr.numerator, fr.denominator)


def flatten_pitch(x, t_track, f_track, f_target, t0, t1, sr=SR):
    """Abschnitt [t0,t1] eines Sweeps per zeitvariablem Resampling auf konstante
    Frequenz f_target bringen (Phasen-Abbildung). Rueckgabe: Signal mit konstanter f."""
    tt = np.arange(len(x)) / sr
    f_s = np.interp(tt, t_track, f_track)
    phase = np.cumsum(f_s) / sr  # Zyklen
    p0 = np.interp(t0, tt, phase)
    p1 = np.interp(t1, tt, phase)
    n_out = int((p1 - p0) / f_target * sr)
    ph_out = p0 + np.arange(n_out) * f_target / sr
    t_in = np.interp(ph_out, phase, tt)
    # Antialiasing: bei Hochrechnen (f_target > f_s) leicht tiefpassen
    xi = np.interp(t_in * sr, np.arange(len(x)), x)
    return xi


def make_loop_cycles(x, f0, sr=SR, target_len=2.0, xfade=0.12, start=None):
    """Nahtlosen Loop bauen: Laenge auf ganze Motorzyklen (Periode 1/f0 der Zuendfolge
    bzw. des Arbeitsspiels) runden, Ende per gleichleistungs-Kreuzblende mit dem
    Vorlauf vor dem Loopstart verschmelzen. x muss >= target_len + xfade lang sein."""
    period = 1.0 / f0
    ncyc = max(1, int(round(target_len / period)))
    L = int(round(ncyc * period * sr))
    X = int(xfade * sr)
    if start is None:
        start = X
    if start < X:
        raise ValueError("start muss >= xfade sein")
    if start + L > len(x):
        raise ValueError(f"zu kurz: brauche {start + L} Samples, habe {len(x)}")
    seg = x[start:start + L].copy()
    pre = x[start - X:start]           # Material direkt vor dem Loopstart
    tail = seg[L - X:]                 # Ende des Loops
    t = np.linspace(0, 1, X)
    g_in = np.sin(t * np.pi / 2)
    g_out = np.cos(t * np.pi / 2)
    # Korrelationsabhaengige Normierung: bei korrelierten Signalen (gleiche Zyklen) wuerde
    # die Gleichleistungsblende sonst bis +3 dB aufdicken.
    r = float(np.dot(tail, pre) / (np.linalg.norm(tail) * np.linalg.norm(pre) + 1e-12))
    r = min(max(r, 0.0), 1.0)
    norm = np.sqrt(1.0 + 2.0 * r * g_in * g_out)
    # Ende des Loops geht in 'pre' ueber -> am Loop-Punkt folgt seg[0] nahtlos auf pre[-1]
    seg[L - X:] = (tail * g_out + pre * g_in) / norm
    return seg


def best_loop_start(x, f0, sr=SR, target_len=2.0, xfade=0.12, search=None):
    """Loopstart suchen, an dem Ende und Vorlauf am besten korrelieren (minimiert Phasing)."""
    period = 1.0 / f0
    ncyc = max(1, int(round(target_len / period)))
    L = int(round(ncyc * period * sr))
    X = int(xfade * sr)
    lo = X
    hi = len(x) - L - 1
    if hi <= lo:
        return lo, 0.0
    best, bestc = lo, -2.0
    step = max(1, int(0.002 * sr))
    for s in range(lo, hi, step):
        a = x[s + L - X:s + L]
        b = x[s - X:s]
        c = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
        if c > bestc:
            best, bestc = s, c
    return best, bestc


def loop_seam_error(seg, sr=SR, w=0.01):
    """Diskontinuitaet am Loop-Punkt: Sprung zwischen letztem und erstem Sample relativ zum RMS."""
    rms = np.sqrt(np.mean(seg ** 2)) + 1e-12
    jump = abs(seg[-1] - seg[0])
    return float(jump / rms)


def write_json(obj, path):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- Diagnose-Bilder
def write_png(path, rgb):
    """rgb: uint8-Array (H, W, 3) -> PNG (ohne externe Bibliotheken)."""
    import struct
    import zlib
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    Path(path).write_bytes(png)


def spectrogram_png(x, path, sr=SR, fmax=1200.0, win=0.08, hop=0.01, height=600, tracks=(),
                    dyn=60.0):
    """Spektrogramm (linear 0..fmax) als PNG; tracks = [(t, f, (r,g,b)), ...] als Linien."""
    nwin, nhop = int(win * sr), int(hop * sr)
    nfft = 1 << 15
    wnd = signal.windows.hann(nwin)
    frames = []
    for s in range(0, max(1, len(x) - nwin), nhop):
        S = np.abs(np.fft.rfft(x[s:s + nwin] * wnd, nfft))
        frames.append(20 * np.log10(S + 1e-9))
    M = np.array(frames).T  # (freq, time)
    freqs = np.fft.rfftfreq(nfft, 1 / sr)
    rows = np.linspace(fmax, 0, height)
    img = np.array([np.interp(rows, freqs, M[:, j]) for j in range(M.shape[1])]).T
    top = np.percentile(img, 99.5)
    v = np.clip((img - (top - dyn)) / dyn, 0, 1)
    rgb = np.stack([v ** 0.8, v ** 1.5, (1 - v) * 0.3 + v ** 3], axis=-1)
    rgb = (rgb * 255).astype(np.uint8)
    # Gitter alle 100 Hz
    for fg in np.arange(100, fmax, 100):
        r = int(round((fmax - fg) / fmax * (height - 1)))
        rgb[r, ::4] = (90, 90, 90)
    W = rgb.shape[1]
    for (tt, ff, col) in tracks:
        for t_, f_ in zip(tt, ff):
            c = int(round((t_ - win / 2) / hop))
            r = int(round((fmax - f_) / fmax * (height - 1)))
            if 0 <= c < W and 0 <= r < height:
                rgb[max(0, r - 1):r + 2, c] = col
    write_png(path, rgb)


def salience_map(x, sr=SR, fmin=15.0, fmax=280.0, nf=600, hop=0.02, win=0.15, nharm=10):
    """Harmonische Salienz S[t, f] (log-Frequenzraster) fuer Viterbi-Tracking."""
    nwin, nhop = int(win * sr), int(hop * sr)
    nfft = 1 << 16
    wnd = signal.windows.hann(nwin)
    freqs = np.fft.rfftfreq(nfft, 1 / sr)
    fgrid = np.geomspace(fmin, fmax, nf)
    lim = int(min(sr / 2, fmax * nharm * 1.05) / freqs[1])
    w = 2 * int(12 / freqs[1]) + 1
    rows, ts = [], []
    for s in range(0, max(1, len(x) - nwin), nhop):
        Sp = np.abs(np.fft.rfft(x[s:s + nwin] * wnd, nfft)) ** 2
        Sdb = 10 * np.log10(Sp[:lim] + 1e-20)
        med = signal.medfilt(Sdb, w)
        prom = np.clip(Sdb - med, 0, None)
        ff = freqs[:lim]
        sal = np.zeros(nf)
        for k in range(1, nharm + 1):
            sal += np.interp(fgrid * k, ff, prom, right=0) / np.sqrt(k)
        rows.append(sal)
        ts.append((s + nwin / 2) / sr)
    return np.array(ts), fgrid, np.array(rows)


def viterbi_track(ts, fgrid, S, max_jump_oct=0.08, jump_cost=4.0, f_start=None, f_end=None,
                  anchor_w=50.0):
    """Ridge-Tracking: maximiert Salienz minus Sprungkosten (in Oktaven). Optionale Anker
    (Start/Ende) ziehen den Pfad zu bekannten Frequenzen."""
    T, F = S.shape
    lf = np.log2(fgrid)
    Sn = S / (np.percentile(S, 99) + 1e-9) * 10
    if f_start is not None:
        Sn[0] -= anchor_w * np.abs(lf - np.log2(f_start))
    if f_end is not None:
        Sn[-1] -= anchor_w * np.abs(lf - np.log2(f_end))
    D = np.abs(lf[:, None] - lf[None, :])  # [prev, cur]
    trans = -jump_cost * (D / max_jump_oct) ** 2
    trans[D > 3 * max_jump_oct] = -1e9
    acc = Sn[0].copy()
    back = np.zeros((T, F), dtype=np.int32)
    for t in range(1, T):
        tot = acc[:, None] + trans
        back[t] = np.argmax(tot, axis=0)
        acc = tot[back[t], np.arange(F)] + Sn[t]
    path = np.zeros(T, dtype=np.int32)
    path[-1] = int(np.argmax(acc))
    for t in range(T - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    return fgrid[path]


def track_peak(x, t_seed, f_seed, sr=SR, hop=0.01, win=0.08, rel=0.06, fmin=25, fmax=320,
               t_from=None, t_to=None):
    """Staerkste Spektrallinie (= Zuendfrequenz bei Auspuff-/Motorraum-Mikro) ab einem
    bekannten Saatpunkt vorwaerts und rueckwaerts verfolgen. Pro Schritt wird nur im
    Fenster +-rel um den letzten Wert gesucht; Peak per Parabel verfeinert."""
    nwin, nhop = int(win * sr), int(hop * sr)
    nfft = 1 << 16
    wnd = signal.windows.hann(nwin)
    fr = np.fft.rfftfreq(nfft, 1 / sr)
    t_from = 0.0 if t_from is None else t_from
    t_to = len(x) / sr if t_to is None else t_to

    def est(tc, fc):
        a = int(tc * sr - nwin / 2)
        if a < 0 or a + nwin > len(x):
            return None
        S = np.abs(np.fft.rfft(x[a:a + nwin] * wnd, nfft))
        lo, hi = fc * (1 - rel), fc * (1 + rel)
        m = (fr >= max(fmin, lo)) & (fr <= min(fmax, hi))
        idx = np.where(m)[0]
        if len(idx) < 5:
            c = int(round(fc / fr[1]))
            idx = np.arange(max(1, c - 2), c + 3)
        i = idx[np.argmax(S[idx])]
        if 0 < i < len(S) - 1:
            a_, b_, c_ = np.log(S[i - 1] + 1e-12), np.log(S[i] + 1e-12), np.log(S[i + 1] + 1e-12)
            den = a_ - 2 * b_ + c_
            off = 0.5 * (a_ - c_) / den if den != 0 else 0.0
        else:
            off = 0.0
        return float(fr[i] + off * fr[1])

    ts = [t_seed]
    fs = [est(t_seed, f_seed) or f_seed]
    # vorwaerts
    t, f = t_seed, fs[0]
    fwd_t, fwd_f = [], []
    while t + hop <= t_to - win / 2:
        t += hop
        g = est(t, f)
        if g is None:
            break
        f = g
        fwd_t.append(t)
        fwd_f.append(f)
    t, f = t_seed, fs[0]
    bwd_t, bwd_f = [], []
    while t - hop >= t_from + win / 2:
        t -= hop
        g = est(t, f)
        if g is None:
            break
        f = g
        bwd_t.append(t)
        bwd_f.append(f)
    T = np.array(bwd_t[::-1] + ts + fwd_t)
    F = np.array(bwd_f[::-1] + fs + fwd_f)
    # leicht glaetten (Median 5)
    if len(F) >= 5:
        F = signal.medfilt(F, 5)
    return T, F


# ---------------------------------------------------------------- Motor-Loops aus Sweeps
def crossing_time(T, F, f_target):
    """Erster Zeitpunkt, an dem der (monotone Abschnitt des) Verlaufs f_target kreuzt."""
    for i in range(len(F) - 1):
        a, b = F[i], F[i + 1]
        if (a - f_target) * (b - f_target) <= 0 and a != b:
            return float(T[i] + (f_target - a) / (b - a) * (T[i + 1] - T[i]))
    return None


def window_around(T, F, tc, f_target, half_span):
    """Zeitfenster um tc, in dem F innerhalb f_target*(1 +- half_span) bleibt."""
    i = int(np.argmin(np.abs(T - tc)))
    lo = hi = i
    while lo > 0 and abs(F[lo - 1] / f_target - 1) <= half_span:
        lo -= 1
    while hi < len(F) - 1 and abs(F[hi + 1] / f_target - 1) <= half_span:
        hi += 1
    return float(T[lo]), float(T[hi])


def cycle_loop(x, T, F, f_target, sr=SR, half_span=0.06, loop_len=1.5, cyc_per_grain=4,
               xfade_frac=0.3, level_flatten=True, t_window=None, order_mode="walk", seed=1):
    """Konstant-Drehzahl-Loop aus einem Sweep: Abschnitt um f_target auf konstante
    Zuendfrequenz bringen (zeitvariables Resampling, max. +-half_span), in Arbeitsspiele
    (cyc_per_grain Zuendperioden = 720 Grad KW beim 4-Zylinder) zerlegen und diese als
    Palindrom (1..n..2) zirkulaer per Overlap-Add zu einem nahtlosen Loop zusammensetzen.
    Rueckgabe: (loop, info)."""
    if t_window is None:
        tc = crossing_time(T, F, f_target)
        if tc is None:
            raise ValueError(f"f={f_target:.1f} Hz wird im Verlauf nicht erreicht")
        t0, t1 = window_around(T, F, tc, f_target, half_span)
    else:
        t0, t1 = t_window
        tc = 0.5 * (t0 + t1)
    # Grain-Laenge ganzzahlig machen -> Zielfrequenz minimal anpassen
    G = int(round(cyc_per_grain * sr / f_target))
    f_eff = cyc_per_grain * sr / G
    X = int(G * xfade_frac)
    # mit Rand fuer die Ueberblendungen flach rechnen
    dt_margin = X / sr * 1.2
    flat = flatten_pitch(x, T, F, f_eff, max(0.0, t0 - dt_margin), min(len(x) / sr, t1 + dt_margin), sr)
    m = int(round(dt_margin * sr * f_eff / np.interp(t0, T, F)))  # Rand in Ausgabesamples (ca.)
    m = max(X, min(m, len(flat) // 4))
    n = (len(flat) - 2 * m) // G
    if n < 3:
        raise ValueError(f"Fenster zu kurz ({n} Grains) fuer f={f_target:.1f}")
    grains = []
    for i in range(n):
        a = m + i * G - X
        grains.append(flat[a:a + G + 2 * X].copy())
    if level_flatten:
        r = np.array([np.sqrt(np.mean(g[X:X + G] ** 2)) for g in grains])
        ref = np.median(r)
        # weiche Korrektur (Trend raus, Mikrodynamik bleibt grob erhalten)
        sm = np.convolve(np.pad(r, 2, mode="edge"), np.ones(5) / 5, mode="valid")
        grains = [g * (ref / max(s, 1e-9)) for g, s in zip(grains, sm)]
    n_out = int(round(loop_len * f_eff / cyc_per_grain))
    if order_mode == "walk":
        # Zufallsweg (Schritte +-1, reflektierend) + Spiegelung: jede Nahtstelle verbindet
        # benachbarte Arbeitsspiele, die Abfolge wirkt aber nicht periodisch.
        rng = np.random.default_rng(seed)
        half = max(2, n_out // 2 + 1)
        w = [int(rng.integers(0, n))]
        while len(w) < half:
            step = 1 if rng.random() < 0.5 else -1
            nxt = w[-1] + step
            if nxt < 0 or nxt >= n:
                nxt = w[-1] - step
            w.append(nxt)
        seq = w + w[-2:0:-1]
    else:
        order = list(range(n)) + list(range(n - 2, 0, -1))
        n_out = max(len(order), n_out)
        seq = [order[k % len(order)] for k in range(n_out)]
    n_out = len(seq)
    L = n_out * G
    out = np.zeros(L)
    wsum = np.zeros(L)
    # Fenster: flach mit cos^2-Flanken der Laenge 2X (gleichamplitudig komplementaer)
    w = np.ones(G + 2 * X)
    ramp = np.sin(np.linspace(0, np.pi / 2, 2 * X)) ** 2
    w[:2 * X] = ramp
    w[-2 * X:] = ramp[::-1]
    for k, gi in enumerate(seq):
        start = k * G - X
        idx = (np.arange(G + 2 * X) + start) % L
        np.add.at(out, idx, grains[gi] * w)
        np.add.at(wsum, idx, w)
    out /= np.maximum(wsum, 1e-9)
    info = {"t_center": tc, "t0": t0, "t1": t1, "f_eff": f_eff, "grains": n,
            "span_pct": half_span * 100}
    return out, info


def constant_loop(x, f_fire, sr=SR, loop_len=2.0, xfade=0.12, cyc_per_grain=4):
    """Loop aus Konstant-Drehzahl-Aufnahme: Laenge = ganze Arbeitsspiele, bester Startpunkt
    nach Korrelation, korrelationsnormierte Kreuzblende am Loop-Punkt."""
    f_cyc = f_fire / cyc_per_grain
    maxlen = len(x) / sr - xfade - 0.02
    loop_len = min(loop_len, maxlen)
    s, c = best_loop_start(x, f_cyc, sr, target_len=loop_len, xfade=xfade)
    seg = make_loop_cycles(x, f_cyc, sr, target_len=loop_len, xfade=xfade, start=s)
    return seg, {"start": s / sr, "corr": c}


def stable_flat_region(x, seed_f, k=1, sr=SR, region_len=2.4, rel=0.03):
    """Konstantaufnahme: Linie seed_f (= k-te Harmonische der Zuendfrequenz) verfolgen,
    den ruhigsten Abschnitt der Laenge region_len waehlen und auf dessen mittlere
    Zuendfrequenz flach rechnen. Rueckgabe: (flat, f_fire_mean, info)."""
    dur = len(x) / sr
    T, F = track_peak(x, dur / 2, seed_f, sr=sr, rel=rel, hop=0.01, win=0.1)
    F = F / k
    region_len = min(region_len, T[-1] - T[0])
    best = None
    step = 0.05
    t = T[0]
    while t + region_len <= T[-1] + 1e-9:
        m = (T >= t) & (T <= t + region_len)
        s = float(np.std(F[m]) / np.mean(F[m]))
        if best is None or s < best[0]:
            best = (s, t)
        t += step
    s, t0 = best
    t1 = t0 + region_len
    m = (T >= t0) & (T <= t1)
    fm = float(np.mean(F[m]))
    flat = flatten_pitch(x, T, F, fm, t0, t1, sr)
    return flat, fm, {"t0": t0, "t1": t1, "rel_std_pct": s * 100,
                      "f_min": float(F[m].min()), "f_max": float(F[m].max())}


def seam_report(y, sr=SR, frame=0.01):
    """Loop-Naht pruefen: Loop zweimal hintereinander, Spektralfluss und Pegelsprung an der
    Naht relativ zum 99. Perzentil im Rest (Werte <= ~1 sind unauffaellig)."""
    z = np.concatenate([y, y])
    n = int(frame * sr)
    nfr = len(z) // n
    w = signal.windows.hann(2 * n)
    specs, rms = [], []
    for i in range(nfr - 1):
        seg = z[i * n:i * n + 2 * n]
        if len(seg) < 2 * n:
            break
        mag = np.abs(np.fft.rfft(seg * w))
        # Boden 45 dB unter dem Frame-Maximum: ignoriert unhoerbare Codec-Rauschtextur
        specs.append(np.log(np.maximum(mag, mag.max() * 10 ** (-45 / 20)) + 1e-9))
        rms.append(np.sqrt(np.mean(seg ** 2)) + 1e-9)
    specs = np.array(specs)
    rms = 20 * np.log10(np.array(rms))
    flux = np.sqrt(np.mean(np.diff(specs, axis=0) ** 2, axis=1))
    dl = np.abs(np.diff(rms))
    seam = len(y) // n - 1  # Frame-Index, der die Naht ueberdeckt
    idx = [i for i in (seam - 1, seam, seam + 1) if 0 <= i < len(flux)]
    rest = np.delete(flux, idx)
    restl = np.delete(dl, idx)
    # Verhaeltnis zum 99. Perzentil des restlichen Signals (<= ~1 = Naht faellt nicht auf)
    zf = max(flux[idx]) / (np.percentile(rest, 99) + 1e-9)
    zl = max(dl[idx]) / (np.percentile(restl, 99) + 1e-9)
    # Sample-Sprung
    d = np.abs(np.diff(z))
    jump = abs(y[0] - y[-1]) / (np.percentile(d, 99.9) + 1e-12)
    return {"flux_z": float(zf), "level_z": float(zl), "jump_rel": float(jump)}


def load_ogg_exact(path, sr=SR):
    """OGG Vorbis sample-genau dekodieren (GStreamer/libvorbis beachtet die Granule-
    Positionen; ffmpegs Vorbis-Decoder verwirft die ersten 128 Samples)."""
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".raw")
    os.close(fd)
    try:
        subprocess.run(
            ["gst-launch-1.0", "-q", "filesrc", f"location={path}", "!", "oggdemux", "!",
             "vorbisdec", "!", "audioconvert", "!", "audioresample", "!",
             f"audio/x-raw,format=F32LE,channels=1,rate={sr}", "!", "filesink",
             f"location={tmp}"], check=True, capture_output=True)
        y = np.fromfile(tmp, dtype=np.float32).astype(np.float64)
    finally:
        os.unlink(tmp)
    n = ogg_length(path)
    return y[:n] if n else y


def ogg_length(path):
    """Sampleanzahl laut letzter Granule-Position (massgeblich fuer Godot)."""
    import struct
    d = Path(path).read_bytes()
    j = d.rfind(b"OggS")
    if j < 0:
        return None
    return int(struct.unpack("<q", d[j + 6:j + 14])[0])


# ---------------------------------------------------------------- Allgemeine Loops/Schnitte
def short_levels(x, sr=SR, win=0.1):
    n = int(win * sr)
    m = len(x) // n
    e = np.sqrt(np.mean(x[:m * n].reshape(m, n) ** 2, axis=1))
    return 20 * np.log10(e + 1e-9)


def pick_stationary(x, length, sr=SR, t_from=0.0, t_to=None, xfade=0.0, max_jump_db=8.0,
                    win=0.1, step=0.1):
    """Startzeit des ruhigsten Fensters (Laenge length + xfade Vorlauf) suchen: kleine
    Pegelstreuung, keine Einzelereignisse > median + max_jump_db, Anfangs- und Endpegel
    aehnlich (fuer die Loop-Kreuzblende)."""
    lv = short_levels(x, sr, win)
    t_to = len(x) / sr if t_to is None else t_to
    need = int((length + xfade) / win)
    best = None
    i = int((t_from + 0.0) / win)
    while (i + need) * win <= t_to:
        seg = lv[i:i + need]
        med = np.median(seg)
        if np.max(seg) - med <= max_jump_db:
            k = max(2, int(1.0 / win))
            edge = abs(np.mean(seg[:k]) - np.mean(seg[-k:]))
            score = np.std(seg) + 0.7 * edge
            if best is None or score < best[0]:
                best = (score, i * win, med)
        i += max(1, int(step / win))
    if best is None:
        raise ValueError("kein ruhiges Fenster gefunden")
    return best[1] + xfade, best


def noise_loop(x, start, length, xfade, sr=SR):
    """Loop fuer rausch-/texturartiges Material: ab 'start' (s) 'length' s, Ende mit dem
    Material vor dem Start ueberblendet (gleichleistungs, korrelationskorrigiert)."""
    s = int(start * sr)
    L = int(length * sr)
    X = int(xfade * sr)
    if s < X or s + L > len(x):
        raise ValueError("Fenster ausserhalb der Datei")
    seg = x[s:s + L].copy()
    pre = x[s - X:s]
    tail = seg[L - X:]
    t = np.linspace(0, 1, X)
    g_in = np.sin(t * np.pi / 2)
    g_out = np.cos(t * np.pi / 2)
    r = float(np.dot(tail, pre) / (np.linalg.norm(tail) * np.linalg.norm(pre) + 1e-12))
    r = min(max(r, 0.0), 1.0)
    norm = np.sqrt(1.0 + 2.0 * r * g_in * g_out)
    seg[L - X:] = (tail * g_out + pre * g_in) / norm
    return seg


def one_shot(x, t0, t1, sr=SR, fin=0.003, fout=0.05):
    a = max(0, int(t0 * sr))
    b = min(len(x), int(t1 * sr))
    return fade(x[a:b].copy(), fin, fout, sr)


def transients(x, k, sr=SR, band=None, min_sep=1.0, win=0.01, t_from=0.0, t_to=None,
               exclude=()):
    """Die k staerksten Einschwingvorgaenge (Pegelsprung gegenueber 100 ms davor),
    optional in einem Frequenzband. Rueckgabe: Liste (t_onset, sprung_dB, peak_dB)."""
    y = x
    if band:
        lo, hi = band
        if lo:
            y = hp(y, lo, sr, 4)
        if hi:
            y = lp(y, hi, sr, 4)
    lv = short_levels(y, sr, win)
    back = int(0.1 / win)
    rise = np.full_like(lv, -99.0)
    for i in range(back, len(lv)):
        rise[i] = lv[i] - np.median(lv[i - back:i])
    t_to = len(x) / sr if t_to is None else t_to
    out = []
    order = np.argsort(rise)[::-1]
    for i in order:
        t = i * win
        if t < t_from or t > t_to:
            continue
        if any(abs(t - e) < min_sep for e in exclude):
            continue
        if all(abs(t - o[0]) >= min_sep for o in out):
            out.append((t, float(rise[i]), float(np.max(lv[i:i + int(0.3 / win)]))))
        if len(out) >= k:
            break
    return sorted(out)


def clip_fraction(x, rel=0.995, run=3):
    """Anteil der Samples in Plateaus (>= run Samples) nahe dem Absolutmaximum."""
    a = np.abs(x)
    m = a.max()
    if m <= 0:
        return 0.0
    hot = a >= rel * m
    cnt, cur = 0, 0
    for h in hot:
        if h:
            cur += 1
        else:
            if cur >= run:
                cnt += cur
            cur = 0
    if cur >= run:
        cnt += cur
    return cnt / len(x)


# ---------------------------------------------------------------- Stereo (Atmos)
def load_stereo(path, sr=SR):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True, check=True,
    ).stdout
    a = np.frombuffer(raw, dtype=np.float32).astype(np.float64)
    return a.reshape(-1, 2).T.copy()


def save_ogg_stereo(xy, path, sr=SR, q=6):
    global FFMPEG_ENC
    if FFMPEG_ENC is None:
        FFMPEG_ENC = _find_vorbis_ffmpeg()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    inter = np.stack([xy[0], xy[1]], axis=1).astype(np.float32)
    subprocess.run(
        [FFMPEG_ENC, "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "2", "-i", "-",
         "-c:a", "libvorbis", "-q:a", str(q), "-map_metadata", "-1", str(path)],
        input=inter.tobytes(), check=True,
    )


def lufs_stereo(xy, sr=SR):
    """Integrierte Lautheit eines Stereosignals (ebur128 auf beiden Kanaelen)."""
    x = np.stack([xy[0], xy[1]], axis=1)
    if len(x) < 3 * sr:
        reps = int(np.ceil(3 * sr / max(1, len(x))))
        x = np.tile(x, (reps, 1))
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-f", "f32le", "-ar", str(sr), "-ac", "2",
         "-i", "-", "-af", "ebur128=peak=true", "-f", "null", "-"],
        input=x.astype(np.float32).tobytes(), capture_output=True,
    )
    txt = p.stderr.decode("utf-8", "replace")
    m = re.findall(r"I:\s+(-?[\d.]+|-inf) LUFS", txt)
    return float(m[-1]) if m and m[-1] != "-inf" else float("-inf")
