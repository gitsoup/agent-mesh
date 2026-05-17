import json

import pytest
from pydantic import ValidationError

from agent_mesh.config import ProjectConfig


def test_project_config_defaults_match_expected_contract() -> None:
    config = ProjectConfig(project_name="demo", project_key="APP")

    assert config.schema_version == "0.1"
    assert config.planning.provider == "local"
    assert config.coordination.work_dir == ".agentic/work"
    assert config.adapters == ["generic"]


def test_project_config_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ProjectConfig.model_validate(
            {
                "project_name": "demo",
                "project_key": "APP",
                "unexpected": True,
            }
        )


def test_project_config_serializes_to_json() -> None:
    config = ProjectConfig(project_name="demo", project_key="APP")

    payload = json.loads(config.to_json())

    assert payload["project_name"] == "demo"
    assert payload["dashboard"]["output_dir"] == ".agentic/dashboard"
