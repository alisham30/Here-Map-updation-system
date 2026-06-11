# pyre-ignore-all-errors
# ============================================================================
# Agent 7 — Public Discussion Evidence Agent (Reddit via fetchlayer.dev)
# ============================================================================
"""
Gathers real community discussion signals from Reddit using the fetchlayer.dev
Reddit search API (a simple Bearer-token wrapper over Reddit search).

Behaviour:
  * For each baseline place, searches Reddit for "<name> Singapore".
  * Classifies each matching post as opening / closing / rebrand / review.
  * Derives a sentiment (positive / negative / neutral) per place.
  * Skips cleanly (returns []) when no fetchlayer key is configured — never
    fabricates discussion data.

This is intentionally a LOW-WEIGHT signal in the decision agent: community
chatter corroborates, it does not by itself decide open/closed.
"""
import logging
from typing import Any, Dict, List, Optional
import httpx

from backend.agents.base_agent import BaseAgent
from backend.agents._util import extract_latlng, gather_bounded, key_present
from backend.schemas.models import DiscussionEvidence, SourceTypeEnum, FreshnessLabel
from backend.config import settings

log = logging.getLogger("discussion_agent")

REQUEST_TIMEOUT = 12.0
MAX_PLACES = 30          # cap to respect rate limits on large baselines
POSTS_PER_QUERY = 10

CLOSING_TERMS = ["closed", "closing", "shut down", "shutting", "ceased", "no longer", "gone", "out of business"]
OPENING_TERMS = ["opened", "opening", "new outlet", "now open", "just opened", "newly opened", "grand opening"]
REBRAND_TERMS = ["rebrand", "renamed", "now called", "formerly", "taken over", "under new management"]
NEGATIVE_TERMS = ["closed", "closing", "shut", "ceased", "bad", "terrible", "disappointing", "avoid", "overpriced", "gone downhill"]
POSITIVE_TERMS = ["great", "love", "best", "amazing", "delicious", "recommend", "favourite", "favorite", "must try", "reopened"]


class DiscussionEvidenceAgent(BaseAgent):
    name = "discussion_evidence"

    async def execute(self, payload: Dict[str, Any]) -> List[DiscussionEvidence]:
        if not key_present(settings.fetchlayer_api_key):
            log.warning("FETCHLAYER_API_KEY not set — skipping Reddit discussion agent")
            return []

        baseline = payload.get("baseline", [])
        # Discussion chatter is most meaningful for consumer-facing places.
        sample = [p for p in baseline if p.get("name")][:MAX_PLACES]

        headers = {
            "Authorization": f"Bearer {settings.fetchlayer_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=headers) as client:
            results = await gather_bounded(
                sample,
                lambda p: self._search_place(client, p),
                concurrency=5,
            )

        log.info(f"Discussion evidence: {len(results)} places with Reddit mentions")
        return results

    async def _search_place(self, client: httpx.AsyncClient, place: Dict) -> Optional[DiscussionEvidence]:
        name = place.get("name", "").strip()
        if not name:
            return None

        query = f"{name} Singapore"
        url = f"{settings.fetchlayer_base_url.rstrip('/')}/reddit/search"
        try:
            resp = await client.post(url, json={"query": query, "limit": POSTS_PER_QUERY, "sort": "top"})
            if resp.status_code != 200:
                log.debug(f"fetchlayer {resp.status_code} for '{query}'")
                return None
            posts = self._extract_posts(resp.json())
        except Exception as e:
            log.debug(f"fetchlayer error for '{query}': {e}")
            return None

        if not posts:
            return None

        # Keep only posts that actually mention the place name (reduce noise).
        name_lc = name.lower()
        relevant = [p for p in posts if name_lc in (p.get("text", "").lower())] or posts

        mention_type, sentiment, top = self._classify(relevant, name_lc)
        if top is None:
            return None

        lat, lng = extract_latlng(place)
        return DiscussionEvidence(
            source_type=SourceTypeEnum.reddit,
            source_url=top.get("url"),
            confidence=0.45 + (0.1 if mention_type in ("closing", "opening", "rebrand") else 0.0),
            freshness=FreshnessLabel.recent,
            platform="reddit",
            thread_title=top.get("title"),
            thread_url=top.get("url"),
            mention_type=mention_type,
            sentiment=sentiment,
            snippet=(top.get("body") or top.get("title") or "")[:240],
            raw_data={
                "name": name,
                "lat": lat,
                "lng": lng,
                "query": query,
                "post_count": len(relevant),
                "subreddit": top.get("subreddit"),
            },
        )

    @staticmethod
    def _extract_posts(data: Any) -> List[Dict]:
        """Normalize fetchlayer's response into a list of {title, body, url, subreddit, text}."""
        if isinstance(data, dict):
            raw = data.get("data") or data.get("results") or data.get("posts") or []
        elif isinstance(data, list):
            raw = data
        else:
            raw = []
        posts = []
        for r in raw:
            if not isinstance(r, dict):
                continue
            title = r.get("title") or ""
            body = r.get("selftext") or r.get("body") or r.get("text") or ""
            url = r.get("url") or r.get("permalink") or r.get("link")
            if url and isinstance(url, str) and url.startswith("/"):
                url = "https://www.reddit.com" + url
            posts.append({
                "title": title,
                "body": body,
                "url": url,
                "subreddit": r.get("subreddit") or r.get("subreddit_name_prefixed"),
                "text": f"{title} {body}",
            })
        return posts

    @staticmethod
    def _classify(posts: List[Dict], name_lc: str):
        """Return (mention_type, sentiment, representative_post)."""
        if not posts:
            return "review", "neutral", None

        close_hits = open_hits = rebrand_hits = 0
        pos_hits = neg_hits = 0
        for p in posts:
            t = p.get("text", "").lower()
            if any(term in t for term in CLOSING_TERMS):
                close_hits += 1
            if any(term in t for term in OPENING_TERMS):
                open_hits += 1
            if any(term in t for term in REBRAND_TERMS):
                rebrand_hits += 1
            pos_hits += sum(1 for term in POSITIVE_TERMS if term in t)
            neg_hits += sum(1 for term in NEGATIVE_TERMS if term in t)

        if close_hits and close_hits >= open_hits:
            mention_type = "closing"
        elif open_hits:
            mention_type = "opening"
        elif rebrand_hits:
            mention_type = "rebrand"
        else:
            mention_type = "review"

        if neg_hits > pos_hits:
            sentiment = "negative"
        elif pos_hits > neg_hits:
            sentiment = "positive"
        else:
            sentiment = "neutral"

        # Representative post: prefer one matching the detected mention type.
        rep = posts[0]
        type_terms = {"closing": CLOSING_TERMS, "opening": OPENING_TERMS, "rebrand": REBRAND_TERMS}.get(mention_type)
        if type_terms:
            for p in posts:
                if any(term in p.get("text", "").lower() for term in type_terms):
                    rep = p
                    break
        return mention_type, sentiment, rep
