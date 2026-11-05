"""Shared fixtures for the addon tests.

Tests never import `ayon_core`: they read files and use AST.
"""
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = REPO_ROOT / "client" / "ayon_editorial"


def _stub_package() -> None:
    """Make `ayon_editorial.<module>` importable without its `__init__`.

    The real `__init__` imports `addon.py` and so `ayon_core`, which tests
    never have. A bare package object with the right `__path__` is enough
    for the layer 0 modules and their relative imports.
    """
    if "ayon_editorial" in sys.modules:
        return
    package = types.ModuleType("ayon_editorial")
    package.__path__ = [str(PACKAGE_DIR)]
    sys.modules["ayon_editorial"] = package


_stub_package()


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Root directory of the addon repository."""
    return REPO_ROOT
