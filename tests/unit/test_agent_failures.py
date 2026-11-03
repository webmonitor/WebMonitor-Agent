"""A run reports the failure class the user can act on, never one generic outage."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from agents.exceptions import MaxTurnsExceeded, ModelBehaviorError
from openai import APIConnectionError

from webmonitor.agent.orchestration import _failure
from webmonitor.agent.tools import _reusable_analysis, _wait_timeout
from webmonitor.errors import DomainError
from webmonitor.models import utc_now


@pytest.mark.parametrize("exc,expected", [
    (TimeoutError(), ("run_timeout", None)),
    (MaxTurnsExceeded("limit"), ("max_turns_exceeded", None)),
    (ModelBehaviorError("bad tool"), ("model_output_invalid", "bad tool")),
    (APIConnectionError(request=None), ("model_unavailable", "connection")),
    (DomainError("stale_revision", 409), ("stale_revision", None)),
    (RuntimeError("x"), ("run_failed", "RuntimeError")),
])
def test_failure_reports_the_actionable_class(exc, expected):
    assert _failure(exc) == expected


@pytest.mark.asyncio
async def test_wait_timeout_without_a_budget_uses_the_full_wait():
    assert _wait_timeout(None) == 70.0


@pytest.mark.asyncio
async def test_wait_timeout_stays_inside_the_remaining_budget():
    value = _wait_timeout(asyncio.get_running_loop().time() + 30)
    assert 24 < value <= 25


@pytest.mark.asyncio
async def test_wait_timeout_refuses_a_budget_with_no_margin_left():
    with pytest.raises(DomainError) as raised:
        _wait_timeout(asyncio.get_running_loop().time() - 1)
    assert raised.value.code == "run_budget_exhausted"


def _row(status, mode, age_minutes, now):
    return SimpleNamespace(status=status, spec={"collection_mode": mode},
                           created_at=now - timedelta(minutes=age_minutes))


def test_reusable_analysis_skips_stale_and_browser_evidence():
    now = utc_now()
    rows = [_row("succeeded", "browser", 1, now),
            _row("succeeded", "http", 16, now),
            _row("failed", "http", 1, now),
            _row("succeeded", "http", 1, now)]
    reused = _reusable_analysis(rows, now)
    assert reused is rows[-1]
    assert _reusable_analysis(rows[:3], now) is None
