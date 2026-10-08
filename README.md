# Steigungsatlas deutscher Großstädte

Plus die neun österreichischen Landeshauptstädte, die zehn größten Schweizer Städte und Luxemburg als Vergleich,
dazu Tübingen und Pirmasens auf Leserwunsch.

Welche deutschen Großstädte (> 100.000 EW) haben pro Straßenkilometer die meiste bzw. steilste Steigung?
Pipeline in Python, Ergebnis als CSV/JSON plus eine selbstenthaltene interaktive Seite (`index.html`).

**Live:** https://silviodc.de/ai-projects/hoehenprofil/

## Ausführen

```bash
git clone https://github.com/L0b0mau/Steigungsatlas.git && cd Steigungsatlas
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python run_analysis.py --test      # Testlauf: Wuppertal, Münster, Stuttgart
python run_analysis.py             # alle 85 DE-Städte + 9 AT + 10 CH + LU + 2 Wunschstädte (~15 min mit 4 Workern, Downloads gecacht)
# dann index.html im Browser öffnen (läuft offline, alle Bibliotheken und Schriften sind eingebettet)
```

Weitere Optionen: `--cities Essen Aachen`, `--workers 4`, `--skip-analysis` (nur Auswertung + HTML aus dem Cache).
Downloads (Overture-Segmente, DEM-Kacheln) und berechnete Netze landen in `cache/` (nicht versioniert, ca. 5 GB).

**Veröffentlichen:** `index.html` ist die einzige Datei, die auf einen Webspace muss. Daten, three.js, d3 und Schriften
sind eingebettet, es gibt keine externen Abhängigkeiten.

## Ergebnisse

| Datei | Inhalt |
|---|---|
| `data/staedte.csv` | Städteliste inkl. Einwohner (OSM), Grenztyp, Fläche, Status Großstadt/Grenzfall |
| `results/staedte_kennzahlen.csv` | alle Kennzahlen je Stadt (drive + bike, Copernicus + SRTM), Histogramm-km je Klasse |
| `results/top_staedte.json` | Top 3, flachste Stadt, beide Rankings, Methodik, bekannte Grenzen |
| `results/validierung.json` | Stichprobe bekannter Straßen mit Höhenprofil |
| `index.html` | interaktive Visualisierung (4,1 MB, offline) |
| `social/wuppertal_vs_innsbruck.png` | Vergleichsbild für Social Media (3200×2000, englisch) |

### Top 10 nach Höhenmetern pro Straßenkilometer (Netz „drive“, Copernicus GLO-30)

| # | Stadt | Hm/km | Ø Steigung | Median | P90 | > 6 % | > 10 % | > 15 % | Rang > 6 % | Hm/km SRTM (Rang) |
|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 1 | Wuppertal | 20,8 | 4,2 % | 3,2 % | 9,0 % | 25,2 % | 7,6 % | 1,6 % | 1 | 19,1 (3) |
| 2 | Remscheid | 20,7 | 4,1 % | 3,2 % | 9,0 % | 23,9 % | 7,5 % | 1,5 % | 2 | 19,4 (2) |
| 3 | Siegen ° | 20,1 | 4,0 % | 2,7 % | 9,5 % | 23,6 % | 9,0 % | 2,3 % | 3 | 19,6 (1) |
| 4 | Hagen | 18,8 | 3,8 % | 2,6 % | 8,8 % | 20,6 % | 7,2 % | 1,9 % | 4 | 17,8 (4) |
| 5 | Solingen | 17,8 | 3,6 % | 2,8 % | 7,5 % | 18,1 % | 3,7 % | 0,7 % | 5 | 16,7 (6) |
| 6 | Pforzheim | 17,3 | 3,5 % | 2,4 % | 7,7 % | 17,4 % | 4,8 % | 1,3 % | 6 | 17,2 (5) |
| 7 | Würzburg | 16,9 | 3,4 % | 2,2 % | 7,8 % | 17,0 % | 5,6 % | 1,6 % | 8 | 15,9 (8) |
| 8 | Jena | 16,8 | 3,4 % | 2,2 % | 8,4 % | 17,1 % | 5,7 % | 1,3 % | 7 | 15,9 (7) |
| 9 | Bergisch Gladbach | 15,9 | 3,2 % | 2,4 % | 7,0 % | 14,3 % | 3,5 % | 0,9 % | 10 | 14,0 (12) |
| 10 | Stuttgart | 15,5 | 3,1 % | 2,1 % | 7,0 % | 14,2 % | 3,8 % | 0,8 % | 11 | 15,2 (10) |

° Siegen liegt laut OSM bei 99.403 EW und ist als Grenzfall markiert. Für die Top 3 der Visualisierung zählen nur
Städte ≥ 100.000 EW, deshalb rückt Hagen auf Platz 3.

Flachste Großstadt: **Moers** (5,0 Hm/km), knapp vor Hamm (5,1) und Krefeld (5,2).

### Was die Daten sagen

- **Bergisches Land vorne.** Wuppertal, Remscheid, (Siegen), Hagen, Solingen. Wuppertal und Remscheid trennen 0,2 Hm/km,
  das ist weniger als die Messunsicherheit. Mit SRTM lautet die Reihenfolge Siegen, Remscheid, Wuppertal. Robust ist die Gruppe, nicht der Platz.
- **Stuttgart nur auf Platz 10.** Die steilen Hanglagen sind da, aber Neckartal, Filder und Talkessel-Boden haben viel flaches Netz,
  das den Schnitt drückt. Pro Straßenkilometer gemessen ist Stuttgart hügelig, nicht extrem.
- **Die erwarteten flachen Städte sind nicht die flachsten.** Berlin (Rang 42, 8,9 Hm/km), Hamburg (53), Bremen (68), Münster (73),
  Leipzig (74) liegen deutlich über Moers/Hamm/Krefeld. Ein Teil ist echte Topografie (Moränenkanten, Elbhang), ein großer Teil ist
  Rauschen des Oberflächenmodells (Gebäude, Bäume, viele Brücken). Mit SRTM sinken Berlin auf 7,5 und Hamburg auf 6,9.
  Unterhalb von ca. 7–8 Hm/km sind Rangunterschiede kaum aussagekräftig.
- **Ranking nach Anteil > 6 % ist fast identisch** (Spearman ρ = 0,98). Größere Verschiebungen: Heidelberg (21 → 12) und Karlsruhe
  (49 → 37) haben wenige, aber steile Hanglagen am Stadtrand; Osnabrück (38 → 51), Recklinghausen, Wolfsburg haben flächig sanfte Wellen ohne steile Abschnitte.
- **Copernicus vs. SRTM**: Spearman ρ = 0,97 über alle Städte. Copernicus liegt fast überall leicht höher (mehr Oberflächenrauschen).
- **Radnetz („bike“)** ist überall steiler als das Autonetz (Wuppertal 25,4 Hm/km), weil Wald- und Feldwege an Hängen dazukommen.

### Vergleich: österreichische Landeshauptstädte

Gleiche Methode und Datenquellen, kein Rang im deutschen Ranking, aber ein Gesamtrang über alle 107 Städte (DE + AT + CH + LU + Wunschstädte).

| Gesamtrang | Stadt | Hm/km | Median | > 6 % | > 10 % | > 15 % | Hm/km SRTM | Radnetz Hm/km |
|--:|---|--:|--:|--:|--:|--:|--:|--:|
| 11 | Innsbruck | 17,5 | 1,9 % | 20,0 % | 7,9 % | 2,5 % | 17,9 | 32,1 |
| 17 | Bregenz | 15,9 | 1,8 % | 17,5 % | 6,9 % | 1,7 % | 16,2 | 26,2 |
| 27 | Graz | 13,7 | 1,4 % | 14,0 % | 5,4 % | 1,3 % | 13,9 | 23,5 |
| 34 | Eisenstadt | 12,9 | 1,7 % | 9,3 % | 2,9 % | 0,6 % | 12,6 | 18,3 |
| 38 | Wien | 12,1 | 1,3 % | 10,4 % | 3,2 % | 0,9 % | 11,7 | 15,4 |
| 39 | Linz | 12,0 | 1,2 % | 11,3 % | 3,6 % | 0,8 % | 12,1 | 17,6 |
| 43 | Salzburg | 11,7 | 1,3 % | 9,0 % | 4,1 % | 1,1 % | 11,4 | 16,6 |
| 57 | Klagenfurt | 9,6 | 1,0 % | 7,8 % | 2,1 % | 0,4 % | 10,2 | 18,6 |
| 99 | St. Pölten | 6,1 | 0,7 % | 2,3 % | 0,6 % | 0,1 % | 7,1 | 9,1 |

**Ist Innsbruck steiler als Wuppertal?** Im Durchschnitt nein: 17,5 gegen 20,8 Hm/km, in beiden Höhenmodellen.
Innsbruck (Gesamtrang 11) ist zweigeteilt: Der Talboden im Inntal ist flach (52 % der Straßen-km unter 2 % Steigung, Wuppertal 35 %),
die Hänge zur Hungerburg, nach Igls und Mühlau sind dafür steiler. Bei den sehr steilen Abschnitten liegt Innsbruck
vorne (> 15 %: 2,5 % gegen 1,6 %), ebenso im Radnetz (32,1 gegen 25,4 Hm/km), weil dort die Hangwege dazukommen.
Wuppertal ist flächig hügelig, Innsbruck ist flach mit steilen Rändern.

Die Alpenlage allein macht eine Stadt nicht steil: Salzburg (11,7) und Klagenfurt (9,6) liegen in breiten Becken,
St. Pölten gehört zu den flachsten Städten im ganzen Vergleich. Gemessen wird das Straßennetz, nicht die Berge
im Stadtgebiet: Die Nordkette gehört zu Innsbruck, hat aber kaum befahrbare Straßen.

### Vergleich: die zehn größten Schweizer Städte

Nur sechs Schweizer Städte haben mehr als 100.000 Einwohner. Die 26 Kantonshauptorte wären das Gegenstück zu den
österreichischen Landeshauptstädten, enthalten aber Dörfer mit wenigen Dutzend Straßenkilometern. Deshalb die zehn
größten Städte. Grenze ist die politische Gemeinde.

| Gesamtrang | Stadt | Hm/km | Median | > 6 % | > 10 % | > 15 % | Hm/km SRTM | Radnetz Hm/km |
|--:|---|--:|--:|--:|--:|--:|--:|--:|
| 1 | Lugano | 28,0 | 4,8 % | 40,9 % | 14,7 % | 3,5 % | 27,9 | 41,8 |
| 4 | Lausanne | 20,6 | 3,1 % | 23,7 % | 7,8 % | 1,6 % | 20,3 | 25,2 |
| 6 | Luzern | 19,9 | 2,8 % | 25,2 % | 7,4 % | 1,7 % | 19,3 | 24,4 |
| 8 | Genf | 18,7 | 2,7 % | 19,6 % | 6,4 % | 2,1 % | 16,4 | 21,3 |
| 9 | St. Gallen | 18,6 | 2,7 % | 20,9 % | 5,8 % | 1,2 % | 18,5 | 26,4 |
| 16 | Zürich | 16,7 | 2,2 % | 16,8 % | 5,7 % | 1,3 % | 15,9 | 21,4 |
| 21 | Biel/Bienne | 15,1 | 1,9 % | 14,9 % | 5,0 % | 0,8 % | 14,4 | 25,4 |
| 31 | Bern | 13,3 | 1,7 % | 10,5 % | 2,7 % | 0,6 % | 13,5 | 18,3 |
| 44 | Winterthur | 11,6 | 1,3 % | 9,6 % | 2,0 % | 0,6 % | 11,8 | 20,4 |
| 49 | Basel | 10,8 | 1,3 % | 7,0 % | 1,8 % | 0,6 % | 10,6 | 12,9 |

- **Lugano ist mit Abstand am steilsten** (28,0 Hm/km, 41 % der Straßen-km über 6 %), in beiden Höhenmodellen.
  Der Wert hängt aber am Zuschnitt: Seit den Fusionen 2004–2013 gehören Bergdörfer bis ins Val Colla zur Stadt.
  Das ist eher eine Berggemeinde mit Stadtkern als eine steile Stadt im Sinne von Wuppertal.
- **Lausanne liegt gleichauf mit Wuppertal und Remscheid** (20,6 gegen 20,8 / 20,7), Luzern knapp dahinter.
  Der Unterschied ist kleiner als die Messunsicherheit.
- **Genf ist überraschend hoch** (18,7). Mit SRTM sind es 16,4. Genf ist auf 18 km² fast vollständig dicht bebaut,
  dort erzeugt das Oberflächenmodell mehr Gebäuderauschen als anderswo. Ein Teil ist echt (Altstadthügel, Hänge zu Rhône und Arve).
- **Basel und Winterthur** liegen im Mittelfeld: Basel (10,8) etwa wie Bonn oder Freiburg, Winterthur (11,6) etwa wie Dortmund oder Mainz.

### Leserwünsche: Pirmasens, Luxemburg, Tübingen

Nachgereicht nach Kommentaren auf Reddit. Pirmasens (ca. 40.000 EW) und Tübingen (ca. 89.000 EW) liegen unter
100.000 Einwohnern und laufen außer Konkurrenz: Gesamtrang ja, Rang im deutschen Großstadt-Ranking nein. Luxemburg
wird wie AT/CH als Vergleichsstadt geführt. Grenze ist jeweils die Gemeinde.

| Gesamtrang | Stadt | Hm/km | Median | > 6 % | > 10 % | > 15 % | Hm/km SRTM | Radnetz Hm/km |
|--:|---|--:|--:|--:|--:|--:|--:|--:|
| 15 | Pirmasens | 16,7 | 2,3 % | 16,5 % | 4,1 % | 1,0 % | 16,4 | 22,0 |
| 24 | Luxemburg | 14,3 | 1,8 % | 11,6 % | 3,7 % | 1,2 % | 14,2 | 18,8 |
| 25 | Tübingen | 14,0 | 1,7 % | 14,2 % | 3,2 % | 0,6 % | 14,0 | 18,9 |

- **Pirmasens** läge unter den deutschen Großstädten auf Platz 9, gleichauf mit Jena (16,8) und vor Stuttgart
  (15,5). Der Ruf als steilste Stadt der Pfalz bestätigt sich, an Wuppertal (20,8) reicht es nicht heran.
- **Luxemburg** (14,3) liegt etwa bei Reutlingen und Essen. Die Altstadt auf dem Felsplateau und die tief
  eingeschnittenen Täler von Alzette und Pétrusse sind steil, die Plateaus dazwischen flach.
- **Tübingen** (14,0) liegt etwa bei Wiesbaden. Die Altstadthänge sind steil, die Neckar- und Ammertalböden
  ziehen den Schnitt nach unten.

## Methodik

1. **Straßen**: Overture Maps Transportation (Release 2026-09-23.1), aus OpenStreetMap abgeleitet, per Bounding Box aus GeoParquet
   auf S3 gelesen. *Abweichung vom Plan:* Overpass/Nominatim (und damit `osmnx.graph_from_polygon`/`geocode_to_gdf`) waren in der
   Ausführungsumgebung blockiert. Die Netzlogik ist OSMnx nachgebaut: Filter „drive“ (motorway … residential, living_street,
   unclassified, service ohne parking_aisle/driveway, ohne access=private/no) und „bike“ (ohne motorway, footway, steps, bridleway).
2. **Grenzen**: Overture Divisions (OSM-Verwaltungsgrenzen). Kreisfreie Städte = county, kreisangehörige = locality, Berlin/Hamburg = region.
3. **Städteliste**: Overture Divisions, `locality` mit `class=city` und OSM-Tag `population ≥ 100.000` (79 Städte).
   Wikipedia/Destatis waren ebenfalls nicht erreichbar. 6 Orte mit 97.000–99.999 EW laut OSM sind als „Grenzfall“ mitgerechnet.
4. **Höhe**: Copernicus DEM GLO-30 (Kacheln von AWS Open Data, gecacht), bilinear direkt in der Originalkachel interpoliert.
   Gegenprüfung mit SRTM 1″ (AWS Terrain Tiles, Skadi) für alle Städte.
5. **Netz**: Segmente an Connectoren (OSM-Knoten) geteilt, ungerichteter Graph, Knoten mit Grad 2 entfernt (wie `osmnx.simplify_graph`).
   Jede Straße zählt einmal, unabhängig von Fahrtrichtungen.
6. **Brücken/Tunnel**: Knoten, die nur an Brücken-/Tunnelkanten hängen, bekommen eine entlang des Netzes linear zwischen den
   Bauwerksenden interpolierte Höhe statt des DEM-Werts.
7. **Kanten < 10 m** werden kontrahiert (Endknoten verschmolzen, Höhe gemittelt).
8. **Steigung** je Kante = |Δh| / Länge. Kanten > 40 % werden markiert, gezählt (`ausreisser_n`, `ausreisser_km`) und aus den
   Kennzahlen ausgenommen; `hm_pro_km_inkl_ausreisser` zeigt den Wert mit ihnen. Alle Kennzahlen längengewichtet.
9. **Hm/km** = Σ positiver Höhenmeter, über beide Fahrtrichtungen gemittelt (= Σ|Δh|/2), geteilt durch Straßen-km.
10. **Steilste Strecke**: zusammenhängende Kantenfolge gleichen Namens, 100–800 m, maximale Netto-Steigung. Konservativ bewertet:
    Minimum aus Copernicus und SRTM, beide müssen in dieselbe Richtung steigen. Brücken, Tunnel und Ausreißer sind ausgeschlossen.

### Was gemessen und was geschätzt ist

- **Gemessen** (aus den Daten berechnet): alle Kennzahlen, Rankings, Histogramme, Profile, Straßen-km.
- **Abgeleitet/geschätzt**: Höhen auf Brücken/in Tunneln (linear interpoliert), Höhen verschmolzener Knoten (Mittelwert),
  Einwohnerzahlen (OSM-Tag, gemischte Stichtage, nicht Destatis).
- **Referenzwerte der Stichprobe** stammen aus Online-Quellen (komoot, climbfinder), nicht aus eigener Vermessung.

### Stichprobe (Qualitätssicherung)

| Straße | Referenz | DEM Copernicus | DEM SRTM | Urteil |
|---|---|---|---|---|
| Hauptstraße, Aachen-Burtscheid (333 m) | Ø 9 %, steilster Abschnitt 13,3 % | Ø 9,7 %, max. 14,2 % (100 m) | Ø 7,3 %, max. 13,3 % | passt |
| Stotznocken, Essen-Werden (101 m) | ca. 30 % Spitze | Ø 17,2 %, max. 27,0 % (50 m) | Ø 17,0 %, max. 25,3 % | Spitze plausibel, aber Straße ist nur gut 3 Pixel lang |
| Neue Weinsteige, Stuttgart (1,3-km-Teilstück) | Talkessel → Degerloch (≈ 470 m) | 294 → 360 m, Ø 5,1 % | 292 → 361 m, Ø 5,3 % | Δh plausibel, kein Prozent-Referenzwert gefunden |

### Bekannte Grenzen

- **Hm/km und mittlere Steigung sind dasselbe Maß.** Bei knotenbasierter Methode gilt Hm/km = 5 × mittlere Steigung (%).
  Das Primärranking ist damit identisch mit dem Ranking nach mittlerer Steigung; ein unabhängiges zweites Maß ist nur „Anteil > 6 %“.
- **Copernicus GLO-30 ist ein Oberflächenmodell (DSM)**, kein Geländemodell. Gebäude, Bäume und Brückendecks fließen ein. Das
  erzeugt in flachen Städten ein Grundrauschen von ca. 5 Hm/km (≈ 1 % mittlere Steigung). Ein echtes Geländemodell (DGM1 der
  Länder) wäre genauer und ist in vielen Ländern frei verfügbar, die Portale waren in der Ausführungsumgebung aber
  nicht erreichbar. Die Umstellung ist geplant: [docs/PLAN_DTM_UND_STADTDATEIEN.md](docs/PLAN_DTM_UND_STADTDATEIEN.md).
- **30-m-Raster**: Rampen ab ca. 100 m werden gut getroffen. Kürzere Abschnitte schwanken um mehrere Prozentpunkte, Rampen unter 30 m sind unsichtbar.
- **Nur Knotenhöhen**: Kuppen und Senken zwischen zwei Kreuzungen fehlen; lange Kanten werden unterschätzt.
- **Unter Brücken**: Straßen, die unter einer Brücke durchführen, können im DSM die Deckhöhe bekommen (nicht korrigiert).
- **Stadtzuschnitt**: Verwaltungsgrenze. Eingemeindete ländliche Ortsteile oder flache Talböden verändern das Ergebnis.

## Datenquellen und Lizenzen

- Straßen und Grenzen: © OpenStreetMap-Mitwirkende (ODbL), bereitgestellt über [Overture Maps](https://overturemaps.org)
- Copernicus DEM GLO-30 © DLR e.V. 2010–2014 und © Airbus Defence and Space GmbH 2014–2018, bereitgestellt unter COPERNICUS durch die EU und ESA
- SRTM (NASA/USGS) über AWS Terrain Tiles
- Eingebettet in `index.html`: three.js (MIT), d3 (ISC), Chakra Petch und JetBrains Mono (SIL OFL)

## Aufbau

```
run_analysis.py          Einstieg: Städteliste -> Netze -> Kennzahlen -> Report -> Validierung -> HTML
steigung/overture.py     Overture-Zugriff (S3, BBox-Filter, Cache)
steigung/cities.py       Großstädte + Verwaltungsgrenzen
steigung/dem.py          DEM-Kacheln laden, cachen, bilinear samplen
steigung/network.py      Netzfilter, Teilen an Connectoren, Brücken/Tunnel, Vereinfachung, Kontraktion
steigung/metrics.py      längengewichtete Kennzahlen, Histogramm, steilste Strecke
steigung/report.py       CSV/JSON inkl. Methodik und Grenzen
steigung/validate.py     Stichprobe bekannter Straßen
steigung/viz_export.py   Datenaufbereitung + Einbetten in index.html
web/template.html        Seite (HTML/CSS/JS), web/vendor/ eingebettete Bibliotheken und Schriften
social/poster.js         rendert das Social-Media-Bild aus index.html (Node + Playwright)
docs/PLAN_DTM_UND_STADTDATEIEN.md  Plan für v2: Geländemodell (DGM) statt DSM, eine JSON-Datei pro Stadt
```

Das Social-Media-Bild neu erzeugen (benötigt Node und `npm i playwright`):

```bash
node social/poster.js index.html social/wuppertal_vs_innsbruck.png
```
