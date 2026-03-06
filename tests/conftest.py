import sys
import time
from pathlib import Path
from collections import deque
from threading import Lock

import pytest


# Ensure repo root is importable from any test subdir.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def pytest_addoption(parser):
    parser.addoption("--device", default=None, help="MIDI device name (defaults to auto-detect)")
    parser.addoption(
        "--emulator",
        action="store_true",
        help="Run E2E tests against the local EP-133 MIDI emulator",
    )


class _InMemoryQueue:
    def __init__(self):
        self._items = deque()
        self._lock = Lock()

    def push(self, item):
        with self._lock:
            self._items.append(item)

    def drain(self):
        out = []
        with self._lock:
            while self._items:
                out.append(self._items.popleft())
        return out


class _InMemoryBus:
    """Directional queues for one virtual MIDI endpoint name.

    - to_virtual_input: client output -> emulator input
    - to_virtual_output: emulator output -> client input
    """

    def __init__(self):
        self.to_virtual_input = _InMemoryQueue()
        self.to_virtual_output = _InMemoryQueue()


class _InMemoryPort:
    def __init__(self, name, rx: _InMemoryQueue | None, tx: _InMemoryQueue | None):
        self.name = name
        self._rx = rx
        self._tx = tx
        self._closed = False

    def send(self, msg):
        if self._closed:
            return
        if self._tx is not None:
            self._tx.push(msg.copy())

    def iter_pending(self):
        if self._closed or self._rx is None:
            return []
        return self._rx.drain()

    def close(self):
        self._closed = True


class _InMemoryMidiBackend:
    def __init__(self):
        self._buses: dict[str, _InMemoryBus] = {}
        self._lock = Lock()

    def _bus(self, name: str) -> _InMemoryBus:
        with self._lock:
            bus = self._buses.get(name)
            if bus is None:
                bus = _InMemoryBus()
                self._buses[name] = bus
            return bus

    def open_input(self, name, virtual=False):
        bus = self._bus(name)
        if virtual:
            return _InMemoryPort(name, rx=bus.to_virtual_input, tx=None)
        return _InMemoryPort(name, rx=bus.to_virtual_output, tx=None)

    def open_output(self, name, virtual=False):
        bus = self._bus(name)
        if virtual:
            return _InMemoryPort(name, rx=None, tx=bus.to_virtual_output)
        return _InMemoryPort(name, rx=None, tx=bus.to_virtual_input)

    def open_ioport(self, name, virtual=False):
        bus = self._bus(name)
        if virtual:
            return _InMemoryPort(name, rx=bus.to_virtual_input, tx=bus.to_virtual_output)
        return _InMemoryPort(name, rx=bus.to_virtual_output, tx=bus.to_virtual_input)

    def get_output_names(self):
        with self._lock:
            return list(self._buses.keys())

    def get_input_names(self):
        with self._lock:
            return list(self._buses.keys())


@pytest.fixture(scope="session")
def emulator_device(pytestconfig):
    if not pytestconfig.getoption("--emulator"):
        yield None
        return
    import mido
    backend = _InMemoryMidiBackend()
    orig_open_input = mido.open_input
    orig_open_output = mido.open_output
    orig_open_ioport = getattr(mido, "open_ioport", None)
    orig_get_output_names = mido.get_output_names
    orig_get_input_names = mido.get_input_names
    mido.open_input = backend.open_input
    mido.open_output = backend.open_output
    mido.open_ioport = backend.open_ioport
    mido.get_output_names = backend.get_output_names
    mido.get_input_names = backend.get_input_names
    from ko2_emulator import EP133Emulator

    emu = EP133Emulator(port_name="EP-133 Emulator")
    emu.start()
    time.sleep(0.01)
    try:
        yield emu
    finally:
        emu.stop()
        mido.open_input = orig_open_input
        mido.open_output = orig_open_output
        if orig_open_ioport is not None:
            mido.open_ioport = orig_open_ioport
        mido.get_output_names = orig_get_output_names
        mido.get_input_names = orig_get_input_names


@pytest.fixture(scope="session")
def device_name(pytestconfig, emulator_device):
    if emulator_device is not None:
        return emulator_device.port_name
    # Avoid auto-detect here: on some systems CoreMIDI/RtMidi can abort the
    # interpreter if permissions aren't granted. E2E tests should pass --device
    # explicitly.
    return pytestconfig.getoption("--device")


@pytest.fixture(scope="session")
def ep133_client(device_name):
    from ko2_client import EP133Client, DeviceNotFoundError

    try:
        with EP133Client(device_name) as c:  # device_name=None triggers auto-detect
            yield c
    except DeviceNotFoundError as e:
        pytest.skip(str(e))
