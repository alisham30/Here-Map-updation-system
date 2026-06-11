import os
import sys
import json
import base64
import difflib
import requests
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()
_backend_env = os.path.join(os.path.dirname(__file__), '..', '..', 'map', 'backend', '.env')
if os.path.exists(_backend_env):
    load_dotenv(_backend_env)

MAPILLARY_ACCESS_TOKEN = os.getenv('MAPILLARY_ACCESS_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'imagery_cache')


# ─── Mapillary image fetch ────────────────────────────────────────────────────

def fetch_mapillary_image(lat: float, lon: float, osm_id: str = 'unknown') -> dict:
    """Fetch the most recent Mapillary street image near (lat, lon)."""
    _null = {
        'found': False, 'image_path': None, 'image_url': None,
        'image_base64': None, 'captured_at': None,
        'recency_weight': 1.0, 'age_label': '', 'image_age_days': 0,
        'mapillary_id': None, 'compass_angle': None,
    }

    try:
        if not MAPILLARY_ACCESS_TOKEN:
            return _null

        bbox = f"{lon-0.001},{lat-0.001},{lon+0.001},{lat+0.001}"
        for attempt in range(2):
            try:
                resp = requests.get(
                    'https://graph.mapillary.com/images',
                    params={
                        'access_token': MAPILLARY_ACCESS_TOKEN,
                        'fields': 'id,captured_at,geometry,thumb_1024_url,compass_angle',
                        'bbox': bbox,
                        'limit': 10,
                    },
                    timeout=15,
                )
                if resp.status_code == 429:
                    import time; time.sleep(2)
                    continue
                resp.raise_for_status()
                break
            except requests.exceptions.RequestException:
                if attempt == 0:
                    import time; time.sleep(2)
                else:
                    return _null

        data = resp.json().get('data', [])
        if not data:
            return _null

        # Sort by captured_at descending (most recent first)
        data.sort(key=lambda x: x.get('captured_at', 0) if isinstance(x.get('captured_at'), (int, float)) else 0, reverse=True)
        top = data[0]

        img_id = top.get('id', 'unknown')
        captured_at = top.get('captured_at', 0)
        thumb_url = top.get('thumb_1024_url', '')
        compass_angle = top.get('compass_angle')

        # ── Recency weight ────────────────────────────────────────────────
        captured_ts = captured_at / 1000 if isinstance(captured_at, (int, float)) else 0
        captured_dt = datetime.fromtimestamp(captured_ts, tz=timezone.utc) if captured_ts > 0 else None
        if captured_dt:
            image_age_days = (datetime.now(timezone.utc) - captured_dt).days
        else:
            image_age_days = 9999

        if image_age_days <= 180:
            recency_weight = 1.0
        elif image_age_days <= 365:
            recency_weight = 0.8
        elif image_age_days <= 730:
            recency_weight = 0.55
        elif image_age_days <= 1460:
            recency_weight = 0.30
        else:
            recency_weight = 0.15

        if image_age_days < 30:
            age_label = 'less than a month ago'
        elif image_age_days < 365:
            age_label = f"{image_age_days // 30} months ago"
        elif image_age_days < 730:
            age_label = 'about 1 year ago'
        elif image_age_days < 1460:
            age_label = f"about {image_age_days // 365} years ago — low confidence"
        else:
            age_label = f"{image_age_days // 365} years ago — very low confidence"

        # ── Download image ────────────────────────────────────────────────
        cache_dir = os.path.join(CACHE_DIR, str(osm_id))
        os.makedirs(cache_dir, exist_ok=True)
        img_path = os.path.join(cache_dir, f'mapillary_{img_id}.jpg')

        img_b64 = None
        if thumb_url:
            try:
                img_resp = requests.get(thumb_url, timeout=20)
                img_resp.raise_for_status()
                with open(img_path, 'wb') as f:
                    f.write(img_resp.content)
                img_b64 = base64.b64encode(img_resp.content).decode('utf-8')
            except Exception as e:
                print(f"[streetview] Image download failed: {e}")
                img_path = None

        return {
            'found': img_path is not None and os.path.exists(img_path),
            'image_path': img_path,
            'image_url': thumb_url,
            'image_base64': img_b64,
            'captured_at': captured_dt.strftime('%Y-%m-%d') if captured_dt else str(captured_at),
            'recency_weight': recency_weight,
            'age_label': age_label,
            'image_age_days': image_age_days,
            'mapillary_id': img_id,
            'compass_angle': compass_angle,
        }

    except Exception as e:
        print(f"[streetview] fetch_mapillary_image error: {e}")
        return _null


# ─── OpenAI vision analysis ───────────────────────────────────────────────────

def analyze_image_with_openai(image_base64: str, poi_name: str, poi_category: str) -> dict:
    """
    Send image to OpenAI GPT-4o-mini vision and analyze the business.
    Reads signage text, assesses open/closed status, detects business type.
    """
    _mock = {
        'is_open': True, 'confidence': 0.5,
        'observation': 'Mock: OpenAI API not available',
        'detected_business_type': 'unknown',
        'signage_text': None, 'all_text_found': [],
        'detected_business_name': None, 'closure_keywords': [],
        'status': 'UNCLEAR',
    }

    if not OPENAI_API_KEY:
        print('[streetview] Warning: OPENAI_API_KEY not set — returning mock vision result')
        return _mock

    prompt = (
        f'You are a map quality analyst reviewing a street-level image from Singapore.\n\n'
        f'The OSM record says this location should be: "{poi_name}" ({poi_category})\n\n'
        f'Do THREE things:\n\n'
        f'1. READ ALL TEXT visible on signs, boards, banners, awnings, windows. List every piece of text you can see.\n\n'
        f'2. ASSESS the business status by looking at:\n'
        f'   - ACTIVE signs: lit signage, open doors, customers inside, merchandise on display, maintained exterior\n'
        f'   - CLOSED signs: boarded windows, "closed"/"for lease"/"for rent" signs, empty storefront, construction barriers, faded/broken signage, overgrown entrance\n'
        f'   - DIFFERENT BUSINESS: signage shows a completely different business name/type than what OSM says\n\n'
        f'3. DETERMINE the business type from visual cues (restaurant, cafe, pharmacy, supermarket, hotel, etc.)\n\n'
        f'Return ONLY valid JSON, no other text:\n'
        f'{{\n'
        f'  "is_open": true or false,\n'
        f'  "confidence": 0.0 to 1.0,\n'
        f'  "observation": "2-3 sentence description of what you see",\n'
        f'  "detected_business_type": "single word like restaurant/cafe/pharmacy/hotel/supermarket/mall/fuel/empty/construction/unknown",\n'
        f'  "all_text_found": ["list", "of", "every", "text", "visible", "on", "signs"],\n'
        f'  "detected_business_name": "the main business name visible on signage, or null if not readable",\n'
        f'  "closure_keywords": ["any closure-related text like for lease, closed, etc"],\n'
        f'  "status": "ACTIVE" or "CLOSED" or "UNDER_CONSTRUCTION" or "DIFFERENT_BUSINESS" or "UNCLEAR",\n'
        f'  "signage_text": "most prominent text visible on signs"\n'
        f'}}'
    )

    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': 'gpt-4o-mini',
        'messages': [{
            'role': 'user',
            'content': [
                {
                    'type': 'image_url',
                    'image_url': {'url': f'data:image/jpeg;base64,{image_base64}', 'detail': 'low'},
                },
                {'type': 'text', 'text': prompt},
            ],
        }],
        'max_tokens': 1024,
        'temperature': 0.1,
    }

    try:
        resp = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers=headers, json=payload, timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content'].strip()

        # Strip markdown fences
        if '```' in content:
            parts = content.split('```')
            content = parts[1] if len(parts) >= 2 else parts[0]
            if content.startswith('json'):
                content = content[4:]
            content = content.strip()

        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1:
            content = content[start:end + 1]

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            import re
            m_open = re.search(r'"is_open"\s*:\s*(true|false)', content, re.IGNORECASE)
            m_conf = re.search(r'"confidence"\s*:\s*([\d.]+)', content)
            m_obs  = re.search(r'"observation"\s*:\s*"([^"]*)"', content)
            m_type = re.search(r'"detected_business_type"\s*:\s*"([^"]*)"', content)
            m_name = re.search(r'"detected_business_name"\s*:\s*"([^"]*)"', content)
            m_stat = re.search(r'"status"\s*:\s*"([^"]*)"', content)
            result = {
                'is_open': m_open.group(1).lower() == 'true' if m_open else True,
                'confidence': float(m_conf.group(1)) if m_conf else 0.5,
                'observation': m_obs.group(1) if m_obs else '',
                'detected_business_type': m_type.group(1) if m_type else 'unknown',
                'detected_business_name': m_name.group(1) if m_name else None,
                'status': m_stat.group(1) if m_stat else 'UNCLEAR',
                'all_text_found': [], 'closure_keywords': [], 'signage_text': None,
            }

        result['is_open'] = bool(result.get('is_open', True))
        result['confidence'] = float(result.get('confidence', 0.5))
        result.setdefault('observation', '')
        result.setdefault('detected_business_type', 'unknown')
        result.setdefault('all_text_found', [])
        result.setdefault('detected_business_name', None)
        result.setdefault('closure_keywords', [])
        result.setdefault('status', 'UNCLEAR')
        result.setdefault('signage_text', None)
        return result

    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else 'unknown'
        txt  = e.response.text[:300] if e.response is not None else ''
        print(f'[streetview] OpenAI API error ({code}): {txt}')
        return _mock
    except Exception as e:
        print(f'[streetview] analyze_image_with_openai error: {e}')
        return _mock


# ─── Combined street view score ───────────────────────────────────────────────

def get_street_view_score(lat: float, lon: float, poi_name: str,
                          poi_category: str = '', osm_id: str = 'unknown') -> dict:
    """
    Main entry point. Fetches Mapillary image, runs OpenAI vision,
    applies fuzzy name matching and recency weighting.
    Returns a dict with vision_score (0-100) and all evidence fields.
    """
    _null_result = {
        'vision_score': 50, 'found': False,
        'image_url': None, 'image_path': None,
        'captured_at': None, 'recency_weight': 1.0,
        'age_label': '', 'image_age_days': 0,
        'is_open': None, 'confidence': 0,
        'observation': '', 'detected_business_type': 'unknown',
        'all_text_found': [], 'detected_business_name': None,
        'name_match_score': 0, 'name_mismatch': False,
        'closure_keywords': [], 'status': 'UNCLEAR',
        'signage_text': None, 'best_matching_text': None,
    }

    try:
        img_result = fetch_mapillary_image(lat, lon, osm_id=osm_id)
        if not img_result.get('found') or not img_result.get('image_base64'):
            return {**_null_result, 'found': False}

        analysis = analyze_image_with_openai(
            img_result['image_base64'], poi_name, poi_category
        )

        # ── Fuzzy name matching ───────────────────────────────────────────
        detected_name = analysis.get('detected_business_name')
        all_texts = analysis.get('all_text_found', [])

        name_match_score = 0.0
        best_matching_text = None

        if detected_name and str(detected_name).lower() not in ('null', 'none', ''):
            name_match_score = difflib.SequenceMatcher(
                None, poi_name.lower(), detected_name.lower()
            ).ratio()
            best_matching_text = detected_name

        for text in all_texts:
            if isinstance(text, str) and len(text) > 2:
                sim = difflib.SequenceMatcher(None, poi_name.lower(), text.lower()).ratio()
                if sim > name_match_score:
                    name_match_score = sim
                    best_matching_text = text

        name_mismatch = bool(best_matching_text and name_match_score < 0.4)

        analysis['name_match_score']   = round(name_match_score, 3)
        analysis['best_matching_text'] = best_matching_text
        analysis['name_mismatch']      = name_mismatch

        # ── Vision score ──────────────────────────────────────────────────
        is_open   = analysis.get('is_open', True)
        confidence = float(analysis.get('confidence', 0.5))
        recency_weight = img_result.get('recency_weight', 1.0)

        if is_open:
            base_vision_score = 90 if confidence > 0.8 else 70 if confidence >= 0.5 else 55
        else:
            base_vision_score = 10 if confidence > 0.8 else 30 if confidence >= 0.5 else 45

        vision_score = int(base_vision_score * recency_weight)

        if analysis.get('closure_keywords'):
            vision_score = int(vision_score * 0.5)

        if name_mismatch:
            vision_score = max(vision_score - 15, 0)

        vision_score = max(0, min(100, vision_score))

        return {
            'vision_score': vision_score,
            'found': True,
            'image_url': img_result.get('image_url'),
            'image_path': img_result.get('image_path'),
            'captured_at': img_result.get('captured_at'),
            'recency_weight': recency_weight,
            'age_label': img_result.get('age_label', ''),
            'image_age_days': img_result.get('image_age_days', 0),
            'is_open': is_open,
            'confidence': confidence,
            'observation': analysis.get('observation', ''),
            'detected_business_type': analysis.get('detected_business_type', 'unknown'),
            'all_text_found': analysis.get('all_text_found', []),
            'detected_business_name': analysis.get('detected_business_name'),
            'name_match_score': analysis.get('name_match_score', 0),
            'name_mismatch': name_mismatch,
            'best_matching_text': best_matching_text,
            'closure_keywords': analysis.get('closure_keywords', []),
            'status': analysis.get('status', 'UNCLEAR'),
            'signage_text': analysis.get('signage_text'),
        }

    except Exception as e:
        print(f'[streetview] get_street_view_score error: {e}')
        return _null_result


if __name__ == '__main__':
    tests = [
        ('Orchard Road', 1.3040, 103.8318, 'restaurant'),
        ('Bugis Junction', 1.2994, 103.8554, 'mall'),
    ]
    for name, lat, lon, cat in tests:
        print(f'\n--- {name} ---')
        r = get_street_view_score(lat, lon, poi_name=name, poi_category=cat, osm_id=name.replace(' ', '_'))
        print(f"  found          : {r['found']}")
        print(f"  vision_score   : {r['vision_score']}")
        print(f"  status         : {r['status']}")
        print(f"  age_label      : {r['age_label']}")
        print(f"  recency_weight : {r['recency_weight']}")
        print(f"  all_text_found : {r['all_text_found']}")
        print(f"  detected_name  : {r['detected_business_name']}")
        print(f"  name_mismatch  : {r['name_mismatch']} (score={r['name_match_score']:.2f})")
        print(f"  closure_kw     : {r['closure_keywords']}")
        print(f"  observation    : {r['observation'][:120]}")
