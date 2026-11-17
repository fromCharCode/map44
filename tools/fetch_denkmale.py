"""Kulturdenkmale Dresdens aus den Wikipedia-Denkmallisten (Vorlage „Denkmalliste Sachsen Tabellenzeile“).

  python tools/fetch_denkmale.py

Schreibt data/raw/denkmale/denkmale.json: [{id, name, adresse, lat, lon, x, z, datierung, jahr, text, bild, commonscat,
wikidata, liste}]. Quelle: de.wikipedia.org, Texte CC BY-SA 4.0; die Bilder liegen auf Wikimedia Commons (Lizenz je Bild).
Die Seiten werden in data/raw/denkmale/pages/ zwischengespeichert.
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "denkmale"
API = "https://de.wikipedia.org/w/api.php"
UA = {"User-Agent": "map-data-research/1.0"}
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
ORIGIN_E, ORIGIN_N = 411000.0, 5656200.0


def api(**params):
    params["format"] = "json"
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:                                  # noqa: BLE001 – Netzfehler: warten und wiederholen
            time.sleep(20 + attempt * 30)
    raise RuntimeError("API nicht erreichbar: " + url)


def plain(s):
    """Wikitext -> Klartext (Links, Vorlagen, Verweise entfernen)"""
    s = re.sub(r"<ref[^>]*?/>|<ref.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s.replace("'''", "").replace("''", "")).strip()


def rows(wikitext):
    """Vorlagenaufrufe mit ausgeglichenen Klammern herauslösen"""
    key = "{{Denkmalliste Sachsen Tabellenzeile"
    i = 0
    while True:
        i = wikitext.find(key, i)
        if i < 0:
            return
        depth, j = 0, i
        while j < len(wikitext):
            if wikitext.startswith("{{", j):
                depth += 1
                j += 2
            elif wikitext.startswith("}}", j):
                depth -= 1
                j += 2
                if depth == 0:
                    break
            else:
                j += 1
        yield wikitext[i + len(key):j - 2]
        i = j


def fields(body):
    """|Schlüssel = Wert auf oberster Ebene (Pipes in Links/Vorlagen zählen nicht)"""
    out, depth, cur, parts = {}, 0, "", []
    k = 0
    while k < len(body):
        two = body[k:k + 2]
        if two in ("[[", "{{"):
            depth += 1
            cur += two
            k += 2
        elif two in ("]]", "}}"):
            depth -= 1
            cur += two
            k += 2
        elif body[k] == "|" and depth == 0:
            parts.append(cur)
            cur = ""
            k += 1
        else:
            cur += body[k]
            k += 1
    parts.append(cur)
    for p in parts:
        if "=" in p:
            a, b = p.split("=", 1)
            out[a.strip()] = b.strip()
    return out


def main():
    (OUT / "pages").mkdir(parents=True, exist_ok=True)
    titles, cont = [], {}
    while True:
        d = api(action="query", list="categorymembers", cmtitle="Kategorie:Liste_(Kulturdenkmale_in_Dresden)",
                cmlimit="500", **cont)
        titles += [m["title"] for m in d["query"]["categorymembers"] if m["ns"] == 0]
        if "continue" not in d:
            break
        cont = d["continue"]
    seen, out = set(), []
    for t in titles:
        f = OUT / "pages" / (re.sub(r"[^\w\-]+", "_", t) + ".txt")
        if not f.exists():
            d = api(action="parse", page=t, prop="wikitext")
            f.write_text(d.get("parse", {}).get("wikitext", {}).get("*", ""), encoding="utf-8")
            time.sleep(2.0)
        n = 0
        for body in rows(f.read_text(encoding="utf-8")):
            fl = fields(body)
            try:
                lat, lon = float(fl.get("NS", "")), float(fl.get("EW", ""))
            except ValueError:
                continue
            key = (fl.get("ID", ""), round(lat, 6), round(lon, 6))
            if key in seen:
                continue
            seen.add(key)
            e, nn = TO_UTM.transform(lon, lat)
            dat = plain(fl.get("Datierung", ""))
            ym = re.search(r"(1[0-9]{3}|20[0-2][0-9])", dat)
            out.append({"id": fl.get("ID", ""), "name": plain(fl.get("Name", "")), "adresse": plain(fl.get("Adresse", "")),
                        "lat": lat, "lon": lon, "x": round(e - ORIGIN_E, 1), "z": round(-(nn - ORIGIN_N), 1),
                        "datierung": dat, "jahr": int(ym.group(1)) if ym else None,
                        "text": plain(fl.get("Beschreibung", "")), "bild": fl.get("Bild", "").strip(),
                        "commonscat": fl.get("Commonscat", "").strip(), "wikidata": fl.get("Wikidata", "").strip(),
                        "liste": t})
            n += 1
        print(f"  {t}: {n}")
    (OUT / "denkmale.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(out)} Denkmale, {sum(1 for o in out if o['bild'])} mit Bild, {sum(1 for o in out if o['jahr'])} mit Jahr")


if __name__ == "__main__":
    main()
