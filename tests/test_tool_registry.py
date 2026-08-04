import pytest

from tools.base import ToolDefinition, ToolResult
from tools.registry import ToolRegistry


async def sample_tool(query: str) -> ToolResult:
    return ToolResult(success=True, data={"echo": query})


@pytest.mark.asyncio
async def test_tool_registration_listing_and_execution() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="sample",
            description="Echo test tool.",
            handler=sample_tool,
        )
    )

    assert registry.list_names() == ["sample"]

    result = await registry.execute("sample", query="hello")

    assert result.success is True
    assert result.data == {"echo": "hello"}


def test_duplicate_registration_is_rejected() -> None:
    registry = ToolRegistry()
    tool = ToolDefinition(name="sample", description="Echo test tool.", handler=sample_tool)

    registry.register(tool)

    with pytest.raises(ValueError, match="Tool already registered: sample"):
        registry.register(tool)


@pytest.mark.asyncio
async def test_unknown_tool_execution_is_explicit() -> None:
    registry = ToolRegistry()

    with pytest.raises(ValueError, match="Unknown tool: missing"):
        await registry.execute("missing")
