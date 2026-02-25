---
name: ko2-tui-threading
description: Threading patterns for bridging ko2_client.py (synchronous, blocking MIDI client) into a Textual TUI. Use when implementing any TUI feature that talks to the EP-133 device — connection management, sample listing, upload/download, delete, status polling. Read this before using the generic textual-tui worker patterns; this client has specific constraints.
spec-commit: 28f3c8b  # ko2_client.py at this commit
---

# ko2-tui: Bridging EP133Client into Textual

## The Core Constraint

`EP133Client` in `ko2_client.py` is **entirely synchronous and blocking**. It uses `mido.open_input()` with polling loops, `time.sleep()` for timing, and `_send_and_wait()` with deadline-based busy-poll loops (up to 2s per operation, 5s for init/upload). There is no asyncio, no queues, no callbacks.

**Consequence for Textual:**
- You **cannot** `run_worker(coroutine)` — there is no coroutine
- You **must** use `run_worker(fn, thread=True)` — blocking work runs in a OS thread
- You **must** use `call_from_thread()` to push results back to the main thread
- All device operations **must be serialized** — `EP133Client._seq` (sequence counter) is not thread-safe; concurrent calls from multiple workers will corrupt it

## Available Public Methods

From `ko2_client.py` (verified at spec-commit):

```python
client.list_sounds()              # -> dict[int, dict]  filesystem listing
client.list_slots(start, end)     # -> list[SampleInfo]  slot range
client.get(slot, output_path)     # -> Path  download sample
client.put(path, slot, name, progress, debug)  # -> None  upload (blocking)
client.delete(slot)               # -> None  fire-and-forget
client.get_meta(slot)             # -> dict | None  (unreliable, avoid)
client.get_node_metadata(node_id) # -> dict | None  reliable metadata
client.rename(slot, new_name)     # -> None
client.list_directory(node_id)    # -> list[dict]
```

Key: `list_sounds()` not `list_samples()`. `put()` is a single blocking call, not a generator.

## EP133Client Lifecycle in TUI Context

The client is a blocking context manager (`with EP133Client(port) as client:`). In a TUI it must stay open for the full session. Pattern:

```python
from textual.app import App, ComposeResult
from textual.reactive import reactive
from ko2_client import EP133Client, find_device, EP133Error, SlotEmptyError

class KO2App(App):
    _client: EP133Client | None = None
    _shutdown: bool = False

    def on_mount(self) -> None:
        self.run_worker(self._connect, thread=True, name="connect")

    def _connect(self) -> None:
        """Thread: opens client and blocks until app shuts down."""
        port = find_device()
        if port is None:
            self.call_from_thread(self.post_message, self.StateChanged("error", "No EP-133 found"))
            return
        try:
            with EP133Client(port) as client:
                self._client = client
                self.call_from_thread(self.post_message, self.StateChanged("connected"))
                # Block here keeping context manager open
                while not self._shutdown:
                    import time; time.sleep(0.1)
        except EP133Error as e:
            self.call_from_thread(self.post_message, self.StateChanged("error", str(e)))
        finally:
            self._client = None

    def on_unmount(self) -> None:
        self._shutdown = True  # signals _connect loop to exit → context manager closes

    class StateChanged(Message):
        def __init__(self, state: str, detail: str = "") -> None:
            super().__init__()
            self.state = state
            self.detail = detail
```

**Important:** `_client` is set from the thread but read from the main thread. Treat it as read-only from the main thread after it's set. All mutations go through workers.

## Device Operation Worker Pattern

Every device call runs in a `thread=True` worker. Never call `EP133Client` methods on the main thread.

```python
from textual.worker import Worker, WorkerState

class SampleListScreen(Screen):

    def action_refresh(self) -> None:
        if self.app._client is None:
            self.notify("Not connected", severity="warning")
            return
        self.run_worker(self._fetch_sounds, thread=True,
                        exclusive=True, name="fetch_sounds")

    def _fetch_sounds(self) -> None:
        """Thread: blocking MIDI operations."""
        try:
            sounds = self.app._client.list_sounds()
            self.call_from_thread(self.post_message, self.SoundsLoaded(sounds))
        except SlotEmptyError:
            pass  # expected during listing — not a device error
        except EP133Error as e:
            self.call_from_thread(self.post_message, self.DeviceError(str(e)))

    class SoundsLoaded(Message):
        def __init__(self, sounds: dict) -> None:
            super().__init__()
            self.sounds = sounds

    class DeviceError(Message):
        def __init__(self, error: str) -> None:
            super().__init__()
            self.error = error

    def on_sample_list_screen_sounds_loaded(self, msg: SoundsLoaded) -> None:
        table = self.query_one(DataTable)
        table.clear()
        for slot, info in sorted(msg.sounds.items()):
            table.add_row(slot, info.get("name", ""), info.get("size", 0))

    def on_sample_list_screen_device_error(self, msg: DeviceError) -> None:
        self.notify(f"Device error: {msg.error}", severity="error")
```

## Upload Pattern

`put()` is a **single blocking call** — there is no chunked/generator API. It logs progress to stdout. For TUI progress, wrap at a higher level:

```python
class UploadScreen(Screen):
    _upload_worker: Worker | None = None

    def start_upload(self, path: Path, slot: int) -> None:
        self._upload_worker = self.run_worker(
            lambda: self._do_upload(path, slot),
            thread=True,
            exclusive=True,
            name=f"upload_{slot}",
        )

    def _do_upload(self, path: Path, slot: int) -> None:
        """Thread: blocking upload (init + N chunks + end + metadata + re-init)."""
        try:
            self.call_from_thread(self.post_message, self.UploadStarted(slot))
            self.app._client.put(path, slot, progress=False)
            self.call_from_thread(self.post_message, self.UploadDone(slot))
        except ValueError as e:
            # put() raises ValueError for wrong sample rate/channels/bit depth
            self.call_from_thread(self.post_message, self.UploadFailed(slot, str(e)))
        except EP133Error as e:
            self.call_from_thread(self.post_message, self.UploadFailed(slot, str(e)))

    def action_cancel_upload(self) -> None:
        if self._upload_worker and not self._upload_worker.is_finished:
            self._upload_worker.cancel()
            # Note: cancel() does NOT interrupt blocking MIDI I/O in progress.
            # It will stop before the next Python-level chunk loop iteration.
```

## Delete Behavior

`delete()` is **fire-and-forget**: sends the message + `time.sleep(0.1)`, no response awaited. It will not raise on device-side failure. Wrap defensively:

```python
def _do_delete(self, slot: int) -> None:
    try:
        self.app._client.delete(slot)
        self.call_from_thread(self.post_message, self.DeleteDone(slot))
    except EP133Error as e:
        self.call_from_thread(self.post_message, self.DeviceError(str(e)))
```

## Error Hierarchy

```
EP133Error (base)
├── DeviceNotFoundError  — no EP-133 on any MIDI port
└── SlotEmptyError       — slot has no sample (expected during list operations)
```

Distinguish `SlotEmptyError` from actual device errors — it's expected when probing empty slots and should not surface as a UI error notification.

## Thread Safety Rules

| Do | Don't |
|----|-------|
| `call_from_thread(widget.update, value)` | Modify widgets directly from thread |
| `call_from_thread(self.post_message, Msg())` | Call `self.query_one()` from thread |
| Pass results via `Message` subclasses | Call client methods from main thread |
| `exclusive=True` to prevent duplicate ops | Start concurrent workers on same client |
| Serialize all client ops (one at a time) | Two workers calling client simultaneously |

## Connection State Machine

```python
from enum import Enum

class DeviceState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    BUSY = "busy"
```

Drive UI from state reactive:

```python
class KO2App(App):
    device_state: reactive[str] = reactive("disconnected")

    def watch_device_state(self, state: str) -> None:
        for btn in self.query(".requires-device"):
            btn.disabled = state != "connected"
```

## Known EP133Client Constraints

1. **`list_sounds()` not `list_samples()`** — there is no `list_samples()` method
2. **`put()` enforces 46,875 Hz** — raises `ValueError` for other rates; validate WAV before calling
3. **`get_meta()` is unreliable** — returns stale/cached data; use `get_node_metadata(node_id)` instead
4. **Sequence counter** (`_seq`) is an instance variable — concurrent workers will corrupt it; enforce one operation at a time
5. **`delete()` is fire-and-forget** — no response, no failure detection
6. **Per-operation blocking time**: `_send_and_wait()` defaults to 2s timeout; init/upload can block up to 5s; cancelling a worker won't interrupt in-progress MIDI I/O
7. **No reconnect API**: to reconnect after disconnect, you need a new `with EP133Client(...)` block — close the old one first

## Planned File Structure

```
tui/
├── app.py              # KO2App — connection lifecycle, global state
├── screens/
│   ├── main.py         # Sample grid, navigation
│   ├── upload.py       # Upload flow
│   └── detail.py       # Sample detail / rename / trim
├── widgets/
│   ├── sample_grid.py  # 10×100 slot display
│   ├── status_bar.py   # Connection state
│   └── progress.py     # Upload progress (indeterminate — no chunk API)
└── workers.py          # All thread worker functions (pure, no UI refs)
```
