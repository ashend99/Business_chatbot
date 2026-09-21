"""Shared config/helpers for the eval/ harness.

Run scripts in this directory from the project root, e.g.:
    uv run python eval/conversation_agent.py --scenario order_specific_item
    uv run python eval/eval_agent.py --all

Both scripts talk to the real backend over HTTP (POST /bot/message) rather
than importing bot_engine directly -- this exercises the exact same path a
real channel adapter (n8n, the website widget, WhatsApp) would use, not a
shortcut around it. The backend must already be running.
"""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIOS_PATH = Path(__file__).resolve().parent / "scenarios.yaml"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

sys.path.insert(0, str(PROJECT_ROOT / "src"))

load_dotenv(PROJECT_ROOT / ".env")

import os  # noqa: E402

API_BASE_URL = os.environ.get("EVAL_API_BASE_URL", "http://127.0.0.1:8000")
BOT_API_KEY = os.environ.get("EVAL_BOT_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
TENANT_USERNAME = os.environ.get("EVAL_TENANT_USERNAME", "demo")
TENANT_PASSWORD = os.environ.get("EVAL_TENANT_PASSWORD")
SUPERADMIN_EMAIL = os.environ.get("SUPERADMIN_EMAIL")
SUPERADMIN_PASSWORD = os.environ.get("SUPERADMIN_PASSWORD")


class Scenario:
    def __init__(self, data: dict):
        self.id: str = data["id"]
        self.channel: str = data.get("channel", "website_widget")
        self.persona: str = data["persona"]
        self.success_criteria: str = data["success_criteria"]
        self.max_turns: int = data.get("max_turns", 8)
        # Optional per-scenario settings overrides, applied through the real
        # settings APIs before the conversation and restored afterwards:
        #   settings: {tenant: {ordering_enabled: false}, admin: {currency_code: EUR}}
        settings: dict = data.get("settings") or {}
        self.tenant_settings: dict = settings.get("tenant") or {}
        self.admin_settings: dict = settings.get("admin") or {}


def load_scenarios() -> list[Scenario]:
    with open(SCENARIOS_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [Scenario(d) for d in data["scenarios"]]


def get_scenario(scenario_id: str) -> Scenario:
    for s in load_scenarios():
        if s.id == scenario_id:
            return s
    raise ValueError(f"no scenario named {scenario_id!r} in {SCENARIOS_PATH}")


def new_external_user_id(scenario_id: str) -> str:
    """eval- prefix marks these conversations as eval-harness-generated, not
    a real customer -- same convention as the manual "test-*" ids used
    throughout this project's own verification scripts, so they're easy to
    find/prune in bulk later without touching real data."""
    return f"eval-{scenario_id}-{uuid.uuid4().hex[:8]}"


def send_bot_message(channel_type: str, external_user_id: str, text: str) -> dict:
    if not BOT_API_KEY:
        raise RuntimeError("EVAL_BOT_API_KEY is not set in .env")
    resp = httpx.post(
        f"{API_BASE_URL}/bot/message",
        json={"channel_type": channel_type, "external_user_id": external_user_id, "text": text},
        headers={"X-Api-Key": BOT_API_KEY},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def result_path(scenario_id: str, run_id: str) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESULTS_DIR / f"{scenario_id}__{run_id}.json"


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ---- per-scenario settings overrides ----------------------------------------
#
# Applied through the real APIs (not straight into the DB) so the running
# backend's in-process settings cache is invalidated -- a DB write from this
# separate process would be invisible to the server for up to the cache TTL.


def _api(method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = httpx.request(method, f"{API_BASE_URL}{path}", json=body, headers=headers, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {resp.status_code}: {resp.text}")
    return resp.json()


def _tenant_token() -> str:
    if not TENANT_PASSWORD:
        raise RuntimeError("EVAL_TENANT_PASSWORD is not set in .env (needed for scenarios with settings overrides)")
    return _api("POST", "/auth/tenant/login", body={"username": TENANT_USERNAME, "password": TENANT_PASSWORD})[
        "access_token"
    ]


def _admin_token_and_tenant(tenant_token: str) -> tuple[str, str]:
    import base64
    import json as _json

    if not (SUPERADMIN_EMAIL and SUPERADMIN_PASSWORD):
        raise RuntimeError("SUPERADMIN_EMAIL/SUPERADMIN_PASSWORD are not set in .env (needed for admin overrides)")
    payload = tenant_token.split(".")[1]
    tenant_id = _json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["sub"]
    token = _api("POST", "/superadmin/auth/login", body={"email": SUPERADMIN_EMAIL, "password": SUPERADMIN_PASSWORD})[
        "access_token"
    ]
    return token, tenant_id


class SettingsOverride:
    """Context manager: apply a scenario's tenant/admin settings overrides,
    always restore the previous values on exit (even if the run crashes), and
    expose the tenant's local "now" for date-awareness scenarios."""

    def __init__(self, scenario: "Scenario"):
        self.scenario = scenario
        self.tenant_token: str | None = None
        self.admin_token: str | None = None
        self.tenant_id: str | None = None
        self._tenant_before: dict = {}
        self._admin_before: dict = {}
        self.timezone: str = "UTC"

    def __enter__(self) -> "SettingsOverride":
        self.tenant_token = _tenant_token()
        current = _api("GET", "/tenant/settings", self.tenant_token)["settings"]
        self.timezone = current["timezone"]
        if self.scenario.admin_settings:
            self.admin_token, self.tenant_id = _admin_token_and_tenant(self.tenant_token)
            admin_now = _api("GET", f"/superadmin/tenants/{self.tenant_id}/settings", self.admin_token)
            self._admin_before = {k: admin_now[k] for k in self.scenario.admin_settings}
            _api("PATCH", f"/superadmin/tenants/{self.tenant_id}/settings", self.admin_token, self.scenario.admin_settings)
        if self.scenario.tenant_settings:
            self._tenant_before = {k: current[k] for k in self.scenario.tenant_settings}
            _api("PATCH", "/tenant/settings", self.tenant_token, self.scenario.tenant_settings)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._tenant_before and self.tenant_token:
            _api("PATCH", "/tenant/settings", self.tenant_token, self._tenant_before)
        if self._admin_before and self.admin_token and self.tenant_id:
            _api("PATCH", f"/superadmin/tenants/{self.tenant_id}/settings", self.admin_token, self._admin_before)

    def local_now(self) -> str:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(self.timezone)).strftime("%A, %d %B %Y, %I:%M %p (%Z)")
