"""Guards for the Hugging Face Space bundle (what gets pushed to the Space repository)."""

from pathlib import Path

import pytest

from deploy.space_bundle import ROOT, build_bundle

PORT = "7860"


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> Path:
    dest = tmp_path_factory.mktemp("space") / "bundle"
    build_bundle(dest)
    return dest


def test_bundle_has_the_files_a_docker_space_needs_at_its_root(bundle: Path) -> None:
    for name in ["Dockerfile", "README.md", "start.sh", "pyproject.toml", "uv.lock", "Makefile"]:
        assert (bundle / name).is_file(), name


def test_bundle_contains_the_application_code(bundle: Path) -> None:
    for package in ["data_platform", "dbt", "ml", "services"]:
        assert (bundle / package).is_dir(), package
    assert (bundle / "dbt" / "dbt_project.yml").is_file()


@pytest.mark.parametrize(
    "excluded", [".git", ".venv", "data", "mlruns", "tests", "docs", "dbt/target", "dbt/logs"]
)
def test_bundle_leaves_out_local_state_and_dev_files(bundle: Path, excluded: str) -> None:
    assert not (bundle / excluded).exists()


def test_bundle_has_no_bytecode_caches(bundle: Path) -> None:
    assert not list(bundle.rglob("__pycache__"))


def test_space_readme_declares_a_docker_space_on_the_expected_port(bundle: Path) -> None:
    header = (bundle / "README.md").read_text().split("---")[1]
    assert "sdk: docker" in header
    assert f"app_port: {PORT}" in header


def test_space_readme_is_not_the_github_readme(bundle: Path) -> None:
    assert (bundle / "README.md").read_text() != (ROOT / "README.md").read_text()


def test_dockerfile_builds_the_data_and_model_and_listens_on_the_space_port(bundle: Path) -> None:
    dockerfile = (bundle / "Dockerfile").read_text()
    assert "make pipeline" in dockerfile
    assert f"EXPOSE {PORT}" in dockerfile
    assert "start.sh" in dockerfile


def test_dockerfile_runs_as_the_non_root_user_spaces_expects(bundle: Path) -> None:
    lines = (bundle / "Dockerfile").read_text().splitlines()
    assert "USER app" in lines
    assert "useradd --create-home --uid 1000 app" in "\n".join(lines)


def test_start_script_runs_the_api_privately_before_the_public_dashboard(bundle: Path) -> None:
    script = (bundle / "start.sh").read_text()
    assert script.index("uvicorn") < script.index("streamlit")
    assert "--host 127.0.0.1" in script
    assert f"--server.port {PORT}" in script
    assert "--server.address 0.0.0.0" in script
    assert "API_URL=http://127.0.0.1:8010" in script


def test_start_script_waits_for_the_api_to_be_healthy(bundle: Path) -> None:
    assert "/health" in (bundle / "start.sh").read_text()


def test_start_script_is_executable(bundle: Path) -> None:
    assert (bundle / "start.sh").stat().st_mode & 0o111


def test_building_again_replaces_the_previous_bundle(tmp_path: Path) -> None:
    dest = tmp_path / "bundle"
    build_bundle(dest)
    (dest / "stale.txt").write_text("old")
    build_bundle(dest)
    assert not (dest / "stale.txt").exists()


def test_refuses_to_overwrite_a_directory_it_did_not_create(tmp_path: Path) -> None:
    dest = tmp_path / "precious"
    dest.mkdir()
    (dest / "notes.txt").write_text("keep me")
    with pytest.raises(FileExistsError, match="not a space bundle"):
        build_bundle(dest)
    assert (dest / "notes.txt").read_text() == "keep me"


def test_makefile_has_a_space_bundle_target() -> None:
    assert "\nspace-bundle:" in (ROOT / "Makefile").read_text()


def test_rebuilding_keeps_the_git_directory_of_the_space_repository(tmp_path: Path) -> None:
    dest = tmp_path / "bundle"
    build_bundle(dest)
    (dest / ".git").mkdir()
    (dest / ".git" / "config").write_text("[remote]")
    build_bundle(dest)
    assert (dest / ".git" / "config").read_text() == "[remote]"
