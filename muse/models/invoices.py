"""Data models for Muse invoice operations."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class InvoiceLineItem(BaseModel):
    """A single line item on an invoice."""

    id: Optional[str] = None
    description: str = Field(description="Line item description, e.g. 'Live performance at The Earl'")
    amount: float = Field(description="Amount in USD")
    event_date: Optional[str] = Field(default=None, description="Date of the event (ISO format)")
    event_type: Optional[str] = Field(default=None, description="Type: gig, session, rehearsal, lesson, etc.")
    venue: str = Field(default="", description="Venue or studio name")


class Invoice(BaseModel):
    """Represents an invoice for music services."""

    id: Optional[str] = None
    invoice_number: str = Field(default="", description="Human-readable invoice number, e.g. INV-2026-001")
    artist_name: str = Field(default="", description="Artist/business name (the payee)")
    artist_email: str = Field(default="", description="Artist email for the invoice header")
    client_name: str = Field(description="Client/venue name (the payer)")
    client_email: str = Field(default="", description="Client email address")
    line_items: list[InvoiceLineItem] = Field(default_factory=list, description="Invoice line items")
    status: InvoiceStatus = Field(default=InvoiceStatus.DRAFT)
    invoice_date: Optional[str] = Field(default=None, description="Invoice date (ISO format)")
    due_date: Optional[str] = Field(default=None, description="Payment due date (ISO format)")
    payment_terms: str = Field(default="Due upon receipt", description="Payment terms")
    notes: str = Field(default="", description="Additional notes on the invoice")
    payment_date: Optional[str] = Field(default=None, description="Date payment was received")
    payment_notes: str = Field(default="", description="Payment method or reference")
    created_at: Optional[str] = Field(default=None, description="Record creation timestamp")

    @property
    def total_amount(self) -> float:
        """Calculate total from line items."""
        return sum(item.amount for item in self.line_items)

    def to_preview(self) -> str:
        """Format invoice for artist review before generating PDF."""
        status_emoji = {
            InvoiceStatus.DRAFT: "📝",
            InvoiceStatus.SENT: "📤",
            InvoiceStatus.PAID: "✅",
            InvoiceStatus.OVERDUE: "⚠️",
            InvoiceStatus.CANCELLED: "❌",
        }.get(self.status, "📄")

        lines = [
            f"{status_emoji} **Invoice {self.invoice_number}**",
            f"  Status: {self.status.value.upper()}",
            f"  To: {self.client_name}",
        ]
        if self.client_email:
            lines.append(f"  Email: {self.client_email}")
        lines.append(f"  Date: {self.invoice_date or 'Not set'}")
        lines.append(f"  Due: {self.due_date or self.payment_terms}")
        lines.append("")
        lines.append("  **Line Items:**")
        for item in self.line_items:
            date_str = f" ({item.event_date})" if item.event_date else ""
            venue_str = f" @ {item.venue}" if item.venue else ""
            lines.append(f"    - {item.description}{venue_str}{date_str} — ${item.amount:,.2f}")
        lines.append("")
        lines.append(f"  **Total: ${self.total_amount:,.2f}**")
        if self.notes:
            lines.append(f"  Notes: {self.notes}")
        if self.payment_date:
            lines.append(f"  Paid: {self.payment_date}")
            if self.payment_notes:
                lines.append(f"  Payment ref: {self.payment_notes}")

        return "\n".join(lines)
