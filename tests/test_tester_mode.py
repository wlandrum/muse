"""A tester round: several invited people on one deployment."""

import os

import pytest

from muse.agents.base import EMPTY_REPLY, MAX_ROUNDS_REPLY
from muse.config import config
from muse.eval.scripted_client import ScriptedClient
from muse.orchestrator import Orchestrator

from tests.test_agent_loop import EchoAgent, tool_turn

GIG = {
    "title": "Gig at The Earl", "event_type": "gig", "venue": "The Earl",
    "start_time": "2026-12-05T21:00:00", "end_time": "2026-12-06T00:00:00",
}


def _gig_titles(orchestrator):
    events = orchestrator.calendar_agent.calendar.list_events("2026-12-01", "2026-12-31")
    return [e["title"] for e in events]


def test_each_session_gets_its_own_data(workdir):
    first = Orchestrator(client=ScriptedClient(route="CALENDAR", trajectory=[
        {"tools": [{"name": "create_event", "input": GIG}]}, {"text": "Added."},
    ]), db_path=os.path.join(workdir, "s1.db"))
    first.route("add my gig at The Earl")
    second = Orchestrator(client=ScriptedClient(route="", trajectory=[]),
                          db_path=os.path.join(workdir, "s2.db"))

    assert "Gig at The Earl" in _gig_titles(first)
    assert "Gig at The Earl" not in _gig_titles(second)
    assert not os.path.exists(config.DB_PATH)  # shared database untouched
    # Both still start from the same sample data.
    assert second.invoice_agent.invoices.list_invoices()


def test_each_session_gets_its_own_voice_samples(workdir):
    first = Orchestrator(client=object(), db_path=os.path.join(workdir, "s1.db"))
    second = Orchestrator(client=object(), db_path=os.path.join(workdir, "s2.db"))
    before = second.social_agent.social.list_voice_samples()["total_samples"]
    first.social_agent.social.add_voice_sample("Sold out night at The Earl.", "fan_engagement")
    assert second.social_agent.social.list_voice_samples()["total_samples"] == before


def test_tester_mode_never_uses_google(workdir, monkeypatch):
    from muse.tools import calendar_tools, email_tools
    monkeypatch.setattr(config, "TESTER_MODE", True)
    monkeypatch.setattr(calendar_tools, "GOOGLE_AVAILABLE", True)
    monkeypatch.setattr(email_tools, "GOOGLE_AVAILABLE", True)

    def no_google(*args, **kwargs):
        raise AssertionError("tester mode must not load Google credentials")

    monkeypatch.setattr("muse.utils.google_oauth.load_credentials", no_google)
    assert calendar_tools.CalendarTools().use_local
    assert email_tools.EmailTools().use_local


@pytest.mark.parametrize("cloud", [True, False])
def test_invoice_pdf_is_offered_for_download(workdir, monkeypatch, cloud):
    if cloud:
        monkeypatch.setenv("STREAMLIT_URL", "https://muse.example.com")
    client = ScriptedClient(route="INVOICE", trajectory=[
        {"tools": [{"name": "generate_pdf", "input": {"invoice_id": "inv_sample_001"}}]},
        {"text": "Your PDF is ready."},
    ])
    orchestrator = Orchestrator(client=client)
    orchestrator.route("make the PDF for my first invoice")

    filename, data = orchestrator.take_pending_pdf()
    assert filename.endswith(".pdf") and data.startswith(b"%PDF")
    assert orchestrator.take_pending_pdf() is None  # handed over once
    tool_result = client.requests[-1]["messages"][-1]["content"][0]["content"]
    assert "pdf_bytes" not in tool_result and "%PDF" not in tool_result
    assert "download button" in tool_result


class FailingOn(ScriptedClient):
    """Raises, as the SDK does when the API is down, on the given request numbers."""

    def __init__(self, fail_on, **kwargs):
        super().__init__(**kwargs)
        self.fail_on = set(fail_on)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.calls in self.fail_on:
            raise ConnectionError("API unreachable")
        return super().create(**kwargs)


def test_api_error_leaves_history_as_it_was():
    agent = EchoAgent(FailingOn([2], route="", trajectory=[{"text": "first"}, {"text": "second"}]))
    assert agent.run("hello") == "first"
    before = list(agent.conversation_history)
    with pytest.raises(ConnectionError):
        agent.run("are you there?")
    assert agent.conversation_history == before
    assert agent.run("are you there?") == "second"


def test_error_mid_tool_loop_is_rolled_back():
    agent = EchoAgent(FailingOn([2], route="", trajectory=[tool_turn("a"), tool_turn("a"), {"text": "done"}]))
    with pytest.raises(ConnectionError):
        agent.run("echo a")
    assert agent.conversation_history == []
    assert agent.run("try again") == "done"


def test_empty_final_reply_gets_a_message():
    agent = EchoAgent(ScriptedClient(route="", trajectory=[{"text": ""}]))
    assert agent.run("hello") == EMPTY_REPLY


def test_max_rounds_closes_the_turn():
    agent = EchoAgent(ScriptedClient(route="", trajectory=[tool_turn("again")] * 5))
    agent.max_tool_rounds = 2
    assert agent.run("loop") == MAX_ROUNDS_REPLY
    assert agent.conversation_history[-1] == {"role": "assistant", "content": MAX_ROUNDS_REPLY}
