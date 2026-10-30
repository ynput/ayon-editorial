"""Smoke tests of the Hiero reference exporter fixture.

The reference is the host export code run on a plain input dict, so the
structure of its result is what the builder is compared against later.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

otio = pytest.importorskip("opentimelineio")
pytestmark = pytest.mark.otio

RESOURCES = Path(__file__).parent / "resources" / "host_exports"


def _load_reference():
    spec = importlib.util.spec_from_file_location(
        "hiero_reference", RESOURCES / "hiero_reference.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def timeline():
    data = json.loads((RESOURCES / "hiero_input.json").read_text())
    return _load_reference().export(data)


def _by_name(track):
    return {child.name: child for child in track if child.name}


def _gaps(track):
    return [
        child.source_range.duration.value
        for child in track
        if isinstance(child, otio.schema.Gap)
    ]


def test_tracks(timeline):
    tracks = list(timeline.tracks)
    assert [t.name for t in tracks] == ["Video 1", "Video 2", "Audio 1"]
    assert [t.kind for t in tracks] == [
        otio.schema.TrackKind.Video,
        otio.schema.TrackKind.Video,
        otio.schema.TrackKind.Audio,
    ]
    assert timeline.global_start_time == otio.opentime.RationalTime(86400, 24)


def test_clips_and_gaps(timeline):
    video, video2, _audio = timeline.tracks
    names = [c.name for c in video if isinstance(c, otio.schema.Clip)]
    assert names == [
        "sh010",
        "sh020",
        "sh030",
        "sh040",
        "sh050",
        "sh060",
        "sh070",
    ]
    # start gap, adjacent (none), middle gap, overlap, adjacent x2, gap
    assert _gaps(video) == [10, 12, -4, 8]
    # prev_out == 0 keeps the whole difference (no -1)
    assert _gaps(video2) == [5]


def test_source_ranges(timeline):
    video, video2, _audio = timeline.tracks
    clips = _by_name(video)
    # 23.976 media on a 24 timeline: rate of the clip is the rounded one
    sh010 = clips["sh010"].source_range
    assert sh010.duration == otio.opentime.RationalTime(24, 23.976)
    assert sh010.start_time.rate == 23.976
    assert sh010.start_time.value == pytest.approx(
        otio.opentime.RationalTime(86400 + 5, 23.976).value
    )
    sh020 = clips["sh020"].source_range
    assert sh020.start_time == otio.opentime.RationalTime(1001 + 12, 25)
    assert sh020.duration == otio.opentime.RationalTime(24, 25)
    sh030 = clips["sh030"].source_range
    assert sh030.start_time == otio.opentime.RationalTime(20, 24)
    # reverse takes sourceOut, freeze too
    assert clips["sh040"].source_range.start_time.value == 63
    assert clips["sh050"].source_range.start_time.value == pytest.approx(
        10, abs=0.1
    )


def test_references(timeline):
    clips = _by_name(timeline.tracks[0])
    ref = clips["sh020"].media_reference
    assert isinstance(ref, otio.schema.ImageSequenceReference)
    assert ref.name_prefix == "shot0020_v0010."
    assert ref.frame_zero_padding == 4
    assert ref.metadata["isSequence"] is True
    movie = clips["sh010"].media_reference
    assert isinstance(movie, otio.schema.ExternalReference)
    assert movie.target_url.endswith("sh010.mov")
    assert movie.metadata["ayon.source.width"] == 1920


def test_effects(timeline):
    video, _video2, audio = timeline.tracks
    clips = _by_name(video)

    def effects(name):
        return [(type(e).__name__, e.name) for e in clips[name].effects]

    assert effects("sh010") == []
    assert effects("sh030") == [
        ("LinearTimeWarp", "Speed"),
        ("TimeEffect", "tw_free"),
    ]
    assert effects("sh040") == [("LinearTimeWarp", "Speed")]
    assert effects("sh050") == [("FreezeFrame", "FreezeFrame")]
    assert effects("sh060") == [("TimeEffect", "tw_anim")]
    assert effects("sh070") == [("TimeEffect", "tw_const")]
    animated = clips["sh060"].effects[0].metadata
    assert len(animated["lookup"]) == 24
    assert len(animated["length"]) == 24
    assert clips["sh070"].effects[0].metadata["lookup"] == 2.5
    assert clips["sh070"].effects[0].effect_name == "TimeWarp"
    # media with audio gets no effects at all
    assert len(audio[0].effects) == 0


def test_markers(timeline):
    video, video2, _audio = timeline.tracks
    clips = _by_name(video)
    # track item tag; `Copy` and invisible tags are skipped
    (marker,) = clips["sh010"].markers
    assert marker.name == "AYONData"
    assert marker.color == otio.schema.MarkerColor.MAGENTA
    assert marker.marked_range.duration.value == 24
    assert marker.metadata["hiero_source_type"] == "TrackItem"
    assert json.loads(marker.metadata["json_metadata"])["productType"]
    # source clip tag
    (source_marker,) = clips["sh020"].markers
    assert source_marker.metadata["hiero_source_type"] == "Clip"
    assert source_marker.marked_range.start_time.rate == 25.0
    # track tag
    (track_marker,) = video.markers
    assert track_marker.metadata["hiero_source_type"] == "VideoTrack"
    assert track_marker.marked_range.start_time.rate == 24.0
    assert len(video2.markers) == 0


def test_round_trip(timeline):
    text = otio.adapters.write_to_string(timeline, "otio_json")
    again = otio.adapters.read_from_string(text, "otio_json")
    assert [t.name for t in again.tracks] == [t.name for t in timeline.tracks]
    for left, right in zip(timeline.tracks, again.tracks):
        assert [c.name for c in left] == [c.name for c in right]
        assert [len(c.effects) for c in left] == [
            len(c.effects) for c in right
        ]
        assert [len(c.markers) for c in left] == [
            len(c.markers) for c in right
        ]
        for a, b in zip(left, right):
            assert a.source_range.start_time.value == pytest.approx(
                b.source_range.start_time.value
            )
