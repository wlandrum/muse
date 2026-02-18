"""Gmail API tools for the Email Agent.

Handles OAuth authentication and all email operations.
When Google credentials are not available, falls back to a local
SQLite-based email store for development and demos.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime
from email.mime.text import MIMEText
from typing import Optional

from muse.config import config

logger = logging.getLogger(__name__)

# Try to import Google API libraries — fall back gracefully if not available
try:
    from googleapiclient.discovery import build

    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    logger.info("Google API libraries not installed — using local email store")

MAX_BODY_LENGTH = 10000


class EmailTools:
    """Wraps Gmail API (or local fallback) for the Email Agent."""

    def __init__(self):
        self.service = None
        self.use_local = not GOOGLE_AVAILABLE
        self.db_path = config.DB_PATH

        if not self.use_local:
            try:
                self._authenticate()
            except Exception as e:
                logger.warning(f"Gmail auth failed: {e}. Using local email store.")
                self.use_local = True

        if self.use_local:
            self._init_local_db()

    # ── Authentication ──────────────────────────────────────────────

    def _authenticate(self) -> None:
        """Authenticate with Gmail API using a saved OAuth token.

        Uses a SEPARATE token file (token_gmail.json) to avoid
        scope conflicts with the calendar token.
        Tokens are managed by the Streamlit UI via muse.utils.google_oauth.
        If no valid token exists, raises RuntimeError to trigger local fallback.
        """
        from muse.utils.google_oauth import load_credentials

        creds = load_credentials(config.GOOGLE_GMAIL_TOKEN_PATH, config.GMAIL_SCOPES)
        if not creds:
            raise RuntimeError("Gmail not connected — using local mode")

        self.service = build("gmail", "v1", credentials=creds)
        logger.info("Gmail authenticated successfully")

    # ── Local SQLite Fallback ───────────────────────────────────────

    def _init_local_db(self) -> None:
        """Initialize local SQLite database for development/demo mode."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                id TEXT PRIMARY KEY,
                thread_id TEXT,
                subject TEXT DEFAULT '',
                sender TEXT DEFAULT '',
                to_addresses TEXT DEFAULT '[]',
                cc_addresses TEXT DEFAULT '[]',
                date TEXT,
                body_text TEXT DEFAULT '',
                snippet TEXT DEFAULT '',
                labels TEXT DEFAULT '["INBOX", "UNREAD"]',
                is_read INTEGER DEFAULT 0,
                has_attachments INTEGER DEFAULT 0,
                attachment_names TEXT DEFAULT '[]'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS drafts (
                id TEXT PRIMARY KEY,
                to_addresses TEXT DEFAULT '[]',
                cc_addresses TEXT DEFAULT '[]',
                subject TEXT DEFAULT '',
                body TEXT DEFAULT '',
                in_reply_to TEXT,
                thread_id TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
        conn.close()
        self._seed_sample_emails()
        logger.info(f"Local email store initialized at {self.db_path}")

    def _seed_sample_emails(self) -> None:
        """Insert sample booking emails for demo/testing."""
        samples = [
            {
                "id": "local_sample_001",
                "thread_id": "thread_001",
                "subject": "Booking Inquiry - March 22 at The Earl",
                "sender": "Sarah Chen <sarah@theearlatlanta.com>",
                "to_addresses": json.dumps([config.ARTIST_EMAIL or "artist@example.com"]),
                "date": "2026-03-01T10:30:00",
                "body_text": (
                    "Hey!\n\n"
                    "We'd love to have you play The Earl on Saturday, March 22. "
                    "We're thinking a 9pm set time, load-in at 5pm, soundcheck at 6:30pm. "
                    "We can offer $400 guarantee + 15% of door after first 100 tickets. "
                    "Full backline provided (Fender Twin, Ampeg SVT, drum kit). "
                    "Green room with drinks and food for the band.\n\n"
                    "Let me know if you're interested!\n\n"
                    "Sarah Chen\nTalent Buyer, The Earl\n404-555-0123"
                ),
                "snippet": "We'd love to have you play The Earl on Saturday, March 22...",
                "labels": json.dumps(["INBOX", "UNREAD"]),
                "is_read": 0,
            },
            {
                "id": "local_sample_002",
                "thread_id": "thread_002",
                "subject": "Session Rates - West End Sound",
                "sender": "Miles Davis Jr <miles@westendsound.com>",
                "to_addresses": json.dumps([config.ARTIST_EMAIL or "artist@example.com"]),
                "date": "2026-02-28T14:15:00",
                "body_text": (
                    "Hey,\n\n"
                    "Following up on our conversation about tracking next month. "
                    "My rate is $75/hour, minimum 4-hour block. "
                    "I have openings on March 10, 11, and 14. "
                    "Studio B has the Neve console you liked.\n\n"
                    "Let me know what works.\n\n"
                    "Miles"
                ),
                "snippet": "Following up on our conversation about tracking next month...",
                "labels": json.dumps(["INBOX", "UNREAD"]),
                "is_read": 0,
            },
            {
                "id": "local_sample_003",
                "thread_id": "thread_003",
                "subject": "Re: Summer Festival Lineup",
                "sender": "Dave Promotions <bookings@davepromotes.com>",
                "to_addresses": json.dumps([config.ARTIST_EMAIL or "artist@example.com"]),
                "date": "2026-02-25T09:00:00",
                "body_text": (
                    "Great news! You're confirmed for the Sweetwater Music Festival "
                    "on June 14. Your set is 4:30-5:30pm on the Main Stage. "
                    "Pay is $1,500 flat. Travel stipend of $200. "
                    "We'll need your stage plot and input list by May 1.\n\n"
                    "Full details and contract to follow next week.\n\n"
                    "Dave Ramirez\nDave Promotions\n615-555-0789"
                ),
                "snippet": "Great news! You're confirmed for the Sweetwater Music Festival...",
                "labels": json.dumps(["INBOX"]),
                "is_read": 1,
            },
        ]
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        for email in samples:
            conn.execute(
                """INSERT OR IGNORE INTO emails
                (id, thread_id, subject, sender, to_addresses, date, body_text,
                 snippet, labels, is_read)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    email["id"], email["thread_id"], email["subject"],
                    email["sender"], email["to_addresses"], email["date"],
                    email["body_text"], email["snippet"], email["labels"],
                    email["is_read"],
                ),
            )
        conn.commit()
        conn.close()

    # ── Tool Implementations ────────────────────────────────────────

    def list_emails(
        self,
        max_results: int = 20,
        label: str = "INBOX",
        unread_only: bool = False,
    ) -> list[dict]:
        """List emails from a label/folder."""
        if self.use_local:
            return self._local_list_emails(max_results, label, unread_only)
        return self._google_list_emails(max_results, label, unread_only)

    def read_email(self, message_id: str) -> dict:
        """Read the full content of an email by ID."""
        if self.use_local:
            return self._local_read_email(message_id)
        return self._google_read_email(message_id)

    def search_emails(self, query: str, max_results: int = 10) -> list[dict]:
        """Search emails using Gmail query syntax (or substring for local)."""
        if self.use_local:
            return self._local_search_emails(query, max_results)
        return self._google_search_emails(query, max_results)

    def draft_reply(
        self,
        message_id: str,
        body: str,
        cc: list[str] | None = None,
    ) -> dict:
        """Create a draft reply to an existing email. Does NOT send."""
        if self.use_local:
            return self._local_draft_reply(message_id, body, cc)
        return self._google_draft_reply(message_id, body, cc)

    def create_draft(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
    ) -> dict:
        """Create a new draft email. Does NOT send."""
        if self.use_local:
            return self._local_create_draft(to, subject, body, cc)
        return self._google_create_draft(to, subject, body, cc)

    def send_draft(self, draft_id: str) -> dict:
        """Send a previously created draft (after artist approval)."""
        if self.use_local:
            return self._local_send_draft(draft_id)
        return self._google_send_draft(draft_id)

    def modify_labels(
        self,
        message_id: str,
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
    ) -> dict:
        """Add/remove labels on a message."""
        if self.use_local:
            return self._local_modify_labels(message_id, add_labels, remove_labels)
        return self._google_modify_labels(message_id, add_labels, remove_labels)

    def extract_gig_details(self, message_id: str) -> dict:
        """Read an email and return content for gig detail extraction."""
        return self.read_email(message_id)

    # ── Google Gmail Implementations ────────────────────────────────

    def _decode_body(self, payload: dict) -> str:
        """Recursively extract text/plain body from Gmail message payload."""
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
        if payload.get("parts"):
            for part in payload["parts"]:
                text = self._decode_body(part)
                if text:
                    return text
        return ""

    def _get_header(self, headers: list[dict], name: str) -> str:
        """Extract a header value from Gmail message headers."""
        for h in headers:
            if h["name"].lower() == name.lower():
                return h["value"]
        return ""

    def _google_list_emails(
        self, max_results: int, label: str, unread_only: bool
    ) -> list[dict]:
        query = "is:unread" if unread_only else ""
        results = (
            self.service.users()
            .messages()
            .list(
                userId="me",
                labelIds=[label],
                maxResults=max_results,
                q=query or None,
            )
            .execute()
        )

        messages = []
        for msg_ref in results.get("messages", []):
            msg = (
                self.service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg_ref["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date", "To"],
                )
                .execute()
            )
            headers = msg.get("payload", {}).get("headers", [])
            labels = msg.get("labelIds", [])
            messages.append({
                "id": msg["id"],
                "thread_id": msg.get("threadId", ""),
                "subject": self._get_header(headers, "Subject"),
                "sender": self._get_header(headers, "From"),
                "date": self._get_header(headers, "Date"),
                "snippet": msg.get("snippet", ""),
                "is_read": "UNREAD" not in labels,
                "labels": labels,
            })

        return messages

    def _google_read_email(self, message_id: str) -> dict:
        msg = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        headers = msg.get("payload", {}).get("headers", [])
        labels = msg.get("labelIds", [])
        body = self._decode_body(msg.get("payload", {}))
        if len(body) > MAX_BODY_LENGTH:
            body = body[:MAX_BODY_LENGTH] + "\n\n[... truncated ...]"

        # Check for attachments
        parts = msg.get("payload", {}).get("parts", [])
        attachment_names = [
            p["filename"]
            for p in parts
            if p.get("filename")
        ]

        return {
            "id": msg["id"],
            "thread_id": msg.get("threadId", ""),
            "subject": self._get_header(headers, "Subject"),
            "sender": self._get_header(headers, "From"),
            "to": self._get_header(headers, "To"),
            "cc": self._get_header(headers, "Cc"),
            "date": self._get_header(headers, "Date"),
            "body_text": body,
            "snippet": msg.get("snippet", ""),
            "is_read": "UNREAD" not in labels,
            "labels": labels,
            "has_attachments": len(attachment_names) > 0,
            "attachment_names": attachment_names,
        }

    def _google_search_emails(self, query: str, max_results: int) -> list[dict]:
        results = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )

        messages = []
        for msg_ref in results.get("messages", []):
            msg = (
                self.service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg_ref["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )
            headers = msg.get("payload", {}).get("headers", [])
            labels = msg.get("labelIds", [])
            messages.append({
                "id": msg["id"],
                "thread_id": msg.get("threadId", ""),
                "subject": self._get_header(headers, "Subject"),
                "sender": self._get_header(headers, "From"),
                "date": self._get_header(headers, "Date"),
                "snippet": msg.get("snippet", ""),
                "is_read": "UNREAD" not in labels,
                "labels": labels,
            })

        return messages

    def _google_draft_reply(
        self, message_id: str, body: str, cc: list[str] | None
    ) -> dict:
        # Get original message for reply headers
        original = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="metadata",
                 metadataHeaders=["From", "Subject", "Message-ID", "To"])
            .execute()
        )
        headers = original.get("payload", {}).get("headers", [])
        reply_to = self._get_header(headers, "From")
        subject = self._get_header(headers, "Subject")
        message_id_header = self._get_header(headers, "Message-ID")

        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        msg = MIMEText(body)
        msg["to"] = reply_to
        msg["subject"] = subject
        if cc:
            msg["cc"] = ", ".join(cc)
        if message_id_header:
            msg["In-Reply-To"] = message_id_header
            msg["References"] = message_id_header

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        draft = (
            self.service.users()
            .drafts()
            .create(
                userId="me",
                body={
                    "message": {
                        "raw": raw,
                        "threadId": original.get("threadId", ""),
                    }
                },
            )
            .execute()
        )

        return {
            "status": "draft_created",
            "draft_id": draft["id"],
            "to": reply_to,
            "subject": subject,
            "body": body,
            "message": "Draft created. Show it to the artist for approval before sending.",
        }

    def _google_create_draft(
        self, to: list[str], subject: str, body: str, cc: list[str] | None
    ) -> dict:
        msg = MIMEText(body)
        msg["to"] = ", ".join(to)
        msg["subject"] = subject
        if cc:
            msg["cc"] = ", ".join(cc)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        draft = (
            self.service.users()
            .drafts()
            .create(userId="me", body={"message": {"raw": raw}})
            .execute()
        )

        return {
            "status": "draft_created",
            "draft_id": draft["id"],
            "to": to,
            "subject": subject,
            "body": body,
            "message": "Draft created. Show it to the artist for approval before sending.",
        }

    def _google_send_draft(self, draft_id: str) -> dict:
        result = (
            self.service.users()
            .drafts()
            .send(userId="me", body={"id": draft_id})
            .execute()
        )
        return {
            "status": "sent",
            "message_id": result.get("id", ""),
            "thread_id": result.get("threadId", ""),
            "message": "Email sent successfully.",
        }

    def _google_modify_labels(
        self,
        message_id: str,
        add_labels: list[str] | None,
        remove_labels: list[str] | None,
    ) -> dict:
        body: dict = {}
        if add_labels:
            body["addLabelIds"] = add_labels
        if remove_labels:
            body["removeLabelIds"] = remove_labels

        self.service.users().messages().modify(
            userId="me", id=message_id, body=body
        ).execute()

        return {
            "status": "labels_updated",
            "message_id": message_id,
            "added": add_labels or [],
            "removed": remove_labels or [],
        }

    # ── Local SQLite Implementations ────────────────────────────────

    def _local_list_emails(
        self, max_results: int, label: str, unread_only: bool
    ) -> list[dict]:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        query = "SELECT * FROM emails WHERE labels LIKE ?"
        params: list = [f"%{label}%"]

        if unread_only:
            query += " AND is_read = 0"

        query += " ORDER BY date DESC LIMIT ?"
        params.append(max_results)

        rows = conn.execute(query, params).fetchall()
        conn.close()

        return [
            {
                "id": row["id"],
                "thread_id": row["thread_id"],
                "subject": row["subject"],
                "sender": row["sender"],
                "date": row["date"],
                "snippet": row["snippet"],
                "is_read": bool(row["is_read"]),
                "labels": json.loads(row["labels"]),
            }
            for row in rows
        ]

    def _local_read_email(self, message_id: str) -> dict:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM emails WHERE id = ?", (message_id,)
        ).fetchone()
        conn.close()

        if not row:
            return {"error": f"Email not found: {message_id}"}

        return {
            "id": row["id"],
            "thread_id": row["thread_id"],
            "subject": row["subject"],
            "sender": row["sender"],
            "to": json.loads(row["to_addresses"]),
            "cc": json.loads(row["cc_addresses"]),
            "date": row["date"],
            "body_text": row["body_text"],
            "snippet": row["snippet"],
            "is_read": bool(row["is_read"]),
            "labels": json.loads(row["labels"]),
            "has_attachments": bool(row["has_attachments"]),
            "attachment_names": json.loads(row["attachment_names"]),
        }

    def _local_search_emails(self, query: str, max_results: int) -> list[dict]:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # Simple substring search across subject, sender, and body
        search_term = f"%{query}%"
        rows = conn.execute(
            """SELECT * FROM emails
            WHERE subject LIKE ? OR sender LIKE ? OR body_text LIKE ?
            ORDER BY date DESC LIMIT ?""",
            (search_term, search_term, search_term, max_results),
        ).fetchall()
        conn.close()

        return [
            {
                "id": row["id"],
                "thread_id": row["thread_id"],
                "subject": row["subject"],
                "sender": row["sender"],
                "date": row["date"],
                "snippet": row["snippet"],
                "is_read": bool(row["is_read"]),
                "labels": json.loads(row["labels"]),
            }
            for row in rows
        ]

    def _local_draft_reply(
        self, message_id: str, body: str, cc: list[str] | None
    ) -> dict:
        # Get original email for reply context
        original = self._local_read_email(message_id)
        if "error" in original:
            return original

        draft_id = f"draft_{uuid.uuid4().hex[:12]}"
        subject = original["subject"]
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        # Extract email address from sender string like "Name <email>"
        reply_to = original["sender"]

        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute(
            """INSERT INTO drafts
            (id, to_addresses, cc_addresses, subject, body, in_reply_to, thread_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                draft_id,
                json.dumps([reply_to]),
                json.dumps(cc or []),
                subject,
                body,
                message_id,
                original.get("thread_id", ""),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        return {
            "status": "draft_created",
            "draft_id": draft_id,
            "to": reply_to,
            "subject": subject,
            "body": body,
            "message": "Draft created. Show it to the artist for approval before sending.",
        }

    def _local_create_draft(
        self, to: list[str], subject: str, body: str, cc: list[str] | None
    ) -> dict:
        draft_id = f"draft_{uuid.uuid4().hex[:12]}"

        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute(
            """INSERT INTO drafts
            (id, to_addresses, cc_addresses, subject, body, in_reply_to, thread_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                draft_id,
                json.dumps(to),
                json.dumps(cc or []),
                subject,
                body,
                None,
                None,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        return {
            "status": "draft_created",
            "draft_id": draft_id,
            "to": to,
            "subject": subject,
            "body": body,
            "message": "Draft created. Show it to the artist for approval before sending.",
        }

    def _local_send_draft(self, draft_id: str) -> dict:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM drafts WHERE id = ?", (draft_id,)
        ).fetchone()

        if not row:
            conn.close()
            return {"error": f"Draft not found: {draft_id}"}

        # Move draft to sent emails
        sent_id = f"sent_{uuid.uuid4().hex[:12]}"
        conn.execute(
            """INSERT INTO emails
            (id, thread_id, subject, sender, to_addresses, cc_addresses, date,
             body_text, snippet, labels, is_read)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sent_id,
                row["thread_id"] or f"thread_{uuid.uuid4().hex[:8]}",
                row["subject"],
                config.ARTIST_EMAIL or "artist@example.com",
                row["to_addresses"],
                row["cc_addresses"],
                datetime.now().isoformat(),
                row["body"],
                row["body"][:100],
                json.dumps(["SENT"]),
                1,
            ),
        )
        # Remove draft
        conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
        conn.commit()
        conn.close()

        return {
            "status": "sent",
            "message_id": sent_id,
            "message": "Email sent successfully.",
        }

    def _local_modify_labels(
        self,
        message_id: str,
        add_labels: list[str] | None,
        remove_labels: list[str] | None,
    ) -> dict:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT labels, is_read FROM emails WHERE id = ?", (message_id,)
        ).fetchone()

        if not row:
            conn.close()
            return {"error": f"Email not found: {message_id}"}

        labels = set(json.loads(row["labels"]))
        is_read = row["is_read"]

        if add_labels:
            labels.update(add_labels)
        if remove_labels:
            labels -= set(remove_labels)

        # Sync is_read with UNREAD label
        if "UNREAD" in (remove_labels or []):
            is_read = 1
        if "UNREAD" in (add_labels or []):
            is_read = 0

        conn.execute(
            "UPDATE emails SET labels = ?, is_read = ? WHERE id = ?",
            (json.dumps(sorted(labels)), is_read, message_id),
        )
        conn.commit()
        conn.close()

        return {
            "status": "labels_updated",
            "message_id": message_id,
            "added": add_labels or [],
            "removed": remove_labels or [],
        }
