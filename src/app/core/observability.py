"""Error reporting (Sentry), enabled only when SENTRY_DSN is set.

Customer chats carry personal data (names, phone numbers, addresses), so
nothing beyond the error itself is sent: no request bodies, no local
variables, no user/IP details.
"""

import sentry_sdk

from app.core.config import Settings


def init_sentry(settings: Settings) -> bool:
    """Returns whether Sentry was enabled."""
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
    )
    return True
