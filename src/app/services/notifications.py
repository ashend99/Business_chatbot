"""Lead/order notifications (Phase 5 / order module).

notify_new_lead is called only on the specific transition into status=NEW --
repos/leads.py's create_or_update_lead_from_bot returns whether a given call
caused that transition, so this fires exactly once per lead, not on every
subsequent bot tool call for the same conversation. status=INTERESTED
(partial leads) are dashboard-visible only, no email, per the plan's MVP
scope.

notify_new_order fires once per order, the moment repos/orders.confirm_order
successfully moves it DRAFT -> PLACED -- there's no equivalent "partial"
state worth emailing about, a draft cart is just dashboard-visible (once the
Orders page exists) like an INTERESTED lead.
"""

from app.models.leads import Lead
from app.models.orders import Order
from app.models.tenants import Tenant
from app.services.email import EmailSender
from common import PROJECT_CONFIG
from utils import from_env


async def notify_new_lead(email_sender: EmailSender, tenant: Tenant, lead: Lead) -> None:
    if not tenant.email:
        return

    field_lines = "\n".join(f"- {key}: {value}" for key, value in lead.fields.items())
    mail_subject = PROJECT_CONFIG.email.new_lead_mail.subject.format(tenant_name=tenant.name)
    mail_body = PROJECT_CONFIG.email.new_lead_mail.body.format(
        tenant_name=tenant.name,
        field_lines=field_lines or "(no details captured)",
        dashboard_link=from_env("CLIENT_DASHBOARD_URL"),
    )
    email_sender.send(to=tenant.email, subject=mail_subject, body=mail_body)


async def notify_new_order(email_sender: EmailSender, tenant: Tenant, order: Order) -> None:
    if not tenant.email:
        return

    item_lines = "\n".join(
        f"- {item['quantity']}x {item['product_name']}"
        + (f" ({item['variant_label']})" if item.get("variant_label") else "")
        + f" @ {item['unit_price']} each = {item['line_total']}"
        for item in order.items
    )
    fulfillment_lines = "\n".join(f"- {key}: {value}" for key, value in (order.fulfillment or {}).items())
    mail_subject = PROJECT_CONFIG.email.new_order_mail.subject.format(tenant_name=tenant.name)
    mail_body = PROJECT_CONFIG.email.new_order_mail.body.format(
        tenant_name=tenant.name,
        item_lines=item_lines or "(no items)",
        total=order.total,
        fulfillment_lines=fulfillment_lines or "(not specified)",
        notes=order.notes or "(none)",
        dashboard_link=from_env("CLIENT_DASHBOARD_URL"),
    )
    email_sender.send(to=tenant.email, subject=mail_subject, body=mail_body)
