"""The system prompt and the toolset are both derived from
enabled_tool_names, so a tenant's settings change what the agent is told
and what it can do in lockstep."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fakes import effective_settings

from app.models.settings import BotTone, NegotiationMode, OrderConfirmationMode
from app.services.prompt_builder import (
    build_system_prompt,
    enabled_tool_names,
    local_now,
    ordering_active,
)

FIXED_NOW = datetime(2026, 3, 14, 18, 30, tzinfo=ZoneInfo("Asia/Colombo"))


def prompt(**overrides) -> str:
    return build_system_prompt(effective_settings(**overrides), "Test Shop", now=FIXED_NOW)


# ---- enabled_tool_names -----------------------------------------------------


ALL_TOOLS = [
    "search_documents",
    "search_catalog",
    "browse_catalog",
    "create_lead",
    "update_order",
    "confirm_order",
]


def test_all_features_on_gives_every_tool() -> None:
    assert enabled_tool_names(effective_settings()) == ALL_TOOLS


@pytest.mark.parametrize(
    ("overrides", "missing"),
    [
        ({"documents_enabled": False}, {"search_documents"}),
        ({"leads_enabled": False}, {"create_lead"}),
        ({"ordering_enabled": False}, {"update_order", "confirm_order"}),
        # an order is built from catalog variants: no catalog, no cart
        (
            {"catalog_enabled": False},
            {"search_catalog", "browse_catalog", "update_order", "confirm_order"},
        ),
    ],
)
def test_disabled_features_remove_their_tools(overrides: dict, missing: set[str]) -> None:
    names = enabled_tool_names(effective_settings(**overrides))
    assert not missing & set(names)
    assert set(names) == set(ALL_TOOLS) - missing


def test_everything_off_gives_no_tools() -> None:
    settings = effective_settings(
        documents_enabled=False, catalog_enabled=False, leads_enabled=False, ordering_enabled=False
    )
    assert enabled_tool_names(settings) == []
    assert not ordering_active(settings)


def test_local_now_uses_tenant_timezone() -> None:
    assert (
        local_now(effective_settings(timezone="Asia/Colombo")).utcoffset().total_seconds()
        == 5.5 * 3600
    )


# ---- build_system_prompt ----------------------------------------------------


def test_identity_includes_tenant_persona_and_clock() -> None:
    text = prompt(bot_name="Sunny", tone=BotTone.FORMAL, language="Sinhala")
    assert "You are Sunny, the professional and formal chat assistant for Test Shop" in text
    assert "Reply in Sinhala" in text
    assert "Saturday, 14 March 2026, 06:30 PM" in text


def test_prompt_only_describes_enabled_tools() -> None:
    text = prompt(documents_enabled=False, ordering_enabled=False)
    assert "- search_documents:" not in text
    assert "- update_order:" not in text
    assert "- search_catalog:" in text
    assert "You cannot take or place orders in this chat" in text


def test_no_tools_section_when_no_tools() -> None:
    text = prompt(documents_enabled=False, catalog_enabled=False, leads_enabled=False)
    assert "You have these tools:" not in text


def test_bot_vs_human_confirmation_wording() -> None:
    bot = prompt()
    human = prompt(order_confirmation_mode=OrderConfirmationMode.HUMAN)
    assert "finalizes the cart into a placed order" in bot
    assert "submits the cart to the business for confirmation" in human
    assert 'Never say it is "confirmed" or\n"placed"' in human


def test_fulfillment_types_listed() -> None:
    assert "This business offers: delivery and pickup." in prompt()
    assert "This business offers: pickup." in prompt(delivery_enabled=False)


def test_minimum_order_in_tenant_currency() -> None:
    text = prompt(currency_code="LKR", min_order_value=Decimal("1500"))
    assert "The minimum order value is Rs. 1500.00." in text
    assert "Amounts are in LKR." in text


def test_cash_on_delivery_only_when_delivery_offered() -> None:
    assert "cash on delivery" in prompt(cash_on_delivery=True)
    assert "cash on delivery" not in prompt(cash_on_delivery=True, delivery_enabled=False)


@pytest.mark.parametrize(
    ("mode", "phrase"),
    [
        (NegotiationMode.FIXED, "Prices are fixed."),
        (NegotiationMode.ESCALATE, "negotiation_request"),
    ],
)
def test_negotiation_policy(mode: NegotiationMode, phrase: str) -> None:
    assert phrase in prompt(negotiation_mode=mode)


def test_pricing_rule_lists_only_available_price_tools() -> None:
    text = prompt(ordering_enabled=False)
    assert "figures returned by search_catalog/browse_catalog verbatim" in text
    assert "update_order/confirm_order" not in text


def test_no_pricing_rule_without_catalog() -> None:
    assert "relay the exact" not in prompt(catalog_enabled=False)


def test_welcome_message_included_when_set() -> None:
    assert "Hi there! Welcome in." in prompt(welcome_message="Hi there! Welcome in.")
    assert "If the customer opens with just a greeting" not in prompt()


def test_custom_instructions_come_after_rules_with_override_reminder() -> None:
    text = prompt(custom_instructions="Always mention our loyalty card.")
    assert text.index("Rules:") < text.index("Always mention our loyalty card.")
    assert text.rstrip().endswith("those rules always win.")


def test_blank_custom_instructions_are_ignored() -> None:
    assert "Additional instructions from the business" not in prompt(custom_instructions="   ")
