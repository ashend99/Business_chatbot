# eval/ harness

Simulated-customer conversations against the real bot, graded later by a
separate LLM judge. See [architecture_v0.1.md](../architecture_v0.1.md)'s
"eval/ harness" section for the full picture; this is quick local reference.

## Running it

From this directory (or `python eval/conversation_agent.py` from the repo
root):

```
python conversation_agent.py --scenario <id>   # one scenario
python conversation_agent.py --all              # every scenario in scenarios.yaml
python eval_agent.py --all                      # grade everything ungraded
python eval_agent.py --summary                  # print/save a report from what's already graded
```

The backend must already be running (`python -m app.main` from the repo
root — see root `AGENTS.md`).

## Env vars (root `.env`)

- `EVAL_BOT_API_KEY` — a dedicated tenant `api_secret` key for this harness
  (separate from the dashboard's own test key), so it's independently
  revocable. Minted via `repos/tenants.create_api_key`.
- `EVAL_API_BASE_URL` — defaults to `http://127.0.0.1:8000`.

## Adding a scenario

Add an entry to `scenarios.yaml`: `persona` (instructions for the simulated
customer — written as instructions *to* them, not a description of them),
`success_criteria` (graded later, so write concrete/checkable behaviors, not
vibes), `max_turns`, `channel`.

**Keep personas tenant-agnostic.** Describe customer *behavior* ("ask what
size options exist for whatever specific item the assistant first
mentions"), never a specific tenant's actual catalog items by name — this
platform is multi-tenant and multi-vertical; a scenario hardcoding "large
chicken pizza" only makes sense against one tenant's menu. The simulated
customer is itself an LLM reacting to the real transcript, so
behavior-described personas work against any tenant's actual
catalog/documents without knowing their contents in advance.

## Settings overrides

A scenario can include `settings: {tenant: {...}, admin: {...}}` — the harness
applies them via the real APIs (tenant login + superadmin login, using
`EVAL_TENANT_USERNAME`/`EVAL_TENANT_PASSWORD` and `SUPERADMIN_EMAIL`/
`SUPERADMIN_PASSWORD` from `.env`) before the run and restores the previous
values afterwards (`lib.SettingsOverride`). It goes through the API on purpose:
a direct DB write from this process wouldn't invalidate the running server's
settings cache. Saved results record the overrides and the business's local
date/time, and the judge is told about both. A rejected message (e.g. HTTP 403
for a disallowed channel) is recorded as a transcript turn, not a crash.

## The judge's known bias

`gpt-4o` can claim an order "wasn't really confirmed" while quoting its own
`db_facts` showing `status="placed"` — survived several rounds of explicit
counter-instruction in `eval_agent.py`'s prompt. `eval_agent.py` catches
this mechanically (`_is_confirmation_false_positive`) and marks matching
issues `SUSPECT` in `--summary` output rather than trusting them. Always
read `SUSPECT`-flagged issues (and really, any `fail`/`partial` verdict)
against the actual saved transcript before treating them as real bugs.

## Results

`eval/results/<scenario>__<run_id>.json` (transcript + `db_snapshot`),
`.eval.json` (judge verdict) alongside it, `summary.md` from `--summary`.
Gitignored — generated output, not source.

## LangSmith pipeline (`eval/langsmith_eval/`)

A parallel, more observable pipeline built alongside this one -- not a
replacement (yet). Design doc: [LANGSMITH_PLAN.md](LANGSMITH_PLAN.md).
`scenarios.yaml` is still the only source of truth; this pipeline reads it
and reuses `lib.py`, `conversation_agent.py`, and `eval_agent.py` directly
rather than re-implementing scenario loading, the simulator, or the judge.

```
uv run python eval/langsmith_eval/sync_dataset.py          # scenarios.yaml -> LangSmith dataset
uv run python eval/langsmith_eval/run_experiment.py         # run the full dataset, grade, compare in the LangSmith UI
uv run python eval/langsmith_eval/run_experiment.py --category ordering_cart
```

Needs `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` in
`.env` (a LangSmith account/API key, separate from anything else) alongside
the existing `EVAL_*`/`OPENAI_API_KEY` vars. The backend must already be
running, same as the local harness.

What it adds over `conversation_agent.py`/`eval_agent.py`:

- **A real trajectory trace per scenario**, not just a saved JSON transcript
  -- customer-simulator turns, the bot's LangGraph run, and every tool call
  nested under one trace, viewable in the LangSmith UI. This works because
  `api/bot/router.py` picks up a `langsmith-trace` header this pipeline's
  `target.py` sends with each `POST /bot/message` call and nests the
  backend's own run under it (inert for every real request, which never
  sends that header).
- **Deterministic evaluators** (`evaluators.py`) for the handful of things
  cheaply checkable in code -- order status, lead fields, price-matches-
  order-total, payment-mention-forbidden, HTTP-status-for-rejected-channel
  -- driven by an optional `checks:` block on a scenario (see `scenarios.yaml`,
  currently on ~17 of the 49 scenarios; adding more is additive, never
  required). Everything else is still graded by `llm_judge` alone, same as
  today.
- **Side-by-side experiment comparison** across prompt/model/agent versions,
  for free, once two experiment runs share the dataset -- no equivalent in
  the local harness's `summary.md`.

`settings_driven`-category scenarios still mutate live tenant settings via
the real API (`SettingsOverride`), so `run_experiment.py` always runs that
category at `max_concurrency=1` regardless of what else was asked for --
don't bypass this when editing it, see `LANGSMITH_PLAN.md` section 10 for
why.

Editing `scenarios.yaml`? Re-run `sync_dataset.py` afterward -- it's a
deliberate sync step, not automatic, same as running an Alembic migration
after changing a model.
