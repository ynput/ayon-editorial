"""AYON addon definition of the editorial library.

Imported by the launcher at startup: keep imports light. Never import
OpenTimelineIO, Qt or a host API here.
"""
import os

from ayon_core.addon import AYONAddon

from .version import __version__

EDITORIAL_ADDON_ROOT = os.path.dirname(os.path.abspath(__file__))


class EditorialAddon(AYONAddon):
    """Shared editorial code used by editorial host addons.

    Not a host: it has no application, launch hooks or plugins of its own.
    Host addons import from `ayon_editorial` and declare `editorial` in
    `ayon_required_addons` of their `package.py`.
    """

    name = "editorial"
    version = __version__
