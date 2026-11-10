"""Navigation previews yield to commands without losing their idle retry."""

import io
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
import wave

import pytest

from core.client import DownloadCancelledError, EP133Client
from tui import actions
from tui.app import TUIApp
from tui.worker import DeviceWorker, WorkerEvent


def _wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(46875)
        wav.writeframes(b"\x00\x00\x10\x00" * 100)
    return buffer.getvalue()


class PreviewClient:
    def __init__(self):
        self.calls = []

    def connect(self):
        pass

    def close(self):
        self.calls.append(("close",))

    def get(self, slot, output_path, **_kwargs):
        self.calls.append(("get", slot))
        Path(output_path).write_bytes(_wav_bytes())

    def audition(self, slot):
        self.calls.append(("audition", slot))


def _worker(monkeypatch, client):
    monkeypatch.setenv("KO2_TUI_WAVEFORM_PRECALC_MODE", "single")
    worker = DeviceWorker("EP-133", Queue(), Queue(), client_factory=lambda *_args, **_kwargs: client)
    monkeypatch.setattr(worker, "_load_ratio", lambda: 0.0)
    return worker


def test_queued_previews_yield_to_audition_and_retry_latest_when_idle(monkeypatch):
    client = PreviewClient()
    worker = _worker(monkeypatch, client)
    for slot in [1, 2, 3]:
        worker.submit(actions.waveform(slot))
    worker.submit(actions.audition(3))

    while not worker._request_queue.empty():
        worker._process_request(worker._request_queue.get_nowait())

    assert client.calls == [("audition", 3)]
    assert worker._waveform_precalc_slots == [3, 2, 1]
    cancelled = [event.payload["slot"] for event in worker._event_queue.queue if event.kind == "waveform_cancelled"]
    assert cancelled == [1, 2, 3]

    worker._maybe_run_waveform_precalc_step()
    assert client.calls == [("audition", 3), ("get", 3)]
    assert any(event.kind == "waveform" and event.payload["slot"] == 3 for event in worker._event_queue.queue)


def test_last_queued_preview_runs_and_deferred_slots_are_deduplicated(monkeypatch):
    client = PreviewClient()
    worker = _worker(monkeypatch, client)
    for slot in [1, 2, 1, 3]:
        worker.submit(actions.waveform(slot))
    while not worker._request_queue.empty():
        worker._process_request(worker._request_queue.get_nowait())
    assert client.calls == [("get", 3)]
    assert worker._waveform_precalc_slots == [1, 2]


def test_deferred_preview_is_not_retried_after_slot_deletion(monkeypatch):
    client = PreviewClient()
    client.delete = lambda slot: client.calls.append(("delete", slot))
    worker = _worker(monkeypatch, client)
    worker.submit(actions.waveform(1))
    worker.submit(actions.delete(1))
    while not worker._request_queue.empty():
        worker._process_request(worker._request_queue.get_nowait())
    worker._maybe_run_waveform_precalc_step()
    assert client.calls == [("delete", 1)]
    assert worker._waveform_precalc_slots == []


@pytest.mark.parametrize("incoming", [actions.audition(1), actions.waveform(2)])
def test_inflight_preview_cancels_without_closing_session_and_retries(monkeypatch, incoming):
    class InterruptedClient(PreviewClient):
        interrupted = False

        def get(self, slot, output_path, **kwargs):
            if not self.interrupted:
                self.interrupted = True
                self.calls.append(("cancelled_get", slot))
                cancel_check = kwargs["cancel_check"]
                assert not cancel_check()
                worker.submit(incoming)
                assert cancel_check()
                raise DownloadCancelledError("new user request")
            super().get(slot, output_path, **kwargs)

    client = InterruptedClient()
    worker = _worker(monkeypatch, client)
    worker._process_request(actions.waveform(1))
    assert worker._waveform_precalc_slots == [1]
    assert ("close",) not in client.calls
    assert not any(event.kind == "error" for event in worker._event_queue.queue)
    assert any(event.kind == "waveform_cancelled" for event in worker._event_queue.queue)

    worker._process_request(worker._request_queue.get_nowait())
    if incoming.op == "audition":
        assert client.calls[-1] == ("audition", 1)
        worker._maybe_run_waveform_precalc_step()
        assert client.calls[-1] == ("get", 1)
    else:
        assert client.calls[-1] == ("get", 2)


def test_waveform_cancelled_clears_ui_pending_without_marking_device_online(monkeypatch):
    app = TUIApp(device_name="EP-133", debug=False)
    app.state.selected_slot = 1
    app._device_online = False
    app._waveform_pending.add(1)
    refreshed = []
    monkeypatch.setattr(app, "_update_waveform", refreshed.append)

    app._handle_event(WorkerEvent("waveform_cancelled", {"slot": 1}))
    assert 1 not in app._waveform_pending
    assert refreshed == [1]
    assert not app._device_online


def test_cancelled_core_download_resets_session_before_next_command(monkeypatch, tmp_path):
    client = EP133Client.__new__(EP133Client)
    calls = []
    monkeypatch.setattr(client, "info", lambda _slot: SimpleNamespace(is_empty=False, size_bytes=100))
    monkeypatch.setattr(client, "_initialize", lambda: calls.append("reset"))

    def cancelled(_slot, cancel_check):
        assert cancel_check()
        raise DownloadCancelledError("cancelled preview")

    monkeypatch.setattr(client, "_download_data", cancelled)
    with pytest.raises(DownloadCancelledError):
        client.get(1, tmp_path / "preview.wav", cancel_check=lambda: True)
    assert calls == ["reset"]
