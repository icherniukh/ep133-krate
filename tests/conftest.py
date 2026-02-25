import sys
from pathlib import Path

import pytest


# Ensure repo root is importable from any test subdir.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def pytest_addoption(parser):
    parser.addoption("--device", default=None, help="MIDI device name (defaults to auto-detect)")


@pytest.fixture(scope="session")
def device_name(pytestconfig):
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
