import os

CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'imagery_cache')

_YOLO_MODEL = None  # module-level cache — loaded once


def _load_yolo():
    global _YOLO_MODEL
    if _YOLO_MODEL is not None:
        return _YOLO_MODEL
    try:
        from ultralytics import YOLO  # type: ignore
        _YOLO_MODEL = YOLO("yolov8n.pt")  # auto-downloads on first run
        return _YOLO_MODEL
    except Exception as e:
        print(f"[yolo_cropper] ultralytics not available: {e}")
        return None


def _center_crop(image_path: str, osm_id: str) -> dict:
    """Fallback: PIL center 60% crop."""
    try:
        from PIL import Image
        img = Image.open(image_path)
        w, h = img.size
        margin_x = int(w * 0.2)
        margin_y = int(h * 0.2)
        box = (margin_x, margin_y, w - margin_x, h - margin_y)
        cropped = img.crop(box)
        cache_dir = os.path.join(CACHE_DIR, str(osm_id))
        os.makedirs(cache_dir, exist_ok=True)
        out_path = os.path.join(cache_dir, "crop.jpg")
        cropped.save(out_path)
        return {
            "crop_path": out_path,
            "crop_method": "fallback_center",
            "detected_objects": [],
            "bbox": list(box),
            "crop_confidence": 0.0,
        }
    except Exception as e:
        print(f"[yolo_cropper] _center_crop error: {e}")
        return {
            "crop_path": None,
            "crop_method": "fallback_center",
            "detected_objects": [],
            "bbox": [],
            "crop_confidence": 0.0,
        }


def crop_storefront(image_path: str, osm_id: str = "unknown") -> dict:
    try:
        if not image_path or not os.path.exists(image_path):
            print(f"[yolo_cropper] Image not found: {image_path}")
            return _center_crop(image_path or "", osm_id)

        model = _load_yolo()
        if model is None:
            return _center_crop(image_path, osm_id)

        results = model(image_path, verbose=False)
        detections = []
        best_box = None
        best_area = 0

        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                cls_name = model.names.get(cls_id, str(cls_id))
                area = (x2 - x1) * (y2 - y1)
                detections.append({
                    "class": cls_name,
                    "confidence": round(conf, 3),
                    "bbox": [x1, y1, x2, y2],
                    "area": area,
                })
                if area > best_area:
                    best_area = area
                    best_box = [x1, y1, x2, y2]
                    best_conf = conf

        if not best_box:
            return _center_crop(image_path, osm_id)

        from PIL import Image
        img = Image.open(image_path)
        x1, y1, x2, y2 = [int(v) for v in best_box]
        cropped = img.crop((x1, y1, x2, y2))

        cache_dir = os.path.join(CACHE_DIR, str(osm_id))
        os.makedirs(cache_dir, exist_ok=True)
        out_path = os.path.join(cache_dir, "crop.jpg")
        cropped.save(out_path)

        return {
            "crop_path": out_path,
            "crop_method": "yolo_detection",
            "detected_objects": detections,
            "bbox": best_box,
            "crop_confidence": round(best_conf, 3),
        }

    except Exception as e:
        print(f"[yolo_cropper] crop_storefront error: {e}")
        return _center_crop(image_path, osm_id)


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("Usage: python yolo_cropper.py <image_path>")
    else:
        result = crop_storefront(path, osm_id="test")
        print(f"Method  : {result['crop_method']}")
        print(f"Crop    : {result['crop_path']}")
        print(f"Objects : {len(result['detected_objects'])} detected")
        for obj in result['detected_objects'][:5]:
            print(f"  - {obj['class']} ({obj['confidence']:.2f})")
