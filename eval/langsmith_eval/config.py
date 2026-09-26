"""Shared env/path setup for the LangSmith eval pipeline. Import this first
(as `import config`) in every script in this directory -- its only job is
sys.path/env setup, mirroring eval/lib.py's own pattern, so `import lib`,
`import conversation_agent`, `import eval_agent`, and `from app.services...`
all resolve regardless of which script here actually gets run directly.

Not a package (no __init__.py, no relative imports) on purpose -- these
scripts are meant to be run directly the same way conversation_agent.py and
eval_agent.py already are ("uv run python eval/langsmith_eval/<script>.py"),
and relative imports don't work for a script executed as __main__.

Named `langsmith_eval`, not `langsmith`, deliberately: a directory literally
named `langsmith` sitting where `eval/` ends up on sys.path (see below) would
shadow the real installed `langsmith` package the moment anything here does
`import langsmith`.
"""

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
EVAL_ROOT = PACKAGE_ROOT.parent
PROJECT_ROOT = EVAL_ROOT.parent

for _p in (str(EVAL_ROOT), str(PROJECT_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# `lib` also loads PROJECT_ROOT/.env via python-dotenv at import time, which
# is where LANGSMITH_TRACING/LANGSMITH_API_KEY/LANGSMITH_PROJECT should live
# alongside the existing EVAL_*/OPENAI_API_KEY vars -- no separate env
# loading needed here.
import os  # noqa: E402

from lib import OPENAI_API_KEY  # noqa: E402,F401

DATASET_NAME = os.environ.get("LANGSMITH_DATASET_NAME", "business-chatbot-scenarios")
JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "gpt-4o")

# Scenario categories whose settings overrides (eval/lib.py's SettingsOverride)
# mutate real, shared tenant state via the live API -- see LANGSMITH_PLAN.md
# section 10. Running two of these concurrently against the same dev tenant
# can race. run_experiment.py uses this to force that category to
# max_concurrency=1 regardless of what was passed for the rest of the run.
SETTINGS_DRIVEN_CATEGORY = "settings_driven"
