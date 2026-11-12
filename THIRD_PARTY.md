# Daten, Inhalte und Lizenzen von Dritten

Map44 nutzt offene Daten und freie Inhalte. Die Quellenvermerke unten gelten für das Spiel, die Release-Datenpakete
(`map44-data-*.zip`) und die Pipeline unter `tools/`.

## Geodaten

| Daten | Quelle | Lizenz |
|---|---|---|
| Digitale Orthophotos (RGB, CIR), Digitales Geländemodell DGM1, Digitales Oberflächenmodell DOM1, 3D-Gebäudemodelle LoD2 (inkl. Brückenbauwerke), ALKIS vereinfacht (tatsächliche Nutzung) | © GeoSN – Staatsbetrieb Geobasisinformation und Vermessung Sachsen | [Datenlizenz Deutschland – Namensnennung – 2.0](https://www.govdata.de/dl-de/by-2-0) |
| Straßen, Wege, Gleise, Gewässer, Haltestellen, Bus- und Straßenbahnlinien, Läden, Stadtmöbel | © [OpenStreetMap](https://www.openstreetmap.org/copyright)-Mitwirkende (Geofabrik-Auszug Sachsen) | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) – aus OSM abgeleitete Kartendaten (u. a. `city.json`, `*_routes.json`, `streets.json`) stehen unter der ODbL |
| Stadtbäume (Baumkataster), Haltestellen Dresden – Barrierefreiheit, Stadtstrukturtypen, Straßen- und Verkehrsflächen, Grün- und Freiflächen, Anlagen des Radverkehrs, Straßenknotennetz | © Landeshauptstadt Dresden (Themenstadtplan / Open-Data-Portal) | dl-de/by-2-0 |
| Gebäude nach Baujahr (Zensus 2022, 100-m-Gitter) | © Statistische Ämter des Bundes und der Länder | dl-de/by-2-0 |

## Inhalte

| Inhalt | Quelle | Lizenz |
|---|---|---|
| Materialtexturen (Putz, Ziegel, Pflaster, Asphalt …) | [ambientCG](https://ambientcg.com), Liste in `godot/assets/textures/LICENSES.md` | CC0 1.0 |
| Klänge (Motoren, Reifen, Straßenbahn, Stadt …) | [freesound.org](https://freesound.org), Urheber in `godot/assets/audio/LICENSES.md` | CC0 1.0 |
| Schriften Noto Sans / Noto Serif | The Noto Project Authors | SIL Open Font License 1.1 (`godot/assets/fonts/OFL.txt`) |
| Spiel-Engine | [Godot Engine](https://godotengine.org) | MIT |

## Eigene Inhalte

Alle 3D-Modelle (Fahrzeuge, Straßenbahnen NGT D12DD/NGT DX DD, Busse, Haltestellen, Stadtmöbel, Bäume, Laternen,
Wahrzeichen, Hochhaus am Pirnaischen Platz), die Verkehrszeichen-, Plakat- und Graffiti-Texturen sind für dieses
Projekt prozedural erzeugt (Skripte unter `tools/blender/`). Fotos aus der Recherche (`data/research/*_img/`) dienten
nur der Analyse und sind nicht Teil des Spiels oder dieses Repositorys.

Markenzeichen (z. B. DVB, Alstom) werden nicht verwendet; Fahrzeuge und Haltestellen sind nach öffentlich
zugänglichen Maßen nachgebildet.
