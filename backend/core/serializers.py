from __future__ import annotations

from typing import Any

from django.utils import translation
from rest_framework import serializers

from core.models import localized


def current_lang() -> str:
    lang = translation.get_language() or "ar"
    return "en" if lang.startswith("en") else "ar"


class LocalizedField(serializers.Field):
    """Read-only: returns `<base>_<lang>` with fallback."""

    def __init__(self, base: str, **kwargs: Any):
        self.base = base
        kwargs["source"] = "*"
        kwargs["read_only"] = True
        super().__init__(**kwargs)

    def to_representation(self, value: Any) -> str:
        return localized(value, self.base, current_lang())
