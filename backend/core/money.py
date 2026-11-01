"""Money as integer minor units. Never use floats for amounts."""

from __future__ import annotations

from dataclasses import dataclass

CURRENCY_EXPONENTS: dict[str, int] = {"IQD": 0, "USD": 2}
CURRENCY_SYMBOLS: dict[str, dict[str, str]] = {
    "IQD": {"ar": "د.ع", "en": "IQD"},
    "USD": {"ar": "$", "en": "$"},
}
SUPPORTED_CURRENCIES = tuple(CURRENCY_EXPONENTS)
CURRENCY_CHOICES = [(c, c) for c in SUPPORTED_CURRENCIES]
_ARABIC_DIGITS = str.maketrans("0123456789,.", "٠١٢٣٤٥٦٧٨٩٬٫")


@dataclass(frozen=True, slots=True)
class Money:
    amount: int
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, int) or isinstance(self.amount, bool):
            raise TypeError("Money.amount must be an int of minor units")
        if self.currency not in CURRENCY_EXPONENTS:
            raise ValueError(f"Unsupported currency {self.currency}")

    def _check(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError("Currency mismatch")

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, qty: int) -> Money:
        if not isinstance(qty, int):
            raise TypeError("Can only multiply Money by int")
        return Money(self.amount * qty, self.currency)


def format_amount(amount: int, currency: str, lang: str = "ar", arabic_digits: bool = False) -> str:
    exp = CURRENCY_EXPONENTS[currency]
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if exp:
        major, minor = divmod(amount, 10**exp)
        number = f"{major:,}.{minor:0{exp}d}"
    else:
        number = f"{amount:,}"
    if lang == "ar" and arabic_digits:
        number = number.translate(_ARABIC_DIGITS)
    symbol = CURRENCY_SYMBOLS[currency][lang if lang in ("ar", "en") else "en"]
    if currency == "USD":
        return f"{sign}{symbol}{number}"
    return f"{sign}{number} {symbol}" if lang == "ar" else f"{sign}{symbol} {number}"
