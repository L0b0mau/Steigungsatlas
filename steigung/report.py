"""Ergebnisdateien: results/staedte_kennzahlen.csv und results/top_staedte.json."""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from . import config

log = logging.getLogger(__name__)

MAIN_COLS = [
    "rang_hm_pro_km", "rang_anteil_6pct", "rang_gesamt_hm_pro_km", "stadt", "land", "status", "bundesland", "einwohner_osm",
    "flaeche_km2", "strassen_km", "hm_pro_km", "mittl_steigung_pct", "median_steigung_pct",
    "p90_steigung_pct", "anteil_ueber_6pct", "anteil_ueber_10pct", "anteil_ueber_15pct",
    "ausreisser_n", "ausreisser_km", "kontrahiert_km", "brueckentunnel_knoten_interpoliert",
    "steilste_strasse", "steilste_strecke_pct_konservativ", "steilste_strecke_pct_cop30",
    "steilste_strecke_pct_srtm", "steilste_strecke_m",
    "rang_hm_pro_km_srtm", "drive_srtm_hm_pro_km", "drive_srtm_anteil_ueber_6pct",
    "drive_srtm_p90_steigung_pct",
    "bike_cop30_strassen_km", "bike_cop30_hm_pro_km", "bike_cop30_anteil_ueber_6pct",
]

METHODIK = {
    "strassendaten": "Overture Maps Transportation (Release {rel}), abgeleitet aus OpenStreetMap. "
                     "Overpass/Nominatim waren in der Ausführungsumgebung nicht erreichbar; Overture "
                     "liefert dieselben OSM-Wege als GeoParquet. Netz 'drive' angelehnt an den OSMnx-Filter "
                     "(motorway…residential, living_street, unclassified, service ohne parking_aisle/driveway, "
                     "ohne access=private/no). 'bike' analog (ohne motorway, footway, steps, bridleway).",
    "stadtgrenzen": "Overture Divisions (OSM-Verwaltungsgrenzen): kreisfreie Städte = county, "
                    "kreisangehörige = locality, Berlin/Hamburg = region.",
    "staedteliste": "Overture Divisions, locality class=city, OSM-Tag population >= 100.000. "
                    "Wikipedia/Destatis waren nicht erreichbar. Siegen liegt im OSM-Tag knapp darunter (99.403), "
                    "ist amtlich aber über 100.000 EW und zählt daher als Großstadt. Orte mit 97.000–99.999 laut OSM "
                    "sind als 'Grenzfall' mitgerechnet, aber nicht für Top 3/Vergleichsstadt verwendet.",
    "hoehenmodell": "Primär Copernicus DEM GLO-30 (1\", DSM). Gegenprüfung mit SRTM 1\" "
                    "(AWS Terrain Tiles/Skadi). Bilineare Interpolation an den Knoten.",
    "netz": "Ungerichteter, vereinfachter Graph (Knoten = Kreuzungen/Sackgassen, wie osmnx.simplify_graph); "
            "jede Straße zählt einmal, unabhängig von Fahrtrichtungen.",
    "bruecken_tunnel": "Knoten, die nur an Brücken-/Tunnelkanten hängen, erhalten eine entlang des Netzes "
                       "linear zwischen den Bauwerksenden interpolierte Höhe.",
    "kurze_kanten": f"Kanten < {config.MIN_EDGE_LEN_M:.0f} m werden kontrahiert (Endknoten verschmolzen, Höhe gemittelt).",
    "steigung": "Steigung je Kante = |Δh| / Kantenlänge (Knotenhöhen). Alle Kennzahlen längengewichtet.",
    "ausreisser": f"Kanten > {100 * config.OUTLIER_GRADE:.0f} % werden markiert, gezählt und aus den Kennzahlen "
                  "ausgenommen (Spalte hm_pro_km_inkl_ausreisser zeigt den Wert mit ihnen).",
    "hm_pro_km": "Σ positiver Höhenmeter, über beide Fahrtrichtungen gemittelt (= Σ|Δh|/2), geteilt durch Straßen-km.",
    "oesterreich": "Zum Vergleich die neun österreichischen Landeshauptstädte (Wien zugleich Bundeshauptstadt), "
                   "gleiche Methode und Datenquellen. Grenzen: Statutarstädte = county, Bregenz = locality, Wien = region. "
                   "Sie erhalten keinen Rang im deutschen Ranking, nur einen Gesamtrang.",
    "schweiz": "Zum Vergleich die zehn größten Schweizer Städte (nur sechs davon > 100.000 EW): Zürich, Genf, Basel, "
               "Lausanne, Bern, Winterthur, Luzern, St. Gallen, Lugano, Biel/Bienne. Grenze = politische Gemeinde "
               "(OSM localadmin). Gleiche Methode, nur Gesamtrang.",
    "luxemburg": "Luxemburg-Stadt auf Leserwunsch, Grenze = Gemeinde. Gleiche Methode, nur Gesamtrang.",
    "wunschstaedte": "Reddit-Wishlist: Tübingen, Pirmasens, Marburg, Niedernhausen (Gemeinde) und Engenhahn (Ortsteil von "
                     "Niedernhausen) auf Leserwunsch. Alle liegen unter 100.000 EW und laufen daher außer Konkurrenz: "
                     "Gesamtrang, aber kein Rang im deutschen Großstadt-Ranking. Sehr kleine Gebiete wie Engenhahn "
                     "(wenige Straßenkilometer) sind statistisch weniger belastbar.",
    "steilste_strecke": "Zusammenhängende Kantenfolge gleichen Straßennamens, 100–800 m, maximale Netto-Steigung. "
                        "Konservativ: Minimum aus Copernicus und SRTM, Richtung muss übereinstimmen.",
}

GRENZEN = [
    "Hm/km ist bei knotenbasierter Methode mathematisch = 5 × mittlere Steigung (%). Beide Kennzahlen ergeben "
    "exakt dasselbe Ranking; Hm/km ist kein unabhängiges zweites Maß.",
    "Copernicus GLO-30 ist ein Oberflächenmodell (DSM): Gebäude, Bäume und Brückendecks fließen ein. "
    "In flachen Städten erzeugt das ein Grundrauschen von ca. 5–6 Hm/km bzw. 1–1,3 % mittlerer Steigung, "
    "das keine echte Topografie ist.",
    "30-m-Raster: Rampen ab ca. 100 m Länge werden in der Stichprobe gut getroffen (Burtscheid Ø 9,7 % vs. 9 %). "
    "Auf kürzeren Fenstern (< 2 Pixel) schwanken Werte um mehrere Prozentpunkte; Spitzenwerte einzelner kurzer "
    "Rampen sind nicht belastbar, und Treppen-/Kurzrampen unter 30 m sind unsichtbar.",
    "Die Differenzen an der Spitze sind kleiner als die Messunsicherheit: Wuppertal und Remscheid liegen "
    "0,2 Hm/km auseinander, mit SRTM dreht sich die Reihenfolge der ersten drei. Robust ist die Gruppe, nicht der Platz.",
    "Nur Knotenhöhen: Kuppen und Senken zwischen zwei Kreuzungen werden nicht erfasst (Unterschätzung bei langen Kanten).",
    "Straßen, die unter Brücken hindurchführen, können im DSM die Brückenhöhe erhalten (nicht korrigiert).",
    "Einwohnerzahlen stammen aus OSM (gemischte Stichtage), nicht direkt aus Destatis, Statistik Austria bzw. BFS.",
    "Längen werden für alle Städte in UTM 32N gerechnet. Für Ostösterreich (Wien, Graz) liegt der Maßstabsfehler "
    "dadurch bei ca. 0,3–0,4 %; Steigungen ändern sich um denselben relativen Betrag (vernachlässigbar).",
    "Stadtgebiet = Verwaltungsgrenze. Große Waldflächen/ländliche Ortsteile verändern das Ergebnis je nach Zuschnitt. "
    "Extremfall Lugano: Durch Gemeindefusionen (2004–2013) gehören Bergdörfer bis ins Val Colla zur Stadt.",
    "Dichte Altstädte mit hohen Häuserzeilen (z. B. Genf, 18 km² fast vollständig bebaut) bekommen im DSM mehr "
    "Gebäuderauschen als locker bebaute Städte; Genf liegt mit SRTM bei 16,4 statt 18,7 Hm/km.",
]


def _rank(s: pd.Series) -> pd.Series:
    return s.rank(ascending=False, method="min").astype("Int64")


def write_results(cities: pd.DataFrame, store: dict, failed: dict):
    meta = cities.drop(columns="geometry").set_index("stadt")
    rows = [dict(r) for k, r in store.items() if k in meta.index]
    df = pd.DataFrame(rows).set_index("stadt")
    df = meta[["land", "status", "bundesland", "einwohner_osm", "flaeche_km2"]].join(df, how="inner").reset_index()
    # Ränge der deutschen Städte untereinander (wie ursprünglich), AT-Städte ohne DE-Rang
    # Wunschstädte (< 100.000 EW) laufen außer Konkurrenz, wie die Vergleichsländer nur mit Gesamtrang
    is_de = (df["land"] == "DE") & (df["status"] != "Wunschstadt")
    for col, src in (("rang_hm_pro_km", "hm_pro_km"), ("rang_anteil_6pct", "anteil_ueber_6pct"),
                     ("rang_hm_pro_km_srtm", "drive_srtm_hm_pro_km")):
        df[col] = pd.Series(pd.NA, index=df.index, dtype="Int64")
        df.loc[is_de, col] = _rank(df.loc[is_de, src])
    df["rang_gesamt_hm_pro_km"] = _rank(df["hm_pro_km"])
    bins = config.GRADE_BINS
    hist_cols = []
    for i, (lo, hi) in enumerate(zip(bins[:-1], bins[1:])):
        c = f"km_{lo}_{hi if hi < 1000 else 'inf'}pct"
        df[c] = df["hist_km"].apply(lambda h: h[i])
        hist_cols.append(c)
    df = df.sort_values("hm_pro_km", ascending=False)
    is_de = (df["land"] == "DE") & (df["status"] != "Wunschstadt")
    other = [c for c in df.columns if c not in MAIN_COLS + hist_cols + ["hist_km", "hist_km_srtm"]]
    out = df[[c for c in MAIN_COLS if c in df.columns] + hist_cols + other]
    out.to_csv(config.RESULTS / "staedte_kennzahlen.csv", index=False, float_format="%.3f")
    log.info("results/staedte_kennzahlen.csv: %d Städte", len(out))

    gs = df[(df.status == "Großstadt") & is_de]
    de = df[is_de].copy()
    top3 = gs.nsmallest(3, "rang_hm_pro_km")
    flat = gs.nlargest(1, "rang_hm_pro_km")
    top3_alt = gs.nsmallest(3, "rang_anteil_6pct")

    # Ranking-Vergleich
    rho_rank = float(de["rang_hm_pro_km"].astype(float).corr(de["rang_anteil_6pct"].astype(float), method="spearman"))
    rho_dem = float(de["hm_pro_km"].corr(de["drive_srtm_hm_pro_km"], method="spearman"))
    de["rangdiff"] = de["rang_anteil_6pct"].astype(float) - de["rang_hm_pro_km"].astype(float)
    movers = de.loc[de["rangdiff"].abs() >= 5, ["stadt", "rang_hm_pro_km", "rang_anteil_6pct", "rangdiff"]]

    def brief(r):
        keys = ["stadt", "land", "rang_hm_pro_km", "rang_gesamt_hm_pro_km", "rang_anteil_6pct", "rang_hm_pro_km_srtm", "hm_pro_km",
                "mittl_steigung_pct", "median_steigung_pct", "p90_steigung_pct", "anteil_ueber_6pct",
                "anteil_ueber_10pct", "anteil_ueber_15pct", "strassen_km", "drive_srtm_hm_pro_km",
                "drive_srtm_anteil_ueber_6pct", "steilste_strasse", "steilste_strecke_pct_konservativ",
                "steilste_strecke_m"]
        return {k: (None if pd.isna(r[k]) else r[k].item() if hasattr(r[k], "item") else r[k]) for k in keys}

    res = {
        "stand": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "overture_release": config.OVERTURE_RELEASE,
        "methodik": {k: v.format(rel=config.OVERTURE_RELEASE) for k, v in METHODIK.items()},
        "bekannte_grenzen": GRENZEN,
        "top3_hm_pro_km": [brief(r) for _, r in top3.iterrows()],
        "top3_anteil_6pct": [brief(r) for _, r in top3_alt.iterrows()],
        "flachste_grossstadt": brief(flat.iloc[0]),
        "ranking_hm_pro_km": de.sort_values("rang_hm_pro_km")["stadt"].tolist(),
        "ranking_anteil_6pct": de.sort_values("rang_anteil_6pct")["stadt"].tolist(),
        "oesterreich": [brief(r) for _, r in df[df.land == "AT"].sort_values("hm_pro_km", ascending=False).iterrows()],
        "schweiz": [brief(r) for _, r in df[df.land == "CH"].sort_values("hm_pro_km", ascending=False).iterrows()],
        "luxemburg": [brief(r) for _, r in df[df.land == "LU"].iterrows()],
        "wunschstaedte": [brief(r) for _, r in df[df.status == "Wunschstadt"].iterrows()],
        "ranking_gesamt_hm_pro_km": df.sort_values("hm_pro_km", ascending=False)["stadt"].tolist(),
        "ranking_vergleich": {
            "spearman_hm_vs_anteil6": round(rho_rank, 3),
            "staedte_mit_rangdifferenz_ab_5": movers.to_dict("records"),
        },
        "dem_vergleich": {"spearman_hm_pro_km_cop30_vs_srtm": round(rho_dem, 3)},
        "fehlgeschlagen": {k: v.splitlines()[0] for k, v in failed.items()},
        "anzahl_staedte": int(is_de.sum()),
        "anzahl_staedte_at": int((df.land == "AT").sum()),
        "anzahl_staedte_ch": int((df.land == "CH").sum()),
        "anzahl_staedte_lu": int((df.land == "LU").sum()),
        "anzahl_wunschstaedte": int((df.status == "Wunschstadt").sum()),
        "anzahl_staedte_gesamt": int(len(df)),
    }
    (config.RESULTS / "top_staedte.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    log.info("Top 3: %s | flachste: %s", ", ".join(top3.stadt), flat.stadt.iloc[0])
    return df
