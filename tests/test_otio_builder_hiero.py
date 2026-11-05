"""The builder reproduces the Hiero reference export.

`hiero_reference.py` is the host export code run on a plain input,
`hiero_specs.py` maps the same input to builder specs (the template of the
P2.7 adoption). Both must give the same timeline, and the reference must
still give the golden written on OTIO 0.15.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from ayon_editorial.otio.compare import compare_timelines, format_differences

otio = pytest.importorskip("opentimelineio")
pytestmark = pytest.mark.otio

RESOURCES = Path(__file__).parent / "resources" / "host_exports"


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, RESOURCES / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data():
    return json.loads((RESOURCES / "hiero_input.json").read_text())


@pytest.fixture(scope="module")
def reference(data):
    return _load("hiero_reference").export(data)


def test_builder_matches_reference(data, reference):
    built = _load("hiero_specs").build(data)
    diffs = compare_timelines(reference, built)
    assert diffs == [], format_differences(diffs)


def test_reference_matches_golden(reference):
    golden = otio.adapters.read_from_file(str(RESOURCES / "hiero.otio"))
    diffs = compare_timelines(golden, reference)
    assert diffs == [], format_differences(diffs)
