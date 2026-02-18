"""Invoice Agent — handles billing, PDF generation, payment tracking, and income reporting for musicians."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from muse.agents.base import BaseAgent
from muse.config import config
from muse.tools.invoice_tools import InvoiceTools

logger = logging.getLogger(__name__)


INVOICE_SYSTEM_PROMPT = f"""You are the Invoice Agent for Muse, an AI manager for independent musicians.

Your job is to help the artist create invoices, track payments, generate professional PDFs, and understand their income. The artist's name is {config.ARTIST_NAME}.

## How You Operate

You are conversational, efficient, and music-industry-aware. You understand how musicians get paid:

- **Gig guarantees** — flat rate for a performance (e.g., "$400 for a 1-hour set")
- **Door splits** — percentage of ticket sales after a threshold (e.g., "$300 + 15% after 100 tickets")
- **Session rates** — hourly or per-track rates for recording (e.g., "$75/hour, 4-hour minimum")
- **Lesson rates** — per lesson or monthly rate (e.g., "$60/hour, weekly")
- **Deposits** — partial payment upfront, balance due after the event
- **Flat fees** — one-time payments for sync licensing, session work, etc.

## Rules

1. When creating an invoice, always show a preview first and confirm with the artist before generating the PDF.
2. Each invoice gets a sequential number (INV-YYYY-NNN format).
3. Default payment terms are "{config.INVOICE_PAYMENT_TERMS}" unless the artist specifies otherwise.
4. When the artist mentions a gig with pay, help them turn it into an invoice — suggest line items based on the details.
5. For income summaries, break down by paid vs. outstanding and flag overdue invoices.
6. Be smart about line item descriptions — include the event type, venue, and date for clarity.
7. When marking invoices as paid, ask about the payment method (Venmo, Zelle, cash, check, etc.) for record-keeping.

## Invoice Workflow

1. Artist says "create an invoice for [client/gig]"
2. You gather details: client name, line items (description + amount), payment terms
3. Create the invoice (DRAFT status) and show a preview
4. Artist approves → you generate the PDF
5. Artist can optionally send via email (routes to Email Agent)
6. Later: artist marks as paid when they receive payment

## Important

- Today's date is {datetime.now().strftime("%A, %B %d, %Y")}.
- The artist's name is {config.ARTIST_NAME}.
- The artist's email is {config.ARTIST_EMAIL or "not configured"}.
- Default payment terms: {config.INVOICE_PAYMENT_TERMS}.
- Be concise. Musicians are busy. Don't over-explain.
"""


TOOL_DEFINITIONS = [
    {
        "name": "create_invoice",
        "description": (
            "Create a new invoice for the artist. Creates it as a DRAFT. "
            "Always show the preview to the artist before generating a PDF."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_name": {
                    "type": "string",
                    "description": "Client/venue name (the payer)",
                },
                "line_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "Line item description, e.g. 'Live performance - Saturday Night Showcase'",
                            },
                            "amount": {
                                "type": "number",
                                "description": "Amount in USD",
                            },
                            "event_date": {
                                "type": "string",
                                "description": "Event date in ISO format (YYYY-MM-DD)",
                            },
                            "event_type": {
                                "type": "string",
                                "description": "Type: gig, session, rehearsal, lesson, other",
                            },
                            "venue": {
                                "type": "string",
                                "description": "Venue or studio name",
                            },
                        },
                        "required": ["description", "amount"],
                    },
                    "description": "List of line items with descriptions and amounts",
                },
                "client_email": {
                    "type": "string",
                    "description": "Client email address for the invoice",
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes on the invoice",
                },
                "payment_terms": {
                    "type": "string",
                    "description": "Payment terms, e.g. 'Net 15', 'Due upon receipt'. Default: config value.",
                },
                "due_date": {
                    "type": "string",
                    "description": "Payment due date in ISO format (YYYY-MM-DD)",
                },
            },
            "required": ["client_name", "line_items"],
        },
    },
    {
        "name": "list_invoices",
        "description": (
            "List invoices, optionally filtered by date range and/or status. "
            "Shows invoice number, client, total, and status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start of date range (YYYY-MM-DD). Optional.",
                },
                "end_date": {
                    "type": "string",
                    "description": "End of date range (YYYY-MM-DD). Optional.",
                },
                "status": {
                    "type": "string",
                    "enum": ["draft", "sent", "paid", "overdue", "cancelled"],
                    "description": "Filter by invoice status. Optional.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_invoice",
        "description": "Get full details of a specific invoice including all line items.",
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {
                    "type": "string",
                    "description": "The ID of the invoice to retrieve",
                },
            },
            "required": ["invoice_id"],
        },
    },
    {
        "name": "update_invoice",
        "description": (
            "Update fields on an existing invoice. Can change client info, "
            "status, due date, payment terms, or notes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {
                    "type": "string",
                    "description": "The ID of the invoice to update",
                },
                "updates": {
                    "type": "object",
                    "description": (
                        "Key-value pairs of fields to update. Allowed fields: "
                        "client_name, client_email, status, due_date, payment_terms, "
                        "notes, payment_date, payment_notes."
                    ),
                },
            },
            "required": ["invoice_id", "updates"],
        },
    },
    {
        "name": "mark_paid",
        "description": (
            "Mark an invoice as paid. Ask the artist about payment date "
            "and method (Venmo, Zelle, cash, check, etc.) for record-keeping."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {
                    "type": "string",
                    "description": "The ID of the invoice to mark as paid",
                },
                "payment_date": {
                    "type": "string",
                    "description": "Date payment was received (YYYY-MM-DD). Defaults to today.",
                },
                "payment_notes": {
                    "type": "string",
                    "description": "Payment method or reference, e.g. 'Venmo', 'Check #1234'",
                },
            },
            "required": ["invoice_id"],
        },
    },
    {
        "name": "generate_pdf",
        "description": (
            "Generate a professional PDF for an invoice. Returns the file path. "
            "Only generate after the artist has reviewed and approved the invoice."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {
                    "type": "string",
                    "description": "The ID of the invoice to generate a PDF for",
                },
            },
            "required": ["invoice_id"],
        },
    },
    {
        "name": "get_income_summary",
        "description": (
            "Get an income summary showing total invoiced, paid, outstanding, "
            "and overdue amounts. Optionally filter by date range."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start of date range (YYYY-MM-DD). Optional — omit for all time.",
                },
                "end_date": {
                    "type": "string",
                    "description": "End of date range (YYYY-MM-DD). Optional — omit for all time.",
                },
            },
            "required": [],
        },
    },
]


class InvoiceAgent(BaseAgent):
    """Manages invoicing — creation, PDF generation, payment tracking, income reporting."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.invoices = InvoiceTools()

    @property
    def name(self) -> str:
        return "InvoiceAgent"

    def system_prompt(self) -> str:
        return INVOICE_SYSTEM_PROMPT

    def tool_definitions(self) -> list[dict]:
        return TOOL_DEFINITIONS

    def execute_tool(self, tool_name: str, tool_input: dict) -> Any:
        """Route tool calls to InvoiceTools methods."""

        if tool_name == "create_invoice":
            return self.invoices.create_invoice(
                client_name=tool_input["client_name"],
                line_items=tool_input["line_items"],
                client_email=tool_input.get("client_email", ""),
                notes=tool_input.get("notes", ""),
                payment_terms=tool_input.get("payment_terms"),
                due_date=tool_input.get("due_date"),
            )

        elif tool_name == "list_invoices":
            return self.invoices.list_invoices(
                start_date=tool_input.get("start_date"),
                end_date=tool_input.get("end_date"),
                status=tool_input.get("status"),
            )

        elif tool_name == "get_invoice":
            return self.invoices.get_invoice(
                invoice_id=tool_input["invoice_id"],
            )

        elif tool_name == "update_invoice":
            return self.invoices.update_invoice(
                invoice_id=tool_input["invoice_id"],
                updates=tool_input["updates"],
            )

        elif tool_name == "mark_paid":
            return self.invoices.mark_paid(
                invoice_id=tool_input["invoice_id"],
                payment_date=tool_input.get("payment_date"),
                payment_notes=tool_input.get("payment_notes", ""),
            )

        elif tool_name == "generate_pdf":
            return self.invoices.generate_pdf(
                invoice_id=tool_input["invoice_id"],
            )

        elif tool_name == "get_income_summary":
            return self.invoices.get_income_summary(
                start_date=tool_input.get("start_date"),
                end_date=tool_input.get("end_date"),
            )

        else:
            return {"error": f"Unknown tool: {tool_name}"}
