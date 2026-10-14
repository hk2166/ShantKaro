"""Load and validate the scenario YAML files in the repo's scenarios/ folder."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from shant.scenarios.schema import Scenario

SCENARIOS_DIR = Path(__file__).resolve().parents[4] / "scenarios"


class ScenarioError(Exception):
    """A scenario file can't be read or doesn't match the schema."""


def load_scenario(path: Path) -> Scenario:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        scenario = Scenario.model_validate(data)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ScenarioError(f"{path.name}: {error}") from error
    if scenario.id != path.stem:
        raise ScenarioError(f"{path.name}: id '{scenario.id}' must match the file name")
    return scenario


def load_all(directory: Path = SCENARIOS_DIR) -> dict[str, Scenario]:
    paths = sorted(directory.glob("*.yaml"))
    if not paths:
        raise ScenarioError(f"no scenario files in {directory}")
    return {path.stem: load_scenario(path) for path in paths}
