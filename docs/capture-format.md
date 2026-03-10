# Capture Formats (midi_proxy.py)

This repo uses `midi_proxy.py` to capture MIDI SysEx traffic. Captures can be
written as JSONL/TSV/plain text, or in a raw binary format.

## Tool Choice

Use `midi_proxy.py` for all captures and pretty-printing. The older
`midi_sniffer.py` has been removed.

## Raw Binary Format (`--format raw`)

Each record is:

- 1 byte: direction (`T` for TX, `R` for RX)
- 8 bytes: timestamp (milliseconds since epoch, little-endian uint64)
- 4 bytes: message length in bytes (little-endian uint32)
- N bytes: full SysEx message (`F0 ... F7`)

Records are concatenated back-to-back with no separators.

### Example parse (Python)

```python
def iter_records(fp):
    while True:
        direction = fp.read(1)
        if not direction:
            return
        ts_ms = int.from_bytes(fp.read(8), "little")
        length = int.from_bytes(fp.read(4), "little")
        data = fp.read(length)
        yield direction, ts_ms, data
```

## Capture vs Pretty Print

Capture writes a file:

```bash
python midi_proxy.py --proxy --format raw captures/sniffer-raw.bin
```

Pretty-print reads an existing capture:

```bash
python midi_proxy.py --pretty --format raw captures/sniffer-raw.bin
```

## Pretty Printing Raw Captures

```bash
python midi_proxy.py --pretty --format raw captures/sniffer-raw.bin
```

## MIDI File Format (`--format mid`)

Writes a standard SMF Type 1 `.mid` file so regular MIDI tools can open it.

- Track 0: meta (track name `META`) and a tempo event.
- Track 1: `TX` SysEx events.
- Track 2: `RX` SysEx events.
- PPQN: `1000`, tempo: `1,000,000` us/quarter (1 tick = 1 ms).
- SysEx events use `0xF0` with data that omits the leading `0xF0` byte and
  includes the trailing `0xF7` if present in the captured message.

## About `.syx` Files

`.syx` files are typically just a concatenation of raw SysEx messages
(`F0 ... F7`) with no timestamps or direction. The current raw format preserves
direction + time for protocol analysis. If you want a `.syx` export mode, we
can add a `--format syx` option to emit the bare SysEx stream.
