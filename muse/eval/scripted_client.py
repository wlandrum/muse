"""A fake Anthropic client that replays a case's gold trajectory.

Stands in for `anthropic.Anthropic` so the orchestrator and agents run their
real code paths (routing, tool loop, tool execution) without any API calls.
"""

from __future__ import annotations

import copy
import itertools
import json
from types import SimpleNamespace
from typing import Any, Callable

from anthropic.types import (
    Message, RefusalStopDetails, TextBlock, ThinkingBlock, ToolUseBlock, Usage,
)

from muse.orchestrator import ROUTER_PROMPT


class ScriptExhausted(AssertionError):
    """The agent asked the model for more turns than the case scripted."""


class ScriptedClient:
    """Replays scripted model turns.

    - Router calls (system == ROUTER_PROMPT) get `route` back as text.
      (as JSON when the request asks for structured output).
    - Agent calls get the next step of `trajectory`: either a list of tool
      calls (stop_reason="tool_use") or a final text reply (stop_reason="end_turn").
      A step may also be {"refusal": True} or {"max_tokens": True}, and
      {"thinking": True} prepends an (empty) thinking block, as real models do.

    `resolve` is called on each tool call's input just before it is emitted,
    so inputs can reference results of earlier tool calls (see runner).
    `on_emit` is told which `save_as` names the emitted tool calls carry.
    """

    def __init__(
        self,
        route: str,
        trajectory: list[dict],
        resolve: Callable[[Any], Any] = lambda x: x,
        on_emit: Callable[[list[str | None]], None] = lambda names: None,
        model: str = "scripted",
    ):
        self.route = route
        self.trajectory = list(trajectory)
        self.resolve = resolve
        self.on_emit = on_emit
        self.model = model
        self.requests: list[dict] = []
        self._ids = itertools.count(1)
        self.messages = self  # mimic client.messages.create(...)
        self.beta = SimpleNamespace(messages=self)  # and client.beta.messages.create(...)

    def create(self, **kwargs) -> Message:
        # Snapshot: agents pass their live history list, which keeps mutating.
        self.requests.append(copy.deepcopy(kwargs))

        if kwargs.get("system") == ROUTER_PROMPT:
            structured = "format" in (kwargs.get("output_config") or {})
            text = json.dumps({"category": self.route}) if structured else self.route
            return self._message([TextBlock(type="text", text=text)], "end_turn")

        if not self.trajectory:
            raise ScriptExhausted("Agent requested another model turn but the trajectory is finished")
        step = self.trajectory.pop(0)
        thinking = [ThinkingBlock(type="thinking", thinking="", signature="scripted")] if step.get("thinking") else []

        if step.get("refusal"):
            return self._message(thinking, "refusal",
                                 stop_details=RefusalStopDetails(type="refusal", category=None, explanation=None))
        if step.get("max_tokens"):
            return self._message(thinking + [TextBlock(type="text", text="Cut off mid-")], "max_tokens")

        if "tools" in step:
            blocks = []
            names = []
            for call in step["tools"]:
                blocks.append(ToolUseBlock(
                    type="tool_use",
                    id=f"toolu_scripted_{next(self._ids)}",
                    name=call["name"],
                    input=self.resolve(call.get("input", {})),
                ))
                names.append(call.get("save_as"))
            self.on_emit(names)
            if step.get("text"):
                blocks.insert(0, TextBlock(type="text", text=step["text"]))
            return self._message(thinking + blocks, "tool_use")

        return self._message(thinking + [TextBlock(type="text", text=step.get("text", ""))], "end_turn")

    @property
    def unused_steps(self) -> int:
        return len(self.trajectory)

    def _message(self, content: list, stop_reason: str, stop_details=None) -> Message:
        return Message(
            id=f"msg_scripted_{next(self._ids)}",
            type="message",
            role="assistant",
            model=self.model,
            content=content,
            stop_reason=stop_reason,
            stop_details=stop_details,
            stop_sequence=None,
            usage=Usage(input_tokens=0, output_tokens=0),
        )
