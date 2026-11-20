"""BaseAgent tool loop and Orchestrator routing, driven by a scripted client."""

import pytest

from muse.agents.base import BaseAgent
from muse.eval.scripted_client import ScriptedClient
from muse.orchestrator import Orchestrator


class EchoAgent(BaseAgent):
    name = "EchoAgent"

    def __init__(self, client, fail_on=None):
        super().__init__(client=client, model="test-model")
        self.fail_on = fail_on
        self.executed = []

    def system_prompt(self):
        return "You echo."

    def tool_definitions(self):
        return [{"name": "echo", "description": "Echo", "input_schema": {"type": "object"}}]

    def execute_tool(self, tool_name, tool_input):
        self.executed.append((tool_name, tool_input))
        if tool_input.get("text") == self.fail_on:
            raise ValueError("boom")
        return {"echoed": tool_input.get("text")}


def tool_turn(*texts):
    return {"tools": [{"name": "echo", "input": {"text": t}} for t in texts]}


def tool_results(request):
    return request["messages"][-1]["content"]


# ── BaseAgent ────────────────────────────────────────────────────────

def test_plain_text_reply():
    client = ScriptedClient(route="", trajectory=[{"text": "hi"}])
    agent = EchoAgent(client)
    assert agent.run("hello") == "hi"
    assert agent.executed == []
    assert agent.conversation_history == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_tool_results_fed_back_in_order():
    client = ScriptedClient(route="", trajectory=[tool_turn("a", "b"), {"text": "done"}])
    agent = EchoAgent(client)
    assert agent.run("go") == "done"
    assert agent.executed == [("echo", {"text": "a"}), ("echo", {"text": "b"})]

    second_request = client.requests[1]
    assert second_request["model"] == "test-model"
    assert second_request["system"] == "You echo."
    results = tool_results(second_request)
    assert [r["content"] for r in results] == ['{"echoed": "a"}', '{"echoed": "b"}']
    tool_use_ids = [b["id"] for b in second_request["messages"][-2]["content"] if b["type"] == "tool_use"]
    assert [r["tool_use_id"] for r in results] == tool_use_ids


def test_tool_exception_reported_as_error_and_loop_continues():
    client = ScriptedClient(route="", trajectory=[tool_turn("ok", "bad"), {"text": "recovered"}])
    agent = EchoAgent(client, fail_on="bad")
    assert agent.run("go") == "recovered"
    ok, bad = tool_results(client.requests[1])
    assert "is_error" not in ok
    assert bad["is_error"] is True and "boom" in bad["content"]


def test_max_tool_rounds_stops_runaway_loop():
    client = ScriptedClient(route="", trajectory=[tool_turn("again")] * 20)
    agent = EchoAgent(client)
    agent.max_tool_rounds = 3
    reply = agent.run("loop forever")
    assert "trouble" in reply
    assert len(client.requests) == 3


def test_history_persists_across_turns_until_reset():
    client = ScriptedClient(route="", trajectory=[{"text": "one"}, {"text": "two"}])
    agent = EchoAgent(client)
    agent.run("first")
    agent.run("second")
    assert [m["content"] for m in client.requests[1]["messages"]] == ["first", "one", "second"]
    agent.reset()
    assert agent.conversation_history == []


# ── Orchestrator ─────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("CALENDAR", "CALENDAR"),
    ("  invoice\n", "INVOICE"),
    ("Crm", "CRM"),
    ("CALENDAR.", "GENERAL"),
    ("I think this is EMAIL", "GENERAL"),
    ("", "GENERAL"),
])
def test_classify_normalizes_and_validates(raw, expected, workdir):
    orch = Orchestrator(client=ScriptedClient(route=raw, trajectory=[]))
    assert orch._classify("anything") == expected


def test_router_uses_short_classification_call(workdir):
    client = ScriptedClient(route="GENERAL", trajectory=[])
    Orchestrator(client=client).route("hi")
    (request,) = client.requests
    assert request["max_tokens"] <= 20
    assert "tools" not in request


def test_general_route_does_not_load_agents(workdir):
    orch = Orchestrator(client=ScriptedClient(route="GENERAL", trajectory=[]))
    category, reply = orch.route("hey")
    assert category == "GENERAL" and "Muse" in reply
    assert all(getattr(orch, f"_{n}_agent") is None for n in ("calendar", "email", "invoice", "social", "crm"))


def test_routes_to_agent_and_shares_client(workdir):
    client = ScriptedClient(route="INVOICE", trajectory=[{"text": "invoice reply"}])
    orch = Orchestrator(client=client)
    assert orch.route("bill the earl") == ("INVOICE", "invoice reply")
    assert orch._invoice_agent is not None and orch._invoice_agent.client is client
    assert orch._calendar_agent is None


def test_reset_clears_loaded_agents(workdir):
    orch = Orchestrator(client=ScriptedClient(route="CRM", trajectory=[{"text": "ok"}]))
    orch.route("who is jen")
    assert orch._crm_agent.conversation_history
    orch.reset()
    assert orch._crm_agent.conversation_history == []
