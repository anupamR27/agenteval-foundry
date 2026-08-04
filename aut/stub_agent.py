from aut.base import AgentMetadata, AgentRequest, AgentResult, ExecutionContext, ToolCallRecord
from tools.registry import ToolRegistry

# query -> StubAgent -> Tool_Registry -> Answer
class StubAgent:
    """Deterministic reference agent that exercises the tool registry."""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tool_registry = tool_registry
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

        if not tool_result.success:
            return AgentResult(
                answer="The refund policy could not be retrieved.",
                agent_metadata=self.metadata,
                tool_calls=[tool_call],
                metadata={"run_id": context.run_id},
            )

        policy_text = str(tool_result.data.get("policy", tool_result.data))
        return AgentResult(
            answer=f"Refund policy: {policy_text}",
            agent_metadata=self.metadata,
            tool_calls=[tool_call],
            metadata={"run_id": context.run_id},
        )
