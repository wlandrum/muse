"""Runs every eval case in mock mode, and checks the graders catch bad behaviour."""

import copy

import pytest

from muse.eval.graders import grade, is_subsequence, match
from muse.eval.runner import load_cases, run_case

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_eval_case(case):
    result = run_case(case)
    assert result.passed, "\n".join(result.failures)


# ── Matchers ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("expected,actual,ok", [
    ("session", "Session", True),
    (500, 500.0, True),
    ({"contains": "west end"}, "West End Sound", True),
    ({"startswith": "2026-12-03T12"}, "2026-12-03T12:00:00", True),
    ({"startswith": "2026-12-03T12"}, "2026-12-04T12:00:00", False),
    ({"one_of": ["a", "b"]}, "b", True),
    ({"gte": 3}, 2, False),
    ({"regex": r"^inv_[0-9a-f]+$"}, "inv_abc123", True),
    ({"event_type": "gig", "pay": 400}, {"event_type": "gig", "pay": 400, "venue": "x"}, True),
    ({"event_type": "gig"}, {"pay": 400}, False),
    ({"contains": "x"}, None, False),
    ({"min_len": 1}, [{"id": 1}], True),
    ({"min_len": 1}, [], False),
    ({"max_len": 0}, [], True),
])
def test_match(expected, actual, ok):
    assert match(expected, actual) is ok


def test_router_only_cases_are_separate():
    all_routes = load_cases(router_only=True)
    assert len(all_routes) > len(CASES)
    assert not any(c.get("router_only") for c in CASES)


def test_is_subsequence():
    assert is_subsequence(["a", "c"], ["a", "b", "c"])
    assert not is_subsequence(["c", "a"], ["a", "b", "c"])
    assert is_subsequence([], ["a"])


# ── Graders catch regressions ────────────────────────────────────────

def _case(case_id):
    return copy.deepcopy(next(c for c in CASES if c["id"] == case_id))


def test_catches_sending_without_approval():
    case = _case("email-draft-reply-never-sends")
    case["trajectory"].insert(-1, {"tools": [
        {"name": "send_draft", "input": {"draft_id": "draft_whatever"}},
    ]})
    result = run_case(case)
    assert not result.passed
    assert any("send_draft" in f and "tools_not_called" in f for f in result.failures)


def test_catches_booking_over_conflict():
    case = _case("calendar-conflict-blocks-create")
    case["trajectory"].insert(-1, {"tools": [{"name": "create_event", "input": {
        "title": "Rehearsal", "event_type": "rehearsal",
        "start_time": "2026-12-05T20:00:00", "end_time": "2026-12-05T22:00:00",
    }}]})
    result = run_case(case)
    assert not result.passed
    assert any("tools_not_called" in f for f in result.failures)
    assert any(f.startswith("state:") for f in result.failures)


def test_catches_schema_violation():
    case = _case("calendar-book-session")
    case["trajectory"][1]["tools"][0]["input"]["event_type"] = "concert"
    result = run_case(case)
    assert not result.passed
    assert any("input invalid" in f for f in result.failures)


def test_catches_wrong_route():
    # In mock mode the router replays the case's own route, so grade a
    # hand-built run where the (live) router chose differently.
    run = {"route": "CALENDAR", "response": "", "calls": []}
    failures = grade(_case("route-who-is-contact-is-crm"), run, {}, ".")
    assert any(f.startswith("route:") for f in failures)


def test_catches_agent_stopping_early():
    case = _case("invoice-mark-paid")
    case["trajectory"].append({"text": "extra turn the agent never asks for"})
    result = run_case(case)
    assert not result.passed
    assert any("unused" in f for f in result.failures)


def test_unknown_tool_is_reported():
    case = _case("social-list-drafts")
    case["trajectory"][0]["tools"][0]["name"] = "publish_to_instagram"
    case["expect"] = {"no_tool_errors": False}
    result = run_case(case)
    assert not result.passed
    assert any("not defined" in f for f in result.failures)


def test_sandbox_does_not_touch_real_db():
    import os
    from muse.config import config
    before = config.DB_PATH
    mtime = os.path.getmtime(before) if os.path.exists(before) else None
    run_case(_case("invoice-create-draft"))
    assert config.DB_PATH == before
    assert (os.path.getmtime(before) if os.path.exists(before) else None) == mtime


def test_usage_tracking_cost():
    from types import SimpleNamespace
    from muse.eval.usage import UsageTrackingClient

    def fake_create(**kwargs):
        usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=100_000,
                                cache_read_input_tokens=1_000_000, cache_creation_input_tokens=0)
        return SimpleNamespace(model=kwargs["model"], usage=usage)

    inner = SimpleNamespace(messages=SimpleNamespace(create=fake_create),
                            beta=SimpleNamespace(messages=SimpleNamespace(create=fake_create)))
    tracker = UsageTrackingClient(inner)
    tracker.messages.create(model="claude-haiku-5-5")
    tracker.beta.messages.create(model="claude-sonnet-5-5")
    assert tracker.cost("claude-haiku-5-5") == pytest.approx(0.10 + 0.05 + 0.01)
    assert tracker.cost("claude-sonnet-5-5") == pytest.approx(2.00 + 1.00 + 0.20)
    assert "total" in tracker.report()
