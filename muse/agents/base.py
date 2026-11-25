"""Base agent class with Anthropic native tool calling loop."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from anthropic import Anthropic

from muse.config import config

logger = logging.getLogger(__name__)

# Models that accept server-side refusal fallback (`fallbacks: "default"`).
SERVER_FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}
SERVER_FALLBACK_BETA = "server-side-fallback-2026-07-01"

REFUSAL_REPLY = (
    "Sorry, I can't help with that request. "
    "If that seems wrong, try rephrasing it."
)
TRUNCATED_REPLY = (
    "I ran out of room before finishing that. "
    "Could you break the request into smaller pieces?"
)
MAX_ROUNDS_REPLY = "I'm having trouble completing this request. Could you try rephrasing?"
EMPTY_REPLY = "Sorry, I couldn't put a reply together for that. Could you try asking another way?"


class BaseAgent(ABC):
    """Base class for all Muse agents.

    Implements the core agent loop:
    1. Send user message + tools to Claude
    2. If Claude wants to call a tool → execute it → feed result back → repeat
    3. If Claude returns a text response → return it to the user

    The conversation history is append-only: assistant turns are stored
    exactly as returned (thinking blocks included) so the prompt cache and
    the model's earlier reasoning stay valid across turns.
    """

    def __init__(
        self,
        client: Anthropic | None = None,
        model: str | None = None,
        db_path: str | None = None,
    ):
        self.client = client or Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.model = model or config.MODEL
        # Where this agent's tools keep their data. None means config.DB_PATH.
        self.db_path = db_path
        self.conversation_history: list[dict] = []
        self.max_tool_rounds = 10  # safety limit to prevent infinite loops

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent name for logging and routing."""
        ...

    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt that defines the agent's personality and capabilities."""
        ...

    @abstractmethod
    def tool_definitions(self) -> list[dict]:
        """Anthropic-formatted tool definitions this agent can use."""
        ...

    @abstractmethod
    def execute_tool(self, tool_name: str, tool_input: dict) -> Any:
        """Execute a tool call and return the result.

        Should return a string or dict that will be sent back to Claude
        as the tool result.
        """
        ...

    def turn_context(self) -> str:
        """Per-turn context appended to each user message.

        Kept out of the system prompt so the prompt stays byte-identical
        (cacheable) and the date is never stale on a long-running server.
        """
        now = datetime.now(ZoneInfo(config.DEFAULT_TIMEZONE))
        return f"(Current date and time: {now:%A, %B %d, %Y, %I:%M %p} {config.DEFAULT_TIMEZONE})"

    def _create(self):
        kwargs = dict(
            model=self.model,
            max_tokens=config.AGENT_MAX_TOKENS,
            system=self.system_prompt(),
            tools=self.tool_definitions(),
            messages=self.conversation_history,
            output_config={"effort": config.AGENT_EFFORT},
            # Auto-caches the prefix up to the last block, so each tool round
            # re-reads tools + system + history from cache.
            cache_control={"type": "ephemeral"},
        )
        if config.REFUSAL_FALLBACK and self.model in SERVER_FALLBACK_MODELS:
            return self.client.beta.messages.create(
                betas=[SERVER_FALLBACK_BETA], fallbacks="default", **kwargs
            )
        return self.client.messages.create(**kwargs)

    def run(self, user_message: str) -> str:
        """Execute the full agent loop for a user message.

        Returns the agent's final text response. If a request to the API
        fails, the unfinished turn is taken back out of the history and the
        error is raised, so the next message starts from the last complete
        turn instead of a dangling question or tool exchange.
        """
        start = len(self.conversation_history)
        self.conversation_history.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_message},
                {"type": "text", "text": self.turn_context()},
            ],
        })
        try:
            return self._loop()
        except Exception:
            del self.conversation_history[start:]
            raise

    def _loop(self) -> str:
        for round_num in range(self.max_tool_rounds):
            logger.info(f"[{self.name}] Round {round_num + 1}")
            response = self._create()

            if response.stop_reason in ("refusal", "max_tokens"):
                # Don't keep a turn that may end in a half-written tool call;
                # record a plain reply instead so the history stays valid.
                if response.stop_reason == "refusal":
                    logger.warning(f"[{self.name}] Refused: {response.stop_details}")
                    reply = REFUSAL_REPLY
                else:
                    logger.warning(f"[{self.name}] Hit max_tokens ({config.AGENT_MAX_TOKENS})")
                    reply = TRUNCATED_REPLY
                self.conversation_history.append({"role": "assistant", "content": reply})
                return reply

            self.conversation_history.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    logger.info(
                        f"[{self.name}] Calling tool: {block.name} "
                        f"with input: {json.dumps(block.input, default=str)[:200]}"
                    )
                    try:
                        result = self.execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str)
                            if not isinstance(result, str)
                            else result,
                        })
                    except Exception as e:
                        logger.error(f"[{self.name}] Tool error: {e}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Error executing tool: {str(e)}",
                            "is_error": True,
                        })

                # All results go back in a single user message.
                self.conversation_history.append({
                    "role": "user",
                    "content": tool_results,
                })
                continue  # next round

            logger.info(f"[{self.name}] Completed in {round_num + 1} round(s)")
            reply = "\n".join(b.text for b in response.content if b.type == "text").strip()
            if not reply:
                logger.warning(f"[{self.name}] Final turn had no text")
                if not response.content:
                    # An empty assistant turn would be rejected next time.
                    self.conversation_history[-1] = {"role": "assistant", "content": EMPTY_REPLY}
                return EMPTY_REPLY
            return reply

        # If we hit the safety limit, close the turn so the history ends on
        # an assistant reply like every other turn.
        logger.warning(f"[{self.name}] Hit max tool rounds ({self.max_tool_rounds})")
        self.conversation_history.append({"role": "assistant", "content": MAX_ROUNDS_REPLY})
        return MAX_ROUNDS_REPLY

    def reset(self) -> None:
        """Clear conversation history for a fresh start."""
        self.conversation_history = []
