from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from wte_trend_viewer.data_manager import (
    TrendDataError,
    TrendDataManager,
    TrendSeriesData,
    _coerce_numeric_value,
    _coerce_timestamp_to_epoch,
)
from wte_trend_viewer.workbook import WorkbookInspectionResult, WorkbookSheetSummary


def _local_epoch_seconds(value: datetime) -> float:
    local_timezone = datetime.now().astimezone().tzinfo
    return value.replace(tzinfo=local_timezone).timestamp()


def test_plot_points_skip_non_numeric_or_missing_values() -> None:
    timestamps = pl.Series(
        "timestamp",
        [
            datetime(2026, 1, 1, 12, 0, 0),
            datetime(2026, 1, 1, 12, 5, 0),
            None,
            datetime(2026, 1, 1, 12, 15, 0),
        ],
    )
    series = TrendSeriesData(
        tag_name="Flow",
        sheet_name="Sheet1",
        source_column="Flow",
        values=pl.Series("Flow", ["1.5", "bad", "3.0", None], strict=False),
    )

    x_values, y_values = series.plot_points(timestamps)

    assert x_values == [datetime(2026, 1, 1, 12, 0, 0).timestamp()]
    assert y_values == [1.5]


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("2026-01-01T12:00:00", _local_epoch_seconds(datetime(2026, 1, 1, 12, 0, 0))),
        (
            2.5,
            _local_epoch_seconds(datetime(1899, 12, 30) + timedelta(days=2.5)),
        ),
        (20_000, 20_000.0),
    ],
)
def test_coerce_timestamp_to_epoch_handles_supported_inputs(
    raw_value: object,
    expected: float,
) -> None:
    assert _coerce_timestamp_to_epoch(raw_value) == expected


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (None, None),
        (True, None),
        ("  ", None),
        ("4.2", 4.2),
        (7, 7.0),
    ],
)
def test_coerce_numeric_value_filters_invalid_inputs(
    raw_value: object,
    expected: float | None,
) -> None:
    assert _coerce_numeric_value(raw_value) == expected


def test_resolve_selected_summaries_requires_data_sheet() -> None:
    manager = TrendDataManager()
    result = WorkbookInspectionResult(
        source_path=Path("dummy.xlsx"),
        sheets=(
            WorkbookSheetSummary(
                name="Meta",
                row_count=1,
                column_count=1,
                timestamp_column=None,
                tag_names=(),
            ),
        ),
    )

    with pytest.raises(TrendDataError, match="Select at least one worksheet"):
        manager._resolve_selected_summaries(result, ["Meta"])
