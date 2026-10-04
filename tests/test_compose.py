"""Structural guards for docker-compose.yml (no Docker needed, runs in CI)."""

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def services() -> dict[str, Any]:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services: dict[str, Any] = compose["services"]
    return services


def test_has_pipeline_api_and_dashboard(services: dict[str, Any]) -> None:
    assert set(services) == {"pipeline", "api", "dashboard"}


def test_api_waits_for_the_pipeline_to_finish_successfully(services: dict[str, Any]) -> None:
    condition = services["api"]["depends_on"]["pipeline"]["condition"]
    assert condition == "service_completed_successfully"


def test_dashboard_waits_for_a_healthy_api(services: dict[str, Any]) -> None:
    assert services["dashboard"]["depends_on"]["api"]["condition"] == "service_healthy"


def test_dashboard_reaches_the_api_by_service_name(services: dict[str, Any]) -> None:
    assert services["dashboard"]["environment"]["API_URL"] == "http://api:8010"


def test_pipeline_does_not_restart_after_it_finishes(services: dict[str, Any]) -> None:
    assert services["pipeline"].get("restart", "no") == "no"


def test_api_and_pipeline_share_data_and_model_volumes(services: dict[str, Any]) -> None:
    def targets(name: str) -> set[str]:
        return {str(v).split(":")[1] for v in services[name]["volumes"]}

    assert {"/app/data", "/app/mlruns"} <= targets("pipeline")
    assert {"/app/data", "/app/mlruns"} <= targets("api")


def test_services_publish_the_documented_ports(services: dict[str, Any]) -> None:
    assert "8010:8010" in services["api"]["ports"]
    assert "8501:8501" in services["dashboard"]["ports"]


def test_every_service_uses_the_same_image_build(services: dict[str, Any]) -> None:
    assert len({str(s["image"]) for s in services.values()}) == 1


def test_dockerfile_runs_as_a_non_root_user() -> None:
    lines = (ROOT / "Dockerfile").read_text().splitlines()
    assert any(line.startswith("USER ") and line.split()[1] != "root" for line in lines)


def test_dockerignore_keeps_local_state_out_of_the_image() -> None:
    ignored = (ROOT / ".dockerignore").read_text().split()
    assert {".venv", "data", "mlruns", ".git"} <= set(ignored)
