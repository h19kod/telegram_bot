"""Iraqi phone number normalisation to E.164."""

from __future__ import annotations

import phonenumbers
from phonenumbers import PhoneNumberType

from core.text import to_latin_digits


class InvalidPhoneNumber(ValueError):
    pass


def normalize_phone(raw: str, region: str = "IQ", mobile_only: bool = True) -> str:
    """Accept `0770 123 4567`, `7701234567`, `+964…`, `00964…`, Arabic-Indic digits."""
    if not raw:
        raise InvalidPhoneNumber("empty")
    value = to_latin_digits(raw).strip()
    value = "".join(ch for ch in value if ch.isdigit() or ch == "+")
    if value.startswith("00"):
        value = "+" + value[2:]
    if region == "IQ" and not value.startswith("+") and len(value) == 10 and value[0] == "7":
        value = "0" + value
    try:
        parsed = phonenumbers.parse(value, region)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneNumber(str(exc)) from exc
    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneNumber("invalid")
    if mobile_only and phonenumbers.number_type(parsed) not in (
        PhoneNumberType.MOBILE,
        PhoneNumberType.FIXED_LINE_OR_MOBILE,
    ):
        raise InvalidPhoneNumber("not a mobile number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def mask_phone(e164: str | None) -> str:
    if not e164:
        return ""
    if len(e164) < 8:
        return "***"
    return f"{e164[:7]}*****{e164[-2:]}"
