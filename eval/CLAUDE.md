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
