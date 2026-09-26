"""Runs the full scenario dataset through langsmith.aevaluate() against the
real backend (must already be running -- `python -m app.main` from the
project root, see AGENTS.md) and the deterministic + llm_judge evaluators.

Usage (from the project root):
    uv run python eval/langsmith_eval/run_experiment.py
    uv run python eval/langsmith_eval/run_experiment.py --max-concurrency 4
    uv run python eval/langsmith_eval/run_experiment.py --prefix bot-prompt-v2
    uv run python eval/langsmith_eval/run_experiment.py --category ordering_cart

Split into two aevaluate() calls under one experiment, not one:
`settings_driven`-category scenarios mutate a real, shared tenant's settings
through the live API for the duration of each run (eval/lib.py's
SettingsOverride) and restore them afterward -- running two of those
concurrently can race and leave the wrong value in place mid-run. Every
other category runs at whatever concurrency was asked for; the
`settings_driven` category always runs at max_concurrency=1, appended into
the same experiment via the `experiment=` param so the result is one
comparable experiment, not two. See LANGSMITH_PLAN.md section 10.
"""

import config  # noqa: F401,I001  -- sets up sys.path before the imports below

import argparse
import asyncio
import subprocess
import sys

from langsmith import Client
from langsmith.evaluation import aevaluate

from evaluators import (
    http_status_matches,
    lead_fields_match,
    llm_judge,
    order_status_matches,
    payment_never_mentioned,
    price_matches_order_total,
)
from target import run_scenario

if sys.platform == "win32":
    # same reasoning as app/main.py and conversation_agent.py: psycopg's
    # async driver (used by _snapshot_db) needs the selector event loop on
    # Windows, and it must be set before any event loop is created.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

EVALUATORS = [
    order_status_matches,
    lead_fields_match,
    price_matches_order_total,
    payment_never_mentioned,
    http_status_matches,
    llm_judge,
]


def _git_sha() -> str:
    try:
        cmd = ["git", "rev-parse", "--short", "HEAD"]
        return subprocess.check_output(cmd, cwd=config.PROJECT_ROOT).decode().strip()
    except Exception:
        return "unknown"


async def _run(max_concurrency: int, prefix: str, category_filter: str | None) -> None:
    client = Client()
    all_examples = list(client.list_examples(dataset_name=config.DATASET_NAME))
    if not all_examples:
        raise SystemExit(
            f"dataset {config.DATASET_NAME!r} has no examples -- run "
            "sync_dataset.py first."
        )

    def _category(ex) -> str | None:
        return (ex.metadata or {}).get("category")

    if category_filter:
        all_examples = [ex for ex in all_examples if _category(ex) == category_filter]
        if not all_examples:
            raise SystemExit(f"no examples with category={category_filter!r}")

    settings_cat = config.SETTINGS_DRIVEN_CATEGORY
    settings_examples = [ex for ex in all_examples if _category(ex) == settings_cat]
    other_examples = [ex for ex in all_examples if ex not in settings_examples]

    metadata = {"git_sha": _git_sha()}

    experiment_name = None
    if other_examples:
        print(f"running {len(other_examples)} scenario(s) at max_concurrency={max_concurrency}...")
        results = await aevaluate(
            run_scenario,
            data=other_examples,
            evaluators=EVALUATORS,
            experiment_prefix=prefix,
            max_concurrency=max_concurrency,
            metadata=metadata,
        )
        experiment_name = results.experiment_name
        url = results.url if hasattr(results, "url") else ""
        print(f"experiment: {experiment_name}\n{url}")

    if settings_examples:
        n = len(settings_examples)
        print(f"\nrunning {n} settings-driven scenario(s) at max_concurrency=1...")
        kwargs = (
            {"experiment": experiment_name} if experiment_name else {"experiment_prefix": prefix}
        )
        results = await aevaluate(
            run_scenario,
            data=settings_examples,
            evaluators=EVALUATORS,
            max_concurrency=1,
            metadata=metadata,
            **kwargs,
        )
        print(f"experiment: {results.experiment_name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=1,
        help=(
            "Concurrency for non-settings-driven scenarios (default 1 -- raise once "
            "you've confirmed the backend/DB handle it; see LANGSMITH_PLAN.md's "
            "async-blocking caveat in target.py)."
        ),
    )
    parser.add_argument(
        "--prefix", default=None, help="Experiment name prefix (default: bot-<git sha>)."
    )
    parser.add_argument(
        "--category",
        default=None,
        help="Only run scenarios in this category (see scenarios.yaml's `category:` field).",
    )
    args = parser.parse_args()

    prefix = args.prefix or f"bot-{_git_sha()}"
    asyncio.run(_run(args.max_concurrency, prefix, args.category))


if __name__ == "__main__":
    main()
