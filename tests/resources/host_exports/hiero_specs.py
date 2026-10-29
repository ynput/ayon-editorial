"""Hiero export mapped to builder specs: the template for the P2.7 adoption.

Does the same job as `hiero_reference.py` (the host code), from the same
plain input dict (`hiero_input.json`), but assembles the timeline with
`ayon_editorial.otio`. The reads that stay in the host (tag filters, the
`tag.` key strip, `hiero_source_type`, icon colour, knob sampling,
`get_rate`, disabled track skip, `hasAudio` gate) are plain code here; in
the host each `data[...]` read is a Hiero call.

Must not import `hiero_reference`.
"""

import os
import re

import opentimelineio as otio

from ayon_editorial.otio import effects, paths
from ayon_editorial.otio.builder import (
    GAP_RECORD,
    ClipSpec,
    MarkerSpec,
    MediaSpec,
    SequenceSpec,
    SpeedEffectSpec,
    TimelineBuilder,
    TimeWarpEffectSpec,
)

MARKER_COLORS = {
    "magenta": otio.schema.MarkerColor.MAGENTA,
    "red": otio.schema.MarkerColor.RED,
    "yellow": otio.schema.MarkerColor.YELLOW,
    "green": otio.schema.MarkerColor.GREEN,
    "cyan": otio.schema.MarkerColor.CYAN,
    "blue": otio.schema.MarkerColor.BLUE,
}


def get_rate(framerate):
    """Rate of a Hiero item from its `[num, den]`, rounded to 4 digits."""
    num, den = framerate
    try:
        rate = float(num) / float(den)
    except ZeroDivisionError:
        return None
    if rate.is_integer():
        return rate
    return round(rate, 4)


def _marker_color(icon):
    match = re.search(r"icons:Tag(?P<color>\w+)\.\w+", icon)
    if match:
        color = match.group("color").lower()
        if color in MARKER_COLORS:
            return MARKER_COLORS[color]
    return otio.schema.MarkerColor.RED


def _marker_specs(tags, source_type, rate):
    specs = []
    for tag in tags:
        if not tag.get("visible", True):
            continue
        if tag["name"] == "Copy":
            # Hiero adds this tag to a lot of clips
            continue
        metadata = {
            key.replace("tag.", ""): value
            for key, value in tag.get("metadata", {}).items()
        }
        metadata["hiero_source_type"] = source_type
        specs.append(
            MarkerSpec(
                name=tag["name"],
                start=tag.get("in_time", 0),
                duration=int(tag.get("metadata", {}).get("tag.length", "0")),
                color=_marker_color(tag.get("icon", "")),
                metadata=metadata,
                rate=rate,
            )
        )
    return specs


def _knob_values(knob, first, last):
    """Sample a knob like the host: the value, or an offset per frame."""
    if "curve" not in knob:
        return knob["value"]
    keys = knob["curve"]

    def value_at(frame):
        if frame <= keys[0][0]:
            return keys[0][1]
        for (f_a, v_a), (f_b, v_b) in zip(keys, keys[1:]):
            if frame <= f_b:
                return v_a + (v_b - v_a) * (frame - f_a) / (f_b - f_a)
        return keys[-1][1]

    return effects.lookup_from_frames(
        [value_at(frame) for frame in range(first, last + 1)], first
    )


def _effect_specs(item, track, has_audio):
    if has_audio:
        return []
    speed = item.get("speed", 1.0)
    specs = [SpeedEffectSpec(speed)]
    first, last = item["timeline_in"], item["timeline_out"]
    for group in track.get("effects", []):
        for effect in group:
            linked = effect.get("linked", [])
            if item["name"] not in linked and len(linked) > 0:
                continue
            if "TimeWarp" not in effect["name"]:
                continue
            if not effect.get("enabled", True):
                continue
            node = effect["node"]
            specs.append(
                TimeWarpEffectSpec(
                    lookup=_knob_values(node["lookup"], first, last),
                    name=node["name"]["value"],
                    effect_name=effects.timewarp_effect_name(effect["name"]),
                    metadata={
                        "length": _knob_values(node["length"], first, last)
                    },
                )
            )
    return specs


def _media_spec(clip, project_fps):
    media = clip["media"]
    path = media["filename"]
    fps = get_rate(clip["framerate"]) or project_fps
    metadata = dict(media.get("metadata", {}))
    metadata.update(clip.get("metadata", {}))
    sequence = None
    if not media["single_file"]:
        metadata.update({"isSequence": True, "padding": media["padding"]})
        sequence = SequenceSpec(
            target_url_base=os.path.dirname(path) + os.sep,
            name_prefix=media["head"],
            name_suffix=os.path.splitext(path)[-1],
            start_frame=media["start_frame"],
            padding=media["padding"],
        )
    metadata.update(
        {
            "ayon.source.colorspace": clip.get("colour_transform", ""),
            "ayon.source.width": int(media["width"]),
            "ayon.source.height": int(media["height"]),
            "ayon.source.pixelAspect": float(media.get("pixel_aspect", 1.0)),
        }
    )
    return MediaSpec(
        target_url=paths.reformat_path(path, padded=False),
        available_start=media["timecode_start"],
        available_duration=media["duration"],
        rate=fps,
        metadata=metadata,
        sequence=sequence,
    )


def _clip_spec(item, track, clips, project_fps):
    clip = clips[item["clip"]]
    speed = item.get("speed", 1.0)
    # flip if speed is in minus
    source_in = item["source_in"] if speed > 0 else item["source_out"]
    fps = get_rate(clip["framerate"]) or project_fps
    markers = _marker_specs(item.get("tags", []), "TrackItem", fps)
    markers += _marker_specs(clip.get("tags", []), "Clip", fps)
    return ClipSpec(
        name=item["name"],
        source_offset=source_in,
        duration=int(item["timeline_out"] - item["timeline_in"] + 1),
        media=_media_spec(clip, project_fps),
        rate=fps,
        record_in=item["timeline_in"],
        record_out=item["timeline_out"],
        markers=markers,
        effects=_effect_specs(
            item, track, clip["media"].get("has_audio", False)
        ),
    )


def build(data: dict) -> "otio.schema.Timeline":
    """Build the timeline of the input dict, like `hiero_reference.export`."""
    project_fps = float(data["framerate"][0]) / float(data["framerate"][1])
    project = data["project"]
    fmt = data["format"]
    metadata = dict(data.get("metadata", {}))
    metadata.update(
        {
            "ayon.timeline.width": int(fmt["width"]),
            "ayon.timeline.height": int(fmt["height"]),
            "ayon.timeline.pixelAspect": int(fmt["pixel_aspect"]),
        }
    )
    metadata.update(
        {"ayon.project." + key: value for key, value in project.items()}
    )
    builder = TimelineBuilder(
        data["name"],
        project_fps,
        data["timecode_start"],
        metadata,
        gap_mode=GAP_RECORD,
        sequence_fallback_padded=False,
    )
    for track in data["tracks"]:
        if not track.get("enabled", True):
            continue
        kind = (
            otio.schema.TrackKind.Audio
            if track["kind"] == "audio"
            else otio.schema.TrackKind.Video
        )
        track_builder = builder.add_track(
            track["name"],
            kind,
            _marker_specs(track.get("tags", []), "VideoTrack", None),
        )
        for item in track["items"]:
            track_builder.append_clip(
                _clip_spec(item, track, data["clips"], project_fps)
            )
    return builder.build()
