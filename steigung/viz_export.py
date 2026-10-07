"""Daten für index.html aufbereiten und alles in eine selbstenthaltene Datei schreiben."""
from __future__ import annotations

import base64
import json
import logging

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer

from . import config, metrics
from .cities import build_city_table
from .dem import DemSampler
from .pipeline import load_network

log = logging.getLogger(__name__)
_to_ll = Transformer.from_crs(config.METRIC_CRS, 4326, always_xy=True)

SIMPLIFY_M = 4.0
TERRAIN_CELLS = 150


def _sample_xy(sampler, xs, ys):
    lon, lat = _to_ll.transform(np.asarray(xs), np.asarray(ys))
    return sampler.sample(lon, lat)


def _orient(geom, x, y):
    c = np.asarray(geom.coords)[:, :2]
    if np.hypot(*(c[0] - (x, y))) > np.hypot(*(c[-1] - (x, y))):
        c = c[::-1]
    return c


def city_payload(city: str, row, crow: dict):
    edges, nodes, _ = load_network(city, "drive")
    edges = edges[~edges["selfloop"]].copy()
    nodes = nodes.set_index("id")
    poly = gpd.GeoSeries([row.geometry], crs=4326).to_crs(config.METRIC_CRS).iloc[0]
    cx, cy = poly.centroid.x, poly.centroid.y
    sampler = DemSampler("cop30", row.geometry.bounds)
    sampler_s = DemSampler("srtm", row.geometry.bounds)

    g = metrics.grades(edges, "cop30")
    geoms = shapely.simplify(edges.geometry.values, SIMPLIFY_M)
    names, name_idx = [], {}
    xy, z, off, gr, ln, nm, cl = [], [], [0], [], [], [], []
    cls_list = ["motorway", "trunk", "primary", "secondary", "tertiary", "residential",
                "living_street", "unclassified", "service", "unknown"]
    for geom, u, v, grade, L, name, cls, struct in zip(geoms, edges["u"], edges["v"], g, edges["length"],
                                                      edges["name"], edges["cls"], edges["struct"]):
        c = _orient(geom, nodes.at[u, "x"], nodes.at[u, "y"])
        if struct:
            hu, hv = nodes.at[u, "h_cop30"], nodes.at[v, "h_cop30"]
            seg = np.r_[0, np.cumsum(np.hypot(*np.diff(c, axis=0).T))]
            zz = hu + (hv - hu) * seg / max(seg[-1], 1e-6)
        else:
            zz = _sample_xy(sampler, c[:, 0], c[:, 1])
        q = np.round(c - (cx, cy)).astype(int)
        d = np.vstack([q[:1], np.diff(q, axis=0)])
        xy.extend(d.ravel().tolist())
        z.extend(np.round(zz).astype(int).tolist())
        off.append(off[-1] + len(c))
        gr.append(int(round(1000 * grade)))
        ln.append(int(round(L)))
        if name not in name_idx:
            name_idx[name] = len(names)
            names.append(name)
        nm.append(name_idx[name])
        cl.append(cls_list.index(cls) if cls in cls_list else 9)

    # Gelände-Raster (für Relief), außerhalb der Stadt = -9999
    minx, miny, maxx, maxy = poly.bounds
    span = max(maxx - minx, maxy - miny)
    step = span / TERRAIN_CELLS
    gx = np.arange(minx, maxx + step, step)
    gy = np.arange(miny, maxy + step, step)
    GX, GY = np.meshgrid(gx, gy)
    H = _sample_xy(sampler, GX.ravel(), GY.ravel())
    inside = shapely.contains_xy(poly.buffer(step), GX.ravel(), GY.ravel())
    H = np.where(inside, np.round(H), -9999).astype(int)

    outline = poly.simplify(20)
    rings = []
    for p in (outline.geoms if outline.geom_type == "MultiPolygon" else [outline]):
        rings.append(np.round(np.asarray(p.exterior.coords)[:, :2] - (cx, cy)).astype(int).ravel().tolist())

    # steilste Strecke mit Profil
    st = metrics.steepest_stretch(edges, nodes.reset_index(), ("cop30", "srtm"))
    spot = None
    if st:
        pts = []
        cur = st["nodes"][0]
        for nid, ei in zip(st["nodes"][1:], st["edge_idx"]):
            c = _orient(edges.loc[ei].geometry, nodes.at[cur, "x"], nodes.at[cur, "y"])
            pts.extend(c.tolist() if not pts else c[1:].tolist())
            cur = nid
        line = shapely.LineString(pts)
        dist = np.arange(0, line.length, 5.0).tolist() + [line.length]
        p = shapely.line_interpolate_point(line, dist)
        px, py = shapely.get_x(p), shapely.get_y(p)
        spot = {
            "name": st["name"], "len": round(line.length, 1),
            "grade_cons": st["steigung_pct_konservativ"], "grade_cop": st["steigung_pct_cop30"],
            "grade_srtm": st["steigung_pct_srtm"],
            "xy": np.round(np.asarray(pts) - (cx, cy)).astype(int).ravel().tolist(),
            "d": [round(x, 1) for x in dist],
            "h": [round(float(x), 1) for x in _sample_xy(sampler, px, py)],
            "h_srtm": [round(float(x), 1) for x in _sample_xy(sampler_s, px, py)],
        }
    keys = ["hm_pro_km", "mittl_steigung_pct", "median_steigung_pct", "p90_steigung_pct",
            "anteil_ueber_6pct", "anteil_ueber_10pct", "anteil_ueber_15pct", "strassen_km",
            "drive_srtm_hm_pro_km", "drive_srtm_anteil_ueber_6pct", "ausreisser_n", "einwohner_osm",
            "rang_hm_pro_km", "rang_anteil_6pct", "rang_gesamt_hm_pro_km"]
    return {
        "name": city,
        "m": {k: (None if pd.isna(crow.get(k)) else float(crow.get(k))) for k in keys},
        "hist": crow["hist_km"], "hist_srtm": crow["hist_km_srtm"],
        "edges": {"xy": xy, "z": z, "off": off, "g": gr, "len": ln, "name": nm, "cls": cl},
        "names": names,
        "terrain": {"x0": round(minx - cx), "y0": round(miny - cy), "step": round(step, 2),
                    "nx": len(gx), "ny": len(gy), "h": H.tolist()},
        "outline": rings,
        "spot": spot,
    }


def _b64(path):
    return base64.b64encode(path.read_bytes()).decode()


def build_html():
    cities = build_city_table().set_index("stadt")
    df = pd.read_csv(config.RESULTS / "staedte_kennzahlen.csv")
    top = json.loads((config.RESULTS / "top_staedte.json").read_text())
    store = json.loads((config.CACHE / "city_results.json").read_text())
    sel = [r["stadt"] for r in top["top3_hm_pro_km"]] + [top["flachste_grossstadt"]["stadt"]]
    roles = ["top"] * 3 + ["ref"]
    # Österreich: steilste Landeshauptstadt, außerdem Innsbruck (Alpenstadt, häufigste Vergleichsfrage)
    # Vergleichsländer: jeweils die steilste Stadt, für Österreich außerdem Innsbruck (Alpenstadt)
    for key, cc, extra in (("oesterreich", "AT", "Innsbruck"), ("schweiz", "CH", None)):
        lst = [r["stadt"] for r in top.get(key, [])]
        for c in ([lst[0]] if lst else []) + ([extra] if extra in lst else []):
            if c not in sel:
                sel.append(c)
                roles.append(cc)
    payload = []
    for c in sel:
        crow = {**store[c], **df[df.stadt == c].iloc[0].to_dict()}
        log.info("Viz-Export %s", c)
        payload.append(city_payload(c, cities.loc[c], crow))
    ranking = df[["stadt", "land", "status", "hm_pro_km", "anteil_ueber_6pct", "p90_steigung_pct",
                  "mittl_steigung_pct", "drive_srtm_hm_pro_km", "strassen_km", "einwohner_osm"]]
    val = json.loads((config.RESULTS / "validierung.json").read_text()) \
        if (config.RESULTS / "validierung.json").exists() else []
    for v in val:
        v.pop("profil_cop30", None)
    data = {
        "cities": payload, "featured": sel, "roles": roles, "ranking": ranking.round(3).to_dict("records"),
        "bins": config.GRADE_BINS, "meta": {k: top[k] for k in ("stand", "overture_release", "methodik",
                                                                   "bekannte_grenzen", "ranking_vergleich",
                                                                   "dem_vergleich", "anzahl_staedte",
                                                                   "anzahl_staedte_at", "anzahl_staedte_ch",
                                                                   "anzahl_staedte_gesamt")},
        "validation": val,
    }
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    tpl = (config.WEB / "template.html").read_text()
    vendor = config.WEB / "vendor"
    three = (vendor / "three-bundle.min.js").read_text()
    assert "</script" not in three.lower()
    html = (tpl.replace("/*__DATA__*/null", js)
            .replace("/*__D3__*/", (vendor / "d3.min.js").read_text())
            .replace("/*__THREE__*/", three)
            .replace("__FONT_DISPLAY_500__", _b64(vendor / "chakra-petch-latin-500-normal.woff2"))
            .replace("__FONT_DISPLAY_700__", _b64(vendor / "chakra-petch-latin-700-normal.woff2"))
            .replace("__FONT_MONO_400__", _b64(vendor / "jetbrains-mono-latin-400-normal.woff2"))
            .replace("__FONT_MONO_600__", _b64(vendor / "jetbrains-mono-latin-600-normal.woff2")))
    out = config.ROOT / "index.html"
    # <title> und <meta description> gehören in den <head> (Suchmaschinen, Link-Vorschauen)
    head_tags, body = [], html
    for _ in range(2):
        body = body.lstrip()
        if body.startswith(("<title>", "<meta ")):
            end = body.index("</title>") + 8 if body.startswith("<title>") else body.index(">") + 1
            head_tags.append(body[:end])
            body = body[end:]
    out.write_text('<!doctype html>\n<html lang="de">\n<head>\n<meta charset="utf-8">\n'
                   '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                   + "\n".join(head_tags) + '\n</head>\n<body>\n' + body + '\n</body>\n</html>\n')
    # Variante ohne Dokumentgerüst (für die Veröffentlichung als Artifact)
    (config.CACHE / "index_fragment.html").write_text(html)
    log.info("index.html geschrieben (%.1f MB)", out.stat().st_size / 1e6)
    return out
