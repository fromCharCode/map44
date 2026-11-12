"""Gemessene Fahrbahnbreiten (tools/strassenraum.py) für build_city.road_width – nur verlässliche Messungen.

Quellen der Messung (strassenraum.road_widths_for_tile, Feld fahrbahn_quelle):
  kombiniert / osm_flaeche / osm_bordstein  – aus Flächen bzw. Bordsteinkanten quer zur Achse gemessen -> übernehmen
  osm_width                                 – OSM-Tag width (nutzt road_width ohnehin)
  fahrstreifen                              – nur Fahrstreifenzahl × Regelbreite (Schätzung) -> nicht übernehmen
Plausibilität: höchstens das 1,7-fache und mindestens das 0,6-fache der Schätzung aus den OSM-Tags (zweibahnige
Straßen: Flächenmessung erfasst oft beide Richtungsfahrbahnen samt Gleisbereich).
"""
import os

RELIABLE = {"kombiniert", "osm_flaeche", "osm_bordstein"}
_CACHE = None


def _data():
    global _CACHE
    if _CACHE is None:
        _CACHE = {}
        tile = os.environ.get("DRESDEN_TILE", "")
        if tile and os.environ.get("MAP44_NO_WIDTHS") != "1":
            try:
                from strassenraum import road_widths_for_tile
                e_km, n_km = (int(v) for v in tile.split(","))
                for k, v in road_widths_for_tile(e_km, n_km).items():
                    try:
                        _CACHE[int(k)] = v
                    except (TypeError, ValueError):
                        pass
                print(f"  Straßenbreiten: {len(_CACHE)} Wege vermessen", flush=True)
            except Exception as ex:  # pragma: no cover
                print(f"  Straßenbreiten nicht verfügbar: {ex}", flush=True)
    return _CACHE


def measured(way_id, estimate):
    """Gemessene Fahrbahnbreite (m) oder None."""
    v = _data().get(way_id)
    if not v:
        return None
    w = v.get("fahrbahn_m")
    if not w or v.get("fahrbahn_quelle") not in RELIABLE:
        return None
    w = float(w)
    if not (2.5 <= w <= 30.0):
        return None
    if estimate and not (0.6 * estimate <= w <= 1.7 * estimate):
        return None
    return w


def record(way_id):
    return _data().get(way_id) or {}


def sidewalk_width(way_id, side):
    """Gehwegbreite (m) links (+1) bzw. rechts (−1) der Digitalisierrichtung aus dem Straßenraum, sonst None."""
    v = record(way_id)
    if not v or v.get("zweibahnig"):
        return None
    k = "links" if side > 0 else "rechts"
    w = v.get(f"gehweg_{k}_m")
    src = v.get(f"gehweg_{k}_quelle") or ""
    if not w or src in ("", "regel", "regelwert", "default"):
        return None
    w = float(w)
    return w if 1.0 <= w <= 7.0 else None
