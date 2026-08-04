from tools.base import ToolDefinition, ToolResult
from tools.registry import ToolRegistry


async def search_policy(query: str) -> ToolResult:
    """Return deterministic subscription refund policy information."""

    return ToolResult(
        success=True,
        data={
            "query": query,
            "policy": "Annual subscriptions may be refunded within 14 days of purchase.",
        },
    )


def build_default_tool_registry() -> ToolRegistry:
    """Build a registry containing the default deterministic mock tools."""

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="search_policy",
            description="Search subscription refund policy information.",
            handler=search_policy,
        )
    )
    return registry
