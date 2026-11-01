import json
import time

import pytest

from core.money import Money, format_amount
from core.phone import InvalidPhoneNumber, mask_phone, normalize_phone
from core.telegram import InitDataError, sign_init_data, validate_init_data
from core.text import normalize_arabic

TOKEN = "123456:TEST-token-abcdefghijklmnopqrstuvwxyz"


@pytest.mark.parametrize(
    "raw",
    [
        "07701234567",
        "0770 123 4567",
        "7701234567",
        "+9647701234567",
        "009647701234567",
        "٠٧٧٠١٢٣٤٥٦٧",
        "+964 770 123 4567",
    ],
)
def test_iraqi_phone_normalisation(raw):
    assert normalize_phone(raw) == "+9647701234567"


@pytest.mark.parametrize("raw", ["", "123", "0770123", "abc", "+15555555555x"])
def test_invalid_phones(raw):
    with pytest.raises(InvalidPhoneNumber):
        normalize_phone(raw)


def test_mask_phone():
    assert mask_phone("+9647701234567") == "+964770*****67"


def test_money_and_formatting():
    assert (Money(8000, "IQD") * 2 + Money(2000, "IQD")).amount == 18000
    with pytest.raises(ValueError, match="Currency mismatch"):
        Money(1, "IQD") + Money(1, "USD")
    with pytest.raises(TypeError):
        Money(1.5, "IQD")  # type: ignore[arg-type]
    assert format_amount(12500, "IQD", "ar") == "12,500 د.ع"
    assert format_amount(12500, "IQD", "en") == "IQD 12,500"
    assert format_amount(1250, "USD", "en") == "$12.50"


def test_arabic_normalisation():
    assert normalize_arabic("أَكْلَة إِبراهيم") == normalize_arabic("اكله ابراهيم")
    assert normalize_arabic("مشويّات  ٣") == "مشويات 3"
    assert normalize_arabic("Burger") == "burger"


def _init_data(**over):
    fields = {
        "auth_date": str(int(time.time())),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps({"id": 42, "first_name": "Ali", "language_code": "ar"}),
    }
    fields.update(over)
    return sign_init_data(fields, TOKEN)


def test_init_data_valid():
    user = validate_init_data(_init_data(), TOKEN)
    assert user.id == 42
    assert user.first_name == "Ali"


def test_init_data_wrong_bot():
    with pytest.raises(InitDataError):
        validate_init_data(_init_data(), "999:other-token-abcdefghijklmnopqrstuvwxyz")


def test_init_data_tampered():
    data = _init_data().replace("Ali", "Bob")
    with pytest.raises(InitDataError):
        validate_init_data(data, TOKEN)


def test_init_data_expired():
    old = str(int(time.time()) - 90000)
    with pytest.raises(InitDataError, match="expired"):
        validate_init_data(_init_data(auth_date=old), TOKEN)


def test_init_data_missing_hash():
    with pytest.raises(InitDataError):
        validate_init_data("auth_date=1&user=%7B%7D", TOKEN)
