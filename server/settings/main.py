"""Settings of the editorial addon (settings category `editorial`)."""
from typing import Any

from ayon_server.settings import BaseSettingsModel, SettingsField

from .create_plugins import DEFAULT_CREATE_VALUES, EditorialCreateModel

DEFAULT_VALUES: dict[str, Any] = {
    "create": DEFAULT_CREATE_VALUES,
}


class EditorialSettings(BaseSettingsModel):
    """Editorial settings, shared by every editorial host.

    Add a field here only for behaviour that is shared by every host.
    """

    create: EditorialCreateModel = SettingsField(
        default_factory=EditorialCreateModel,
        title="Creator plugins",
    )
