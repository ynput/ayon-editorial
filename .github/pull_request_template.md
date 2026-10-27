<!-- Title: [Editorial P2.3]: <short label> -->

## Changelog Description
<!-- Summary for the user of the addon: what changes and why. -->

## Additional info
<!-- Brief technical context, only if useful. -->

## Testing notes:
<!-- Steps a reviewer can follow. For host applications, list the manual
steps a human must run; do not claim a host run you did not do.
1. start with this step
2. follow this step
-->

## Dependency
Close <issue url>
<!-- Host adoption PRs: also link the counterpart PR in the other repo. -->

## Checklist
- [ ] `ruff check` and `pytest` pass
- [ ] `python create_package.py --skip-zip` builds
- [ ] No frozen contract changed (or the change is stated above)
- [ ] Settings key renamed only with a conversion function
- [ ] Layer rules kept (`tests/test_dcc_agnostic.py`)
- [ ] Host adoption: `editorial` in `ayon_required_addons`, `bump minor` label
