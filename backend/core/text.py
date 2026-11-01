"""Text helpers: digit conversion and Arabic normalisation for search."""

from __future__ import annotations

import re

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DIACRITICS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_ARABIC_MAP = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ة": "ه",
        "ى": "ي",
        "ئ": "ي",
        "ؤ": "و",
        "ک": "ك",
        "ی": "ي",
        "گ": "ك",
        "چ": "ج",
        "پ": "ب",
        "ڤ": "ف",
    }
)
_SPACES = re.compile(r"\s+")


def to_latin_digits(value: str) -> str:
    return value.translate(_DIGITS)


def normalize_arabic(value: str) -> str:
    """Lowercase, strip diacritics/tatweel, unify letter variants, collapse spaces."""
    if not value:
        return ""
    value = to_latin_digits(value)
    value = _DIACRITICS.sub("", value)
    value = value.translate(_ARABIC_MAP).lower()
    return _SPACES.sub(" ", value).strip()
