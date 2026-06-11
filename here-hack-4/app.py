"""
MapFreshness — Streamlit Demo App
Loads Singapore POIs and runs vision analysis on demand.
"""
import os
import sys
import json

import streamlit as st

# ── path setup ────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, 'map', 'backend', '.env'))

from agent.tools.streetview import get_street_view_score

st.set_page_config(
    page_title='MapFreshness — Singapore',
    page_icon='🗺️',
    layout='wide',
)

# ── Load baseline POIs ────────────────────────────────────────────────────────

@st.cache_data
def load_pois():
    geojson_path = os.path.join(ROOT, 'map', 'baseline_consolidated.geojson')
    if not os.path.exists(geojson_path):
        return []
    with open(geojson_path, 'r') as f:
        data = json.load(f)
    pois = []
    for feat in data.get('features', []):
        props = feat.get('properties', {})
        geom  = feat.get('geometry', {})
        coords = geom.get('coordinates', [None, None])
        pois.append({
            'name':      props.get('name', 'Unknown'),
            'category':  props.get('category') or props.get('amenity') or props.get('shop') or '',
            'lat':       coords[1],
            'lon':       coords[0],
            'place_id':  props.get('place_id') or props.get('osm_id') or '',
            'address':   props.get('address') or props.get('addr:street') or '',
            'source_layer': props.get('source_layer', ''),
        })
    return [p for p in pois if p['lat'] and p['lon']]


def process_single_poi(poi: dict) -> dict:
    """Run vision analysis on one POI and return enriched result dict."""
    sv = get_street_view_score(
        lat=poi['lat'],
        lon=poi['lon'],
        poi_name=poi['name'],
        poi_category=poi.get('category', ''),
        osm_id=poi.get('place_id', 'unknown'),
    )
    result = dict(poi)
    result['vision_score']           = sv.get('vision_score', 50)
    result['image_url']              = sv.get('image_url')
    result['image_path']             = sv.get('image_path')
    result['captured_at']            = sv.get('captured_at')
    result['recency_weight']         = sv.get('recency_weight', 1.0)
    result['age_label']              = sv.get('age_label', '')
    result['image_age_days']         = sv.get('image_age_days', 0)
    result['is_open']                = sv.get('is_open')
    result['confidence']             = sv.get('confidence', 0)
    result['observation']            = sv.get('observation', '')
    result['detected_business_type'] = sv.get('detected_business_type', 'unknown')
    result['all_text_found']         = sv.get('all_text_found', [])
    result['detected_business_name'] = sv.get('detected_business_name')
    result['name_match_score']       = sv.get('name_match_score', 0)
    result['name_mismatch']          = sv.get('name_mismatch', False)
    result['closure_keywords']       = sv.get('closure_keywords', [])
    result['status']                 = sv.get('status', 'UNCLEAR')
    result['signage_text']           = sv.get('signage_text')
    result['best_matching_text']     = sv.get('best_matching_text')
    return result


# ── Session state ─────────────────────────────────────────────────────────────
if 'results' not in st.session_state:
    st.session_state.results = {}   # place_id → result dict
if 'selected_id' not in st.session_state:
    st.session_state.selected_id = None


# ── Header ────────────────────────────────────────────────────────────────────
st.title('🗺️ MapFreshness — Singapore POI Freshness')
st.caption('Select a POI from the sidebar, run vision analysis, inspect signage evidence.')

pois = load_pois()
if not pois:
    st.error('No POIs loaded — check baseline_consolidated.geojson path')
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header('📍 POI Explorer')
    st.caption(f'{len(pois)} places loaded')

    # Filters
    search_q = st.text_input('🔍 Search by name', placeholder='e.g. McDonald')
    cat_options = ['All'] + sorted({p['category'] for p in pois if p['category']})
    cat_filter = st.selectbox('Category', cat_options)
    show_visuals_only = st.checkbox('📷 Only POIs with images', value=False)

    st.divider()

    # Apply filters
    filtered = pois
    if search_q:
        filtered = [p for p in filtered if search_q.lower() in p['name'].lower()]
    if cat_filter != 'All':
        filtered = [p for p in filtered if p['category'] == cat_filter]
    if show_visuals_only:
        filtered = [p for p in filtered if st.session_state.results.get(
            p['place_id'] or p['name'], {}
        ).get('image_url')]

    st.caption(f'Showing {len(filtered)} POIs')

    for poi in filtered[:80]:
        pid = poi['place_id'] or poi['name']
        res = st.session_state.results.get(pid, {})
        has_img = '📷 ' if res.get('image_url') else ''
        scr = res.get('vision_score', '—')
        cat = poi['category'][:18] if poi['category'] else ''
        label = f"{has_img}{poi['name'][:30]}  ·  {cat}  ·  {scr}/100" if res else f"{poi['name'][:35]}  ·  {cat}"
        if st.button(label, key=f"btn_{pid}", use_container_width=True):
            st.session_state.selected_id = pid


# ── Main panel ────────────────────────────────────────────────────────────────
selected_poi = None
if st.session_state.selected_id:
    pid = st.session_state.selected_id
    selected_poi = next((p for p in pois if (p['place_id'] or p['name']) == pid), None)

if selected_poi is None:
    st.info('Select a POI from the sidebar to begin.')
    st.stop()

pid = selected_poi['place_id'] or selected_poi['name']
existing = st.session_state.results.get(pid)
selected = existing or selected_poi

col_info, col_vision = st.columns([1, 1], gap='large')

# ── Left col: basic info + run button ────────────────────────────────────────
with col_info:
    st.subheader(f"📍 {selected_poi['name']}")
    st.markdown(f"**Category:** {selected_poi.get('category') or '—'}")
    st.markdown(f"**Address:** {selected_poi.get('address') or '—'}")
    st.markdown(f"**Coordinates:** {selected_poi['lat']:.5f}, {selected_poi['lon']:.5f}")

    if existing:
        scr = existing.get('vision_score', 50)
        status = existing.get('status', 'UNCLEAR')
        status_color = {
            'ACTIVE': '🟢', 'CLOSED': '🔴', 'UNDER_CONSTRUCTION': '🟠',
            'DIFFERENT_BUSINESS': '🟣', 'UNCLEAR': '⚪',
        }.get(status, '⚪')
        st.metric('Vision Score', f'{scr} / 100')
        st.markdown(f"**Verdict:** {status_color} {status}")
        if existing.get('observation'):
            with st.expander('AI Observation'):
                st.write(existing['observation'])
        if st.button('↺ Re-run Vision Analysis', use_container_width=True):
            with st.spinner('Running vision analysis…'):
                result = process_single_poi(selected_poi)
                st.session_state.results[pid] = result
            st.rerun()
    else:
        if st.button('▶ Run Vision Analysis', type='primary', use_container_width=True):
            with st.spinner('Fetching image + running GPT-4o-mini vision…'):
                result = process_single_poi(selected_poi)
                st.session_state.results[pid] = result
            st.rerun()

# ── Right col: visual evidence ────────────────────────────────────────────────
with col_vision:
    if not existing:
        st.info('Click "Run Vision Analysis" to fetch street imagery and analyse it.')
    else:
        st.subheader('📷 Street View Evidence')

        # ── Age warning ───────────────────────────────────────────────────
        age_label = existing.get('age_label', '')
        recency   = existing.get('recency_weight', 1.0)
        if age_label:
            if recency < 0.5:
                st.warning(f'⚠️ Image captured {age_label} — confidence reduced to {int(recency*100)}%')
            else:
                st.caption(f'📅 Captured {age_label}')

        # ── Street image ──────────────────────────────────────────────────
        if existing.get('image_url'):
            try:
                st.image(existing['image_url'], use_container_width=True)
            except Exception:
                st.markdown(f"[View Image]({existing['image_url']})")
        elif existing.get('image_path') and os.path.exists(existing['image_path']):
            st.image(existing['image_path'], use_container_width=True)
        else:
            st.warning('No street image found near this location.')

        # ── Signage text ──────────────────────────────────────────────────
        all_text = existing.get('all_text_found', [])
        if all_text:
            st.markdown(f"**📝 Text on signs:** {', '.join(str(t) for t in all_text)}")

        # ── Name match ────────────────────────────────────────────────────
        detected_name = existing.get('detected_business_name')
        if detected_name and str(detected_name).lower() not in ('null', 'none', ''):
            name_score = existing.get('name_match_score', 0)
            if name_score > 0.6:
                st.success(f"✅ Sign reads '{detected_name}' — matches OSM name ({name_score:.0%})")
            elif name_score > 0.3:
                st.warning(f"⚠️ Sign reads '{detected_name}' — partial match ({name_score:.0%})")
            else:
                st.error(f"❌ Sign reads '{detected_name}' — does NOT match OSM '{selected_poi['name']}' ({name_score:.0%})")

        # ── Closure keywords ──────────────────────────────────────────────
        closure_kw = existing.get('closure_keywords', [])
        if closure_kw:
            st.error(f"🚫 Closure signals found: {', '.join(str(k) for k in closure_kw)}")

        # ── Vision status badge ───────────────────────────────────────────
        vision_status = existing.get('status', '')
        if vision_status and vision_status != 'UNCLEAR':
            emoji = {'ACTIVE': '🟢', 'CLOSED': '🔴', 'UNDER_CONSTRUCTION': '🟠',
                     'DIFFERENT_BUSINESS': '🟣'}.get(vision_status, '⚪')
            st.markdown(f"**Vision verdict:** {emoji} {vision_status}")

        # ── YOLO objects (if populated) ───────────────────────────────────
        yolo_objs = existing.get('yolo_objects', [])
        if yolo_objs:
            objs = list(set(d.get('object', d.get('class', '')) for d in yolo_objs[:8]))
            st.markdown(f"**🔍 Objects detected:** {', '.join(objs)}")

        # ── GradCAM overlay (from vision_pipeline if available) ───────────
        gradcam_b64 = existing.get('gradcam_overlay_b64') or (
            existing.get('gradcam_result') or {}
        ).get('gradcam_overlay_b64')
        if gradcam_b64:
            with st.expander('🔥 GradCAM Heatmap'):
                import base64
                from PIL import Image
                import io
                img_bytes = base64.b64decode(gradcam_b64)
                img = Image.open(io.BytesIO(img_bytes))
                st.image(img, caption='GradCAM attention overlay', use_container_width=True)
                zone = (existing.get('gradcam_result') or {}).get('attention_focus_zone', '—')
                reliable = (existing.get('gradcam_result') or {}).get('attention_reliable', False)
                st.caption(f'Focus zone: {zone} · Reliable: {"yes" if reliable else "no"}')
