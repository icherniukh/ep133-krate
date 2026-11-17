# MIDI capture and file formats

Install the desktop dependencies from [the development setup](../CONTRIBUTING.md#development-setup).
From the repository root, proxy both directions and connect the Sample Tool
to the virtual port. Give each run a fresh filename since capture appends to
an existing JSONL or raw file.

```bash
python scripts/midi_proxy.py --proxy --spoof captures/sniffer-example.jsonl
python scripts/midi_proxy.py --pretty --limit 50 captures/sniffer-example.jsonl
```

Preserve the startup exchange. Record the model, hardware variant, firmware
from GREET, client, and action for each capture. Keep the full TX/RX frames.
Current proxy labels and `--hunt` matching are helpful for finding requests.
For replies and events, verify the raw bytes against the
[frame layout](../PROTOCOL.md#message-structure). The preview decoder can
interpret the status byte as Packed7 and give a misleading operation label.

## JSON Lines (default)

Each line records `ts` (local clock time), `dir` (`TX` or `RX`), `len`
(full frame length in bytes), and `hex` (complete SysEx including `F0` and
`F7`). Known Teenage Engineering headers can also include `mfg`, `family`,
and `cmd`. The `cmd` field is the high part of the request ID in this tool.
TSV and plain-text export are also available.

## Raw binary

Each record consists of these fields in order, with no separator.

| Length | Field |
|---:|---|
| 1 byte | Direction, ASCII `T` or `R` |
| 8 bytes | Unix timestamp in milliseconds, unsigned little-endian |
| 4 bytes | SysEx frame length, unsigned little-endian |
| Variable | Complete SysEx frame, including `F0` and `F7` |

```bash
python scripts/midi_proxy.py --proxy --spoof --format raw captures/sniffer-example.bin
python scripts/midi_proxy.py --pretty --format raw captures/sniffer-example.bin
```

Some old `.bin` files contain concatenated SysEx frames with no record
headers. Inspect their framing before treating them as the proxy's raw format.

## Standard MIDI file

`--format mid` writes SMF Type 1 with three tracks (`META`, `TX`, `RX`).
Timing is 1,000 ticks per quarter note at 1,000,000 µs per quarter, or 1 ms
per tick. SysEx events store the bytes following `F0`, with the final
`F7` included. Open the file in a MIDI tool for inspection.
