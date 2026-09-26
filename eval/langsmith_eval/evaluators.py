"""Row-level evaluators for langsmith.aevaluate(). Each has the signature
`(run, example) -> dict | None`:

- `run.outputs` is whatever target.run_scenario returned this experiment run
  (transcript, db_snapshot, ...).
- `example.inputs`/`example.outputs` are the dataset example's own fields --
  outputs carries `success_criteria` and the scenario's optional `checks`
  block (see eval/scenarios.yaml, eval/LANGSMITH_PLAN.md section 5).

The deterministic evaluators return None (LangSmith records nothing, rather
than a misleading 0/1) whenever a scenario never declared an opinion on that
dimension via `checks:` -- most scenarios still only get graded by
`llm_judge`, same as the current eval_agent.py-only setup.

`llm_judge` reuses eval/eval_agent.py's prompt/grading logic directly rather
than re-deriving it -- that prompt has several rounds of hard-won anti-bias
tuning (see its module docstring) that a fresh judge prompt would have to
rediscover.
"""

import config  # noqa: F401,I001  -- sets up sys.path before the imports below

import re
from decimal import Decimal

from langsmith.schemas import Example, Run

from app.services.money import extract_amounts
from eval_agent import _is_confirmation_false_positive, grade_result

# Deliberately narrow and literal (card/cvv/"pay now in chat" phrasing) --
# this is an evaluator, not the guardrail itself (bot_engine.py's actual
# payment boundary is enforced by prompt + the pricing/discount guardrails);
# it exists as an *independent* check that regressed guardrail behavior would
# still get caught here even if bot_engine.py's own logic silently broke.
_PAYMENT_KEYWORDS = re.compile(
    r"\bcard number\b|\bcredit card\b|\bdebit card\b|\bcvv\b|\bcvc\b"
    r"|\bpay(?:ment)?\s+(?:right\s+)?(?:now|here)\s+(?:in|via)\s+(?:the\s+)?chat\b"
    r"|\benter your card\b|\bprocess(?:ing)? your payment\b|\bcharge your card\b",
    re.IGNORECASE,
)


def _checks(example: Example) -> dict:
    return (example.outputs or {}).get("checks") or {}


def _assistant_texts(transcript: list[dict]) -> list[str]:
    return [t["text"] for t in transcript if t.get("role") == "assistant" and t.get("text")]


def order_status_matches(run: Run, example: Example) -> dict | None:
    expected = _checks(example).get("expected_order_status")
    if expected is None:
        return None
    orders = ((run.outputs or {}).get("db_snapshot") or {}).get("orders", [])
    if expected == "none":
        bad = [o for o in orders if o.get("status") in ("placed", "pending_confirmation")]
        score = int(not bad)
        if score:
            comment = "no order was placed/pending, as expected"
        else:
            comment = f"expected no order, found: {bad}"
    else:
        match = any(o.get("status") == expected for o in orders)
        score = int(match)
        comment = (
            f"found order with status={expected}"
            if score
            else f"no order with status={expected!r} among: {orders}"
        )
    return {"key": "order_status_matches", "score": score, "comment": comment}


def lead_fields_match(run: Run, example: Example) -> dict | None:
    expected = _checks(example).get("expected_lead_fields")
    if not expected:
        return None
    leads = ((run.outputs or {}).get("db_snapshot") or {}).get("leads", [])
    for lead in leads:
        fields = lead.get("fields") or {}
        if all(fields.get(k) == v for k, v in expected.items()):
            comment = f"matched lead {lead.get('id')}"
            return {"key": "lead_fields_match", "score": 1, "comment": comment}
    comment = f"no lead matched {expected}; leads found: {leads}"
    return {"key": "lead_fields_match", "score": 0, "comment": comment}


def price_matches_order_total(run: Run, example: Example) -> dict | None:
    if not _checks(example).get("price_must_match_order_total"):
        return None
    outputs = run.outputs or {}
    orders = (outputs.get("db_snapshot") or {}).get("orders", [])
    if not orders:
        return {
            "key": "price_matches_order_total",
            "score": 0,
            "comment": "no order to check a price against",
        }

    order = orders[-1]
    try:
        order_total = Decimal(str(order["total"]))
    except (KeyError, ArithmeticError, ValueError):
        return {
            "key": "price_matches_order_total",
            "score": 0,
            "comment": f"order has no usable total: {order}",
        }

    currency = order.get("currency_code", "USD")
    stated: set[Decimal] = set()
    for text in _assistant_texts(outputs.get("transcript", [])):
        stated |= extract_amounts(text, currency)

    if not stated:
        # nothing to contradict the total with -- not a failure, just nothing
        # to check (e.g. the bot only ever showed a cart summary the customer
        # never got a chance to restate a number for)
        return {
            "key": "price_matches_order_total",
            "score": 1,
            "comment": "no price stated in reply to check",
        }

    score = int(order_total in stated)
    return {
        "key": "price_matches_order_total",
        "score": score,
        "comment": f"order total={order_total}, prices stated by the bot={stated}",
    }


def payment_never_mentioned(run: Run, example: Example) -> dict | None:
    if not _checks(example).get("payment_mention_forbidden"):
        return None
    transcript = (run.outputs or {}).get("transcript", [])
    hits = [t for t in _assistant_texts(transcript) if _PAYMENT_KEYWORDS.search(t)]
    score = int(not hits)
    comment = "no payment-collection language found" if score else f"payment language found: {hits}"
    return {"key": "payment_never_mentioned", "score": score, "comment": comment}


def http_status_matches(run: Run, example: Example) -> dict | None:
    expected = _checks(example).get("http_status_expected")
    if expected is None:
        return None
    transcript = (run.outputs or {}).get("transcript", [])
    statuses = [t["http_status"] for t in transcript if t.get("http_status")]
    score = int(expected in statuses)
    comment = f"statuses seen: {statuses}" if statuses else "no rejected request recorded"
    return {"key": "http_status_matches", "score": score, "comment": comment}


def llm_judge(run: Run, example: Example) -> dict:
    """Straight port of eval_agent.py's judge: same prompt, same gpt-4o
    model, same db_facts-first / confirmation-dispute-counter-instruction
    structure. Also folds in eval_agent.py's own known-bias catcher
    (_is_confirmation_false_positive) as a second metric here instead of a
    separate post-hoc summary pass -- so a suspect verdict is visible right
    on the experiment row, not just in a later `--summary` report."""
    outputs = run.outputs or {}
    result = {
        "scenario_id": (example.inputs or {}).get("scenario_id", "?"),
        "success_criteria": (example.outputs or {}).get("success_criteria", ""),
        "settings_overrides": outputs.get("settings_overrides", {}),
        "run_context": outputs.get("run_context", {}),
        "transcript": outputs.get("transcript", []),
        "db_snapshot": outputs.get("db_snapshot", {}),
    }
    verdict = grade_result(result)

    score = {"pass": 1.0, "partial": 0.5, "fail": 0.0}.get(verdict.get("verdict"), 0.0)
    issues = verdict.get("issues", [])
    suspect = [i for i in issues if _is_confirmation_false_positive(i, result["db_snapshot"])]
    real_issues = [i for i in issues if i not in suspect]

    comment = verdict.get("reasoning", "")
    if real_issues:
        comment += f" Issues: {real_issues}"

    results = [{"key": "llm_judge", "score": score, "comment": comment}]
    if issues:
        results.append(
            {
                "key": "llm_judge_suspect_free",
                "score": int(not suspect),
                "comment": (
                    f"{len(suspect)} issue(s) dispute an order's confirmation despite "
                    "db_snapshot already showing status=placed -- likely judge bias, "
                    "see eval_agent.py's module docstring. Read the transcript before "
                    "trusting these." if suspect else "no suspect issues"
                ),
            }
        )
    return {"results": results}
