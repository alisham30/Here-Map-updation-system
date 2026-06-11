import os
import re
import json
import base64
import requests
from dotenv import load_dotenv

load_dotenv()
_backend_env = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'map', 'backend', '.env')
if os.path.exists(_backend_env):
    load_dotenv(_backend_env)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Vision analysis is inherently uncertain — images may be old, obstructed, or misleading.
# Confidence is kept very low (≤0.08) to prevent over-reliance on a single street photo.
_CONFIDENCE_CAP = 0.08

_MOCK_RESULT = {
    "storefront_status": "UNCLEAR",
    "confidence": 0.03,
    "detected_business_type": "unknown",
    "visual_evidence": "No image analysis performed — API key missing",
    "name_visible": False,
    "detected_name": None,
    "closure_indicators": [],
    "active_indicators": [],
    "image_quality": "unknown",
    "recommendation": "REVIEW",
    "final_confidence": 0.03,
}


def _parse_gemini_json(text: str) -> dict:
    """Extract JSON from Gemini response, handling markdown fences."""
    text = text.strip()
    # Strip ```json ... ``` fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # Find first { ... } block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Regex fallback: extract key-value pairs
        result = {}
        for key in ["storefront_status", "detected_business_type", "visual_evidence",
                    "detected_name", "image_quality", "recommendation"]:
            m = re.search(rf'"{key}"\s*:\s*"([^"]*)"', text)
            if m:
                result[key] = m.group(1)
        for key in ["confidence"]:
            m = re.search(rf'"{key}"\s*:\s*([0-9.]+)', text)
            if m:
                result[key] = float(m.group(1))
        for key in ["name_visible"]:
            m = re.search(rf'"{key}"\s*:\s*(true|false)', text)
            if m:
                result[key] = m.group(1) == "true"
        return result if result else {}


def analyze_with_vision(
    image_path: str,
    osm_name: str = "",
    osm_category: str = "",
    captured_at: str = "unknown",
    age_label: str = "",
    satellite_result: dict = None,
    recency_weight: float = 0.5,
) -> dict:
    try:
        if not GEMINI_API_KEY:
            print("[gemini_vision] No GEMINI_API_KEY — returning mock result")
            mock = dict(_MOCK_RESULT)
            mock["final_confidence"] = round(_CONFIDENCE_CAP * recency_weight, 4)
            return mock

        if not image_path or not os.path.exists(image_path):
            print(f"[gemini_vision] Image not found: {image_path}")
            mock = dict(_MOCK_RESULT)
            mock["visual_evidence"] = "Image file not found"
            mock["final_confidence"] = round(_CONFIDENCE_CAP * recency_weight, 4)
            return mock

        # Encode image
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        # Determine image mime type
        ext = os.path.splitext(image_path)[-1].lower()
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"

        # Build satellite context string
        sat_interp = "no satellite data available"
        if satellite_result:
            ndvi = satellite_result.get("ndvi_interpretation", "unknown")
            change = satellite_result.get("change_detected", False)
            construction = satellite_result.get("construction_signal", False)
            if construction:
                sat_interp = f"possible construction or demolition detected (NDVI={satellite_result.get('ndvi_value', 0):.2f}, significant ground change)"
            elif change:
                sat_interp = f"moderate physical change detected at site (magnitude={satellite_result.get('change_magnitude', 0):.2f})"
            else:
                sat_interp = f"no significant change detected (NDVI interpretation: {ndvi})"

        prompt = f"""You are a map quality analyst reviewing street level imagery for HERE Technologies.

Image details:
- Captured: {captured_at} ({age_label})
- OSM records this location as: {osm_name} ({osm_category})
- Satellite analysis shows: {sat_interp}

Note: This image may be old. Be conservative in your assessment. When uncertain, use UNCLEAR.

Analyze this street image carefully and return ONLY valid JSON, no other text:
{{
  "storefront_status": "ACTIVE" or "CLOSED_TEMPORARY" or "CLOSED_PERMANENT" or "UNDER_CONSTRUCTION" or "VACANT_LOT" or "DIFFERENT_BUSINESS" or "UNCLEAR",
  "confidence": float between 0 and 1,
  "detected_business_type": "single word category",
  "visual_evidence": "specific description of what you see",
  "name_visible": true or false,
  "detected_name": "any business name visible on signage or null",
  "closure_indicators": ["list of specific visual closure signals if any"],
  "active_indicators": ["list of specific visual active signals if any"],
  "image_quality": "good" or "blurry" or "obstructed" or "dark",
  "recommendation": "ACCEPT" or "REVIEW" or "REJECT"
}}"""

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": mime,
                                "data": img_b64,
                            }
                        },
                        {"text": prompt},
                    ]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": 2048,
            },
        }

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        )
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        resp_json = resp.json()

        # Extract text from response
        candidates = resp_json.get("candidates", [])
        if not candidates:
            raise ValueError("No candidates in Gemini response")
        parts = candidates[0].get("content", {}).get("parts", [])
        raw_text = "".join(p.get("text", "") for p in parts)

        parsed = _parse_gemini_json(raw_text)
        if not parsed:
            raise ValueError(f"Failed to parse Gemini JSON: {raw_text[:200]}")

        # Apply extremely low confidence cap — street imagery is inherently uncertain
        raw_confidence = float(parsed.get("confidence", 0.5))
        # Scale to max 0.08, weighted by recency
        capped_confidence = min(raw_confidence * 0.08, _CONFIDENCE_CAP)
        final_confidence = round(capped_confidence * recency_weight, 4)

        parsed["confidence"] = round(capped_confidence, 4)
        parsed["final_confidence"] = final_confidence

        # Fill missing fields with safe defaults
        parsed.setdefault("storefront_status", "UNCLEAR")
        parsed.setdefault("detected_business_type", "unknown")
        parsed.setdefault("visual_evidence", "")
        parsed.setdefault("name_visible", False)
        parsed.setdefault("detected_name", None)
        parsed.setdefault("closure_indicators", [])
        parsed.setdefault("active_indicators", [])
        parsed.setdefault("image_quality", "unknown")
        parsed.setdefault("recommendation", "REVIEW")

        return parsed

    except Exception as e:
        print(f"[gemini_vision] analyze_with_vision error: {e}")
        mock = dict(_MOCK_RESULT)
        mock["visual_evidence"] = f"Analysis failed: {e}"
        mock["final_confidence"] = round(_CONFIDENCE_CAP * recency_weight, 4)
        return mock


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("Usage: python gemini_vision_analyzer.py <image_path>")
    else:
        r = analyze_with_vision(
            image_path=path,
            osm_name="Test Place",
            osm_category="restaurant",
            captured_at="2024-01-01",
            age_label="Captured 1 year ago — confidence reduced",
            recency_weight=0.5,
        )
        print(f"Status          : {r.get('storefront_status')}")
        print(f"Confidence      : {r.get('confidence')}")
        print(f"Final confidence: {r.get('final_confidence')}")
        print(f"Evidence        : {r.get('visual_evidence')}")
        print(f"Recommendation  : {r.get('recommendation')}")
