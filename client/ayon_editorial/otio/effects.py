"""Retime effects on OTIO clips, in the shape ayon-core reads.

Replaces `create_time_effects` in `ayon_hiero/api/otio/hiero_export.py` and
`ayon_flame/otio/flame_export.py`. Resolve writes none itself: its native
OTIO export carries a `LinearTimeWarp`.

`ayon_core.pipeline.editorial.get_media_range_with_retimes` is the reader
and the contract. It looks at `otio_clip.effects` in order:

- `LinearTimeWarp`: `time_scalar` is the speed, the last one wins.
- `FreezeFrame`: speed 0.
- `TimeEffect` with `"TimeWarp"` in `effect_name`: a time warp node, when
  `metadata["lookup"]` is not empty.

A time warp node is the effect `name`, all its metadata and its `lookup`
(per frame offset of the source frame from the plain source frame) as a
list. `get_retime_info` reads clips exactly like that, so a clip that
round-trips through `add_retime_effects` is read the same by ayon-core.

What stays in the hosts: reading Flame timewarp XML (`tw_bake.py`) and
Hiero `TimeWarp` nodes. They compute the `lookup` frames and pass them to
`lookup_from_frames`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Union

import opentimelineio as otio

__all__ = (
    "FREEZE_FRAME_NAME",
    "SPEED_EFFECT_NAME",
    "TIMEWARP_EFFECT_NAME",
    "RetimeInfo",
    "add_retime_effects",
    "add_speed_effect",
    "add_timewarp_effect",
    "create_speed_effect",
    "create_timewarp_effect",
    "get_retime_info",
    "lookup_from_frames",
    "timewarp_effect_name",
)

log = logging.getLogger(__name__)

SPEED_EFFECT_NAME = "Speed"
FREEZE_FRAME_NAME = "FreezeFrame"
TIMEWARP_EFFECT_NAME = "TimeWarp"


@dataclass
class RetimeInfo:
    """What ayon-core reads from the effects of a clip.

    Attributes:
        time_scalar: Playback speed: 1 is none, 0 a freeze frame, negative
            is reversed.
        timewarps: Time warp nodes in effect order, each a dict with
            `Class`, `name`, the effect metadata and `lookup` (a list).
    """

    time_scalar: float = 1.0
    timewarps: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def is_retimed(self) -> bool:
        """Whether ayon-core treats the clip as retimed."""
        return bool(self.timewarps) or self.time_scalar != 1.0


def create_speed_effect(speed: float) -> Optional["otio.schema.Effect"]:
    """Create the constant speed effect for a playback speed.

    Args:
        speed: 1 for none, 0 for a freeze frame, negative for reversed.

    Returns:
        Optional[Effect]: A `FreezeFrame` for 0, a `LinearTimeWarp` named
            `Speed` for any other speed but 1, None for 1.
    """
    if speed == 0.0:
        return otio.schema.FreezeFrame(name=FREEZE_FRAME_NAME)
    if speed != 1.0:
        return otio.schema.LinearTimeWarp(
            name=SPEED_EFFECT_NAME, time_scalar=speed
        )
    return None


def add_speed_effect(otio_clip: Any, speed: float) -> bool:
    """Append the constant speed effect to a clip.

    Returns:
        bool: Whether an effect was added, False for speed 1.
    """
    effect = create_speed_effect(speed)
    if effect is None:
        return False
    otio_clip.effects.append(effect)
    return True


def create_timewarp_effect(
    lookup: Union[Iterable[float], float],
    name: str = "",
    effect_name: str = TIMEWARP_EFFECT_NAME,
    metadata: Optional[Mapping[str, Any]] = None,
) -> "otio.schema.TimeEffect":
    """Create a time warp effect.

    Args:
        lookup: Per frame offsets, see `lookup_from_frames`. A number
            (Hiero, not animated) is stored as is.
        name: Effect name; Hiero uses its node name, Flame none.
        effect_name: Effect class name; must contain `TimeWarp`.
        metadata: More metadata, e.g. Hiero's `length`.
    """
    effect = otio.schema.TimeEffect()
    effect.name = name
    effect.effect_name = effect_name
    effect.metadata.update(dict(metadata or {}))
    # Hiero stores a number for a time warp that is not animated; keep it
    # as it is, ayon-core ignores it when it is 0.
    try:
        effect.metadata["lookup"] = list(lookup)
    except TypeError:
        effect.metadata["lookup"] = lookup
    return effect


def add_timewarp_effect(
    otio_clip: Any,
    lookup: Iterable[float],
    name: str = "",
    effect_name: str = TIMEWARP_EFFECT_NAME,
    metadata: Optional[Mapping[str, Any]] = None,
) -> "otio.schema.TimeEffect":
    """Create a time warp effect and append it to a clip."""
    effect = create_timewarp_effect(lookup, name, effect_name, metadata)
    otio_clip.effects.append(effect)
    return effect


def lookup_from_frames(
    source_frames: Iterable[float], first_frame: float
) -> List[float]:
    """Compute a `lookup` from the source frame played at each frame.

    The lookup holds, per frame of the clip, how far the played source
    frame is from the frame that would play without the time warp.

    Args:
        source_frames: The source frame played at each frame in turn.
        first_frame: The frame number the first entry stands for: the
            source frame played without a time warp (Flame) or the
            timeline frame it is played at (Hiero, `timelineIn`).

    Example:
        lookup_from_frames([1001, 1001, 1002, 1003], 1001) > [0, -1, -1, -1]
    """
    return [
        frame - (first_frame + index)
        for index, frame in enumerate(source_frames)
    ]


_NUMBERED_NAME_RE = re.compile(r"(?:_)[_0-9]+")
_DIGITS_RE = re.compile(r"\d+")


def timewarp_effect_name(host_name: str) -> str:
    """Strip the numbering a host adds to an effect class.

    Example:
        timewarp_effect_name("TimeWarp6") > "TimeWarp"
        timewarp_effect_name("TimeWarp_2_1") > "TimeWarp"
    """
    if "_" in host_name:
        return _NUMBERED_NAME_RE.sub("", host_name)
    return _DIGITS_RE.sub("", host_name)


def get_retime_info(otio_clip: Any) -> RetimeInfo:
    """Read the retime of a clip the way ayon-core does.

    Args:
        otio_clip: An `otio.schema.Clip`.

    Returns:
        RetimeInfo: Speed and time warp nodes. A time warp whose lookup is
            empty or not a list is skipped, as ayon-core does (it would
            fail on a number; here it is logged and skipped).
    """
    info = RetimeInfo()
    for effect in otio_clip.effects:
        if isinstance(effect, otio.schema.LinearTimeWarp):
            info.time_scalar = effect.time_scalar
        elif isinstance(effect, otio.schema.FreezeFrame):
            info.time_scalar = 0.0
        elif isinstance(effect, otio.schema.TimeEffect):
            if "TimeWarp" not in effect.effect_name:
                continue
            metadata = effect.metadata
            lookup = metadata.get("lookup")
            if not lookup:
                continue
            try:
                lookup = list(lookup)
            except TypeError:
                log.warning(
                    "Ignoring time warp %r: lookup %r is not a list",
                    effect.name, lookup,
                )
                continue
            node = {"Class": "TimeWarp", "name": effect.name}
            node.update(metadata)
            node["lookup"] = lookup
            info.timewarps.append(node)
    return info


def add_retime_effects(otio_clip: Any, info: RetimeInfo) -> None:
    """Write a `RetimeInfo` the Hiero way: the speed first, then the warps.

    Flame writes a warp or the speed, never both: it calls
    `add_timewarp_effect` or `add_speed_effect` itself.
    """
    add_speed_effect(otio_clip, info.time_scalar)
    for node in info.timewarps:
        extra = {
            key: value
            for key, value in node.items()
            if key not in ("Class", "name", "lookup")
        }
        add_timewarp_effect(
            otio_clip,
            node["lookup"],
            name=node.get("name", ""),
            metadata=extra,
        )
