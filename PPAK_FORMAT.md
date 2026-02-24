# EP-133 .ppak Project File Format

This document describes the `.ppak` project file format used by the Teenage Engineering EP-133 KO-II.

**Source:** https://github.com/DannyDesert/EP133-skill/blob/main/references/format-details.md

## Overview

A `.ppak` file is a **ZIP archive** with a specific internal structure containing projects, patterns, and samples.

## File Structure

```
project.ppak (ZIP archive)
├── meta.json              # Project metadata
├── projects/
│   ├── P01.tar           # Project 1
│   ├── P02.tar           # Project 2
│   └── ...               # Projects P01-P16
└── sounds/
    ├── 001.wav           # Sample files
    ├── 002.wav
    └── ...
```

**Note:** All paths in the ZIP use **leading slashes** (e.g., `/meta.json`, `/projects/P01.tar`).

## meta.json Format

```json
{
  "info": "teenage engineering - pak file",
  "pak_version": 1,
  "pak_type": "user",
  "pak_release": "1.2.0",
  "device_name": "EP-133",
  "device_sku": "TE032AS001",      // MUST match target device
  "device_version": "2.0.5",
  "generated_at": "2026-01-21T17:00:00.000Z",
  "author": "Your Name",
  "base_sku": "TE032AS001"
}
```

**Critical field:** `device_sku` must be `"TE032AS001"` for the EP-133 KO-II.

## Project TAR Structure

Each `P0X.tar` file contains:

```
P0X.tar
├── pads/
│   ├── a/
│   │   ├── p01           # 27 bytes each
│   │   ├── p02
│   │   └── ...p12
│   ├── b/
│   │   └── p01-p12
│   ├── c/
│   │   └── p01-p12
│   └── d/
│       └── p01-p12
├── patterns/
│   ├── a01               # Binary pattern data
│   ├── b01
│   ├── c01
│   └── d01
└── settings              # Binary settings file
```

## Pad File Format (27 bytes)

Each pad file (`p01`-`p12`) is **27 bytes**:

```
Offset  Size    Type        Description
------  ----    --------   -----------
0       1       uint8       Unknown (preserve from template)
1       2       uint16LE    Sample number (0 = no sample)
3       24      bytes       Pad parameters (preserve from template)
```

### Assigning a Sample to a Pad

```python
import struct

def assign_sample(pad_data: bytes, sample_num: int) -> bytes:
    """Assign a sample number to a pad file."""
    data = bytearray(pad_data)
    data[1:3] = struct.pack('<H', sample_num)  # Little-endian
    return bytes(data)
```

## Pattern File Format (Binary)

### Pattern Header (4 bytes)

```
Byte 0: 0x00 (constant)
Byte 1: 0x01 (constant)
Byte 2: Number of events (uint8, max 255)
Byte 3: 0x00 (constant)
```

### Event Structure (8 bytes per event)

```
Offset  Size    Type        Description
------  ----    --------   -----------
0       2       uint16LE    Time position (0-383 ticks per bar)
2       1       uint8       Row byte (pad identifier)
3       1       uint8       Column byte (0x3c = 60 for normal playback)
4       1       uint8       Velocity (0-127)
5       3       bytes       Flags (typically 0x10 0x00 0x00)
```

### Row Byte to Pad Mapping

The row byte determines which pad triggers:

```
Pad 1  = 0x00 (0)
Pad 2  = 0x08 (8)
Pad 3  = 0x10 (16)
Pad 4  = 0x18 (24)
Pad 5  = 0x20 (32)
Pad 6  = 0x28 (40)
Pad 7  = 0x30 (48)
Pad 8  = 0x38 (56)
Pad 9  = 0x40 (64)
Pad 10 = 0x48 (72)
Pad 11 = 0x50 (80)
Pad 12 = 0x58 (88)
```

**Formula:** `row_byte = (pad_number - 1) * 8`

### Pattern to Group Relationship

**Important:** The pattern **filename** determines which group's samples play, NOT the column byte:
- `patterns/a01` → plays Group A samples (pads/a/p01-p12)
- `patterns/b01` → plays Group B samples (pads/b/p01-p12)
- `patterns/c01` → plays Group C samples (pads/c/p01-p12)
- `patterns/d01` → plays Group D samples (pads/d/p01-p12)

### Creating Pattern Data

```python
import struct

def create_pattern(events: list[tuple[int, int, int]]) -> bytes:
    """
    Create pattern binary data.

    Args:
        events: List of (time_ticks, pad_num, velocity) tuples
               time_ticks: 0-383 (one bar in 4/4 at 96 PPQN)
               pad_num: 1-12
               velocity: 0-127

    Returns:
        Binary pattern data
    """
    if not events:
        return bytes([0x00, 0x01, 0x00, 0x00])

    events = sorted(events, key=lambda x: x[0])
    if len(events) > 255:
        raise ValueError(f"Too many events: {len(events)}. Maximum is 255")

    header = bytes([0x00, 0x01, len(events), 0x00])
    data = bytearray(header)

    for time, pad, velocity in events:
        row = (pad - 1) * 8
        col = 0x3c  # Standard playback
        event = struct.pack('<HB', time, row) + bytes([col, velocity, 0x10, 0x00, 0x00])
        data.extend(event)

    return bytes(data)
```

## Sequencer Timing

The EP-133 uses **96 PPQN** (ticks per quarter note):

| Duration    | Ticks |
|-------------|-------|
| 32nd note   | 12    |
| 16th note   | 24    |
| 8th note    | 48    |
| Quarter note| 96    |
| Half note   | 192   |
| One bar (4/4) | 384 |

### Swing Example

```python
def swing_time(time: int, amount: int = 8) -> int:
    """Apply swing to odd eighth notes."""
    eighth = time // 48
    remainder = time % 48
    if eighth % 2 == 1 and remainder == 0:
        return time + amount
    return time
```

## Sample File Requirements

Samples in the `.ppak` must be:

- **Sample rate:** 46875 Hz (critical!)
- **Bit depth:** 16-bit
- **Channels:** Mono
- **Format:** Little-endian signed 16-bit PCM
- **Extension:** .wav

### Required WAV Metadata

Each `.wav` file must include a `LIST/INFO/TNGE` chunk with JSON metadata:

```json
{
  "sound.playmode":"oneshot",
  "sound.rootnote":60,
  "sound.pitch":0,
  "sound.pan":0,
  "sound.amplitude":100,
  "envelope.attack":0,
  "envelope.release":255,
  "time.mode":"off"
}
```

See `PROTOCOL.md` for complete WAV format details.

## Implementation Ideas

### .ppak Creator Module

```python
import zipfile
import tarfile
import json
from pathlib import Path

class EP133Project:
    """Create .ppak files for EP-133."""

    def __init__(self, device_sku: str = "TE032AS001", project_num: int = 1):
        self.device_sku = device_sku
        self.project_num = project_num
        self.pad_assignments = {
            'a': {i: 0 for i in range(1, 13)},
            'b': {i: 0 for i in range(1, 13)},
            'c': {i: 0 for i in range(1, 13)},
            'd': {i: 0 for i in range(1, 13)}
        }
        self.patterns = {'a': [], 'b': [], 'c': [], 'd': []}
        self.samples = {}  # sample_num -> wav_path

    def assign_sample(self, group: str, pad: int, sample_num: int):
        """Assign a sample to a pad."""
        self.pad_assignments[group][pad] = sample_num

    def add_event(self, group: str, time: int, pad: int, velocity: int = 100):
        """Add an event to a pattern."""
        self.patterns[group].append((time, pad, velocity))

    def save(self, filename: str):
        """Create the .ppak file."""
        with zipfile.ZipFile(filename, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add meta.json with leading slash
            zf.writestr('/meta.json', json.dumps(self._meta(), indent=2))

            # Add project TAR
            tar_data = self._create_project_tar()
            zf.writestr(f'/projects/P{self.project_num:02d}.tar', tar_data)

            # Add samples
            for sample_num, wav_path in self.samples.items():
                zf.writestr(f'/sounds/{sample_num:03d}.wav',
                           Path(wav_path).read_bytes())

    def _meta(self) -> dict:
        from datetime import datetime
        return {
            "info": "teenage engineering - pak file",
            "pak_version": 1,
            "pak_type": "user",
            "pak_release": "1.2.0",
            "device_name": "EP-133",
            "device_sku": self.device_sku,
            "device_version": "2.0.5",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "author": "ko2-tools",
            "base_sku": self.device_sku
        }

    def _create_project_tar(self) -> bytes:
        import io
        tar_buffer = io.BytesIO()

        with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
            # Add pad files
            for group in 'abcd':
                for pad in range(1, 13):
                    pad_data = self._create_pad_file(self.pad_assignments[group][pad])
                    path = f'pads/{group}/p{pad:02d}'
                    tarinfo = tarfile.TarInfo(name=path)
                    tarinfo.size = len(pad_data)
                    tar.addfile(tarinfo, io.BytesIO(pad_data))

            # Add patterns
            for group in 'abcd':
                pattern_data = create_pattern(self.patterns[group])
                path = f'patterns/{group}01'
                tarinfo = tarfile.TarInfo(name=path)
                tarinfo.size = len(pattern_data)
                tar.addfile(tarinfo, io.BytesIO(pattern_data))

        return tar_buffer.getvalue()

    def _create_pad_file(self, sample_num: int) -> bytes:
        # Template: unknown byte + sample num + 24 param bytes
        import struct
        return bytes([0x00]) + struct.pack('<H', sample_num) + bytes(24)
```

## Usage Examples

### Creating a Simple Beat

```python
# Create a project
proj = EP133Project(project_num=1)

# Assign samples (assuming you've uploaded samples 1-4)
proj.assign_sample('a', 1, 1)  # Kick on pad A1
proj.assign_sample('a', 5, 2)  # Snare on pad A5
proj.assign_sample('a', 9, 3)  # Hi-hat on pad A9

# Create a basic beat (time in ticks, 384 = one bar)
proj.add_event('a', 0, 1, 100)    # Beat 1: Kick
proj.add_event('a', 192, 5, 100)  # Beat 3: Snare
proj.add_event('a', 0, 9, 80)     # Offbeat: Hi-hat
proj.add_event('a', 96, 9, 80)
proj.add_event('a', 192, 9, 80)
proj.add_event('a', 288, 9, 80)

# Save to .ppak
proj.save('my_beat.ppak')
```

## CLI Integration Ideas

### ko2 ppak create
```bash
ko2 ppak create --project 1 --output beat.ppak
ko2 ppak create --from-midi midi_file.mid
ko2 ppak create --template "hip-hop"
```

### ko2 ppak extract
```bash
ko2 ppak extract beat.ppak --output ./extracted
ko2 ppak extract beat.ppak --patterns-only
```

### ko2 ppak info
```bash
ko2 ppak info beat.ppak
# Shows: projects, samples used, pattern counts, etc.
```

## Notes

1. **Device SKU mismatch** will cause the EP-133 to reject the .ppak
2. **Max 255 events** per pattern (hardware limitation)
3. **16 projects maximum** per device (P01-P16)
4. **999 sample slots** total (shared across projects)
5. Leading slashes in ZIP paths are required for the device to recognize the archive

## See Also

- `PROTOCOL.md` - MIDI SysEx protocol for device communication
- https://github.com/DannyDesert/EP133-skill - Original source for this format spec
