"""Lead notification (Phase 5).

Called only on the specific transition into status=NEW -- repos/leads.py's
create_or_update_lead_from_bot returns whether a given call caused that
transition, so this fires exactly once per lead, not on every subsequent
bot tool call for the same conversation. status=INTERESTED (partial leads)
are dashboard-visible only, no email, per the plan's MVP scope.
"""

from app.models.leads import Lead
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
