"""Core library for EP-133 KO-II device communication.

Re-exports the main public API for convenience.
"""

from .models import Sample, SampleInfo, MAX_SAMPLE_RATE, SAMPLE_RATE, BIT_DEPTH, CHANNELS, MAX_SLOTS  # noqa: F401
from .client import EP133Client, EP133Error, SlotEmptyError, DeviceNotFoundError, find_device  # noqa: F401
