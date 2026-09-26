"""The three post-generation reply guardrails in bot_engine. Each one exists
because the LLM was caught misstating a fact that prompt instructions alone
didn't prevent (see architecture_v0.1.md §4)."""

from fakes import effective_settings
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.models.settings import OrderConfirmationMode
from app.services.bot_engine import (
    _apply_discount_guardrail,
    _apply_order_confirmation_guardrail,
    _apply_pricing_guardrail,
)

USD = effective_settings()
LKR = effective_settings(currency_code="LKR")

CATALOG_OUTPUT = (
    "Classic Latte - Small: $3.50 (in stock) [variant_id: 11111111-1111-1111-1111-111111111111]\n"
    "Classic Latte - Large: $4.50 (in stock) [variant_id: 22222222-2222-2222-2222-222222222222]"
)


def tool(name: str, content: str) -> ToolMessage:
    return ToolMessage(content=content, name=name, tool_call_id=f"call-{name}")


# ---- pricing ----------------------------------------------------------------


def test_pricing_reply_without_prices_passes() -> None:
    assert _apply_pricing_guardrail("We have lattes!", CATALOG_OUTPUT, USD) == "We have lattes!"


def test_pricing_reply_quoting_real_prices_passes() -> None:
    reply = "A small latte is $3.50 and a large is $4.50."
    assert _apply_pricing_guardrail(reply, CATALOG_OUTPUT, USD) == reply


def test_pricing_reply_matching_numerically_passes() -> None:
    reply = "The small one is $3.5."
    assert _apply_pricing_guardrail(reply, CATALOG_OUTPUT, USD) == reply


def test_pricing_invented_price_is_replaced_with_tool_output() -> None:
    result = _apply_pricing_guardrail("A small latte is only $2.99 today!", CATALOG_OUTPUT, USD)
    assert "$2.99" not in result
    assert result.startswith("Here's what I found:")
    assert "Classic Latte - Small: $3.50" in result


def test_pricing_fallback_strips_internal_variant_ids() -> None:
    result = _apply_pricing_guardrail("It's $1.00", CATALOG_OUTPUT, USD)
    assert "variant_id" not in result
    assert "1111" not in result


def test_pricing_without_any_trusted_output_is_left_alone() -> None:
    # no catalog lookup this turn -> nothing to verify against
    assert _apply_pricing_guardrail("It's $9.99", None, USD) == "It's $9.99"


def test_pricing_uses_tenant_currency() -> None:
    catalog = "Cake - Whole: Rs. 2800.00 (in stock)"
    assert _apply_pricing_guardrail("It's LKR 2,800", catalog, LKR) == "It's LKR 2,800"
    assert _apply_pricing_guardrail("It's Rs. 2500", catalog, LKR).startswith(
        "Here's what I found:"
    )


def test_pricing_minimum_order_and_shortfall_are_trusted() -> None:
    settings = effective_settings(min_order_value="10.00")
    reply = "Your cart is $4.50; the minimum order is $10.00, so add $5.50 more."
    assert _apply_pricing_guardrail(reply, CATALOG_OUTPUT, settings) == reply


def test_pricing_shortfall_not_trusted_without_a_minimum() -> None:
    reply = "Your cart is $4.50, add $5.50 more."
    assert _apply_pricing_guardrail(reply, CATALOG_OUTPUT, USD).startswith("Here's what I found:")


# ---- discount ---------------------------------------------------------------


def test_discount_reply_without_a_discount_claim_passes() -> None:
    assert _apply_discount_guardrail("We're open 9 to 5.", []) == "We're open 9 to 5."


def test_discount_invented_percentage_is_replaced() -> None:
    result = _apply_discount_guardrail("Good news, you get 20% off today!", [])
    assert "20%" not in result
    assert "can't offer or confirm discounts" in result


def test_discount_phrased_save_x_percent_is_caught() -> None:
    assert "can't offer" in _apply_discount_guardrail("You can save 15% with this.", [])


def test_discount_backed_by_a_knowledge_base_promo_passes() -> None:
    messages = [tool("search_documents", "Holiday promo: 20 % off all cakes until Friday.")]
    reply = "Yes -- there's 20% off all cakes until Friday."
    assert _apply_discount_guardrail(reply, messages) == reply


def test_discount_with_a_different_percentage_than_the_promo_is_replaced() -> None:
    messages = [tool("search_documents", "Holiday promo: 10% off all cakes.")]
    assert "can't offer" in _apply_discount_guardrail("You get 25% off!", messages)


# ---- order confirmation -----------------------------------------------------


CONFIRMED_CLAIMS = [
    "Your order is confirmed!",
    "Great, your order has been placed.",
    "Your order for 2 Cold Espressos is confirmed.",
    "Order confirmed -- thanks!",
    "I've confirmed your order.",
]


def test_confirmation_reply_without_a_claim_passes() -> None:
    reply = "Shall I place the order?"
    assert _apply_order_confirmation_guardrail(reply, [], USD) == reply


def test_confirmation_claim_with_successful_confirm_order_passes() -> None:
    messages = [tool("confirm_order", "Order confirmed.\n\n1x Classic Latte ...")]
    for claim in CONFIRMED_CLAIMS:
        assert _apply_order_confirmation_guardrail(claim, messages, USD) == claim


def test_confirmation_claim_without_confirm_order_is_replaced() -> None:
    for claim in CONFIRMED_CLAIMS:
        result = _apply_order_confirmation_guardrail(claim, [], USD)
        assert result.startswith("I haven't actually placed an order yet"), claim


def test_confirmation_claim_after_failed_confirm_order_is_replaced_with_cart() -> None:
    messages = [
        tool("update_order", "1x Classic Latte (Small) - $3.50 each = $3.50\nTotal: $3.50"),
        tool("confirm_order", "Can't confirm yet -- still need the customer's Phone Number."),
    ]
    result = _apply_order_confirmation_guardrail("Your order is confirmed!", messages, USD)
    assert result.startswith("Let's just confirm before I place this")
    assert "Total: $3.50" in result


def test_confirmation_human_mode_rewrites_claim_to_submitted() -> None:
    human = effective_settings(order_confirmation_mode=OrderConfirmationMode.HUMAN)
    messages = [tool("confirm_order", "Order submitted for the business to confirm.\n\n...")]
    result = _apply_order_confirmation_guardrail("Your order is confirmed!", messages, human)
    assert result == "Your order has been submitted -- the business will confirm it shortly."


def test_confirmation_human_mode_never_accepts_a_bot_mode_success_string() -> None:
    human = effective_settings(order_confirmation_mode=OrderConfirmationMode.HUMAN)
    messages = [tool("confirm_order", "Order confirmed.\n\n...")]
    result = _apply_order_confirmation_guardrail("Your order is placed.", messages, human)
    assert result.startswith("I haven't actually placed an order yet")


def test_confirmation_uses_most_recent_confirm_order_result() -> None:
    messages = [
        tool("confirm_order", "Order confirmed.\n\n..."),
        HumanMessage(content="add another"),
        AIMessage(content=""),
        tool(
            "confirm_order", "There's no cart to confirm yet -- add items with update_order first."
        ),
    ]
    result = _apply_order_confirmation_guardrail("Your order is confirmed!", messages, USD)
    assert result.startswith("I haven't actually placed an order yet")
