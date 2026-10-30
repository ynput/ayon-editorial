"""Smoke tests for the Resolve reference exporter fixture."""

import importlib.util
import json
from pathlib import Path

import pytest

otio = pytest.importorskip("opentimelineio")
pytest.importorskip("clique")

pytestmark = pytest.mark.otio

# OTIO 0.18 rejects timecode at the rounded 23.976 (the host would too)
_RATE_23976 = 24000 / 1001
# OTIO 0.18 rejects timecode at the rounded 23.976 (the host would too)
_RATE_23976 = 24000 / 1001
_RESOURCES = Path(__file__).parent / "resources" / "host_exports"


def _load_reference():
    spec = importlib.util.spec_from_file_location(
        "resolve_reference", _RESOURCES / "resolve_reference.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def timeline():
    data = json.loads((_RESOURCES / "resolve_input.json").read_text())
    return _load_reference().export(data)


def _items(track):
    return [(type(c).__name__, c.name) for c in track]


def test_tracks(timeline):
    assert [(t.kind, t.name) for t in timeline.tracks] == [
        ("Video", "Video 1"),
        ("Video", "Video 2"),
        ("Audio", "Audio 1"),
        ("Audio", "Audio 1"),
        ("Audio", "Audio 2"),
    ]
    assert timeline.name == "ref_timeline"
    assert timeline.global_start_time.value == 86400
    assert timeline.global_start_time.rate == 24
    assert timeline.metadata["width"] == 1920
    assert timeline.metadata["pixelAspect"] == 1.0


def test_video_clips_and_gaps(timeline):
    v1 = timeline.tracks[0]
    # the offline item is skipped, start and middle gaps are inserted
    assert _items(v1) == [
        ("Gap", ""),
        ("Clip", "sh010"),
        ("Clip", "sh020"),
        ("Gap", ""),
        ("Clip", "sh030"),
    ]
    assert v1[0].source_range.duration.value == 24
    assert v1[3].source_range.duration.value == 12
    # overlap: no gap, the clip is simply appended
    v2 = timeline.tracks[1]
    assert _items(v2) == [("Clip", "sh040"), ("Clip", "sh050")]


def test_source_ranges(timeline):
    v1, v2 = timeline.tracks[0], timeline.tracks[1]
    start = otio.opentime.from_timecode("01:00:00:00", _RATE_23976)
    # 23.976 media on a 24 timeline: conform the start, then add the offset
    r = v1[1].source_range
    assert r.start_time.rate == 24
    assert r.start_time.value == pytest.approx(
        start.value_rescaled_to(24) + 10
    )
    assert r.duration.value == 48
    # 25 media on a 24 timeline
    start = otio.opentime.from_timecode("00:00:04:00", 25)
    r = v1[2].source_range
    assert r.start_time.value == pytest.approx(start.value_rescaled_to(24) + 5)
    # same rate
    assert v1[4].source_range.start_time.value == 86400
    assert v2[1].source_range.start_time.value == pytest.approx(2)


def test_references(timeline):
    v1 = timeline.tracks[0]
    movie = v1[1].media_reference
    assert isinstance(movie, otio.schema.ExternalReference)
    assert movie.target_url == "/tmp/ref/sh010.mov"
    assert movie.available_range.duration.value == 200
    assert movie.available_range.duration.rate == pytest.approx(_RATE_23976)
    assert movie.metadata["Shot"] == "sh010"
    assert "isSequence" not in movie.metadata

    seq = v1[2].media_reference
    if hasattr(otio.schema, "ImageSequenceReference"):
        assert isinstance(seq, otio.schema.ImageSequenceReference)
        assert seq.target_url_base == "/tmp/ref/sh020/"
        assert seq.name_prefix == "shot0020_v0010."
        assert seq.name_suffix == ".exr"
        assert seq.start_frame == 1
        assert seq.frame_zero_padding == 4
    assert seq.metadata["isSequence"] is True
    assert seq.metadata["padding"] == 4
    assert seq.available_range.duration.value == 100


def test_markers(timeline):
    markers = timeline.tracks[0][1].markers
    assert [m.name for m in markers] == ["ayon marker", "plain"]
    assert markers[0].color == "BLUE"
    assert markers[0].metadata["productType"] == "plate"
    assert markers[0].marked_range.duration.value == 1
    assert markers[1].color == "SKY"
    assert markers[1].metadata == {"note": "just a note"}
    # marker start is relative to the available start of the media
    start = otio.opentime.from_timecode("01:00:00:00", _RATE_23976)
    assert markers[0].marked_range.start_time.value == pytest.approx(
        start.value_rescaled_to(24) + 5
    )
    assert markers[0].marked_range.start_time.rate == 24


def test_audio_channels(timeline):
    a1, a1_split, a2 = list(timeline.tracks)[2:]
    assert _items(a1) == [("Gap", ""), ("Clip", "dialog_0")]
    assert _items(a1_split) == [("Gap", ""), ("Clip", "dialog_1")]
    assert a1[0].source_range.duration.value == 48
    assert a1[1].source_range.duration.value == 72
    # the audio Duration timecode (00:00:04:00 at 24) gives 96 frames
    ref = a1[1].media_reference
    assert ref.available_range.duration.value == 96
    assert [m.name for m in a1[1].markers] == ["cue"]
    assert _items(a2) == [("Clip", "music_0")]
    assert a2[0].media_reference.available_range.duration.value == 192


def test_round_trip(timeline):
    text = otio.adapters.write_to_string(timeline, "otio_json")
    again = otio.adapters.read_from_string(text, "otio_json")
    assert len(again.tracks) == len(timeline.tracks)
    assert otio.adapters.write_to_string(again, "otio_json") == text
