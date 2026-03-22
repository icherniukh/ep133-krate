"""Core library for EP-133 KO-II device communication.

Re-exports the main public API for convenience.
"""

from .models import (  # noqa: F401
    Sample, SampleInfo, MAX_SAMPLE_RATE, SAMPLE_RATE, BIT_DEPTH, CHANNELS, MAX_SLOTS,
    EP133Error, DeviceNotFoundError, SlotEmptyError, DownloadCancelledError,
)
from .client import EP133Client, find_device  # noqa: F401
