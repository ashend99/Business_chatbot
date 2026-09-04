"""Central logging setup.

Without a call to `logging.basicConfig()` (or an explicit handler)
somewhere, the stdlib logging module has no handler anywhere in the
propagation chain. Records still get created if a logger's own level allows
it (e.g. `logger.setLevel("DEBUG")` in repos/tenants.py), but with no
handler to write them anywhere, Python falls back to its "handler of last
resort" -- which only prints WARNING and above. That's why `logger.info(...)`
calls were invisible even though the logger's level was set correctly.

Call `configure_logging()` once, early, at process startup (see
`app/main.py`) so every module's `logging.getLogger(__name__)` actually
reaches a real handler.
"""

import logging

from .config import PROJECT_CONFIG

_DEFAULT_LEVEL = "INFO"
_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    level = PROJECT_CONFIG.get("logging", {}).get("level", _DEFAULT_LEVEL)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _configured = True
