from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import polars as pl


EXCEL_SCHEMA_INFER_LENGTH = 1_000
TIMESTAMP_COLUMN_CANDIDATES = (
    "timestamp",
    "time stamp",
    "datetime",
    "date time",
    "date_time",
    "time",
    "date",
)
NORMALIZED_NAME_PATTERN = re.compile(r"[^0-9a-zA-Z]+")


@dataclass(frozen=True)
class WorkbookSheetSummary:
    name: str
    row_count: int
    column_count: int
    timestamp_column: str | None
    tag_names: tuple[str, ...]

    @property
    def is_data_sheet(self) -> bool:
        return self.timestamp_column is not None and bool(self.tag_names)


@dataclass(frozen=True)
class WorkbookInspectionResult:
    source_path: Path
    sheets: tuple[WorkbookSheetSummary, ...]

    @property
    def data_sheets(self) -> tuple[WorkbookSheetSummary, ...]:
        return tuple(sheet for sheet in self.sheets if sheet.is_data_sheet)

    @property
    def available_tags(self) -> tuple[str, ...]:
        return self.tags_for_sheet_names(sheet.name for sheet in self.data_sheets)

    def tags_for_sheet_names(self, sheet_names) -> tuple[str, ...]:
        selected = {str(sheet_name) for sheet_name in sheet_names}
        merged: list[str] = []
        for sheet in self.sheets:
            if sheet.name in selected:
                merged.extend(sheet.tag_names)
        return tuple(dict.fromkeys(merged))


class WorkbookInspector:
    """Inspect Excel workbooks and extract candidate trend tags."""

    def inspect(self, source: str | Path) -> WorkbookInspectionResult:
        source_path = Path(source)
        sheet_map = read_workbook_frames(source_path)

        sheet_summaries: list[WorkbookSheetSummary] = []
        data_sheet_names = [
            name
            for name, frame in sheet_map.items()
            if isinstance(frame, pl.DataFrame) and self._find_timestamp_column(frame) is not None
        ]
        multiple_data_sheets = len(data_sheet_names) > 1

        for sheet_name, frame in sheet_map.items():
            if not isinstance(frame, pl.DataFrame):
                continue

            timestamp_column = self._find_timestamp_column(frame)
            tag_names: tuple[str, ...] = ()
            if timestamp_column is not None:
                tag_names = tuple(
                    self._qualify_tag_name(sheet_name, column_name, prefix=multiple_data_sheets)
                    for column_name in frame.columns
                    if column_name != timestamp_column
                )

            sheet_summaries.append(
                WorkbookSheetSummary(
                    name=sheet_name,
                    row_count=frame.height,
                    column_count=frame.width,
                    timestamp_column=timestamp_column,
                    tag_names=tag_names,
                )
            )

        return WorkbookInspectionResult(
            source_path=source_path,
            sheets=tuple(sheet_summaries),
        )

    def _find_timestamp_column(self, frame: pl.DataFrame) -> str | None:
        normalized_names = {
            column_name: self._normalize_column_name(column_name)
            for column_name in frame.columns
        }

        for candidate in TIMESTAMP_COLUMN_CANDIDATES:
            for original_name, normalized_name in normalized_names.items():
                if normalized_name == candidate:
                    return original_name

        for original_name, normalized_name in normalized_names.items():
            parts = normalized_name.split()
            if any(candidate in parts for candidate in TIMESTAMP_COLUMN_CANDIDATES):
                return original_name

        for column_name, dtype in frame.schema.items():
            if dtype.is_temporal():
                return column_name

        return None

    def _normalize_column_name(self, value: str) -> str:
        collapsed = NORMALIZED_NAME_PATTERN.sub(" ", value.strip().lower())
        return " ".join(collapsed.split())

    def _qualify_tag_name(self, sheet_name: str, column_name: str, *, prefix: bool) -> str:
        if prefix:
            return f"{sheet_name}/{column_name}"
        return column_name


def read_workbook_frames(source: str | Path) -> dict[str, pl.DataFrame]:
    source_path = Path(source)
    frames = pl.read_excel(
        source_path,
        sheet_id=0,
        engine="calamine",
        infer_schema_length=EXCEL_SCHEMA_INFER_LENGTH,
    )

    if isinstance(frames, pl.DataFrame):
        return {source_path.stem: frames}

    return {
        sheet_name: frame
        for sheet_name, frame in frames.items()
        if isinstance(frame, pl.DataFrame)
    }
