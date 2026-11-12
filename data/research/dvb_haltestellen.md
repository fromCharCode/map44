# DVB-Haltestellen (Straßenbahn und Bus): Aussehen, Maße, Datenquellen

Stand: 2026-11-12. Ziel: Dresdner Haltestellen prozedural nachbauen (Blender-Skripte) und aus Daten automatisch platzieren,
als Grundlage für einen DVB-Simulator.

**Kennzeichnung der Werte:**
- **(Q)**: aus einer Quelle belegt (Link unten).
- **(D)**: aus Daten gemessen (OSM, Dresdner Open Data). Die Auswertung steht in Teil B.
- **(g)**: aus Fotos geschätzt. Als Maßstab dienten der Mast mit Ø 76 mm, Menschen, Fahrzeughöhe und A4-Aushänge.
  Mit ±10–20 % Fehler rechnen.
- **(N)**: allgemeine deutsche Norm oder Richtlinie eines anderen Verbunds (RMV, DIN), für Dresden nicht geprüft.

Fotos zur Analyse liegen in `data/research/dvb_stops_img/` (33 Bilder, alle von Wikimedia Commons, Liste mit Lizenz am Ende
und in `_sources.jsonl`). Google-Dienste wurden nicht genutzt.

---

## Kurzfassung / Empfehlung

1. **Hauptquelle für die Platzierung ist der Dresdner Datensatz „Haltestellen Dresden – Barrierefreiheit“**
   (OGC-API `kommisdd.dresden.de/net4/public/ogcapi/collections/L1233/items`, Lizenz **dl-de/by-2-0**).
   Er liefert **jeden Haltesteig** als Punkt (1 761 Punkte, 1 690 DHIDs) mit Koordinate in EPSG:25833, Steignummer, Linien,
   Verkehrsmittel, **Bordhöhe in cm**, **Warteflächenbreite in m**, Art des Leit- und Auffindestreifens,
   Barrierefreiheitsklasse und Fotos. Das ist genauer und vollständiger als GTFS, und die Steig-IDs (DHID) sind stabil.
2. **Geometrie aus OSM ergänzen:** Bahnsteig-Linien und -Flächen (`public_transport=platform`, 594 Tram-Objekte mit Median
   62 m Länge), Wartehallen-Grundrisse (`amenity=shelter` + `shelter_type=public_transport`, 347 Flächen) und die
   Ausstattungs-Tags `shelter`, `bench`, `bin`, `tactile_paving` und `passenger_information_display`. Bei Tram-Bahnsteigen
   sind die ersten vier Tags zu ~98 % gesetzt, `passenger_information_display` zu 57 %.
   **Bordhöhe und Breite fehlen in OSM praktisch** (kerb:height 0 %, width 2 %). Diese Werte kommen aus L1233.
3. **Ausrichtung und Kante aus dem eigenen Gleis- und Straßengraph ableiten:** Der Steigpunkt wird auf das nächste Gleis
   (Tram) bzw. den nächsten Fahrbahnrand (Bus) projiziert. Die Bahnsteigkante liegt etwa 1,35–1,45 m (g) von der
   Gleisachse entfernt. Die Länge kommt aus OSM, sonst gilt 45 m für die Tram bzw. 20 m für den Bus. Zwei Punkte mit
   gleicher DHID im Abstand von 30–60 m bedeuten eine **Doppelhaltestelle** (ca. 90–100 m).
4. **Fahrplan und Linientexte aus GTFS** (gtfs.de / DELFI, CC 4.0, Fahrtziel = `trip_headsign`). GTFS-Steigkoordinaten
   sind **nicht kantengenau**: Sie liegen im Median 9 m und im 90-%-Quantil 27 m von den Stadtpunkten entfernt, und es gibt
   keine Steignummern. GTFS deshalb nur für Zeiten und Ziele nutzen.
5. **Echtzeit (WebAPI) nicht für die Spielwelt nutzen.** Sie ist inoffiziell und hat keine Nutzungsbedingungen.
   Abfahrtsanzeigen im Spiel aus dem GTFS-Fahrplan simulieren.
6. **Wartehallen:** Kein offener Datensatz, denn die Hallen gehören dem Werbepartner Wall (JCDecaux). Für das Modell gilt:
   - Standardmodell „Flachdach-Glashalle“, 4,0 × 1,5 × 2,5 m (D/g), in 1,3–1,5-m-Modulen auf 6–10 m verlängerbar.
   - Varianten: Bogendach (alt), begrünte Klimawartehalle und Sonderbauten (Postplatz, „Käseglocke“, Albertplatz).
   - Seit 2023 läuft der Austausch von 850 Hallen „im Design von Norman Foster“ (Q). Wie die neuen Hallen genau aussehen,
     ist **nicht verifiziert**.

---

# Teil A – Aussehen

## A1 Haltestellenmast (H-Mast, „Fahne“)

Bauart: senkrechter **Rundrohrmast** mit seitlich angehängter, hochkant-rechteckiger **Schildfahne** mit stark
gerundeten Ecken (Hersteller-Aufdruck **MABEG**). Die Fahne hängt an 3–4 kurzen Rohrstutzen, mit 5–8 cm Abstand zum Mast (g).
Die Fahne sitzt links oder rechts vom Mast, meist zur Fahrbahn bzw. zum Gleis hin orientiert. Die Schildfläche steht
**quer zur Fahrtrichtung** und ist damit für ankommende Fahrzeuge lesbar.
Darunter hängen am Mast 1–3 **Fahrplankästen** (A4 hoch). Die Fahne ist **modular aufgebaut**: Ihre Höhe wächst mit der
Zahl der Linienzeilen.

**Schildgenerationen:**

| Variante | Merkmale | Verbreitung |
|---|---|---|
| **Alt** (vor ca. 2010) | grauer Rahmen; H in hellgrünem Ring; Fußzeile mit VVO-Logo und Dresdner Löwe; Name in Groteskschrift | selten (Seidnitzcenter 2018) |
| **Standard 2010er** | gesamte Fläche gelb, dunkler Rahmen, H in türkisgrünem Ring auf gelbem Grund; **Name in Antiqua (Times-ähnlich)**; Fußzeile „//DVB Ihr Partner im VVO“ | sehr häufig (Walpurgisstraße 2016, Mengsstraße 2019) |
| **Neu, „StVO-konform“** (ab ca. 2021/23) | **Kopf weiß** mit gelbem Schwung (Swoosh) nach unten rechts; darin Zeichen 224 (gelbe Scheibe, grüner Ring, grünes H) mit schmalem gelbem Außenrand; Rest gelb; Name je nach Schild in Antiqua oder Grotesk (Helvetica/Arial) | zunehmend (Tolkewitz 2023, Nürnberger Platz 2024, S-Bf Plauen 2025, Diakonissenkrankenhaus 2025) |
| **Mit integrierter Anzeige** | zwischen Linienzeilen und Fußzeile ein Anzeigefenster: LED amber (3–4 Zeilen) oder „DFI-light“ (LCD) | häufig an Tram-Steigen |
| **Stele** (hohe Bauform) | freistehende, ca. 0,45 m breite, 2,5–3 m hohe gelbe Stele auf zwei Füßen; oben H, Name und Linien, unten Fahrplan- und Netzplanfelder | große Haltestellen, Doppelhaltestellen (Straßburger Platz 2008, Schillerplatz 2022) |

### Maße Mast und Schild

| Bauteil | Maß | Kennung |
|---|---|---|
| Mast, Rundrohr Ø | 0,076 m | (g), deckt sich mit dem Standardrohr 60/76 mm (Q Herstellerdatenblätter) |
| Masthöhe über Gelände | 3,3–3,6 m (Rohrende knapp über der Fahne) | (g) |
| Fahne Breite (mit Rahmen) | 0,56–0,62 m | (g) |
| Fahne Höhe (mit Rahmen) | **modular:** Kopf 0,45 + Name 0,15 (1-zeilig) / 0,25 (2-zeilig) + je Linie 0,09 + Fußzeile 0,08 m → bei 3 Linien ≈ 1,15 m, bei 6 Zeilen ≈ 1,6 m | (g) |
| Rahmen | Rundrohr Ø ≈ 0,025–0,03 m, Eckradius ≈ 0,08 m, Tiefe der Fahne ≈ 0,04 m | (g) |
| Unterkante Fahne | ≈ 2,2 m (Lichtraum über Gehweg) | (g), deckt sich mit der 2,20-m-Regel für Schilder über Gehwegen |
| H-Symbol (Zeichen 224) | Ø ≈ 0,34–0,36 m, Ringbreite ≈ 0,045 m, H-Höhe ≈ 0,17 m | (g) |
| „Steig n“ | rechts oben im Kopf, Versalhöhe ≈ 25–30 mm, Grotesk, dunkelgrau | (g) |
| Haltestellenname | Versalhöhe ≈ 45–55 mm, schwarz, zentriert, 1–2 Zeilen | (g); RMV-Richtwert 50 mm (N) |
| Liniennummer | fett (Helvetica Bold-ähnlich), Versalhöhe ≈ 55–60 mm, linksbündig | (g); RMV-Modulhöhe 100 mm (N) |
| Fahrtziel neben der Nummer | normal, Versalhöhe ≈ 22–28 mm, schwarz | (g) |
| Zeilentrenner | dünne dunkle Linien (≈ 2 mm) zwischen den Modulen | (g) |
| Fahrplankasten | Außenmaß ≈ 0,25 × 0,34 m, Rahmen dunkelgrau/oliv, Glas; Aushang A4 hoch, Kopf gelb/orange mit Liniennummer; 1–3 Kästen übereinander, Mitte bei ≈ 1,2–1,4 m | (g); RMV: A4 hoch / A3 quer, Mitte 1,20–1,30 m (N) |
| Abstand Mast zur Bordkante | ≈ 0,5–0,8 m | (g) |

**Liniennummern-Kacheln:** Am DVB-Mast gibt es **keine farbigen Kacheln**. Tram- und Buslinien stehen gleich da: schwarze
Nummer auf gelbem Linienmodul. **Rote Linienmodule** mit heller Schrift tauchen auf, z. B. am Nürnberger Platz 2024 und
(orange) am Straßburger Platz 2008. Vermutlich kennzeichnen sie zeitweilige Linien, Umleitungen oder Ersatzverkehr
(unbestätigt). Die Liniennummern-Farben des DVB-Netzplans erscheinen am Mast nicht.

**Extras am Mast:** gelbe Zusatzleiste „GuteNachtLinie“ (Nachtverkehr); bei Bus-Steigen gelegentlich ein kleiner grauer
Kasten (Lautsprecher/Blindeninfo?) neben der Fahne; Steignummer.
**Mülleimer** hängen in Dresden in der Regel **nicht am Mast**. Sie stehen frei 1–3 m daneben (siehe A2).

### Farben Mast/Schild

Die Werte sind Fotomittelwerte, für die Albedo leicht korrigiert. Wo es passt, ist die RAL-Entsprechung angegeben.

| Element | Hex (Albedo-Vorschlag) | Foto-Median (Licht!) | Bemerkung |
|---|---|---|---|
| Schild-Gelb (DVB) | `#F2B01E` | `#DC9728` (Sonne), `#E8AF50` | warmes Signalgelb, ähnlich RAL 1003 / 1023 |
| H-Ring + H, Grün | `#1F8A6C` | `#3E917F`, `#418379` | Norm RAL 6024 Verkehrsgrün (`#008754`); Fotos wirken türkis, ausgebleicht |
| Kopf weiß (neue Schilder) | `#F2F2F2` | `#F0F0F6` | |
| Schrift | `#1A1A1A` | – | |
| „Steig n“ | `#4A4A4A` | – | |
| Schildrahmen | `#1C1C1C` | `#141311` | Rundrohr, fast schwarz |
| Mast (Bestand) | `#33363A` | `#342E29` | anthrazit/schwarzgrau, ähnlich RAL 7021 oder DB 703 |
| Mast (neuere Steige) | `#A9AEB2` | `#AEB3B6` | silbergrau (z. B. Diakonissenkrankenhaus 2025), nicht überall |
| rotes Linienmodul | `#C8312A` | – | Sonderfall |

## A2 Wartehallen (Fahrgastunterstände)

**Betreiber:** Die rund 800 Hallen gehören der **Wall GmbH (Berlin, Teil von JCDecaux)**. Wall ist seit 1991
Außenwerbepartner der Stadt (Q). Ein neuer Werberechtsvertrag läuft vom 1.1.2023 bis 2037:
- **850 neue Fahrgastunterstände „im Design von Lord Norman Foster“** (Q)
- 59 % weniger Werbestandorte, dafür 70 digitale City-Light-Poster in der Innenstadt (Q)

Fotos zeigen den Aufdruck „JCDecaux“ auf den Vitrinen. **Ströer/DSM spielen bei den Dresdner Wartehallen keine Rolle**
(kein Beleg gefunden).

**Typen (aus Fotos):**

| Typ | Beschreibung | Beispiele |
|---|---|---|
| **W1 Flachdach-Glashalle** (Standard, sehr häufig) | dünnes Flachdach (Glas oder Blech, Stirnkante ≈ 8–12 cm) auf 4–6 schlanken Rechteckpfosten; Glasrückwand in 2–4 Feldern mit Mittelriegel; Glasseitenwand an 1–2 Stirnseiten; Front offen. An einer Stirnseite **City-Light-Vitrine** (doppelseitig, in die Halle integriert oder frei davor). Innen ein Sitzbalken oder eine schmale Bank an der Rückwand, Fahrplan-/Infovitrine („Information“ mit gelbem DVB-Kopf). An der Dachfront oft eine **gelb-orange Namensblende** mit Haltestellennamen in schwarzer Grotesk oder ein gelber **DVB-Logokasten** auf dem Dach. | Leubener Str., Seidnitzcenter, Wasaplatz (lang), Walpurgisstr., Vahlteichstr., Trachauer Str. |
| **W2 Bogendach** (1990er, Auslaufmodell) | gewölbtes Glasdach mit dunklem Rahmen, Glaswände | Straßburger Platz 2008 |
| **W3 offenes Flachdach / neues Design** | Dach nur auf Pfosten, kaum Wände, anthrazit; freistehende JCDecaux-Vitrine. Ob das die neuen „Foster“-Hallen sind, ist **unbestätigt**. | Tolkewitz Schulcampus 2024 |
| **W4 begrünte Klimawartehalle** (Pilot) | anthrazit lackierter Stahlrahmen aus Rechteckrohr, Wände und Dach aus Edelstahl-Seilnetz mit Kletterpflanzen (Wilder Wein), Bank innen. Gehört zum Projekt „hitzeangepasste Haltestellen“ (FH Erfurt / Stadt / DVB). | Julius-Vahlteich-Straße 2024 |
| **W5 Sonderbauten** | Postplatz: großes Stahl-Glas-Dach der Zentralhaltestelle (2006, dunkelgraue Fachwerkträger); „Käseglocke“ Postplatz (historischer Rundbau); Albertplatz: runder DVB-Servicepavillon mit Kegeldach; Hauptbahnhof Wiener Platz: Haltestelle unter der Bahnbrücke | als Unikate modellieren |

**Maße Wartehalle W1:**

| Größe | Wert | Kennung |
|---|---|---|
| Grundriss (OSM-Flächen, 347 Stück) | Länge Median **4,2 m** (q25 3,7 / q75 5,9), Tiefe Median **1,7 m** (q25 1,4 / q75 2,0). Häufigste Kombination **4,0 × 1,5 m**, dann 3,5 × 1,5 und 4,5 × 1,5 | (D) |
| Modulbreite (Glasfeld) | 1,25–1,5 m; Standard 3 Felder, große Haltestellen 5–7 Felder (6–10 m) | (g) |
| Höhe Dachunterkante | ≈ 2,3 m | (g) |
| Höhe Dachoberkante | ≈ 2,45–2,55 m | (g) |
| Dachüberstand vorn | ≈ 0,2–0,3 m | (g) |
| Pfosten | Rechteckrohr ≈ 60 × 60–80 mm | (g) |
| Glas | ESG, klar, ≈ 10 mm; untere Kante ≈ 0,1 m über Boden; häufig ein Querriegel oder Kontraststreifen bei ≈ 1,0–1,5 m | (g) |
| City-Light-Vitrine | Sichtfläche 1,19 × 1,75 m (Plakat 4/1); Gehäuse ≈ 1,3 × 1,9 × 0,15 m, Füße ≈ 0,1 m | Plakatformat (N), Gehäuse (g) |
| Sitzbank innen | Sitzhöhe ≈ 0,45 m, Länge 1,2–1,8 m, Sitzbalken ≈ 0,3 m tief | (g) |
| Namensblende | ≈ 2,0 × 0,15 m an der Dachfront; Text schwarz, Versalhöhe ≈ 70 mm | (g) |
| Beleuchtung | im Dach integrierte LED-Leiste (Dachunterseite) und hinterleuchtete City-Light-Vitrine; nachts wirkt die Vitrine als Hauptlichtquelle | (g) |

**Farben Wartehalle:**

| Element | Hex | Bemerkung |
|---|---|---|
| Pfosten/Rahmen/Dach | `#3D4241` | Foto-Median `#3B423F` / `#4A4C49`, ähnlich RAL 7021/DB 703 |
| Glas | Tint `#DDE6E8`, Alpha 0,15, Roughness 0,05 | |
| Namensblende gelb-orange | `#F2A93B` | Foto-Median `#DFAC6A` |
| City-Light-Rahmen | `#1E1E1E` | Aufdruck „JCDecaux“ weiß oben |
| Klimahalle Stahl | `#5F6470` | |

**Weitere Stadtmöbel an Haltestellen:**
- **Sitzgruppe frei** (sehr typisch für Dresden): 2–4 Einzelschalensitze aus Lochblech an einem Rohrbalken,
  anthrazit/schwarz (`#2B2D2F`), Sitzhöhe ≈ 0,45 m, Länge ≈ 1,6–2,0 m (g). Beispiele: Walpurgisstr., Prohlis,
  Schillerplatz, Vahlteichstr.
- **Abfallbehälter**, 4 Typen:
  1. alter Rundbehälter, bronze/dunkelbraun gerippt, mit gewölbtem Deckel (`#353531`), Ø ≈ 0,4 × 0,9 m;
  2. Edelstahl-Zylinder mit schrägem Deckelschnitt (`#B8BCC0`), Ø ≈ 0,35 × 1,0 m;
  3. Stadtreinigung-Behälter, eckig grau mit **orangem Deckel** (`#3A3A39` / `#D35A22`), ≈ 0,45 × 0,35 × 0,95 m;
  4. schwarzer Rundbehälter.

  Alle Maße (g). Bin-Modell im Projekt (`assets/models/furniture/bin_public.glb`) entsprechend variieren.
- **Fahrkartenautomat** DVB: gelb (`#F2B21B`) mit grauer Front, ≈ 0,6 × 0,4 × 1,8 m (g), an größeren Tram-Steigen.
- **Leuchten am Bahnsteig:** dunkle oder silbergraue Mastleuchten 4,5–6 m mit flachem Rechteckkopf (g).

## A3 Dynamische Fahrgastinformation (DFI)

Mehr als **700 elektronische Abfahrtstafeln** sind im Einsatz (Q, 2026). Typen:

| Typ | Form / Montage | Anzeige | Größe |
|---|---|---|---|
| **Große LED-Matrix-Tafel** (Knotenpunkte; Hbf und Pirnaischer Platz bekommen 2026 acht neue) | Gehäuse an **L-förmigem „Galgenmast“** (Rohr Ø ≈ 0,15 m, Ausleger ≈ 1,2 m) oder unter dem Dach abgehängt. Unterkante ≈ 2,5 m (g). Bestand: schwarzes Gehäuse, rechts ein gelbes Feld mit **Analoguhr** und DVB-Logo (Schillerplatz). | 4–8 Zeilen, **amber/gelb-orange LED** auf Schwarz. Spalten: Linie, Ziel, Minuten | ≈ 1,4 × 0,6 × 0,15 m (g) |
| **Alt (ADtranz, um 2000–2008)** | gelbes Kunststoffgehäuse mit runden Ecken am Galgenmast, rechts Analoguhr und Stadtwappen | Kopfzeile „Linie Ziel in Min.“, gelbgrüne LED-Punktmatrix | ≈ 1,35 × 0,6 m (g) |
| **Kleine LED-Anzeige im H-Schild** | integriert zwischen Linienzeilen und Fußzeile der Fahne | 3–4 Zeilen amber, schwarzes Fenster | ≈ 0,45 × 0,22 m (g) |
| **DFI-light** | im H-Schild, Akku, ohne Netzanschluss (Q) | reflektierendes LCD, dunkle Schrift auf grau-weiß, Kopf „Linie … in Min“, 2 Zeilen | ≈ 0,45 × 0,15 m (g) |
| **ePaper** (neu 2026; Riegelplatz, Overbeckstraße u. a.) | Akku für ca. 3 Jahre plus Solarmodul (Q), am Mast | schwarz auf weiß, **13″, 1 600 × 1 200 px** (Q) | ≈ 0,3 × 0,23 m Fenster (Q/g) |

**Typische Anzeige:** `3  Wilder Mann    2`, `7  Weixdorf    5`, `10 Friedrichstadt  sofort`. Dazu kommen Laufschrift für
Störungen und Kopfzeile „Linie  Ziel  in Min“. Abfahrten innerhalb 1 Minute stehen als `sofort` oder `0` da (beides kommt
vor, nicht verifiziert).

**Farben:** LED amber `#FFA51F` (Emission, Pixelraster ≈ 4–5 mm); Gehäuse `#1A1A1A`; gelbes Uhrfeld `#F2B01E`;
LCD-Grund `#C9CCC4`, Schrift `#202020`; ePaper-Grund `#E9E9E4`.

## A4 Bahnsteige / Haltestelleninseln

**Bauformen in Dresden:**

| Typ | Beschreibung | Beispiele (Fotos) |
|---|---|---|
| **Seitenbahnsteig an eigener Gleistrasse** | Gleis auf besonderem Bahnkörper (Rasen- oder Schottergleis), Bahnsteig seitlich; zur Gegenrichtung oder Fahrbahn ein **Rohrgeländer** | Prohlis Gleisschleife, Straßburger Platz, Walpurgisstraße, Vahlteichstraße |
| **Haltestelleninsel (Mittelinsel)** | Insel zwischen Gleis (Straßenmitte) und Fahrbahn; Zugang über Ampel und Rampe (≤ 6 %, Restschwelle ≤ 3 cm (Q)); fahrbahnseitig Geländer bzw. Schutzgitter | Albertplatz, Pirnaischer Platz |
| **Haltestellenkap** | Gehweg bis an das straßenbündige Gleis vorgezogen. Neuere Kaps (2024/25) haben einen **Radweg zwischen Bahnsteigkante (schmaler Einstiegsstreifen) und Gehweg** auf Bahnsteigniveau. | Wasaplatz, Tolkewitz Schulcampus, Diakonissenkrankenhaus, Trachauer Straße |
| **Überfahrbares Kap / Zeitinsel** | Fahrbahn im Haltestellenbereich auf Bahnsteighöhe angehoben (Rampe), Autos warten hinter der Bahn; laut DVB eine „Dresdner Haltestellenlösung“ (Q) | Leubener Straße (Rampe sichtbar) |
| **Zentralhaltestelle** | mehrere Steige und Gleise, Bus und Tram gemeinsam, große Dachanlagen | Postplatz, Hauptbahnhof, Bahnhof Mitte, Pirnaischer Platz |
| **Fahrbahnrand ohne Kap** (Altbestand) | Einstieg über die Fahrspur vom normalen Bordstein | Cotta, Gottfried-Keller-Str. (2020) |

**Maße:**

| Größe | Tram | Bus | Kennung |
|---|---|---|---|
| Bordhöhe Soll | **23–24 cm** über Schienenoberkante (Combibord 240 mm) | **18 cm** | (Q) DVB-Fakt 2012, Amtsblatt 2021, Kassel-kerb-Artikel |
| Bordhöhe Ist (L1233, gemessene Steige) | Median 22 cm; häufig 22 / 24 / 23 cm; Bestand bis 12 cm | Median 18 cm (q10 9 / q90 22); häufig 20 / 22 / 19 / 18 cm; Altbestand 10–14 cm | (D) |
| gemeinsame Tram/Bus-Steige | Median 22 cm, häufig 24 / 22 / 23 / 20 cm | | (D) |
| Restspalt / Restschwelle | ≤ 5 cm / ≤ 5 cm (Bus ≤ 8 cm Schwelle) | | (Q) |
| Warteflächenbreite am Einstieg | Median **3,0 m** (q10 1,9 / q90 4,2) | Median 2,8 m (q10 1,75 / q90 4,7) | (D) L1233 |
| kombinierte Steige Breite | Median 3,3 m (q10 2,4 / q90 5,1) | | (D) |
| Bahnsteiglänge | **45 m** für eine Bahn (NGT D12DD ≈ 45 m; Ausbaustandard 45 m (Q, Niedersedlitz)). Doppelhaltestelle ≈ 90–100 m. OSM-Linien: Median 62 m, q25 49 / q75 73 m | Median 19 m (q25 15,5 / q75 22) | (Q)/(D) |
| Gleisachsabstand (Neubau) | 3,0 m (für 2,65 m breite NGT DX DD) | – | (Q) Amtsblatt 2021 |
| Bahnsteigkante ↔ Gleisachse | ≈ 1,35–1,45 m (Fahrzeug 2,65 m bzw. 2,30 m breit, Spalt ≤ 5 cm) | – | (g), abgeleitet |
| Rampe Inselzugang | ≤ 6 % | | (Q) |
| Höhe Geländer | ≈ 1,0 m, 2 Holme (Handlauf und Knieholm), Pfosten alle ≈ 2 m, Rundrohr Ø ≈ 0,05 m | | (g) |

**Dresdner Combibord:** Patentierter Bordstein (DE 19730055, 1997), entwickelt für die NGT6DD. Der Betonbordstein hat
unten ein Profil mit Hohlkehle. Busreifen rollen daran nah an die Kante heran, sodass Bus und Tram denselben Bahnsteig
nutzen können (Q). In den Fotos ist er gut zu sehen: helle Betonblöcke von ca. 1 m Länge mit gerundeter unterer Kante
(Tolkewitz 2024).

**Bodenbelag und Blindenleitsystem:**
- **Pflaster:** graues Betonsteinpflaster, Rechteck ca. 20 × 10 cm im Läufer- oder Fischgrätverband.
  - Farben: Bestand dunkelgrau (`#5F6065`, Prohlis) bzw. warmgrau (`#7C7468`); Walpurgisstraße teils rotbraun; neuere
    Kaps mit hellen Granit- oder Betonplatten (`#CCC5BD`, z. B. 60 × 40 cm).
  - Gleisbereich in der Altstadt und am Hbf: Granit-Groß- oder Kleinpflaster (`#8A8580`).
- **Kantenstreifen:** helles Betonband an der Bahnsteigkante (Combibord + 0,3–0,5 m Platte, `#9C9F98`–`#B8B5AE`).
- **Leitstreifen** (längs, Dresden-Daten L1233):
  - Häufigkeit nach Art: **Rillenplatten** 444, Rippen 96, Kleinpflaster 49, Noppen 10 (D).
  - Ausführung: hellgrau (`#C6C2BF`), ≈ 0,3 m breit, parallel zur Kante in ≈ 0,6 m Abstand (N, DIN 32984); auf älteren
    Inselbahnsteigen auch als Mittelstreifen (Straßburger Platz 2008).
- **Auffindestreifen** (quer vom Gehweg zum Einstieg):
  - Häufigkeit nach Art: **Kleinpflaster** 415, Rippe 99, Rille 83 (D). In Dresden also oft ein Streifen aus
    Natursteinkleinpflaster.
  - **Einstiegsfeld** an der vorderen Tür: Noppen- oder Rippenplatten ca. 0,9 × 1,2 m (N).
- **Entwässerung:** Schlitzrinne bzw. Kastenrinne längs hinter der Kante (Walpurgisstraße).

**Geländer und Schutzgitter:** Rohrgeländer anthrazit oder schwarz (`#2F3234`), 2 Holme, an Seitenbahnsteigen zur
Gegenrichtung. An Mittelinseln zur Fahrbahn Schutzgitter mit Füllung aus Lochblech oder Glas (Vahlteichstraße:
anthrazit Rahmen + graue Füllplatte, Höhe ≈ 1,0–1,1 m). Fußgängerdurchlass am Inselende, dort Z-Sperre bzw. versetzte
Gitter (g).

## A5 Unterschiede Bus- vs. Tramhaltestelle

| Merkmal | Tram | Bus |
|---|---|---|
| Kante | 23–24 cm, Combibord, ≈ 1,4 m von Gleisachse | 18 cm (Kasseler oder Combibord), oft Altbestand 10–14 cm |
| Länge | 45 m (Doppelhaltestelle ≈ 90–100 m) | ≈ 18–20 m (Gelenkbus 18 m) |
| Lage | Insel, Seitenbahnsteig, Kap, Zentralhaltestelle | Gehwegrand oder Busbucht. Fahrbahn mit **Zickzack-Grenzmarkierung (Zeichen 299)** vor dem Steig (Walpurgisstraße) |
| Wartehalle (OSM `shelter=yes`) | 81 % der Tram-Bahnsteigobjekte | 39 % |
| Bank (`bench=yes`) | 85 % | 49 % |
| Mülleimer (`bin=yes`) | 92 % | 69 % |
| Blindenleitstreifen (`tactile_paving=yes`) | 64 % | 38 % |
| DFI (`passenger_information_display=yes`) | 44 % aller Objekte (77 % der getaggten) | 8 % aller Objekte |
| Mast | Fahne, oft mit integrierter DFI; große Steige mit Stele und Galgen-DFI | Fahne mit Fahrplankästen; DFI-light oder ePaper an Nebenhaltestellen |
| Geländer | häufig (eigene Trasse, Inseln) | selten |

Prozentwerte (D) aus OSM, je Plattform-Objekt. Doppelt erfasste Objekte (Knoten + Linie) verzerren leicht.

---

# Teil B – Datenquellen

## B1 OpenStreetMap

**Lizenz:** ODbL. Ausgewertet wurde die lokale Geofabrik-Datei `data/raw/geofabrik/sachsen.osm.pbf` (Stand 2026-11-09,
Rahmen 13.579–13.966 °E / 50.975–51.178 °N, also Stadt Dresden plus etwas Randgebiet).
Die Stichprobe kam per Overpass (eine Abfrage, Stand 2026-11-11). Skripte liegen im Scratchpad und sind nicht Teil der
Pipeline.

**Gesamtbild** (`public_transport=platform`: 3 556 Objekte, davon 2 398 Knoten und 1 158 Wege; 2 818 `stop_position`,
davon 612 Tram):

| Tag | alle | Tram-Bahnsteige (594) | nur Bus (2 438) |
|---|---|---|---|
| name | 96 % | 93 % | 99 % |
| shelter | 97 % | 99 % | 98 % |
| bench | 97 % | 99 % | 97 % |
| bin | 91 % | 98 % | 89 % |
| tactile_paving | 88 % | 98 % | 85 % |
| lit | 83 % | 96 % | 80 % |
| wheelchair | 70 % | 90 % | 62 % |
| passenger_information_display | 29 % | 57 % | 26 % |
| departures_board | 9 % | 9 % | 10 % |
| ref:IFOPT (DHID) | 34 % | 17 % | 43 % |
| local_ref (Steig) | 22 % | 46 % | 19 % |
| route_ref | **0,6 %** | 0,5 % | 0,5 % |
| kerb | 7 % | 11 % | 7 % |
| **kerb:height** | **0 %** | 0 % | 0 % |
| height | 0,4 % | 2 % | 0 % |
| width | 2 % | 8 % | 1 % |
| surface | 11 % | 35 % | 5 % |

**Geometrie:**
- Tram-Bahnsteige sind meist als **Linie entlang der Kante** erfasst (371 Linien, Länge Median 62 m), nur 29–39 als
  **Fläche** (`highway=platform` + `area=yes`; Länge Median 56 m, Breite Median 3,7 m).
- Bus-Bahnsteige: 638 Linien (Median 19 m), 41 Flächen.
- Wartehallen als Grundriss: 347 Wege `amenity=shelter` + `shelter_type=public_transport`, 50 als Knoten.
- Weitere Objekte im Rahmen: 8 819 Bänke, 3 125 Mülleimer, 207 Fahrkartenautomaten (`vending=public_transport_tickets`),
  256 Litfaßsäulen; nur 34 DFI-Anzeigen sind als eigene Objekte erfasst.

**Stichprobe Overpass (Plattform-Objekte im Namensbereich, je Haltestelle):**

| Haltestelle | Plattform-Obj. (Tram) | Fläche | shelter/bench/bin/tactile | PID getaggt | width | height / kerb:height | separate Objekte < 25 m |
|---|---|---|---|---|---|---|---|
| Postplatz | 27 (8) | 3 | 27/27 je | 20 | 2 | 0 / 0 | 8 Bänke, 2 Automaten, 4 Leuchten, Leitstreifen |
| Pirnaischer Platz | 19 (8) | 2 | 19/19 je | 12 | 4 | 0 / 0 | 14 Bänke, 5 Mülleimer, 2 Hallen-Grundrisse, Geländer |
| Albertplatz | 14 (4) | 0 | 14/14 je | 14 | 2 | 0 / 0 | 3 Bänke, Zäune, 5 Leuchten |
| Hauptbahnhof (inkl. Bus) | 27 (12) | 4 | 27/27 je | 20 | 2 | 0 / 0 | 8 Bänke, 5 Mülleimer, 3 Automaten, 1 Halle, 8 Leuchten |
| Straßburger Platz | 16 (12) | 1 | 16/16 je | 12 | 0 | 0 / 0 | 5 Handläufe, 6 Leuchten |
| Walpurgisstraße | 8 (4) | 0 | 8/8 je | 8 | 0 | 0 / 0 | 6 Bänke, 2 Mülleimer, 6 Zaunlinien, 1 Halle |
| Prohlis, Gleisschleife | 3 (2) | 0 | 3/3 je | 0 | 0 | 0 / 0 | – |
| Wasaplatz | 13 (4) | 0 | 13/13 je | 10 | 0 | 0 / 0 | 5 Hallen-Knoten, 3 Automaten |

**Fazit OSM:**
- **Vorhandensein** der Ausstattung (Halle, Bank, Mülleimer, Leitsystem, Licht) ist in Dresden sehr gut erfasst.
- **Lage und Länge der Bahnsteige** ist ordentlich erfasst, meist als Linie.
- **Maße fehlen** (Höhe, Breite) und `route_ref` fehlt fast immer. DHIDs sind nur an 17 % der Tram-Objekte gesetzt.
- Doppelerfassung (Knoten mit Tags + Linie) kommt häufig vor und muss dedupliziert werden. Der Code dafür steht schon in
  `tools/street_life.py` (Zeilen ~300–360).

## B2 Fahrplandaten (GTFS / DELFI / NeTEx)

| Quelle | Inhalt | Lizenz / Zugang | Bewertung |
|---|---|---|---|
| **gtfs.de „nv_free“** `https://download.gtfs.de/germany/nv_free/latest.zip` (~285 MB) | deutschlandweiter Nahverkehr aus DELFI-Daten: agency, stops, routes, trips, stop_times, calendar, ca. 30 Tage | „Creative Commons 4.0“ (BY oder BY-SA unklar), Attribution DELFI e.V. + gtfs.de + OSM-Mitwirkende (`attributions.txt`) | **Für Fahrplan und Fahrtziele nutzen.** Keine shapes, keine Tarife, IDs intern und instabil |
| **VVO-Ausschnitt** (Community, wöchentlich) `https://github.com/kiliankoe/vvo/releases/latest/download/vvo-gtfs.zip` (6,7 MB, geprüft am 2026-11-12) | Fahrten mit Halt im VVO-Gebiet, aus gtfs.de geschnitten | wie gtfs.de | Bequem zum Entwickeln. 17 901 Stops (6 271 Stationen, 11 630 Steige), **Dresden 1 371 Steige, nur 43 mit `platform_code`** |
| VVO selbst | **kein eigener GTFS-Feed** gefunden (Seite „Fahrplan für Entwickler“ bietet nur Widgets und Linkgenerator) | – | – |
| **VVO_STOPS.JSON** `https://www.vvo-online.de/open_data/VVO_STOPS.JSON` (3,3 MB, täglich) | 3 911 Haltestellen **auf Haltestellenebene** (gid = DHID, Name, Ort, WGS84, Linienliste mit Betreiber, Verkehrsmittel, LineNr) | keine Lizenzangabe gefunden | Gut für die Zuordnung DHID ↔ WebAPI-ID (`33000037`); **keine Steige** |
| **DELFI-Sollfahrplan (GTFS/NeTEx), zHV** via `opendata-oepnv.de` | deutschlandweit, NeTEx mit Steigen; zHV = zentrales Haltestellenverzeichnis mit allen DHIDs bis zur Steigebene und Koordinaten | Registrierung nötig; Lizenz je Datensatz (laut Dritten CC BY 4.0, **nicht verifiziert**) | Nur nötig, wenn L1233 außerhalb Dresdens fehlt (Umland) |

**Genauigkeit der GTFS-Steigkoordinaten:**
- Abstand zum Dresdner Steigpunkt (L1233): Median **9 m**, q25 5,7 m, q75 16 m, q90 27 m.
- 1 223 von 11 630 GTFS-Steigen haben exakt die Koordinate der Station.
- Koordinaten mit 5–6 Nachkommastellen.
- **Nicht kantengenau.** Für die Bahnsteigkante immer das Gleis bzw. die Fahrbahn aus dem eigenen Graph nehmen.

## B3 Echtzeit / Abfahrtsmonitor (nur beschrieben, nicht abgefragt)

| Schnittstelle | Zugang | Bedingungen |
|---|---|---|
| **VVO WebAPI** `POST https://webapi.vvo-online.de/dm`, JSON `{"stopid":"33000028" oder "de:14612:28","limit":10,"mot":["Tram","CityBus"],"format":"json"}` | ohne Anmeldung, CORS offen. Antwort `Departures[]` mit `LineName`, `Direction`, `Platform{Name,Type}`, `Mot`, `ScheduledTime`, `RealTime`, `State`. Weitere Endpunkte: `/tr/pointfinder`, `/dm/trip`, `/rc` (Linienänderungen) | **inoffiziell**, Doku nur reverse-engineered (Community-Repo kiliankoe/vvo), keine Nutzungsbedingungen. Gelegentlich 503 und IP-Sperren. Kontakt für Großnutzung: `opendata@vvo-online.de` |
| VVO Widget API `http://widgets.vvo-online.de` / Abfahrtsmonitor-iFrame | GET | laut Community-Doku **nur nichtkommerziell**, Fair Use |
| **TRIAS** `http://efa.vvo-online.de:8080/std3/trias` (VDV 431-2) | offiziell, `RequestorRef` „OpenService“ | kommerzielle Nutzung nur mit Vereinbarung |
| SIRI ET (DELFI, Mobilithek) | Registrierung bei Mobilithek | CC BY-SA (laut Community-Doku) |
| GTFS-RT `https://realtime.gtfs.de/realtime-free.pb` | frei, beta, nur TripUpdates und Alerts | CC BY-SA 4.0 |
| DVB WebDFI `dfi.dvb.de` | nur Geschäftskunden | – |

**Empfehlung:** Im Spiel die Abfahrten aus dem GTFS-Fahrplan **simulieren**. Wenn überhaupt eine Live-Option kommen soll,
dann nur als Opt-in für die eine Haltestelle, an der der Spieler steht: höchstens 1 Abfrage pro 30–60 s mit Cache und
neutralem User-Agent. Vor einer Veröffentlichung den VVO um Erlaubnis fragen.

## B4 Open Data Dresden

| Datensatz | Zugang | Inhalt | Lizenz |
|---|---|---|---|
| **Haltestellen Dresden – Barrierefreiheit (L1233)** | OGC API: `https://kommisdd.dresden.de/net4/public/ogcapi/collections/L1233/items?f=json` (ohne `limit` alle; `crs=…/EPSG/0/25833` möglich). WFS: `https://kommisdd.dresden.de/net3/public/ogc.ashx?NodeId=1593&Service=WFS&Request=GetCapabilities`. Themenstadtplan stadtplan.dresden.de | **1 761 Punkte / 1 690 DHIDs** (Bus 949, Straßenbahn 402, Straßenbahn + Bus 153, Regionalverkehr 232, ALITA 25; zuletzt geändert 2026-11-05). Felder: `globale_id` (DHID, z. B. `de:14612:28:2:6` = Dresden / Hbf / Bereich 2 / Steig 6), `hst_name`, `steig`, `verkehrsmittel`, `verkehrende_linien`, `bordhoehe` [cm], `breite` [m], `ls_txt` (Leitstreifen), `afs_txt` (Auffindestreifen), `best_einstieg` (10 = barrierefrei ohne Rampe … 40 = keiner), `dvb_atlas` (vermutlich 2/1/0 = DVB-Atlas-Kategorie), `x`/`y` EPSG:25833, `aend_dat`. Dazu Fotolinks (1 395 Steige mit Fotos) | **dl-de/by-2-0** (GovData/DCAT). Quellenvermerk „Landeshauptstadt Dresden“. Fotos nur einzeln ansehen, nicht massenhaft laden (Bildrechte nicht gesondert angegeben) |
| Straßenbahnlinien (L457, L457..1–12) | OGC API | Linienverläufe als MultiLineString, Takt | dl-de/by-2-0 (vermutlich) |
| Buslinien (L1076) | OGC API | Linienverläufe | dl-de/by-2-0 (vermutlich) |
| Straßenbahntrassen SKN5 (L124), KUEK5 (L80) | OGC API | Gleistrassen-Geometrie | dl-de/by-2-0 |
| Infoportal Barrierefreiheit – Verkehr (L1171/L1172) | OGC API | Verkehrseinrichtungen (Bahnhöfe, Servicepunkte) mit Eingängen | dl-de/by-2-0 |
| DVB-Servicepunkte (L1087) | OGC API | Kundenzentren | dl-de/by-2-0 |
| **Wartehallen, Werbeanlagen, DFI-Standorte** | – | **kein Datensatz gefunden** (Wall/DVB-Eigentum) | – |

**Datenqualität L1233:**
- Messwerte (Bordhöhe, Breite) gibt es für **alle Bus-Steige** (949/949), für **134 von 153 kombinierte Steige**,
  aber nur für **76 von 402 reine Tram-Steige**.
- Bei den übrigen Tram-Steigen ist zumindest die Barrierefreiheitsklasse im Text gesetzt.
- 66 DHIDs kommen doppelt vor: zwei Haltepunkte einer **Doppelhaltestelle** im Abstand von 18–60 m (Median 30 m).
- Lage der Punkte: Median 14 m von der OSM-`stop_position` auf dem Gleis entfernt, 6 m von der OSM-Plattform gleicher
  DHID. Der Punkt liegt also **auf dem Bahnsteig**, nicht an der Haltemarke.

---

## Empfehlung: Pipeline für die automatische Platzierung

1. **Laden** (einmalig, mit Quellenvermerk) nach `data/raw/haltestellen/`:
   - L1233 vollständig (≈ 12,8 MB GeoJSON; die `maptip`-HTML-Felder verwerfen, nur die Foto-URLs behalten);
   - `VVO_STOPS.JSON`;
   - gtfs.de-`nv_free` bzw. den VVO-Ausschnitt.
2. **Steig-Objekte bilden**, Schlüssel ist die DHID. Je Steig: Position, Linien, Bordhöhe (Fallback: 0,23 m Tram,
   0,18 m Bus, 0,12 m für Steige mit `best_einstieg` 40), Breite (Fallback 3,0 m Tram, 2,5 m Bus),
   Leit- und Auffindestreifen-Typ, Doppelhaltestelle (DHID doppelt).
3. **An die Infrastruktur anbinden:**
   - Tram (`verkehrsmittel` enthält „Straßenbahn“): auf das nächste Gleis aus `rail.json` projizieren (≤ 25 m).
     Tangente = Fahrtrichtung, Seite = Seite des Punktes.
   - Bus: auf den nächsten Fahrbahnrand projizieren.
   - Kante: Tram bei Gleisachse + 1,40 m (g), Bus am Bordstein.
4. **Länge und Form:**
   - Mit OSM-Bahnsteig gleicher DHID (`ref:IFOPT`) oder Namensgleichheit in < 30 m: dessen Linie bzw. Fläche nehmen.
   - Sonst: Tram 45 m, Doppelhaltestelle 2 × 45 m + 5 m; Bus 20 m. Mittelpunkt am L1233-Punkt.
   - **Typ ableiten:**
     - Straße auf beiden Seiten des Bahnsteigs → Insel (mit Geländer zur Fahrbahn);
     - Gleis straßenbündig und Bahnsteig am Gehweg → Kap;
     - Gleis auf eigenem Bahnkörper (OSM `railway=tram` ohne `embedded`/`highway`-Überlagerung) → Seitenbahnsteig mit
       Rohrgeländer.
5. **Ausstattung:**
   - Wartehalle, Bank, Mülleimer, Leitsystem und DFI nach den OSM-Tags des passenden Bahnsteigs.
   - Liegt ein OSM-Hallengrundriss vor (`amenity=shelter`), Modell W1 auf dessen OBB skalieren
     (Länge auf 1,25–1,5-m-Module runden). Sonst W1 4,0 × 1,5 m an der Bahnsteigrückseite mittig.
   - Ohne Tag: Tram mit 81 %, Bus mit 39 % Wahrscheinlichkeit eine Halle setzen.
6. **Mast:**
   - Eine Fahne je Steig am **vorderen Ende** in Fahrtrichtung (Halteplatz der Fahrzeugspitze), 0,6 m hinter der Kante.
   - Inhalt aus den Daten: Name `hst_name`, „Steig n“ = `steig`, Linienzeilen = `verkehrende_linien`.
     Fahrtziel = häufigstes GTFS-`trip_headsign` je Linie an diesem Steig.
   - Fahnen-Höhe modular nach Zeilenzahl.
   - Schildvariante zufällig gewichtet: 60 % Standard gelb, 35 % neu weiß/gelb, 5 % alt.
7. **DFI:**
   - Haltestellen mit ≥ 4 Linien oder Zentralhaltestellen: große LED-Tafel am Galgenmast.
   - Sonst bei `passenger_information_display=yes` bzw. `departures_board=realtime`: LED im Schild.
   - Bus ohne Tag: DFI-light oder ePaper mit 20 % Wahrscheinlichkeit.
   - Anzeigetext aus dem simulierten Fahrplan.
8. **Material:** Pflaster nach Baualter, aus `aend_dat` bzw. Lage abgeleitet. Granitplatten bei Neubau-Kaps,
   dunkelgraues Betonpflaster im Bestand. Leitstreifen nach `ls_txt` (Rille / Rippe / Noppen / Kleinpflaster).
9. **Unikate** (Postplatz-Dach, Käseglocke, Albertplatz-Pavillon, Hbf Wiener Platz) über `tools/overrides.json` bzw.
   landmarks einhängen, nicht prozedural.

**Pflicht-Quellenvermerk** (z. B. Abspann):
„Haltestellendaten: Landeshauptstadt Dresden, dl-de/by-2-0;
Fahrplandaten: DELFI e.V. / gtfs.de (CC 4.0) und © OpenStreetMap-Mitwirkende (ODbL)“.

---

## Quellen

- DVB „Fakt 3/2012 – Mit der DVB AG barrierefrei durch Dresden“: Bordhöhen 23/18 cm, Restspalt, Rampe 6 %, Combibord,
  überfahrbares Kap. https://www.dvb.de/-/media/files/die-dvb/dvb-fakt-barrierefrei-3-2012.pdf
- Dresdner Amtsblatt 15/2021: 23 cm, 3-m-Gleisachsabstand, 2,65-m-Wagen, 1 168 Bussteige / 558 Tram-Steige, Daten auf
  opendata.dresden.de. https://www.dresden.de/media/pdf/vermessung/Amtsblatt_15_PM_BarrierefreieHaltestellen.pdf
- Sachsen Fernsehen 10.05.2022 (Wall, 850 Hallen, Foster-Design, Vertrag 2023–2037):
  https://www.sachsen-fernsehen.de/amp/neue-dvb-wartehaeuschen-von-einem-star-architekten-1032956/
- Sachsen Fernsehen 26.03.2021 (800 Wall-Wartehallen): https://www.sachsen-fernsehen.de/amp/gruene-wollen-800-wartehaeuschen-abreissen-warum-939083/
- Sachsen Fernsehen 30.03.2026 (über 700 Abfahrtstafeln, LED / DFI-light / ePaper 13″):
  https://www.sachsen-fernsehen.de/amp/dvb-erneuert-abfahrtstafeln-in-dresden-2208960/
- Sachsen Fernsehen 22.07.2026, Umbau Bahnhof Niedersedlitz (Tram-Bahnsteige auf 45 m):
  https://www.sachsen-fernsehen.de/amp/dresden-plant-umbau-am-bahnhof-niedersedlitz-2257242/
- Kassel kerb / Combibord (Wikipedia-Spiegel): https://ipfs.aleph.im/ipfs/QmXoypizjW3WknFiJnKLwHCnL72vedxjQkDDP1mXWo6uco/wiki/Kassel_curb.html
- RMV-Styleguide Haltestellen 2025 (Richtwerte Schrift und Aushang):
  https://www.rmv.de/c/fileadmin/documents/PDFs/_RMV_DE/Der_RMV/Aufgaben_der_RMV_GmbH/250711_StyleguideHaltestellen_v02_BF.pdf
- Community-Doku VVO-APIs (WebAPI, GTFS, Open Data): https://github.com/kiliankoe/vvo
- GovData-Metadaten L1233 (Lizenz dl-by-de/2.0): https://ckan.govdata.de/api/3/action/package_search?q=Haltestellen%20Dresden%20Barrierefreiheit
- FH Erfurt / ISP: Hitzeangepasste Haltestellen (Klimawartehalle):
  https://fh-erfurt.de/fileadmin/Dokumente/ISP/Weitere/Berichte/Online-Befragung_Haltestellen_-_Fragen_und_Antworten.pdf

## Bilder in `dvb_stops_img/` (nur zur Analyse; Weitergabe nur unter der jeweiligen Lizenz mit Namensnennung)

| Datei | Commons-Seite | Lizenz | Urheber | Datum | Inhalt |
|---|---|---|---|---|---|
| `mast_walpurgis_2016_dcb.jpg` | [Haltestelle Walpurgisstraße (DCB)](https://commons.wikimedia.org/wiki/File:2016-03-04_Haltestelle_Walpurgisstra%C3%9Fe_Dresden_by_DCB.jpg) | CC BY-SA 3.0 | DCB | 2016-03-04 | Fahne Standard gelb, Nahaufnahme |
| `mast_walpurgis_2016_dcb_1.jpg` | [… DCB–1](https://commons.wikimedia.org/wiki/File:2016-03-04_Haltestelle_Walpurgisstra%C3%9Fe_Dresden_by_DCB%E2%80%931.jpg) | CC BY-SA 3.0 | DCB | 2016-03-04 | Fahne |
| `mast_stvo_tolkewitz_2023.jpg` | [Stop signs … Wasserwerk Tolkewitz](https://commons.wikimedia.org/wiki/File:Stop_signs_of_the_transport_company_Dresden_2023_-_Legally_compliant_according_to_the_StVO_-_Wasserwerk_Tolkewitz.jpg) | CC BY-SA 4.0 | Lupus in Saxonia | 2023-07-14 | neue Fahne weiß/gelb |
| `mast_stvo_tolkewitz_2023_2.jpg` | [… Image 2](https://commons.wikimedia.org/wiki/File:Stop_signs_of_the_transport_company_Dresden_2023_-_Legally_compliant_according_to_the_StVO_-_Wasserwerk_Tolkewitz_-_Image_2.jpg) | CC BY-SA 4.0 | Lupus in Saxonia | 2023-07-14 | neue Fahne komplett |
| `dfi_light_mengsstr_2019.jpg` | [DFI light Mengsstraße](https://commons.wikimedia.org/wiki/File:DFI_light_Dresden_Mengsstra%C3%9Fe,_2019.jpg) | CC BY-SA 4.0 | Hgzh | 2019-03-01 | ganzer Mast + DFI-light + Plakatkasten |
| `dfi_strassburger_2008.jpg` | [DFI Straßburger Platz](https://commons.wikimedia.org/wiki/File:DFI_an_der_DVB_Haltestelle_Stra%C3%9Fburger_Platz_(Dresden)_2008-08-31.jpg) | CC BY-SA 3.0 | Henry Mühlpfordt | 2008-08-31 | Galgen-DFI alt, Stele, Seitenbahnsteig, Bogendachhalle |
| `tram_schillerplatz_2022_cc0.jpg` | [Schillerplatz tram stop](https://commons.wikimedia.org/wiki/File:Blasewitz,_Schillerplatz_tram_stop_in_Dresden.jpg) | CC0 | Robert von Oliva | 2022-08-13 | LED-DFI mit Uhr, Stelen |
| `bus_seidnitzcenter_2018_1.jpg` | [Bushaltestelle Seidnitzcenter](https://commons.wikimedia.org/wiki/File:DVB_Dresden_-_Bushaltestelle_-_Seidnitzcenter_-_Bild_001.jpg) | CC BY-SA 4.0 | Lupus in Saxonia | 2018-06-07 | alte Fahne, Halle W1 + DVB-Kasten, alter Mülleimer |
| `bus_nuernberger_platz_2024_012.jpg` | [Bus Stop Nürnberger Platz](https://commons.wikimedia.org/wiki/File:20240127.Bus_Stop_N%C3%BCrnberger_Platz.-012.jpg) | CC BY 4.0 | Bybbisch94 | 2024-01-27 | neue Fahne mit roten Modulen |
| `bus_walpurgis_2024_011.jpg` | [Bus Stop Walpurgisstraße](https://commons.wikimedia.org/wiki/File:20240129.Bus_Stop.Walpurgisstra%C3%9Fe.-011.jpg) | CC BY 4.0 | Bybbisch94 | 2024-01-29 | Bus-Steig, Zickzack, Fahrplankästen |
| `bus_fritzfoerster_2024_01.jpg` | [Bus Stop Fritz-Förster-Platz](https://commons.wikimedia.org/wiki/File:20240126.Bus_Stop_Fritz-F%C3%B6rster-Platz.-01.jpg) | CC BY 4.0 | Bybbisch94 | 2024-01-26 | Nacht, Mülleimer grau/orange, Leitstreifen |
| `tram_postplatz_2025_0701_012.jpg` | [Postplatz](https://commons.wikimedia.org/wiki/File:20250701.Dresden.Postplatz.-012.jpg) | CC BY-SA 4.0 | Bybbisch94 | 2025-07-01 | Postplatz-Dach (Baustelle) |
| `tram_postplatz_2025_0621_011.jpg` | [Postplatz](https://commons.wikimedia.org/wiki/File:20250621.Dresden.Postplatz.-011.jpg) | CC BY-SA 4.0 | Bybbisch94 | 2025-06-21 | Postplatz |
| `tram_albertplatz_2024_011.jpg` | [Albertplatz](https://commons.wikimedia.org/wiki/File:20240103.Albertplatz.-011.jpg) | CC BY 4.0 | Bybbisch94 | 2024-01-03 | Albertplatz |
| `tram_prohlis_gleisschleife_2023_01.jpg` | [Prohlis, Gleisschleife](https://commons.wikimedia.org/wiki/File:2023-06-03_Tram_Haltestelle_Prohlis,_Gleisschleife_01.jpg) | CC BY-SA 4.0 | Maschienenbau | 2023-06-03 | Seitenbahnsteige, Geländer, Pflaster, Bänke |
| `tram_hbf_2024_01.jpg` | [Haltestelle Hauptbahnhof](https://commons.wikimedia.org/wiki/File:20240126.Stra%C3%9Fenbahn_Haltestelle_Hauptbahnhof.-01.jpg) | CC BY 4.0 | Bybbisch94 | 2024-01-26 | Wiener Platz, Granitpflaster, DFI |
| `tram_walpurgis_2024_01.jpg` | [Tram stop Walpurgisstraße](https://commons.wikimedia.org/wiki/File:20240207.Tram_stop_Walpurgisstra%C3%9Fe,_Dresden.-01.jpg) | CC BY 4.0 | Bybbisch94 | 2024-02-07 | Halle W1 lang, Bänke, Edelstahl-Mülleimer |
| `tram_walpurgis_2024_03.jpg` | [… -03](https://commons.wikimedia.org/wiki/File:20240207.Tram_stop_Walpurgisstra%C3%9Fe,_Dresden.-03.jpg) | CC BY 4.0 | Bybbisch94 | 2024-02-07 | Seitenbahnsteig, City-Light-Stele |
| `tram_strassburger_2023_0711_011.jpg` | [Straßburger Platz](https://commons.wikimedia.org/wiki/File:20230711.Stra%C3%9Fburger_Platz,_Dresden.-011.jpg) | CC BY-SA 4.0 | Bybbisch94 | 2023-07-11 | Baustelle, wenig relevant |
| `tram_wasaplatz_2024_01.jpg` | [Wasaplatz 01](https://commons.wikimedia.org/wiki/File:2024-05-25_Tram_Haltestelle_Wasaplatz_01.jpg) | CC BY-SA 4.0 | Maschienenbau | 2024-05-25 | Kap mit Radweg, Leitplatten |
| `tram_wasaplatz_2024_05.jpg` | [Wasaplatz 05](https://commons.wikimedia.org/wiki/File:2024-05-25_Tram_Haltestelle_Wasaplatz_05.jpg) | CC BY-SA 4.0 | Maschienenbau | 2024-05-25 | lange Halle mit Namensblende |
| `tram_cotta_gkeller_2020.jpg` | [Cotta, Gottfried-Keller-Straße](https://commons.wikimedia.org/wiki/File:2020-10-06_Tram_Haltestelle_Cotta,_Gottfried-Keller-Stra%C3%9Fe_f%C3%BCr_Fahrt_in_Richtung_Leutewitz.jpg) | CC BY-SA 4.0 | Maschienenbau | 2020-10-06 | Fahrbahnrand-Halt, LED im Schild |
| `bus_zschertnitzer_2024_01.jpg` | [Bus Stop Zschertnitzer Straße](https://commons.wikimedia.org/wiki/File:20240205.Bus_Stop_Zschertnitzer_Stra%C3%9Fe.-01.jpg) | CC BY 4.0 | Bybbisch94 | 2024-02-05 | Bus-Steig Wohngebiet |
| `tram_bus_trachauer_2023.jpg` | [Trachauer Straße](https://commons.wikimedia.org/wiki/File:2023012509_Strassenbahn-_und_Bushaltestelle_Trachauer_Strasse_2023.jpg) | CC BY-SA 4.0 | VSchagow | 2023-01-25 | Kaps beidseitig, Halle |
| `shelter_albertplatz.jpg` | [Wartehäuschen Albertplatz](https://commons.wikimedia.org/wiki/File:Warteh%C3%A4uschen_am_Dresdner_Albertplatz.jpg) | CC BY 3.0 | Xaver X. Dreißig | 2012-05-21 | DVB-Pavillon (Unikat) |
| `shelter_tolkewitz_schulcampus_werbung_1.jpg` | [Schulcampus Tolkewitz – Werbefläche](https://commons.wikimedia.org/wiki/File:Haltestelle_DVB_-_Schulcampus_Tolkewitz_-_Werbeff%C3%A4che_am_Warteh%C3%A4uschen_-_Bild_001.jpg) | CC BY-SA 4.0 | Lupus in Saxonia | – | JCDecaux-Vitrine |
| `tram_tolkewitz_schulcampus_2024_02.jpg` | [Tolkewitz, Schulcampus 02](https://commons.wikimedia.org/wiki/File:2024-08-03_Tram_Haltestelle_Tolkewitz,_Schulcampus_02.jpg) | CC BY-SA 4.0 | Maschienenbau | 2024-08-03 | Combibord, neue Halle W3, Automat |
| `tram_diakonissen_2025_011.jpg` | [Diakonissenkrankenhaus](https://commons.wikimedia.org/wiki/File:20250710.Haltestelle_Diakonissenkrankenhaus,_Dresden.-011.jpg) | CC BY-SA 4.0 | Bybbisch94 | 2025-07-10 | Neubau-Kap 2025, silberne Masten |
| `tram_vahlteich_2024_03.jpg` | [Julius-Vahlteich-Straße 03](https://commons.wikimedia.org/wiki/File:2024-10-20_Tram_Haltestelle_Julius-Vahlteich-Stra%C3%9Fe_03.jpg) | CC BY-SA 4.0 | Maschienenbau | 2024-10-20 | Klimawartehalle, Leitstreifen, Schutzgitter |
| `tram_leubener_2024_07.jpg` | [Leubener Straße 07](https://commons.wikimedia.org/wiki/File:2024-05-26_Tram_Haltestelle_Leubener_Stra%C3%9Fe_07.jpg) | CC BY-SA 4.0 | Maschienenbau | 2024-05-26 | Halle W1 frontal, Zeitinsel-Rampe |
| `shelter_kaeseglocke_postplatz.jpg` | [Käseglocke Postplatz](https://commons.wikimedia.org/wiki/File:Warteh%C3%A4uschen_K%C3%A4seglocke_Postplatz_Dresden.JPG) | CC BY-SA 3.0 | Paulae | 2011-11-07 | Unikat |
| `bus_sbf_plauen_2025_01.jpg` | [Haltestelle S-Bf Plauen](https://commons.wikimedia.org/wiki/File:20250501.Haltestelle_S-Bf_Plauen_(Dresden).-01.jpg) | CC BY-SA 4.0 | Bybbisch94 | 2025-05-01 | **bestes Proportionsfoto Mast** (frontal, 2 Fahrplankästen) |
