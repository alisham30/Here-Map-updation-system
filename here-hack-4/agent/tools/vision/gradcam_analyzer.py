import os
import base64
import io

CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'imagery_cache')

_ZONE_NAMES = [
    "top-left", "top-center", "top-right",
    "middle-left", "center", "middle-right",
    "bottom-left", "bottom-center", "bottom-right",
]

_NULL_RESULT = {
    "gradcam_overlay_b64": None,
    "gradcam_pure_b64": None,
    "gradcam_overlay_path": None,
    "attention_reliable": False,
    "attention_focus_zone": "unknown",
    "activation_map": [],
    "error": None,
}


def _encode_pil_b64(pil_img) -> str:
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def run_gradcam(image_path: str, osm_id: str = "unknown") -> dict:
    try:
        if not image_path or not os.path.exists(image_path):
            result = dict(_NULL_RESULT)
            result["error"] = f"Image not found: {image_path}"
            return result

        # ── Imports (all optional — fail gracefully) ──────────────────────
        try:
            import torch
            import numpy as np
            from PIL import Image
            import timm  # type: ignore
            from pytorch_grad_cam import GradCAM  # type: ignore
            from pytorch_grad_cam.utils.image import show_cam_on_image  # type: ignore
        except ImportError as e:
            result = dict(_NULL_RESULT)
            result["error"] = f"Missing dependency: {e}"
            print(f"[gradcam_analyzer] {result['error']}")
            return result

        # ── Load model (EfficientNet-B0, pretrained, no custom head) ──────
        model = timm.create_model("efficientnet_b0", pretrained=True)
        model.eval()

        # ── Preprocess ────────────────────────────────────────────────────
        from torchvision import transforms  # type: ignore
        preprocess = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ])
        orig_img = Image.open(image_path).convert("RGB").resize((224, 224))
        input_tensor = preprocess(Image.open(image_path).convert("RGB")).unsqueeze(0)

        # ── Find last conv layer ───────────────────────────────────────────
        target_layer = None
        for module in model.modules():
            if isinstance(module, torch.nn.Conv2d):
                target_layer = module
        if target_layer is None:
            raise RuntimeError("Could not find conv layer in EfficientNet-B0")

        # ── GradCAM ───────────────────────────────────────────────────────
        cam = GradCAM(model=model, target_layers=[target_layer])
        grayscale_cam = cam(input_tensor=input_tensor, targets=None)[0]  # H×W array

        # Overlay
        orig_np = np.array(orig_img, dtype=np.float32) / 255.0
        overlay_np = show_cam_on_image(orig_np, grayscale_cam, use_rgb=True, image_weight=0.6)

        # Pure heatmap (jet colormap)
        import matplotlib  # type: ignore
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(2.24, 2.24), dpi=100)
        ax.imshow(grayscale_cam, cmap="jet", vmin=0, vmax=1)
        ax.axis("off")
        buf = io.BytesIO()
        plt.savefig(buf, format="jpeg", bbox_inches="tight", pad_inches=0)
        plt.close(fig)
        buf.seek(0)
        from PIL import Image as PILImage
        pure_img = PILImage.open(buf).convert("RGB")
        gradcam_pure_b64 = _encode_pil_b64(pure_img)

        # Overlay PIL image
        overlay_pil = PILImage.fromarray(overlay_np)
        gradcam_overlay_b64 = _encode_pil_b64(overlay_pil)

        # Save overlay to disk
        cache_dir = os.path.join(CACHE_DIR, str(osm_id))
        os.makedirs(cache_dir, exist_ok=True)
        overlay_path = os.path.join(cache_dir, "gradcam_overlay.jpg")
        overlay_pil.save(overlay_path)

        # ── Attention reliability ─────────────────────────────────────────
        threshold = float(np.percentile(grayscale_cam, 80))
        high_mask = grayscale_cam >= threshold

        h, w = grayscale_cam.shape
        center_mask = np.zeros_like(high_mask, dtype=bool)
        cy1, cy2 = int(h * 0.2), int(h * 0.8)
        cx1, cx2 = int(w * 0.2), int(w * 0.8)
        center_mask[cy1:cy2, cx1:cx2] = True

        overlap = (high_mask & center_mask).sum()
        total_high = high_mask.sum()
        attention_reliable = bool(total_high > 0 and (overlap / total_high) >= 0.15)

        # ── Zone with highest mean activation (3×3 grid) ──────────────────
        zone_scores = []
        rows = np.array_split(grayscale_cam, 3, axis=0)
        for row_idx, row_strip in enumerate(rows):
            cols = np.array_split(row_strip, 3, axis=1)
            for col_idx, zone in enumerate(cols):
                zone_scores.append(float(zone.mean()))
        best_zone_idx = int(np.argmax(zone_scores))
        attention_focus_zone = _ZONE_NAMES[best_zone_idx]

        return {
            "gradcam_overlay_b64": gradcam_overlay_b64,
            "gradcam_pure_b64": gradcam_pure_b64,
            "gradcam_overlay_path": overlay_path,
            "attention_reliable": attention_reliable,
            "attention_focus_zone": attention_focus_zone,
            "activation_map": grayscale_cam.flatten().tolist(),
            "error": None,
        }

    except Exception as e:
        print(f"[gradcam_analyzer] run_gradcam error: {e}")
        result = dict(_NULL_RESULT)
        result["error"] = str(e)
        return result


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("Usage: python gradcam_analyzer.py <image_path>")
    else:
        r = run_gradcam(path, osm_id="test")
        print(f"Attention reliable : {r['attention_reliable']}")
        print(f"Focus zone         : {r['attention_focus_zone']}")
        print(f"Overlay saved      : {r['gradcam_overlay_path']}")
        print(f"Error              : {r['error']}")
        print(f"Has overlay b64    : {bool(r['gradcam_overlay_b64'])}")
