import os
import math
import requests
from datetime import datetime, timedelta

CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'imagery_cache')

_NEUTRAL = {
    "satellite_image_path": None,
    "satellite_source": "none",
    "capture_date": None,
    "ndvi_value": 0.0,
    "ndvi_interpretation": "unknown",
    "change_detected": False,
    "change_magnitude": 0.0,
    "construction_signal": False,
    "satellite_score": 50,
    "error": None,
}


def _ndvi_label(ndvi: float) -> str:
    if ndvi < 0.0:
        return "water"
    elif ndvi < 0.1:
        return "bare_ground"
    elif ndvi < 0.3:
        return "built_up"
    else:
        return "vegetation"


def _latlon_to_gibs_tile(lat: float, lon: float, zoom: int = 8):
    """Convert lat/lon to GIBS WMTS tile row/col for epsg4326."""
    n = 2 ** zoom
    col = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    row = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return zoom, row, col


def _fetch_gibs_tile(lat: float, lon: float, date_str: str, osm_id: str) -> str | None:
    """Fetch NASA GIBS tile for a given date. Returns saved path or None."""
    try:
        zoom, row, col = _latlon_to_gibs_tile(lat, lon, zoom=8)
        url = (
            f"https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/"
            f"MODIS_Terra_CorrectedReflectance_TrueColor/default/"
            f"{date_str}/250m/{zoom}/{row}/{col}.jpg"
        )
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        cache_dir = os.path.join(CACHE_DIR, str(osm_id))
        os.makedirs(cache_dir, exist_ok=True)
        path = os.path.join(cache_dir, f"satellite_{date_str}.jpg")
        with open(path, "wb") as f:
            f.write(resp.content)
        return path
    except Exception as e:
        print(f"[satellite_fetcher] GIBS tile fetch failed for {date_str}: {e}")
        return None


def _pixel_change_magnitude(path_current: str, path_old: str) -> float:
    """Compare two images pixel-wise. Returns 0-1 change fraction."""
    try:
        from PIL import Image
        import numpy as np
        img1 = np.array(Image.open(path_current).convert("RGB"), dtype=float)
        img2 = np.array(Image.open(path_old).convert("RGB"), dtype=float)
        if img1.shape != img2.shape:
            img2 = np.array(
                Image.open(path_old).convert("RGB").resize(
                    (img1.shape[1], img1.shape[0])
                ),
                dtype=float,
            )
        diff = np.abs(img1 - img2).mean(axis=2)  # per-pixel mean channel diff
        changed_pixels = (diff > 30).sum()
        total_pixels = diff.size
        return round(float(changed_pixels) / total_pixels, 4)
    except Exception as e:
        print(f"[satellite_fetcher] pixel_change_magnitude error: {e}")
        return 0.0


def _try_openeo(lat: float, lon: float, osm_id: str) -> dict | None:
    """Attempt Sentinel-2 NDVI via OpenEO. Returns partial result or None."""
    try:
        import openeo  # type: ignore
        connection = openeo.connect("https://openeo.cloud")
        bbox = {
            "west": lon - 0.002,
            "south": lat - 0.002,
            "east": lon + 0.002,
            "north": lat + 0.002,
        }
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        start_date = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")

        dc = connection.load_collection(
            "SENTINEL2_L2A",
            spatial_extent=bbox,
            temporal_extent=[start_date, end_date],
            bands=["B04", "B08"],
            max_cloud_cover=50,
        )
        nir = dc.band("B08")
        red = dc.band("B04")
        ndvi_cube = (nir - red) / (nir + red)
        ndvi_mean = ndvi_cube.reduce_dimension(reducer="mean", dimension="t")

        cache_dir = os.path.join(CACHE_DIR, str(osm_id))
        os.makedirs(cache_dir, exist_ok=True)
        out_path = os.path.join(cache_dir, "ndvi_openeo.tif")
        ndvi_mean.download(out_path)

        # Read NDVI value
        try:
            import rasterio  # type: ignore
            with rasterio.open(out_path) as src:
                data = src.read(1)
                valid = data[data != src.nodata] if src.nodata else data.flatten()
                ndvi_val = float(valid.mean()) if len(valid) > 0 else 0.0
        except Exception:
            ndvi_val = 0.0

        return {
            "satellite_image_path": out_path,
            "satellite_source": "openeo_sentinel2",
            "capture_date": end_date,
            "ndvi_value": round(ndvi_val, 4),
            "ndvi_interpretation": _ndvi_label(ndvi_val),
        }
    except Exception as e:
        print(f"[satellite_fetcher] OpenEO failed (expected if not installed): {e}")
        return None


def fetch_satellite(lat: float, lon: float, osm_id: str = "unknown") -> dict:
    try:
        # ── Source 1: OpenEO / Sentinel-2 ──────────────────────────────────
        openeo_result = _try_openeo(lat, lon, osm_id)

        today = datetime.utcnow()
        date_current = today.strftime("%Y-%m-%d")
        date_old = (today - timedelta(days=180)).strftime("%Y-%m-%d")

        # ── Source 2: NASA GIBS fallback ───────────────────────────────────
        path_current = _fetch_gibs_tile(lat, lon, date_current, osm_id)
        path_old = _fetch_gibs_tile(lat, lon, date_old, osm_id)

        # Change detection
        change_magnitude = 0.0
        if path_current and path_old:
            change_magnitude = _pixel_change_magnitude(path_current, path_old)
        change_detected = change_magnitude > 0.30

        # NDVI from OpenEO if available, else skip
        if openeo_result:
            ndvi_val = openeo_result["ndvi_value"]
            ndvi_interp = openeo_result["ndvi_interpretation"]
            satellite_source = openeo_result["satellite_source"]
            sat_image_path = openeo_result["satellite_image_path"]
            capture_date = openeo_result["capture_date"]
        else:
            ndvi_val = 0.0
            ndvi_interp = "unknown"
            satellite_source = "nasa_gibs"
            sat_image_path = path_current
            capture_date = date_current

        # Construction signal: bare ground NDVI + significant change
        construction_signal = (ndvi_val < 0.1 and ndvi_interp == "bare_ground" and change_detected)

        # Satellite score: penalise construction/change, neutral otherwise
        if construction_signal:
            satellite_score = 30
        elif change_detected:
            satellite_score = 45
        elif ndvi_interp == "built_up":
            satellite_score = 70
        else:
            satellite_score = 50

        return {
            "satellite_image_path": sat_image_path,
            "satellite_source": satellite_source,
            "capture_date": capture_date,
            "ndvi_value": round(ndvi_val, 4),
            "ndvi_interpretation": ndvi_interp,
            "change_detected": change_detected,
            "change_magnitude": round(change_magnitude, 4),
            "construction_signal": construction_signal,
            "satellite_score": satellite_score,
            "error": None,
        }

    except Exception as e:
        err = f"[satellite_fetcher] fetch_satellite error: {e}"
        print(err)
        result = dict(_NEUTRAL)
        result["error"] = str(e)
        return result


if __name__ == "__main__":
    print("--- Satellite fetch test: Orchard Road ---")
    r = fetch_satellite(1.3040, 103.8318, osm_id="orchard_test")
    for k, v in r.items():
        print(f"  {k}: {v}")
