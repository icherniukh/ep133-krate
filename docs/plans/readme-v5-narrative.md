# ep133-krate

You have an EP-133 KO-II. You've filled it with samples. Now you want to reorganize them — maybe move that kick to a different slot, pull a sample back to your computer, or swap out a few things before a set. So you open the official EP Sample Tool app and start clicking.

There's no API. There's no CLI. There's no third-party tool that speaks to this device. If you want to automate anything, you're on your own.

---

That's where this started. The EP-133 connects over USB and speaks MIDI SysEx — a well-understood transport, even if what's riding on top of it isn't. So I pointed a MIDI proxy at the official app, started capturing traffic, and began reading bytes.

What came out the other side: a custom 7-bit binary encoding (Packed7) for fitting binary payloads into MIDI's 7-bit data constraint. Opcodes for every operation — upload (0x6C/0x6D), metadata query (0x75), move/copy, delete. A session state machine where the device stays stuck in download mode after a transfer completes and silently drops the next command unless you reset it first. A native sample rate of exactly 46875 Hz, derived from the 24 MHz system clock divided by 512, matching the Cirrus Logic CS42L52 codec on the board.

Some things are still unknown. Opcode 0x76 appears to be a playback trigger. The TX format, the parameters, the device response — none of it is confirmed yet. Memory stats come back in a known RX payload, but the TX command that prompts them hasn't been identified. This is what reverse engineering looks like when it's honest about its gaps.

`krate` is the tool that came out of that work.

---

## Install

```bash
pip install mido[ports-rtmidi] textual
brew install sox    # macOS
apt install sox     # Linux
```

Connect your EP-133 via USB, then:

```bash
python krate.py tui
```

Or use the CLI directly:

```bash
python krate.py ls
```

---

## Terminal UI

The TUI is the main way to browse and manage your samples interactively:

```bash
krate tui
```

Arrow keys navigate slots. Press `?` for the full keybinding reference.

---

## CLI

All commands accept `--device <name>` to target a specific MIDI port.
Run `krate --help` for the complete list.

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

The EP-133 has 999 slots but finite flash. `optimize` converts a sample to mono and downsamples it to the device's native 46875 Hz. `squash` removes gaps between slots to pack everything into a contiguous range.

```bash
krate optimize 43     # convert slot 43 to mono / native sample rate
krate optimize-all    # optimize all stereo samples
krate squash          # dry run: show how gaps would be filled
krate squash --execute
```

---

## Troubleshooting

If the device isn't detected, list available MIDI ports:

```bash
python -c "import mido; print(mido.get_input_names())"
```

Then pass the port name explicitly:

```bash
krate --device "EP-133" ls
```

If uploaded audio sounds wrong on-device, verify the WAV parameters with `ffprobe`.
The device expects LE s16 PCM at 46875 Hz mono. See [PROTOCOL.md](../../PROTOCOL.md) for exact wire format.

---

## Protocol

The full reverse-engineered specification lives in [PROTOCOL.md](../../PROTOCOL.md) — opcodes, byte layouts, slot encoding, the session state machine, everything that's confirmed and everything that's still speculative. If you want to understand how the device works at the wire level, or contribute captures to fill in the remaining gaps, start there.

Contributions are welcome: device captures, protocol analysis, tests, features.
See [CONTRIBUTING.md](../../CONTRIBUTING.md) for setup and capture workflow.

---

## Requirements

- Python 3.11+
- EP-133 KO-II connected via USB
- [mido](https://mido.readthedocs.io/) — MIDI I/O
- [textual](https://textual.textualize.io/) — terminal UI
- [sox](https://sox.sourceforge.net/) — audio conversion
