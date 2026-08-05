from collections.abc import Iterable

from faults.models import FaultActivationRecord, FaultSpec, FaultType
from faults.policies import FaultActivationPolicy
from tools.base import ToolExecutor, ToolResult


class FaultInjectingToolExecutor:
    """Applies deterministic configured faults around an async tool executor."""

    def __init__(
        self,
        wrapped: ToolExecutor,
        faults: Iterable[FaultSpec] | None = None,
        activation_policy: FaultActivationPolicy | None = None,
    ) -> None:
        self._wrapped = wrapped
        self._faults = list(faults or [])
        self._activation_policy = activation_policy or FaultActivationPolicy()
        self._activation_records: list[FaultActivationRecord] = []

    @property
    def activation_records(self) -> tuple[FaultActivationRecord, ...]:
        return tuple(self._activation_records)

    async def execute(self, name: str, **arguments: object) -> ToolResult:
        call_number = self._activation_policy.next_call_number(name)
        fault = self._select_fault(name, call_number)
        if fault is None:
            return await self._wrapped.execute(name, **arguments)

        record = FaultActivationRecord(
            fault_id=fault.fault_id,
            fault_type=fault.fault_type,
            target_tool=name,
            call_number=call_number,
            activated=True,
            reason=f"Activated {fault.fault_type} for {name} call {call_number}",
            parameters=fault.parameters,
        )
        self._activation_records.append(record)
        return self._apply_fault(fault, record)

    def _select_fault(self, name: str, call_number: int) -> FaultSpec | None:
        for fault in self._faults:
            if self._activation_policy.should_activate(fault, name, call_number):
                return fault
        return None

    def _apply_fault(self, fault: FaultSpec, record: FaultActivationRecord) -> ToolResult:
        metadata = {"fault": record.model_dump(mode="json")}
        if fault.fault_type == FaultType.TOOL_TIMEOUT:
            return ToolResult(
                success=False,
                data=None,
                error=f"Injected timeout for tool: {record.target_tool}",
                metadata=metadata,
            )
        if fault.fault_type == FaultType.TOOL_ERROR:
            message = fault.parameters.get("message", f"Injected error for tool: {record.target_tool}")
            return ToolResult(success=False, data=None, error=str(message), metadata=metadata)
        if fault.fault_type == FaultType.MALFORMED_OUTPUT:
            return ToolResult(success=True, data={"unexpected_field": 123}, metadata=metadata)
        if fault.fault_type == FaultType.BAD_RETRIEVAL:
            return ToolResult(
                success=True,
                data={
                    "policy": "Annual subscriptions may be refunded within 30 days of purchase.",
                },
                metadata=metadata,
            )
        if fault.fault_type == FaultType.CONTEXT_TRUNCATION:
            return ToolResult(
                success=True,
                data={"policy": "Annual subscriptions may be refunded within..."},
                metadata=metadata,
            )

        msg = f"Unsupported fault type: {fault.fault_type}"
        raise ValueError(msg)
