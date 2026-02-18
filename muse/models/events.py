"""Data models for Muse events and calendar operations."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    GIG = "gig"
    SESSION = "session"
    REHEARSAL = "rehearsal"
    LESSON = "lesson"
    MEETING = "meeting"
    OTHER = "other"


class EventStatus(str, Enum):
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"


class GigEvent(BaseModel):
    """Represents any music-related calendar event."""

    id: Optional[str] = None  # Google Calendar event ID
    title: str = Field(description="Event title, e.g. 'Live at The Earl' or 'Session at West End Sound'")
    event_type: EventType = Field(description="Type of event")
    venue: str = Field(default="", description="Venue or studio name")
    address: str = Field(default="", description="Full address of the venue")
    start_time: datetime = Field(description="Event start time")
    end_time: datetime = Field(description="Event end time")
    load_in_time: Optional[datetime] = Field(default=None, description="Load-in time for gigs")
    soundcheck_time: Optional[datetime] = Field(default=None, description="Soundcheck time")
    set_time: Optional[datetime] = Field(default=None, description="Set/performance start time")
    pay: Optional[float] = Field(default=None, description="Payment amount in USD")
    pay_notes: str = Field(default="", description="Payment details, e.g. '$300 + door split'")
    contact_name: str = Field(default="", description="Booking contact name")
    contact_info: str = Field(default="", description="Contact email or phone")
    gear_notes: str = Field(default="", description="Equipment to bring")
    status: EventStatus = Field(default=EventStatus.CONFIRMED)
    notes: str = Field(default="", description="Additional notes")

    def to_calendar_description(self) -> str:
        """Format event details for Google Calendar description field."""
        lines = []
        if self.event_type:
            lines.append(f"Type: {self.event_type.value.title()}")
        if self.venue:
            lines.append(f"Venue: {self.venue}")
        if self.load_in_time:
            lines.append(f"Load-in: {self.load_in_time.strftime('%I:%M %p')}")
        if self.soundcheck_time:
            lines.append(f"Soundcheck: {self.soundcheck_time.strftime('%I:%M %p')}")
        if self.set_time:
            lines.append(f"Set Time: {self.set_time.strftime('%I:%M %p')}")
        if self.pay is not None:
            lines.append(f"Pay: ${self.pay:,.2f}")
        if self.pay_notes:
            lines.append(f"Pay Details: {self.pay_notes}")
        if self.contact_name:
            lines.append(f"Contact: {self.contact_name}")
        if self.contact_info:
            lines.append(f"Contact Info: {self.contact_info}")
        if self.gear_notes:
            lines.append(f"Gear: {self.gear_notes}")
        if self.notes:
            lines.append(f"Notes: {self.notes}")
        return "\n".join(lines)

    def to_summary(self) -> str:
        """Human-readable summary for chat responses."""
        emoji = {
            EventType.GIG: "🎸",
            EventType.SESSION: "🎙️",
            EventType.REHEARSAL: "🥁",
            EventType.LESSON: "📚",
            EventType.MEETING: "🤝",
            EventType.OTHER: "📅",
        }.get(self.event_type, "📅")

        lines = [f"{emoji} **{self.title}**"]
        if self.venue:
            lines.append(f"📍 {self.venue}")
        if self.address:
            lines.append(f"   {self.address}")

        date_str = self.start_time.strftime("%A, %B %d")
        time_str = f"{self.start_time.strftime('%I:%M %p')} - {self.end_time.strftime('%I:%M %p')}"
        lines.append(f"🕐 {date_str} · {time_str}")

        if self.load_in_time:
            lines.append(f"🚪 Load-in: {self.load_in_time.strftime('%I:%M %p')}")
        if self.set_time:
            lines.append(f"🎤 Set: {self.set_time.strftime('%I:%M %p')}")
        if self.pay is not None:
            lines.append(f"💰 ${self.pay:,.2f}")
        if self.pay_notes:
            lines.append(f"   {self.pay_notes}")
        if self.contact_name:
            lines.append(f"👤 Contact: {self.contact_name}")
        if self.gear_notes:
            lines.append(f"🎒 Gear: {self.gear_notes}")

        return "\n".join(lines)


class ConflictInfo(BaseModel):
    """Information about a scheduling conflict."""

    conflicting_event: GigEvent
    overlap_type: str = Field(description="'full' if completely overlapping, 'partial' if partially")
    message: str = Field(description="Human-readable conflict description")


class AvailabilitySlot(BaseModel):
    """An available time slot."""

    start: datetime
    end: datetime
    duration_hours: float
