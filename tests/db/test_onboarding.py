"""services/onboarding.py: tenant creation, two-step activation, password
reset and invite resend -- including the single-use/expiry rules."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from fakes import CapturingEmailSender

from app.core.security import hash_token, verify_password
from app.models.settings import TenantAdminSettings, TenantSettings
from app.repos import leads_admin as leads_admin_repo
from app.repos import tenants as tenants_repo
from app.services import onboarding


def token_in(body: str) -> str:
    """The raw invite/reset token from an email body."""
    match = re.search(r"token=([\w-]+)", body) or re.search(
        r"invitation token to log in:\s*([\w-]+)", body
    )
    assert match, body
    return match.group(1)


async def onboard(session, sender, **overrides):
    kwargs = {
        "name": "Corner Bakery",
        "slug": "corner-bakery",
        "email": "owner@example.com",
        "currency_code": "LKR",
    }
    return await onboarding.onboard_tenant(session, sender, **{**kwargs, **overrides})


async def test_onboard_seeds_everything_and_emails_an_invite(session) -> None:
    sender = CapturingEmailSender()
    tenant = await onboard(
        session,
        sender,
        timezone="Asia/Colombo",
        admin_settings={"ordering_allowed": False, "llm_model": "gpt-4o"},
    )

    admin = await session.get(TenantAdminSettings, tenant.id)
    settings = await session.get(TenantSettings, tenant.id)
    assert (admin.currency_code, admin.ordering_allowed, admin.llm_model) == (
        "LKR",
        False,
        "gpt-4o",
    )
    assert settings.timezone == "Asia/Colombo"
    assert [
        d.field_key for d in await leads_admin_repo.list_lead_field_defs(session, tenant.id)
    ] == ["name", "phone", "email"]

    [mail] = sender.outbox
    assert mail.to == "owner@example.com"
    invite = await tenants_repo.get_invite_token_by_hash(session, hash_token(token_in(mail.body)))
    assert invite.tenant_id == tenant.id
    assert tenants_repo.is_invite_valid(invite)


async def test_activation_flow(session) -> None:
    sender = CapturingEmailSender()
    tenant = await onboard(session, sender)
    token = token_in(sender.outbox[0].body)

    await onboarding.verify_activation(session, token, "OWNER@example.com")  # case-insensitive
    with pytest.raises(ValueError):
        await onboarding.verify_activation(session, token, "someone-else@example.com")
    with pytest.raises(ValueError):
        await onboarding.verify_activation(session, "not-a-token", "owner@example.com")

    admin = await onboarding.complete_activation(session, token, "corner", "s3cret-pass")
    assert admin.tenant_id == tenant.id
    assert verify_password("s3cret-pass", admin.hashed_password)

    # the invite is burned
    with pytest.raises(ValueError):
        await onboarding.complete_activation(session, token, "corner2", "another-pass")


async def test_expired_invite_is_rejected(session) -> None:
    sender = CapturingEmailSender()
    await onboard(session, sender)
    token = token_in(sender.outbox[0].body)
    invite = await tenants_repo.get_invite_token_by_hash(session, hash_token(token))
    invite.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()

    with pytest.raises(ValueError):
        await onboarding.verify_activation(session, token, "owner@example.com")


async def activated(session, sender):
    tenant = await onboard(session, sender)
    await onboarding.complete_activation(
        session, token_in(sender.outbox[0].body), "corner", "first-password"
    )
    sender.outbox.clear()
    return tenant


async def test_password_reset_flow(session) -> None:
    sender = CapturingEmailSender()
    await activated(session, sender)

    await onboarding.request_password_reset(session, sender, "corner")
    [first] = sender.outbox
    assert "/reset-password?token=" in first.body
    await onboarding.request_password_reset(session, sender, "corner")
    first_token, second_token = token_in(first.body), token_in(sender.outbox[1].body)

    # only the newest link works
    with pytest.raises(ValueError):
        await onboarding.reset_password(session, first_token, "new-password-1")
    invite = await tenants_repo.get_invite_token_by_hash(session, hash_token(second_token))
    assert invite.expires_at - datetime.now(UTC) <= timedelta(hours=1)

    await onboarding.reset_password(session, second_token, "new-password-2")
    admin = await tenants_repo.get_tenant_admin_by_username(session, "corner")
    assert verify_password("new-password-2", admin.hashed_password)
    with pytest.raises(ValueError):
        await onboarding.reset_password(session, second_token, "new-password-3")


async def test_password_reset_for_unknown_user_is_silent(session) -> None:
    sender = CapturingEmailSender()
    await onboarding.request_password_reset(session, sender, "nobody")
    assert sender.outbox == []


async def test_reset_without_an_admin_account_fails(session) -> None:
    sender = CapturingEmailSender()
    await onboard(session, sender)  # invited, never activated
    with pytest.raises(ValueError, match="no admin account"):
        await onboarding.reset_password(session, token_in(sender.outbox[0].body), "whatever-pass")


async def test_resend_invite(session) -> None:
    import uuid

    sender = CapturingEmailSender()
    tenant = await onboard(session, sender)
    old_token = token_in(sender.outbox[0].body)

    await onboarding.resend_invite(session, sender, tenant.id)
    new_token = token_in(sender.outbox[1].body)
    with pytest.raises(ValueError):
        await onboarding.verify_activation(session, old_token, "owner@example.com")
    await onboarding.verify_activation(session, new_token, "owner@example.com")

    with pytest.raises(ValueError):
        await onboarding.resend_invite(session, sender, uuid.uuid4())

    await tenants_repo.set_tenant_active(session, tenant.id, False)
    await session.commit()
    with pytest.raises(onboarding.TenantSuspendedError):
        await onboarding.resend_invite(session, sender, tenant.id)
