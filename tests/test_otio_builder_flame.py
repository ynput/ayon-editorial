"""The builder reproduces the Flame reference exporter.

`flame_reference.py` is the host export code run without Flame,
`flame_specs.py` maps the same input to builder specs. Both must give the
same timeline, and the reference must still give the `flame.otio` golden
(written on OTIO 0.15), which catches OTIO drift and edits to the reference.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from ayon_editorial.otio.compare import compare_timelines, format_differences

otio = pytest.importorskip("opentimelineio")
pytestmark = pytest.mark.otio

HOST_EXPORTS = Path(__file__).resolve().parent / "resources" / "host_exports"


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, HOST_EXPORTS / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data():
    return json.loads((HOST_EXPORTS / "flame_input.json").read_text())


@pytest.fixture(scope="module")
def reference(data):
    return _load("flame_reference").export(json.loads(json.dumps(data)))


def test_builder_flame_matches_reference(data, reference):
    built = _load("flame_specs").build(json.loads(json.dumps(data)))
    diffs = compare_timelines(reference, built)
    assert diffs == [], format_differences(diffs)


def test_flame_reference_matches_golden(reference):
    golden = otio.adapters.read_from_file(str(HOST_EXPORTS / "flame.otio"))
    diffs = compare_timelines(golden, reference)
    assert diffs == [], format_differences(diffs)
