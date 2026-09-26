"""Request-schema rules that enforce product decisions at the API edge --
most importantly the admin/tenant settings split (extra="forbid")."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.documents import ContentSource
from app.schemas.catalog import ProductCreate
from app.schemas.documents import DocumentCreate
from app.schemas.settings import AdminSettingsUpdate, TenantSettingsUpdate
from app.schemas.tenants import PasswordResetRequest, TenantCreate

# ---- settings split ---------------------------------------------------------


@pytest.mark.parametrize(
    "admin_field",
    [
        {"currency_code": "EUR"},
        {"ordering_allowed": True},
        {"allowed_channels": ["whatsapp"]},
        {"llm_model": "gpt-4o"},
        {"monthly_message_limit": 10},
    ],
)
def test_tenant_update_rejects_admin_fields(admin_field: dict) -> None:
    with pytest.raises(ValidationError):
        TenantSettingsUpdate(**admin_field)


@pytest.mark.parametrize(
    "tenant_field", [{"bot_name": "Sunny"}, {"timezone": "UTC"}, {"min_order_value": 5}]
)
def test_admin_update_rejects_tenant_fields(tenant_field: dict) -> None:
    with pytest.raises(ValidationError):
        AdminSettingsUpdate(**tenant_field)


def test_tenant_update_validates_timezone() -> None:
    assert TenantSettingsUpdate(timezone="Asia/Colombo").timezone == "Asia/Colombo"
    with pytest.raises(ValidationError):
        TenantSettingsUpdate(timezone="Mars/Olympus")


def test_tenant_update_field_limits() -> None:
    with pytest.raises(ValidationError):
        TenantSettingsUpdate(min_order_value=Decimal("-1"))
    with pytest.raises(ValidationError):
        TenantSettingsUpdate(custom_instructions="x" * 2001)
    with pytest.raises(ValidationError):
        TenantSettingsUpdate(notify_emails=["not-an-email"])


def test_admin_update_normalises_currency() -> None:
    assert AdminSettingsUpdate(currency_code=" lkr ").currency_code == "LKR"
    for bad in ("RUPEES", "L1R", "US"):
        with pytest.raises(ValidationError):
            AdminSettingsUpdate(currency_code=bad)


def test_admin_update_rejects_unknown_channels() -> None:
    assert AdminSettingsUpdate(allowed_channels=["website_widget", "whatsapp"]).allowed_channels
    with pytest.raises(ValidationError):
        AdminSettingsUpdate(allowed_channels=["telegram"])


def test_tenant_create_requires_valid_currency_and_timezone() -> None:
    base = {"name": "Shop", "slug": "shop", "email": "owner@example.com"}
    assert TenantCreate(**base, currency_code="usd").currency_code == "USD"
    with pytest.raises(ValidationError):
        TenantCreate(**base)  # currency is required
    with pytest.raises(ValidationError):
        TenantCreate(**base, currency_code="USD", timezone="Nowhere/Land")


def test_password_reset_minimum_length() -> None:
    with pytest.raises(ValidationError):
        PasswordResetRequest(token="t", password="short")


# ---- documents / catalog ----------------------------------------------------


def test_paste_document_needs_content() -> None:
    with pytest.raises(ValidationError):
        DocumentCreate(title="FAQ", content_source=ContentSource.PASTE, draft_content="   ")
    assert DocumentCreate(title="FAQ", draft_content="Q&A").content_source == ContentSource.PASTE


def test_upload_document_may_start_empty() -> None:
    assert DocumentCreate(title="Menu", content_source=ContentSource.UPLOAD).draft_content is None


def test_url_documents_must_use_import_endpoint() -> None:
    with pytest.raises(ValidationError):
        DocumentCreate(title="Site", content_source=ContentSource.URL, draft_content="x")


def test_standalone_product_needs_a_price() -> None:
    with pytest.raises(ValidationError):
        ProductCreate(name="Mug")
    assert ProductCreate(name="Mug", price=Decimal("8")).price == Decimal("8")
    assert (
        ProductCreate(name="Mug", variants=[{"name": "Blue", "price": "8"}]).variants[0].name
        == "Blue"
    )
