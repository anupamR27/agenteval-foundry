import pytest

from faults.injector import FaultInjectingToolExecutor
from faults.models import FaultSpec, FaultTrigger, FaultType
from tools.base import ToolDefinition, ToolResult
from tools.registry import ToolRegistry


async def search_policy(query: str) -> ToolResult:
    return ToolResult(success=True, data={"policy": f"normal policy for {query}"})


async def other_tool(query: str) -> ToolResult:
    return ToolResult(success=True, data={"other": query})


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(name="search_policy", description="Policy lookup.", handler=search_policy)
    )
    registry.register(ToolDefinition(name="other_tool", description="Other tool.", handler=other_tool))
    return registry


@pytest.mark.asyncio
async def test_no_configured_faults_delegates_unchanged() -> None:
    executor = FaultInjectingToolExecutor(build_registry())

    result = await executor.execute("search_policy", query="hello")

    assert result.success is True
    assert result.data == {"policy": "normal policy for hello"}
    assert executor.activation_records == ()


@pytest.mark.asyncio
async def test_always_activates_on_every_matching_call() -> None:
    executor = FaultInjectingToolExecutor(
        build_registry(),
        [FaultSpec(fault_type=FaultType.TOOL_TIMEOUT, target_tool="search_policy", trigger=FaultTrigger.ALWAYS)],
    )

    first = await executor.execute("search_policy", query="one")
    second = await executor.execute("search_policy", query="two")

    assert first.success is False
    assert second.success is False
    assert len(executor.activation_records) == 2
    assert [record.call_number for record in executor.activation_records] == [1, 2]


@pytest.mark.asyncio
async def test_first_call_activates_only_once() -> None:
    executor = FaultInjectingToolExecutor(
        build_registry(),
        [
            FaultSpec(
                fault_type=FaultType.TOOL_ERROR,
                target_tool="search_policy",
                trigger=FaultTrigger.FIRST_CALL,
            )
        ],
    )

    first = await executor.execute("search_policy", query="one")
    second = await executor.execute("search_policy", query="two")

    assert first.success is False
    assert second.success is True
    assert len(executor.activation_records) == 1
    assert executor.activation_records[0].call_number == 1


@pytest.mark.asyncio
async def test_call_number_activates_only_on_configured_call() -> None:
    executor = FaultInjectingToolExecutor(
        build_registry(),
        [
            FaultSpec(
                fault_type=FaultType.TOOL_ERROR,
                target_tool="search_policy",
                trigger=FaultTrigger.CALL_NUMBER,
                call_number=2,
            )
        ],
    )

    first = await executor.execute("search_policy", query="one")
    second = await executor.execute("search_policy", query="two")
    third = await executor.execute("search_policy", query="three")

    assert first.success is True
    assert second.success is False
    assert third.success is True
    assert len(executor.activation_records) == 1
    assert executor.activation_records[0].call_number == 2


@pytest.mark.asyncio
async def test_non_targeted_and_disabled_faults_do_not_activate() -> None:
    executor = FaultInjectingToolExecutor(
        build_registry(),
        [
            FaultSpec(fault_type=FaultType.TOOL_TIMEOUT, target_tool="search_policy"),
            FaultSpec(fault_type=FaultType.TOOL_ERROR, target_tool="other_tool", enabled=False),
        ],
    )

    other_result = await executor.execute("other_tool", query="hello")

    assert other_result.success is True
    assert other_result.data == {"other": "hello"}
    assert executor.activation_records == ()


@pytest.mark.asyncio
async def test_fault_semantics_are_deterministic() -> None:
    fault_types = [
        FaultType.TOOL_TIMEOUT,
        FaultType.TOOL_ERROR,
        FaultType.MALFORMED_OUTPUT,
        FaultType.BAD_RETRIEVAL,
        FaultType.CONTEXT_TRUNCATION,
    ]

    results = []
    for fault_type in fault_types:
        executor = FaultInjectingToolExecutor(
            build_registry(),
            [FaultSpec(fault_type=fault_type, target_tool="search_policy")],
        )
        results.append(await executor.execute("search_policy", query="hello"))
        assert executor.activation_records[0].target_tool == "search_policy"
        assert executor.activation_records[0].call_number == 1

    timeout, tool_error, malformed, bad_retrieval, truncation = results
    assert timeout.success is False
    assert timeout.error == "Injected timeout for tool: search_policy"
    assert tool_error.success is False
    assert tool_error.error == "Injected error for tool: search_policy"
    assert malformed.success is True
    assert malformed.data == {"unexpected_field": 123}
    assert bad_retrieval.success is True
    assert "30 days" in bad_retrieval.data["policy"]
    assert truncation.success is True
    assert truncation.data == {"policy": "Annual subscriptions may be refunded within..."}
