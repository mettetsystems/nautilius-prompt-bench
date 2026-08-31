from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


DEFAULT_SCENARIO_PATH = repo_root() / "demo" / "coding_prompt.yaml"


class DemoScenario(BaseModel):
    title: str = "FastAPI coding prompt"
    initial_request: str
    clarification_answers: list[str] = Field(min_length=2, max_length=2)
    edit_instructions: list[str] = Field(min_length=2, max_length=2)
    expected_initial_draft_contains: list[str] = Field(default_factory=list)
    expected_after_edits_contains: list[str] = Field(default_factory=list)
    registry_files: list[str] = Field(default_factory=list)
    core_artifact_files: list[str] = Field(default_factory=list)


def load_scenario(path: Path | None = None) -> DemoScenario:
    scenario_path = path or DEFAULT_SCENARIO_PATH
    raw = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"Invalid demo scenario file: {scenario_path}"
        raise ValueError(msg)
    return DemoScenario.model_validate(raw)


@dataclass
class DemoRunResult:
    session_id: str
    prompt_id: str
    registry_dir: Path
    artifact_dir: Path
    artifact_paths: list[Path]

    def print_summary(self) -> None:
        print("Nautilius Prompting Workbench demo complete")
        print(f"  Session:   {self.session_id}")
        print(f"  Prompt ID: {self.prompt_id}")
        print(f"  Registry:  {self.registry_dir}")
        print(f"  Artifacts: {self.artifact_dir}")
        print("  Generated files:")
        for path in self.artifact_paths:
            print(f"    - {path}")
