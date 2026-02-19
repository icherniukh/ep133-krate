# EP-133 Project Operations

This document describes project-related operations on the EP-133 KO-II.

## Device Projects

- **Total projects:** 16 (numbered 1-16, labeled P01-P16)
- **Project switching:** Via MIDI SysEx (Device ID 0x7C)
- **Project storage:** Each project has independent sample assignments and patterns
- **Sample slots:** 999 slots shared across all projects

## Project Switching via MIDI

### Protocol

```
F0 00 20 76 33 40 7C [seq] 05 08 07 01 07 50 [json_data] 00 F7
```

| Field | Value | Description |
|-------|-------|-------------|
| Device ID | 0x7C | PROJECT |
| Cmd group | 05 | CMD_FILE |
| Flags | 08 | Project mode |
| Op | 07 | Project operation |
| Sub-op | 01 | Switch project |
| Data | JSON | `{"active":8000}` for project 8 |

### Project Encoding

The JSON payload uses a **value = project_num × 1000** encoding:

| Project | JSON Payload |
|---------|--------------|
| 1 | `{"active":1000}` |
| 2 | `{"active":2000}` |
| 3 | `{"active":3000}` |
| ... | ... |
| 8 | `{"active":8000}` |
| ... | ... |
| 16 | `{"active":16000}` |

### Python Implementation

```python
def switch_project(project_num: int) -> bytes:
    """
    Generate SysEx message to switch to a project.

    Args:
        project_num: Project number (1-16)

    Returns:
        SysEx message bytes
    """
    if not 1 <= project_num <= 16:
        raise ValueError("Project number must be 1-16")

    json_data = f'{{"active":{project_num * 1000}}}'
    return build_sysex(
        device_id=0x7C,  # PROJECT
        flags=0x08,
        op=0x07,
        subop=0x01,
        data=json_data.encode() + b'\x00'
    )
```

### Usage Example

```python
# Switch to project 8
msg = switch_project(8)
mido.Message('sysex', data=msg)
output.send(msg)
```

## Project vs Sample Relationship

### Sample Slots
- **999 total slots** (numbered 001-999)
- Slots are **shared** across all 16 projects
- Uploading to slot 100 in Project 1 also affects Project 2

### Pad Assignments
- Each project has **independent pad assignments** (pads A-D, 1-12)
- Project 1 might have sample 100 on pad A1
- Project 2 might have sample 200 on pad A1
- These assignments are stored per-project

### Patterns
- Each project has **4 patterns** (one per group: A, B, C, D)
- Patterns reference pads, not sample numbers directly
- The pattern filename determines which group plays:
  - `patterns/a01` → plays Group A pads

## Project Files (.ppak)

The `.ppak` format is a ZIP archive containing:
- `meta.json` - Project metadata
- `projects/P0X.tar` - Project data (pad assignments, patterns)
- `sounds/*.wav` - Sample files

**Note:** Device projects (1-16) are separate from .ppak files. A .ppak is an archive that can be loaded onto the device, not the internal project storage format.

See `PPAK_FORMAT.md` for complete .ppak specification.

## Current Implementation Status

| Operation | Status | Notes |
|-----------|--------|-------|
| Switch Project | ✅ Protocol known | Device ID 0x7C documented |
| List Projects | ❓ Unknown | May exist, needs investigation |
| Backup Project | ❓ Unknown | Likely requires .ppak creation |
| Restore Project | ❓ Unknown | Likely requires .ppak loading |
| Export to .ppak | 🔧 Format known | See PPAK_FORMAT.md |
| Import from .ppak | 🔧 Format known | See PPAK_FORMAT.md |

## Known Operations

### Device IDs Related to Projects

| ID | Name | Usage |
|----|------|-------|
| 0x7C | PROJECT | Switch active project |

### Operations (Op field)

| Op | Name | Usage |
|----|------|-------|
| 0x07 | PROJECT | Project operations |

### Sub-operations

| Sub-op | Name | Usage |
|--------|------|-------|
| 0x01 | SWITCH | Switch active project |

## Investigation Needed

1. **List Projects** - Is there a command to query current project or list all?
2. **Project Metadata** - Can we query project name/properties?
3. **Project Backup** - Can we download project data (pad assignments, patterns)?
4. **Project Restore** - Can we upload project data to device?

## References

- `PROTOCOL.md` - Complete MIDI SysEx protocol
- `PPAK_FORMAT.md` - .ppak file format specification
- https://github.com/DannyDesert/EP133-skill - .ppak creation reference
