# WTE3 Todo

Repo root:
- `C:\Users\jakob\GIT\wte3`

Branch:
- `main`

## Current state

Implemented and working on `main`:
- workbook open / sheet selection
- imported tag list with drag-drop into hierarchy
- hierarchy category / subcategory grouping
- selecting a category previews all descendant tags
- selecting a subcategory previews all tags inside that subcategory
- session restore for the main trend workflow
- shared-range trend plot with fixed `0..100` visual Y scale
- per-tag `Low Range` / `High Range` editing in the bottom legend table
- display ranges saved per selected tag set, so a category reopens with the same scaling layout
- X-only drag / pan behavior in the plot
- bottom-strip cursor and visible-range status
- time-window controls with start / duration or start / end
- saved time-duration presets
- cursor inspection with `Prev Value`, `Cursor Value`, `Interp Value`, and `Next Value`
- floating in-plot legend removed
- left shared-scale label panel with compact stacked labels
- reusable tag unit library
- right-click unit assignment on imported tags and hierarchy tags
- custom tag names with right-click add / edit / remove
- hierarchy labels now show custom name plus unit
- imported tag list now shows custom name, original name, and unit
- legend, analytics, and plot title/surface labels now use custom display labels instead of raw tag paths
- detached pop-out trend windows, so multiple trend windows can stay open at the same time

Reference artifacts already saved in the repo:
- `artifacts/app-running-main.png`
- `artifacts/independent-y-axes-sketch.svg`
- `artifacts/time-selection-placement-sketch.png`
- `artifacts/time-selection-implemented.png`

## Verification status

Automated checks already passing on `main`:
- `.\.venv\Scripts\python.exe -m compileall src`
- `.\.venv\Scripts\python.exe -m pytest`

Most recent known passing test count:
- `51 passed`

Manual testing status:
- desktop testing looks good
- more testing is still wanted on the older laptop

## Remaining work

### 1. Manual QA on the older laptop

Check:
1. Clone / install / run from the current `main`
2. Open `sample-data.xlsx`
3. Load sheets and plot mixed-range tags
4. Verify custom names and units on:
   - hierarchy list
   - imported tag list
   - legend tab
   - analytics tab
   - plot title / scale tooltips
5. Verify category and subcategory selection behavior
6. Verify saved display ranges survive restart
7. Verify time-window restore survives restart
8. Verify WSL / old laptop GUI behavior is acceptable

### 2. Update session restore to reselect the same hierarchy item(s)

Status:
- not implemented yet

Goal:
- on reopen, restore not only the previewed tag set but also the visible hierarchy selection state where practical

Notes:
- current restore brings back the previewed tags
- the next polish step is restoring the actual selected category / subcategory / tag in the tree

### 3. Optional polish backlog

Only if needed after manual QA:
- refine the compact shared-scale panel spacing and typography
- tune imported-tag display formatting if long custom names wrap poorly
- add export behavior that uses the same custom display labels consistently

### 4. Saved feature ideas

Keep these on the backlog for later implementation:
- multi-cursor comparison
  - two cursors with delta time and delta value between them
- derived tags
  - formulas like difference, ratio, rolling average, and rate-of-change
- snapshot/export of current view
  - export exactly the visible trend view as image and/or visible-window data

## Suggested next starting point

The next best step is:
- finish the old-laptop manual QA
- then implement hierarchy-selection restore if that still feels missing
