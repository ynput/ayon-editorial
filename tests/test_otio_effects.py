"""Characterization tests of `otio/effects.py`.

Fixtures in `tests/resources/ayon_core_retime/` are the retimed clips from
the ayon-core editorial tests (Apache 2.0, synthetic projects). The reader
of ayon-core and the host writers are reproduced here so the shared code
is compared with them.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

from ayon_editorial.otio import effects

otio = pytest.importorskip("opentimelineio")
pytestmark = pytest.mark.otio

FIXTURES = sorted(
    (Path(__file__).parent / "resources" / "ayon_core_retime").glob("*.json")
)


def _load(path):
    return otio.schema.Clip.from_json_file(str(path))


# --- ayon-core, ayon_core/pipeline/editorial.py get_media_range_with_retimes
def core_read_retime(otio_clip):
    time_scalar = 1.
    time_warp_nodes = []

    for effect in otio_clip.effects:
        if isinstance(effect, otio.schema.LinearTimeWarp):
            time_scalar = effect.time_scalar

        elif isinstance(effect, otio.schema.FreezeFrame):
            time_scalar = 0.

        elif isinstance(effect, otio.schema.TimeEffect):
            name = effect.name
            effect_name = effect.effect_name
            if "TimeWarp" not in effect_name:
                continue
            metadata = effect.metadata
            lookup = metadata.get("lookup")
            if not lookup:
                continue

            tw_node = {
                "Class": "TimeWarp",
                "name": name
            }
            tw_node.update(metadata)
            tw_node["lookup"] = list(lookup)

            time_warp_nodes.append(tw_node)
    return time_scalar, time_warp_nodes


# --- Hiero, ayon_hiero/api/otio/hiero_export.py create_time_effects
def hiero_speed_effects(otio_clip, speed):
    otio_effect = None
    if speed != 1.:
        otio_effect = otio.schema.LinearTimeWarp()
        otio_effect.name = "Speed"
        otio_effect.time_scalar = speed

    if speed == 0.:
        otio_effect = otio.schema.FreezeFrame()
        otio_effect.name = "FreezeFrame"

    if otio_effect:
        otio_clip.effects.append(otio_effect)


def hiero_timewarp_effect(name, host_name, metadata):
    if "_" in host_name:
        effect_name = re.sub(r"(?:_)[_0-9]+", "", host_name)
    else:
        effect_name = re.sub(r"\d+", "", host_name)
    otio_effect = otio.schema.TimeEffect()
    otio_effect.name = name
    otio_effect.effect_name = effect_name
    otio_effect.metadata.update(metadata)
    return otio_effect


# --- Flame, ayon_flame/otio/flame_export.py create_time_effects
def flame_speed_effects(otio_clip, speed):
    otio_effect = None
    if speed == 0.:
        otio_effect = otio.schema.FreezeFrame(
            name="FreezeFrame"
        )

    elif speed != 1:
        otio_effect = otio.schema.LinearTimeWarp(
            name="Speed",
            time_scalar=speed
        )

    if otio_effect:
        otio_clip.effects.append(otio_effect)


def flame_timewarp_effect(metadata):
    otio_effect = otio.schema.TimeEffect()
    otio_effect.effect_name = "TimeWarp"
    otio_effect.metadata.update(metadata)
    return otio_effect


def _effects_json(otio_clip):
    return [e.to_json_string() for e in otio_clip.effects]


def _bare_clip(clip):
    bare = copy.deepcopy(clip)
    bare.effects.clear()
    return bare


def test_fixtures_are_present():
    assert len(FIXTURES) == 14


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_get_retime_info_matches_core_reader(path):
    clip = _load(path)
    time_scalar, nodes = core_read_retime(clip)
    info = effects.get_retime_info(clip)
    assert info.time_scalar == time_scalar
    assert info.timewarps == nodes
    assert info.is_retimed


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_core_retime_fixture_round_trips(path):
    clip = _load(path)
    info = effects.get_retime_info(clip)

    rebuilt = _bare_clip(clip)
    effects.add_retime_effects(rebuilt, info)

    assert core_read_retime(rebuilt) == core_read_retime(clip)
    assert effects.get_retime_info(rebuilt) == info


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_core_retime_fixture_round_trips_through_file(path, tmp_path):
    clip = _load(path)
    rebuilt = _bare_clip(clip)
    effects.add_retime_effects(rebuilt, effects.get_retime_info(clip))
    target = tmp_path / "clip.json"
    rebuilt.to_json_file(str(target))
    assert core_read_retime(_load(target)) == core_read_retime(clip)


@pytest.mark.parametrize(
    "path",
    [p for p in FIXTURES
     if p.stem in {
         "img_seq_2x_speed", "img_seq_freeze_frame", "qt_freeze_frame",
         "img_seq_reverse_speed_0_7", "qt_reverse_speed_2x",
         "img_seq_2x_time_warp", "img_seq_multiple_tws", "qt_timewarp",
     }],
    ids=lambda p: p.stem,
)
def test_hiero_shaped_fixture_effects_are_identical(path):
    """Fixtures written by the Hiero exporter come back byte for byte."""
    clip = _load(path)
    rebuilt = _bare_clip(clip)
    effects.add_retime_effects(rebuilt, effects.get_retime_info(clip))
    assert _effects_json(rebuilt) == _effects_json(clip)


@pytest.mark.parametrize("speed", [1.0, 1, 0.0, 0, 2.0, 0.5, -1.0, -0.7, 2.5])
def test_speed_effects_hiero_variant(speed):
    expected = otio.schema.Clip()
    hiero_speed_effects(expected, speed)
    clip = otio.schema.Clip()
    effects.add_speed_effect(clip, speed)
    assert _effects_json(clip) == _effects_json(expected)


@pytest.mark.parametrize("speed", [1.0, 1, 0.0, 0, 2.0, 0.5, -1.0, -0.7, 2.5])
def test_speed_effects_flame_variant(speed):
    expected = otio.schema.Clip()
    flame_speed_effects(expected, speed)
    clip = otio.schema.Clip()
    effects.add_speed_effect(clip, speed)
    assert _effects_json(clip) == _effects_json(expected)


def test_add_speed_effect_reports_what_it_did():
    clip = otio.schema.Clip()
    assert not effects.add_speed_effect(clip, 1.0)
    assert effects.add_speed_effect(clip, 2.0)
    assert effects.add_speed_effect(clip, 0.0)
    assert len(clip.effects) == 2


def test_timewarp_effect_hiero_variant():
    metadata = {"lookup": [0, -1, -1], "length": 3.0}
    expected = hiero_timewarp_effect("TimeWarp6", "TimeWarp6", metadata)
    effect = effects.create_timewarp_effect(
        [0, -1, -1],
        name="TimeWarp6",
        effect_name=effects.timewarp_effect_name("TimeWarp6"),
        metadata={"length": 3.0},
    )
    assert effect.to_json_string() == expected.to_json_string()


def test_timewarp_effect_flame_variant():
    metadata = {"lookup": [1, 0, 0]}
    expected = flame_timewarp_effect(metadata)
    effect = effects.create_timewarp_effect([1, 0, 0])
    assert effect.to_json_string() == expected.to_json_string()


@pytest.mark.parametrize(
    "host_name",
    ["TimeWarp", "TimeWarp1", "TimeWarp6", "TimeWarp12", "TimeWarp_2",
     "TimeWarp_2_1", "My_TimeWarp_3"],
)
def test_timewarp_effect_name_hiero_variant(host_name):
    if "_" in host_name:
        expected = re.sub(r"(?:_)[_0-9]+", "", host_name)
    else:
        expected = re.sub(r"\d+", "", host_name)
    assert effects.timewarp_effect_name(host_name) == expected


def test_lookup_from_frames_flame_formula():
    """`mapped_frame - (frame_src_offset + idx)`."""
    mapped = [1001, 1001, 1002, 1005]
    offset = 1001
    expected = [
        mapped_frame - (offset + idx)
        for idx, mapped_frame in enumerate(mapped)
    ]
    assert effects.lookup_from_frames(mapped, offset) == expected
    assert expected == [0, -1, -1, 1]


def test_lookup_from_frames_hiero_formula():
    """`value_at(i) - i` for `i` from `timelineIn`."""
    timeline_in = 86400

    def value_at(i):
        return i * 2 - timeline_in

    expected = [value_at(i) - i for i in range(timeline_in, timeline_in + 4)]
    mapped = [value_at(i) for i in range(timeline_in, timeline_in + 4)]
    assert effects.lookup_from_frames(mapped, timeline_in) == expected


def test_get_retime_info_plain_clip():
    info = effects.get_retime_info(otio.schema.Clip())
    assert info == effects.RetimeInfo()
    assert not info.is_retimed


def test_get_retime_info_skips_empty_or_scalar_lookup(caplog):
    clip = otio.schema.Clip()
    clip.effects.append(effects.create_timewarp_effect([]))
    scalar = otio.schema.TimeEffect(
        name="TimeWarp1", effect_name="TimeWarp", metadata={"lookup": 2.5})
    clip.effects.append(scalar)
    other = otio.schema.TimeEffect(
        name="Blur", effect_name="Blur", metadata={"lookup": [1]})
    clip.effects.append(other)
    info = effects.get_retime_info(clip)
    assert info.timewarps == []
    assert "not a list" in caplog.text


def test_get_retime_info_last_speed_wins_and_freeze_overrides():
    clip = otio.schema.Clip()
    clip.effects.append(otio.schema.LinearTimeWarp(time_scalar=2.0))
    clip.effects.append(otio.schema.LinearTimeWarp(time_scalar=3.0))
    assert effects.get_retime_info(clip).time_scalar == 3.0
    clip.effects.append(otio.schema.FreezeFrame())
    assert effects.get_retime_info(clip).time_scalar == 0.0


def test_add_retime_effects_orders_speed_before_warps():
    clip = otio.schema.Clip()
    info = effects.RetimeInfo(
        2.0,
        [{"Class": "TimeWarp", "name": "TimeWarp1", "lookup": [0, 1],
          "length": 2.0}],
    )
    effects.add_retime_effects(clip, info)
    assert [type(e).__name__ for e in clip.effects] == [
        "LinearTimeWarp", "TimeEffect"]
    assert clip.effects[1].metadata["length"] == 2.0
    assert effects.get_retime_info(clip) == info


def test_flame_shape_has_no_speed_effect_with_a_timewarp():
    """Flame writes the warp alone; the speed then reads as 1."""
    clip = otio.schema.Clip()
    effects.add_timewarp_effect(clip, [1, 0, 0])
    assert _effects_json(clip) == [
        flame_timewarp_effect({"lookup": [1, 0, 0]}).to_json_string()]
    info = effects.get_retime_info(clip)
    assert info.time_scalar == 1.0
    assert info.timewarps[0]["lookup"] == [1, 0, 0]
    assert core_read_retime(clip) == (1.0, info.timewarps)


def test_hiero_not_animated_timewarp_keeps_the_number():
    """Hiero writes `node["lookup"].value()`, a number; it is kept."""
    expected = hiero_timewarp_effect(
        "TimeWarp2", "TimeWarp2", {"lookup": 0.0, "length": 12.0})
    effect = effects.create_timewarp_effect(
        0.0, name="TimeWarp2", metadata={"length": 12.0})
    assert effect.to_json_string() == expected.to_json_string()
    clip = otio.schema.Clip()
    clip.effects.append(effect)
    assert effects.get_retime_info(clip).timewarps == []
    assert core_read_retime(clip) == (1.0, [])
