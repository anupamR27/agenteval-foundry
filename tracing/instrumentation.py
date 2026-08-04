from collections.abc import Callable
from typing import Any

from aut.base import AgentRequest, AgentResult, AgentUnderTest, ExecutionContext
from tools.base import ToolExecutor, ToolResult
from tracing.collector import TraceCollector
from tracing.models import TraceNodeType


class TracingAgentExecutor:
    """Wrap an agent execution in a root trace span."""

    def __init__(self, agent: AgentUnderTest, collector: TraceCollector) -> None:
        self._agent = agent
        self._collector = collector
        self.metadata = getattr(agent, "metadata", None)

    async def execute(self, request: AgentRequest, context: ExecutionContext) -> AgentResult:
        async with self._collector.span(
            TraceNodeType.AGENT_EXECUTION,
            name=getattr(self.metadata, "name", "agent"),
            input_data={
                "request": request.model_dump(mode="json"),
                "context": context.model_dump(mode="json"),
            },
        ) as span:
            result = await self._agent.execute(request, context)
            self._collector.complete_span(
                span,
                output_data={
                    "answer": result.answer,
                    "agent_metadata": result.agent_metadata.model_dump(mode="json"),
                    "tool_calls": [
                        tool_call.model_dump(mode="json") for tool_call in result.tool_calls
                    ],
                    "metadata": result.metadata,
                },
            )
            return result


class TracingToolExecutor:
    """Wrap tool execution in child trace spans without changing registry semantics."""

    def __init__(self, tool_executor: ToolExecutor, collector: TraceCollector) -> None:
        self._tool_executor = tool_executor
        self._collector = collector

    async def execute(self, name: str, **arguments: object) -> ToolResult:
        async with self._collector.span(
            TraceNodeType.TOOL_EXECUTION,
            name=name,
            input_data={"tool_name": name, "arguments": arguments},
        ) as span:
            result = await self._tool_executor.execute(name, **arguments)
            output_data = result.model_dump(mode="json")
            if result.success:
                self._collector.complete_span(span, output_data=output_data)
            else:
                self._collector.fail_span(
                    span,
                    error=result.error or f"Tool returned unsuccessful result: {name}",
                    output_data=output_data,
                )
            return result


class TraceSynthesisRecorder:
    """Record deterministic answer construction as a synthesis span."""

    def __init__(self, collector: TraceCollector) -> None:
        self._collector = collector

    async def record(self, input_data: dict[str, Any], synthesize: Callable[[], str]) -> str:
        async with self._collector.span(
            TraceNodeType.SYNTHESIS,
            name="deterministic_answer",
            input_data=input_data,
        ) as span:
            answer = synthesize()
            self._collector.complete_span(span, output_data={"answer": answer})
            return answer
