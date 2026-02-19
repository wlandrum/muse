"""CRM tools for the CRM Agent.

Handles contact and interaction CRUD operations in SQLite.
Cross-references invoices and calendar events for relationship summaries.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from typing import Optional

from muse.config import config
from muse.models.contacts import (
    Contact,
    ContactRole,
    Interaction,
    InteractionType,
    RelationshipStatus,
)

logger = logging.getLogger(__name__)


class CRMTools:
    """Handles contact and interaction CRUD for the CRM Agent."""

    def __init__(self):
        self.db_path = config.DB_PATH
        self._init_db()

    # ── Database Setup ──────────────────────────────────────────────

    def _init_db(self) -> None:
        """Initialize SQLite tables for contacts and interactions."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id TEXT PRIMARY KEY,
                organization_name TEXT NOT NULL,
                contact_person TEXT NOT NULL DEFAULT '',
                email TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                role TEXT NOT NULL DEFAULT 'other',
                tags TEXT DEFAULT '[]',
                notes TEXT DEFAULT '',
                typical_rate TEXT DEFAULT '',
                payment_terms TEXT DEFAULT '',
                preferred_payment TEXT DEFAULT '',
                relationship_status TEXT DEFAULT 'active',
                first_contact_date TEXT,
                last_contact_date TEXT,
                last_invoice_id TEXT DEFAULT '',
                upcoming_event_id TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                id TEXT PRIMARY KEY,
                contact_id TEXT NOT NULL,
                interaction_type TEXT NOT NULL DEFAULT 'general',
                content TEXT NOT NULL DEFAULT '',
                interaction_date TEXT NOT NULL,
                follow_up_date TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(contact_id) REFERENCES contacts(id)
            )
        """)
        conn.commit()
        conn.close()
        self._seed_sample_data()
        logger.info(f"CRM database initialized at {self.db_path}")

    def _seed_sample_data(self) -> None:
        """Seed sample contacts and interactions for demo/testing."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)

        # Check if already seeded
        count = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        if count > 0:
            conn.close()
            return

        now = datetime.now()

        contacts = [
            {
                "id": "contact_the_earl_01",
                "organization_name": "The Earl",
                "contact_person": "Sarah Chen",
                "email": "sarah@theearlatlanta.com",
                "phone": "404-555-0123",
                "role": "venue",
                "tags": json.dumps(["atlanta", "rock", "recurring"]),
                "notes": "Great indie venue in East Atlanta. Full backline provided. Green room + drinks.",
                "typical_rate": "$400 guarantee + 15% door after 100",
                "payment_terms": "Net 15",
                "preferred_payment": "Venmo",
                "relationship_status": "active",
                "first_contact_date": "2025-09-15",
                "last_contact_date": "2026-03-01",
                "last_invoice_id": "inv_sample_001",
                "upcoming_event_id": "",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            },
            {
                "id": "contact_west_end_01",
                "organization_name": "West End Sound",
                "contact_person": "Miles Davis Jr",
                "email": "miles@westendsound.com",
                "phone": "",
                "role": "studio",
                "tags": json.dumps(["recording", "atlanta", "neve-console"]),
                "notes": "Great studio. Studio B has the Neve console. Miles is an incredible engineer.",
                "typical_rate": "$75/hr (4-hr minimum)",
                "payment_terms": "Net 15",
                "preferred_payment": "",
                "relationship_status": "active",
                "first_contact_date": "2025-11-01",
                "last_contact_date": "2026-02-28",
                "last_invoice_id": "inv_sample_002",
                "upcoming_event_id": "",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            },
            {
                "id": "contact_dave_promo_01",
                "organization_name": "Dave Promotions",
                "contact_person": "Dave Ramirez",
                "email": "bookings@davepromotes.com",
                "phone": "615-555-0789",
                "role": "promoter",
                "tags": json.dumps(["festivals", "summer", "nashville"]),
                "notes": "Festival promoter. Sweetwater Music Festival. Reliable, pays on time.",
                "typical_rate": "$1,500 flat + $200 travel",
                "payment_terms": "Net 30",
                "preferred_payment": "Check",
                "relationship_status": "active",
                "first_contact_date": "2026-01-10",
                "last_contact_date": "2026-02-25",
                "last_invoice_id": "",
                "upcoming_event_id": "",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            },
        ]

        interactions = [
            # The Earl
            {
                "id": "intr_earl_001",
                "contact_id": "contact_the_earl_01",
                "interaction_type": "email_note",
                "content": "Sarah sent booking inquiry for March 22 show. $400 guarantee + 15% door. Full backline. Need to confirm.",
                "interaction_date": "2026-03-01",
                "follow_up_date": "2026-03-05",
                "created_at": now.isoformat(),
            },
            {
                "id": "intr_earl_002",
                "contact_id": "contact_the_earl_01",
                "interaction_type": "general",
                "content": "Played Feb 1 show. Great turnout, 150+ people. Sarah mentioned wanting us back monthly. Invoice paid via Venmo on Feb 10.",
                "interaction_date": "2026-02-01",
                "follow_up_date": None,
                "created_at": now.isoformat(),
            },
            # West End Sound
            {
                "id": "intr_west_001",
                "contact_id": "contact_west_end_01",
                "interaction_type": "session_note",
                "content": "Tracked guitars and vocals over two sessions (Feb 10 + 12). Total 7 hours. Miles is great to work with. Invoiced $525.",
                "interaction_date": "2026-02-12",
                "follow_up_date": None,
                "created_at": now.isoformat(),
            },
            {
                "id": "intr_west_002",
                "contact_id": "contact_west_end_01",
                "interaction_type": "email_note",
                "content": "Miles followed up about scheduling next tracking session in March. Has openings on 10, 11, 14. Studio B with Neve console.",
                "interaction_date": "2026-02-28",
                "follow_up_date": "2026-03-07",
                "created_at": now.isoformat(),
            },
            # Dave Promotions
            {
                "id": "intr_dave_001",
                "contact_id": "contact_dave_promo_01",
                "interaction_type": "email_note",
                "content": "Confirmed for Sweetwater Music Festival June 14. Main Stage, 4:30-5:30pm. $1,500 + $200 travel. Need to send stage plot and input list by May 1.",
                "interaction_date": "2026-02-25",
                "follow_up_date": "2026-04-15",
                "created_at": now.isoformat(),
            },
            {
                "id": "intr_dave_002",
                "contact_id": "contact_dave_promo_01",
                "interaction_type": "call",
                "content": "Intro call with Dave. Discussed summer festival possibilities. He promotes 3-4 festivals in the Southeast. Seems well-connected.",
                "interaction_date": "2026-01-10",
                "follow_up_date": None,
                "created_at": now.isoformat(),
            },
        ]

        for c in contacts:
            conn.execute(
                """INSERT OR IGNORE INTO contacts
                (id, organization_name, contact_person, email, phone, role, tags,
                 notes, typical_rate, payment_terms, preferred_payment,
                 relationship_status, first_contact_date, last_contact_date,
                 last_invoice_id, upcoming_event_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    c["id"], c["organization_name"], c["contact_person"],
                    c["email"], c["phone"], c["role"], c["tags"],
                    c["notes"], c["typical_rate"], c["payment_terms"],
                    c["preferred_payment"], c["relationship_status"],
                    c["first_contact_date"], c["last_contact_date"],
                    c["last_invoice_id"], c["upcoming_event_id"],
                    c["created_at"], c["updated_at"],
                ),
            )

        for i in interactions:
            conn.execute(
                """INSERT OR IGNORE INTO interactions
                (id, contact_id, interaction_type, content, interaction_date,
                 follow_up_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    i["id"], i["contact_id"], i["interaction_type"],
                    i["content"], i["interaction_date"],
                    i["follow_up_date"], i["created_at"],
                ),
            )

        conn.commit()
        conn.close()
        logger.info("CRM seeded with 3 contacts and 6 interactions")

    # ── Tool Implementations ────────────────────────────────────────

    def add_contact(
        self,
        organization_name: str,
        contact_person: str = "",
        email: str = "",
        phone: str = "",
        role: str = "other",
        tags: list[str] | None = None,
        notes: str = "",
        typical_rate: str = "",
        payment_terms: str = "",
        preferred_payment: str = "",
        relationship_status: str = "active",
        first_contact_date: str | None = None,
    ) -> dict:
        """Create a new contact. Returns the created contact."""
        contact_id = f"contact_{uuid.uuid4().hex[:12]}"
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        first_date = first_contact_date or today

        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute(
            """INSERT INTO contacts
            (id, organization_name, contact_person, email, phone, role, tags,
             notes, typical_rate, payment_terms, preferred_payment,
             relationship_status, first_contact_date, last_contact_date,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                contact_id, organization_name, contact_person,
                email, phone, role, json.dumps(tags or []),
                notes, typical_rate, payment_terms, preferred_payment,
                relationship_status, first_date, first_date,
                now.isoformat(), now.isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        logger.info(f"[CRM] Added contact {contact_id}: {organization_name}")
        return {
            "status": "created",
            "contact_id": contact_id,
            "organization_name": organization_name,
            "contact_person": contact_person,
            "role": role,
            "message": f"Contact '{organization_name}' added to your network.",
        }

    def search_contacts(
        self,
        query: str = "",
        role: str | None = None,
        tag: str | None = None,
        relationship_status: str | None = None,
    ) -> list[dict]:
        """Search contacts by name, role, tag, or status."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        sql = "SELECT * FROM contacts WHERE 1=1"
        params: list = []

        if query:
            sql += " AND (organization_name LIKE ? OR contact_person LIKE ? OR email LIKE ?)"
            q = f"%{query}%"
            params.extend([q, q, q])

        if role:
            sql += " AND role = ?"
            params.append(role)

        if tag:
            sql += " AND tags LIKE ?"
            params.append(f"%{tag}%")

        if relationship_status:
            sql += " AND relationship_status = ?"
            params.append(relationship_status)

        sql += " ORDER BY last_contact_date DESC"
        rows = conn.execute(sql, params).fetchall()
        conn.close()

        results = []
        for row in rows:
            results.append({
                "id": row["id"],
                "organization_name": row["organization_name"],
                "contact_person": row["contact_person"],
                "email": row["email"],
                "phone": row["phone"],
                "role": row["role"],
                "relationship_status": row["relationship_status"],
                "tags": json.loads(row["tags"]) if row["tags"] else [],
                "typical_rate": row["typical_rate"],
                "last_contact_date": row["last_contact_date"],
            })

        return results

    def get_contact(self, contact_id: str) -> dict:
        """Get full contact profile with recent interactions."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            "SELECT * FROM contacts WHERE id = ?", (contact_id,)
        ).fetchone()

        if not row:
            conn.close()
            return {"error": f"Contact not found: {contact_id}"}

        # Get last 5 interactions
        interactions = conn.execute(
            """SELECT * FROM interactions
            WHERE contact_id = ?
            ORDER BY interaction_date DESC
            LIMIT 5""",
            (contact_id,),
        ).fetchall()
        conn.close()

        interaction_list = [
            {
                "id": i["id"],
                "interaction_type": i["interaction_type"],
                "content": i["content"],
                "interaction_date": i["interaction_date"],
                "follow_up_date": i["follow_up_date"],
            }
            for i in interactions
        ]

        return {
            "id": row["id"],
            "organization_name": row["organization_name"],
            "contact_person": row["contact_person"],
            "email": row["email"],
            "phone": row["phone"],
            "role": row["role"],
            "tags": json.loads(row["tags"]) if row["tags"] else [],
            "notes": row["notes"],
            "typical_rate": row["typical_rate"],
            "payment_terms": row["payment_terms"],
            "preferred_payment": row["preferred_payment"],
            "relationship_status": row["relationship_status"],
            "first_contact_date": row["first_contact_date"],
            "last_contact_date": row["last_contact_date"],
            "last_invoice_id": row["last_invoice_id"],
            "upcoming_event_id": row["upcoming_event_id"],
            "recent_interactions": interaction_list,
        }

    def update_contact(self, contact_id: str, updates: dict) -> dict:
        """Update contact fields."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)

        allowed = {
            "organization_name", "contact_person", "email", "phone",
            "role", "tags", "notes", "typical_rate", "payment_terms",
            "preferred_payment", "relationship_status",
            "last_invoice_id", "upcoming_event_id",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed}

        if not filtered:
            conn.close()
            return {"error": f"No valid fields to update. Allowed: {', '.join(sorted(allowed))}"}

        # Serialize tags if present
        if "tags" in filtered and isinstance(filtered["tags"], list):
            filtered["tags"] = json.dumps(filtered["tags"])

        set_clauses = []
        params = []
        for key, value in filtered.items():
            set_clauses.append(f"{key} = ?")
            params.append(value)

        # Always update the updated_at timestamp
        set_clauses.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(contact_id)

        conn.execute(
            f"UPDATE contacts SET {', '.join(set_clauses)} WHERE id = ?", params
        )
        conn.commit()
        conn.close()

        return {"status": "updated", "contact_id": contact_id, "updates": updates}

    def add_interaction(
        self,
        contact_id: str,
        interaction_type: str = "general",
        content: str = "",
        interaction_date: str | None = None,
        follow_up_date: str | None = None,
    ) -> dict:
        """Log a new interaction for a contact. Auto-updates last_contact_date."""
        interaction_id = f"intr_{uuid.uuid4().hex[:12]}"
        now = datetime.now()
        int_date = interaction_date or now.strftime("%Y-%m-%d")

        conn = sqlite3.connect(self.db_path, check_same_thread=False)

        # Verify contact exists
        contact = conn.execute(
            "SELECT organization_name FROM contacts WHERE id = ?", (contact_id,)
        ).fetchone()
        if not contact:
            conn.close()
            return {"error": f"Contact not found: {contact_id}"}

        conn.execute(
            """INSERT INTO interactions
            (id, contact_id, interaction_type, content, interaction_date,
             follow_up_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                interaction_id, contact_id, interaction_type,
                content, int_date, follow_up_date, now.isoformat(),
            ),
        )

        # Auto-update last_contact_date on the contact
        conn.execute(
            "UPDATE contacts SET last_contact_date = ?, updated_at = ? WHERE id = ?",
            (int_date, now.isoformat(), contact_id),
        )

        conn.commit()
        conn.close()

        logger.info(f"[CRM] Added interaction {interaction_id} for {contact_id}")
        return {
            "status": "logged",
            "interaction_id": interaction_id,
            "contact_id": contact_id,
            "contact_name": contact[0],
            "interaction_type": interaction_type,
            "interaction_date": int_date,
            "follow_up_date": follow_up_date,
            "message": f"Interaction logged for {contact[0]}.",
        }

    def list_interactions(
        self,
        contact_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        interaction_type: str | None = None,
    ) -> list[dict]:
        """List interactions for a contact with optional filters."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        sql = "SELECT * FROM interactions WHERE contact_id = ?"
        params: list = [contact_id]

        if start_date:
            sql += " AND interaction_date >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND interaction_date <= ?"
            params.append(end_date)
        if interaction_type:
            sql += " AND interaction_type = ?"
            params.append(interaction_type)

        sql += " ORDER BY interaction_date DESC"
        rows = conn.execute(sql, params).fetchall()
        conn.close()

        return [
            {
                "id": row["id"],
                "interaction_type": row["interaction_type"],
                "content": row["content"],
                "interaction_date": row["interaction_date"],
                "follow_up_date": row["follow_up_date"],
            }
            for row in rows
        ]

    def get_contact_summary(self, contact_id: str) -> dict:
        """Relationship overview — cross-references invoices and events."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # Get the contact
        contact = conn.execute(
            "SELECT * FROM contacts WHERE id = ?", (contact_id,)
        ).fetchone()
        if not contact:
            conn.close()
            return {"error": f"Contact not found: {contact_id}"}

        org_name = contact["organization_name"]
        email = contact["email"]

        # Cross-reference invoices by client_name or client_email
        invoice_rows = conn.execute(
            """SELECT i.id, i.invoice_number, i.status, i.invoice_date,
                      COALESCE(SUM(li.amount), 0) as total
               FROM invoices i
               LEFT JOIN invoice_line_items li ON i.id = li.invoice_id
               WHERE i.client_name = ? OR i.client_email = ?
               GROUP BY i.id
               ORDER BY i.invoice_date DESC""",
            (org_name, email),
        ).fetchall()

        total_invoiced = sum(r["total"] for r in invoice_rows)
        total_paid = sum(r["total"] for r in invoice_rows if r["status"] == "paid")
        total_outstanding = sum(
            r["total"] for r in invoice_rows if r["status"] not in ("paid", "cancelled")
        )

        # Cross-reference events by venue or contact_info
        try:
            event_rows = conn.execute(
                """SELECT * FROM events
                   WHERE venue = ? OR contact_info LIKE ?
                   ORDER BY start_time DESC""",
                (org_name, f"%{email}%"),
            ).fetchall()
            event_count = len(event_rows)
            total_event_pay = sum(r["pay"] or 0 for r in event_rows)
        except Exception:
            # Events table might not exist if calendar hasn't been used
            event_count = 0
            total_event_pay = 0.0

        # Get interaction stats
        interaction_count = conn.execute(
            "SELECT COUNT(*) FROM interactions WHERE contact_id = ?",
            (contact_id,),
        ).fetchone()[0]

        last_interaction = conn.execute(
            """SELECT interaction_type, interaction_date, content
               FROM interactions WHERE contact_id = ?
               ORDER BY interaction_date DESC LIMIT 1""",
            (contact_id,),
        ).fetchone()

        # Pending follow-ups
        today = datetime.now().strftime("%Y-%m-%d")
        follow_ups = conn.execute(
            """SELECT interaction_type, content, follow_up_date
               FROM interactions
               WHERE contact_id = ? AND follow_up_date IS NOT NULL AND follow_up_date >= ?
               ORDER BY follow_up_date ASC""",
            (contact_id, today),
        ).fetchall()

        conn.close()

        return {
            "contact_id": contact_id,
            "organization_name": org_name,
            "contact_person": contact["contact_person"],
            "role": contact["role"],
            "relationship_status": contact["relationship_status"],
            "first_contact_date": contact["first_contact_date"],
            "last_contact_date": contact["last_contact_date"],
            # Invoice summary
            "invoice_count": len(invoice_rows),
            "total_invoiced": total_invoiced,
            "total_paid": total_paid,
            "total_outstanding": total_outstanding,
            # Event summary
            "event_count": event_count,
            "total_event_pay": total_event_pay,
            # Interaction summary
            "interaction_count": interaction_count,
            "last_interaction": {
                "type": last_interaction["interaction_type"],
                "date": last_interaction["interaction_date"],
                "content": last_interaction["content"][:100] + "..." if len(last_interaction["content"]) > 100 else last_interaction["content"],
            } if last_interaction else None,
            # Follow-ups
            "pending_follow_ups": [
                {
                    "type": f["interaction_type"],
                    "content": f["content"][:80] + "..." if len(f["content"]) > 80 else f["content"],
                    "follow_up_date": f["follow_up_date"],
                }
                for f in follow_ups
            ],
        }
