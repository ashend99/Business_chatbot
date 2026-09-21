import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, hash_token
from app.models import InviteTokens, Tenant, TenantAdmin
from app.repos import leads_admin as leads_admin_repo
from app.repos import settings_admin as settings_admin_repo
from app.repos import tenants as tenants_repo
from app.services.email import EmailSender
from common import PROJECT_CONFIG
from utils import from_env

logger = logging.getLogger(__name__)

RESET_URL_TEMPLATE = "https://dashboard.example.com/reset-password?token={token}"


class TenantSuspendedError(ValueError):
    """Raised when an operation is attempted against a suspended tenant.

    A ValueError subclass so existing `except ValueError` call sites keep
    working, but distinct enough that callers who care (the API layer) can
    map it to 409 instead of the generic 404 used for "tenant not found".
    """


async def onboard_tenant(
    session: AsyncSession,
    email_sender: EmailSender,
    *,
    name: str,
    slug: str,
    email: str,
    contact_person: str | None = None,
    contact_number: str | None = None,
    address: str | None = None,
    currency_code: str = "USD",
    timezone: str = "UTC",
    admin_settings: dict | None = None,
) -> Tenant:
    """
    Onboard a new tenant by creating the tenant record, generating an invite token,
    and sending an activation email to the provided email address.

    Args:
        session (AsyncSession): The database session.
        email_sender (EmailSender): The email sender instance.
        name (str): The name of the tenant.
        slug (str): The slug for the tenant.
        email (str): The email address of the tenant.
        contact_person (str | None, optional): The contact person for the tenant. Defaults to None.
        contact_number (str | None, optional): The contact number for the tenant. Defaults to None.
        address (str | None, optional): The address of the tenant. Defaults to None.

    Returns:
        Tenant: The created Tenant object.
    """
    tenant = await tenants_repo.create_tenant(
        session,
        name=name,
        slug=slug,
        email=email,
        contact_person=contact_person,
        contact_number=contact_number,
        address=address,
    )
    _invite, raw_token = await tenants_repo.create_invite_token(session, tenant_id=tenant.id)
    # sensible lead-capture defaults (name/phone/email) so the bot has a
    # schema to work with immediately -- clients edit/add/remove later via
    # PUT /tenant/lead-field-defs
    await leads_admin_repo.seed_default_lead_field_defs(session, tenant.id)
    # admin-set settings (currency, entitlements, channels, model) + the
    # tenant's own starting settings -- see models/settings.py for the split
    await settings_admin_repo.create_default_settings(
        session,
        tenant.id,
        currency_code=currency_code,
        timezone=timezone,
        **(admin_settings or {}),
    )
    await session.commit()

    mail_subject = PROJECT_CONFIG.email.onboard_mail.subject
    mail_body = PROJECT_CONFIG.email.onboard_mail.body.format(
        name=name,
        dashboard_link=from_env("CLIENT_DASHBOARD_URL"),
        invitation_token=raw_token,
    )
    email_sender.send(
        to=email,
        subject=mail_subject,
        body=mail_body,
    )
    return tenant


async def _get_valid_invite(session: AsyncSession, raw_token: str) -> InviteTokens:
    """The raw invite token alone -- an unguessable secret -- is sufficient
    to identify and authorize against a pending invite."""
    invite = await tenants_repo.get_invite_token_by_hash(session, hash_token(raw_token))
    if invite is None or not tenants_repo.is_invite_valid(invite):
        raise ValueError("invalid or expired invite token")
    return invite


async def verify_activation(session: AsyncSession, raw_token: str, email: str) -> None:
    """Step 1 of activation: confirm the invite token is valid AND belongs
    to the tenant with the given email. This email check exists only here,
    as an extra identity confirmation before showing the credentials form
    (e.g. catches a forwarded/stale link) -- it's not required again in
    step 2, since the token itself is already the real secret. Stateless --
    no side effects, so this is safe to call repeatedly."""
    invite = await _get_valid_invite(session, raw_token)

    tenant = await tenants_repo.get_tenant_by_id(session, invite.tenant_id)
    # same generic message either way -- don't reveal whether the email or
    # the token was the part that didn't match
    if tenant is None or not tenant.email or tenant.email.lower() != email.lower():
        raise ValueError("invalid or expired invite token")


async def complete_activation(session: AsyncSession, raw_token: str, username: str, password: str) -> TenantAdmin:
    """Step 2 of activation: the client resubmits only the same raw invite
    token it already holds from the original activation link (not
    something the user re-enters) plus a new username/password. Creates
    the real dashboard login and burns the invite."""
    invite = await _get_valid_invite(session, raw_token)

    admin = await tenants_repo.create_tenant_admin(
        session, tenant_id=invite.tenant_id, username=username, hashed_password=hash_password(password)
    )
    await tenants_repo.mark_invite_used(session, invite)
    await session.commit()
    return admin


async def request_password_reset(session: AsyncSession, email_sender: EmailSender, username: str) -> None:
    admin = await tenants_repo.get_tenant_admin_by_username(session, username)
    if admin is None:
        return  # don't reveal whether a username exists

    tenant = await tenants_repo.get_tenant_by_id(session, admin.tenant_id)
    _invite, raw_token = await tenants_repo.create_invite_token(session, tenant_id=admin.tenant_id, expires_in_hours=1)
    await session.commit()

    if tenant and tenant.email:
        mail_subject = PROJECT_CONFIG.email.reset_password_mail.subject
        mail_body = PROJECT_CONFIG.email.reset_password_mail.body.format(
            name=tenant.name,
            reset_token=raw_token,
        )
        email_sender.send(
            to=tenant.email,
            subject=mail_subject,
            body=mail_body,
        )

async def reset_password(session: AsyncSession, raw_token: str, new_password: str) -> None:
    invite = await tenants_repo.get_invite_token_by_hash(session, hash_token(raw_token))
    if invite is None or not tenants_repo.is_invite_valid(invite):
        raise ValueError("invalid or expired token")

    admin = await tenants_repo.get_tenant_admin_by_tenant_id(session, invite.tenant_id)
    if admin is None:
        raise ValueError("no admin account to reset")

    await tenants_repo.update_tenant_admin_password(session, admin, hash_password(new_password))
    await tenants_repo.mark_invite_used(session, invite)
    await session.commit()


async def resend_invite(session: AsyncSession, email_sender: EmailSender, tenant_id: uuid.UUID) -> None:
    tenant = await tenants_repo.get_tenant_by_id(session, tenant_id)
    if tenant is None:
        raise ValueError("tenant not found")
    if not tenant.is_active:
        # a suspended tenant shouldn't be handed a fresh way to activate/log
        # in -- that's the whole point of suspending them
        raise TenantSuspendedError("tenant is suspended -- reactivate before resending an invite")

    await tenants_repo.invalidate_pending_invites(session, tenant_id)
    _invite, raw_token = await tenants_repo.create_invite_token(session, tenant_id=tenant_id)
    await session.commit()

    if tenant.email:
        mail_subject = PROJECT_CONFIG.email.onboard_mail.subject
        mail_body = PROJECT_CONFIG.email.onboard_mail.body.format(
            name=tenant.name,
            dashboard_link=from_env("CLIENT_DASHBOARD_URL"),
            invitation_token=raw_token,
        )
        email_sender.send(
            to=tenant.email,
            subject=mail_subject,
            body=mail_body,
        )
