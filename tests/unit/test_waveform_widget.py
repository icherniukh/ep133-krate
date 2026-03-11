"""Tests for WaveformWidget cursor state and rendering."""
from __future__ import annotations

import pytest
from ko2_tui.waveform_widget import WaveformWidget


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
