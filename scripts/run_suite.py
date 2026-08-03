from pathlib import Path

from pydantic import ValidationError

from scenarios.loader import load_scenario


DEFAULT_SCENARIO_PATH = Path("scenarios/examples/normal.yaml")


def main() -> None:
    try:
        scenario = load_scenario(DEFAULT_SCENARIO_PATH)
    except FileNotFoundError as exc:
        print(f"File error: {exc}")
        raise SystemExit(1) from exc
    except (ValueError, ValidationError) as exc:
        print(f"Scenario validation failed:\n{exc}")
        raise SystemExit(1) from exc

    print("AgentEval Foundry")
    print("=================")
    print(f"Scenario ID: {scenario.id}")
    print(f"Version: {scenario.version}")
    print(f"Name: {scenario.name}")
    print(f"Query: {scenario.query}")
    print(f"Required tools: {scenario.expected.required_tools}")
    print(f"Required claims: {scenario.expected.required_claims}")
    print(f"Forbidden claims: {scenario.expected.forbidden_claims}")
    print(f"Fault profile: {scenario.fault_profile}")


if __name__ == "__main__":
    main()