import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class TenantAdmin(TimestampMixin, Base):
    """The dashboard login credential for a tenant.

    One admin per tenant for this MVP (multi-user client accounts are
    explicitly deferred) -- tenant_id is the primary key, same 1:1 pattern
    as BotConfig. Username is globally unique (not just per-tenant) so login
    can resolve the tenant from username+password alone. The tenant's contact
    email (Tenant.email) is a separate business-profile field used only to
    look the tenant up during activation -- it plays no role in login once
    the client has picked their own username.
    """

    __tablename__ = "tenant_admins"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
