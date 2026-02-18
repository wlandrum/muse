"""Calendar Agent — handles scheduling, conflict detection, and event management for musicians."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from muse.agents.base import BaseAgent
from muse.config import config
from muse.models.events import GigEvent, EventType, EventStatus
from muse.tools.calendar_tools import CalendarTools

logger = logging.getLogger(__name__)


CALENDAR_SYSTEM_PROMPT = f"""You are the Calendar Agent for Muse, an AI manager for independent musicians.

Your job is to manage the artist's schedule — creating events, detecting conflicts, finding availability, and keeping their calendar organized. The artist's name is {config.ARTIST_NAME}.

## How You Operate

You are conversational, efficient, and music-industry-aware. You understand the difference between a gig (live performance), a recording session, a rehearsal, a lesson, and a meeting. You know that:

- **Gigs** have load-in times, soundcheck times, set times, and end times. Load-in is typically 2-4 hours before the set. Always ask about pay.
- **Sessions** are booked in blocks (usually 4-8 hours). Ask about the studio, the engineer, and the rate.
- **Rehearsals** are usually 2-3 hours. Ask about the location and who else is involved.
- **Lessons** are recurring (usually weekly). Ask about the student and location.
- **Meetings** can be anything — label meetings, booking agent calls, etc.

## Rules

1. **Always check for conflicts** before creating any event. Use the `check_conflicts` tool first.
2. If there's a conflict, present the conflict clearly and offer options (reschedule, cancel the conflicting event, or proceed anyway).
3. When the user gives partial info, fill in reasonable defaults but confirm with them:
   - If no end time is given for a gig, assume 4 hours after the set time (or 5 hours after load-in).
   - If no end time is given for a session, assume a 4-hour block.
   - If no end time is given for a rehearsal, assume 2.5 hours.
4. Parse natural language dates and times. "Next Thursday" means the coming Thursday. "This weekend" means the upcoming Saturday/Sunday.
5. After creating an event, show a clean summary of what was created.
6. When listing events, organize them chronologically and group by day.
7. Use the artist's timezone: {config.DEFAULT_TIMEZONE}.

## Important

- Today's date is {datetime.now().strftime("%A, %B %d, %Y")}.
- Always use 12-hour time format (e.g., "2:00 PM") when talking to the user.
- Always use ISO 8601 format when calling tools.
- If the user mentions pay, always capture it — this feeds into the invoice agent later.
- Be concise. Musicians are busy. Don't over-explain.
"""


TOOL_DEFINITIONS = [
    {
        "name": "create_event",
        "description": (
            "Create a new event on the artist's calendar. Always check for "
            "conflicts FIRST using check_conflicts before calling this."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Event title, e.g. 'Live at The Earl' or 'Session at West End Sound'",
                },
                "event_type": {
                    "type": "string",
                    "enum": ["gig", "session", "rehearsal", "lesson", "meeting", "other"],
                    "description": "Type of event",
                },
                "venue": {
                    "type": "string",
                    "description": "Venue or studio name",
                },
                "address": {
                    "type": "string",
                    "description": "Full address of the venue",
                },
                "start_time": {
                    "type": "string",
                    "description": "Event start time in ISO 8601 format",
                },
                "end_time": {
                    "type": "string",
                    "description": "Event end time in ISO 8601 format",
                },
                "load_in_time": {
                    "type": "string",
                    "description": "Load-in time in ISO 8601 format (gigs only)",
                },
                "soundcheck_time": {
                    "type": "string",
                    "description": "Soundcheck time in ISO 8601 format (gigs only)",
                },
                "set_time": {
                    "type": "string",
                    "description": "Set/performance start time in ISO 8601 format (gigs only)",
                },
                "pay": {
                    "type": "number",
                    "description": "Payment amount in USD",
                },
                "pay_notes": {
                    "type": "string",
                    "description": "Payment details, e.g. '$300 + door split'",
                },
                "contact_name": {
                    "type": "string",
                    "description": "Booking contact name",
                },
                "contact_info": {
                    "type": "string",
                    "description": "Contact email or phone number",
                },
                "gear_notes": {
                    "type": "string",
                    "description": "Equipment notes, e.g. 'Bring acoustic + DI box'",
                },
                "status": {
                    "type": "string",
                    "enum": ["confirmed", "tentative", "cancelled"],
                    "description": "Event status. Default: confirmed",
                },
                "notes": {
                    "type": "string",
                    "description": "Any additional notes",
                },
            },
            "required": ["title", "event_type", "start_time", "end_time"],
        },
    },
    {
        "name": "list_events",
        "description": "List calendar events within a date range. Use to show the artist their schedule.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start of range in ISO 8601 format (e.g. '2026-02-14T00:00:00')",
                },
                "end_date": {
                    "type": "string",
                    "description": "End of range in ISO 8601 format (e.g. '2026-02-21T23:59:59')",
                },
                "event_type": {
                    "type": "string",
                    "enum": ["gig", "session", "rehearsal", "lesson", "meeting", "other"],
                    "description": "Optional filter by event type",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "update_event",
        "description": "Update an existing calendar event. Use the event ID from list_events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "The ID of the event to update",
                },
                "updates": {
                    "type": "object",
                    "description": "Key-value pairs of fields to update (e.g. {'pay': 500, 'venue': 'New Venue'})",
                },
            },
            "required": ["event_id", "updates"],
        },
    },
    {
        "name": "delete_event",
        "description": "Cancel/delete a calendar event. Use the event ID from list_events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "The ID of the event to cancel",
                },
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "check_conflicts",
        "description": (
            "Check for scheduling conflicts in a time range. "
            "ALWAYS call this before creating a new event."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_time": {
                    "type": "string",
                    "description": "Start of time range in ISO 8601 format",
                },
                "end_time": {
                    "type": "string",
                    "description": "End of time range in ISO 8601 format",
                },
            },
            "required": ["start_time", "end_time"],
        },
    },
    {
        "name": "find_availability",
        "description": "Find open time slots in a date range where the artist is available.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_start": {
                    "type": "string",
                    "description": "Start of search range in ISO 8601 format",
                },
                "search_end": {
                    "type": "string",
                    "description": "End of search range in ISO 8601 format",
                },
                "duration_hours": {
                    "type": "number",
                    "description": "Minimum duration needed in hours. Default: 2",
                },
            },
            "required": ["search_start", "search_end"],
        },
    },
]


class CalendarAgent(BaseAgent):
    """Manages the artist's calendar — gigs, sessions, rehearsals, lessons."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calendar = CalendarTools()

    @property
    def name(self) -> str:
        return "CalendarAgent"

    def system_prompt(self) -> str:
        return CALENDAR_SYSTEM_PROMPT

    def tool_definitions(self) -> list[dict]:
        return TOOL_DEFINITIONS

    def execute_tool(self, tool_name: str, tool_input: dict) -> Any:
        """Route tool calls to CalendarTools methods."""

        if tool_name == "create_event":
            event = GigEvent(
                title=tool_input["title"],
                event_type=EventType(tool_input["event_type"]),
                venue=tool_input.get("venue", ""),
                address=tool_input.get("address", ""),
                start_time=datetime.fromisoformat(tool_input["start_time"]),
                end_time=datetime.fromisoformat(tool_input["end_time"]),
                load_in_time=(
                    datetime.fromisoformat(tool_input["load_in_time"])
                    if tool_input.get("load_in_time")
                    else None
                ),
                soundcheck_time=(
                    datetime.fromisoformat(tool_input["soundcheck_time"])
                    if tool_input.get("soundcheck_time")
                    else None
                ),
                set_time=(
                    datetime.fromisoformat(tool_input["set_time"])
                    if tool_input.get("set_time")
                    else None
                ),
                pay=tool_input.get("pay"),
                pay_notes=tool_input.get("pay_notes", ""),
                contact_name=tool_input.get("contact_name", ""),
                contact_info=tool_input.get("contact_info", ""),
                gear_notes=tool_input.get("gear_notes", ""),
                status=EventStatus(tool_input.get("status", "confirmed")),
                notes=tool_input.get("notes", ""),
            )
            return self.calendar.create_event(event)

        elif tool_name == "list_events":
            return self.calendar.list_events(
                start_date=tool_input["start_date"],
                end_date=tool_input["end_date"],
                event_type=tool_input.get("event_type"),
            )

        elif tool_name == "update_event":
            return self.calendar.update_event(
                event_id=tool_input["event_id"],
                updates=tool_input["updates"],
            )

        elif tool_name == "delete_event":
            return self.calendar.delete_event(event_id=tool_input["event_id"])

        elif tool_name == "check_conflicts":
            return self.calendar.check_conflicts(
                start_time=tool_input["start_time"],
                end_time=tool_input["end_time"],
            )

        elif tool_name == "find_availability":
            return self.calendar.find_availability(
                search_start=tool_input["search_start"],
                search_end=tool_input["search_end"],
                duration_hours=tool_input.get("duration_hours", 2.0),
            )

        else:
            return {"error": f"Unknown tool: {tool_name}"}
