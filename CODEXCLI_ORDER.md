# CodexCLI Order

Base repo:
- `C:\Users\jakob\GIT\wte3`

Current branch:
- `main`

Current base commit for this handoff:
- `c6e13a2` (`Add CodexCLI legend handoff`)

## Objective

Fix the remaining user-reported issues in the floating in-plot trend legend without regressing current plotting, session restore, or hierarchy drag/drop behavior.

## Scope

Focus only on the floating plot legend system unless a very small supporting change is required elsewhere.

Primary files:
- `src/wte_trend_viewer/ui/widgets/trend_plot_widget.py`
- `src/wte_trend_viewer/ui/styles/theme.py`
- `src/wte_trend_viewer/ui/main_window.py`

Do not refactor unrelated plotting, workbook, session, or hierarchy code unless required to fix the legend cleanly.

## User-provided references

Reference video:
- `C:\Users\jakob\WSL\Issue - Trend legend\Screen Recording 2026-03-13 073532.mp4`

Reference image:
- `C:\Users\jakob\WSL\Issue - Trend legend\TrendLegend resize button placement and size edit.png`

Use both before editing.

## Current implemented legend behavior

The floating legend currently supports:
- drag by header
- minimize / restore
- session restore of geometry and minimized state
- dedicated circular width handle
- dedicated circular height handle
- wrapped legend entries into multiple columns as width increases

This baseline should remain unless the user explicitly asks otherwise.

## Exact issues to fix

1. Height shrink behavior is wrong.
   - When the legend window is made smaller in height, the entry boxes shrink.
   - The text does not scale with the box height.
   - The text then disappears or clips.
   - Required result: the text must remain visible and scale down with the available height instead of disappearing.

2. Reflow when narrowing is wrong.
   - When the legend is widened, items wrap into multiple columns as intended.
   - When the legend is narrowed again, they do not reliably reflow back to fit the smaller width.
   - Required result: column and row layout must recompute correctly in both directions, not just while widening.

3. Resize handles are wrong.
   - The width and height resize controls are too large.
   - They are also misplaced.
   - Required result: resize handles must match the size and placement shown in the reference image.
   - From the reference image:
     - the width handle should sit small and close to the mid-right edge of the legend
     - the height handle should sit small and close to the bottom-center edge of the legend
     - both handles should be visually subtle, not dominant UI elements

## Your job

1. Reproduce the current legend behavior in the running app.
2. Compare it against the user-provided video and image.
3. Fix only the three issues listed above.
4. Keep the following working:
   - drag by header
   - minimize / restore
   - dedicated resize handles
   - multi-column wrapping
   - session persistence

## Run command

```powershell
cd C:\Users\jakob\GIT\wte3
.\.venv\Scripts\python.exe -m wte_trend_viewer
```

## Suggested reproduction workflow

Use the real workbook already present in the repo root:
- `sample-data.xlsx`

Then:
1. Open workbook.
2. Select a data sheet.
3. Plot multiple tags.
4. Interact with the floating legend:
   - drag it
   - resize width wider
   - resize width narrower again
   - resize height smaller until the current clipping problem would show up
   - minimize / restore
   - restart app and confirm restore

## Known implementation locations

Legend overlay classes are inside:
- `src/wte_trend_viewer/ui/widgets/trend_plot_widget.py`

Important structures:
- `_FloatingLegendEntry`
- `_WrappingLegendEntries`
- `_LegendResizeHandle`
- `_FloatingLegendOverlay`
- `TrendPlotWidget.legend_state()`
- `TrendPlotWidget.apply_legend_state(...)`

Session persistence wiring is in:
- `src/wte_trend_viewer/ui/main_window.py`

Theme styling is in:
- `src/wte_trend_viewer/ui/styles/theme.py`

## Constraints

- Keep ASCII-only edits unless the file already requires otherwise.
- Use `apply_patch` for edits.
- Do not revert user-visible behavior outside the legend unless necessary.
- Do not remove the current pan controls.
- Do not break current session restore.
- Do not break hierarchy drag/drop.

## Verification checklist

Before finishing, verify:
- `python -m compileall src`
- legend still appears when tags are plotted
- drag still works
- minimize / restore still works
- width resize still works
- height resize still works
- shrinking height keeps text visible instead of clipping away
- widening then narrowing recomputes wrapped layout correctly
- resize handles match the intended size and placement from the reference image
- restart restores legend state
- no new interference with plot interaction

## Commit guidance

Use a focused commit message that mentions the legend issue actually fixed.
