# Baualter der Gebäude in Dresden – offene Datenquellen

Stand: 2026-11-11. Ziel: jedem Gebäude der Pipeline (UTM33/EPSG:25833) eine Bauepoche zuordnen
(Barock, Gründerzeit, Reformstil/20er, NS-Zeit, 50er-Wiederaufbau, DDR-Platte IW 64/P2/WBS 70, Nachwende),
statt den Stil nur aus der Geometrie zu raten.

## Kurzfassung / Empfehlung

1. **Hauptquelle: Zensus 2022, „Gebäude nach Baujahr (Jahrzehnte)“, 100-m-Gitter** (dl-de/by-2-0).
   Flächendeckend für ganz Dresden und Umland, 10 Baujahresklassen (vor 1919, 1919–1949, dann Jahrzehnte
   bis 2016+). Enthält nur Gebäude mit Wohnraum.
2. **Ergänzung: Dresdner „Nutzungsarten (Strukturtypen)-Kartierung“** des Umweltamts (dl-de/by-2-0).
   Das ist die gesuchte Stadtstrukturtypen-Kartierung: rund 15 800 Blockflächen mit Typen wie
   C11 Blockrand, C12 Gebäudeketten, B13 Plattenbauten (Zeilen), B14 Punkthochhäuser, B12 Zeilenbau,
   A13 Mehrfamilien-Einzelhäuser/„Würfelhäuser“, A12 EFH/DHH, B11 Reihenhäuser, Kleingärten, Garagen
   und Gewerbe. Sie enthält **keine Jahreszahlen**, trennt aber Bebauungstypen sauber.
   Innerhalb der Stadtgrenze hat jedes Gebäude einen Typ.
3. Kombiniert in `data/raw/baujahre/years_grid.npz` (0,77 MB). Abfrage per `tools/build_years.py`:
   `lookup(e, n)` / `lookup_many(E, N)`.
4. Für Einzelgebäude taugen OSM-Tags nur in Ausnahmefällen (0,27 % der Gebäude). GeoSN (INSPIRE-Gebäude, LoD2)
   führt kein Baujahr.

Empfehlung für die Pipeline: Zensus-Verteilung als **Prior je Ort**, Strukturtyp und Geometrie wählen
**innerhalb** der dort vorkommenden Epochen. Barock wird weiter über Denkmal-/Kirchen-Tags und Lage bestimmt.
Details unten.

## Geprüfte Quellen

| Quelle | Inhalt | Auflösung / Abdeckung | Lizenz | Bewertung |
|---|---|---|---|---|
| **Zensus 2022 – Gebäude nach Baujahr (Jahrzehnte)** [destatis.de/static/DE/zensus/gitterdaten/Gebaeude_nach_Baujahr_Jahrzehnte.zip](https://www.destatis.de/static/DE/zensus/gitterdaten/Gebaeude_nach_Baujahr_Jahrzehnte.zip) | Anzahl Wohngebäude je Klasse: vor1919, 1919–49, 50er, 60er, 70er, 80er, 90er, 2000–09, 2010–15, ab 2016 | 100 m / 1 km / 10 km, INSPIRE-Gitter EPSG:3035, ganz DE. Im Ausschnitt: 18 406 bewohnte 100-m-Zellen, 130 295 Gebäude | **dl-de/by-2-0** | **Beste Quelle.** Die Jahrzehnte trennen 50er/60er/70er/80er, also Wiederaufbau, frühe Platte und WBS 70. **Genutzt.** |
| Zensus 2022 – Baujahr in Mikrozensus-Klassen (…_in_Mikrozensus_Klassen.zip) | vor1919, 1919–48, 1949–78, 1979–90, 1991–2000, 2001–10, 2011–19, 2020+ | wie oben | dl-de/by-2-0 | Gröber (1949–78 in einer Klasse). Einziger Vorteil ist die DDR-Ende-Grenze 1990. Liegt vor, **nicht genutzt**. |
| **Zensus 2022 – Gebäude mit Wohnraum nach Gebäudetyp/Größe** | freist. EFH/ZFH, DHH/Reihenhaus, MFH 3–6 / 7–12 / 13+ WE, andere | 100 m, EPSG:3035 | dl-de/by-2-0 | Gute Ergänzung (MFH 13+ = Großwohnsiedlung). **Genutzt** (`btype`). |
| Zensus 2011 – Gitterdaten Gebäude (BAUJAHR_MZ) | Baujahr in MZ-Klassen (1919–48, 1949–78, 1979–86, 1987–90 …) | 100 m | dl-de/by-2-0 | Durch 2022 überholt (älter, gröber). Die Zensus-2011-Seiten leiten inzwischen auf 2022 um. **Nicht geladen.** |
| **Dresden: Nutzungsarten (Strukturtypen)-Kartierung**, Umweltamt (opendata.dresden.de; WFS `kommisdd.dresden.de/net3/public/ogcsl.ashx?nodeid=1059`, OGC-API `…/net4/public/ogcapi/collections/L1267` u. a.) | Typ Ebene 1–3 je Teilblock der Erweiterten Blockkarte (EBK), Versiegelungsgrad; Steckbrief-PDF mit Typbeschreibungen | Polygone (~15 800), ganz Dresden, Fortführung jährlich (Bebauung zuletzt geändert 26.02.2026) | **dl-de/by-2-0** | **Sehr wertvoll für den Bebauungstyp**, kein Baujahr. Alle 8 Ebenen geladen (Bebauung, Grün, Erholung, Landwirtschaft, Sonstige, Verkehr, Wasser). **Genutzt** (`sst`). |
| Dresden: „Baukultur in Dresden“ (OGC-API L1090) | ~105 Punkte prämierter/neuer Bauten mit `bauzeit`, Planer | Punkte | dl-de/by-2-0 | Fast nur Neubauten nach 1990. Kann einzelne Gebäude bestätigen, **nicht geladen**. |
| Dresden: „Denkmalschutz“ (WFS nodeid=292) | nur **Denkmalschutzgebiete** (Satzungen), keine Einzeldenkmale/Baujahre | Flächen | dl-de/by-2-0 | Für Baujahre ungeeignet. |
| Dresden: „Gebäude-Leerstand nach Baujahr“, „Wohnkosten nach Baujahresgruppen“ (KST) | Tabellen ohne Raumbezug bzw. auf Stadtteilebene | – | dl-de/by-2-0 | Ungeeignet. |
| **OSM** `start_date` / `building:year` / `construction_date` / `year_of_construction` (lokale Kacheldaten) | Einzelgebäude | 350 von 128 066 Gebäuden = **0,27 %** (Fläche 1,0 %). Davon 156 nach 2010, sonst Denkmale/Kirchen; `heritage` 0,44 %, `building:architecture` 0,17 % | ODbL | Zu dünn für Flächenwirkung. Wird in `classify_style` schon genutzt und sollte Vorrang behalten. |
| GeoSN INSPIRE „SN Gebäude“ (WFS `geodienste.sachsen.de/aaa/public_inspire/alkis/bu-core2d/dls/wfs`) | ALKIS-Gebäude (Umriss, Nutzung, Zustand) | ganz Sachsen | dl-de/by-2-0 | **Kein `dateOfConstruction`** (geprüft an 915 Gebäuden in Prohlis, Altstadt und Neustadt). Ungeeignet. |
| GeoSN LoD2 (vorhanden in data/raw/lod2) | generische Attribute: Dachtyp, Höhen, Datenquellen | – | dl-de/by-2-0 | **Kein Baujahr-Attribut.** |
| GeoSN ALKIS-Bestandsdaten ohne Eigentümer (`alkis_sn.zip`, dl-de/by-2-0) | AX_Gebaeude hat optional `baujahr` | ganz Sachsen (groß) | dl-de/by-2-0 | **Nicht geprüft** (sehr großer Download). Laut INSPIRE-Ableitung ist kein Baujahr veröffentlicht, daher vermutlich leer. Falls das wichtig wird, die Datei für eine Gemeinde stichprobenartig prüfen. |
| Wikidata (Kulturdenkmale Sachsen, P1708) | Einzeldenkmale | 2 415 Dresdner Denkmale mit Koordinate, nur **328 mit Bauzeit (P571)** | CC0 | Zu dünn. |
| Wikipedia „Liste der Kulturdenkmale in Dresden-…“ | Tabellen mit Datierung + Koordinaten je Denkmal | ganz Dresden (Denkmale) | CC BY-SA 4.0 (Share-alike!) | **Nicht geprüft** (API-Ratenlimit 429). Einzige erkennbare Einzelgebäude-Quelle, die **Barock von Gründerzeit** trennt. Optionaler nächster Schritt. |
| Denkmalkarte/Denkmalliste Sachsen (LfD) | Einzeldenkmale | – | unklar | Keinen offenen WFS oder Download mit klarer Lizenz gefunden. **Nicht genutzt.** |

Quellenvermerk (Pflicht nach dl-de/by-2-0, z. B. im Spiel-Abspann):
„Zensus 2022: © Statistische Ämter des Bundes und der Länder, dl-de/by-2-0;
Strukturtypen: Landeshauptstadt Dresden (Umweltamt), dl-de/by-2-0“ (steht auch in `meta.attribution`).

## Wichtige Eigenschaften der Zensus-Daten

- Gezählt werden nur **Gebäude mit Wohnraum** (Stichtag 15.05.2022). Reine Gewerbe-, Industrie- und
  öffentliche Bauten fehlen. Dort liefert das Raster die Verteilung der Nachbarschaft (`source = nachbarschaft/1km`).
- Baujahr = Bezugsfertigstellung. Bei Um- und Anbau gilt das ursprüngliche Jahr. Bei völlig zerstörten und
  wiederaufgebauten Häusern gilt das **Wiederaufbaujahr**, was für Dresden 1945 wichtig ist.
- Geheimhaltung per **Cell-Key-Methode**: „–“ heißt „genau 0 oder auf 0 gesetzt“. In Dresden kommen die Werte
  1 und 2 nie vor, 3 aber 4× häufiger als 4. Wahre 1 und 2 erscheinen also als 0 oder 3.
  Das Skript zählt eine veröffentlichte 3 deshalb als 2. Von den Klassenwerten fehlen in Summe 17 % gegenüber
  den Gesamtzahlen, und 27 % der bewohnten Zellen haben gar keine Klassenwerte (≤ ~4 Gebäude).
- 100-m-Zellen mischen oft zwei Epochen, z. B. Gründerzeit-Blockrand mit 90er-Lückenschluss.
  Ein Einzelgebäude lässt sich daraus nur wahrscheinlich, nicht sicher datieren.
- **Barock und Gründerzeit** stecken beide in „vor1919“, **Reformstil/20er und NS-Zeit** beide in „1919–1949“.
  Zensus trennt das nicht.

## Aufbereitung: `tools/build_years.py` → `data/raw/baujahre/years_grid.npz`

Aufruf: `.venv/bin/python tools/build_years.py` (≈ 9 s) bzw. `… --test` (nur Prüforte).
Die Python-Umgebung des Projekts wird ohne `-I` gestartet. Die Rohdaten werden nur als CSV/ZIP gelesen, nichts wird ausgeführt.

Verarbeitung:
1. Zensus-CSV (100 m und 1 km) direkt aus den ZIPs lesen, Fenster EPSG:3035 x 4 567–4 604 km, y 3 096–3 132 km.
2. Je 100-m-Zelle Anteile = (Zellwerte + 4 × Nachbarschaftsanteile) / (Zellsumme + 4).
   Die Nachbarschaft ist Gauß σ = 150 m. Zellen ohne Klassenwerte erhalten die Nachbarschaft, ohne diese die 1-km-Zelle.
3. Nachabtastung auf ein UTM33-Raster mit 50 m (Gitter gegen UTM ~4° gedreht, nächster Nachbar).
4. Strukturtypen-Polygone (alle EBK-Ebenen, „Bebauung“ hat Vorrang) auf 25 m rastern.

Inhalt der npz (`np.load(..., allow_pickle=False)`):

| Feld | Form / Typ | Bedeutung |
|---|---|---|
| `meta` | JSON-String | `origin_e` 398000, `origin_n` 5644000, `width` 32000, `height` 30000, `cell` 50, `cell_sst` 25, Klassen- und Typlisten, `sst_codes/names/groups`, Quellenvermerk |
| `years` | (600, 640, 10) uint8 | Anteile der Baujahresklassen × 255 (`year_classes`) |
| `btype` | (600, 640, 6) uint8 | Anteile Gebäudetyp × 255: efh_zfh_frei, doppel_reihenhaus, mfh_3_6, mfh_7_12, mfh_13plus, andere |
| `n_bld` | (600, 640) uint16 | Wohngebäude in der 100-m-Zensuszelle |
| `src` | (600, 640) uint8 | 0 keine, 1 zelle, 2 nachbarschaft, 3 1km |
| `sst` | (1200, 1280) uint8 | Index in `meta.sst_codes` (0 = keiner) |

Index: `i = floor((n − origin_n)/cell)` (Zeile 0 = Süden), `j = floor((e − origin_e)/cell)`.
Das Raster deckt E 398–430 km und N 5 644–5 674 km ab, also alle 117 Spielkacheln plus 2 km Rand.

API (in `tools/`, z. B. aus build_city.py `from build_years import lookup, lookup_many, sample_era`):

- `lookup(e, n) -> dict` liefert `years` {Klasse: Anteil}, `eras` {vor1919, 1919-1949, wiederaufbau_50er,
  ddr_frueh_60er, ddr_wbs70, nachwende}, `era`, `dominant`, `year_median` (grobe Schätzung), `btype`, `n_bld`,
  `source`, `sst`, `sst_name`, `sst_group` und `inside`.
  Außerhalb des Rasters sind `years` und `eras` leer.
  Liegt ein Punkt knapp außerhalb eines Blocks (Straße), wird der Strukturtyp aus den 3×3 Nachbarzellen genommen.
- `lookup_many(E, N)` ist vektorisiert, 200 000 Punkte in 0,07 s. Liefert Arrays `years` (N,10), `btype`, `n_bld`,
  `src`, `sst`, `inside`.
- `sample_era(info, u)` wählt deterministisch eine Epoche für ein Einzelgebäude, z. B. mit `u = stable_rand(id)`.

Die Abbildung der Epochen auf die DDR-Serien ist eine Näherung. Die 60er werden als frühe Typen gelesen
(IW 64, P2, Q6 …), 70er und 80er als WBS 70, das ab 1973 gebaut wurde.

## Testergebnisse (`tools/build_years.py --test`)

Die Prüforte aus dem Auftrag und weitere Orte, deren Lage aus den OSM-Straßenmitten der Kacheldaten stammt:

| Ort | E / N | erwartet | Ergebnis (Top-Klassen) | n / Quelle | Strukturtyp | ✓ |
|---|---|---|---|---|---|---|
| Prohlis (Auftragspunkt) | 415500 / 5650500 | 1976–85 | **1970–79 82 %**, 1919–49 11 %, 1980–89 6 % | 0 / Nachbarschaft | D41 Gewerbe (Punkt liegt südl. der Wohnblöcke) | ✓ |
| Äußere Neustadt (Auftragspunkt) | 412300 / 5658000 | vor 1919 | **vor1919 55 %**, 1990–99 34 % | 8 / Zelle | C11 Blockrand | ✓ |
| Gorbitz (Auftragspunkt) | 406000 / 5655000 | 1980er | vor1919 47 %, **1980–89 25 %**, 1919–49 17 % | 3 / Nachbarschaft | F22 Hausgärten | ✗ (Punkt liegt an der Kesselsdorfer Str./Altgorbitz, ~700 m südwestl. der Plattenbauten) |
| Prohlis Jacob-Winter-Platz | 415593 / 5651134 | 1976–85 | **1980–89 58 %**, 1970–79 42 % | 4 / Zelle | D41 (Prohlis-Zentrum) | ✓ |
| Prohlis Herzberger Str. | 415676 / 5651290 | 1976–85 | **1970–79 98 %** | 7 / Zelle | C12 Gebäudeketten | ✓ |
| Gorbitz Omsewitzer Ring | 406471 / 5656048 | 1980er | **1980–89 98 %** (MFH 7–12 WE 86 %) | 9 / Zelle | B13 Plattenbauten | ✓ |
| Gorbitz Wölfnitzer Ring | 406985 / 5655351 | 1980er | **1980–89 97 %** | 9 / Zelle | C12 Gebäudeketten | ✓ |
| Gorbitz Leutewitzer Ring | 407184 / 5655988 | 1980er | **1980–89 95 %** | 3 / Zelle | B31 öffentl. Gebäude | ✓ |
| Zamenhofstr. (Gebäudekette) | 417147 / 5651709 | DDR | **1970–79 98 %** | 11 / Zelle | C12 | ✓ |
| Äuß. Neustadt Görlitzer Str. | 412753 / 5658101 | vor 1919 | **vor1919 60 %**, 1990–99 11 %, 1919–49 10 % | 18 / Zelle | C11 Blockrand | ✓ |
| Äuß. Neustadt Alaunstr. | 412519 / 5657987 | vor 1919 | 1990–99 44 %, vor1919 43 % | 3 / Zelle | C11 Blockrand | ~ (Punkt 10 m neben einer Zellgrenze; die Nachbarzelle mit 3 Gebäuden der 90er gewinnt) |
| Hellerau Am Grünen Zipfel | 413302 / 5662453 | 1909–13 | **vor1919 99 %** | 26 / Zelle | B11 Reihenhäuser | ✓ |
| Striesen Wittenberger Str. | 415315 / 5655708 | vor 1919 | **vor1919 51 %**, 1960–69 28 %, 1990–99 17 % | 12 / Zelle | A22 Mischbebauung | ✓ (Kriegslücken mit 60er-Bauten) |
| Hechtviertel Hechtstr. (Nordteil) | 412122 / 5659583 | vor 1919 (grob) | **1919–49 91 %** | 6 / Zelle | (Straßenrand) | ? Rohzellen zeigen 15 + 6 Gebäude 1919–49, die Daten sind also konsistent. Die Erwartung war zu grob, der Nordteil ist Zwischenkriegsbebauung. |
| Neumarkt | 411720 / 5656255 | 2004–20 | **ab2016 41 %**, vor1919 31 %, 2010–15 12 % | 3 / Zelle | P31 Plätze | ✓ |
| Altmarkt | 411531 / 5656074 | 1953–58 | ab2016 41 %, 1960–69 13 % … | 4 / Nachbarschaft | P31 Plätze | ✗ Innere Altstadt: kaum Wohngebäude, Zellen fast ganz geheimgehalten. Die Nachbarschaft wird von den Neumarkt-Neubauten dominiert. |
| Prager Straße | 411425 / 5655617 | 1965–69 | 1980–89 45 %, 1950–59 27 %, 1960–69 16 % | 0 / Nachbarschaft | D41 | ~ (DDR-Epoche stimmt, Jahrzehnt nicht; die Nachbarzelle meldet 14 Gebäude 1980–89) |

Fazit: Großwohnsiedlungen (Prohlis, Gorbitz, Reick/Zamenhofstr.), Gründerzeitviertel (Neustadt, Striesen) und
Hellerau werden richtig erkannt. Der Gorbitz-Auftragspunkt liegt außerhalb der Plattenbausiedlung, 700 m daneben
ist das Ergebnis eindeutig. Schwach ist die **Innere Altstadt** (Altmarkt, Prager Str.): Dort gibt es wenige
Wohngebäude mit vielen Adressen, die Werte sind geheimgehalten und Neubauten dominieren. Hier sollten Wahrzeichen,
Denkmal-Tags und Sonderregeln Vorrang haben (z. B. Altmarkt und Wilsdruffer Str. = 50er).

### Abgleich mit OSM-Gebäuden mit bekanntem Baujahr

Grundlage sind 353 Gebäude mit `start_date` u. ä., davon 243 Wohngebäude oder `building=yes`:

| Teilmenge | n | Klasse = häufigste Klasse der Zelle | Epoche = häufigste Epoche | mittlerer Anteil der wahren Klasse | zum Vergleich Stadtmittel |
|---|---:|---:|---:|---:|---:|
| alle | 353 | 35 % | 56 % | 26 % | 17 % |
| Wohn/yes | 243 | 37 % | 63 % | 27 % | 16 % |
| Wohn ohne Denkmal | 191 | 32 % | 65 % | 23 % | 13 % |

Die OSM-Stichprobe ist stark zu Neubauten verzerrt: 156 der 350 Gebäude sind nach 2010 gebaut, oft als Lückenschluss
in Altbauvierteln. Das ist der schwerste Fall für eine Gebietsstatistik. Für eine eindeutige Zuordnung braucht es
daher zusätzlich Geometrie und Strukturtyp.

### Abdeckung (alle 128 066 OSM-Gebäude der 117 Kacheln)

- Zensus-Anteile: 61,7 % aus der eigenen Zelle, 32,0 % aus der Nachbarschaft, 5,3 % aus 1 km, 1,0 % ohne Daten.
- Strukturtyp: innerhalb der Stadtgrenze **100 %**, außerhalb (Radebeul, Freital … in den Randkacheln) 2 %.
  Insgesamt liegen 72,9 % der Kachelgebäude in der Stadt.

### Epochenanteile je Strukturtyp (Mittel über Gebäude)

| SST | Name | Gebäude | vor1919 | 1919–49 | 50er | 60er | 70/80er (WBS 70) | Nachwende |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| C11 | Blockrandbebauung | 4757 | **55 %** | 15 % | 4 % | 3 % | 4 % | 19 % |
| C12 | Gebäudeketten | 647 | 8 % | 7 % | 2 % | 2 % | **70 %** | 11 % |
| B13 | Plattenbauten (Zeilen) | 397 | 8 % | 7 % | 2 % | 11 % | **53 %** | 19 % |
| B14 | Punkthochhäuser | 122 | 5 % | 5 % | 17 % | 23 % | 37 % | 13 % |
| B12 | Zeilenbebauung | 3771 | 18 % | **33 %** | 7 % | 14 % | 5 % | 22 % |
| B11 | Reihenhausbebauung | 2574 | 13 % | 28 % | 1 % | 1 % | 7 % | **50 %** |
| A13 | Mehrfamilien-Einzelhäuser/Würfelhäuser | 18333 | **44 %** | 21 % | 2 % | 3 % | 4 % | 25 % |
| A12 | EFH/DHH | 31437 | 18 % | 35 % | 2 % | 2 % | 6 % | **38 %** |
| A11 | Dörfliche Bebauung (Wohnen) | 3414 | **47 %** | 14 % | 1 % | 1 % | 4 % | 33 % |
| F11 | Kleingärten | 5682 | (Lauben – Zensus-Werte stammen aus der Umgebung) | | | | | |
| P21 | Parkplätze/Garagenanlagen | 812 | (Garagenreihen) | | | | | |

## Vorschlag zur Einbindung in `build_city.classify_style` (noch nicht umgesetzt)

Projektdateien wurden auftragsgemäß nicht geändert. Vorschlag:

1. Vorrang bleibt bei OSM `start_date`, `building:architecture`, `historic`/`heritage`, Kirche/Palast (→ Barock 1)
   und Industrie-Gebäudetypen (→ 5).
2. Dann `info = lookup(cx, cy)` (oder einmal `lookup_many` je Kachel):
   - `sst` in D41/A41/B41/C41/D43/D42 und Gebäude ohne Wohn-Tag → Industrie/Gewerbe (5).
   - `sst` F11/F21/F23 → Gartenlaube (klein, Holz, Satteldach). `sst` P21 → Garagenreihe.
   - Plattenbau (2), wenn `eras.ddr_wbs70 + eras.ddr_frueh_60er ≥ 0.25` **und** die Geometrie passt
     (Flachdach, ≥ 4–5 Geschosse, lang) bzw. `sst` ∈ {B13, B14, C12}. Die 60er-Anteile entsprechen IW 64/P2, die 70er/80er WBS 70.
   - Gründerzeit (0), wenn `eras.vor1919 ≥ 0.3` und Blockrand/Satteldach/Mansarde, bzw. `sst` ∈ {C11, A13, B21, C21, A11, A21}.
     A13 mit vor1919 sind die Dresdner Villen und „Kaffeemühlen“.
   - Reformstil/20er/NS (3), wenn `eras["1919-1949"]` dominiert, besonders bei `sst` B12 (Genossenschafts-Zeilenbau)
     und B11 (Reihenhäuser, z. B. Hellerau später).
   - 50er-Wiederaufbau (heute Stil 3, evtl. eigene Variante), wenn `eras.wiederaufbau_50er ≥ 0.3`.
   - Nachwende (4 bzw. modernes EFH), wenn `eras.nachwende` dominiert und kein Steildach-Altbau.
   - Sonst `sample_era(info, stable_rand(id))`. Das hält die Mischung je Viertel realistisch.
3. Barock: Zensus kann es nicht von der Gründerzeit trennen. Weiterhin über Tags und Lage regeln
   (Innere Altstadt/Neustadt, Königstraße, Hauptstraße, Dorfkerne A11/A21 mit vor1919 als „ländlicher Barock/Klassizismus“).
   Für genauere Daten bräuchte es die Wikipedia-Denkmallisten (CC BY-SA, nicht geprüft).

## Dateien

- `data/raw/baujahre/zensus2022/Gebaeude_nach_Baujahr_Jahrzehnte.zip`: Hauptquelle
- `data/raw/baujahre/zensus2022/Gebaeude_mit_Wohnraum_nach_Gebaeudetyp_Groesse.zip`: Gebäudetypen
- `data/raw/baujahre/zensus2022/Gebaeude_nach_Baujahr_in_Mikrozensus_Klassen.zip`: Alternative, ungenutzt
- `data/raw/baujahre/zensus2022/extract/*.xlsx`: Datensatzbeschreibungen (Lizenz, Zeichenerklärung)
- `data/raw/baujahre/dresden_strukturtypen/*_L12xx.csv`: OGC-API-Export (EWKT, EPSG:4326), alle EBK-Ebenen.
  `Steckbrief_Strukturtyp_Nutzungsart_A_Q.pdf` enthält die Typbeschreibungen.
- `data/raw/baujahre/years_grid.npz`: das erzeugte Raster
- `tools/build_years.py`: Aufbau und Abfrage

Neu laden der Strukturtypen (jährliche Fortführung), z. B.:
`curl -A "<neutraler UA>" "https://kommisdd.dresden.de/net4/public/ogcapi/collections/L1267/items?format=csv/ewkt&delimiter=semicolon"`
(weitere Ebenen: L1262 Wasser, L1263 Erholung, L1264 Verkehr, L1265 Sonstige, L1266 Grün, L1268 Landwirtschaft).
