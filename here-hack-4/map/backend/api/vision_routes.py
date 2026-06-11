# pyre-ignore-all-errors
# ============================================================================
# API Routes — On-demand Vision Intelligence
# ============================================================================
import sys
import os
import logging
from fastapi import APIRouter

# Make the repo root importable so agent/tools/vision/* can be found
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

router = APIRouter(prefix="/api", tags=["vision"])
log = logging.getLogger("vision_routes")


@router.get("/vision")
async def get_vision_analysis(lat: float, lon: float, name: str = "", category: str = "", osm_id: str = "unknown"):
    """
    Run the vision pipeline (Mapillary + GPT-4o, no Google) for a given lat/lon.
    Optional CV tools (YOLO/GradCAM/OCR/satellite) enhance the result when their
    libraries are installed. Returns storefront_status, detected_name and an
    is_rebrand flag (a different business name on the sign than the map records).
    """
    try:
        from agent.tools.vision.vision_pipeline import run_vision_pipeline
        poi = {
            "osm_id": osm_id,
            "name": name,
            "lat": lat,
            "lon": lon,
            "category": category,
        }
        # Blocking pipeline (requests + optional CV) — run off the event loop.
        import asyncio
        result = await asyncio.to_thread(run_vision_pipeline, poi)
        # Drop the large activation_map list to keep response size down
        if result.get("gradcam_result"):
            result["gradcam_result"].pop("activation_map", None)
        return {"success": True, "vision": result}
    except Exception as e:
        log.error(f"Vision pipeline failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "vision": {
                "vision_available": False,
                "vision_score": -1,
                "storefront_status": "UNCLEAR",
                "final_confidence": 0.0,
            },
        }
