# pyre-ignore-all-errors
# ============================================================================
# API Routes — NLP Search (GPT-4o geospatial query grounding + ranking)
# ============================================================================
"""
Natural-language POI search over the pipeline's classified places.

Pipeline:
  1. GROUND  — GPT-4o extracts structured grounding from the query:
                 intent (find / check_status / find_new / find_closed / find_rebranded),
                 entity_type (e.g. "vegetarian restaurant", "hotel"),
                 location_scope (e.g. "Orchard Road", "near Marina Bay", "all Singapore"),
                 status_filter (active/new_place/closed/rebranded/uncertain or null).
  2. PREFILTER — a fast lexical pass narrows large candidate sets to a bounded
                 shortlist so the LLM call stays cheap and accurate.
  3. RANK     — GPT-4o ranks the shortlist against the grounded intent.

Falls back cleanly to lexical ranking when no OpenAI key is configured, so the
endpoint always returns useful results.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app_state import get_state, get_baseline_agent
from backend.agents._util import key_present
from backend.config import settings

router = APIRouter(prefix="/api", tags=["nlp"])
log = logging.getLogger("nlp_routes")

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4o"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
LLM_SHORTLIST = 60   # max candidates handed to the LLM for ranking


class NLPSearchRequest(BaseModel):
    query: str = Field(min_length=2)
    limit: int = Field(default=50, ge=1, le=300)
    use_full: bool = False


def _compact_record(r: Dict[str, Any], idx: int) -> Dict[str, Any]:
    return {
        "idx": idx,
        "name": r.get("detected_name") or r.get("name") or "",
        "category": r.get("category") or "",
        "cuisine": r.get("cuisine") or "",
        "address": r.get("address") or "",
        "status": r.get("status") or "uncertain",
        "source_layer": r.get("source_layer") or "",
        "latitude": r.get("latitude"),
        "longitude": r.get("longitude"),
    }


def _build_universe() -> List[Dict[str, Any]]:
    """
    The searchable universe = the full baseline map (10k+ POIs), enriched with the
    pipeline's verdict where it has run. This lets a query like "seafood" find every
    seafood place on the map, not just the handful the last run classified.
    """
    baseline = []
    agent = get_baseline_agent()
    if agent is not None:
        baseline = agent.places or []

    state = get_state()
    classified = state.get("records", []) or []
    # Index the pipeline's verdicts by the baseline place they refer to.
    verdict_by_pid: Dict[str, Dict[str, Any]] = {}
    extra_new: List[Dict[str, Any]] = []
    for r in classified:
        pid = r.get("baseline_place_id")
        if pid:
            verdict_by_pid[pid] = r
        elif r.get("status") == "new_place":
            extra_new.append(r)  # discovered places not in the baseline

    universe: List[Dict[str, Any]] = []
    for p in baseline:
        v = verdict_by_pid.get(p.get("place_id"))
        merged = {
            "detected_name": p.get("name", ""),
            "category": p.get("category", ""),
            "cuisine": p.get("cuisine") or (p.get("properties", {}) or {}).get("cuisine") or "",
            "address": p.get("address", ""),
            "source_layer": p.get("source_layer", ""),
            "latitude": p.get("latitude"),
            "longitude": p.get("longitude"),
            "place_id": p.get("place_id"),
            # If the pipeline verified this place, use its verdict; otherwise it's an
            # existing, on-map POI (shown as active for search) and unverified.
            "status": v.get("status") if v else "active",
            "verified": bool(v),
        }
        if v:
            # Carry the full verified record (confidence, XAI, signals) for the UI.
            merged = {**v, **{k: merged[k] for k in ("cuisine", "verified")}}
            merged.setdefault("detected_name", p.get("name", ""))
        universe.append(merged)

    universe.extend(extra_new)
    return universe


def _extract_json(content: str) -> Dict[str, Any]:
    content = (content or "").strip()
    if "```" in content:
        parts = content.split("```")
        content = parts[1] if len(parts) > 1 else content
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        content = content[start:end + 1]
    try:
        return json.loads(content)
    except Exception:
        return {}


# ── Grounding heuristics (used for prefilter + as fallback) ───────────────────

VEG_ALIAS = {"veg", "vegan", "vegetarian", "plant", "plantbased", "plant-based"}
STATUS_HINTS = {
    "new": "new_place", "newly": "new_place", "opened": "new_place", "opening": "new_place",
    "closed": "closed", "shut": "closed", "closure": "closed", "defunct": "closed",
    "rebrand": "rebranded", "renamed": "rebranded",
    "active": "active", "open": "active",
}


def _heuristic_grounding(query: str) -> Dict[str, Any]:
    q = query.lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", q) if t]
    status_filter = next((v for k, v in STATUS_HINTS.items() if k in tokens), None)
    if any(t in VEG_ALIAS for t in tokens):
        entity_type = "vegetarian restaurant"
    elif "restaurant" in q or "food" in q or "eat" in q:
        entity_type = "restaurant"
    elif "hotel" in q or "stay" in q:
        entity_type = "hotel"
    elif "cafe" in q or "coffee" in q:
        entity_type = "cafe"
    else:
        entity_type = "any"
    m = re.search(r"\b(?:near|around|in|at)\s+([a-z0-9 ]{3,40})", q)
    location_scope = m.group(1).strip() if m else "all Singapore"
    intent = ("find_closed" if status_filter == "closed"
              else "find_new" if status_filter == "new_place"
              else "find_rebranded" if status_filter == "rebranded"
              else "find")
    return {
        "intent": intent,
        "entity_type": entity_type,
        "location_scope": location_scope,
        "status_filter": status_filter,
    }


def _lexical_scores(query: str, places: List[Dict[str, Any]]) -> List[tuple]:
    q = query.lower().strip()
    q_tokens = [t for t in re.split(r"[^a-z0-9]+", q) if t]
    wants_veg = any(t in VEG_ALIAS for t in q_tokens)
    g = _heuristic_grounding(query)
    scored = []
    for p in places:
        text = f"{p.get('name','')} {p.get('category','')} {p.get('cuisine','')} {p.get('address','')} {p.get('source_layer','')}".lower()
        score = sum(2 for t in q_tokens if t in text)
        # Seafood/cuisine queries: match the cuisine/source_layer strongly.
        if p.get('cuisine') and any(t in str(p.get('cuisine','')).lower() for t in q_tokens):
            score += 4
        if "restaurant" in q and "restaurant" in text:
            score += 3
        if "hotel" in q and "hotel" in text:
            score += 3
        if wants_veg and any(v in text for v in ("veg", "vegan", "vegetarian")):
            score += 4
        # status-aware boost
        if g.get("status_filter") and p.get("status") == g["status_filter"]:
            score += 5
        # location hint
        loc = g.get("location_scope", "")
        if loc and loc != "all Singapore" and loc in text:
            score += 4
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: -x[0])
    return scored


# ── LLM grounding + ranking (GPT-4o, Groq fallback) ───────────────────────────

GROUND_PROMPT = (
    "You are a geospatial POI search engine for Singapore. Given a user query and a "
    "list of candidate places (each with an 'idx'), return ONLY a JSON object:\n"
    "{\n"
    '  "intent": "find | find_new | find_closed | find_rebranded | check_status",\n'
    '  "entity_type": "what kind of place (e.g. vegetarian restaurant, hotel, cafe, any)",\n'
    '  "location_scope": "the area/landmark the user means, or \'all Singapore\'",\n'
    '  "status_filter": "active|new_place|closed|rebranded|uncertain or null",\n'
    '  "interpretation": "one-sentence plain-English reading of the query",\n'
    '  "match_indexes": [idx values best matching the query, best first],\n'
    '  "reason": "short rationale for the ranking"\n'
    "}\n"
    "Rules:\n"
    "- Use ONLY idx values that appear in the candidates.\n"
    "- Honor semantic meaning (e.g. 'veg' => vegetarian/vegan/plant-based).\n"
    "- If the query names a status (new/closed/rebranded), set status_filter and prefer those.\n"
    "- For 'near <place>' use name/address proximity hints from candidates.\n"
)


async def _llm_rank(query: str, places: List[Dict[str, Any]], limit: int) -> Dict[str, Any]:
    """Try GPT-4o first, then Groq. Returns {ok, grounding..., indexes} or {ok:False}."""
    user_payload = json.dumps({"query": query, "candidates": places}, ensure_ascii=False)
    messages = [
        {"role": "system", "content": GROUND_PROMPT + f"- Return at most {limit} indexes.\n"},
        {"role": "user", "content": user_payload},
    ]

    provider = None
    if key_present(settings.openai_api_key):
        provider = ("openai", OPENAI_URL, settings.openai_api_key, OPENAI_MODEL)
    elif key_present(settings.groq_api_key):
        provider = ("groq", GROQ_URL, settings.groq_api_key, settings.groq_model)
    if not provider:
        return {"ok": False, "error": "no LLM key (OPENAI_API_KEY / GROQ_API_KEY) configured"}

    name, url, api_key, model = provider
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "seed": 42,
        "max_tokens": 900,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code == 400:
                # Some models reject response_format — retry without it.
                body.pop("response_format", None)
                resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        parsed = _extract_json(content)
        idxs = parsed.get("match_indexes") or []
        idxs = [int(i) for i in idxs if str(i).lstrip("-").isdigit()]
        return {
            "ok": True,
            "provider": name,
            "intent": parsed.get("intent", ""),
            "entity_type": parsed.get("entity_type", ""),
            "location_scope": parsed.get("location_scope", ""),
            "status_filter": parsed.get("status_filter"),
            "interpretation": parsed.get("interpretation", ""),
            "reason": parsed.get("reason", ""),
            "indexes": idxs[:limit],
        }
    except Exception as e:
        log.warning(f"LLM NLP rank failed ({name}), falling back to lexical: {e}")
        return {"ok": False, "error": str(e)}


@router.post("/nlp/search")
async def nlp_search(req: NLPSearchRequest):
    # Search the FULL map (baseline enriched with pipeline verdicts), so a query
    # like "seafood" finds every seafood place on the map — not just the handful
    # the last pipeline run classified.
    records = _build_universe()

    if not records:
        return {
            "success": True,
            "query": req.query,
            "grounding": _heuristic_grounding(req.query),
            "interpretation": "Baseline map not loaded yet.",
            "reason": "Empty result set",
            "matches": [],
            "used_model": "none",
        }

    compact = [_compact_record(r, i) for i, r in enumerate(records)]

    # ── Prefilter: narrow large sets to a bounded shortlist for the LLM ──
    scored = _lexical_scores(req.query, compact)
    if scored:
        shortlist = [p for _, p in scored[:LLM_SHORTLIST]]
    else:
        shortlist = compact[:LLM_SHORTLIST]   # nothing matched lexically — let the LLM judge

    llm = await _llm_rank(req.query, shortlist, req.limit)

    if llm.get("ok"):
        grounding = {
            "intent": llm.get("intent"),
            "entity_type": llm.get("entity_type"),
            "location_scope": llm.get("location_scope"),
            "status_filter": llm.get("status_filter"),
        }
        indexes = list(llm.get("indexes", []))
        interpretation = llm.get("interpretation", "")
        reason = llm.get("reason", "")
        used = llm.get("provider", "llm")
    else:
        grounding = _heuristic_grounding(req.query)
        indexes = []
        interpretation = "Keyword + status-aware lexical ranking (LLM unavailable)."
        reason = llm.get("error", "LLM unavailable")
        used = "fallback"

    # Show the FULL category set: the LLM's best picks first (semantic order), then
    # every other lexical match appended, so "seafood" returns ALL seafood places,
    # not just the top few the LLM happened to list.
    seen = set(indexes)
    for _, p in scored:
        i = p["idx"]
        if i not in seen:
            indexes.append(i)
            seen.add(i)
        if len(indexes) >= req.limit:
            break

    # Honor an explicit status filter (e.g. "active seafood" → only active).
    sf = grounding.get("status_filter") if isinstance(grounding, dict) else None
    matches = []
    for i in indexes:
        if 0 <= i < len(records):
            r = records[i]
            if sf and r.get("status") != sf:
                continue
            matches.append(r)

    return {
        "success": True,
        "query": req.query,
        "grounding": grounding,
        "interpretation": interpretation,
        "reason": reason,
        "matches": matches,
        "used_model": used,
        "candidate_count": len(records),
        "shortlisted": len(shortlist),
    }
