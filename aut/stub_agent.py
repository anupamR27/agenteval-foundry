from collections.abc import Callable
from typing import Any, Protocol

from aut.base import AgentMetadata, AgentRequest, AgentResult, ExecutionContext, ToolCallRecord
from tools.base import ToolExecutor, ToolResult


class SynthesisRecorder(Protocol):
    """Optional instrumentation hook for deterministic answer construction."""

    async def record(self, input_data: dict[str, Any], synthesize: Callable[[], str]) -> str:
        ...

# query -> StubAgent -> Tool_Registry -> Answer
class StubAgent:
    """Deterministic reference agent that exercises the tool registry."""

    def __init__(
        self,
        tool_registry: ToolExecutor,
        synthesis_recorder: SynthesisRecorder | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._synthesis_recorder = synthesis_recorder
        self.metadata = AgentMetadata(
            name="StubAgent",
            version="0.1.0",
            description="Deterministic reference agent for AgentEval Foundry.",
        )

    async def execute(self, request: AgentRequest, context: ExecutionContext) -> AgentResult:
        tool_arguments = {"query": request.query} # get user query
        # await is a keyword used to pause the execution of an asynchronous function (coroutine)
        # until the operation it is waiting for is complete, basically wait for the tool
        # to retrieve the needed parts
        tool_result = await self._tool_registry.execute("search_policy", **tool_arguments)
        tool_call = ToolCallRecord(
            tool_name="search_policy",
            arguments=tool_arguments,
            result=tool_result.data,
            success=tool_result.success,
            error=tool_result.error,
        )

        answer = await self._synthesize_answer(tool_result)
        return AgentResult(
            answer=answer,
            agent_metadata=self.metadata,
            tool_calls=[tool_call],
            metadata={"run_id": context.run_id},
        )

    async def _synthesize_answer(self, tool_result: ToolResult) -> str:
        input_data = {
            "tool_success": tool_result.success,
            "tool_data": tool_result.data,
            "tool_error": tool_result.error,
        }

        if self._synthesis_recorder is not None:
            return await self._synthesis_recorder.record(
                input_data=input_data,
                synthesize=lambda: self._build_answer(tool_result),
            )

        return self._build_answer(tool_result)

    def _build_answer(self, tool_result: ToolResult) -> str:
        if not tool_result.success:
            return "The refund policy could not be retrieved."

        policy_text = str(tool_result.data.get("policy", tool_result.data))
        return f"Refund policy: {policy_text}"
