"""Sync `.github/roadmap.yml` to GitHub issues and the roadmap Project.

Creates or updates one issue per roadmap entry, keyed by its step ID in the
title (`[Editorial P2.3]: …`), then sets issue types, labels, sub-issues,
"blocked by" links and Project fields. Running it twice changes nothing.

Usage:
    uv run --with pyyaml tools/roadmap_sync.py [--dry-run]

Needs the `gh` CLI logged in with the `repo` and `project` scopes.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / ".github" / "roadmap.yml"

# Org issue type for each roadmap kind.
ISSUE_TYPES = {
    "Epic": "🚀 Epic",
    "Infra": "Task",
    "Docs": "Task",
    "Library": "Feature",
    "Adoption": "Maintenance",
    "Parity": "Enhancement",
    "Decision": "Topic",
    "Research": "Topic",
}
KIND_LABELS = {
    "Infra": "type: maintenance",
    "Docs": "documentation",
    "Library": "type: feature",
    "Adoption": "type: maintenance",
    "Parity": "type: enhancement",
}
HOST_LABELS = {
    "ayon-flame": "host: flame",
    "ayon-hiero": "host: hiero",
    "ayon-resolve": "host: resolve",
    "ayon-traypublisher": "host: traypublisher",
    "ayon-core": "host: core",
}
NO_VALIDATION_KINDS = {"Infra", "Docs", "Library", "Decision", "Research"}

DRY_RUN = False


def gh(*args: str, input_data: dict | None = None) -> object:
    """Run `gh` and return its parsed JSON output (or None when empty)."""
    proc = subprocess.run(
        ["gh", *args],
        input=json.dumps(input_data) if input_data is not None else None,
        capture_output=True,
        text=True,
    )
    if proc.returncode:
        sys.exit(
            f"gh {' '.join(args[:3])} failed:\n{proc.stdout}{proc.stderr}"
        )
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def graphql(query: str, **variables) -> dict:
    result = gh(
        "api",
        "graphql",
        "--input",
        "-",
        input_data={"query": query, "variables": variables},
    )
    if result.get("errors"):
        sys.exit(json.dumps(result["errors"], indent=2))
    return result["data"]


def write(description: str, func, *args, **kwargs):
    """Print a mutating action and run it unless in dry-run mode."""
    print(("[dry-run] " if DRY_RUN else "") + description)
    if DRY_RUN:
        return None
    result = func(*args, **kwargs)
    time.sleep(0.5)
    return result


# --- Manifest -------------------------------------------------------------


def load_entries(manifest: dict) -> list[dict]:
    """Flatten the manifest into root, phase epics and steps, in order."""
    root = dict(manifest["root"], level="root", parent=None, phase=None)
    root["title_full"] = f"[Editorial]: {root['title']}"
    entries = [root]
    for phase in manifest["phases"]:
        epic = {
            "id": phase["id"],
            "title": phase["title"],
            "title_full": f"[Editorial {phase['id']}]: {phase['title']}",
            "kind": "Epic",
            "repo": "ayon-editorial",
            "tier": "main",
            "priority": phase.get("priority", "High"),
            "status": phase.get("status", "Backlog"),
            "goal": phase["goal"],
            "phase": phase["phase"],
            "release": phase.get("release"),
            "level": "epic",
            "parent": root["id"],
        }
        entries.append(epic)
        for step in phase["steps"]:
            entry = dict(step)
            entry.setdefault("status", "Backlog")
            entry.setdefault(
                "repo",
                (step.get("repos") or ["ayon-editorial"])[0]
                if len(step.get("repos") or []) <= 1
                else None,
            )
            entry.update(
                title_full=f"[Editorial {step['id']}]: {step['title']}",
                phase=phase["phase"],
                release=phase.get("release"),
                level="step",
                parent=phase["id"],
            )
            entries.append(entry)
    return entries


def target_repos(entry: dict) -> list[str]:
    return entry.get("repos") or ([entry["repo"]] if entry.get("repo") else [])


def labels_for(entry: dict) -> list[str]:
    labels = ["roadmap"]
    if entry["kind"] in KIND_LABELS:
        labels.append(KIND_LABELS[entry["kind"]])
    labels += [HOST_LABELS[r] for r in target_repos(entry) if r in HOST_LABELS]
    if entry.get("priority") == "Very low":
        labels.append("to consider")
    return labels


# --- Body rendering -------------------------------------------------------


def link(ref_id: str, numbers: dict[str, int]) -> str:
    number = numbers.get(ref_id)
    return f"#{number}" if number else f"`{ref_id}`"


def resolve(text: str, numbers: dict[str, int]) -> str:
    return re.sub(
        r"\{(P\d+(?:\.\d+)?|ROADMAP)\}",
        lambda m: link(m.group(1), numbers),
        text,
    )


def bullet_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def render_body(entry, entries, manifest, numbers) -> str:
    by_id = {e["id"]: e for e in entries}
    meta = [f"**Kind:** {entry['kind']}"]
    if entry.get("phase"):
        meta.insert(0, f"**Phase:** {entry['phase']}")
    repos = target_repos(entry)
    if repos:
        meta.append("**Target repo:** " + ", ".join(f"`{r}`" for r in repos))
    meta += [
        f"**Tier:** {entry['tier']}",
        f"**Priority:** {entry['priority']}",
    ]
    if entry.get("release"):
        meta.append(f"**Release:** `{entry['release']}`")
    header = "> " + " · ".join(meta)
    if entry["parent"]:
        header += f"\n> Part of {link(entry['parent'], numbers)}" + (
            ""
            if entry["parent"] == "ROADMAP"
            else f" · Roadmap: {link('ROADMAP', numbers)}"
        )
    parts = [header]

    parts.append("## Goal\n\n" + entry["goal"].strip())
    if entry.get("scope"):
        parts.append("## Scope\n\n" + bullet_list(entry["scope"]))

    if entry["level"] == "root":
        rows = ["| Phase | Epic | Release |", "|---|---|---|"]
        rows += [
            f"| {e['phase']} | {link(e['id'], numbers)} {e['title']} "
            f"| `{e.get('release') or ''}` |"
            for e in entries
            if e["level"] == "epic"
        ]
        parts.append("## Phases\n\n" + "\n".join(rows))
    if entry["level"] == "epic":
        rows = [
            "| Step | Issue | Kind | Target repo | Tier | Priority |",
            "|---|---|---|---|---|---|",
        ]
        rows += [
            f"| {e['id']} | {link(e['id'], numbers)} {e['title']} "
            f"| {e['kind']} | {', '.join(target_repos(e))} "
            f"| {e['tier']} | {e['priority']} |"
            for e in entries
            if e["parent"] == entry["id"]
        ]
        parts.append("## Steps\n\n" + "\n".join(rows))
        parts.append(
            "Library steps of this phase are stacked with `gh stack` in "
            "ynput/ayon-editorial and released as "
            f"`{entry.get('release')}`; host adoption PRs wait for that "
            "release."
        )

    if entry["level"] == "step":
        acceptance = list(entry.get("acceptance") or [])
        acceptance = [
            a if a.startswith("[") else f"[ ] {a}" for a in acceptance
        ]
        if entry["kind"] == "Library":
            acceptance += [
                "[ ] Tests written first (characterization tests when "
                "porting host code)",
                "[ ] ruff, the pytest matrix and "
                "`create_package.py --skip-zip` pass",
                "[ ] Module map in `client/ayon_editorial/AGENTS.md` updated",
            ]
        if entry["kind"] in ("Adoption", "Parity"):
            acceptance += [
                "[ ] Duplicate code removed or reduced to a re-export shim",
                f'[ ] `"editorial": ">={entry.get("release")}"` in '
                "`ayon_required_addons` of `package.py`",
                "[ ] ruff and `create_package.py` pass in the host repo",
                "[ ] Manual host test steps in the PR, run by a person",
            ]
        if acceptance:
            parts.append(
                "## Acceptance criteria\n\n" + bullet_list(acceptance)
            )

        deps = entry.get("depends") or []
        if deps:
            parts.append(
                "## Depends on\n\n"
                + bullet_list(
                    [f"{link(d, numbers)} {by_id[d]['title']}" for d in deps]
                )
            )

        counterparts = []
        if entry["kind"] == "Library":
            counterparts = [
                e
                for e in entries
                if entry["id"] in (e.get("depends") or [])
                and e["kind"] in ("Adoption", "Parity")
            ]
        if counterparts:
            parts.append(
                "## Host counterparts\n\n"
                + bullet_list(
                    [
                        f"{link(e['id'], numbers)} {e['title']} "
                        f"({', '.join(target_repos(e))})"
                        for e in counterparts
                    ]
                )
            )

        if entry["kind"] in ("Library", "Adoption", "Parity"):
            parts.append(
                "## Frozen contracts\n\n"
                "Unchanged by this step. If one must change, the PR states "
                "the before and after values.\n\n"
                + bullet_list(manifest["frozen_contracts"])
            )

    if entry.get("refs"):
        parts.append("## Related discussions\n\n" + bullet_list(entry["refs"]))
    if entry.get("notes"):
        parts.append(entry["notes"].strip())

    if entry["level"] == "step":
        pid = entry["id"]
        agent = [
            f"Read `AGENTS.md` and `AI-CONTRIBUTION.md` "
            f"(added in {link('P0.5', numbers)}) before starting."
        ]
        host_repos = [r for r in repos if r != "ayon-editorial"]
        if host_repos and entry["kind"] in ("Adoption", "Parity"):
            agent += [
                "Open a counterpart issue in "
                + ", ".join(f"ynput/{r}" for r in host_repos)
                + " linking back here, then branch "
                "`enhancement/<issue>-editorial-<slug>` in that repo's "
                "editorial stack.",
                f"PR title `[Editorial {pid}]: …`; PR body closes the host "
                "issue and this one (`Close ynput/ayon-editorial#<n>`).",
                "Attach the `tools/otio_compare.py` before/after result "
                "where the step touches OTIO output.",
                "Agents never claim a host test was run.",
            ]
        else:
            agent += [
                "Branch `feature/<issue>-<slug>` in this phase's `gh stack`.",
                f"PR title `[Editorial {pid}]: …`; PR body "
                "`Close ynput/ayon-editorial#<n>`.",
            ]
        agent.append(manifest["supported_hosts"].strip())
        parts.append("## For agents\n\n" + bullet_list(agent))

    parts.append(
        "<!-- generated by tools/roadmap_sync.py from "
        f".github/roadmap.yml (id: {entry['id']}); edit the manifest -->"
    )
    return resolve("\n\n".join(parts), numbers) + "\n"


# --- GitHub ---------------------------------------------------------------


def existing_issues(repo: str) -> dict[str, dict]:
    issues = gh(
        "issue",
        "list",
        "-R",
        repo,
        "--state",
        "all",
        "--limit",
        "500",
        "--json",
        "number,title,body,labels,id",
    )
    found = {}
    for issue in issues:
        match = re.match(
            r"\[Editorial(?: (P\d+(?:\.\d+)?))?\]:", issue["title"]
        )
        if match:
            found[match.group(1) or "ROADMAP"] = issue
    return found


def issue_type_ids(owner: str) -> dict[str, str]:
    data = graphql(
        "query($o:String!){organization(login:$o)"
        "{issueTypes(first:50){nodes{id name}}}}",
        o=owner,
    )
    return {
        n["name"].strip(): n["id"]
        for n in data["organization"]["issueTypes"]["nodes"]
    }


def sync_issues(repo, entries, manifest) -> dict[str, dict]:
    issues = existing_issues(repo)
    numbers = {k: v["number"] for k, v in issues.items()}
    for entry in entries:
        if entry["id"] in issues:
            continue
        body = render_body(entry, entries, manifest, numbers)
        created = write(
            f"create issue {entry['title_full']}",
            gh,
            "api",
            f"repos/{repo}/issues",
            "--method",
            "POST",
            "--input",
            "-",
            input_data={
                "title": entry["title_full"],
                "body": body,
                "labels": labels_for(entry),
            },
        )
        if created:
            issues[entry["id"]] = {
                "number": created["number"],
                "id": created["node_id"],
                "title": entry["title_full"],
                "body": body,
                "labels": [{"name": n} for n in labels_for(entry)],
            }
            numbers[entry["id"]] = created["number"]
            time.sleep(1.5)

    for entry in entries:
        issue = issues.get(entry["id"])
        if not issue:
            continue
        body = render_body(entry, entries, manifest, numbers)
        current_labels = {label["name"] for label in issue["labels"]}
        missing_labels = [
            label
            for label in labels_for(entry)
            if label not in current_labels
        ]
        update = {}
        if issue["title"] != entry["title_full"]:
            update["title"] = entry["title_full"]
        if issue["body"].strip() != body.strip():
            update["body"] = body
        if update:
            write(
                f"update #{issue['number']} {', '.join(update)}",
                gh,
                "api",
                f"repos/{repo}/issues/{issue['number']}",
                "--method",
                "PATCH",
                "--input",
                "-",
                input_data=update,
            )
        if missing_labels:
            write(
                f"label #{issue['number']} {missing_labels}",
                gh,
                "api",
                f"repos/{repo}/issues/{issue['number']}/labels",
                "--method",
                "POST",
                "--input",
                "-",
                input_data={"labels": missing_labels},
            )
    return issues


def issue_details(repo: str, number: int) -> dict:
    owner, name = repo.split("/")
    data = graphql(
        """query($o:String!,$n:String!,$num:Int!){repository(owner:$o,name:$n){
        issue(number:$num){id databaseId issueType{name}
        subIssues(first:100){nodes{number}}
        blockedBy(first:100){nodes{number}}}}}""",
        o=owner,
        n=name,
        num=number,
    )
    return data["repository"]["issue"]


def sync_relations(repo, entries, issues, type_ids):
    details = {k: issue_details(repo, v["number"]) for k, v in issues.items()}
    for entry in entries:
        if entry["id"] not in issues:
            continue
        number = issues[entry["id"]]["number"]
        info = details[entry["id"]]
        wanted_type = ISSUE_TYPES[entry["kind"]]
        if (info["issueType"] or {}).get("name", "").strip() != wanted_type:
            write(
                f"type #{number} -> {wanted_type}",
                graphql,
                "mutation($i:ID!,$t:ID!){updateIssueIssueType(input:"
                "{issueId:$i,issueTypeId:$t}){issue{number}}}",
                i=info["id"],
                t=type_ids[wanted_type],
            )

        children = [e for e in entries if e["parent"] == entry["id"]]
        have = {n["number"] for n in info["subIssues"]["nodes"]}
        for child in children:
            child_issue = issues.get(child["id"])
            if child_issue and child_issue["number"] not in have:
                write(
                    f"sub-issue #{number} <- #{child_issue['number']}",
                    graphql,
                    "mutation($i:ID!,$s:ID!){addSubIssue(input:"
                    "{issueId:$i,subIssueId:$s}){issue{number}}}",
                    i=info["id"],
                    s=details[child["id"]]["id"],
                )

        blocked = {n["number"] for n in info["blockedBy"]["nodes"]}
        for dep in entry.get("depends") or []:
            dep_issue = issues.get(dep)
            if dep_issue and dep_issue["number"] not in blocked:
                write(
                    f"blocked #{number} by #{dep_issue['number']}",
                    graphql,
                    "mutation($i:ID!,$b:ID!){addBlockedBy(input:"
                    "{issueId:$i,blockingIssueId:$b}){issue{number}}}",
                    i=info["id"],
                    b=details[dep]["id"],
                )


def project_state(owner: str, number: int) -> tuple[str, dict, dict]:
    data = graphql(
        """query($o:String!,$n:Int!){organization(login:$o){projectV2(number:$n){
        id fields(first:50){nodes{... on ProjectV2FieldCommon{id name dataType}
        ... on ProjectV2SingleSelectField{options{id name}}}}}}}""",
        o=owner,
        n=number,
    )
    project = data["organization"]["projectV2"]
    fields = {f["name"]: f for f in project["fields"]["nodes"] if f}
    items, cursor = {}, None
    while True:
        page = graphql(
            """query($p:ID!,$c:String){node(id:$p){... on ProjectV2{
            items(first:100,after:$c){pageInfo{hasNextPage endCursor} nodes{id
            content{... on Issue{id}}
            fieldValues(first:30){nodes{
              ... on ProjectV2ItemFieldTextValue{
                text field{... on ProjectV2FieldCommon{name}}}
              ... on ProjectV2ItemFieldSingleSelectValue{
                name field{... on ProjectV2FieldCommon{name}}}
            }}}}}}}""",
            p=project["id"],
            c=cursor,
        )
        block = page["node"]["items"]
        for node in block["nodes"]:
            if node["content"]:
                values = {
                    v["field"]["name"]: v.get("text", v.get("name"))
                    for v in node["fieldValues"]["nodes"]
                    if v
                }
                items[node["content"]["id"]] = {
                    "id": node["id"],
                    "values": values,
                }
        if not block["pageInfo"]["hasNextPage"]:
            break
        cursor = block["pageInfo"]["endCursor"]
    return project["id"], fields, items


def field_values(entry: dict) -> dict[str, str]:
    values = {
        "Status": entry.get("status", "Backlog"),
        "Kind": entry["kind"],
        "Tier": entry["tier"],
        "Priority": entry["priority"],
        "Step": entry["id"],
    }
    if entry.get("phase"):
        values["Phase"] = entry["phase"]
    if entry.get("repo"):
        values["Target repo"] = entry["repo"]
    if entry.get("release"):
        values["Release"] = entry["release"]
    if entry.get("depends"):
        values["Depends on"] = ", ".join(entry["depends"])
    if entry["kind"] in NO_VALIDATION_KINDS:
        values["Validation"] = "n/a"
    return values


def sync_project(manifest, entries, issues):
    owner, number = manifest["project"]["owner"], manifest["project"]["number"]
    project_id, fields, items = project_state(owner, number)
    for entry in entries:
        issue = issues.get(entry["id"])
        if not issue:
            continue
        item = items.get(issue["id"])
        if not item:
            added = write(
                f"project add #{issue['number']}",
                graphql,
                "mutation($p:ID!,$c:ID!){addProjectV2ItemById(input:"
                "{projectId:$p,contentId:$c}){item{id}}}",
                p=project_id,
                c=issue["id"],
            )
            if not added:
                continue
            item = {
                "id": added["addProjectV2ItemById"]["item"]["id"],
                "values": {},
            }
        for name, value in field_values(entry).items():
            if item["values"].get(name) == value:
                continue
            field = fields[name]
            if field["dataType"] == "SINGLE_SELECT":
                option = next(
                    o["id"] for o in field["options"] if o["name"] == value
                )
                payload = {"singleSelectOptionId": option}
            else:
                payload = {"text": value}
            write(
                f"field #{issue['number']} {name}={value}",
                graphql,
                "mutation($p:ID!,$i:ID!,$f:ID!,$v:ProjectV2FieldValue!)"
                "{updateProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,"
                "fieldId:$f,value:$v}){projectV2Item{id}}}",
                p=project_id,
                i=item["id"],
                f=field["id"],
                v=payload,
            )


def main():
    global DRY_RUN
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the planned changes without making them",
    )
    DRY_RUN = parser.parse_args().dry_run

    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    repo = manifest["repository"]
    entries = load_entries(manifest)
    issues = sync_issues(repo, entries, manifest)
    sync_relations(repo, entries, issues, issue_type_ids(repo.split("/")[0]))
    sync_project(manifest, entries, issues)


if __name__ == "__main__":
    main()
