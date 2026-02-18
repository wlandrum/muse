"""Email Agent — handles inbox triage, reply drafting, gig detail extraction, and email search for musicians."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from muse.agents.base import BaseAgent
from muse.config import config
from muse.tools.email_tools import EmailTools

logger = logging.getLogger(__name__)


EMAIL_SYSTEM_PROMPT = f"""You are the Email Agent for Muse, an AI manager for independent musicians.

Your job is to manage the artist's email — reading the inbox, searching for messages, drafting replies, and extracting gig details from booking emails. The artist's name is {config.ARTIST_NAME}.

## How You Operate

You are conversational, efficient, and music-industry-aware. You understand the types of emails musicians receive:

- **Booking inquiries** from venues, promoters, and booking agents. These contain gig details: dates, times, pay, backline, hospitality.
- **Session offers** from studios, engineers, and producers. These contain rates, availability, and studio details.
- **Business emails** from labels, management, publishers, PRs, and sync licensing contacts.
- **Fan/press emails** from fans, journalists, and bloggers.
- **Spam/irrelevant** emails that can be archived or ignored.

## Rules

1. **NEVER auto-send any email.** Always create a draft first and show it to the artist for approval. The artist must explicitly say "send", "send it", or "looks good, send it" before you call send_draft.
2. When the artist asks to reply, draft the reply in a professional but warm tone that matches music industry norms. Show the draft and wait for approval.
3. When you see a booking email, proactively offer to extract gig details. These details could be used to create a calendar event later.
4. When listing emails, show them in reverse chronological order with clear formatting.
5. When searching, use Gmail query syntax for precision (e.g., "from:venue@email.com", "subject:booking", "is:unread").
6. For archiving: remove the INBOX label (don't delete). For starring: add the STARRED label. For marking as read: remove the UNREAD label.
7. Always summarize emails concisely — musicians are busy. Show subject, sender, date, and a brief snippet.
8. If the artist asks to "clean up" or "triage" their inbox, go through unread messages and categorize them.

## Gig Detail Extraction

When you read a booking email, look for and extract:
- Venue name and address
- Date and all times (load-in, soundcheck, set time, end time)
- Pay (guarantee, door split, percentage, etc.)
- Promoter/booker contact info (name, email, phone)
- Backline/gear provided
- Hospitality (green room, food, drinks, parking)
- Ticket link
- Any special requirements

Present extracted details in a clean, structured format and offer to create a calendar event with the Calendar Agent.

## Tone for Drafts

When drafting replies to booking emails, use a professional but personable tone:
- Acknowledge the offer warmly
- Confirm or ask about specific details (times, pay, gear)
- Keep it concise — no fluff
- Sign off with the artist's name: {config.ARTIST_NAME}

## Important

- Today's date is {datetime.now().strftime("%A, %B %d, %Y")}.
- The artist's email is {config.ARTIST_EMAIL or "not configured"}.
- The artist's timezone is {config.DEFAULT_TIMEZONE}.
- Be concise. Musicians are busy. Don't over-explain.
"""


TOOL_DEFINITIONS = [
    {
        "name": "list_emails",
        "description": (
            "List emails from the artist's inbox or a specific label. "
            "Returns message summaries (subject, sender, date, snippet)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of emails to return. Default: 20",
                },
                "label": {
                    "type": "string",
                    "enum": ["INBOX", "SENT", "DRAFT", "TRASH", "STARRED", "IMPORTANT", "SPAM"],
                    "description": "Gmail label/folder to list from. Default: INBOX",
                },
                "unread_only": {
                    "type": "boolean",
                    "description": "If true, only return unread emails. Default: false",
                },
            },
            "required": [],
        },
    },
    {
        "name": "read_email",
        "description": (
            "Read the full content of a specific email by its message ID. "
            "Use this after list_emails to get the complete body text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The ID of the email message to read",
                },
            },
            "required": ["message_id"],
        },
    },
    {
        "name": "search_emails",
        "description": (
            "Search emails using Gmail query syntax. Examples: "
            "'from:sarah@venue.com', 'subject:booking', 'is:unread', "
            "'has:attachment', 'after:2026/02/01'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Gmail search query. Supports operators like "
                        "from:, to:, subject:, is:unread, has:attachment, "
                        "after:, before:, label:, and free text."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results. Default: 10",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "draft_reply",
        "description": (
            "Create a draft reply to an existing email. This does NOT send the email — "
            "it creates a draft for the artist to review. Always show the draft to the "
            "artist and wait for approval before sending."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The ID of the email to reply to",
                },
                "body": {
                    "type": "string",
                    "description": "The reply text body",
                },
                "cc": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional CC addresses",
                },
            },
            "required": ["message_id", "body"],
        },
    },
    {
        "name": "create_draft",
        "description": (
            "Create a new draft email (not a reply). This does NOT send the email — "
            "it creates a draft for the artist to review."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Recipient email addresses",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line",
                },
                "body": {
                    "type": "string",
                    "description": "Email body text",
                },
                "cc": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional CC addresses",
                },
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "send_draft",
        "description": (
            "Send a previously created draft. ONLY call this after the artist has "
            "explicitly approved the draft by saying 'send', 'send it', 'looks good, send it', etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_id": {
                    "type": "string",
                    "description": "The ID of the draft to send",
                },
            },
            "required": ["draft_id"],
        },
    },
    {
        "name": "modify_labels",
        "description": (
            "Modify labels on an email message. Use to archive (remove INBOX), "
            "star (add STARRED), mark as read (remove UNREAD), mark as important "
            "(add IMPORTANT), or move to trash (add TRASH)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The ID of the email message",
                },
                "add_labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels to add (e.g. ['STARRED', 'IMPORTANT'])",
                },
                "remove_labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels to remove (e.g. ['INBOX', 'UNREAD'])",
                },
            },
            "required": ["message_id"],
        },
    },
    {
        "name": "extract_gig_details",
        "description": (
            "Read a booking/gig email and return its full content for structured "
            "detail extraction. After calling this, parse the email content to identify "
            "venue, dates, times, pay, contact info, backline, and other gig details. "
            "Present the extracted details to the artist and offer to create a calendar event."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The ID of the booking email to extract details from",
                },
            },
            "required": ["message_id"],
        },
    },
]


class EmailAgent(BaseAgent):
    """Manages the artist's email — inbox triage, replies, gig detail extraction."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.email = EmailTools()

    @property
    def name(self) -> str:
        return "EmailAgent"

    def system_prompt(self) -> str:
        return EMAIL_SYSTEM_PROMPT

    def tool_definitions(self) -> list[dict]:
        return TOOL_DEFINITIONS

    def execute_tool(self, tool_name: str, tool_input: dict) -> Any:
        """Route tool calls to EmailTools methods."""

        if tool_name == "list_emails":
            return self.email.list_emails(
                max_results=tool_input.get("max_results", 20),
                label=tool_input.get("label", "INBOX"),
                unread_only=tool_input.get("unread_only", False),
            )

        elif tool_name == "read_email":
            return self.email.read_email(
                message_id=tool_input["message_id"],
            )

        elif tool_name == "search_emails":
            return self.email.search_emails(
                query=tool_input["query"],
                max_results=tool_input.get("max_results", 10),
            )

        elif tool_name == "draft_reply":
            return self.email.draft_reply(
                message_id=tool_input["message_id"],
                body=tool_input["body"],
                cc=tool_input.get("cc"),
            )

        elif tool_name == "create_draft":
            return self.email.create_draft(
                to=tool_input["to"],
                subject=tool_input["subject"],
                body=tool_input["body"],
                cc=tool_input.get("cc"),
            )

        elif tool_name == "send_draft":
            return self.email.send_draft(
                draft_id=tool_input["draft_id"],
            )

        elif tool_name == "modify_labels":
            return self.email.modify_labels(
                message_id=tool_input["message_id"],
                add_labels=tool_input.get("add_labels"),
                remove_labels=tool_input.get("remove_labels"),
            )

        elif tool_name == "extract_gig_details":
            return self.email.extract_gig_details(
                message_id=tool_input["message_id"],
            )

        else:
            return {"error": f"Unknown tool: {tool_name}"}
