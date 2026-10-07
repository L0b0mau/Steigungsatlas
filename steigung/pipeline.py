"""Verarbeitung einer Stadt: Segmente laden -> Netz bauen -> Kennzahlen."""
from __future__ import annotations

import json
import logging
import time

import geopandas as gpd
import pandas as pd

from . import config, metrics
from .cities import slug
from .dem import DemSampler
from .network import build_network
from .overture import fetch_segments

log = logging.getLogger(__name__)
DEMS = ("cop30", "srtm")


def net_paths(city: str, kind: str):
    d = config.CACHE / "networks"
    s = slug(city)
    return d / f"{s}_{kind}_edges.parquet", d / f"{s}_{kind}_nodes.parquet", d / f"{s}_{kind}_info.json"


def load_network(city: str, kind: str):
    pe, pn, pi = net_paths(city, kind)
    return gpd.read_parquet(pe), pd.read_parquet(pn), json.loads(pi.read_text())


def process_city(row, kinds=("drive", "bike"), dems=DEMS, force=False) -> dict:
    city = row["stadt"]
    poly = row["geometry"]
    t0 = time.time()
    res = {"stadt": city}
    segs = None
    samplers = None
    for kind in kinds:
        pe, pn, pi = net_paths(city, kind)
        if force or not pe.exists():
            if segs is None:
                segs = fetch_segments(poly.bounds, config.CACHE / "segments" / f"{slug(city)}.parquet")
                samplers = {d: DemSampler(d, poly.bounds) for d in dems}
            poly_m = gpd.GeoSeries([poly], crs=4326).to_crs(config.METRIC_CRS).iloc[0]
            edges, nodes, info = build_network(segs, poly_m, kind, samplers)
            pe.parent.mkdir(parents=True, exist_ok=True)
            edges.to_parquet(pe)
            nodes.to_parquet(pn)
            pi.write_text(json.dumps(info))
        edges, nodes, info = load_network(city, kind)
        for dem in dems:
            pre = "" if (kind == "drive" and dem == "cop30") else f"{kind}_{dem}_"
            res.update(metrics.city_metrics(edges, dem, prefix=pre))
        if kind == "drive":
            res["kontrahiert_km"] = round(info["kontrahiert_km"], 2)
            res["brueckentunnel_knoten_interpoliert"] = info.get("strukturknoten_interpoliert_cop30")
            res["hist_km"] = metrics.histogram(edges, "cop30")
            res["hist_km_srtm"] = metrics.histogram(edges, "srtm")
            st = metrics.steepest_stretch(edges, nodes, dems)
            if st:
                res.update(steilste_strasse=st["name"],
                           steilste_strecke_pct_konservativ=st["steigung_pct_konservativ"],
                           steilste_strecke_pct_cop30=st["steigung_pct_cop30"],
                           steilste_strecke_pct_srtm=st["steigung_pct_srtm"],
                           steilste_strecke_m=st["laenge_m"])
    log.info("%-22s fertig in %.0fs  (Hm/km %.1f, >6%% %.1f%%)", city, time.time() - t0,
             res.get("hm_pro_km", float("nan")), res.get("anteil_ueber_6pct", float("nan")))
    return res
