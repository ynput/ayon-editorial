"""The builder reproduces the Resolve reference exporter."""

import importlib.util
import json
from pathlib import Path

import pytest

otio = pytest.importorskip("opentimelineio")
pytest.importorskip("clique")

from ayon_editorial.otio.compare import (  # noqa: E402
    compare_timelines,
    format_differences,
)

pytestmark = pytest.mark.otio

_RESOURCES = Path(__file__).parent / "resources" / "host_exports"


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, _RESOURCES / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data():
    return json.loads((_RESOURCES / "resolve_input.json").read_text())


@pytest.fixture(scope="module")
def reference(data):
    return _load("resolve_reference").export(data)


def test_builder_matches_reference(data, reference):
    built = _load("resolve_specs").build(data)
    diffs = compare_timelines(reference, built)
    assert diffs == [], format_differences(diffs)


def test_reference_matches_golden(reference):
    golden = otio.adapters.read_from_file(str(_RESOURCES / "resolve.otio"))
    diffs = compare_timelines(golden, reference)
    assert diffs == [], format_differences(diffs)
