"""Map the Flame reference input to builder specs: the P2.9 template.

`build(data)` reads the plain input dict the way `ayon_flame` reads its
segments (the host reads stay plain data code below) and hands specs to
`TimelineBuilder`. P2.9 copies this into `flame_export.py`, replacing the
dict reads by the Flame reads. It does not import the reference exporter.
"""

from __future__ import annotations

import json
import os
import re

import opentimelineio as otio

from ayon_editorial.otio import builder, effects, paths

# ayon_core.lib.transcoding.IMAGE_EXTENSIONS
IMAGE_EXTENSIONS = {
    ".bmp", ".dpx", ".exr", ".gif", ".jpeg", ".jpg", ".png", ".tif",
    ".tiff", ".tga", ".hdr",
}  # fmt: skip

MARKERS_COLOR_MAP = {
    (1.0, 0.0, 0.0): otio.schema.MarkerColor.RED,
    (1.0, 0.5, 0.0): otio.schema.MarkerColor.ORANGE,
    (1.0, 1.0, 0.0): otio.schema.MarkerColor.YELLOW,
    (1.0, 0.5, 1.0): otio.schema.MarkerColor.PINK,
    (1.0, 1.0, 1.0): otio.schema.MarkerColor.WHITE,
    (0.0, 1.0, 0.0): otio.schema.MarkerColor.GREEN,
    (0.0, 1.0, 1.0): otio.schema.MarkerColor.CYAN,
    (0.0, 0.0, 1.0): otio.schema.MarkerColor.BLUE,
    (0.5, 0.0, 0.5): otio.schema.MarkerColor.PURPLE,
    (0.5, 0.0, 1.0): otio.schema.MarkerColor.MAGENTA,
    (0.0, 0.0, 0.0): otio.schema.MarkerColor.BLACK,
}


def _get_marker_color(flame_colour):
    # clamp colors to closes half numbers
    clamped = [round(c * 2) / 2 for c in flame_colour]
    for color, otio_color in MARKERS_COLOR_MAP.items():
        if clamped == list(color):
            return otio_color
    return otio.schema.MarkerColor.RED


def _marker_spec(marker, record_in):
    comment = marker["comment"]
    # Flame keeps its own test: at least `{`, `:`, `}` three times
    metadata = {}
    if len(re.findall(r"[{:}]", comment)) >= 3:
        try:
            metadata.update(json.loads(comment))
        except ValueError:
            pass
    else:
        metadata["comment"] = comment
    return builder.MarkerSpec(
        name=marker["name"],
        start=(marker["location"] - record_in) + 1,
        duration=marker["duration"],
        color=_get_marker_color(marker["colour"]),
        metadata=metadata,
    )


def _media_spec(path, info, source_duration, timeline_rate):
    """Media of a segment, from the probed `info` of its file."""
    metadata = {}
    if "width" in info:
        metadata.update(
            {
                "ayon.source.width": info["width"],
                "ayon.source.height": info["height"],
                "ayon.source.pixelAspect": info["pixel_aspect"],
            }
        )
    media_start = info["start_frame"] or 0
    fps = info["fps"] or timeline_rate
    file_name = os.path.basename(path)
    file_head, extension = os.path.splitext(file_name)

    sequence = None
    match = re.match(
        r".*\[(?P<start_frame>\d*)-(?P<end_frame>\d*)\].?",
        info.get("file_pattern", path),
    )
    if match:
        frame_number = match.group("start_frame")
        sequence = builder.SequenceSpec(
            target_url_base=os.path.dirname(path) + os.sep,
            name_prefix=file_name.split(frame_number)[0],
            name_suffix=extension,
            start_frame=int(frame_number),
            padding=len(frame_number),
        )
    return builder.MediaSpec(
        target_url=path,
        available_start=media_start,
        available_duration=source_duration,
        rate=fps,
        metadata=metadata,
        sequence=sequence,
    )


def _clip_spec(segment, info_by_path, timeline_rate):
    # segment attributes
    name = segment.get("name")
    path = segment.get("file_path", "")
    if not (path and name):
        name = "Missing: Segment's File Path"
        path = ""
    record_in = segment["record_in"]
    record_out = segment["record_out"]
    record_duration = int(segment["record_duration"])
    clip_source_in = int(segment["source_in"])
    clip_source_out = int(segment["source_out"])

    info = None
    file_first_frame = None
    media_timecode_start = None
    if path:
        info = info_by_path[path]
        media_timecode_start = info["start_frame"]
        file_first_frame = paths.get_frame(path, IMAGE_EXTENSIONS)
        if file_first_frame:
            file_first_frame = int(file_first_frame)
    elif segment.get("start_frame"):
        file_first_frame = int(segment["start_frame"])
        media_timecode_start = file_first_frame
    first_frame = media_timecode_start or file_first_frame or 0

    # reverse timing: Flame swaps source in and out
    speed = 1
    if clip_source_in > clip_source_out:
        source_in = clip_source_out - first_frame
        source_out = clip_source_in - first_frame
        speed = -1
    else:
        source_in = clip_source_in - first_frame
        source_out = clip_source_out - first_frame
    source_duration = source_out - source_in + 1

    # retime from the difference of source and record durations
    if source_duration != record_duration:
        speed *= float(source_duration) / float(record_duration)

    media = None
    if info:
        media = _media_spec(path, info, source_duration, timeline_rate)

    markers = [
        _marker_spec(marker, record_in)
        for marker in segment.get("markers", [])
    ]

    # Flame writes a time warp OR a speed effect, never both
    clip_effects = []
    if info:
        time_effect = segment.get("time_effect") or {}
        tw_data = time_effect.get("data", {})
        timewarp = None
        if not time_effect.get("is_empty", True):
            if tw_data["type"] == "speed" and tw_data.get("numKeys") == 1:
                speed = tw_data["speed"]
            else:
                av_start = int(media.available_start)
                mapped_frames = [
                    av_start + iframe - 1
                    for iframe in time_effect.get("iframes", {}).values()
                ]
                timewarp = builder.TimeWarpEffectSpec(
                    lookup=effects.lookup_from_frames(
                        mapped_frames, min(clip_source_in, clip_source_out)
                    )
                )
        if timewarp is not None:
            clip_effects.append(timewarp)
        else:
            clip_effects.append(builder.SpeedEffectSpec(speed))

    return builder.ClipSpec(
        name=name,
        source_offset=source_in,
        duration=record_duration,
        media=media,
        record_in=record_in,
        record_out=record_out,
        markers=markers,
        effects=clip_effects,
    )


def _fill_track(track_builder, segments, info_by_path, timeline_rate):
    for segment in segments:
        if segment.get("type") == "Gap":
            continue
        track_builder.append_clip(
            _clip_spec(segment, info_by_path, timeline_rate)
        )


def build(data: dict) -> otio.schema.Timeline:
    """Build the timeline of the input dict with `TimelineBuilder`."""
    sequence = data["sequence"]
    info_by_path = data["media_info"]
    rate = float(sequence["frame_rate"])
    start_frame = int(
        otio.opentime.to_frames(
            otio.opentime.from_timecode(
                sequence["start_time"].replace("+", ":"), rate
            )
        )
    )
    metadata = dict(data["colourspace_policy"])
    metadata.update(
        {
            "ayon.timeline.width": int(sequence["width"]),
            "ayon.timeline.height": int(sequence["height"]),
            "ayon.timeline.pixelAspect": float(1),
        }
    )
    timeline_builder = builder.TimelineBuilder(
        sequence["name"],
        rate,
        start_frame=start_frame,
        metadata=metadata,
        gap_mode=builder.GAP_RECORD,
        sequence_fallback_padded=False,
    )

    for version in sequence["versions"]:
        for track in version:
            # avoid all empty or hidden tracks
            if not track.get("segments") or track.get("hidden"):
                continue
            track_builder = timeline_builder.add_track(track["name"], "Video")
            _fill_track(track_builder, track["segments"], info_by_path, rate)

    for audio_track in sequence.get("audio_tracks", []):
        # only the first channel is exported
        channel = audio_track["channels"][0]
        if not channel.get("segments") or channel.get("hidden"):
            continue
        track_builder = timeline_builder.add_track(
            audio_track["name"] or "unnamed", "Audio"
        )
        _fill_track(track_builder, channel["segments"], info_by_path, rate)

    return timeline_builder.build()
