"""Google Calendar API tools for the Calendar Agent.

Handles OAuth authentication and all calendar CRUD operations.
When Google credentials are not available, falls back to a local
SQLite-based calendar for development and demos.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from muse.config import config
from muse.models.events import GigEvent, EventType, EventStatus, ConflictInfo

logger = logging.getLogger(__name__)

# Try to import Google API libraries — fall back gracefully if not available
try:
    from googleapiclient.discovery import build

    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    logger.info("Google API libraries not installed — using local calendar")


# Fields the agent may change via update_event (mirrors the events table).
UPDATABLE_FIELDS = {
    "title", "event_type", "venue", "address", "start_time", "end_time",
    "load_in_time", "soundcheck_time", "set_time", "pay", "pay_notes",
    "contact_name", "contact_info", "gear_notes", "status", "notes",
}


def _window_bounds(start: str, end: str) -> tuple[str, str]:
    """Expand date-only bounds to cover whole days (end date is inclusive)."""
    if "T" not in start:
        start += "T00:00:00"
    if "T" not in end:
        end += "T23:59:59"
    return start, end


def _to_rfc3339(value: str) -> str:
    """Give a naive ISO datetime the artist's timezone, as the Google API expects.

    Naive times from the agent are local to the artist (events are created
    with timeZone=DEFAULT_TIMEZONE), so they must not be treated as UTC.
    """
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(config.DEFAULT_TIMEZONE))
    return dt.isoformat()


def _parse_local(value: str) -> datetime:
    """Parse an ISO datetime as naive local time in the artist's timezone."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(ZoneInfo(config.DEFAULT_TIMEZONE)).replace(tzinfo=None)
    return dt


def _local_dt(dt: datetime | None) -> str | None:
    """Local-mode storage format: naive ISO time in the artist's timezone.

    Times are compared as strings in SQLite, so every stored value and query
    bound must share one format (models may or may not send a UTC offset).
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(ZoneInfo(config.DEFAULT_TIMEZONE)).replace(tzinfo=None)
    return dt.isoformat()


TIME_FIELDS = {"start_time", "end_time", "load_in_time", "soundcheck_time", "set_time"}


class CalendarTools:
    """Wraps Google Calendar API (or local fallback) for the Calendar Agent."""

    def __init__(self):
        self.service = None
        self.use_local = not GOOGLE_AVAILABLE
        self.db_path = config.DB_PATH

        if not self.use_local:
            try:
                self._authenticate()
            except Exception as e:
                logger.warning(f"Google Calendar auth failed: {e}. Using local calendar.")
                self.use_local = True

        if self.use_local:
            self._init_local_db()

    # ── Authentication ──────────────────────────────────────────────

    def _authenticate(self) -> None:
        """Authenticate with Google Calendar API using a saved OAuth token.

        Tokens are managed by the Streamlit UI via muse.utils.google_oauth.
        If no valid token exists, raises RuntimeError to trigger local fallback.
        """
        from muse.utils.google_oauth import load_credentials

        creds = load_credentials(config.GOOGLE_TOKEN_PATH, config.GOOGLE_SCOPES)
        if not creds:
            raise RuntimeError("Google Calendar not connected — using local mode")

        self.service = build("calendar", "v3", credentials=creds)
        logger.info("Google Calendar authenticated successfully")

    # ── Local SQLite Fallback ───────────────────────────────────────

    def _init_local_db(self) -> None:
        """Initialize local SQLite database for development/demo mode."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                event_type TEXT NOT NULL,
                venue TEXT DEFAULT '',
                address TEXT DEFAULT '',
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                load_in_time TEXT,
                soundcheck_time TEXT,
                set_time TEXT,
                pay REAL,
                pay_notes TEXT DEFAULT '',
                contact_name TEXT DEFAULT '',
                contact_info TEXT DEFAULT '',
                gear_notes TEXT DEFAULT '',
                status TEXT DEFAULT 'confirmed',
                notes TEXT DEFAULT ''
            )
        """)
        conn.commit()
        conn.close()
        logger.info(f"Local calendar initialized at {self.db_path}")

    # ── Tool Implementations ────────────────────────────────────────

    def create_event(self, event: GigEvent) -> dict:
        """Create a calendar event. Returns the created event with ID."""
        if self.use_local:
            return self._local_create(event)
        return self._google_create(event)

    def list_events(
        self,
        start_date: str,
        end_date: str,
        event_type: str | None = None,
    ) -> list[dict]:
        """List events within a date range. Dates in ISO format."""
        if self.use_local:
            return self._local_list(start_date, end_date, event_type)
        return self._google_list(start_date, end_date, event_type)

    def update_event(self, event_id: str, updates: dict) -> dict:
        """Update an existing event by ID."""
        if self.use_local:
            return self._local_update(event_id, updates)
        return self._google_update(event_id, updates)

    def delete_event(self, event_id: str) -> dict:
        """Delete/cancel an event by ID."""
        if self.use_local:
            return self._local_delete(event_id)
        return self._google_delete(event_id)

    def check_conflicts(self, start_time: str, end_time: str) -> list[dict]:
        """Check for scheduling conflicts in a time range."""
        events = self.list_events(start_time, end_time)
        conflicts = []
        for event in events:
            if event.get("status") == "cancelled":
                continue
            conflicts.append({
                "event_id": event["id"],
                "title": event["title"],
                "start_time": event["start_time"],
                "end_time": event["end_time"],
                "venue": event.get("venue", ""),
                "overlap_type": "full_or_partial",
            })
        return conflicts

    def find_availability(
        self,
        search_start: str,
        search_end: str,
        duration_hours: float = 2.0,
    ) -> list[dict]:
        """Find available time slots of at least `duration_hours` length.
        
        Returns slots during reasonable hours (8 AM - 11 PM).
        """
        events = self.list_events(search_start, search_end)

        start_dt = _parse_local(search_start)
        end_dt = _parse_local(search_end)
        duration = timedelta(hours=duration_hours)

        # Sort events by start time, ignoring cancelled ones
        sorted_events = sorted(
            (e for e in events if e.get("status") != "cancelled"),
            key=lambda e: _parse_local(e["start_time"]),
        )

        # Find gaps between events
        available = []
        current = start_dt

        for event in sorted_events:
            event_start = _parse_local(event["start_time"])
            event_end = _parse_local(event["end_time"])

            if event_start > current:
                gap = event_start - current
                if gap >= duration:
                    available.append({
                        "start": current.isoformat(),
                        "end": event_start.isoformat(),
                        "duration_hours": gap.total_seconds() / 3600,
                    })

            if event_end > current:
                current = event_end

        # Check remaining time after last event
        if end_dt > current and (end_dt - current) >= duration:
            available.append({
                "start": current.isoformat(),
                "end": end_dt.isoformat(),
                "duration_hours": (end_dt - current).total_seconds() / 3600,
            })

        return available

    # ── Local SQLite Implementations ────────────────────────────────

    def _local_create(self, event: GigEvent) -> dict:
        event_id = f"local_{uuid.uuid4().hex[:12]}"
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute(
            """INSERT INTO events 
            (id, title, event_type, venue, address, start_time, end_time,
             load_in_time, soundcheck_time, set_time, pay, pay_notes,
             contact_name, contact_info, gear_notes, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                event.title,
                event.event_type.value,
                event.venue,
                event.address,
                _local_dt(event.start_time),
                _local_dt(event.end_time),
                _local_dt(event.load_in_time),
                _local_dt(event.soundcheck_time),
                _local_dt(event.set_time),
                event.pay,
                event.pay_notes,
                event.contact_name,
                event.contact_info,
                event.gear_notes,
                event.status.value,
                event.notes,
            ),
        )
        conn.commit()
        conn.close()

        result = event.model_dump()
        result["id"] = event_id
        return {"status": "created", "event": result}

    def _local_list(
        self, start_date: str, end_date: str, event_type: str | None = None
    ) -> list[dict]:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # Return every event that overlaps the window (same semantics as
        # Google's timeMin/timeMax), not just those starting inside it.
        start_date, end_date = _window_bounds(start_date, end_date)
        start_date, end_date = _local_dt(_parse_local(start_date)), _local_dt(_parse_local(end_date))
        query = "SELECT * FROM events WHERE start_time < ? AND end_time > ?"
        params: list = [end_date, start_date]

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)

        query += " ORDER BY start_time"
        rows = conn.execute(query, params).fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def _local_update(self, event_id: str, updates: dict) -> dict:
        filtered = {k: v for k, v in updates.items() if k in UPDATABLE_FIELDS}
        for key in TIME_FIELDS & filtered.keys():
            if filtered[key]:
                filtered[key] = _local_dt(_parse_local(filtered[key]))
        if not filtered:
            return {"error": f"No valid fields to update. Allowed: {', '.join(sorted(UPDATABLE_FIELDS))}"}

        set_clauses = []
        params = []
        for key, value in filtered.items():
            set_clauses.append(f"{key} = ?")
            params.append(value)
        params.append(event_id)

        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        cursor = conn.execute(
            f"UPDATE events SET {', '.join(set_clauses)} WHERE id = ?", params
        )
        conn.commit()
        conn.close()
        if cursor.rowcount == 0:
            return {"error": f"Event not found: {event_id}"}
        return {"status": "updated", "event_id": event_id, "updates": filtered}

    def _local_delete(self, event_id: str) -> dict:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        cursor = conn.execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (event_id,))
        conn.commit()
        conn.close()
        if cursor.rowcount == 0:
            return {"error": f"Event not found: {event_id}"}
        return {"status": "cancelled", "event_id": event_id}

    # ── Google Calendar Implementations ─────────────────────────────

    def _google_create(self, event: GigEvent) -> dict:
        body = {
            "summary": event.title,
            "location": event.address or event.venue,
            "description": event.to_calendar_description(),
            "start": {
                "dateTime": event.start_time.isoformat(),
                "timeZone": config.DEFAULT_TIMEZONE,
            },
            "end": {
                "dateTime": event.end_time.isoformat(),
                "timeZone": config.DEFAULT_TIMEZONE,
            },
            "status": "confirmed" if event.status == EventStatus.CONFIRMED else "tentative",
        }

        created = self.service.events().insert(calendarId="primary", body=body).execute()

        result = event.model_dump()
        result["id"] = created["id"]
        return {"status": "created", "event": result, "google_link": created.get("htmlLink")}

    def _google_list(
        self, start_date: str, end_date: str, event_type: str | None = None
    ) -> list[dict]:
        start_date, end_date = _window_bounds(start_date, end_date)
        start_date, end_date = _to_rfc3339(start_date), _to_rfc3339(end_date)

        results = (
            self.service.events()
            .list(
                calendarId="primary",
                timeMin=start_date,
                timeMax=end_date,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = []
        for item in results.get("items", []):
            start = item["start"].get("dateTime", item["start"].get("date", ""))
            end = item["end"].get("dateTime", item["end"].get("date", ""))
            events.append({
                "id": item["id"],
                "title": item.get("summary", "Untitled"),
                "start_time": start,
                "end_time": end,
                "venue": item.get("location", ""),
                "description": item.get("description", ""),
                "status": item.get("status", "confirmed"),
            })

        return events

    def _google_update(self, event_id: str, updates: dict) -> dict:
        # Fetch existing event
        event = self.service.events().get(calendarId="primary", eventId=event_id).execute()

        # Apply updates
        field_map = {
            "title": "summary",
            "address": "location",
            "venue": "location",
            "notes": "description",
        }
        for key, value in updates.items():
            gcal_key = field_map.get(key, key)
            if gcal_key in ("summary", "location", "description"):
                event[gcal_key] = value
            elif key == "start_time":
                event["start"]["dateTime"] = value
            elif key == "end_time":
                event["end"]["dateTime"] = value

        updated = (
            self.service.events()
            .update(calendarId="primary", eventId=event_id, body=event)
            .execute()
        )
        return {"status": "updated", "event_id": event_id, "updates": updates}

    def _google_delete(self, event_id: str) -> dict:
        self.service.events().delete(calendarId="primary", eventId=event_id).execute()
        return {"status": "deleted", "event_id": event_id}
