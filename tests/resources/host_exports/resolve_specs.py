"""Map the Resolve reference input to builder specs.

Template for the Resolve host adoption (P2.8): the host reads (clip
properties, clique parse, audio channel split, marker notes, metadata
dicts, offline skip) stay here as plain data code, the timeline assembly
goes to `ayon_editorial.otio.builder`.

Reads the same input dict as `resolve_reference.export`, see the
docstring of that module. Does not import the reference.
"""

import json
import os
import re

import clique
import opentimelineio as otio

from ayon_editorial.otio import builder


def _frames_from_timecode(timecode, fps):
    """Mirror of the host `utils.timecode_to_frames`: decoded at 24.

    Kept on purpose so the adopted export stays byte-equal to today's. It is
    wrong for non 24 fps audio (10 s at 25 fps give 240 frames, not 250); the
    shared `otio.time.timecode_to_frames` is right. P2.8 decides, see
    `test_resolve_audio_duration_is_decoded_at_24_fps`.
    """
    rt = otio.opentime.from_timecode(timecode, 24)
    return int(otio.opentime.to_frames(rt))


def _padding_from_path(path):
    """Padding of a Resolve `[0001-0100]` sequence path, else None."""
    if "[" in path:
        return len(re.findall("(\\d+)(?=-)", path).pop())
    return None


def _reformat_path(path):
    """`plate.[0001-1008].exr` to `plate.%04d.exr`."""
    if "[" in path:
        padding = len(re.findall(r"(\d+)(?=-)", path).pop())
        path = re.sub(r"(\[\d+\-\d+\])", f"%0{padding}d", path)
    return path


def _metadata(item):
    """Media pool item metadata plus the width, height and pixel aspect."""
    data = dict(item.get("metadata", {}))
    for name, value in (item.get("properties") or {}).items():
        if "Resolution" in name and "" != value:
            width, height = value.split("x")
            data.update({"width": int(width), "height": int(height)})
        if "PAR" in name and "" != value:
            try:
                data.update({"pixelAspect": float(value)})
            except ValueError:
                data.update({"pixelAspect": float(1)})
    return data


def _media_spec(item):
    props = item["properties"]
    path = props["File Path"]
    padding = _padding_from_path(path)
    fps = float(props["FPS"])
    if props["Type"] == "Video":
        frame_start = int(props["Start"])
        frame_duration = int(props["Frames"])
    else:
        frame_start = 0
        frame_duration = int(
            _frames_from_timecode(str(props["Duration"]), fps)
        )
    available_start = otio.opentime.from_timecode(props["Start TC"], fps)

    sequence = None
    if padding:
        dirname, filename = os.path.split(path)
        collection = clique.parse(filename, "{head}[{ranges}]{tail}")
        sequence = builder.SequenceSpec(
            target_url_base=dirname + os.sep,
            name_prefix=collection.format("{head}"),
            name_suffix=collection.format("{tail}"),
            start_frame=frame_start,
            padding=len(re.findall("(\\d+)(?=-)", filename).pop()),
        )
    metadata = _metadata(item)
    return builder.MediaSpec(
        target_url=_reformat_path(path),
        available_start=available_start.value,
        available_duration=frame_duration,
        rate=fps,
        metadata=metadata,
        sequence=sequence,
    )


def _marker_specs(markers):
    specs = []
    for frame, marker in markers.items():
        note = marker["note"]
        if "{" in note and "}" in note:
            metadata = json.loads(note)
        else:
            metadata = {"note": note}
        specs.append(
            builder.MarkerSpec(
                name=marker["name"],
                start=int(frame),
                duration=marker["duration"],
                color=marker["color"].upper(),
                metadata=metadata,
                relative_to_available_start=True,
            )
        )
    return specs


def _clip_specs(track_item, timeline_start, fps):
    """One spec per clip, an audio clip gives one per channel."""
    item = track_item["media_pool_item"]
    props = item["properties"]
    record_in = track_item["start"] - timeline_start
    common = dict(
        source_offset=track_item["left_offset"],
        duration=track_item["duration"],
        media=_media_spec(item),
        rate=fps,
        offset_at_clip_rate=True,
        record_in=record_in,
    )
    name = track_item["name"]
    if props["Type"] == "Audio":
        return [
            builder.ClipSpec(
                name=f"{name}_{channel}",
                markers=_marker_specs(track_item.get("markers", {})),
                **common,
            )
            for channel in range(0, int(props["Audio Ch"]))
        ]
    return [
        builder.ClipSpec(
            name=name,
            markers=_marker_specs(track_item.get("markers", {})),
            **common,
        )
    ]


def build(data):
    """Build the timeline of the input dict with the builder.

    Args:
        data (dict): Input, same as for the reference exporter.

    Returns:
        otio.schema.Timeline: The built timeline.
    """
    timeline = data["timeline"]
    fps = (
        timeline["settings"].get("timelineFrameRate")
        or data["project"]["settings"]["timelineFrameRate"]
    )
    start_frame = timeline["start_frame"]
    tl_builder = builder.TimelineBuilder(
        timeline["name"],
        fps,
        start_frame,
        metadata=_metadata(timeline["media_pool_item"]),
        gap_mode=builder.GAP_TRACK_END,
        sequence_fallback_padded=True,
    )
    for kind, track_type in (("Video", "video"), ("Audio", "audio")):
        for track in timeline["tracks"].get(track_type, []):
            track_builder = tl_builder.add_track(track["name"], kind)
            for track_item in track["items"]:
                if track_item["media_pool_item"] is None:
                    continue  # offline
                specs = _clip_specs(track_item, start_frame, fps)
                for index, spec in enumerate(specs):
                    if index:
                        track_builder = tl_builder.add_track(
                            track["name"], kind
                        )
                    track_builder.append_clip(spec)
    return tl_builder.build()
