# Straßenraum Dresden – offene Datenquellen, Aufbereitung, Breiten-Messung

Stand: 2026-11-12. Ziel: Fahrbahnen so breit wie in echt, Gehwege, Bordsteine und Bepflanzung wie in echt.
Ergebnis: Download-Skript `tools/fetch_strassenraum.py`, Pipeline-Modul `tools/strassenraum.py`,
Daten in `data/raw/strassenraum/` (480 MB inkl. 104 MB ALKIS-Rohcache und 265 MB Kachel-Auszüge).

## Kurzfazit

- **Stadtbäume** sind vollständig und gut: 124 483 städtische Bäume mit Art, Höhe, Krone, Stamm und Alter
  (dl-de/by-2-0). Rund 40 000 stehen in Baumscheiben im Straßenraum, 11 700 auf Grünstreifen.
- **Öffentlicher Straßenraum** (Grenze zu Grundstück bzw. Hauskante) ist flächendeckend bekannt: ALKIS
  „tatsächliche Nutzung“ von GeoSN (14 198 Flächen, kostenfrei mit Quellenangabe). ALKIS trennt aber
  **nicht** zwischen Fahrbahn, Gehweg und Grün.
- **Gemessene Fahrbahnflächen** gibt es offen nur in OSM (`area:highway`), und nur für 1,2 % der Straßenlänge,
  vor allem in der Innenstadt (Altstadt, St. Petersburger Straße, Grunaer Straße, Wilsdruffer Straße).
  Bordsteinkanten sind als OSM-Linien fast nicht erfasst (155 Linien). Bordhöhen, Rinnen und Sonderborde fehlen.
- Eine offene Dresdner Fahrbahn-, Gehweg- oder Bordsteinkarte gibt es nicht. Die Straßendatenbank des
  Straßen- und Tiefbauamts (Maße, Beläge, Straßenbegleitgrün) ist nicht veröffentlicht. Man könnte sie dort
  anfragen.
- Das ATKIS Basis-DLM (mit `breiteDerFahrbahn`) ist in Sachsen nicht als freier Vektordienst auffindbar.
  Die WFS-Adressen liefern 404. Der Katalogspiegel kennzeichnet den Datensatz als `non_open`.
- Daher **misst `road_widths_for_tile()` die Breiten selbst**: Querschnitte alle 4 m, Messquellen in fester
  Reihenfolge, sonst eine kalibrierte Ableitung aus Straßenraum, Fahrstreifen, Baumreihen und Gehweglinien.
  Die Abweichung gegenüber OSM-`width`-Tags beträgt im Mittel 1,5 m (63 % innerhalb ±1,5 m).

## Quellen und Lizenzen

| Datensatz | Anbieter / Zugriff | Lizenz | Umfang (ganz Dresden) | Inhalt / Nutzen |
|---|---|---|---|---|
| Stadtbäume (L1261) | LH Dresden, Amt für Stadtgrün; OGC API Features `kommisdd.dresden.de/net4/public/ogcapi` | dl-de/by-2-0 (im Open-Data-Portal bestätigt) | 124 483 Punkte | art_deutsch/botanisch, baumhoehe_akt, kronendurchmesser_akt, stammdurchmesser_akt, jalter, Objekt (meist Straßenname) |
| Straßenflächen (L1564) | LH Dresden, Themenstadtplan | dl-de/by-2-0 | 185 Polygone | Straßenland auf Blockebene, grob. Wird nur als Ersatz genutzt, wo ALKIS fehlt |
| Verkehrsflächen (L1264) | LH Dresden, Stadtstrukturtypen | dl-de/by-2-0 | 946 Polygone | Parkplätze (P21), Plätze (P31), Bahngelände (G11), sonstige Verkehrsflächen |
| Grün- und Freiflächen (L1266) | LH Dresden, Stadtstrukturtypen | dl-de/by-2-0 | 3 011 Polygone, davon 478 **F31 Verkehrsbegleitgrün** | Straßenbegleitgrün und Mittelstreifen auf Blockebene |
| Anlagen des Radverkehrs (L1652) | LH Dresden | dl-de/by-2-0 | 13 392 Abschnitte | Radfahrstreifen, Schutzstreifen, Radweg, gemeinsamer Geh-/Radweg, Tempo-30-Zone usw. mit Lage L/R/M |
| Straßenknotennetz SKN5 – Kanten (L123) | LH Dresden | dl-de/by-2-0 | 16 952 Kanten | Straßenschlüssel, Widmung (B/S/K/O), Straßenbahn-Kennung, Länge |
| ALKIS vereinfacht, `ave:Nutzung` | GeoSN, WFS `geodienste.sachsen.de/aaa/public_alkis/vereinf/wfs` | „kostenfrei unter Angabe der Quelle GeoSN“ (Capabilities), dl-de/by-2-0 | 14 198 Flächen (Straßenverkehr 9 057, Weg 4 357, Platz 544, Bahnverkehr 240) | Öffentlicher Straßenraum, Flurstücksgrenzen. Nur das Attribut `nutzart`, keine Fahrbahn/Gehweg-Trennung |
| OSM `area:highway` | OSM (Geofabrik-Auszug, lokal; Zahlen für das Spielgebiet) | ODbL 1.0 | 1 271 Flächen, davon ca. 540 Fahrbahn (residential 222, secondary 105, service 79, tertiary 54, primary 38 …), 295 Verkehrsinseln | Echte Fahrbahnumrisse, vor allem in der Innenstadt |
| OSM Bordsteine | OSM | ODbL 1.0 | 155 `barrier=kerb`-Linien, 4 893 Bordstein-Knoten (lowered 3 833, raised 560, flush 200) | Absenkungen an Querungen |
| OSM separate Gehwege | OSM | ODbL 1.0 | 4 581 Wege (`footway=sidewalk` u. ä.), 298 mit `width` | Lage der Gehwege |

Zur Lizenz der Themenstadtplan-Ebenen: Das Dresdner Open-Data-Portal führt alle seine Datensätze unter
dl-de/by-2-0, der Lizenzfilter kennt nur diesen Wert. Ausdrücklich geprüft wurde das für „Stadtbäume“
(Datenquelle Amt für Stadtgrün und Abfallwirtschaft). Die übrigen Ebenen stammen aus derselben öffentlichen
OGC-API (`/net4/public/`). Ihre Einzelseiten im Portal wurden nicht aufgerufen.

Geprüft, aber nicht geladen: Besonders wertvolle Gehölze (L807, 2007er Stand), Biotoptypen (L1804/L1805),
Versiegelungsklassen (L931), „Neue Gehwege“ (L1568, das sind Planungsmaßnahmen und kein Bestand),
Behindertenparkplätze (L1113), Orthophotos 2024/25 und 2025/26 (L1815/L40, nur als Bild).
Nicht verwendet wurden Google Maps/Earth/Street View/3D Tiles, Apple Look Around und das ArcGIS-LOD3-Modell
der Stadt (dessen Lizenz verbietet den Download).

**Namensnennung im Spiel**: „Datenquellen: Landeshauptstadt Dresden, Open-Data-Portal / Themenstadtplan
(dl-de/by-2-0); GeoSN – Landesamt für Geobasisinformation Sachsen (dl-de/by-2-0); © OpenStreetMap-Mitwirkende
(ODbL)“. Eine Kurzfassung liegt in `data/raw/strassenraum/QUELLEN.txt`.

Zum Feld `jalter` der Stadtbäume: Dort steht das Alter in Jahren (Median 28). 20 % der Einträge sind
„kein“ oder leer, ein Ausreißer enthält eine Jahreszahl (2025). Das Modul gibt `alter_j` aus und berechnet
daraus `pflanzjahr`; Werte > 1700 behandelt es als Pflanzjahr. Bezugsjahr ist das Änderungsdatum
(fast immer 2025/2026), daher gilt das Pflanzjahr nur ungefähr (±1–2 Jahre).

## OSM-Erfassungsgrad in Dresden (Stadtgebiet, Fahrzeugstraßen ohne service, 1 653 km)

| Merkmal | alle | Hauptstraßen (primary–tertiary, 514 km) | Wohn-/Nebenstraßen (1 056 km) |
|---|---|---|---|
| `width` | 17,9 % | 6,9 % | 23,5 % |
| `width:carriageway` / `est_width` | 0 % | 0 % | 0 % |
| `lanes` | 36,6 % | 76,3 % | 12,2 % |
| `sidewalk*` (irgendein Wert) | 73,8 % | 84,9 % | 74,2 % |
| `sidewalk=separate` | 17,0 % | 35,2 % | 9,4 % |
| `sidewalk:*:width` | **0,2 %** | 0,5 % | 0,1 % |
| `sidewalk:*:surface` | 27,2 % | 27,3 % | 29,2 % |
| `sidewalk:*:kerb` | ≈ 0 % | ≈ 0 % | ≈ 0 % |
| `parking:*` | 33,0 % | 44,0 % | 30,3 % |
| `cycleway*` | 63,3 % | 84,4 % | 57,6 % |
| `surface` / `maxspeed` / `lit` | 98 % / 89 % / 80 % | 99,6 % / 93 % / 87 % | 97 % / 86 % / 75 % |

Separat erfasste Gehwege: 2 768 Wege mit 327 km Länge. Medianwerte des `width`-Tags: residential 6,0 m
(10–90 %: 4,0–10,0), tertiary 6,7 m, secondary 5,2 m (meist eine Richtungsfahrbahn), living_street 4,5 m,
motorway 12,0 m.
Fazit: Fahrstreifenzahl, Parken und Radverkehr sind gut erfasst. Gehwegbreiten und Bordsteine fehlen in OSM
praktisch ganz.

## Verfahren in `tools/strassenraum.py`

Für jeden OSM-Weg (Fahrzeugstraßen und Fußgängerzonen) der Kachel wird alle 4 m ein Querschnitt gelegt,
6 m Abstand zu den Wegenden. Jeder Querschnitt wird vektorisiert mit Liniensegmenten geschnitten
(STRtree; 0,6 s je Kachel im Median, höchstens 5 s). Gemessen werden je Seite:

- Fahrbahnrand aus der Vereinigung der OSM-Fahrbahnflächen (`area:highway`) bzw. aus `barrier=kerb`-Linien;
- die Grenze des öffentlichen Straßenraums aus ALKIS (Straßenverkehr ∪ Platz ∪ Weg; Ersatz: Dresdner Straßenflächen);
- die erste Gebäudekante (OSM-Gebäude);
- die nächste parallele Gehweglinie. Linien hinter einer anderen Fahrbahn oder weiter als 15 m werden verworfen;
- Grünflächen (Dresden F31 und OSM grass/flowerbed/planter/village_green) mit 0,5-m-Abtastung zwischen Bord und Raumgrenze;
- Straßenbahngleise, parallele gleichnamige Fahrbahnen (zweibahnige Straßen; dann zählt die Innenseite als
  Mittelstreifen) und Dresdner Radverkehrsanlagen.

Bäume werden dem nächsten Weg zugeordnet (höchstens 22 m entfernt, nur Bäume im ALKIS-Straßenraum).
Daraus ergeben sich je Seite Anzahl, Abstand und Achsversatz.

**Fahrbahnbreite**, in dieser Reihenfolge: `osm_flaeche` (Median der Querschnitte) → `osm_bordstein` →
`osm_width` → `kombiniert` = Median aller Ableitungen, sobald mindestens zwei vorliegen. Die Ableitungen sind:
- `raum_abgeleitet`: Straßenraum minus Regelgehwege, gemessenes Grün und Hochbord-Radwege, plus Restkorrektur
  je Klasse (Hauptstraße −2,0 m, sonst −1,0 m);
- `fahrstreifen`: lanes × Regelbreite + Parkstreifen (`tools/parking.py`) + 1,6 m je Radfahr-/Schutzstreifen;
- `baumreihen`: Abstand der beiden Baumreihen minus 2 × 1,2 m, nicht an Hauptstraßen;
- `gehweglinien`.

Steht nur eine Ableitung zur Verfügung, wird sie allein verwendet.

**Kalibrierung** über alle 117 Kacheln (48 678 Wege). Abweichung = Schätzung − Referenz, nur einbahnige Querschnitte:

| Schätzer | gegen `area:highway`-Messung | gegen OSM-`width`-Tag |
|---|---|---|
| kombiniert | n=243, Median −0,15 m, mittl. Betrag 2,9 m, 43 % ≤ 1,5 m | n=2 185, Median +0,55 m, mittl. Betrag **1,5 m**, **63 %** ≤ 1,5 m |
| raum_abgeleitet | n=240, +0,17 / 3,3 m / 37 % | n=2 181, +0,75 / 2,0 m / 57 % |
| fahrstreifen | n=326, −1,5 / 4,4 m / 43 % (Hauptstraßen: −0,9 / 2,6 m / 63 %) | n=3 190, 0,0 / 1,65 m / 66 % |
| baumreihen | n=5, +0,6 / 0,9 m | n=256, −0,26 / 1,6 m / 70 % |
| gehweglinien | n=20, +1,1 / 2,5 m / 50 % | n=144, +0,9 / 2,1 m / 54 % |
| osm_width | n=9, 0,0 / 1,9 m / 78 % | – |

Die Flächenmessungen liegen fast nur an komplizierten Innenstadtstraßen mit Abbiegestreifen und Busbuchten.
Dort fallen alle Ableitungen schlechter aus.

**Herkunft der Fahrbahnbreite** (3 806 km Fahrzeugstraßen inkl. service/Autobahn): kombiniert 46,8 %,
nur Fahrstreifen 42,1 % (vor allem Zufahrten/service, Autobahn und Straßen ohne ALKIS-Raum), osm_width 9,8 %,
gemessene Fläche 1,2 %, Bordsteinlinien < 0,1 %.
**Gehwegbreite** (Länge je Seite): Regelwert 42 %, aus dem Straßenraum abgeleitet 39 %, OSM-Tag 13,5 %
(meist `sidewalk=no` → 0), aus Gehweglinien 2,6 %, Mittelstreifen 2,4 %.

## Funktionen (Pipeline-Schnittstelle)

Alle Funktionen erhalten `e_km, n_km` (SW-Ecke der 2×2-km-Kachel) und liefern Spielkoordinaten
(x = E − 411000, z = −(N − 5656200)). „links“ und „rechts“ beziehen sich auf die Digitalisierrichtung des
OSM-Wegs, wie in `tools/parking.py`. Die Daten werden je Kachel gecacht. Voraussetzung ist
`data/raw/strassenraum/tiles/<E>_<N>.json`.

- `trees_for_tile(e, n, margin=0, standort=True)` gibt eine Liste zurück:
  `{x, z, e, n, art, art_bot, hoehe_m, krone_m, stamm_cm, alter_j, pflanzjahr, objekt, strassenbaum, id, standort}`.
  `standort` ist `baumscheibe`, `gruenstreifen`, `strassenraum` (Platz/Anlage im Straßenraum) oder `ausserhalb`.
  Bäume werden strikt innerhalb der Kachel ausgegeben, wie in build_city.
- `road_widths_for_tile(e, n, ways=None)` gibt `{osm_way_id: {...}}` zurück. Kernfelder:
  `fahrbahn_m`, `fahrbahn_quelle`, `messungen`, `fahrbahn_spanne`, `achsversatz_m`, `bord_links_m/_rechts_m`
  (Achse → Bord, asymmetrisch bei Flächenmessung), `gehweg_links_m/_rechts_m` + `_quelle`, `gruen_*_m`,
  `seitenraum_*_m`, `raum_m`, `raum_links_m/_rechts_m`, `raum_gesamt_m` (zweibahnig),
  `flucht_links_m/_rechts_m` (Gebäudekante), `baeume_links/_rechts {n, abstand_m, versatz_m}`, `zweibahnig`,
  `gegenfahrbahn_seite`, `abstand_gegenfahrbahn_m`, `tram_gleise`, `radanlage`, `radanlage_lage`,
  `lanes`, `osm_width`. Fußgängerflächen (Weg mit `area=yes`) erscheinen mit `flaeche=True`. Mit `ways`
  kann man eigene Achsen übergeben: `[(id, tags, utm_xy)]`.
- `kerbs_for_tile(e, n)` gibt `{"linien": [{pts, typ, hoehe_m, quelle}], "punkte": [{x, z, typ, hoehe_m}]}` zurück.
  Mögliche `quelle`-Werte: `osm_kerb` (kartierte Bordsteinlinie) oder `osm_flaeche` (Rand der Fahrbahnflächen ohne
  Einmündungsöffnungen; Achsen werden mit 4 m Puffer herausgeschnitten). Höhen: raised 0,14 m, regular/yes
  0,12 m, rolled 0,06 m, lowered 0,03 m, flush/no 0.
- `green_strips_for_tile(e, n)` gibt `[{pts, holes, quelle, art, flaeche_m2}]` zurück. Mögliche `quelle`-Werte:
  `dresden_f31`, `osm_strassengruen` (OSM-Grünfläche innerhalb des ALKIS-Straßenraums) und `osm_insel`
  (`area:highway=traffic_island`, `art` = surface).
- `defaults_for(highway)` liefert den Regelquerschnitt `{fahrstreifen_m, gehweg_m, bordstein_m, gruen_m}`.

Schnelltest: `.venv/bin/python tools/strassenraum.py 410,5656 412,5656`.
Neu laden: `.venv/bin/python tools/fetch_strassenraum.py [--force] [--only ogc|alkis|osm|tiles]`.
Laufzeiten: OGC 1 min, ALKIS 1,5 min, OSM-Auszug 1,7 min, Kachel-Auszüge 7 s. `alkis_cache/` (104 MB GML)
darf gelöscht werden; dann lädt der nächste Lauf die Daten neu.

Vorschlag für die Einbindung in build_city (nicht umgesetzt):
1. Die Straßenmesh-Breite aus `fahrbahn_m` nehmen, bei `osm_flaeche` asymmetrisch über `bord_links/rechts_m`.
2. Die Gehwegbreite aus `gehweg_*_m`. Grenze ist höchstens `flucht_*_m`, also die Hauskante.
3. `trees_for_tile` liefert Straßenbäume mit Art, Höhe und Krone. Damit lassen sich die nDSM-Kronen aus
   vegetation.py im Straßenraum ersetzen oder zuordnen. Bei `standort=baumscheibe` eine Baumscheibe von etwa
   1,5–2 × 2 m setzen.
4. Die Bordsteinkante und -höhe aus `kerbs_for_tile`. Absenkungen (`lowered`) an Querungen.
5. Grünstreifen aus `green_strips_for_tile` in die Splat-Karte übernehmen (Gras).

## Testergebnisse (Kacheln 410,5656 / 410,5654 / 412,5656)

| Straße (OSM-Weg) | OSM-Tags | Fahrbahn (Quelle) | weitere Werte |
|---|---|---|---|
| Wilsdruffer Str. 205991584 (Richtungsfahrbahn) | lanes=1, kein width | **5,63 m** (Fläche, 56 Querschnitte, IQR 4,9–6,3) | zweibahnig, Gegenfahrbahn 17,6 m entfernt; Straßenraum gesamt **47,9 m**; Gehweg außen 8,0 m; 13 Bäume alle 8,9 m, 11,6 m von der Achse |
| Wilsdruffer Str. 313559084 | lanes=2 | **5,33 m** (Fläche) | Straßenraum 47,5 m; Gehweg außen ≥ 10 m (Altmarkt-Seite) |
| Wilsdruffer Str. 216071215 | width=4.8 | 4,8 m (Tag; Ableitung 4,6) | Straßenraum 54,4 m |
| Prager Str. 22999568 (Fußgängerzone) | – | – | Straßenraum **47,9 m** (12,4/35,8 m), Gebäude 45,8/35,5 m entfernt; 18 + 22 Bäume alle 9–10 m |
| Prager Str. 4811392 (Südteil) | – | – | Straßenraum 18,0 m |
| St. Petersburger Str. 24209433 | lanes=2 | **7,89 m** (Fläche) | zweibahnig, Gegenfahrbahn 42 m entfernt (breiter Grünmittelstreifen) |
| St. Petersburger Str. 374908611 | lanes=2 | **12,11 m** (Fläche, IQR 9,7–12,5; mit Bus-/Abbiegestreifen) | Gehweg außen 9,1 m; 29 Bäume am Mittelstreifen alle 4,9 m |
| St. Petersburger Str. 313559080 | lanes=4 | **16,2 m** (Fläche) | Grün 6,0/8,2 m |
| St. Petersburger Str. 250508599 | lanes=5 | **19,55 m** (Fläche) | – |
| Bautzner Str. 79641861 (Radeberger Vorstadt) | lanes=2, 2 Tramgleise, Radfahrstreifen | **10,15 m** (kombiniert: Raum 10,6 / Fahrstreifen 9,7) | Straßenraum 19,6 m; Gehwege 4,4/5,0 m; 37 + 33 Bäume alle 11–13 m, 6,4/7,0 m von der Achse |
| Bautzner Str. 28586200 | wie oben | 9,75 m (kombiniert) | Straßenraum 18,8 m; Gehwege 4,3/4,8 m |
| Bautzner Str. 28813887 (zweibahniger Abschnitt) | width=5, lanes=1 | 5,0 m (Tag; Ableitung 4,85) | Straßenraum gesamt 28,3 m |
| Bautzner Str. 383734605 (Albertplatz) | lanes=4 | 16,0 m (kombiniert) | Straßenraum 29,4 m |

Beim Vergleich mit OSM-`width` stimmen Tag und Ableitung an der Wilsdruffer Straße (4,8 zu 4,6 m) und an
der Bautzner Straße (5,0 zu 4,85 m) gut überein. Gemessene und getaggte Breiten an derselben Straße gibt es
in Dresden nur 9-mal; dort beträgt die Abweichung im Median 0,0 m.

Weitere Kachelzahlen 410,5656: 3 194 Bäume (1 189 Baumscheibe, 462 Grünstreifen), 70 Bordlinien aus Flächen,
7 kartierte Bordlinien, 218 Bordpunkte (179 abgesenkt), 160 Grünflächen mit 88 900 m².

## Typische Querschnitte (Fallback, wenn Daten fehlen)

Die Werte stammen aus der Fotorecherche `data/research/stadtteile_g1/g2/g4` (je Stadtteil rund 20–26 Commons-Fotos;
Maße geschätzt) und aus Regelwerten (RASt 06, EFA, FLL). Die Regelwerte sind Fachwissen und stammen nicht aus
Dresdner Daten.

| Gebietstyp (Beispiele) | Fahrbahn | Gehweg je Seite | Bordstein | Bepflanzung |
|---|---|---|---|---|
| Innenstadt/Barock (Innere Altstadt, Innere Neustadt) | 5–14 m, Hauptachsen 2×2 + Tram | **4–8 m**, Granitplatten 40×80 mit Kleinpflaster-Streifen | Granit hellgrau, 12–15 cm; Kasseler Sonderbord an Haltestellen | Baumreihen auf Plätzen (Platane, Linde), Abstand ≈ 8 m; Baumbänke |
| Gründerzeit (Äußere Neustadt, Radeberger/Leipziger Vorstadt, Pieschen, Löbtau, Johannstadt-Nord) | 5,5–9 m | **2–3,5 m**, Granitplatten-Läufer + Mosaik-/Kleinpflaster | Granit gelblich-grau, **14–16 cm**, oft alt/abgesenkt | Straßenbäume in offenen Baumscheiben (Pieschen ≈ 1,2 m), Abstand 9–12 m |
| DDR-Großsiedlung (Prohlis, Gorbitz, Johannstadt-Süd, Südvorstadt) | 5,5–7 m (Wohnstr.), Magistralen 14–16 m | **1,5–2,5 m**, Betonplatten 40×40/50×50 | Beton-Hochbord 15 cm, Granit an Hauptstraßen | Rasen-Abstandsgrün 20–40 m, Allee-Mittelstreifen 4–6 m, Rasengleis |
| Villen-/Gartenstadt (Klotzsche, Hellerau, Blasewitz, Loschwitz) | 4,5–7 m | **1,5–2,5 m**, Asphalt/Betonverbund, oft Kies-/Grasbankett | Granit niedrig, ~10 cm | Bäume in Grünstreifen, Hecken, Vorgärten |
| Ortschaften/Dorfkerne (Weixdorf, Schönfeld-Weißig, Cossebaude, Mobschatz) | 4–7 m | **1,2–2 m**, einseitig oder fehlend | Granit-Kantenstein 10–15 cm, Granit-Kleinpflaster-Rinne | Alleen an Hauptstraßen, Obstwiesen |

Regelwerte für Neubau und Ersatz:
- Fahrstreifen 2,75–3,25 m, Hauptstraße mit Tram 3,25–3,5 m.
- Radfahrstreifen 1,85 m, Schutzstreifen 1,5 m.
- Gehweg-Regelbreite 2,50 m (1,80 m Gehbereich + Abstände).
- Hochbord 10–12 cm, Dresdner Granitborde meist 12–16 cm (Recherche-Median 14 cm).
- Kasseler Sonderbord an Haltestellen 16–22 cm.
- Absenkung an Querungen 0–3 cm.
- Baumscheibe mindestens 6 m² offen (FLL), in Dresden häufig 1,5–2 × 2 m oder rund ≈ 1,2–1,5 m.
- Baumstreifen bzw. Parkstreifen mit Bäumen 2,0–2,5 m.
- Baumabstand in Reihen gemessen: 4,6–5 m (St. Petersburger Mittelstreifen), 9–10 m (Prager Straße),
  11–13 m (Bautzner Straße).

## Grenzen und mögliche nächste Schritte

1. Echte Fahrbahnkanten fehlen für 98 % der Straßen. Offene Wege dazu:
   - aus den Orthophotos (GeoSN DOP 20 cm, dl-de/by-2-0, liegen schon in der Pipeline) die Asphalt-/Pflasterkante
     quer zur Achse erkennen (Helligkeit/Textur; Bäume über CIR maskieren);
   - GeoSN-Laserpunktwolken nutzen, falls offen (Bordsteinstufe 12–15 cm). Das ist nicht geprüft und datenintensiv;
   - beim Straßen- und Tiefbauamt Dresden die Straßendatenbank anfragen (Maße, Beläge, Straßenbegleitgrün).
2. ALKIS-Grenzen sind Flurstücksgrenzen. Vorgärten, private Gehwegstreifen oder Gleisflurstücke verfälschen
   den Seitenraum. Negative Werte werden verworfen; Gehwege werden auf 10 m gekappt.
3. Die Dresdner Radverkehrsanlagen haben eine Lage L/R/M bezogen auf die Dresdner Linienrichtung. Diese wird
   unverändert ausgegeben und nicht auf die OSM-Seite umgerechnet.
4. `area:highway` umfasst teils Bus- und Abbiegestreifen. Bei Einzelwegen an Kreuzungen ist die
   Spanne (`fahrbahn_spanne`) aussagekräftiger als der Median.
