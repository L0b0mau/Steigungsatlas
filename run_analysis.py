#!/usr/bin/env python
"""Steigungsanalyse deutscher Großstädte.

    python run_analysis.py                 # alle Großstädte (+ Grenzfälle)
    python run_analysis.py --test          # nur Wuppertal, Münster, Stuttgart
    python run_analysis.py --cities Essen Aachen
    python run_analysis.py --skip-analysis # nur Auswertung/HTML aus dem Cache neu bauen

Downloads (Overture-Segmente, DEM-Kacheln) und berechnete Netze liegen in ./cache.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd

from steigung import config
from steigung.cities import build_city_table

log = logging.getLogger("run")
TEST_CITIES = ["Wuppertal", "Münster", "Stuttgart"]


def _worker(row_dict):
    import geopandas as gpd  # noqa: F401  (Prozess-Init)
    from steigung.pipeline import process_city
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        return process_city(row_dict), None
    except Exception as e:  # einzelne Städte überspringen, am Ende listen
        return {"stadt": row_dict["stadt"]}, f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"


def run(cities: pd.DataFrame, workers: int):
    results, failed = [], {}
    rows = [r for _, r in cities.iterrows()]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_worker, r.to_dict()): r["stadt"] for r in rows}
        for i, f in enumerate(as_completed(futs), 1):
            res, err = f.result()
            if err:
                failed[res["stadt"]] = err
                log.error("[%d/%d] %s FEHLER: %s", i, len(rows), res["stadt"], err.splitlines()[0])
            else:
                results.append(res)
                log.info("[%d/%d] %s ok (%.0f min)", i, len(rows), res["stadt"], (time.time() - t0) / 60)
    return results, failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--cities", nargs="*")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--skip-analysis", action="store_true")
    ap.add_argument("--skip-html", action="store_true")
    args = ap.parse_args()

    config.RESULTS.mkdir(exist_ok=True)
    (config.ROOT / "logs").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(config.ROOT / "logs" / "run.log")])

    cities = build_city_table()
    cities.drop(columns="geometry").to_csv(config.DATA / "staedte.csv", index=False)
    grenzen = cities[["stadt", "geometry"]].copy()
    grenzen["geometry"] = grenzen.geometry.simplify(0.0002)  # ~15 m, nur zur Dokumentation
    grenzen.to_file(config.DATA / "staedte_grenzen.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)
    log.info("%d Städte (%d Großstädte, %d Grenzfälle)", len(cities),
             (cities.status == "Großstadt").sum(), (cities.status == "Grenzfall").sum())

    sel = cities
    if args.test:
        sel = cities[cities.stadt.isin(TEST_CITIES)]
    elif args.cities:
        sel = cities[cities.stadt.isin(args.cities)]

    raw_path = config.CACHE / "city_results.json"
    store = json.loads(raw_path.read_text()) if raw_path.exists() else {}
    failed = {}
    if not args.skip_analysis:
        results, failed = run(sel, args.workers)
        for r in results:
            store[r["stadt"]] = r
        raw_path.write_text(json.dumps(store, ensure_ascii=False))

    from steigung.report import write_results
    write_results(cities, store, failed)

    if not args.skip_html:
        from steigung.validate import run_validation
        from steigung.viz_export import build_html
        run_validation()
        build_html(only=set(sel.stadt) if (args.cities or args.test) else None, workers=args.workers)
    if failed:
        log.warning("Fehlgeschlagene Städte: %s", ", ".join(failed))


if __name__ == "__main__":
    main()
