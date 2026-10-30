"""Characterization tests of `otio/markers.py`.

The host lookups are copied below and run on the same timelines as the
shared one. Marker metadata shapes are those the hosts write.
"""
from __future__ import annotations

import json
import logging

import pytest

from ayon_editorial.otio import markers
from ayon_editorial.otio.compat import find_clips

otio = pytest.importorskip("opentimelineio")
pytestmark = pytest.mark.otio

HOST_MARKER_NAME = "AYONData"  # ayon_flame.api.MARKER_NAME


# --- Flame, ayon_flame/otio/utils.py (`find_clips()` goes through compat)
def flame_get_marker_from_clip_index(otio_timeline, clip_index):
    for otio_clip in find_clips(otio_timeline):
        for marker in otio_clip.markers:
            if HOST_MARKER_NAME not in marker.name:
                continue

            if marker.metadata.get("clip_index") == clip_index:
                return otio_clip, marker

    return None, None


# --- Hiero, ayon_hiero/api/otio/utils.py
def hiero_get_marker_from_clip_index(otio_timeline, clip_index):
    all_clips = find_clips(otio_timeline)

    for otio_clip in all_clips:
        for marker in otio_clip.markers:

            try:
                json_metadata = marker.metadata["json_metadata"]
            except KeyError:
                continue

            else:
                metadata = json.loads(json_metadata)
                if metadata.get("clip_index") == clip_index:
                    return otio_clip, marker

    return None, None


# --- Resolve, ayon_resolve/otio/utils.py (the unwrap stays in Resolve)
def unwrap_resolve_otio_marker(marker):
    try:
        marker_note = marker.metadata["Resolve_OTIO"]["Note"]
    except KeyError:
        return marker
    try:
        marker_note_dict = json.loads(marker_note)
    except json.decoder.JSONDecodeError:
        return marker
    marker.metadata.update(marker_note_dict)
    return marker


def resolve_get_marker_from_clip_index(otio_timeline, clip_index):
    all_clips = find_clips(otio_timeline)

    for otio_clip in all_clips:
        for marker in otio_clip.markers:
            marker = unwrap_resolve_otio_marker(marker)
            if marker.metadata.get("clip_index") == clip_index:
                return otio_clip, marker

    return None, None


def _timeline(*clips):
    """Timeline with one track; `clips` are `(name, [markers])`."""
    timeline = otio.schema.Timeline()
    track = otio.schema.Track()
    for name, clip_markers in clips:
        clip = otio.schema.Clip(name=name)
        clip.markers.extend(clip_markers)
        track.append(clip)
    timeline.tracks.append(track)
    return timeline


def _marker(name, metadata):
    return otio.schema.Marker(name=name, metadata=metadata)


def _hiero_timeline():
    return _timeline(
        ("a", [_marker("Tag", {"hiero_source_type": "TrackItem"})]),
        ("b", [_marker("AYONData", {
            "json_metadata": json.dumps({"clip_index": "id-b", "k": 1})})]),
    )


def _flame_timeline():
    return _timeline(
        ("a", [_marker("Other", {"clip_index": "id-b"})]),
        ("b", [_marker("AYONData", {"clip_index": "id-b", "k": 1})]),
    )


def _resolve_timeline():
    return _timeline(
        ("a", [_marker("Red", {"note": "hello"})]),
        ("b", [_marker("AYONData", {"clip_index": "id-b", "k": 1})]),
        ("c", [_marker("AYONData", {"Resolve_OTIO": {
            "Note": json.dumps({"clip_index": "id-c"})}})]),
    )


def test_find_clip_by_index_hiero_variant():
    tl = _hiero_timeline()
    clip, marker = markers.find_clip_by_index(tl, "id-b")
    expected_clip, expected_marker = hiero_get_marker_from_clip_index(
        tl, "id-b")
    assert clip.name == expected_clip.name == "b"
    assert marker.name == expected_marker.name
    assert markers.find_clip_by_index(tl, "missing") == (None, None)
    assert hiero_get_marker_from_clip_index(tl, "missing") == (None, None)


def test_find_clip_by_index_flame_variant():
    tl = _flame_timeline()
    clip, marker = markers.find_clip_by_index(
        tl, "id-b", marker_name=markers.MARKER_NAME)
    expected_clip, _ = flame_get_marker_from_clip_index(tl, "id-b")
    assert clip.name == expected_clip.name == "b"
    assert marker.name == "AYONData"
    # without the name filter the marker of clip "a" matches first
    clip, _ = markers.find_clip_by_index(tl, "id-b")
    assert clip.name == "a"


def test_find_clip_by_index_resolve_variant():
    tl = _resolve_timeline()
    for index, name in (("id-b", "b"), ("id-c", "c")):
        clip, marker = markers.find_clip_by_index(
            tl, index, unwrap=unwrap_resolve_otio_marker)
        expected_clip, _ = resolve_get_marker_from_clip_index(tl, index)
        assert clip.name == expected_clip.name == name
        assert marker.metadata["clip_index"] == index


def test_find_clip_by_index_resolve_wrapped_needs_unwrap():
    tl = _resolve_timeline()
    assert markers.find_clip_by_index(tl, "id-c") == (None, None)


def test_find_clip_by_index_survives_broken_json():
    """Deliberate difference: Hiero raises, the shared lookup skips."""
    tl = _timeline(
        ("a", [_marker("AYONData", {"json_metadata": "{not json"})]),
        ("b", [_marker("AYONData", {
            "json_metadata": json.dumps({"clip_index": "id-b"})})]),
    )
    with pytest.raises(json.JSONDecodeError):
        hiero_get_marker_from_clip_index(tl, "id-b")
    clip, _ = markers.find_clip_by_index(tl, "id-b")
    assert clip.name == "b"


def test_find_clip_by_index_compares_as_is():
    tl = _timeline(("a", [_marker("AYONData", {"clip_index": 3})]))
    assert markers.find_clip_by_index(tl, 3)[0].name == "a"
    assert markers.find_clip_by_index(tl, "3") == (None, None)


def test_find_clip_by_index_empty_timeline():
    assert markers.find_clip_by_index(
        otio.schema.Timeline(), "x") == (None, None)


@pytest.mark.parametrize("flat", [False, True])
def test_create_ayon_marker_round_trip(flat):
    data = {"clip_index": "abc", "folderPath": "/shots/sh010", "n": 3}
    marker = markers.create_ayon_marker(data, flat=flat)
    assert marker.name == "AYONData"
    assert markers.decode_marker_data(marker.metadata) == data
    tl = _timeline(("a", [marker]))
    assert markers.find_clip_by_index(tl, "abc")[0].name == "a"


def test_create_ayon_marker_json_shape_is_the_hiero_contract():
    marker = markers.create_ayon_marker({"clip_index": "abc"})
    assert list(marker.metadata.keys()) == ["json_metadata"]
    assert json.loads(marker.metadata["json_metadata"]) == {
        "clip_index": "abc"}


def test_create_ayon_marker_survives_otio_file(tmp_path):
    marker = markers.create_ayon_marker(
        {"clip_index": "abc"},
        marked_range=otio.opentime.TimeRange(
            otio.opentime.RationalTime(10, 24),
            otio.opentime.RationalTime(1, 24)),
        color=otio.schema.MarkerColor.RED,
    )
    tl = _timeline(("a", [marker]))
    path = str(tmp_path / "t.otio")
    otio.adapters.write_to_file(tl, path)
    loaded = otio.adapters.read_from_file(path)
    clip, found = markers.find_clip_by_index(loaded, "abc")
    assert clip.name == "a"
    assert found.color == "RED"
    assert found.marked_range.start_time.value == 10


def test_decode_marker_data_cases():
    assert markers.decode_marker_data(None) is None
    assert markers.decode_marker_data({}) is None
    assert markers.decode_marker_data({"a": 1}) == {"a": 1}
    assert markers.decode_marker_data(
        {"json_metadata": '{"a": 1}', "other": 2}) == {"a": 1}
    assert markers.decode_marker_data({"json_metadata": "[1]"}) is None
    assert markers.decode_marker_data({"json_metadata": None}) is None


def test_decode_marker_data_logs_invalid_json(caplog):
    with caplog.at_level(logging.WARNING):
        assert markers.decode_marker_data({"json_metadata": "{x"}) is None
    assert "not valid JSON" in caplog.text


@pytest.mark.parametrize(
    "text, key, expected",
    [
        ('{"clip_index": "a", "x": 1}', "comment",
         {"clip_index": "a", "x": 1}),
        ("just a note", "comment", {"comment": "just a note"}),
        ("just a note", "note", {"note": "just a note"}),
        ("", "comment", {"comment": ""}),
        (None, "note", {"note": ""}),
        ("[1, 2]", "comment", {"comment": "[1, 2]"}),
        ("{broken: }", "comment", {}),
    ],
)
def test_parse_marker_text(text, key, expected):
    assert markers.parse_marker_text(text, key) == expected


def test_parse_marker_text_flame_variant_json_detection():
    """Flame needs 3 of `{`, `:`, `}`; a JSON object always has them."""
    text = json.dumps({"clip_index": "a"})
    assert markers.parse_marker_text(text) == {"clip_index": "a"}


def test_is_ayon_marker():
    assert markers.is_ayon_marker(otio.schema.Marker(name="AYONData"))
    assert markers.is_ayon_marker(otio.schema.Marker(name="AYONData 2"))
    assert not markers.is_ayon_marker(otio.schema.Marker(name="Red"))
    assert not markers.is_ayon_marker(otio.schema.Marker())


def test_find_clips_is_used_for_nested_clips():
    inner = otio.schema.Track()
    clip = otio.schema.Clip(name="deep")
    clip.markers.append(markers.create_ayon_marker({"clip_index": "d"}))
    inner.append(clip)
    stack = otio.schema.Stack()
    stack.append(inner)
    tl = otio.schema.Timeline()
    tl.tracks.append(otio.schema.Track())
    tl.tracks[0].append(stack)
    assert [c.name for c in find_clips(tl)] == ["deep"]
    assert markers.find_clip_by_index(tl, "d")[0].name == "deep"
