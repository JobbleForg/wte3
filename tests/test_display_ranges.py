from __future__ import annotations

from wte_trend_viewer.session import SessionStore
from wte_trend_viewer.ui.main_window import TrendViewerMainWindow


def test_display_ranges_are_scoped_to_selected_tag_set(qapp, tmp_path) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path),
        restore_last_session=False,
    )

    window._current_preview_tag_names = ["TagB", "TagA"]
    window._set_display_range("TagA", 10.0, 20.0)

    window._current_preview_tag_names = ["TagA"]
    window._set_display_range("TagA", 1.0, 2.0)

    window._current_preview_tag_names = ["TagA", "TagB"]
    assert window._stored_display_range("TagA") == (10.0, 20.0)

    window._current_preview_tag_names = ["TagA"]
    assert window._stored_display_range("TagA") == (1.0, 2.0)


def test_display_range_selection_key_ignores_tag_order(qapp, tmp_path) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path),
        restore_last_session=False,
    )

    window._current_preview_tag_names = ["TagB", "TagA"]
    window._set_display_range("TagA", 10.0, 20.0)

    window._current_preview_tag_names = ["TagA", "TagB"]
    assert window._stored_display_range("TagA") == (10.0, 20.0)


def test_selection_scoped_display_ranges_persist_in_session(qapp, tmp_path) -> None:
    session_store = SessionStore(tmp_path)
    window = TrendViewerMainWindow(
        session_store=session_store,
        restore_last_session=False,
    )
    window._current_preview_tag_names = ["TagB", "TagA"]
    window._set_display_range("TagA", 10.0, 20.0)

    session = window._capture_session()

    restored_window = TrendViewerMainWindow(
        session_store=session_store,
        restore_last_session=False,
    )
    restored_window._apply_session(session)
    restored_window._current_preview_tag_names = ["TagA", "TagB"]

    assert restored_window._stored_display_range("TagA") == (10.0, 20.0)
