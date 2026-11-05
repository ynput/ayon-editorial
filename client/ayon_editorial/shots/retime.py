"""Retime options: include handles, retimed handles, retimed frame range.

Replaces Flame's `_set_workfile_start` (`collect_shots.py`), the handle and
source range math of its `extract_product_resources.py`, and the
`shotDurationFromSource` flag of its plate collector. Hiero gains the same
options through these helpers.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

__all__ = [
    "RetimeOptions",
    "SourceRange",
    "handles_for_core",
    "retime_instance_data",
    "source_range_with_handles",
    "unlinked_retime_values",
    "workfile_frame_start",
]

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetimeOptions:
    """The three retime flags of a shot.

    Attributes:
        include_handles: The workfile start frame includes the head handle.
        retimed_handles: Handles follow the clip speed.
        retimed_framerange: The shot frame range is the retimed source
            length.
    """

    include_handles: bool = False
    retimed_handles: bool = True
    retimed_framerange: bool = True

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "RetimeOptions":
        """Read `includeHandles`, `retimedHandles`, `retimedFramerange`.

        Missing or None values take the field defaults, so an older
        workfile without the keys publishes as before.
        """
        defaults = cls()

        def _get(key: str, default: bool) -> bool:
            value = data.get(key)
            return default if value is None else bool(value)

        return cls(
            include_handles=_get("includeHandles", defaults.include_handles),
            retimed_handles=_get("retimedHandles", defaults.retimed_handles),
            retimed_framerange=_get(
                "retimedFramerange", defaults.retimed_framerange
            ),
        )

    def to_attributes(self) -> Dict[str, bool]:
        """The flags under their creator attribute keys."""
        return {
            "includeHandles": self.include_handles,
            "retimedHandles": self.retimed_handles,
            "retimedFramerange": self.retimed_framerange,
        }


def workfile_frame_start(
    workfile_start: int, handle_start: int, include_handles: bool
) -> int:
    """First workfile frame of the shot (Flame `_set_workfile_start`).

    Args:
        workfile_start: Configured workfile start frame.
        handle_start: Head handle in frames.
        include_handles: The start frame includes the head handle.

    Returns:
        `workfile_start + handle_start` with included handles, else
        `workfile_start`.
    """
    if include_handles:
        return workfile_start + handle_start
    return workfile_start


def _unscale(handle: int, scale: float) -> int:
    """Integer `x` whose scaled value `x * scale` is closest to `handle`."""
    exact = handle / scale
    low, high = math.floor(exact), math.ceil(exact)
    if abs(low * scale - handle) <= abs(high * scale - handle):
        return int(low)
    return int(high)


def handles_for_core(
    handle_start: int,
    handle_end: int,
    speed: float,
    retimed_handles: bool,
) -> Tuple[int, int]:
    """Handles to give `get_media_range_with_retimes`.

    ayon-core scales both handles by `abs(speed)` and swaps them when the
    speed is negative. With `retimed_handles` that is wanted and the
    handles pass through. Without it, the handles are divided by the
    scale (and swapped for a negative speed) so that core's result is the
    configured handles.

    Rounding: the result is an integer, so core's scaled handle can differ
    from the configured one by up to `abs(speed) / 2` frames (exact for
    speeds of 1 over an integer, e.g. 0.5, and for whole speeds that divide
    the handle). A speed of 0 (freeze frame) cannot be undone: core scales
    the handles to 0 and the input is returned unchanged.

    Args:
        handle_start: Configured head handle.
        handle_end: Configured tail handle.
        speed: Clip speed (`time_scalar`), negative when reversed.
        retimed_handles: Handles follow the clip speed.

    Returns:
        Handles to pass to core as (start, end).
    """
    scale = abs(speed)
    if retimed_handles or scale == 0 or scale == 1:
        return handle_start, handle_end
    start, end = _unscale(handle_start, scale), _unscale(handle_end, scale)
    if speed < 0:
        # Core swaps after scaling: its start comes from our end.
        return end, start
    return start, end


@dataclass(frozen=True)
class SourceRange:
    """Result of `source_range_with_handles`.

    Attributes:
        source_start_handles: First source frame with handles.
        source_end_handles: Last source frame with handles.
        frame_start_handle: First workfile frame of the exported media.
        repre_frame_start: First frame number of the representation.
        source_duration_handles: Source frames with handles.
    """

    source_start_handles: float
    source_end_handles: float
    frame_start_handle: float
    repre_frame_start: float
    source_duration_handles: float


def source_range_with_handles(
    frame_start: int,
    handle_start: int,
    handle_end: int,
    source_start_handles: float,
    source_end_handles: float,
    retimed_speed: float,
    retimed_handle_start: float,
    retimed_handle_end: float,
    retimed_source_duration: float,
    include_handles: bool,
    retimed_handles: bool,
) -> SourceRange:
    """Source range with handles of a retimed clip.

    Pure port of the math in Flame's `extract_product_resources.py`.

    Args:
        frame_start: Workfile start frame, handles excluded.
        handle_start: Configured head handle.
        handle_end: Configured tail handle.
        source_start_handles: Source start minus the handle (`sourceStartH`).
        source_end_handles: Source end plus the handle (`sourceEndH`).
        retimed_speed: Clip speed, 1 when not retimed.
        retimed_handle_start: Head handle scaled by the speed.
        retimed_handle_end: Tail handle scaled by the speed.
        retimed_source_duration: Source duration scaled by the speed.
        include_handles: The shot start frame includes the head handle.
        retimed_handles: Handles follow the clip speed.

    Returns:
        The ranges as `SourceRange`.
    """
    if retimed_speed != 1.0:
        if retimed_handles:
            source_start_handles = (
                source_start_handles - retimed_handle_start)
            source_end_handles = (
                source_start_handles
                + (retimed_source_duration - 1)
                + retimed_handle_start
                + retimed_handle_end
            )
        else:
            source_end_handles = (
                source_start_handles
                + (retimed_source_duration - 1)
                + handle_start
                + handle_end
            )

    frame_start_handle = frame_start - handle_start
    repre_frame_start = frame_start_handle
    if include_handles:
        if retimed_speed == 1.0 or not retimed_handles:
            frame_start_handle = frame_start
        else:
            frame_start_handle = (
                frame_start - handle_start) + retimed_handle_start

    return SourceRange(
        source_start_handles=source_start_handles,
        source_end_handles=source_end_handles,
        frame_start_handle=frame_start_handle,
        repre_frame_start=repre_frame_start,
        source_duration_handles=(
            source_end_handles - source_start_handles) + 1,
    )


def unlinked_retime_values(
    source_in: float,
    source_out: float,
    record_duration: float,
    handle_start: int,
    handle_end: int,
) -> Dict[str, float]:
    """Retime inputs of a segment without linked media (Flame).

    The speed is the source length over the record length. Flame took
    `source_out - handle_end` for the end with handles; a handle extends
    the range, so this uses `source_out + handle_end`.

    Returns:
        `speed`, `handle_start`, `handle_end`, `source_duration`,
        `source_start_handles` and `source_end_handles`, the inputs of
        `source_range_with_handles`.
    """
    source_duration = source_out - source_in + 1
    speed = 1.0
    if source_duration != record_duration:
        speed *= float(source_duration) / float(record_duration)
    return {
        "speed": speed,
        "handle_start": handle_start * speed,
        "handle_end": handle_end * speed,
        "source_duration": source_duration * speed,
        "source_start_handles": source_in - handle_start,
        "source_end_handles": source_out + handle_end,
    }


def retime_instance_data(options: RetimeOptions) -> Dict[str, Any]:
    """Keys a shot instance carries for the publish plugins.

    ayon-core switches to the retimed ranges when `shotDurationFromSource`
    is present in `instance.data`, whatever its value (Flame set it to the
    flag, so it was always present). It is added only when the retimed
    frame range is on.

    Args:
        options: The retime flags of the shot.

    Returns:
        The three flags, plus `shotDurationFromSource` (True) if retimed.
    """
    data: Dict[str, Any] = options.to_attributes()
    if options.retimed_framerange:
        data["shotDurationFromSource"] = True
    return data
