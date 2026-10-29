# AI contribution guide

How a person or an AI agent runs one roadmap step. Read
[AGENTS.md](AGENTS.md) first, then the step's issue. The issue plus these
files must be enough to start. If they are not, say what is missing in the
issue instead of guessing.

## Workflow

One step = one issue = one branch = one PR.

1. **Claim.** Set yourself on the step in the
   [Project](https://github.com/orgs/ynput/projects/77) and move it to
   In progress. Check its "Depends on": the blocking steps must be merged.
2. **Survey.** Look for an existing implementation in this repo and in the
   host repos. If the feature already exists, stop and report it.
   List the host files named in the issue and read them.
3. **Branch in the stack.** One `gh stack` per phase:
   `gh stack init` for the first step, `gh stack add` for each next one.
   Branch names: `feature/<issue>-<slug>` here,
   `enhancement/<issue>-editorial-<slug>` in a host repo.
4. **Implement.** Only the files in the step's scope. For a port, write
   characterization tests first ([tests/AGENTS.md](tests/AGENTS.md)).
5. **Verify.** Run the [ladder](#verification-ladder).
6. **PR.** `gh stack submit`. Title `[Editorial P2.3]: <label>`. Fill in
   the PR template. Body ends with `Close <issue url>`.
7. **Link.** A host adoption step has a counterpart issue and PR in the
   host repo. Both link back to the step issue.
8. **Hand over.** List the manual host steps for a human. Do not merge.
   After a merge in the stack, `gh stack sync`.

Edit `.github/roadmap.yml` for a roadmap change, then run
`uv run --with pyyaml tools/roadmap_sync.py --dry-run`.

## Recipes

### Library port

Move code from the host copies into a shared module.

1. Read every host copy named in the issue. List the differences.
2. Write characterization tests, one case per host variant.
3. Write the shared module in the right layer, Python 3.9, OTIO 0.15+.
4. Make the tests pass without changing the expected output.
5. Do not touch the host repos. Their adoption is a separate step.
6. Run the ladder. State any deliberate behaviour difference in the PR.

### Host adoption

Replace a host copy with the shared code. Needs the library phase released
as `0.N.0`.

1. Branch `enhancement/<issue>-editorial-<slug>` in the host repo, from
   `develop-minor` (create it from `develop` if missing). The PR targets
   `develop-minor`, never `develop`.
2. Add `"editorial": ">=0.N.0"` to `ayon_required_addons`.
3. Replace the copy with an import; keep a re-export shim where the
   issue says so. Keep plugin `order`, `families`, `hosts`, creator
   `identifier`s and settings paths unchanged.
4. Compare output before and after (`tools/otio_compare.py` for timelines).
5. PR with the `bump minor` label. Link the step issue and this repo's PR.
6. Write the host test steps for a human.

### Parity feature

Give a host a feature only another host has (P6).

1. Write a short research note: what the host API allows. If it cannot,
   say so and close as not possible.
2. Implement through the shared creator framework, not in one host.
3. New settings are additive. Never rename an existing key without a
   conversion function in `server/settings/conversion.py`.
4. Test with a fake adapter; hand the host check to a human.

### Docs

1. Change the source: the manifest for the roadmap, the `AGENTS.md` files
   for instructions.
2. Keep sentences short, prefer tables and lists, wrap at 79 columns.
3. Check that every relative link resolves.
4. Do not name a repository whose visibility you have not checked.

## Subagent briefing template

Give a subagent only what the part needs.

```
Task: <one sentence>
Step: <ID and issue URL>
Checkout and branch: <path>, <branch>
Files you may change: <list>
Files you must not touch: <list>
Facts that bind you: <layer rules, frozen contracts involved>
Read first: AGENTS.md, <module>/AGENTS.md
Done when: <acceptance criteria that apply>
Checks to run: <ladder steps>
Reply with: files changed, checks and results, what a human must verify
in the host, what is left. At most 8 lines.
```

A subagent never commits, pushes, merges or switches branches. Check its
report against `git diff --stat` and re-run the checks before you build on
it.

## Tiers

| Tier | Use for | Escalate when |
| --- | --- | --- |
| light | Finding, extracting, applying a fixed recipe. A wrong result is obvious. | The result needs a choice between designs, or the tests do not settle it. |
| standard | A bounded change with judgement: a port, an adoption, a review. | The design is unclear, a frozen contract is touched, or two attempts failed. |
| deep | Design and open-ended debugging: `otio/builder.py`, the clip adapter, reviews of retime and hierarchy code. | A decision outside the roadmap is needed: hand to a human. |
| main | Outward-facing GitHub work: issues, PRs, Project fields, releases prep. | A release, merge or visibility change: hand to a human. |
| human | Host application validation, merge, release, decisions. | Not applicable. |

Each step's tier is in its issue. Start one tier lower when unsure and
move up if the result had to be redone; say so in the PR.

## Verification ladder

In this repo, in order:

1. `./tools/manage.sh ruff-check`
2. `./tools/manage.sh run-tests` (the CI matrix covers Python 3.9 with
   OTIO 0.15, 0.16, 0.17 and Python 3.11 with the latest OTIO)
3. `./tools/manage.sh codespell`
4. `python create_package.py --skip-zip`
5. Host application: not available to agents; write the manual steps.

In a host repo, in order:

1. `ruff check` and `ruff format --check` with that repo's own config
2. Its tests, only if the repo has a `tests/` folder
3. `python create_package.py --skip-zip`
4. Compare output before and after (`tools/otio_compare.py`)
5. Host application validation by a human

## Agents never

- Merge, release, or change repository visibility.
- Rename a settings key without a conversion function in
  `server/settings/conversion.py`.
- Change a frozen contract silently (see [AGENTS.md](AGENTS.md)).
- Claim they ran a host application.
- Name or quote a private repository.
- Touch vendor code.
- Import a host API, Qt at import time or an `ayon_<host>` addon.
- Commit or push unless the person who asked told them to.

## PR checklist

- [ ] One step, one issue, one branch; title `[Editorial P2.3]: <label>`
- [ ] Body has Changelog Description, Additional info, Testing notes,
      Dependency (`Close <issue url>`)
- [ ] Only files in the step's scope changed
- [ ] Ruff, tests and `create_package.py --skip-zip` pass
- [ ] Characterization tests exist for a port
- [ ] No frozen contract changed, or the change is stated
- [ ] Settings renames have a conversion function
- [ ] Host adoption: `editorial` in `ayon_required_addons`, `bump minor`
      label, counterpart issue and PR linked
- [ ] Manual host steps listed for a human
