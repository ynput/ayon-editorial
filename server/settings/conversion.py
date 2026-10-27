"""Conversion of settings overrides stored by older addon versions.

Add one `_convert_<what>_<version>` function per breaking settings change
and call it from `convert_settings_overrides`.
"""
from typing import Any


def convert_settings_overrides(
    source_version: str,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    """Convert overrides in place and return them.

    Args:
        source_version: Addon version that stored the overrides.
        overrides: Stored overrides.

    Returns:
        dict[str, Any]: The converted overrides.

    """
    return overrides
