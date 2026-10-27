"""Metadata of `package.py` and its agreement with the client code."""
import ast
import re
from pathlib import Path

import pytest

SEMVER_RE = re.compile(
    r"^\d+\.\d+\.\d+"
    r"(-[0-9A-Za-z.-]+)?"
    r"(\+[0-9A-Za-z.-]+)?$"
)


def _read_assignments(path: Path) -> dict:
    """Read top level literal assignments of a python file without import."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                values[target.id] = ast.literal_eval(node.value)
    return values


@pytest.fixture(scope="module")
def package_data(repo_root):
    return _read_assignments(repo_root / "package.py")


def test_name_and_title(package_data):
    assert package_data["name"] == "editorial"
    assert package_data["title"]


def test_version_is_semver(package_data):
    assert SEMVER_RE.match(package_data["version"])


def test_client_dir_exists(package_data, repo_root):
    assert package_data["client_dir"] == "ayon_editorial"
    assert (repo_root / "client" / package_data["client_dir"]).is_dir()


def test_server_version(package_data):
    assert package_data["ayon_server_version"]


def test_core_is_required(package_data):
    assert "core" in package_data["ayon_required_addons"]


def test_client_version_matches_package(package_data, repo_root):
    version_path = (
        repo_root / "client" / package_data["client_dir"] / "version.py"
    )
    client_data = _read_assignments(version_path)
    assert client_data["__version__"] == package_data["version"]
