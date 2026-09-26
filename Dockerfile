# Backend image (FastAPI). The two Next.js apps deploy to Vercel instead.
#
#   docker build -t business-chatbot-backend .
#   docker run --env-file .env -p 8000:8000 business-chatbot-backend
#   docker run --env-file .env business-chatbot-backend alembic upgrade head   # migrations
#
# Migrations are a separate release step, never run on startup: several app
# instances starting at once must not race to migrate.

# ---- builder: resolve dependencies with uv from the lockfile -----------------
FROM python:3.11-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app
COPY pyproject.toml uv.lock ./
# dependencies only (no dev tools, not the project itself): the app runs from
# /app/src via PYTHONPATH, same as locally
RUN uv sync --locked --no-dev --no-install-project

# ---- runtime -----------------------------------------------------------------
FROM python:3.11-slim

RUN useradd --create-home --uid 1000 app

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src ./src
COPY database ./database
COPY alembic.ini project_config.yaml ./

# PROJECT_HOME: where common/config.py finds project_config.yaml
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PROJECT_HOME=/app \
    PYTHONUNBUFFERED=1 \
    PORT=8000

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=4)"

# PORT is injected by the host (Railway/Render/Fly); --proxy-headers because
# the app always sits behind the platform's TLS-terminating proxy
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
