# CodexCLI Order

Base repo:
- `C:\Users\jakob\GIT\wte3`

Current branch:
- `main`

Current base commit for this handoff:
- `df79596` (`Fix hierarchy tag drag and drop`)

## Objective

Investigate and fix the remaining user-reported issues in the floating in-plot trend legend without regressing the current plotting/session behavior.

## Scope

Focus only on the floating plot legend system unless a very small supporting change is required elsewhere.

Primary files:
- `src/wte_trend_viewer/ui/widgets/trend_plot_widget.py`
- `src/wte_trend_viewer/ui/styles/theme.py`
- `src/wte_trend_viewer/ui/main_window.py`

Do not refactor unrelated plotting/data/session code unless required to fix the legend issue cleanly.

## Current implemented legend behavior

The current floating legend already supports:
- drag by header
- minimize / restore
- session restore of geometry and minimized state
- dedicated circular width handle on the right side
- dedicated circular height handle on the bottom side
- wrapped legend entries into multiple columns as width increases

This behavior was added recently and should be preserved unless the user explicitly wants it changed.

## Likely task

The user has said there are still issues with the trend legend. The exact new issue list may be provided separately in the next interaction.

Your job:
1. Reproduce the current legend behavior in the running app.
2. Identify the remaining legend UX/behavior defects from the user’s report.
3. Fix only those defects.
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
   - resize width
   - resize height
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
- wrapped columns still work
- restart restores legend state
- no new interference with plot interaction

## Commit guidance

Use a focused commit message that mentions the legend issue actually fixed.
