"""Compare the Flame OTIO export before and after the editorial builder.

Run it in Flame's Python console (Shift+F2 > Python) with AYON running
(so `ayon_flame`, `ayon_core` and `ayon_editorial` are importable):

    exec(open("/path/to/tests/host/flame_check.py").read())
    # or: import runpy; runpy.run_path("/path/to/tests/host/flame_check.py")

Select a sequence (or a segment of it) in the media panel or timeline
first. The script exports it with the new `ayon_flame.otio.flame_export`
and with the old one (`develop-minor`), compares both with
`ayon_editorial.otio.compare.compare_timelines` and prints `OK` or the
differences. It writes nothing to the Flame project.

The old export comes from the git ref `OLD_REF` of the host checkout
`HOST_REPO` (empty: the checkout `ayon_flame` is loaded from), or from the
directory `OLD_OTIO_DIR` when you have the old `otio/` folder yourself
(a `git worktree add <dir> origin/develop-minor` gives
`<dir>/client/ayon_flame/otio`).
"""
import importlib
import importlib.util
import os
import subprocess
import sys
import tempfile

# --- settings ---------------------------------------------------------------
OLD_OTIO_DIR = ""  # directory with the OLD otio/ package files, or empty
HOST_REPO = ""  # host checkout for `git show`, empty: where ayon_flame is
OLD_REF = "origin/develop-minor"
# ----------------------------------------------------------------------------

OLD_FILES = ("__init__.py", "flame_export.py", "tw_bake.py", "utils.py")


def _old_otio_dir():
    if OLD_OTIO_DIR:
        return OLD_OTIO_DIR
    import ayon_flame

    repo = HOST_REPO or os.path.dirname(
        os.path.dirname(os.path.dirname(ayon_flame.__file__))
    )
    target = tempfile.mkdtemp(prefix="flame_check_old_")
    for name in OLD_FILES:
        out = subprocess.check_output(
            [
                "git", "-C", repo, "show",
                f"{OLD_REF}:client/ayon_flame/otio/{name}",
            ]
        )
        with open(os.path.join(target, name), "wb") as stream:
            stream.write(out)
    return target


def _load_old_export():
    """Import the old otio package under another name.

    Its relative imports (`tw_bake`, `utils`) resolve inside the copy;
    `ayon_flame.api` and `ayon_core` are the live ones.
    """
    directory = _old_otio_dir()
    name = "ayon_flame_old_otio"
    spec = importlib.util.spec_from_file_location(
        name,
        os.path.join(directory, "__init__.py"),
        submodule_search_locations=[directory],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[name] = package
    spec.loader.exec_module(package)
    return importlib.import_module(f"{name}.flame_export")


def _selection():
    import flame

    selection = list(flame.media_panel.selected_entries or [])
    return selection or [flame.timeline.current_segment]


def run():
    import ayon_flame.api as ayfapi
    from ayon_editorial.otio.compare import (
        compare_timelines,
        format_differences,
    )
    from ayon_flame.otio import flame_export as new_export

    sequence = ayfapi.get_current_sequence(_selection())
    if sequence is None:
        print("No sequence: select a sequence or one of its segments.")
        return None
    print(f"Sequence: {sequence.name.get_value()}")

    old_export = _load_old_export()
    results = {}
    for label, module in (("old", old_export), ("new", new_export)):
        aggregator = ayfapi.ValidationAggregator()
        with ayfapi.maintained_segment_selection(sequence):
            results[label] = module.create_otio_timeline(
                sequence, validation_aggregator=aggregator
            )

    diffs = compare_timelines(results["old"], results["new"])
    if diffs:
        print(format_differences(diffs))
    else:
        print("OK")
    return diffs


DIFFS = run()
