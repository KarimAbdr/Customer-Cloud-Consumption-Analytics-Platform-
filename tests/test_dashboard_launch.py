"""`streamlit run <script>` puts the script's folder on sys.path, not the project root.

AppTest-based tests run inside pytest, where the root is already importable, so they cannot see
this. These tests start the script the way Streamlit does (a fresh interpreter, script folder on
sys.path) and guard every launch configuration.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = "services/dashboard/app.py"


def _run_script(pythonpath: str | None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["API_URL"] = "http://127.0.0.1:9"  # nothing listens here: exercises the error page too
    if pythonpath is not None:
        env["PYTHONPATH"] = pythonpath
    return subprocess.run(
        [sys.executable, SCRIPT], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )


def test_script_cannot_import_the_project_without_pythonpath() -> None:
    """Documents why PYTHONPATH is required in every launch configuration."""
    result = _run_script(None)
    assert "No module named 'services'" in result.stderr


def test_script_starts_and_shows_an_error_page_when_the_api_is_down() -> None:
    result = _run_script(str(ROOT))
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr


def test_makefile_dashboard_target_sets_pythonpath() -> None:
    makefile = (ROOT / "Makefile").read_text()
    recipe = re.search(r"^dashboard:\n\t(.+)$", makefile, re.MULTILINE)
    assert recipe
    assert "PYTHONPATH=." in recipe.group(1)


def test_compose_image_sets_pythonpath_for_the_dashboard_service() -> None:
    assert re.search(r'^ENV .*PYTHONPATH="?/app"?', (ROOT / "Dockerfile").read_text(), re.M | re.S)


def test_render_image_sets_pythonpath_for_the_dashboard() -> None:
    dockerfile = (ROOT / "deploy" / "render" / "Dockerfile").read_text()
    assert re.search(r'PYTHONPATH="?/app"?', dockerfile)
