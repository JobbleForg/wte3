from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from .workbook import (
    WorkbookInspectionResult,
    WorkbookInspector,
    WorkbookSheetSummary,
    read_workbook_frames,
)


class TrendDataError(RuntimeError):
    """Raised when workbook trend data cannot be loaded into memory."""


@dataclass(frozen=True)
class TrendSeriesData:
    tag_name: str
    sheet_name: str
    source_column: str
    values: pl.Series

    @property
    def row_count(self) -> int:
        return self.values.len()

    @property
    def non_null_count(self) -> int:
        return self.values.len() - self.values.null_count()

    @property
    def dtype_name(self) -> str:
        return str(self.values.dtype)

    def plot_points(self, timestamps: pl.Series) -> tuple[list[float], list[float]]:
        x_values: list[float] = []
        y_values: list[float] = []

        for timestamp_value, raw_value in zip(timestamps, self.values):
            x_value = _coerce_timestamp_to_epoch(timestamp_value)
            y_value = _coerce_numeric_value(raw_value)
            if x_value is None or y_value is None:
                continue
            x_values.append(x_value)
            y_values.append(y_value)

        return x_values, y_values

    def numeric_series(self) -> pl.Series:
        if self.values.dtype.is_numeric():
            return self.values.cast(pl.Float64, strict=False)
        if self.values.dtype == pl.String:
            return self.values.cast(pl.Float64, strict=False)
        return pl.Series(name=self.values.name, values=[], dtype=pl.Float64)

    def latest_numeric_value(self) -> float | None:
        numeric_values = self.numeric_series().drop_nulls()
        if numeric_values.is_empty():
            return None
        return float(numeric_values[-1])

    def minimum_value(self) -> float | None:
        value = self.numeric_series().min()
        if value is None:
            return None
        return float(value)

    def maximum_value(self) -> float | None:
        value = self.numeric_series().max()
        if value is None:
            return None
        return float(value)

    def average_value(self) -> float | None:
        value = self.numeric_series().mean()
        if value is None:
            return None
        return float(value)

    def window_statistics(
        self,
        timestamps: pl.Series,
        *,
        x_min: float | None = None,
        x_max: float | None = None,
    ) -> "TrendWindowStats":
        x_values, y_values = self.plot_points(timestamps)
        window_values = [
            y_value
            for x_value, y_value in zip(x_values, y_values)
            if (x_min is None or x_value >= x_min) and (x_max is None or x_value <= x_max)
        ]

        if not window_values:
            return TrendWindowStats(
                sample_count=0,
                latest_value=None,
                minimum_value=None,
                maximum_value=None,
                average_value=None,
            )

        return TrendWindowStats(
            sample_count=len(window_values),
            latest_value=window_values[-1],
            minimum_value=min(window_values),
            maximum_value=max(window_values),
            average_value=sum(window_values) / len(window_values),
        )


@dataclass(frozen=True)
class TrendWindowStats:
    sample_count: int
    latest_value: float | None
    minimum_value: float | None
    maximum_value: float | None
    average_value: float | None


@dataclass(frozen=True)
class TrendSheetData:
    name: str
    timestamp_column: str
    timestamps: pl.Series
    tag_series: tuple[TrendSeriesData, ...]
    row_count: int
    column_count: int

    @property
    def tag_names(self) -> tuple[str, ...]:
        return tuple(series.tag_name for series in self.tag_series)

    def first_timestamp_value(self) -> Any | None:
        return _first_non_null(self.timestamps)

    def last_timestamp_value(self) -> Any | None:
        return _last_non_null(self.timestamps)


@dataclass(frozen=True)
class LoadedTrendWorkbook:
    source_path: Path
    selected_sheet_names: tuple[str, ...]
    sheets: tuple[TrendSheetData, ...]

    @property
    def available_tags(self) -> tuple[str, ...]:
        merged: list[str] = []
        for sheet in self.sheets:
            merged.extend(sheet.tag_names)
        return tuple(dict.fromkeys(merged))

    @property
    def sheet_count(self) -> int:
        return len(self.sheets)

    @property
    def tag_count(self) -> int:
        return len(self.available_tags)

    @property
    def total_row_count(self) -> int:
        return sum(sheet.row_count for sheet in self.sheets)

    def series_for_tag(self, tag_name: str) -> TrendSeriesData | None:
        for sheet in self.sheets:
            for series in sheet.tag_series:
                if series.tag_name == tag_name:
                    return series
        return None

    def sheet_for_tag(self, tag_name: str) -> TrendSheetData | None:
        for sheet in self.sheets:
            for series in sheet.tag_series:
                if series.tag_name == tag_name:
                    return sheet
        return None


class TrendDataManager:
    """Load selected workbook sheets into an in-memory trend model."""

    def __init__(self, inspector: WorkbookInspector | None = None) -> None:
        self._inspector = inspector or WorkbookInspector()
        self._current_workbook: LoadedTrendWorkbook | None = None

    @property
    def current_workbook(self) -> LoadedTrendWorkbook | None:
        return self._current_workbook

    def clear(self) -> None:
        self._current_workbook = None

    def load_workbook(
        self,
        source: str | Path,
        selected_sheet_names: list[str] | tuple[str, ...],
        *,
        inspection: WorkbookInspectionResult | None = None,
    ) -> LoadedTrendWorkbook:
        source_path = Path(source)
        result = inspection or self._inspector.inspect(source_path)
        selected_summaries = self._resolve_selected_summaries(result, selected_sheet_names)
        sheet_map = read_workbook_frames(source_path)

        loaded_sheets = tuple(
            self._load_sheet(summary, sheet_map)
            for summary in selected_summaries
        )
        workbook = LoadedTrendWorkbook(
            source_path=source_path,
            selected_sheet_names=tuple(summary.name for summary in selected_summaries),
            sheets=loaded_sheets,
        )
        self._current_workbook = workbook
        return workbook

    def _resolve_selected_summaries(
        self,
        result: WorkbookInspectionResult,
        selected_sheet_names: list[str] | tuple[str, ...],
    ) -> list[WorkbookSheetSummary]:
        requested_names = [str(name).strip() for name in selected_sheet_names if str(name).strip()]
        data_summaries = {sheet.name: sheet for sheet in result.data_sheets}
        selected_summaries = [
            data_summaries[sheet_name]
            for sheet_name in requested_names
            if sheet_name in data_summaries
        ]

        if not selected_summaries:
            raise TrendDataError("Select at least one worksheet that contains trend data.")

        return selected_summaries

    def _load_sheet(
        self,
        summary: WorkbookSheetSummary,
        sheet_map: dict[str, pl.DataFrame],
    ) -> TrendSheetData:
        frame = sheet_map.get(summary.name)
        if frame is None:
            raise TrendDataError(f"Worksheet '{summary.name}' could not be read from the workbook.")

        if summary.timestamp_column is None:
            raise TrendDataError(
                f"Worksheet '{summary.name}' does not have a recognized timestamp column."
            )

        try:
            timestamps = frame.get_column(summary.timestamp_column)
        except Exception as exc:
            raise TrendDataError(
                f"Timestamp column '{summary.timestamp_column}' was not found in '{summary.name}'."
            ) from exc

        value_columns = [column_name for column_name in frame.columns if column_name != summary.timestamp_column]
        qualified_tag_names = summary.tag_names
        if len(qualified_tag_names) != len(value_columns):
            raise TrendDataError(
                f"Worksheet '{summary.name}' changed shape between inspection and load."
            )

        tag_series = tuple(
            TrendSeriesData(
                tag_name=tag_name,
                sheet_name=summary.name,
                source_column=column_name,
                values=frame.get_column(column_name),
            )
            for tag_name, column_name in zip(qualified_tag_names, value_columns, strict=True)
        )

        return TrendSheetData(
            name=summary.name,
            timestamp_column=summary.timestamp_column,
            timestamps=timestamps,
            tag_series=tag_series,
            row_count=frame.height,
            column_count=frame.width,
        )


def _first_non_null(series: pl.Series) -> Any | None:
    for value in series:
        if value is not None:
            return value
    return None


def _last_non_null(series: pl.Series) -> Any | None:
    values = series.to_list()
    for value in reversed(values):
        if value is not None:
            return value
    return None


def _coerce_timestamp_to_epoch(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _datetime_to_epoch(value)
    if isinstance(value, date):
        return _datetime_to_epoch(datetime.combine(value, time.min))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return _datetime_to_epoch(datetime.fromisoformat(text.replace("Z", "+00:00")))
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        if value > 10_000:
            return float(value)
        excel_epoch = datetime(1899, 12, 30)
        return _datetime_to_epoch(excel_epoch + timedelta(days=float(value)))
    return None


def _coerce_numeric_value(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _datetime_to_epoch(value: datetime) -> float:
    if value.tzinfo is not None:
        return value.timestamp()
    try:
        return value.timestamp()
    except OSError:
        local_timezone = datetime.now().astimezone().tzinfo
        if local_timezone is None:
            raise
        return value.replace(tzinfo=local_timezone).timestamp()
