# EP-133 KO-II Tools

A sample manager and memory optimizer for the Teenage Engineering EP-133 KO-II.
Communicates with the device directly over MIDI SysEx — no official app required.

## What It Does

- List, upload, download, rename, delete, move, and copy samples
- Optimize samples in place (stereo → mono, downsample to native rate)
- Squash slot gaps to pack samples into a contiguous range
- Browse and manage everything via a terminal UI

The device protocol is reverse-engineered. See [PROTOCOL.md](PROTOCOL.md) for the full specification.

## Prerequisites

- Python 3.11+
- [mido](https://mido.readthedocs.io/) — MIDI I/O (`pip install mido[ports-rtmidi]`)
- [textual](https://textual.textualize.io/) — TUI (`pip install textual`)
- [sox](https://sox.sourceforge.net/) — audio conversion:
  - macOS: `brew install sox`
  - Linux: `apt install sox`
- EP-133 KO-II connected via USB

## TUI

The TUI is the main interface for browsing and managing samples:

```bash
krate tui
```

Use arrow keys to navigate slots. Press `?` for keybindings.

## CLI

All commands accept `--device <name>` to target a specific MIDI port.
Run `krate --help` for the full list.

### Listing and inspecting

```bash
krate ls              # list first 99 slots
krate ls --page 2     # slots 100–199
krate ls --all        # all 999 slots
krate info 43         # name, size, duration for slot 43
krate info 1-50       # info for a range
```

### Transferring samples

```bash
krate get 43 ./kick.wav          # download slot 43
krate put ./kick.wav 43          # upload to slot 43
krate put ./kick.wav 43 --name "afterparty kick"
```

### Managing slots

```bash
krate mv 43 50        # move slot 43 to 50
krate cp 43 50        # copy slot 43 to 50
krate rm 43           # delete slot 43
krate rename 43 "new name"
```

### Optimizing memory

```bash
krate optimize 43     # convert slot 43 to mono / native sample rate
krate optimize-all    # optimize all stereo samples
krate squash          # dry run: show how gaps would be filled
krate squash --execute
```

## Troubleshooting

If the device is not detected, list available MIDI ports:

```bash
python -c "import mido; print(mido.get_input_names())"
```

Then pass the port name explicitly:

```bash
krate --device "EP-133" ls
```

If uploaded audio sounds wrong on-device, verify the WAV parameters with `ffprobe`.
See [PROTOCOL.md](PROTOCOL.md) for the required audio format.

## Documentation

- [Protocol Specification](PROTOCOL.md)
- [Contributing](CONTRIBUTING.md)
