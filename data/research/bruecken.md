# Brücken in Dresden – Inventar, Recherche und Typen für das Spiel

Stand: 12.11.2026 · OSM-Auszug 08.11.2026 · maschinenlesbar: `data/research/bruecken.json` · Analysebilder: `data/research/bruecken_img/` (Lizenzliste unten und in `LIZENZEN.jsonl`).

## 1. Kurzfassung

- **1224 Brückenbauwerke** im Spielgebiet (117 Kacheln, ganz Dresden + Randorte) aus 1855 OSM-Brückenwegen, 336 `man_made=bridge`-Flächen und 24 Brücken-/Multipolygon-Relationen zusammengeführt.
- **393 Hauptbauwerke** (Straße/Tram/Bahn ≥ 15 m oder benannt) mit Einzeldatensatz, davon **32 Unikate** (recherchierte Landmarken, einzeln modellieren) und 2 Einträge „entfernen“ (Carolabrücke).
- **792 Kleinbrücken** (Fuß-/Radstege, Wirtschaftswege, Bachdurchlässe < 15 m) nur gezählt und typisiert, **39 sonstige Bauwerke** (Gebäudebrücken/Übergänge, Rohrbrücken, Grünbrücke, Flächenreste ohne Weg).
- **Carolabrücke:** Am 11.09.2024 teileingestürzt, bis September 2025 vollständig abgerissen. Ende 2026 steht **keine Brücke**. Neubau (Entwurf LAP + Knight Architects) frühestens ab Mai 2028. Im Spiel: OSM-Wege 4214231/10368500 (demolished:highway) und die abgebauten Tram-Wege 1422377883/1422377884 nicht bauen, LoD2-Brückenteile ausblenden, Straßengraph an den Rampen kappen, Bauzaun an den Enden.
- **Augustusbrücke** ist seit 2022 nur für Straßenbahn, Fuß- und Radverkehr offen, für Kfz gesperrt (Verkehrs-KI!).
- **Baustellen 2026:** Blaues Wunder (Grundsanierung seit Herbst 2026, Gerüst Blasewitzer Seite), Nossener Brücke (Verkehr nur auf Südzug, Nordteil im Abbruch, Neubau bis 2031), Brücke Budapester Straße (Notstützen, 1 Spur je Richtung, 7,5 t), Kreuzungsbauwerk Hauptbahnhof (im Bau bis 11/2027), Königsbrücker Straße (Abbruch/Neubau ab 2027).
- **Pfeilerlagen aus Geodaten:** Die OSM-Flächen von Augustus-, Albert- und Marienbrücke bilden die Pfeilerkanzeln als Ausbuchtungen ab. Daraus wurden Pfeilerstationen entlang der Achse bestimmt (`pier_stations_m`). Bei der Marienbrücke stimmen sie auf ±1,5 m mit den Wikipedia-Maßen überein (12 × 28,32 m + 2 × 14,16 m, Pfeiler 4,53/6,80 m).
- **10 Brückentypen** mit Standardmaßen und Farben für die Masse; jede Brücke trägt `type`/`variant`, nicht recherchierte Werte sind als Typregel-Schätzung markiert (`confidence`).

## 2. Methode Inventar

1. Alle `bridges.json` der Kacheln eingelesen, Duplikate über OSM-ID zusammengeführt (Geometrie ist je Weg vollständig, nicht geclippt). Zusätzlich aus `sachsen.osm.pbf` die Relationen `type=bridge` (Rollen outline/across) und `man_made=bridge`-Multipolygone (Nossener, Niederwarthaer Brücke u. a.) ergänzt.
2. Wege → Bauwerk: (a) über Relation (across), (b) Weg liegt zu > 50 % bzw. > 15 m in einer `man_made=bridge`-Fläche (+1,5 m Puffer), (c) freie Wege verkettet (gemeinsamer Endknoten) oder parallel (≤ 12 m, Überdeckung > 70 %); freie Gruppen werden an Flächen-Gruppen angehängt, wenn sie parallel daneben liegen oder als kurzer Rest (< 20 m) an genau einem Ende hängen.
3. Länge = längste zusammenhängende Wegkette innerhalb der Fläche; Breite = Fläche/Länge (sonst LoD2-Fußabdruck/Länge, sonst aus Tags geschätzt).
4. Querungen: Schnitt der Deckfläche mit Gewässerlinien/-flächen (`water.json`), Gleisen (`rail.json`) und Straßen/Wegen (`roads.json`) mit niedrigerem `layer` bzw. ohne `bridge`; Anschlüsse an den Brückenenden (< 3 m) und längs auf dem Deck liegende Wege ausgeschlossen. „Tal“ = Fahrbahn (aus `bridge_heights.json`) ≥ 12 m über dem tiefsten DGM1-Punkt.
5. LoD2-Brückenteile (`data/raw/lod2_bridges`, Funktion 53001_1800/51009_1700) über Flächenüberdeckung zugeordnet (`lod2.ids`, `top_z`).
6. Typ per Regelwerk (Abschnitt 6), recherchierte Werte überschreiben Typwerte.

Zahlen: stadt_beton_balken 131, bahn_eue_modern 66, bahn_eue_historisch 51, autobahn_ueberfuehrung 49, sandstein_bogen 25, fuss_holz_klein 23, stadt_hochstrasse 17, autobahn_talbruecke 12, stahl_fachwerk 9, fuss_rad_stahl 8, abgerissen 2.

## 3. Elbbrücken (Steckbriefe)

Stationen `s` jeweils ab dem genannten Ende der OSM-Fläche (EPSG:25833); Farben = Albedo-Schätzung aus Fotos.

| Brücke | Bauart | Länge / Breite (m) | Felder (m) | Pfeiler | Geländer | Hauptfarben | Stand 11/2026 |
|---|---|---|---|---|---|---|---|
| **Loschwitzer Brücke („Blaues Wunder“)** (B0797) | Versteifte Hängebrücke als Stahlfachwerk (Hängefachwerk mit 3 Gelenken, Kragarm-/Auslegerprinzip), ohne Strompfeiler; Obergurt fällt von den Turmspitzen über de | 280,0 / 17,0 | 61,76 / 146,68 / 61,76 | 2 | außen: Stahlgeländer mit senkrechten Stäben und Handlauf (hellblau); innen zwischen Gehweg und Fahrbahn: niedr; 1,10 m `#6fa9d4` | steel `#6fa9d4`, steel_shadow `#3a5777`, footway_wood `#7e7061` | in Betrieb (max. 15 t); seit Ende Sept. 2026 Sanierung: Geländerteile/Kabelrinnen abgebaut, Gerüstbau auf Blasewitzer Seite, Vollsperrung Kf |
| **Waldschlößchenbrücke** (B0641) | Stahlverbund-Bogenbrücke: zwei Stahlbögen 148 m über der Elbe (Bogenfüße unter der Fahrbahn im Gelände, Bogenscheitel ~26 m über der Elbe, Fahrbahn mittig an Hä | 636,1 / 28,6 | 213,49 / 148,0 / 274,81 | – | Stahl-Füllstabgeländer mit Handlauf, schlank (hellgrau); 1,30 m `#b9bcc0` | steel_arch `#c9ccd0`, steel_girder `#9a9fa5`, v_struts `#b8b9b6` | in Betrieb |
| **Albertbrücke** (B0516) | Steinbogenbrücke (Sandstein), 14 Segmentbögen symmetrisch zum 7,5 m breiten Mittelpfeiler: 4 Stromöffnungen à 31 m, je 5 Flutbögen; 1945 je 3 Bögen gesprengt, 1 | 316,0 / 22,2 | 14 Felder (u. a. 31,0, 12,8, 13,2) | 13 | historisches Gusseisengeländer (Stabfelder mit verzierten Pfosten, Kugel-/Zapfenaufsätze) auf niedrigem Sandst; 1,20 m `#2a2e36` | masonry_sunlit `#d8c49a`, masonry `#bfa983`, masonry_shadow `#7d6a52` | in Betrieb (Straße, Straßenbahn Linien 6/13, viel Radverkehr) |
| **Carolabrücke (abgerissen)** (B0370) | ehemals Spannbeton-Hohlkastenbrücke (1967–1971) aus drei getrennten Brückenzügen A/B/C (Zug C mit Straßenbahn), gevoutet, Konstruktionshöhe 1,60–5,30 m, Gesamts | 0,0 / 10,0 | – | 0 | –; – m `` | construction_fence `#d23c2c` | KEIN Bauwerk vorhanden (Stand Nov. 2026). Elbe seit Mitte Aug. 2025 wieder schiffbar, Terrassenufer seit 17.09.2025 frei, Elberadweg Neustäd |
| **Augustusbrücke** (B0371) | Massive Gewölbebrücke aus 9 Dreigelenk-Segmentbögen (Stampfbeton, Stirnflächen mit Sandstein verblendet), 4 Bögen über Strompfeilern, 4 Bögen über den Neustädte | 390,0 / 18,0 | 17,6 / 23,0 / 35,8 / 39,3 / 39,3 / 35,8 / 31,8 / 27,3 / 20,5 | 8 | massive Sandsteinbrüstung (geschlossen, mit Abdeckplatte) auf Konsolgesims; 1,10 m `#7a6a5c` | masonry `#7a6a5c`, masonry_patina_dark `#5c5554`, masonry_new_stone `#b8a787` | in Betrieb nur für Straßenbahn (Linien 3, 4, 7, 9), Fuß- und Radverkehr – kein Kfz-Verkehr |
| **Marienbrücke (Straßenbrücke)** (B0365) | Steinbogenbrücke (1852) mit 14 Öffnungen: 12 Korbbögen à 28,32 m + je ein Halbkreisbogen 14,16 m an den Enden; 1997–2002 unterstromseitig mit einstegigem Stahlb | 434,0 / 20,5 | 14 Felder (u. a. 28,3, 14,2) | 13 | Stahl-/Gussgeländer mit senkrechten Stäben und Zierpfosten auf Sandstein-Gesims mit Konsolen (oberstrom); unte; 1,20 m `#2b2b2e` | masonry_sunlit `#cfb59a`, masonry `#b69f85`, masonry_shadow `#7b7067` | in Betrieb (B 6, Straßenbahn Linien 6/11); Auffahrt Richtung Altstadt einstreifig; provisorische Fernwärmeleitung unter einem Bogen (seit Ca |
| **Marienbrücke (Eisenbahnbrücke, „Marienbrücke II“)** (B0373) | Strombrücke: gevoutete Spannbeton-Hohlkastenbrücke im Freivorbau (2001–2004), zwei getrennte Überbauten (oberstrom 1-zelliger Kasten für 2 S-Bahn-Gleise, unters | 490,0 / 24,8 | 36,96 / 67,7 / 65,8 / 64,86 / 24,0 | 10 | gestaltetes Stahlgeländer mit senkrechten Füllstäben auf den Kragarmen; in den Randfeldern massive Sandsteinbr; 1,10 m `#55585a` | concrete `#a69e87`, deck_edge `#a69e87`, masonry `#9d8768` | in Betrieb, 5 Gleise (Kulturdenkmal 09216624 „Marienbrücke II – Eisenbahnbrücke“) |
| **Flügelwegbrücke** (B0179) | Stahlverbund-Durchlaufträger, zwei getrennte Überbauten (je 3 Fahrstreifen + Geh- und Radweg), je ein Stahltrog (unten 5,25 m breit) mit quer gevouteter Stahlbe | 285,0 / 31,0 | 40,0 / 65,0 / 115,0 / 65,0 | 3 | Stahl-Füllstabgeländer mit Handlauf auf Betonkappe; 1,30 m `#8c9094` | steel `#3a4350`, concrete `#c9c3b4`, piers `#c9c3b4` | in Betrieb (S 73) |
| **Elbebrücke Dresden (A 4) – Autobahnbrücke Dresden-Kaditz** (B0191) | Stahlverbund-Durchlaufträger über 7 Felder, je Richtung ein Überbau mit zwei Stahlhohlkästen, über den Strompfeilern gevoutet (Ersatzneubau 1995–1998 der Fachwe | 496,0 / 43,0 | 55,0 / 73,0 / 130,0 / 73,0 / 68,0 / 56,6 / 40,4 | 6 | transparente Glas-/Lärmschutzwand mit Stahlpfosten am Überbaurand (Foto), dazu Geh-/Radweg mit Geländer; 2,00 m `#9aa8a8` | steel `#889a96`, masonry `#a88780`, concrete `#b2b7bd` | in Betrieb; 8-streifiger Ausbau AD Dresden-West–AD Dresden-Nord in Planung (DEGES, Planungsauftrag 2019) – kein Baubeginn belegt |
| **Eisenbahnbrücke Niederwartha (Strecke Berlin–Dresden, 6248)** (B0053) | Balkenbrücke: Strombrücke 3 x 64 m als zwei 192 m lange Durchlaufträger aus dreizelligen Stahlhohlkästen, Vorlandbrücken aus Spannbetonfertigteilen; auf den alt | 353,5 / 17,4 | 10 Felder (u. a. 23,0, 64,0, 22,8) | 9 | Füllstabgeländer (senkrechte Stäbe) mit Handlauf am Fuß-/Radweg, zum Gleis ebenfalls Stabgeländer; 1,20 m `#5f6a62` | masonry `#9a8c78`, steel `#3c3f3e`, concrete `#b8b8b4` | in Betrieb (DB InfraGO); Fuß-/Radweg auf der Brücke |
| **Niederwarthaer Brücke (Straßenbrücke Niederwartha, S 84)** (B0058) | einhüftige Schrägseilbrücke mit A-förmigem (umgekehrt Y) Betonpylon am rechten (Radebeuler) Ufer, 9 Seilpaare; Hauptfeld Stahlverbund, Seitenfeld und Vorlandbrü | 366,0 / 12,5 | 22,0 / 23,0 / 23,0 / 23,5 / 192,0 / 82,5 | 5 | transparente Wand (Glas-/Kunststoffpaneele mit Stahlpfosten) auf beiden Kappen (Fotos); 2,00 m `#8c9fa2` | concrete `#cfc8c4`, steel `#2a2a28`, deck_edge `#d8d8d4` | in Betrieb |

### Details und Besonderheiten

- **Loschwitzer Brücke („Blaues Wunder“)**: Stahlfachwerk-Hängebrücke (1893) ohne Strompfeiler, Stützweiten 61,76/146,68/61,76 m, Türme ca. 24 m über der Fahrbahn auf den Uferpfeilern (s ≈ 62,5 und 209 m ab Blasewitz). Der Obergurt hängt zur Feldmitte bis knapp über die Fahrbahn durch. Fahrbahn 10,2 m. Außen liegen 1935 angebaute Gehwege mit Holzbohlenbelag und hellblauem Stabgeländer. Blaue Doppellaternen-Kandelaber, nachts LED-Anstrahlung. Blasewitzer Rampe mit Sandsteinpfosten. Neuanstrich im Originalton 1893 läuft bis ca. 2031.
- **Waldschlößchenbrücke**: Stahlverbund-Bogenbrücke, 636,1 m: rechtselbische Vorlandbrücke 213,49 m (Nord, s = 0–213,5), Bogen 148 m (s ≈ 213,5–361,5, Scheitel ~26 m über der Elbe), linkselbische Vorlandbrücke 274,81 m. Die Bogenfüße stehen unter der Fahrbahn im Gelände. Die Vorlandbrücken ruhen auf V-förmigen Doppelstreben. Querschnitt 28,6 m (Bogen) bzw. 24,4 m: 4 × 3,25 m Fahrstreifen, außen je 2,35 m Geh-/Radweg. Im Norden direkter Tunnelanschluss.
- **Albertbrücke**: 14 Sandstein-Segmentbögen: 4 Stromöffnungen à 31 m lichte Weite, beidseitig 5 Flutbögen (12,8–17,6 m, aus Kanzellagen geschätzt). Mittelpfeiler 7,5 m mit Carrara-Marmorreliefs. Kanzeln an den Uferpfeilern (s 86,8/232,8) und am Mittelpfeiler (s 159,5 ab Neustadt). Breite seit 2016 22,2 m mit Gehwegen 2,0 m (Granit), Radwegen 1,6 m (beige) und historischem Gussgeländer (anthrazit). Durchfahrtshöhe ~7,9 m bei HSW.
- **Carolabrücke (abgerissen)**: Abgerissen (Abbruch Zug C 2024, Züge A/B Juni–Sept. 2025). Elbe, Terrassenufer und Elberadweg sind frei. Auf den Neustädter Elbwiesen lag Okt. 2025–März 2026 ein Baufeld zur Kampfmittelsondierung. Ob Widerlagerreste stehen, ist nicht belegt; nach Angaben der Stadt ist die Brücke „vollständig verschwunden“. Empfehlung: Rampen mit Bauzaun/Baken enden lassen.
- **Augustusbrücke**: 9 Dreigelenk-Segmentbögen (Stampfbeton, Sandsteinverblendung), lichte Weiten 17,6–39,3 m. Reihenfolge abgeleitet: 17,6 (über Terrassenufer) / 23 / 35,8 (Schifffahrt, 3. Bogen) / 39,3 / 39,3 / 35,8 / 31,8 / 27,3 / 20,5 m. Pfeilerkanzeln (Breite dort 25–32 m) bei s = 51…303,5 m ab Altstadt; der Pegel Dresden hängt am Pfeiler s ≈ 51. Massive Sandsteinbrüstung mit Konsolgesims, dunkel patiniert und fleckig. Altstädter Brückenkopf (s 0–23, 30 m breit) über dem Terrassenufer.
- **Marienbrücke (Straßenbrücke)**: 14 Öffnungen: Halbkreis 14,16 / 12 × Korbbogen 28,32 / Halbkreis 14,16 m. 13 Pfeiler, 4,53 m dick, die ersten Innenpfeiler und der Mittelpfeiler 6,80 m. Oberstrom runde Pfeilervorlagen bis zur Brüstung (Postkartenansicht, denkmalgeschützt). Unterstrom 1997–2002 mit einem Stahlbeton-Plattenbalken auf 20,5 m verbreitert, sichtbar als glatter grauer Betonbalken. Fahrbahn 11 m mit 2 Tramgleisen. Neustädter Rampe 198 m über den Palaisgarten.
- **Marienbrücke (Eisenbahnbrücke, „Marienbrücke II“)**: Spannbeton-Hohlkasten (2001–2004), zwei Überbauten für 5 Gleise, gevoutet 2,50 m (Feld) bis 5,81 m (Pfeiler). Stromfelder 36,96/67,70/65,80/64,86 m. Die Sandsteinpfeiler tragen Kanzeln für die Oberleitungsmasten. Vorlandbrücke 203 m mit 6 Sandsteinbögen. Liegt 40 m stromab der Straßenbrücke.
- **Flügelwegbrücke**: Zwei getrennte Stahlverbund-Überbauten (je 15,5 m breit, 3 Fahrstreifen + Geh- und Radweg), dunkler Stahltrog 4,0–5,5 m hoch. Stützweiten Nord→Süd 40/65/115/65 m (Reihenfolge aus Wasserfläche abgeleitet). Durchfahrtshöhe 6,53 m.
- **Elbebrücke Dresden (A 4) – Autobahnbrücke Dresden-Kaditz**: Stahlverbund (1995–98), je Richtung ein Überbau mit 2 Stahlkästen (blassgrün) unter heller Betonplatte. 7 Felder 55/73/130/73/68/56,6/40,4 m, über den Strompfeilern bis 6 m gevoutet. Pfeilerscheiben mit rötlich-brauner Natursteinverkleidung und halbrunden Köpfen. Glaswand ~2 m, außen Geh- und Radweg. Achtstreifiger Ausbau in Planung.
- **Eisenbahnbrücke Niederwartha (Strecke Berlin–Dresden, 6248)**: Stählerne Balkenbrücke (1977–83) auf den alten Sandsteinpfeilern, 10 Felder (22,75 … 3 × 64 … 22,75 m), mit Fuß- und Radweg. Steht parallel 10 m oberstrom der Straßenbrücke.
- **Niederwarthaer Brücke (Straßenbrücke Niederwartha, S 84)**: Erste Schrägseilbrücke Sachsens (2006–08, freigegeben 2011). Heller A-/Y-Pylon 77 m am Radebeuler Ufer, Seilfächer zum 192-m-Hauptfeld. Felder 22/23/23/23,5/192/82,5 m, Überbau 2 m, 12,5 m breit, keine Gehwege.

## 4. Weitere recherchierte Bauwerke

| ID | Brücke | Typ | Länge / Breite (m) | Felder (m) | Pfeiler | Bauart (Kurz) | Stand / Hinweis | Vertrauen |
|---|---|---|---|---|---|---|---|---|
| B0567 | Lockwitztalbrücke | autobahn_talbruecke/stahlverbund | 723,0 / 29,5 | 48,0 / 60,0 / 65,0 / 70,0 / 85,0 / 125,0 / 125,0 / 85,0 / 60,0 | 8 | Stahlverbund-Hohlkastenbalken (Doppelbrücke) mit unter der Fahrbahn liegenden, im Überbau verankerten Stahlbet | in Betrieb (keine Hinweise auf Neubau/Abriss gefunden) | hoch |
| B0227 | Löbtauer Brücke (Löbtauer Hochstraße) | stadt_hochstrasse/nachwende | 998,0 / 17,2 | 26 Felder (u. a. 27,7, 22,2) | 25 | Spannbeton-Hochstraße, Durchlaufträger; zwei baulich getrennte Richtungsfahrbahnen; Querschnitt laut Foto Plat | in Betrieb (keine gegenteilige Meldung gefunden) | mittel |
| B0682 | Überwerfungsbauwerk Dresden-Klotzsche (Flughafen-S-Bahn, Str | bahn_eue_modern | 525,5 / 7,6 | 24 Felder (u. a. 22,3, 17,8) | 23 | eingleisige, gekrümmte Stahlbeton-Viaduktbrücke (Durchlaufträger mit Kragplatte) auf zahlreichen Rundstützen u | in Betrieb | mittel |
| B0229 | Nossener Brücke (Bestand „Brücke der Jugend“ 1964, Ersatzneu | stadt_hochstrasse/ddr_ueber_bahn | 284,0 / 26,4 | 28 Felder (u. a. 12,3, 9,8) | 27 | Zug aus 4 Stahlbeton-Teilbrücken: Rahmenbrücke über die Fabrikstraße (gevoutete Rahmenecken, Foto), Balken-/Pl | Stand Nov. 2026: Altbau in Betrieb, aber seit 14.06.2026 läuft der gesamte Verkehr (Kfz, Bus 61, Fuß, Rad) nur über den  | mittel |
| B0258 | Schlachthofbrücke (+ Straßenbahnbrücke 2011) | stadt_hochstrasse/nachwende | 315,5 / 12,5 | 13 Felder (u. a. 24,4, 22,1, 26,1) | 12 | Stahlverbund-Durchlaufträger (Überbau 1999) auf 12 massiven Pfeilerpaaren von 1932; daneben separate zweigleis | in Betrieb | hoch |
| B0445 | Gebergrundbrücke | autobahn_talbruecke/spannbeton | 288,0 / 29,5 | 38,2 / 47,7 / 47,7 / 47,7 / 47,7 / 47,7 / 38,2 | 6 | Spannbeton-Hohlkastenbalken, zwei getrennte Überbauten, im Taktschiebeverfahren hergestellt | in Betrieb | mittel |
| B0257 | Waltherstraßenbrücke (über Bahnhof Dresden-Friedrichstadt) | stadt_hochstrasse/nachwende | 300,0 / 22,0 | 11 Felder (u. a. 28,5, 22,8) | 10 | Durchlaufträger mit Hohlkastenquerschnitt, 11 Felder (structurae: box girder); Bemessung nach DIN-Fachbericht  | in Betrieb | mittel |
| B0274 | Unionbrücke (A 4, Radebeul) | autobahn_talbruecke/stahlverbund | 253,7 / 38,2 | 27,4 / 34,3 / 34,3 / 34,3 / 34,3 / 34,3 / 34,3 / 27,4 | 7 | Stahlverbund-Durchlaufträger über 8 Felder, zwei getrennte Überbauten, je zweistegiger Plattenbalken aus 2 luf | in Betrieb | hoch |
| B0794 | Schwebebahn Dresden (Bergschwebebahn Loschwitz–Oberloschwitz | stahl_fachwerk/bergbahn | 273,8 / 3,0 | 34 Felder (u. a. 7,6, 6,1) | 33 | seilgezogene Einschienen-Hängebahn System Eugen Langen auf stählernem Traggerüst: 33 Stützen (32 Pendeljoche + | in Betrieb (Kulturdenkmal 09211294; halbjährliche Revisionen, Herbstrevision 2025 mit Schwerpunkt Stützen/Fahrschienentr | hoch |
| B0145 | Weißeritztalbrücke (Talbrücke Weißeritz) | autobahn_talbruecke/stahlverbund | 218,0 / 31,2 | 42,9 / 53,6 / 53,6 / 53,6 / 42,9 | 4 | Balkenbrücke mit türkis beschichtetem Stahlhohlkasten und Stahlbeton-Fahrbahnplatte (Stahlverbund), zwei Teilb | in Betrieb | mittel |
| B0346 | Brücke Budapester Straße | stadt_hochstrasse/ddr_ueber_bahn | 850,0 / 36,4 | 14 Felder (u. a. 12,3, 9,9) | 13 | Spannbeton-Balkenbrücke aus zwei getrennten Richtungsbrücken (Brückenzüge) über Gleisfeld Hbf (West), Straßenb | 08.05.2026 Spanndrahtbrüche → 1 Spur/Richtung, 7,5 t; 14.05.2026 Teilsperrung Abschnitt Ammonstraße–Josephinenstraße; Ju | mittel |
| B0340 | Brücke Budapester Straße | stadt_hochstrasse/ddr_ueber_bahn | 850,0 / 38,0 | 13 Felder (u. a. 12,6, 10,1) | 12 | Spannbeton-Balkenbrücke aus zwei getrennten Richtungsbrücken (Brückenzüge) über Gleisfeld Hbf (West), Straßenb | 08.05.2026 Spanndrahtbrüche → 1 Spur/Richtung, 7,5 t; 14.05.2026 Teilsperrung Abschnitt Ammonstraße–Josephinenstraße; Ju | mittel |
| B0272 | Pieschener Molenbrücke (Elberad- und Wanderwegbrücke Hafen P | fuss_rad_stahl | 150,0 / 3,4 | 62,35 | 1 | Schrägseilbrücke: luftdicht geschweißter Stahl-Hohlkasten, Fächerabspannung in zwei seitlichen Ebenen an zweia | in Betrieb | hoch |
| B0533 | Prießnitztalviadukt (ehem. Carolabrücke), Stauffenbergallee | sandstein_bogen/viadukt | 86,5 / 20,0 | 14,5 / 14,5 / 14,5 | 2 | Steinbogenbrücke aus Sandstein, 3 Bögen (mittlerer über Prießnitz, westlicher über Prießnitzgrundweg), Talhöhe | in Betrieb, Kulturdenkmal (LfD 09210024) | mittel |
| B0253 | Hafenbrücke (Straße, Flügelweg–Hafenweg; Fuß-/Radverkehr) | stahl_fachwerk | 77,0 / 6,8 | 77,0 | 0 | eiserne Fachwerkbrücke mit untenliegender Fahrbahn (Rautenfachwerk, Obergurt an den Enden abgerundet, Portale  | in Betrieb für Fuß- und Radverkehr (Elberadweg); seit 2013 für Kfz gesperrt | mittel |
| B0256 | Hafenbrücke (Eisenbahn), Einfahrt Alberthafen | stahl_fachwerk | 76,7 / 5,1 | 76,7 | 0 | eiserne Fachwerkbrücke mit untenliegender Fahrbahn (Gitterträger/Rautenfachwerk), Einfeldträger, Obergurt an d | vorhanden, eingleisiges Anschlussgleis der Hafenbahn (Betriebsumfang nicht ermittelt) | mittel |
| B0800 | Gerüstviadukt der Standseilbahn Dresden (Loschwitz–Weißer Hi | stahl_fachwerk/bergbahn | 102,0 / 7,9 | 79,2 | 0 | stählerne Gerüstbrücke (Trestle: geneigte Stahljoche mit Diagonalverbänden, Längsträger) im Gefälle bis 29,8 % | in Betrieb (Revisionen zweimal jährlich, Frühjahr 16.–27.03.2026); Kulturdenkmal seit 1984 | mittel |
| B0683 | Nesselgrundviadukt, östliche EÜ (Flughafen-S-Bahn, Strecke 6 | bahn_eue_modern | 74,4 / 7,6 | 22,9 / 28,6 / 22,9 | 2 | integrale Stahlbeton-Rahmenbrücke mit 3 Feldern, Mittelfeld gevoutet, Pfeiler als massive Rechteckscheiben auf | in Betrieb | hoch |
| B0684 | Nesselgrundviadukt, westliche EÜ (Görlitz–Dresden, Strecke 6 | bahn_eue_modern | 68,8 / 11,4 | 21,2 / 26,5 / 21,2 | 2 | integrale Stahlbeton-Rahmenbrücke mit 3 Feldern in Bauart des Nachbarbauwerks von 1999 | in Betrieb | hoch |
| B0400 | EÜ Großenhainer Straße/Harkortstraße (Strecken 6363/6239) | bahn_eue_modern | 59,9 / 19,5 | 18,9 / 22,1 / 18,9 | 2 | semiintegrale Rahmenbrücke in Walzträger-in-Beton-(WiB-)Bauweise, 3 Felder | in Betrieb | hoch |
| B0217 | Hegereiterbrücke (Forsthausbrücke), Plauenscher Grund | sandstein_bogen/klein | 40,0 / 4,0 | 14,2 / 14,2 / 14,2 | 2 | Sandstein-Bogenbrücke mit 3 Segmentbögen und 2 massiven Strompfeilern | in Betrieb als Fuß-/Wanderwegbrücke (Bienert-Wanderweg), Kulturdenkmal (LfD 09210561) | mittel |
| B0233 | Bismarckbrücke (Chausseehausbrücke), Weißeritz/Freiberger St | sandstein_bogen/klein | 37,1 / 14,8 | 12,4 / 12,4 / 12,4 | 2 | Sandstein-Bogenbrücke, 3 Segmentbögen, zylindrische Pfeilervorköpfe mit Kegelhauben, Zwickel in polygonalem Sa | in Betrieb (Straßenbahn + Kfz, OSM) | mittel |
| B0887 | Müglitztalbrücke (A 17, bei Heidenau/Dohna) | autobahn_talbruecke/stahlverbund | 347,0 / 29,5 | 54,5 / 68,2 / 68,2 / 68,2 / 54,5 | 4 | Stahlverbund-Balkenbrücke über Müglitz, Müglitztalstraße und Müglitztalbahn | in Betrieb | niedrig |
| B0305 | Nöthnitzgrundbrücke | autobahn_talbruecke/spannbeton | 225,0 / 29,5 | 34,7 / 43,3 / 43,3 / 43,3 / 43,3 / 34,7 | 5 | Spannbeton-Plattenbalkenbrücke (zwei Überbauten), auf Lehrgerüst hergestellt | in Betrieb | niedrig |
| B0027 | Zschonergrundbrücke (A 17) | autobahn_talbruecke/spannbeton | 230,0 / 29,7 | 34,4 / 42,9 / 42,9 / 42,9 / 42,9 / 34,4 | 5 | Betonbalkenbrücke (Hohlkasten mit Kragplatten), zwei Überbauten, Pfeiler rund mit aufgeweitetem Kopf | in Betrieb | mittel |
| B0318 | Zschauketalbrücke (A 17) | autobahn_talbruecke/spannbeton | 142,0 / 33,2 | 39,6 / 49,6 / 49,6 / 39,6 | 3 | Spannbeton-Balkenbrücke (Talbrücke), zwei Überbauten | in Betrieb | niedrig |
| B0066 | Südliche Vorlandbrücke der Niederwarthaer Brücke (S 84, über | stadt_hochstrasse/nachwende | 173,2 / 12,5 | 24,7 / 30,9 / 30,9 / 30,9 / 30,9 / 24,7 | 5 | Vorlandbrücke, Spannbeton-Balkenbrücke (südliche Vorlandbrücke laut Brückenliste) | in Betrieb | niedrig |
| B0267 | Flutrinnenbrücke Washingtonstraße (Kaditzer Flutrinne) | stadt_hochstrasse/nachwende | 160,0 / 23,3 | 22,9 / 28,6 / 28,6 / 28,6 / 28,6 / 22,9 | 5 | Mehrfeldrige Balkenbrücke über die Kaditzer Flutrinne (Bauart nicht belegt) | in Betrieb | niedrig |
| B0271 | Flutrinnenbrücke Sternstraße | stadt_hochstrasse/nachwende | 143,2 / 12,2 | 24,9 / 31,1 / 31,1 / 31,1 / 24,9 | 4 | Balkenbrücke über die Kaditzer Flutrinne (nur OSM/LoD2) | in Betrieb (keine Meldung gefunden) | niedrig |
| B0190 | Elbe-Flutbrücke der A 4 über die Kaditzer Flutrinne | autobahn_talbruecke/stahlverbund | 138,8 / 40,1 | 24,1 / 30,2 / 30,2 / 30,2 / 24,1 | 4 | mehrfeldrige Balkenbrücke (Bauart nicht belegt; vermutlich Stahlverbund wie Unionbrücke) mit Stützenpaaren, Gl | in Betrieb; Fahrbahnerneuerung/Vorarbeiten AS Neustadt–AD Nord 2026 angekündigt (Pressemeldungen), betrifft nicht das Tr | niedrig |
| B0035 | Überführung der Rampe Dresden–Prag (A 4 -> A 17) über die A  | autobahn_ueberfuehrung | 126,2 / 14,6 | 28,0 / 35,1 / 35,1 / 28,0 | 3 | Rampenüberführung im Autobahndreieck Dresden-West (Bauart nicht belegt) | in Betrieb | niedrig |
| B0020 | Nördliche Vorlandbrücke der Niederwarthaer Brücke (S 84, Rad | stadt_hochstrasse/nachwende | 112,0 / 12,9 | 21,2 / 26,5 / 26,5 / 26,5 / 21,2 | 4 | Vorlandbrücke (Beton-Balkenbrücke); vermutlich die aus Hochwasserschutzgründen von 68 m auf 112 m verlängerte  | in Betrieb | niedrig |
| B0039 | Lotzebachtalbrücke (A 4) | autobahn_talbruecke/spannbeton | 120,0 / 41,0 | 37,2 / 46,5 / 37,2 | 2 | Balkenbrücke, zwei Überbauten à 120 m über 3 Felder (Bauart lt. Quelle nicht angegeben, vermutlich Spannbeton) | in Betrieb | niedrig |
| B0307 | Zschauketalbrücke (B 170, Innsbrucker Straße) | stadt_hochstrasse/nachwende | 92,0 / 20,7 | 24,3 / 30,4 / 30,4 / 24,3 | 3 | Plattenbalkenbrücke (Stahl-/Spannbeton) im Zuge des A17-Zubringers B 170 über das Zschauketal | in Betrieb | niedrig |
| B0405 | Kreuzungsbauwerk Dresden-Neustadt Ost (Strecke 6212 über 623 | bahn_eue_modern | 104,2 / 13,4 | 18,1 / 22,7 / 22,7 / 22,7 / 18,1 | 4 | Überwerfungsbauwerk der Görlitzer Strecke über die Leipziger Strecke und die S-Bahn-Gleise am Ostkopf Dresden- | in Betrieb | mittel |
| B0012 | Überführung K 6240 (Am Schreiberbach) über die A 4 – möglich | autobahn_ueberfuehrung | 71,5 / 9,8 | 24,7 / 30,9 / 24,7 | 2 | Straßenüberführung über die A 4 im tiefen Einschnitt; Kandidat für LAP-Projekt 'Tor nach Dresden' (Königspfost | in Betrieb | niedrig |
| B0715 | Überführung S 175 über die A 17 (östlich Lockwitztalbrücke) | autobahn_ueberfuehrung | 78,7 / 12,4 | 24,2 / 30,3 / 24,2 | 2 | Straßenüberführung über die A 17 (Bauart nicht belegt; vermutlich Spannbeton-Plattenbalken/Rahmen) | in Betrieb | niedrig |
| B0540 | Brücke Königsbrücker Straße über die DB-Gleise (Industriegel | stadt_hochstrasse/ddr_ueber_bahn | 71,0 / 32,3 | 11,1 / 13,9 / 13,9 / 13,9 / 13,9 / 11,1 | 5 | Spannbetonbrücke aus drei getrennten Überbauten: Zug A Straßenbahn (2 Gleise), Zug B und C je eine Richtungsfa | in Betrieb (seit 11/2023 Dauerüberwachung, jährliche Sonderprüfung, Schallemissionsmonitoring); Ausschreibung 2026, Bauv | hoch |
| B0349 | Kreuzungsbauwerk Dresden Hauptbahnhof (KDH), km 63,215 Strec | bahn_eue_modern | 120,0 / 32,2 | 23,6 / 29,5 / 23,6 | 2 | Überwerfungsbauwerk (Eisenbahnüberführung über die Sachsen-Franken-Magistrale 6258) westlich des Hbf; Ersatzne | im Bau – neue Gleise ab 16.11.2026 geplant, Inbetriebnahme des Gesamtbauwerks November 2027 (DB-Pressemitteilung 08.10.2 | mittel |
| B0344 | EÜ Am Hauptbahnhof (B 170), südlicher Teil (Strecken 6240/62 | bahn_eue_historisch/erneuert | 76,3 / 45,9 | 17,0 / 21,2 / 21,2 / 17,0 | 3 | Eisenbahnüberführung der Hbf-Westausfahrt über die B 170 „Am Hauptbahnhof“ samt Straßenbahn; Überbau in den 19 | in Betrieb | niedrig |
| B0343 | EÜ Am Hauptbahnhof (B 170), nördlicher Teil (Strecke 6239, S | bahn_eue_historisch/erneuert | 74,9 / 33,9 | 16,6 / 20,8 / 20,8 / 16,6 | 3 | Eisenbahnüberführung der Hbf-Nordhallengleise (S-Bahn) über B 170 und Straßenbahn; Überbau 1990er Jahre erneue | in Betrieb | niedrig |
| B0398 | EÜ Bischofsplatz/Hechtstraße mit Hp Dresden-Bischofsplatz (S | bahn_eue_modern | 74,9 / 22,8 | 23,0 / 28,8 / 23,0 | 2 | moderne Eisenbahnüberführung(en) (zwei Überbauten) über Bischofsplatz, Hechtstraße und Straßenbahn; S-Bahn-Hal | in Betrieb | mittel |
| B0404 | Kreuzungsbauwerk Dresden-Neustadt Ost (Strecke 6241 über 623 | bahn_eue_modern | 74,9 / 7,1 | 23,0 / 28,8 / 23,0 | 2 | eingleisiges Überwerfungsbauwerk der Güterzugstrecke über die Leipziger Strecke und die S-Bahn-Gleise; Bauart  | in Betrieb | niedrig |
| B0263 | EÜ über Gleise der Strecke 6272 bei Dresden-Friedrichstadt ( | sandstein_bogen/klein | 73,7 / 12,5 | 7,8 / 9,7 / 9,7 / 9,7 / 9,7 / 9,7 / 9,7 / 7,8 | 7 | zwei parallele eingleisige Eisenbahnbrücken über Gleisanlagen; OSM: Bogenbrücke – Bauart nicht belegt | in Betrieb | niedrig |
| B0262 | EÜ über Gleise der Strecke 6272 bei Dresden-Friedrichstadt ( | sandstein_bogen/klein | 73,7 / 12,5 | 8,3 / 10,4 / 10,4 / 10,4 / 10,4 / 10,4 / 8,3 | 6 | zwei parallele eingleisige Eisenbahnbrücken über Gleisanlagen; OSM: Bogenbrücke – Bauart nicht belegt | in Betrieb | niedrig |
| B0304 | Überführung Innsbrucker Straße (B 170) über die A 17, AS Dre | autobahn_ueberfuehrung | 65,1 / 26,2 | 32,5 / 32,5 | 1 | Straßenüberführung über die A 17 (Bauart nicht belegt; vermutlich Spannbeton-Plattenbalken/Rahmen, 2–3 Felder) | in Betrieb | niedrig |
| B0193 | Brücke Meißner Landstraße über die Bahn | stadt_beton_balken/ueberfuehrung | 64,0 / 16,1 | 32,0 / 32,0 | 1 | Balkenbrücke (OSM) | in Betrieb | niedrig |
| B0237 | Weißeritzbrücke Löbtauer Straße | stadt_beton_balken/gewaesser | 56,1 / 17,1 | 28,1 / 28,1 | 1 | Zweifeldbrücke (Neubau nach Hochwasser 2002, Voraussetzung für Aufweitung des Weißeritzknicks) | in Betrieb | mittel |
| B0216 | Weißeritzbrücke am Felsenkeller (Strecke 6258, km 3,544) | bahn_eue_modern | 54,9 / 10,8 | 27,4 / 27,4 | 1 | zweigleisige Eisenbahnbrücke über die Vereinigte Weißeritz im Plauenschen Grund; Neubau 2001 (Bauart nicht bel | in Betrieb | mittel |
| B0750 | EÜ Moränenende / S-Bahnhof Dobritz (Strecken 6239/6240) | bahn_eue_modern | 53,1 / 27,1 | 26,6 / 26,6 | 1 | Eisenbahnüberführung am S-Bahnhof Dobritz über Straße Moränenende, Straßenbahn, Fußweg/Treppen und verrohrten  | in Betrieb | niedrig |
| B0150 | Weißeritzbrücke an der Heidenschanze (Strecke 6258, km 5,057 | bahn_eue_modern | 49,9 / 10,2 | 24,9 / 24,9 | 1 | zweigleisige Stahlbeton-Balken-/Rahmenbrücke mit gevouteter Untersicht und Zwischenpfeiler, über Weißeritz und | in Betrieb | mittel |
| B0155 | EÜ Weißeritz Heidenschanze Nordwest (Strecke 6258, km 4,806) | bahn_eue_modern | 49,7 / 10,1 | 24,9 / 24,9 | 1 | zweigleisige Eisenbahnbrücke über die Vereinigte Weißeritz westlich der A-17-Brücke; Neubau 2003, OSM: Bogen – | in Betrieb | niedrig |
| B0416 | Brücke Ludwig-Kossuth-Straße über die A 4 | autobahn_ueberfuehrung | 49,0 / 20,7 | 24,5 / 24,5 | 1 | Balkenbrücke (OSM) | in Betrieb | niedrig |
| B0154 | EÜ Weißeritz Heidenschanze Nord (Strecke 6258, km 4,588) | bahn_eue_modern | 48,2 / 11,3 | 24,1 / 24,1 | 1 | zweigleisige Eisenbahnbrücke über die Vereinigte Weißeritz; Neubau 2003 (IBB GmbH), OSM: Bogen – Bauart nicht  | in Betrieb | niedrig |
| B0464 | EÜ Rayskistraße/Karcherallee (Strecken 6239/6240, Strehlen) | bahn_eue_modern | 46,1 / 18,6 | 23,1 / 23,1 | 1 | Eisenbahnüberführung der Elbtalbahn über Rayskistraße/Karcherallee und Radweg; Bauart nicht belegt | in Betrieb | niedrig |
| B0325 | Brücke Südhöhe über die Bergstraße | stadt_beton_balken/ueberfuehrung | 44,7 / 22,0 | 22,4 / 22,4 | 1 | Balkenbrücke (OSM) | in Betrieb | niedrig |
| B0558 | Brücke Müller-Armack-Straße über die Flughafen-S-Bahn | stadt_beton_balken/ueberfuehrung | 43,4 / 17,2 | 21,7 / 21,7 | 1 | Straßenbrücke über Bahnstrecke 6607 (OSM, Bauart ohne Tag) | in Betrieb | niedrig |
| B0388 | EÜ Eisenbahnstraße (Strecke 6246 Dresden-Pieschen–Dresden-Ne | bahn_eue_historisch/original | 42,0 / 9,2 | 21,0 / 21,0 | 1 | genietete Blechträgerbrücke mit gusseisernen Pendelstützen (Zwischenstützen zwischen Fahrbahn und Gehweg), Kon | in Betrieb (eingleisig; zweites Gleis abgebaut/abandoned laut OSM); Kulturdenkmal 09215393 | hoch |
| B0251 | EÜ Löbtauer Straße (Strecke 6247 Dresden-Friedrichstadt–Dres | bahn_eue_historisch/original | 41,8 / 12,4 | 20,9 / 20,9 | 1 | Eisenbahnüberführung über Löbtauer Straße und Straßenbahn; Bauart nicht belegt (OSM: Balken) | in Betrieb | niedrig |
| B0180 | Weißeritzbrücke(n) Hamburger Straße (an der Weißeritzmündung | stadt_beton_balken/gewaesser | 38,9 / 32,1 | 38,9 | 0 | Balkenbrücke(n) (OSM), Bauart nicht belegt | in Betrieb; Hamburger Straße wird 2026–2029 zwischen Alte Meißner Landstraße und den Weißeritzbrücken ausgebaut (Brücken | niedrig |
| B0232 | Landwärtige Weißeritzbrücke Freiberger Straße | sandstein_bogen/klein | 35,3 / 11,8 | 7,8 / 9,8 / 9,8 / 7,8 | 3 | Bogenbrücke laut OSM (bridge:structure=arch), unmittelbar unterhalb der Bismarckbrücke | in Betrieb | niedrig |
| B0255 | Weißeritzbrücke Fröbelstraße | stadt_beton_balken/gewaesser | 31,2 / 32,7 | 31,2 | 0 | Balkenbrücke mit Straßenbahn im Knoten Fröbelstraße/Emerich-Ambros-Ufer (OSM) | in Betrieb | niedrig |
| B0387 | Wallgrabenbrücke (Kronentor, Zwinger) | fuss_holz_klein/steg | 32,0 / 5,5 | 9,5 / 11,9 / 9,5 | 2 | dreifeldriger Holzsteg auf zwei Holzjochen (Stahlträger, Holz, Mauerwerk, ganz mit Holz verkleidet), seit 1996 | in Betrieb (Erneuerung in den 2020er Jahren geplant, tiefere Lage wegen Funden 2021–2025; kein Baubeginn gefunden) | mittel |
| B0796 | Mordgrundbrücke (Bautzner Landstraße über Mordgrundbach) | sandstein_bogen/klein | 30,5 / 20,3 | 30,5 | 0 | Steinbogenbrücke 1828, Bogen stromauf stufenweise verjüngt; heute unter breiter Straße (B 6) mit Straßenbahn | in Betrieb, Kulturdenkmal (LfD 09217023) | mittel |
| B0234 | Weißeritzbrücke Wernerstraße | stadt_beton_balken/gewaesser | 29,2 / 17,1 | 29,2 | 0 | einfeldriger Balken, Neubau nach Hochwasser 2002 | in Betrieb | mittel |
| B0324 | Campus-Brücke TU Dresden | fuss_rad_stahl | 28,9 / 12,7 | 28,9 | 0 | Fußgängerbrücken-/Stegsystem im TU-Campus (OSM: 18 Fußwegstücke, start_date 2004, Breiten 4–5 m) | in Betrieb | niedrig |
| B0383 | EÜ Leipziger Straße (Strecken 6240/6241/6239/6363) | bahn_eue_historisch/erneuert | 28,2 / 26,2 | 14,1 / 14,1 | 1 | Eisenbahnüberführung der Verbindungsbahn Marienbrücke–Neustadt über Leipziger Straße und Straßenbahn; historis | in Betrieb | mittel |
| B0230 | Weißeritzbrücke Würzburger Straße | stadt_beton_balken/gewaesser | 28,1 / 14,3 | 28,1 | 0 | einfeldrige Platten-/Balkenbrücke mit dünnem Überbau (Foto 2024) | in Betrieb; Foto 04/2024 zeigt rot-weiße Warnbaken am Geländer (Grund unbekannt) | niedrig |
| B0231 | Weißeritzbrücke Oederaner Straße | stadt_beton_balken/gewaesser | 27,4 / 15,4 | 27,4 | 0 | Balkenbrücke (Neubau 2004) | in Betrieb | niedrig |
| B0215 | Hofmühlenbrücke (Weißeritzbrücke Altplauen) | stadt_beton_balken/gewaesser | 27,2 / 14,8 | 27,2 | 0 | einfeldriger schlanker Balken (Neubau nach Hochwasser 2002, Foto) | in Betrieb | mittel |
| B0374 | EÜ Hansastraße (Strecken 6363/6212/6241) | bahn_eue_historisch/erneuert | 27,2 / 28,4 | 13,6 / 13,6 | 1 | Eisenbahnüberführung am Bahnhof Dresden-Neustadt über Hansastraße (B 170) und Straßenbahn; historische Sandste | in Betrieb | mittel |
| B0134 | Weißeritzbrücke Coschützer Straße (Freital-Potschappel) | stadt_beton_balken/gewaesser | 27,0 / 14,6 | 27,0 | 0 | Balkenbrücke (OSM) | in Betrieb | niedrig |
| B0342 | EÜ Andreas-Schubert-Straße (Strecke 6239, S-Bahn) | bahn_eue_historisch/original | 26,2 / 22,4 | 26,2 | 0 | kurze Eisenbahnüberführung der Hbf-Ostausfahrt über die Andreas-Schubert-Straße; Bauart nicht belegt (OSM: Bal | in Betrieb | niedrig |
| B1129 | EÜ Straße des Friedens, Radeberg (Strecke 6212 + Nebengleis  | bahn_eue_historisch/original | 26,1 / 17,1 | 26,1 | 0 | Eisenbahnüberführung über die Straße des Friedens in Radeberg; Bauart nicht belegt | in Betrieb | niedrig |
| B0348 | EÜ Andreas-Schubert-Straße (Strecken 6240/6241) | bahn_eue_historisch/original | 25,7 / 26,8 | 25,7 | 0 | Eisenbahnüberführung der Fern- und Güterzuggleise über die Andreas-Schubert-Straße; Bauart nicht belegt (OSM:  | in Betrieb | niedrig |
| B0350 | EÜ Franklinstraße (Strecken 6239/6240) | sandstein_bogen/klein | 24,4 / 19,2 | 7,5 / 9,4 / 7,5 | 2 | Eisenbahnüberführung der Hbf-Ostausfahrt (Richtung Pirna) über die Franklinstraße; OSM kennzeichnet sie als Bo | in Betrieb | niedrig |
| B0341 | EÜ Freiberger Straße (Strecken 6240/6241) | bahn_eue_historisch/erneuert | 24,3 / 20,4 | 24,3 | 0 | Eisenbahnüberführung der Verbindungsbahn Hbf–Dresden Mitte über Freiberger Straße und Straßenbahn; Bauart nich | in Betrieb | niedrig |
| B0142 | Weißeritzbrücke Richard-Wagner-Straße (Freital-Potschappel) | stadt_beton_balken/gewaesser | 22,9 / 13,5 | 22,9 | 0 | Balkenbrücke (OSM) | in Betrieb | niedrig |
| B0147 | EÜ Coschützer Straße (Windbergbahn, Strecke 6609, km 0,872) | bahn_eue_historisch/original | 18,0 / 4,4 | 20,0 | 0 | eingleisige Eisenbahnüberführung, 18 m; Bauart nicht belegt (OSM: Balken; vermutlich Stahlträger wie B0135) | vorhanden, ohne Verkehr (Museumsbahn-Sonderfahrten nur zwischen Dresden-Gittersee und km 3,55; Ziel Freital-Birkigt) | niedrig |
| B0135 | EÜ Karlsruher Straße (Windbergbahn, Strecke 6609, km 5,204) | bahn_eue_historisch/original | 18,0 / 13,0 | 18,0 | 0 | eingleisige genietete Blechträgerbrücke (Vollwandträger mit Aussteifungen), ein Feld ~18 m, auf Betonwiderlage | vorhanden; Museumsbahnstrecke (Windbergbahn e. V.), Sonderfahrten ab Dresden-Gittersee | mittel |

Wichtige Einzelbefunde aus der Recherche:

- **Löbtauer Brücke** (Hochstraße B 173) ist laut Wikipedia 998 m lang. Die OSM-Fläche deckt nur 710 m; die übrigen Felder liegen in Nachbarbauwerken bzw. Wegen ohne Fläche.
- **Brücke Budapester Straße**: rund 850 m lange DDR-Hochstraße aus zwei Brückenzügen (in OSM zwei Teile mit 167 bzw. 159 m). Seit 2026 stehen darunter stählerne Notstützen und Stapel aus Betonringen (sichtbares Detail!).
- **Nossener Brücke**: Der Altbau von 1964 steht noch. Seit 14.06.2026 rollt der Verkehr nur über den Südzug; das nördliche Teilbauwerk und die Brücke über die Fabrikstraße werden abgebrochen. Neubau bis Mitte 2031.
- **Schlachthofbrücke**: 13 Felder (3 × 22,08, 7 × 24,42, 3 × 26,10 m) mit sechseckigen Pfeilerpaaren, dazu die Straßenbahnbrücke von 2011.
- **Marienbrücke (Eisenbahn)**, **Großenhainer Straße** (18,9/22,1/18,9 m), **Nesselgrundviadukt** und **Hafenbrücken** sind gut belegt. Die Eisenbahnüberführungen am Hauptbahnhof und in der Neustadt sind nur über Typen zugeordnet.
- **Überwerfungsbauwerk Klotzsche** (Flughafen-S-Bahn über Strecke 6212): OSM 525 m durchgehend; Wikipedia nennt ~200 m, Fotos zeigen einen langen Viadukt. Unsicher.
- **Lockwitztalbrücke**: 9 Felder (48–125 m), sechs Beton-Halbbögen, blauer Stahltrog (#2e4a5f), ~64 m über dem Tal. **Weißeritztalbrücke**: türkiser Stahlkasten (#5d827f) mit Glaswänden.
- **Unionbrücke** (A 4): 8 Felder 24,85–35,35 m, dunkelgraue Stahlstützen, Pfeiler mit rotem Granit verkleidet, 4,5 m hohe Glaswand.
- Die Streckennummern im Inventar folgen dem OSM-`ref` (6239 = S-Bahn Pirna–Coswig, 6240 = Elbtalbahn, 6258 = Dresden–Werdau, 6212 = Görlitz–Dresden, 6248 = Berlin–Dresden, 6607 = Flughafen).

## 5. Brückentypen (Standardmaße)

| Typ | Bezeichnung | Anzahl Haupt/Klein | Felder typ. | Überbauhöhe | Geländer | Hauptfarben |
|---|---|---|---|---|---|---|
| `sandstein_bogen` | Elbsandstein-Bogenbrücke (historisch, 1780–1910) | 25 / 15 | klein 9,5 m, gross 28,0 m, viadukt 14,5 m | Scheitel: Fahrbahn bis Gewölbeunterkante = Ringdicke + 0,4–0,8 m Überschüttung | Variante A: massive Sandsteinbrüstung mit Abdeckplatte (Augustusbrücke, alte Weißeritzbrücken); Variante B: Gussgeländer; 1,10 m `#2a2e36` | masonry `#bfa983`, masonry_sunlit `#d8c49a`, masonry_weathered `#a39179`, patina_dark `#5c5554` |
| `stadt_beton_balken` | Stadt-Balkenbrücke Stahlbeton/Spannbeton kurz (1–3 Felder, v. a. Nachwende/nach Hochwasser 2002) | 131 / 156 | 26,0 m | h ≈ L/25 … L/30 (Platte/Plattenbalken) | Stahl-Füllstabgeländer (Pfosten ~2,2 m, senkrechte Rundstäbe Abstand 0,12 m, Rohr-/Flachhandlauf), verzinkt; 1,10 m `#a9a8a2` | concrete `#9d978c`, concrete_fresh `#b9b6ae`, kappe `#c7c6bd`, railing `#a9a8a2` |
| `stadt_hochstrasse` | Mehrfeldrige Stadt-Hochstraße / Viadukt (Spannbeton, Stahlverbund) über Bahn, Flutrinne, Straßen | 17 / 0 | nachwende 27,0 m, ddr_ueber_bahn 12,0 m | h ≈ L/17 … L/20 | nachwende: verzinktes Füllstabgeländer 1,1–1,3 m; ddr: dunkles Stabgeländer mit senkrechten Stäben; über elektrifizierte; 1,10 m `#a9a8a2` | concrete `#9d978c`, concrete_ddr `#8f8a82`, kappe `#b2adae`, railing `#a9a8a2` |
| `autobahn_talbruecke` | Autobahn-Talbrücke (A 17/A 4): zwei getrennte Überbauten, Spannbeton-Hohlkasten oder Stahlverbund mit farbigem Stahlkasten | 12 / 0 | spannbeton 42,0 m, stahlverbund 60,0 m | spannbeton h ≈ L/15 … L/17; stahlverbund h ≈ L/19 … L/23, gevoutet über Strompfeilern | Füllstabgeländer verzinkt außen hinter der Schutzplanke; 1,00 m `#8c9294` | concrete `#a4a6a3`, concrete_sunlit `#b4b6b2`, underside `#8e938f`, steel_lockwitz_blau `#2e4a5f` |
| `autobahn_ueberfuehrung` | Überführung über/unter der Autobahn (Spannbeton-Plattenbalken oder Rahmen, 1–4 Felder) | 49 / 4 | 30,0 m | h ≈ L/18 … L/22, Rahmen mit Vouten | Füllstabgeländer verzinkt; 1,00 m `#8c9294` | concrete `#a4a6a3`, kappe `#b0b2b0`, railing `#8c9294`, cladding_sandstone `#c8b48c` |
| `bahn_eue_historisch` | Eisenbahnüberführung der Hochlegung 1890–1901 (Sandsteinwiderlager; Stahlträger original oder Überbau erneuert) | 51 / 1 | 18,0 m | original 1,60, erneuert 1,20 | Stahl-Stabgeländer (senkrechte Stäbe, Flachstahl-Handlauf) oder Rohrgeländer (Pfosten + 2 Holme); an Brückenköpfen Sands; 1,00 m `#4f4f4c` | masonry `#9a8a6c`, masonry_light `#c6ab81`, masonry_patina `#4a463e`, plaster `#a29b8c` |
| `bahn_eue_modern` | Moderne Eisenbahnüberführung / Kreuzungsbauwerk (Stahlbeton-Rahmen, Walzträger in Beton, Spannbeton), 1999–2027 | 66 / 21 | 22,0 m | WiB/Platte h ≈ L/18; gevoutete Rahmen an Stützen höher | Stahlgeländer mit senkrechten Füllstäben und Rahmenholm auf Betonkappe (Pfosten ~1,5–2 m); 1,10 m `#5a5552` | concrete `#b5b0a5`, concrete_sunlit `#c8c6be`, concrete_shadow `#645f51`, ballast `#675041` |
| `stahl_fachwerk` | Stahlfachwerk-/Stahlträgerbrücke (genietet, Köpcke-Ära) – Sonderfälle | 9 / 1 | 77,0 m | default 1,20, truss_height_m 10,00 | Stabgeländer innen vor den Fachwerkwänden; 1,10 m `#2c3a44` | steel_road_bridge `#b8d4e0`, steel_rail_bridge `#3d5a8a`, abutment `#504d4a` |
| `fuss_rad_stahl` | Moderne Fuß-/Radwegbrücke (Stahl, Stahlbeton, Schrägseil), 2000–2015 | 8 / 185 | 30,0 m | h ≈ L/30 … L/40 | Edelstahl-/verzinktes Füllstab- oder Seilnetzgeländer mit Holzhandlauf, teils LED im Handlauf; 1,30 m `#9a9a96` | deck `#d4d2cc`, steel `#c9c9c4`, railing `#9a9a96`, wood_handrail `#8a6a48` |
| `fuss_holz_klein` | Kleiner Steg / Wirtschaftsweg-Brücke (Holz, Betonplatte oder Wellstahl-Durchlass) – Dresdner Heide, Parks, Felder | 23 / 409 | 6,0 m | default 0,40 | Holzgeländer (Pfosten 12×12 cm alle 2 m, Handlauf + Knieholm) bzw. Stahlrohrgeländer; Wirtschaftswege oft nur Bordbalken; 1,00 m `#7a5f44` | wood `#7a5f44`, concrete `#a8a49a`, stone `#7c714f` |

Varianten, Pfeilerformen, Kappen/Gesimse, Schutzplanken, Lärmschutzwände und Widerlager stehen vollständig in `types` der JSON. Kurzcharakteristik:

- **`sandstein_bogen`**: Pfeiler: Quaderpfeiler mit halbrunden oder spitzen Vorköpfen (Eisbrecher) und Kegel-/Gesimskappe; bei großen Brücken Kanzel über dem Pfeiler (Fahrbahnaufweitung 3–5 m je Seite). Widerlager: Sandsteinquader-Widerlager mit Flügelmauern, Böschungen gepflastert; Treppen zum Ufer. Licht: historisierende Kandelaber (ein- oder zweiarmig) auf der Brüstung/Kanzel oder moderne Mastleuchten bei Straßenbahnbrücken. Varianten: *gross* – Elbbrücken-Bogenreihen (Augustus-, Albert-, Marienbrücke, Vorlandbögen Marien-Bahn): Bögen 14–39 m, Pfeiler mit Vorköpfen und Kanzeln, Konsolgesims, Brüstung Sandstein oder Gussgeländer; *klein* – 1–3 Segmentbögen 6–15 m über Weißeritz/Prießnitz/Lockwitzbach/Kaitzbach, Fuß- oder Straßenbrücke; *viadukt* – hohe Talüberbrückung mit Quaderpfeilern (Prießnitztalviadukt 3×14,5 m, 23 m hoch)
- **`stadt_beton_balken`**: Pfeiler: Wandscheibe oder 2–3 Rundstützen Ø 0,8–1,0 m je Achse. Widerlager: Stahlbeton-Kastenwiderlager in Flucht der Ufermauern; Ufermauern Bruchstein (Syenit/Sandstein, #7c714f) mit Betonkrone. Licht: meist keine eigenen Leuchten (Straßenleuchten am Ufer/Anschluss). Varianten: *gewaesser* – über Weißeritz/Bäche/Flutrinne, leicht überhöhte Gradiente, Ufermauern aus Bruchstein; *ueberfuehrung* – Straße über Straße/Weg, Widerlager vertikal, Stützenreihe bei 2–3 Feldern; *bogen_beton* – OSM bridge:structure=arch bei Straßen > 40 m ohne Denkmalstatus: moderner Stahlbeton-Bogen/Rahmen (Bogen unter der Fahrbahn, Ständer), betongrau – nicht Sandstein
- **`stadt_hochstrasse`**: Pfeiler: nachwende: Einzelpfeiler 1,6–3 m (teils natursteinverkleidet); ddr: Stützenreihen, sechseckige Pfeilerpaare (Schlachthof). Widerlager: Sichtbeton-Widerlager, Böschungskegel oder Stützwände. Licht: Mastleuchten mit Ausleger 8–10 m am Fahrbahnrand oder Mittelstreifen, Abstand ~30 m. Varianten: *nachwende* – 1995–2010: Durchlaufträger (Plattenbalken/Hohlkasten/Stahlverbund), Felder 22–40 m, schlanke Pfeiler, oft Lärmschutzglas (Löbtauer Brücke, Waltherstraße, Schlachthof-Überbau, Washingtonstraße); *ddr_ueber_bahn* – 1959–1979: getrennte Überbauten, Stützenreihen (3 Stützen je Achse und Überbau, Ø/Breite 0,7 m, Achsabstand ~12 m), dunkles Stabgeländer (Budapester Str., Nossener Brücke Bestand, Königsbrücker Str.)
- **`autobahn_talbruecke`**: Pfeiler: je Überbau ein Rechteckpfeiler mit Fasen/Nuten und aufgeweitetem Kopf (Schaft ~2,5×4 m) oder Rundpfeiler Ø 2,5 m mit Kapitell. Widerlager: Kastenwiderlager im Hang, begrünte Böschungskegel, Flügelwände parallel. Licht: keine Fahrbahnbeleuchtung auf freier Strecke. Varianten: *spannbeton* – Hohlkasten konstant hoch, Felder 35–50 m, betongrau (Gebergrund, Zschonergrund, Zschauketal, Lotzebach); *stahlverbund* – farbiger Stahltrog/-kasten unter heller Betonplatte, Felder 50–130 m, ggf. gevoutet (Lockwitztal blau, Weißeritztal türkis, Elbe A4 blassgrün, Unionbrücke dunkelgrau)
- **`autobahn_ueberfuehrung`**: Pfeiler: Rechteck-/Rundstützen oder Wandscheibe im Mittelstreifen. Widerlager: Bankwiderlager auf dem Böschungskopf; A 4 Dresden: Natursteinverkleidung ('Brückenfamilie': rötlicher Granit/Elbsandstein/grauer Granit). Licht: keine (außer innerörtlich).
- **`bahn_eue_historisch`**: Pfeiler: gusseiserne Säulen mit Kapitell (Pendelstützen) oder Stahlstützen am Bordstein. Widerlager: Elbsandstein-Quader (bossiert/rustiziert) mit Sockel- und Abschlussgesims, übergehend in Bahndamm-Stützmauern; oft teilverputzt, Graffiti. Licht: Unterführungsleuchten an den Widerlagern; auf der Brücke Oberleitungsmasten. Varianten: *original* – genietete Blechträger (Steghöhe 1,2–1,8 m, Steifenraster 1,0–1,5 m), teils gusseiserne Pendelstützen am Gehwegrand; rot-weißer Warnstreifen bei geringer Höhe; *erneuert* – Walzträger in Beton / Stahlbetonplatte mit glatter heller Stirn (1,0–1,5 m) auf den alten Sandsteinwiderlagern (Hbf, Neustadt, Leipziger Vorstadt)
- **`bahn_eue_modern`**: Pfeiler: Rechteckpfeiler/Wandscheiben oder Rundstützen, glatter Sichtbeton. Widerlager: glatte Sichtbeton-Widerlager/Rahmenstiele, Böschungen mit Treppen; an Gewässern Bruchsteinverkleidung. Licht: keine; Oberleitungsmasten auf der Kappe (Abstand 50–65 m).
- **`stahl_fachwerk`**: Pfeiler: Sandstein-/Bruchsteinwiderlager. Widerlager: –. Licht: keine/vereinzelt.
- **`fuss_rad_stahl`**: Pfeiler: schlanke Stahlstützen oder Pylon (Schrägseil). Widerlager: –. Licht: LED im Handlauf oder Pollerleuchten.
- **`fuss_holz_klein`**: Pfeiler: –. Widerlager: Bruchstein- oder Betonwiderlager, Bachufer naturnah. Licht: keine. Varianten: *steg* – Fuß-/Radsteg Holz oder Betonplatte, 2–3 m breit; *wirtschaftsweg* – Wirtschafts-/Forstweg (highway=track): Stahlbetonplatte oder Bruchsteingewölbe/Durchlass, 3,5–4,5 m breit, Bordbalken statt Geländer

## 6. Auswahlregeln (OSM-Tags/Kontext → Typ)

1. **Wenn** Bauwerk ist recherchiert (Feld research=true) **→** Typ/Maße aus Recherche; model='unikat' bei Landmarken
2. **Wenn** bridge:structure=truss ODER Name enthält 'Hafenbrücke' **→** stahl_fachwerk
3. **Wenn** nur Fuß/Rad/Feldweg (highway=footway|path|cycleway|steps|pedestrian|track) **→** material=wood ODER Länge<8 m → fuss_holz_klein; bridge:structure=arch ODER material=stone/sandstone → sandstein_bogen (klein); sonst fuss_rad_stahl
4. **Wenn** railway=rail|light_rail|narrow_gauge (auch construction/disused/abandoned) **→** bridge:structure=arch/material=stone → sandstein_bogen; im Hochlage-Ring (UTM-Kacheln E 408–414, N 5654–5658, Strecken 6239/6240/6241/6244/6246/6247/6248/6363/6212) und quert Straße/Tram und L ≤ 45 m → bahn_eue_historisch; sonst bahn_eue_modern
5. **Wenn** highway=motorway|motorway_link|trunk ODER ref beginnt mit 'A ' **→** L ≥ 100 m ODER Höhe über Gelände ≥ 12 m → autobahn_talbruecke (variant stahlverbund bei material=steel/composite, sonst spannbeton); sonst autobahn_ueberfuehrung
6. **Wenn** Straße quert eine Autobahn (crosses enthält 'A …') **→** autobahn_ueberfuehrung
7. **Wenn** Straße/Tram/Service **→** bridge:structure=arch ODER material=stone/sandstone → sandstein_bogen (klein); L ≥ 80 m → stadt_hochstrasse (variant ddr_ueber_bahn wenn Bahn gequert, sonst nachwende); quert Bahn und L ≥ 30 m → stadt_hochstrasse (ddr_ueber_bahn); sonst stadt_beton_balken (variant gewaesser bei Gewässerquerung, sonst ueberfuehrung)
8. **Wenn** Spannweiten unbekannt **→** n = max(1, round(L / typical_span_m)); gleichmäßig teilen, Endfelder 0,8×; Pfeiler nicht in Fahrbahnen/Gleise/Gewässerachse der gequerten Wege setzen (Stützen in Mittelstreifen/Gehwegkante verschieben)
9. **Wenn** Breite unbekannt **→** Straße: Fahrstreifen×3,25 + Gleise×3,1 + Gehwege (2,5 je Seite, falls sidewalk) + 2×0,6 Kappe; Bahn: 4,5 m je Gleis + 2×1,2; Fuß/Rad 3,0–4,0 m

Allgemeine Bauregeln für den Generator (gegen harte Kanten, für saubere Anschlüsse):

- Deckoberkante = Straßenprofil (`road_surface.py`); Überbau hängt darunter mit `deck_depth_m`. An den Enden **Widerlager mit Flügelmauern** bis ins Gelände (Böschungskegel 1:1,5) statt offener Plattenkanten. Die Fahrbahnplatte läuft 2–5 m auf die Rampe weiter (Schleppplatte), damit kein Höhensprung entsteht.
- Kappe/Gesims als durchgehendes helles Band (0,35–0,6 m Ansicht) mit 2–5 cm Überstand und Tropfkante. Das Geländer steht auf der Kappe, 0,15–0,3 m vom Rand eingerückt.
- Pfeiler in Querungsachsen vermeiden: Felder so teilen, dass gequerte Fahrbahnen/Gleise/Fahrrinne in Feldmitte liegen (Daten: `crosses`; Stationen der Querungen lassen sich wie in Abschnitt 3 aus der Achse schneiden).
- Brückenachse folgt den OSM-Wegen; Breite aus `width_m`. Bei mehreren parallelen Überbauten (Autobahn, Budapester, Flügelweg) Fuge 0,5–1,0 m.
- Farbvariation: Beton ±6 % Helligkeit je Feld, Sandstein mit Patina-Laufspuren von Gesims und Fugen, Graffiti an Widerlagern/Pfeilerfüßen in der Innenstadt.

## 7. Kleinbrücken (nur gezählt)

Kriterium: keine Straße/Tram/Bahn oder < 15 m, unbenannt. Gesamt **792**.

| Typ | Anzahl | Aufschlüsselung |
|---|---|---|
| `fuss_holz_klein` | 409 | Fuß/Rad über Gewässer: 354, Fuß/Rad über Straße/Weg: 43, Fuß/Rad über unbekannt: 11, Straße/Zufahrt über Gewässer: 1 |
| `fuss_rad_stahl` | 185 | Fuß/Rad über Gewässer: 132, Fuß/Rad über unbekannt: 33, Fuß/Rad über Straße/Weg: 17, Fuß/Rad über Bahn/Tram: 2, Straße/Zufahrt über Bahn/Tram: 1 |
| `stadt_beton_balken` | 156 | Straße/Zufahrt über Gewässer: 142, Straße/Zufahrt über Straße/Weg: 11, Straße/Zufahrt über unbekannt: 2, Straße/Zufahrt über Bahn/Tram: 1 |
| `bahn_eue_modern` | 21 | Bahn über Straße/Weg: 8, Bahn über unbekannt: 7, Bahn über Gewässer: 5, Bahn über Bahn/Tram: 1 |
| `sandstein_bogen` | 15 | Fuß/Rad über Gewässer: 8, Straße/Zufahrt über Gewässer: 4, Fuß/Rad über Straße/Weg: 2, Fuß/Rad über unbekannt: 1 |
| `autobahn_ueberfuehrung` | 4 | Straße/Zufahrt über Gewässer: 2, Straße/Zufahrt über unbekannt: 2 |
| `stahl_fachwerk` | 1 | Bahn über Bahn/Tram: 1 |
| `bahn_eue_historisch` | 1 | Bahn über Bahn/Tram: 1 |

## 8. Sonstige Bauwerke (keine Verkehrsbrücken)

sonstiges (Rohrbrücke, Grünbrücke, Teilfläche): 30, Gebäudebrücke/Übergang: 9. Sie stehen in `other_structures` mit OSM-IDs, u. a. die Fernwärme-Rohrbrücke an der Freiberger Straße (221 m, wird mit der Nossener Brücke ausgehoben), die Grünbrücke (`man_made=wildlife_crossing`, 195 m) bei Wilschdorf und Gebäudeübergänge (z. B. Industriebrücke 128 m in Kachel 414_5662).

## 9. Unsicherheiten

- **Farben** stammen fast immer aus der Fotoanalyse (Median über Bildbereiche, Licht korrigiert); RAL-Töne nennt keine Quelle. Blaues Wunder: „Himmel-/Hellblau“, Originalton 1893 per Farbanalyse ermittelt, aber nicht veröffentlicht.
- **Spannweiten**: Für 18 Bauwerke stammen die Felder aus der Recherche, davon nur ein Teil vollständig belegt (siehe `spans_src`/`notes`). Bei Augustus- und Albertbrücke ist die Reihenfolge bzw. sind die Flutbögen aus OSM-Kanzellagen rekonstruiert (Pfeilerdicken angenommen). Alle `typ`-Bauwerke haben nur Regel-Schätzungen (`spans_src`).
- **Stichhöhen** der Steinbögen, Geländerhöhen (meist Regelwerk 1,0/1,1/1,3 m) und Überbauhöhen kleiner Brücken sind geschätzt.
- **structurae.net** blockiert automatisierte Abrufe (HTTP 403); Werte von dort nur aus Suchauszügen (z. B. Blaues Wunder 270,2 m, Waldschlößchen-Vorlandfelder 30,38–80,16 m, Augustusbrücke zwei Bögen à 39,3 m). Die Sperre wurde nicht umgangen.
- **Gruppierung**: Wo OSM keine Brückenfläche hat, können parallele, getrennte Bauwerke zusammengefasst (≤ 12 m Abstand) oder ein Bauwerk in mehrere Teile zerlegt sein (Budapester Straße, Löbtauer Brücke). Querungslisten enthalten vereinzelt Wege am Brückenrand.
- `deck_over_ground_m` (aus `bridge_heights.json` minus DGM1-Minimum) ist bei Stadtbrücken ungenau, teils negativ; nur für Talbrücken aussagekräftig.
- Carolabrücke: Verbleib von Widerlagerresten ungeklärt.
- Überwerfungsbauwerk Klotzsche (OSM 525 m durchgehend) ist nicht bestätigt; Coschützer und Richard-Wagner-Straße (B0134/B0142) liegen in Freital.

## 10. Quellen

Daten: © OpenStreetMap-Mitwirkende (ODbL), Geofabrik-Auszug 08.11.2026; GeoSN LoD2/DGM1 (dl-de/by-2-0). Textquellen (Fakten, keine Textübernahme):

- https://de.wikipedia.org/wiki/Lockwitztalbr%C3%BCcke
- https://de.wikipedia.org/wiki/Bundesautobahn_17
- https://www.brueckenweb.de/2content/datenbank/bruecken/3brueckenblatt.php?bas=2464
- https://commons.wikimedia.org/wiki/File:20200918200DR_Dresden-Lockwitz_Lockwitztalbr%C3%BCcke_BAB_A17.jpg
- https://commons.wikimedia.org/wiki/File:Lockwitztalbr%C3%BCcke_B%C3%B6gen.jpg
- https://de.wikipedia.org/wiki/L%C3%B6btauer_Br%C3%BCcke
- https://www.wikidata.org/wiki/Q15119076
- https://de.wikipedia.org/wiki/Waldschlößchenbrücke
- https://www.this-magazin.de/download/425273/this_01_2012_58.pdf
- https://structurae.net/de/bauwerke/waldschloesschenbruecke (Suchauszug: Vorlandfelder 30,38–80,16 m)
- https://de.wikipedia.org/wiki/Bahnstrecke_Dresden-Klotzsche–Dresden_Flughafen
- https://commons.wikimedia.org/wiki/File:20250315.Dresdner_Heide.Railway_line_6607.-014.jpg
- https://de.wikipedia.org/wiki/Elbebr%C3%BCcke_Dresden_(A_4)
- https://deges.de/wp-content/uploads/2019/08/2003-11-Dokumentation-A4_Sachsen.pdf
- https://www.bbsr.bund.de/BBSR/DE/forschung/programme/ao/WohnenBauen/HochVerkehrsbau/Ergebnisse/Verkehrsbauten/DresdenBrueckenfamilie.html
- https://commons.wikimedia.org/wiki/File:20201001100DR_Dresden_Elbe-Autobahnbr%C3%BCcke_A4.jpg
- https://commons.wikimedia.org/wiki/File:20260311.Autobahnbr%C3%BCcke_Dresden.-011.jpg
- https://commons.wikimedia.org/wiki/File:Autobahnbr%C3%BCcke_A4,_Dresden_2019_12.jpg
- https://de.wikipedia.org/wiki/Marienbrücke_(Dresden)
- https://structurae.net/en/structures/marienbrucke-2004
- https://tu-dresden.de/bu/bauingenieurwesen/imb/ressourcen/dateien/veranstaltungen/dbbs/13_DBBS/02_download/13bbs_03.pdf
- https://de.wikipedia.org/wiki/Liste_der_Kulturdenkmale_in_der_Inneren_Neustadt
- https://commons.wikimedia.org/wiki/File:20230601.Marienbrücke-Eisenbahnbrücke.-011.jpg
- https://commons.wikimedia.org/wiki/File:Dresden-Marienbrücke-Radweg.jpg
- https://de.wikipedia.org/wiki/Elbebr%C3%BCcken_Niederwartha
- https://commons.wikimedia.org/wiki/File:20220210.Elbebr%C3%BCcken_Niederwartha.-011.jpg
- https://commons.wikimedia.org/wiki/File:Railway_Bridge,_Niederwartha_-_geo.hlipp.de_-_2148.jpg
- https://de.wikipedia.org/wiki/Nossener_Br%C3%BCcke
- https://www.dresden.de/de/stadtraum/zentrale-projekte/stadtbahnprojekte/campuslinie/nossener-bruecke-und-nuernberger-strasse.php
- https://www.dresden.de/de/stadtraum/zentrale-projekte/stadtbahnprojekte/campuslinie/bautagebuch-nossener-bruecke-nuernberger-strasse.php
- https://www.berliner-zeitung.de/article/dresden-campuslinie-und-nossener-bruecke-bauarbeiten-starten-verkehrseinschraenkungen-ab-12-juni-10072870
- https://de.wikipedia.org/wiki/Augustusbrücke
- https://www.dresden.de/de/stadtraum/zentrale-projekte/augustusbruecke/das-bauwerk.php
- https://www.dresden.de/de/stadtraum/zentrale-projekte/augustusbruecke/sanierung.php
- https://structurae.net/de/bauwerke/augustusbruecke (Suchauszug)
- https://de.wikipedia.org/wiki/Albertbrücke
- https://www.dresden.de/de/rathaus/aktuelles/pressemitteilungen/archiv/2016/08/pm_004.php
- https://www.lap-consult.com/es/proyectos/proyectos/detalles/albertbruecke-ueber-die-elbe-dresden
- https://de.wikipedia.org/wiki/Schlachthofbr%C3%BCcke_(Dresden)
- https://structurae.net/de/bauwerke/schlachthofbruecke-strassenbahn
- https://structurae.net/structures/gebergrund-bridge
- https://commons.wikimedia.org/wiki/File:Talsperre_Kauscha,_Gebergrundbr%C3%BCcke_A17.JPG
- https://commons.wikimedia.org/wiki/File:Gebergrundbr%C3%BCcke_01.jpg
- https://structurae.net/structures/waltherstrasse-bridge
- https://structurae.net/en/literature/conference-paper/aktuelle-erfahrungen-mit-der-einfuhrung-der-din-fachberichte-103-und-104-neubau-der-brucke-im-zuge-der-waltherstrasse-dresden
- https://commons.wikimedia.org/wiki/File:20240217.Waltherstra%C3%9Fenbr%C3%BCcke.-011.jpg
- https://de.wikipedia.org/wiki/Flügelwegbrücke
- https://www.lap-consult.com/es/proyectos/proyectos/detalles/elbebruecke-niederwartha
- https://structurae.net/de/bauwerke/elbebruecke-niederwartha
- https://commons.wikimedia.org/wiki/File:Dresden,_Niederwarthaer_Br%C3%BCcke_%C3%BCber_Elbe,_Stadtteil_Cossebaude-Mobschatz-Oberwartha,_17.6.2.40-120066.jpg
- https://commons.wikimedia.org/wiki/File:20251208.Elbansichten_vom_Radweg_in_Dresden.-011.jpg
- https://de.wikipedia.org/wiki/Blaues_Wunder_(Dresden)
- https://en.wikipedia.org/wiki/Loschwitz_Bridge
- https://www.dresden.de/de/tourismus/sehen/sehenswuerdigkeiten/stadtgebiet/blaues-wunder-und-bergbahnen.php
- https://structurae.net/en/structures/the-blue-miracle (Gesamtlänge 270,2 m, über Suchauszug)
- https://www.volksstimme.de/panorama/dresden-sperrt-blaues-wunder-wahrend-der-herbstferien-4335133 (dpa 08.10.2026)
- https://de.wikipedia.org/wiki/Unionbr%C3%BCcke_(Radebeul)
- https://tu-dresden.de/bu/bauingenieurwesen/imb/ressourcen/dateien/veranstaltungen/dbbs/14_DBBS/02_download/14bbs_11.pdf
- https://commons.wikimedia.org/wiki/File:Radebeul_2022_Unionbr%C3%BCcke_07.jpg
- https://commons.wikimedia.org/wiki/File:Radebeul_2022_Unionbr%C3%BCcke_09.jpg
- https://de.wikipedia.org/wiki/Schwebebahn_Dresden
- https://structurae.net/en/structures/schwebebahn-dresden
- https://www.sachsen-fernsehen.de/amp/dresdner-bergbahnen-starten-in-den-winter-2126814/
- https://commons.wikimedia.org/wiki/File:DD-Veilchenweg-Schwebeseilbahn_20221017_161126.jpg
- https://de.wikipedia.org/wiki/Wei%C3%9Feritztalbr%C3%BCcke
- https://structurae.net/de/bauwerke/talbruecke-weisseritz
- https://commons.wikimedia.org/wiki/File:01189_Dresden,_Wei%C3%9Feritztalbr%C3%BCcke_02_2023-06-11.jpg
- https://commons.wikimedia.org/wiki/File:20220416200DR_Dresden_Wei%C3%9Feritztalbr%C3%BCcke_und_Begerburg.jpg
- https://de.wikipedia.org/wiki/Br%C3%BCcke_Budapester_Stra%C3%9Fe
- https://www.dresden.de/de/rathaus/aktuelles/pressemitteilungen/2026/05/pm_043.php
- https://www.dresden.de/de/rathaus/aktuelles/pressemitteilungen/2026/05/pm_052.php
- https://www.dresden.de/de/rathaus/aktuelles/pressemitteilungen/2026/06/pm_035.php
- https://www.dresden.de/de/rathaus/aktuelles/pressemitteilungen/2026/08/pm_016.php
- https://www.sachsen-fernsehen.de/amp/budapester-strasse-bruecke-ab-montag-wieder-frei-2272956/
- https://de.wikipedia.org/wiki/Molenbr%C3%BCcke_(Dresden)
- https://www.eibs.de/leistungen-projekte/projekt/fussgaenger-und-radwegbruecke-hafen-dresden-pieschen
- https://de.wikipedia.org/wiki/Prie%C3%9Fnitztalviadukt
- https://www.wikidata.org/wiki/Q49457582
- https://de.wikipedia.org/wiki/Hafenbrücke_(Dresden)
- https://structurae.net/de/bauwerke/hafenbruecke-strasse
- https://commons.wikimedia.org/wiki/File:20210518115DR_Dresden-Friedrichstadt_Hafenbrücke_Alberthafen.jpg
- https://commons.wikimedia.org/wiki/File:20250904.Hafenbrücke_(Dresden).-011.jpg
- https://structurae.net/de/bauwerke/hafenbruecke-eisenbahn
- https://de.wikipedia.org/wiki/Standseilbahn_Dresden
- https://structurae.net/de/bauwerke/geruestviadukt-der-standseilbahn-dresden
- https://commons.wikimedia.org/wiki/File:051030-Standseilbahn-Dresden-Talfahrt-Begegnung-Viadukt.jpg
- https://commons.wikimedia.org/wiki/File:Fotothek_df_ps_0003729_x.jpg
- https://de.wikipedia.org/wiki/Nesselgrundviadukt
- https://www.sachsenschiene.net/bahn/kun/kun0490.htm
- https://www.sachsenschiene.net/bahn/kun/kun0491.htm
- https://commons.wikimedia.org/wiki/File:20190612.02.Eisenbahnbrücke_in_Klotzsche.jpg
- https://structurae.net/en/structures/grossenhainer-strasse-railroad-bridge
- https://de.wikipedia.org/wiki/Liste_der_Eisenbahnstrecken_in_Sachsen
- https://de.wikipedia.org/wiki/Hegereiterbr%C3%BCcke
- https://www.wikidata.org/wiki/Q15056587
- https://www.wikidata.org/wiki/Q49458199
- https://commons.wikimedia.org/wiki/Category:Bismarckbr%C3%BCcke_(Dresden)
- https://de.wikipedia.org/wiki/Carolabrücke_(Dresden)
- https://www.dresden.de/de/rathaus/aktuelles/pressemitteilungen/2026/02/pm_033.php
- https://www.dresden.de/de/rathaus/aktuelles/pressemitteilungen/2026/08/pm_041.php
- https://www.n-tv.de/panorama/Dresdner-Stadtrat-entscheidet-sich-fuer-risikoreichsten-Carolabruecken-Entwurf-id31268358.html
- https://structurae.net/structures/muglitztalbrucke
- https://commons.wikimedia.org/wiki/File:A17-m%C3%BCglitztalbr%C3%BCcke-bei-dohna-sommer-2004.jpg
- https://structurae.net/de/bauwerke/noethnitzgrundbruecke
- https://commons.wikimedia.org/wiki/File:20021208100NR_Rosentitz_(Bannewitz)_N%C3%B6thnitzgrundbr%C3%BCcke_der_BAB_17.jpg
- https://commons.wikimedia.org/wiki/File:Dresden,_Steinbacher_Grundstra%C3%9Fe_(unter_Br%C3%BCcke_der_Autobahn_A17),_Stadtteil_Altfranken-Gompitz,_17.6.2.40-130056.jpg
- https://structurae.net/en/structures/zschauke-viaduct
- https://de.wikipedia.org/wiki/Washingtonstra%C3%9Fe
- https://commons.wikimedia.org/wiki/File:20250924.Kaditzer_Flutrinne.-011.jpg
- https://structurae.net/structures/lotzebachtalbrucke
- https://structurae.net/structures/zschauke-viaduct-b-170
- https://de.wikipedia.org/wiki/Bahnhof_Dresden-Neustadt
- https://www.lap-consult.com/es/proyectos/proyectos/detalles/a4-tor-nach-dresden
- https://structurae.net/literature/conference-paper/tor-nach-dresden-entwurf-und-ausfuhrung-eines-uberfuhrungsbauwerkes-im-tiefen-einschnitt
- https://www.dresden.de/de/stadtraum/zentrale-projekte/koenigsbruecker/bruecken-koenigsbruecker.php
- https://www.sachsen-fernsehen.de/amp/naechste-dresdner-spannbetonbruecke-muss-abgerissen-werden-2088364/
- https://www.deutschebahn.com/de/presse/presse-regional/pr-leipzig-de/aktuell/presseinformationen/Noch-mal-3000-Tonnen-Beton-Meilenstein-beim-neuen-Kreuzungsbauwerk-in-Dresden-14063458
- https://tu-dresden.de/bu/verkehr/ibv/schienenfahrwege/die-professur/news/besichtigung-kreuzungsbauwerk-dresden-hbf
- https://de.wikipedia.org/wiki/Dresden_Hauptbahnhof
- https://commons.wikimedia.org/wiki/File:Haltepunkt_Dresden-Bischofsplatz,_Blick_zur_Straßenbahnhaltestelle_Bischofsplatz_(1).jpg
- https://www.dresden.de/media/pdf/umwelt/ub_05_06_Anlage2.pdf
- https://www.dresden.de/media/pdf/umwelt/Fachbericht_2022_20_Jahre_nach_der-Flut.pdf
- https://de.wikipedia.org/wiki/Bahnstrecke_Dresden–Werdau
- https://www.sachsenschiene.net/bahn/kun/kun0326.htm
- https://www.wikidata.org/wiki/Q110906994
- https://commons.wikimedia.org/wiki/File:Felsenkeller-DD3.jpg
- https://www.sachsenschiene.net/bahn/kun/kun0294.htm
- https://www.wikidata.org/wiki/Q110906663
- https://commons.wikimedia.org/wiki/File:20190225110DR_Dresden-Coschütz_Heidenschanze_Pulvermühle_Bahnbrücke.jpg
- https://www.sachsenschiene.net/bahn/kun/kun0328.htm
- https://www.wikidata.org/wiki/Q130384746
- https://www.sachsenschiene.net/bahn/kun/kun0327.htm
- https://www.wikidata.org/wiki/Q130384756
- https://de.wikipedia.org/wiki/Liste_der_Kulturdenkmale_in_der_Leipziger_Vorstadt_(A–H)
- https://www.wikidata.org/wiki/Q49458085
- https://commons.wikimedia.org/wiki/File:Eisenbahnstraße_Eisenbahnbrücke.JPG
- https://www.wikidata.org/wiki/Q130375375
- https://www.dresden.de/de/stadtraum/zentrale-projekte/hamburger-strasse.php
- https://www.wikidata.org/wiki/Q130375771
- https://commons.wikimedia.org/wiki/Category:Landw%C3%A4rtige_Wei%C3%9Feritzbr%C3%BCcke_Freiberger_Stra%C3%9Fe_(Dresden)
- https://www.wikidata.org/wiki/Q130375856
- https://de.wikipedia.org/wiki/Fr%C3%B6belstra%C3%9Fe_(Dresden)
- https://de.wikipedia.org/wiki/Wallgrabenbr%C3%BCcke
- https://www.wikidata.org/wiki/Q87587759
- https://de.wikipedia.org/wiki/Mordgrundbr%C3%BCcke
- https://www.wikidata.org/wiki/Q106253694
- https://commons.wikimedia.org/wiki/File:Leipziger_Straße_Dresden_Eisenbahnbrücke_und_Bahndammbefestigung.JPG
- https://www.wikidata.org/wiki/Q130376114
- https://www.wikidata.org/wiki/Q130375784
- https://www.wikidata.org/wiki/Q130370555
- https://de.wikipedia.org/wiki/Bahnstrecke_Freital_Ost–Possendorf
- https://www.wikidata.org/wiki/Q131451123
- https://commons.wikimedia.org/wiki/File:DD-Brücke-KarlsruherStr.jpg

Nicht verwendet: Google Maps/Earth/Street View/3D Tiles, Apple Look Around.

## 11. Bild- und Lizenzliste (nur Analyse, nicht für Spieltexturen)

| Datei | Commons-Seite | Urheber | Lizenz | Datum |
|---|---|---|---|---|
| a17_geber_1.JPG | [Talsperre Kauscha, Gebergrundbrücke A17.JPG](https://commons.wikimedia.org/wiki/File:Talsperre_Kauscha,_Gebergrundbr%C3%BCcke_A17.JPG) | Derbrauni | CC BY-SA 3.0 | 2012-08-10 16:35:37 |
| a17_geber_2.jpg | [Gebergrundbrücke 01.jpg](https://commons.wikimedia.org/wiki/File:Gebergrundbr%C3%BCcke_01.jpg) | Derbrauni | CC BY-SA 4.0 | 2021-02-28 12:03:10 |
| a17_lockwitz_1.jpg | [20200918200DR Dresden-Lockwitz Lockwitztalbrücke BAB A17.jpg](https://commons.wikimedia.org/wiki/File:20200918200DR_Dresden-Lockwitz_Lockwitztalbr%C3%BCcke_BAB_A17.jpg) | Jörg Blobelt | CC BY-SA 4.0 | 2020-09-18 12:04:06 |
| a17_lockwitz_2.jpg | [Lockwitztalbrücke Bögen.jpg](https://commons.wikimedia.org/wiki/File:Lockwitztalbr%C3%BCcke_B%C3%B6gen.jpg) | ProfessorX | CC BY-SA 3.0 | 2005-10-23 |
| a17_mueglitz_1.jpg | [A17-müglitztalbrücke-bei-dohna-sommer-2004.jpg](https://commons.wikimedia.org/wiki/File:A17-m%C3%BCglitztalbr%C3%BCcke-bei-dohna-sommer-2004.jpg) | kreidefossilien.de | CC BY-SA 3.0 | 2004 |
| a17_noethnitz_1.jpg | [20021208100NR Rosentitz (Bannewitz) Nöthnitzgrundbrücke der BAB 1](https://commons.wikimedia.org/wiki/File:20021208100NR_Rosentitz_(Bannewitz)_N%C3%B6thnitzgrundbr%C3%BCcke_der_BAB_17.jpg) | Jörg Blobelt | CC BY-SA 4.0 | 2002-12-08 |
| a17_weisseritz_1.jpg | [01189 Dresden, Weißeritztalbrücke 02 2023-06-11.jpg](https://commons.wikimedia.org/wiki/File:01189_Dresden,_Wei%C3%9Feritztalbr%C3%BCcke_02_2023-06-11.jpg) | Hangman'sDeath | CC0 | 2023-06-11 20:51:56 |
| a17_weisseritz_2.jpg | [20220416200DR Dresden Weißeritztalbrücke und Begerburg.jpg](https://commons.wikimedia.org/wiki/File:20220416200DR_Dresden_Wei%C3%9Feritztalbr%C3%BCcke_und_Begerburg.jpg) | Jörg Blobelt | CC BY-SA 4.0 | 2022-04-16 14:56:29 |
| a17_zschoner_1.jpg | [Dresden, Steinbacher Grundstraße (unter Brücke der Autobahn A17),](https://commons.wikimedia.org/wiki/File:Dresden,_Steinbacher_Grundstra%C3%9Fe_(unter_Br%C3%BCcke_der_Autobahn_A17),_Stadtteil_Altfranken-Gompitz,_17.6.2.40-130056.jpg) | Albrecht Voß | CC BY-SA 4.0 | 12 October 2024 |
| a4_elbe_1.jpg | [20201001100DR Dresden Elbe-Autobahnbrücke A4.jpg](https://commons.wikimedia.org/wiki/File:20201001100DR_Dresden_Elbe-Autobahnbr%C3%BCcke_A4.jpg) | Jörg Blobelt | CC BY-SA 4.0 | 2020-10-01 13:18:05 |
| a4_elbe_2.jpg | [20260311.Autobahnbrücke Dresden.-011.jpg](https://commons.wikimedia.org/wiki/File:20260311.Autobahnbr%C3%BCcke_Dresden.-011.jpg) | Bybbisch94 | CC BY-SA 4.0 | 2026-03-11 14:37:28 |
| a4_elbe_3.jpg | [Autobahnbrücke A4, Dresden 2019 12.jpg](https://commons.wikimedia.org/wiki/File:Autobahnbr%C3%BCcke_A4,_Dresden_2019_12.jpg) | Hgzh | CC BY-SA 4.0 | 2019-03-01 14:38:05 |
| a4_flutrinne_1.jpg | [20250924.Kaditzer Flutrinne.-011.jpg](https://commons.wikimedia.org/wiki/File:20250924.Kaditzer_Flutrinne.-011.jpg) | Bybbisch94 | CC BY-SA 4.0 | 2025-09-24 15:13:02 |
| a4_union_1.jpg | [Radebeul 2022 Unionbrücke 07.jpg](https://commons.wikimedia.org/wiki/File:Radebeul_2022_Unionbr%C3%BCcke_07.jpg) | Jbergner | CC BY-SA 4.0 | 2022-04-03 13:27:49 |
| a4_union_2.jpg | [Radebeul 2022 Unionbrücke 09.jpg](https://commons.wikimedia.org/wiki/File:Radebeul_2022_Unionbr%C3%BCcke_09.jpg) | Jbergner | CC BY-SA 4.0 | 2022-04-03 13:29:52 |
| albert_1.jpg | [20241017.Albertbrücke.Dresden.-01.jpg](https://commons.wikimedia.org/wiki/File:20241017.Albertbr%C3%BCcke.Dresden.-01.jpg) | Bybbisch94 | CC BY 4.0 | 2024-10-17 12:20:37 |
| albert_2.jpg | [20251106.Albertbrücke.Dresden.-012.jpg](https://commons.wikimedia.org/wiki/File:20251106.Albertbr%C3%BCcke.Dresden.-012.jpg) | Bybbisch94 | CC BY-SA 4.0 | 2025-11-06 13:19:07 |
| albert_3.jpg | [20251104.Albertbrücke.Dresden.-011.jpg](https://commons.wikimedia.org/wiki/File:20251104.Albertbr%C3%BCcke.Dresden.-011.jpg) | Bybbisch94 | CC BY-SA 4.0 | 2025-11-04 16:53:25 |
| augustus_1.jpg | [20230720.Dresden Augustusbrücke.-01.jpg](https://commons.wikimedia.org/wiki/File:20230720.Dresden_Augustusbr%C3%BCcke.-01.jpg) | Bybbisch94, Christian Gebhardt | CC BY-SA 4.0 | 2023-07-20 19:19:04 |
| augustus_2.jpg | [20231213.Augustusbrücke.-011.jpg](https://commons.wikimedia.org/wiki/File:20231213.Augustusbr%C3%BCcke.-011.jpg) | Bybbisch94 | CC BY 4.0 | 2023-12-13 17:05:26 |
| augustus_3.jpg | [Dresden, Elbe und Augustusbrücke -- 2023 -- 112746.jpg](https://commons.wikimedia.org/wiki/File:Dresden,_Elbe_und_Augustusbr%C3%BCcke_--_2023_--_112746.jpg) | Dietmar Rabich | CC BY-SA 4.0 | Taken on 3 December |
| augustus_4.jpg | [2022121401 Bewegungsunscharfe Strassenbahn und Passanten Augustus](https://commons.wikimedia.org/wiki/File:2022121401_Bewegungsunscharfe_Strassenbahn_und_Passanten_Augustusbruecke_2022.jpg) | VSchagow | CC BY-SA 4.0 | 2022-12-14 11:49:23 |
| bismarck_1.jpg | [20141102190DR Dresden-Löbtau Weißeritz Bismarck-Brücke.jpg](https://commons.wikimedia.org/wiki/File:20141102190DR_Dresden-L%C3%B6btau_Wei%C3%9Feritz_Bismarck-Br%C3%BCcke.jpg) | Jörg Blobelt | CC BY-SA 4.0 | 2014-11-02 12:19:11 |
| blaueswunder_1.jpg | [20250226.Dresden.Blaues Wunder.-011.1.jpg](https://commons.wikimedia.org/wiki/File:20250226.Dresden.Blaues_Wunder.-011.1.jpg) | Bybbisch94 | CC BY-SA 4.0 | 2025-02-26 12:32:46 |
| blaueswunder_2.jpg | [20240408.Dresden.Blaues Wunder.-013.jpg](https://commons.wikimedia.org/wiki/File:20240408.Dresden.Blaues_Wunder.-013.jpg) | Bybbisch94 | CC BY 4.0 | 2024-04-08 11:58:23 |
| blaueswunder_3.jpg | [20250226.Dresden.Blaues Wunder.-016.jpg](https://commons.wikimedia.org/wiki/File:20250226.Dresden.Blaues_Wunder.-016.jpg) | Bybbisch94 | CC BY-SA 4.0 | 2025-02-26 12:36:15 |
| budapester_1.jpg | [Brücke Budapester Straße 2.jpg](https://commons.wikimedia.org/wiki/File:Br%C3%BCcke_Budapester_Stra%C3%9Fe_2.jpg) | Derbrauni | CC BY-SA 4.0 | 2018-03-18 14:51:43 |
| eue_bischofsplatz_1.jpg | [Haltepunkt Dresden-Bischofsplatz, Blick zur Straßenbahnhaltestell](https://commons.wikimedia.org/wiki/File:Haltepunkt_Dresden-Bischofsplatz,_Blick_zur_Stra%C3%9Fenbahnhaltestelle_Bischofsplatz_(1).jpg) | Aagnverglaser | CC BY-SA 4.0 | 2025-09-28 14:43:17 |
| eue_eisenbahnstr_1.JPG | [Eisenbahnstraße Eisenbahnbrücke.JPG](https://commons.wikimedia.org/wiki/File:Eisenbahnstra%C3%9Fe_Eisenbahnbr%C3%BCcke.JPG) | Paulae | CC BY-SA 3.0 | 2012-09-13 17:24:37 |
| eue_leipziger_1.JPG | [Leipziger Straße Dresden Eisenbahnbrücke und Bahndammbefestigung.](https://commons.wikimedia.org/wiki/File:Leipziger_Stra%C3%9Fe_Dresden_Eisenbahnbr%C3%BCcke_und_Bahndammbefestigung.JPG) | Paulae | CC BY-SA 3.0 | 2012-09-26 16:41:21 |
| eue_schubert_1.jpg | [Andreas-Schubert-Straße Dresden 2020-04 Richtung Süd.jpg](https://commons.wikimedia.org/wiki/File:Andreas-Schubert-Stra%C3%9Fe_Dresden_2020-04_Richtung_S%C3%BCd.jpg) | Hgzh | CC BY-SA 4.0 | 2020-04-03 11:09:11 |
| fluegelweg_1.jpg | [20250904.Dresden.Flügelwegbrücke.-011.jpg](https://commons.wikimedia.org/wiki/File:20250904.Dresden.Fl%C3%BCgelwegbr%C3%BCcke.-011.jpg) | Bybbisch94 | CC BY-SA 4.0 | 2025-09-04 10:28:46 |
| fluegelweg_2.jpg | [2022-06-18 Flügelwegbrücke 02.jpg](https://commons.wikimedia.org/wiki/File:2022-06-18_Fl%C3%BCgelwegbr%C3%BCcke_02.jpg) | Stefan Kühn | CC0 | 2022-06-18 18:09:42 |
| fluegelweg_3.jpg | [20250502.Brücken in Dresden.Flügelwegbrücke .-012.jpg](https://commons.wikimedia.org/wiki/File:20250502.Br%C3%BCcken_in_Dresden.Fl%C3%BCgelwegbr%C3%BCcke_.-012.jpg) | Bybbisch94 | CC BY-SA 4.0 | 2025-05-02 15:27:57 |
| flughafen_sbahn_1.jpg | [20250315.Dresdner Heide.Railway line 6607.-014.jpg](https://commons.wikimedia.org/wiki/File:20250315.Dresdner_Heide.Railway_line_6607.-014.jpg) | Bybbisch94 | CC BY-SA 4.0 | 2025-03-15 14:47:31 |
| hafen_bahn_1.jpg | [20210518115DR Dresden-Friedrichstadt Hafenbrücke Alberthafen.jpg](https://commons.wikimedia.org/wiki/File:20210518115DR_Dresden-Friedrichstadt_Hafenbr%C3%BCcke_Alberthafen.jpg) | Jörg Blobelt | CC BY-SA 4.0 | 2021-05-18 13:49:33 |
| hafen_bahn_2.jpg | [20250904.Hafenbrücke (Dresden).-011.jpg](https://commons.wikimedia.org/wiki/File:20250904.Hafenbr%C3%BCcke_(Dresden).-011.jpg) | Bybbisch94 | CC BY 4.0 | 2025-09-04 17:47:00 |
| hegereiter_1.jpg | [Hegereiterbrücke.jpg](https://commons.wikimedia.org/wiki/File:Hegereiterbr%C3%BCcke.jpg) | SchiDD | CC BY-SA 3.0 | 2012-02-16 |
| hofmuehlen_1.jpg | [20080215210DR Dresden-Plauen-Löbtau Hofmühlenbrücke.jpg](https://commons.wikimedia.org/wiki/File:20080215210DR_Dresden-Plauen-L%C3%B6btau_Hofm%C3%BChlenbr%C3%BCcke.jpg) | Jörg Blobelt | CC BY-SA 4.0 | 2008-02-15 |
| koenigsbr_1.jpg | [20240919.Königsbrücker Straße.Brücke Industriegelände.-011.jpg](https://commons.wikimedia.org/wiki/File:20240919.K%C3%B6nigsbr%C3%BCcker_Stra%C3%9Fe.Br%C3%BCcke_Industriegel%C3%A4nde.-011.jpg) | Bybbisch94 | CC BY 4.0 | 2024-09-19 12:18:49 |
| loebtauer_1.JPG | [Löbtauer Brücke, Dresden 02.JPG](https://commons.wikimedia.org/wiki/File:L%C3%B6btauer_Br%C3%BCcke,_Dresden_02.JPG) | Ubahnverleih | CC BY 3.0 | 2013-10-20 14:34:07 |
| marien_bahn_1.jpg | [20230601.Marienbrücke-Eisenbahnbrücke.-011.jpg](https://commons.wikimedia.org/wiki/File:20230601.Marienbr%C3%BCcke-Eisenbahnbr%C3%BCcke.-011.jpg) | Bybbisch94, Christian Gebhardt | CC BY-SA 4.0 | 2023-06-01 17:23:25 |
| marien_bahn_2.jpg | [20230601.Marienbrücke-Eisenbahnbrücke.-014.jpg](https://commons.wikimedia.org/wiki/File:20230601.Marienbr%C3%BCcke-Eisenbahnbr%C3%BCcke.-014.jpg) | Bybbisch94, Christian Gebhardt | CC BY-SA 4.0 | 2023-06-01 17:28:15 |
| marien_bahn_3.jpg | [Dresden-Marienbrücke-Radweg.jpg](https://commons.wikimedia.org/wiki/File:Dresden-Marienbr%C3%BCcke-Radweg.jpg) | User:Kolossos | CC BY-SA 3.0 | 2010-10-10 04:01:21 |
| marien_str_1.jpg | [20260520.Marienbrücke (Dresden).-012.jpg](https://commons.wikimedia.org/wiki/File:20260520.Marienbr%C3%BCcke_(Dresden).-012.jpg) | Bybbisch94 | CC BY-SA 4.0 | 2026-05-20 18:01:28 |
| marien_str_2.jpg | [20250904.Marienbrücke (Dresden).-012.jpg](https://commons.wikimedia.org/wiki/File:20250904.Marienbr%C3%BCcke_(Dresden).-012.jpg) | Bybbisch94 | CC BY 4.0 | 2025-09-04 10:07:59 |
| marien_str_3.jpg | [20251208.Marienbrücke.-011.jpg](https://commons.wikimedia.org/wiki/File:20251208.Marienbr%C3%BCcke.-011.jpg) | Bybbisch94 | CC BY-SA 4.0 | 2025-12-08 15:12:03 |
| molen_1.JPG | [Molenbruecke Dresden5.JPG](https://commons.wikimedia.org/wiki/File:Molenbruecke_Dresden5.JPG) | Derbrauni | CC BY-SA 3.0 | 2010-09-10 |
| nesselgrund_1.jpg | [20190612.02.Eisenbahnbrücke in Klotzsche.jpg](https://commons.wikimedia.org/wiki/File:20190612.02.Eisenbahnbr%C3%BCcke_in_Klotzsche.jpg) | Bybbisch94, Christian Gebhardt | CC BY-SA 4.0 | 2019-06-12 13:57:48 |
| nossener_1.jpg | [20220925.Dresden.Nossener Brücke.-011.jpg](https://commons.wikimedia.org/wiki/File:20220925.Dresden.Nossener_Br%C3%BCcke.-011.jpg) | Bybbisch94, Christian Gebhardt | CC BY-SA 4.0 | 2022-09-25 18:45:48 |
| nossener_2.jpg | [Nossener Brücke, Überführung Fabrikstraße, Südseite.jpg](https://commons.wikimedia.org/wiki/File:Nossener_Br%C3%BCcke,_%C3%9Cberf%C3%BChrung_Fabrikstra%C3%9Fe,_S%C3%BCdseite.jpg) | Hgzh | CC BY-SA 4.0 | 2018-02-02 14:47:28 |
| nw_bahn_1.jpg | [Railway Bridge, Niederwartha - geo.hlipp.de - 2148.jpg](https://commons.wikimedia.org/wiki/File:Railway_Bridge,_Niederwartha_-_geo.hlipp.de_-_2148.jpg) | Bill Johnson on geo.hlipp.de | CC BY-SA 2.0 | Taken on 4 May 2008 |
| nw_bruecken_1.jpg | [20220210.Elbebrücken Niederwartha.-011.jpg](https://commons.wikimedia.org/wiki/File:20220210.Elbebr%C3%BCcken_Niederwartha.-011.jpg) | Bybbisch94, Christian Gebhardt | CC BY-SA 4.0 | 2022-02-10 12:17:33 |
| nw_bruecken_2.jpg | [20251208.Elbansichten vom Radweg in Dresden.-011.jpg](https://commons.wikimedia.org/wiki/File:20251208.Elbansichten_vom_Radweg_in_Dresden.-011.jpg) | Bybbisch94 | CC BY-SA 4.0 | 2025-12-08 14:14:35 |
| nw_strasse_1.jpg | [Dresden, Niederwarthaer Brücke über Elbe, Stadtteil Cossebaude-Mo](https://commons.wikimedia.org/wiki/File:Dresden,_Niederwarthaer_Br%C3%BCcke_%C3%BCber_Elbe,_Stadtteil_Cossebaude-Mobschatz-Oberwartha,_17.6.2.40-120066.jpg) | Albrecht Voß | CC BY-SA 4.0 | 7 October 2024 |
| priessnitz_1.JPG | [Stauffenbergallee Dresden Viadukt über die Prießnitz mit Sandstei](https://commons.wikimedia.org/wiki/File:Stauffenbergallee_Dresden_Viadukt_%C3%BCber_die_Prie%C3%9Fnitz_mit_Sandsteinb%C3%B6gen.JPG) | Paulae | CC BY-SA 3.0 | 2012-09-15 13:40:58 |
| schlachthof_1.JPG | [Schlachthofbrücke Dresden 2.JPG](https://commons.wikimedia.org/wiki/File:Schlachthofbr%C3%BCcke_Dresden_2.JPG) | Brücke-Osteuropa | CC0 | 2012-03-20 |
| schwebebahn_1.jpg | [DD-Veilchenweg-Schwebeseilbahn 20221017 161126.jpg](https://commons.wikimedia.org/wiki/File:DD-Veilchenweg-Schwebeseilbahn_20221017_161126.jpg) | Rigorius | CC BY-SA 4.0 | 2022-10-17 16:11:26 |
| standseilbahn_viadukt_1.jpg | [051030-Standseilbahn-Dresden-Talfahrt-Begegnung-Viadukt.jpg](https://commons.wikimedia.org/wiki/File:051030-Standseilbahn-Dresden-Talfahrt-Begegnung-Viadukt.jpg) | Martin Röll Martinroell | CC BY-SA 2.0 de | 2005-10-30 |
| standseilbahn_viadukt_2.jpg | [Fotothek df ps 0003729 x.jpg](https://commons.wikimedia.org/wiki/File:Fotothek_df_ps_0003729_x.jpg) | Richard Peter | CC BY-SA 3.0 de | circa 1960date QS:P |
| waldschloesschen_1.jpg | [20260210.Waldschlößchenbrücke.-01.jpg](https://commons.wikimedia.org/wiki/File:20260210.Waldschl%C3%B6%C3%9Fchenbr%C3%BCcke.-01.jpg) | Bybbisch94 | CC BY-SA 4.0 | 2026-02-10 12:44:37 |
| waldschloesschen_2.jpg | [20230517.Dresdner Elbwiesen.-028.jpg](https://commons.wikimedia.org/wiki/File:20230517.Dresdner_Elbwiesen.-028.jpg) | Bybbisch94; Christian Gebhardt | CC BY-SA 4.0 | 2023-05-17 20:09:36 |
| waldschloesschen_3.jpg | [20211001.Dresden.Waldschlößchenbrücke.-012.jpg](https://commons.wikimedia.org/wiki/File:20211001.Dresden.Waldschl%C3%B6%C3%9Fchenbr%C3%BCcke.-012.jpg) | Bybbisch94, Christian Gebhardt | CC BY-SA 4.0 | 2021-10-01 14:27:40 |
| wallgraben_1.jpg | [Wallgrabenbrücke 32.jpg](https://commons.wikimedia.org/wiki/File:Wallgrabenbr%C3%BCcke_32.jpg) | Derbrauni | CC BY-SA 4.0 | 2021-06-01 17:19:36 |
| waltherstr_1.jpg | [20240217.Waltherstraßenbrücke.-011.jpg](https://commons.wikimedia.org/wiki/File:20240217.Waltherstra%C3%9Fenbr%C3%BCcke.-011.jpg) | Bybbisch94 | CC BY 4.0 | 2024-02-17 12:45:13 |
| weisseritz_bahn_1.jpg | [Felsenkeller-DD3.jpg](https://commons.wikimedia.org/wiki/File:Felsenkeller-DD3.jpg) | SchiDD | CC BY-SA 3.0 | 2014-02-25 14:05:25 |
| weisseritz_bahn_2.jpg | [20190225110DR Dresden-Coschütz Heidenschanze Pulvermühle Bahnbrüc](https://commons.wikimedia.org/wiki/File:20190225110DR_Dresden-Cosch%C3%BCtz_Heidenschanze_Pulverm%C3%BChle_Bahnbr%C3%BCcke.jpg) | Jörg Blobelt | CC BY-SA 4.0 | 2019-02-25 12:42:29 |
| windberg_1.jpg | [DD-Brücke-KarlsruherStr.jpg](https://commons.wikimedia.org/wiki/File:DD-Br%C3%BCcke-KarlsruherStr.jpg) | SchiDD | CC BY-SA 4.0 | 2019-04-25 11:05:42 |
| wuerzburger_1.jpg | [20240430.Weißeritz in Dresden.-018.3.jpg](https://commons.wikimedia.org/wiki/File:20240430.Wei%C3%9Feritz_in_Dresden.-018.3.jpg) | Bybbisch94 | CC BY 4.0 | 2024-04-30 10:58:35 |

