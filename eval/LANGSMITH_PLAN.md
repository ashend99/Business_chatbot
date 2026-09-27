# LangSmith eval pipeline — implementation plan

Status: **implemented**, in `eval/langsmith_eval/`. This is still kept as
the design record — the "why" behind decisions the code doesn't otherwise
explain — not just a historical artifact; see [CLAUDE.md](CLAUDE.md) for the
day-to-day usage reference and [architecture_v0.1.md](../.claude/architectures/architecture_v0.1.md)
for the bot itself.

**Deviations from this plan, as actually built:**

- The package is `eval/langsmith_eval/`, not `eval/langsmith/` as originally
  sketched below. A directory
  literally named `langsmith` sitting where `eval/` ends up on `sys.path`
  (every script here inserts `EVAL_ROOT` onto `sys.path` to reach `lib.py`)
  would shadow the real installed `langsmith` package the first time
  anything did `import langsmith`. Discovered while implementing §4, not
  anticipated when this plan was first written.
- Not a real Python package (no `__init__.py`, no relative imports) —
  flat scripts sharing a `config.py` that does `sys.path`/env setup as an
  import-time side effect, mirroring `eval/lib.py`'s own pattern. This
  matches how `conversation_agent.py`/`eval_agent.py` are already meant to
  be run directly (`uv run python eval/langsmith_eval/run_experiment.py`),
  which relative imports inside a package don't support when the module
  being run is `__main__`.
- `run_experiment.py`'s settings-driven-category concurrency split (§10) is
  implemented as two sequential `aevaluate()` calls appended into the same
  experiment via the `experiment=` kwarg on the second call, rather than a
  single call with per-example concurrency control (`aevaluate()` doesn't
  expose that).
- The distributed-tracing hook in `api/bot/router.py` (§6) uses
  `langsmith.run_helpers.tracing_context(parent=dict(request.headers))`,
  guarded by checking for the `langsmith-trace` header first — confirmed
  against the actual installed SDK version (`langsmith>=0.12.1`, added to
  `pyproject.toml`) rather than guessed.

## 1. Why move off the current harness

The current `conversation_agent.py` + `eval_agent.py` pair already gets the
two things that matter most right — a real multi-turn simulator against the
actual `/bot/message` endpoint, and grading against ground-truth DB state
instead of trusting the bot's own account of what happened. What it's
missing is **observability**: there is no way to look inside a run and see
*which* tool calls happened, in what order, with what arguments/outputs, or
to compare two versions of the prompt/agent against the same 49 scenarios
side by side. Today that requires manually reading `eval/results/*.json`.

LangSmith buys three things without reinventing what already works:

1. **Trace-level visibility** — every LangGraph run already goes through
   `create_react_agent`, which LangSmith auto-instruments the moment tracing
   env vars are set. Zero code change gets you per-tool-call visibility
   *inside a single bot turn*. The work in this plan is almost entirely
   about extending that to *one trace per whole scenario* (customer turns +
   bot turns + evaluators), not about instrumenting the bot itself.
2. **Dataset/experiment comparison** — running the same 49 scenarios against
   two prompt/model versions and getting a side-by-side diff in the UI, for
   free, once the dataset exists.
3. **Decoupled, composable evaluators** — the current single LLM judge does
   everything. Splitting the mechanical checks (order status, price
   accuracy, payment-boundary keyword scan) into separate deterministic
   evaluator functions makes each failure mode individually visible instead
   of buried in one paragraph of judge prose.

**What is explicitly *not* changing:** `scenarios.yaml` stays the source of
truth (edited by hand, same as today); the DB-snapshot-over-transcript
principle stays; the tenant-agnostic persona convention stays; the bot is
still driven over real HTTP, exactly as `eval/CLAUDE.md` already mandates.

## 2. Decision log

- **Trace wiring: HTTP + distributed tracing.** The target function keeps
  calling the real `POST /bot/message` endpoint (not
  `bot_engine.handle_message` in-process) and propagates LangSmith's trace
  context across that HTTP boundary, so the backend's LangGraph run nests
  under the scenario's trace. This costs one small, dev-only change in the
  backend (§6) but preserves "exercises the exact same path a real channel
  adapter would use" — the property `eval/CLAUDE.md` explicitly calls out as
  intentional, not a shortcut to bypass.
- **Coexistence, not a rewrite.** `conversation_agent.py`/`eval_agent.py`
  stay as-is during the migration. The LangSmith pipeline lives in a new
  `eval/langsmith_eval/` package. Cut over (or don't) once the two have been
  run side by side on a few scenarios and agree.
- **`scenarios.yaml` gets one new optional block (`checks:`)**, not the
  fully-structured `success_criteria` ChatGPT's answer sketched. The
  narrative `success_criteria` string stays and keeps feeding the LLM judge
  — rewriting all 49 of those into structured fields is a lot of surface
  area for criteria that are often genuinely narrative ("politely declines
  and offers to follow up"). Only the handful of dimensions that are cheaply
  and unambiguously checkable by code get a `checks:` entry, added
  incrementally, not required for every scenario. This matches the "don't
  add abstractions beyond what's needed" rule already in this repo's
  `AGENTS.md`.

## 3. Architecture

```
scenarios.yaml (unchanged, hand-edited)
        │
        ▼
eval/langsmith_eval/sync_dataset.py  ──►  LangSmith Dataset
                                      "business-chatbot-scenarios"
                                      one Example per scenario, keyed by
                                      scenario id in metadata

                        langsmith.aevaluate(
                          target = run_scenario,     ← eval/langsmith_eval/target.py
                          data   = dataset,
                          evaluators = [...],         ← eval/langsmith_eval/evaluators.py
                        )
                                │
                                ▼
        ┌───────────────────────────────────────────────┐
        │  run_scenario(inputs)  == one Example           │
        │  @traceable root span                           │
        │                                                  │
        │   SettingsOverride(tenant/admin) applied         │
        │        │                                         │
        │   loop until done/max_turns:                     │
        │        customer_simulator (OpenAI, wrapped)      │
        │              │                                    │
        │        POST /bot/message  ──[trace headers]──►  FastAPI
        │                                                    │
        │                                             bot_engine.handle_message
        │                                             create_react_agent.ainvoke
        │                                               ├─ search_catalog
        │                                               ├─ create_lead
        │                                               └─ confirm_order
        │                                                  (all nest under
        │                                                   the same trace,
        │                                                   via §6)
        │        │                                         │
        │   DB snapshot (leads/orders/messages)  ◄──────────┘
        │        │                                         │
        │   returns {transcript, db_snapshot, ...}          │
        └───────────────────────────────────────────────┘
                                │
                                ▼
                 evaluators run against (inputs, outputs)
                 ├─ order_status_matches      (deterministic)
                 ├─ no_forbidden_order        (deterministic)
                 ├─ price_matches_order_total (deterministic)
                 ├─ payment_never_mentioned   (deterministic)
                 ├─ channel_rejection_ok      (deterministic)
                 └─ llm_judge                 (LLM, migrated eval_agent.py prompt)
                                │
                                ▼
                    LangSmith Experiment
                    (viewable, comparable across runs)
```

## 4. Repo layout

```
eval/
  scenarios.yaml                 unchanged — still hand-edited, still what
                                  conversation_agent.py/eval_agent.py read
  lib.py                         unchanged — Scenario, SettingsOverride,
                                  send_bot_message, new_external_user_id all
                                  get reused, not duplicated
  conversation_agent.py          unchanged, kept during migration
  eval_agent.py                  unchanged, kept during migration
  CLAUDE.md                      update once the new pipeline is real (§8)
  LANGSMITH_PLAN.md              this file

  langsmith/
    __init__.py
    config.py                    env var loading (LANGSMITH_*, dataset name,
                                  project name), one place, not scattered
    sync_dataset.py               CLI: scenarios.yaml -> LangSmith dataset
    target.py                     the traceable scenario-runner
    evaluators.py                  deterministic + llm_judge evaluator fns
    run_experiment.py             CLI: kicks off langsmith.aevaluate()
```

Everything under `eval/langsmith_eval/` imports from `eval/lib.py` rather than
re-implementing scenario loading, settings overrides, or the bot-message
HTTP call. `Scenario` (in `lib.py`) needs one addition: read the new
`checks:` block the same way it already reads `settings:` (§5).

## 5. `scenarios.yaml` schema addition

Additive and fully optional — omitting `checks:` on a scenario changes
nothing; it just means only the LLM judge grades it, same as today.

```yaml
  - id: order_specific_item
    category: ordering_cart
    channel: website_widget
    persona: >
      ...unchanged...
    max_turns: 8
    success_criteria: >
      ...unchanged, still fed to the LLM judge verbatim...
    checks:
      expected_order_status: placed        # placed | pending_confirmation | draft | none
      payment_mention_forbidden: true
      price_must_match_order_total: true
```

Field reference (all optional, evaluators skip whatever isn't declared):

| Field | Type | Meaning |
|---|---|---|
| `expected_order_status` | enum | What `Order.status` should be for this conversation's order, if any. `none` asserts no order was created at all — use for abandonment/blocked scenarios (`cart_abandonment`, `settings_ordering_disabled`, `settings_minimum_order`, `settings_entitlement_overrides_tenant`). |
| `payment_mention_forbidden` | bool | Assistant turns must not contain payment-collection language (card/CVV/"pay now in chat"/etc.) — independent of and in addition to the server-side guardrail; this is an *external* check that the guardrail itself didn't silently regress. |
| `price_must_match_order_total` | bool | Any currency amount stated in the assistant's final confirming turn must equal `db_snapshot.orders[].total`. |
| `expected_lead_fields` | dict | e.g. `{name: Kasun, phone: "0771234567"}` — exact match against the linked lead's `fields`, for scenarios where the persona hands over fixed values worth asserting on exactly (most of them do). |
| `http_status_expected` | int | For channel/entitlement-rejection scenarios (`settings_channel_not_allowed`) — asserts the transcript recorded that HTTP status. |

Backfill incrementally — start with the ~15 scenarios where a wrong result
would otherwise be easy to miss (anything settings-driven, the guardrail
scenarios, `multi_item_cart_edit`, `bulk_quantity_order`, `contact_info_correction`).
Scenarios like `faq_question` or `vague_menu_question`, whose criteria are
inherently narrative ("answers using real info, doesn't claim ignorance"),
can stay judge-only indefinitely — that's a legitimate end state, not a gap
to fill later.

## 6. Distributed tracing (the one backend change)

**Goal:** when `target.py` calls `POST /bot/message`, the LangGraph run
`bot_engine.handle_message` kicks off should become a *child* of the
scenario's LangSmith trace, not a disconnected root run.

**Mechanism (verify exact helper names against the installed `langsmith`
SDK version when implementing — this has moved around across SDK versions,
check the current "Distributed tracing" page in LangSmith's docs):**

1. In `target.py`, before each `send_bot_message` call, get the current run
   tree (`langsmith.run_helpers.get_current_run_tree()`) and serialize it to
   headers (`run_tree.to_headers()` or equivalent). Pass those headers
   through to `httpx.post(...)` alongside the existing `X-Api-Key` header.
2. In the backend — the smallest correct hook point is the `/bot` router
   (`api/bot/...`, wherever `POST /bot/message` is defined), *not*
   `bot_engine.py` itself, so the tracing concern stays at the transport
   layer rather than leaking into business logic. Before calling
   `bot_engine.handle_message`, check for the incoming LangSmith trace
   header; if present, open a tracing context scoped to that parent for the
   duration of the request (LangSmith's SDK provides a context manager for
   exactly this — e.g. `tracing_context(parent=...)` at time of writing).
   If the header is absent (i.e. every real customer request, and the
   existing `--all` local harness run without this plumbing), this is a
   no-op — real traffic is completely unaffected.
3. Guard this behind `settings.langsmith_tracing_enabled` (or simply: only
   do anything if the header is present, which is self-guarding) so
   there's no risk of it firing for production traffic. This is a few lines
   in the router, not a new dependency the whole app takes on — `langsmith`
   becomes a dependency either way once tracing is on for the bot itself
   (it already would be, since `LANGSMITH_TRACING=true` instruments
   LangChain/LangGraph globally).

**Fallback if this turns out fiddlier than expected:** ship without it
first. Every bot turn will still show up in LangSmith as its own root trace
(searchable/filterable by `conversation_id` or a `scenario_id` tag passed
via `langsmith_extra={"metadata": {...}}` on the call, or via
`LANGCHAIN_PROJECT` scoping) — you lose the single-nested-trajectory view but
keep per-turn tool-call visibility, which is most of the value. Add §6 once
the rest of the pipeline works end to end.

## 7. `target.py` — the traceable scenario runner

Interface, not a full implementation (you're writing this part):

```python
from langsmith import traceable

@traceable(name="scenario_conversation", run_type="chain")
async def run_scenario(inputs: dict) -> dict:
    """inputs come from the LangSmith dataset example:
    {scenario_id, persona, channel, max_turns, tenant_settings, admin_settings}

    Returns the dict LangSmith stores as this run's `outputs` — same shape
    conversation_agent.py already produces (transcript, db_snapshot,
    conversation_id, settings_overrides, run_context), so evaluators can
    reuse the exact same field paths eval_agent.py's judge prompt already
    depends on.
    """
```

Body, reusing `eval/lib.py` as-is:

- Rebuild a `Scenario`-shaped object from `inputs` (or just pass the
  original `Scenario` through dataset metadata — see §8 on what actually
  needs to round-trip through LangSmith vs. what can stay a local lookup by
  `scenario_id`).
- `with SettingsOverride(scenario):` — unchanged from `conversation_agent.py`.
- The customer-simulator loop is *nearly* a straight lift of
  `conversation_agent.run_scenario`'s body. The two differences:
  1. Attach the current run tree's trace headers to each `send_bot_message`
     call (§6).
  2. Wrap the simulator's `OpenAI` client with
     `langsmith.wrappers.wrap_openai(...)` so its calls show up as traced
     children too — optional, but cheap and useful when a scenario's
     conversation goes somewhere unexpected and you want to know if that was
     the simulator improvising oddly vs. the bot misbehaving.
- Snapshot the DB exactly as `conversation_agent._snapshot_db` does today —
  lift that function verbatim (or import it; consider moving it into
  `lib.py` since both harnesses now need it).

## 8. Dataset sync — `sync_dataset.py`

One `Example` per scenario. Keep it boring and idempotent:

- `inputs`: `{scenario_id, persona, channel, max_turns, tenant_settings, admin_settings, category}`.
- `outputs` (LangSmith's "reference" side): `{success_criteria, checks}` —
  there is no single "correct transcript" to diff against (this is a
  trajectory eval, not QA-pair eval, exactly as the ChatGPT answer noted),
  so `outputs` here just carries what the evaluators need to grade against,
  not an expected answer.
- Use `scenario_id` as the stable identity for upsert: list existing
  examples in the dataset, diff against `scenarios.yaml` by id, `update`
  changed ones, `create` new ones, and — deliberately — **report** (don't
  silently delete) examples that exist in LangSmith but no longer exist in
  the YAML, so a typo'd id rename doesn't quietly orphan history.
- Run this manually after editing `scenarios.yaml`, same mental model as
  `alembic upgrade head` after a migration — a deliberate sync step, not
  something that runs implicitly.

## 9. Evaluators — `evaluators.py`

Each evaluator is a plain function LangSmith calls with (at minimum) the
example's `inputs`/`outputs` (reference) and the target's `outputs` (actual)
— exact signature depends on whether you use `evaluate()`'s
`(run, example) -> dict` form or the newer `(inputs, outputs,
reference_outputs) -> dict` form; pick one and use it consistently. Each
returns `{"key": "...", "score": 0|1, "comment": "..."}` (or `None`/skip
entirely when the relevant `checks:` field isn't set on that scenario —
don't score a dimension that scenario never declared an opinion about).

| Evaluator | Type | Reads | Checks |
|---|---|---|---|
| `order_status_matches` | deterministic | `checks.expected_order_status`, `db_snapshot.orders` | The order's actual status (or absence) matches what's declared. `none` = assert zero orders with status in `{placed, pending_confirmation}`. |
| `lead_fields_match` | deterministic | `checks.expected_lead_fields`, `db_snapshot.leads` | Exact field match on the linked lead, when declared. |
| `price_matches_order_total` | deterministic | `checks.price_must_match_order_total`, transcript, `db_snapshot.orders[].total` | Reuse `services.money.extract_amounts` (already imported cross-process in `bot_engine.py`; `eval/lib.py` already puts `src/` on `sys.path`, so this import works from the eval side too) against the assistant's confirming turn. |
| `payment_never_mentioned` | deterministic | `checks.payment_mention_forbidden`, transcript | Keyword/regex scan for payment-collection language across all assistant turns — independent verification of the server-side guardrail, not a replacement for it. |
| `http_status_matches` | deterministic | `checks.http_status_expected`, transcript | For channel/entitlement rejection scenarios. |
| `llm_judge` | LLM | full transcript, `db_snapshot`, `success_criteria` | Straight port of `eval_agent.py`'s `_judge_prompt`/`grade_result` — same anti-bias instructions (db_facts-first, the confirmation-dispute counter-instruction), same `gpt-4o`. Don't regress the hard-won prompt tuning by starting over with a generic off-the-shelf judge template. |
| `llm_judge_suspect_free` | deterministic, folded into `llm_judge` | `_is_confirmation_false_positive`, `db_snapshot.orders` | Built as a second `EvaluationResults` entry returned alongside `llm_judge`'s own score (from the same function call) rather than a separate top-level evaluator — avoids depending on evaluator execution order/shared state to see the judge's own issues list. Only emitted when the judge actually raised issues to check. |

`llm_judge`'s known bias (documented at length in `eval_agent.py`'s
docstring — the judge disputing an order's confirmation status even while
quoting `db_facts` that show `status="placed"`) doesn't go away by moving
platforms. Keep treating `fail`/`partial` `llm_judge` verdicts as a
prompt to go read the trace, not ground truth — LangSmith's per-run trace
view is a better tool for that "go read it yourself" step than the current
flow of opening a `.json` file by hand, which is itself a concrete
observability win from this migration.

## 10. Running & comparing experiments — `run_experiment.py`

```python
from langsmith import aevaluate

await aevaluate(
    run_scenario,
    data="business-chatbot-scenarios",
    evaluators=[order_status_matches, lead_fields_match, ...],
    experiment_prefix=f"bot-{git_sha}",       # or a prompt-version tag
    max_concurrency=3,                         # see the concurrency note below
    metadata={"git_sha": git_sha, "llm_model": ...},
)
```

- **Concurrency and the settings-override race.** `SettingsOverride` (in
  `lib.py`) mutates a real tenant's settings via the live API and restores
  them afterward. Two dataset examples running concurrently that both touch
  settings (any `settings_*` scenario) can race and leave the wrong value in
  place for whichever one reads it mid-flight — the exact same hazard exists
  in principle in the current `--all` runner too, except that one is
  strictly sequential, so it's never actually hit it. `aevaluate`'s
  concurrency needs *either* `max_concurrency=1` for the whole eval run
  (slow but safe, and honestly fine for 49 scenarios), *or* two separate
  `aevaluate()` calls — one over a dataset split/filter of
  non-`settings_driven`-category scenarios at real concurrency, one over the
  `settings_driven` category at `max_concurrency=1`. Decide this before
  wiring it up; don't discover it from a flaky run.
- **Experiment naming**: tag experiments by what actually changed between
  runs (prompt version, model, git sha) so LangSmith's comparison view is
  meaningful — `experiment_prefix` plus `metadata` both matter here.
- **Comparison itself needs no new code** — this is LangSmith's built-in
  Datasets & Experiments UI, once two experiments share the same dataset.
  That side-by-side "which scenarios regressed" view is the headline reason
  for this migration; nothing further to build for it.

## 11. Setup checklist

- `pyproject.toml`: add `langsmith` to the eval-relevant dependency group
  (check how `openai`/`httpx` are currently scoped in this repo's dependency
  groups and match that).
- `.env` (root, gitignored, same file `eval/lib.py` already loads):
  `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY=...`, `LANGSMITH_PROJECT=business-chatbot-eval`
  (a *separate* project from anything that might later trace real prod
  traffic — don't mix eval noise into a prod project or vice versa).
- LangSmith account + API key (new signup if none exists yet) — flag to the
  user, not something to fetch autonomously.
- Trace volume awareness: 49 scenarios × several turns × occasional re-runs
  adds up in trace count reasonably fast on a free/trial tier. Worth
  checking LangSmith's current plan limits before running `--all` on repeat
  during development; iterate on a small scenario subset (`--scenario`
  equivalent / dataset splits) while building this out, save full-`--all`
  runs for actual comparisons.

## 12. Migration/rollout order

1. `sync_dataset.py` — get the 49 scenarios into a LangSmith dataset. Purely
   additive, no runtime risk, immediately gives a look at the dataset UI.
2. `target.py` **without** §6's distributed tracing — plain HTTP calls,
   normal per-turn tracing. Run one scenario through `aevaluate()` with zero
   evaluators to confirm the plumbing (dataset → target → outputs stored)
   works before adding grading.
3. `evaluators.py`'s deterministic checks only, against 3–4 scenarios that
   already have `checks:` entries. Confirm scores land correctly and
   `None`-skipping behaves for scenarios without `checks:`.
4. Port `llm_judge` from `eval_agent.py`. Compare its verdict against
   `eval_agent.py`'s own verdict on the same saved transcript for a handful
   of scenarios — they should agree, since it's the same prompt.
5. Wire up §6 distributed tracing. Confirm in the LangSmith UI that a
   scenario's trace tree now shows nested tool calls under the customer
   turns, not just a bare HTTP span.
6. Run `--all` equivalent, compare pass/fail against `eval_agent.py --summary`'s
   current output on the same scenario set as a sanity check that nothing
   was lost in translation.
7. Decide whether to fully retire `conversation_agent.py`/`eval_agent.py` or
   keep the lightweight local one for quick iteration and reserve LangSmith
   runs for actual before/after comparisons. Either is reasonable — this
   plan doesn't force that call.

## 13. Open questions — resolved during implementation

- **Distributed-tracing API name/shape (§6)**: confirmed against the actual
  installed `langsmith==0.12.1` — `RunTree.to_headers()` on the sending
  side, `langsmith.run_helpers.tracing_context(parent=dict(request.headers))`
  on the receiving side, gated on the `langsmith-trace` header key
  (`langsmith.run_trees.LANGSMITH_DOTTED_ORDER`). Verified by inspecting
  the installed package directly, not guessed from memory — re-check if the
  pinned version changes materially.
- **Evaluator signature style**: settled on `(run, example) -> dict | None`
  for every evaluator in `evaluators.py` — matches `EVALUATOR_T`'s
  `Callable[[schemas.Run, Optional[schemas.Example]], ...]` form in the
  installed SDK. `None` is used deliberately (not a `0` score) when a
  scenario's `checks:` block doesn't declare an opinion on that dimension.
- **`db_snapshot`'s async DB access under concurrency**: not yet stress-
  tested above `max_concurrency=1` (the documented default in
  `run_experiment.py` — see §10). Each call still opens/closes its own
  `AsyncSessionLocal()`, same as `conversation_agent._snapshot_db`, so it's
  expected to be fine, but this wants an actual run at higher concurrency
  before trusting it — and note `target.py`'s simulator/HTTP calls are
  currently blocking (sync `httpx`/`OpenAI` calls inside an `async def`),
  so raising `max_concurrency` won't buy real parallelism until those move
  to async clients. Left as a follow-up, not a blocker for the default
  concurrency=1 path this ships with.

Still genuinely open (not attempted this pass):

- Whether to eventually retire `conversation_agent.py`/`eval_agent.py`
  (§12 step 7) — no data yet on how the two compare side by side.
  `evaluators.llm_judge` has not been cross-checked against
  `eval_agent.py`'s own verdict on the same saved transcript.
- No scenario has actually been run end to end through `aevaluate()`
  against a live LangSmith project yet (no `LANGSMITH_API_KEY` configured
  in this environment) — `sync_dataset.py`/`evaluators.py`/`target.py` are
  verified by unit-level checks (see the implementation notes below) and a
  real auth error confirms the network path is reached correctly, but a
  full live run is the next step, not something this pass could complete.
