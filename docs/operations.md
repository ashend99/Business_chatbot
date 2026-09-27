# Operations runbook

Running the platform once it's deployed (see [deployment.md](deployment.md)).

## Error tracking (Sentry)

The backend reports unhandled errors to Sentry when `SENTRY_DSN` is set
(`app/core/observability.py`); without it Sentry is off.

1. Create a Sentry project (platform: FastAPI) and copy its DSN.
2. Render → backend service → Environment: `SENTRY_DSN=<dsn>`. Optional:
   `SENTRY_TRACES_SAMPLE_RATE` (default `0.05` = 5% of requests traced).
3. Redeploy. Errors are tagged with `ENVIRONMENT`.

Privacy: customer chats contain names, phone numbers and addresses, so the
SDK is configured to send **no** request bodies, local variables or user/IP
details -- only the exception and stack trace. Keep it that way.

Frontends: runtime errors from `client_ui`/`admin_ui` are in each Vercel
project's Logs tab. Adding `@sentry/nextjs` later is done per app with
`npx @sentry/wizard@latest -i nextjs` (interactive, needs the Sentry login).

## Uptime monitoring

Point an uptime monitor (Better Stack, UptimeRobot, ...) at
`https://<backend-domain>/health/ready` every 1-5 minutes. It checks the
database too, so it catches a Supabase outage, not just a crashed container.
(`/health` is the host's liveness probe and deliberately skips the DB.)

## Cost and abuse protection

- **Burst limits** on `POST /bot/message`, per customer and per tenant
  (`bot.rate_limit` in `project_config.yaml`, default 20 and 300 per minute).
  Over the limit the request gets `429` with `Retry-After` before anything is
  stored or any LLM call is made. Limits are per backend process -- exact
  with one instance; move them to Redis/Postgres before scaling out.
- **Monthly quota** per tenant: admin settings `monthly_message_limit`
  (superadmin API / admin UI; empty = unlimited). Counts customer messages
  in the tenant's calendar month (its own timezone). Past the limit the bot
  goes silent exactly like `bot_enabled=false` -- messages are still stored
  for staff -- and the response carries a `message_limit_reached` action.
- **OpenAI spend cap**: give production its own OpenAI project and set a
  monthly budget/limit on it in the OpenAI dashboard -- the backstop if
  everything above is misconfigured.

## Backups

Customer data (leads, orders, transcripts) lives only in Postgres.

- **Supabase**: daily backups come with the Pro plan (the free plan has no
  project backups -- don't run production on it). Point-in-time recovery is a
  paid add-on worth enabling once there are real orders.
- **Your own copy** (monthly, and before risky migrations), from a machine
  with the Postgres client tools:

  ```
  pg_dump "<MIGRATION_DATABASE_URL without the +psycopg>" --format=custom --no-owner --file=backup-YYYY-MM-DD.dump
  ```

  The dump contains customer personal data: keep it encrypted, off shared
  drives, and delete old ones.

### Restore drill (do this once now, then every few months)

A backup you've never restored is a guess. Restore into a **scratch**
database, never production:

1. Create an empty database with pgvector (a local Postgres, or a throwaway
   Supabase project), then `CREATE EXTENSION IF NOT EXISTS vector;`.
2. `pg_restore --no-owner --dbname="<scratch url>" backup-YYYY-MM-DD.dump`
3. Check it: `MIGRATION_DATABASE_URL=<scratch url> alembic current` shows
   the expected head, and row counts of `tenants`, `leads`, `orders` match
   production.
4. Drop the scratch database.

For Supabase's own backups, use Database → Backups → Restore -- to a new
project when drilling, not over production.

## Incident quick reference

| Symptom | First check |
|---|---|
| Bot replies with the fallback message | Sentry / Render logs for the agent error; OpenAI status and key |
| `/health/ready` 503 | Supabase status; `DATABASE_URL` still valid |
| Deploy stuck / failed | Render deploy logs -- a failed `alembic upgrade head` stops the new container and the previous version keeps serving |
| Tenant says bot went silent | admin settings: `bot_enabled`, `monthly_message_limit`; tenant's `allowed_channels` |
| Emails not arriving | `EMAIL_BACKEND=smtp` and `SMTP_*` on Render; provider's sending logs |
