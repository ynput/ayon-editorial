"""Smoke tests of the Flame reference exporter.

`tests/resources/host_exports/flame_reference.py` is the host export code
run without Flame. This checks that it runs on `flame_input.json`, that the
timeline has the structure the input was built for, and that it survives a
write/read round trip.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from ayon_editorial.otio.compat import find_clips

otio = pytest.importorskip("opentimelineio")
pytestmark = pytest.mark.otio

HOST_EXPORTS = Path(__file__).resolve().parent / "resources" / "host_exports"


def _load_reference():
    spec = importlib.util.spec_from_file_location(
        "flame_reference", HOST_EXPORTS / "flame_reference.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def timeline():
    data = json.loads((HOST_EXPORTS / "flame_input.json").read_text())
    return _load_reference().export(data)


def _items(track):
    return list(track)


def _clips(track):
    return {c.name: c for c in track if isinstance(c, otio.schema.Clip)}


def _gaps(track):
    return [
        g.source_range.duration.value
        for g in track
        if isinstance(g, otio.schema.Gap)
    ]


def test_flame_reference_tracks(timeline):
    tracks = list(timeline.tracks)
    assert [(t.name, t.kind) for t in tracks] == [
        ("V1", "Video"),
        ("V2", "Video"),
        ("A1", "Audio"),
        ("unnamed", "Audio"),
    ]


def test_flame_reference_timeline(timeline):
    assert timeline.global_start_time == otio.opentime.RationalTime(86400, 24)
    assert timeline.metadata["ayon.timeline.width"] == 1920
    assert timeline.metadata["ayon.flame.working_space"] == "ACEScg"


def test_flame_reference_clip_names(timeline):
    v1, v2 = timeline.tracks[0], timeline.tracks[1]
    assert [c.name for c in v1 if isinstance(c, otio.schema.Clip)] == [
        "sh010_seq",
        "sh020_2398",
        "sh030_25on24",
        "sh040_overlap",
        "Missing: Segment's File Path",
    ]
    assert list(_clips(v2)) == [
        "sh060_reverse",
        "sh070_half",
        "sh080_freeze",
        "sh090_const_tw",
        "sh100_curve_tw",
    ]


def test_flame_reference_gaps(timeline):
    v1, v2 = timeline.tracks[0], timeline.tracks[1]
    # start gap is record_in as is (prev_out == 0 quirk: no -1), middle gap
    # is record_in - prev_out - 1, the overlap gives a negative gap
    assert _gaps(v1) == [10, 12, -4]
    assert isinstance(_items(v1)[0], otio.schema.Gap)
    assert _gaps(v2) == []
    # adjacent clips get no gap
    assert [type(i).__name__ for i in v1][1:3] == ["Clip", "Clip"]
    assert _gaps(timeline.tracks[3]) == [10]


def test_flame_reference_source_ranges(timeline):
    clips = _clips(timeline.tracks[0])
    seq = clips["sh010_seq"]
    assert seq.source_range == otio.opentime.TimeRange(
        otio.opentime.RationalTime(1001, 24),
        otio.opentime.RationalTime(24, 24),
    )
    # 23.976 media on a 24 timeline: (1000 + 100) at 23.976 rescaled to 24
    start = clips["sh020_2398"].source_range.start_time
    assert start.rate == 24
    assert start.value == pytest.approx(1100 / 23.976 * 24)
    assert (
        clips["sh020_2398"].media_reference.available_range.start_time.rate
        == 23.976
    )
    # 25 media on a 24 timeline: (500 + 10) / 25 * 24
    start = clips["sh030_25on24"].source_range.start_time
    assert start.value == pytest.approx(489.6)
    assert start.rate == 24
    assert clips["sh030_25on24"].source_range.duration.value == 24


def test_flame_reference_references(timeline):
    clips = _clips(timeline.tracks[0])
    seq_ref = clips["sh010_seq"].media_reference
    assert isinstance(seq_ref, otio.schema.ImageSequenceReference)
    assert seq_ref.name_prefix == "shot0010_v0010_"
    assert seq_ref.name_suffix == ".exr"
    assert seq_ref.start_frame == 1001
    assert seq_ref.frame_zero_padding == 4
    assert seq_ref.metadata["isSequence"] is True
    assert seq_ref.metadata["padding"] == 4
    movie_ref = clips["sh020_2398"].media_reference
    assert isinstance(movie_ref, otio.schema.ExternalReference)
    assert movie_ref.target_url.endswith("sh020/plate.mov")
    assert movie_ref.metadata["ayon.source.width"] == 1920
    missing = clips["Missing: Segment's File Path"].media_reference
    assert isinstance(missing, otio.schema.MissingReference)
    # audio has no image size metadata
    mix = _clips(timeline.tracks[2])["mix"].media_reference
    assert "ayon.source.width" not in mix.metadata


def test_flame_reference_effects(timeline):
    clips = _clips(timeline.tracks[1])

    def effects(name):
        return list(clips[name].effects)

    (reverse,) = effects("sh060_reverse")
    assert isinstance(reverse, otio.schema.LinearTimeWarp)
    assert reverse.time_scalar == -1
    (half,) = effects("sh070_half")
    assert half.time_scalar == 0.5
    (freeze,) = effects("sh080_freeze")
    assert isinstance(freeze, otio.schema.FreezeFrame)
    (const,) = effects("sh090_const_tw")
    assert const.time_scalar == 2.0
    (curve,) = effects("sh100_curve_tw")
    assert curve.effect_name == "TimeWarp"
    assert list(curve.metadata["lookup"]) == [-10, -10, -9, -9, -8, -8]
    # no effect on a clip at speed 1
    assert not list(_clips(timeline.tracks[0])["sh010_seq"].effects)


def test_flame_reference_markers(timeline):
    clip = _clips(timeline.tracks[0])["sh030_25on24"]
    json_marker, text_marker = clip.markers
    assert json_marker.name == "AYONData"
    assert json_marker.color == otio.schema.MarkerColor.RED
    assert json_marker.metadata["clip_index"] == "abc123"
    assert "comment" not in json_marker.metadata
    # start is relative to the segment record_in, plus one
    assert json_marker.marked_range.start_time.value == 11
    assert text_marker.metadata["comment"] == "check the grade"
    # colour is clamped to the closest half number
    assert text_marker.color == otio.schema.MarkerColor.ORANGE


def test_flame_reference_skips_hidden_and_empty(timeline):
    names = {t.name for t in timeline.tracks}
    assert names.isdisjoint({"hidden", "empty", "A3"})
    all_clips = {c.name for c in find_clips(timeline)}
    assert not {"skipped", "hidden"} & all_clips


def test_flame_reference_round_trip(timeline):
    text = otio.adapters.write_to_string(timeline, "otio_json")
    back = otio.adapters.read_from_string(text, "otio_json")
    assert otio.adapters.write_to_string(back, "otio_json") == text
    assert [t.name for t in back.tracks] == [t.name for t in timeline.tracks]
