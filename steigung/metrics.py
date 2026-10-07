"""Längengewichtete Steigungskennzahlen + steilste zusammenhängende Strecke."""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from . import config


def wquantile(values, weights, q):
    idx = np.argsort(values)
    v, w = values[idx], weights[idx]
    cw = np.cumsum(w)
    if cw[-1] <= 0:
        return np.nan
    return float(np.interp(q * cw[-1], cw - 0.5 * w, v))


def grades(edges: pd.DataFrame, dem: str) -> np.ndarray:
    return np.abs(edges[f"dh_{dem}"].to_numpy()) / edges["length"].to_numpy()


def city_metrics(edges: pd.DataFrame, dem: str, prefix: str = "") -> dict:
    e = edges[~edges["selfloop"]]
    g = grades(e, dem)
    L = e["length"].to_numpy()
    dh = np.abs(e[f"dh_{dem}"].to_numpy())
    out = g > config.OUTLIER_GRADE
    gv, Lv, dhv = g[~out], L[~out], dh[~out]
    Ltot = Lv.sum()
    m = {
        "strassen_km": round(L.sum() / 1000, 1),
        "mittl_steigung_pct": 100 * float((gv * Lv).sum() / Ltot),
        "median_steigung_pct": 100 * wquantile(gv, Lv, 0.5),
        "p90_steigung_pct": 100 * wquantile(gv, Lv, 0.9),
        "anteil_ueber_6pct": 100 * float(Lv[gv > 0.06].sum() / Ltot),
        "anteil_ueber_10pct": 100 * float(Lv[gv > 0.10].sum() / Ltot),
        "anteil_ueber_15pct": 100 * float(Lv[gv > 0.15].sum() / Ltot),
        # Summe positiver Δh, über beide Fahrtrichtungen gemittelt = Σ|Δh|/2
        "hm_pro_km": float(dhv.sum() / 2 / (Ltot / 1000)),
        "hm_pro_km_inkl_ausreisser": float(dh.sum() / 2 / (L.sum() / 1000)),
        "ausreisser_n": int(out.sum()),
        "ausreisser_km": round(float(L[out].sum() / 1000), 2),
        "kanten_n": int(len(e)),
        "kanten_unter_30m_anteil_km": 100 * float(L[L < 30].sum() / L.sum()),
    }
    return {prefix + k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()}


def histogram(edges: pd.DataFrame, dem: str) -> list[float]:
    e = edges[~edges["selfloop"]]
    g = 100 * grades(e, dem)
    L = e["length"].to_numpy() / 1000
    bins = config.GRADE_BINS
    km = [float(L[(g >= lo) & (g < hi)].sum()) for lo, hi in zip(bins[:-1], bins[1:])]
    return [round(x, 2) for x in km]


def steepest_stretch(edges: pd.DataFrame, nodes: pd.DataFrame, dems=("cop30", "srtm"),
                     min_len=100.0, max_len=800.0):
    """Steilste zusammenhängende Strecke >= min_len entlang einer benannten Straße.

    Bewertet wird die Netto-Steigung zwischen Start- und Endknoten (Knotenhöhen).
    Konservativ: Score = Minimum über alle DEMs (eine Strecke zählt nur als steil,
    wenn beide Höhenmodelle das bestätigen -> unterdrückt DSM-Artefakte).
    Brücken/Tunnel und Ausreißerkanten sind ausgeschlossen.
    """
    H = {d: dict(zip(nodes["id"], nodes[f"h_{d}"])) for d in dems}
    e = edges[(~edges["selfloop"]) & (~edges["struct"]) & edges["name"].notna()].copy()
    ok = np.ones(len(e), dtype=bool)
    for d in dems:
        ok &= grades(e, d) <= config.OUTLIER_GRADE
    e = e[ok]
    adj = defaultdict(lambda: defaultdict(list))
    for i, r in zip(e.index, e.itertuples(index=False)):
        adj[r.name][r.u].append((r.v, r.length, i))
        adj[r.name][r.v].append((r.u, r.length, i))

    def score(a, b, L):
        return min(abs(H[d][b] - H[d][a]) for d in dems) / L

    best = None
    for name, A in adj.items():
        for start in A:
            stack = [(start, 0.0, [start], [])]
            while stack:
                node, L, path, eids = stack.pop()
                if L >= min_len:
                    s_ = score(start, node, L)
                    # Vorzeichen muss in allen DEMs gleich sein
                    same_dir = len({np.sign(H[d][node] - H[d][start]) for d in dems}) == 1
                    if same_dir and (best is None or s_ > best[0]):
                        best = (s_, name, list(path), list(eids), L)
                if L >= max_len:
                    continue
                for nb, l, i in A[node]:
                    if nb in path:
                        continue
                    stack.append((nb, L + l, path + [nb], eids + [i]))
    if best is None:
        return None
    s_, name, path, eids, L = best
    d0 = dems[0]
    if H[d0][path[0]] > H[d0][path[-1]]:  # immer bergauf orientieren
        path, eids = path[::-1], eids[::-1]
    out = {"name": name, "steigung_pct_konservativ": round(100 * s_, 2), "laenge_m": round(L, 1),
           "nodes": path, "edge_idx": [int(i) for i in eids]}
    for d in dems:
        out[f"steigung_pct_{d}"] = round(100 * abs(H[d][path[-1]] - H[d][path[0]]) / L, 2)
        out[f"h_start_{d}"] = round(float(H[d][path[0]]), 1)
        out[f"h_ende_{d}"] = round(float(H[d][path[-1]]), 1)
    return out
