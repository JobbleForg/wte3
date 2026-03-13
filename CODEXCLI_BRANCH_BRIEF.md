# CodexCLI Branch Brief

Repo:
- `C:\Users\jakob\GIT\wte3`

Remote:
- `https://github.com/JobbleForg/wte3`

Required base:
- start from current `origin/main`
- if working from the WSL clone, rebase or reset the branch base so it includes commit `254b219`

Why this matters:
- the WSL review repo used for the issue report is behind the current Windows repo state
- current `main` already includes newer cursor analytics and the shared-range redesign handoff

## Safe scope for CodexCLI

CodexCLI may work on a branch for the cursor issue report, but should stay inside this scope:

Allowed:
1. Fix analytics-table cursor update churn.
2. Suppress redundant cursor-stat emissions when the effective sampled result has not changed.
3. Keep or expand regression tests that support those fixes.
4. Update `pyproject.toml` only as needed for the repo-local test workflow.
5. Add or refine tests under `tests/`.

Do not do without explicit approval:
1. Do not remove or redesign the new cursor analytics columns.
2. Do not implement the shared-range Y redesign.
3. Do not remove the floating legend overlay as part of the CodexCLI branch.
4. Do not change workbook/session/hierarchy behavior outside what is required for the cursor fixes.
5. Do not change cursor timestamp semantics to snap the cursor line or label to the nearest sample unless explicitly requested.

## Reason for the timestamp restriction

The issue report correctly notes that the cursor label time can differ from the sampled value time.

That is a real product decision, not just a mechanical bug:
- snapping the cursor readout to sample time may conflict with the newer interpolation-based cursor workflow
- if that change is desired later, it should be reviewed as a deliberate interaction-model decision

So for this branch:
- fix findings 1 and 3 from the report
- leave finding 2 alone unless specifically approved

## Files most likely to change

- `src/wte_trend_viewer/ui/main_window.py`
- `src/wte_trend_viewer/ui/widgets/trend_plot_widget.py`
- `pyproject.toml`
- `tests/test_cursor_regressions.py`
- other `tests/` files if needed

## Expected branch outcome

A reviewable branch that:
- reduces cursor-driven table churn
- coalesces redundant cursor updates
- keeps the current user-visible cursor semantics
- merges cleanly against the current redesign work on `main`
