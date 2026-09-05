"""Shared tenant-scoping helper for repo queries.

Every tenant-scoped table is filtered by `<Model>.tenant_id == tenant_id`,
but that alone leaves a suspended tenant's rows just as reachable as an
active one's -- suspension is currently enforced only at the auth-dependency
boundary (`get_current_tenant_id` / `get_current_service_tenant`). This adds
the tenant's `is_active` check into the same filter, as defense in depth: any
query that reaches a tenant-scoped table -- now or in some future code path
that doesn't happen to go through those dependencies -- stays blocked for a
suspended tenant.
"""

import uuid

from sqlalchemy import ColumnElement, and_, exists
from sqlalchemy.orm import InstrumentedAttribute

from app.models.tenants import Tenant


def tenant_scope(tenant_id_column: InstrumentedAttribute, tenant_id: uuid.UUID) -> ColumnElement[bool]:
    """Use in place of `Model.tenant_id == tenant_id` in any tenant-scoped
    query's `.where(...)`, e.g.:

        select(Document).where(tenant_scope(Document.tenant_id, tenant_id), Document.id == document_id)
    """
    return and_(
        tenant_id_column == tenant_id,
        exists().where(Tenant.id == tenant_id, Tenant.is_active.is_(True)),
    )
