import os
import sys
import time
import requests
from datetime import datetime, timezone

from dotenv import load_dotenv

# Search for .env up the directory tree, then try backend path explicitly
load_dotenv()
_backend_env = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'map', 'backend', '.env')
if os.path.exists(_backend_env):
    load_dotenv(_backend_env)

MAPILLARY_ACCESS_TOKEN = os.getenv("MAPILLARY_ACCESS_TOKEN")
CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'imagery_cache')


def _recency_weight(age_days: int) -> float:
    if age_days <= 180:
        return 1.0
    elif age_days <= 365:
        return 0.8
    elif age_days <= 730:
        return 0.55
    elif age_days <= 1460:
        return 0.30
    else:
        return 0.15


def _age_label(age_days: int) -> str:
    if age_days < 30:
        return f"Captured {age_days} days ago — fresh"
    elif age_days < 365:
        months = age_days // 30
        return f"Captured ~{months} month{'s' if months > 1 else ''} ago"
    else:
        years = age_days // 365
        remainder_months = (age_days % 365) // 30
        base = f"Captured ~{years} year{'s' if years > 1 else ''}"
        if remainder_months:
            base += f" {remainder_months}mo"
        base += " ago — confidence reduced"
        return base


def _null_result() -> dict:
    return {
        "image_path": None,
        "image_url": None,
        "captured_at": None,
        "image_age_days": None,
        "recency_weight": 0.15,
        "age_label": "Unknown capture date",
        "compass_angle": None,
        "mapillary_id": None,
        "found": False,
    }


def fetch_mapillary_images(lat: float, lon: float, radius: int = 30, osm_id: str = "unknown") -> dict:
    try:
        if not MAPILLARY_ACCESS_TOKEN:
            print("[mapillary_fetcher] No MAPILLARY_ACCESS_TOKEN — skipping")
            return _null_result()

        bbox = f"{lon - 0.001},{lat - 0.001},{lon + 0.001},{lat + 0.001}"
        params = {
            "access_token": MAPILLARY_ACCESS_TOKEN,
            "fields": "id,captured_at,geometry,thumb_1024_url,compass_angle",
            "bbox": bbox,
            "limit": 10,
        }

        for attempt in range(2):
            try:
                resp = requests.get(
                    "https://graph.mapillary.com/images",
                    params=params,
                    timeout=15,
                )
                if resp.status_code == 429:
                    print("[mapillary_fetcher] Rate limited — waiting 2s")
                    time.sleep(2)
                    continue
                resp.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                if attempt == 0:
                    time.sleep(2)
                else:
                    raise

        data = resp.json().get("data", [])
        if not data:
            print(f"[mapillary_fetcher] No images found near ({lat}, {lon})")
            return _null_result()

        # Sort by captured_at descending (most recent first)
        def _parse_ts(item):
            try:
                ca = item.get("captured_at", 0)
                return int(ca) if isinstance(ca, (int, float)) else 0
            except Exception:
                return 0

        # Deterministic ordering: newest first, with image id as a stable
        # tie-breaker so the SAME image is chosen on every run.
        data.sort(key=lambda x: (_parse_ts(x), str(x.get("id", ""))), reverse=True)
        top = data[0]

        img_id = top.get("id", "unknown")
        captured_at_raw = top.get("captured_at", 0)
        thumb_url = top.get("thumb_1024_url", "")
        compass_angle = top.get("compass_angle")

        # Parse captured_at (Mapillary returns Unix ms or ISO string)
        try:
            if isinstance(captured_at_raw, (int, float)):
                captured_dt = datetime.fromtimestamp(int(captured_at_raw) / 1000, tz=timezone.utc)
            else:
                captured_dt = datetime.fromisoformat(str(captured_at_raw).replace("Z", "+00:00"))
            captured_str = captured_dt.strftime("%Y-%m-%d")
            now = datetime.now(tz=timezone.utc)
            age_days = (now - captured_dt).days
        except Exception:
            captured_str = str(captured_at_raw)
            age_days = 9999

        weight = _recency_weight(age_days)
        label = _age_label(age_days)

        # Download image
        cache_dir = os.path.join(CACHE_DIR, str(osm_id))
        os.makedirs(cache_dir, exist_ok=True)
        img_path = os.path.join(cache_dir, f"mapillary_{img_id}.jpg")

        if thumb_url:
            try:
                img_resp = requests.get(thumb_url, timeout=20)
                img_resp.raise_for_status()
                with open(img_path, "wb") as f:
                    f.write(img_resp.content)
            except Exception as e:
                print(f"[mapillary_fetcher] Image download failed: {e}")
                img_path = None
        else:
            img_path = None

        return {
            "image_path": img_path,
            "image_url": thumb_url,
            "captured_at": captured_str,
            "image_age_days": age_days,
            "recency_weight": weight,
            "age_label": label,
            "compass_angle": compass_angle,
            "mapillary_id": img_id,
            "found": img_path is not None and os.path.exists(img_path),
        }

    except Exception as e:
        print(f"[mapillary_fetcher] fetch_mapillary_images error: {e}")
        return _null_result()


if __name__ == "__main__":
    test_locations = [
        ("Orchard Road", 1.3040, 103.8318),
        ("Punggol", 1.4050, 103.9020),
    ]
    for name, lat, lon in test_locations:
        print(f"\n--- {name} ({lat}, {lon}) ---")
        result = fetch_mapillary_images(lat, lon, osm_id=name.replace(" ", "_"))
        print(f"  Found      : {result['found']}")
        print(f"  Captured   : {result['captured_at']}")
        print(f"  Age label  : {result['age_label']}")
        print(f"  Weight     : {result['recency_weight']}")
        print(f"  Image path : {result['image_path']}")
