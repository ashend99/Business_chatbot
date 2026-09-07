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
        actions = _extract_lead_actions(messages)
        reply = _apply_pricing_guardrail(reply, _last_tool_output(messages, "search_catalog"))
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
    return f"Here's what I found:\n\n{catalog_output}"
