# Fold Redesign: Per-Region Fold/Unfold

## Problem

Current fold is a global toggle (`f`): all empty regions collapse or expand at once.
Cursor skips over folded regions entirely — they're visible but unreachable.
No way to expand just one region while keeping others collapsed.

## Desired Behavior

- **`f`** — toggle fold for the region at cursor:
  - Cursor on an empty slot → fold the contiguous empty run containing it
  - Cursor on a folded region → expand it back to individual slots
  - Cursor on an occupied slot → no-op
- **`F`** (shift) — fold ALL empty regions at once (bulk fold)
- Cursor **can land on** folded region rows (arrow keys, page up/down)
- Enter/details/waveform do nothing on folded regions
- **Scroll anchor**: when folding/unfolding, the selected cell stays in the same visual position relative to the viewport — no jumping

## Current Architecture

### State (`src/tui/state.py`)
- `FoldedRegion(start_slot, end_slot, count)` — dataclass for a collapsed run
- `build_visible_rows(slots, fold: bool, min_run=2)` — global bool, returns `list[SlotRow | FoldedRegion]`
- `VisibleRow = SlotRow | FoldedRegion`

### App (`src/tui/app.py`)
- `self._fold_empty: bool` — single global toggle
- `self._visible_rows: list[FoldedRegion | SlotRow]` — rebuilt on `_refresh_table()`
- `_refresh_table()` calls `build_visible_rows(slots, self._fold_empty)`, rebuilds DataTable
- `_next_slot_row()` skips `FoldedRegion` rows (cursor never lands on them)
- `_slot_to_table_row()` maps slot number → table row index
- `action_toggle_fold()` flips `_fold_empty`, calls `_refresh_table()`
- Binding: `f` → `action_toggle_fold`

### UI (`src/tui/ui.py`)
- `table_row_values()` handles both `SlotRow` and `FoldedRegion`, returns 7-tuple

### Tests (`tests/unit/test_tui_state.py`)
- 8 tests for `build_visible_rows` covering fold on/off, thresholds, ordering

## Implementation Plan

### Step 1: Change fold state from `bool` to `set[tuple]` in app

**File: `src/tui/app.py`**

Replace:
```python
self._fold_empty: bool = False
```
With:
```python
self._folded_regions: set[tuple[int, int]] = set()
# Each entry is (start_slot, end_slot) of a folded empty run
```

### Step 2: Rewrite `build_visible_rows` signature

**File: `src/tui/state.py`**

Change signature from:
```python
def build_visible_rows(slots, fold: bool, min_run=2)
```
To:
```python
def build_visible_rows(slots, folded_regions: set[tuple[int, int]], min_run=2)
```

Logic change:
1. Always scan for contiguous empty runs (same as current `fold=True` path)
2. For each run, check if `(start, end)` is in `folded_regions`
   - If yes → emit `FoldedRegion`
   - If no → emit individual `SlotRow` items
3. When `folded_regions` is empty → all slots visible (equivalent to old `fold=False`)

### Step 3: Implement `f` as per-region toggle

**File: `src/tui/app.py`**

New `action_toggle_fold()`:
```
1. Get current cursor item from self._visible_rows[table.cursor_row]
2. If FoldedRegion → remove (start_slot, end_slot) from self._folded_regions (unfold)
3. If SlotRow and not exists → find the contiguous empty run containing this slot,
   add (run_start, run_end) to self._folded_regions (fold)
4. If SlotRow and exists → no-op
5. Call _refresh_table()
```

Finding the contiguous run: scan `self.state.slots` outward from current slot while `not exists`.

### Step 4: Implement `F` as fold-all

**File: `src/tui/app.py`**

New `action_fold_all()`:
```
1. Scan all slots, identify all contiguous empty runs of length >= min_run
2. Add all (start, end) tuples to self._folded_regions
3. Call _refresh_table()
```

Add binding: `Binding("F", "fold_all", "Fold All")`

### Step 5: Allow cursor to land on folded regions

**File: `src/tui/app.py`**

- **Remove** the `_next_slot_row()` skip logic from `action_cursor_down/up`
  - Arrow keys now use default DataTable behavior (lands on any row including folded)
- **Remove** `_next_slot_row()` method entirely
- In `on_data_table_row_highlighted`: when cursor is on a `FoldedRegion`, set
  `selected_slot` to `region.start_slot` (or keep previous — either works since
  details pane should show nothing)
- Details pane / waveform: check if current visible row is `FoldedRegion` → show
  "no sample" state (already handled by slot not existing)

### Step 6: Scroll anchoring on fold/unfold

**File: `src/tui/app.py`, in `_refresh_table()`**

Current code already saves/restores `scroll_x`/`scroll_y`. Enhance:

```
1. Before rebuild: record cursor_row's pixel offset from viewport top
   pixel_offset = table.scroll_y - (cursor_row * row_height)
   (or use table.cursor_coordinate and scroll_offset)
2. Rebuild table
3. Find new cursor_row for the same slot
4. Restore: set scroll_y so cursor_row sits at same pixel_offset
```

The key insight: `table.move_cursor(row=new_row, scroll=False)` + explicit
`table.scroll_to(y=computed_y)` achieves the anchor effect. Current code
already does this pattern (line 289-296) — verify it works for fold transitions
or adjust the y calculation.

### Step 7: Update fold status indicator

**File: `src/tui/app.py`, `_status_bar()`**

Replace `[fold]` suffix with count: `[3 folded]` or nothing when 0.

### Step 8: Clean up stale code

- Remove `self._fold_empty` field
- Remove `_next_slot_row()` method
- Remove fold-guard in `_copy_cursor_move` and `_jump_to_empty_slot`
  (folded regions are just rows now — copy mode can unfold-all or work as-is)
- For copy mode: when entering copy, call `action_fold_all` inverse (unfold all)
  so user sees empty slots. Or: keep folds, let user `f` to reveal targets.
  Simplest: unfold all on copy-enter, re-fold on copy-cancel/complete.

### Step 9: Maintain `_folded_regions` across inventory refreshes

When `_refresh_table()` runs after an inventory update, the empty runs may have changed
(user uploaded/deleted). Stale entries in `_folded_regions` need pruning:

```
After inventory update, before build_visible_rows:
  for (start, end) in list(self._folded_regions):
      if any slot in [start..end] now exists → remove this entry
```

This prevents a region from staying folded when it no longer consists of only empty slots.

### Step 10: Update tests

**File: `tests/unit/test_tui_state.py`**

Update all `build_visible_rows` calls from `fold=True/False` to `folded_regions=set()/set(...)`.
Add tests for:
- Per-region fold: one region folded, others not
- Fold a region, then occupy a slot in it → region removed from set
- Empty `folded_regions` → all slots visible
- Multiple non-adjacent regions folded

## Files Changed

| File | Changes |
|------|---------|
| `src/tui/state.py` | `build_visible_rows` signature + logic |
| `src/tui/app.py` | `_folded_regions` set, `action_toggle_fold`, `action_fold_all`, remove `_next_slot_row`, scroll anchor, status bar, copy-mode handling |
| `src/tui/ui.py` | No changes expected (already handles `FoldedRegion`) |
| `tests/unit/test_tui_state.py` | Update calls, add per-region tests |

## Edge Cases

- **`f` on an isolated empty slot** (run length 1): still folds it (min_run=1 for per-region, or skip if run < 2 — match current min_run=2 behavior: don't fold single empties)
- **`F` when some regions already folded**: idempotent — adds all, existing ones already in set
- **Unfold during copy mode**: `_copy_cursor_move` already unfolds all — keep this behavior
- **Page up/down landing on folded region**: fine, cursor rests there, details pane shows empty state
