import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.settings import BotTone, NegotiationMode, OrderConfirmationMode
from app.models.tenants import ApiKeyTypes

CUSTOM_INSTRUCTIONS_MAX_CHARS = 2000
KNOWN_CHANNELS = {"website_widget", "facebook", "instagram", "whatsapp"}


def _validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown timezone {value!r} (use an IANA name like 'Asia/Colombo')") from exc
    return value


def _validate_currency(value: str) -> str:
    value = value.strip().upper()
    if len(value) != 3 or not value.isalpha():
        raise ValueError("currency_code must be a 3-letter ISO 4217 code, e.g. 'LKR'")
    return value


# ---- tenant-settable --------------------------------------------------------


class TenantSettingsUpdate(BaseModel):
    """Everything a tenant may change from the dashboard -- and nothing
    else. `extra="forbid"` means sending an admin-only field (currency,
    entitlements, channels, model, quotas) is a 422, not silently ignored."""

    model_config = {"extra": "forbid"}

    timezone: str | None = None

    bot_name: str | None = Field(default=None, max_length=100)
    tone: BotTone | None = None
    language: str | None = Field(default=None, min_length=1, max_length=50)
    welcome_message: str | None = Field(default=None, max_length=1000)
    fallback_message: str | None = Field(default=None, max_length=1000)
    custom_instructions: str | None = Field(default=None, max_length=CUSTOM_INSTRUCTIONS_MAX_CHARS)

    bot_enabled: bool | None = None
    ordering_enabled: bool | None = None
    catalog_enabled: bool | None = None
    documents_enabled: bool | None = None
    leads_enabled: bool | None = None

    delivery_enabled: bool | None = None
    pickup_enabled: bool | None = None
    cash_on_delivery: bool | None = None
    min_order_value: Decimal | None = Field(default=None, ge=0)
    negotiation_mode: NegotiationMode | None = None
    order_confirmation_mode: OrderConfirmationMode | None = None

    notify_emails: list[EmailStr] | None = None
    notify_new_lead: bool | None = None
    notify_new_order: bool | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str | None) -> str | None:
        return None if value is None else _validate_timezone(value)


class TenantSettingsRead(BaseModel):
    timezone: str
    bot_name: str | None
    tone: BotTone
    language: str
    welcome_message: str | None
    fallback_message: str | None
    custom_instructions: str | None
    bot_enabled: bool
    ordering_enabled: bool
    catalog_enabled: bool
    documents_enabled: bool
    leads_enabled: bool
    delivery_enabled: bool
    pickup_enabled: bool
    cash_on_delivery: bool
    min_order_value: Decimal | None
    negotiation_mode: NegotiationMode
    order_confirmation_mode: OrderConfirmationMode
    notify_emails: list[str]
    notify_new_lead: bool
    notify_new_order: bool

    model_config = {"from_attributes": True}


class CapabilitiesRead(BaseModel):
    """The read-only, admin-set half a tenant may SEE (never edit): what
    they've been granted. Deliberately omits admin-internal fields (model,
    quotas, allowed channels)."""

    currency_code: str
    ordering_allowed: bool
    catalog_allowed: bool
    documents_allowed: bool
    leads_allowed: bool

    model_config = {"from_attributes": True}


class TenantSettingsResponse(BaseModel):
    settings: TenantSettingsRead
    capabilities: CapabilitiesRead


# ---- admin-settable ---------------------------------------------------------


class AdminSettingsUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    currency_code: str | None = None
    ordering_allowed: bool | None = None
    catalog_allowed: bool | None = None
    documents_allowed: bool | None = None
    leads_allowed: bool | None = None
    allowed_channels: list[str] | None = None
    llm_model: str | None = Field(default=None, max_length=100)
    monthly_message_limit: int | None = Field(default=None, ge=0)
    max_documents: int | None = Field(default=None, ge=0)

    @field_validator("currency_code")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        return None if value is None else _validate_currency(value)

    @field_validator("allowed_channels")
    @classmethod
    def _channels(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        unknown = set(value) - KNOWN_CHANNELS
        if unknown:
            raise ValueError(f"unknown channel(s): {sorted(unknown)}")
        return value


class AdminSettingsRead(BaseModel):
    tenant_id: uuid.UUID
    currency_code: str
    ordering_allowed: bool
    catalog_allowed: bool
    documents_allowed: bool
    leads_allowed: bool
    allowed_channels: list[str]
    llm_model: str | None
    monthly_message_limit: int | None
    max_documents: int | None

    model_config = {"from_attributes": True}


class ApiKeyRead(BaseModel):
    id: uuid.UUID
    key_prefix: str
    key_type: ApiKeyTypes
    created_at: datetime
    revoked_at: datetime | None

    model_config = {"from_attributes": True}


class ApiKeyCreated(ApiKeyRead):
    # the raw secret -- returned exactly once, never retrievable again
    secret: str
