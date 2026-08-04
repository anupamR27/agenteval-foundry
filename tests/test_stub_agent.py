import pytest

from aut.base import AgentRequest, ExecutionContext
from aut.stub_agent import StubAgent
from tools.base import ToolDefinition, ToolResult
from tools.mock_tools import build_default_tool_registry
from tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_stub_agent_uses_search_policy_and_returns_refund_answer() -> None:
    agent = StubAgent(build_default_tool_registry())

    result = await agent.execute(
        AgentRequest(
            query="Find the refund period for an annual subscription.",
            scenario_id="demo-normal-001",
        ),
        ExecutionContext(run_id="test-run", scenario_version=1),
    )

    assert "14 days" in result.answer
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "search_policy"
    assert result.tool_calls[0].success is True


async def failing_search_policy(query: str) -> ToolResult:
    return ToolResult(success=False, data=None, error=f"policy unavailable for: {query}")


@pytest.mark.asyncio
async def test_stub_agent_records_failed_tool_call_and_safe_answer() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="search_policy",
            description="Failing policy lookup.",
            handler=failing_search_policy,
        )
    )
    agent = StubAgent(registry)

    result = await agent.execute(
        AgentRequest(query="Find the refund period.", scenario_id="demo-normal-001"),
        ExecutionContext(run_id="test-run", scenario_version=1),
    )

    assert result.answer == "The refund policy could not be retrieved."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "search_policy"
    assert result.tool_calls[0].success is False
    assert result.tool_calls[0].error == "policy unavailable for: Find the refund period."
