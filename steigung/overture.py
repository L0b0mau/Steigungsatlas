"""Zugriff auf Overture Maps (OSM-basierte Straßen + Verwaltungsgrenzen) auf AWS S3.

Overture-Transportation ist aus OpenStreetMap abgeleitet. Wir nutzen es statt
Overpass/OSMnx, weil es per Bounding-Box-Filter direkt aus GeoParquet gelesen
werden kann (kein Overpass-Server nötig).
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.fs as pfs
import pyarrow.parquet as pq

from . import config

log = logging.getLogger(__name__)
_FS = None


def filesystem() -> pfs.S3FileSystem:
    global _FS
    if _FS is None:
        kw = dict(anonymous=True, region=config.OVERTURE_REGION, connect_timeout=30, request_timeout=120)
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if proxy:
            kw["proxy_options"] = proxy
        ca = os.environ.get("AWS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
        if ca and Path(ca).exists():
            kw["tls_ca_file_path"] = ca
        elif Path("/root/.ccr/ca-bundle.crt").exists():
            kw["tls_ca_file_path"] = "/root/.ccr/ca-bundle.crt"
        _FS = pfs.S3FileSystem(**kw)
    return _FS


def dataset(theme: str, typ: str) -> ds.Dataset:
    path = f"{config.OVERTURE_BUCKET}/release/{config.OVERTURE_RELEASE}/theme={theme}/type={typ}"
    return ds.dataset(path, filesystem=filesystem(), format="parquet")


def _bbox_filter(xmin, ymin, xmax, ymax):
    b = pc.field("bbox")
    return ((pc.field("bbox", "xmin") < xmax) & (pc.field("bbox", "xmax") > xmin)
            & (pc.field("bbox", "ymin") < ymax) & (pc.field("bbox", "ymax") > ymin))


def _retry(fn, tries=4):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # Netzwerkfehler
            if i == tries - 1:
                raise
            wait = 2 ** (i + 1)
            log.warning("Overture-Abruf fehlgeschlagen (%s), neuer Versuch in %ss", e, wait)
            time.sleep(wait)


SEGMENT_COLUMNS = ["id", "names", "subtype", "class", "subclass", "connectors",
                   "road_flags", "access_restrictions", "geometry"]


def fetch_segments(bounds, cache_path: Path) -> gpd.GeoDataFrame:
    """Alle Straßensegmente (subtype=road) innerhalb einer BBox (lon/lat)."""
    if not cache_path.exists():
        xmin, ymin, xmax, ymax = bounds
        flt = _bbox_filter(xmin, ymin, xmax, ymax) & (pc.field("subtype") == "road")
        t0 = time.time()
        tb = _retry(lambda: dataset("transportation", "segment").to_table(filter=flt, columns=SEGMENT_COLUMNS))
        name = pc.struct_field(tb["names"], "primary")
        tb = tb.drop(["names"]).append_column("name", name)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(tb, cache_path)
        log.info("  Overture: %d Segmente in %.0fs geladen", tb.num_rows, time.time() - t0)
    tb = pq.read_table(cache_path)
    geom = gpd.GeoSeries.from_wkb(tb["geometry"].to_numpy(zero_copy_only=False), crs=4326)
    df = tb.drop(["geometry"]).to_pandas()
    return gpd.GeoDataFrame(df, geometry=geom, crs=4326)


# ---------------------------------------------------------------- Städteliste

def fetch_city_candidates() -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Deutsche Orte (locality, class=city) + zugehörige Grenzpolygone."""
    cache_div = config.CACHE / "divisions_de.parquet"
    cache_area = config.CACHE / "division_areas_de.parquet"
    if not cache_div.exists():
        d = dataset("divisions", "division")
        flt = (pc.field("country") == "DE") & pc.field("subtype").isin(["locality", "county", "region"]) \
            & (pc.field("population") >= 50_000)
        tb = _retry(lambda: d.to_table(filter=flt, columns=["id", "names", "subtype", "class", "population",
                                                             "wikidata", "region", "geometry"]))
        tb = tb.append_column("name", pc.struct_field(tb["names"], "primary")).drop(["names"])
        pq.write_table(tb, cache_div)
    tb = pq.read_table(cache_div)
    div = gpd.GeoDataFrame(tb.drop(["geometry"]).to_pandas(),
                           geometry=gpd.GeoSeries.from_wkb(tb["geometry"].to_numpy(zero_copy_only=False)), crs=4326)
    if not cache_area.exists():
        names = sorted(set(div["name"]))
        d = dataset("divisions", "division_area")
        flt = (pc.field("country") == "DE") & pc.field("subtype").isin(["county", "locality", "region"]) \
            & pc.field("names", "primary").isin(names)
        tb = _retry(lambda: d.to_table(filter=flt, columns=["id", "division_id", "subtype", "class", "names", "geometry"]))
        tb = tb.append_column("name", pc.struct_field(tb["names"], "primary")).drop(["names"])
        pq.write_table(tb, cache_area)
    tb = pq.read_table(cache_area)
    areas = gpd.GeoDataFrame(tb.drop(["geometry"]).to_pandas(),
                             geometry=gpd.GeoSeries.from_wkb(tb["geometry"].to_numpy(zero_copy_only=False)), crs=4326)
    return div, areas


def fetch_named_divisions(country: str, names: list[str], tag: str) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Divisions + Grenzflächen für eine feste Namensliste (z. B. österreichische Landeshauptstädte)."""
    cache_div = config.CACHE / f"divisions_{tag}.parquet"
    cache_area = config.CACHE / f"division_areas_{tag}.parquet"
    subtypes = ["locality", "localadmin", "county", "region"]

    def load(typ, cols, path):
        if not path.exists():
            flt = (pc.field("country") == country) & pc.field("subtype").isin(subtypes)
            tb = _retry(lambda: dataset("divisions", typ).to_table(filter=flt, columns=cols))
            tb = tb.append_column("name", pc.struct_field(tb["names"], "primary")).drop(["names"])
            pq.write_table(tb, path)
        tb = pq.read_table(path)
        return gpd.GeoDataFrame(tb.drop(["geometry"]).to_pandas(),
                                geometry=gpd.GeoSeries.from_wkb(tb["geometry"].to_numpy(zero_copy_only=False)),
                                crs=4326)

    div = load("division", ["id", "names", "subtype", "class", "population", "wikidata", "region", "geometry"], cache_div)
    areas = load("division_area", ["id", "division_id", "subtype", "class", "names", "geometry"], cache_area)
    return div[div["name"].isin(names)], areas
