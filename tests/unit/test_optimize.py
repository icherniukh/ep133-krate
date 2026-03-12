import array
import shutil
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

import cli.cmd_transfer
import cli.cmd_slots
import cli.cmd_audio
import cli.cmd_system
import core.ops
import cli.helpers
from ko2_client import EP133Client, SlotEmptyError
from core.ops import backup_copy, optimize_sample
from ko2_display import SilentView
from ko2_models import SAMPLE_RATE
from tests.helpers import create_test_wav


def _sox_available():
    return shutil.which("sox") is not None


def create_stereo_wav(path: Path, framerate: int = 44100, duration_sec: float = 0.5):
    """Create a stereo WAV at a non-EP-133 sample rate."""
    channels = 2
    sampwidth = 2  # 16-bit
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(framerate)
        frames = int(framerate * duration_sec)
        data = array.array("h")
        for i in range(frames):
            val = int(16000 * (i / frames))
            data.append(val)   # L channel
            data.append(-val)  # R channel
        w.writeframes(data.tobytes())


# --- optimize_sample: real WAV transformation ---

@pytest.mark.skipif(not _sox_available(), reason="sox not installed")
def test_optimize_sample_downmixes_stereo_preserves_rate(tmp_path):
    """
    A stereo 44100 Hz WAV must come out mono at the same 44100 Hz.
    The device stores sub-46875 Hz samples at their original rate (OS 2.0+),
    so there is no reason to upsample.
    """
    input_wav = tmp_path / "stereo44k.wav"
    create_stereo_wav(input_wav, framerate=44100)

    output_wav = tmp_path / "out.wav"
    success, msg, orig_size, opt_size = optimize_sample(input_wav, output_path=output_wav)

    assert success, f"optimize_sample failed: {msg}"
    assert output_wav.exists()

    with wave.open(str(output_wav)) as w:
        assert w.getnchannels() == 1, "output must be mono"
        assert w.getframerate() == 44100, "rate must be preserved, not forced to 46875"
        assert w.getsampwidth() == 2, "output must be 16-bit"


@pytest.mark.skipif(not _sox_available(), reason="sox not installed")
def test_optimize_sample_downsamples_above_native_rate(tmp_path):
    """
    A 96000 Hz file must be downsampled to 46875 Hz — device cannot store above that.
    """
    input_wav = tmp_path / "hi96k.wav"
    create_stereo_wav(input_wav, framerate=96000)

    output_wav = tmp_path / "out.wav"
    success, _, _, _ = optimize_sample(input_wav, output_path=output_wav)

    assert success
    with wave.open(str(output_wav)) as w:
        assert w.getframerate() == SAMPLE_RATE, "must downsample to 46875 Hz"


@pytest.mark.skipif(not _sox_available(), reason="sox not installed")
def test_optimize_sample_stereo_produces_smaller_file(tmp_path):
    """Downmixing stereo to mono halves the sample data."""
    input_wav = tmp_path / "stereo.wav"
    create_stereo_wav(input_wav, framerate=44100, duration_sec=1.0)

    output_wav = tmp_path / "out.wav"
    success, _, orig_size, opt_size = optimize_sample(input_wav, output_path=output_wav)

    assert success
    assert opt_size < orig_size


@pytest.mark.skipif(not _sox_available(), reason="sox not installed")
def test_optimize_sample_already_optimal_returns_early(tmp_path):
    """A mono 44100 Hz 16-bit WAV needs no conversion — returns 'already optimal'."""
    input_wav = tmp_path / "mono44k.wav"
    create_test_wav(input_wav)  # creates mono, 46875 Hz, 16-bit — already optimal

    success, msg, orig_size, opt_size = optimize_sample(input_wav)

    assert success
    assert msg == "already optimal"
    assert opt_size == orig_size


@pytest.mark.skipif(not _sox_available(), reason="sox not installed")
def test_optimize_sample_reports_correct_sizes(tmp_path):
    """Returned orig_size and opt_size must match the actual files on disk."""
    input_wav = tmp_path / "in.wav"
    create_stereo_wav(input_wav)

    output_wav = tmp_path / "out.wav"
    success, _, orig_size, opt_size = optimize_sample(input_wav, output_path=output_wav)

    assert success
    assert orig_size == input_wav.stat().st_size
    assert opt_size == output_wav.stat().st_size


# --- cmd_optimize: integration via mocked client ---

def _fake_client_class(log, name="drums.pcm"):
    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def info(self, slot, include_size=False):
            return SimpleNamespace(name=name, channels=2, samplerate=44100, size_bytes=0)

        def get(self, slot, path: Path):
            create_test_wav(path)
            log.append(("get", slot))

        def put(self, path: Path, slot: int, name=None, progress=False, pitch=0.0):
            log.append(("put", slot, name))

    return FakeClient


def _args(slot, **kwargs):
    return SimpleNamespace(device=None, slot=slot, yes=True, **kwargs)


def test_cmd_optimize_downloads_then_uploads_when_savings_large(monkeypatch):
    """
    When optimize_sample reports savings above the 5 KB threshold,
    cmd_optimize must get the sample, then put the optimized version back.
    """
    log = []

    monkeypatch.setattr(cli.cmd_audio, "EP133Client", lambda *_a, **_kw: _fake_client_class(log)())
    monkeypatch.setattr("core.ops.backup_copy", lambda *a, **k: None)
    monkeypatch.setattr(
        cli.cmd_audio, "optimize_sample",
        # Return sizes based on the actual downloaded file so savings are consistent.
        lambda p, **kw: (True, "optimized with sox", p.stat().st_size, p.stat().st_size - 20 * 1024),
    )

    rc = cli.cmd_audio.cmd_optimize(_args(slot=7), SilentView())

    assert rc == 0
    assert ("get", 7) in log
    assert ("put", 7, "drums.pcm") in log


def test_cmd_optimize_skips_upload_when_savings_below_threshold(monkeypatch):
    """
    Savings < 5 KB: download happens (to check), but upload is skipped.
    """
    log = []

    monkeypatch.setattr(cli.cmd_audio, "EP133Client", lambda *_a, **_kw: _fake_client_class(log)())
    monkeypatch.setattr("core.ops.backup_copy", lambda *a, **k: None)
    monkeypatch.setattr(
        cli.cmd_audio, "optimize_sample",
        lambda p, **kw: (True, "optimized with sox", p.stat().st_size, p.stat().st_size - 1024),  # 1 KB
    )

    rc = cli.cmd_audio.cmd_optimize(_args(slot=7), SilentView())

    assert rc == 0
    assert ("get", 7) in log
    assert ("put", 7, "drums.pcm") not in log


def test_cmd_optimize_skips_entirely_when_already_optimal(monkeypatch):
    """
    Samples already optimal: download happens (WAV header is authoritative for
    channels/rate — metadata may be absent for samples not uploaded by this tool),
    optimize_sample returns 'already optimal', no upload occurs.
    """
    log = []

    class OptimalFakeClient:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def info(self, slot, include_size=False):
            return SimpleNamespace(name="tiny.pcm", channels=1, samplerate=SAMPLE_RATE, size_bytes=0)
        def get(self, slot, path):
            log.append(("get", slot))
            create_test_wav(path)  # must be a valid WAV — cmd_optimize calls wave.open after get
        def put(self, path, slot, name=None, progress=False, pitch=0.0): log.append(("put", slot, name))

    monkeypatch.setattr(cli.cmd_audio, "EP133Client", lambda *_a, **_kw: OptimalFakeClient())
    monkeypatch.setattr(cli.cmd_audio, "optimize_sample", lambda p, **kw: (True, "already optimal", p.stat().st_size, p.stat().st_size))
    monkeypatch.setattr("core.ops.backup_copy", lambda *a, **k: None)

    rc = cli.cmd_audio.cmd_optimize(_args(slot=3), SilentView())

    assert rc == 0
    assert ("get", 3) in log                      # download happens
    assert ("put", 3, "tiny.pcm") not in log      # no upload
