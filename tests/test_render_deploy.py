"""Guards for the Render deployment files (render.yaml, Dockerfile, start script)."""

import re
import stat
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
RENDER_DIR = ROOT / "deploy" / "render"
DOCKERFILE = RENDER_DIR / "Dockerfile"
START = RENDER_DIR / "start.sh"


@pytest.fixture(scope="module")
def service() -> dict[str, Any]:
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text())
    services: list[dict[str, Any]] = blueprint["services"]
    assert len(services) == 1
    return services[0]


def test_blueprint_declares_one_free_docker_web_service(service: dict[str, Any]) -> None:
    assert service["type"] == "web"
    assert service["runtime"] == "docker"
    assert service["plan"] == "free"


def test_blueprint_points_at_the_demo_dockerfile_not_the_compose_one(
    service: dict[str, Any],
) -> None:
    assert service["dockerfilePath"] == "./deploy/render/Dockerfile"
    assert service["dockerContext"] == "."
    assert DOCKERFILE.is_file()


def test_blueprint_health_check_uses_the_dashboard_endpoint(service: dict[str, Any]) -> None:
    assert service["healthCheckPath"] == "/_stcore/health"


def test_blueprint_redeploys_on_every_commit(service: dict[str, Any]) -> None:
    assert service["autoDeployTrigger"] == "commit"


def test_dockerfile_has_a_cmd_that_starts_the_app() -> None:
    """Regression: the Compose Dockerfile has no CMD and the container exited immediately."""
    assert 'CMD ["./start.sh"]' in DOCKERFILE.read_text()


def test_dockerfile_builds_the_data_and_the_model() -> None:
    assert "RUN make pipeline" in DOCKERFILE.read_text()


def test_dockerfile_runs_as_a_non_root_user() -> None:
    assert "USER app" in DOCKERFILE.read_text().splitlines()


def test_dockerfile_installs_the_openmp_runtime_for_lightgbm() -> None:
    assert "libgomp1" in DOCKERFILE.read_text()


def _copy_sources() -> list[str]:
    sources: list[str] = []
    for line in DOCKERFILE.read_text().splitlines():
        match = re.match(r"COPY\s+(?!--from)(.+)\s+\S+$", line)
        if match:
            sources += match.group(1).split()
    return sources


def test_every_copied_path_exists_in_the_build_context() -> None:
    sources = _copy_sources()
    assert sources
    for source in sources:
        assert (ROOT / source).exists(), f"COPY source missing: {source}"


def test_no_copied_path_is_excluded_by_dockerignore() -> None:
    ignored = {line.strip().rstrip("/") for line in (ROOT / ".dockerignore").read_text().split()}
    for source in _copy_sources():
        assert source.lstrip("./").split("/")[0] not in ignored, f"{source} is dockerignored"


def test_start_script_binds_the_port_render_provides() -> None:
    script = START.read_text()
    assert 'PORT="${PORT:-10000}"' in script
    assert '--server.port "$PORT"' in script
    assert "--server.address 0.0.0.0" in script


def test_start_script_keeps_the_api_private_and_starts_it_first() -> None:
    script = START.read_text()
    assert script.index("uvicorn") < script.index("streamlit")
    assert "--host 127.0.0.1" in script
    assert "API_URL=http://127.0.0.1:8010" in script


def test_start_script_waits_for_a_healthy_api() -> None:
    assert "/health" in START.read_text()


def test_start_script_is_executable() -> None:
    assert START.stat().st_mode & stat.S_IXUSR


def test_readme_documents_the_render_deployment() -> None:
    readme = (ROOT / "README.md").read_text()
    assert "render.yaml" in readme
    assert "Hugging Face" not in readme
