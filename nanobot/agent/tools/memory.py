"""Memory tools for the agent."""

import logging
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.agent.memory import MemoryStore

logger = logging.getLogger(__name__)


class AppendTodayTool(Tool):
    """Tool to append content to today's memory notes."""

    def __init__(self, memory_store: MemoryStore):
        self.memory_store = memory_store

    @property
    def name(self) -> str:
        return "append_today"

    @property
    def description(self) -> str:
        return "Append content to today's memory notes. Use this for things you want to remember today."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The content to append to today's notes",
                }
            },
            "required": ["content"],
        }

    async def execute(self, content: str) -> str:
        """Append content to today's memory notes."""
        self.memory_store.append_today(content)
        logger.info("[memory] append_today called")
        return "Appended to today's notes"


class WriteLongTermTool(Tool):
    """Tool to write to long-term memory."""

    def __init__(self, memory_store: MemoryStore):
        self.memory_store = memory_store

    @property
    def name(self) -> str:
        return "write_long_term"

    @property
    def description(self) -> str:
        return "Write or update long-term memory. Use this for important user information, preferences, and facts that should persist across sessions."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The long-term memory content to store",
                }
            },
            "required": ["content"],
        }

    async def execute(self, content: str) -> str:
        """Write to long-term memory."""
        self.memory_store.write_long_term(content)
        logger.info("[memory] write_long_term called")
        return "Wrote to long-term memory"
