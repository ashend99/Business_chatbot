"""Currency formatting/recognition shared by the bot tools, notifications and
the pricing guardrail, so they always agree on how an amount is written.

Currency is an admin-set, per-tenant setting (TenantAdminSettings.
currency_code) -- nothing here assumes `$`.
"""

import re
from decimal import Decimal

# Prefix used when writing an amount. Anything not listed falls back to the
# ISO code itself ("LKR 2800.00"), which is unambiguous for any currency.
_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "INR": "₹",
    "LKR": "Rs. ",
}


def currency_prefix(currency_code: str) -> str:
    return _SYMBOLS.get(currency_code.upper(), f"{currency_code.upper()} ")


def format_money(amount: Decimal | str | float | int, currency_code: str) -> str:
    return f"{currency_prefix(currency_code)}{Decimal(str(amount)):.2f}"


def price_pattern(currency_code: str) -> re.Pattern[str]:
    """Matches an amount as the tools write it OR with the ISO code instead
    of the symbol (an LLM may write either), e.g. "Rs. 2,800.00" / "LKR 2800".
    Used by the pricing guardrail to find every price a reply states."""
    code = currency_code.upper()
    prefixes = {re.escape(currency_prefix(code).strip()), re.escape(code)}
    alternation = "|".join(sorted(prefixes, key=len, reverse=True))
    return re.compile(rf"(?:{alternation})\s?\d+(?:,\d{{3}})*(?:\.\d{{1,2}})?", re.IGNORECASE)


_NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d{1,2})?")


def extract_amounts(text: str, currency_code: str) -> set[Decimal]:
    """Every amount `text` states in this currency, as Decimals -- compared
    numerically so "Rs.2800" and "Rs. 2,800.00" count as the same price."""
    amounts: set[Decimal] = set()
    for match in price_pattern(currency_code).finditer(text):
        number = _NUMBER.search(match.group(0))
        if number:
            amounts.add(Decimal(number.group(0).replace(",", "")))
    return amounts
