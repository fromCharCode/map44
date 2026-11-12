# Map44 – Dresden

Ein Open-World-Spiel in **ganz Dresden**: 117 Kacheln à 2 × 2 km, gebaut aus offenen Geodaten (Gelände, Luftbilder,
3D-Gebäude, Straßen, Bäume, Haltestellen). Fahr durch die Altstadt, über die Elbbrücken, neben echten DVB-Linien her –
mit Verkehr, Fußgängern, Straßenbahnen und Bussen nach Fahrplan, Tag/Nacht und Wetter. Gebaut mit Godot 4.7.

*An open-world driving game set in all of Dresden, generated from open geodata (terrain, aerial imagery, 3D buildings,
streets, street trees, transit stops). Installers below download the game and the map data (~5 GB).*

## Schnell installieren

**Linux** (x86_64) – im Terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/fromCharCode/map44/main/install/install.sh | bash
```

Danach starten mit `map44` oder über das Startmenü („Map44 – Dresden“).

**Windows 10/11** (x64) – in PowerShell:

```powershell
irm https://raw.githubusercontent.com/fromCharCode/map44/main/install/install.ps1 | iex
```

Danach starten über Startmenü oder Desktop („Map44 Dresden“). Windows SmartScreen kann beim ersten Start warnen
(das Spiel ist nicht signiert): „Weitere Informationen“ → „Trotzdem ausführen“.

Beide Installer laden die neueste Version aus den [Releases](https://github.com/fromCharCode/map44/releases), prüfen die
Prüfsummen und setzen abgebrochene Downloads fort. Erneut ausführen = Update (die Kartendaten werden nur neu geladen,
wenn sich ihre Version ändert). Deinstallieren unter Linux: `… install.sh | bash -s -- --uninstall`.

**Manuell:** `map44-<system>-x86_64.zip` aus dem neuesten Release entpacken, die Kartendaten
`map44-data-*-NN.zip` aus dem zugehörigen Daten-Release (`data-v…`) in denselben Ordner entpacken (es entsteht
`data/`), dann `map44.x86_64` bzw. `map44.exe` starten.

### Systemanforderungen

- 64-Bit Linux oder Windows 10/11, Grafikkarte mit Vulkan (oder Direct3D 12), ab ~4 GB Grafikspeicher
- 8 GB RAM (16 GB empfohlen), rund 8 GB freier Platz
- Getestet auf AMD RX 6700 XT in 1080p und 4K (FSR 2 wird bei hohen Auflösungen automatisch genutzt)

## Steuerung

| Aktion | Tastatur | Gamepad (Xbox-Belegung) |
|---|---|---|
| Gas / Bremse / Lenken | W / S / A, D (oder Pfeiltasten) | RT / LT / linker Stick |
| Handbremse | Leertaste | RB |
| Kamera wechseln / zurückschauen | C / B (halten) | Y / LB (halten) |
| Umschauen | Maus | rechter Stick |
| Licht / Hupe | L / H | Steuerkreuz hoch / L3 |
| Gang hoch / runter | E / Q | A / X |
| Automatik ↔ Manuell | F | R3 |
| Karte | M | Steuerkreuz runter oder Back |
| Auto zurücksetzen | R | B |
| Tageszeit vor / zurück | T / G | Steuerkreuz rechts / links |
| Reparieren, Wetter | F5, F6 | |
| Straße wählen (Teleport) | F3 | |
| Grafikqualität, Schaden an/aus | F2, F4 | |
| Pause / Menü | Esc | Start |

## Was drin ist

- Ganz Dresden aus Geodaten: Gelände (DGM1), Luftbilder, 3D-Gebäude (LoD2) mit Fassadenstil nach Baujahr und
  Stadtstruktur, Wahrzeichen (Frauenkirche, Hofkirche, Semperoper, Hausmannsturm, Kreuzkirche, Hochhaus am
  Pirnaischen Platz mit „Naddl und Ronny siegt“ …), Elbe mit Dampfern, Brücken
- Straßen in echter Breite (aus dem öffentlichen Straßenraum abgeleitet), Gehwege bis zur Hauskante, Granit-Bordsteine,
  Markierungen, Ampeln, Verkehrszeichen; Gehwegbeläge je Viertel; über 120 000 echte Bäume aus dem Dresdner
  Baumkataster (Art, Höhe, Standort) mit Baumscheiben; Grünstreifen und Allee-Mittelstreifen als Rasen; Plätze wie
  der Altmarkt als gepflasterte Freiflächen
- Brücken nach Recherche: Sandstein-Bogenbrücken (Augustus-, Albert-, Marienbrücke …) mit echten Bögen und Pfeilern,
  Geländer je Bauwerk (Stein, Stahl in Originalfarbe, Glaswände), Blaues Wunder als Stahlfachwerk,
  Waldschlößchenbrücke mit Stahlbogen und V-Streben; die 2024 eingestürzte und abgerissene Carolabrücke fehlt wie in
  echt
- Verkehr mit Vorfahrt und Ampeln, Fußgänger, Buslinien (OSM) mit Zielanzeigen
- Straßenbahnen der DVB (NGT D12DD und NGT DX DD, maßstäblich nachgebaut) auf ihren echten Linien mit Zielanzeigen,
  Haltestellen an allen 1 761 echten Steigen: Masten mit Linien und Zielen, Bahnsteige mit Bordhöhe,
  Blindenleitstreifen und Schutzgittern an Inseln, Wartehallen, Abfahrtstafeln im DVB-Format („3 Wilder Mann 2“, Takt
  nach Tageszeit, echte Bahnen live)
- Fahrphysik mit Reifenmodell, Federung, ABS/ESP, Schaden, Reifenspuren

Noch nicht drin: Tunnel (A17, Wiener Platz, Waldschlößchen-Nordseite – die Straße endet am Portal), Fahrplan nach
echtem DVB-Fahrplan (bisher Takt nach Tageszeit).

## Aus dem Quellcode starten (Entwickler)

1. [Godot 4.7.1](https://godotengine.org/download) installieren.
2. Kartendaten holen: entweder die Daten-Zips aus dem Release nach `data/` entpacken und `MAP44_DATA=<pfad>/data`
   setzen, oder selbst bauen (siehe unten).
3. `./start_dresden.sh` (bzw. `godot --path godot`).

Pipeline (Python 3 mit `.venv`, siehe `tools/`): `tools/run_tile.sh E,N` baut eine Kachel (Luftbild, Gelände, Stadt),
`tools/rebuild_city.sh E,N` nur Stadt + Vegetation; alle Kacheln: `xargs -P 6 -I{} bash tools/rebuild_city.sh {} <
data/raw/tile_order.txt`. Release-Pakete: `tools/package_release.sh <version> <datenversion>`.

## Daten und Lizenzen

Die Geodaten stammen aus offenen Quellen und dürfen mit Namensnennung weitergegeben werden. Vollständige Liste:
[THIRD_PARTY.md](THIRD_PARTY.md). Kurz:

- © GeoSN – Staatsbetrieb Geobasisinformation und Vermessung Sachsen (Luftbilder, DGM/DOM, LoD2, ALKIS), dl-de/by-2-0
- © OpenStreetMap-Mitwirkende, ODbL (Straßen, Linien, Haltestellen, POIs) – die abgeleiteten Kartendaten stehen
  unter der ODbL
- © Landeshauptstadt Dresden (Baumkataster, Haltestellen-Barrierefreiheit, Stadtstrukturtypen, Straßenflächen),
  dl-de/by-2-0
- © Statistische Ämter des Bundes und der Länder, Zensus 2022 (Gebäude nach Baujahr), dl-de/by-2-0
- Texturen: ambientCG (CC0), Klänge: freesound.org (CC0), Schriften: Noto (SIL OFL 1.1)

Alle 3D-Modelle (Fahrzeuge, Straßenbahnen, Haltestellen, Möbel, Bäume, Wahrzeichen) sind eigens für dieses Projekt
prozedural erzeugt (Blender-Skripte unter `tools/blender/`).
