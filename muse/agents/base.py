"""Base agent class with Anthropic native tool calling loop."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from anthropic import Anthropic
from anthropic.types import Message, ToolUseBlock, TextBlock

from muse.config import config

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Base class for all Muse agents.

    Implements the core agent loop:
    1. Send user message + tools to Claude
    2. If Claude wants to call a tool → execute it → feed result back → repeat
    3. If Claude returns a text response → return it to the user
    """

    def __init__(
        self,
        client: Anthropic | None = None,
        model: str | None = None,
    ):
        self.client = client or Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.model = model or config.MODEL
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

    def run(self, user_message: str) -> str:
        """Execute the full agent loop for a user message.

        Returns the agent's final text response.
        """
        self.conversation_history.append({
            "role": "user",
            "content": user_message,
        })

        for round_num in range(self.max_tool_rounds):
            logger.info(f"[{self.name}] Round {round_num + 1}")

            response: Message = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt(),
                tools=self.tool_definitions(),
                messages=self.conversation_history,
            )

            # Check if Claude wants to use tools
            if response.stop_reason == "tool_use":
                # Add the assistant's response (which contains tool_use blocks)
                self.conversation_history.append({
                    "role": "assistant",
                    "content": [block.model_dump() for block in response.content],
                })

                # Execute each tool call and collect results
                tool_results = []
                for block in response.content:
                    if isinstance(block, ToolUseBlock):
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

                # Feed tool results back to Claude
                self.conversation_history.append({
                    "role": "user",
                    "content": tool_results,
                })
                continue  # next round

            # Claude returned a final text response — extract and return it
            text_parts = []
            for block in response.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)

            assistant_text = "\n".join(text_parts)
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_text,
            })

            logger.info(f"[{self.name}] Completed in {round_num + 1} round(s)")
            return assistant_text

        # If we hit the safety limit
        logger.warning(f"[{self.name}] Hit max tool rounds ({self.max_tool_rounds})")
        return "I'm having trouble completing this request. Could you try rephrasing?"

    def reset(self) -> None:
        """Clear conversation history for a fresh start."""
        self.conversation_history = []
