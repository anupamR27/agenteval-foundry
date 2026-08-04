# The contract every AI must follow, defines the language that your evaluation framework and every future AI agent will use to communicate
from typing import Any, Protocol

from pydantic import BaseModel, Field


class AgentMetadata(BaseModel):
    """Describes an agent implementation under evaluation."""

    name: str
    version: str
    description: str | None = None


class AgentRequest(BaseModel):
    """Input passed to an agent for one scenario execution."""

    query: str
    scenario_id: str


class ExecutionContext(BaseModel):
    """Run-scoped execution data supplied by the evaluator."""
    # Information ABOUT the execution

    run_id: str
    scenario_version: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCallRecord(BaseModel):
    """Observed tool call emitted during agent execution."""
    
    tool_name: str
    arguments: dict[str, Any]
    result: Any
    success: bool
    error: str | None = None


class AgentResult(BaseModel):
    """Structured result returned by an agent execution."""

    answer: str
    agent_metadata: AgentMetadata
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentUnderTest(Protocol):
    """Framework-neutral async contract for agents under evaluation."""

    async def execute(self, request: AgentRequest, context: ExecutionContext) -> AgentResult:
        ... 
        # Ellipsis -> Nothing is implemented here yet
        # I'm only defining that this method must exist, I'm not implementing it
