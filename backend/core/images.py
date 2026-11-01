"""Image upload validation: decode with Pillow, strip metadata, re-encode to WebP."""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError
from uuid6 import uuid7

from core.errors import DomainError

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 4096 * 4096
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@dataclass
class ProcessedImage:
    image: ContentFile
    thumbnail: ContentFile
    width: int
    height: int


def _encode(img: Image.Image, max_side: int) -> tuple[ContentFile, int, int]:
    copy = img.copy()
    copy.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    copy.save(buf, format="WEBP", quality=82, method=4)
    return ContentFile(buf.getvalue(), name=f"{uuid7().hex}.webp"), copy.width, copy.height


def validate_and_process_image(
    upload: Any, max_side: int = 1600, thumb_side: int = 400
) -> ProcessedImage:
    if upload is None:
        raise DomainError("invalid_image", {"image": ["required"]}, 400)
    if upload.size > MAX_BYTES:
        raise DomainError("invalid_image", {"image": ["max 5 MB"]}, 400)
    try:
        upload.seek(0)
        with Image.open(upload) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise DomainError("invalid_image", {"image": ["jpeg, png or webp"]}, 400)
            probe.verify()
        upload.seek(0)
        with Image.open(upload) as img:
            img.load()
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
            main, w, h = _encode(img, max_side)
            thumb, _, _ = _encode(img, thumb_side)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError):
        raise DomainError("invalid_image", status_code=400) from None
    return ProcessedImage(main, thumb, w, h)
