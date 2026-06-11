# pyre-ignore-all-errors
# ============================================================================
# Agent 8 — Visual Verification Agent (Vision AI)
# ============================================================================
"""
Uses Multimodal AI (Vision) to analyze street-level imagery or storefront photos.
Automatically performs OCR on signboards to detect "Rebrands" and reads "Temporarily Closed" signs.
"""
import asyncio
import logging
import random
import json
import os
import sys
from typing import Any, Dict, List
from backend.agents.base_agent import BaseAgent
from backend.agents._util import extract_latlng, gather_bounded, key_present
from backend.schemas.models import VisualEvidence, SourceTypeEnum, FreshnessLabel
from backend.config import settings
import httpx

log = logging.getLogger("visual_agent")

# Make repo root importable so agent.tools.* can be imported from backend runtime
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


class VisualVerificationAgent(BaseAgent):
    name = "visual_verification"

    async def execute(self, payload: Dict[str, Any]) -> List[VisualEvidence]:
        baseline = payload.get("baseline", [])

        # Cover the whole focused batch deterministically so every place gets a
        # vision check (reproducible across runs).
        if len(baseline) > 50:
            sample = random.Random(42).sample(baseline, 50)
        else:
            sample = baseline[:]

        self._has_openai = key_present(settings.openai_api_key)
        try:
            from agent.tools.vision.mapillary_fetcher import fetch_mapillary_images
            self._fetch_mapillary = fetch_mapillary_images
        except Exception as e:
            log.warning(f"Mapillary fetcher import failed, falling back to no-image mode: {e}")
            self._fetch_mapillary = None

        # Fan out across the sample. Mapillary fetch is blocking, so push each
        # place's work onto a thread; GPT-4o vision runs as a real async call.
        results = await gather_bounded(sample, self._process_place, concurrency=6)

        with_images = sum(1 for r in results if r.image_url)
        log.info(f"Vision AI: {len(results)} storefronts analyzed, {with_images} with Mapillary imagery")
        return results

    async def _process_place(self, place: Dict[str, Any]) -> VisualEvidence:
        place_name = place.get("name", "Unknown Store")
        lat, lon = extract_latlng(place)

        image_url = image_date = age_label = recency_weight = None

        if self._fetch_mapillary and lat is not None and lon is not None:
            try:
                # Blocking HTTP call — run off the event loop so it doesn't serialize.
                m = await asyncio.to_thread(
                    self._fetch_mapillary, float(lat), float(lon), place.get("place_id", "unknown")
                )
                image_url = m.get("image_url")
                image_date = m.get("captured_at")
                age_label = m.get("age_label")
                recency_weight = m.get("recency_weight")
            except Exception as e:
                log.debug(f"Mapillary fetch failed for {place_name}: {e}")

        if image_url:
            visual_state, sign_text, confidence = await self._analyze_vision(place_name, self._has_openai, image_url)
        else:
            # No image → no visual evidence. We do NOT invent a state.
            visual_state, sign_text, confidence = ("unknown", "", 0.2)

        sign_match = self._calculate_similarity(place_name, sign_text) if sign_text else 0.0

        return VisualEvidence(
            image_url=image_url,
            image_date=image_date or "unknown",
            visual_state=visual_state,
            sign_text=sign_text,
            sign_match_score=sign_match,
            storefront_presence_score=0.9 if visual_state in ("open", "changed") else 0.2,
            visual_confidence=confidence,
            signage_changed=(visual_state == "changed"),
            storefront_replaced=(visual_state == "changed" and sign_match < 0.3),
            confidence=confidence,
            freshness=FreshnessLabel.recent,
            raw_data={
                "name": place_name,
                "lat": lat,
                "lng": lon,
                "address": place.get("address"),
                "category": place.get("category"),
                "image_url": image_url,
                "captured_at": image_date,
                "age_label": age_label,
                "recency_weight": recency_weight,
                "ocr_text": sign_text,
                "ai_detected_state": visual_state,
            },
        )

    # Words that explicitly signal permanent closure when found in signage text.
    # A shutter being down is NOT closure — only explicit written notices count.
    _CLOSURE_KEYWORDS = [
        "permanently closed", "permanent closure", "notice of closure",
        "closed for good", "closed permanently", "we are closed",
        "for rent", "to let", "unit available", "space available",
        "vacant", "shop for rent", "office for rent",
        "ceased operations", "winding up", "liquidation",
    ]

    def _sign_text_signals_closure(self, sign_text: str) -> bool:
        """
        Returns True only if the extracted sign text contains explicit permanent-closure
        language via fuzzy token matching.  A shutter, roller-door, or 'closed today'
        sign does NOT qualify.
        """
        if not sign_text:
            return False
        text_lower = sign_text.lower()
        for kw in self._CLOSURE_KEYWORDS:
            # Fuzzy: every token in the keyword phrase must appear in sign_text
            kw_tokens = set(kw.split())
            text_tokens = set(text_lower.split())
            if kw_tokens.issubset(text_tokens):
                return True
            # Substring fallback for short compound phrases
            if kw in text_lower:
                return True
        return False

    async def _analyze_vision(self, place_name: str, has_openai: bool, image_url: str) -> tuple[str, str, float]:
        """
        Calls GPT-4o Vision (if key present) or falls back to a mock.

        Important rules reflected in both paths:
          • visual_state = "closed" is ONLY set when the sign/notice text
            explicitly states permanent closure.  A pulled-down shutter means
            the shop may just be closed today — that returns "unknown".
          • visual_state is derived from WORDS in the image, not from the
            physical state of shutters or doors.
        """
        if has_openai:
            try:
                headers = {
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json"
                }
                system_prompt = (
                    "You are a storefront sign-text analyzer. Your ONLY job is to read "
                    "the text visible on signs, notices, and boards in the image.\n\n"
                    "Rules:\n"
                    "1. Extract the exact text from any sign or notice ('sign_text').\n"
                    "2. Set 'visual_state' to 'closed' ONLY if the sign text explicitly "
                    "states permanent closure (e.g. 'Permanently Closed', 'Ceased Operations', "
                    "'For Rent', 'To Let', 'Notice of Closure', 'Winding Up'). "
                    "A shutter being down means the shop may just be closed today — "
                    "that is NOT a permanent closure. Set 'visual_state' to 'unknown' in that case.\n"
                    "3. Set 'visual_state' to 'changed' if the sign shows a DIFFERENT business name "
                    "than the expected baseline name.\n"
                    "4. Set 'visual_state' to 'open' only if the business name on the sign "
                    "matches the expected name and the shop appears operational.\n"
                    "5. Reply ONLY with a JSON object: "
                    "{\"visual_state\": \"open|closed|changed|unknown\", "
                    "\"sign_text\": \"<exact text>\", \"confidence\": 0.0-1.0}"
                )
                req_body = {
                    "model": "gpt-4o",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"Expected business name: '{place_name}'. Read the sign text in this image."},
                                {"type": "image_url", "image_url": {"url": image_url}}
                            ]
                        }
                    ],
                    "max_tokens": 150,
                    # Deterministic vision reads → same storefront verdict every run.
                    "temperature": 0,
                    "seed": 42,
                    "response_format": {"type": "json_object"},
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post("https://api.openai.com/v1/chat/completions",
                                            headers=headers, json=req_body)
                    if resp.status_code == 200:
                        content = resp.json()["choices"][0]["message"]["content"]
                        if "```json" in content:
                            content = content.replace("```json", "").replace("```", "").strip()
                        data = json.loads(content)
                        sign_text = data.get("sign_text", "")
                        state = data.get("visual_state", "unknown")
                        # Safety gate: if GPT says "closed" but sign_text has no closure keywords,
                        # override to "unknown" — don't trust shutter-based inference
                        if state == "closed" and not self._sign_text_signals_closure(sign_text):
                            state = "unknown"
                        log.info(f"GPT-4o Vision for '{place_name}': state={state} sign='{sign_text[:60]}'")
                        return state, sign_text, data.get("confidence", 0.75)
            except Exception as e:
                log.warning(f"OpenAI Vision API failed for {place_name}, using mock: {e}")

        # ── Honest fallback ──────────────────────────────────────────────────
        # If we have a real image but no working vision model (no key, or the API
        # call failed), we do NOT guess a storefront state. Returning "unknown"
        # keeps the image visible in the UI for human review without injecting a
        # fabricated open/changed/closed signal into the pipeline.
        return "unknown", "", 0.30

    def _calculate_similarity(self, a: str, b: str) -> float:
        """Token overlap similarity used for sign-text ↔ baseline-name matching."""
        a_tokens = set(a.lower().split())
        b_tokens = set(b.lower().split())
        if not a_tokens or not b_tokens:
            return 0.0
        return len(a_tokens & b_tokens) / max(len(a_tokens), len(b_tokens))
