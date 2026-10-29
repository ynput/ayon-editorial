"""Reference exporter: the AYON Resolve host export, run without Resolve.

Host repo: ayon-resolve
Host file: client/ayon_resolve/otio/davinci_export.py
Host commit: 59328ceca3e7e62f1ba4e29291dfd4cd9dbde4b1
Host git blob: 6db566dc154d6a84b1c46ad10edbbd253475df67

Copied verbatim from davinci_export.py: lines 14-339 (TRACK_TYPES to the end
of create_otio_timeline); `write_to_file` (L342-343) is not needed.
Copied verbatim from client/ayon_resolve/otio/utils.py (same commit):
lines 9-12 (timecode_to_frames), 24-53 (get_reformated_path), 56-74
(get_padding_from_path).

One docstring end gets `# noqa: E501` (L273).

Changed lines carry a trailing `# HOST-READ` comment: the host imports
(`ayon_resolve.api.lib` and `utils`, replaced by the helpers below) and the
read of the timeline media pool item. Every other host read (GetClipProperty,
GetMetadata, GetMarkers, GetLeftOffset, GetStart, GetSetting, ...) is served
by the fake classes at the end of this module, built from a plain dict, so
the copied lines stay as they are. Only opentimelineio, clique and stdlib are
used, deliberately not `ayon_editorial`.

Input dict (see resolve_input.json): `project.settings`, `timeline` with
`name`, `start_frame`, `settings`, `media_pool_item` and `tracks` (`video`,
`audio`: lists of `{name, items}`); an item has `name`, `start`,
`left_offset`, `duration`, `markers` and `media_pool_item` (None: offline).
A media pool item has `name`, `metadata` and `properties` (the Resolve clip
properties as strings).
"""

import os
import re
import json
import types

import opentimelineio as otio
import clique


# fmt: off
# --- utils.py (verbatim) ---

def timecode_to_frames(timecode, framerate):
    rt = otio.opentime.from_timecode(timecode, 24)
    return int(otio.opentime.to_frames(rt))


def get_reformated_path(path, padded=True, first=False):
    """
    Return fixed python expression path

    Args:
        path (str): path url or simple file name

    Returns:
        type: string with reformatted path

    Example:
        get_reformated_path("plate.[0001-1008].exr") > plate.%04d.exr

    """
    num_pattern = r"(\[\d+\-\d+\])"
    padding_pattern = r"(\d+)(?=-)"
    first_frame_pattern = re.compile(r"\[(\d+)\-\d+\]")

    if "[" in path:
        padding = len(re.findall(padding_pattern, path).pop())
        if padded:
            path = re.sub(num_pattern, f"%0{padding}d", path)
        elif first:
            first_frame = re.findall(first_frame_pattern, path, flags=0)
            if len(first_frame) >= 1:
                first_frame = first_frame[0]
            path = re.sub(num_pattern, first_frame, path)
        else:
            path = re.sub(num_pattern, "%d", path)
    return path


def get_padding_from_path(path):
    """
    Return padding number from DaVinci Resolve sequence path style

    Args:
        path (str): path url or simple file name

    Returns:
        int: padding number

    Example:
        get_padding_from_path("plate.[0001-1008].exr") > 4

    """
    padding_pattern = "(\\d+)(?=-)"
    if "[" in path:
        return len(re.findall(padding_pattern, path).pop())

    return None


utils = types.SimpleNamespace(  # HOST-READ
    timecode_to_frames=timecode_to_frames,
    get_reformated_path=get_reformated_path,
    get_padding_from_path=get_padding_from_path,
)
lib = types.SimpleNamespace(  # HOST-READ
    get_timeline_media_pool_item=(
        lambda timeline: timeline.GetTimelineMediaPoolItem()
    ),
)


# --- davinci_export.py (verbatim L14-339) ---

TRACK_TYPES = {
    "video": otio.schema.TrackKind.Video,
    "audio": otio.schema.TrackKind.Audio
}


def create_otio_rational_time(frame, fps):
    return otio.opentime.RationalTime(
        float(frame),
        float(fps)
    )


def create_otio_time_range(start_frame, frame_duration, fps):
    return otio.opentime.TimeRange(
        start_time=create_otio_rational_time(start_frame, fps),
        duration=create_otio_rational_time(frame_duration, fps)
    )


def create_otio_reference(media_pool_item):
    metadata = _get_metadata_media_pool_item(media_pool_item)
    print("media pool item: {}".format(media_pool_item.GetName()))

    _mp_clip_property = media_pool_item.GetClipProperty

    path = _mp_clip_property("File Path")
    reformat_path = utils.get_reformated_path(path, padded=True)
    padding = utils.get_padding_from_path(path)

    if padding:
        metadata.update({
            "isSequence": True,
            "padding": padding
        })

    # get clip property regarding to type
    fps = float(_mp_clip_property("FPS"))
    if _mp_clip_property("Type") == "Video":
        frame_start = int(_mp_clip_property("Start"))
        frame_duration = int(_mp_clip_property("Frames"))
    else:
        audio_duration = str(_mp_clip_property("Duration"))
        frame_start = 0
        frame_duration = int(utils.timecode_to_frames(
            audio_duration, float(fps)))

    otio_ex_ref_item = None
    available_start = otio.opentime.from_timecode(
        _mp_clip_property("Start TC"),
        fps
    )

    if padding:
        # if it is file sequence try to create `ImageSequenceReference`
        # the OTIO might not be compatible so return nothing and do it old way
        try:
            dirname, filename = os.path.split(path)
            collection = clique.parse(filename, '{head}[{ranges}]{tail}')
            padding_num = len(re.findall("(\\d+)(?=-)", filename).pop())
            otio_ex_ref_item = otio.schema.ImageSequenceReference(
                target_url_base=dirname + os.sep,
                name_prefix=collection.format("{head}"),
                name_suffix=collection.format("{tail}"),
                start_frame=frame_start,
                frame_zero_padding=padding_num,
                rate=fps,
                available_range=create_otio_time_range(
                    available_start.value,
                    frame_duration,
                    fps
                )
            )
        except AttributeError:
            pass

    if not otio_ex_ref_item:
        # in case old OTIO or video file create `ExternalReference`
        otio_ex_ref_item = otio.schema.ExternalReference(
            target_url=reformat_path,
            available_range=create_otio_time_range(
                available_start.value,
                frame_duration,
                fps
            )
        )

    # add metadata to otio item
    add_otio_metadata(otio_ex_ref_item, media_pool_item, **metadata)

    return otio_ex_ref_item


def create_otio_markers(track_item, fps, clip):
    track_item_markers = track_item.GetMarkers()
    markers = []
    available_start = clip.available_range().start_time.value_rescaled_to(fps)

    for marker_frame in track_item_markers:
        note = track_item_markers[marker_frame]["note"]
        if "{" in note and "}" in note:
            metadata = json.loads(note)
        else:
            metadata = {"note": note}
        markers.append(
            otio.schema.Marker(
                name=track_item_markers[marker_frame]["name"],
                marked_range=create_otio_time_range(
                    marker_frame + available_start,
                    track_item_markers[marker_frame]["duration"],
                    fps
                ),
                color=track_item_markers[marker_frame]["color"].upper(),
                metadata=metadata
            )
        )
    return markers


def create_otio_clip(track_item, fps=None):
    media_pool_item = track_item.GetMediaPoolItem()
    _mp_clip_property = media_pool_item.GetClipProperty

    fps = fps or float(_mp_clip_property("FPS"))
    name = track_item.GetName()

    media_reference = create_otio_reference(media_pool_item)
    available_start = media_reference.available_range.start_time
    conformed_start = available_start.value_rescaled_to(fps)

    source_range = create_otio_time_range(
        conformed_start + track_item.GetLeftOffset(),
        track_item.GetDuration(),
        fps
    )

    if _mp_clip_property("Type") == "Audio":
        return_clips = list()
        audio_chanels = _mp_clip_property("Audio Ch")
        for channel in range(0, int(audio_chanels)):
            clip = otio.schema.Clip(
                name=f"{name}_{channel}",
                source_range=source_range,
                media_reference=media_reference
            )
            for marker in create_otio_markers(track_item, fps, clip):
                clip.markers.append(marker)
            return_clips.append(clip)
        return return_clips
    else:
        clip = otio.schema.Clip(
            name=name,
            source_range=source_range,
            media_reference=media_reference
        )
        for marker in create_otio_markers(track_item, fps, clip):
            clip.markers.append(marker)

        return clip


def create_otio_gap(gap_start, clip_start, tl_start_frame, fps):
    return otio.schema.Gap(
        source_range=create_otio_time_range(
            0,
            (clip_start - tl_start_frame) - gap_start,
            fps
        )
    )


def _create_otio_timeline(project, timeline, fps):
    metadata = _get_timeline_metadata(project, timeline)
    print(f"metadata: {metadata}")
    start_time = create_otio_rational_time(
        timeline.GetStartFrame(), fps)
    otio_timeline = otio.schema.Timeline(
        name=timeline.GetName(),
        global_start_time=start_time,
        metadata=metadata
    )
    return otio_timeline


def _get_timeline_metadata(project, timeline):
    timeline = project.GetCurrentTimeline()
    timeline_name = timeline.GetName()
    print(f"timeline name: {timeline_name}")
    #  get timeline media pool item for metadata update
    timeline_media_pool_item = lib.get_timeline_media_pool_item(timeline)
    return _get_metadata_media_pool_item(timeline_media_pool_item)


def _get_metadata_media_pool_item(media_pool_item):
    data = dict()
    data.update({k: v for k, v in media_pool_item.GetMetadata().items()})
    property = media_pool_item.GetClipProperty() or {}
    for name, value in property.items():
        if "Resolution" in name and "" != value:
            print(f"property: {name} - {value}")
            width, height = value.split("x")
            print(f"width: {width} - height: {height}")
            data.update({
                "width": int(width),
                "height": int(height)
            })
        if "PAR" in name and "" != value:
            try:
                data.update({"pixelAspect": float(value)})
            except ValueError:
                if "Square" in value:
                    data.update({"pixelAspect": float(1)})
                else:
                    data.update({"pixelAspect": float(1)})
    print("_" * 100)
    return data


def create_otio_track(track_type, track_name):
    return otio.schema.Track(
        name=track_name,
        kind=TRACK_TYPES[track_type]
    )


def add_otio_gap(clip_start, otio_track, track_item, timeline):
    # if gap between track start and clip start
    if clip_start > otio_track.available_range().duration.value:
        # create gap and add it to track
        otio_track.append(
            create_otio_gap(
                otio_track.available_range().duration.value,
                track_item.GetStart(),
                timeline.GetStartFrame(),
                timeline.GetSetting("timelineFrameRate")
            )
        )


def add_otio_metadata(otio_item, media_pool_item, **kwargs):
    mp_metadata = media_pool_item.GetMetadata()
    # add additional metadata from kwargs
    if kwargs:
        mp_metadata.update(kwargs)

    # add metadata to otio item metadata
    for key, value in mp_metadata.items():
        otio_item.metadata.update({key: value})


def create_otio_timeline(resolve_project, timeline=None):
    """Create otio timeline from resolve timeline

    Args:
        resolve_project (resolve.Project): resolve project
        timeline (resolve.Timeline, optional): resolve timeline. Defaults to None.

    Returns:
        otio.schema.Timeline: otio timeline
    """  # noqa: E501

    # get current timeline
    timeline = timeline or resolve_project.GetCurrentTimeline()
    timeline_fps = (
        timeline.GetSetting("timelineFrameRate") or
        resolve_project.GetSetting("timelineFrameRate")
    )

    # convert timeline to otio
    otio_timeline = _create_otio_timeline(
        resolve_project, timeline, timeline_fps)

    # loop all defined track types
    for track_type in list(TRACK_TYPES.keys()):
        # get total track count
        track_count = timeline.GetTrackCount(track_type)

        # loop all tracks by track indexes
        for track_index in range(1, int(track_count) + 1):
            # get current track name
            track_name = timeline.GetTrackName(track_type, track_index)

            # convert track to otio
            otio_track = create_otio_track(
                track_type, track_name)

            # get all track items in current track
            current_track_items = timeline.GetItemListInTrack(
                track_type, track_index)

            # loop available track items in current track items
            for track_item in current_track_items:
                # skip offline track items
                if track_item.GetMediaPoolItem() is None:
                    continue

                # calculate real clip start
                clip_start = track_item.GetStart() - timeline.GetStartFrame()

                add_otio_gap(
                    clip_start, otio_track, track_item, timeline)

                # create otio clip and add it to track
                otio_clip = create_otio_clip(track_item, fps=timeline_fps)

                if not isinstance(otio_clip, list):
                    otio_track.append(otio_clip)
                else:
                    for index, clip in enumerate(otio_clip):
                        if index == 0:
                            otio_track.append(clip)
                        else:
                            # add previous otio track to timeline
                            otio_timeline.tracks.append(otio_track)
                            # convert track to otio
                            otio_track = create_otio_track(
                                track_type, track_name)
                            add_otio_gap(
                                clip_start, otio_track,
                                track_item, timeline)
                            otio_track.append(clip)

            # add track to otio timeline
            otio_timeline.tracks.append(otio_track)

    return otio_timeline
# fmt: on


class _FakeMediaPoolItem:
    """Resolve MediaPoolItem reads, served from a dict."""

    def __init__(self, data):
        self._data = data

    def GetName(self):
        return self._data["name"]

    def GetMetadata(self):
        # Resolve returns a new dict on every call; the host mutates it
        return dict(self._data.get("metadata", {}))

    def GetClipProperty(self, name=None):
        properties = self._data.get("properties", {})
        if name is None:
            return dict(properties)
        return properties.get(name)


class _FakeTrackItem:
    """Resolve TimelineItem reads, served from a dict."""

    def __init__(self, data):
        self._data = data

    def GetMediaPoolItem(self):
        media = self._data.get("media_pool_item")
        return None if media is None else _FakeMediaPoolItem(media)

    def GetName(self):
        return self._data["name"]

    def GetStart(self):
        return self._data["start"]

    def GetLeftOffset(self):
        return self._data["left_offset"]

    def GetDuration(self):
        return self._data["duration"]

    def GetMarkers(self):
        # Resolve keys markers by integer frame offset, JSON by string
        return {
            int(frame): dict(marker)
            for frame, marker in self._data.get("markers", {}).items()
        }


class _FakeTimeline:
    """Resolve Timeline reads, served from a dict."""

    def __init__(self, data):
        self._data = data

    def GetName(self):
        return self._data["name"]

    def GetStartFrame(self):
        return self._data["start_frame"]

    def GetSetting(self, name):
        return self._data.get("settings", {}).get(name)

    def GetTimelineMediaPoolItem(self):
        return _FakeMediaPoolItem(self._data["media_pool_item"])

    def GetTrackCount(self, track_type):
        return len(self._data["tracks"].get(track_type, []))

    def GetTrackName(self, track_type, track_index):
        return self._data["tracks"][track_type][track_index - 1]["name"]

    def GetItemListInTrack(self, track_type, track_index):
        track = self._data["tracks"][track_type][track_index - 1]
        return [_FakeTrackItem(item) for item in track["items"]]


class _FakeProject:
    """Resolve Project reads, served from a dict."""

    def __init__(self, data):
        self._timeline = _FakeTimeline(data["timeline"])
        self._settings = data.get("project", {}).get("settings", {})

    def GetCurrentTimeline(self):
        return self._timeline

    def GetSetting(self, name):
        return self._settings.get(name)


def export(data):
    """Run the host export on the plain input dict.

    Args:
        data (dict): Input, see the module docstring.

    Returns:
        otio.schema.Timeline: The timeline the host would have written.
    """
    return create_otio_timeline(_FakeProject(data))  # HOST-READ
