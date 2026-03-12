"""Tests for WaveformWidget cursor state and rendering."""
from __future__ import annotations

import pytest
from tui.waveform_widget import WaveformWidget


def _make_widget() -> WaveformWidget:
    return WaveformWidget()


def test_initial_cursor_is_none():
    w = _make_widget()
    assert w._cursor is None


def test_set_cursor_stores_fraction():
    w = _make_widget()
    w.set_cursor(0.42)
    assert w._cursor == pytest.approx(0.42)


def test_clear_cursor_sets_none():
    w = _make_widget()
    w.set_cursor(0.5)
    w.clear_cursor()
    assert w._cursor is None


def test_set_empty_clears_cursor():
    w = _make_widget()
    w.set_cursor(0.3)
    w.set_empty()
    assert w._cursor is None


def test_set_pending_clears_cursor():
    w = _make_widget()
    w.set_cursor(0.3)
    w.set_pending(1)
    assert w._cursor is None


def test_set_not_loaded_clears_cursor():
    w = _make_widget()
    w.set_cursor(0.3)
    w.set_not_loaded(1)
    assert w._cursor is None


def test_set_bins_clears_cursor():
    w = _make_widget()
    w.set_cursor(0.3)
    bins = {"mins": [0] * 10, "maxs": [64] * 10}
    w.set_bins(1, bins)
    assert w._cursor is None


def test_set_cursor_clamps_negative():
    w = _make_widget()
    w.set_cursor(-0.5)
    assert w._cursor == 0.0


def test_render_with_cursor_inserts_bar():
    """│ appears at the correct column when cursor is set and bins are loaded."""
    from rich.text import Text
    from rich.panel import Panel

    w = _make_widget()
    bins = {"mins": [-64] * 20, "maxs": [64] * 20}
    w.set_bins(1, bins)
    w.set_cursor(0.5)

    result = w.render()
    # result is a Panel; get its renderable
    assert isinstance(result, Panel)
    content = result.renderable
    assert isinstance(content, Text)
    full = content.plain
    # With cols=72 (fallback) and fraction=0.5, cursor_col = min(36, 71) = 36
    # Each row should have │ at position 36
    lines = full.split("\n")
    for line in lines:
        # All lines padded to cols when cursor is active — │ present on every row
        assert len(line) > 36, f"Line too short: {line!r}"
        assert line[36] == "│", f"Expected │ at col 36, got {line[36]!r} in: {line!r}"
