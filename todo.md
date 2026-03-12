# WTE Trend Viewer TODO / Handoff

This document is the handoff for the next session.
It should be detailed enough for a new agent or developer to continue the project without any chat history.

Project root:
- `C:\Users\jakob\GIT\wte3`

Run command:

```powershell
cd C:\Users\jakob\GIT\wte3
.\.venv\Scripts\python.exe -m wte_trend_viewer
```

Editable install:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

## Current state

The app is now running from the non-OneDrive location and the editable install points to:
- `C:\Users\jakob\GIT\wte3`

The current desktop app already has:
- dark-themed PySide6 shell
- left workspace dock
- empty configurable hierarchy tree
- imported tags list populated from selected workbook sheets
- workbook sheet picker
- session save/load and last-session restore
- in-memory workbook/trend data layer
- multi-tag plotting with PyQtGraph
- bottom legend tab populated from plotted tags
- bottom analytics tab populated from plotted tags
- visible-window analytics
- visible-window plotting with cached arrays and downsampled redraws

## Important files

Main app entry:
- `src/wte_trend_viewer/app.py`

Main window:
- `src/wte_trend_viewer/ui/main_window.py`

Plot widget:
- `src/wte_trend_viewer/ui/widgets/trend_plot_widget.py`

Hierarchy widget:
- `src/wte_trend_viewer/ui/widgets/hierarchy_tree.py`

Imported tags widget:
- `src/wte_trend_viewer/ui/widgets/imported_tag_list.py`

Sheet picker dialog:
- `src/wte_trend_viewer/ui/dialogs/sheet_selection_dialog.py`

Theme:
- `src/wte_trend_viewer/ui/styles/theme.py`

Workbook inspection/loading:
- `src/wte_trend_viewer/workbook.py`
- `src/wte_trend_viewer/data_manager.py`

Session persistence:
- `src/wte_trend_viewer/session.py`

## Dependencies

Current Python dependencies in `pyproject.toml`:
- `PySide6`
- `numpy`
- `polars[calamine]`
- `pyqtgraph`

Local helper dependency used only for test workbook generation during development:
- `openpyxl`

## Important environment note

`tsdownsample` was attempted but could not be installed under the current Python 3.14 environment.
The build failed because the current PyO3 support in that package only officially supports up to Python 3.13.

Because of that, the current performance implementation uses a numpy-based visible-window min/max downsampler instead of `tsdownsample`.

This matters for next session:
- do not assume `tsdownsample` is available
- if wanting to retry it, either:
  - switch to Python 3.13, or
  - try the package with `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1`, or
  - keep the current numpy downsampler and refine it

## What is already implemented in the current phase

The current phase is the first real plotting/data phase.

Completed in this phase:
- workbook import with explicit sheet selection
- selected workbook sheets loaded into memory
- selected tags plotted end-to-end
- multiple tags plotted simultaneously
- plot summary updates from the visible window
- legend tab reflects plotted tags
- analytics tab reflects plotted tags
- visible-window redraw logic
- visible-window downsampling

## What is still missing in the current phase

These are the remaining pieces that should be treated as unfinished in the current plotting phase.

### 1. Requested pan controls under the plot

This is the immediate next task requested by the user.

User request:
- add left/right navigation buttons under the plot, as indicated in the screenshot
- add an input field to the left of those buttons that visually behaves like:
  - `1 / 4`
- the slash `/` must be static and not deletable
- the user only edits numerator and denominator
- pressing left/right moves the trend backward/forward by that fraction of the currently visible time range
- this move must not reset the current scale/zoom

Expected behavior:
- if current visible range is 4 hours and the field is `1 / 4`:
  - left button shifts the X range left by 1 hour
  - right button shifts the X range right by 1 hour
- if current visible range is 20 minutes and field is `1 / 4`:
  - each button press shifts by 5 minutes
- the width of the current window must stay exactly the same
- the vertical scale should not be force-reset by the button press
- the current zoom level should remain intact

Recommended implementation:
- add a small control row below the plot, still inside `TrendPlotWidget`
- use:
  - one `QSpinBox` for numerator
  - one static `QLabel("/")`
  - one `QSpinBox` for denominator
  - one left button
  - one right button
- this is better than a free-text field because it guarantees:
  - the slash is static
  - only digits are editable
  - denominator cannot be zero

Recommended defaults:
- numerator default: `1`
- denominator default: `4`
- numerator min/max: `1` to `100`
- denominator min/max: `1` to `100`

Implementation notes:
- add the controls in `src/wte_trend_viewer/ui/widgets/trend_plot_widget.py`
- add two button handlers:
  - `_pan_left_by_fraction()`
  - `_pan_right_by_fraction()`
- compute:
  - `window_width = x_max - x_min`
  - `step = window_width * numerator / denominator`
- set new X range:
  - left: `x_min - step`, `x_max - step`
  - right: `x_min + step`, `x_max + step`
- use the current X range from `current_x_range()`
- while applying the new X range, prevent redraw feedback loops the same way current range updates are protected

Most important UX requirement:
- panning with these buttons must not call any "reset" behavior
- do not call `enableAutoRange()` during button pan actions
- do not recompute a brand-new full-range view when the buttons are pressed

### 2. Better Y-axis behavior during manual navigation

Current behavior:
- when the visible X window changes, the plot recalculates Y range from visible data

This is useful for readable zoom behavior, but it may conflict with the user's phrase "without the scales resetting".

This needs a product decision next session:
- Option A: keep visible-window Y autoscaling during button panning
- Option B: preserve the current Y range during left/right button panning only
- Option C: add a toggle later for autoscale-on-pan

Recommended immediate behavior:
- preserve current Y range during left/right button presses
- keep existing visible-window Y autoscaling for manual zoom/pan gestures for now

If implementing that:
- before button panning, read current Y range
- set new X range
- restore Y range immediately after
- do not call the current visible-window Y autoscale inside the button-pan path

### 3. Plot interaction polish

Still missing:
- crosshair / cursor
- cursor value readout
- better legend interaction
- direct click-to-highlight between legend and plot

These are not blockers for the next requested button feature, but they are still missing in this phase.

### 4. Proper analytics semantics

Current analytics columns are window-based:
- visible last
- window min
- window max
- window avg

Still missing:
- cursor-based value
- nearest raw point before cursor
- nearest raw point after cursor
- clearer distinction between:
  - visible-window analytics
  - full-series analytics
  - cursor analytics

### 5. Independent Y axes

Not implemented yet.

Currently:
- all selected tags share one axis

Still needed:
- independent Y axes for tags with very different magnitudes
- at minimum a strategy for:
  - one primary left axis
  - one or more extra right axes

## Detailed implementation note for the next immediate task

If starting with the screenshot request first, the recommended exact order is:

1. Add a bottom control row inside `TrendPlotWidget`.
2. Add numerator and denominator spin boxes with a static slash label.
3. Add left and right pan buttons.
4. Keep current visible X range width fixed when panning.
5. Preserve Y range during button-driven panning.
6. Verify that legend and analytics still update after button pans.
7. Persist the numerator and denominator in session state.

Session persistence recommendation:
- store under `trend_state`, for example:
  - `pan_step_numerator`
  - `pan_step_denominator`

## Current technical behavior of the plot path

This is important context for anyone continuing.

The plot widget currently:
- caches full `numpy` arrays per selected tag
- listens to X-range changes from PyQtGraph
- debounces redraw updates with a short timer
- slices only the visible X window
- downsamples only that visible slice
- redraws each curve with reduced point count
- emits visible stats for the analytics table

Relevant current behavior:
- full view of a large dataset already renders about 800 points per curve
- zooming further reduces the number of rendered points again

This means the next session should build on the current visible-window pipeline, not replace it with a full-series redraw approach.

## Remaining work by phase

Below is the recommended roadmap from here.

### Phase 2: Plotting and navigation completion

Goal:
- make the plot area feel like a real trend viewer rather than a data preview

Still to do:
- add left/right fraction-based pan buttons
- persist pan fraction controls in session
- decide and implement Y-scale behavior during button pan
- add cursor/crosshair
- add cursor-driven analytics
- improve legend interaction
- consider "remove plotted tag" interaction from legend
- add explicit "reset view" behavior that restores sensible X/Y ranges

### Phase 3: Better multi-tag plotting

Goal:
- handle many plotted tags more deliberately

Still to do:
- independent Y axes
- per-tag visibility toggles
- per-tag color editing
- per-tag line style
- tag ordering / z-order control
- better handling of tags with flat or sparse data

### Phase 4: Data and workbook workflow refinement

Goal:
- make workbook handling production-usable

Still to do:
- merge vs replace behavior when importing another workbook
- clearer current-workbook indicator in the UI
- reloading when workbook changed on disk
- better messaging when sheets change shape between sessions
- possibly background loading with worker thread

Important note:
- a worker reference/lifetime bug existed in the older `wte2` project and was previously fixed there
- when background loading is introduced here, keep a persistent reference to the worker/thread objects

### Phase 5: Session completeness

Goal:
- make the workspace reopen exactly as the user left it

Still to do:
- persist:
  - plotted tag set
  - current visible X range
  - current Y ranges if preserving axis state
  - pan fraction control values
  - tab state and future legend/settings controls
- restore:
  - selected imported tags
  - plotted curves
  - view window
  - axis state

### Phase 6: Analytics and inspection

Goal:
- bring the viewer closer to SCADA trend behavior

Still to do:
- cursor ruler
- interpolated value at cursor
- previous/next raw values at cursor
- better visible-window stats
- possibly delta between two cursors
- quality/status overlays if data contains status columns later

### Phase 7: Advanced trend features

Goal:
- match or exceed the older trend viewer behavior

Still to do:
- ABB-style offset traces
- compare traces with time shift
- export plotted window
- export analytics
- inspect-tag details
- annotation/event overlays if needed later

## Known issues / caveats

### 1. `tsdownsample` not installed

Reason:
- build failed under Python 3.14

Current workaround:
- local numpy-based downsampler in `TrendPlotWidget`

### 2. Repo history

This repository currently appears to be at the first meaningful commit from the GIT copy.
The next session should continue from this repo root:
- `C:\Users\jakob\GIT\wte3`

### 3. `Raw Data.xlsx`

There is a workbook file in the repo root:
- `Raw Data.xlsx`

Before building more sample-data-dependent features, decide whether this file is:
- real project input data that should remain in git
- or just local development data

## Recommended first task for the next session

Do this first:
- implement the fraction-based left/right pan control exactly as requested in the screenshot

Then do this second:
- persist the numerator/denominator values in session

Then do this third:
- decide whether button panning should preserve current Y range

Then after that:
- implement cursor/crosshair and cursor analytics

## Verification checklist for the next session

After implementing the pan controls, verify all of the following:
- workbook opens correctly
- sheet selection still works
- multiple tags still plot
- clicking left/right buttons moves the visible X window by the configured fraction
- X window width stays constant
- no reset-to-full-range occurs
- Y scale behaves according to the decided rule
- legend still matches plotted tags
- analytics still update after button panning
- session restore still works
- pan fraction values restore correctly after restart

## Suggested commit style for next work

Recommended next commit after the button feature:
- `Add fraction-based trend panning controls`
