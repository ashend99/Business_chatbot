from decimal import Decimal

import pytest

from app.services.money import currency_prefix, extract_amounts, format_money


@pytest.mark.parametrize(
    ("code", "prefix"),
    [
        ("USD", "$"),
        ("usd", "$"),
        ("EUR", "€"),
        ("GBP", "£"),
        ("INR", "₹"),
        ("LKR", "Rs. "),
        ("JPY", "JPY "),
    ],
)
def test_currency_prefix(code: str, prefix: str) -> None:
    assert currency_prefix(code) == prefix


@pytest.mark.parametrize(
    ("amount", "code", "expected"),
    [
        (Decimal("3.5"), "USD", "$3.50"),
        ("2800", "LKR", "Rs. 2800.00"),
        (12, "EUR", "€12.00"),
        (0.1, "USD", "$0.10"),
        (Decimal("1000"), "AUD", "AUD 1000.00"),
    ],
)
def test_format_money(amount, code: str, expected: str) -> None:
    assert format_money(amount, code) == expected


def test_extract_amounts_reads_symbol_and_iso_code_forms() -> None:
    text = "Small is Rs. 2,800.00, large LKR 3200 and the combo Rs.4500."
    assert extract_amounts(text, "LKR") == {Decimal("2800.00"), Decimal("3200"), Decimal("4500")}


def test_extract_amounts_compares_numerically() -> None:
    assert extract_amounts("$4.5", "USD") == extract_amounts("$4.50", "USD")


def test_extract_amounts_ignores_other_currencies_and_bare_numbers() -> None:
    assert extract_amounts("Table for 4 at 7pm, €12.00 per head", "USD") == set()


def test_extract_amounts_round_trips_format_money() -> None:
    for code in ("USD", "EUR", "GBP", "INR", "LKR", "CHF"):
        assert extract_amounts(f"Total: {format_money('1234.5', code)}", code) == {
            Decimal("1234.50")
        }


def test_extract_amounts_is_case_insensitive_for_codes() -> None:
    assert extract_amounts("that's usd 10", "USD") == {Decimal("10")}
