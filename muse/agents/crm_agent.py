"""CRM Agent — manages the artist's professional network.

Handles contacts, interactions/meeting notes, relationship tracking,
and cross-references invoices and calendar events for full context.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from muse.agents.base import BaseAgent
from muse.config import config
from muse.tools.crm_tools import CRMTools

logger = logging.getLogger(__name__)

# ── System Prompt ────────────────────────────────────────────────────

CRM_SYSTEM_PROMPT = f"""You are the CRM Agent for Muse, an AI manager for independent musicians.

Your job is to help the artist manage their professional network — venues, studios, promoters, labels, collaborators, and other music industry contacts. You track who they work with, keep notes from meetings and calls, and help them maintain strong relationships.

## How You Operate

You are conversational, efficient, and music-industry-aware. You understand the relationships musicians maintain:

- **Venues** — bookers, talent buyers, sound engineers. Track capacity, backline, typical pay, door deals.
- **Studios** — engineers, producers. Track rates, preferred rooms/gear, session history.
- **Promoters** — festival promoters, booking agents. Track festivals, typical offers, deadlines.
- **Labels & Management** — A&R contacts, managers, publishers. Track deal status, conversations.
- **Collaborators** — other musicians, producers, photographers, videographers. Track project history.

## Rules

1. When the artist mentions a new person or organization, offer to add them as a contact.
2. When the artist finishes a meeting, call, or session, offer to log the interaction.
3. When showing a contact profile, include their recent interaction history and any pending follow-ups.
4. For the contact summary, cross-reference invoices and events to give a complete picture of the relationship.
5. Keep notes practical and actionable. Musicians are busy — bullet points over paragraphs.
6. When a follow-up date is past due, mention it proactively if the artist asks about the contact.
7. Auto-update the last_contact_date whenever a new interaction is logged.

## Relationship Context

Good CRM means knowing the history:
- "What's my history with The Earl?" should pull invoices, events, and all notes.
- "When did I last talk to Dave?" should check the latest interaction date.
- "Who do I need to follow up with?" should search for interactions with pending follow-up dates.

## Important

- Today's date is {datetime.now().strftime("%A, %B %d, %Y")}.
- The artist's name is {config.ARTIST_NAME}.
- Be concise. Musicians are busy. Don't over-explain.
- When searching, try to find the right contact by name before asking the artist for an ID.
"""

# ── Tool Definitions ─────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "add_contact",
        "description": (
            "Add a new client/contact to the CRM. Use for venues, studios, "
            "promoters, labels, managers, collaborators, or any professional contact."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "organization_name": {
                    "type": "string",
                    "description": "Organization or venue name, e.g. 'The Earl', 'West End Sound'",
                },
                "contact_person": {
                    "type": "string",
                    "description": "Primary contact person name",
                },
                "email": {
                    "type": "string",
                    "description": "Contact email address",
                },
                "phone": {
                    "type": "string",
                    "description": "Contact phone number",
                },
                "role": {
                    "type": "string",
                    "enum": ["venue", "studio", "promoter", "label", "manager", "collaborator", "other"],
                    "description": "Type of contact/relationship",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Free-form tags, e.g. ['atlanta', 'rock', 'recurring']",
                },
                "notes": {
                    "type": "string",
                    "description": "General notes about this contact",
                },
                "typical_rate": {
                    "type": "string",
                    "description": "Typical rate, e.g. '$400/gig', '$75/hr'",
                },
                "payment_terms": {
                    "type": "string",
                    "description": "Payment terms, e.g. 'Net 15'",
                },
                "preferred_payment": {
                    "type": "string",
                    "description": "Preferred payment method, e.g. 'Venmo', 'Check'",
                },
                "relationship_status": {
                    "type": "string",
                    "enum": ["active", "inactive", "prospect", "past"],
                    "description": "Relationship status. Default: active",
                },
                "first_contact_date": {
                    "type": "string",
                    "description": "First contact date (YYYY-MM-DD). Defaults to today.",
                },
            },
            "required": ["organization_name", "role"],
        },
    },
    {
        "name": "search_contacts",
        "description": (
            "Search contacts by name, role, tag, or relationship status. "
            "Returns matching contacts with key details. Use with no arguments to list all contacts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search text — matches organization name, contact person, or email",
                },
                "role": {
                    "type": "string",
                    "enum": ["venue", "studio", "promoter", "label", "manager", "collaborator", "other"],
                    "description": "Filter by contact role",
                },
                "tag": {
                    "type": "string",
                    "description": "Filter by tag",
                },
                "relationship_status": {
                    "type": "string",
                    "enum": ["active", "inactive", "prospect", "past"],
                    "description": "Filter by relationship status",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_contact",
        "description": (
            "Get full profile of a contact including recent interactions. "
            "Shows all details plus the last 5 logged interactions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {
                    "type": "string",
                    "description": "The ID of the contact to retrieve",
                },
            },
            "required": ["contact_id"],
        },
    },
    {
        "name": "update_contact",
        "description": (
            "Update any field on a contact — name, email, phone, role, "
            "tags, notes, rate, payment info, or relationship status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {
                    "type": "string",
                    "description": "The ID of the contact to update",
                },
                "updates": {
                    "type": "object",
                    "description": (
                        "Key-value pairs to update. Allowed: organization_name, "
                        "contact_person, email, phone, role, tags, notes, "
                        "typical_rate, payment_terms, preferred_payment, "
                        "relationship_status, last_invoice_id, upcoming_event_id."
                    ),
                },
            },
            "required": ["contact_id", "updates"],
        },
    },
    {
        "name": "add_interaction",
        "description": (
            "Log a meeting note, call, email note, session note, or general "
            "interaction for a contact. Auto-updates the contact's last contact date."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {
                    "type": "string",
                    "description": "The ID of the contact this interaction is for",
                },
                "interaction_type": {
                    "type": "string",
                    "enum": ["meeting", "call", "email_note", "session_note", "general"],
                    "description": "Type of interaction. Default: general",
                },
                "content": {
                    "type": "string",
                    "description": "Meeting notes, follow-up items, session details, etc.",
                },
                "interaction_date": {
                    "type": "string",
                    "description": "Date of the interaction (YYYY-MM-DD). Defaults to today.",
                },
                "follow_up_date": {
                    "type": "string",
                    "description": "Optional follow-up reminder date (YYYY-MM-DD)",
                },
            },
            "required": ["contact_id", "content"],
        },
    },
    {
        "name": "list_interactions",
        "description": (
            "List interactions for a contact, optionally filtered by date range "
            "or type. Returns interactions in reverse chronological order."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {
                    "type": "string",
                    "description": "The ID of the contact",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start of date range (YYYY-MM-DD)",
                },
                "end_date": {
                    "type": "string",
                    "description": "End of date range (YYYY-MM-DD)",
                },
                "interaction_type": {
                    "type": "string",
                    "enum": ["meeting", "call", "email_note", "session_note", "general"],
                    "description": "Filter by interaction type",
                },
            },
            "required": ["contact_id"],
        },
    },
    {
        "name": "get_contact_summary",
        "description": (
            "Get a relationship overview: total invoiced, events together, "
            "last interaction, pending follow-ups. Cross-references invoices and calendar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {
                    "type": "string",
                    "description": "The ID of the contact to summarize",
                },
            },
            "required": ["contact_id"],
        },
    },
]


# ── Agent Class ──────────────────────────────────────────────────────


class CRMAgent(BaseAgent):
    """Manages the artist's professional network — contacts, interactions, relationships."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.crm = CRMTools()

    @property
    def name(self) -> str:
        return "CRMAgent"

    def system_prompt(self) -> str:
        return CRM_SYSTEM_PROMPT

    def tool_definitions(self) -> list[dict]:
        return TOOL_DEFINITIONS

    def execute_tool(self, tool_name: str, tool_input: dict) -> Any:
        """Route tool calls to CRMTools methods."""

        if tool_name == "add_contact":
            return self.crm.add_contact(
                organization_name=tool_input["organization_name"],
                contact_person=tool_input.get("contact_person", ""),
                email=tool_input.get("email", ""),
                phone=tool_input.get("phone", ""),
                role=tool_input.get("role", "other"),
                tags=tool_input.get("tags"),
                notes=tool_input.get("notes", ""),
                typical_rate=tool_input.get("typical_rate", ""),
                payment_terms=tool_input.get("payment_terms", ""),
                preferred_payment=tool_input.get("preferred_payment", ""),
                relationship_status=tool_input.get("relationship_status", "active"),
                first_contact_date=tool_input.get("first_contact_date"),
            )

        elif tool_name == "search_contacts":
            return self.crm.search_contacts(
                query=tool_input.get("query", ""),
                role=tool_input.get("role"),
                tag=tool_input.get("tag"),
                relationship_status=tool_input.get("relationship_status"),
            )

        elif tool_name == "get_contact":
            return self.crm.get_contact(
                contact_id=tool_input["contact_id"],
            )

        elif tool_name == "update_contact":
            return self.crm.update_contact(
                contact_id=tool_input["contact_id"],
                updates=tool_input["updates"],
            )

        elif tool_name == "add_interaction":
            return self.crm.add_interaction(
                contact_id=tool_input["contact_id"],
                interaction_type=tool_input.get("interaction_type", "general"),
                content=tool_input["content"],
                interaction_date=tool_input.get("interaction_date"),
                follow_up_date=tool_input.get("follow_up_date"),
            )

        elif tool_name == "list_interactions":
            return self.crm.list_interactions(
                contact_id=tool_input["contact_id"],
                start_date=tool_input.get("start_date"),
                end_date=tool_input.get("end_date"),
                interaction_type=tool_input.get("interaction_type"),
            )

        elif tool_name == "get_contact_summary":
            return self.crm.get_contact_summary(
                contact_id=tool_input["contact_id"],
            )

        else:
            return {"error": f"Unknown tool: {tool_name}"}
