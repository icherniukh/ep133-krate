# ep133-krate

Sample manager for the Teenage Engineering EP-133 KO-II.
Communicates over MIDI SysEx. No official API — protocol is reverse-engineered.

## Prerequisites

- Python 3.11+
- sox: `brew install sox` (macOS) or `apt install sox` (Linux)
- EP-133 connected via USB

## Install

```bash
git clone https://github.com/your-username/ep133-krate
cd ep133-krate
pip install -r requirements.txt
```

## Usage

```bash
krate tui                        # terminal UI (recommended starting point)
```

Press `?` in the TUI for keybindings.

### CLI

```bash
krate ls                         # list slots 1–99
krate ls --all                   # all 999 slots
krate get 43 ./kick.wav          # download slot 43
krate put ./kick.wav 43          # upload to slot 43
krate mv 43 50                   # move slot
krate cp 43 50                   # copy slot
krate rm 43                      # delete slot
krate rename 43 "afterparty kick"
krate optimize 43                # convert to mono / native sample rate
krate optimize-all               # optimize all stereo samples
krate squash --execute           # close gaps between slots
```

All commands accept `--device <name>` to target a specific MIDI port.
Run `krate --help` for the full command list.

## Troubleshooting

List available MIDI ports:

```bash
python -c "import mido; print(mido.get_input_names())"
```

Pass the port name explicitly if auto-detection fails:

```bash
krate --device "EP-133" ls
```

## Development

```bash
pytest                           # 379 unit tests, no device required
pytest -m e2e --device "EP-133"  # end-to-end tests (device required)
```

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for architecture notes, protocol gaps, and how to capture traffic.

## Protocol

The full SysEx protocol specification is in [PROTOCOL.md](../../PROTOCOL.md).
