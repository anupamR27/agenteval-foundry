from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

ToolHandler = Callable[..., Awaitable["ToolResult"]]


class ToolResult(BaseModel):
    """Result returned by an async tool handler."""

    success: bool
    data: Any = None
    error: str | None = None


class ToolDefinition(BaseModel):
    """Registry definition for one async tool."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str
    description: str
    handler: ToolHandler
