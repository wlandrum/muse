"""Data models for Muse email operations."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EmailLabel(str, Enum):
    INBOX = "INBOX"
    SENT = "SENT"
    DRAFT = "DRAFT"
    TRASH = "TRASH"
    UNREAD = "UNREAD"
    STARRED = "STARRED"
    IMPORTANT = "IMPORTANT"
    SPAM = "SPAM"


class EmailMessage(BaseModel):
    """Represents an email message."""

    id: Optional[str] = None
    thread_id: Optional[str] = None
    subject: str = Field(default="", description="Email subject line")
    sender: str = Field(default="", description="From address")
    to: list[str] = Field(default_factory=list, description="Recipient email addresses")
    cc: list[str] = Field(default_factory=list, description="CC addresses")
    date: Optional[datetime] = Field(default=None, description="Date received/sent")
    body_text: str = Field(default="", description="Plain text body")
    snippet: str = Field(default="", description="Short preview of the message")
    labels: list[str] = Field(default_factory=list, description="Gmail labels")
    is_read: bool = Field(default=False, description="Whether the email has been read")
    has_attachments: bool = Field(default=False, description="Whether email has attachments")
    attachment_names: list[str] = Field(default_factory=list, description="Names of attachments")

    def to_summary(self) -> str:
        """Human-readable one-line summary for chat responses."""
        read_icon = "" if self.is_read else " [NEW]"
        attach_icon = " [ATTACH]" if self.has_attachments else ""
        date_str = self.date.strftime("%b %d, %I:%M %p") if self.date else "Unknown date"
        return (
            f"{read_icon}{attach_icon} {self.subject}\n"
            f"  From: {self.sender}\n"
            f"  Date: {date_str}\n"
            f"  {self.snippet[:100]}..."
        )


class EmailDraft(BaseModel):
    """Represents a draft email for artist approval before sending."""

    id: Optional[str] = None
    to: list[str] = Field(description="Recipient email addresses")
    cc: list[str] = Field(default_factory=list, description="CC addresses")
    subject: str = Field(description="Email subject line")
    body: str = Field(description="Email body text")
    in_reply_to: Optional[str] = Field(default=None, description="Message ID being replied to")
    thread_id: Optional[str] = Field(default=None, description="Gmail thread ID for replies")

    def to_preview(self) -> str:
        """Format draft for artist review before sending."""
        cc_line = f"\n  CC: {', '.join(self.cc)}" if self.cc else ""
        return (
            f"--- DRAFT FOR REVIEW ---\n"
            f"  To: {', '.join(self.to)}{cc_line}\n"
            f"  Subject: {self.subject}\n"
            f"  ---\n"
            f"  {self.body}\n"
            f"  --- END DRAFT ---\n"
            f"\n  Reply 'send' to send, or tell me what to change."
        )


class ExtractedGigDetails(BaseModel):
    """Gig details extracted from a booking email."""

    venue: str = Field(default="", description="Venue name")
    address: str = Field(default="", description="Venue address")
    date: Optional[str] = Field(default=None, description="Gig date (ISO format if parseable)")
    load_in_time: Optional[str] = Field(default=None, description="Load-in time")
    soundcheck_time: Optional[str] = Field(default=None, description="Soundcheck time")
    set_time: Optional[str] = Field(default=None, description="Set/performance time")
    end_time: Optional[str] = Field(default=None, description="End time")
    pay: Optional[float] = Field(default=None, description="Payment amount in USD")
    pay_notes: str = Field(default="", description="Payment details")
    promoter_name: str = Field(default="", description="Promoter/booker name")
    promoter_email: str = Field(default="", description="Promoter/booker email")
    promoter_phone: str = Field(default="", description="Promoter/booker phone")
    backline_provided: str = Field(default="", description="Backline/gear provided by venue")
    hospitality: str = Field(default="", description="Hospitality details")
    ticket_link: str = Field(default="", description="Ticket purchase URL")
    additional_notes: str = Field(default="", description="Other details from the email")
    confidence: str = Field(default="low", description="Extraction confidence: high, medium, low")
    source_email_id: Optional[str] = Field(default=None, description="ID of the source email")
