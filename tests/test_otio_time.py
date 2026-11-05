"""Characterization tests of `otio/time.py`.

Each host variant is written out as the host code has it today, so the
shared functions are compared with what the hosts return now.
"""
from __future__ import annotations

import pytest

from ayon_editorial.otio import time as otio_time

otio = pytest.importorskip("opentimelineio")
pytestmark = pytest.mark.otio


# Host copies, verbatim (names as in the hosts).
def flame_timecode_to_frames(timecode, framerate):
    rt = otio.opentime.from_timecode(timecode, framerate)
    return int(otio.opentime.to_frames(rt))


def hiero_resolve_timecode_to_frames(timecode, framerate):
    rt = otio.opentime.from_timecode(timecode, 24)
    return int(otio.opentime.to_frames(rt))


def host_frames_to_timecode(frames, framerate):
    rt = otio.opentime.from_frames(frames, framerate)
    return otio.opentime.to_timecode(rt)


def host_frames_to_seconds(frames, framerate):
    rt = otio.opentime.from_frames(frames, framerate)
    return otio.opentime.to_seconds(rt)


def hiero_get_rate(num, den):
    try:
        rate = float(num) / float(den)
    except ZeroDivisionError:
        return None
    if rate.is_integer():
        return rate
    return round(rate, 4)


@pytest.mark.parametrize("framerate", [24, 25, 30, 24.0])
@pytest.mark.parametrize(
    "timecode", ["00:00:00:00", "00:00:01:00", "01:00:00:00", "00:10:03:12"]
)
def test_timecode_to_frames_flame_variant(timecode, framerate):
    assert otio_time.timecode_to_frames(
        timecode, framerate
    ) == flame_timecode_to_frames(timecode, framerate)


@pytest.mark.parametrize(
    "timecode", ["00:00:00:00", "00:00:01:00", "01:00:00:00", "00:10:03:12"]
)
def test_timecode_to_frames_hiero_resolve_variant_at_24(timecode):
    assert otio_time.timecode_to_frames(
        timecode, 24
    ) == hiero_resolve_timecode_to_frames(timecode, 24)


def test_timecode_to_frames_hiero_resolve_variant_ignores_rate():
    """Deliberate difference: the hosts parse at 24 whatever they are told."""
    assert hiero_resolve_timecode_to_frames("00:00:01:00", 25) == 24
    assert otio_time.timecode_to_frames("00:00:01:00", 25) == 25


@pytest.mark.parametrize("framerate", [23.976, 24, 25, 29.97, 30, 60])
@pytest.mark.parametrize("frames", [0, 1, 24, 1001, 86400])
def test_frames_conversions_all_hosts(frames, framerate):
    assert otio_time.frames_to_timecode(
        frames, framerate
    ) == host_frames_to_timecode(frames, framerate)
    assert otio_time.frames_to_seconds(
        frames, framerate
    ) == host_frames_to_seconds(frames, framerate)


def test_frames_to_timecode_values():
    assert otio_time.frames_to_timecode(25, 25) == "00:00:01:00"
    assert otio_time.frames_to_timecode(86400, 24) == "01:00:00:00"


def test_frames_to_seconds_value():
    assert otio_time.frames_to_seconds(50, 25) == 2.0


@pytest.mark.parametrize(
    "num, den",
    [(24, 1), (25, 1), (24000, 1001), (30000, 1001), (60, 1), (0, 1),
     (24, 0), (1, 3)],
)
def test_rational_to_rate_hiero_variant(num, den):
    assert otio_time.rational_to_rate(num, den) == hiero_get_rate(num, den)


def test_rational_to_rate_values():
    assert otio_time.rational_to_rate(24000, 1001) == 23.976
    assert otio_time.rational_to_rate(25, 1) == 25.0
    assert otio_time.rational_to_rate(24, 0) is None


def test_create_rational_time_converts_to_float():
    value = otio_time.create_rational_time(1001, 24)
    assert value == otio.opentime.RationalTime(1001.0, 24.0)
    assert isinstance(value.value, float)


def test_create_time_range():
    value = otio_time.create_time_range(1001, 48, 25)
    assert value.start_time == otio.opentime.RationalTime(1001.0, 25.0)
    assert value.duration == otio.opentime.RationalTime(48.0, 25.0)
    assert value.end_time_exclusive().value == 1049.0


def test_timecode_to_frames_drop_frame():
    """Drop frame timecode skips frames 0 and 1 at the start of a minute."""
    assert otio_time.timecode_to_frames("00:00:59;29", 30000 / 1001) == 1799
    assert otio_time.timecode_to_frames("00:01:00;02", 30000 / 1001) == 1800


@pytest.mark.parametrize(
    "timecode, framerate",
    [
        ("00:00:01:00", 0),  # no rate
        ("00:00:01;00", 25),  # drop frame needs a 29.97/59.94 rate
        ("00:00:00:25", 25),  # frame field is not below the rate
        ("not a timecode", 24),
    ],
)
def test_timecode_to_frames_rejects_bad_input(timecode, framerate):
    """The Hiero and Resolve copies read these at 24 fps; this one raises."""
    with pytest.raises(ValueError):
        otio_time.timecode_to_frames(timecode, framerate)
