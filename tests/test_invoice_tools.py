import os


def create(invoices, client="Smith's Olde Bar", amounts=(350,), **kw):
    items = [{"description": f"Item {i}", "amount": a} for i, a in enumerate(amounts)]
    return invoices.create_invoice(client_name=client, line_items=items, **kw)


def test_seed_data(invoices):
    numbers = {i["invoice_number"] for i in invoices.list_invoices()}
    assert numbers == {"INV-2026-001", "INV-2026-002"}


def test_create_invoice_totals_and_draft_status(invoices):
    result = create(invoices, amounts=(300, 50.5))
    assert result["status"] == "created"
    assert result["total"] == 350.5

    invoice = invoices.get_invoice(result["invoice_id"])
    assert invoice["status"] == "draft"
    assert invoice["total"] == 350.5
    assert len(invoice["line_items"]) == 2


def test_invoice_numbers_are_sequential(invoices):
    first = create(invoices)["invoice_number"]
    second = create(invoices)["invoice_number"]
    assert int(second.rsplit("-", 1)[1]) == int(first.rsplit("-", 1)[1]) + 1


def test_list_filters_by_status(invoices):
    create(invoices)
    assert {i["status"] for i in invoices.list_invoices(status="draft")} == {"draft"}
    assert [i["client_name"] for i in invoices.list_invoices(status="paid")] == ["The Earl"]


def test_mark_paid(invoices):
    inv = create(invoices)
    result = invoices.mark_paid(inv["invoice_id"], payment_date="2026-11-20", payment_notes="Venmo")
    assert result["status"] == "marked_paid"
    stored = invoices.get_invoice(inv["invoice_id"])
    assert (stored["status"], stored["payment_date"], stored["payment_notes"]) == ("paid", "2026-11-20", "Venmo")


def test_missing_invoice_is_an_error(invoices):
    assert "error" in invoices.mark_paid("inv_nope")
    assert "error" in invoices.update_invoice("inv_nope", {"notes": "x"})
    assert "error" in invoices.get_invoice("inv_nope")
    assert "error" in invoices.generate_pdf("inv_nope")


def test_update_invoice_only_allows_known_fields(invoices):
    inv = create(invoices)
    result = invoices.update_invoice(inv["invoice_id"], {"notes": "thanks", "id": "hijack"})
    assert result["updates"] == {"notes": "thanks"}
    assert invoices.get_invoice(inv["invoice_id"])["notes"] == "thanks"
    assert "error" in invoices.update_invoice(inv["invoice_id"], {"id": "hijack"})


def test_income_summary(invoices):
    # Seeds: $400 paid, $525 sent and past due.
    summary = invoices.get_income_summary()
    assert summary["total_invoiced"] == 925
    assert summary["total_paid"] == 400
    assert summary["total_outstanding"] == 525
    assert summary["overdue_count"] == 1


def test_income_summary_excludes_cancelled(invoices):
    inv = create(invoices, amounts=(1000,))
    invoices.update_invoice(inv["invoice_id"], {"status": "cancelled"})
    summary = invoices.get_income_summary()
    assert summary["total_invoiced"] == 925
    assert summary["invoice_count"] == 2


def test_income_summary_date_range(invoices):
    summary = invoices.get_income_summary(start_date="2026-02-01", end_date="2026-02-01")
    assert summary["total_invoiced"] == 400


def test_generate_pdf(invoices, workdir):
    inv = create(invoices)
    result = invoices.generate_pdf(inv["invoice_id"])
    assert "error" not in result
    pdfs = os.listdir(os.path.join(workdir, "invoices"))
    assert len(pdfs) == 1 and pdfs[0].endswith(".pdf")
    with open(os.path.join(workdir, "invoices", pdfs[0]), "rb") as f:
        assert f.read(5) == b"%PDF-"
