# pyre-ignore-all-errors
# ============================================================================
# Agent 3 — Website Extraction Agent
# ============================================================================
"""
Identifies official place websites, crawls target pages, extracts structured
operational fields, and detects open/closed/rebrand clues.
"""
import re
import logging
from typing import Any, Dict, List, Optional
import httpx
from backend.agents.base_agent import BaseAgent
from backend.agents._util import gather_bounded
from backend.schemas.models import WebsiteEvidence, SourceTypeEnum, FreshnessLabel
from backend.config import settings

log = logging.getLogger("website_agent")

# Domain-parking / placeholder fingerprints — these pages are "alive" (HTTP 200)
# but indicate the business no longer maintains a real site.
PARKED_FINGERPRINTS = [
    "domain is for sale", "buy this domain", "this domain is parked",
    "domain for sale", "godaddy.com/domainsearch", "sedoparking.com",
    "default web page", "website coming soon", "account suspended",
    "this site can’t be reached", "under construction",
]

_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _html_to_text(html: str) -> str:
    """Strip scripts/styles/tags → lowercase visible text (no bs4 dependency)."""
    no_blocks = _TAG_RE.sub(" ", html)
    text = _HTML_RE.sub(" ", no_blocks)
    return _WS_RE.sub(" ", text).strip().lower()

CLOSURE_KEYWORDS = [
    "permanently closed", "we have closed", "no longer in operation",
    "ceased operations", "shutting down", "last day", "closed for good",
    "closing down sale", "thank you for the memories",
]
REBRAND_KEYWORDS = [
    "formerly known as", "new name", "rebranded", "now called",
    "we are now", "changed our name", "welcome to the new",
]
OPENING_KEYWORDS = [
    "grand opening", "now open", "newly opened", "just opened",
    "opening soon", "we are open", "come visit our new",
]
RELOCATION_KEYWORDS = [
    "we have moved", "new location", "relocated to", "find us at our new",
    "moved to", "new address",
]


class WebsiteExtractionAgent(BaseAgent):
    name = "website_extractor"

    async def execute(self, payload: Dict[str, Any]) -> List[WebsiteEvidence]:
        baseline = payload.get("baseline", [])

        places_with_websites = [p for p in baseline if p.get("website")]
        log.info(f"Checking {len(places_with_websites)} places with websites")

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": "Mozilla/5.0 (PlaceIQ-Singapore POI verifier)"},
        ) as client:
            results = await gather_bounded(
                places_with_websites,
                lambda p: self._extract_website(client, p, p["website"]),
                concurrency=10,
            )

        states = {}
        for r in results:
            states[r.website_state] = states.get(r.website_state, 0) + 1
        log.info(f"Website evidence for {len(results)} places — states: {states}")
        return results

    async def _normalize_url(self, url: str) -> str:
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url

    async def _extract_website(self, client: httpx.AsyncClient, place: Dict, url: str) -> Optional[WebsiteEvidence]:
        """
        Real extraction: fetch the page, classify operational state, and scan the
        visible text for closure / rebrand / opening / relocation language.
        """
        fetch_url = await self._normalize_url(url)

        website_state = "active"
        html = ""
        status_code: Optional[int] = None
        copyright_year: Optional[int] = None
        keywords = {"closure": [], "rebrand": [], "opening": [], "relocation": []}

        try:
            resp = await client.get(fetch_url)
            status_code = resp.status_code
            if status_code >= 500 or status_code in (403, 404, 410):
                website_state = "inactive"
            elif status_code >= 400:
                website_state = "error"
            else:
                html = resp.text or ""
                text = _html_to_text(html)
                if not text:
                    website_state = "inactive"
                elif any(fp in text for fp in PARKED_FINGERPRINTS):
                    website_state = "parked"
                else:
                    website_state = "active"
                    keywords = self.detect_keywords(text)
                    copyright_year = self.extract_copyright_year(html)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
            website_state = "inactive"
        except Exception as e:
            log.debug(f"Website fetch failed for {fetch_url}: {e}")
            website_state = "error"

        # Confidence reflects how decisively we could read the site.
        if website_state == "active":
            confidence = 0.85 if (keywords["opening"] or copyright_year) else 0.7
        elif website_state in ("inactive", "parked"):
            confidence = 0.6
        else:  # error — inconclusive
            confidence = 0.3

        has_menu = bool(re.search(r"\bmenu\b", html, re.IGNORECASE)) if html else False
        has_booking = bool(re.search(r"\b(book(ing)?|reserv)", html, re.IGNORECASE)) if html else False

        return WebsiteEvidence(
            source_url=fetch_url,
            confidence=confidence,
            freshness=FreshnessLabel.recent,
            business_name=place.get("name"),
            brand_name=place.get("brand"),
            address=place.get("address"),
            postal_code=place.get("postal_code"),
            phone=place.get("phone"),
            opening_hours=place.get("opening_hours"),
            website_state=website_state,
            has_menu=has_menu,
            has_booking=has_booking,
            closure_keywords_found=keywords["closure"],
            reopening_keywords_found=keywords["opening"],
            relocation_keywords_found=keywords["relocation"],
            grand_opening_keywords=keywords["opening"],
            copyright_year=copyright_year,
            raw_data={
                "place_id": place.get("place_id"),
                "url": fetch_url,
                "status_code": status_code,
                "lat": place.get("latitude"),
                "lng": place.get("longitude"),
                "name": place.get("name"),
                "rebrand_keywords": keywords["rebrand"],
            },
        )

    @staticmethod
    def detect_keywords(text: str) -> Dict[str, List[str]]:
        """Scan page text for operational clue keywords."""
        text_lower = text.lower()
        found = {
            "closure": [k for k in CLOSURE_KEYWORDS if k in text_lower],
            "rebrand": [k for k in REBRAND_KEYWORDS if k in text_lower],
            "opening": [k for k in OPENING_KEYWORDS if k in text_lower],
            "relocation": [k for k in RELOCATION_KEYWORDS if k in text_lower],
        }
        return found

    @staticmethod
    def extract_copyright_year(html: str) -> int | None:
        match = re.search(r'©\s*(\d{4})', html)
        if match:
            return int(match.group(1))
        match = re.search(r'copyright\s+(\d{4})', html, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None
