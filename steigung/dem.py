"""Höhenmodelle: Kacheln laden, lokal cachen, bilinear samplen.

cop30 : Copernicus DEM GLO-30 (1x1°-COG-Kacheln, AWS Open Data). Achtung: DSM,
        d. h. Oberflächenmodell inkl. Gebäude/Vegetation, kein Geländemodell.
srtm  : SRTM 1" aus den AWS Terrain Tiles (Skadi-Format, .hgt.gz).
"""
from __future__ import annotations

import gzip
import logging
import os
import math
import shutil
import time
from pathlib import Path

import numpy as np
import rasterio
import requests
import rasterio.errors
import rasterio.windows
from scipy.ndimage import distance_transform_edt, map_coordinates

from . import config

log = logging.getLogger(__name__)


class DemDownloadError(RuntimeError):
    pass


def _tile_names(bounds):
    xmin, ymin, xmax, ymax = bounds
    for lat in range(math.floor(ymin), math.floor(ymax) + 1):
        for lon in range(math.floor(xmin), math.floor(xmax) + 1):
            yield lat, lon


def _download(url: str, dest: Path, tries: int = 4):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + f".{os.getpid()}.part")
    for i in range(tries):
        try:
            with requests.get(url, stream=True, timeout=120) as r:
                if r.status_code == 404:
                    return False  # Kachel existiert nicht (z. B. reines Meer)
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    shutil.copyfileobj(r.raw, f, length=1 << 20)
            os.replace(tmp, dest)
            return True
        except requests.RequestException as e:
            if i == tries - 1:
                raise DemDownloadError(f"Download fehlgeschlagen: {url} ({e})") from e
            time.sleep(2 ** (i + 1))


def tile_path(source: str, lat: int, lon: int) -> Path | None:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    if source == "cop30":
        name = f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"
        dest = config.CACHE / "dem" / "cop30" / f"{name}.tif"
        url = f"https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif"
    elif source == "srtm":
        name = f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}"
        dest = config.CACHE / "dem" / "srtm" / f"{name}.hgt"
        url = f"https://elevation-tiles-prod.s3.amazonaws.com/skadi/{ns}{abs(lat):02d}/{name}.hgt.gz"
    else:
        raise ValueError(source)
    if dest.exists():
        return dest
    log.info("  DEM-Download %s %s", source, name)
    if source == "srtm":
        gz = dest.with_suffix(f".{os.getpid()}.hgt.gz")
        if not _download(url, gz):
            return None
        tmp = dest.with_suffix(f".{os.getpid()}.tmp")
        with gzip.open(gz, "rb") as fi, open(tmp, "wb") as fo:
            shutil.copyfileobj(fi, fo)
        os.replace(tmp, dest)
        gz.unlink()
    elif not _download(url, dest):
        return None
    return dest


class DemSampler:
    """Bilineares Sampling direkt in den Originalkacheln (kein Resampling/Mosaik).

    Jeder Punkt wird in der Kachel interpoliert, in der er liegt; an Kachelrändern
    wird der Randpixel fortgesetzt (Fehler < 1/2 Pixel). NaN/Nodata-Pixel werden
    gezählt und durch den nächsten gültigen Nachbarn ersetzt.
    """

    def __init__(self, source: str, bounds, pad: float = 0.01):
        self.source = source
        xmin, ymin, xmax, ymax = bounds
        b = (xmin - pad, ymin - pad, xmax + pad, ymax + pad)
        self.tiles = {}
        self.filled = 0
        for lat, lon in _tile_names(b):
            p = tile_path(source, lat, lon)
            if p is None:
                continue
            with rasterio.open(p) as src:
                win = rasterio.windows.from_bounds(*b, transform=src.transform).round_offsets().round_lengths()
                try:
                    win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
                except rasterio.errors.WindowError:
                    continue  # Kachel berührt den Puffer nur auf der Kante
                if win.width < 1 or win.height < 1:
                    continue
                arr = src.read(1, window=win).astype("float32")
                tr = src.window_transform(win)
                nod = src.nodata
            bad = ~np.isfinite(arr) | (arr <= -1000)
            if nod is not None:
                bad |= arr == nod
            if bad.any():
                self.filled += int(bad.sum())
                idx = distance_transform_edt(bad, return_distances=False, return_indices=True)
                arr = arr[tuple(idx)]
            self.tiles[(lat, lon)] = (arr, tr)
        if not self.tiles:
            raise DemDownloadError(f"Keine DEM-Kacheln für {bounds}")
        if self.filled:
            log.warning("  %s: %d Nodata-Pixel durch Nachbarwerte ersetzt", source, self.filled)
        first = next(iter(self.tiles.values()))[1]
        self.res_m = abs(first.e) * 111_320

    def sample(self, lon, lat) -> np.ndarray:
        lon = np.atleast_1d(np.asarray(lon, dtype="float64"))
        lat = np.atleast_1d(np.asarray(lat, dtype="float64"))
        out = np.full(lon.shape, np.nan)
        klat, klon = np.floor(lat).astype(int), np.floor(lon).astype(int)
        for (tl, tn), (arr, tr) in self.tiles.items():
            m = (klat == tl) & (klon == tn)
            if not m.any():
                continue
            col, row = ~tr * (lon[m], lat[m])
            coords = np.vstack([np.asarray(row) - 0.5, np.asarray(col) - 0.5])
            out[m] = map_coordinates(arr, coords, order=1, mode="nearest")
        if np.isnan(out).any():
            raise DemDownloadError(f"{int(np.isnan(out).sum())} Punkte ohne DEM-Kachel ({self.source})")
        return out
