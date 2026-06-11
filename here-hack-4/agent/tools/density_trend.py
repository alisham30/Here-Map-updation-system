import os
import sys
import time
import math
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
load_dotenv()

MAPILLARY_ACCESS_TOKEN = os.getenv('MAPILLARY_ACCESS_TOKEN')


# ─── SOURCE 1: Mapillary Image Density ───

def get_mapillary_density(lat, lon, radius_deg=0.002) -> dict:
    """
    Count how many Mapillary street-level images exist near this POI.
    More images = more humans have visited and photographed this area.
    Also check how RECENT the images are — recent photos = area is active.

    radius_deg=0.002 ≈ 220 meters
    """
    if not MAPILLARY_ACCESS_TOKEN:
        return {
            "mapillary_count": 0,
            "recent_count": 0,
            "mapillary_score": 50,
            "old_count": 0,
            "mapillary_trend": "stable",
        }

    try:
        bbox = f"{lon - radius_deg},{lat - radius_deg},{lon + radius_deg},{lat + radius_deg}"
        resp = requests.get(
            "https://graph.mapillary.com/images",
            params={
                "access_token": MAPILLARY_ACCESS_TOKEN,
                "fields": "id,captured_at",
                "bbox": bbox,
                "limit": 100,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])

        total = len(data)
        recent_count = 0
        old_count = 0
        cutoff_recent = datetime.utcnow() - timedelta(days=365)
        cutoff_old = datetime(2024, 1, 1)

        for img in data:
            captured_at = img.get("captured_at", "")
            captured_str = str(captured_at)
            # captured_at is typically a Unix timestamp in ms or an ISO string
            try:
                if isinstance(captured_at, (int, float)):
                    dt = datetime.utcfromtimestamp(captured_at / 1000)
                else:
                    dt = datetime.fromisoformat(captured_str.replace("Z", "+00:00").replace("+00:00", ""))
                if dt >= cutoff_recent:
                    recent_count += 1
                elif dt < cutoff_old:
                    old_count += 1
            except Exception:
                # Fallback: check string content
                if "2025" in captured_str or "2026" in captured_str:
                    recent_count += 1
                elif any(yr in captured_str for yr in ["2019", "2020", "2021", "2022", "2023"]):
                    old_count += 1

        # Mapillary score
        if total == 0:
            score = 10
        elif total <= 5 and recent_count == 0:
            score = 25
        elif total <= 5 and recent_count > 0:
            score = 45
        elif total <= 20 and recent_count > 0:
            score = 65
        elif total <= 50 and recent_count >= total * 0.4:
            score = 80
        elif total > 50 and recent_count >= total * 0.4:
            score = 95
        else:
            score = 50

        # Trend
        if total == 0:
            trend = "stable"
        elif recent_count == 0 and old_count > 0:
            trend = "declining"
        elif recent_count >= old_count:
            trend = "growing"
        else:
            trend = "stable"

        return {
            "mapillary_count": total,
            "recent_count": recent_count,
            "old_count": old_count,
            "mapillary_score": score,
            "mapillary_trend": trend,
        }

    except Exception as e:
        print(f"[density_trend] Mapillary error: {e}")
        return {
            "mapillary_count": 0,
            "recent_count": 0,
            "old_count": 0,
            "mapillary_score": 50,
            "mapillary_trend": "stable",
        }
    finally:
        time.sleep(1)


# ─── SOURCE 2: OSM GPS Trace Density ───

def get_osm_trace_density(lat, lon, radius_deg=0.002) -> dict:
    """
    Query OSM GPS trace API to count how many GPS trackpoints exist near this POI.
    GPS traces are uploaded by real humans walking/driving/cycling with GPS loggers.
    More traces = more human traffic through this area.

    API: https://api.openstreetmap.org/api/0.6/trackpoints?bbox={w},{s},{e},{n}&page=0
    Returns GPX XML format. No API key needed. Completely free.
    """
    west = lon - radius_deg
    south = lat - radius_deg
    east = lon + radius_deg
    north = lat + radius_deg

    try:
        resp = requests.get(
            "https://api.openstreetmap.org/api/0.6/trackpoints",
            params={"bbox": f"{west},{south},{east},{north}", "page": 0},
            headers={"User-Agent": "MapFreshness-Hackathon/1.0"},
            timeout=15,
        )
        resp.raise_for_status()

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            print(f"[density_trend] OSM XML parse error: {e}")
            return {"trace_count": 0, "recent_trace_count": 0, "trace_score": 50}

        # GPX namespace
        ns = {"gpx": "http://www.topografix.com/GPX/1/0"}
        trkpts = root.findall(".//gpx:trkpt", ns)
        if not trkpts:
            # Try without namespace
            trkpts = root.findall(".//{http://www.topografix.com/GPX/1/0}trkpt")
        if not trkpts:
            trkpts = root.findall(".//trkpt")

        total = len(trkpts)
        recent_trace_count = 0
        cutoff = datetime.utcnow() - timedelta(days=365 * 2)

        for pt in trkpts:
            time_el = pt.find("{http://www.topografix.com/GPX/1/0}time")
            if time_el is None:
                time_el = pt.find("time")
            if time_el is not None and time_el.text:
                try:
                    dt_str = time_el.text.replace("Z", "").replace("+00:00", "")
                    dt = datetime.fromisoformat(dt_str)
                    if dt >= cutoff:
                        recent_trace_count += 1
                except Exception:
                    pass

        # Trace score
        if total == 0:
            trace_score = 10
        elif total <= 10:
            trace_score = 30
        elif total <= 50:
            trace_score = 50
        elif total <= 200:
            trace_score = 70
        else:
            trace_score = 90

        return {
            "trace_count": total,
            "recent_trace_count": recent_trace_count,
            "trace_score": trace_score,
        }

    except Exception as e:
        print(f"[density_trend] OSM trace error: {e}")
        return {"trace_count": 0, "recent_trace_count": 0, "trace_score": 50}
    finally:
        time.sleep(2)


# ─── COMBINED: Human Density Score ───

def analyze_human_density(lat, lon) -> dict:
    """
    Combine Mapillary + OSM traces into a single human density assessment.
    Mapillary weight: 60% (more reliable — actual photos with timestamps)
    OSM traces weight: 40% (GPS points, less reliable but covers more area)
    """
    mapillary = get_mapillary_density(lat, lon)
    osm = get_osm_trace_density(lat, lon)

    mapillary_score = mapillary.get("mapillary_score", 50)
    trace_score = osm.get("trace_score", 50)

    density_score = round(0.6 * mapillary_score + 0.4 * trace_score)

    if density_score >= 70:
        density_signal = "high_activity"
    elif density_score >= 40:
        density_signal = "moderate_activity"
    else:
        density_signal = "low_activity"

    mapillary_count = mapillary.get("mapillary_count", 0)
    recent_count = mapillary.get("recent_count", 0)
    trace_count = osm.get("trace_count", 0)
    mapillary_trend = mapillary.get("mapillary_trend", "stable")

    # Build human-readable interpretation
    if mapillary_count == 0 and trace_count == 0:
        interpretation = (
            "No Mapillary images and no GPS traces found near this location. "
            "Very low human presence — businesses here may have closed."
        )
    elif mapillary_count <= 1 and recent_count == 0 and trace_count == 0:
        year_hint = ""
        if mapillary.get("old_count", 0) > 0:
            year_hint = " (from an older year)"
        interpretation = (
            f"Only {mapillary_count} Mapillary image{year_hint} and {trace_count} GPS traces found. "
            "Very low human presence — businesses here may have closed."
        )
    elif density_signal == "high_activity":
        interpretation = (
            f"Found {mapillary_count} Mapillary images ({recent_count} recent) and "
            f"{trace_count} GPS traces near this location. "
            "Area shows high human activity, suggesting active businesses."
        )
    elif density_signal == "moderate_activity":
        interpretation = (
            f"Found {mapillary_count} Mapillary images ({recent_count} recent) and "
            f"{trace_count} GPS traces near this location. "
            "Area shows moderate human activity, suggesting businesses are likely active."
        )
    else:
        interpretation = (
            f"Found {mapillary_count} Mapillary images ({recent_count} recent) and "
            f"{trace_count} GPS traces near this location. "
            "Low human presence in this area — some businesses may be inactive."
        )

    return {
        "density_score": density_score,
        "density_signal": density_signal,
        "mapillary_count": mapillary_count,
        "mapillary_recent": recent_count,
        "mapillary_score": mapillary_score,
        "mapillary_trend": mapillary_trend,
        "trace_count": trace_count,
        "trace_score": trace_score,
        "interpretation": interpretation,
    }


# ─── TEST BLOCK ───

if __name__ == "__main__":
    test_locations = [
        ("Orchard Road restaurant", 1.3040, 103.8318, "HIGH"),
        ("Punggol residential", 1.4050, 103.9020, "LOW"),
        ("Tampines medium area", 1.3530, 103.9450, "MEDIUM"),
    ]

    print("=" * 70)
    print("Human Density Analysis — MapFreshness Hackathon")
    print("NOTE: Makes live API calls, takes ~15-20 seconds total.")
    print("=" * 70)

    for name, lat, lon, expected in test_locations:
        print(f"\n📍 {name} (lat={lat}, lon={lon}) — expected: {expected}")
        print("-" * 60)
        result = analyze_human_density(lat, lon)
        print(f"  Density Score : {result['density_score']}/100")
        print(f"  Signal        : {result['density_signal']}")
        print(f"  Mapillary     : {result['mapillary_count']} images "
              f"({result['mapillary_recent']} recent) — score {result['mapillary_score']}, "
              f"trend: {result['mapillary_trend']}")
        print(f"  OSM Traces    : {result['trace_count']} trackpoints — score {result['trace_score']}")
        print(f"  Interpretation: {result['interpretation']}")
