# Working in this repo

Practical, action-oriented notes for anyone (human or agent) picking up this
codebase. For what the system *is* — modules, the agent's tools, the data
model — read [architecture_v0.1.md](architecture_v0.1.md) first. This file
is about how to actually run and modify it without rediscovering the same
gotchas.

## Running things locally

**Backend** — from the repo root, not `src/`:

```
python -m app.main
```

Not `uvicorn app.main:app`. Windows' `psycopg` async driver can't use the
default `ProactorEventLoop`; `main.py` sets
`asyncio.WindowsSelectorEventLoopPolicy()` at import time, but the bare
`uvicorn` CLI form imports the app *inside* `asyncio.run()`, too late for
the policy to take effect. `python -m app.main` runs it via the module's
own `__main__` block, which sets the policy first. See the comment at the
top of `src/app/main.py`. (`uvicorn app.main:app --reload` does work once
you're past this — the reloader subprocess still goes through the same
`__main__` path on each respawn.)

**Frontend** — `cd client_ui && npm run dev`, served at `localhost:3000`.
Login: `demo` / `changeme123` (tenant `dulas_kitchen`, the one seeded dev
tenant). A standalone `/widget-test` page (no dashboard login) exercises the
bot directly like a real embedded chat widget would.

**Eval harness** — `cd eval` (its scripts assume being run from that
directory, or `python eval/conversation_agent.py` from the root works too
since Python adds the script's own directory to `sys.path`). See
`eval/CLAUDE.md` for details.

**Migrations** — `alembic upgrade head` from the repo root (`alembic.ini`
points `script_location` at `database/alembic`).

## Environment gotchas worth knowing before you hit them

- **`websockets` package corruption.** This has recurred several times:
  `uv sync` reports `Failed to uninstall package ... due to missing RECORD
  file` and leaves broken `websockets-*.dist-info` folders in
  `.venv/Lib/site-packages/` (missing `__init__.py`, `ImportError: cannot
  import name '__version__' from 'websockets'`). Re-running `uv sync` alone
  does **not** fix it — it just inherits the same corruption. Fix: delete
  `.venv/Lib/site-packages/websockets/` and every `websockets-*.dist-info/`
  folder by hand, then `uv sync --reinstall-package websockets`. Likely
  cause: antivirus/Windows Defender real-time protection interfering with
  writes to the compiled `.pyd` speedups binary — adding `.venv` to Defender
  exclusions would probably stop it recurring, but that needs admin rights.
- **Low-RAM `next build` OOM.** `client_ui`'s dev machine can have very
  little free RAM. If `next build` dies, kill stray node/python/chrome
  processes and build with
  `NODE_OPTIONS=--max-old-space-size=1500-2560 npm run build`.
- **Windows process ghosts.** Killing a backgrounded `uvicorn --reload`
  process by PID sometimes leaves the actual socket-holding process
  invisible to `Get-Process` but still `LISTENING` per `netstat`. Find the
  real holder via `Get-CimInstance Win32_Process` (look for the
  `multiprocessing.spawn_main(parent_pid=...)` child), kill that first,
  then the parent.

## Conventions to follow

- **Every tenant-scoped query goes through `tenant_scope()`**
  (`src/app/repos/tenant_scope.py`), never a bare `.where(Model.tenant_id ==
  ...)`. This is the entire multi-tenancy isolation mechanism at the app
  layer — skipping it is a cross-tenant data leak, not a style nit.
- **The bot/admin repo split is a hard boundary, not a convention.**
  `repos/leads.py` (bot-write-only) vs `repos/leads_admin.py`
  (dashboard read/update), same split for `repos/orders.py` vs
  `repos/orders_admin.py`. The `/bot` router, `bot_engine.py`, and
  `bot_tools.py` must never import an `_admin` module — the bot can create
  leads/orders but never read existing ones back (see
  architecture_v0.1.md's agent section for why). New tenant-scoped modules
  that the bot also touches should follow the same split.
- **New agent tools need a guardrail if they state a fact the LLM could
  misstate.** The pattern established for pricing and order-confirmation in
  `bot_engine.py`: after generation, check the reply against what the
  tool(s) actually returned/wrote, and override the reply if it disagrees.
  Learned the hard way this session — prompt instructions alone ("relay
  the exact price", "only confirm after the tool succeeds") are not
  reliable enough on their own; pair them with a mechanical check.
- **Verify against the real system, not the LLM's account of it.** The
  single most repeated pattern this session: when testing a bot behavior,
  don't trust the chat reply — query the database directly (`Order`/`Lead`
  rows) to see what actually happened. This caught real bugs (a "confirmed"
  order that was still `draft`, duplicate leads from a race condition,
  duplicate `actions` in the API response) that reading the chat transcript
  alone would have missed. The same principle applies to the eval harness's
  LLM judge — see `eval/eval_agent.py`'s documented bias and treat
  `fail`/`partial` verdicts as a prompt to go read the transcript, not as
  ground truth.
- **Don't hardcode one tenant's business into shared code, prompts, or
  test data.** This platform is explicitly multi-vertical (see the
  Leads/Orders design discussion in git history / architecture doc) —
  `dulas_kitchen` is the one seeded dev tenant, not a template to encode
  assumptions around. This applies to `eval/scenarios.yaml` personas too:
  describe customer *behavior*, not this tenant's specific menu items.
