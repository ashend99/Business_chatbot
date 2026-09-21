"""Debug helper: delete a tenant's conversations, leads and orders (and the
agent's LangGraph memory for those conversations) from the database.

Run from the project root:
    python scripts/clear_conversations.py --tenant dulas_kitchen
    python scripts/clear_conversations.py --tenant dulas_kitchen --only-eval
    python scripts/clear_conversations.py --tenant dulas_kitchen --yes

By default EVERYTHING for the tenant is deleted, including orders/leads that
aren't linked to a conversation. With --only-eval, only rows tied to
conversations whose external_user_id starts with `eval-` or `test-` (what the
eval harness and manual tests create) are deleted.

Everything runs in one transaction, so a failure leaves the DB untouched.
This is irreversible and targets DATABASE_URL from .env (the shared DB) --
check the counts it prints before confirming.
"""

import argparse
import asyncio
import sys
from pathlib import Path

if sys.platform == "win32":
    # psycopg's async driver can't use the default ProactorEventLoop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import delete, func, or_, select, text  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models import Conversation, Lead, Message, Order  # noqa: E402
from app.repos import tenants as tenants_repo  # noqa: E402
from app.repos.tenant_scope import tenant_scope  # noqa: E402

# LangGraph's Postgres checkpointer tables; rows are keyed by thread_id,
# which is the conversation id as text.
CHECKPOINT_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")
EVAL_PREFIXES = ("eval-", "test-")


async def clear(slug: str, only_eval: bool, assume_yes: bool) -> None:
    async with AsyncSessionLocal() as session:
        tenant = await tenants_repo.get_tenant_by_slug(session, slug)
        if tenant is None:
            raise SystemExit(f"No tenant with slug '{slug}'")
        tid = tenant.id

        conv_stmt = select(Conversation.id).where(tenant_scope(Conversation.tenant_id, tid))
        if only_eval:
            conv_stmt = conv_stmt.where(
                or_(*(Conversation.external_user_id.startswith(p) for p in EVAL_PREFIXES))
            )
        conv_ids = list((await session.execute(conv_stmt)).scalars().all())

        # Orders/leads: everything for the tenant, or only those tied to the chosen conversations.
        order_where = [tenant_scope(Order.tenant_id, tid)]
        lead_where = [tenant_scope(Lead.tenant_id, tid)]
        if only_eval:
            order_where.append(Order.conversation_id.in_(conv_ids))
            lead_where.append(Lead.conversation_id.in_(conv_ids))

        n_orders = (await session.execute(select(func.count()).select_from(Order).where(*order_where))).scalar_one()
        n_leads = (await session.execute(select(func.count()).select_from(Lead).where(*lead_where))).scalar_one()
        n_msgs = (
            await session.execute(
                select(func.count()).select_from(Message).where(Message.conversation_id.in_(conv_ids))
            )
        ).scalar_one()

        scope = "eval/test rows only" if only_eval else "ALL rows"
        print(f"Tenant {slug} ({tid}) -- {scope}:")
        print(f"  conversations: {len(conv_ids)} ({n_msgs} messages), leads: {n_leads}, orders: {n_orders}")
        if not (conv_ids or n_orders or n_leads):
            print("Nothing to delete.")
            return
        if not assume_yes and input("Type 'delete' to continue: ") != "delete":
            print("Aborted.")
            return

        # Orders and leads first: their conversation FK is SET NULL, so deleting
        # conversations first would leave them behind as orphans.
        await session.execute(delete(Order).where(*order_where))
        await session.execute(delete(Lead).where(*lead_where))
        await session.execute(delete(Message).where(Message.conversation_id.in_(conv_ids)))
        await session.execute(delete(Conversation).where(Conversation.id.in_(conv_ids)))

        # The agent's memory; skip tables that don't exist (agent never ran).
        thread_ids = [str(c) for c in conv_ids]
        for table in CHECKPOINT_TABLES:
            exists = (await session.execute(text("select to_regclass(:t)"), {"t": table})).scalar_one()
            if exists is not None and thread_ids:
                await session.execute(
                    text(f"delete from {table} where thread_id = any(:ids)"), {"ids": thread_ids}
                )
        await session.commit()
        print("Deleted.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tenant", required=True, help="tenant slug, e.g. dulas_kitchen")
    parser.add_argument("--only-eval", action="store_true", help="only eval-*/test-* conversations")
    parser.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args()
    asyncio.run(clear(args.tenant, args.only_eval, args.yes))


if __name__ == "__main__":
    main()
