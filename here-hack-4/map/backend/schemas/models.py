# pyre-ignore-all-errors
# ============================================================================
# PlaceIQ — Pydantic schemas for all data models
# ============================================================================
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
import uuid


def _uid() -> str:
    return str(uuid.uuid4())[:12]


# ── Enums ───────────────────────────────────────────────────────────────────

class PlaceStatusEnum(str, Enum):
    active = "active"
    new_place = "new_place"
    closed = "closed"
    rebranded = "rebranded"
    uncertain = "uncertain"


class SourceTypeEnum(str, Enum):
    baseline_geojson = "baseline_geojson"
    official_website = "official_website"
    grabfood = "grabfood"
    foodpanda = "foodpanda"
    yelp = "yelp"
    social_media = "social_media"
    reddit = "reddit"
    stb_tourism = "stb_tourism"
    visual_street = "visual_street"
    acra_registry = "acra_registry"
    public_listing = "public_listing"
    tripadvisor = "tripadvisor"


class ReviewAction(str, Enum):
    approve_new = "approve_new"
    approve_closed = "approve_closed"
    approve_rebrand = "approve_rebrand"
    mark_active = "mark_active"
    reject = "reject"
    need_more_evidence = "need_more_evidence"


class MatchType(str, Enum):
    strong_match = "strong_match"
    possible_rebrand = "possible_rebrand"
    likely_new = "likely_new"
    ambiguous = "ambiguous"


class FreshnessLabel(str, Enum):
    very_recent = "very_recent"
    recent = "recent"
    moderate = "moderate"
    stale = "stale"


# ── Coordinates ─────────────────────────────────────────────────────────────

class Coordinates(BaseModel):
    latitude: float
    longitude: float


# ── BaselinePlace ───────────────────────────────────────────────────────────

class BaselinePlace(BaseModel):
    place_id: str = Field(default_factory=_uid)
    osm_id: Optional[str] = None
    name: str = ""
    brand: Optional[str] = None
    category: str = ""
    amenity: Optional[str] = None
    tourism: Optional[str] = None
    source_layer: str = ""
    coordinates: Coordinates
    address: Optional[str] = None
    postal_code: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    opening_hours: Optional[str] = None
    cuisine: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)
    ingested_at: datetime = Field(default_factory=datetime.utcnow)


# ── Evidence Records ────────────────────────────────────────────────────────

class EvidenceBase(BaseModel):
    evidence_id: str = Field(default_factory=_uid)
    source_type: SourceTypeEnum
    source_url: Optional[str] = None
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    confidence: float = 0.5
    freshness: FreshnessLabel = FreshnessLabel.moderate
    raw_data: Dict[str, Any] = Field(default_factory=dict)


class WebsiteEvidence(EvidenceBase):
    source_type: SourceTypeEnum = SourceTypeEnum.official_website
    business_name: Optional[str] = None
    brand_name: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    opening_hours: Optional[str] = None
    has_booking: bool = False
    has_menu: bool = False
    has_reservation: bool = False
    closure_keywords_found: List[str] = Field(default_factory=list)
    reopening_keywords_found: List[str] = Field(default_factory=list)
    relocation_keywords_found: List[str] = Field(default_factory=list)
    grand_opening_keywords: List[str] = Field(default_factory=list)
    social_links: List[str] = Field(default_factory=list)
    copyright_year: Optional[int] = None
    last_update_signal: Optional[str] = None
    website_state: str = "active"  # active | inactive | error | parked


class DeliveryEvidence(EvidenceBase):
    platform: str = ""  # grabfood | foodpanda
    merchant_name: Optional[str] = None
    merchant_id: Optional[str] = None
    address: Optional[str] = None
    category: Optional[str] = None
    is_available: bool = True
    has_delivery: bool = False
    has_pickup: bool = False
    estimated_hours: Optional[str] = None
    menu_item_count: int = 0
    rating: Optional[float] = None
    review_count: int = 0
    last_active: Optional[str] = None


class SocialEvidence(EvidenceBase):
    source_type: SourceTypeEnum = SourceTypeEnum.social_media
    platform: str = ""
    profile_name: Optional[str] = None
    profile_url: Optional[str] = None
    follower_count: int = 0
    last_post_date: Optional[str] = None
    post_frequency: Optional[str] = None
    location_tagged: Optional[str] = None
    brand_consistent: bool = True
    activity_level: str = "unknown"  # active | dormant | inactive


class DiscussionEvidence(EvidenceBase):
    source_type: SourceTypeEnum = SourceTypeEnum.reddit
    platform: str = "reddit"
    thread_title: Optional[str] = None
    thread_url: Optional[str] = None
    mention_type: str = ""  # opening | closing | rebrand | review | complaint
    sentiment: str = "neutral"  # positive | negative | neutral
    mention_date: Optional[str] = None
    snippet: Optional[str] = None


class ListingEvidence(EvidenceBase):
    source_type: SourceTypeEnum = SourceTypeEnum.public_listing
    listing_name: Optional[str] = None
    listing_url: Optional[str] = None
    address: Optional[str] = None
    category: Optional[str] = None
    rating: Optional[float] = None
    review_count: int = 0
    hours: Optional[str] = None
    phone: Optional[str] = None
    first_listed: Optional[str] = None
    is_active: bool = True


class TripAdvisorReview(BaseModel):
    review_id: str
    title: Optional[str] = None
    text: Optional[str] = None
    rating: int = 0
    published_date: Optional[str] = None  # ISO date string
    age_days: int = 0
    recency_weight: float = 1.0  # 1.0 = newest, 0.3 = oldest


class TripAdvisorEvidence(EvidenceBase):
    source_type: SourceTypeEnum = SourceTypeEnum.tripadvisor
    location_id: Optional[str] = None
    listing_name: Optional[str] = None
    address: Optional[str] = None
    category: Optional[str] = None
    rating: Optional[float] = None
    review_count: int = 0
    is_permanently_closed: bool = False
    is_active: bool = True
    # Fuzzy match score between candidate name and baseline name
    name_match_score: float = 0.0
    # Weighted average rating using recency weights
    weighted_avg_rating: Optional[float] = None
    # Most recent review date seen
    latest_review_date: Optional[str] = None
    # Recency-weighted confidence boost applied
    recency_boost: float = 0.0
    reviews: List[TripAdvisorReview] = Field(default_factory=list)


class VisualEvidence(EvidenceBase):
    source_type: SourceTypeEnum = SourceTypeEnum.visual_street
    image_url: Optional[str] = None
    image_date: Optional[str] = None
    visual_state: str = "unknown"  # open | closed | construction | vacant | changed
    sign_text: Optional[str] = None
    sign_match_score: float = 0.0
    storefront_presence_score: float = 0.0
    visual_confidence: float = 0.0
    signage_changed: bool = False
    storefront_replaced: bool = False


# ── Match Result ────────────────────────────────────────────────────────────

class MatchScore(BaseModel):
    coordinate_score: float = 0.0
    name_score: float = 0.0
    address_score: float = 0.0
    category_score: float = 0.0
    brand_score: float = 0.0
    sign_text_score: float = 0.0
    composite: float = 0.0


class MatchResult(BaseModel):
    match_id: str = Field(default_factory=_uid)
    candidate_id: str
    baseline_place_id: Optional[str] = None
    match_type: MatchType
    scores: MatchScore = Field(default_factory=MatchScore)
    distance_m: Optional[float] = None
    matched_baseline_name: Optional[str] = None


# ── Place Intelligence Record (fused) ──────────────────────────────────────

class PlaceIntelligenceRecord(BaseModel):
    record_id: str = Field(default_factory=_uid)
    baseline_place_id: Optional[str] = None
    detected_name: str = ""
    detected_brand: Optional[str] = None
    coordinates: Coordinates
    address: Optional[str] = None
    postal_code: Optional[str] = None
    category: str = ""
    source_layer: Optional[str] = None

    # Status
    status: PlaceStatusEnum = PlaceStatusEnum.uncertain
    confidence: float = 0.0
    freshness: FreshnessLabel = FreshnessLabel.moderate

    # Evidence summary
    evidence_ids: List[str] = Field(default_factory=list)
    source_types: List[str] = Field(default_factory=list)
    source_count: int = 0
    source_agreement: float = 0.0
    source_conflicts: List[str] = Field(default_factory=list)

    # Matching
    match_result: Optional[MatchResult] = None
    nearest_baseline_name: Optional[str] = None
    nearest_baseline_distance_m: Optional[float] = None

    # Signals
    website_state: Optional[str] = None
    delivery_available: Optional[bool] = None
    social_active: Optional[bool] = None
    visual_state: Optional[str] = None
    discussion_sentiment: Optional[str] = None

    # Timestamps
    first_detected: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    # Review
    review_needed: bool = False
    review_reason: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_action: Optional[ReviewAction] = None
    final_status: Optional[PlaceStatusEnum] = None


# ── Fused Record (pipeline working shape) ───────────────────────────────────
# The orchestrator passes plain dicts between fusion → decision for speed, but
# we validate them through this typed model at the fusion boundary so coordinate
# types, booleans, and source lists are coerced/checked before scoring. Extra
# keys are allowed because the decision agent enriches the record afterwards.

class FusedRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    detected_name: str = "Unknown"
    detected_brand: Optional[str] = None
    latitude: float = 0.0
    longitude: float = 0.0
    address: Optional[str] = None
    category: str = ""
    source_type: str = "unknown"

    # Matching
    match_type: str = "likely_new"
    match_score: float = 0.0
    nearest_baseline_name: Optional[str] = None
    nearest_baseline_distance_m: Optional[float] = None
    baseline_place_id: Optional[str] = None

    # Source tracking
    source_types: List[str] = Field(default_factory=list)
    source_count: int = 0
    evidence_ids: List[str] = Field(default_factory=list)

    # Operational signals
    website_state: Optional[str] = None
    delivery_available: Optional[bool] = None
    social_active: Optional[bool] = None
    visual_state: Optional[str] = None
    sign_text: Optional[str] = None
    image_explanation: Optional[str] = None
    discussion_sentiment: Optional[str] = None
    image_url: Optional[str] = None
    captured_at: Optional[str] = None
    age_label: Optional[str] = None
    recency_weight: Optional[float] = None

    # TripAdvisor signals
    ta_permanently_closed: Optional[bool] = None
    ta_review_count: Optional[int] = None
    ta_recency_boost: Optional[float] = None
    ta_weighted_avg_rating: Optional[float] = None
    ta_is_active: Optional[bool] = None

    # Gov / OneMap signals
    gov_status_negative: Optional[bool] = None
    gov_confirmed_active: Optional[bool] = None
    onemap_found: Optional[bool] = None
    onemap_revgeo_found: Optional[bool] = None
    onemap_found_nearby: Optional[bool] = None

    # Decision outputs (filled later)
    status: str = "uncertain"
    confidence: float = 0.0
    freshness: str = "moderate"
    review_needed: bool = False


# ── Review Queue Item ───────────────────────────────────────────────────────

class ReviewQueueItem(BaseModel):
    queue_id: str = Field(default_factory=_uid)
    record_id: str
    place_name: str = ""
    coordinates: Coordinates
    status: PlaceStatusEnum
    confidence: float = 0.0
    review_reason: str = ""
    evidence_summary: str = ""
    source_types: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    priority: int = 0  # higher = more urgent
    assigned_to: Optional[str] = None
    resolved: bool = False


# ── Dashboard Summary ───────────────────────────────────────────────────────

class DashboardSummary(BaseModel):
    total_baseline: int = 0
    total_new: int = 0
    total_closed: int = 0
    total_rebranded: int = 0
    total_active: int = 0
    total_uncertain: int = 0
    review_queue_size: int = 0
    category_counts: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    source_contribution: Dict[str, int] = Field(default_factory=dict)
    freshness_distribution: Dict[str, int] = Field(default_factory=dict)
    last_pipeline_run: Optional[datetime] = None


# ── Agent Messages ──────────────────────────────────────────────────────────

class AgentTask(BaseModel):
    task_id: str = Field(default_factory=_uid)
    agent_name: str
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 0


class AgentResult(BaseModel):
    task_id: str
    agent_name: str
    success: bool = True
    data: Any = None
    error: Optional[str] = None
    elapsed_s: float = 0.0


# ── GeoJSON helpers ─────────────────────────────────────────────────────────

class GeoJSONFeature(BaseModel):
    type: str = "Feature"
    geometry: Dict[str, Any]
    properties: Dict[str, Any]


class GeoJSONCollection(BaseModel):
    type: str = "FeatureCollection"
    features: List[GeoJSONFeature] = Field(default_factory=list)
