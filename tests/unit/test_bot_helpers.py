"""Pure helpers in bot_engine / bot_tools: message-history slicing, action
extraction, and the customer-facing text formatters."""

import json
import uuid
from decimal import Decimal
from types import SimpleNamespace

from fakes import effective_settings
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.models.catalog import StockStatus
from app.models.conversations import ConversationChannel
from app.services.bot_engine import (
    _extract_lead_actions,
    _last_ai_text,
    _last_tool_output,
    _this_turn_messages,
)
from app.services.bot_tools import (
    _format_catalog_grouped_by_category,
    _format_fulfillment,
    _format_order_summary,
    _format_variant_line,
    build_tools,
)

# ---- bot_engine helpers -----------------------------------------------------


def lead_tool(lead_id: uuid.UUID) -> ToolMessage:
    return ToolMessage(
        content=json.dumps({"lead_id": str(lead_id), "status": "new"}),
        name="create_lead",
        tool_call_id="c",
    )


def test_this_turn_starts_at_last_human_message() -> None:
    old, new = HumanMessage(content="hi"), HumanMessage(content="and now?")
    messages = [old, AIMessage(content="hello"), new, AIMessage(content="sure")]
    assert _this_turn_messages(messages) == [new, messages[-1]]


def test_this_turn_without_human_message_returns_everything() -> None:
    messages = [AIMessage(content="x")]
    assert _this_turn_messages(messages) == messages


def test_extract_lead_actions_skips_malformed_tool_output() -> None:
    lead_id = uuid.uuid4()
    messages = [
        lead_tool(lead_id),
        ToolMessage(content="not json", name="create_lead", tool_call_id="c2"),
        ToolMessage(content=json.dumps({"no": "id"}), name="create_lead", tool_call_id="c3"),
        ToolMessage(content=json.dumps({"lead_id": "x"}), name="search_catalog", tool_call_id="c4"),
    ]
    actions = _extract_lead_actions(messages)
    assert [(a.type, a.lead_id) for a in actions] == [("lead_created", lead_id)]


def test_last_ai_text_skips_empty_tool_calling_messages() -> None:
    messages = [AIMessage(content="first"), AIMessage(content="", tool_calls=[])]
    assert _last_ai_text(messages) == "first"
    assert _last_ai_text([]).startswith("Sorry")


def test_last_tool_output_returns_most_recent_by_name() -> None:
    messages = [
        ToolMessage(content="old", name="search_catalog", tool_call_id="1"),
        ToolMessage(content="other", name="browse_catalog", tool_call_id="2"),
        ToolMessage(content="new", name="search_catalog", tool_call_id="3"),
    ]
    assert _last_tool_output(messages, "search_catalog") == "new"
    assert _last_tool_output(messages, "confirm_order") is None


# ---- bot_tools formatters ---------------------------------------------------


def variant(**kw):
    defaults = {
        "id": uuid.uuid4(),
        "name": "Large",
        "price": Decimal("4.50"),
        "stock_status": StockStatus.IN_STOCK,
        "stock_qty": None,
        "stock_message": None,
    }
    return SimpleNamespace(**{**defaults, **kw})


def test_variant_line_stock_states() -> None:
    product = SimpleNamespace(name="Latte")
    assert "(in stock)" in _format_variant_line(variant(), product, "USD")
    assert "(in stock, 3 available)" in _format_variant_line(variant(stock_qty=3), product, "USD")
    assert "(in stock)" in _format_variant_line(
        variant(stock_status=StockStatus.UNLIMITED, stock_qty=3), product, "USD"
    )
    assert "(out of stock)" in _format_variant_line(
        variant(stock_status=StockStatus.OUT_OF_STOCK), product, "USD"
    )
    assert "(back Friday)" in _format_variant_line(
        variant(stock_status=StockStatus.OUT_OF_STOCK, stock_message="back Friday"), product, "USD"
    )


def test_variant_line_includes_price_and_variant_id() -> None:
    v = variant()
    line = _format_variant_line(v, SimpleNamespace(name="Latte"), "LKR")
    assert line.startswith("Latte - Large: Rs. 4.50")
    assert line.endswith(f"[variant_id: {v.id}]")


def test_catalog_grouped_by_category() -> None:
    product = SimpleNamespace(name="Latte")
    rows = [
        (variant(), product, SimpleNamespace(name="Hot Drinks")),
        (variant(name="Small"), product, None),
    ]
    text = _format_catalog_grouped_by_category(rows, "USD")
    assert text.startswith("Hot Drinks:\nLatte - Large")
    assert "\n\nOther:\nLatte - Small" in text


def test_fulfillment_is_rendered_as_labels_not_a_dict() -> None:
    text = _format_fulfillment(
        {"type": "delivery", "address": "12 Main St", "needed_by": "Friday", "gate_code": "42"}
    )
    assert text == "Type: delivery, Address: 12 Main St, Needed by: Friday, Gate_Code: 42"
    assert "{" not in text


def test_order_summary() -> None:
    order = SimpleNamespace(
        items=[
            {
                "quantity": 2,
                "product_name": "Latte",
                "variant_label": "Large",
                "unit_price": "4.50",
                "line_total": "9.00",
            },
            {
                "quantity": 1,
                "product_name": "Tea",
                "variant_label": None,
                "unit_price": "2.75",
                "line_total": "2.75",
            },
        ],
        total=Decimal("11.75"),
        fulfillment={"type": "pickup", "time": "5pm"},
        notes="no sugar",
    )
    assert _format_order_summary(order, "USD") == (
        "2x Latte (Large) - $4.50 each = $9.00\n"
        "1x Tea - $2.75 each = $2.75\n"
        "Total: $11.75\n"
        "Fulfillment: Type: pickup, Time: 5pm\n"
        "Notes: no sugar"
    )


# ---- build_tools ------------------------------------------------------------


def test_build_tools_matches_enabled_tool_names() -> None:
    tools = build_tools(
        uuid.uuid4(),
        uuid.uuid4(),
        ConversationChannel.WEBSITE_WIDGET,
        effective_settings(leads_enabled=False),
    )
    assert [t.name for t in tools] == [
        "search_documents",
        "search_catalog",
        "browse_catalog",
        "update_order",
        "confirm_order",
    ]
    assert all(t.description for t in tools)


async def test_update_order_tool_rejects_unoffered_fulfillment_without_touching_db() -> None:
    settings = effective_settings(delivery_enabled=False)
    tools = {
        t.name: t
        for t in build_tools(
            uuid.uuid4(), uuid.uuid4(), ConversationChannel.WEBSITE_WIDGET, settings
        )
    }
    result = await tools["update_order"].ainvoke(
        {
            "items": [{"variant_id": str(uuid.uuid4()), "quantity": 1}],
            "fulfillment": {"type": "Delivery"},
        }
    )
    assert result.startswith("Not saved: this business does not offer delivery. Available: pickup.")
