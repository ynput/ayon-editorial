"""Checks of `.github/roadmap.yml`, the source of the roadmap issues."""
import importlib.util
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / ".github" / "roadmap.yml"
SYNC_PATH = ROOT / "tools" / "roadmap_sync.py"

TIERS = {"light", "standard", "deep", "main", "human"}
PRIORITIES = {"High", "Medium", "Low", "Very low"}
STATUSES = {"Backlog", "Ready", "In progress", "In review", "Blocked", "Done"}


def _load_sync_module():
    spec = importlib.util.spec_from_file_location("roadmap_sync", SYNC_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def sync():
    return _load_sync_module()


@pytest.fixture(scope="module")
def manifest():
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def entries(sync, manifest):
    return sync.load_entries(manifest)


def test_ids_are_unique(entries):
    ids = [entry["id"] for entry in entries]
    duplicates = {i for i in ids if ids.count(i) > 1}
    assert not duplicates, f"Duplicate step IDs: {sorted(duplicates)}"


def test_step_ids_match_their_phase(manifest):
    for phase in manifest["phases"]:
        for step in phase["steps"]:
            assert re.fullmatch(rf"{phase['id']}\.\d+", step["id"]), (
                f"Step {step['id']} is not numbered under {phase['id']}"
            )


def test_fields_have_known_values(sync, entries):
    for entry in entries:
        assert entry["kind"] in sync.ISSUE_TYPES, entry["id"]
        assert entry["tier"] in TIERS, entry["id"]
        assert entry["priority"] in PRIORITIES, entry["id"]
        assert entry.get("status", "Backlog") in STATUSES, entry["id"]
        assert entry.get("goal"), f"{entry['id']} has no goal"


def test_dependencies_exist_and_have_no_cycle(entries):
    by_id = {entry["id"]: entry for entry in entries}
    for entry in entries:
        for dep in entry.get("depends") or []:
            assert dep in by_id, f"{entry['id']} depends on unknown {dep}"

    def visit(step_id, path):
        assert step_id not in path, f"Dependency cycle: {path + [step_id]}"
        for dep in by_id[step_id].get("depends") or []:
            visit(dep, path + [step_id])

    for entry in entries:
        visit(entry["id"], [])


def test_every_body_renders_without_unresolved_placeholders(
    sync, manifest, entries
):
    numbers = {entry["id"]: index for index, entry in enumerate(entries, 1)}
    for entry in entries:
        body = sync.render_body(entry, entries, manifest, numbers)
        unresolved = re.findall(r"\{P\d+(?:\.\d+)?\}|\{ROADMAP\}", body)
        assert not unresolved, f"{entry['id']}: {unresolved}"
