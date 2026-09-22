"""Status rules for leads written by the bot (repos/leads.py:resolve_bot_status)."""

import pytest

from app.models.leads import LeadStatus
from app.repos.leads import resolve_bot_status

I, N = LeadStatus.INTERESTED, LeadStatus.NEW


@pytest.mark.parametrize(
    ("existing", "requested", "missing", "expected"),
    [
        # fresh lead
        (None, I, [], I),
        (None, N, [], N),
        (None, N, ["Phone"], I),  # NEW needs the tenant's required fields
        # INTERESTED -> NEW only once the required details are in
        (I, N, [], N),
        (I, N, ["Name"], I),
        # the bot never moves a lead backwards
        (N, I, [], N),
        (N, N, ["Phone"], N),
        # staff-owned statuses are never touched by the bot
        (LeadStatus.CONTACTED, N, [], LeadStatus.CONTACTED),
        (LeadStatus.CONVERTED, I, [], LeadStatus.CONVERTED),
        (LeadStatus.LOST, N, [], LeadStatus.LOST),
    ],
)
def test_resolve_bot_status(existing, requested, missing, expected):
    assert resolve_bot_status(existing, requested, missing) == expected
