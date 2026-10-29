"""Rational time, time ranges and timecode conversions.

Replaces `timecode_to_frames`, `frames_to_timecode`, `frames_to_secons`
(sic) in `ayon_flame/otio/utils.py`, `ayon_hiero/api/otio/utils.py` and
`ayon_resolve/otio/utils.py`, the `create_otio_rational_time` and
`create_otio_time_range` copies in the three exporters, and the rate
calculation of Hiero's `get_rate`.

The Hiero and Resolve copies of `timecode_to_frames` ignore their
`framerate` argument and always parse at 24 fps; the Flame copy uses it.
This module follows Flame, so all three agree at 24 fps and Hiero and
Resolve become correct at any other rate.
"""
from __future__ import annotations

from typing import Optional, Union

import opentimelineio as otio

__all__ = (
    "create_rational_time",
    "create_time_range",
    "frames_to_seconds",
    "frames_to_timecode",
    "rational_to_rate",
    "timecode_to_frames",
)

Number = Union[int, float]


def timecode_to_frames(timecode: str, framerate: Number) -> int:
    """Convert a timecode to a frame count.

    Args:
        timecode: `HH:MM:SS:FF` (or `;` before FF for drop frame).
        framerate: Frames per second the timecode is counted at.

    Example:
        timecode_to_frames("00:00:01:00", 25) > 25
    """
    rate = otio.opentime.from_timecode(timecode, framerate)
    return int(otio.opentime.to_frames(rate))


def frames_to_timecode(frames: Number, framerate: Number) -> str:
    """Convert a frame count to a timecode at `framerate`."""
    rate = otio.opentime.from_frames(frames, framerate)
    return otio.opentime.to_timecode(rate)


def frames_to_seconds(frames: Number, framerate: Number) -> float:
    """Convert a frame count to seconds at `framerate`."""
    rate = otio.opentime.from_frames(frames, framerate)
    return otio.opentime.to_seconds(rate)


def rational_to_rate(
    numerator: Number, denominator: Number
) -> Optional[Number]:
    """Turn a rational frame rate into the rate OTIO objects are built at.

    Args:
        numerator: Rational numerator, e.g. 24000.
        denominator: Rational denominator, e.g. 1001.

    Returns:
        Optional[Number]: A float that is whole for whole rates (`24.0`),
            rounded to 4 decimals otherwise (`23.976`). None when the
            denominator is zero.

    Example:
        rational_to_rate(24000, 1001) > 23.976
    """
    try:
        rate = float(numerator) / float(denominator)
    except ZeroDivisionError:
        return None
    if rate.is_integer():
        return rate
    return round(rate, 4)


def create_rational_time(
    frame: Number, fps: Number
) -> "otio.opentime.RationalTime":
    """Create a `RationalTime` of `frame` frames at `fps`."""
    return otio.opentime.RationalTime(float(frame), float(fps))


def create_time_range(
    start_frame: Number, frame_duration: Number, fps: Number
) -> "otio.opentime.TimeRange":
    """Create a `TimeRange` from a start frame and a duration in frames."""
    return otio.opentime.TimeRange(
        start_time=create_rational_time(start_frame, fps),
        duration=create_rational_time(frame_duration, fps),
    )
