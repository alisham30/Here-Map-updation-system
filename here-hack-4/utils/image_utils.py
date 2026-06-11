import base64
import io
import os
from PIL import Image, ImageDraw, ImageFont


def encode_image_b64(image_path: str) -> str:
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        print(f"[image_utils] encode_image_b64 error: {e}")
        return ""


def decode_b64_to_image(b64_str: str):
    try:
        img_bytes = base64.b64decode(b64_str)
        return Image.open(io.BytesIO(img_bytes))
    except Exception as e:
        print(f"[image_utils] decode_b64_to_image error: {e}")
        return None


def resize_image(image_path: str, max_size: int = 1024) -> str:
    try:
        img = Image.open(image_path)
        img.thumbnail((max_size, max_size))
        out_path = image_path.replace(".jpg", "_resized.jpg")
        img.save(out_path)
        return out_path
    except Exception as e:
        print(f"[image_utils] resize_image error: {e}")
        return image_path


def add_age_watermark(image_path: str, age_label: str) -> str:
    """Adds semi-transparent banner at bottom showing image age warning."""
    try:
        img = Image.open(image_path).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        banner_height = 30
        draw.rectangle(
            [(0, img.size[1] - banner_height), (img.size[0], img.size[1])],
            fill=(0, 0, 0, 160),
        )
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14
            )
        except Exception:
            font = ImageFont.load_default()
        draw.text(
            (10, img.size[1] - banner_height + 8),
            age_label,
            fill=(255, 255, 255, 230),
            font=font,
        )
        result = Image.alpha_composite(img, overlay).convert("RGB")
        out_path = image_path.replace(".jpg", "_watermarked.jpg")
        result.save(out_path)
        return out_path
    except Exception as e:
        print(f"[image_utils] add_age_watermark error: {e}")
        return image_path
