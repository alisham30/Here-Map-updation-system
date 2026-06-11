# pyre-ignore-all-errors
# ============================================================================
# PlaceIQ — SQLAlchemy ORM models with PostGIS
# ============================================================================
from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime, Text, JSON,
    ForeignKey, Index, Enum as SAEnum
)
from sqlalchemy.orm import declarative_base, relationship
from geoalchemy2 import Geometry

Base = declarative_base()


class BaselinePlace(Base):
    __tablename__ = "baseline_places"

    place_id = Column(String(36), primary_key=True)
    osm_id = Column(String(64), index=True)
    name = Column(String(512), nullable=False, default="")
    brand = Column(String(256))
    category = Column(String(128), index=True)
    amenity = Column(String(128))
    tourism = Column(String(128))
    source_layer = Column(String(128), index=True)
    geom = Column(Geometry("POINT", srid=4326), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    address = Column(String(512))
    postal_code = Column(String(16), index=True)
    phone = Column(String(64))
    website = Column(String(512))
    opening_hours = Column(String(512))
    cuisine = Column(String(256))
    properties = Column(JSON, default={})
    ingested_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_baseline_geom", "geom", postgresql_using="gist"),
        Index("idx_baseline_name_trgm", "name", postgresql_using="gin",
              postgresql_ops={"name": "gin_trgm_ops"}),
    )


class EvidenceRecord(Base):
    __tablename__ = "evidence_records"

    evidence_id = Column(String(36), primary_key=True)
    record_id = Column(String(36), ForeignKey("intelligence_records.record_id"), index=True)
    source_type = Column(String(64), nullable=False, index=True)
    source_url = Column(String(1024))
    confidence = Column(Float, default=0.5)
    freshness = Column(String(32), default="moderate")
    extracted_at = Column(DateTime, default=datetime.utcnow)

    # Common extracted fields
    extracted_name = Column(String(512))
    extracted_brand = Column(String(256))
    extracted_address = Column(String(512))
    extracted_postal = Column(String(16))
    extracted_phone = Column(String(64))
    extracted_hours = Column(String(512))
    extracted_category = Column(String(128))

    # Source-specific
    is_available = Column(Boolean, default=True)
    platform = Column(String(64))
    rating = Column(Float)
    review_count = Column(Integer, default=0)
    visual_state = Column(String(32))
    sign_text = Column(String(512))
    website_state = Column(String(32))

    # Full data
    raw_data = Column(JSON, default={})

    record = relationship("IntelligenceRecord", back_populates="evidence_records")


class IntelligenceRecord(Base):
    __tablename__ = "intelligence_records"

    record_id = Column(String(36), primary_key=True)
    baseline_place_id = Column(String(36), ForeignKey("baseline_places.place_id"), index=True)
    detected_name = Column(String(512), nullable=False, default="")
    detected_brand = Column(String(256))
    geom = Column(Geometry("POINT", srid=4326))
    latitude = Column(Float)
    longitude = Column(Float)
    address = Column(String(512))
    postal_code = Column(String(16))
    category = Column(String(128), index=True)
    source_layer = Column(String(128))

    # Status & scoring
    status = Column(String(32), default="uncertain", index=True)
    confidence = Column(Float, default=0.0)
    freshness = Column(String(32), default="moderate")

    # Evidence aggregation
    source_count = Column(Integer, default=0)
    source_types = Column(JSON, default=[])
    source_agreement = Column(Float, default=0.0)
    source_conflicts = Column(JSON, default=[])

    # Match info
    match_type = Column(String(32))
    match_score = Column(Float, default=0.0)
    nearest_baseline_name = Column(String(512))
    nearest_baseline_distance_m = Column(Float)

    # Signal flags
    website_state = Column(String(32))
    delivery_available = Column(Boolean)
    social_active = Column(Boolean)
    visual_state = Column(String(32))
    discussion_sentiment = Column(String(32))

    # Timestamps
    first_detected = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow)

    # Review
    review_needed = Column(Boolean, default=False, index=True)
    review_reason = Column(Text)
    reviewed_by = Column(String(128))
    reviewed_at = Column(DateTime)
    review_action = Column(String(32))
    final_status = Column(String(32))

    evidence_records = relationship("EvidenceRecord", back_populates="record")

    __table_args__ = (
        Index("idx_intel_geom", "geom", postgresql_using="gist"),
        Index("idx_intel_status", "status"),
    )


class ReviewQueueItem(Base):
    __tablename__ = "review_queue"

    queue_id = Column(String(36), primary_key=True)
    record_id = Column(String(36), ForeignKey("intelligence_records.record_id"), index=True)
    place_name = Column(String(512))
    latitude = Column(Float)
    longitude = Column(Float)
    status = Column(String(32))
    confidence = Column(Float)
    review_reason = Column(Text)
    evidence_summary = Column(Text)
    source_types = Column(JSON, default=[])
    created_at = Column(DateTime, default=datetime.utcnow)
    priority = Column(Integer, default=0, index=True)
    assigned_to = Column(String(128))
    resolved = Column(Boolean, default=False, index=True)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    run_id = Column(String(36), primary_key=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    status = Column(String(32), default="running")
    baseline_count = Column(Integer, default=0)
    candidates_extracted = Column(Integer, default=0)
    new_detected = Column(Integer, default=0)
    closed_detected = Column(Integer, default=0)
    rebranded_detected = Column(Integer, default=0)
    uncertain_count = Column(Integer, default=0)
    active_confirmed = Column(Integer, default=0)
    log = Column(JSON, default=[])
