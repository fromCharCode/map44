"""Freesound-Quellen holen (ohne Login): Metadaten der Soundseite + HQ-OGG-Vorschau.

Aufruf:
    python -I fs_fetch.py info <id> [<id> ...]          # nur anzeigen
    python -I fs_fetch.py get <zielordner> <id> [...]   # laden + sources.json ergaenzen

Zielordner liegt unter data/raw/audio_src/<quelle_id>/ (wird neu angelegt). Die Vorschau-
dateien haben dieselbe Lizenz wie das Original (Freesound-Nutzungsbedingungen). Es werden
nur CC0- und CC-BY-Lizenzen akzeptiert (BY-NC, Sampling+ usw. -> Abbruch).
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "raw" / "audio_src"
UA = "Mozilla/5.0 (X11; Linux x86_64)"
OK_LIC = {
    "publicdomain/zero/1.0": "CC0 1.0",
    "licenses/by/4.0": "CC BY 4.0",
    "licenses/by/3.0": "CC BY 3.0",
}


def curl(url):
    return subprocess.run(["curl", "-sL", "-A", UA, url], capture_output=True, text=True,
                          timeout=90).stdout


def info(sid):
    page = curl(f"https://freesound.org/s/{sid}/")
    t = re.search(r"<title>Freesound - (.*?) by ([^<]+)</title>", page, re.S)
    title = html.unescape(t.group(1).strip()) if t else "?"
    author = html.unescape(t.group(2).strip()) if t else "?"
    canon = re.search(r'href="(/people/[^/"]+/sounds/%s/)"' % sid, page)
    lic = re.search(r'href="(https?://creativecommons.org/[^"]+)"', page)
    ogg = re.search(r'data-ogg="([^"]+)"', page)
    dur = re.search(r'data-duration="([\d.]+)"', page)
    sr = re.search(r'data-samplerate="([\d.]+)"', page)
    pack = re.search(r'href="/people/[^/]+/packs/(\d+)/"[^>]*>\s*([^<]+?)\s*<', page)
    desc = re.search(r'<div[^>]*id="soundDescriptionSection"[^>]*>(.*?)</div>', page, re.S)
    d = ""
    if desc:
        d = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", desc.group(1))).split())
    licname = None
    if lic:
        for k, v in OK_LIC.items():
            if k in lic.group(1):
                licname = v
    return {
        "freesound_id": int(sid),
        "title": title,
        "author": author,
        "source_url": "https://freesound.org" + canon.group(1) if canon else f"https://freesound.org/s/{sid}/",
        "license": licname or (lic.group(1) if lic else "?"),
        "license_url": lic.group(1).replace("http://", "https://") if lic else None,
        "license_ok": licname is not None,
        "duration": float(dur.group(1)) if dur else None,
        "samplerate": float(sr.group(1)) if sr else None,
        "pack": html.unescape(pack.group(2)) if pack else None,
        "description": d,
        "preview_hq": ogg.group(1).replace("-lq.", "-hq.") if ogg else None,
    }


def main():
    mode = sys.argv[1]
    if mode == "info":
        for sid in sys.argv[2:]:
            m = info(sid)
            print(f"{sid} | {m['author']} | {m['license']} | {m['duration']}s | {m['title']}")
            print(f"    pack={m['pack']} :: {m['description'][:400]}")
        return
    if mode == "get":
        dest = SRC / sys.argv[2]
        dest.mkdir(parents=True, exist_ok=True)
        meta_path = dest / "sources.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        for sid in sys.argv[3:]:
            m = info(sid)
            if not m["license_ok"]:
                print(f"SKIP {sid}: Lizenz {m['license']} nicht erlaubt")
                continue
            if not m["preview_hq"]:
                print(f"SKIP {sid}: keine Vorschau gefunden")
                continue
            out = dest / f"{sid}.ogg"
            if not out.exists():
                r = subprocess.run(["curl", "-sf", "-A", UA, "-o", str(out), m["preview_hq"]])
                if r.returncode != 0:
                    print(f"FAIL {sid}")
                    continue
            m["file"] = out.name
            meta[str(sid)] = m
            print(f"ok {sid} {m['license']} {m['duration']}s {m['title']}")
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
        return
    raise SystemExit("mode: info|get")


if __name__ == "__main__":
    main()
