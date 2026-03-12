import array
import wave
from pathlib import Path

from core.models import SAMPLE_RATE, BIT_DEPTH, CHANNELS


def create_test_wav(path: Path, duration_sec: float = 0.1) -> None:
    """Create a valid EP-133 format WAV file for testing."""
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(BIT_DEPTH // 8)
        wav.setframerate(SAMPLE_RATE)

        frames = int(SAMPLE_RATE * duration_sec)
        data = array.array("h")
        for i in range(frames):
            value = int(16000 * (i / frames) * (1 if (i // 1000) % 2 == 0 else -1))
            data.append(value)

        wav.writeframes(data.tobytes())

