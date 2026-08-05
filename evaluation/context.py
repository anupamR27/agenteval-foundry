from pydantic import BaseModel, ConfigDict

from aut.base import AgentResult
from faults.models import FaultActivationRecord
from scenarios.models import Scenario
from tracing.models import ExecutionTrace


class EvaluationContext(BaseModel):
    """Read-only inputs available to deterministic graders."""

    model_config = ConfigDict(frozen=True)

    scenario: Scenario
    agent_result: AgentResult
    execution_trace: ExecutionTrace
    fault_activation_records: tuple[FaultActivationRecord, ...] = ()
