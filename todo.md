# WTE3 Todo

Repo root:
- `C:\Users\jakob\GIT\wte3`

Branch:
- `main`

## Current state

Implemented and working on `main`:
- workbook open / sheet selection
- hierarchy browsing and tag plotting
- session restore for the main trend workflow
- cursor inspection in the plot
- analytics table with `Prev Value`, `Cursor Value`, `Interp Value`, and `Next Value`
- bottom tab area holding plot metadata and analytics
- bottom legend tab converted to an editable table with per-tag `Low Range` / `High Range`
- edited display ranges persist in session state under `trend_state.display_ranges`
- floating in-plot trend legend removed from the UI and session wiring
- plotted series now render on a shared normalized Y display using the saved per-tag ranges
- plot Y range is fixed to `0..100` as a shared display scale
- plot mouse interaction is constrained to X movement only
- a first-pass left-side shared-scale label panel now shows colored high / midpoint / low values for plotted tags

Reference artifacts already saved in the repo:
- `artifacts/app-running-main.png`
- `artifacts/independent-y-axes-sketch.svg`

## New direction from user

Do not build independent visible Y axes per tag.

The new target is the trend behavior shown in the work reference image:
- one shared visual Y scale in the plot area
- each tag uses its own configured `Low range` and `High range`
- the plot maps each tag's raw value into the shared display scale using those configured ranges
- the left side shows multiple colored numeric labels at the same shared tick levels, one set per plotted tag
- drag interaction in the plot should move only on the X axis
- the floating legend overlay should be removed entirely because the bottom tabs already hold the needed information

Ignore the unrelated workstation UI details from the reference image.

## Recommended next session order

### Phase 1: remove stale legend direction and establish the new source of truth

Status:
- completed on `main`

Goal:
- the bottom tabs become the only plot metadata surface

Work:
1. Remove the floating legend overlay from `TrendPlotWidget`.
2. Remove any legend session persistence wiring in `main_window.py`.
3. Remove or simplify stale helper classes that only exist for the overlay:
   - `_FloatingLegendEntry`
   - `_WrappingLegendEntries`
   - `_LegendResizeHandle`
   - `_FloatingLegendOverlay`
4. Remove any `legend_state`, `apply_legend_state`, or `legendStateChanged` code paths that are now dead.
5. Keep the bottom legend/details tab intact.

Verification:
- plotting still works with multiple tags
- no floating overlay appears after plotting
- session restore still works for normal trend state

### Phase 2: add per-tag display ranges

Status:
- completed on `main`

Goal:
- every plotted tag has an editable display `Low range` and `High range`

Recommended implementation:
- add `Low range` and `High range` columns to the bottom legend/details table
- store the values per tag, keyed by a stable tag identifier
- persist them in session data

Behavior:
- default the first pass to the raw min/max of each plotted series
- validate numeric input
- reject or auto-correct invalid `low >= high`
- updating a range should immediately refresh the plot

Files likely involved:
- `src/wte_trend_viewer/ui/main_window.py`
- `src/wte_trend_viewer/session.py`
- `src/wte_trend_viewer/ui/widgets/trend_plot_widget.py`

Verification:
- range edits survive session restore
- editing a range changes only the display mapping, not the raw analytics values

### Phase 3: convert plotting to a shared normalized Y display

Status:
- completed for first pass on `main`

Goal:
- all plotted tags share one visual Y space while still representing their own configured engineering ranges

Recommended implementation:
1. Normalize each displayed point with:
   - `(value - low_range) / (high_range - low_range)`
2. Render the normalized values on a fixed display range such as `0.0` to `1.0`.
3. Keep the cursor calculations and analytics values in raw engineering units.
4. Keep X handling unchanged except for the later pan constraint.

Important:
- do not replace raw stored data with normalized data
- normalization should be a display-only transform
- decide whether out-of-range values clip or draw outside bounds; first pass should clip to the display range for stability

Verification:
- tags with very different units/ranges align in the same plot area
- raw analytics still show original values
- no regressions in zoom-to-window and data reload

### Phase 4: replace the Y axis presentation

Status:
- completed for the current shared-range design on `main`
- left-side grouped labels are implemented with compact column stacking
- panel width is now derived from the rendered label widths instead of a wide fixed estimate

Goal:
- match the work-style left-side labeling model instead of separate per-series axes

Desired appearance:
- one shared axis spine/grid
- three shared anchor levels are enough for the first pass:
  - top
  - middle
  - bottom
- for each anchor level, draw one colored label per plotted tag on the left:
  - top -> each tag's configured `High range`
  - middle -> midpoint between low/high
  - bottom -> each tag's configured `Low range`

Notes:
- the labels should use the tag plot color
- the labels can stack vertically in a compact cluster at each anchor level
- do not add right-side axes

Verification:
- colors match the plotted tags
- adding/removing tags updates the label clusters correctly
- label layout remains readable with several plotted tags
- the scale panel now stays narrow for small tag counts and expands only as needed

### Phase 5: constrain plot interaction to X only

Status:
- completed on `main`
- view-box mouse movement is X-only
- explicit scale and translate operations now keep the Y range fixed as well

Goal:
- mouse drag only pans in time

Behavior:
- click-hold-drag moves only on the X axis
- Y stays fixed to the shared normalized display range
- wheel behavior should not introduce vertical scaling drift
- existing fraction pan controls should keep working

Verification:
- drag does not shift the curves vertically
- panning still feels smooth
- cursor inspection still tracks correctly after pan/zoom
- direct view-box scale/translate calls were verified to keep Y locked to `0..100`

### Phase 6: final cleanup and verification

Run:
- `.\.venv\Scripts\python.exe -m compileall src`
- `.\.venv\Scripts\python.exe -m pytest`
- `.\.venv\Scripts\python.exe -m wte_trend_viewer`

Manual smoke test:
1. Open `sample-data.xlsx`.
2. Select a data sheet.
3. Plot tags with clearly different ranges/units.
4. Confirm the bottom table exposes `Low range` / `High range`.
5. Edit ranges and confirm the curves remap immediately.
6. Drag in the plot and confirm only X changes.
7. Hover the cursor and confirm analytics still show raw previous / nearest / interpolated / next values.
8. Close and reopen the app and confirm the tag ranges restore.
9. Confirm no floating legend window appears anywhere.
10. Confirm time-range Apply still restores the same visible X window after session reload.

Automated verification already completed on `main`:
- `.\.venv\Scripts\python.exe -m compileall src`
- `.\.venv\Scripts\python.exe -m pytest`
- offscreen workbook smoke with `sample-data.xlsx`

Smoke checks already confirmed:
- Y remains locked at `0..100` during explicit scale and translate calls
- display range edits still remap plotted series
- a 6-hour applied time window restores correctly after session capture/restore
- cursor analytics still populate with raw values
- the visible range badge and cursor label still update as expected

Most recent stabilization files:
- `src/wte_trend_viewer/data_manager.py`
- `src/wte_trend_viewer/ui/main_window.py`
- `src/wte_trend_viewer/ui/widgets/trend_plot_widget.py`
- `tests/test_data_manager.py`
- `tests/test_trend_plot_widget.py`

## Suggested next starting point

The next work is no longer core plotting infrastructure.

Suggested focus:
- manual visual QA in the full desktop app
- decide whether the compact shared-scale panel needs more presentation polish
- then move to the next user-requested feature instead of more internal plotting rewrites
