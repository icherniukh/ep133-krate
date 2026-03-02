from __future__ import annotations

import pytest

from ko2_tui.selectors import RangeSelector, parse_selector
from ko2_tui.state import TuiState


def _slots(state: TuiState) -> dict:
    return state.slots


def test_single_slot():
    state = TuiState()
    assert RangeSelector("200").resolve(_slots(state)) == {200}


def test_comma_list():
    state = TuiState()
    assert RangeSelector("201,202").resolve(_slots(state)) == {201, 202}


def test_inclusive_range():
    state = TuiState()
    result = RangeSelector("200-205").resolve(_slots(state))
    assert result == {200, 201, 202, 203, 204, 205}


def test_mixed_list_and_range():
    state = TuiState()
    result = RangeSelector("101,201-205").resolve(_slots(state))
    assert result == {101, 201, 202, 203, 204, 205}


def test_spaces_are_ignored():
    state = TuiState()
    assert RangeSelector("200, 201 - 203").resolve(_slots(state)) == {200, 201, 202, 203}


def test_slot_outside_available_set_is_skipped():
    state = TuiState()
    assert RangeSelector("1000").resolve(_slots(state)) == set()


def test_range_beyond_max_clipped_to_available():
    state = TuiState()
    result = RangeSelector("995-1005").resolve(_slots(state))
    assert result == {995, 996, 997, 998, 999}


def test_inverted_range_produces_empty_set():
    state = TuiState()
    # range(300, 200) is empty — silently yields nothing
    assert RangeSelector("300-200").resolve(_slots(state)) == set()


def test_empty_tokens_skipped():
    state = TuiState()
    # leading/trailing commas produce empty tokens
    assert RangeSelector(",200,").resolve(_slots(state)) == {200}


def test_non_integer_raises_value_error():
    state = TuiState()
    with pytest.raises(ValueError):
        RangeSelector("abc").resolve(_slots(state))


def test_parse_selector_returns_range_selector():
    sel = parse_selector("200-299")
    assert isinstance(sel, RangeSelector)


def test_parse_selector_result_resolves():
    state = TuiState()
    result = parse_selector("1,2,3").resolve(_slots(state))
    assert result == {1, 2, 3}
