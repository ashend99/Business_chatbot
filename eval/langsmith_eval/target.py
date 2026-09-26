"""The `target` function passed to langsmith.aevaluate(): runs one scenario
end to end (simulated customer <-> real POST /bot/message, for up to
max_turns) and returns {transcript, db_snapshot, ...} for the evaluators in
evaluators.py to grade.

Reuses conversation_agent.py's simulator and DB-snapshot logic directly
(imported, not re-implemented) so there is exactly one place that knows how
to play a persona or read back Lead/Order rows -- conversation_agent.py's
own local harness and this LangSmith target must never quietly drift apart
in what a "scenario run" actually does.

Distributed tracing: `_traced_send_bot_message` attaches the current
LangSmith run's trace headers to each call to POST /bot/message, so the
backend's LangGraph run nests under this function's `@traceable` span
instead of starting a disconnected root trace -- see the receiving side in
src/app/api/bot/router.py and LANGSMITH_PLAN.md section 6. If that backend
hook isn't wired up (or LANGSMITH_TRACING is off), these headers are simply
ignored server-side -- every call here still works, you just get one root
trace per bot turn instead of one nested trace per scenario.
"""

import config  # noqa: F401,I001  -- sets up sys.path before the imports below

import json

import httpx
from langsmith.run_helpers import get_current_run_tree, traceable

from conversation_agent import _simulator_next, _simulator_system_prompt, _snapshot_db
from lib import API_BASE_URL, BOT_API_KEY, Scenario, SettingsOverride, new_external_user_id


def _scenario_from_inputs(inputs: dict) -> Scenario:
    """Rebuild a Scenario-shaped object from the dataset example's `inputs`
    so SettingsOverride and the simulator prompt builder -- both written
    against Scenario -- can be reused as-is instead of re-implemented against
    a plain dict. success_criteria is left blank here on purpose: the
    evaluators read it from the dataset example's `outputs`, not from this
    reconstructed object, so there's exactly one place it's sourced from."""
    return Scenario(
        {
            "id": inputs["scenario_id"],
            "channel": inputs.get("channel", "website_widget"),
            "persona": inputs["persona"],
            "success_criteria": "",
            "max_turns": inputs.get("max_turns", 8),
            "settings": {
                "tenant": inputs.get("tenant_settings") or {},
                "admin": inputs.get("admin_settings") or {},
            },
        }
    )


def _traced_send_bot_message(channel_type: str, external_user_id: str, text: str) -> dict:
    if not BOT_API_KEY:
        raise RuntimeError("EVAL_BOT_API_KEY is not set in .env")
    headers = {"X-Api-Key": BOT_API_KEY}
    run_tree = get_current_run_tree()
    if run_tree is not None:
        headers.update(run_tree.to_headers())
    resp = httpx.post(
        f"{API_BASE_URL}/bot/message",
        json={"channel_type": channel_type, "external_user_id": external_user_id, "text": text},
        headers=headers,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


@traceable(name="scenario_conversation", run_type="chain")
async def run_scenario(inputs: dict) -> dict:
    scenario = _scenario_from_inputs(inputs)
    external_user_id = new_external_user_id(scenario.id)

    with SettingsOverride(scenario) as overrides:
        sim_messages = [{"role": "system", "content": _simulator_system_prompt(scenario)}]
        transcript: list[dict] = []
        conversation_id: str | None = None

        for _turn in range(scenario.max_turns):
            # conversation_agent._simulator_next uses its own plain OpenAI
            # client (not LangSmith-wrapped) -- its calls won't show up as
            # traced children yet. Wrapping it (langsmith.wrappers.wrap_openai)
            # is a reasonable follow-up, deliberately left out of this first
            # cut to avoid a second simulator client/prompt path to keep in
            # sync with conversation_agent.py's own.
            sim_turn = _simulator_next(sim_messages)
            customer_text = sim_turn["message"].strip()
            if not customer_text:
                break
            sim_messages.append({"role": "assistant", "content": json.dumps(sim_turn)})
            transcript.append({"role": "customer", "text": customer_text})

            try:
                bot_result = _traced_send_bot_message(
                    scenario.channel, external_user_id, customer_text
                )
            except httpx.HTTPStatusError as exc:
                transcript.append(
                    {
                        "role": "assistant",
                        "text": "",
                        "http_status": exc.response.status_code,
                        "http_detail": exc.response.text,
                    }
                )
                break

            bot_reply = bot_result["reply"]
            conversation_id = bot_result["conversation_id"]
            transcript.append(
                {"role": "assistant", "text": bot_reply, "actions": bot_result.get("actions", [])}
            )

            if sim_turn["done"]:
                break
            sim_messages.append({"role": "user", "content": bot_reply or "(no reply)"})

        db_snapshot = await _snapshot_db(conversation_id)
        local_now = overrides.local_now()

    return {
        "transcript": transcript,
        "db_snapshot": db_snapshot,
        "conversation_id": conversation_id,
        "external_user_id": external_user_id,
        "settings_overrides": {
            "tenant": scenario.tenant_settings,
            "admin": scenario.admin_settings,
        },
        "run_context": {"business_local_now": local_now},
    }
