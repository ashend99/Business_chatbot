"""resolve_bot_status: the bot may only move a lead forward, never touch a
staff-owned status, and only grant NEW once required fields are filled."""

import pytest

from app.models.leads import LeadStatus
from app.repos.leads import resolve_bot_status

S = LeadStatus


@pytest.mark.parametrize("requested", [S.INTERESTED, S.NEW])
def test_fresh_lead_gets_requested_status_when_nothing_missing(requested: LeadStatus) -> None:
    assert resolve_bot_status(None, requested, []) == requested


def test_fresh_lead_stays_interested_when_required_fields_missing() -> None:
    assert resolve_bot_status(None, S.NEW, ["Phone Number"]) == S.INTERESTED


def test_interested_lead_upgrades_to_new_when_complete() -> None:
    assert resolve_bot_status(S.INTERESTED, S.NEW, []) == S.NEW


def test_interested_lead_is_not_upgraded_when_incomplete() -> None:
    assert resolve_bot_status(S.INTERESTED, S.NEW, ["Name"]) == S.INTERESTED


def test_new_lead_is_never_downgraded() -> None:
    assert resolve_bot_status(S.NEW, S.INTERESTED, []) == S.NEW
    assert resolve_bot_status(S.NEW, S.NEW, ["Name"]) == S.NEW


@pytest.mark.parametrize("staff_status", [S.CONTACTED, S.CONVERTED, S.LOST])
@pytest.mark.parametrize("requested", [S.INTERESTED, S.NEW])
def test_staff_owned_status_is_never_changed_by_the_bot(
    staff_status: LeadStatus, requested: LeadStatus
) -> None:
    assert resolve_bot_status(staff_status, requested, []) == staff_status
