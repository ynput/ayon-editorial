"""Build an OTIO timeline from plain specs, without a host.

Replaces the timeline assembly copied in `ayon_flame/otio/flame_export.py`,
`ayon_hiero/api/otio/hiero_export.py` and
`ayon_resolve/otio/davinci_export.py`: the media reference with its image
sequence fallback, the source range, the record gaps, the markers and
effects of a clip, the tracks and the file write. A host reads its own
objects into `ClipSpec`, `MediaSpec` and `MarkerSpec` and hands them over.

The builder never rounds or rationalises a rate and never reads a path or
a host object. Every rate goes through `float()` once (inside
`create_rational_time`) and every number is stored unrounded, so a rounded
and an unrounded rate of the same media (Hiero) both survive. What the
hosts disagree on stays a parameter: `gap_mode`,
`ClipSpec.offset_at_clip_rate`, `sequence_fallback_padded`,
`MarkerSpec.rate` and `MarkerSpec.relative_to_available_start`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Union,
)

import opentimelineio as otio

from . import compat
from .effects import create_speed_effect, create_timewarp_effect
from .time import create_rational_time, create_time_range

__all__ = (
    "GAP_NONE",
    "GAP_RECORD",
    "GAP_TRACK_END",
    "ClipSpec",
    "MarkerSpec",
    "MediaSpec",
    "SequenceSpec",
    "SpeedEffectSpec",
    "TimeWarpEffectSpec",
    "TimelineBuilder",
    "TrackBuilder",
    "create_clip",
    "create_marker",
    "create_media_reference",
    "write_to_file",
)

log = logging.getLogger(__name__)

GAP_RECORD = "record"
GAP_TRACK_END = "track_end"
GAP_NONE = "none"


@dataclass
class SequenceSpec:
    """Media that is an image sequence.

    Attributes:
        target_url_base: Directory, with its trailing separator.
        name_prefix: File name before the frame number.
        name_suffix: File name after the frame number, with the dot.
        start_frame: First frame number of the sequence.
        padding: Zero padding of the frame number.
    """

    target_url_base: str
    name_prefix: str
    name_suffix: str
    start_frame: int
    padding: int


@dataclass
class MediaSpec:
    """Media of a clip.

    Attributes:
        target_url: Url of a plain file, unused with a `sequence`.
        available_start: First available frame at `rate`.
        available_duration: Available frames at `rate`.
        rate: Frame rate of the media.
        metadata: Metadata of the reference, host merged.
        sequence: Set when the media is an image sequence.
    """

    target_url: str
    available_start: float
    available_duration: float
    rate: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    sequence: Optional[SequenceSpec] = None


@dataclass
class MarkerSpec:
    """A marker.

    Attributes:
        name: Marker name.
        start: Start frame, see `relative_to_available_start`.
        duration: Duration in frames.
        color: OTIO marker color string.
        metadata: Marker metadata.
        rate: Rate of `start` and `duration`; None for the rate of the
            owner (clip rate, or timeline rate on a track).
        relative_to_available_start: Add the available start of the clip
            media, in `rate`, to `start` (Resolve).
    """

    name: str
    start: float
    duration: float
    color: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    rate: Optional[float] = None
    relative_to_available_start: bool = False


@dataclass
class SpeedEffectSpec:
    """Constant speed, see `effects.create_speed_effect` (1.0 adds none)."""

    speed: float


@dataclass
class TimeWarpEffectSpec:
    """A time warp, see `effects.create_timewarp_effect`.

    Attributes:
        lookup: Host computed lookup, a list or a number.
        name: Effect name.
        effect_name: Effect class name, must contain `TimeWarp`.
        metadata: More effect metadata.
    """

    lookup: Union[List[float], float]
    name: str = ""
    effect_name: str = "TimeWarp"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClipSpec:
    """A clip on a track.

    Attributes:
        name: Clip name.
        source_offset: Frames from the available start of the media.
        duration: Record frames at the clip rate.
        media: Media, None gives a `MissingReference`.
        rate: Clip rate; None for the timeline rate.
        offset_at_clip_rate: Conform the offset at the clip rate (Resolve)
            instead of at the media rate (Flame, Hiero).
        record_in: Record in frame, for `GAP_RECORD` and `GAP_TRACK_END`.
        record_out: Inclusive record out frame, for `GAP_RECORD`.
        markers: Applied in list order.
        effects: Applied in list order, after the markers.
        metadata: Clip metadata.
    """

    name: str
    source_offset: float
    duration: float
    media: Optional[MediaSpec] = None
    rate: Optional[float] = None
    offset_at_clip_rate: bool = False
    record_in: Optional[float] = None
    record_out: Optional[float] = None
    markers: List[MarkerSpec] = field(default_factory=list)
    effects: List[Union[SpeedEffectSpec, TimeWarpEffectSpec]] = field(
        default_factory=list
    )
    metadata: Dict[str, Any] = field(default_factory=dict)


def create_media_reference(
    media: Optional[MediaSpec],
    name: str,
    fallback_padded: bool = False,
) -> "otio.schema.MediaReference":
    """Create the media reference of a clip.

    Args:
        media: Media, None gives a `MissingReference` named `name`.
        name: Name of the clip.
        fallback_padded: On OTIO without `ImageSequenceReference`, build
            the url with `%0Nd` instead of `%d`.

    Returns:
        MediaReference: An `ImageSequenceReference`, or an
            `ExternalReference`, or a `MissingReference`.
    """
    if media is None:
        return otio.schema.MissingReference(name=name)

    available_range = create_time_range(
        media.available_start, media.available_duration, media.rate
    )
    sequence = media.sequence
    if sequence is None:
        reference = otio.schema.ExternalReference(
            target_url=media.target_url, available_range=available_range
        )
    elif compat.has_image_sequence_reference():
        reference = otio.schema.ImageSequenceReference(
            sequence.target_url_base,
            sequence.name_prefix,
            sequence.name_suffix,
            sequence.start_frame,
            frame_zero_padding=sequence.padding,
            rate=float(media.rate),
            available_range=available_range,
        )
    else:
        frame = f"%0{sequence.padding}d" if fallback_padded else "%d"
        reference = otio.schema.ExternalReference(
            target_url=(
                f"{sequence.target_url_base}{sequence.name_prefix}"
                f"{frame}{sequence.name_suffix}"
            ),
            available_range=available_range,
        )

    reference.metadata.update(dict(media.metadata))
    if sequence is not None:
        reference.metadata.update(
            {"isSequence": True, "padding": sequence.padding}
        )
    return reference


def create_marker(
    spec: MarkerSpec,
    rate: float,
    available_start: Optional["otio.opentime.RationalTime"] = None,
) -> "otio.schema.Marker":
    """Create a marker.

    Args:
        spec: Marker spec.
        rate: Rate of the owner, used when `spec.rate` is None.
        available_start: Available start of the clip media, added when
            `spec.relative_to_available_start` is set.
    """
    marker_rate = rate if spec.rate is None else spec.rate
    start = spec.start
    if spec.relative_to_available_start and available_start is not None:
        start = start + available_start.value_rescaled_to(
            float(marker_rate)
        )
    return otio.schema.Marker(
        name=spec.name,
        color=spec.color,
        marked_range=create_time_range(start, spec.duration, marker_rate),
        metadata=dict(spec.metadata),
    )


def _conform_start(spec: ClipSpec, rate: float) -> float:
    """Get the source range start of a clip, in frames at `rate`."""
    media = spec.media
    if media is None:
        available = create_rational_time(0, rate)
    else:
        available = create_rational_time(
            media.available_start, media.rate
        )
    if spec.offset_at_clip_rate:
        return available.value_rescaled_to(float(rate)) + spec.source_offset
    offset = create_rational_time(spec.source_offset, available.rate)
    return (available + offset).rescaled_to(float(rate)).value


def create_clip(
    spec: ClipSpec,
    rate: float,
    fallback_padded: bool = False,
) -> "otio.schema.Clip":
    """Create a clip with its reference, markers and effects.

    Args:
        spec: Clip spec.
        rate: Timeline rate, used when `spec.rate` is None.
        fallback_padded: See `create_media_reference`.
    """
    clip_rate = rate if spec.rate is None else spec.rate
    clip = otio.schema.Clip(
        name=spec.name,
        media_reference=create_media_reference(
            spec.media, spec.name, fallback_padded
        ),
        source_range=create_time_range(
            _conform_start(spec, clip_rate), spec.duration, clip_rate
        ),
    )
    if spec.metadata:
        clip.metadata.update(dict(spec.metadata))

    available_start = None
    available_range = clip.media_reference.available_range
    if callable(available_range):
        available_range = available_range()
    if available_range is not None:
        available_start = available_range.start_time
    for marker in spec.markers:
        clip.markers.append(create_marker(marker, clip_rate, available_start))

    for effect_spec in spec.effects:
        if isinstance(effect_spec, SpeedEffectSpec):
            effect = create_speed_effect(effect_spec.speed)
        else:
            effect = create_timewarp_effect(
                effect_spec.lookup,
                name=effect_spec.name,
                effect_name=effect_spec.effect_name,
                metadata=effect_spec.metadata,
            )
        if effect is not None:
            clip.effects.append(effect)
    return clip


def write_to_file(timeline: "otio.schema.Timeline", path: str) -> None:
    """Write a timeline to an OTIO file, the format follows the extension."""
    otio.adapters.write_to_file(timeline, path)


class TrackBuilder:
    """Fills one track, inserting the record gaps before each clip.

    Attributes:
        track: The OTIO track, already part of the timeline.
    """

    def __init__(
        self,
        track: "otio.schema.Track",
        rate: float,
        gap_mode: str = GAP_RECORD,
        sequence_fallback_padded: bool = False,
    ) -> None:
        self.track = track
        self._rate = rate
        self._gap_mode = gap_mode
        self._fallback_padded = sequence_fallback_padded
        self._prev_out: Optional[float] = None

    def append_clip(self, spec: ClipSpec) -> "otio.schema.Clip":
        """Append a clip, preceded by the gap of the gap mode.

        Raises:
            ValueError: When the gap mode needs `record_in` (and
                `record_out` for `GAP_RECORD`) and the spec has none.
        """
        if self._gap_mode == GAP_RECORD:
            self._check(spec, spec.record_in, spec.record_out)
            self._append_record_gap(spec.record_in)
        elif self._gap_mode == GAP_TRACK_END:
            self._check(spec, spec.record_in)
            end = self.track.available_range().duration.value
            if spec.record_in > end:
                self.track.append(
                    otio.schema.Gap(
                        source_range=create_time_range(
                            0, spec.record_in - end, self._rate
                        )
                    )
                )

        clip = create_clip(spec, self._rate, self._fallback_padded)
        self.track.append(clip)
        if self._gap_mode == GAP_RECORD:
            self._prev_out = spec.record_out
        return clip

    def append_gap(self, duration: float) -> "otio.schema.Gap":
        """Append a gap of `duration` frames at the timeline rate."""
        gap = otio.schema.Gap(
            source_range=create_time_range(0, duration, self._rate)
        )
        self.track.append(gap)
        return gap

    def add_marker(self, spec: MarkerSpec) -> "otio.schema.Marker":
        """Add a marker to the track."""
        marker = create_marker(spec, self._rate)
        self.track.markers.append(marker)
        return marker

    @staticmethod
    def _check(spec: ClipSpec, *values: Optional[float]) -> None:
        if any(value is None for value in values):
            raise ValueError(
                f"Clip '{spec.name}' needs record_in"
                " (and record_out for the record gap mode)."
            )

    def _append_record_gap(self, record_in: float) -> None:
        prev_out = self._prev_out
        if prev_out is None:
            if record_in <= 0:
                return
            length = record_in
        else:
            length = record_in - prev_out
            if length == 1:
                return
            if prev_out != 0:
                length -= 1
            if length <= 0:
                log.warning(
                    "Clip starts at record frame %s, before or at the"
                    " previous out %s: gap of %s frames.",
                    record_in,
                    prev_out,
                    length,
                )
        self.track.append(
            otio.schema.Gap(
                source_range=otio.opentime.TimeRange(
                    duration=create_rational_time(length, self._rate)
                )
            )
        )


class TimelineBuilder:
    """Builds a timeline track by track.

    Args:
        name: Timeline name.
        rate: Timeline rate.
        start_frame: Global start time in frames at `rate`.
        metadata: Timeline metadata.
        gap_mode: `GAP_RECORD`, `GAP_TRACK_END` or `GAP_NONE`.
        sequence_fallback_padded: See `create_media_reference`.
    """

    def __init__(
        self,
        name: str,
        rate: float,
        start_frame: float = 0.0,
        metadata: Optional[Mapping[str, Any]] = None,
        gap_mode: str = GAP_RECORD,
        sequence_fallback_padded: bool = False,
    ) -> None:
        self._rate = rate
        self._gap_mode = gap_mode
        self._fallback_padded = sequence_fallback_padded
        self._timeline = otio.schema.Timeline(
            name=name,
            global_start_time=create_rational_time(start_frame, rate),
            metadata=dict(metadata or {}),
        )

    @property
    def timeline(self) -> "otio.schema.Timeline":
        """The timeline being built."""
        return self._timeline

    def add_track(
        self,
        name: str,
        kind: str = "Video",
        markers: Sequence[MarkerSpec] = (),
    ) -> TrackBuilder:
        """Add a track to the timeline at once, in creation order."""
        track = otio.schema.Track(name=name, kind=kind)
        self._timeline.tracks.append(track)
        builder = TrackBuilder(
            track, self._rate, self._gap_mode, self._fallback_padded
        )
        for marker in markers:
            builder.add_marker(marker)
        return builder

    def build(self) -> "otio.schema.Timeline":
        """Get the timeline."""
        return self._timeline

    def write_to_file(self, path: str) -> None:
        """Write the timeline to an OTIO file."""
        write_to_file(self._timeline, path)
