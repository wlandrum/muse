BOOKING = "local_sample_001"
FESTIVAL = "local_sample_003"


def test_list_inbox(email):
    ids = [m["id"] for m in email.list_emails()]
    assert set(ids) == {"local_sample_001", "local_sample_002", "local_sample_003"}


def test_list_unread_only(email):
    assert {m["id"] for m in email.list_emails(unread_only=True)} == {"local_sample_001", "local_sample_002"}


def test_list_respects_max_results(email):
    assert len(email.list_emails(max_results=1)) == 1


def test_read_email(email):
    message = email.read_email(BOOKING)
    assert "The Earl" in message["subject"]
    assert message["body_text"]


def test_read_missing_email(email):
    assert "error" in email.read_email("nope")


def test_search_matches_subject_sender_and_body(email):
    assert [m["id"] for m in email.search_emails("Festival")] == [FESTIVAL]
    assert BOOKING in [m["id"] for m in email.search_emails("sarah")]
    assert BOOKING in [m["id"] for m in email.search_emails("backline")]
    assert email.search_emails("zzz-no-match") == []


def test_draft_reply_threads_to_sender(email):
    draft = email.draft_reply(BOOKING, body="I'm in!")
    assert draft["status"] == "draft_created"
    assert "sarah@theearlatlanta.com" in draft["to"]
    assert draft["subject"].startswith("Re: ")


def test_draft_reply_to_missing_email(email):
    assert "error" in email.draft_reply("nope", body="x")


def test_create_and_send_draft(email):
    draft = email.create_draft(to=["miles@westendsound.com"], subject="Rates", body="Sounds good")
    assert email.send_draft(draft["draft_id"])["status"] == "sent"
    assert "error" in email.send_draft("draft_nope")


def test_archive_and_star(email):
    email.modify_labels(FESTIVAL, remove_labels=["INBOX"])
    email.modify_labels(BOOKING, add_labels=["STARRED"])
    assert FESTIVAL not in [m["id"] for m in email.list_emails()]
    assert [m["id"] for m in email.list_emails(label="STARRED")] == [BOOKING]


def test_modify_missing_email(email):
    assert "error" in email.modify_labels("nope", add_labels=["STARRED"])


def test_extract_gig_details_returns_email_content(email):
    details = email.extract_gig_details(BOOKING)
    assert "March 22" in details["subject"]
    assert details["body_text"]
