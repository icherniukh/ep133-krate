# EP-133 KO-II Tools - Agent Guide

## Project Overview

Python toolkit for managing Teenage Engineering EP-133 KO-II samples via MIDI SysEx.

**Key Files:**
- `ko2.py` - Main CLI tool
- `ko2_client.py` - MIDI client implementation
- `ko2_protocol.py` - Protocol constants and utilities
- `PROTOCOL.md` - Complete protocol documentation

## Commands

```bash
# Device detection (requires EP-133 connected via USB)
python ko2.py ls [--page N]           # List samples by page
python ko2.py info <slot>             # Get sample metadata
python ko2.py get <slot> [file]       # Download sample
python ko2.py put <file> <slot>       # Upload sample
python ko2.py rm <slot>               # Delete sample
python ko2.py optimize <slot>         # Optimize single sample
python ko2.py optimize-all            # Batch optimize
```

## Development

```bash
# Run tests
python -m pytest tests/

# Check device connection
python -c "import mido; print([p for p in mido.get_output_names() if 'EP-133' in p])"
```

## Known Issues

### Upload Not Persisting (CRITICAL)

**Status:** Under investigation - reference sysex files also don't work!

**Key findings:**
- Download, delete, and metadata queries work correctly
- **Reference sysex files from external repos also fail to persist**
- This suggests a firmware change or undiscovered device state requirement
- Device firmware may have changed protocol since reference files were created

**Investigation files:**
- `UPLOAD_INVESTIGATION.md` - Key findings and hypotheses
- `PROTOCOL.md` - Protocol documentation
- Reference sysex files: `/tmp/ep_133_sysex_thingy/` (no longer work!)

## Protocol Notes

- All messages use Teenage Engineering manufacturer ID: `00 20 76`
- Device family: `33 40`
- 7-bit encoding required for variable-length data
- Sample rate: 46875 Hz (not 44.1 or 48!)
- Bit depth: 16-bit mono

## Dependencies

```bash
pip install mido
```
