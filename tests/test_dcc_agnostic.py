"""AST scan of the client code for the module layer rules.

Nothing is imported, so the tests run without `ayon_core` or any host.
"""
import ast
import sys
from pathlib import Path
from typing import Iterator, Tuple

import pytest

PACKAGE = "ayon_editorial"

HOST_MODULES = {
    "hiero",
    "flame",
    "DaVinciResolveScript",
    "fusionscript",
    "unreal",
    "nuke",
}
QT_MODULES = {"qtpy", "PySide2", "PySide6", "Qt"}
ALLOWED_AYON_PACKAGES = {
    "ayon_core",
    "ayon_api",
    "ayon_applications",
    PACKAGE,
}
LAYER0_THIRD_PARTY = {"opentimelineio", "clique"}
LAYER0_PATHS = ("otio", "shots", "editorial_package.py")
ADDON_ALLOWED = {"ayon_core"}

if hasattr(sys, "stdlib_module_names"):
    STDLIB = set(sys.stdlib_module_names) | {"__future__"}
else:  # Python 3.9
    STDLIB = {
        "__future__", "abc", "argparse", "array", "ast", "asyncio",
        "base64", "bisect", "builtins", "calendar", "collections",
        "colorsys", "concurrent", "configparser", "contextlib", "copy",
        "csv", "ctypes", "dataclasses", "datetime", "decimal", "difflib",
        "enum", "errno", "fnmatch", "fractions", "functools", "gc",
        "getpass", "glob", "gzip", "hashlib", "heapq", "hmac", "html",
        "http", "importlib", "inspect", "io", "itertools", "json",
        "logging", "math", "mimetypes", "numbers", "operator", "os",
        "pathlib", "pickle", "platform", "posixpath", "pprint", "queue",
        "random", "re", "shlex", "shutil", "signal", "socket", "stat",
        "statistics", "string", "struct", "subprocess", "sys", "tempfile",
        "textwrap", "threading", "time", "timeit", "traceback", "types",
        "typing", "unittest", "urllib", "uuid", "warnings", "weakref",
        "xml", "zipfile", "zlib",
    }

Import = Tuple[int, str, int, bool]  # line, module, level, top level


def _client_root(repo_root: Path) -> Path:
    return repo_root / "client" / PACKAGE


def _is_layer0(path: Path, client_root: Path) -> bool:
    relative = path.relative_to(client_root).parts
    return bool(relative) and relative[0] in LAYER0_PATHS


def _iter_imports(tree: ast.AST) -> Iterator[Import]:
    """Yield `(line, module, level, top_level)` for every import.

    For `from . import x` the module is `x`, so relative imports of
    siblings are visible as modules with a level.
    """
    def walk(node: ast.AST, top_level: bool):
        for child in ast.iter_child_nodes(node):
            nested = top_level and isinstance(
                child, (ast.If, ast.Try, ast.With, ast.ExceptHandler)
            )
            if isinstance(child, ast.Import):
                for alias in child.names:
                    yield child.lineno, alias.name, 0, top_level
            elif isinstance(child, ast.ImportFrom):
                module = child.module or ""
                if child.level and not module:
                    for alias in child.names:
                        yield child.lineno, alias.name, child.level, top_level
                else:
                    yield child.lineno, module, child.level, top_level
            elif isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                yield from walk(child, False)
            else:
                yield from walk(child, nested)

    yield from walk(tree, True)


def _python_files(client_root: Path):
    if not client_root.is_dir():
        return []
    return sorted(client_root.rglob("*.py"))


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def check_file(path: Path, client_root: Path, repo_root: Path):
    """Return violation messages (file, line, rule) of one file."""
    rel = path.relative_to(repo_root).as_posix()
    layer0 = _is_layer0(path, client_root)
    violations = []
    for line, module, level, top_level in _iter_imports(_parse(path)):
        root = module.split(".")[0]
        where = f"{rel}:{line}"
        if level:
            continue
        if root in HOST_MODULES:
            violations.append(
                f"{where}: host API '{module}' must not be imported"
            )
        if root.startswith("ayon_") and root not in ALLOWED_AYON_PACKAGES:
            violations.append(
                f"{where}: package '{root}' is not allowed"
                " (no host addon imports)"
            )
        if top_level and root in QT_MODULES:
            violations.append(
                f"{where}: Qt module '{module}' must not be imported"
                " at module top level"
            )
        if layer0 and not (
            root in STDLIB
            or root in LAYER0_THIRD_PARTY
            or root == PACKAGE
        ):
            violations.append(
                f"{where}: layer 0 may import only the standard library,"
                f" opentimelineio and clique, not '{module}'"
            )
        if layer0 and root == PACKAGE:
            parts = module.split(".")[1:]
            if not parts or parts[0] not in {
                Path(p).stem for p in LAYER0_PATHS
            }:
                violations.append(
                    f"{where}: layer 0 may import only layer 0 modules of"
                    f" {PACKAGE}, not '{module}'"
                )
    return violations


def test_no_host_qt_or_host_addon_imports(repo_root):
    client_root = _client_root(repo_root)
    violations = []
    for path in _python_files(client_root):
        violations.extend(check_file(path, client_root, repo_root))
    assert not violations, "\n".join(violations)


def _layer0_relative_violations(path, client_root, repo_root):
    """Relative imports of layer 0 files must stay in layer 0."""
    violations = []
    package_parts = path.relative_to(client_root).parent.parts
    for line, module, level, _ in _iter_imports(_parse(path)):
        if not level:
            continue
        base = package_parts[: len(package_parts) - (level - 1)]
        target = [*base, *module.split(".")] if module else list(base)
        if not target:
            # `from .. import version` style: top of the package
            continue
        if target[0] not in {Path(p).stem for p in LAYER0_PATHS}:
            rel = path.relative_to(repo_root).as_posix()
            violations.append(
                f"{rel}:{line}: layer 0 may import only layer 0 modules,"
                f" not relative '{'.' * level}{module}'"
            )
    return violations


def test_layer0_relative_imports(repo_root):
    client_root = _client_root(repo_root)
    violations = []
    for path in _python_files(client_root):
        if _is_layer0(path, client_root):
            violations.extend(
                _layer0_relative_violations(path, client_root, repo_root)
            )
    assert not violations, "\n".join(violations)


def test_addon_imports_only_core_and_version(repo_root):
    client_root = _client_root(repo_root)
    path = client_root / "addon.py"
    rel = path.relative_to(repo_root).as_posix()
    violations = []
    for line, module, level, _ in _iter_imports(_parse(path)):
        root = module.split(".")[0]
        if level:
            if not (level == 1 and module == "version"):
                violations.append(
                    f"{rel}:{line}: addon.py may import only '.version'"
                    f" from the package, not '{'.' * level}{module}'"
                )
        elif root not in STDLIB and root not in ADDON_ALLOWED:
            violations.append(
                f"{rel}:{line}: addon.py may import only the standard"
                f" library and ayon_core, not '{module}'"
            )
    assert not violations, "\n".join(violations)


@pytest.mark.parametrize(
    "source, expected",
    [
        ("import hiero", "host API"),
        ("from nuke import x", "host API"),
        ("import ayon_hiero", "not allowed"),
        ("from qtpy import QtWidgets", "top level"),
    ],
)
def test_scanner_detects_violations(tmp_path, source, expected):
    client_root = tmp_path / "client" / PACKAGE
    client_root.mkdir(parents=True)
    path = client_root / "bad.py"
    path.write_text(source + "\n", encoding="utf-8")
    messages = check_file(path, client_root, tmp_path)
    assert any(expected in message for message in messages)


def test_scanner_layer0_rules(tmp_path):
    client_root = tmp_path / "client" / PACKAGE
    (client_root / "otio").mkdir(parents=True)
    path = client_root / "otio" / "mod.py"
    path.write_text(
        "import os\nimport clique\nimport requests\n"
        "from ayon_editorial.shots import x\n"
        "from ayon_editorial.addon import y\n",
        encoding="utf-8",
    )
    messages = check_file(path, client_root, tmp_path)
    assert len(messages) == 2
    assert "requests" in messages[0]
    assert "ayon_editorial.addon" in messages[1]
