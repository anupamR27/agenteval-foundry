from collections import defaultdict

from faults.models import FaultSpec, FaultTrigger


class FaultActivationPolicy:
    """Tracks per-tool call counts and evaluates deterministic fault triggers."""

    def __init__(self) -> None:
        self._call_counts: dict[str, int] = defaultdict(int)

    def next_call_number(self, tool_name: str) -> int:
        self._call_counts[tool_name] += 1
        return self._call_counts[tool_name]

    def should_activate(self, fault: FaultSpec, tool_name: str, call_number: int) -> bool:
        if not fault.enabled or fault.target_tool != tool_name:
            return False
        if fault.trigger == FaultTrigger.ALWAYS:
            return True
        if fault.trigger == FaultTrigger.FIRST_CALL:
            return call_number == 1
        if fault.trigger == FaultTrigger.CALL_NUMBER:
            return call_number == fault.call_number
        return False
