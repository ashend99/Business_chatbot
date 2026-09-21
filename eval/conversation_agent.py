"""Simulated-customer driver: plays a scenario's persona against the real
POST /bot/message endpoint for several turns, then saves the transcript plus
a DB snapshot (the resulting Lead/Order rows for that conversation) to
eval/results/ for eval_agent.py to grade later.

Usage (from the project root):
    uv run python eval/conversation_agent.py --scenario order_specific_item
    uv run python eval/conversation_agent.py --all
"""

import argparse
import asyncio
import json
import sys

import httpx
from openai import OpenAI

from lib import (
    OPENAI_API_KEY,
    Scenario,
    SettingsOverride,
    load_scenarios,
    new_external_user_id,
    new_run_id,
    result_path,
    send_bot_message,
)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

SIMULATOR_MODEL = "gpt-4o-mini"

_client = OpenAI(api_key=OPENAI_API_KEY)


def _simulator_system_prompt(scenario: Scenario) -> str:
    return f"""You are role-playing as a customer chatting with a business's AI \
chat assistant, purely for automated testing purposes.

Your character and goal for this conversation:
{scenario.persona}

Rules:
- Write natural, casual customer messages, one at a time -- never the whole \
conversation at once, never narrate stage directions.
- Never break character, and never mention that you are an AI, a test, or \
role-playing, even if asked.
- React naturally to whatever the assistant actually said, adjusting your \
next message accordingly rather than following a fixed script.
- Even if your character notes below mention your name or contact number, \
only actually give them once the assistant has asked for that information --\
 never volunteer them unprompted. If the assistant hasn't asked yet, talk \
about what you want instead (items, delivery/pickup, timing, questions) and \
wait for it to ask.
- Set "done": true on the message where your goal is accomplished, or the \
conversation has reached a natural end -- that message may still be a real \
reply (e.g. a thank-you), it's just your last one.

Always reply with a single JSON object: {{"message": "<your next chat \
message>", "done": true|false}}. No other text."""


def _simulator_next(sim_messages: list[dict]) -> dict:
    resp = _client.chat.completions.create(
        model=SIMULATOR_MODEL,
        messages=sim_messages,
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    content = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {"message": content.strip(), "done": True}
    return {"message": data.get("message", ""), "done": bool(data.get("done", False))}


def run_scenario(scenario: Scenario, local_now: str) -> dict:
    external_user_id = new_external_user_id(scenario.id)
    run_id = new_run_id()
    print(f"\n=== {scenario.id} ({external_user_id}) ===")

    sim_messages = [{"role": "system", "content": _simulator_system_prompt(scenario)}]
    transcript: list[dict] = []
    conversation_id: str | None = None

    for turn in range(scenario.max_turns):
        sim_turn = _simulator_next(sim_messages)
        customer_text = sim_turn["message"].strip()
        if not customer_text:
            break
        sim_messages.append({"role": "assistant", "content": json.dumps(sim_turn)})
        transcript.append({"role": "customer", "text": customer_text})
        print(f"customer: {customer_text}")

        try:
            bot_result = send_bot_message(scenario.channel, external_user_id, customer_text)
        except httpx.HTTPStatusError as exc:
            # e.g. 403 for a channel the tenant's admin hasn't enabled -- a
            # legitimate outcome for a settings scenario, not a harness crash
            detail = exc.response.text
            transcript.append(
                {"role": "assistant", "text": "", "http_status": exc.response.status_code, "http_detail": detail}
            )
            print(f"bot: [HTTP {exc.response.status_code}] {detail}")
            break
        bot_reply = bot_result["reply"]
        conversation_id = bot_result["conversation_id"]
        transcript.append({"role": "assistant", "text": bot_reply, "actions": bot_result.get("actions", [])})
        print(f"bot: {bot_reply}")

        if sim_turn["done"]:
            break
        # an empty reply is the contract for "the bot stayed silent"
        sim_messages.append({"role": "user", "content": bot_reply or "(no reply)"})

    return {
        "scenario_id": scenario.id,
        "run_id": run_id,
        "external_user_id": external_user_id,
        "conversation_id": conversation_id,
        "channel": scenario.channel,
        "success_criteria": scenario.success_criteria,
        "settings_overrides": {"tenant": scenario.tenant_settings, "admin": scenario.admin_settings},
        "run_context": {"business_local_now": local_now},
        "transcript": transcript,
    }


async def _snapshot_db(conversation_id: str | None) -> dict:
    if conversation_id is None:
        return {"leads": [], "orders": [], "messages": {}}

    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.leads import Lead
    from app.models.orders import Order

    async with AsyncSessionLocal() as session:
        leads = (
            (await session.execute(select(Lead).where(Lead.conversation_id == conversation_id))).scalars().all()
        )
        orders = (
            (await session.execute(select(Order).where(Order.conversation_id == conversation_id))).scalars().all()
        )
        from sqlalchemy import func

        from app.models.conversations import Message

        counts = (
            await session.execute(
                select(Message.role, func.count()).where(Message.conversation_id == conversation_id).group_by(Message.role)
            )
        ).all()
        return {
            "messages": {role.value: n for role, n in counts},
            "leads": [
                {"id": str(l.id), "status": l.status.value, "fields": l.fields} for l in leads
            ],
            "orders": [
                {
                    "id": str(o.id),
                    "status": o.status.value,
                    "items": o.items,
                    "total": str(o.total),
                    "currency_code": o.currency_code,
                    "notes": o.notes,
                    "fulfillment": o.fulfillment,
                    "lead_id": str(o.lead_id) if o.lead_id else None,
                }
                for o in orders
            ],
        }


async def _main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scenario", help="Run a single scenario by id.")
    group.add_argument("--all", action="store_true", help="Run every scenario in scenarios.yaml.")
    args = parser.parse_args()

    scenarios = load_scenarios()
    if args.scenario:
        scenarios = [s for s in scenarios if s.id == args.scenario]
        if not scenarios:
            raise SystemExit(f"no scenario named {args.scenario!r}")

    for scenario in scenarios:
        with SettingsOverride(scenario) as overrides:
            result = run_scenario(scenario, overrides.local_now())
        result["db_snapshot"] = await _snapshot_db(result["conversation_id"])
        path = result_path(scenario.id, result["run_id"])
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"saved -> {path}")


if __name__ == "__main__":
    asyncio.run(_main())
