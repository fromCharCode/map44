# DVB-Straßenbahnen: maßgenaue Beschreibung für den prozeduralen Nachbau in Blender

Stand: 2026-11-12. Recherche ohne Google Maps/Earth/Street View/3D-Tiles/Look Around.
Analysebilder, Quellen und Lizenzen: `data/research/dvb_tram_img/` (Liste in `QUELLEN.txt`). Nichts davon ins Spiel übernehmen.

## 0. Korrekturen zur Aufgabenstellung (wichtig)

1. **Der NGT DX DD ist kein Škoda ForCity Smart 37T.** Er stammt von **Alstom (vormals Bombardier)**, Typ *Flexity Citytram Low-Floor* (Alstom führt ihn heute auch als *Citadis Classic*). Gebaut wurde er in Görlitz und Bautzen, das Design stammt von büro+staubach. In Dresden fährt kein Škoda-Wagen (Stand der Quellen).
2. **2,65 m Breite gelten nur für den NGT DX DD.** Alle älteren Dresdner Niederflurwagen sind **2,30 m** breit: NGT D12DD, NGT D8DD, NGT8DD und NGT6DD. Der DX DD ist im Fußbodenbereich auf 2,30 m eingezogen, damit er an die alten Bahnsteige passt.
3. **Der NGT D8DD hat keine 41-m-Variante.** Er ist immer 30,04 m lang. 41,02 m lang ist der **NGT8DD** (7-teilig, Bombardier/DWA Bautzen, 2001–2002). Der eigentliche 1990er-Typ ist der **NGT6DD** (29,72 m, DWA Bautzen, 1995–1998).
4. Neue Lackierung: Seit Ende Oktober 2025 (D12DD) bzw. Mitte November 2025 (D8DD) entfernt die DVB bei den Hauptuntersuchungen die **schwarzen Farbbänder** an den Seiten. Neues Design haben bereits die D12DD 2815, 2816, 2818, 2819, 2821–2823, 2826, 2838–2842 und die D8DD 2637, 2638, 2640 (Quelle: de.wikipedia).

**Genauigkeitslegende** (gilt für das ganze Dokument):
- **[Q]**: Herstellerangabe, DVB oder Wikipedia.
- **[Z]**: aus einer maßstäblichen Zeichnung gemessen, ±0,05 m.
- **[F]**: aus Fotos gemessen, ±0,1–0,3 m.
- **[S]**: geschätzt.

**Koordinatensystem für alle Tabellen:**
- x = Abstand ab der Bugspitze (Front-Mitte, vorderste Kante Puffer/Kupplungsabdeckung) **nach hinten positiv**, in m.
- y = quer zur Fahrzeugachse, **+ = rechte Seite in Fahrtrichtung = Türseite**, in m.
- z = Höhe über Schienenoberkante (SO), in m.

Alle Typen sind **Einrichtungswagen (ER)**: Fahrgasttüren nur rechts, links eine durchgehende Fensterseite. Ausnahme sind die 9 Zweirichtungswagen NGT DX DD 2981–2989. Die ER-Wagen haben **hinten einen Hilfsführerstand** in einem **vollständigen zweiten Kopf** mit derselben Kopfform, Frontscheibe und Zielanzeige. Eine Fahrerraumtür gibt es nur vorne rechts.

---

## 1. NGT D12DD (Bombardier Flexity Classic XXL), 43 Wagen 2801–2843

### 1.1 Eckdaten
| Größe | Wert | Güte |
|---|---|---|
| Länge über Kupplung | 45,09 m | [Q] |
| Wagenkastenbreite | 2,30 m | [Q] |
| Höhe (max., Dachgeräte, Stromabnehmer gesenkt nicht eingerechnet) | 3,50 m | [Q] |
| Höhe Dachverkleidung (gelb) | ≈ 3,42 m | [F] |
| Höhe mit gesenktem Stromabnehmer | ≈ 3,75–3,80 m | [S] |
| Arbeitshöhe Stromabnehmer (Fahrdraht) | ≈ 5,5–6,0 m (Dresden typisch) | [S] |
| Fußboden | Einstieg ≈ 0,30 m; Niederflur ≈ 0,35–0,37 m; über Triebdrehgestellen ≈ 0,585 m (Werte des baugleichen Leipziger Typs 38: 295 / 365–585 mm) | [Q, Leipzig] |
| Module | 5: Endmodul A (4-achsig), Sänfte, Mittelmodul (4-achsig), Sänfte, Endmodul B (4-achsig) | [Q] |
| Fahrwerke | 6 Drehgestelle: je 2 **Triebdrehgestelle** unter Modul 1 und 5, 2 **Laufdrehgestelle** unter Modul 3. Die Sänften (2, 4) haben kein Fahrwerk. Achsformel Bo'Bo'+2'2'+Bo'Bo' | [Q] |
| Drehzapfenabstände | 5,50 / 10,325 / 5,50 / 10,325 / 5,50 m (Leipziger Zwilling Typ 38, gleiche Länge 45,09 m) | [Q] |
| Raddurchmesser | 600 mm neu (Leipzig) | [Q] |
| Achsstand im Drehgestell | ≈ 1,80 m | [S] |
| Türen | 5 elektromechanische Doppel-Außenschwenkschiebetüren rechts, eine je Modul, dazu 1 einflügelige Fahrerraumtür vorne rechts | [Q]/[F] |
| Masse | 55,4 t (DVB) bzw. 56,7 t (Wikipedia) | [Q] |

### 1.2 Module, Gelenke, Drehgestelle (x ab Bug)
Abgeleitet aus Gesamtlänge und Drehzapfenabständen [Q] (symmetrisch angenommen), den Proportionen der Wikipedia-Seitenskizze und einem perspektivisch entzerrten Foto (2829) [F]. **Toleranz der Modulgrenzen ±0,3 m.**

| Teil | x von | x bis | Länge | Bemerkung |
|---|---|---|---|---|
| M1 Endmodul A (Kopf, Führerstand) | 0,00 | 11,80 | 11,80 | Drehgestelle B1 3,97 und B2 9,47 (Trieb) |
| Gelenk 1 (Faltenbalg) | 11,80 | 12,22 | 0,42 | |
| M2 Sänfte | 12,22 | 17,42 | 5,20 | kein Fahrwerk |
| Gelenk 2 | 17,42 | 17,84 | 0,42 | |
| M3 Mittelmodul | 17,84 | 27,24 | 9,40 | B3 19,80 und B4 25,30 (Lauf) |
| Gelenk 3 | 27,24 | 27,66 | 0,42 | |
| M4 Sänfte | 27,66 | 32,86 | 5,20 | |
| Gelenk 4 | 32,86 | 33,28 | 0,42 | |
| M5 Endmodul B (Heckkopf, Hilfsführerstand) | 33,28 | 45,09 | 11,81 | B5 35,62 und B6 41,12 (Trieb) |

Achsen: Drehgestellmitte ±0,90 m [S]. Gelenkmitten: 12,01 / 17,63 / 27,45 / 33,07.
Die Faltenbälge sind schwarz, senkrecht gerippt und leicht eingezogen. Die angrenzenden Modulenden sind senkrecht abgerundet (Radius ≈ 0,15 m) [F].

### 1.3 Türen (rechte Seite)
| Tür | x von | x bis | Mitte | Güte |
|---|---|---|---|---|
| Fahrerraumtür (einflügelig) | 1,05 | 1,75 | 1,40 | [F] aus orthogonalem Foto 2827 |
| T1 (M1) | 5,55 | 7,15 | 6,35 | [F] ±0,3 |
| T2 (M2, ca. 0,3 m zur Front versetzt) | 13,75 | 15,35 | 14,55 | [F/S] ±0,4 |
| T3 (M3, genau Fahrzeugmitte) | 21,74 | 23,34 | 22,54 | [F] |
| T4 (M4, wie T2 nach vorn versetzt) | 29,19 | 30,79 | 29,99 | [F/S] ±0,4 |
| T5 (M5, spiegelbildlich zu T1) | 37,94 | 39,54 | 38,74 | [S] ±0,4 |

- **Portal**: Außenmaß ≈ 1,60 m breit, lichte Weite ≈ 1,30 m [S]. Portal z ≈ 0,30–2,65 m [F]. Fahrerraumtür z ≈ 0,38–2,52 m.
- **Türblätter**: Sie sind **gelb in Wagenkastenfarbe** und schwarz umrandet. Die Blätter sind gerade, im Gegensatz zu Leipzig ohne Knick. Jedes Blatt hat **ein hohes Fenster in Stadionform** (oben und unten halbrund), ≈ 0,50 m breit und 1,5–1,75 m hoch, Lage z ≈ 0,65–2,40 [F]. Das Glas ist dunkel getönt. Fensteranteil der Tür ≈ 40–45 %. Taster sitzen an den Blattkanten auf z ≈ 1,1 m.
- **Fahrerraumtür**: oben ein dunkles Fenster (z ≈ 1,25–2,45), unten ein gelbes Feld mit dem Wagennummernschild.

### 1.4 Fensterband
- **Altes Design** (noch die Mehrheit der Wagen): Das gesamte Fensterband ist **schwarz** lackiert und reicht über die Fensterzwischenräume hinweg, Höhe z ≈ 1,25–2,60 [F]. Es wird nur von den gelben Türen unterbrochen. Glas z ≈ 1,29–2,56, dunkel grau-grün getönt. Jede Scheibe hat oben einen ≈ 0,3 m hohen Kippflügel mit horizontaler Teilfuge bei z ≈ 2,25.
- **Neues Design** (ab 10/2025): Das schwarze Band wird entfernt. Dann bleiben vermutlich einzeln schwarz gerahmte Fenster im gelben Kasten stehen. Das ist **auf Fotos nicht verifiziert**, weil das einzige gefundene Foto eines umlackierten Wagens Vollwerbung trägt.
- Scheibenteilung rechts (x der Glasflächen, [F/S] ±0,3). Die Holme dazwischen sind ≈ 0,15–0,20 m breit und schwarz:
  - M1: schmales schwarzes Feld 1,75–2,10 | 2,15–3,55 | 3,75–5,30 | T1 | 7,35–9,45 | 9,60–11,65
  - M2: 12,32–13,65 | T2 | 15,45–17,32
  - M3: 17,95–19,75 | 19,85–21,65 | T3 | 23,43–25,23 | 25,33–27,13
  - M4: 27,76–29,09 | T4 | 30,89–32,76
  - M5: 33,43–35,48 | 35,63–37,74 | T5 | 39,79–41,34 | 41,54–42,94 | schmales Feld 42,99–43,34
  - Links: dasselbe Raster, an den Türpositionen jeweils Fenster statt Tür. An der Stelle der Fahrerraumtür sitzt ein hohes Seitenfenster.
- Oberhalb des Fensterbands ist die Seitenwand gelb bis zur Dachfuge bei z ≈ 3,05. Darüber folgt die gelbe Dachverkleidung bis z ≈ 3,42 mit gerundeter Kante. Unterhalb ist die Seitenwand gelb bis zur Unterkante bei z ≈ 0,27, mit Schürzen-Revisionsklappen (dünne Fugen) bei z ≈ 0,27–0,60.

### 1.5 Kopf / Front (vorne und hinten gleich)
Gemessen am orthogonalen Seitenfoto 2827, Frontfoto 2832 (2026) und Foto 2820 (2006).
- **Seitenprofil** (Abstand hinter Bug bei Höhe z) [F]: Puffer 0,00 @ 0,30–0,63 | Bugmaske 0,13 @ 0,65 → 0,18 @ 1,20 | Frontscheibe unten 0,26 @ 1,22 → oben 0,54 @ 3,08 (**Neigung ≈ 8–9° gegen die Senkrechte**) | Dachkappe vorne 0,56 @ 3,10 → Übergang ins Dach 0,97 @ 3,42.
- **Draufsicht**: Die Front ist flach gewölbt, die Ecken sind gerundet (R ≈ 0,25–0,3 m) [S]. Die Frontscheibe zieht sich um die Ecken in die Seite herum, oben bis ≈ 0,85 m und unten bis ≈ 0,30 m hinter den Bug. Dann folgt eine schmale gelbe A-Säule (0,88–1,05) und danach die Fahrerraumtür.
- **Frontansicht** [F]:
  - Fahrzeugbreite 2,30 m.
  - Frontscheibe: eine durchgehende, leicht gewölbte Scheibe, unten ≈ 2,05 m breit, z ≈ 1,20–3,10, schwarz gerahmt. Ihr oberes Drittel ist schwarz bedruckt bzw. getönt und enthält die Zielanzeige. Darunter ist innen oft ein weißes Sonnenrollo zu sehen.
  - **Dachkappe**: anthrazit bis schwarz glänzend, über die Scheibe vorkragend (wie ein „Mützenschirm“), z ≈ 3,10–3,45. Mittig oben sitzt **eine runde weiße Leuchte** (Ø ≈ 0,20 m, z ≈ 3,30).
  - **Bugmaske** gelb, z ≈ 0,63–1,20. In der Mitte ein flaches Feld (≈ 0,92 m breit) mit dem **schwarzen DVB-Löwen samt zwei Schrägbalken** (≈ 0,35 × 0,40 m). Links und rechts davon je ein Feld mit **runden Scheinwerfern**: oben Scheinwerfer Ø ≈ 0,18 m bei z ≈ 0,98, darunter Schlussleuchte (rot) Ø ≈ 0,14 m bei z ≈ 0,78, beide bei y = ±0,63. Außen an den Ecken bei y ≈ ±0,95 je ein senkrechtes Paar Rechteckleuchten: oben gelb (Blinker), unten rot (Brems- bzw. Schlusslicht), z ≈ 0,74–1,16.
  - **Stoßfänger/Schürze**: anthrazit (dunkelgrau mit leichtem Blaustich), umlaufend um die Ecken, z ≈ 0,30–0,63 (Unterkante schräg zurückgesetzt bis ≈ 0,15). Er kragt ≈ 0,13 m vor die Maske vor.
  - Außenspiegel: schwarze Spiegelarme an beiden Seiten, Spiegelkopf bei z ≈ 2,3–2,8, ≈ 0,35 m seitlich ausladend.
- **Zielanzeige vorn**: **orange/bernsteinfarbene LED-Punktmatrix auf Schwarz**, einzeilig mit Linie und Ziel in gleicher Schrifthöhe (z. B. „3 Coschütz“, „11 ⇗ Bühlau“ mit Umleitungspfeil). Sichtfeld ≈ 1,30 × 0,26 m bei z ≈ 2,78–3,04 [F]. Das **Heck** hat denselben Kopf und dort sehr wahrscheinlich ebenfalls Linie und Ziel; beim DX DD ist das fotografisch belegt, beim D12DD nicht.
- **Seitenzielanzeige**: Ein Schmalbanddisplay ≈ 1,1 × 0,16 m sitzt oben in der ersten Scheibe hinter einem Gelenk (rechte Seite, z ≈ 2,40–2,56). Es ist ein grünlich hinterleuchtetes LCD, zweizeilig mit Liniennummer und Ziel („7 Pennrich / ü. Hauptbahnhof“) [F, Foto 2024].

### 1.6 Lackierung und Beschriftung
- Wagenkasten, Dachverkleidung und Türblätter: **DVB-Gelb** (siehe Farbtabelle Abschnitt 4).
- Schwarz: Fensterband (altes Design), Fensterrahmen und Holme, Faltenbälge, Dachkappe vorn und hinten. Stoßfänger/Schürze anthrazit. Dachgeräte hellgrau. **Keine silbernen oder grauen Zierstreifen.**
- **DVB-Logo** an beiden Seiten am Endmodul direkt hinter dem Kopf über der Fahrerraumtür: schwarz auf Gelb, Löwe + „//“ + „DVB“ fett-kursiv, darunter klein „DRESDNER VERKEHRSBETRIEBE AG“. Feld ≈ 0,90 × 0,38 m, x ≈ 1,0–1,9, z ≈ 2,59–2,97 [F]. Das alte Design hat ein dünn schwarz umrandetes Logofeld.
- **Wagennummer** (z. B. „2829“): schwarze Ziffern ≈ 0,10 m hoch in einem schwarz umrandeten, gerundeten Rechteck ≈ 0,47 × 0,14 m. Es sitzt rechts unten auf der Fahrerraumtür bei x ≈ 1,17–1,64, z ≈ 0,49–0,62 [F] und analog links. Die Nummer steht an **beiden Fahrzeugenden** (auch am Heckkopf).
- **Taufname** der Wagen 2801–2832 („STADT THARANDT“ usw.): schwarze Serifen-Versalien, zweizeilig, am Kopf vor der Fahrerraumtür bei x ≈ 0,45–0,90, z ≈ 0,95–1,10.
- Signalleuchten: kleine orange Seitenblinker und Rückstrahler an den Modulenden. Eine rote Rechteckleuchte sitzt oben auf der Dachverkleidung des M1 (Funktion unklar).

### 1.7 Dach
- Gelbe Dachverkleidung an den Seiten bis z ≈ 3,42. Darüber ragen **hellgraue, kastenförmige Dachgeräte** (Stromrichter, Widerstände) mit wenigen Zentimetern bis max. 3,50 m.
- **Stromabnehmer**: Einholm, auf **M1 über dem hinteren Drehgestell B2**, Fuß bei x ≈ 9,0–9,5 [F, Skizze + Modell; perspektivisch korrigiert]. Das **Knie zeigt nach vorn**. Wippe ≈ 1,6 m breit [S], Rahmen grau bzw. silbern, Wippe mit schwarzen Hörnern.
- Keine Fahrgastraum-Klimaanlage (nur Leipzig hat sie). Die Gelenke sind auf dem Dach mit schwarzen Faltenbalg-Abdeckungen überbrückt.

### 1.8 Unterseite
- Die Seitenschürze ist gelb und reicht bis z ≈ 0,27. Die **Drehgestelle sind weitgehend verkleidet** (Revisionsklappen in Gelb). Sichtbar ist nur das untere Radsegment unter der Schürze (Spalt ≈ 0,27 m bis SO), dazu dunkle Rahmenteile.
- Am Kopf reicht die anthrazitfarbene Schürze bis ≈ 0,15–0,30.

### 1.9 Innenraum (für Sicht durch Fenster)
- Haltestangen **gelb kunststoffummantelt** (RAL-1003-artig) mit grauen Halterungen. Decke hellgrau, gelochte Paneele. Doppel-Bildschirme unter der Decke in Hellgrau.
- Sitzbezüge: nicht belegt. Vermutlich dunkle Polster in Anthrazit oder Blaugrau mit Muster [S]. Durch die getönten Scheiben reicht dunkelgrau-blau.

### 1.10 Bildbeobachtungen (konkret)
- **Foto 2820 (2006, Regen, ¾-Front):**
  - Die Frontscheibe beginnt knapp über 1,2 m und reicht bis unter die schwarze, rundlich vorkragende Dachkappe mit runder Leuchte in der Mitte.
  - Der schwarze Scheibenrahmen läuft um die Ecken.
  - Unten liegt eine gelbe Maske mit runden Scheinwerfern (oben hell, darunter rot) beidseits eines Mittelfelds mit schwarzem Löwen.
  - Außen sitzen senkrechte Rechteckleuchten (rot), unten ein breiter schwarzer Stoßfänger.
  - Das große schwarze „DVB“-Logo steht hinter der Front über der Fahrerraumtür, „2820“ im Kästchen unten auf der Tür.
  - Die Türblätter tragen zwei hohe ovale Fenster.
- **Foto 2827 (orthogonal, Frontmodul):**
  - Das schwarze Fensterband läuft von z ≈ 1,25 bis 2,6 durch.
  - Zwei Scheiben von je ≈ 1,45–1,5 m Breite haben oben einen ≈ 0,3 m hohen Kippflügel.
  - Die Doppeltür hat gelbe Blätter mit Stadionfenstern.
  - Die Dachverkleidung ist gelb mit Teilfugen, darüber hellgraue Gerätekästen.
  - Unter der Schürze ist das Drehgestell nur als dunkler Streifen mit Radunterteilen sichtbar.
- **Foto 2832 (2026, frontal):** Das Zielband zeigt „3 Coschütz“ in großer oranger LED-Schrift über ≈ 60 % der Scheibenbreite. Die Leuchtenanordnung ist unverändert. Spiegelarme sind beidseits vorhanden.

---

## 2. NGT DX DD (Alstom/Bombardier Flexity Citytram Low-Floor), Wagen 2901–2924 (ER) und 2981–2989 (ZR)

Hauptquelle ist eine **maßstäbliche Seitenansicht aus der DVB-Broschüre 2021**. Ihr Maßstab wurde geprüft: Panoramafenster 3,30 × 1,30 m und Drehzapfenabstand 6,50 m stimmen auf ±1 % mit den offiziellen Werten überein. Maßstab 124,25 px/m, Länge über Bug 43,29 m. Die Werte unten sind daher überwiegend **[Z]**.

### 2.1 Eckdaten
| Größe | Wert | Güte |
|---|---|---|
| Länge | 43,29 m (DVB-Website), 43,30 (Wikipedia), „43,5 m“ (Broschüre, gerundet) | [Q] |
| Breite | 2,65 m, im Fußbodenbereich eingezogen auf 2,30 m | [Q] |
| Höhe max. | 3,50 m (Klimageräte). Dachoberkante bzw. Dachkante 3,36 m | [Q]/[Z] |
| Höhe mit gesenktem Stromabnehmer | ≈ 3,75–3,80 m | [S] |
| Fußboden | Einstieg 0,280 m; Niederflurbereich 0,325 m; über Triebdrehgestellen 0,530 m; Niederfluranteil 65 % | [Q] |
| Module | 5: Endwagen 1 (2 Triebdrehgestelle), Sänfte, kurzer Mittelwagen (1 Laufwerk, um ≈ 2° drehbar), Sänfte, Endwagen 5 | [Q] |
| Achsen / Antrieb | 10 Achsen, 8 × 95 kW, Achsformel (Bo'Bo')+2+(Bo'Bo') | [Q] |
| Drehzapfenabstand im Endwagen | 6,50 m | [Q] |
| Rad | Ø 600 mm neu / 520 mm abgenutzt | [Q] |
| Achsstand | 1,85 m | [Z] |
| Türen ER | 6 Doppel-Außenschwenkschiebetüren rechts + 1 einflügelige Außenschwenkschiebetür Fahrerraum (vorne rechts) | [Q] |
| Türen ZR | je Seite 5 Doppeltüren, 2 vollwertige Führerstände (Anordnung nicht vermessen) | [Q] |
| Besonderheit | Keine Außenspiegel, stattdessen ein Kamerasystem. Wagenkasten aus Edelstahl (Seitenwände und Dach) | [Q] |

### 2.2 Module, Gelenke, Drehgestelle (x ab Bug) [Z]
| Teil | x von | x bis | Länge | Fahrwerk |
|---|---|---|---|---|
| M1 Endwagen A | 0,00 | 12,56 | 12,56 | B1 Mitte 4,21 (Achsen 3,28 / 5,14), B2 Mitte 10,72 (9,79 / 11,65), beide Trieb |
| Gelenk 1 | 12,56 | 13,58 | 1,02 | Faltenbalg-Zone (Balg selbst ≈ 0,6–0,8 m) |
| M2 Sänfte | 13,58 | 18,74 | 5,16 | – |
| Gelenk 2 | 18,74 | 19,75 | 1,01 | |
| M3 Mittelwagen | 19,75 | 23,57 | 3,82 | B3 Mitte 21,65 (20,72 / 22,57), Laufwerk |
| Gelenk 3 | 23,57 | 24,57 | 1,00 | |
| M4 Sänfte | 24,57 | 29,74 | 5,17 | – |
| Gelenk 4 | 29,74 | 30,74 | 1,00 | |
| M5 Endwagen B | 30,74 | 43,29 | 12,55 | B4 Mitte 32,57, B5 Mitte 39,08, beide Trieb |

### 2.3 Türen rechts [Z]
| Tür | x von | x bis | Mitte |
|---|---|---|---|
| Fahrerraumtür (einflügelig) | 1,46 | 2,25 | 1,86 |
| T1 (M1) | 6,20 | 7,76 | 6,98 |
| T2 (M2 vorn) | 13,92 | 15,48 | 14,70 |
| T3 (M2 hinten) | 16,84 | 18,40 | 17,62 |
| T4 (M4 vorn) | 24,90 | 26,46 | 25,68 |
| T5 (M4 hinten) | 27,82 | 29,38 | 28,60 |
| T6 (M5) | 34,59 | 36,15 | 35,37 |

- **Portal** (schwarz, Ecken gerundet R ≈ 0,1): 1,57 m breit, z = 0,25–2,50. Lichte Weite ≈ 1,30 m [S].
- **Türblätter: schwarz** (nicht gelb wie beim D12DD) und **nahezu vollverglast**. Pro Blatt gibt es ein Glasfeld ≈ 0,52 m breit mit drei übereinanderliegenden Scheiben: oben z 1,29–2,25, Mitte ≈ 0,62–1,13, unten ≈ 0,48–0,56. Dazwischen liegen schwarze Querriegel bei z ≈ 1,13–1,29 und ≈ 0,56–0,62. Glasanteil ≈ 55 %.
- An der Blatt-Innenkante sitzen bei z ≈ 1,00–1,35 ein **gelber Ring-Taster** und darunter ein **blauer Rollstuhl-Taster**. Senkrecht am Portal laufen **LED-Leuchtstreifen** (grün = Zustieg möglich, rot = Tür schließt).
- **Fahrerraumtür**: z 0,36–2,51. Glas oben z 1,36–2,25, klein unten 1,00–1,13. Die Wagennummer steht **in gelben Ziffern auf dem schwarzen unteren Türfeld** (z ≈ 0,68–0,76).
- Die **untere Türkante läuft schräg in den eingezogenen Unterkasten**: Die Türblätter folgen unten der Einzugsschräge. Daher sieht man unten an jeder Tür ein schwarzes Trapez.

### 2.4 Fenster [Z]
Alle Fenster haben einen schwarzen Rahmen (≈ 0,06 m) mit gerundeten Ecken (R ≈ 0,10). Das Glas ist neutralgrau getönt. **Rahmen-Unterkante z = 1,19, Oberkante z = 2,49** (Glas 1,25–2,43).
- **Panoramafenster über den Drehgestellen** (Glas 3,20 × 1,18, Rahmen ≈ 3,32 × 1,30):
  - M1: 2,74–5,93 und 8,98–12,18
  - M3: 20,10–23,31
  - M5: 31,12–34,32 und 37,37–40,56
  - Einige haben oben mittig einen Kippflügel ≈ 1,35 × 0,33 m (z 2,09–2,43). Die Fenster mit Seitenzielanzeige haben keinen.
- **Kleines Fenster** zwischen den Sänftentüren: Glas 15,77–16,57 bzw. 26,75–27,55 (0,80 m, Rahmen ≈ 0,93). Oben ein Kippflügel z 2,15–2,41.
- **Heck M5 rechts**: hohes Seitenfenster statt Fahrerraumtür, Rahmen 41,15–41,89.
- **Kopf**: Die Frontscheibe ist um die Ecke gezogen. Dahinter folgt eine **schwarze A-Säule (Glasoptik)** bei x ≈ 0,47–0,66, dann ein **Kabinenseitenfenster** x ≈ 0,66–1,25 (z ≈ 1,2–2,8). Danach kommen die gelbe Säule 1,25–1,46 und die Fahrerraumtür.
- **Linke Seite (ER)**: An den Türpositionen sitzen Fenster gleicher Höhe, z. B. in M1 ein schmales und ein breites Fenster. An der Fahrerraumtür-Position steht ein hohes Seitenfenster (Foto 2902). Seitenzielanzeigen gibt es auch links.

### 2.5 Kopf / Front (vorne und hinten gleich) [Z] + [F]
- **Seitenprofil** (Abstand hinter Bugspitze bei z), direkt aus der Zeichnung:
  `z: 0,47→0,03 | 0,64→0,00 (Bugspitze) | 0,77→0,02 | 0,90→0,05 | 1,03→0,07 | 1,16→0,10 | 1,35→0,20 | 1,61→0,26 | 1,87→0,31 | 2,13→0,36 | 2,39→0,40 | 2,64→0,46 | 2,77→0,49 | 2,97→0,60 | 3,10→0,66 | 3,16→0,74 | 3,23→0,84 | 3,29→0,99 | 3,36→1,16 | 3,42→1,39 | 3,49→1,48`
  - Frontscheibe von z ≈ 1,2 bis 2,8 mit **≈ 10° Neigung** gegen die Senkrechte.
  - Darüber die **schwarze, stark gerundete Dachhaube (Visier)** bis z 3,36.
  - Oben schließt eine **gelbe Dachlippe** ab, die bei x ≈ 1,4–1,5 bis 3,49 aufsteigt.
  - Unterer Kopf (gelb): fast senkrecht, z 0,47–1,16. Fuge (Oberkante unteres Stoßfängerteil) bei z 0,82.
  - Die schwarze Bugschürze darunter reicht bis ≈ 0,15 [S]. Sie ist in der Zeichnung unsichtbar, auf Fotos klar zu sehen.
- **Draufsicht** [S]: Die Front ist flach gewölbt (Ecken ≈ 0,12–0,15 m zurück) und hat stark gerundete Ecken (R ≈ 0,35). Der untere Kopf wirkt „bauchig“ und läuft weich in die Seiten.
- **Frontansicht** (Piktogramm im Faktenheft 2019, etwa maßstäblich, plus Fotos 2904/2917/2901):
  - Breite 2,65 m. Unten an der Bugschürze ist der Kopf auf ≈ 2,0–2,3 m eingezogen, Kanten abgeschrägt ab z ≈ 0,7.
  - Die Frontscheibe ist ≈ 1,95 m breit und **eine große Scheibe**. Die schwarzen A-Säulen trennen die seitlichen Eckfenster ab. Alles ist schwarz gerahmt, sodass ein umlaufender schwarzer Glasbereich entsteht.
  - Unterkante der Frontscheibe z ≈ 1,17, mit **schwarzem Siebdruckband z 1,17–1,47**. Darin links unten das weiße Logo „ALSTOM“ (≈ 0,30 m breit, z ≈ 1,25).
  - Zielanzeige hinter der Scheibe im schwarzen Oberband: **orange/bernsteinfarbene LED**, Liniennummer links groß, Ziel mittig, z. B. „2 Gorbitz“. Sichtfeld ≈ 1,4–1,5 × 0,25 m bei z ≈ 2,55–2,80 [F/Piktogramm 2,60–2,80].
  - **Spitzenlicht**: rechteckige LED-Leuchte mit zwei waagerechten Streifen, ≈ 0,25 × 0,08 m, mittig auf der schwarzen Haube bei z ≈ 2,95–3,05.
  - Gelbe Bugmaske, Leuchten je Seite bei z ≈ 0,82–0,98: oben ein schmaler, leicht schräger LED-Streifen ≈ 0,30 m lang (Positions- und Tagfahrlicht, Blinker). Darunter ein **waagerechter LED-Hauptscheinwerfer-Balken** ≈ 0,28 × 0,05 m. Außen eine **runde Leuchte Ø ≈ 0,10 m mit Chromring** bei y ≈ ±1,0 (am Heck rot). Streifen bei y ≈ ±0,55–0,90.
  - Mitte: **schwarzer DVB-Löwe mit Schrägbalken**, klein (≈ 0,17 × 0,20 m), z ≈ 0,92.
  - Am Heck leuchtet der obere Streifen rot. Zusätzlich gibt es kleine rote Leuchten unten in den Stoßfängerecken (Foto 2901 Heck).
  - Kleines Kamera- bzw. Sensorgehäuse oben an den A-Säulen, keine Spiegel.
- **Liniennummer hinten**: Der Heckkopf hat eine volle Zielanzeige mit Linie und Ziel, orange LED (Foto 2901 von hinten: „2 Gorbitz“).
- **Seitenzielanzeigen** (rechts, [Z]): schwarzer Kasten 1,29 × 0,36 m, **oben mittig im Panoramafenster** bei z 2,09–2,45, an folgenden Stellen:
  - M1: x 3,69–4,97 (über B1)
  - M3: x 21,05–22,34
  - M5: x 32,08–33,36
  - Inhalt: oranges „2“ links und Ziel zweizeilig („Gorbitz / ü. Hebbelplatz“), orange LED.

### 2.6 Lackierung und Beschriftung
- **Ganzer Kasten gelb**: Seiten, Dachverkleidung, untere Kopfmaske. **Kein schwarzes Fensterband.**
- Schwarz sind: Fensterrahmen, **Türblätter samt Portalen**, Kopfhaube (glänzend), Frontscheibenrahmen, Bugschürze und Faltenbälge.
- Die Unterkastenschräge (eingezogener Bereich z 0,20–0,62) ist gelb, wirkt aber durch die Neigung dunkler. In der Zeichnung ist sie als dunkleres Band #E1970B wiedergegeben.
- **Großer Löwe mit „//“ als Ton-in-Ton-Grafik** auf den Endwagen:
  - M1 bei x ≈ 7,3–9,1 zwischen T1 und dem zweiten Panoramafenster, M5 bei x ≈ 35,5–37,4, z ≈ 0,9–2,8, auf beiden Seiten.
  - In der Zeichnung etwas dunkleres Orange-Gelb (#EC9E0C auf #F7B808). Auf Sonnenfotos erscheint die Grafik als blasser, hellerer Schimmer.
  - Umsetzung: Decal mit ±8 % Helligkeit und abweichender Rauigkeit.
- **DVB-Logo** klein (Löwe + „//DVB“, schwarz, ≈ 0,50 × 0,17 m) oben über der Fahrerraumtür bei x ≈ 1,59–2,08 und z ≈ 2,62–2,79. Ebenso am Heck (x ≈ 41,8–42,3) und links.
- **Wagennummer**: rechts gelb auf schwarzem Türfeld (Fahrerraumtür, z ≈ 0,7). Links und am Heck **schwarz auf Gelb** unter dem Kabinenfenster bei x ≈ 1,9–2,2 bzw. 41,9–42,2, z ≈ 0,64–0,76.
- Keine silbernen Zierstreifen. Die Faltenbälge wirken je nach Licht schwarz oder silbergrau (gerippte Kunststoff- bzw. Metallabdeckung). In der Broschürenzeichnung sind sie silbergrau gestreift.
- Orange Rückstrahler (Oval ≈ 0,12 m) an der Seite bei z ≈ 0,75. Seitenblinker als schmale senkrechte Leuchtschlitze an den Modulenden bei z ≈ 2,1–2,4.

### 2.7 Dach [Z]
- Die gelbe Seitenwand und die Dachverkleidung reichen bis 3,36 m. Die Dachkante ist gerundet: Lichtkante z 3,24–3,36, Fuge zwischen Seitenwand und Dachverkleidung bei z ≈ 2,97.
- **3 Klimageräte** (je 1,92 m lang, Oberkante 3,50) auf M1 bei x 5,96–7,88, auf M3 bei x 20,70–22,62 und auf M5 bei x 35,42–37,34. Auf Fotos hellgrau, in der Zeichnung dunkelgrau.
- Weitere Gerätekästen ragen nur bis ≈ 3,43 heraus:
  - M1: x 2,05–2,47, 2,78–3,96, 4,32–5,51, 11,13–11,61, 11,84–12,35
  - M5: spiegelbildlich, x 30,95–34,60 und 37,79–41,24
  - an den Gelenken kurze schwarze Brücken (≈ 0,5 m)
- **Stromabnehmer**: Einholm auf **M1 über B2**, Fuß und Isolator bei x ≈ 10,5. **Knie nach vorn**, bei gehobenem Stromabnehmer Knie bei x ≈ 9,6 und z ≈ 4,2, Wippe bei x ≈ 11,4. Grauer Rahmen.

### 2.8 Unterseite [Z]
- Die Schürzenunterkante liegt zwischen den Fahrwerken bei **z = 0,20**. Der Unterkasten ist ab z 0,62 nach unten auf 2,30 m Breite eingezogen.
- **Drehgestelle unverkleidet, Räder sichtbar.** Ausschnitte als Trapez, Oberkante z 0,63, Kanten schräg:
  - B1: unten 3,2–5,5, oben 3,4–5,1
  - B2: unten 9,5–12,0, oben 10,0–11,6
  - B3: unten 20,4–22,9
  - B4: unten 31,3–33,9
  - B5: unten 37,8–40,1
- Unter dem Kopf liegt die Unterkante bei z 0,47 (x 0–3,2 bzw. 40,1–43,29). Darunter sitzt die schwarze Schürze.
- Motoren und Getriebe liegen **außen an den Radsätzen**. Sie sind dunkelgrau bis oliv und verschmutzt, Getriebe mit Aufschrift „FLENDER“. Räder stahlgrau mit Bremsscheiben (Foto Falk2).

### 2.9 Innenraum
- Serie: Sitzpolster **schwarz-anthrazit mit gelb-orangem Wellenlinienmuster**, Sitzschalen schwarz, 2+2-Bestuhlung, Gang 0,66 m.
- Haltestangen **hellgrau bzw. aluminiumfarben** (Aluminium statt Edelstahl), Haltewunsch-Taster in **gelben Gehäusen**.
- Decke weiß bzw. hellgrau mit zwei durchgehenden LED-Lichtbändern (Lichtfarbe variabel), Boden dunkelgrau.
- Das Mockup von 2020 hatte noch Sitzstoff mit großen gelben Löwen.

### 2.10 Bildbeobachtungen (konkret)
- **Broschürenzeichnung:**
  - Panoramafenster mit schwarzem Rahmen und gerundeten Ecken, Rahmen-Unterkante 1,19 m.
  - Türen als schwarze Portale mit Glasblättern und gelb- bzw. blauen Tastern.
  - Kopf mit schwarzer Haube, die von der Scheibenoberkante (≈ 2,8 m) bis 3,36 m gewölbt nach hinten läuft. Die gelbe Dachlippe steigt bei 1,4–1,5 m hinter dem Bug auf.
  - Unten ist der eingezogene Schrägstreifen als dunkleres Gelb zu sehen. Drehgestelle offen mit grauen Rädern.
- **Foto 2904 (Hbf):**
  - Schwarze, glänzende Haube mit doppeltem LED-Spitzenlicht.
  - Breites schwarzes Zielband „3 Coschütz“ in Orange, große Scheibe mit Wischer rechts, schwarzes Unterband mit „ALSTOM“.
  - Gelbe, gerundete Maske mit schmalen LED-Leisten und Rundleuchten außen, Löwe mittig.
  - Gelbes unteres Stoßfängerteil mit Fuge, darunter eine breite schwarze Schürze.
- **Foto 2902 (linke Seite):** Fenster an allen Türpositionen. Großer heller Löwe mit „//“ auf dem Endwagen. Silbrig wirkende Faltenbälge, offene Drehgestelle.
- **Foto 2901 von hinten:** Der Heckkopf ist identisch mit der Front und zeigt Linie und Ziel. Rote Schlussleuchten im oberen Leuchtstreifen.

---

## 3. NGT D8DD sowie NGT8DD/NGT6DD (kurz)

### NGT D8DD (Bombardier Flexity Classic, 40 Wagen 2601–2640, 2006–2009)
- 30,04 m lang, 2,30 m breit, Höhe ≈ 3,50 [S, wie D12DD], ER. Masse 39,1 t (DVB). 6 × 85 kW.
- **3 Module**: Die Endmodule entsprechen den Endmodulen des D12DD (je 2 Drehgestelle, je 1 Doppeltür). Dazwischen hängt eine **laufwerkslose Sänfte mit 2 Doppeltüren**. **4 Drehgestelle**, davon 3 Trieb- und 1 Laufdrehgestell (das dritte, mit Losradsätzen). Achsformel Bo'Bo'2'Bo'. 4 Fahrgasttüren und 1 Fahrerraumtür.
- Abgeleitete Lage [S] (x ab Bug):

| Teil | x |
|---|---|
| M1 | 0–11,80 |
| Gelenk 1 | 11,80–12,22 |
| Sänfte | 12,22–17,82 |
| Gelenk 2 | 17,82–18,24 |
| M3 | 18,24–30,04 |
| Drehgestelle | 3,97 / 9,47 / 20,57 / 26,07 |
| Türen | Fahrerraum 1,05–1,75; T1 5,55–7,15; T2 12,42–14,02; T3 16,02–17,62 (Sänfte: Tür, Fenster dazwischen 14,17–15,87, Tür); T4 22,89–24,49 |

- Aussehen, Kopf, Lackierung, Logo, Nummer und Stromabnehmer (auf M1 über B2) wie beim D12DD.

### NGT8DD (23 Wagen 2701–2723, Bombardier/DWA Bautzen 2001–2002)
- 41,02 m lang, 2,30 m breit, ER, **7 Module**.
- **4 starre Fahrwerke**: 2-achsige Triebgestelle unter Modul 1, 5 und 7, ein Losradlaufwerk unter Modul 3.
- Die drei laufwerkslosen Zwischenmodule (2, 4, 6) haben **je 2 Doppel-Außenschwenkschiebetüren**, zusammen also 6. Dazu kommt eine nach innen öffnende Fahrerraumtür vorne rechts.
- Haltestangen gelb ummantelt. Seit 2024 werden die Wagen auf LED umgerüstet.

### NGT6DD (Dresdens erster Niederflurtyp, DWA Bautzen 1995–1998)
- 29,72 m (DVB) bzw. 30,28 m über Kupplung (Wikipedia), 2,30 m breit, 5 Module.
- 2 Triebfahrwerke (Modul 1 und 5) und 1 Losradlaufwerk (Modul 3). Die zwei Sänften haben je 2 Türen, beim ZR 4.
- ER 2501–2547 und ZR 2581–2593. Die ZR-Wagen hatten zusätzlich **weiße Bänder über den Fenstern**, die seit 2026 mit den schwarzen Bändern entfernt werden.
- Haltestangen Edelstahl poliert.
- Für die Höhen der 6DD- und 8DD-Kästen wurden keine Quellen gefunden. Sie sind optisch ähnlich zum D12DD, aber mit eigener, älterer Kopfform.

---

## 4. Farbtabelle (Blender Principled BSDF)
Ein offizieller RAL-Ton der DVB-Fahrzeuge ist **nicht veröffentlicht**. Die DVB-Markenfarbe der Website ist #FDC400. Am nächsten liegen **RAL 1023 Verkehrsgelb (#F7B500)** und RAL 1021 Rapsgelb (#F6B600). Die Zeichnung der DVB-Broschüre zeigt #F7B808. Fotos zeigen in der Sonne #E1BC12 bis #F7BE36 und bei Bewölkung #B67703 bis #B88D20.

| Material | sRGB | Linear (Base Color) | Rauigkeit / Metall | Bemerkung |
|---|---|---|---|---|
| DVB-Gelb Kasten | #F5B800 | (0.913, 0.479, 0.000) | 0.25 / 0 (Klarlack glänzend) | [S] Kompromiss aus RAL 1023 und Markenfarbe |
| Löwengrafik DX DD | #E9A20A | (0.815, 0.361, 0.003) | 0.35 | dezent, Ton in Ton |
| Schwarz glänzend (Haube, Rahmen, DX-Türen) | #111213 | (0.006, 0.006, 0.007) | 0.15 / 0 | |
| Fensterband D12DD/D8DD (altes Design) | #1E201E | (0.013, 0.014, 0.013) | 0.3 | |
| Stoßfänger/Schürze (anthrazit) | #2F3234 | (0.028, 0.032, 0.034) | 0.5 | ≈ RAL 7021 |
| Dachgeräte | #CBD0CC | (0.597, 0.631, 0.604) | 0.5 | ≈ RAL 7035 |
| Faltenbalg | #1C1C1C | (0.012, 0.012, 0.012) | 0.6 | gerippt (Normal Map) |
| Glas getönt | #2A3236 | (0.023, 0.032, 0.037) | 0.05, Transmission niedrig, eher spiegelnd | |
| LED-Zielanzeige | #FF9A00 | (1.000, 0.323, 0.000) | Emission 3–8 | Punktmatrix-Textur |
| Haltestangen D12DD/8DD | #E5B000 | (0.784, 0.434, 0.000) | 0.4 | |
| Sitze DX DD | #23262E | (0.017, 0.019, 0.027) | 0.8 | mit gelben Wellen |
| Drehgestell/Motor | #3A3A36 | – | 0.7 | Schmutz |

---

## 5. Blender-Bauanleitung (Maßtabellen zum Übernehmen)

Koordinaten: x ab Bugspitze nach hinten [m], y quer (+ = rechts = Türseite), z über SO [m]. Für Blender (Y vorwärts) z. B. `loc = (y, -x, z)` setzen und das ganze Objekt um die halbe Länge verschieben. Alle Fenster und Türen gelten für die **rechte Seite**. Für die linke Seite gilt `y = -y`, mit Fenstern statt Türen.

```python
# ---------- NGT DX DD (Alstom Flexity, ER) -- ueberwiegend aus massstaeblicher Zeichnung ----------
DXDD = dict(
    length=43.29, width=2.65, width_floor=2.30, roof_z=3.36, max_z=3.50,
    skirt_z=0.20, taper_top_z=0.62,          # unten eingezogen: halbe Breite 1.325 (z>=0.62) -> 1.15 (z=0.20)
    seam_z=2.97, roof_edge_z=(3.24, 3.36),    # Fuge Seitenwand/Dachverkleidung, gerundete Dachkante
    section=[(1.15,0.20),(1.325,0.62),(1.325,2.50),(1.30,2.97),(1.25,3.24),(1.05,3.36),(0.0,3.38)],  # (halbe Breite, z) [S oben]
    modules=[(0.00,12.56,'M1'),(13.58,18.74,'M2_saenfte'),(19.75,23.57,'M3'),(24.57,29.74,'M4_saenfte'),(30.74,43.29,'M5')],
    joints=[(12.56,13.58),(18.74,19.75),(23.57,24.57),(29.74,30.74)],
    bogies=[4.21,10.72,21.65,32.57,39.08], wheelbase=1.85, wheel_d=0.60,
    bogie_cutouts=[(3.2,5.5),(9.5,12.0),(20.4,22.9),(31.3,33.9),(37.8,40.1)],  # unten; Oberkante z=0.63, Kanten schraeg (~0.4 m)
    head_bottom_z=0.47, head_bottom_x=(0.0,3.2),  # und spiegelbildlich am Heck
    # Tueren rechts: (x0, x1, z0, z1, typ)
    doors=[(1.46,2.25,0.36,2.51,'cab'),(6.20,7.76,0.25,2.50,'double'),(13.92,15.48,0.25,2.50,'double'),
           (16.84,18.40,0.25,2.50,'double'),(24.90,26.46,0.25,2.50,'double'),(27.82,29.38,0.25,2.50,'double'),
           (34.59,36.15,0.25,2.50,'double')],
    door_glass_z=[(1.29,2.25),(0.62,1.13),(0.48,0.56)], door_leaf_glass_w=0.52,
    # Fensterrahmen rechts (x0,x1); Rahmen z 1.19-2.49, Glas 1.25-2.43, Rahmenbreite 0.06, Eckradius 0.10
    windows=[(2.68,5.99),(8.92,12.24),(15.70,16.63),(20.04,23.37),(26.69,27.61),(31.06,34.38),(37.31,40.62),(41.15,41.89)],
    win_z=(1.19,2.49),
    side_displays=[(3.69,4.97),(21.05,22.34),(32.08,33.36)], side_display_z=(2.09,2.45),
    # Kopf-Seitenprofil (x hinter Bug, z) -- vorne und hinten identisch
    head_profile=[(0.03,0.47),(0.00,0.64),(0.02,0.77),(0.05,0.90),(0.07,1.03),(0.10,1.16),(0.20,1.35),(0.26,1.61),
                  (0.31,1.87),(0.36,2.13),(0.40,2.39),(0.46,2.64),(0.49,2.77),(0.60,2.97),(0.66,3.10),(0.74,3.16),
                  (0.84,3.23),(0.99,3.29),(1.16,3.36),(1.39,3.42),(1.48,3.49)],
    windscreen=dict(z=(1.17,2.85), frit_band_z=(1.17,1.47), width=1.95, a_pillar_x=(0.47,0.66), cab_side_window_x=(0.66,1.25)),
    front_display=dict(z=(2.55,2.80), w=1.45, color='#FF9A00'),
    lights=dict(top_led=(0.0,3.00,0.25,0.08), main_bar_z=0.90, main_bar_y=(0.55,0.85), round_lamp=(1.00,0.86,0.10), lion_z=0.92),
    roof_ac=[(5.96,7.88),(20.70,22.62),(35.42,37.34)], roof_ac_top=3.50,
    pantograph=dict(base_x=10.5, knee='forward', module='M1'),
    logo=dict(x=(1.59,2.08), z=(2.62,2.79)), number_z=(0.68,0.76),
    lion_decal=[(7.3,9.1),(35.5,37.4)], lion_decal_z=(0.9,2.8),
)

# ---------- NGT D12DD (Flexity Classic XXL, ER) -- Fotos/Ableitung, Toleranz +-0.3 m ----------
D12DD = dict(
    length=45.09, width=2.30, max_z=3.50, roof_fairing_z=3.42, seam_z=3.05, skirt_z=0.27,
    section=[(1.15,0.27),(1.15,3.05),(1.10,3.30),(0.90,3.42),(0.0,3.44)],
    modules=[(0.00,11.80,'M1'),(12.22,17.42,'M2_saenfte'),(17.84,27.24,'M3'),(27.66,32.86,'M4_saenfte'),(33.28,45.09,'M5')],
    joints=[(11.80,12.22),(17.42,17.84),(27.24,27.66),(32.86,33.28)],
    bogies=[3.97,9.47,19.80,25.30,35.62,41.12], wheelbase=1.80, wheel_d=0.60,  # Drehgestelle verkleidet
    doors=[(1.05,1.75,0.38,2.52,'cab'),(5.55,7.15,0.30,2.65,'double'),(13.75,15.35,0.30,2.65,'double'),
           (21.74,23.34,0.30,2.65,'double'),(29.19,30.79,0.30,2.65,'double'),(37.94,39.54,0.30,2.65,'double')],
    door_leaf_color='yellow', door_window='stadium', door_window_wh=(0.50,1.75), door_window_z=(0.65,2.40),
    window_band_z=(1.25,2.60), glass_z=(1.29,2.56), hopper_split_z=2.25,   # altes Design: Band komplett schwarz
    panes=[(1.75,2.10),(2.15,3.55),(3.75,5.30),(7.35,9.45),(9.60,11.65),(12.32,13.65),(15.45,17.32),
           (17.95,19.75),(19.85,21.65),(23.43,25.23),(25.33,27.13),(27.76,29.09),(30.89,32.76),
           (33.43,35.48),(35.63,37.74),(39.79,41.34),(41.54,42.94),(42.99,43.34)],
    head_profile=[(0.00,0.30),(0.00,0.63),(0.13,0.65),(0.18,1.20),(0.26,1.22),(0.54,3.08),(0.56,3.10),(0.97,3.42)],
    windscreen=dict(z=(1.20,3.10), width=2.05, side_wrap_x=(0.30,0.85), a_pillar_x=(0.88,1.05)),
    roof_cap=dict(z=(3.10,3.45), color='#111213', top_lamp=(0.0,3.30,0.20)),
    front_display=dict(z=(2.78,3.04), w=1.30, color='#FF9A00'),
    lights=dict(head_round=(0.63,0.98,0.18), tail_round=(0.63,0.78,0.14), corner_pair_y=0.95, corner_pair_z=(0.74,1.16),
                center_panel_w=0.92, lion=(0.35,0.40)),
    bumper=dict(z=(0.30,0.63), overhang=0.13, color='#2F3234'),
    side_display=dict(w=1.1, h=0.16, z=(2.40,2.56), color='#9CD27A'),  # gruenliches LCD
    logo=dict(x=(1.0,1.9), z=(2.59,2.97)), number_box=dict(x=(1.17,1.64), z=(0.49,0.62)),
    name_text=dict(x=(0.45,0.90), z=(0.95,1.10)),
    pantograph=dict(base_x=9.3, knee='forward', module='M1'),
)
```

**Hinweise zur Umsetzung:**
- **Seitenwand**: Querschnitt (`section`) entlang x extrudieren und jedes Modul einzeln mit gerundeten Enden (R ≈ 0,15) anlegen. Die Gelenke als eingezogene, gerippte Faltenbalg-Zylinder modellieren (halbe Breite ≈ 1,05 bzw. 1,25 beim DX).
- **Kopf**: Die `head_profile`-Polylinie als Seitenkontur nutzen und mit dem Querschnitt lofen, Draufsicht-Ecken mit R ≈ 0,3. Den Heck-Kopf gespiegelt bei x = L ansetzen.
- **Fenster**: als Ausschnitt im Kasten plus eingesetztes, bündiges Glas mit schwarzem Rahmenstreifen (Rahmen 0,06 m beim DX, schwarzes Band beim D12DD).
- **Unterkasten DX DD**: Schräge von (1,325 | 0,62) nach (1,15 | 0,20). Türblätter unten mit der Schräge abschneiden.
- **LOD**: Drehgestelle beim D12DD nur als dunkle Box mit Radunterkante. Beim DX sind sie sichtbar: 2 Radsätze Ø 0,60, außenliegender Motor-Getriebe-Block grau.

---

## 6. Quellen
- de.wikipedia: [Gelenktriebwagen NGT D12DD](https://de.wikipedia.org/wiki/NGT_D12DD), [Gelenktriebwagen NGT DXDD](https://de.wikipedia.org/wiki/NGT_DXDD), [NGT D8DD](https://de.wikipedia.org/wiki/NGT_D8DD), [NGT8DD](https://de.wikipedia.org/wiki/NGT8DD), [NGT6DD](https://de.wikipedia.org/wiki/NGT6DD), [LVB-Typ 38](https://de.wikipedia.org/wiki/LVB-Typ_38) (Drehzapfenabstände, Fußboden), [Bombardier Flexity Classic](https://de.wikipedia.org/wiki/Bombardier_Flexity_Classic), [RAL-Farbe](https://de.wikipedia.org/wiki/RAL-Farbe)
- DVB: [Fahrzeugübersicht Straßenbahn](https://www.dvb.de/de-de/die-dvb/technik/fahrzeuge/strassenbahn) (Längen, Massen, Türen), [Broschüre NGT DX DD 2021](https://www.dvb.de/-/media/files/die-dvb/broschuere_ngtdxdd_doppel.pdf) (maßstäbliche Seitenansicht), [Faktenheft 2019](https://www.dvb.de/-/media/files/die-dvb/faktenheft2019_web_doppelseiten.pdf) (Steckbrief, Frontpiktogramm, Panoramafenster 3,30 × 1,20 m, Kamerasystem statt Spiegel), dvb.de-CSS (Markengelb #FDC400)
- Halling/LH Modelle: [Beipack NGT D12 Dresden](https://www.halling.at/documents/Beipack-Nahverkehr/Beipack---NGT-D12---Dresden-5-Teilig.pdf) (Modellfotos, Moduleinteilung)
- Wikimedia Commons, Kategorien „NGT D12DD (Dresden)“ und „NGT DXDD (Dresden)“: Einzelnachweise mit Lizenz in `dvb_tram_img/QUELLEN.txt`
- Weitere Hintergründe: urban-transport-magazine.com, railwaygazette.com (DX DD 2,65 m, Hersteller)
