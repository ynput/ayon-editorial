"""Tests of `otio/compat.py`: version helpers and the clip search shims."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from ayon_editorial.otio import compat

otio = pytest.importorskip("opentimelineio")
pytestmark = pytest.mark.otio


def _timeline():
    """Timeline with a clip in a track and a clip in a nested stack."""
    timeline = otio.schema.Timeline(name="tl")
    track = otio.schema.Track(name="v1")
    track.append(otio.schema.Clip(name="top"))
    nested = otio.schema.Stack(name="nested")
    inner = otio.schema.Track(name="inner")
    inner.append(otio.schema.Clip(name="deep"))
    nested.append(inner)
    track.append(nested)
    timeline.tracks.append(track)
    return timeline


@pytest.mark.parametrize(
    "text, expected",
    [
        ("0.15.0", (0, 15, 0)),
        ("0.17.0.dev1", (0, 17, 0)),
        ("  0.16", (0, 16)),
        ("1.0.0rc1", (1, 0, 0)),
        ("", ()),
        (None, ()),
        ("dev", ()),
    ],
)
def test_parse_version(text, expected):
    assert compat.parse_version(text) == expected


def test_get_otio_version_matches_installed():
    assert compat.get_otio_version() == compat.parse_version(
        otio.__version__)
    assert compat.get_otio_version() >= compat.MIN_OTIO_VERSION


def test_check_otio_version_returns_version():
    assert compat.check_otio_version() == compat.get_otio_version()
    assert compat.is_otio_supported()


def test_check_otio_version_too_old(monkeypatch):
    monkeypatch.setattr(compat, "get_otio_version", lambda: (0, 14, 1))
    with pytest.raises(compat.OTIOVersionError, match="0.15 or newer"):
        compat.check_otio_version()
    assert not compat.is_otio_supported()
    assert compat.is_otio_supported((0, 14))


def test_check_otio_version_unreadable(monkeypatch):
    monkeypatch.setattr(compat, "get_otio_version", lambda: ())
    with pytest.raises(compat.OTIOVersionError, match="unreadable"):
        compat.check_otio_version()


def test_require_otio_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "opentimelineio", None)
    with pytest.raises(compat.OTIOVersionError, match="not installed"):
        compat.require_otio()
    assert not compat.is_otio_supported()


def test_find_clips_includes_nested_clips():
    names = [clip.name for clip in compat.find_clips(_timeline())]
    assert names == ["top", "deep"]


def test_find_clips_shallow_search():
    names = [
        clip.name
        for clip in compat.find_clips(_timeline(), shallow_search=True)
    ]
    assert names == []
    track = _timeline().tracks[0]
    names = [
        clip.name for clip in compat.find_clips(track, shallow_search=True)
    ]
    assert names == ["top"]


def test_find_clips_on_track():
    track = _timeline().tracks[0]
    assert [c.name for c in compat.find_clips(track)] == ["top", "deep"]


def test_each_clip_yields_same_clips():
    names = [clip.name for clip in compat.each_clip(_timeline())]
    assert names == ["top", "deep"]


def test_find_children_by_type():
    stacks = compat.find_children(
        _timeline(), descended_from_type=otio.schema.Stack)
    assert [s.name for s in stacks] == ["nested"]


def test_find_children_without_type():
    children = compat.find_children(_timeline().tracks[0])
    assert {c.name for c in children} == {"top", "nested", "inner", "deep"}


def test_find_clips_legacy_each_clip_only():
    """OTIO 0.15 has `each_clip` only (Hiero 14 and Resolve 18 variant)."""
    calls = []

    def each_clip(search_range=None, shallow_search=False):
        calls.append((search_range, shallow_search))
        return iter(["a", "b"])

    legacy = SimpleNamespace(each_clip=each_clip)
    assert compat.find_clips(legacy) == ["a", "b"]
    assert calls == [(None, False)]


def test_find_clips_prefers_find_clips():
    modern = SimpleNamespace(
        find_clips=lambda search_range=None, shallow_search=False: ["new"],
        each_clip=lambda *args: ["old"],
    )
    assert compat.find_clips(modern) == ["new"]


def test_find_children_legacy_each_child_only():
    def each_child(
        search_range=None, descended_from_type=None, shallow_search=False
    ):
        return iter(["x"])

    legacy = SimpleNamespace(each_child=each_child)
    assert compat.find_children(legacy) == ["x"]
