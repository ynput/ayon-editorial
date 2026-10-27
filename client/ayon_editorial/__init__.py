"""DCC-agnostic editorial (OpenTimelineIO) library for AYON host addons."""
from .version import __version__
from .addon import (
    EDITORIAL_ADDON_ROOT,
    EditorialAddon,
)


__all__ = (
    "__version__",

    "EDITORIAL_ADDON_ROOT",
    "EditorialAddon",
)
