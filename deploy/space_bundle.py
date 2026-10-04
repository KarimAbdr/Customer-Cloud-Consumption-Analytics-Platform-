"""Assemble the folder that is pushed to a Hugging Face (Docker) Space.

A Space needs its own `Dockerfile` and `README.md` at the repository root, which differ from this
repository's, so the bundle is generated: `make space-bundle` -> `dist/space`.
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPACE_FILES = ["Dockerfile", "README.md", "start.sh"]
ROOT_FILES = ["pyproject.toml", "uv.lock", "Makefile"]
PACKAGES = ["data_platform", "dbt", "ml", "services"]
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "target", "logs", ".user.yml")


def _clean(dest: Path) -> None:
    """Empty a previous bundle but keep its `.git`; refuse anything that is not a bundle."""
    if not dest.exists():
        return
    children = list(dest.iterdir())
    if children and not {"Dockerfile", "start.sh"} <= {c.name for c in children}:
        raise FileExistsError(f"{dest} exists and is not a space bundle; refusing to overwrite it")
    for child in children:
        if child.name == ".git":
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()


def build_bundle(dest: Path) -> None:
    _clean(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for name in SPACE_FILES:
        shutil.copy2(ROOT / "deploy" / "space" / name, dest / name)
    for name in ROOT_FILES:
        shutil.copy2(ROOT / name, dest / name)
    for package in PACKAGES:
        shutil.copytree(ROOT / package, dest / package, ignore=IGNORE)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "space"
    build_bundle(target)
    print(f"Space bundle written to {target}")
