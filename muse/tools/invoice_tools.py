"""Invoice tools for the Invoice Agent.

Handles invoice CRUD operations in SQLite and PDF generation
with ReportLab. No external API needed — invoices are stored locally.
"""

from __future__ import annotations

import io
import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Optional

from muse.config import config
from muse.models.invoices import Invoice, InvoiceLineItem, InvoiceStatus
from muse.utils.env import is_cloud

logger = logging.getLogger(__name__)

# Try to import ReportLab for PDF generation
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate,
        Table,
        TableStyle,
        Paragraph,
        Spacer,
    )

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.info("ReportLab not installed — PDF generation disabled")


class InvoiceTools:
    """Handles invoice CRUD and PDF generation for the Invoice Agent."""

    def __init__(self):
        self.db_path = config.DB_PATH
        self.output_dir = config.INVOICE_OUTPUT_DIR
        if not is_cloud():
            os.makedirs(self.output_dir, exist_ok=True)
        self._init_db()

    # ── Database Setup ──────────────────────────────────────────────

    def _init_db(self) -> None:
        """Initialize SQLite database for invoices."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id TEXT PRIMARY KEY,
                invoice_number TEXT NOT NULL,
                artist_name TEXT NOT NULL,
                artist_email TEXT DEFAULT '',
                client_name TEXT NOT NULL,
                client_email TEXT DEFAULT '',
                status TEXT DEFAULT 'draft',
                invoice_date TEXT NOT NULL,
                due_date TEXT,
                payment_terms TEXT DEFAULT 'Due upon receipt',
                notes TEXT DEFAULT '',
                payment_date TEXT,
                payment_notes TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invoice_line_items (
                id TEXT PRIMARY KEY,
                invoice_id TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                event_date TEXT,
                event_type TEXT,
                venue TEXT DEFAULT '',
                FOREIGN KEY(invoice_id) REFERENCES invoices(id)
            )
        """)
        conn.commit()
        conn.close()
        self._seed_sample_invoices()
        logger.info(f"Invoice database initialized at {self.db_path}")

    def _seed_sample_invoices(self) -> None:
        """Insert sample invoices for demo/testing."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)

        # Check if already seeded
        count = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        if count > 0:
            conn.close()
            return

        now = datetime.now()
        samples = [
            {
                "id": "inv_sample_001",
                "invoice_number": "INV-2026-001",
                "artist_name": config.ARTIST_NAME or "Artist",
                "artist_email": config.ARTIST_EMAIL or "artist@example.com",
                "client_name": "The Earl",
                "client_email": "sarah@theearlatlanta.com",
                "status": "paid",
                "invoice_date": "2026-02-01",
                "due_date": "2026-02-15",
                "payment_terms": "Net 15",
                "notes": "Live performance - Saturday night showcase",
                "payment_date": "2026-02-10",
                "payment_notes": "Venmo",
                "created_at": "2026-02-01T10:00:00",
                "line_items": [
                    {
                        "description": "Live performance - Saturday Night Showcase",
                        "amount": 400.00,
                        "event_date": "2026-02-01",
                        "event_type": "gig",
                        "venue": "The Earl",
                    },
                ],
            },
            {
                "id": "inv_sample_002",
                "invoice_number": "INV-2026-002",
                "artist_name": config.ARTIST_NAME or "Artist",
                "artist_email": config.ARTIST_EMAIL or "artist@example.com",
                "client_name": "West End Sound",
                "client_email": "miles@westendsound.com",
                "status": "sent",
                "invoice_date": "2026-02-15",
                "due_date": "2026-03-01",
                "payment_terms": "Net 15",
                "notes": "Recording session - tracking guitars and vocals",
                "payment_date": None,
                "payment_notes": "",
                "created_at": "2026-02-15T14:00:00",
                "line_items": [
                    {
                        "description": "Recording session - Guitar tracking (4 hours)",
                        "amount": 300.00,
                        "event_date": "2026-02-10",
                        "event_type": "session",
                        "venue": "West End Sound",
                    },
                    {
                        "description": "Recording session - Vocal tracking (3 hours)",
                        "amount": 225.00,
                        "event_date": "2026-02-12",
                        "event_type": "session",
                        "venue": "West End Sound",
                    },
                ],
            },
        ]

        for inv in samples:
            conn.execute(
                """INSERT OR IGNORE INTO invoices
                (id, invoice_number, artist_name, artist_email, client_name,
                 client_email, status, invoice_date, due_date, payment_terms,
                 notes, payment_date, payment_notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    inv["id"], inv["invoice_number"], inv["artist_name"],
                    inv["artist_email"], inv["client_name"], inv["client_email"],
                    inv["status"], inv["invoice_date"], inv["due_date"],
                    inv["payment_terms"], inv["notes"], inv["payment_date"],
                    inv["payment_notes"], inv["created_at"],
                ),
            )
            for item in inv["line_items"]:
                item_id = f"li_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """INSERT OR IGNORE INTO invoice_line_items
                    (id, invoice_id, description, amount, event_date, event_type, venue)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        item_id, inv["id"], item["description"], item["amount"],
                        item["event_date"], item["event_type"], item["venue"],
                    ),
                )

        conn.commit()
        conn.close()

    # ── Next Invoice Number ─────────────────────────────────────────

    def _next_invoice_number(self) -> str:
        """Generate the next sequential invoice number."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        row = conn.execute(
            "SELECT invoice_number FROM invoices ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        conn.close()

        year = datetime.now().year
        if row and row[0]:
            try:
                parts = row[0].split("-")
                seq = int(parts[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1

        return f"INV-{year}-{seq:03d}"

    # ── Tool Implementations ────────────────────────────────────────

    def create_invoice(
        self,
        client_name: str,
        line_items: list[dict],
        client_email: str = "",
        notes: str = "",
        payment_terms: str | None = None,
        due_date: str | None = None,
    ) -> dict:
        """Create a new invoice. Returns the invoice with ID."""
        invoice_id = f"inv_{uuid.uuid4().hex[:12]}"
        invoice_number = self._next_invoice_number()
        now = datetime.now()
        terms = payment_terms or config.INVOICE_PAYMENT_TERMS

        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute(
            """INSERT INTO invoices
            (id, invoice_number, artist_name, artist_email, client_name,
             client_email, status, invoice_date, due_date, payment_terms,
             notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                invoice_id, invoice_number,
                config.ARTIST_NAME or "Artist",
                config.ARTIST_EMAIL or "",
                client_name, client_email, "draft",
                now.strftime("%Y-%m-%d"),
                due_date, terms, notes,
                now.isoformat(),
            ),
        )

        total = 0.0
        created_items = []
        for item in line_items:
            item_id = f"li_{uuid.uuid4().hex[:12]}"
            amount = float(item.get("amount", 0))
            total += amount
            conn.execute(
                """INSERT INTO invoice_line_items
                (id, invoice_id, description, amount, event_date, event_type, venue)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    item_id, invoice_id,
                    item.get("description", ""),
                    amount,
                    item.get("event_date"),
                    item.get("event_type"),
                    item.get("venue", ""),
                ),
            )
            created_items.append({**item, "id": item_id})

        conn.commit()
        conn.close()

        return {
            "status": "created",
            "invoice_id": invoice_id,
            "invoice_number": invoice_number,
            "client_name": client_name,
            "total": total,
            "line_items": created_items,
            "message": "Invoice created as DRAFT. Review it and say 'generate PDF' to export.",
        }

    def list_invoices(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """List invoices, optionally filtered by date range and status."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        query = "SELECT * FROM invoices WHERE 1=1"
        params: list = []

        if start_date:
            query += " AND invoice_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND invoice_date <= ?"
            params.append(end_date)
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY invoice_date DESC"
        rows = conn.execute(query, params).fetchall()

        invoices = []
        for row in rows:
            # Get line items for each invoice
            items = conn.execute(
                "SELECT * FROM invoice_line_items WHERE invoice_id = ?",
                (row["id"],),
            ).fetchall()
            total = sum(item["amount"] for item in items)

            invoices.append({
                "id": row["id"],
                "invoice_number": row["invoice_number"],
                "client_name": row["client_name"],
                "client_email": row["client_email"],
                "status": row["status"],
                "invoice_date": row["invoice_date"],
                "due_date": row["due_date"],
                "total": total,
                "line_item_count": len(items),
                "payment_date": row["payment_date"],
            })

        conn.close()
        return invoices

    def get_invoice(self, invoice_id: str) -> dict:
        """Get full invoice details including line items."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()

        if not row:
            conn.close()
            return {"error": f"Invoice not found: {invoice_id}"}

        items = conn.execute(
            "SELECT * FROM invoice_line_items WHERE invoice_id = ? ORDER BY event_date",
            (invoice_id,),
        ).fetchall()
        conn.close()

        line_items = [
            {
                "id": item["id"],
                "description": item["description"],
                "amount": item["amount"],
                "event_date": item["event_date"],
                "event_type": item["event_type"],
                "venue": item["venue"],
            }
            for item in items
        ]

        total = sum(item["amount"] for item in items)

        return {
            "id": row["id"],
            "invoice_number": row["invoice_number"],
            "artist_name": row["artist_name"],
            "artist_email": row["artist_email"],
            "client_name": row["client_name"],
            "client_email": row["client_email"],
            "status": row["status"],
            "invoice_date": row["invoice_date"],
            "due_date": row["due_date"],
            "payment_terms": row["payment_terms"],
            "notes": row["notes"],
            "payment_date": row["payment_date"],
            "payment_notes": row["payment_notes"],
            "line_items": line_items,
            "total": total,
        }

    def update_invoice(self, invoice_id: str, updates: dict) -> dict:
        """Update invoice fields (status, notes, due_date, etc.)."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)

        # Only allow updating certain fields
        allowed = {
            "client_name", "client_email", "status", "due_date",
            "payment_terms", "notes", "payment_date", "payment_notes",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed}

        if not filtered:
            conn.close()
            return {"error": f"No valid fields to update. Allowed: {', '.join(sorted(allowed))}"}

        set_clauses = []
        params = []
        for key, value in filtered.items():
            set_clauses.append(f"{key} = ?")
            params.append(value)
        params.append(invoice_id)

        conn.execute(
            f"UPDATE invoices SET {', '.join(set_clauses)} WHERE id = ?", params
        )
        conn.commit()
        conn.close()

        return {"status": "updated", "invoice_id": invoice_id, "updates": filtered}

    def mark_paid(
        self,
        invoice_id: str,
        payment_date: str | None = None,
        payment_notes: str = "",
    ) -> dict:
        """Mark an invoice as paid."""
        pay_date = payment_date or datetime.now().strftime("%Y-%m-%d")

        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute(
            """UPDATE invoices
            SET status = 'paid', payment_date = ?, payment_notes = ?
            WHERE id = ?""",
            (pay_date, payment_notes, invoice_id),
        )
        conn.commit()
        conn.close()

        return {
            "status": "marked_paid",
            "invoice_id": invoice_id,
            "payment_date": pay_date,
            "payment_notes": payment_notes,
        }

    def generate_pdf(self, invoice_id: str) -> dict:
        """Generate a PDF for an invoice using ReportLab.

        On cloud: generates into memory and returns pdf_bytes.
        Locally: saves to file and returns filepath.
        """
        if not REPORTLAB_AVAILABLE:
            return {
                "error": "ReportLab is not installed. Run: pip install reportlab",
            }

        invoice_data = self.get_invoice(invoice_id)
        if "error" in invoice_data:
            return invoice_data

        filename = f"{invoice_data['invoice_number'].replace(' ', '_')}.pdf"

        if is_cloud():
            # Generate PDF into memory buffer
            buffer = io.BytesIO()
            self._build_pdf(invoice_data, buffer)
            pdf_bytes = buffer.getvalue()
            buffer.close()

            return {
                "status": "pdf_generated",
                "invoice_id": invoice_id,
                "invoice_number": invoice_data["invoice_number"],
                "filename": filename,
                "total": invoice_data["total"],
                "pdf_bytes": pdf_bytes,
                "message": f"PDF generated in memory ({len(pdf_bytes)} bytes)",
            }
        else:
            filepath = os.path.join(self.output_dir, filename)
            self._build_pdf(invoice_data, filepath)

            return {
                "status": "pdf_generated",
                "invoice_id": invoice_id,
                "invoice_number": invoice_data["invoice_number"],
                "filepath": filepath,
                "filename": filename,
                "total": invoice_data["total"],
                "message": f"PDF saved to {filepath}",
            }

    def get_income_summary(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        """Get income summary — total invoiced, paid, outstanding, overdue."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        query = "SELECT i.*, COALESCE(SUM(li.amount), 0) as total FROM invoices i LEFT JOIN invoice_line_items li ON i.id = li.invoice_id WHERE 1=1"
        params: list = []

        if start_date:
            query += " AND i.invoice_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND i.invoice_date <= ?"
            params.append(end_date)

        query += " GROUP BY i.id"
        rows = conn.execute(query, params).fetchall()
        conn.close()

        total_invoiced = 0.0
        total_paid = 0.0
        total_outstanding = 0.0
        total_overdue = 0.0
        invoice_count = len(rows)
        paid_count = 0
        outstanding_count = 0
        overdue_count = 0

        today = datetime.now().strftime("%Y-%m-%d")

        for row in rows:
            amount = row["total"]
            total_invoiced += amount

            if row["status"] == "paid":
                total_paid += amount
                paid_count += 1
            elif row["status"] == "cancelled":
                pass  # Skip cancelled
            else:
                total_outstanding += amount
                outstanding_count += 1
                if row["due_date"] and row["due_date"] < today:
                    total_overdue += amount
                    overdue_count += 1

        return {
            "total_invoiced": total_invoiced,
            "total_paid": total_paid,
            "total_outstanding": total_outstanding,
            "total_overdue": total_overdue,
            "invoice_count": invoice_count,
            "paid_count": paid_count,
            "outstanding_count": outstanding_count,
            "overdue_count": overdue_count,
            "period": {
                "start": start_date or "all time",
                "end": end_date or "present",
            },
        }

    # ── PDF Generation ──────────────────────────────────────────────

    def _build_pdf(self, data: dict, output) -> None:
        """Build a professional invoice PDF with ReportLab.

        Args:
            data: Invoice data dict.
            output: File path (str) or file-like object (BytesIO).
        """
        doc = SimpleDocTemplate(
            output,
            pagesize=letter,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )

        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            "InvoiceTitle",
            parent=styles["Heading1"],
            fontSize=24,
            spaceAfter=6,
            textColor=colors.HexColor("#1a1a2e"),
        )
        header_style = ParagraphStyle(
            "InvoiceHeader",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#555555"),
            spaceAfter=2,
        )
        label_style = ParagraphStyle(
            "Label",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#888888"),
        )
        value_style = ParagraphStyle(
            "Value",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#1a1a2e"),
        )
        total_style = ParagraphStyle(
            "Total",
            parent=styles["Normal"],
            fontSize=14,
            textColor=colors.HexColor("#1a1a2e"),
            alignment=2,  # Right align
        )
        notes_style = ParagraphStyle(
            "Notes",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#666666"),
        )

        elements = []

        # ── Header: Invoice title + number ──
        elements.append(Paragraph("INVOICE", title_style))
        elements.append(Paragraph(data["invoice_number"], header_style))
        elements.append(Spacer(1, 20))

        # ── From / To section ──
        from_to_data = [
            [
                Paragraph("<b>FROM</b>", label_style),
                Paragraph("<b>BILL TO</b>", label_style),
                Paragraph("<b>DETAILS</b>", label_style),
            ],
            [
                Paragraph(data.get("artist_name", "Artist"), value_style),
                Paragraph(data.get("client_name", ""), value_style),
                Paragraph(f"Date: {data.get('invoice_date', '')}", value_style),
            ],
            [
                Paragraph(data.get("artist_email", ""), header_style),
                Paragraph(data.get("client_email", ""), header_style),
                Paragraph(f"Due: {data.get('due_date', data.get('payment_terms', ''))}", value_style),
            ],
            [
                Paragraph("", header_style),
                Paragraph("", header_style),
                Paragraph(f"Status: {data.get('status', 'draft').upper()}", value_style),
            ],
        ]

        from_to_table = Table(
            from_to_data,
            colWidths=[2.3 * inch, 2.3 * inch, 2.3 * inch],
        )
        from_to_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        elements.append(from_to_table)
        elements.append(Spacer(1, 30))

        # ── Line Items Table ──
        table_header = ["Description", "Date", "Venue", "Amount"]
        table_data = [table_header]

        for item in data.get("line_items", []):
            table_data.append([
                item.get("description", ""),
                item.get("event_date", ""),
                item.get("venue", ""),
                f"${item.get('amount', 0):,.2f}",
            ])

        # Total row
        table_data.append(["", "", "TOTAL", f"${data.get('total', 0):,.2f}"])

        items_table = Table(
            table_data,
            colWidths=[3.0 * inch, 1.2 * inch, 1.5 * inch, 1.2 * inch],
        )
        items_table.setStyle(TableStyle([
            # Header row
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            # Data rows
            ("FONTNAME", (0, 1), (-1, -2), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -2), 9),
            ("TOPPADDING", (0, 1), (-1, -2), 6),
            ("BOTTOMPADDING", (0, 1), (-1, -2), 6),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f5f5f5")]),
            # Total row
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, -1), (-1, -1), 11),
            ("TOPPADDING", (0, -1), (-1, -1), 10),
            ("LINEABOVE", (0, -1), (-1, -1), 1.5, colors.HexColor("#1a1a2e")),
            # Grid
            ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (-2, -1), (-2, -1), "RIGHT"),
            ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#1a1a2e")),
        ]))
        elements.append(items_table)
        elements.append(Spacer(1, 30))

        # ── Payment Terms ──
        if data.get("payment_terms"):
            elements.append(Paragraph(f"<b>Payment Terms:</b> {data['payment_terms']}", notes_style))
            elements.append(Spacer(1, 6))

        # ── Notes ──
        if data.get("notes"):
            elements.append(Paragraph(f"<b>Notes:</b> {data['notes']}", notes_style))
            elements.append(Spacer(1, 6))

        # ── Payment Status ──
        if data.get("status") == "paid" and data.get("payment_date"):
            elements.append(Spacer(1, 12))
            paid_style = ParagraphStyle(
                "Paid",
                parent=styles["Normal"],
                fontSize=12,
                textColor=colors.HexColor("#16a34a"),
            )
            pay_text = f"PAID on {data['payment_date']}"
            if data.get("payment_notes"):
                pay_text += f" ({data['payment_notes']})"
            elements.append(Paragraph(pay_text, paid_style))

        # ── Footer ──
        elements.append(Spacer(1, 40))
        footer_style = ParagraphStyle(
            "Footer",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.HexColor("#aaaaaa"),
            alignment=1,  # Center
        )
        elements.append(Paragraph("Generated by Muse — AI Manager for Independent Artists", footer_style))

        doc.build(elements)
        logger.info(f"Invoice PDF generated: {output if isinstance(output, str) else 'in-memory buffer'}")
