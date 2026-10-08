"""Deutsche Großstädte (>100k EW) + Vergleichsstädte (AT, CH, LU) + Wunschstädte, inkl. Verwaltungsgrenze."""
from __future__ import annotations

import logging

import geopandas as gpd
import pandas as pd

from . import config
from .overture import fetch_city_candidates, fetch_named_divisions

log = logging.getLogger(__name__)

SUBTYPE_PRIO = {"county": 0, "locality": 1, "region": 2}


# Vergleichsländer: Anzeigename -> Wikidata-ID (Ort und Grenze heißen in OSM teils verschieden)
FOREIGN = {
    "AT": dict(
        status="Landeshauptstadt AT",
        # die neun Landeshauptstädte (Wien ist zugleich Bundeshauptstadt)
        cities={"Wien": "Q1741", "Graz": "Q13298", "Linz": "Q41329", "Salzburg": "Q34713",
                "Innsbruck": "Q1735", "Klagenfurt": "Q41753", "St. Pölten": "Q82500",
                "Bregenz": "Q1737", "Eisenstadt": "Q126321"},
        names=["Wien", "Graz", "Linz", "Salzburg", "Innsbruck", "Klagenfurt", "Klagenfurt am Wörthersee",
               "St. Pölten", "Bregenz", "Eisenstadt"],
        # Statutarstädte sind in OSM Bezirke (county)
        prio={"county": 0, "locality": 1, "localadmin": 2, "region": 3},
    ),
    "CH": dict(
        status="Großstadt CH (Top 10)",
        # die zehn größten Städte; nur sechs haben > 100.000 EW
        cities={"Zürich": "Q72", "Genf": "Q71", "Basel": "Q78", "Lausanne": "Q807", "Bern": "Q70",
                "Winterthur": "Q9125", "Luzern": "Q4191", "St. Gallen": "Q25607", "Lugano": "Q7024",
                "Biel/Bienne": "Q1034"},
        names=["Zürich", "Genève", "Basel", "Lausanne", "Bern", "Winterthur", "Luzern", "St. Gallen",
               "Lugano", "Biel/Bienne"],
        # Gemeinde = localadmin; county ist in der Schweiz der Bezirk
        prio={"localadmin": 0, "locality": 1, "county": 2, "region": 3},
    ),
    "LU": dict(
        status="Hauptstadt LU",
        cities={"Luxemburg": "Q1842"},
        names=["Luxembourg"],
        # Gemeinde Luxemburg ist in Overture ein county mit derselben Wikidata-ID (der Kanton hat eine andere)
        prio={"county": 0, "localadmin": 1, "locality": 2, "region": 3},
    ),
}

# Reddit-Wishlist: von Lesern gewünschte Orte unter 100.000 EW: im Gesamtranking, aber ohne deutschen Rang
WISH = {
    "DE": dict(
        status="Wunschstadt",
        cities={"Tübingen": "Q3806", "Pirmasens": "Q14849", "Marburg": "Q3869",
                "Niedernhausen": "Q427360", "Engenhahn": "Q1342227"},
        names=["Tübingen", "Pirmasens", "Marburg", "Niedernhausen", "Engenhahn"],
        # Pirmasens ist kreisfrei (county), die übrigen kreisangehörig (locality/localadmin);
        # Engenhahn ist ein Ortsteil von Niedernhausen
        prio={"county": 0, "locality": 1, "localadmin": 2, "region": 3},
    ),
}


def build_city_table() -> gpd.GeoDataFrame:
    de = build_de_table()
    de["land"] = "DE"
    parts = [de] + [build_foreign_table(cc) for cc in FOREIGN] \
        + [build_foreign_table(cc, WISH[cc], f"{cc.lower()}_wunsch") for cc in WISH]
    return pd.concat(parts, ignore_index=True).pipe(gpd.GeoDataFrame, crs=4326)


def build_foreign_table(cc: str, spec: dict | None = None, tag: str | None = None) -> gpd.GeoDataFrame:
    spec = spec or FOREIGN[cc]
    div, areas = fetch_named_divisions(cc, spec["names"], tag or cc.lower())
    areas = areas[areas["class"] == "land"].copy()
    areas["km2"] = areas.to_crs(config.METRIC_CRS).area / 1e6
    rows = []
    for stadt, qid in spec["cities"].items():
        d = div[div["wikidata"] == qid]
        loc = d[d["subtype"] == "locality"].sort_values("population", ascending=False)
        cand = areas[areas["division_id"].isin(d["id"])].copy()
        if cand.empty or loc.empty:
            log.warning("Keine Grenze/Ort für %s", stadt)
            continue
        cand["prio"] = cand["subtype"].map(spec["prio"])
        best = cand.sort_values(["prio", "km2"], ascending=[True, False]).iloc[0]
        c = loc.iloc[0]
        rows.append(dict(
            stadt=stadt, name_osm=c["name"], bundesland=c["region"],
            einwohner_osm=None if pd.isna(c["population"]) else int(c["population"]),
            einwohner_kreis_osm=None, status=spec["status"], wikidata=qid,
            division_area_id=best["id"], grenze_typ=best["subtype"], flaeche_km2=round(best["km2"], 1),
            geometry=best.geometry, land=cc,
        ))
    return gpd.GeoDataFrame(rows, crs=4326)


def build_de_table() -> gpd.GeoDataFrame:
    div, areas = fetch_city_candidates()
    areas = areas[areas["class"] == "land"].copy()
    areas["km2"] = areas.to_crs(config.METRIC_CRS).area / 1e6

    loc = div[(div["subtype"] == "locality") & (div["class"] == "city")].copy()
    county_pop = div[div["subtype"] == "county"].groupby("wikidata")["population"].max()
    loc["pop_county"] = loc["wikidata"].map(county_pop)
    loc["pop_max"] = loc[["population", "pop_county"]].max(axis=1)
    loc = loc[loc["pop_max"] >= config.BORDERLINE_POP]

    rows = []
    for _, c in loc.iterrows():
        cand = areas[(areas["name"] == c["name"]) & areas.contains(c.geometry)].copy()
        if cand.empty:
            log.warning("Keine Grenze für %s gefunden", c["name"])
            continue
        cand["prio"] = cand["subtype"].map(SUBTYPE_PRIO)
        best = cand.sort_values(["prio", "km2"], ascending=[True, False]).iloc[0]
        if c["population"] >= config.MIN_POP or c["wikidata"] in config.AMTLICH_GROSSSTADT:
            status = "Großstadt"
        else:
            status = "Grenzfall"
        rows.append(dict(
            stadt=c["name"].replace("Cottbus - Chóśebuz", "Cottbus"),
            name_osm=c["name"], bundesland=c["region"], einwohner_osm=int(c["population"]),
            einwohner_kreis_osm=None if pd.isna(c["pop_county"]) else int(c["pop_county"]),
            status=status, wikidata=c["wikidata"], division_area_id=best["id"],
            grenze_typ=best["subtype"], flaeche_km2=round(best["km2"], 1),
            geometry=best.geometry,
        ))
    g = gpd.GeoDataFrame(rows, crs=4326).sort_values("einwohner_osm", ascending=False).reset_index(drop=True)
    return g


def slug(name: str) -> str:
    tr = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"})
    s = name.translate(tr).lower()
    return "".join(ch if ch.isalnum() else "_" for ch in s).strip("_").replace("__", "_")
