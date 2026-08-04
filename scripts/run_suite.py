import asyncio
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from aut.base import AgentRequest, ExecutionContext
from aut.stub_agent import StubAgent
from scenarios.loader import load_scenario
from tools.mock_tools import build_default_tool_registry

DEFAULT_SCENARIO_PATH = Path("scenarios/examples/normal.yaml")


async def run() -> None:
    try:
        scenario = load_scenario(DEFAULT_SCENARIO_PATH)
    except FileNotFoundError as exc:
        print(f"File error: {exc}")
        raise SystemExit(1) from exc
    except (TypeError, ValueError, ValidationError) as exc:
        print(f"Scenario validation failed:\n{exc}")
        raise SystemExit(1) from exc

    run_id = str(uuid4())
    registry = build_default_tool_registry()
    agent = StubAgent(registry)
    result = await agent.execute(
        AgentRequest(query=scenario.query, scenario_id=scenario.id),
        ExecutionContext(run_id=run_id, scenario_version=scenario.version),
    )

    print("AgentEval Foundry")
    print("=================")
    print(f"Run ID: {run_id}")
    print(f"Scenario ID: {scenario.id}")
    print(f"Version: {scenario.version}")
    print(f"Name: {scenario.name}")
    print(f"Query: {scenario.query}")
    print(f"Required tools: {scenario.expected.required_tools}")
    print(f"Required claims: {scenario.expected.required_claims}")
    print(f"Forbidden claims: {scenario.expected.forbidden_claims}")
    print(f"Fault profile: {scenario.fault_profile}")
    print()
    print(f"Agent: {result.agent_metadata.name} v{result.agent_metadata.version}")
    print(f"Final answer: {result.answer}")
    print("Observed tool calls:")
    for tool_call in result.tool_calls:
        status = "succeeded" if tool_call.success else "failed"
        print(f"- {tool_call.tool_name}: {status}")
        print(f"  Arguments: {tool_call.arguments}")
        print(f"  Result: {tool_call.result}")
        if tool_call.error:
            print(f"  Error: {tool_call.error}")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
