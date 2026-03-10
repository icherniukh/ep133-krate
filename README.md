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
python ko2.py tui
```

Use arrow keys to navigate slots. Press `?` for keybindings.

## CLI

All commands accept `--device <name>` to target a specific MIDI port.
Run `python ko2.py --help` for the full list.

### Listing and inspecting

```bash
python ko2.py ls              # list first 99 slots
python ko2.py ls --page 2     # slots 100–199
python ko2.py ls --all        # all 999 slots
python ko2.py info 43         # name, size, duration for slot 43
python ko2.py info 1-50       # info for a range
```

### Transferring samples

```bash
python ko2.py get 43 ./kick.wav          # download slot 43
python ko2.py put ./kick.wav 43          # upload to slot 43
python ko2.py put ./kick.wav 43 --name "afterparty kick"
```

### Managing slots

```bash
python ko2.py mv 43 50        # move slot 43 to 50
python ko2.py cp 43 50        # copy slot 43 to 50
python ko2.py rm 43           # delete slot 43
python ko2.py rename 43 "new name"
```

### Optimizing memory

```bash
python ko2.py optimize 43     # convert slot 43 to mono / native sample rate
python ko2.py optimize-all    # optimize all stereo samples
python ko2.py squash          # dry run: show how gaps would be filled
python ko2.py squash --execute
```

## Troubleshooting

If the device is not detected, list available MIDI ports:

```bash
python -c "import mido; print(mido.get_input_names())"
```

Then pass the port name explicitly:

```bash
python ko2.py --device "EP-133" ls
```

If uploaded audio sounds wrong on-device, verify the WAV parameters with `ffprobe`.
See [PROTOCOL.md](PROTOCOL.md) for the required audio format.

## Documentation

- [Protocol Specification](PROTOCOL.md)
- [Contributing](CONTRIBUTING.md)
