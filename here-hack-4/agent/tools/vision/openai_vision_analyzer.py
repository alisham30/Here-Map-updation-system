import os
import re
import json
import base64
import requests
from dotenv import load_dotenv

# Load env (repo root + backend/.env) so OPENAI_API_KEY is available standalone.
load_dotenv()
_backend_env = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'map', 'backend', '.env')
if os.path.exists(_backend_env):
    load_dotenv(_backend_env)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_VISION_MODEL = "gpt-4o"

# Street imagery is inherently uncertain (old, obstructed, geographically imprecise),
# so the closure confidence it produces is intentionally capped low. The REBRAND
# signal (a different business name on the sign) is reported separately and is the
# main thing this analyzer is good at.
_CONFIDENCE_CAP = 0.08

_MOCK_RESULT = {
    "storefront_status": "UNCLEAR",
    "confidence": 0.03,
    "detected_business_type": "unknown",
    "visual_evidence": "No image analysis performed — OPENAI_API_KEY missing",
    "name_visible": False,
    "detected_name": None,
    "closure_indicators": [],
    "active_indicators": [],
    "image_quality": "unknown",
    "recommendation": "REVIEW",
    "is_rebrand": False,
    "final_confidence": 0.03,
}

_PROMPT = """You are a map-quality analyst reviewing street-level imagery for HERE Technologies in Singapore.

The map (OSM/HERE) records this location as: "{name}" (category: {category}).
Image captured: {captured_at} ({age_label}). The image may be old — be conservative; when unsure use UNCLEAR.

Read the storefront sign text carefully and decide whether the business shown matches the recorded name.
Return ONLY valid JSON (no prose):
{{
  "storefront_status": "ACTIVE" | "CLOSED_TEMPORARY" | "CLOSED_PERMANENT" | "UNDER_CONSTRUCTION" | "VACANT_LOT" | "DIFFERENT_BUSINESS" | "UNCLEAR",
  "confidence": float 0..1,
  "detected_business_type": "single word category",
  "visual_evidence": "what you actually see on the sign/storefront",
  "name_visible": true | false,
  "detected_name": "exact business name on the signage, or null",
  "closure_indicators": ["explicit written closure notices only, e.g. 'For Rent', 'Permanently Closed'"],
  "active_indicators": ["signs of operation"],
  "image_quality": "good" | "blurry" | "obstructed" | "dark"
}}
Rules:
- Use DIFFERENT_BUSINESS only when a clear business name is visible AND it does not match "{name}" (a rebrand/takeover).
- A pulled-down shutter is NOT permanent closure — use UNCLEAR unless there is explicit written closure text.
- detected_name must be the literal text on the sign, not a guess."""


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    try:
        return json.loads(text)
    except Exception:
        return {}


def _image_content(image_url: str, image_path: str):
    """Return the OpenAI 'image_url' content block, preferring a direct URL."""
    if image_url:
        return {"type": "image_url", "image_url": {"url": image_url}}
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        ext = os.path.splitext(image_path)[-1].lower()
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
        return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
    return None


def _name_mismatch(detected: str, osm_name: str) -> bool:
    if not detected or not osm_name:
        return False
    a = set(re.sub(r"[^\w\s]", "", detected.lower()).split())
    b = set(re.sub(r"[^\w\s]", "", osm_name.lower()).split())
    if not a or not b:
        return False
    overlap = len(a & b) / max(len(a), len(b))
    return overlap < 0.34   # clearly different name on the sign


def analyze_with_vision_openai(
    image_path: str = None,
    image_url: str = None,
    osm_name: str = "",
    osm_category: str = "",
    captured_at: str = "unknown",
    age_label: str = "",
    recency_weight: float = 0.5,
) -> dict:
    """
    GPT-4o storefront analysis. Replaces the Gemini analyzer (no Google).
    Always returns a dict; never raises. Adds an `is_rebrand` signal derived from
    DIFFERENT_BUSINESS status or a detected-name mismatch against the OSM name.
    """
    try:
        if not OPENAI_API_KEY:
            mock = dict(_MOCK_RESULT)
            mock["final_confidence"] = round(_CONFIDENCE_CAP * recency_weight, 4)
            return mock

        img_block = _image_content(image_url, image_path)
        if img_block is None:
            mock = dict(_MOCK_RESULT)
            mock["visual_evidence"] = "No image available (url/path missing)"
            mock["final_confidence"] = round(_CONFIDENCE_CAP * recency_weight, 4)
            return mock

        prompt = _PROMPT.format(name=osm_name or "unknown", category=osm_category or "unknown",
                                captured_at=captured_at, age_label=age_label)
        body = {
            "model": OPENAI_VISION_MODEL,
            "messages": [
                {"role": "system", "content": "You read storefront signage and report exactly what is written."},
                {"role": "user", "content": [{"type": "text", "text": prompt}, img_block]},
            ],
            "max_tokens": 500,
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        resp = requests.post(OPENAI_URL, headers=headers, json=body, timeout=30)
        if resp.status_code == 400:
            body.pop("response_format", None)
            resp = requests.post(OPENAI_URL, headers=headers, json=body, timeout=30)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = _parse_json(content)
        if not parsed:
            raise ValueError(f"Unparseable model output: {content[:160]}")

        # Defaults
        parsed.setdefault("storefront_status", "UNCLEAR")
        parsed.setdefault("detected_business_type", "unknown")
        parsed.setdefault("visual_evidence", "")
        parsed.setdefault("name_visible", False)
        parsed.setdefault("detected_name", None)
        parsed.setdefault("closure_indicators", [])
        parsed.setdefault("active_indicators", [])
        parsed.setdefault("image_quality", "unknown")
        parsed.setdefault("recommendation", "REVIEW")

        # Rebrand signal: explicit DIFFERENT_BUSINESS, or a visible name that clearly
        # differs from what the map records.
        detected_name = parsed.get("detected_name")
        is_rebrand = (
            parsed.get("storefront_status") == "DIFFERENT_BUSINESS"
            or (parsed.get("name_visible") and _name_mismatch(detected_name, osm_name))
        )
        parsed["is_rebrand"] = bool(is_rebrand)
        if is_rebrand and parsed.get("storefront_status") not in ("CLOSED_PERMANENT", "VACANT_LOT"):
            parsed["storefront_status"] = "DIFFERENT_BUSINESS"

        # Confidence: cap low for closure (street imagery), weighted by recency.
        raw_conf = float(parsed.get("confidence", 0.5) or 0.5)
        capped = min(raw_conf * 0.08, _CONFIDENCE_CAP)
        parsed["confidence"] = round(capped, 4)
        parsed["final_confidence"] = round(capped * recency_weight, 4)
        return parsed

    except Exception as e:
        print(f"[openai_vision] analyze error: {e}")
        mock = dict(_MOCK_RESULT)
        mock["visual_evidence"] = f"Analysis failed: {e}"
        mock["final_confidence"] = round(_CONFIDENCE_CAP * recency_weight, 4)
        return mock


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else None
    r = analyze_with_vision_openai(image_url=url, osm_name="Test Place", osm_category="restaurant",
                                   captured_at="2024-01-01", age_label="~1 year ago", recency_weight=0.5)
    print(json.dumps(r, indent=2))
