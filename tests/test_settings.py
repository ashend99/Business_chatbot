"""Pure-logic tests for the settings layer: money formatting/recognition, the
prompt builder, tool filtering, and the currency-aware guardrails. None of
these touch the database or an LLM."""

import uuid
from decimal import Decimal

from langchain_core.messages import ToolMessage

from app.models.settings import BotTone, NegotiationMode, OrderConfirmationMode
from app.services.bot_engine import _apply_order_confirmation_guardrail, _apply_pricing_guardrail
from app.services.money import extract_amounts, format_money
from app.services.prompt_builder import build_system_prompt, enabled_tool_names
from app.services.settings_resolver import EffectiveSettings


def make_settings(**overrides) -> EffectiveSettings:
    base = dict(
        tenant_id=uuid.uuid4(),
        currency_code="LKR",
        allowed_channels=("website_widget",),
        llm_model="gpt-4o-mini",
        monthly_message_limit=None,
        max_documents=None,
        bot_enabled=True,
        ordering_enabled=True,
        catalog_enabled=True,
        documents_enabled=True,
        leads_enabled=True,
        timezone="Asia/Colombo",
        bot_name=None,
        tone=BotTone.FRIENDLY,
        language="English",
        welcome_message=None,
        fallback_message=None,
        custom_instructions=None,
        delivery_enabled=True,
        pickup_enabled=True,
        cash_on_delivery=False,
        min_order_value=None,
        negotiation_mode=NegotiationMode.FIXED,
        order_confirmation_mode=OrderConfirmationMode.BOT,
        notify_emails=(),
        notify_new_lead=True,
        notify_new_order=True,
    )
    base.update(overrides)
    return EffectiveSettings(**base)


# ---- money ------------------------------------------------------------------


def test_format_money_uses_tenant_currency():
    assert format_money("2800", "LKR") == "Rs. 2800.00"
    assert format_money(Decimal("5"), "USD") == "$5.00"
    assert format_money(10, "JPY") == "JPY 10.00"  # unknown symbol -> ISO code


def test_extract_amounts_is_numeric_and_currency_aware():
    text = "Large is Rs.2,800 and small is LKR 2000.00, not $5"
    assert extract_amounts(text, "LKR") == {Decimal("2800"), Decimal("2000.00")}
    assert extract_amounts("It is $5.00", "USD") == {Decimal("5.00")}


# ---- tools / prompt ---------------------------------------------------------


def test_enabled_tools_follow_toggles():
    assert enabled_tool_names(make_settings()) == [
        "search_documents",
        "search_catalog",
        "browse_catalog",
        "create_lead",
        "update_order",
        "confirm_order",
    ]
    no_order = enabled_tool_names(make_settings(ordering_enabled=False))
    assert "update_order" not in no_order and "confirm_order" not in no_order
    # an order is built from catalog variants -- no catalog, no cart
    assert "update_order" not in enabled_tool_names(make_settings(catalog_enabled=False))
    assert enabled_tool_names(make_settings(documents_enabled=False, leads_enabled=False))[0] == "search_catalog"


def test_prompt_only_describes_available_tools_and_rules():
    prompt = build_system_prompt(make_settings(ordering_enabled=False, catalog_enabled=False), "Acme")
    assert "search_catalog" not in prompt and "update_order" not in prompt
    assert "cannot take or place orders" in prompt


def test_prompt_reflects_settings():
    prompt = build_system_prompt(
        make_settings(
            bot_name="Dula",
            tone=BotTone.FORMAL,
            pickup_enabled=False,
            cash_on_delivery=True,
            min_order_value=Decimal("3000"),
            order_confirmation_mode=OrderConfirmationMode.HUMAN,
            negotiation_mode=NegotiationMode.ESCALATE,
            custom_instructions="Closed on Sundays.",
        ),
        "Acme",
    )
    assert "You are Dula, the professional and formal chat assistant for Acme" in prompt
    assert "This business offers: delivery." in prompt
    assert "Rs. 3000.00" in prompt
    assert "cash on delivery" in prompt.lower()
    assert "SUBMITS" in prompt
    assert "negotiation_request" in prompt
    # custom instructions come last, after the non-negotiable rules
    assert prompt.index("Rules:") < prompt.index("Closed on Sundays.")


# ---- guardrails -------------------------------------------------------------


def test_pricing_guardrail_currency_and_minimum_order():
    settings = make_settings(min_order_value=Decimal("3000"))
    tool_out = "Chicken Pizza - Small: Rs. 2000.00 (in stock) [variant_id: abc]"
    assert _apply_pricing_guardrail("It is Rs.2000, ok?", tool_out, settings) == "It is Rs.2000, ok?"
    # the minimum (from the prompt) and the shortfall are legitimately quotable
    assert "3000" in _apply_pricing_guardrail("Min is Rs. 3000, add Rs. 1000 more", tool_out, settings)
    assert "Here's what I found" in _apply_pricing_guardrail("It is Rs. 1999", tool_out, settings)
    # internal ids never leak into the fallback
    assert "variant_id" not in _apply_pricing_guardrail("It is Rs. 1999", tool_out, settings)


def test_confirmation_guardrail_bot_vs_human_mode():
    confirmed = [ToolMessage(content="Order confirmed.\n\n1x A", name="confirm_order", tool_call_id="1")]
    submitted = [ToolMessage(content="Order submitted for the business to confirm.\n\n1x A", name="confirm_order", tool_call_id="1")]
    claim = "Your order has been confirmed!"

    assert _apply_order_confirmation_guardrail(claim, confirmed, make_settings()) == claim
    assert "haven't actually placed" in _apply_order_confirmation_guardrail(claim, [], make_settings())

    human = make_settings(order_confirmation_mode=OrderConfirmationMode.HUMAN)
    # in human mode nothing is "confirmed" yet, even after a successful submit
    assert "submitted" in _apply_order_confirmation_guardrail(claim, submitted, human)
    assert _apply_order_confirmation_guardrail("Submitted, the business will confirm.", submitted, human) == (
        "Submitted, the business will confirm."
    )


def test_effective_recipients_fall_back_to_tenant_email():
    assert make_settings().recipients("owner@x.com") == ["owner@x.com"]
    assert make_settings(notify_emails=("a@x.com", "b@x.com")).recipients("owner@x.com") == ["a@x.com", "b@x.com"]
    assert make_settings().recipients(None) == []


# ---- resolver: admin ceiling AND tenant choice --------------------------------


def test_resolver_effective_toggle_is_admin_and_tenant(monkeypatch):
    import asyncio

    from app.models.settings import TenantAdminSettings, TenantSettings
    from app.services import settings_resolver

    tenant_id = uuid.uuid4()
    admin = TenantAdminSettings(
        tenant_id=tenant_id, currency_code="lkr", ordering_allowed=False, catalog_allowed=True,
        documents_allowed=True, leads_allowed=True, allowed_channels=["website_widget"],
    )
    tenant = TenantSettings(
        tenant_id=tenant_id, timezone="Asia/Colombo", bot_enabled=True, ordering_enabled=True,
        catalog_enabled=False, documents_enabled=True, leads_enabled=True,
    )

    async def fake_admin(session, tid):
        return admin

    async def fake_tenant(session, tid):
        return tenant

    monkeypatch.setattr(settings_resolver.settings_read, "get_admin_settings", fake_admin)
    monkeypatch.setattr(settings_resolver.settings_read, "get_tenant_settings", fake_tenant)

    effective = asyncio.run(settings_resolver._load(None, tenant_id))
    assert effective.ordering_enabled is False  # tenant on, admin never granted
    assert effective.catalog_enabled is False  # admin granted, tenant switched off
    assert effective.documents_enabled is True
    assert effective.currency_code == "LKR"  # normalized, admin-owned


# ---- discount + widened confirmation-claim guardrails -----------------------------


def test_discount_guardrail_blocks_unsupported_percent_but_allows_document_promo():
    from app.services.bot_engine import _apply_discount_guardrail

    claim = "Good news, everyone gets a 20% discount on every order!"
    assert "can't offer or confirm discounts" in _apply_discount_guardrail(claim, [])
    promo = [ToolMessage(content="Weekend promo: 20% off all coffee.", name="search_documents", tool_call_id="1")]
    assert _apply_discount_guardrail(claim, promo) == claim
    # different percentage than the published promo is still invented
    assert "can't offer or confirm discounts" in _apply_discount_guardrail("Take 50% off today!", promo)
    assert _apply_discount_guardrail("Prices are fixed, sorry.", []) == "Prices are fixed, sorry."


def test_confirmation_claim_pattern_catches_words_between():
    from app.services.bot_engine import _ORDER_CONFIRMED_CLAIM_PATTERN as pattern

    assert pattern.search("Your order for 2 Cold Espressos is confirmed for pickup")
    assert pattern.search("Your order has been placed!")
    assert pattern.search("Order confirmed.")
    assert not pattern.search("I'll confirm your order once I have your phone number")
    assert not pattern.search("Shall I go ahead and confirm it?")
