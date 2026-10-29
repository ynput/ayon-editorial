"""Tests of `otio/builder.py`: specs in, OTIO timeline out."""
from __future__ import annotations

import logging

import pytest

from ayon_editorial.otio import builder, compat
from ayon_editorial.otio.builder import (
    GAP_NONE,
    GAP_RECORD,
    GAP_TRACK_END,
    ClipSpec,
    MarkerSpec,
    MediaSpec,
    SequenceSpec,
    SpeedEffectSpec,
    TimelineBuilder,
    TimeWarpEffectSpec,
)

otio = pytest.importorskip("opentimelineio")
pytestmark = pytest.mark.otio

RT = otio.opentime.RationalTime


def _media(rate=24.0, start=100.0, duration=50.0, **kwargs):
    return MediaSpec(
        target_url="/m/a.mov",
        available_start=start,
        available_duration=duration,
        rate=rate,
        **kwargs,
    )


def _sequence():
    return SequenceSpec(
        target_url_base="/m/seq/",
        name_prefix="a.",
        name_suffix=".exr",
        start_frame=1001,
        padding=4,
    )


def _clip(name="c", record_in=None, record_out=None, **kwargs):
    kwargs.setdefault("source_offset", 17)
    kwargs.setdefault("duration", 10)
    return ClipSpec(
        name=name, record_in=record_in, record_out=record_out, **kwargs
    )


def _children(track):
    return list(track)


@pytest.mark.parametrize("media_rate", [23.976, 24.0, 25.0])
@pytest.mark.parametrize("clip_rate", [23.976, 24.0, 25.0])
def test_conform_formulas(media_rate, clip_rate):
    media = _media(rate=media_rate, start=3600.0)
    start = RT(3600.0, media_rate)
    expected_host = (start + RT(17.0, media_rate)).rescaled_to(
        clip_rate
    ).value
    expected_resolve = start.value_rescaled_to(clip_rate) + 17.0

    for at_clip_rate, expected in (
        (False, expected_host),
        (True, expected_resolve),
    ):
        spec = _clip(
            media=media, rate=clip_rate, offset_at_clip_rate=at_clip_rate
        )
        clip = builder.create_clip(spec, 12.0)
        source = clip.source_range
        assert source.start_time.value == expected
        assert source.start_time.rate == clip_rate
        assert source.duration == RT(10.0, clip_rate)


def test_conform_formulas_differ_for_mixed_rates():
    media = _media(rate=23.976, start=3600.0)
    host = builder.create_clip(_clip(media=media, rate=24.0), 24.0)
    resolve = builder.create_clip(
        _clip(media=media, rate=24.0, offset_at_clip_rate=True), 24.0
    )
    assert host.source_range.start_time != resolve.source_range.start_time


def test_conform_without_media_uses_clip_rate():
    clip = builder.create_clip(_clip(), 25.0)
    assert clip.source_range.start_time == RT(17.0, 25.0)


def test_clip_rate_defaults_to_timeline_rate():
    clip = builder.create_clip(_clip(media=_media(rate=25.0)), 24.0)
    assert clip.source_range.duration.rate == 24.0


def test_missing_reference():
    clip = builder.create_clip(_clip(name="gone"), 24.0)
    ref = clip.media_reference
    assert isinstance(ref, otio.schema.MissingReference)
    assert ref.name == "gone"
    assert ref.available_range is None
    assert not ref.metadata


def test_external_reference_and_metadata():
    media = _media(metadata={"ayon.source.width": 1920})
    ref = builder.create_media_reference(media, "c")
    assert isinstance(ref, otio.schema.ExternalReference)
    assert ref.target_url == "/m/a.mov"
    assert ref.available_range == otio.opentime.TimeRange(
        RT(100.0, 24.0), RT(50.0, 24.0)
    )
    assert ref.metadata["ayon.source.width"] == 1920
    assert "isSequence" not in ref.metadata


def test_media_rate_is_not_rounded():
    ref = builder.create_media_reference(_media(rate=24000 / 1001), "c")
    assert ref.available_range.start_time.rate == 24000 / 1001


def test_image_sequence_reference():
    media = _media(
        sequence=_sequence(), metadata={"padding": 1, "keep": "yes"}
    )
    ref = builder.create_media_reference(media, "c")
    assert isinstance(ref, otio.schema.ImageSequenceReference)
    assert ref.target_url_base == "/m/seq/"
    assert ref.name_prefix == "a."
    assert ref.name_suffix == ".exr"
    assert ref.start_frame == 1001
    assert ref.frame_zero_padding == 4
    assert ref.rate == 24.0
    assert ref.metadata["isSequence"] is True
    assert ref.metadata["padding"] == 4  # builder keys win
    assert ref.metadata["keep"] == "yes"


@pytest.mark.parametrize(
    "padded, url",
    [(False, "/m/seq/a.%d.exr"), (True, "/m/seq/a.%04d.exr")],
)
def test_image_sequence_fallback(monkeypatch, padded, url):
    monkeypatch.setattr(
        compat, "has_image_sequence_reference", lambda: False
    )
    media = _media(sequence=_sequence())
    ref = builder.create_media_reference(media, "c", padded)
    assert isinstance(ref, otio.schema.ExternalReference)
    assert ref.target_url == url
    assert ref.available_range.start_time == RT(100.0, 24.0)
    assert ref.metadata["isSequence"] is True
    assert ref.metadata["padding"] == 4


def test_marker_defaults_to_owner_rate():
    spec = MarkerSpec("m", 5, 2, "RED", metadata={"k": 1})
    marker = builder.create_marker(spec, 25.0)
    assert marker.name == "m"
    assert marker.color == "RED"
    assert marker.marked_range == otio.opentime.TimeRange(
        RT(5.0, 25.0), RT(2.0, 25.0)
    )
    assert marker.metadata["k"] == 1


def test_marker_spec_rate_wins():
    spec = MarkerSpec("m", 5, 2, "RED", rate=23.976)
    marker = builder.create_marker(spec, 25.0)
    assert marker.marked_range.start_time == RT(5.0, 23.976)


def test_marker_relative_to_available_start():
    spec = MarkerSpec(
        "m", 5, 1, "RED", relative_to_available_start=True
    )
    clip = builder.create_clip(
        _clip(media=_media(rate=25.0, start=100.0), markers=[spec]), 24.0
    )
    expected = 5 + RT(100.0, 25.0).value_rescaled_to(24.0)
    assert clip.markers[0].marked_range.start_time == RT(expected, 24.0)


def test_marker_relative_without_media_is_unchanged():
    spec = MarkerSpec(
        "m", 5, 1, "RED", relative_to_available_start=True
    )
    clip = builder.create_clip(_clip(markers=[spec]), 24.0)
    assert clip.markers[0].marked_range.start_time == RT(5.0, 24.0)


def test_effects_in_spec_order_and_unit_speed_is_noop():
    effects = [
        SpeedEffectSpec(0.5),
        TimeWarpEffectSpec([1.0, 2.0], name="tw", metadata={"length": 2}),
        SpeedEffectSpec(1.0),
        TimeWarpEffectSpec(3, effect_name="Foo TimeWarp"),
    ]
    clip = builder.create_clip(_clip(effects=effects), 24.0)
    assert len(clip.effects) == 3
    speed, warp, number = clip.effects
    assert isinstance(speed, otio.schema.LinearTimeWarp)
    assert speed.time_scalar == 0.5
    assert warp.name == "tw"
    assert list(warp.metadata["lookup"]) == [1.0, 2.0]
    assert warp.metadata["length"] == 2
    assert number.metadata["lookup"] == 3
    assert number.effect_name == "Foo TimeWarp"


def test_freeze_effect():
    clip = builder.create_clip(_clip(effects=[SpeedEffectSpec(0.0)]), 24.0)
    assert isinstance(clip.effects[0], otio.schema.FreezeFrame)


def test_clip_metadata():
    clip = builder.create_clip(_clip(metadata={"a": 1}), 24.0)
    assert clip.metadata["a"] == 1


def test_timeline_header_and_track_order():
    tb = TimelineBuilder(
        "tl", 25.0, start_frame=90000, metadata={"x": 1}
    )
    tb.add_track("V1")
    tb.add_track("A1", kind="Audio")
    timeline = tb.build()
    assert timeline is tb.timeline
    assert timeline.name == "tl"
    assert timeline.global_start_time == RT(90000.0, 25.0)
    assert timeline.metadata["x"] == 1
    assert [t.name for t in timeline.tracks] == ["V1", "A1"]
    assert [t.kind for t in timeline.tracks] == ["Video", "Audio"]


def test_track_markers():
    tb = TimelineBuilder("tl", 25.0)
    track = tb.add_track("V1", markers=[MarkerSpec("t", 3, 1, "BLUE")])
    marker = track.track.markers[0]
    assert marker.marked_range.start_time == RT(3.0, 25.0)


def _record_track(*ranges):
    tb = TimelineBuilder("tl", 24.0)
    track = tb.add_track("V1")
    for i, (rec_in, rec_out) in enumerate(ranges):
        track.append_clip(_clip(f"c{i}", rec_in, rec_out, duration=5))
    return track.track


def _gaps(track):
    return [
        child.source_range.duration.value
        for child in track
        if isinstance(child, otio.schema.Gap)
    ]


def test_record_gap_start_and_middle():
    track = _record_track((10, 14), (30, 34))
    kinds = [type(c).__name__ for c in track]
    assert kinds == ["Gap", "Clip", "Gap", "Clip"]
    assert _gaps(track) == [10.0, 15.0]  # 30 - 14 - 1


def test_record_gap_none_at_zero_and_adjacent():
    track = _record_track((0, 4), (5, 9))
    assert [type(c).__name__ for c in track] == ["Clip", "Clip"]


def test_record_gap_prev_out_zero_quirk():
    track = _record_track((0, 0), (5, 9))
    assert _gaps(track) == [5.0]  # no minus 1 when prev_out == 0


def test_record_gap_overlap_is_kept(caplog):
    with caplog.at_level(logging.WARNING, logger=builder.__name__):
        track = _record_track((0, 9), (5, 14))
    assert _gaps(track) == [-5.0]
    assert "gap of -5" in caplog.text


def test_record_gap_start_rate():
    track = _record_track((10, 14))
    gap = _children(track)[0]
    assert gap.source_range.start_time.value == 0.0
    assert gap.source_range.duration == RT(10.0, 24.0)


def test_track_end_gap():
    tb = TimelineBuilder("tl", 24.0, gap_mode=GAP_TRACK_END)
    track = tb.add_track("V1")
    track.append_clip(_clip("a", record_in=10))
    track.append_clip(_clip("b", record_in=20))  # track ends at 20
    track.append_clip(_clip("c", record_in=40))
    kinds = [type(c).__name__ for c in track.track]
    assert kinds == ["Gap", "Clip", "Clip", "Gap", "Clip"]
    gaps = [
        c.source_range for c in track.track if isinstance(c, otio.schema.Gap)
    ]
    assert gaps[0] == otio.opentime.TimeRange(RT(0, 24.0), RT(10.0, 24.0))
    assert gaps[1].duration == RT(10.0, 24.0)
    assert gaps[1].start_time.rate == 24.0


def test_track_end_gap_uses_otio_duration_for_mixed_rates():
    tb = TimelineBuilder("tl", 24.0, gap_mode=GAP_TRACK_END)
    track = tb.add_track("V1")
    track.append_clip(
        _clip("a", record_in=0, rate=48.0, duration=48)
    )  # 24 frames at 24
    end = track.track.available_range().duration.value
    track.append_clip(_clip("b", record_in=60))
    assert _gaps(track.track) == [60 - end]


def test_gap_none_and_explicit_gap():
    tb = TimelineBuilder("tl", 24.0, gap_mode=GAP_NONE)
    track = tb.add_track("V1")
    track.append_clip(_clip("a"))  # no record frames needed
    gap = track.append_gap(7)
    assert gap.source_range.duration == RT(7.0, 24.0)
    assert [type(c).__name__ for c in track.track] == ["Clip", "Gap"]


@pytest.mark.parametrize(
    "mode, spec",
    [
        (GAP_RECORD, _clip("a", record_in=1)),
        (GAP_RECORD, _clip("a", record_out=1)),
        (GAP_TRACK_END, _clip("a")),
    ],
)
def test_missing_record_frames_raise(mode, spec):
    track = TimelineBuilder("tl", 24.0, gap_mode=mode).add_track("V1")
    with pytest.raises(ValueError, match="record_in"):
        track.append_clip(spec)
    assert len(track.track) == 0


def test_write_read_round_trip(tmp_path):
    tb = TimelineBuilder(
        "tl", 24.0, start_frame=86400, metadata={"pixelAspect": 1.0}
    )
    track = tb.add_track("V1")
    track.append_clip(
        _clip(
            "a",
            record_in=10,
            record_out=14,
            media=_media(rate=23.976, sequence=_sequence()),
            markers=[MarkerSpec("m", 2, 1, "RED", metadata={"k": "v"})],
            effects=[SpeedEffectSpec(0.5)],
        )
    )
    track.append_clip(_clip("b", record_in=20, record_out=24))
    path = str(tmp_path / "out.otio")
    tb.write_to_file(path)

    read = otio.adapters.read_from_file(path)
    assert otio.adapters.write_to_string(
        read
    ) == otio.adapters.write_to_string(tb.build())
    assert read.global_start_time == RT(86400.0, 24.0)
    clips = compat.find_clips(read)
    assert [c.name for c in clips] == ["a", "b"]
    assert isinstance(
        clips[0].media_reference, otio.schema.ImageSequenceReference
    )
    assert isinstance(clips[1].media_reference, otio.schema.MissingReference)


def test_write_to_file_function(tmp_path):
    path = str(tmp_path / "t.otio")
    builder.write_to_file(otio.schema.Timeline(name="x"), path)
    assert otio.adapters.read_from_file(path).name == "x"
