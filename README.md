# WTE Trend Viewer

Desktop trend viewer for workbook-based SCADA trend analysis.

## Requirements

- `Python 3.12+`
- `git`
- On WSL: a GUI-capable setup such as `WSLg`

## Clone

Windows PowerShell:

```powershell
git clone https://github.com/JobbleForg/wte3.git
cd wte3
```

WSL / Linux:

```bash
git clone https://github.com/JobbleForg/wte3.git
cd wte3
```

## Install

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .[dev]
```

WSL / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

## Run

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m wte_trend_viewer
```

WSL / Linux:

```bash
source .venv/bin/activate
python -m wte_trend_viewer
```

You can also use the installed entry point:

Windows PowerShell:

```powershell
.\.venv\Scripts\wte-trend-viewer.exe
```

WSL / Linux:

```bash
source .venv/bin/activate
wte-trend-viewer
```

## Test

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

WSL / Linux:

```bash
source .venv/bin/activate
python -m pytest
```

## Notes

- No workbook data is included in the repository.
- Sessions are restored automatically between launches.
- On WSL, if the app does not open, check that GUI forwarding is available.
