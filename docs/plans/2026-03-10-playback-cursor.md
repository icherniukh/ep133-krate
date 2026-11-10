# Playback Cursor Animation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Animate a vertical cursor line sweeping across the braille waveform display during sample playback (audition), at 15fps, for the duration of the sample.

**Architecture:** The worker emits an `audition_started` event (with slot + duration_s) after the device ACKs playback. The app starts a 15fps Textual interval timer that computes elapsed fraction and calls `waveform_widget.set_cursor(fraction)`. The widget overlays a `│` character at that column in the braille render. Timer cancels itself when fraction ≥ 1.0.

**Tech Stack:** Python 3.11+, Textual 0.x, Rich Text, `time.monotonic()`

---

### Task 1: WaveformWidget — cursor state and rendering

**Files:**
- Modify: `ko2_tui/waveform_widget.py`
- Test: `tests/unit/test_waveform_widget.py` (create new)

**Step 1: Write failing tests**

Create `tests/unit/test_waveform_widget.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/unit/test_waveform_widget.py -v
```

Expected: `AttributeError: 'WaveformWidget' object has no attribute '_cursor'`

**Step 3: Implement cursor state in WaveformWidget**

In `ko2_tui/waveform_widget.py`, add `_cursor` field and methods, and clear it in all state-setting methods:

```python
class WaveformWidget(Static):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__("", **kwargs)
        self._slot: int | None = None
        self._pending: bool = False
        self._bins: dict[str, Any] | None = None
        self._cursor: float | None = None  # ADD THIS

    def set_empty(self) -> None:
        self._slot = None
        self._pending = False
        self._bins = None
        self._cursor = None  # ADD THIS
        self.refresh()

    def set_pending(self, slot: int) -> None:
        self._slot = slot
        self._pending = True
        self._bins = None
        self._cursor = None  # ADD THIS
        self.refresh()

    def set_not_loaded(self, slot: int) -> None:
        self._slot = slot
        self._pending = False
        self._bins = None
        self._cursor = None  # ADD THIS
        self.refresh()

    def set_bins(self, slot: int, bins: dict[str, Any]) -> None:
        self._slot = slot
        self._pending = False
        self._bins = bins
        self._cursor = None  # ADD THIS
        self.refresh()

    # ADD THESE TWO METHODS (after set_bins):
    def set_cursor(self, fraction: float) -> None:
        """Set playback cursor position. fraction in [0.0, 1.0)."""
        self._cursor = float(fraction)
        self.refresh()

    def clear_cursor(self) -> None:
        """Remove playback cursor."""
        if self._cursor is not None:
            self._cursor = None
            self.refresh()
```

**Step 4: Overlay cursor in render()**

In the `render()` method, find the `_bins` path (around line 66). After building `art`, add cursor overlay before building the `Text` object:

```python
    def render(self) -> RenderableType:
        # ... (existing empty/pending/not_loaded paths unchanged) ...

        bins = self._bins
        w = int(self.size.width or 0)
        h = int(self.size.height or 0)
        cols = max(24, w - 4) if w > 0 else 72
        rows = max(4, h - 2) if h > 0 else 10
        art = _render_waveform_braille(
            cast(list[int], bins.get("mins", [])),
            cast(list[int], bins.get("maxs", [])),
            width_chars=cols,
            height_chars=rows,
        )

        # --- NEW: cursor column ---
        cursor_col: int | None = None
        if self._cursor is not None:
            cursor_col = min(int(self._cursor * cols), cols - 1)
        # --- END NEW ---

        text = Text()
        center = (len(art) - 1) / 2.0
        for idx, line in enumerate(art):
            dist = abs(idx - center) / center if center > 0 else 0.0
            color = "#f59e0b" if dist > 0.75 else "#2dd4bf" if dist > 0.4 else "#22d3ee"
            # --- NEW: split line at cursor column ---
            if cursor_col is not None and cursor_col < len(line):
                text.append(line[:cursor_col], style=f"bold {color}")
                text.append("│", style="bold bright_white")
                text.append(line[cursor_col + 1:], style=f"bold {color}")
            else:
                text.append(line, style=f"bold {color}")
            # --- END NEW ---
            if idx < len(art) - 1:
                text.append("\n")
        return Panel(
            text,
            title=f"Waveform {slot:03d}",
            subtitle="cached",
            border_style="#0ea5e9",
        )
```

**Step 5: Run tests**

```bash
python3 -m pytest tests/unit/test_waveform_widget.py -v
```

Expected: all 7 tests PASS.

**Step 6: Run full suite to check for regressions**

```bash
python3 -m pytest tests/unit/ -v --tb=short
```

Expected: all existing tests still pass.

**Step 7: Commit**

```bash
git add ko2_tui/waveform_widget.py tests/unit/test_waveform_widget.py
git commit -m "feat(tui): add playback cursor state and rendering to WaveformWidget"
```

---

### Task 2: Worker + Actions — emit `audition_started` event

**Files:**
- Modify: `ko2_tui/actions.py`
- Modify: `ko2_tui/worker.py`
- Modify: `tests/unit/test_audition.py`

**Step 1: Write failing test**

In `tests/unit/test_audition.py`, add a test that verifies the worker emits `audition_started` after ACK. Find the existing worker test pattern and add:

```python
def test_worker_emits_audition_started():
    """Worker should emit audition_started with slot and duration_s after ACK."""
    from ko2_tui.worker import DeviceWorker, WorkerEvent
    from ko2_tui.actions import WorkerRequest
    from queue import Queue

    events: list[WorkerEvent] = []

    class FakeAuditionClient:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def audition(self, slot): pass

    req_q: Queue = Queue()
    evt_q: Queue = Queue()
    req_q.put(WorkerRequest(op="audition", payload={"slot": 5, "duration_s": 2.0}))
    req_q.put(WorkerRequest(op="stop"))

    worker = DeviceWorker(
        device_name="test",
        request_queue=req_q,
        event_queue=evt_q,
        client_factory=lambda name, **kw: FakeAuditionClient(),
    )
    worker.run()

    while not evt_q.empty():
        events.append(evt_q.get_nowait())

    kinds = [e.kind for e in events]
    assert "audition_started" in kinds

    ev = next(e for e in events if e.kind == "audition_started")
    assert ev.payload["slot"] == 5
    assert ev.payload["duration_s"] == pytest.approx(2.0)
```

**Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/unit/test_audition.py::test_worker_emits_audition_started -v
```

Expected: FAIL — `audition_started` not in events.

**Step 3: Update `actions.audition()` to accept duration_s**

In `ko2_tui/actions.py`, change:

```python
def audition(slot: int, duration_s: float = 0.0) -> WorkerRequest:
    return WorkerRequest(op="audition", payload={"slot": int(slot), "duration_s": float(duration_s)})
```

**Step 4: Update worker to emit `audition_started`**

In `ko2_tui/worker.py`, find the `elif req.op == "audition":` block (around line 120) and add the emit:

```python
elif req.op == "audition":
    slot = int(req.payload["slot"])
    duration_s = float(req.payload.get("duration_s") or 0.0)
    self._timed("device.audition", phases, client.audition, slot)
    if duration_s > 0:
        self._emit("audition_started", slot=slot, duration_s=duration_s)
    self._emit_success(f"Auditioning slot {slot:03d}", started_at=t_start)
```

**Step 5: Run the new test**

```bash
python3 -m pytest tests/unit/test_audition.py::test_worker_emits_audition_started -v
```

Expected: PASS.

**Step 6: Run full suite**

```bash
python3 -m pytest tests/unit/ -v --tb=short
```

Expected: all tests pass.

**Step 7: Commit**

```bash
git add ko2_tui/actions.py ko2_tui/worker.py tests/unit/test_audition.py
git commit -m "feat(tui): emit audition_started event with duration after device ACK"
```

---

### Task 3: App — handle `audition_started`, drive 15fps timer

**Files:**
- Modify: `ko2_tui/app.py`
- Modify: `tests/unit/test_tui_keybinds.py`

**Step 1: Write failing tests**

Add to `tests/unit/test_tui_keybinds.py`:

```python
def test_audition_started_event_initializes_playback_state():
    """audition_started event sets _play_slot, _play_duration, _play_start."""
    import time
    app = TUIApp.__new__(TUIApp)
    app.__init__(device_name="test")

    # Fake the waveform widget lookup — not needed for state-only check
    app._play_slot = None
    app._play_duration = 0.0
    app._play_start = 0.0
    app._play_timer = None

    before = time.monotonic()
    app._start_playback_animation(slot=3, duration_s=1.5)
    after = time.monotonic()

    assert app._play_slot == 3
    assert app._play_duration == pytest.approx(1.5)
    assert before <= app._play_start <= after
    # Clean up
    if app._play_timer:
        app._play_timer.stop()
```

> Note: testing the timer-driven UI in isolation is hard without a running Textual app. The above test checks state initialization only. The `_on_playback_tick` logic is covered by the widget tests (cursor appears/disappears correctly).

**Step 2: Run test**

```bash
python3 -m pytest tests/unit/test_tui_keybinds.py::test_audition_started_event_initializes_playback_state -v
```

Expected: FAIL — `TUIApp` has no `_start_playback_animation`.

**Step 3: Add playback animation state and methods to TUIApp**

In `ko2_tui/app.py`:

**3a.** Add `import time` at top if not already present (check — it likely isn't).

**3b.** Add `SAMPLE_RATE` import if needed:
```python
from ko2_models import MAX_SLOTS, SAMPLE_RATE
```
(Check: SAMPLE_RATE is already imported in `ko2_tui/state.py` from `ko2_models`. Check app.py imports.)

**3c.** In `__init__`, add the new playback tracking fields after the existing waveform fields:

```python
        # Playback cursor animation
        self._play_slot: int | None = None
        self._play_start: float = 0.0
        self._play_duration: float = 0.0
        self._play_timer: Any | None = None
```

**3d.** Add three methods after `_update_waveform` (around line 729):

```python
    def _start_playback_animation(self, slot: int, duration_s: float) -> None:
        self._stop_playback_animation()
        self._play_slot = slot
        self._play_start = time.monotonic()
        self._play_duration = duration_s
        self._play_timer = self.set_interval(1 / 15, self._on_playback_tick)

    def _stop_playback_animation(self) -> None:
        if self._play_timer is not None:
            self._play_timer.stop()
            self._play_timer = None
        try:
            widget = self.query_one("#waveform", WaveformWidget)
            widget.clear_cursor()
        except Exception:
            pass
        self._play_slot = None

    def _on_playback_tick(self) -> None:
        if self._play_slot is None or self._play_duration <= 0:
            self._stop_playback_animation()
            return
        elapsed = time.monotonic() - self._play_start
        fraction = elapsed / self._play_duration
        if fraction >= 1.0:
            self._stop_playback_animation()
            return
        if self._play_slot == self.state.selected_slot:
            try:
                widget = self.query_one("#waveform", WaveformWidget)
                widget.set_cursor(fraction)
            except Exception:
                pass
```

**3e.** In `action_audition`, compute duration and pass it in the request:

Find `action_audition` (around line 998):

```python
    def action_audition(self) -> None:
        slot = self._current_slot()
        row = self.state.slots.get(slot)
        if not row or not row.exists:
            return
        sr = row.samplerate or SAMPLE_RATE
        ch = max(row.channels, 1)
        duration_s = row.size_bytes / (sr * ch * 2) if row.size_bytes > 0 else 0.0
        self._queue_request(actions.audition(slot, duration_s=duration_s))
```

**3f.** In `_handle_event`, add handler for `audition_started` (before the `success` handler around line 460):

```python
        if kind == "audition_started":
            slot = int(payload.get("slot") or 0)
            duration_s = float(payload.get("duration_s") or 0.0)
            if slot and duration_s > 0:
                self._start_playback_animation(slot, duration_s)
            return
```

**Step 4: Run the test**

```bash
python3 -m pytest tests/unit/test_tui_keybinds.py::test_audition_started_event_initializes_playback_state -v
```

Expected: PASS.

**Step 5: Run full suite**

```bash
python3 -m pytest tests/unit/ -v --tb=short
```

Expected: all 370+ tests pass, zero regressions.

**Step 6: Commit**

```bash
git add ko2_tui/app.py tests/unit/test_tui_keybinds.py
git commit -m "feat(tui): animate playback cursor over waveform at 15fps during audition"
```

---

## Summary

| Task | Files changed | New tests |
|------|--------------|-----------|
| 1: Widget cursor | `waveform_widget.py` | 7 in `test_waveform_widget.py` |
| 2: Worker event | `actions.py`, `worker.py` | 1 in `test_audition.py` |
| 3: App timer | `app.py` | 1 in `test_tui_keybinds.py` |

Total: 3 commits, ~9 new tests, ~60 lines of new code.
