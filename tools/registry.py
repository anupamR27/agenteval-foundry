from tools.base import ToolDefinition, ToolResult


class ToolRegistry:
    """Small async registry for named tool execution."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool by unique name."""

        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def list_names(self) -> list[str]:
        """Return registered tool names in deterministic order."""

        return sorted(self._tools)

    async def execute(self, name: str, **arguments: object) -> ToolResult:
        """Execute a registered tool by name."""

        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name}")

        return await tool.handler(**arguments)
