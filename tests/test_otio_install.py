"""Tests of the shared OpenTimelineIO install hook mixin.

The module is loaded from its file: importing the `ayon_editorial`
package would import `ayon_core` through `addon.py`.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parent.parent
    / "client" / "ayon_editorial" / "lib" / "otio_install.py"
)


def _load():
    spec = importlib.util.spec_from_file_location(
        "otio_install_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


oi = _load()
RUN = "subprocess.run"


def _proc(code=0, stdout=""):
    return SimpleNamespace(returncode=code, stdout=stdout)


@pytest.mark.parametrize("text, expected", [
    ("0.17.0", (0, 17, 0)),
    ("0.16.0.dev1", (0, 16, 0)),
    ("0.15", (0, 15)),
    (" 0.17.1\n", (0, 17, 1)),
    ("", ()),
    ("garbage", ()),
    ("v0.17", ()),
])
def test_parse_version(text, expected):
    assert oi.parse_version(text) == expected


def test_prepend_pythonpath_unset():
    env = {}
    oi.prepend_pythonpath(env, "/a")
    assert env["PYTHONPATH"] == "/a"


def test_prepend_pythonpath_empty():
    env = {"PYTHONPATH": ""}
    oi.prepend_pythonpath(env, "/a")
    assert env["PYTHONPATH"] == "/a"


def test_prepend_pythonpath_set_and_repeated():
    env = {"PYTHONPATH": os.pathsep.join(["/b", "/c"])}
    oi.prepend_pythonpath(env, "/a")
    assert env["PYTHONPATH"] == os.pathsep.join(["/a", "/b", "/c"])
    oi.prepend_pythonpath(env, "/a")
    assert env["PYTHONPATH"] == os.pathsep.join(["/a", "/b", "/c"])
    oi.prepend_pythonpath(env, "/c")
    assert env["PYTHONPATH"] == os.pathsep.join(["/c", "/a", "/b"])


def test_get_otio_version_success():
    with mock.patch(RUN, return_value=_proc(0, "0.17.0\n")) as run:
        assert oi.get_otio_version("py", {"A": "1"}) == (0, 17, 0)
    args, kwargs = run.call_args
    assert args[0] == [
        "py", "-c", "import opentimelineio as o;print(o.__version__)"]
    assert kwargs["env"] == {"A": "1"}
    assert kwargs["capture_output"] is True


@pytest.mark.parametrize("effect", [
    _proc(1, "0.17.0"),
    subprocess.TimeoutExpired("py", 1),
    OSError("nope"),
    _proc(0, "not a version"),
    _proc(0, ""),
])
def test_get_otio_version_failures(effect):
    kwargs = (
        {"side_effect": effect}
        if isinstance(effect, Exception) else {"return_value": effect}
    )
    with mock.patch(RUN, **kwargs):
        assert oi.get_otio_version("py", {}) is None


def test_install_otio_command():
    with mock.patch(RUN, return_value=_proc(0)) as run:
        assert oi.install_otio("py", "/t", "otio>=1", {"A": "1"})
    assert run.call_args[0][0] == [
        "py", "-m", "pip", "install", "--upgrade",
        "--target", "/t", "otio>=1",
    ]


def test_install_otio_index_url():
    with mock.patch(RUN, return_value=_proc(0)) as run:
        assert oi.install_otio("py", "/t", "r", {}, index_url="http://i")
    assert run.call_args[0][0][-2:] == ["--index-url", "http://i"]


@pytest.mark.parametrize("effect", [
    _proc(1),
    OSError("x"),
    subprocess.TimeoutExpired("py", 1),
])
def test_install_otio_failure(effect):
    kwargs = (
        {"side_effect": effect}
        if isinstance(effect, Exception) else {"return_value": effect}
    )
    with mock.patch(RUN, **kwargs):
        assert oi.install_otio("py", "/t", "r", {}) is False


class FakeHook(oi.OTIOInstallHookMixin):
    settings_category = "fake"
    resources_addon_name = "ayon_fake"
    site_dir = ""
    python_exe = "py"

    def __init__(self, env, settings=None):
        self.launch_context = SimpleNamespace(env=env)
        self.data = {}
        if settings is not None:
            self.data["project_settings"] = settings
        self.log = logging.getLogger("fake-hook")

    def get_python_executable(self):
        return self.python_exe

    def get_site_packages_dir(self, python_exe):
        return self.site_dir


@pytest.fixture
def hook_cls(tmp_path):
    return type(
        "FakeHook", (FakeHook,), {"site_dir": str(tmp_path / "site")})


def _version_calls(run):
    return [c for c in run.call_args_list if c[0][0][1] == "-c"]


def _pip_calls(run):
    return [c for c in run.call_args_list if c[0][0][1] == "-m"]


def test_flow_already_installed(hook_cls):
    env = {}
    with mock.patch(RUN, return_value=_proc(0, "0.17.0")) as run:
        hook_cls(env).execute()
    assert run.call_count == 1
    assert "PYTHONPATH" not in env


def test_flow_too_old_is_missing(hook_cls):
    env = {}
    with mock.patch(RUN, return_value=_proc(0, "0.14.1")) as run:
        hook_cls(env).execute()
    assert len(_pip_calls(run)) == 1


def test_flow_installed_in_custom_folder(hook_cls):
    env = {"PYTHONPATH": "/x"}
    results = [_proc(1), _proc(0, "0.16.0")]
    with mock.patch(RUN, side_effect=results) as run:
        hook_cls(env).execute()
    assert run.call_count == 2
    assert not _pip_calls(run)
    assert env["PYTHONPATH"] == os.pathsep.join([hook_cls.site_dir, "/x"])
    assert os.path.isdir(hook_cls.site_dir)


def test_flow_full_install(hook_cls):
    env = {}
    results = [_proc(1), _proc(1), _proc(0), _proc(0, "0.17.0")]
    with mock.patch(RUN, side_effect=results) as run:
        hook_cls(env).execute()
    kinds = [c[0][0][1] for c in run.call_args_list]
    assert kinds == ["-c", "-c", "-m", "-c"]
    pip_cmd = run.call_args_list[2][0][0]
    assert pip_cmd[:4] == ["py", "-m", "pip", "install"]
    assert hook_cls.site_dir in pip_cmd
    assert oi.OTIO_DEFAULT_REQUIREMENT in pip_cmd
    assert env["PYTHONPATH"] == hook_cls.site_dir


def test_flow_install_failure_only_warns(hook_cls, caplog):
    results = [_proc(1), _proc(1), _proc(1), _proc(1)]
    with caplog.at_level(logging.WARNING, logger="fake-hook"):
        with mock.patch(RUN, side_effect=results):
            hook_cls({}).execute()
    text = caplog.text
    assert "py" in text
    assert hook_cls.site_dir in text
    assert oi.OTIO_DEFAULT_REQUIREMENT in text


def test_flow_exception_is_swallowed(hook_cls, caplog):
    with mock.patch(RUN, side_effect=ValueError("boom")):
        with mock.patch.object(
            hook_cls, "get_site_packages_dir", side_effect=KeyError("k")
        ):
            hook_cls({}).execute()
    assert "crashed" in caplog.text


def test_flow_settings_disabled(hook_cls):
    settings = {"fake": {"hooks": {"FakeHook": {"enabled": False}}}}
    with mock.patch(RUN) as run:
        hook_cls({}, settings).execute()
    run.assert_not_called()


@pytest.mark.parametrize("settings", [
    None,
    {},
    {"fake": {}},
    {"fake": {"hooks": {}}},
    {"fake": {"hooks": {"FakeHook": {}}}},
    {"fake": {"hooks": {"FakeHook": {"enabled": True}}}},
])
def test_flow_settings_enabled(hook_cls, settings):
    with mock.patch(RUN, return_value=_proc(0, "0.17.0")) as run:
        hook_cls({}, settings).execute()
    assert run.call_count == 1


def test_flow_no_python_executable(hook_cls):
    hook_cls.python_exe = None
    with mock.patch(RUN) as run:
        hook_cls({}).execute()
    run.assert_not_called()


def test_flow_pythonpath_unset_contains_site_dir(hook_cls):
    env = {}
    with mock.patch(RUN, return_value=_proc(1)):
        hook_cls(env).execute()
    assert hook_cls.site_dir in env["PYTHONPATH"].split(os.pathsep)


def test_mixin_is_not_a_launch_hook():
    modules = {
        c.__module__.split(".")[0] for c in oi.OTIOInstallHookMixin.__mro__
    }
    assert modules == {"otio_install_under_test", "builtins"}


def test_import_does_not_pull_ayon_modules():
    code = textwrap.dedent(f"""
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location(
            "otio_install", {str(MODULE_PATH)!r})
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        bad = [
            m for m in sys.modules
            if m.split(".")[0] in ("ayon_core", "ayon_applications")
        ]
        assert not bad, bad
    """)
    result = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
