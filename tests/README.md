# Tests

```
pytest                 # everything
pytest -m "not db"     # offline unit tests only -- no database needed
pytest tests/agent     # one folder
```

Run from the repo root.

## Test database

Database tests need a **separate, throwaway** Postgres database with the
`pgvector` extension available. Copy `.env.test.example` to `.env.test` and set
`TEST_DATABASE_URL` (or export it as an environment variable).

- The database name must contain `test` -- the suite refuses to run otherwise,
  because it truncates every tenant table before and after each test.
- `DATABASE_URL` from `.env` is **never** used: `conftest.py` overwrites it
  before the app is imported, so tests can't reach the dev database.
- The database is created on first run (if the user may `CREATE DATABASE`) and
  migrated with the real Alembic migrations (`alembic upgrade head`).
- Without `TEST_DATABASE_URL`, DB tests are skipped and unit tests still run.

## Nothing leaves the machine

- **Embeddings**: `fakes.fake_embed_texts` -- a hashed bag-of-words vector, so
  texts sharing words are genuinely similar and retrieval behaves realistically.
- **Chat model**: `fakes.ScriptedChatModel` replays scripted `AIMessage`s
  (including tool calls), driving the real LangGraph agent, real tools and real
  database. Patch it in with `monkeypatch.setattr(bot_engine, "_get_model", ...)`.
- **Email**: the autouse `outbox` fixture captures every email sent.
- `OPENAI_API_KEY` is set to an invalid value and LangSmith tracing is off, so
  anything that slips past the fakes fails loudly instead of costing money.

The real-LLM checks live in `eval/`, run separately.

## Layout

| Folder | What | Needs DB |
|---|---|---|
| `unit/` | pure logic: guardrails, prompt builder, money, lead status rules, schemas, import-boundary (architecture) checks, parsing | no |
| `db/` | repos and services against Postgres: tenant isolation, order/lead rules, race conditions, publishing, settings resolver, onboarding, bot tools | yes |
| `api/` | HTTP routes via `httpx.ASGITransport`: auth, access control, every dashboard/superadmin/bot route | yes |
| `agent/` | whole bot turns via `POST /bot/message` with a scripted model | yes |

Shared helpers: `conftest.py` (environment, DB lifecycle, `session`/`client`
fixtures), `factories.py` (tenants, generic catalog, conversations, auth
headers), `fakes.py` (the offline stand-ins above).

Follow the repo rule from AGENTS.md when adding tests: assert on database rows,
not only on what the bot's reply claims.
