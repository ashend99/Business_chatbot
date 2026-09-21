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
from common import PROJECT_CONFIG

logger = logging.getLogger(__name__)

_agent_config = PROJECT_CONFIG.get("agent", {})
MODEL_NAME = _agent_config.get("model", "gpt-4o-mini")
SYSTEM_PROMPT_TEMPLATE = _agent_config.get("system_prompt", "You are a helpful assistant for {tenant_name}.")
FALLBACK_REPLY = "Sorry, I'm having trouble responding right now -- please try again in a moment."

# matches "$19.99", "$1,299", "$5" -- used by the pricing guardrail below
_PRICE_PATTERN = re.compile(r"\$\s?\d+(?:,\d{3})*(?:\.\d{1,2})?")

# strips "[variant_id: <uuid>]" -- present in search_catalog/browse_catalog's
# tool output so the agent can reference an item in update_order/create_lead,
# but never meant for a customer to actually see
_VARIANT_ID_SUFFIX_PATTERN = re.compile(r"\s*\[variant_id:[^\]]*\]")

# used by the order-confirmation guardrail below -- catches the LLM telling
# the customer their order is confirmed/placed in prose without actually
# having called confirm_order
_ORDER_CONFIRMED_CLAIM_PATTERN = re.compile(
    r"\border (?:is |has been )?(?:confirmed|placed)\b|\b(?:confirmed|placed) your order\b", re.IGNORECASE
)

_model = ChatOpenAI(model=MODEL_NAME, api_key=settings.openai_api_key)


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

    tools = build_tools(tenant_id, conversation.id, channel_type)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(tenant_name=tenant.name if tenant else "this business")
    agent = create_react_agent(_model, tools, checkpointer=checkpointer, prompt=system_prompt)

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
        trusted_outputs = [
            out
            for out in (
                _last_tool_output(messages, "search_catalog"),
                _last_tool_output(messages, "browse_catalog"),
                _last_tool_output(messages, "update_order"),
                _last_tool_output(messages, "confirm_order"),
            )
            if out is not None
        ]
        combined_trusted_output = "\n".join(trusted_outputs) if trusted_outputs else None
        reply = _apply_pricing_guardrail(reply, combined_trusted_output)
        reply = _apply_order_confirmation_guardrail(reply, messages)
    except Exception:
        # a bot endpoint failing to generate should still reply with
        # *something* a channel adapter can forward, not a raw 500 -- but
        # the failure may have left this session's transaction in a broken
        # state (e.g. a tool-call error), so roll back before reusing it
        # below, or persisting the fallback message fails too
        logger.exception("agent run failed for conversation %s", conversation.id)
        await session.rollback()
        reply = FALLBACK_REPLY

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


def _apply_pricing_guardrail(reply: str, catalog_output: str | None) -> str:
    """If the reply states a price that doesn't appear in this turn's
    search_catalog output, the agent likely paraphrased/invented it --
    discard the LLM's prose and fall back to the tool's own text instead."""
    reply_prices = set(_PRICE_PATTERN.findall(reply))
    if not reply_prices:
        return reply
    if catalog_output is None:
        return reply  # no catalog lookup this turn, nothing to verify against

    catalog_prices = set(_PRICE_PATTERN.findall(catalog_output))
    if reply_prices <= catalog_prices:
        return reply
    # the raw tool output is otherwise trustworthy, but it carries internal
    # [variant_id: ...] tags for the agent's own reference (see bot_tools.py)
    # that a customer should never see verbatim
    customer_safe_output = _VARIANT_ID_SUFFIX_PATTERN.sub("", catalog_output)
    return f"Here's what I found:\n\n{customer_safe_output}"


def _apply_order_confirmation_guardrail(reply: str, messages: list) -> str:
    """If the reply tells the customer their order is confirmed/placed but
    confirm_order was never actually called (or was called and failed --
    e.g. an empty cart), the LLM said so without it being true. Placing an
    order is the one irreversible-feeling claim in this whole flow, so it
    gets the same treatment as the pricing guardrail: never trust the LLM's
    own account of what happened, check the tool's actual result."""
    if not _ORDER_CONFIRMED_CLAIM_PATTERN.search(reply):
        return reply

    confirm_output = _last_tool_output(messages, "confirm_order")
    if confirm_output is not None and confirm_output.startswith("Order confirmed."):
        return reply  # a real confirm_order call this thread actually succeeded

    update_output = _last_tool_output(messages, "update_order")
    if update_output is not None:
        return f"Let's just confirm before I place this -- here's the order so far:\n\n{update_output}\n\nShall I go ahead and confirm it?"
    return "I haven't actually placed an order yet -- could you confirm the items and fulfillment details again so I can do that?"
