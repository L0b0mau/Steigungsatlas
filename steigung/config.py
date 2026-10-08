from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
DATA = ROOT / "data"
RESULTS = ROOT / "results"
WEB = ROOT / "web"

OVERTURE_BUCKET = "overturemaps-us-west-2"
OVERTURE_RELEASE = os.environ.get("OVERTURE_RELEASE", "2026-09-23.1")
OVERTURE_REGION = "us-west-2"

# Metrisches Bezugssystem für Längen (UTM 32N, deckt ganz DE ausreichend ab)
METRIC_CRS = 25832

MIN_EDGE_LEN_M = 10.0      # kürzere Kanten werden kontrahiert (DEM-Rauschen)
OUTLIER_GRADE = 0.40       # > 40 % = unplausibel -> markiert, nicht gelöscht
MIN_POP = 100_000
# Amtlich über 100.000 EW, obwohl der OSM-Tag darunter liegt (Wikidata-ID -> Name)
AMTLICH_GROSSSTADT = {"Q3167": "Siegen"}
BORDERLINE_POP = 97_000    # 97k..100k: als Grenzfall mitgerechnet und markiert

GRADE_BINS = [0, 2, 4, 6, 8, 10, 12, 15, 20, 30, 40, 1000]  # in %

DEM_SOURCES = {
    "cop30": "Copernicus DEM GLO-30 (DSM, 1\", AWS Open Data)",
    "srtm": "SRTM 1\" via AWS Terrain Tiles (Skadi)",
}
