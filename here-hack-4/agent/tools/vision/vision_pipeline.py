import os
import sys

# Make project root importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

# Core dependencies (lightweight, always available): Mapillary fetch + GPT-4o analysis.
from agent.tools.vision.mapillary_fetcher import fetch_mapillary_images
from agent.tools.vision.openai_vision_analyzer import analyze_with_vision_openai

# Optional heavy CV tools (YOLO / GradCAM / OCR / satellite). These require extra
# libraries (ultralytics, torch, easyocr, ...) that may not be installed. We import
# them lazily inside each step so the pipeline runs perfectly with just Mapillary +
# GPT-4o, and transparently adds the extras when their libraries are present.

_VISION_SCORE_WEIGHT = 0.05  # street imagery is a low-weight directional signal

_STATUS_SCORES = {
    "ACTIVE": 90,
    "CLOSED_TEMPORARY": 35,
    "CLOSED_PERMANENT": 10,
    "UNDER_CONSTRUCTION": 40,
    "VACANT_LOT": 15,
    "DIFFERENT_BUSINESS": 50,
    "UNCLEAR": 50,
}

_NULL_VISION = {
    "vision_score": -1,
    "mapillary_result": {},
    "satellite_result": {},
    "yolo_result": {},
    "gradcam_result": {},
    "ocr_result": {},
    "vision_model_result": {},
    "storefront_status": "UNCLEAR",
    "detected_name": None,
    "is_rebrand": False,
    "final_confidence": 0.0,
    "recency_weight": 0.0,
    "age_label": "No image available",
    "image_path": None,
    "image_url": None,
    "gradcam_overlay_b64": None,
    "gradcam_pure_b64": None,
    "satellite_image_path": None,
    "vision_available": False,
    "vision_provider": "openai-gpt4o",
    "vision_error": None,
}


def _try_satellite(lat, lon, osm_id):
    try:
        from agent.tools.vision.satellite_fetcher import fetch_satellite
        return fetch_satellite(lat, lon, osm_id=osm_id)
    except Exception as e:
        return {"satellite_score": 50, "construction_signal": False, "skipped": True, "error": str(e)}


def _try_yolo(image_path, osm_id):
    try:
        from agent.tools.vision.yolo_cropper import crop_storefront
        return crop_storefront(image_path, osm_id=osm_id)
    except Exception as e:
        return {"crop_method": "skipped", "error": str(e)}


def _try_gradcam(image_path, osm_id):
    try:
        from agent.tools.vision.gradcam_analyzer import run_gradcam
        return run_gradcam(image_path, osm_id=osm_id)
    except Exception as e:
        return {"gradcam_overlay_b64": None, "attention_reliable": False, "skipped": True, "error": str(e)}


def _try_ocr(image_path, name):
    try:
        from agent.tools.vision.ocr_module import extract_signage_text
        return extract_signage_text(image_path, osm_name=name)
    except Exception as e:
        return {"closure_signal_strength": 0.0, "raw_texts": [], "skipped": True, "error": str(e)}


def run_vision_pipeline(poi: dict) -> dict:
    """
    Orchestrates vision tools for a single POI using Mapillary + GPT-4o (no Google).

    poi keys: osm_id, name, lat, lon, category
    Returns a vision_result dict. Never raises — all errors are captured.
    Optional CV tools (YOLO/GradCAM/OCR/satellite) enhance the result when their
    libraries are installed but are not required.
    """
    result = dict(_NULL_VISION)

    osm_id = str(poi.get("osm_id", "unknown"))
    name = poi.get("name", "")
    lat = float(poi.get("lat", 0))
    lon = float(poi.get("lon", 0))
    category = poi.get("category", "")

    try:
        # ── Step 1: Mapillary image ───────────────────────────────────────
        mapillary_result = fetch_mapillary_images(lat, lon, osm_id=osm_id)
        result["mapillary_result"] = mapillary_result
        result["image_path"] = mapillary_result.get("image_path")
        result["image_url"] = mapillary_result.get("image_url")
        result["recency_weight"] = mapillary_result.get("recency_weight", 0.15)
        result["age_label"] = mapillary_result.get("age_label", "Unknown")

        # ── Step 2: Satellite imagery (optional) ──────────────────────────
        satellite_result = _try_satellite(lat, lon, osm_id)
        result["satellite_result"] = satellite_result
        result["satellite_image_path"] = satellite_result.get("satellite_image_path")

        has_image = bool(mapillary_result.get("image_url") or mapillary_result.get("found"))
        if not has_image:
            result["vision_available"] = False
            result["vision_score"] = -1
            result["vision_error"] = "No Mapillary image found near POI"
            return result

        image_path = mapillary_result.get("image_path")
        image_url = mapillary_result.get("image_url")
        recency_weight = mapillary_result.get("recency_weight", 0.15)
        captured_at = mapillary_result.get("captured_at", "unknown")
        age_label = mapillary_result.get("age_label", "")

        # ── Step 3: YOLO crop (optional) ──────────────────────────────────
        yolo_result = _try_yolo(image_path, osm_id) if image_path else {"crop_method": "no_local_image"}
        result["yolo_result"] = yolo_result
        crop_path = yolo_result.get("crop_path")
        analysis_path = crop_path if crop_path and os.path.exists(crop_path) else image_path

        # ── Step 4a: GradCAM (optional) ───────────────────────────────────
        gradcam_result = _try_gradcam(analysis_path, osm_id) if analysis_path else {}
        result["gradcam_result"] = gradcam_result
        result["gradcam_overlay_b64"] = gradcam_result.get("gradcam_overlay_b64")
        result["gradcam_pure_b64"] = gradcam_result.get("gradcam_pure_b64")

        # ── Step 4b: OCR (optional) ───────────────────────────────────────
        ocr_result = _try_ocr(analysis_path, name) if analysis_path else {}
        result["ocr_result"] = ocr_result

        # ── Step 4c: GPT-4o vision (core, no Google) ──────────────────────
        model_result = analyze_with_vision_openai(
            image_path=analysis_path,
            image_url=image_url,
            osm_name=name,
            osm_category=category,
            captured_at=captured_at,
            age_label=age_label,
            recency_weight=recency_weight,
        )
        result["vision_model_result"] = model_result
        result["detected_name"] = model_result.get("detected_name")
        result["is_rebrand"] = bool(model_result.get("is_rebrand"))

        # ── Step 5: Vision score ──────────────────────────────────────────
        storefront_status = model_result.get("storefront_status", "UNCLEAR")
        weighted_score = _STATUS_SCORES.get(storefront_status, 50) * recency_weight
        if ocr_result.get("closure_signal_strength", 0) > 0.7:
            weighted_score *= 0.5
        if satellite_result.get("construction_signal", False):
            weighted_score *= 0.4

        result["vision_score"] = max(0, min(100, int(weighted_score)))
        result["storefront_status"] = storefront_status
        result["final_confidence"] = model_result.get("final_confidence", 0.03)
        result["vision_available"] = True
        result["vision_error"] = None
        return result

    except Exception as e:
        print(f"[vision_pipeline] critical error: {e}")
        result["vision_error"] = str(e)
        result["vision_available"] = False
        return result


if __name__ == "__main__":
    test_pois = [
        {"osm_id": "orchard_test_001", "name": "Orchard Road Restaurant", "lat": 1.3040, "lon": 103.8318, "category": "restaurant"},
    ]
    for poi in test_pois:
        print(f"\n{'='*60}\nPOI: {poi['name']}\n{'='*60}")
        r = run_vision_pipeline(poi)
        print(f"  vision_available : {r['vision_available']}")
        print(f"  provider         : {r['vision_provider']}")
        print(f"  storefront_status: {r['storefront_status']}")
        print(f"  detected_name    : {r['detected_name']}")
        print(f"  is_rebrand       : {r['is_rebrand']}")
        print(f"  vision_score     : {r['vision_score']}")
        print(f"  vision_error     : {r['vision_error']}")
