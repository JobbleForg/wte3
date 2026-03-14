# WTE Trend Viewer 1.0.0

First stable release of the workbook-based trend viewer.

## Highlights

- Workbook open and sheet selection for Excel trend data
- Imported tag list with drag-drop into a manual hierarchy
- Category and subcategory selection driving multi-tag trend previews
- Shared-range plotting with per-tag low/high engineering ranges
- Fixed X-only pan and zoom behavior
- Cursor inspection with floating legend and cursor-time values
- Editable time window controls and reusable duration presets
- Legend controls for color assignment and highlight/dimming
- Custom tag names and reusable engineering units
- Detached pop-out trend windows for side-by-side analysis
- Automatic last-session restore and JSON session save/load

## Verification

- Windows test suite: `65 passed`
- Verified with:
  - `.\.venv\Scripts\python.exe -m pytest`
  - `.\.venv\Scripts\python.exe -m compileall src`

## Platform note

- Verified directly in the Windows development environment
- Linux support is part of the runtime design and install path, but Linux Mint should still be validated on the target machine before being treated as fully certified
