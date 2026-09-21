"""Bot agent orchestrator (Phase 4).

A LangGraph ReAct agent (`langgraph.prebuilt.create_react_agent`) over the
Documents/Catalog/Leads tools in `bot_tools.py`. Conversation state lives in
two places that serve different purposes:

- LangGraph's checkpointer (Postgres-backed, see main.py's lifespan) holds
  the agent's own turn-by-turn working memory, keyed by thread_id =
  conversation_id. This is what gives the agent context across messages.
- `conversations`/`messages` (repos/conversations.py) is the human-readable
  business record -- source of truth for the future Inbox dashboard, not
  read back into the agent's own context.
"""

import json
import logging
import re
import uuid

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.prebuilt import create_react_agent
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.conversations import ConversationChannel, MessageRole
from app.repos import conversations as conversations_repo
from app.repos import tenants as tenants_repo
from app.schemas.conversations import BotMessageAction, BotMessageResponse
from app.services.bot_tools import build_tools
from app.services.money import extract_amounts
from app.services.prompt_builder import build_system_prompt
from app.services.settings_resolver import EffectiveSettings, get_effective_settings
from common import PROJECT_CONFIG

logger = logging.getLogger(__name__)

_agent_config = PROJECT_CONFIG.get("agent", {})
DEFAULT_FALLBACK_REPLY = _agent_config.get("prompt").get("default_fallback")

# strips "[variant_id: <uuid>]" -- present in search_catalog/browse_catalog's
# tool output so the agent can reference an item in update_order/create_lead,
# but never meant for a customer to actually see
_VARIANT_ID_SUFFIX_PATTERN = re.compile(r"\s*\[variant_id:[^\]]*\]")

# used by the order-confirmation guardrail below -- catches the LLM telling
# the customer their order is confirmed/placed in prose without actually
# having called confirm_order
_ORDER_CONFIRMED_CLAIM_PATTERN = re.compile(
    # "your order is confirmed", "order has been placed", and also the version
    # with words in between: "Your order for 2 Cold Espressos is confirmed"
    r"\border\b[^.!?\n]{0,60}?\b(?:is|has been|was)\s+(?:now\s+)?(?:confirmed|placed)\b"
    r"|\border (?:confirmed|placed)\b"
    r"|\b(?:confirmed|placed) your order\b",
    re.IGNORECASE,
)

# A percentage discount/saving claim. No catalog item carries a discount, so
# the only legitimate source is a knowledge-base document (e.g. a seasonal
# promo) -- see _apply_discount_guardrail. Catches a tenant's custom
# instructions talking the model into promising one.
_DISCOUNT_CLAIM_PATTERN = re.compile(
    r"\d{1,3}(?:\.\d+)?\s?%[^.!?\n]{0,40}?\b(?:discount|off|savings?|reduction)\b"
    r"|\b(?:discount|off|save|savings?)\b[^.!?\n]{0,40}?\d{1,3}(?:\.\d+)?\s?%",
    re.IGNORECASE,
)
_PERCENT_PATTERN = re.compile(r"\d{1,3}(?:\.\d+)?\s?%")

# one ChatOpenAI per model name -- the model is an admin-set per-tenant
# setting (TenantAdminSettings.llm_model), so it can differ between requests
_models: dict[str, ChatOpenAI] = {}


def _get_model(model_name: str) -> ChatOpenAI:
    if model_name not in _models:
        _models[model_name] = ChatOpenAI(model=model_name, api_key=settings.openai_api_key)
    return _models[model_name]


async def handle_message(
    session: AsyncSession,
    checkpointer: BaseCheckpointSaver,
    tenant_id: uuid.UUID,
    channel_type: ConversationChannel,
    external_user_id: str,
    text: str,
) -> BotMessageResponse:
    tenant = await tenants_repo.get_tenant_by_id(session, tenant_id)
    conversation = await conversations_repo.get_or_create_conversation(session, tenant_id, channel_type, external_user_id)
    await conversations_repo.add_message(session, tenant_id, conversation.id, MessageRole.USER, text)
    # commit now so the user's message survives in the transcript even if
    # generation below fails (LLM/API error) -- the failure means the bot
    # never replied, not that the user never spoke
    await session.commit()

    effective = await get_effective_settings(tenant_id, session)
    if not effective.bot_enabled:
        # human takeover: the customer's message is stored above (so staff
        # see it in Conversations) but the bot stays silent. An empty reply
        # is the contract for "send nothing" to the channel adapter.
        await conversations_repo.touch_conversation(session, conversation)
        await session.commit()
        return BotMessageResponse(reply="", conversation_id=conversation.id, actions=[])

    tools = build_tools(tenant_id, conversation.id, channel_type, effective)
    system_prompt = build_system_prompt(effective, tenant.name if tenant else "this business")
    agent = create_react_agent(
        _get_model(effective.llm_model), tools, checkpointer=checkpointer, prompt=system_prompt
    )

    actions: list[BotMessageAction] = []
    try:
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=text)]},
            config={"configurable": {"thread_id": str(conversation.id)}},
        )
        messages = result["messages"]
        reply = _last_ai_text(messages)
        # `messages` is the whole thread's accumulated history (loaded from
        # the checkpointer), not just this call's activity -- actions must
        # only reflect what happened THIS turn, or every reply would keep
        # re-reporting the same lead_created from turns ago
        actions = _extract_lead_actions(_this_turn_messages(messages))
        # update_order/confirm_order also state trustworthy prices (unit
        # prices, cart total) computed server-side the same way
        # search_catalog's are -- combine whichever of the three ran this
        # turn so the guardrail below checks the reply against all of them.
        # only outputs that actually state a price count: a "No matching
        # products..." line adds nothing to verify and would just clutter the
        # customer-facing fallback text
        trusted_outputs = [
            out
            for out in (
                _last_tool_output(messages, "search_catalog"),
                _last_tool_output(messages, "browse_catalog"),
                _last_tool_output(messages, "update_order"),
                _last_tool_output(messages, "confirm_order"),
            )
            if out is not None and extract_amounts(out, effective.currency_code)
        ]
        combined_trusted_output = "\n".join(trusted_outputs) if trusted_outputs else None
        reply = _apply_pricing_guardrail(reply, combined_trusted_output, effective)
        reply = _apply_discount_guardrail(reply, messages)
        reply = _apply_order_confirmation_guardrail(reply, messages, effective)
    except Exception:
        # a bot endpoint failing to generate should still reply with
        # *something* a channel adapter can forward, not a raw 500 -- but
        # the failure may have left this session's transaction in a broken
        # state (e.g. a tool-call error), so roll back before reusing it
        # below, or persisting the fallback message fails too
        logger.exception("agent run failed for conversation %s", conversation.id)
        await session.rollback()
        reply = effective.fallback_message or DEFAULT_FALLBACK_REPLY

    await conversations_repo.add_message(session, tenant_id, conversation.id, MessageRole.ASSISTANT, reply)
    await conversations_repo.touch_conversation(session, conversation)
    await session.commit()

    return BotMessageResponse(reply=reply, conversation_id=conversation.id, actions=actions)


def _last_ai_text(messages: list) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content:
            return message.content if isinstance(message.content, str) else str(message.content)
    return "Sorry, I wasn't able to come up with a reply."


def _last_tool_output(messages: list, tool_name: str) -> str | None:
    for message in reversed(messages):
        if isinstance(message, ToolMessage) and message.name == tool_name:
            return message.content if isinstance(message.content, str) else str(message.content)
    return None


def _this_turn_messages(messages: list) -> list:
    """`messages` (from agent.ainvoke's result) is the whole thread's
    accumulated history loaded from the checkpointer, with this turn's new
    messages appended at the end -- not just what happened in this call.
    Exactly one new HumanMessage is added per turn, so everything from the
    last one onward is this turn's own activity. Used for `actions` only --
    the guardrails below deliberately keep using the full `messages`, since
    e.g. "was this order ever confirmed" or "what prices have been quoted"
    should hold across the whole conversation, not reset every turn."""
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return messages[i:]
    return messages


def _extract_lead_actions(messages: list) -> list[BotMessageAction]:
    actions = []
    for message in messages:
        if not (isinstance(message, ToolMessage) and message.name == "create_lead"):
            continue
        if not isinstance(message.content, str):
            continue
        try:
            data = json.loads(message.content)
            actions.append(BotMessageAction(type="lead_created", lead_id=uuid.UUID(data["lead_id"])))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            continue
    return actions


def _apply_pricing_guardrail(reply: str, catalog_output: str | None, settings: EffectiveSettings) -> str:
    """If the reply states a price that doesn't appear in this turn's
    trusted tool output, the agent likely paraphrased/invented it -- discard
    the LLM's prose and fall back to the tool's own text instead. Amounts are
    recognized in the tenant's currency and compared numerically.

    Besides the tools' own figures, the tenant's minimum order value (it's in
    the system prompt, so the agent legitimately quotes it) and the shortfall
    of any trusted amount below it are also trusted."""
    currency = settings.currency_code
    reply_prices = extract_amounts(reply, currency)
    if not reply_prices:
        return reply
    if catalog_output is None:
        return reply  # no catalog lookup this turn, nothing to verify against

    trusted = extract_amounts(catalog_output, currency)
    minimum = settings.min_order_value
    if minimum:
        trusted |= {minimum} | {minimum - amount for amount in trusted if amount < minimum}
    if reply_prices <= trusted:
        return reply
    # the raw tool output is otherwise trustworthy, but it carries internal
    # [variant_id: ...] tags for the agent's own reference (see bot_tools.py)
    # that a customer should never see verbatim
    customer_safe_output = _VARIANT_ID_SUFFIX_PATTERN.sub("", catalog_output)
    return f"Here's what I found:\n\n{customer_safe_output}"


def _apply_discount_guardrail(reply: str, messages: list) -> str:
    """A reply promising a percentage discount is replaced unless that exact
    percentage appears in a knowledge-base result this thread (a real,
    published promo). Prices are fixed in the catalog, so an unsupported
    "20% off" is invented -- typically the model obeying a tenant's custom
    instructions over the pricing rules."""
    if not _DISCOUNT_CLAIM_PATTERN.search(reply):
        return reply
    docs = (_last_tool_output(messages, "search_documents") or "").replace(" ", "")
    percents = [p.replace(" ", "") for p in _PERCENT_PATTERN.findall(reply)]
    if percents and all(p in docs for p in percents):
        return reply
    return (
        "Our prices are as listed, and I can't offer or confirm discounts myself. "
        "If you'd like, I can pass a discount request along to the business."
    )


def _apply_order_confirmation_guardrail(reply: str, messages: list, settings: EffectiveSettings) -> str:
    """If the reply tells the customer their order is confirmed/placed but
    confirm_order was never actually called (or was called and failed --
    e.g. an empty cart), the LLM said so without it being true. Placing an
    order is the one irreversible-feeling claim in this whole flow, so it
    gets the same treatment as the pricing guardrail: never trust the LLM's
    own account of what happened, check the tool's actual result.

    In human-confirmation mode a successful confirm_order only *submits* the
    order for the business to confirm, so a reply claiming it is
    confirmed/placed is never true and is replaced with the accurate
    "submitted" message."""
    if not _ORDER_CONFIRMED_CLAIM_PATTERN.search(reply):
        return reply

    confirm_output = _last_tool_output(messages, "confirm_order")

    if settings.human_confirmation:
        if confirm_output is not None and confirm_output.startswith("Order submitted"):
            return "Your order has been submitted -- the business will confirm it shortly."
    elif confirm_output is not None and confirm_output.startswith("Order confirmed."):
        return reply  # a real confirm_order call this thread actually succeeded

    update_output = _last_tool_output(messages, "update_order")
    if update_output is not None:
        return f"Let's just confirm before I place this -- here's the order so far:\n\n{update_output}\n\nShall I go ahead and confirm it?"
    return "I haven't actually placed an order yet -- could you confirm the items and fulfillment details again so I can do that?"
