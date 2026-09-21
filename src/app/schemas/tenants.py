import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.settings import AdminSettingsUpdate, _validate_currency, _validate_timezone


class LoginRequest(BaseModel):
    username: str
    password: str


class SuperadminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VerifyActivationRequest(BaseModel):
    """Step 1 of activation: prove you're the invited tenant via the email
    the invite was sent to, plus the raw invite token. Stateless check --
    no side effects, safe to call repeatedly (e.g. for inline form
    validation before showing the credentials step)."""

    email: EmailStr
    token: str


class CompleteActivationRequest(BaseModel):
    """Step 2 of activation: resubmit the same invite token from step 1 --
    the frontend already holds it from the original activation link, so
    this isn't the user re-entering anything -- plus the username/password
    to actually create the dashboard login. Email isn't needed again here:
    the raw token alone (an unguessable secret) is enough to identify and
    authorize this; the email check in step 1 was just an extra identity
    confirmation for that step, not a security requirement.

    That login is what tenants use for all subsequent logins via
    POST /auth/tenant/login."""

    token: str
    username: str
    password: str


class RequestPasswordResetRequest(BaseModel):
    username: str


class PasswordResetRequest(BaseModel):
    token: str
    password: str = Field(min_length=8)


class TenantRead(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    email: str | None
    contact_person: str | None
    contact_number: str | None
    address: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TenantCreate(BaseModel):
    name: str
    slug: str
    email: EmailStr
    contact_person: str | None = None
    contact_number: str | None = None
    address: str | None = None
    # admin-set at onboarding, never tenant-editable (see models/settings.py):
    # required, since orders store bare numbers and a wrong/missing currency
    # can't be inferred later
    currency_code: str
    # only the tenant's *initial* timezone -- they can change it afterwards
    timezone: str = "UTC"
    # optional entitlements/channels/model/quotas (defaults: everything on)
    admin_settings: AdminSettingsUpdate | None = None

    @field_validator("currency_code")
    @classmethod
    def _currency(cls, value: str) -> str:
        return _validate_currency(value)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str) -> str:
        return _validate_timezone(value)


class TenantUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    contact_person: str | None = None
    contact_number: str | None = None
    address: str | None = None


class TenantListItem(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    email: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TenantListResponse(BaseModel):
    items: list[TenantListItem]
    total: int
    page: int
    page_size: int


class TenantDetail(TenantRead):
    # whether the tenant has completed activation (has a TenantAdmin login)
    activated: bool
    admin_username: str | None = None
