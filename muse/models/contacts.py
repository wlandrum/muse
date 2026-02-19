"""Data models for Muse CRM operations — contacts and interactions."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ContactRole(str, Enum):
    """Type of professional relationship."""

    VENUE = "venue"
    STUDIO = "studio"
    PROMOTER = "promoter"
    LABEL = "label"
    MANAGER = "manager"
    COLLABORATOR = "collaborator"
    OTHER = "other"


class RelationshipStatus(str, Enum):
    """Current status of the relationship."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    PROSPECT = "prospect"
    PAST = "past"


class InteractionType(str, Enum):
    """Type of logged interaction."""

    MEETING = "meeting"
    CALL = "call"
    EMAIL_NOTE = "email_note"
    SESSION_NOTE = "session_note"
    GENERAL = "general"


class Contact(BaseModel):
    """Represents a client/contact in the artist's professional network."""

    id: Optional[str] = None
    organization_name: str = Field(description="Organization or venue name")
    contact_person: str = Field(default="", description="Primary contact person name")
    email: str = Field(default="", description="Contact email address")
    phone: str = Field(default="", description="Contact phone number")
    role: ContactRole = Field(default=ContactRole.OTHER, description="Type of contact")
    tags: list[str] = Field(default_factory=list, description="Free-form tags")
    notes: str = Field(default="", description="General notes about this contact")
    typical_rate: str = Field(default="", description="Typical rate, e.g. '$400/gig'")
    payment_terms: str = Field(default="", description="Payment terms, e.g. 'Net 15'")
    preferred_payment: str = Field(default="", description="Preferred payment method")
    relationship_status: RelationshipStatus = Field(default=RelationshipStatus.ACTIVE)
    first_contact_date: Optional[str] = Field(default=None)
    last_contact_date: Optional[str] = Field(default=None)
    last_invoice_id: str = Field(default="")
    upcoming_event_id: str = Field(default="")
    created_at: Optional[str] = Field(default=None)
    updated_at: Optional[str] = Field(default=None)

    def to_summary(self) -> str:
        """Human-readable summary for chat responses."""
        role_emoji = {
            ContactRole.VENUE: "\U0001f3e0",
            ContactRole.STUDIO: "\U0001f399\ufe0f",
            ContactRole.PROMOTER: "\U0001f4e3",
            ContactRole.LABEL: "\U0001f4bf",
            ContactRole.MANAGER: "\U0001f4cb",
            ContactRole.COLLABORATOR: "\U0001f91d",
            ContactRole.OTHER: "\U0001f464",
        }.get(self.role, "\U0001f464")

        status_emoji = {
            RelationshipStatus.ACTIVE: "\U0001f7e2",
            RelationshipStatus.INACTIVE: "\U0001f7e1",
            RelationshipStatus.PROSPECT: "\U0001f535",
            RelationshipStatus.PAST: "\u26ab",
        }.get(self.relationship_status, "\u26aa")

        lines = [f"{role_emoji} **{self.organization_name}** {status_emoji}"]
        if self.contact_person:
            lines.append(f"  Contact: {self.contact_person}")
        if self.email:
            lines.append(f"  Email: {self.email}")
        if self.phone:
            lines.append(f"  Phone: {self.phone}")
        if self.typical_rate:
            lines.append(f"  Rate: {self.typical_rate}")
        if self.tags:
            lines.append(f"  Tags: {', '.join(self.tags)}")
        if self.last_contact_date:
            lines.append(f"  Last contact: {self.last_contact_date}")

        return "\n".join(lines)


class Interaction(BaseModel):
    """Represents a logged interaction/note for a contact."""

    id: Optional[str] = None
    contact_id: str = Field(description="ID of the linked contact")
    interaction_type: InteractionType = Field(default=InteractionType.GENERAL)
    content: str = Field(default="", description="Meeting notes, follow-up items, etc.")
    interaction_date: Optional[str] = Field(default=None)
    follow_up_date: Optional[str] = Field(default=None, description="Optional follow-up date")
    created_at: Optional[str] = Field(default=None)
