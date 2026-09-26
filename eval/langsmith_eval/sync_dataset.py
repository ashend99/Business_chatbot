"""Sync eval/scenarios.yaml -> a LangSmith dataset, one Example per scenario.

scenarios.yaml stays the source of truth (hand-edited, same as it is for
conversation_agent.py/eval_agent.py today) -- this script is the deliberate
sync step after editing it, the same mental model as running an Alembic
migration after changing a model.

Idempotent: each scenario gets a deterministic example id
(uuid5 of its scenario id), so re-running after editing scenarios.yaml
updates existing examples in place instead of duplicating them. Examples
that exist in the dataset but no longer match any scenario id are reported,
not deleted automatically -- a renamed/typo'd id shouldn't silently orphan
history; remove it by hand once you've confirmed it's intentional.

Usage (from the project root):
    uv run python eval/langsmith_eval/sync_dataset.py
    uv run python eval/langsmith_eval/sync_dataset.py --dry-run
"""

import config  # noqa: F401,I001  -- sets up sys.path before the imports below

import argparse
import uuid

from langsmith import Client

from lib import Scenario, load_scenarios

# Arbitrary, fixed namespace UUID -- only used to derive stable per-scenario
# example ids via uuid5(namespace, scenario_id). Never change this once real
# data exists in the dataset, or every example id derived from it changes,
# turning every "update" into a duplicate "create" on the next sync.
_EXAMPLE_ID_NAMESPACE = uuid.UUID("a7f0a6d1-8b1e-4c1a-9e9b-3b6a1f0d9c2a")


def _example_id(scenario_id: str) -> uuid.UUID:
    return uuid.uuid5(_EXAMPLE_ID_NAMESPACE, scenario_id)


def _inputs_for(scenario: Scenario) -> dict:
    return {
        "scenario_id": scenario.id,
        "persona": scenario.persona,
        "channel": scenario.channel,
        "max_turns": scenario.max_turns,
        "tenant_settings": scenario.tenant_settings,
        "admin_settings": scenario.admin_settings,
        "category": scenario.category,
    }


def _outputs_for(scenario: Scenario) -> dict:
    # Not "expected answers" -- this is a trajectory eval, there's no single
    # correct transcript. `outputs` here just carries what the evaluators
    # (eval/langsmith_eval/evaluators.py) grade the target's actual output
    # against.
    return {
        "success_criteria": scenario.success_criteria,
        "checks": scenario.checks,
    }


def sync(dry_run: bool = False) -> None:
    client = Client()
    scenarios = load_scenarios()

    dataset_exists = client.has_dataset(dataset_name=config.DATASET_NAME)
    if not dataset_exists:
        if dry_run:
            print(f"[dry-run] would create dataset {config.DATASET_NAME!r}")
        else:
            client.create_dataset(
                config.DATASET_NAME,
                description=(
                    "Simulated-customer scenarios for the bot agent "
                    "(services/bot_engine.py), synced from eval/scenarios.yaml. "
                    "See eval/LANGSMITH_PLAN.md."
                ),
            )
            print(f"created dataset {config.DATASET_NAME!r}")
            dataset_exists = True

    existing = {}
    if dataset_exists:
        existing = {ex.id: ex for ex in client.list_examples(dataset_name=config.DATASET_NAME)}

    seen_ids: set[uuid.UUID] = set()
    created, updated = 0, 0
    for scenario in scenarios:
        ex_id = _example_id(scenario.id)
        seen_ids.add(ex_id)
        inputs, outputs = _inputs_for(scenario), _outputs_for(scenario)
        metadata = {"scenario_id": scenario.id, "category": scenario.category}

        if ex_id in existing:
            if dry_run:
                print(f"[dry-run] would update {scenario.id}")
            else:
                client.update_example(ex_id, inputs=inputs, outputs=outputs, metadata=metadata)
            updated += 1
        else:
            if dry_run:
                print(f"[dry-run] would create {scenario.id}")
            else:
                client.create_example(
                    inputs=inputs,
                    outputs=outputs,
                    metadata=metadata,
                    dataset_name=config.DATASET_NAME,
                    example_id=ex_id,
                )
            created += 1

    orphaned = [ex for ex_id, ex in existing.items() if ex_id not in seen_ids]
    suffix = " (dry run, nothing written)" if dry_run else ""
    print(f"\n{created} to create, {updated} to update{suffix}")
    if orphaned:
        print(
            f"\n{len(orphaned)} example(s) in the dataset no longer match a "
            "scenario id in scenarios.yaml -- NOT deleted automatically:"
        )
        for ex in orphaned:
            sid = (ex.metadata or {}).get("scenario_id", "?")
            print(f"  - {sid} (example id {ex.id})")
        print(
            "Remove by hand (LangSmith UI, or client.delete_example) if this "
            "is an intentional removal/rename; otherwise fix the id mismatch "
            "in scenarios.yaml."
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would change without writing anything."
    )
    args = parser.parse_args()
    sync(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
