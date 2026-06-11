import os
import json
import base64
import requests
from dotenv import load_dotenv

load_dotenv()
_backend_env = os.path.join(os.path.dirname(__file__), '..', '..', 'map', 'backend', '.env')
if os.path.exists(_backend_env):
    load_dotenv(_backend_env)

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')


def detect_category_openai(image_base64: str, poi_name: str, osm_category: str) -> dict:
    """
    Use GPT-4o-mini vision to detect the actual business category from an image.
    Returns detected_category, confidence, and reasoning.
    """
    _mock = {'detected_category': 'unknown', 'confidence': 0.5, 'reasoning': 'Mock'}

    if not OPENAI_API_KEY:
        print('[category_detector] Warning: OPENAI_API_KEY not set — returning mock')
        return _mock

    prompt = (
        'What type of business is shown in this image? '
        'Consider the signage, objects, layout, and overall appearance.\n'
        'Also read ALL text visible on any signs or boards.\n\n'
        'Return ONLY valid JSON, no other text:\n'
        '{\n'
        '  "detected_category": "single word: restaurant/cafe/pharmacy/hotel/supermarket/'
        'convenience_store/fuel_station/mall/bank/empty/construction/residential/unknown",\n'
        '  "confidence": 0.0 to 1.0,\n'
        '  "reasoning": "brief explanation"\n'
        '}'
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
        'max_tokens': 512,
        'temperature': 0.1,
    }

    try:
        resp = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers=headers, json=payload, timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content'].strip()

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
            m_cat  = re.search(r'"detected_category"\s*:\s*"([^"]*)"', content)
            m_conf = re.search(r'"confidence"\s*:\s*([\d.]+)', content)
            m_reas = re.search(r'"reasoning"\s*:\s*"([^"]*)"', content)
            result = {
                'detected_category': m_cat.group(1) if m_cat else 'unknown',
                'confidence': float(m_conf.group(1)) if m_conf else 0.5,
                'reasoning': m_reas.group(1) if m_reas else '',
            }

        result['confidence'] = float(result.get('confidence', 0.5))
        result.setdefault('detected_category', 'unknown')
        result.setdefault('reasoning', '')
        return result

    except Exception as e:
        print(f'[category_detector] detect_category_openai error: {e}')
        return _mock


def check_category_mismatch(image_base64: str, poi_name: str, osm_category: str) -> dict:
    """
    Run category detection and compare against OSM category.
    Returns mismatch flag and details.
    """
    try:
        result = detect_category_openai(image_base64, poi_name, osm_category)
        detected = result.get('detected_category', 'unknown')

        # Simple mismatch check — expand as needed
        osm_norm = osm_category.lower().replace('_', ' ').replace('-', ' ')
        det_norm = detected.lower().replace('_', ' ')

        # Direct or partial match = no mismatch
        mismatch = (
            detected not in ('unknown', 'unclear')
            and det_norm not in osm_norm
            and osm_norm not in det_norm
        )

        return {
            **result,
            'osm_category': osm_category,
            'category_mismatch': mismatch,
        }
    except Exception as e:
        print(f'[category_detector] check_category_mismatch error: {e}')
        return {
            'detected_category': 'unknown', 'confidence': 0.5,
            'reasoning': str(e), 'osm_category': osm_category,
            'category_mismatch': False,
        }


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print('Usage: python category_detector.py <image_path> [osm_category]')
    else:
        import base64
        osm_cat = sys.argv[2] if len(sys.argv) > 2 else 'restaurant'
        with open(path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
        r = check_category_mismatch(b64, 'Test Place', osm_cat)
        print(f"Detected  : {r['detected_category']} ({r['confidence']:.0%})")
        print(f"OSM       : {r['osm_category']}")
        print(f"Mismatch  : {r['category_mismatch']}")
        print(f"Reasoning : {r['reasoning']}")
