"""Clip creator settings shared by every editorial host.

One unified attribute set, chosen per host and task type by profiles. The
keys are the pre-create attribute keys of the clip creators, so a profile
is the creator's preset as it is.
"""
from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    task_types_enum,
)


def clip_creator_overrides_enum() -> list[dict[str, str]]:
    """Attributes the artist may change in the clip creator."""
    return [
        {"value": "hierarchy", "label": "Shot parent hierarchy"},
        {"value": "useShotName", "label": "Use shot name (Flame)"},
        {"value": "clipRename", "label": "Rename clips"},
        {"value": "clipName", "label": "Clip name template"},
        {"value": "segmentIndex", "label": "Accept segment order (Flame)"},
        {"value": "countFrom", "label": "Count sequence from"},
        {"value": "countSteps", "label": "Stepping number"},
        {"value": "folder", "label": "{folder}"},
        {"value": "episode", "label": "{episode}"},
        {"value": "sequence", "label": "{sequence}"},
        {"value": "track", "label": "{track}"},
        {"value": "shot", "label": "{shot}"},
        {"value": "vSyncOn", "label": "Enable vertical sync"},
        {"value": "clipVariant", "label": "Product variant"},
        {"value": "plate_product_type", "label": "Plate product type"},
        {"value": "reviewableSource", "label": "Reviewable source"},
        {"value": "export_audio", "label": "Include audio"},
        {"value": "sourceResolution", "label": "Source resolution"},
        {"value": "workfileFrameStart", "label": "Workfile start frame"},
        {"value": "handleStart", "label": "Handle start (head)"},
        {"value": "handleEnd", "label": "Handle end (tail)"},
        {"value": "includeHandles", "label": "Include handles"},
        {"value": "retimedHandles", "label": "Retimed handles"},
        {"value": "retimedFramerange", "label": "Retimed shot frame range"},
    ]


ALL_OVERRIDES = [item["value"] for item in clip_creator_overrides_enum()]


class ClipCreatorProfile(BaseSettingsModel):
    """Preset of the clip creator for some hosts and task types."""

    _layout = "expanded"
    host_names: list[str] = SettingsField(
        default_factory=list,
        title="Host names",
        description="Empty matches every host.",
    )
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum,
    )
    overrides: list[str] = SettingsField(
        default_factory=lambda: list(ALL_OVERRIDES),
        title="Artist can change",
        enum_resolver=clip_creator_overrides_enum,
        description=(
            "Attributes shown in the creator. The others are taken from"
            " this profile and hidden."
        ),
    )

    # Shot hierarchy and naming
    hierarchy: str = SettingsField(
        "{folder}/{sequence}", title="Shot parent hierarchy",
        section="Shot Hierarchy And Rename Settings",
    )
    useShotName: bool = SettingsField(
        False, title="Use shot name (Flame)",
    )
    clipRename: bool = SettingsField(True, title="Rename clips")
    clipName: str = SettingsField(
        "{track}{sequence}{shot}", title="Clip name template",
    )
    segmentIndex: bool = SettingsField(
        False, title="Accept segment order (Flame)",
    )
    countFrom: int = SettingsField(10, title="Count sequence from")
    countSteps: int = SettingsField(10, title="Stepping number")

    # Shot template keys
    folder: str = SettingsField(
        "shots", title="{folder}", section="Shot Template Keys",
    )
    episode: str = SettingsField("ep01", title="{episode}")
    sequence: str = SettingsField("sq01", title="{sequence}")
    track: str = SettingsField("{_track_}", title="{track}")
    shot: str = SettingsField("sh###", title="{shot}")

    # Vertical sync and products
    vSyncOn: bool = SettingsField(
        False, title="Enable vertical sync",
        section="Vertical Synchronization And Products",
    )
    clip_variants: list[str] = SettingsField(
        default_factory=lambda: [
            "<track_name>", "main", "bg", "fg", "animatic"
        ],
        title="Product variants",
        description="`<track_name>` is replaced by the clip's track name.",
    )
    plate_product_types: list[str] = SettingsField(
        default_factory=list,
        title="Plate product types",
        description="Empty gives `plate`.",
    )
    reviewTrackRegexPattern: str = SettingsField(
        "<track_name>_ref", title="Review track pattern",
    )
    export_audio: bool = SettingsField(False, title="Include audio")
    sourceResolution: bool = SettingsField(
        False, title="Source resolution",
    )

    # Frame ranges and retimes
    workfileFrameStart: int = SettingsField(
        1001, title="Workfile start frame",
        section="Frame Ranges And Retimes",
    )
    handleStart: int = SettingsField(10, title="Handle start (head)")
    handleEnd: int = SettingsField(10, title="Handle end (tail)")
    includeHandles: bool = SettingsField(
        False, title="Include handles",
        description="The workfile start frame includes the head handle.",
    )
    retimedHandles: bool = SettingsField(
        True, title="Retimed handles",
        description="Handles follow the clip speed.",
    )
    retimedFramerange: bool = SettingsField(
        True, title="Retimed shot frame range",
        description="The shot frame range is the retimed source length.",
    )


class CreateShotClipModel(BaseSettingsModel):
    """Clip creator of every editorial host."""

    profiles: list[ClipCreatorProfile] = SettingsField(
        default_factory=list,
        title="Profiles",
        description=(
            "The most specific matching profile wins. Without a match the"
            " creator uses the defaults of a profile."
        ),
    )


class EditorialCreateModel(BaseSettingsModel):
    CreateShotClip: CreateShotClipModel = SettingsField(
        default_factory=CreateShotClipModel,
        title="Create Publishable Clip",
    )


# Each host's defaults before the MVP, so nothing changes for a studio
# without overrides.
DEFAULT_CREATE_VALUES = {
    "CreateShotClip": {
        "profiles": [
            {
                "host_names": ["hiero"],
                "task_types": [],
                "overrides": list(ALL_OVERRIDES),
                "hierarchy": "{folder}/{sequence}",
                "useShotName": False,
                "clipRename": True,
                "clipName": "{track}{sequence}{shot}",
                "segmentIndex": False,
                "countFrom": 10,
                "countSteps": 10,
                "folder": "shots",
                "episode": "ep01",
                "sequence": "sq01",
                "track": "{_track_}",
                "shot": "sh###",
                "vSyncOn": False,
                "clip_variants": [
                    "<track_name>", "main", "bg", "fg", "animatic"
                ],
                "plate_product_types": [],
                "reviewTrackRegexPattern": "<track_name>_ref",
                "export_audio": False,
                "sourceResolution": False,
                "workfileFrameStart": 1001,
                "handleStart": 10,
                "handleEnd": 10,
                "includeHandles": False,
                "retimedHandles": True,
                "retimedFramerange": True,
            },
            {
                "host_names": ["flame"],
                "task_types": [],
                "overrides": list(ALL_OVERRIDES),
                "hierarchy": "{folder}/{sequence}",
                "useShotName": True,
                "clipRename": False,
                "clipName": "{sequence}{shot}",
                "segmentIndex": True,
                "countFrom": 10,
                "countSteps": 10,
                "folder": "shots",
                "episode": "ep01",
                "sequence": "a",
                "track": "{_track_}",
                "shot": "####",
                "vSyncOn": False,
                "clip_variants": [
                    "<track_name>", "main", "bg", "fg", "animatic"
                ],
                "plate_product_types": [],
                "reviewTrackRegexPattern": "<track_name>_ref",
                "export_audio": False,
                "sourceResolution": False,
                "workfileFrameStart": 1001,
                "handleStart": 5,
                "handleEnd": 5,
                "includeHandles": False,
                "retimedHandles": True,
                "retimedFramerange": True,
            },
        ],
    },
}
