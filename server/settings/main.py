"""Settings of the editorial addon (settings category `editorial`)."""
from typing import Any

from ayon_server.settings import BaseSettingsModel

DEFAULT_VALUES: dict[str, Any] = {}


class EditorialSettings(BaseSettingsModel):
    """Editorial settings.

    Empty for now: editorial creator and publish settings stay in each
    host addon. Add a field here only for behaviour that is shared by
    every host.
    """
