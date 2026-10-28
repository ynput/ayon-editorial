"""Install OpenTimelineIO into a host's own Python before it launches.

Replaces the per host copies of the OTIO pre-launch hook. This is a mixin
and not a `PreLaunchHook` subclass on purpose: `ayon_applications` collects
every `PreLaunchHook` subclass found in a hook module, imported ones
included. A shared base with empty `app_groups` would then run for every
application. A host hook is declared as
`class X(OTIOInstallHookMixin, PreLaunchHook)` and its module imports
only the mixin.

Only the standard library is imported at module level.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from typing import Mapping, MutableMapping, Optional, Tuple

OTIO_DEFAULT_REQUIREMENT = "opentimelineio>=0.15,<0.18"
OTIO_DEFAULT_MIN_VERSION = (0, 15)

_VERSION_RE = re.compile(r"\s*(\d+(?:\.\d+)*)")
_VERSION_SCRIPT = "import opentimelineio as o;print(o.__version__)"


def parse_version(text: str) -> Tuple[int, ...]:
    """Parse the leading numeric part of a version string.

    Args:
        text: Version such as `0.17.0` or `0.16.0.dev1`.

    Returns:
        tuple[int, ...]: Numbers of the version, empty when unparsable.
    """
    match = _VERSION_RE.match(text or "")
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def get_otio_version(
    python_exe: str,
    env: Optional[Mapping[str, str]],
    timeout: float = 60,
) -> Optional[Tuple[int, ...]]:
    """Get the OpenTimelineIO version importable by a Python executable.

    Args:
        python_exe: Python executable to ask.
        env: Environment to run it with.
        timeout: Seconds to wait.

    Returns:
        Optional[tuple[int, ...]]: Version, or None when the import fails,
            times out or prints nothing parsable. Never raises.
    """
    try:
        result = subprocess.run(
            [python_exe, "-c", _VERSION_SCRIPT],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    lines = (result.stdout or "").strip().splitlines()
    version = parse_version(lines[-1]) if lines else ()
    return version or None


def prepend_pythonpath(env: MutableMapping[str, str], path: str) -> None:
    """Put a path first in `PYTHONPATH` of an environment.

    Works for an unset or empty `PYTHONPATH` and never duplicates `path`.

    Args:
        env: Environment to change.
        path: Directory to put first.
    """
    entries = [
        entry
        for entry in env.get("PYTHONPATH", "").split(os.pathsep)
        if entry and entry != path
    ]
    env["PYTHONPATH"] = os.pathsep.join([path] + entries)


def install_otio(
    python_exe: str,
    target: str,
    requirement: str,
    env: Optional[Mapping[str, str]],
    index_url: Optional[str] = None,
    timeout: float = 900,
) -> bool:
    """Install OpenTimelineIO into a folder with pip.

    Args:
        python_exe: Python executable that runs pip.
        target: Folder to install into.
        requirement: Requirement specifier to install.
        env: Environment to run pip with.
        index_url: Optional package index URL.
        timeout: Seconds to wait.

    Returns:
        bool: True when pip exited with code 0. Never raises.
    """
    cmd = [
        python_exe, "-m", "pip", "install", "--upgrade",
        "--target", target, requirement,
    ]
    if index_url:
        cmd.extend(["--index-url", index_url])
    try:
        result = subprocess.run(cmd, env=env, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


class OTIOInstallHookMixin:
    """Pre-launch hook behaviour that installs OpenTimelineIO.

    Mix it in before `PreLaunchHook` so this `execute` wins. The host
    hook sets `settings_category` and `resources_addon_name` and
    implements `get_python_executable`. The class name of the host hook is
    the settings key `hooks/<ClassName>/enabled`.
    """

    settings_category: str
    resources_addon_name: str

    otio_requirement = OTIO_DEFAULT_REQUIREMENT
    otio_min_version = OTIO_DEFAULT_MIN_VERSION
    otio_index_url: Optional[str] = None

    def get_python_executable(self) -> Optional[str]:
        """Get the Python executable used to run the host."""
        raise NotImplementedError

    def get_site_packages_dir(self, python_exe: str) -> str:
        """Get the folder OpenTimelineIO is installed into.

        Args:
            python_exe: Host Python executable, hashed into the path.

        Returns:
            str: Folder in the addons resources dir.
        """
        from ayon_core.lib import get_addons_resources_dir

        path_hash = hashlib.sha256(python_exe.encode()).hexdigest()
        return get_addons_resources_dir(
            self.resources_addon_name,
            "otio_prehook",
            path_hash[:16],
        )

    def execute(self) -> None:
        """Install OpenTimelineIO when enabled in project settings.

        The install is not crucial: any error is logged as a warning.
        """
        try:
            if not self._is_enabled():
                return
            self.inner_execute()
        except Exception:
            self.log.warning(
                f"Processing of '{type(self).__name__}' crashed.",
                exc_info=True,
            )

    def inner_execute(self) -> None:
        """Check for OpenTimelineIO and install it when missing."""
        self.log.debug("Check for OpenTimelineIO installation.")
        python_exe = self.get_python_executable()
        if not python_exe:
            self.log.warning("Host python executable not found.")
            return

        env = self.launch_context.env
        if self._has_otio(python_exe, env):
            self.log.info("OpenTimelineIO is installed within host env.")
            return

        site_dir = self.get_site_packages_dir(python_exe)
        os.makedirs(site_dir, exist_ok=True)
        prepend_pythonpath(env, site_dir)
        if self._has_otio(python_exe, env):
            self.log.info(
                f"OpenTimelineIO is installed within '{site_dir}'.")
            return

        install_otio(
            python_exe,
            site_dir,
            self.otio_requirement,
            env,
            self.otio_index_url,
        )
        if self._has_otio(python_exe, env):
            self.log.info(
                "OpenTimelineIO is installed now and ready to be used.")
            return

        self.log.warning(
            f"Failed to install '{self.otio_requirement}' with python "
            f"'{python_exe}' into '{site_dir}'."
        )

    def _has_otio(self, python_exe: str, env) -> bool:
        version = get_otio_version(python_exe, env)
        return version is not None and version >= tuple(
            self.otio_min_version)

    def _is_enabled(self) -> bool:
        """Read the hook switch from settings, missing keys mean enabled."""
        value = self.data.get("project_settings", {})
        for key in (
            self.settings_category, "hooks", type(self).__name__, "enabled"
        ):
            if not isinstance(value, Mapping) or key not in value:
                return True
            value = value[key]
        return bool(value)
