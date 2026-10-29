"""The `AYONData` timeline marker: reading, writing and lookup by clip.

Replaces `get_marker_from_clip_index` in `ayon_flame/otio/utils.py`,
`ayon_hiero/api/otio/utils.py`, `ayon_resolve/otio/utils.py`, the clip
lookup in `ayon_resolve/api/lib.py` and the marker text parsing of the
Flame and Resolve exporters.

The marker carries the creator data of a clip, among them `clip_index`.
Hosts write it differently into their own markers or tags, so on the OTIO
side the data is found in one of two shapes:

| Shape | Marker metadata | Written by |
| --- | --- | --- |
| json | `{"json_metadata": "{\\"clip_index\\": 1}"}` | Hiero |
| flat | `{"clip_index": 1}` | Flame, Resolve |

Resolve's own OTIO exporter wraps the note in
`{"Resolve_OTIO": {"Note": ...}}`. That workaround is Resolve-specific and
stays in `ayon_resolve`; pass it as `unwrap`.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

import opentimelineio as otio

from .compat import find_clips

__all__ = (
    "JSON_METADATA_KEY",
    "MARKER_NAME",
    "create_ayon_marker",
    "decode_marker_data",
    "encode_marker_data",
    "find_clip_by_index",
    "is_ayon_marker",
    "parse_marker_text",
)

log = logging.getLogger(__name__)

MARKER_NAME = "AYONData"
JSON_METADATA_KEY = "json_metadata"


def encode_marker_data(data: Mapping[str, Any]) -> str:
    """Serialise creator data for the `json_metadata` key."""
    return json.dumps(data)


def decode_marker_data(
    metadata: Optional[Mapping[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Read the creator data out of the metadata of a marker.

    Args:
        metadata: `marker.metadata`.

    Returns:
        Optional[dict]: The decoded `json_metadata`, else the metadata
            itself as a plain dict. None when `json_metadata` is not a JSON
            object (it is logged).
    """
    if not metadata:
        return None
    if JSON_METADATA_KEY not in metadata:
        return dict(metadata)
    try:
        data = json.loads(metadata[JSON_METADATA_KEY])
    except (TypeError, ValueError):
        log.warning(
            "Marker %s is not valid JSON: %r",
            JSON_METADATA_KEY, metadata[JSON_METADATA_KEY],
        )
        return None
    return data if isinstance(data, dict) else None


def parse_marker_text(
    text: Optional[str], fallback_key: str = "comment"
) -> Dict[str, Any]:
    """Turn the note or comment of a host marker into marker metadata.

    A JSON object becomes the metadata (flat shape); any other text is kept
    under `fallback_key`. Text that looks like JSON but does not parse is
    logged and gives an empty dict.

    Args:
        text: Marker comment (Flame) or note (Resolve).
        fallback_key: Key for text that is not JSON: `comment` for Flame,
            `note` for Resolve.
    """
    text = text or ""
    if "{" not in text or "}" not in text:
        return {fallback_key: text}
    try:
        data = json.loads(text)
    except ValueError as exc:
        log.error("Marker json conversion: %s", exc)
        return {}
    return data if isinstance(data, dict) else {fallback_key: text}


def is_ayon_marker(marker: Any, name: str = MARKER_NAME) -> bool:
    """Tell whether the marker name contains `name` (`AYONData`)."""
    return name in (marker.name or "")


def create_ayon_marker(
    data: Mapping[str, Any],
    marked_range: Optional["otio.opentime.TimeRange"] = None,
    color: Optional[str] = None,
    name: str = MARKER_NAME,
    flat: bool = False,
) -> "otio.schema.Marker":
    """Create an `AYONData` marker holding creator data.

    Args:
        data: Creator data, e.g. `{"clip_index": "abc"}`.
        marked_range: Range of the marker, none for a point marker.
        color: An `otio.schema.MarkerColor` name.
        name: Marker name.
        flat: Write the data as the metadata (Flame, Resolve shape)
            instead of under `json_metadata` (Hiero shape).
    """
    metadata = (
        dict(data) if flat else {JSON_METADATA_KEY: encode_marker_data(data)}
    )
    kwargs: Dict[str, Any] = {"name": name, "metadata": metadata}
    if marked_range is not None:
        kwargs["marked_range"] = marked_range
    if color is not None:
        kwargs["color"] = color
    return otio.schema.Marker(**kwargs)


def find_clip_by_index(
    otio_timeline: Any,
    clip_index: Any,
    marker_name: Optional[str] = None,
    unwrap: Optional[Callable[[Any], Any]] = None,
) -> Tuple[Optional[Any], Optional[Any]]:
    """Find the clip whose marker has the given `clip_index`.

    Args:
        otio_timeline: `Timeline` or composition to search.
        clip_index: Value to match, compared as is.
        marker_name: Only look at markers whose name contains this
            (`MARKER_NAME` for Flame); every marker when None.
        unwrap: Applied to each marker before it is read; the Resolve
            marker unwrap.

    Returns:
        tuple: `(clip, marker)`, or `(None, None)`. The marker is the one
            `unwrap` returned.
    """
    for otio_clip in find_clips(otio_timeline):
        for marker in otio_clip.markers:
            if marker_name and not is_ayon_marker(marker, marker_name):
                continue
            if unwrap is not None:
                marker = unwrap(marker)
            data = decode_marker_data(marker.metadata)
            if data and data.get("clip_index") == clip_index:
                return otio_clip, marker
    return None, None
