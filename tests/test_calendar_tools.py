from datetime import datetime

import pytest

from muse.models.events import EventStatus, EventType, GigEvent
from muse.tools.calendar_tools import _to_rfc3339


def make(calendar, start, end, title="Event", event_type="gig", venue="The Earl", **kw):
    event = GigEvent(
        title=title,
        event_type=EventType(event_type),
        venue=venue,
        start_time=datetime.fromisoformat(start),
        end_time=datetime.fromisoformat(end),
        **kw,
    )
    return calendar.create_event(event)["event"]


# ── Create / list ────────────────────────────────────────────────────

def test_create_and_list(calendar):
    created = make(calendar, "2026-12-05T19:00:00", "2026-12-05T23:00:00", pay=400)
    assert created["id"].startswith("local_")

    events = calendar.list_events("2026-12-05", "2026-12-05")
    assert [e["id"] for e in events] == [created["id"]]
    assert events[0]["pay"] == 400


def test_list_date_only_end_includes_whole_day(calendar):
    make(calendar, "2026-12-13T21:00:00", "2026-12-13T23:30:00")
    assert len(calendar.list_events("2026-12-07", "2026-12-13")) == 1


def test_list_includes_event_already_in_progress(calendar):
    make(calendar, "2026-12-05T19:00:00", "2026-12-05T23:00:00")
    assert len(calendar.list_events("2026-12-05T20:00:00", "2026-12-05T21:00:00")) == 1


def test_list_filters_by_type_and_orders_by_start(calendar):
    make(calendar, "2026-12-06T18:00:00", "2026-12-06T20:00:00", title="B", event_type="rehearsal")
    make(calendar, "2026-12-05T18:00:00", "2026-12-05T20:00:00", title="A", event_type="rehearsal")
    make(calendar, "2026-12-05T21:00:00", "2026-12-05T23:00:00", title="Gig")
    rehearsals = calendar.list_events("2026-12-01", "2026-12-31", event_type="rehearsal")
    assert [e["title"] for e in rehearsals] == ["A", "B"]


# ── Conflicts ────────────────────────────────────────────────────────

@pytest.mark.parametrize("start,end,conflicts", [
    ("2026-12-05T20:00:00", "2026-12-05T22:00:00", 1),  # inside existing
    ("2026-12-05T18:00:00", "2026-12-05T20:00:00", 1),  # overlaps the start
    ("2026-12-05T22:00:00", "2026-12-06T01:00:00", 1),  # overlaps the end
    ("2026-12-05T18:00:00", "2026-12-06T00:00:00", 1),  # contains existing
    ("2026-12-05T15:00:00", "2026-12-05T19:00:00", 0),  # ends exactly as it starts
    ("2026-12-05T23:00:00", "2026-12-06T01:00:00", 0),  # starts exactly as it ends
    ("2026-12-06T19:00:00", "2026-12-06T23:00:00", 0),  # next day
])
def test_check_conflicts(calendar, start, end, conflicts):
    make(calendar, "2026-12-05T19:00:00", "2026-12-05T23:00:00", title="Live at The Earl")
    found = calendar.check_conflicts(start, end)
    assert len(found) == conflicts
    if conflicts:
        assert found[0]["title"] == "Live at The Earl"


def test_cancelled_events_do_not_conflict(calendar):
    event = make(calendar, "2026-12-05T19:00:00", "2026-12-05T23:00:00")
    calendar.delete_event(event["id"])
    assert calendar.check_conflicts("2026-12-05T20:00:00", "2026-12-05T21:00:00") == []


# ── Availability ─────────────────────────────────────────────────────

def test_find_availability_gaps(calendar):
    make(calendar, "2026-12-14T12:00:00", "2026-12-14T14:00:00")
    make(calendar, "2026-12-14T15:00:00", "2026-12-14T18:00:00")
    slots = calendar.find_availability("2026-12-14T09:00:00", "2026-12-14T22:00:00", duration_hours=2)
    assert [(s["start"][11:16], s["end"][11:16]) for s in slots] == [("09:00", "12:00"), ("18:00", "22:00")]


def test_find_availability_respects_event_in_progress(calendar):
    make(calendar, "2026-12-14T08:00:00", "2026-12-14T13:00:00")
    slots = calendar.find_availability("2026-12-14T10:00:00", "2026-12-14T18:00:00", duration_hours=2)
    assert slots[0]["start"].startswith("2026-12-14T13:00")


def test_find_availability_ignores_cancelled(calendar):
    event = make(calendar, "2026-12-14T12:00:00", "2026-12-14T14:00:00")
    calendar.delete_event(event["id"])
    slots = calendar.find_availability("2026-12-14T09:00:00", "2026-12-14T17:00:00", duration_hours=8)
    assert len(slots) == 1 and slots[0]["duration_hours"] == 8


# ── Update / delete ──────────────────────────────────────────────────

def test_update_event(calendar):
    event = make(calendar, "2026-12-05T19:00:00", "2026-12-05T23:00:00", pay=300)
    result = calendar.update_event(event["id"], {"pay": 450, "notes": "bumped"})
    assert result["status"] == "updated"
    stored = calendar.list_events("2026-12-05", "2026-12-05")[0]
    assert stored["pay"] == 450 and stored["notes"] == "bumped"


def test_update_rejects_unknown_columns(calendar):
    event = make(calendar, "2026-12-05T19:00:00", "2026-12-05T23:00:00")
    result = calendar.update_event(event["id"], {"id = 'x', title": "pwned"})
    assert "error" in result
    assert calendar.list_events("2026-12-05", "2026-12-05")[0]["id"] == event["id"]


def test_update_and_delete_missing_event(calendar):
    assert "error" in calendar.update_event("local_nope", {"pay": 1})
    assert "error" in calendar.delete_event("local_nope")


def test_delete_soft_cancels(calendar):
    event = make(calendar, "2026-12-05T19:00:00", "2026-12-05T23:00:00")
    assert calendar.delete_event(event["id"])["status"] == "cancelled"
    assert calendar.list_events("2026-12-05", "2026-12-05")[0]["status"] == EventStatus.CANCELLED.value


# ── Google time handling ─────────────────────────────────────────────

def test_naive_times_are_artist_local_for_google(monkeypatch):
    from muse.config import config
    monkeypatch.setattr(config, "DEFAULT_TIMEZONE", "America/New_York")
    assert _to_rfc3339("2026-12-03T12:00:00") == "2026-12-03T12:00:00-05:00"
    assert _to_rfc3339("2026-07-03T12:00:00") == "2026-07-03T12:00:00-04:00"
    assert _to_rfc3339("2026-12-03T17:00:00Z") == "2026-12-03T17:00:00+00:00"


# ── Mixed time formats (models may send UTC offsets) ─────────────────

def test_offset_and_naive_times_compare_correctly(calendar, monkeypatch):
    from muse.config import config
    monkeypatch.setattr(config, "DEFAULT_TIMEZONE", "America/New_York")
    make(calendar, "2026-12-05T19:00:00-05:00", "2026-12-05T23:00:00-05:00")
    assert len(calendar.check_conflicts("2026-12-05T20:00:00", "2026-12-05T21:00:00")) == 1
    assert len(calendar.check_conflicts("2026-12-06T01:00:00Z", "2026-12-06T02:00:00Z")) == 1  # 8-9 PM local
    assert calendar.check_conflicts("2026-12-05T23:00:00-05:00", "2026-12-06T01:00:00-05:00") == []
    stored = calendar.list_events("2026-12-05", "2026-12-05")[0]
    assert stored["start_time"] == "2026-12-05T19:00:00"


def test_update_normalizes_times(calendar, monkeypatch):
    from muse.config import config
    monkeypatch.setattr(config, "DEFAULT_TIMEZONE", "America/New_York")
    event = make(calendar, "2026-12-05T19:00:00", "2026-12-05T23:00:00")
    calendar.update_event(event["id"], {"start_time": "2026-12-06T00:30:00Z"})
    assert calendar.list_events("2026-12-05", "2026-12-05")[0]["start_time"] == "2026-12-05T19:30:00"
