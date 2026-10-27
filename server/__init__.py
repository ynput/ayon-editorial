"""Server side of the editorial addon."""
from typing import Any, Type

from ayon_server.addons import BaseServerAddon

from .settings import (
    DEFAULT_VALUES,
    EditorialSettings,
    convert_settings_overrides,
)


class EditorialAddon(BaseServerAddon):
    """Editorial addon with its (empty for now) project settings."""

    settings_model: Type[EditorialSettings] = EditorialSettings

    async def get_default_settings(self):
        """Return default settings."""
        settings_model_cls = self.get_settings_model()
        return settings_model_cls(**DEFAULT_VALUES)

    async def convert_settings_overrides(
        self,
        source_version: str,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert overrides stored by older versions of this addon."""
        convert_settings_overrides(source_version, overrides)
        return await super().convert_settings_overrides(
            source_version, overrides
        )
