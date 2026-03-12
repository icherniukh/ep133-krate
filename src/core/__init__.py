"""Core library for EP-133 KO-II device communication.

Re-exports the main public API for convenience.
"""

from .client import EP133Client, SampleInfo, EP133Error, SlotEmptyError, DeviceNotFoundError, find_device  # noqa: F401
from .models import SAMPLE_RATE, BIT_DEPTH, CHANNELS, MAX_SLOTS  # noqa: F401
