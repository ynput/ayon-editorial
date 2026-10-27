"""Shared fixtures for the addon tests.

Tests never import `ayon_core`: they read files and use AST.
"""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Root directory of the addon repository."""
    return REPO_ROOT
