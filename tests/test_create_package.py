"""`create_package.py --skip-zip` produces the expected package layout."""
import ast
import subprocess
import sys
import zipfile

import pytest


def _package_version(repo_root) -> str:
    tree = ast.parse((repo_root / "package.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "version"
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("'version' not found in package.py")


@pytest.fixture(scope="module")
def built_package(repo_root, tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("package")
    subprocess.run(
        [
            sys.executable,
            str(repo_root / "create_package.py"),
            "--skip-zip",
            "-o",
            str(output_dir),
        ],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
    )
    return output_dir / "editorial" / _package_version(repo_root)


def test_layout(built_package):
    for relative in (
        "package.py",
        "LICENSE",
        "server/__init__.py",
        "server/settings/main.py",
        "private/client.zip",
    ):
        assert (built_package / relative).is_file(), relative


def test_client_zip_content(built_package, repo_root):
    version = _package_version(repo_root)
    with zipfile.ZipFile(built_package / "private" / "client.zip") as zipf:
        names = zipf.namelist()
        for name in (
            "ayon_editorial/__init__.py",
            "ayon_editorial/addon.py",
            "ayon_editorial/version.py",
        ):
            assert name in names
        version_content = zipf.read("ayon_editorial/version.py").decode()

    assert f'__version__ = "{version}"' in version_content
    for name in names:
        parts = name.split("/")
        assert "AGENTS.md" not in parts
        assert "tests" not in parts
        assert "tools" not in parts
