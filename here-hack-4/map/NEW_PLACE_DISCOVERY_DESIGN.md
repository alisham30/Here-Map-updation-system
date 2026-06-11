# New Place Discovery Layer for Singapore

**Author**: Senior Geospatial Intelligence Engineer  
**Date**: March 26, 2026  
**Version**: 1.0  
**Scope**: Discovery of NEW places absent from baseline inventory via multi-source evidence

---

## A. Goal of the New-Place Discovery Layer

The new-place discovery layer systematically identifies places that are likely **newly opened** or **recently established** and are **not already present** in the baseline place inventory.

**Primary Objectives:**
1. **Systematic Coverage**: Scan all 6 evidence sources (data.gov.sg, OneMap, Yelp, Grab, websites, imagery) in priority order
2. **Baseline Exclusion**: Match candidates against baseline to identify only truly NEW places (not existing duplicates)
3. **Geographic Sensitivity**: Handle dense Singapore urban areas with consolidation logic for candidate clustering
4. **Multi-Source Promotion**: Promote candidates from uncertain to high-confidence when multiple independent sources agree
5. **Freshness Assessment**: Flag candidates based on registration date, listing date, first-seen date
6. **Category-Aware Logic**: Apply category-specific rules (cafes differ from hotels; pharmacies differ from attractions)
7. **Disambiguation**: Separate true new places from rebrands, duplicate listings, and uncertain candidates (rebranding logic is deferred)

**Non-Goals:**
- Detecting closed or rebranded places (handled in separate layer)
- Building dashboard or UI
- Human review workflow
- Change scoring or confidence training

**Output:**
List of candidate new places with source evidence, freshness timestamps, baseline matching results, and promotion confidence.

---

## B. Source Priority and Rationale

### Priority Ranking

| Priority | Source | Why | Freshness | Coverage | Reliability |
|----------|--------|-----|-----------|----------|-------------|
| **1** | data.gov.sg / ACRA | Official government registry; authoritative for new business registrations; exact registration dates | ~2-4 weeks after registration | ~80% of businesses | High |
| **2** | OneMap | Official national geocoding service; address resolution; travel-time validation against baseline | Real-time | ~95% address coverage | Very High |
| **3** | Yelp | Crowd-sourced business listings; public reviews and opening dates; covers food/entertainment heavily | Days to weeks | ~60% of F&B in Singapore | Medium-High |
| **4** | Grab / GrabFood / GrabMaps | Merchant/food platform presence; active merchant profiles; real-time order data | Days (real-time) | ~70% of food delivery merchants | High |
| **5** | Official Websites | Direct business evidence; hours, contact, branding | Variable (owner-dependent) | ~40% of established businesses | High (but stale) |
| **6** | Imagery | Street-level confirmation; storefronts; recent photos indicate active operations | Days to weeks | ~100% potential | Medium (subjective) |

### Why This Order?

1. **data.gov.sg/ACRA first**: Government registry is authoritative anchor for business existence. ACRA registration date is ground truth for "newness."
2. **OneMap second**: Validates/geocodes ACRA records; confirms address exists; enables baseline matching by coordinates
3. **Yelp third**: Public business listings with crowd-sourced opening dates; fills gaps for F&B not yet in ACRA
4. **Grab fourth**: Real-time operational evidence; food merchants register with platform on opening day
5. **Websites**: Confirms branding and business info; often lag registrations by months
6. **Imagery**: Verification only; too labor-intensive to drive discovery; used for confirmation

---

## C. Candidate Extraction Logic Per Source

### 1. **data.gov.sg / ACRA Business Registry**

**API/Data Source:**
- ACRA (Accounting and Corporate Regulatory Authority) entity registry
- data.gov.sg: https://data.gov.sg/dataset/acra-change-of-constitution
- Export: monthly/weekly CSV of newly registered entities

**Extraction Strategy:**

```python
def extract_candidates_from_acra(acra_dataset, baseline_categories):
    """
    Extract NEW business entities from ACRA registry.
    
    Criteria:
    - Registration date within last 90 days (configurable)
    - Business activity matches tracked categories (F&B, retail, accommodation, etc.)
    - Company status = "Active"
    - Not already in baseline
    
    Returns: List of (name, registration_date, address, entity_type)
    """
    candidates = []
    
    for entity in acra_dataset:
        # Filter 1: Recency (last 90 days)
        if days_since(entity['registration_date']) > 90:
            continue
        
        # Filter 2: Status (only Active)
        if entity['status'] != 'Active':
            continue
        
        # Filter 3: Category match
        if not matches_tracked_category(entity['business_activity'], baseline_categories):
            continue
        
        # Extract candidate
        candidate = {
            'detected_name': entity['entity_name'],
            'acra_registry_number': entity['uen'],
            'registration_date': entity['registration_date'],
            'business_activity': entity['business_activity'],
            'address_raw': entity['registered_address'],
            'source_type': 'acra_registry',
            'source_reference': f"ACRA/{entity['uen']}",
            'category_raw': infer_category_from_activity(entity['business_activity']),
            'freshness': freshness_from_registration_date(entity['registration_date']),
        }
        
        candidates.append(candidate)
    
    return candidates

# Category filtering for ACRA activities
CATEGORY_ACTIVITY_MAP = {
    '52': 'retail',  # Retail trade
    '56': 'food_beverage',  # Food and beverage
    '55': 'accommodation',  # Accommodation
    '47': 'retail',  # Retail
    '79': 'recreation_tourism',  # Travel agency, tour operator
    '86': 'retail',  # Professional, scientific and technical activities
}
```

**Key Fields Extracted:**
- Entity name
- UEN (Unique Entity Number)
- Registration date
- Business activity code
- Registered address
- Entity status

**Volume & Timing:**
- ~200-400 new entities per week in F&B/retail/accommodation
- Data available 2-4 weeks after registration
- Pull: Weekly from data.gov.sg

---

### 2. **STB Tourist Attraction Dataset (data.gov.sg)**

**API/Data Source:**
- Singapore Tourism Board (STB) attraction listings
- data.gov.sg: Tourism board dataset

**Extraction Strategy:**

```python
def extract_candidates_from_stb(stb_dataset, baseline):
    """
    Extract NEW attractions registered with STB.
    
    Criteria:
    - Listed within last 180 days
    - Category = attraction/museum/park/waterpark/etc
    - Not in baseline
    """
    candidates = []
    
    for attraction in stb_dataset:
        if days_since(attraction['listing_date']) > 180:
            continue
        
        if attraction['status'] != 'Active':
            continue
        
        candidate = {
            'detected_name': attraction['name_en'],
            'stb_registration_id': attraction['stb_id'],
            'listing_date': attraction['listing_date'],
            'address': attraction['address'],
            'postal_code': attraction['postal_code'],
            'latitude': attraction['latitude'],
            'longitude': attraction['longitude'],
            'category': 'recreation_tourism',
            'subcategory': attraction['attraction_type'],
            'source_type': 'stb_registry',
            'source_reference': f"STB/{attraction['stb_id']}",
            'website': attraction['website_url'],
            'phone': attraction['contact_phone'],
            'hours': attraction['operating_hours'],
            'freshness': freshness_from_listing_date(attraction['listing_date']),
        }
        
        candidates.append(candidate)
    
    return candidates
```

---

### 3. **OneMap Geocoding & Address Search**

**API/Data Service:**
- OneMap REST API: search, reverse geocoding, nearby places
- https://www.onemap.gov.sg/apidocs/

**Extraction Strategy:**

```python
def extract_candidates_from_onemap(acra_candidates, baseline):
    """
    Geocode ACRA candidates using OneMap; filter by baseline distance.
    
    For each ACRA candidate:
    1. Search OneMap by name + address → get lat/lon
    2. Check if within 25m of baseline place (same place)
    3. If >25m away, flag as potential NEW place
    4. Extract additional metadata from OneMap
    """
    enriched = []
    
    for candidate in acra_candidates:
        # OneMap search
        search_query = f"{candidate['detected_name']} {candidate['address_raw']}"
        onemap_results = onemap_search(search_query, max_results=5)
        
        if not onemap_results:
            # No geocoding found - mark as uncertain
            candidate['geocoding_status'] = 'not_found'
            enriched.append(candidate)
            continue
        
        best_match = onemap_results[0]  # Highest relevance
        candidate['latitude'] = best_match['lat']
        candidate['longitude'] = best_match['lon']
        candidate['postal_code'] = best_match['postal_code']
        candidate['onemap_reference'] = best_match['onemap_id']
        candidate['geocoding_status'] = 'found'
        candidate['address_normalized'] = best_match['address']
        
        enriched.append(candidate)
    
    return enriched

def filter_by_baseline_distance(candidates, baseline_places, distance_threshold_m=25):
    """
    Remove candidates too close to existing baseline places.
    
    Logic:
    - If candidate within distance_threshold_m of baseline place: likely existing place
    - Otherwise: likely new place
    """
    new_candidates = []
    
    for candidate in candidates:
        if candidate.get('latitude') is None:
            # Can't compute distance
            candidate['baseline_match'] = None
            new_candidates.append(candidate)
            continue
        
        # Find nearest baseline place
        nearest = find_nearest_baseline(
            candidate['latitude'],
            candidate['longitude'],
            baseline_places,
            search_radius_m=100  # Search in 100m radius
        )
        
        if not nearest:
            # No baseline place nearby
            candidate['baseline_match'] = None
            candidate['baseline_distance_m'] = None
            new_candidates.append(candidate)
        elif nearest['distance_m'] <= distance_threshold_m:
            # Too close to baseline - likely duplicate
            candidate['baseline_match'] = {
                'baseline_place_id': nearest['baseline_place_id'],
                'baseline_name': nearest['name'],
                'distance_m': nearest['distance_m'],
                'match_confidence': 'high',
            }
            candidate['is_duplicate_of_baseline'] = True
            # DON'T add to new_candidates - exclude this
        else:
            # Far enough from baseline - potential new place
            candidate['baseline_match'] = {
                'baseline_place_id': nearest['baseline_place_id'],
                'baseline_name': nearest['name'],
                'distance_m': nearest['distance_m'],
                'match_confidence': 'low',
            }
            candidate['is_duplicate_of_baseline'] = False
            new_candidates.append(candidate)
    
    return new_candidates
```

**Enrichment via OneMap:**
- Validated lat/lon
- Postal code extraction
- Address normalization
- Nearby landmark context

---

### 4. **Yelp Places API**

**API:**
- Yelp Fusion API: /businesses/search, /businesses/:id

**Extraction Strategy:**

```python
def extract_candidates_from_yelp(categories_to_track):
    """
    Query Yelp for recent business openings in Singapore.
    
    Strategy:
    - Search by category (cafe, restaurant, hotel, pharmacy, etc.)
    - Filter for "newly_opened" or "recently_opened" reviews
    - Extract business opening info from first reviews
    """
    candidates = []
    
    for category in categories_to_track:
        # Query Yelp by category
        results = yelp_search(
            locale='Singapore',
            categories=[category],
            sort_by='rating',  # Get popular new places
        )
        
        for business in results:
            # Estimate opening date from reviews
            estimated_opening_date = estimate_opening_date_from_reviews(business['reviews'])
            
            if not is_recent_opening(estimated_opening_date, days=90):
                continue
            
            candidate = {
                'detected_name': business['name'],
                'yelp_business_id': business['id'],
                'yelp_url': business['url'],
                'estimated_opening_date': estimated_opening_date,
                'latitude': business['coordinates']['latitude'],
                'longitude': business['coordinates']['longitude'],
                'address': business['location']['address1'],
                'postal_code': business['location']['zip_code'],
                'city': business['location']['city'],
                'phone': business['phone'],
                'website': business['website'] if 'website' in business else None,
                'yelp_rating': business['rating'],
                'yelp_review_count': business['review_count'],
                'category': category,
                'source_type': 'yelp_business',
                'source_reference': f"Yelp/{business['id']}",
                'hours': business.get('hours', [{}])[0]['open'] if 'hours' in business else None,
                'freshness': freshness_from_estimated_date(estimated_opening_date),
            }
            
            candidates.append(candidate)
    
    return candidates

def estimate_opening_date_from_reviews(reviews, limit_reviews=50):
    """
    Estimate opening date by finding earliest "just opened" or "new place" reviews.
    
    Heuristic: If 50 oldest reviews have timestamps, earliest review ≈ opening date.
    """
    if not reviews or len(reviews) < 3:
        return None
    
    oldest_reviews = sorted(reviews, key=lambda r: r['time_created'])[:limit_reviews]
    
    if oldest_reviews and oldest_reviews[0]:
        # Estimate opening ~2 weeks before first review
        first_review_date = oldest_reviews[0]['time_created']
        estimated_opening = first_review_date - timedelta(days=14)
        return estimated_opening
    
    return None
```

**Extraction Logic:**
- Search by category (cafe, restaurant, hotel, pharmacy, tourist attraction)
- Find recent openings by estimating opening date from review timestamps
- Extract hours from Yelp business hours
- Get phone, website, coordinates

**Volume & Timing:**
- ~50-100 potential new businesses per month
- Opening date estimated retroactively from reviews (~2 weeks lag)
- Pull: Weekly query by category

---

### 5. **Grab / GrabFood / GrabMaps Evidence**

**API:**
- GrabFood API (if accessible)
- GrabMaps merchant data (if accessible)
- Merchant platform evidence

**Extraction Strategy:**

```python
def extract_candidates_from_grab(baseline):
    """
    Extract merchant/food vendor evidence from Grab ecosystem.
    
    For food merchants:
    - GrabFood merchant list
    - Active delivery areas
    - First-seen dates in platform
    - Active order volume
    
    For place presence:
    - GrabMaps points of interest
    - Merchant locations
    """
    candidates = []
    
    # GrabFood vendors
    grabfood_vendors = fetch_grabfood_merchant_list()
    
    for vendor in grabfood_vendors:
        # Filter: Active merchants only
        if vendor['status'] != 'active':
            continue
        
        # Estimate "first listed" from account creation date
        if days_since(vendor['account_creation_date']) > 180:
            continue
        
        candidate = {
            'detected_name': vendor['business_name'],
            'grab_merchant_id': vendor['merchant_id'],
            'account_creation_date': vendor['account_creation_date'],
            'latitude': vendor['latitude'],
            'longitude': vendor['longitude'],
            'address': vendor['address'],
            'postal_code': vendor['postal_code'],
            'phone': vendor['phone'],
            'category': infer_category_from_cuisine(vendor['cuisine_types']),
            'subcategory': ','.join(vendor['cuisine_types']),
            'source_type': 'grab_merchant',
            'source_reference': f"Grab/{vendor['merchant_id']}",
            'hours': vendor['operating_hours'],
            'website': vendor.get('website'),
            'social_media': vendor.get('social_profiles', []),
            'daily_order_volume_avg': vendor['avg_daily_orders'],
            'freshness': freshness_from_account_creation(vendor['account_creation_date']),
        }
        
        candidates.append(candidate)
    
    return candidates
```

**Key Evidence from Grab:**
- Merchant account creation date (indicates opening)
- Active delivery coverage
- Daily order volume (indicates established operations)
- Cuisine types for categorization

---

### 6. **Official Place Websites**

**Extraction Strategy:**

```python
def extract_candidates_from_website_discovery(candidates_from_other_sources):
    """
    For candidates that have websites (from ACRA, Yelp, Grab):
    1. Crawl website
    2. Look for opening announcement or date
    3. Extract business hours, contact, branding
    """
    enriched = []
    
    for candidate in candidates_from_other_sources:
        if not candidate.get('website'):
            enriched.append(candidate)
            continue
        
        try:
            website_data = crawl_website(candidate['website'], timeout_s=10)
            
            candidate['website_extracted'] = {
                'title': website_data.get('title'),
                'operating_hours': website_data.get('operating_hours'),
                'about_text': website_data.get('about_text'),
                'opening_date_mentioned': extract_opening_date_from_text(
                    website_data.get('about_text')
                ),
                'last_updated': website_data.get('last_modified'),
            }
        
        except Exception as e:
            candidate['website_extracted'] = {'error': str(e)}
        
        enriched.append(candidate)
    
    return enriched
```

---

### 7. **Street/Storefront Imagery**

**Extraction Strategy:**

```python
def extract_candidates_from_imagery(candidates, baseline):
    """
    For candidates with confirmed lat/lon:
    1. Fetch street View imagery (Google Street View, local sources)
    2. Detect storefront signs/activity
    3. Confirm operational status
    4. Note imagery freshness
    """
    enriched = []
    
    for candidate in candidates:
        if not candidate.get('latitude') or not candidate.get('longitude'):
            enriched.append(candidate)
            continue
        
        # Fetch street view
        image_data = fetch_street_view_image(
            candidate['latitude'],
            candidate['longitude'],
            max_age_days=90  # Within 3 months
        )
        
        if image_data:
            candidate['imagery'] = {
                'image_url': image_data['url'],
                'image_date': image_data['date'],
                'confidence_operational': analyze_storefront_activity(image_data['image']),
                'visual_confirmation': 'confirmed' if confidence > 0.7 else 'uncertain',
                'signage_visible': detect_signage(image_data['image']),
            }
        else:
            candidate['imagery'] = {'available': False}
        
        enriched.append(candidate)
    
    return enriched
```

---

## D. Baseline Exclusion Logic

The core process to identify NEW places: compare extracted candidates against baseline inventory.

### Matching Strategy

```python
def match_candidate_to_baseline(candidate, baseline_places, thresholds):
    """
    Determine if candidate is a NEW place or already in baseline.
    
    Multi-criteria matching:
    1. Geographic proximity (within DISTANCE_THRESHOLD)
    2. Name similarity (name_sim > NAME_SIM_THRESHOLD)
    3. Category match
    4. Address match (postal code, street)
    
    If ALL criteria match → Duplicate
    If SOME criteria match → Review candidate
    If NO criteria match → NEW place
    """
    
    # Step 1: Geographic search
    nearby_baseline = find_baseline_within_radius(
        candidate['latitude'],
        candidate['longitude'],
        radius_m=thresholds['geom_search_radius']  # e.g., 50m
    )
    
    if not nearby_baseline:
        # No baseline place nearby
        return {
            'match_type': 'new_place',
            'matched_baseline_id': None,
            'match_score': 0.0,
            'reasoning': 'No baseline places found within search radius',
        }
    
    # Step 2: For each nearby baseline place, score similarity
    best_match = None
    best_score = 0.0
    
    for baseline in nearby_baseline:
        match_score = calculate_match_score(candidate, baseline, thresholds)
        
        if match_score > best_score:
            best_score = match_score
            best_match = baseline
    
    # Step 3: Make decision
    if best_score >= thresholds['match_threshold']:  # e.g., 0.8
        return {
            'match_type': 'duplicate',
            'matched_baseline_id': best_match['baseline_place_id'],
            'matched_baseline_name': best_match['name'],
            'match_score': best_score,
            'reasoning': f'High match score {best_score:.2f} with nearby baseline place',
        }
    
    elif best_score >= thresholds['uncertain_threshold']:  # e.g., 0.6
        return {
            'match_type': 'uncertain',
            'matched_baseline_id': best_match['baseline_place_id'],
            'matched_baseline_name': best_match['name'],
            'match_score': best_score,
            'reasoning': f'Uncertain match (score {best_score:.2f}); could be rebrand or duplicate',
        }
    
    else:
        return {
            'match_type': 'new_place',
            'matched_baseline_id': best_match['baseline_place_id'],  # Nearest for context
            'nearest_baseline_distance_m': best_match['distance_m'],
            'match_score': best_score,
            'reasoning': f'Low match score {best_score:.2f}; appears to be genuinely new',
        }

def calculate_match_score(candidate, baseline, thresholds):
    """
    Multi-criteria scoring: geographic + name + category + address.
    """
    scores = {}
    
    # 1. Geographic proximity (weight 0.3)
    distance_m = haversine_distance(
        candidate['latitude'], candidate['longitude'],
        baseline['latitude'], baseline['longitude']
    )
    
    if distance_m <= thresholds['geom_threshold_exact']:  # e.g., 10m
        scores['geom'] = 1.0
    elif distance_m <= thresholds['geom_threshold_probable']:  # e.g., 50m
        scores['geom'] = 0.5 + 0.5 * (1 - distance_m / thresholds['geom_threshold_probable'])
    else:
        scores['geom'] = 0.0
    
    # 2. Name similarity (weight 0.4)
    name_sim = text_similarity(
        normalize_name(candidate['detected_name']),
        normalize_name(baseline['name'])
    )
    scores['name'] = name_sim
    
    # 3. Category match (weight 0.2)
    category_match = 1.0 if candidate['category'] == baseline['category'] else 0.0
    scores['category'] = category_match
    
    # 4. Address/postcode match (weight 0.1)
    address_sim = 0.0
    if candidate.get('postal_code') and baseline.get('postal_code'):
        if candidate['postal_code'] == baseline['postal_code']:
            address_sim = 1.0
    scores['address'] = address_sim
    
    # Weighted combination
    combined_score = (
        scores['geom'] * 0.3 +
        scores['name'] * 0.4 +
        scores['category'] * 0.2 +
        scores['address'] * 0.1
    )
    
    return combined_score
```

### Thresholds (Tunable)

```python
BASELINE_MATCH_THRESHOLDS = {
    'geom_search_radius': 50,  # Search baseline within 50m
    'geom_threshold_exact': 10,  # Within 10m = high spatial match
    'geom_threshold_probable': 50,  # Within 50m = moderate spatial match
    'name_sim_threshold': 0.80,  # 80% name similarity = match
    'match_threshold': 0.80,  # Combined score >= 0.80 = duplicate
    'uncertain_threshold': 0.60,  # 0.60-0.80 = uncertain
}
```

---

## E. Candidate Consolidation in Dense Map Areas

Singapore's dense urban areas (CBD, Orchard Road, Marina Bay) have many proximate POIs. Need deduplication of candidates that are actually the same place extracted multiple times from different sources.

### Consolidation Algorithm

```python
def consolidate_candidates_in_dense_areas(candidates, density_threshold_candidates_per_100m=5):
    """
    Identify candidate clusters in dense areas; merge into single consolidated record.
    
    Approach:
    1. Cluster candidates by proximity (within 20m)
    2. For each cluster, elect representative candidate
    3. Merge evidence from all sources
    """
    
    # Step 1: Build spatial index and find clusters
    clusters = spatial_cluster_candidates(candidates, radius_m=20)
    
    consolidated = []
    
    for cluster in clusters:
        if len(cluster) == 1:
            # Single candidate - keep as-is
            consolidated.append(cluster[0])
        else:
            # Multiple candidates in same cluster - consolidate
            merged = merge_candidate_cluster(cluster)
            consolidated.append(merged)
    
    return consolidated

def spatial_cluster_candidates(candidates, radius_m=20):
    """
    Group candidates into clusters based on spatial proximity.
    """
    clusters = []
    visited = set()
    
    for i, candidate in enumerate(candidates):
        if i in visited:
            continue
        
        cluster = [candidate]
        visited.add(i)
        
        for j in range(i + 1, len(candidates)):
            if j in visited:
                continue
            
            distance = haversine_distance(
                candidate['latitude'], candidate['longitude'],
                candidates[j]['latitude'], candidates[j]['longitude']
            )
            
            if distance <= radius_m:
                cluster.append(candidates[j])
                visited.add(j)
        
        clusters.append(cluster)
    
    return clusters

def merge_candidate_cluster(cluster):
    """
    Merge multiple candidate records from different sources into one consolidated record.
    
    Strategy:
    - Elect candidate with most source evidence as "primary"
    - Merge all names (pick most common)
    - Average geocoding
    - Combine all source references
    """
    
    # Primary candidate: highest source count
    primary = max(cluster, key=lambda c: len(c.get('sources', [])))
    
    merged = {
        'detected_name_primary': primary['detected_name'],
        'detected_names_all': list(set(c['detected_name'] for c in cluster)),
        'latitude': sum(c['latitude'] for c in cluster) / len(cluster),
        'longitude': sum(c['longitude'] for c in cluster) / len(cluster),
        'address': consolidate_addresses([c.get('address') for c in cluster]),
        'postal_code': consolidate_postcodes([c.get('postal_code') for c in cluster]),
        'category': primary.get('category'),
        'sources': list(set(
            src for c in cluster for src in c.get('sources', [])
        )),
        'source_types': list(set(c['source_type'] for c in cluster)),
        'source_instances': [
            {
                'source_type': c['source_type'],
                'detected_name': c['detected_name'],
                'freshness': c.get('freshness'),
                'source_reference': c['source_reference'],
            }
            for c in cluster
        ],
        'multi_source_agreement': True,
        'source_count': len(cluster),
        'consolidation_confidence': 0.95,
    }
    
    return merged
```

### Why Consolidation Matters

In Marina Bay/CBD area:
- ACRA registration → new restaurant record
- Yelp listing → same restaurant (day after)
- GrabFood merchant → same restaurant (day after opening)
- OneMap search result → same address

Without consolidation: **4 candidate records for 1 place** → inflation, duplicate efforts

After consolidation: **1 consolidated record with 4 source references** → confidence boost

---

## F. Category-Aware Source Rules

Not all sources are equally valuable for all categories. Apply category-specific extraction rules.

### Category-Source Value Matrix

| Category | ACRA | OneMap | Yelp | Grab | Website | Imagery |
|----------|------|--------|------|------|---------|---------|
| **Cafe** | Medium | High | **High** | **High** | Medium | Medium |
| **Restaurant** | Medium | High | **High** | **High** | Medium | Medium |
| **Hotel** | **High** | High | High | Low | **High** | Medium |
| **Pharmacy** | **High** | High | Low | Low | Low | Medium |
| **Shopping Mall** | **High** | **High** | Medium | Low | **High** | **High** |
| **Theme Park** | Medium | **High** | High | Low | **High** | **High** |
| **Tourist Attraction** | Low | High | High | Low | **High** | **High** |

### Rules by Category

```python
CATEGORY_SOURCE_RULES = {
    'food_beverage': {
        'cafe': {
            'primary_sources': ['yelp', 'grab_merchant', 'acra_registry'],
            'secondary_sources': ['onemap', 'website'],
            'minimum_sources_for_promotion': 2,
            'freshness_threshold_days': 90,
            'require_operational_evidence': True,  # Must have platform activity or reviews
        },
        'restaurant': {
            'primary_sources': ['yelp', 'grab_merchant', 'acra_registry'],
            'secondary_sources': ['onemap', 'website'],
            'minimum_sources_for_promotion': 2,
            'freshness_threshold_days': 90,
            'require_operational_evidence': True,
        },
    },
    'accommodation': {
        'hotel': {
            'primary_sources': ['acra_registry', 'website'],
            'secondary_sources': ['onemap', 'yelp'],
            'minimum_sources_for_promotion': 2,
            'freshness_threshold_days': 180,  # Hotels announced earlier than opening
            'require_operational_evidence': False,  # Construction/pre-launch OK
        },
    },
    'retail': {
        'pharmacy': {
            'primary_sources': ['acra_registry'],
            'secondary_sources': ['onemap'],
            'minimum_sources_for_promotion': 1,
            'freshness_threshold_days': 60,
            'require_operational_evidence': False,
        },
        'shopping_mall': {
            'primary_sources': ['acra_registry', 'website'],
            'secondary_sources': ['onemap', 'imagery'],
            'minimum_sources_for_promotion': 2,
            'freshness_threshold_days': 180,
            'require_operational_evidence': False,  # Grand opening announcement OK
        },
    },
    'recreation_tourism': {
        'theme_park': {
            'primary_sources': ['stb_registry', 'acra_registry'],
            'secondary_sources': ['website', 'onemap'],
            'minimum_sources_for_promotion': 2,
            'freshness_threshold_days': 180,
            'require_operational_evidence': False,
        },
        'tourist_attraction': {
            'primary_sources': ['stb_registry', 'onemap'],
            'secondary_sources': ['yelp', 'website'],
            'minimum_sources_for_promotion': 1,
            'freshness_threshold_days': 180,
            'require_operational_evidence': False,
        },
    },
}
```

### Application

```python
def apply_category_rules(candidate, category_rules):
    """
    Validate candidate against category-specific source requirements.
    """
    rules = category_rules.get(candidate['category'], {})
    
    if not rules:
        # Unknown category - apply default rules
        rules = {
            'minimum_sources_for_promotion': 1,
            'freshness_threshold_days': 90,
        }
    
    # Check if candidate has sufficient sources
    primary_source_count = len([
        s for s in candidate.get('source_types', [])
        if any(s.startswith(ps) for ps in rules.get('primary_sources', []))
    ])
    
    if primary_source_count < rules.get('minimum_sources_for_promotion', 1):
        candidate['category_rule_status'] = 'insufficient_sources'
        return False
    
    # Check freshness
    if candidate.get('freshness_days', 999) > rules.get('freshness_threshold_days', 90):
        candidate['category_rule_status'] = 'too_old'
        return False
    
    # Check operational evidence if required
    if rules.get('require_operational_evidence', False):
        if not has_operational_evidence(candidate):
            candidate['category_rule_status'] = 'no_operational_evidence'
            return False
    
    candidate['category_rule_status'] = 'pass'
    return True

def has_operational_evidence(candidate):
    """
    Check if candidate has evidence of active operations (reviews, orders, etc).
    """
    # Yelp reviews
    if candidate.get('yelp_review_count', 0) >= 3:
        return True
    
    # Grab daily orders
    if candidate.get('daily_order_volume_avg', 0) >= 10:
        return True
    
    # Recent website update
    if candidate.get('website_extracted', {}).get('last_updated'):
        days_old = (datetime.now() - candidate['website_extracted']['last_updated']).days
        if days_old <= 30:
            return True
    
    # Street imagery showing activity
    if candidate.get('imagery', {}).get('confidence_operational', 0) >= 0.7:
        return True
    
    return False
```

---

## G. Candidate Schema

All candidate new-place records follow a unified schema designed for multi-source evidence aggregation.

```json
{
  "candidate_id": "cand-550e8400-e29b-41d4-a716-446655440000",
  "candidate_source": "multi-source-consolidation",
  "candidate_state": "promoted_high_confidence",
  "detected_name_primary": "Sunset Coffee Roastery",
  "detected_names_all": [
    "Sunset Coffee Roastery",
    "Sunset Coffee"
  ],
  
  "location": {
    "latitude": 1.3521,
    "longitude": 103.8198,
    "postal_code": "048943",
    "address": "123 Orchard Road, Singapore 048943",
    "street": "Orchard Road",
    "housenumber": "123",
    "formatted_address": "123 Orchard Road, Singapore 048943",
    "onemap_reference": "onemap_id_12345",
    "city": "Singapore",
    "country": "SG"
  },
  
  "category": "food_beverage",
  "subcategory": "cafe",
  
  "registration_evidence": {
    "acra_registry": {
      "uen": "200123456A",
      "registration_date": "2026-01-15",
      "business_activity": "Restaurant and Mobile Food Service Activities",
      "status": "Active",
      "source_reference": "ACRA/200123456A"
    }
  },
  
  "source_inventory": [
    {
      "source_type": "acra_registry",
      "detected_name": "Sunset Coffee Roastery",
      "freshness_days": 70,
      "freshness_label": "recent",
      "evidence_date": "2026-01-15",
      "source_reference": "ACRA/200123456A",
      "confidence": "high"
    },
    {
      "source_type": "yelp_business",
      "detected_name": "Sunset Coffee",
      "freshness_days": 65,
      "freshness_label": "recent",
      "evidence_date": "2026-01-20",
      "source_reference": "Yelp/abcd1234",
      "yelp_rating": 4.6,
      "yelp_review_count": 45,
      "estimated_opening_date": "2026-01-15",
      "confidence": "high"
    },
    {
      "source_type": "grab_merchant",
      "detected_name": "Sunset Coffee Roastery",
      "freshness_days": 50,
      "freshness_label": "very_recent",
      "evidence_date": "2026-02-05",
      "source_reference": "Grab/grab_merchant_78910",
      "daily_order_volume_avg": 35,
      "confidence": "high"
    },
    {
      "source_type": "onemap_geocoding",
      "address": "123 Orchard Road, Singapore 048943",
      "postal_code": "048943",
      "geocoded": true,
      "confidence": "high"
    },
    {
      "source_type": "website",
      "website_url": "https://sunsetcoffee.sg",
      "website_title": "Sunset Coffee Roastery | Premium Coffee",
      "operating_hours": "07:00-21:00",
      "last_updated": "2026-02-20",
      "confidence": "medium"
    }
  ],
  
  "contact": {
    "phone": "+65 6789 1234",
    "email": "hello@sunsetcoffee.sg",
    "website": "https://sunsetcoffee.sg",
    "social_media": [
      {
        "platform": "instagram",
        "handle": "@sunsetcoffeesg",
        "followers": 2150
      }
    ]
  },
  
  "hours": {
    "opening_hours": "07:00-21:00",
    "monday": "07:00-21:00",
    "tuesday": "07:00-21:00",
    "wednesday": "07:00-21:00",
    "thursday": "07:00-21:00",
    "friday": "07:00-21:00",
    "saturday": "08:00-22:00",
    "sunday": "08:00-21:00",
    "hours_source": ["website", "grab"],
    "hours_verified": true
  },
  
  "baseline_matching": {
    "baseline_search_radius_m": 50,
    "baseline_places_found": 2,
    "nearest_baseline": {
      "baseline_place_id": "baseline-550e8400-e29b-41d4-a716-446655440001",
      "name": "Old Coffee Store",
      "distance_m": 78,
      "category": "food_beverage",
      "subcategory": "cafe"
    },
    "match_result": "new_place",
    "match_confidence": "high",
    "match_score": 0.15,
    "reasoning": "Far enough from baseline places (78m), unique name, newly registered"
  },
  
  "consolidation": {
    "consolidated_from": 3,
    "source_count": 5,
    "source_types": ["acra_registry", "yelp_business", "grab_merchant", "onemap_geocoding", "website"],
    "multi_source_agreement": true,
    "consolidation_confidence": 0.98
  },
  
  "freshness": {
    "earliest_evidence_date": "2026-01-15",
    "latest_evidence_date": "2026-02-20",
    "freshness_days": 35,
    "freshness_label": "new_recent",
    "primary_freshness_source": "acra_registry"
  },
  
  "operational_evidence": {
    "yelp_reviews": 45,
    "yelp_rating": 4.6,
    "grab_daily_orders": 35,
    "website_recent_update": true,
    "days_since_website_update": 6,
    "imagery_status": "confirmed",
    "operational_confidence": "high"
  },
  
  "derived_reasoning": {
    "evidence_summary": "Strong multi-source agreement: ACRA registration, Yelp reviews, active Grab orders, confirmed website. All sources consistent on opening date ~2026-01-15. New place 78m+ away from baseline.",
    "promotion_reasons": [
      "ACRA registered recently (2026-01-15)",
      "Multi-source consolidation (5 sources)",
      "Operational evidence present (45 Yelp reviews, 35 daily Grab orders)",
      "Website confirmed and recently updated",
      "No baseline place within 50m (nearest: Old Coffee Store, 78m away)"
    ],
    "promotion_confidence": "high",
    "next_action": "promote_to_high_confidence"
  },
  
  "metadata": {
    "discovery_timestamp": "2026-03-26T14:30:00Z",
    "discovery_session_id": "discovery-2026-03-26-session-001",
    "last_updated": "2026-03-26T14:35:00Z",
    "review_status": "automated_promoted",
    "review_timestamp": "2026-03-26T14:35:00Z",
    "human_review_required": false,
    "data_quality_score": 0.94
  }
}
```

---

## H. Freshness Rules for "New Place" Evidence

Freshness determines how recent and credible the "new place" claim is.

### Freshness Scoring

```python
FRESHNESS_HOURS_THRESHOLD = {
    'very_recent': (0, 7),  # Days 0-7 old
    'recent': (7, 30),  # Days 7-30 old
    'moderately_recent': (30, 90),  # Days 30-90 old
    'stale': (90, 999),  # > 90 days old
}

def calculate_freshness(candidate):
    """
    Calculate freshness label and days based on evidence timestamps.
    
    Priority:
    1. Registration date (ACRA) = ground truth for opening
    2. Account creation date (Grab merchant) = very fresh
    3. Estimated opening date (Yelp from reviews) = retroactive estimate
    4. Listing date (STB) = official registration
    5. Website last update = stale indicator
    """
    
    evidence_dates = []
    
    # ACRA registration date (highest priority)
    if candidate.get('registration_evidence', {}).get('acra_registry', {}).get('registration_date'):
        reg_date = candidate['registration_evidence']['acra_registry']['registration_date']
        evidence_dates.append(('acra_registration', reg_date, weight=1.0))
    
    # Grab account creation date (very fresh)
    grab_source = next(
        (s for s in candidate.get('source_inventory', []) if s['source_type'] == 'grab_merchant'),
        None
    )
    if grab_source and grab_source.get('evidence_date'):
        evidence_dates.append(('grab_account_creation', grab_source['evidence_date'], weight=0.95))
    
    # Yelp estimated opening date
    yelp_source = next(
        (s for s in candidate.get('source_inventory', []) if s['source_type'] == 'yelp_business'),
        None
    )
    if yelp_source and yelp_source.get('estimated_opening_date'):
        evidence_dates.append(('yelp_estimated_opening', yelp_source['estimated_opening_date'], weight=0.7))
    
    # STB listing date
    if candidate.get('registration_evidence', {}).get('stb_registry', {}).get('listing_date'):
        listing_date = candidate['registration_evidence']['stb_registry']['listing_date']
        evidence_dates.append(('stb_listing', listing_date, weight=0.8))
    
    if not evidence_dates:
        return {
            'freshness_label': 'unknown',
            'freshness_days': None,
            'freshness_source': None,
            'confidence': 'low',
        }
    
    # Average by weight
    weighted_dates = [
        (date_obj.timestamp() - datetime.now().timestamp()) / 86400 * weight
        for _, date_obj, weight in evidence_dates
    ]
    total_weight = sum(w for _, _, w in evidence_dates)
    avg_days_old = sum(weighted_dates) / total_weight
    freshness_days = int(abs(avg_days_old))
    
    # Map to label
    for label, (min_days, max_days) in FRESHNESS_HOURS_THRESHOLD.items():
        if min_days <= freshness_days < max_days:
            freshness_label = label
            break
    else:
        freshness_label = 'stale'
    
    return {
        'freshness_label': freshness_label,
        'freshness_days': freshness_days,
        'freshness_source': evidence_dates[0][0],  # Primary source
        'confidence': 'high' if len(evidence_dates) >= 2 else 'medium',
    }
```

### Freshness Promotion Logic

```python
def apply_freshness_rules(candidate, rules):
    """
    Use freshness to filter/promote candidates.
    
    Rules:
    - NEW places < 90 days old: PROMOTE
    - Places 90-180 days old: REVIEW (might be rebrand)
    - Places > 180 days old: FILTER OUT (already in baseline or too old)
    """
    freshness = calculate_freshness(candidate)
    days_old = freshness['freshness_days']
    
    if days_old <= 90:
        candidate['freshness_promotion'] = 'promote_high'
        candidate['freshness_promotion_reason'] = f'Recently registered ({days_old} days old)'
    elif days_old <= 180:
        candidate['freshness_promotion'] = 'review_manually'
        candidate['freshness_promotion_reason'] = f'Moderately recent ({days_old} days old); verify not rebrand'
    else:
        candidate['freshness_promotion'] = 'filter_out'
        candidate['freshness_promotion_reason'] = f'Too old ({days_old} days); likely already in baseline'
    
    return candidate
```

---

## I. New vs Rebrand vs Duplicate Logic

Critical distinction during new place discovery: when extracting candidates, determine the fundamental classification.

### Classification Framework

```python
def classify_candidate(candidate, baseline):
    """
    Classify as: NEW_PLACE, REBRAND, DUPLICATE, UNCERTAIN
    
    Logic:
    - NEW_PLACE: Registration date recent, no baseline match within 25m, unique name
    - REBRAND: Baseline place exists at same location, significant name change
    - DUPLICATE: Same name/brand, same location, multiple sources of same listing
    - UNCERTAIN: Ambiguous - multiple interpretations possible
    """
    
    baseline_match = baseline_match_result(candidate)
    
    # Case 1: No baseline within radius
    if not baseline_match['nearest_baseline']:
        return {
            'classification': 'new_place',
            'confidence': 'high',
            'reasoning': 'No baseline place found within search radius; newly registered entity',
        }
    
    nearest = baseline_match['nearest_baseline']
    distance_m = nearest['distance_m']
    name_sim = text_similarity(
        normalize_name(candidate['detected_name']),
        normalize_name(nearest['name'])
    )
    category_match = (candidate['category'] == nearest['category'])
    
    # Case 2: Same location, same/similar name → DUPLICATE
    if distance_m <= 25 and name_sim >= 0.90 and category_match:
        return {
            'classification': 'duplicate',
            'duplicate_of_baseline_id': nearest['baseline_place_id'],
            'duplicate_of_baseline_name': nearest['name'],
            'distance_m': distance_m,
            'name_similarity': name_sim,
            'confidence': 'high',
            'reasoning': 'Same location, matching name and category - likely duplicate listing',
        }
    
    # Case 3: Same location, different name → REBRAND?
    if distance_m <= 25 and name_sim < 0.80 and category_match:
        return {
            'classification': 'rebrand',
            'rebrand_of_baseline_id': nearest['baseline_place_id'],
            'rebrand_of_baseline_name': nearest['name'],
            'old_name': nearest['name'],
            'new_name': candidate['detected_name'],
            'distance_m': distance_m,
            'name_similarity': name_sim,
            'confidence': 'medium',
            'reasoning': 'Same location with significant name change - possible rebrand',
            'deferral_reason': 'Rebrand detection deferred to separate module'
        }
    
    # Case 4: Nearby but not same, similar name → UNCERTAIN
    if distance_m <= 50 and name_sim >= 0.80:
        return {
            'classification': 'uncertain',
            'possible_baseline_id': nearest['baseline_place_id'],
            'possible_baseline_name': nearest['name'],
            'distance_m': distance_m,
            'name_similarity': name_sim,
            'confidence': 'low',
            'reasoning': 'Near baseline place with similar name; could be expansion or separate location',
        }
    
    # Case 5: Far enough away → NEW_PLACE
    if distance_m > 50:
        return {
            'classification': 'new_place',
            'distance_to_nearest_baseline_m': distance_m,
            'nearest_baseline_id': nearest['baseline_place_id'],
            'confidence': 'high',
            'reasoning': f'Significant distance ({distance_m}m) from baseline place; appears to be genuinely new',
        }
```

### Distinction Rules

| Classification | Distance | Name Sim | Category Match | Registration |
|---|---|---|---|---|
| **NEW_PLACE** | > 50m | Any | Any | Recent (< 90 days) |
| **DUPLICATE** | < 25m | > 0.90 | Yes | Recent or old |
| **REBRAND** | < 25m | 0.50-0.80 | Same | Recent |
| **UNCERTAIN** | 25-50m | > 0.80 | Same | Recent |

---

## J. Backend Modules and Function Design

Complete module architecture for new-place discovery.

```
src/discovery/
├── __init__.py
├── config.py                    # Discovery constants and thresholds
│
├── sources/
│   ├── __init__.py
│   ├── acra_extractor.py        # ACRA registry extraction
│   ├── stb_extractor.py         # STB attraction data extraction
│   ├── onemap_enricher.py       # OneMap geocoding and enrichment
│   ├── yelp_extractor.py        # Yelp Places API extraction
│   ├── grab_extractor.py        # Grab merchant/platform extraction
│   ├── website_extractor.py     # Website crawling and info extraction
│   └── imagery_extractor.py     # Street imagery analysis
│
├── matching/
│   ├── __init__.py
│   ├── baseline_matcher.py      # Match candidates to baseline
│   ├── consolidator.py          # Consolidate multi-source candidates
│   └── classifier.py            # Classify as NEW/REBRAND/DUPLICATE
│
├── enrichment/
│   ├── __init__.py
│   ├── freshness_calculator.py  # Calculate freshness evidence
│   ├── category_validator.py    # Apply category rules
│   └── evidence_aggregator.py   # Combine evidence from all sources
│
├── pipeline/
│   ├── __init__.py
│   └── discovery_pipeline.py    # Main orchestrator
│
└── utils/
    ├── __init__.py
    ├── name_matcher.py          # Text similarity functions
    ├── geocoding.py             # Haversine distance, spatial queries
    └── validators.py            # Data validation helpers
```

### Key Module Signatures

```python
# acra_extractor.py
class ACRAExtractor:
    def extract_recent_registrations(self, days_back=90) -> List[Dict]: ...
    def filter_by_category(self, records, categories) -> List[Dict]: ...
    def extract_address(self, entity) -> Dict: ...

# onemap_enricher.py
class OneMapEnricher:
    def geocode_candidate(self, candidate) -> Dict: ...
    def search_nearby_baseline(self, lat, lon, radius_m=50) -> List[Dict]: ...
    def validate_address(self, address, postal_code) -> bool: ...

# baseline_matcher.py
class BaselineMatcher:
    def match_candidate_to_baseline(self, candidate, baseline_places) -> Dict: ...
    def calculate_match_score(self, candidate, baseline) -> float: ...
    def filter_baseline_duplicates(self, candidates) -> List[Dict]: ...

# consolidator.py
class Consolidator:
    def consolidate_candidates(self, candidates, radius_m=20) -> List[Dict]: ...
    def merge_cluster(self, cluster) -> Dict: ...

# classifier.py
class Classifier:
    def classify(self, candidate, baseline_match) -> Dict: ...
    def is_new_place(self, candidate) -> bool: ...
    def is_rebrand(self, candidate, baseline_match) -> bool: ...
    def is_duplicate(self, candidate, baseline_match) -> bool: ...

# freshness_calculator.py
class FreshnessCalculator:
    def calculate_freshness(self, candidate) -> Dict: ...
    def apply_freshness_rules(self, candidate) -> Dict: ...

# discovery_pipeline.py
class DiscoveryPipeline:
    def run(self) -> DiscoveryResult: ...
    def extract_all_sources(self) -> Dict: ...
    def match_to_baseline(self, candidates) -> List[Dict]: ...
    def promote_candidates(self, candidates) -> List[Dict]: ...
```

---

## K. Example Candidate New-Place Record

Low-confidence candidate before consolidation/promotion:

```json
{
  "candidate_id": "cand-temp-yelp-001",
  "source_type": "yelp_business",
  "source_reference": "Yelp/xyz123abc",
  "detected_name": "Dragon Wok Restaurant",
  
  "location": {
    "latitude": 1.3545,
    "longitude": 103.8220,
    "address": "456 Peoples Park Complex, Singapore",
    "postal_code": "050456",
    "geocoding_status": "found_onemap"
  },
  
  "category": "food_beverage",
  "subcategory": "restaurant",
  
  "source_inventory": [
    {
      "source_type": "yelp_business",
      "detected_name": "Dragon Wok Restaurant",
      "yelp_rating": 4.3,
      "yelp_review_count": 12,
      "estimated_opening_date": "2026-02-20",
      "freshness_days": 34,
      "freshness_label": "recent",
      "confidence": "medium"
    }
  ],
  
  "contact": {
    "phone": "+65 6220 8765",
    "website": null,
    "social_media": []
  },
  
  "baseline_matching": {
    "nearest_baseline": {
      "baseline_place_id": "baseline-xyz789",
      "name": "Dragon Restaurant",
      "distance_m": 42,
      "match_score": 0.72
    },
    "match_result": "uncertain",
    "classification": "uncertain",
    "reasoning": "Nearby baseline place (42m) with similar name but different branding"
  },
  
  "freshness": {
    "freshness_label": "recent",
    "freshness_days": 34,
    "freshness_source": "yelp_estimated_opening"
  },
  
  "metadata": {
    "discovery_timestamp": "2026-03-26T14:30:00Z",
    "review_status": "pending_consolidation",
    "confidence": "medium",
    "data_quality_score": 0.62
  }
}
```

---

## L. Example Candidate Promoted as High-Confidence New Place

Candidate after consolidation and multi-source agreement, ready for promotion:

```json
{
  "candidate_id": "cand-new-0001-promoted",
  "candidate_state": "promoted_high_confidence",
  "candidate_source": "multi-source-consolidation",
  
  "detected_name_primary": "Aroma Italian Kitchen",
  "detected_names_all": ["Aroma Italian Kitchen"],
  
  "location": {
    "latitude": 1.3650,
    "longitude": 103.8350,
    "postal_code": "068696",
    "address": "01-234 Marina Square, 6 Marina Boulevard, Singapore 068696",
    "street": "Marina Boulevard",
    "housenumber": "6",
    "formatted_address": "01-234 Marina Square, 6 Marina Boulevard, Singapore 068696",
    "city": "Singapore",
    "country": "SG"
  },
  
  "category": "food_beverage",
  "subcategory": "restaurant",
  
  "registration_evidence": {
    "acra_registry": {
      "uen": "201234567R",
      "company_name": "Aroma Italian Kitchen Pte Ltd",
      "registration_date": "2025-12-10",
      "business_activity": "Food and beverage service activities",
      "status": "Active",
      "source_reference": "ACRA/201234567R"
    }
  },
  
  "source_inventory": [
    {
      "source_type": "acra_registry",
      "detected_name": "Aroma Italian Kitchen",
      "evidence_date": "2025-12-10",
      "freshness_days": 107,
      "freshness_label": "moderately_recent",
      "confidence": "high",
      "source_reference": "ACRA/201234567R"
    },
    {
      "source_type": "onemap_geocoding",
      "address": "01-234 Marina Square, 6 Marina Boulevard, Singapore 068696",
      "postal_code": "068696",
      "geocoded": true,
      "confidence": "high"
    },
    {
      "source_type": "yelp_business",
      "detected_name": "Aroma Italian Kitchen",
      "yelp_id": "aroma-italian-kitchen-singapore",
      "yelp_rating": 4.5,
      "yelp_review_count": 78,
      "estimated_opening_date": "2025-12-15",
      "freshness_days": 102,
      "freshness_label": "moderately_recent",
      "confidence": "high",
      "source_reference": "Yelp/aroma-italian-kitchen-singapore"
    },
    {
      "source_type": "grab_merchant",
      "detected_name": "Aroma Italian Kitchen",
      "grab_merchant_id": "aroma-ik-marina",
      "account_creation_date": "2025-12-12",
      "freshness_days": 105,
      "freshness_label": "moderately_recent",
      "daily_order_volume_avg": 85,
      "confidence": "high",
      "source_reference": "Grab/aroma-ik-marina"
    },
    {
      "source_type": "website",
      "website_url": "https://aromaitaliankitchen.sg",
      "website_title": "Aroma Italian Kitchen - Fine Italian Dining",
      "operating_hours": "11:30-23:00",
      "last_updated": "2026-02-28",
      "days_since_update": 26,
      "confidence": "high"
    },
    {
      "source_type": "imagery",
      "image_date": "2026-02-15",
      "days_old": 39,
      "confidence_operational": 0.92,
      "visual_confirmation": "confirmed",
      "storefront_state": "actively_operating"
    }
  ],
  
  "contact": {
    "phone": "+65 6688 9876",
    "email": "reservations@aromaitaliankitchen.sg",
    "website": "https://aromaitaliankitchen.sg",
    "social_media": [
      {
        "platform": "instagram",
        "handle": "@aromaitaliankitchen_sg",
        "followers": 4200
      },
      {
        "platform": "facebook",
        "handle": "AromaItalianKitchenSG",
        "followers": 3850
      }
    ]
  },
  
  "hours": {
    "opening_hours": "11:30-23:00",
    "monday": "11:30-23:00",
    "tuesday": "11:30-23:00",
    "wednesday": "11:30-23:00",
    "thursday": "11:30-23:00",
    "friday": "11:30-23:30",
    "saturday": "11:30-23:30",
    "sunday": "11:30-23:00",
    "hours_source": ["website", "yelp", "grab"],
    "hours_verified": true
  },
  
  "baseline_matching": {
    "baseline_search_radius_m": 50,
    "baseline_places_found": 3,
    "nearest_baseline": {
      "baseline_place_id": "baseline-999",
      "name": "Italian Restaurant @ Marina",
      "distance_m": 156,
      "category": "food_beverage",
      "subcategory": "restaurant"
    },
    "match_result": "new_place",
    "match_confidence": "high",
    "match_score": 0.18,
    "reasoning": "156m away from nearest baseline; unique brand and registration"
  },
  
  "consolidation": {
    "consolidated_from": 5,
    "source_count": 5,
    "source_types": ["acra_registry", "onemap_geocoding", "yelp_business", "grab_merchant", "website"],
    "multi_source_agreement": true,
    "consolidation_confidence": 0.99,
    "source_agreement_timeline": {
      "acra_registration": "2025-12-10",
      "yelp_opening_estimate": "2025-12-15",
      "grab_account_creation": "2025-12-12",
      "all_sources_agree_within_days": 5
    }
  },
  
  "freshness": {
    "earliest_evidence_date": "2025-12-10",
    "latest_evidence_date": "2026-02-28",
    "freshness_days": 107,
    "freshness_label": "moderately_recent",
    "primary_freshness_source": "acra_registry",
    "within_discovery_threshold": true,
    "within_category_threshold": true
  },
  
  "operational_evidence": {
    "yelp_reviews": 78,
    "yelp_rating": 4.5,
    "grab_daily_orders": 85,
    "website_recent_update": true,
    "days_since_website_update": 26,
    "imagery_status": "confirmed_operational",
    "social_media_followers": 8050,
    "social_media_posts_recent": true,
    "operational_confidence": "very_high",
    "operational_flags": []
  },
  
  "category_validation": {
    "category": "food_beverage",
    "subcategory": "restaurant",
    "primary_sources_required": ["acra_registry", "yelp_business", "grab_merchant"],
    "primary_sources_present": ["acra_registry", "yelp_business", "grab_merchant"],
    "minimum_sources_for_promotion": 2,
    "actual_sources": 5,
    "freshness_threshold_days": 90,
    "actual_freshness_days": 107,
    "require_operational_evidence": true,
    "operational_evidence_present": true,
    "category_rule_status": "passed_all"
  },
  
  "promotion_analysis": {
    "promotion_candidates_considered": 127,
    "promotion_candidates_filtered": 34,
    "promotion_this_candidate": true,
    "promotion_confidence": "high",
    "promotion_rank": 1,
    "promotion_score": 0.96,
    
    "promotion_factors": [
      {
        "factor": "ACRA registration (oldest evidence)",
        "weight": 0.25,
        "score": 1.0,
        "contribution": 0.25, 
        "note": "Recent registration (107 days old, within 180-day threshold)"
      },
      {
        "factor": "Multi-source agreement (5 sources)",
        "weight": 0.25,
        "score": 1.0,
        "contribution": 0.25,
        "note": "ACRA + Yelp + Grab + Website + Imagery all confirm opening date within 5 days"
      },
      {
        "factor": "Strong operational evidence",
        "weight": 0.20,
        "score": 1.0,
        "contribution": 0.20,
        "note": "78 Yelp reviews (4.5★), 85 daily Grab orders, active social media (8k followers)"
      },
      {
        "factor": "Baseline exclusion (156m away)",
        "weight": 0.15,
        "score": 1.0,
        "contribution": 0.15,
        "note": "Clear separation from existing baseline places"
      },
      {
        "factor": "Category rule compliance",
        "weight": 0.15,
        "score": 1.0,
        "contribution": 0.15,
        "note": "Meets all restaurant category requirements (3primary sources, operational evidence)"
      }
    ],
    
    "promotion_reasons": [
      "Official ACRA registration 107 days ago (recent business entity)",
      "Multi-source consolidation (5 independent sources agree)",
      "All evidence sources consistent on opening timeline (Dec 10-15, 2025)",
      "Strong operational indicators (78 Yelp reviews, 85 Grab orders/day, active social media)",
      "156m+ away from baseline places - clearly not existing duplicate",
      "Website recently updated (Feb 28); imagery confirms active storefront"
    ],
    
    "promotion_decision": "PROMOTE_TO_HIGH_CONFIDENCE_NEW_PLACE",
    "promotion_decision_reason": "Converging evidence from 5 independent authoritative sources, strong operational confirmation, clear baseline separation"
  },
  
  "metadata": {
    "discovery_timestamp": "2026-03-26T14:30:00Z",
    "discovery_session_id": "discovery-2026-03-26-session-001",
    "last_updated": "2026-03-26T14:45:00Z",
    "discovery_phase": "consolidated_promoted",
    "review_status": "automated_promoted",
    "review_decision_timestamp": "2026-03-26T14:45:00Z",
    "review_confidence": "very_high",
    "human_review_required": false,
    "human_review_suggested": false,
    "data_quality_score": 0.96,
    "readiness": "ready_for_feed_import"
  }
}
```

---

## Summary

This comprehensive new-place discovery layer provides:

1. **Multi-source extraction**: 6 evidence sources (data.gov.sg, OneMap, Yelp, Grab, websites, imagery)
2. **Baseline matching**: Exclude duplicates via geospatial + name matching
3. **Consolidation**: Merge multi-source candidates in dense areas
4. **Category-aware logic**: Different rules for cafes vs hotels vs attractions
5. **Freshness assessment**: Qualification of "newness" with timestamps
6. **Classification**: NEW vs REBRAND vs DUPLICATE distinction
7. **Production schema**: Comprehensive candidate record structure
8. **Multi-source promotion**: Evidence-based confidence scoring

All functionality is implementation-ready with modular backend design, ready for coding.
