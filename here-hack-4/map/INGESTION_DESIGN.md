# Place-Change Detection System: Baseline Data Ingestion & Normalization Layer

**Author**: Senior Geospatial Data Engineer  
**Date**: March 26, 2026  
**Version**: 1.0  
**Scope**: Baseline data ingestion and schema normalization only

---

## A. Goal of Ingestion Layer

The ingestion layer serves as the foundation for the place-change detection system. Its primary goals are:

1. **Unified Data Ingestion**: Load all 10 baseline GeoJSON files from disparate sources and consolidate into a single canonical dataset
2. **Schema Normalization**: Transform heterogeneous raw OSM properties into a standardized schema that supports downstream evidence matching and change detection
3. **Data Quality & Traceability**: Preserve source-file lineage and raw properties for audit trails and debugging
4. **Duplicate Detection & Deduplication**: Identify and flag duplicate place records before normalizing
5. **Standardized Geometry**: Convert all geometries to lat/lon coordinate pairs for consistency
6. **Category Standardization**: Map diverse amenity types to a controlled taxonomy suitable for change detection
7. **Readiness for Website Matching**: Structure the schema to enable later matching against website URLs, business hours, and website-scraped metadata

**Non-Goals**:
- Website scraping or web discovery
- Evidence scoring or confidence modeling
- Change detection algorithms
- Dashboard or visualization logic

---

## B. Ingestion Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                   BASELINE DATA INGESTION WORKFLOW              │
└─────────────────────────────────────────────────────────────────┘

Step 1: FILE DISCOVERY & LOADING
  ├─ Scan /data/baseline/ directory for GeoJSON files
  ├─ Load each file with source_file tracking
  ├─ Validate GeoJSON format (FeatureCollection)
  └─ Extract timestamp from each source file

Step 2: RAW FEATURE EXTRACTION
  ├─ Iterate through features in each GeoCollection
  ├─ Preserve raw properties as-is
  ├─ Record source_file and original_id (@id)
  └─ Extract geometry coordinates

Step 3: GEOMETRY NORMALIZATION
  ├─ Convert GeoJSON coordinates to lat/lon pair
  ├─ Extract geometry_type (Point -> point)
  ├─ Handle missing/invalid coordinates → flag_as_invalid
  └─ Store geometry_valid flag

Step 4: CATEGORY MAPPING
  ├─ Extract amenity type from properties
  ├─ Map to normalized category using mapping table
  ├─ Extract cuisine/brand/type for subcategory
  ├─ Apply category hierarchy logic
  └─ Handle unmapped categories → "uncategorized"

Step 5: PROPERTY NORMALIZATION
  ├─ Extract and standardize name
  ├─ Normalize address (street + city + postcode)
  ├─ Extract contact info (phone, website, email)
  ├─ Parse opening_hours into normalized format
  ├─ Handle missing fields → null or empty_string
  └─ Collect all non-matched fields → metadata

Step 6: DUPLICATE DETECTION
  ├─ Generate fingerprint: (name, normalized_address, lat, lon)
  ├─ Calculate geographic distance to other records
  ├─ Flag probable duplicates with duplicate_score
  ├─ Mark duplicate_flag and duplicate_cluster_id
  └─ Keep all duplicates (don't delete yet)

Step 7: BASELINE_PLACE_ID GENERATION
  ├─ UUID v5 from: (category, lat, lon, name_hash)
  ├─ Ensures deterministic ID generation
  ├─ Supports reproducibility across runs
  └─ Enables tracking of splits/merges

Step 8: SCHEMA NORMALIZATION
  ├─ Map all raw properties to unified schema
  ├─ Create normalized_record object
  ├─ Preserve original_properties for traceability
  ├─ Add metadata section with processing flags
  └─ Timestamp the ingestion_timestamp

Step 9: OUTPUT SERIALIZATION
  ├─ Output GeoJSON FeatureCollection
  ├─ Output Parquet for analytics
  ├─ Output SQLite for fast querying
  ├─ Output summary stats & validation report
  └─ Track ingestion session_id

Step 10: QUALITY VALIDATION & REPORTING
  ├─ Count records by category
  ├─ Flag geometry_invalid records
  ├─ Flag incomplete records (missing required fields)
  ├─ Flag probable duplicates
  ├─ Generate ingestion report with stats
  └─ Create validation log for review
```

---

## C. Unified Normalized Schema

### Core Schema Structure

```json
{
  "baseline_place_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "The Coffee Bean & Tea Leaf",
  "category": "food_beverage",
  "subcategory": "cafe",
  "latitude": 1.4360981,
  "longitude": 103.7863694,
  "geometry_type": "point",
  "geometry_valid": true,
  "location": {
    "address": "103.76768, Upper Bukit Timah Road, Singapore 678051",
    "street": "Upper Bukit Timah Road",
    "housenumber": "422",
    "city": "Singapore",
    "postcode": "678051",
    "country": "SG",
    "formatted_address": "422 Upper Bukit Timah Road, Singapore 678051, SG"
  },
  "contact": {
    "phone": null,
    "email": null,
    "website": null
  },
  "hours": {
    "opening_hours": "24/7",
    "parsed_hours": {
      "monday": "00:00-23:59",
      "tuesday": "00:00-23:59",
      "wednesday": "00:00-23:59",
      "thursday": "00:00-23:59",
      "friday": "00:00-23:59",
      "saturday": "00:00-23:59",
      "sunday": "00:00-23:59",
      "is_open_24h": true
    },
    "last_check_date": "2024-08-29"
  },
  "source": {
    "source_file": "cafes.geojson",
    "original_id": "way/71400539",
    "source_type": "openstreetmap",
    "source_timestamp": "2026-03-26T11:12:31Z"
  },
  "original_properties": {
    "@id": "way/71400539",
    "addr:city": "Singapore",
    "addr:country": "SG",
    "addr:housenumber": "422",
    "addr:postcode": "678051",
    "addr:street": "Upper Bukit Timah Road",
    "air_conditioning": "yes",
    "amenity": "cafe",
    "brand": "The Coffee Bean & Tea Leaf",
    "brand:wikidata": "Q1141384",
    "building": "retail",
    "check_date": "2024-08-29",
    "cuisine": "coffee_shop",
    "internet_access": "wlan",
    "name": "The Coffee Bean & Tea Leaf",
    "opening_hours": "24/7",
    "outdoor_seating": "no",
    "payment:cash": "yes",
    "payment:credit_cards": "yes",
    "payment:debit_cards": "yes",
    "takeaway": "yes",
    "wheelchair": "limited"
  },
  "duplicates": {
    "duplicate_flag": false,
    "duplicate_score": 0.0,
    "duplicate_cluster_id": null,
    "duplicate_candidates": []
  },
  "metadata": {
    "ingestion_timestamp": "2026-03-26T14:30:00Z",
    "ingestion_session_id": "ingestion-2026-03-26-session-001",
    "raw_property_count": 22,
    "fields_missing": [],
    "fields_incomplete": [],
    "quality_score": 0.95,
    "validation_flags": [],
    "notes": ""
  }
}
```

### Schema Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `baseline_place_id` | UUID | ✓ | Unique deterministic ID (v5 hash) |
| `name` | string | ✓ | Normalized place name |
| `category` | string | ✓ | Primary category from taxonomy |
| `subcategory` | string | ✓ | Secondary category (cuisine, brand type, etc.) |
| `latitude` | float | ✓ | WGS84 latitude (-90 to 90) |
| `longitude` | float | ✓ | WGS84 longitude (-180 to 180) |
| `geometry_type` | string | ✓ | "point" (for baseline) |
| `geometry_valid` | bool | ✓ | Validation flag for coordinates |
| `location.address` | string | ✗ | Raw address concatenation |
| `location.street` | string | ✗ | Street address |
| `location.housenumber` | string | ✗ | Building/house number |
| `location.city` | string | ✗ | City name |
| `location.postcode` | string | ✗ | Postal code |
| `location.country` | string | ✗ | Country code (2-letter ISO) |
| `location.formatted_address` | string | ✗ | Human-readable formatted address |
| `contact.phone` | string | ✗ | Phone number |
| `contact.email` | string | ✗ | Email address |
| `contact.website` | string | ✗ | Website URL (for later website matching) |
| `hours.opening_hours` | string | ✗ | Raw OSM opening_hours string |
| `hours.parsed_hours` | object | ✗ | Parsed day-by-day hours |
| `hours.last_check_date` | date | ✗ | Last verification date |
| `source.source_file` | string | ✓ | Filename of origin GeoJSON |
| `source.original_id` | string | ✓ | Original OSM ID (way/relation/node) |
| `source.source_type` | string | ✓ | "openstreetmap" |
| `source.source_timestamp` | datetime | ✓ | When source file was created |
| `original_properties` | object | ✓ | Complete raw OSM properties (unindexed) |
| `duplicates.duplicate_flag` | bool | ✓ | True if probable duplicate detected |
| `duplicates.duplicate_score` | float | ✓ | 0.0-1.0 confidence of duplication |
| `duplicates.duplicate_cluster_id` | string | ✗ | Cluster ID for grouped duplicates |
| `duplicates.duplicate_candidates` | array | ✓ | List of candidate duplicate IDs |
| `metadata.ingestion_timestamp` | datetime | ✓ | When record was normalized |
| `metadata.ingestion_session_id` | string | ✓ | Session ID for batch processing |
| `metadata.raw_property_count` | int | ✓ | Count of original properties |
| `metadata.fields_missing` | array | ✓ | List of expected fields not present |
| `metadata.fields_incomplete` | array | ✓ | List of fields with partial data |
| `metadata.quality_score` | float | ✓ | 0.0-1.0 quality metric |
| `metadata.validation_flags` | array | ✓ | Specific validation issues |
| `metadata.notes` | string | ✗ | Free-form notes |

---

## D. Category Normalization Rules

### Category Hierarchy

**food_beverage**
- Cafes: `cafe`, `coffee_shop`, `tea_shop`
- Restaurants: `restaurant`, `fast_food`, `ice_cream`, `bakery`, `diner`
- Bars: `bar`, `pub`, `nightclub`, `beer_hall`

**accommodation**
- Hotels: `hotel`, `guest_house`, `hostel`, `motel`, `resort`, `holiday_rental`
- Lodging: `apartment`, `bed_and_breakfast`

**retail**
- Shopping Malls: `shopping_mall`, `shopping_center`, `market`, `bazaar`
- Groceries: `grocery_store`, `supermarket`, `farmers_market`, `convenience_store`
- Department Stores: `department_store`
- Pharmacies: `pharmacy`, `drugstore`

**fuel_energy**
- Fuel Stations: `fuel`, `gas_station`, `filling_station`, `petrol_station`

**recreation_tourism**
- Theme Parks: `theme_park`, `amusement_park`, `water_park`, `amusement_arcade`
- Tourist Attractions: `attraction`, `museum`, `monument`, `historic_site`, `viewpoint`, `park`, `nature_reserve`

**uncategorized**
- Unknown: `[unmapped amenity types]`

### Mapping Algorithm

```python
def normalize_category(raw_amenity, raw_properties):
    """
    Priority order:
    1. Direct amenity type match
    2. Cuisine type (for food amenities)
    3. Brand type inference
    4. Building type fallback
    5. Default to uncategorized
    """
    category_map = {
        # food_beverage
        'cafe': ('food_beverage', 'cafe'),
        'coffee_shop': ('food_beverage', 'cafe'),
        'tea_shop': ('food_beverage', 'cafe'),
        'restaurant': ('food_beverage', 'restaurant'),
        'fast_food': ('food_beverage', 'fast_food'),
        'ice_cream': ('food_beverage', 'ice_cream'),
        'bakery': ('food_beverage', 'bakery'),
        'bar': ('food_beverage', 'bar'),
        'pub': ('food_beverage', 'bar'),
        'nightclub': ('food_beverage', 'bar'),
        
        # accommodation
        'hotel': ('accommodation', 'hotel'),
        'guest_house': ('accommodation', 'hotel'),
        'hostel': ('accommodation', 'hotel'),
        'motel': ('accommodation', 'hotel'),
        'resort': ('accommodation', 'hotel'),
        'bed_and_breakfast': ('accommodation', 'hotel'),
        
        # retail
        'shopping_mall': ('retail', 'shopping_mall'),
        'shopping_center': ('retail', 'shopping_mall'),
        'supermarket': ('retail', 'grocery'),
        'grocery_store': ('retail', 'grocery'),
        'department_store': ('retail', 'department_store'),
        'pharmacy': ('retail', 'pharmacy'),
        'drugstore': ('retail', 'pharmacy'),
        
        # fuel
        'fuel': ('fuel_energy', 'fuel_station'),
        'gas_station': ('fuel_energy', 'fuel_station'),
        
        # tourism
        'theme_park': ('recreation_tourism', 'theme_park'),
        'amusement_park': ('recreation_tourism', 'theme_park'),
        'attraction': ('recreation_tourism', 'tourist_attraction'),
        'museum': ('recreation_tourism', 'tourist_attraction'),
        'monument': ('recreation_tourism', 'tourist_attraction'),
        'historic_site': ('recreation_tourism', 'tourist_attraction'),
    }
    
    # Direct lookup
    if raw_amenity in category_map:
        return category_map[raw_amenity]
    
    # Cuisine-based inference for restaurants
    if 'cuisine' in raw_properties:
        return ('food_beverage', 'restaurant')
    
    # Brand-based inference
    if 'brand' in raw_properties:
        brand = raw_properties['brand'].lower()
        if any(x in brand for x in ['coffee', 'cafe', 'tea']):
            return ('food_beverage', 'cafe')
        if any(x in brand for x in ['hotel', 'resort']):
            return ('accommodation', 'hotel')
    
    # Default
    return ('uncategorized', raw_amenity or 'unknown')
```

---

## E. Duplicate Handling Rules

### Duplicate Detection Strategy

Duplicates are flagged but **NOT deleted** at ingestion time. This preserves data integrity for audit trails and allows validation before deletion.

**Fingerprint Generation**:
```
fingerprint = SHA256(
    normalize(name) + 
    normalize(address) + 
    round(lat, 3) + 
    round(lon, 3)
)
```

**Matching Rules**:

| Match Type | Distance | Name Similarity | Score | Action |
|-----------|----------|-----------------|-------|--------|
| Exact Duplicate | < 5 meters | > 0.95 | 1.0 | Flag, cluster, investigate manually |
| Probable Duplicate | < 10 meters | > 0.85 | 0.8-1.0 | Flag, cluster, suggest merge |
| Near Duplicate | < 50 meters | > 0.80 | 0.5-0.7 | Flag for review |
| Different | > 50 meters | < 0.80 | < 0.5 | Keep separate |

**Duplicate Fields**:

```json
{
  "duplicate_flag": true,
  "duplicate_score": 0.92,
  "duplicate_cluster_id": "cluster-1234",
  "duplicate_candidates": [
    {
      "baseline_place_id": "550e8400-e29b-41d4-a716-446655440001",
      "name": "The Coffee Bean",
      "distance_meters": 3.5,
      "name_similarity": 0.93,
      "score": 0.95
    }
  ]
}
```

**Resolution Not Yet Implemented**:
- Manual deduplication rules (for website matching phase)
- Merge strategies for duplicate records
- Archival of superseded records

---

## F. Missing-Field Handling Rules

### Strategy: Preserve, Flag, Document

| Scenario | Field | Default | Flag | Action |
|----------|-------|---------|------|--------|
| Required but missing | `name` | `"[Name Unknown]"` | ✓ | Use placeholder, mark incomplete |
| Required but missing | `latitude` / `longitude` | `null` | ✓ | Mark as `geometry_invalid: true` |
| Optional and missing | `phone` | `null` | ✗ | Leave null |
| Optional and missing | `website` | `null` | ✗ | Leave null; will be filled by website scraping phase |
| Optional and missing | `opening_hours` | `null` | ✗ | Leave null; will be filled via evidence |
| Address partially missing | Address components | partial data | ✓ | Use available components, mark incomplete |
| Unparseable format | `opening_hours` | raw string stored | ✓ | Store raw, note parsing failure |

### Missing Field Flags

```json
{
  "metadata": {
    "fields_missing": ["phone", "email", "website"],
    "fields_incomplete": ["address"],
    "quality_score": 0.85,
    "validation_flags": [
      "missing_contact_info",
      "incomplete_address",
      "no_website_url"
    ]
  }
}
```

### Quality Score Calculation

```
quality_score = (
    (has_name ? 1 : 0) * 0.20 +
    (has_valid_geometry ? 1 : 0) * 0.20 +
    (has_category ? 1 : 0) * 0.15 +
    (has_address ? 1 : 0) * 0.15 +
    (has_phone_or_website ? 1 : 0) * 0.15 +
    (has_opening_hours ? 1 : 0) * 0.15
)
```

---

## G. Folder Structure

```
place-change-detection-system/
├── README.md
├── INGESTION_DESIGN.md                    # This document
│
├── data/
│   ├── baseline/                          # Raw baseline GeoJSON files
│   │   ├── cafes.geojson
│   │   ├── restaurants.geojson
│   │   ├── hotels.geojson
│   │   ├── pharmacies.geojson
│   │   ├── fuel_station.geojson
│   │   ├── grocery stores.geojson
│   │   ├── shopping_malls.geojson
│   │   ├── theme_parks.geojson
│   │   ├── tourism attraction.geojson
│   │   └── department_stores.geojson
│   │
│   ├── normalized/                        # Output normalized data
│   │   ├── baseline_normalized.geojson    # Full GeoJSON FeatureCollection
│   │   ├── baseline_normalized.parquet    # Parquet for analytics
│   │   ├── baseline_normalized.db         # SQLite for querying
│   │   ├── baseline_duplicates.json       # Flagged duplicates report
│   │   ├── baseline_quality_report.json   # QA/validation report
│   │   └── baseline_ingestion_log.txt     # Processing log
│   │
│   └── archives/                          # Historical snapshots
│       └── baseline_2026-03-26.backup/
│
├── src/
│   ├── __init__.py
│   ├── config.py                          # Configuration and constants
│   │
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── loader.py                      # GeoJSON file loading
│   │   ├── normalizer.py                  # Schema normalization
│   │   ├── category_mapper.py             # Category normalization
│   │   ├── geometry_handler.py            # Lat/lon extraction
│   │   ├── address_parser.py              # Address standardization
│   │   ├── hours_parser.py                # Opening hours parsing
│   │   ├── duplicate_detector.py          # Duplicate detection
│   │   ├── id_generator.py                # UUID v5 generation
│   │   └── quality_validator.py           # QA/validation logic
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── geojson_writer.py              # GeoJSON output
│   │   ├── parquet_writer.py              # Parquet output
│   │   ├── sqlite_writer.py               # SQLite output
│   │   └── backup_manager.py              # Backup/archive logic
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logger.py                      # Logging utilities
│   │   ├── distance.py                    # Haversine distance calc
│   │   ├── text_similarity.py             # String matching
│   │   ├── validators.py                  # Data validation helpers
│   │   └── time_utils.py                  # DateTime utilities
│   │
│   └── pipeline/
│       ├── __init__.py
│       └── ingestion_pipeline.py          # Main orchestration
│
├── tests/
│   ├── __init__.py
│   ├── test_loader.py
│   ├── test_normalizer.py
│   ├── test_category_mapper.py
│   ├── test_duplicate_detector.py
│   ├── test_quality_validator.py
│   └── fixtures/
│       └── sample_features.json           # Test fixtures
│
├── requirements.txt                       # Python dependencies
├── setup.py                               # Package setup
└── main.py                                # Entry point script
```

---

## H. Module/Function Design

### 1. **loader.py** - File Discovery & Loading

```python
class BaselineLoader:
    """Load all baseline GeoJSON files with source tracking."""
    
    def __init__(self, baseline_dir: str):
        """Initialize with baseline data directory."""
        
    def discover_files(self) -> List[str]:
        """Find all .geojson files in baseline directory."""
        
    def load_file(self, filepath: str, source_file: str) -> List[Dict]:
        """
        Load single GeoJSON file and extract features.
        Returns: List of (feature, source_file, timestamp)
        """
        
    def load_all(self) -> Dict[str, List[Dict]]:
        """
        Load all baseline files.
        Returns: {source_file: [features]}
        """
```

### 2. **normalizer.py** - Schema Normalization

```python
class PlaceNormalizer:
    """Normalize raw feature to unified schema."""
    
    def __init__(self, category_mapper, geometry_handler, address_parser):
        """Initialize with helper components."""
        
    def normalize(self, raw_feature: Dict, source_file: str) -> Dict:
        """
        Transform raw feature to normalized schema.
        
        Orchestrates:
        - geometry extraction
        - category mapping
        - property extraction
        - duplicate detection
        - baseline_place_id generation
        - quality scoring
        """
        
    def normalize_batch(self, features: List[Dict]) -> List[Dict]:
        """Normalize list of features, return normalized records."""
```

### 3. **category_mapper.py** - Category Normalization

```python
class CategoryMapper:
    """Map raw amenity types to normalized taxonomy."""
    
    def __init__(self, mapping_table_path: str):
        """Load category mapping table."""
        
    def get_category(self, raw_amenity: str, properties: Dict) -> Tuple[str, str]:
        """
        Return (category, subcategory) tuple.
        Implements priority: direct → cuisine → brand → fallback
        """
        
    def infer_subcategory(self, raw_amenity: str, properties: Dict) -> str:
        """Infer detailed subcategory from brand, cuisine, etc."""
```

### 4. **geometry_handler.py** - Coordinate Extraction

```python
class GeometryHandler:
    """Extract and validate geometry coordinates."""
    
    def extract_coordinates(self, geometry: Dict) -> Tuple[float, float, bool]:
        """
        Extract latitude, longitude from GeoJSON geometry.
        Returns: (lat, lon, is_valid)
        """
        
    def validate_coordinates(self, lat: float, lon: float) -> bool:
        """Validate WGS84 bounds: lat [-90,90], lon [-180,180]."""
        
    def calculate_centroid(self, geometry: Dict) -> Tuple[float, float]:
        """Calculate centroid for non-Point geometries."""
```

### 5. **address_parser.py** - Address Standardization

```python
class AddressParser:
    """Extract and normalize address components."""
    
    def parse_address(self, properties: Dict) -> Dict:
        """
        Extract address components from properties.
        Returns: {
            "street": ...,
            "housenumber": ...,
            "city": ...,
            "postcode": ...,
            "country": ...,
            "formatted_address": ...,
            "incomplete": [...]
        }
        """
        
    def format_address(self, address_parts: Dict) -> str:
        """Create human-readable formatted address."""
```

### 6. **hours_parser.py** - Opening Hours Parsing

```python
class HoursParser:
    """Parse OSM opening_hours format to normalized structure."""
    
    def parse_opening_hours(self, hours_str: str) -> Dict:
        """
        Parse OSM opening_hours format.
        Returns: {
            "is_open_24h": bool,
            "is_closed": bool,
            "parsed_hours": {
                "monday": "09:00-17:00",
                ...
                "sunday": "10:00-16:00"
            },
            "unparseable": bool,
            "raw_input": hours_str
        }
        """
        
    def normalize_day_hours(self, day: str, hours: str) -> str:
        """Normalize single day's hours to HH:MM-HH:MM format."""
```

### 7. **duplicate_detector.py** - Duplicate Detection

```python
class DuplicateDetector:
    """Identify probable duplicate place records."""
    
    def generate_fingerprint(self, record: Dict) -> str:
        """Generate SHA256 fingerprint from (name, address, lat, lon)."""
        
    def detect_duplicates(self, records: List[Dict]) -> List[Dict]:
        """
        Flag probable duplicates within record set.
        Modifies records to add duplicate fields.
        Returns: records with duplicate metadata populated
        """
        
    def calculate_match_score(self, rec1: Dict, rec2: Dict) -> float:
        """
        Calculate 0.0-1.0 probability that rec1 and rec2 are duplicates.
        Combines: geographic distance, name similarity, address match
        """
```

### 8. **id_generator.py** - Deterministic ID Generation

```python
class BaselineIDGenerator:
    """Generate deterministic UUID v5 baseline_place_id."""
    
    def generate_id(self, category: str, lat: float, lon: float, name: str) -> str:
        """
        Generate reproducible UUID v5.
        Namespace: (category, rounded_lat, rounded_lon, name_hash)
        """
```

### 9. **quality_validator.py** - QA & Validation

```python
class QualityValidator:
    """Validate normalized records and assign quality scores."""
    
    def validate_record(self, record: Dict) -> Dict:
        """
        Validate single record, add metadata.validation_flags.
        """
        
    def calculate_quality_score(self, record: Dict) -> float:
        """
        Calculate 0.0-1.0 quality score based on:
        - presence of required fields
        - geometry validity
        - address completeness
        - contact info
        """
        
    def generate_validation_report(self, records: List[Dict]) -> Dict:
        """
        Generate summary validation report:
        - record counts by category
        - geometry_invalid count
        - duplicate flags
        - quality score distribution
        - missing field frequencies
        """
```

### 10. **ingestion_pipeline.py** - Orchestration

```python
class IngestionPipeline:
    """Orchestrate complete baseline ingestion workflow."""
    
    def __init__(self, config: Config):
        """Initialize with configuration."""
        
    def run(self) -> IngestionResult:
        """
        Execute full ingestion pipeline:
        1. Load all GeoJSON files
        2. Normalize each feature
        3. Detect duplicates
        4. Generate validation report
        5. Write outputs to all formats
        6. Create backup/archive
        
        Returns: IngestionResult with summary stats
        """
```

### 11. **Storage Writers**

```python
class GeoJSONWriter:
    """Write normalized records to GeoJSON FeatureCollection."""
    def write(self, records: List[Dict], filepath: str) -> None: ...

class ParquetWriter:
    """Write normalized records to Parquet for analytics."""
    def write(self, records: List[Dict], filepath: str) -> None: ...

class SQLiteWriter:
    """Write normalized records to SQLite with indexes."""
    def write(self, records: List[Dict], filepath: str) -> None: ...
```

---

## I. Example Normalized Record

```json
{
  "type": "Feature",
  "properties": {
    "baseline_place_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "The Coffee Bean & Tea Leaf",
    "category": "food_beverage",
    "subcategory": "cafe",
    "latitude": 1.4360981,
    "longitude": 103.7863694,
    "geometry_type": "point",
    "geometry_valid": true,
    "location": {
      "address": "422 Upper Bukit Timah Road, Singapore 678051, SG",
      "street": "Upper Bukit Timah Road",
      "housenumber": "422",
      "city": "Singapore",
      "postcode": "678051",
      "country": "SG",
      "formatted_address": "422 Upper Bukit Timah Road, Singapore 678051, SG"
    },
    "contact": {
      "phone": null,
      "email": null,
      "website": null
    },
    "hours": {
      "opening_hours": "24/7",
      "parsed_hours": {
        "monday": "00:00-23:59",
        "tuesday": "00:00-23:59",
        "wednesday": "00:00-23:59",
        "thursday": "00:00-23:59",
        "friday": "00:00-23:59",
        "saturday": "00:00-23:59",
        "sunday": "00:00-23:59",
        "is_open_24h": true
      },
      "last_check_date": "2024-08-29"
    },
    "source": {
      "source_file": "cafes.geojson",
      "original_id": "way/71400539",
      "source_type": "openstreetmap",
      "source_timestamp": "2026-03-26T11:12:31Z"
    },
    "original_properties": {
      "@id": "way/71400539",
      "addr:city": "Singapore",
      "addr:country": "SG",
      "addr:housenumber": "422",
      "addr:postcode": "678051",
      "addr:street": "Upper Bukit Timah Road",
      "air_conditioning": "yes",
      "amenity": "cafe",
      "brand": "The Coffee Bean & Tea Leaf",
      "brand:wikidata": "Q1141384",
      "brand:wikipedia": "en:The Coffee Bean & Tea Leaf",
      "building": "retail",
      "check_date": "2024-08-29",
      "cuisine": "coffee_shop",
      "internet_access": "wlan",
      "name": "The Coffee Bean & Tea Leaf",
      "opening_hours": "24/7",
      "outdoor_seating": "no",
      "payment:cash": "yes",
      "payment:credit_cards": "yes",
      "payment:debit_cards": "yes",
      "takeaway": "yes",
      "wheelchair": "limited"
    },
    "duplicates": {
      "duplicate_flag": false,
      "duplicate_score": 0.0,
      "duplicate_cluster_id": null,
      "duplicate_candidates": []
    },
    "metadata": {
      "ingestion_timestamp": "2026-03-26T14:35:22Z",
      "ingestion_session_id": "ingestion-2026-03-26-session-001",
      "raw_property_count": 22,
      "fields_missing": [],
      "fields_incomplete": [],
      "quality_score": 0.95,
      "validation_flags": [],
      "notes": ""
    }
  },
  "geometry": {
    "type": "Point",
    "coordinates": [103.7863694, 1.4360981]
  }
}
```

---

## J. Example Output Dataset Format

### Output 1: Normalized GeoJSON FeatureCollection

**File**: `data/normalized/baseline_normalized.geojson`

```json
{
  "type": "FeatureCollection",
  "name": "baseline_normalized",
  "generator": "baseline-ingestion-pipeline-v1.0",
  "timestamp": "2026-03-26T14:35:22Z",
  "ingestion_session_id": "ingestion-2026-03-26-session-001",
  "statistics": {
    "total_records": 2847,
    "records_by_category": {
      "food_beverage": 1204,
      "retail": 892,
      "accommodation": 456,
      "recreation_tourism": 234,
      "fuel_energy": 61
    },
    "geometry_invalid_count": 3,
    "duplicate_flagged_count": 87,
    "quality_score_avg": 0.89,
    "source_file_counts": {
      "cafes.geojson": 305,
      "restaurants.geojson": 899,
      "hotels.geojson": 456,
      "pharmacies.geojson": 234,
      "fuel_station.geojson": 61,
      "grocery stores.geojson": 456,
      "shopping_malls.geojson": 156,
      "theme_parks.geojson": 89,
      "tourism attraction.geojson": 145,
      "department_stores.geojson": 46
    }
  },
  "features": [
    { "type": "Feature", "properties": {...}, "geometry": {...} },
    { "type": "Feature", "properties": {...}, "geometry": {...} },
    ...
  ]
}
```

### Output 2: Parquet Schema

**File**: `data/normalized/baseline_normalized.parquet`

```
Root
├── baseline_place_id: string
├── name: string
├── category: string
├── subcategory: string
├── latitude: double
├── longitude: double
├── geometry_type: string
├── geometry_valid: boolean
├── location
│   ├── address: string
│   ├── street: string
│   ├── housenumber: string
│   ├── city: string
│   ├── postcode: string
│   ├── country: string
│   └── formatted_address: string
├── contact
│   ├── phone: string
│   ├── email: string
│   └── website: string
├── hours
│   ├── opening_hours: string
│   ├── parsed_hours: map<string, string>
│   ├── last_check_date: string
│   └── is_open_24h: boolean
├── source
│   ├── source_file: string
│   ├── original_id: string
│   ├── source_type: string
│   └── source_timestamp: string
├── original_properties: map<string, string>
├── duplicates
│   ├── duplicate_flag: boolean
│   ├── duplicate_score: double
│   ├── duplicate_cluster_id: string
│   └── duplicate_candidates: array<struct>
└── metadata
    ├── ingestion_timestamp: string
    ├── ingestion_session_id: string
    ├── raw_property_count: int32
    ├── fields_missing: array<string>
    ├── fields_incomplete: array<string>
    ├── quality_score: double
    ├── validation_flags: array<string>
    └── notes: string
```

### Output 3: SQLite Schema

**File**: `data/normalized/baseline_normalized.db`

```sql
CREATE TABLE places (
    baseline_place_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    subcategory TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    geometry_type TEXT DEFAULT 'point',
    geometry_valid INTEGER DEFAULT 1,
    
    street TEXT,
    housenumber TEXT,
    city TEXT,
    postcode TEXT,
    country TEXT,
    formatted_address TEXT,
    
    phone TEXT,
    email TEXT,
    website TEXT,
    
    opening_hours TEXT,
    parsed_hours_json TEXT,  -- JSON string
    last_check_date TEXT,
    
    source_file TEXT NOT NULL,
    original_id TEXT NOT NULL,
    source_type TEXT DEFAULT 'openstreetmap',
    source_timestamp TEXT,
    
    original_properties_json TEXT NOT NULL,  -- JSON string (unindexed)
    
    duplicate_flag INTEGER DEFAULT 0,
    duplicate_score REAL DEFAULT 0.0,
    duplicate_cluster_id TEXT,
    duplicate_candidates_json TEXT,  -- JSON string
    
    ingestion_timestamp TEXT NOT NULL,
    ingestion_session_id TEXT NOT NULL,
    raw_property_count INTEGER,
    fields_missing_json TEXT,  -- JSON string
    fields_incomplete_json TEXT,  -- JSON string
    quality_score REAL,
    validation_flags_json TEXT,  -- JSON string
    notes TEXT
);

-- Indexes for efficient querying
CREATE INDEX idx_category ON places(category);
CREATE INDEX idx_subcategory ON places(subcategory);
CREATE INDEX idx_duplicate_flag ON places(duplicate_flag);
CREATE INDEX idx_duplicate_cluster ON places(duplicate_cluster_id);
CREATE INDEX idx_city ON places(city);
CREATE INDEX idx_quality_score ON places(quality_score);
CREATE INDEX idx_ingestion_session ON places(ingestion_session_id);

-- Spatial index (if using spatialite extension)
SELECT InitSpatialMetaData();
CREATE TABLE places_geom AS 
SELECT baseline_place_id, GeomFromText('POINT('||longitude||' '||latitude||')', 4326) geom 
FROM places;
CREATE SPATIAL INDEX idx_places_geom ON places_geom(geom);
```

### Output 4: Validation & Quality Report

**File**: `data/normalized/baseline_quality_report.json`

```json
{
  "ingestion_session_id": "ingestion-2026-03-26-session-001",
  "timestamp": "2026-03-26T14:35:22Z",
  "duration_seconds": 245,
  "summary": {
    "total_records_ingested": 2847,
    "total_records_normalized": 2844,
    "records_failed": 3,
    "success_rate": 0.9989
  },
  "categories": {
    "food_beverage": {
      "count": 1204,
      "pct": 42.3,
      "avg_quality": 0.91
    },
    "retail": {
      "count": 892,
      "pct": 31.4,
      "avg_quality": 0.87
    },
    "accommodation": {
      "count": 456,
      "pct": 16.0,
      "avg_quality": 0.86
    },
    "recreation_tourism": {
      "count": 234,
      "pct": 8.2,
      "avg_quality": 0.84
    },
    "fuel_energy": {
      "count": 61,
      "pct": 2.1,
      "avg_quality": 0.92
    }
  },
  "geometry": {
    "valid": 2844,
    "invalid": 3,
    "missing_coordinates": 0,
    "out_of_bounds": 3
  },
  "duplicates": {
    "exact_duplicates": 12,
    "probable_duplicates": 75,
    "total_flagged": 87,
    "clusters": 32
  },
  "missing_fields": {
    "website": 2156,
    "phone": 1892,
    "opening_hours": 1045,
    "email": 2780,
    "complete_address": 234
  },
  "quality_distribution": {
    "0.90_1.00": 1823,
    "0.80_0.89": 892,
    "0.70_0.79": 129,
    "below_0.70": 3
  },
  "source_files": {
    "cafes.geojson": {
      "ingested": 305,
      "normalized": 305,
      "quality_avg": 0.92
    },
    "restaurants.geojson": {
      "ingested": 899,
      "normalized": 896,
      "quality_avg": 0.89
    },
    "hotels.geojson": {
      "ingested": 456,
      "normalized": 456,
      "quality_avg": 0.86
    },
    "pharmacies.geojson": {
      "ingested": 234,
      "normalized": 234,
      "quality_avg": 0.88
    },
    "fuel_station.geojson": {
      "ingested": 61,
      "normalized": 61,
      "quality_avg": 0.92
    },
    "grocery stores.geojson": {
      "ingested": 456,
      "normalized": 454,
      "quality_avg": 0.85
    },
    "shopping_malls.geojson": {
      "ingested": 156,
      "normalized": 156,
      "quality_avg": 0.88
    },
    "theme_parks.geojson": {
      "ingested": 89,
      "normalized": 89,
      "quality_avg": 0.84
    },
    "tourism attraction.geojson": {
      "ingested": 145,
      "normalized": 145,
      "quality_avg": 0.82
    },
    "department_stores.geojson": {
      "ingested": 46,
      "normalized": 48,
      "quality_avg": 0.90
    }
  },
  "recommendations": [
    "87 probable duplicates flagged for manual review before use in change detection",
    "3 records with invalid geometry (out of bounds) - coordinates require manual correction",
    "2156 records missing website URL - prioritize for website scraping phase",
    "1045 records with unparseable opening_hours - may require manual standardization",
    "Consider enriching dataset with additional sources before production change detection"
  ]
}
```

### Output 5: Duplicates Report

**File**: `data/normalized/baseline_duplicates.json`

```json
{
  "ingestion_session_id": "ingestion-2026-03-26-session-001",
  "timestamp": "2026-03-26T14:35:22Z",
  "total_duplicate_clusters": 32,
  "total_flagged_records": 87,
  "clusters": [
    {
      "cluster_id": "cluster-001",
      "cluster_score": 0.95,
      "members": [
        {
          "baseline_place_id": "550e8400-e29b-41d4-a716-446655440000",
          "name": "The Coffee Bean & Tea Leaf",
          "source_file": "cafes.geojson",
          "coordinates": [103.7863694, 1.4360981],
          "match_to_cluster_score": 1.0
        },
        {
          "baseline_place_id": "550e8400-e29b-41d4-a716-446655440001",
          "name": "Coffee Bean & Tea Leaf",
          "source_file": "restaurants.geojson",
          "coordinates": [103.7862891, 1.4361105],
          "match_to_cluster_score": 0.98
        }
      ],
      "recommendation": "Likely duplicate - coordinate < 50m apart, name 98% similar"
    },
    ...
  ]
}
```

### Output 6: Ingestion Log

**File**: `data/normalized/baseline_ingestion_log.txt`

```
================================================================================
BASELINE INGESTION LOG
Session ID: ingestion-2026-03-26-session-001
Started: 2026-03-26T14:30:00Z
Completed: 2026-03-26T14:35:22Z (5m 22s)
================================================================================

[2026-03-26T14:30:00Z] INFO   Loading baseline GeoJSON files from: /data/baseline/
[2026-03-26T14:30:01Z] INFO   Discovered 10 GeoJSON files
[2026-03-26T14:30:01Z] INFO   Loading cafes.geojson (305 features)
[2026-03-26T14:30:02Z] INFO   Loading restaurants.geojson (899 features)
[2026-03-26T14:30:03Z] INFO   Loading hotels.geojson (456 features)
[2026-03-26T14:30:03Z] INFO   Loading pharmacies.geojson (234 features)
[2026-03-26T14:30:04Z] INFO   Loading fuel_station.geojson (61 features)
[2026-03-26T14:30:04Z] INFO   Loading grocery stores.geojson (456 features)
[2026-03-26T14:30:05Z] INFO   Loading shopping_malls.geojson (156 features)
[2026-03-26T14:30:06Z] INFO   Loading theme_parks.geojson (89 features)
[2026-03-26T14:30:06Z] INFO   Loading tourism attraction.geojson (145 features)
[2026-03-26T14:30:07Z] INFO   Loading department_stores.geojson (46 features)
[2026-03-26T14:30:07Z] INFO   Total features loaded: 2847

[2026-03-26T14:30:10Z] INFO   Starting normalization of 2847 features
[2026-03-26T14:30:10Z] INFO   Initializing category mapper
[2026-03-26T14:30:11Z] INFO   Initializing geometry handler
[2026-03-26T14:30:11Z] INFO   Initializing address parser
[2026-03-26T14:30:11Z] INFO   Initializing hours parser
[2026-03-26T14:30:12Z] INFO   Normalizing batch 1 (100/2847)
[2026-03-26T14:30:13Z] INFO   Normalizing batch 2 (200/2847)
...
[2026-03-26T14:31:45Z] INFO   Normalization complete: 2844 succeeded, 3 failed

[2026-03-26T14:31:45Z] INFO   Starting duplicate detection on 2844 records
[2026-03-26T14:32:45Z] INFO   Duplicate detection complete: 87 flagged, 32 clusters

[2026-03-26T14:32:46Z] INFO   Running quality validation
[2026-03-26T14:32:50Z] INFO   Quality validation complete

[2026-03-26T14:32:50Z] INFO   Writing output: baseline_normalized.geojson
[2026-03-26T14:33:02Z] INFO   Wrote 2844 records to GeoJSON (22.4 MB)

[2026-03-26T14:33:02Z] INFO   Writing output: baseline_normalized.parquet
[2026-03-26T14:33:18Z] INFO   Wrote 2844 records to Parquet (18.3 MB)

[2026-03-26T14:33:18Z] INFO   Writing output: baseline_normalized.db
[2026-03-26T14:33:35Z] INFO   Wrote 2844 records to SQLite (15.2 MB), created indexes

[2026-03-26T14:33:36Z] INFO   Writing validation report: baseline_quality_report.json
[2026-03-26T14:33:36Z] INFO   Writing duplicates report: baseline_duplicates.json

[2026-03-26T14:33:37Z] INFO   Creating backup: baseline_2026-03-26.backup/
[2026-03-26T14:33:45Z] INFO   Backup complete

[2026-03-26T14:35:22Z] INFO   ✓ INGESTION PIPELINE COMPLETED SUCCESSFULLY
================================================================================
Session Summary:
  Total Duration: 5m 22s
  Records Loaded: 2847
  Records Normalized: 2844
  Normalization Success Rate: 99.89%
  Duplicates Flagged: 87 (3.06%)
  Average Quality Score: 0.89
  Output Formats: GeoJSON, Parquet, SQLite
  Backup Created: ✓
================================================================================
```

---

## Next Steps (Future Phases - NOT in Scope)

1. **Website Scraping Phase**: Enrich `contact.website` field and extract website metadata
2. **Evidence Comparison Phase**: Match scrapped website data against normalized baseline
3. **Change Detection Phase**: Implement detection logic for new/closed/rebranded places
4. **Dashboard & Scoring**: Build visualization and confidence scoring
5. **Automated Updates**: Implement daily/weekly ingestion refresh cycles

---

## Appendix: Architecture Diagram

```
External Data Sources
      ↓
   [Baseline GeoJSON Files]
      cafes.geojson
      restaurants.geojson
      hotels.geojson
      ... (10 files)
      ↓
┌─────────────────────────────────┐
│  INGESTION PIPELINE             │
│  ├─ File Discovery & Loading    │
│  ├─ Feature Extraction          │
│  ├─ Geometry Normalization      │
│  ├─ Category Mapping            │
│  ├─ Property Normalization      │
│  ├─ Duplicate Detection         │
│  ├─ ID Generation               │
│  ├─ Quality Validation          │
│  └─ Output Serialization        │
└─────────────────────────────────┘
      ↓
┌─────────────────────────────────┐
│  NORMALIZED OUTPUT              │
│  ├─ baseline_normalized.geojson │
│  ├─ baseline_normalized.parquet │
│  ├─ baseline_normalized.db      │
│  ├─ quality_report.json         │
│  ├─ duplicates.json             │
│  └─ ingestion_log.txt           │
└─────────────────────────────────┘
      ↓
┌─────────────────────────────────┐
│  READY FOR NEXT PHASES          │
│  ├─ Website Scraping            │
│  ├─ Evidence Matching           │
│  └─ Change Detection            │
└─────────────────────────────────┘
```

---

**Document End**
