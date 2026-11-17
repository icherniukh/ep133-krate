# EP-133 emulator

The emulator exercises Krate's sample I/O against an in-memory sample library.
It models client expectations and uses synthetic data. Use the
[firmware evidence matrix](protocol-evidence.md#operation-coverage) for claims
about physical devices.

## Run it

```bash
# In-memory MIDI backend, no hardware required
pytest -m e2e --emulator

# Standalone virtual port, with a backend that supports virtual MIDI
python tests/emulator.py --port "EP-133 Emulator"
```

For direct tests, instantiate `EP133Emulator` and call `handle_sysex(raw)`.
The method returns `(response_bytes, delay_seconds)` pairs.
[Implementation](../tests/emulator.py), [Direct tests](../tests/unit/test_emulator.py), [Pytest backend](../tests/conftest.py)

## Coverage

There are **three state-backed FILE routes**. The byte values below are
Krate's high request-ID bytes.

| Route | Emulated behavior |
|---|---|
| `0x6A` | LIST on node `1000` only, 24 entries per page. METADATA GET splits JSON into 320-byte pages and emits placeholder metadata for missing slots. SET updates existing samples. |
| `0x7D` | GET selects one download slot and returns synthetic open fields. Data uses 433-byte chunks and Krate's U14LE page encoding. If there is no selected sample, the data handler can fall back to the first occupied slot. |
| `0x7E` | PUT stages one active stream and marks EOF on an empty page. The emulator commits on `0x0B` and returns an empty success body. On the device `0x0B` reads a STAT record. This route also handles DELETE. |

Byte `0x61` is ignored. A non-FILE request with byte `0x77` can return a
synthetic info string. Its `2.0.5` label is test data. The emulator has no
models for project TARs, pad assignment, audition, live storage statistics,
unsolicited events, or FILE session recovery.

Keep emulator tests focused on client behavior. For a wire change, compare
the request and reply against a capture using the
[decoded layouts](../PROTOCOL.md#file-operations).
