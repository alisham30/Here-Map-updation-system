import os
import re
import difflib

CLOSURE_KEYWORDS = [
    "for lease", "for rent", "vacant", "closed", "shuttered",
    "coming soon", "under renovation", "space available", "premises available",
    "to let", "available for lease",
]
ACTIVE_KEYWORDS = [
    "open", "welcome", "hours", "menu", "daily", "serving",
    "delivery", "dine in", "takeaway", "open now",
]


def _clean_text(raw: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9 ]+", " ", raw)
    return cleaned.lower().strip()


def _seq_match(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _null_result() -> dict:
    return {
        "raw_texts": [],
        "cleaned_texts": [],
        "best_match_text": "",
        "match_score": 0.0,
        "name_mismatch": True,
        "closure_keywords_found": [],
        "active_keywords_found": [],
        "closure_signal_strength": 0.0,
        "ocr_confidence": 0.0,
        "possible_new_name": "",
    }


def _run_easyocr(crop_path: str) -> list[tuple[str, float]]:
    """Returns list of (text, confidence) from EasyOCR."""
    import easyocr  # type: ignore
    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    raw_results = reader.readtext(crop_path)
    # Each result: [bbox, text, confidence]
    return [(item[1], float(item[2])) for item in raw_results]


def _run_pytesseract(crop_path: str) -> list[tuple[str, float]]:
    """Fallback: pytesseract. Returns (text, confidence=0.7) tuples."""
    import pytesseract  # type: ignore
    from PIL import Image
    img = Image.open(crop_path)
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    results = []
    for i, text in enumerate(data["text"]):
        conf = int(data["conf"][i])
        if text.strip() and conf > 50:
            results.append((text.strip(), conf / 100.0))
    return results


def extract_signage_text(crop_path: str, osm_name: str = "") -> dict:
    try:
        if not crop_path or not os.path.exists(crop_path):
            print(f"[ocr_module] Crop not found: {crop_path}")
            return _null_result()

        # Try EasyOCR → pytesseract → empty
        raw_items: list[tuple[str, float]] = []
        try:
            raw_items = _run_easyocr(crop_path)
        except ImportError:
            print("[ocr_module] easyocr not installed — trying pytesseract")
            try:
                raw_items = _run_pytesseract(crop_path)
            except ImportError:
                print("[ocr_module] pytesseract also not installed — returning empty")
                return _null_result()
        except Exception as e:
            print(f"[ocr_module] OCR engine error: {e}")
            return _null_result()

        # Filter by confidence threshold
        threshold = 0.5
        filtered = [(txt, conf) for txt, conf in raw_items if conf >= threshold]

        raw_texts = [t for t, _ in filtered]
        cleaned_texts = [_clean_text(t) for t in raw_texts]
        avg_conf = float(sum(c for _, c in filtered) / len(filtered)) if filtered else 0.0

        # Name matching
        best_match_text = ""
        best_score = 0.0
        for t in cleaned_texts:
            score = _seq_match(t, _clean_text(osm_name))
            if score > best_score:
                best_score = score
                best_match_text = t
        name_mismatch = best_score < 0.6

        # Possible new name: highest scoring non-matching text
        possible_new_name = ""
        if name_mismatch and cleaned_texts:
            # Pick longest cleaned text as candidate name
            possible_new_name = max(cleaned_texts, key=len)

        # Keyword detection (on joined full text)
        all_text = " ".join(cleaned_texts)
        closure_found = [kw for kw in CLOSURE_KEYWORDS if kw in all_text]
        active_found = [kw for kw in ACTIVE_KEYWORDS if kw in all_text]

        # Closure signal strength
        if closure_found and not active_found:
            closure_strength = min(0.4 + 0.15 * len(closure_found), 1.0)
        elif closure_found and active_found:
            closure_strength = 0.3
        else:
            closure_strength = 0.0

        return {
            "raw_texts": raw_texts,
            "cleaned_texts": cleaned_texts,
            "best_match_text": best_match_text,
            "match_score": round(best_score, 4),
            "name_mismatch": name_mismatch,
            "closure_keywords_found": closure_found,
            "active_keywords_found": active_found,
            "closure_signal_strength": round(closure_strength, 4),
            "ocr_confidence": round(avg_conf, 4),
            "possible_new_name": possible_new_name,
        }

    except Exception as e:
        print(f"[ocr_module] extract_signage_text error: {e}")
        return _null_result()


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    name = sys.argv[2] if len(sys.argv) > 2 else "test place"
    if not path:
        print("Usage: python ocr_module.py <crop_path> [osm_name]")
    else:
        r = extract_signage_text(path, osm_name=name)
        print(f"Texts found       : {r['raw_texts']}")
        print(f"Best match        : '{r['best_match_text']}' (score={r['match_score']:.2f})")
        print(f"Name mismatch     : {r['name_mismatch']}")
        print(f"Closure keywords  : {r['closure_keywords_found']}")
        print(f"Active keywords   : {r['active_keywords_found']}")
        print(f"Closure strength  : {r['closure_signal_strength']:.2f}")
