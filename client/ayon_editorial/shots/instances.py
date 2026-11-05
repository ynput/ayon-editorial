"""Shot, plate and audio sub-instance data of one clip.

Replaces the instance loop of `CreateShotClip.create` in the Hiero and
Flame addons. The host creates the instances from the returned data, in
the returned order (shot first), and links each child to the stored shot
instance with `link_parent_instance`.
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Dict, Mapping

from .clip import ClipInfo
from .retime import RetimeOptions

__all__ = ["build_clip_instances", "link_parent_instance", "shot_label"]

log = logging.getLogger(__name__)

SHOT_PRODUCT_NAME = "shotMain"
AUDIO_PRODUCT_NAME = "audioMain"


def shot_label(solution_data: Mapping[str, Any]) -> str:
    """Label of the shot instance, e.g. `/shots/sq01/sh010 shotMain`."""
    return f"{solution_data['folderPath']} {SHOT_PRODUCT_NAME}"


def link_parent_instance(
    child_data: Dict[str, Any], parent_stored_data: Mapping[str, Any]
) -> None:
    """Link a plate or audio instance data to its stored shot instance.

    Sets `parent_instance_id` (the id exists only once the host created
    the shot instance) and the `parentInstance` label, in place.

    Args:
        child_data: Data from `build_clip_instances`.
        parent_stored_data: `data_to_store()` of the shot instance, or any
            mapping with `instance_id` and `label`.
    """
    child_data["parent_instance_id"] = parent_stored_data["instance_id"]
    attributes = child_data.setdefault("creator_attributes", {})
    attributes["parentInstance"] = parent_stored_data["label"]


def build_clip_instances(
    solution_data: Mapping[str, Any],
    clip: ClipInfo,
    pre_create_data: Mapping[str, Any],
    creator_ids: Mapping[str, str],
) -> Dict[str, Dict[str, Any]]:
    """Build the sub-instance data of one clip.

    The shot instance exists only for a hero track clip; the audio
    instance only for a hero track clip with `export_audio`; the plate
    instance for every clip. A plate or audio instance of a clip that has
    no shot instance links to the shot instance of its folder, which the
    host remembers from the hero clip (vertical sync sorts it first).

    Args:
        solution_data: What the shot solver returns for the clip: the
            publish tag data (`hierarchy`, `parents`, `hierarchyData`,
            `folderPath`, `folderName`, `productName`, `productType`,
            `productBaseType`, `variant`, `heroTrack`, review keys) and the
            copied pre-create keys.
        clip: The clip as the host read it.
        pre_create_data: Pre-create values, hidden ones filled.
        creator_ids: Host creator identifiers under `shot`, `plate`,
            `audio`.

    Returns:
        Instance data by creator identifier, in creation order. Plate and
        audio data lack `parent_instance_id` (`link_parent_instance`).
    """
    base = copy.deepcopy(dict(solution_data))
    base["clip_index"] = clip.uid
    base.setdefault("task", None)
    hero = bool(base.get("heroTrack", False))
    folder_path = base["folderPath"]

    result: Dict[str, Dict[str, Any]] = {}
    if hero:
        result[creator_ids["shot"]] = _shot_data(
            base, clip, pre_create_data)

    plate = copy.deepcopy(base)
    _plate_data(plate, pre_create_data, folder_path)
    result[creator_ids["plate"]] = plate

    if hero and pre_create_data.get("export_audio", False):
        audio = copy.deepcopy(base)
        _audio_data(audio, folder_path)
        result[creator_ids["audio"]] = audio
    return result


def _shot_data(
    base: Mapping[str, Any],
    clip: ClipInfo,
    pre_create_data: Mapping[str, Any],
) -> Dict[str, Any]:
    data = copy.deepcopy(dict(base))
    attributes = data.setdefault("creator_attributes", {})
    workfile_start = _first(
        data.get("workfileFrameStart"),
        pre_create_data.get("workfileFrameStart"),
        default=1001,
    )
    options = RetimeOptions.from_data(pre_create_data)
    attributes.update({
        "workfileFrameStart": workfile_start,
        "handleStart": _first(
            data.get("handleStart"), pre_create_data.get("handleStart"),
            default=0,
        ),
        "handleEnd": _first(
            data.get("handleEnd"), pre_create_data.get("handleEnd"),
            default=0,
        ),
        "frameStart": workfile_start,
        "frameEnd": workfile_start + clip.duration,
        "clipIn": int(clip.timeline_in),
        "clipOut": int(clip.timeline_out),
        "clipDuration": clip.duration,
        "sourceIn": int(clip.source_in),
        "sourceOut": int(clip.source_out),
        "useSourceResolution": bool(_first(
            data.get("sourceResolution"),
            pre_create_data.get("sourceResolution"),
            default=False,
        )),
        **options.to_attributes(),
    })
    data.update({
        "variant": "main",
        "productType": "shot",
        "productBaseType": "shot",
        "productName": SHOT_PRODUCT_NAME,
        "label": shot_label(data),
    })
    return data


def _plate_data(
    data: Dict[str, Any],
    pre_create_data: Mapping[str, Any],
    folder_path: str,
) -> None:
    attributes = data.setdefault("creator_attributes", {})
    data.update({
        "productType": (
            pre_create_data.get("plate_product_type") or "plate"),
        "productBaseType": "plate",
        "label": f"{folder_path} {data['productName']}",
    })
    if data.get("reviewableSource"):
        attributes.update({
            "review": True,
            "reviewableSource": data["reviewableSource"],
        })


def _audio_data(data: Dict[str, Any], folder_path: str) -> None:
    attributes = data.setdefault("creator_attributes", {})
    data.update({
        "variant": "main",
        "productType": "audio",
        "productBaseType": "audio",
        "productName": AUDIO_PRODUCT_NAME,
        "label": f"{folder_path} {AUDIO_PRODUCT_NAME}",
    })
    if data.get("reviewableSource"):
        attributes["review"] = True


def _first(*values: Any, default: Any) -> Any:
    """First value that is not None."""
    for value in values:
        if value is not None:
            return value
    return default
