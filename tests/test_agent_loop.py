"""BaseAgent tool loop and Orchestrator routing, driven by a scripted client."""

import pytest
from anthropic.types import TextBlock, ThinkingBlock

from muse.agents.base import MAX_ROUNDS_REPLY, REFUSAL_REPLY, TRUNCATED_REPLY, BaseAgent
from muse.config import config
from muse.eval.scripted_client import ScriptedClient
from muse.orchestrator import ROUTER_PROMPT, Orchestrator


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


def tool_turn(*texts, **extra):
    return {"tools": [{"name": "echo", "input": {"text": t}} for t in texts], **extra}


def tool_results(request):
    return request["messages"][-1]["content"]


def user_texts(request):
    """The artist's own words from each user turn (skipping tool-result turns)."""
    return [m["content"][0]["text"] for m in request["messages"]
            if m["role"] == "user" and m["content"][0].get("type") == "text"]


def block_types(message):
    content = message["content"]
    if isinstance(content, str):
        return content
    return [b["type"] if isinstance(b, dict) else b.type for b in content]


# ── BaseAgent ────────────────────────────────────────────────────────

def test_plain_text_reply():
    client = ScriptedClient(route="", trajectory=[{"text": "hi"}])
    agent = EchoAgent(client)
    assert agent.run("hello") == "hi"
    assert agent.executed == []
    user, assistant = agent.conversation_history
    assert user["content"][0] == {"type": "text", "text": "hello"}
    assert block_types(assistant) == ["text"]


def test_user_turn_carries_current_date():
    client = ScriptedClient(route="", trajectory=[{"text": "hi"}])
    EchoAgent(client).run("hello")
    context = client.requests[0]["messages"][0]["content"][1]["text"]
    assert context.startswith("(Current date and time:")
    assert config.DEFAULT_TIMEZONE in context


def test_request_settings(monkeypatch):
    monkeypatch.setattr(config, "AGENT_EFFORT", "medium")
    client = ScriptedClient(route="", trajectory=[{"text": "hi"}])
    EchoAgent(client).run("hello")
    request = client.requests[0]
    assert request["max_tokens"] == config.AGENT_MAX_TOKENS >= 8000  # room for thinking
    assert request["output_config"] == {"effort": "medium"}
    assert request["cache_control"] == {"type": "ephemeral"}
    assert "tool_choice" not in request  # forced tool use is rejected by current models


@pytest.mark.parametrize("model,uses_fallback", [
    ("claude-sonnet-5-5", True),
    ("claude-haiku-5-5", False),
])
def test_refusal_fallback_only_on_supported_models(model, uses_fallback, monkeypatch):
    monkeypatch.setattr(config, "REFUSAL_FALLBACK", True)
    client = ScriptedClient(route="", trajectory=[{"text": "hi"}])
    agent = EchoAgent(client)
    agent.model = model
    agent.run("hello")
    request = client.requests[0]
    assert (request.get("fallbacks") == "default") is uses_fallback
    assert ("betas" in request) is uses_fallback


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
    tool_use_ids = [b.id for b in second_request["messages"][-2]["content"] if b.type == "tool_use"]
    assert [r["tool_use_id"] for r in results] == tool_use_ids


def test_thinking_blocks_kept_verbatim_in_history():
    client = ScriptedClient(route="", trajectory=[
        tool_turn("a", thinking=True),
        {"text": "done", "thinking": True},
    ])
    agent = EchoAgent(client)
    assert agent.run("go") == "done"  # text read by type, not position
    assert [block_types(m) for m in agent.conversation_history[1:]] == [
        ["thinking", "tool_use"],
        ["tool_result"],
        ["thinking", "text"],
    ]
    # The second request replays the first turn's thinking block unchanged.
    assert client.requests[1]["messages"][1]["content"][0].type == "thinking"


def test_tool_exception_reported_as_error_and_loop_continues():
    client = ScriptedClient(route="", trajectory=[tool_turn("ok", "bad"), {"text": "recovered"}])
    agent = EchoAgent(client, fail_on="bad")
    assert agent.run("go") == "recovered"
    ok, bad = tool_results(client.requests[1])
    assert "is_error" not in ok
    assert bad["is_error"] is True and "boom" in bad["content"]


def test_refusal_returns_friendly_reply_and_keeps_history_valid():
    client = ScriptedClient(route="", trajectory=[{"refusal": True}, {"text": "ok"}])
    agent = EchoAgent(client)
    assert agent.run("something") == REFUSAL_REPLY
    assert agent.conversation_history[-1] == {"role": "assistant", "content": REFUSAL_REPLY}
    assert agent.run("something else") == "ok"


def test_max_tokens_mid_tool_loop_drops_partial_turn():
    client = ScriptedClient(route="", trajectory=[tool_turn("a"), {"max_tokens": True}])
    agent = EchoAgent(client)
    assert agent.run("go") == TRUNCATED_REPLY
    assert agent.conversation_history[-1] == {"role": "assistant", "content": TRUNCATED_REPLY}
    assert block_types(agent.conversation_history[-2]) == ["tool_result"]


def test_max_tool_rounds_stops_runaway_loop():
    client = ScriptedClient(route="", trajectory=[tool_turn("again")] * 20)
    agent = EchoAgent(client)
    agent.max_tool_rounds = 3
    assert agent.run("loop forever") == MAX_ROUNDS_REPLY
    assert len(client.requests) == 3


def test_history_persists_across_turns_until_reset():
    client = ScriptedClient(route="", trajectory=[{"text": "one"}, {"text": "two"}])
    agent = EchoAgent(client)
    agent.run("first")
    agent.run("second")
    assert user_texts(client.requests[1]) == ["first", "second"]
    assert len(client.requests[1]["messages"]) == 3
    agent.reset()
    assert agent.conversation_history == []


# ── Orchestrator ─────────────────────────────────────────────────────

class RawRouter(ScriptedClient):
    """Router stand-in that returns the given content and stop reason verbatim."""

    def __init__(self, content, stop_reason="end_turn"):
        super().__init__(route="", trajectory=[])
        self._content, self._stop = content, stop_reason

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self._message(self._content, self._stop)


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


def test_router_request(workdir):
    client = ScriptedClient(route="GENERAL", trajectory=[])
    Orchestrator(client=client).route("hi")
    (request,) = client.requests
    assert request["system"] == ROUTER_PROMPT
    assert request["model"] == config.ROUTER_MODEL
    assert request["max_tokens"] >= 512  # thinking counts toward the limit
    assert request["output_config"]["effort"] == config.ROUTER_EFFORT
    assert request["output_config"]["format"]["schema"]["properties"]["category"]["enum"]
    assert "tools" not in request


def test_router_reads_text_after_thinking(workdir):
    client = RawRouter([ThinkingBlock(type="thinking", thinking="", signature="s"),
                        TextBlock(type="text", text='{"category": "EMAIL"}')])
    assert Orchestrator(client=client)._classify("check my inbox") == "EMAIL"


@pytest.mark.parametrize("text,stop", [
    ("not json", "end_turn"),
    ('{"category": "EMAIL"}', "max_tokens"),
    ('{"wrong": 1}', "end_turn"),
])
def test_router_falls_back_to_general(text, stop, workdir):
    client = RawRouter([TextBlock(type="text", text=text)], stop)
    assert Orchestrator(client=client)._classify("x") == "GENERAL"


def test_router_sees_previous_category_for_follow_ups(workdir):
    client = ScriptedClient(route="INVOICE", trajectory=[{"text": "Want the PDF?"}, {"text": "Done"}])
    orch = Orchestrator(client=client)
    orch.route("invoice the earl $400")
    orch.route("yes")
    router_calls = [r for r in client.requests if r["system"] == ROUTER_PROMPT]
    assert router_calls[0]["messages"][0]["content"] == "invoice the earl $400"
    assert "Previous message was handled by: INVOICE" in router_calls[1]["messages"][0]["content"]
    orch.reset()
    assert orch.last_category is None


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
