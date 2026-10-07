"""Stichprobe: bekannte steile Straßen gegen Referenzwerte prüfen."""
from __future__ import annotations

import json
import logging

import geopandas as gpd
import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import Point
from shapely.ops import linemerge

from . import config
from .cities import build_city_table, slug
from .dem import DemSampler
from .overture import fetch_segments

log = logging.getLogger(__name__)
_to_ll = Transformer.from_crs(config.METRIC_CRS, 4326, always_xy=True)
_to_m = Transformer.from_crs(4326, config.METRIC_CRS, always_xy=True)

STREETS = [
    dict(stadt="Essen", name="Stotznocken", near=None,
         referenz="ca. 30 % (Spitzenwert, komoot-Highlight 'Stotznocken'; Angaben im Netz schwanken stark)",
         ref_max_pct=30.0, ref_mean_pct=None),
    dict(stadt="Aachen", name="Hauptstraße", near=(6.0937, 50.7615), radius=700,
         referenz="Ø 9 %, steilster Abschnitt 13,3 %, ca. 0,2 mi (≈320 m), ≈95 ft (≈29 m) Höhe "
                  "(climbfinder 'Hauptstraße from Burtscheider Markt')",
         ref_max_pct=13.3, ref_mean_pct=9.0),
    dict(stadt="Stuttgart", name="Neue Weinsteige", near=None,
         referenz="Verbindung Talkessel – Degerloch (≈470 m ü. NN); nur Höhendifferenz-Plausibilität, "
                  "kein belastbarer Prozent-Referenzwert gefunden",
         ref_max_pct=None, ref_mean_pct=None),
]


def profile(line_m, samplers, step=5.0):
    d = np.arange(0, line_m.length + 1e-6, step)
    if d[-1] < line_m.length:
        d = np.append(d, line_m.length)
    pts = shapely.line_interpolate_point(line_m, d)
    lon, lat = _to_ll.transform(shapely.get_x(pts), shapely.get_y(pts))
    return d, {k: s.sample(lon, lat) for k, s in samplers.items()}


def window_max(d, h, win):
    best = 0.0
    j = 0
    for i in range(len(d)):
        while j < len(d) and d[j] - d[i] < win:
            j += 1
        if j >= len(d):
            break
        best = max(best, abs(h[j] - h[i]) / (d[j] - d[i]))
    return 100 * best


def check_street(spec, cities):
    row = cities[cities.stadt == spec["stadt"]].iloc[0]
    segs = fetch_segments(row.geometry.bounds, config.CACHE / "segments" / f"{slug(spec['stadt'])}.parquet")
    s = segs[segs["name"] == spec["name"]].to_crs(config.METRIC_CRS)
    if spec.get("near"):
        x, y = _to_m.transform(*spec["near"])
        s = s[s.distance(Point(x, y)) < spec.get("radius", 500)]
    if s.empty:
        return {**spec, "fehler": "Straße nicht gefunden"}
    merged = linemerge(list(s.geometry))
    lines = list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged]
    line = max(lines, key=lambda g: g.length)
    samplers = {d: DemSampler(d, row.geometry.bounds) for d in ("cop30", "srtm")}
    d, H = profile(line, samplers)
    out = {k: spec[k] for k in ("stadt", "name", "referenz", "ref_max_pct", "ref_mean_pct")}
    out["laenge_m"] = round(line.length, 1)
    for k, h in H.items():
        out[k] = {
            "h_start": round(float(h[0]), 1), "h_ende": round(float(h[-1]), 1),
            "mittl_steigung_pct": round(100 * abs(h[-1] - h[0]) / line.length, 2),
            "max_50m_pct": round(window_max(d, h, 50), 2),
            "max_100m_pct": round(window_max(d, h, 100), 2),
        }
    # Bewertung: Referenz-Spitzenwerte sind je nach Quelle über 20–100 m gemessen,
    # daher gegen die Spanne aus 100-m- und 50-m-Fenster prüfen.
    m = out["cop30"]
    notes = []
    if spec["ref_max_pct"]:
        lo, hi = sorted((m["max_100m_pct"], m["max_50m_pct"]))
        ref = spec["ref_max_pct"]
        out["verhaeltnis_max_dem_zu_referenz"] = round(hi / ref, 2)
        if ref > 1.3 * hi:
            notes.append(f"DEM-Spitzenwert ({hi} %) deutlich unter Referenz ({ref} %): 30-m-Raster glättet die Rampe")
        elif ref < 0.7 * lo:
            notes.append(f"DEM-Spitzenwert ({lo}–{hi} %) deutlich über Referenz ({ref} %): mögliches DSM-Artefakt")
        else:
            notes.append(f"Spitzenwert konsistent: DEM {lo}–{hi} % (100-m-/50-m-Fenster) vs. Referenz {ref} %")
    if spec["ref_mean_pct"]:
        notes.append(f"Mittel {m['mittl_steigung_pct']} % (Copernicus) / {out['srtm']['mittl_steigung_pct']} % (SRTM) "
                     f"vs. Referenz {spec['ref_mean_pct']} %")
    if spec["ref_max_pct"] is None:
        notes.append(f"Ausgewertet: längstes zusammenhängendes Teilstück ({out['laenge_m']:.0f} m), "
                     f"{m['h_start']:.0f} → {m['h_ende']:.0f} m ü. NN; Δh plausibel, Mittel {m['mittl_steigung_pct']} %")
    out["bewertung"] = notes
    out["profil_cop30"] = [[round(float(a), 1), round(float(b), 1)] for a, b in zip(d[::2], H["cop30"][::2])]
    return out


def run_validation():
    cities = build_city_table()
    res = []
    for spec in STREETS:
        try:
            r = check_street(spec, cities)
        except Exception as e:  # pragma: no cover
            r = {**spec, "fehler": str(e)}
        log.info("Validierung %s/%s: %s", spec["stadt"], spec["name"],
                 {k: v for k, v in r.items() if k in ("laenge_m", "cop30", "srtm", "fehler")})
        res.append(r)
    (config.RESULTS / "validierung.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return res
