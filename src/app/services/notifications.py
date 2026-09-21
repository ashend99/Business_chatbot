"""Lead/order notifications (Phase 5 / order module).

Recipients and on/off toggles come from the tenant's effective settings
(TenantSettings.notify_emails / notify_new_lead / notify_new_order); with no
recipients configured it falls back to the tenant's signup email. Amounts are
formatted in the tenant's (admin-set) currency.

notify_new_lead is called only on the specific transition into status=NEW --
repos/leads.py's create_or_update_lead_from_bot returns whether a given call
caused that transition, so this fires exactly once per lead, not on every
subsequent bot tool call for the same conversation. status=INTERESTED
(partial leads) are dashboard-visible only, no email, per the plan's MVP
scope.

notify_new_order fires once per order, the moment repos/orders.confirm_order
succeeds. In human-confirmation mode that's a *submission* the business must
act on, so it uses different wording than a bot-placed order.
"""

from app.models.leads import Lead
from app.models.orders import Order
from app.models.tenants import Tenant
from app.services.email import EmailSender
from app.services.money import format_money
from app.services.settings_resolver import EffectiveSettings
from common import PROJECT_CONFIG
from utils import from_env


async def notify_new_lead(
    email_sender: EmailSender, tenant: Tenant, lead: Lead, settings: EffectiveSettings
) -> None:
    recipients = settings.recipients(tenant.email)
    if not settings.notify_new_lead or not recipients:
        return

    field_lines = "\n".join(f"- {key}: {value}" for key, value in lead.fields.items())
    mail_subject = PROJECT_CONFIG.email.new_lead_mail.subject.format(tenant_name=tenant.name)
    mail_body = PROJECT_CONFIG.email.new_lead_mail.body.format(
        tenant_name=tenant.name,
        field_lines=field_lines or "(no details captured)",
        dashboard_link=from_env("CLIENT_DASHBOARD_URL"),
    )
    for recipient in recipients:
        email_sender.send(to=recipient, subject=mail_subject, body=mail_body)


async def notify_new_order(
    email_sender: EmailSender, tenant: Tenant, order: Order, settings: EffectiveSettings
) -> None:
    recipients = settings.recipients(tenant.email)
    if not settings.notify_new_order or not recipients:
        return

    currency = settings.currency_code
    item_lines = "\n".join(
        f"- {item['quantity']}x {item['product_name']}"
        + (f" ({item['variant_label']})" if item.get("variant_label") else "")
        + f" @ {format_money(item['unit_price'], currency)} each = {format_money(item['line_total'], currency)}"
        for item in order.items
    )
    fulfillment_lines = "\n".join(f"- {key}: {value}" for key, value in (order.fulfillment or {}).items())
    template = (
        PROJECT_CONFIG.email.new_order_pending_mail if settings.human_confirmation else PROJECT_CONFIG.email.new_order_mail
    )
    mail_subject = template.subject.format(tenant_name=tenant.name)
    mail_body = template.body.format(
        tenant_name=tenant.name,
        item_lines=item_lines or "(no items)",
        total=format_money(order.total, currency),
        fulfillment_lines=fulfillment_lines or "(not specified)",
        notes=order.notes or "(none)",
        dashboard_link=from_env("CLIENT_DASHBOARD_URL"),
    )
    for recipient in recipients:
        email_sender.send(to=recipient, subject=mail_subject, body=mail_body)
