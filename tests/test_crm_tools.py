from datetime import datetime, timedelta

from muse.models.events import EventType, GigEvent


def add_studio(crm, **kw):
    fields = {"organization_name": "Patchwerk Recording", "contact_person": "Jen", "role": "studio"}
    fields.update(kw)
    return crm.add_contact(**fields)["contact_id"]


def test_seed_contacts(crm):
    names = {c["organization_name"] for c in crm.search_contacts()}
    assert {"The Earl", "West End Sound", "Dave Promotions"} <= names


def test_add_and_get_contact(crm):
    contact_id = add_studio(crm, email="jen@patchwerk.com", tags=["mixing", "tracking"])
    contact = crm.get_contact(contact_id)
    assert contact["organization_name"] == "Patchwerk Recording"
    assert contact["email"] == "jen@patchwerk.com"
    assert set(contact["tags"]) == {"mixing", "tracking"}


def test_search_by_name_person_role_and_tag(crm):
    contact_id = add_studio(crm, tags=["mixing"])
    assert contact_id in [c["id"] for c in crm.search_contacts(query="patchwerk")]
    assert contact_id in [c["id"] for c in crm.search_contacts(query="Jen")]
    assert contact_id in [c["id"] for c in crm.search_contacts(role="studio")]
    assert contact_id not in [c["id"] for c in crm.search_contacts(role="venue")]
    assert [c["id"] for c in crm.search_contacts(tag="mixing")] == [contact_id]


def test_update_contact(crm):
    contact_id = add_studio(crm)
    result = crm.update_contact(contact_id, {"typical_rate": "$80/hr", "id": "hijack"})
    assert result["updates"] == {"typical_rate": "$80/hr"}
    assert crm.get_contact(contact_id)["typical_rate"] == "$80/hr"


def test_missing_contact_is_an_error(crm):
    assert "error" in crm.get_contact("contact_nope")
    assert "error" in crm.update_contact("contact_nope", {"notes": "x"})
    assert "error" in crm.get_contact_summary("contact_nope")


def test_interactions_and_follow_ups(crm):
    contact_id = add_studio(crm)
    upcoming = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    crm.add_interaction(contact_id, interaction_type="meeting", content="EP planning",
                        interaction_date="2026-11-20", follow_up_date=upcoming)
    crm.add_interaction(contact_id, interaction_type="call", content="Rates", interaction_date="2026-11-21")

    assert len(crm.list_interactions(contact_id)) == 2

    summary = crm.get_contact_summary(contact_id)
    assert summary["interaction_count"] == 2
    assert [f["follow_up_date"] for f in summary["pending_follow_ups"]] == [upcoming]


def test_summary_works_before_invoicing_or_calendar_used(crm):
    contact_id = add_studio(crm)
    summary = crm.get_contact_summary(contact_id)
    assert summary["invoice_count"] == 0 and summary["event_count"] == 0


def test_summary_cross_references_only_this_contact(crm, invoices, calendar):
    contact_id = add_studio(crm)  # no email
    invoices.create_invoice("Patchwerk Recording", [{"description": "Session", "amount": 300}])
    invoices.create_invoice("Some Other Venue", [{"description": "Gig", "amount": 900}])
    for venue, pay in [("Patchwerk Recording", 300), ("Some Other Venue", 900)]:
        calendar.create_event(GigEvent(
            title=f"At {venue}", event_type=EventType.SESSION, venue=venue, pay=pay,
            start_time=datetime(2026, 12, 1, 12), end_time=datetime(2026, 12, 1, 16),
        ))

    summary = crm.get_contact_summary(contact_id)
    assert (summary["invoice_count"], summary["total_invoiced"]) == (1, 300)
    assert (summary["event_count"], summary["total_event_pay"]) == (1, 300)
