"""Straßennetz aus Overture-Segmenten bauen (OSMnx-artig, ungerichtet, vereinfacht).

Schritte
1. Segmente nach Netztyp filtern (drive / bike, angelehnt an OSMnx-Filter).
2. Segmente an Overture-Connectoren (= OSM-Knoten mit Verknüpfung) teilen.
3. Knotenhöhen bilinear aus dem DEM.
4. Brücken/Tunnel: Knoten, die ausschließlich an Brücken-/Tunnelkanten hängen,
   bekommen eine linear (über die Netzdistanz) zwischen den Brückenenden
   interpolierte Höhe statt des DEM-Werts (DEM misst Tal bzw. Bergoberfläche).
5. Vereinfachen: Knoten mit Grad 2 entfernen (wie osmnx.simplify_graph).
6. Kanten < 10 m kontrahieren (Endknoten verschmelzen, Höhe = Mittelwert).
"""
from __future__ import annotations

import logging
from collections import defaultdict

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from shapely.geometry import LineString
from shapely.ops import substring, linemerge

from . import config

log = logging.getLogger(__name__)

DRIVE_CLASSES = {"motorway", "trunk", "primary", "secondary", "tertiary", "residential",
                 "living_street", "unclassified", "service", "unknown"}
DRIVE_EXCL_SUBCLASS = {"parking_aisle", "driveway"}
BIKE_EXCL_CLASSES = {"motorway", "footway", "steps", "bridleway"}
DROP_FLAGS = {"is_under_construction", "is_abandoned"}
STRUCT_FLAGS = {"is_bridge", "is_tunnel"}

_to_ll = Transformer.from_crs(config.METRIC_CRS, 4326, always_xy=True)


def _l(x):
    return [] if x is None else list(x)


def _whole(rule) -> bool:
    return rule.get("between") is None


def _access_flags(rules):
    """-> (private, no_motor, no_bike) nur für segmentweite, unbedingte Regeln."""
    private = no_motor = no_bike = False
    allow_dest = False
    if rules is None:
        return private, no_motor, no_bike
    for r in rules:
        if not _whole(r):
            continue
        w = r.get("when") or {}
        if w.get("heading") or w.get("during") or _l(w.get("vehicle")):
            continue
        modes = set(_l(w.get("mode")))
        rec = set(_l(w.get("recognized")))
        using = set(_l(w.get("using")))
        at = r["access_type"]
        if at == "allowed" and "as_private" in rec and (not modes or modes & {"motor_vehicle", "vehicle"}):
            private = True
        if at == "allowed" and "at_destination" in using:
            allow_dest = True
        if at == "denied" and not rec and not using:
            if not modes:
                no_motor = no_bike = True
            if modes & {"motor_vehicle", "vehicle", "motorcar"}:
                no_motor = True
            if modes & {"bicycle", "vehicle"}:
                no_bike = True
    if allow_dest:
        no_motor = False
    return private, no_motor, no_bike


def filter_segments(segs: gpd.GeoDataFrame, kind: str) -> gpd.GeoDataFrame:
    keep = []
    for cls, sub, flags, acc in zip(segs["class"], segs["subclass"], segs["road_flags"],
                                    segs["access_restrictions"]):
        whole_flags = set()
        if flags is not None:
            for f in flags:
                if _whole(f):
                    whole_flags.update(f["values"])
        if whole_flags & DROP_FLAGS:
            keep.append(False)
            continue
        private, no_motor, no_bike = _access_flags(acc)
        if kind == "drive":
            ok = cls in DRIVE_CLASSES and sub not in DRIVE_EXCL_SUBCLASS and not private and not no_motor
        elif kind == "bike":
            ok = (cls not in BIKE_EXCL_CLASSES and sub not in {"sidewalk", "crosswalk"}
                  and not private and not no_bike)
        elif kind == "all":
            ok = True
        else:
            raise ValueError(kind)
        keep.append(ok)
    return segs[np.array(keep, dtype=bool)]


def _struct_ranges(flags):
    out = []
    if flags is None:
        return out
    for f in flags:
        if set(f["values"]) & STRUCT_FLAGS:
            b = f.get("between")
            out.append((0.0, 1.0) if b is None else (float(b[0]), float(b[1])))
    return out


def split_segments(segs_m: gpd.GeoDataFrame):
    """Segmente (metrisch) an Connectoren teilen -> Rohkanten + Knotenkoordinaten."""
    nodes = {}
    rows = []
    for sid, name, cls, conns, flags, geom in zip(segs_m["id"], segs_m["name"], segs_m["class"],
                                                  segs_m["connectors"], segs_m["road_flags"], segs_m.geometry):
        if geom is None or geom.is_empty or conns is None or len(conns) < 2:
            continue
        L = geom.length
        cs = sorted(((float(c["at"]), c["connector_id"]) for c in conns), key=lambda t: t[0])
        sr = _struct_ranges(flags)
        for (a0, c0), (a1, c1) in zip(cs[:-1], cs[1:]):
            if a1 - a0 <= 0:
                continue
            piece = substring(geom, a0, a1, normalized=True)
            if piece.geom_type != "LineString" or piece.length == 0:
                continue
            for cid, pt in ((c0, piece.coords[0]), (c1, piece.coords[-1])):
                if cid not in nodes:
                    nodes[cid] = pt[:2]
            mid = 0.5 * (a0 + a1)
            struct = any(lo - 1e-9 <= mid <= hi + 1e-9 for lo, hi in sr)
            rows.append((c0, c1, piece.length, name, cls, struct, sid, piece))
    edges = pd.DataFrame(rows, columns=["u", "v", "length", "name", "cls", "struct", "seg_id", "geometry"])
    return nodes, edges


def _interpolate_structures(G: nx.MultiGraph, h: dict) -> int:
    """Höhen von Knoten auf Brücken/in Tunneln linear zwischen den Enden interpolieren."""
    S = nx.Graph()
    for u, v, d in G.edges(data=True):
        if d["struct"] and u != v:
            w = d["length"]
            if S.has_edge(u, v):
                w = min(w, S[u][v]["weight"])
            S.add_edge(u, v, weight=w)
    n_fixed = 0
    for comp in nx.connected_components(S):
        interior = [n for n in comp if all(d["struct"] for _, _, d in G.edges(n, data=True))]
        if not interior:
            continue
        anchors = [n for n in comp if n not in set(interior)]
        if not anchors:
            continue
        sub = S.subgraph(comp)
        dist = {a: nx.single_source_dijkstra_path_length(sub, a, weight="weight") for a in anchors}
        for n in interior:
            ds = sorted((dist[a].get(n, np.inf), a) for a in anchors)
            ds = [t for t in ds if np.isfinite(t[0])]
            if not ds:
                continue
            if len(ds) == 1:
                h[n] = h[ds[0][1]]
            else:
                (d1, a1), (d2, a2) = ds[0], ds[1]
                h[n] = (h[a1] * d2 + h[a2] * d1) / (d1 + d2) if d1 + d2 > 0 else h[a1]
            n_fixed += 1
    return n_fixed


def _merge_geoms(parts):
    """LineStrings in Kettenreihenfolge zusammenfügen."""
    coords = list(parts[0].coords)
    for p in parts[1:]:
        pc_ = list(p.coords)
        if np.allclose(coords[-1], pc_[0]):
            coords += pc_[1:]
        elif np.allclose(coords[-1], pc_[-1]):
            coords += pc_[::-1][1:]
        elif np.allclose(coords[0], pc_[-1]):
            coords = pc_ + coords[1:]
        elif np.allclose(coords[0], pc_[0]):
            coords = pc_[::-1] + coords[1:]
        else:
            coords += pc_
    return LineString(coords)


def simplify(G: nx.MultiGraph) -> nx.MultiGraph:
    """Knoten mit genau zwei verschiedenen Nachbarn entfernen (Kettenbildung)."""
    def is_pass(n):
        return G.degree(n) == 2 and len(set(G.neighbors(n))) == 2

    H = nx.MultiGraph()
    H.add_nodes_from((n, d) for n, d in G.nodes(data=True) if not is_pass(n))
    seen = set()
    for start in list(H.nodes):
        for _, nbr, k, d in G.edges(start, keys=True, data=True):
            eid = (min(start, nbr), max(start, nbr), k) if start != nbr else (start, nbr, k)
            if eid in seen:
                continue
            chain = [(start, nbr, k, d)]
            seen.add(eid)
            prev, cur = start, nbr
            while cur not in H:
                nxt = [(cur, b, kk, dd) for _, b, kk, dd in G.edges(cur, keys=True, data=True)
                       if not (b == prev and (min(cur, b), max(cur, b), kk) in seen)]
                if not nxt:
                    break
                e = nxt[0]
                seen.add((min(e[0], e[1]), max(e[0], e[1]), e[2]))
                chain.append(e)
                prev, cur = cur, e[1]
            lengths = [c[3]["length"] for c in chain]
            names = defaultdict(float)
            for c in chain:
                names[c[3]["name"]] += c[3]["length"]
            best_name = max(names.items(), key=lambda t: (t[0] is not None, t[1]))[0]
            cls = max(chain, key=lambda c: c[3]["length"])[3]["cls"]
            struct_len = sum(c[3]["length"] for c in chain if c[3]["struct"])
            H.add_edge(start, cur, length=float(sum(lengths)), name=best_name, cls=cls,
                       struct=struct_len > 0.5 * sum(lengths), struct_len=struct_len,
                       geometry=_merge_geoms([c[3]["geometry"] for c in chain]))
    # isolierte Ringe ohne Endknoten gehen hier verloren (für Steigung irrelevant: Δh=0)
    return H


def contract_short(G: nx.MultiGraph, h: dict, min_len=config.MIN_EDGE_LEN_M):
    """Kanten < min_len kontrahieren. Gibt (neuer Graph, Höhen, kontrahierte Länge) zurück."""
    parent = {n: n for n in G.nodes}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for u, v, d in G.edges(data=True):
        if u != v and d["length"] < min_len:
            ru, rv = find(u), find(v)
            if ru != rv:
                parent[ru] = rv
    groups = defaultdict(list)
    for n in G.nodes:
        groups[find(n)].append(n)
    H = nx.MultiGraph()
    h2 = {}
    for root, members in groups.items():
        xs = [G.nodes[m]["x"] for m in members]
        ys = [G.nodes[m]["y"] for m in members]
        H.add_node(root, x=float(np.mean(xs)), y=float(np.mean(ys)), n_merged=len(members))
        h2[root] = float(np.mean([h[m] for m in members]))
    dropped = 0.0
    for u, v, d in G.edges(data=True):
        ru, rv = find(u), find(v)
        if ru == rv:
            dropped += d["length"]
            continue
        H.add_edge(ru, rv, **d)
    return H, h2, dropped


def build_network(segs: gpd.GeoDataFrame, polygon_m, kind: str, samplers: dict):
    """-> (edges GeoDataFrame [metrisch], nodes DataFrame, info dict)."""
    s = filter_segments(segs, kind)
    s = s.to_crs(config.METRIC_CRS)
    nodes_xy, raw = split_segments(s)
    if raw.empty:
        raise RuntimeError("leeres Netz")
    # nur Kanten, deren Mittelpunkt im Stadtgebiet liegt
    mids = shapely.line_interpolate_point(raw["geometry"].values, 0.5, normalized=True)
    inside = shapely.contains_xy(polygon_m, shapely.get_x(mids), shapely.get_y(mids))
    shapely.prepare(polygon_m)
    raw = raw[inside].reset_index(drop=True)

    G = nx.MultiGraph()
    used = set(raw["u"]) | set(raw["v"])
    for n in used:
        x, y = nodes_xy[n]
        G.add_node(n, x=x, y=y)
    for r in raw.itertuples(index=False):
        G.add_edge(r.u, r.v, length=r.length, name=r.name, cls=r.cls, struct=r.struct, geometry=r.geometry)

    ids = list(G.nodes)
    xs = np.array([G.nodes[n]["x"] for n in ids])
    ys = np.array([G.nodes[n]["y"] for n in ids])
    lon, lat = _to_ll.transform(xs, ys)
    info = {"kind": kind, "segmente": int(len(s)), "rohkanten": int(len(raw))}

    heights = {}
    for dem, sampler in samplers.items():
        hv = sampler.sample(lon, lat)
        h = dict(zip(ids, hv))
        info[f"strukturknoten_interpoliert_{dem}"] = _interpolate_structures(G, h)
        heights[dem] = h

    total_raw_len = float(raw["length"].sum())
    Gs = simplify(G)
    # gleiche Kontraktion für alle DEMs: Höhe je DEM separat mitteln
    first = next(iter(heights))
    Gc, _, dropped = contract_short(Gs, heights[first])
    hc = {}
    for dem, h in heights.items():
        _, hc[dem], _ = contract_short(Gs, h)
    info.update(rohlaenge_km=total_raw_len / 1000, kontrahiert_km=dropped / 1000,
                knoten=Gc.number_of_nodes(), kanten=Gc.number_of_edges())

    recs = []
    for u, v, d in Gc.edges(data=True):
        rec = dict(u=u, v=v, length=d["length"], name=d["name"], cls=d["cls"], struct=d["struct"],
                   geometry=d["geometry"], selfloop=(u == v))
        for dem in heights:
            rec[f"dh_{dem}"] = hc[dem][v] - hc[dem][u]
        recs.append(rec)
    edges = gpd.GeoDataFrame(recs, geometry="geometry", crs=config.METRIC_CRS)
    nodes = pd.DataFrame({"id": list(Gc.nodes), "x": [Gc.nodes[n]["x"] for n in Gc.nodes],
                          "y": [Gc.nodes[n]["y"] for n in Gc.nodes]})
    for dem in heights:
        nodes[f"h_{dem}"] = nodes["id"].map(hc[dem])
    return edges, nodes, info
