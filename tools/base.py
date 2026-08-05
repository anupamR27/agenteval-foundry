from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

ToolHandler = Callable[..., Awaitable["ToolResult"]]


class ToolResult(BaseModel):
    """Result returned by an async tool handler."""

    success: bool
    data: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolDefinition(BaseModel):
    """Registry definition for one async tool."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str
    description: str
    handler: ToolHandler


class ToolExecutor(Protocol):
    """Minimal async tool execution interface used by agents."""

    async def execute(self, name: str, **arguments: object) -> ToolResult:
        ...
