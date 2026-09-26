"""Deterministic stand-ins for everything that would otherwise reach the
network during tests: OpenAI embeddings, the chat model, and email.

Nothing in the test suite may call a real external service -- tests must be
free, fast, offline and give the same result on every run.
"""

import hashlib
import math
import re
import uuid
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from app.models.settings import BotTone, NegotiationMode, OrderConfirmationMode
from app.services.settings_resolver import EffectiveSettings

EMBEDDING_DIMENSIONS = 1536
_WORD = re.compile(r"[a-z0-9]+")


# ---- embeddings -------------------------------------------------------------


def fake_embedding(text: str) -> list[float]:
    """Hashed bag-of-words vector, L2-normalised. Texts that share words get
    a real cosine similarity, so dense retrieval behaves meaningfully
    (unlike random vectors) without calling OpenAI."""
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for word in _WORD.findall(text.lower()):
        bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBEDDING_DIMENSIONS
        vector[bucket] += 1.0
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        vector[0] = 1.0
        return vector
    return [v / norm for v in vector]


async def fake_embed_texts(texts: list[str]) -> list[list[float]]:
    return [fake_embedding(t) for t in texts]


# ---- chat model -------------------------------------------------------------


class ScriptedChatModel(BaseChatModel):
    """Replays a fixed list of AIMessages, one per model call, so an agent
    run is fully deterministic. Put tool calls in an AIMessage's
    `tool_calls` to drive the real tools against the test database.

    Each entry may also be a callable taking the messages the model was
    given and returning an AIMessage -- for replies that depend on tool
    output produced earlier in the same run (e.g. a generated id)."""

    responses: list[Any] = Field(default_factory=list)
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        # the real tool schemas don't matter -- the script decides the calls
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        self.calls.append(list(messages))
        if not self.responses:
            raise RuntimeError("ScriptedChatModel ran out of scripted responses")
        response = self.responses.pop(0)
        message = response(messages) if callable(response) else response
        return ChatResult(generations=[ChatGeneration(message=message)])


def tool_call(name: str, args: dict | None = None, call_id: str | None = None) -> dict:
    return {
        "name": name,
        "args": args or {},
        "id": call_id or f"call_{uuid.uuid4().hex[:8]}",
        "type": "tool_call",
    }


def ai_tool_calls(*calls: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=list(calls))


def ai_text(text: str) -> AIMessage:
    return AIMessage(content=text)


# ---- email ------------------------------------------------------------------


@dataclass
class SentEmail:
    to: str
    subject: str
    body: str


@dataclass
class CapturingEmailSender:
    """Implements services.email.EmailSender; records instead of sending."""

    outbox: list[SentEmail] = field(default_factory=list)

    def send(self, to: str, subject: str, body: str) -> None:
        self.outbox.append(SentEmail(to, subject, body))


# ---- settings ---------------------------------------------------------------

_DEFAULT_EFFECTIVE = EffectiveSettings(
    tenant_id=uuid.UUID(int=0),
    currency_code="USD",
    allowed_channels=("website_widget", "facebook", "instagram", "whatsapp"),
    llm_model="gpt-4o-mini",
    monthly_message_limit=None,
    max_documents=None,
    bot_enabled=True,
    ordering_enabled=True,
    catalog_enabled=True,
    documents_enabled=True,
    leads_enabled=True,
    timezone="UTC",
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


def effective_settings(**overrides: Any) -> EffectiveSettings:
    """An EffectiveSettings with every-feature-on defaults, for pure unit
    tests that don't need the database."""
    if "min_order_value" in overrides and overrides["min_order_value"] is not None:
        overrides["min_order_value"] = Decimal(str(overrides["min_order_value"]))
    return replace(_DEFAULT_EFFECTIVE, **overrides)
