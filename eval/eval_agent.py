"""Grades saved conversation transcripts (from conversation_agent.py)
against their scenario's `success_criteria`, using an LLM judge. Decoupled
from conversation_agent.py on purpose -- a transcript only needs generating
once, and can be re-graded later (e.g. after a prompt/tool change) without
re-running the conversation.

Usage (from the project root):
    uv run python eval/eval_agent.py --all
    uv run python eval/eval_agent.py --file eval/results/order_specific_item__20260101T000000Z.json
    uv run python eval/eval_agent.py --scenario order_specific_item   # grades its most recent run
    uv run python eval/eval_agent.py --all --force                   # re-grade even if already graded
    uv run python eval/eval_agent.py --summary                       # print/save a final report only,
                                                                      # from whatever is already graded
`--all`, `--file`, and `--scenario` also print a summary at the end automatically.

Known limitation, observed while building this: even after the judge
correctly quotes db_facts showing status="placed", it can still write an
issue claiming the order "wasn't really confirmed yet" -- a persistent bias
toward distrusting an assistant's own "confirmed!" language that held up
across several rounds of explicit counter-instruction in the prompt below.
The db_snapshot itself is trustworthy (it's a direct DB read, not an LLM's
account of anything); the judge's prose verdict is not infallible. Treat a
"fail"/"partial" verdict as a first-pass signal to go read the transcript
yourself, not as an authoritative result -- this is a known, general
limitation of LLM-as-judge, not something fully solvable by prompting harder.
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

from lib import OPENAI_API_KEY, RESULTS_DIR

# Matches the judge disputing whether/when an order was really confirmed --
# the exact bias documented above (module docstring), in whatever phrasing
# it happens to use ("premature", "not actually confirmed", "confirmed...
# before collecting their phone number", etc.) -- "confirm" and "before"
# both appearing within ~80 chars of each other catches that family of claim
# regardless of exact wording. If an issue matches this AND the run's own
# db_snapshot shows an order with status="placed", the claim is
# self-contradicting and gets flagged as suspect rather than trusted as-is.
_CONFIRMATION_DISPUTE_PATTERN = re.compile(
    r"confirm\w*.{0,80}\bbefore\b|\bbefore\b.{0,80}confirm\w*|\bpremature", re.IGNORECASE | re.DOTALL
)

# A stronger model than the bot itself (gpt-4o-mini, see project_config.yaml)
# -- gpt-4o-mini was tried here first and hallucinated verdicts that
# contradicted the db_snapshot sitting right in its own context (e.g.
# claiming an order wasn't placed when its status was literally "placed"),
# so grading needs more careful judgment than generation does.
JUDGE_MODEL = "gpt-4o"

_client = OpenAI(api_key=OPENAI_API_KEY)


def _judge_prompt(result: dict) -> str:
    def _line(i: int, turn: dict) -> str:
        if turn.get("http_status"):
            return f"Turn {i + 1} ({turn['role']}): [the API rejected the message: HTTP {turn['http_status']} {turn.get('http_detail', '')}]"
        text = turn["text"] if turn["text"] != "" else "[no reply -- the bot stayed silent]"
        return f"Turn {i + 1} ({turn['role']}): {text}"

    transcript_lines = "\n".join(_line(i, turn) for i, turn in enumerate(result["transcript"]))
    overrides = result.get("settings_overrides") or {}
    settings_note = (
        f"Tenant settings deliberately overridden for this scenario: {json.dumps(overrides)}\n\n"
        if overrides.get("tenant") or overrides.get("admin")
        else ""
    )
    now_note = (
        f"Business local date/time when the conversation ran: {result['run_context']['business_local_now']}\n\n"
        if result.get("run_context")
        else ""
    )
    return f"""You are grading a customer-support chat bot's behavior in a test \
conversation. You are NOT grading the simulated customer -- only the bot's \
(role "assistant") replies and actions. Grade only what the evidence below \
actually shows; do not assume a typical/expected flow.

{settings_note}{now_note}Success criteria for this scenario:
{result["success_criteria"]}

Full transcript, in order:
{transcript_lines}

Ground-truth database state after the conversation -- exactly what the \
bot's tool calls actually wrote, read directly from the database:
{json.dumps(result["db_snapshot"], indent=2)}

First, in "db_facts", quote the specific db_snapshot fields relevant to \
this scenario's criteria (e.g. the order's actual "status" value, its \
"total", its "items", the lead's "fields") verbatim -- do not paraphrase or \
infer. Then, in "reasoning", check the criteria one at a time against the \
transcript turns (citing turn numbers) and db_facts.

Two rules for interpreting the evidence correctly:
- A price, total, or item the bot stated is CORRECT, not invented, if it \
  exactly matches a value you already quoted in db_facts. Only call a \
  figure "invented" if it does NOT match db_facts.
- If db_facts shows an order's status as "placed", that order WAS \
  successfully confirmed by the end of the conversation. Full stop. Do not \
  write any issue claiming it was "not actually confirmed", "premature", \
  or "before the confirmation process completed" -- status="placed" IS the \
  completed confirmation; there is no later step it could be "before". The \
  only legitimate order-of-events criticism is the bot's own reply text \
  asserting something was done (e.g. "confirmed!") BEFORE the customer had \
  given information the criteria requires first (e.g. it confirms in one \
  turn, then only asks for their phone number in a later turn) -- and only \
  if you can cite the exact turn numbers proving that sequence.

Reply with a single JSON object:
{{
  "db_facts": "<verbatim relevant fields you copied from db_snapshot above>",
  "verdict": "pass" | "fail" | "partial",
  "reasoning": "<2-4 sentences citing specific turns/evidence, consistent with db_facts>",
  "issues": ["<specific problem, each one directly supported by the transcript or db_facts, not contradicting either>", ...]
}}
"issues" should be empty for a clean "pass". Never list an issue that contradicts db_facts."""


def grade_result(result: dict) -> dict:
    resp = _client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[{"role": "user", "content": _judge_prompt(result)}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    content = resp.choices[0].message.content or "{}"
    try:
        verdict = json.loads(content)
    except json.JSONDecodeError:
        verdict = {"verdict": "fail", "reasoning": "judge returned invalid JSON", "issues": [content]}
    return verdict


def eval_path_for(result_path: Path) -> Path:
    return result_path.with_suffix(".eval.json")


def grade_file(path: Path, force: bool) -> None:
    out_path = eval_path_for(path)
    if out_path.exists() and not force:
        print(f"skip (already graded): {path.name}")
        return

    result = json.loads(path.read_text(encoding="utf-8"))
    verdict = grade_result(result)
    out_path.write_text(json.dumps(verdict, indent=2), encoding="utf-8")

    mark = {"pass": "PASS", "fail": "FAIL", "partial": "PARTIAL"}.get(verdict.get("verdict"), "?")
    print(f"[{mark}] {result['scenario_id']} ({path.name})")
    if verdict.get("db_facts"):
        print(f"    db_facts: {verdict['db_facts']}")
    print(f"    {verdict.get('reasoning', '')}")
    for issue in verdict.get("issues", []):
        print(f"    - {issue}")


def _is_confirmation_false_positive(issue: str, db_snapshot: dict) -> bool:
    if not _CONFIRMATION_DISPUTE_PATTERN.search(issue):
        return False
    return any(order.get("status") == "placed" for order in db_snapshot.get("orders", []))


def build_summary() -> list[dict]:
    """One row per graded run: scenario id, verdict, and its issues split
    into `issues` (as reported) and `suspect_issues` (issues that dispute an
    order's confirmation while that run's own db_snapshot shows it was
    placed -- see _is_confirmation_false_positive). Rows with no matching
    .eval.json (not graded yet) are skipped."""
    result_files = sorted(p for p in RESULTS_DIR.glob("*.json") if not p.name.endswith(".eval.json"))
    rows = []
    for path in result_files:
        eval_path = eval_path_for(path)
        if not eval_path.exists():
            continue
        result = json.loads(path.read_text(encoding="utf-8"))
        verdict = json.loads(eval_path.read_text(encoding="utf-8"))
        db_snapshot = result.get("db_snapshot", {})

        issues, suspect_issues = [], []
        for issue in verdict.get("issues", []):
            (suspect_issues if _is_confirmation_false_positive(issue, db_snapshot) else issues).append(issue)

        rows.append(
            {
                "scenario_id": result["scenario_id"],
                "run_id": result["run_id"],
                "file": path.name,
                "verdict": verdict.get("verdict", "?"),
                "reasoning": verdict.get("reasoning", ""),
                "issues": issues,
                "suspect_issues": suspect_issues,
            }
        )
    return rows


def print_summary(rows: list[dict]) -> None:
    if not rows:
        print(f"\nnothing graded yet in {RESULTS_DIR} -- run with --all first")
        return

    passed = sum(1 for r in rows if r["verdict"] == "pass" and not r["suspect_issues"])
    print(f"\n=== eval summary: {passed}/{len(rows)} passed ===\n")

    for r in rows:
        clean_pass = r["verdict"] == "pass" and not r["suspect_issues"]
        if clean_pass:
            print(f"[PASS] {r['scenario_id']}")
            continue
        mark = {"pass": "PASS*", "fail": "FAIL", "partial": "PARTIAL"}.get(r["verdict"], "?")
        print(f"[{mark}] {r['scenario_id']}")
        for issue in r["issues"]:
            print(f"    - {issue}")
        for issue in r["suspect_issues"]:
            print(f"    - (SUSPECT -- disputes a db_snapshot order already marked placed) {issue}")

    if any(r["suspect_issues"] for r in rows):
        print(
            "\nNote: issues marked SUSPECT contradict that run's own db_snapshot "
            "(an order it shows as status=placed) -- likely judge bias, not a real "
            "bot bug. See eval_agent.py's module docstring. Read the transcript "
            "yourself before treating these as real."
        )


def write_summary_file(rows: list[dict]) -> Path:
    lines = [f"# Eval summary -- {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", ""]
    passed = sum(1 for r in rows if r["verdict"] == "pass" and not r["suspect_issues"])
    lines.append(f"**{passed}/{len(rows)} passed**")
    lines.append("")
    for r in rows:
        clean_pass = r["verdict"] == "pass" and not r["suspect_issues"]
        mark = "PASS" if clean_pass else {"pass": "PASS*", "fail": "FAIL", "partial": "PARTIAL"}.get(r["verdict"], "?")
        lines.append(f"## [{mark}] {r['scenario_id']} (`{r['file']}`)")
        lines.append(r["reasoning"])
        for issue in r["issues"]:
            lines.append(f"- {issue}")
        for issue in r["suspect_issues"]:
            lines.append(f"- **SUSPECT** (contradicts this run's own db_snapshot): {issue}")
        lines.append("")

    path = RESULTS_DIR / "summary.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Grade one specific result JSON file.")
    group.add_argument("--scenario", help="Grade the most recent run of one scenario.")
    group.add_argument("--all", action="store_true", help="Grade every result file in eval/results/.")
    group.add_argument(
        "--summary", action="store_true", help="Just print/save the final report from whatever is already graded."
    )
    parser.add_argument("--force", action="store_true", help="Re-grade even if a .eval.json already exists.")
    args = parser.parse_args()

    if not args.summary:
        if args.file:
            grade_file(Path(args.file), args.force)
        else:
            result_files = sorted(p for p in RESULTS_DIR.glob("*.json") if not p.name.endswith(".eval.json"))
            if args.scenario:
                matches = [p for p in result_files if p.name.startswith(f"{args.scenario}__")]
                if not matches:
                    raise SystemExit(f"no saved runs for scenario {args.scenario!r} in {RESULTS_DIR}")
                grade_file(matches[-1], args.force)
            elif not result_files:
                print(f"no result files found in {RESULTS_DIR}")
                return
            else:
                for path in result_files:
                    grade_file(path, args.force)

    rows = build_summary()
    print_summary(rows)
    if rows:
        path = write_summary_file(rows)
        print(f"\nsaved -> {path}")


if __name__ == "__main__":
    main()
