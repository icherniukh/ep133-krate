# Metadata Corruption Risk Review

This document summarizes where sample metadata can diverge or be corrupted,
how to detect it, and the mitigations implemented in the codebase.

## Metadata sources on the device

There are multiple sources of truth:

1. Filesystem entry name from `/sounds` (FILE LIST)
2. Filesystem node metadata (FileOp.METADATA GET on a node_id)
3. Slot metadata (GET_META)

These sources can diverge and are not always updated together.

## Known corruption / divergence risks

1. **GET_META offset bug for slots >127**
   - GET_META returns the wrong name (observed +128 shift).
   - Any logic that trusts GET_META for names beyond 127 will mislabel samples.

2. **Stale slot metadata after delete**
   - Device can return metadata for empty slots.
   - Inventory operations that trust GET_META can show ghost names.

3. **Move/Copy resets sound parameters**
   - Move/copy is implemented as download + delete + upload.
   - Upload only carries name + channels + samplerate; any additional
     sound parameters (start/end/loop/pitch/etc.) are lost.

4. **Conflicting metadata fields**
   - Filesystem node metadata and GET_META can disagree (name, sym, etc.).
   - There is no guaranteed direction of truth between them.

5. **Encoding / response attribution errors**
   - Slot encoding errors (7-bit vs 14-bit) shift identifiers.
   - Async responses can be misattributed if not filtered properly.

## Detection (implemented)

`ko2 audit` compares these sources across a slot range:
- Filesystem filename
- Node metadata name
- GET_META name

It flags mismatches and stale meta (GET_META present but no `/sounds` entry).

### Audit JSONL schema

When `--dump-json` is used, each line is a single JSON object:

```json
{
  "slot": 128,
  "fs": { "node_id": 128, "name": "128.pcm", "size": 12345, "flags": 29, "is_dir": false },
  "node": { "name": "kick 02", "sym": "kick 02", "channels": 1, "samplerate": 46875, "format": "s16" },
  "meta": { "name": "kick 02", "sym": "kick 02", "channels": 1, "samplerate": 46875, "format": "s16" },
  "flags": ["name:diff"]
}
```

**Field meanings:**
- `slot`: 1–999 sample slot number.
- `fs`: Filesystem entry from `/sounds` list (may be `null`).
  - `node_id`: Filesystem node ID.
  - `name`: Filesystem filename.
  - `size`: Bytes.
  - `flags`: Raw filesystem flags.
  - `is_dir`: Boolean.
- `node`: Filesystem node metadata JSON (may be `null`).
- `meta`: GET_META response JSON (may be `null`).
- `flags`: Issues detected by audit (see below).

**Flag values:**
- `stale`: GET_META returned a name but no `/sounds` entry exists.
- `node-meta-miss`: `/sounds` entry exists but node metadata could not be fetched.
- `node-name-empty`: node metadata exists but `name`/`sym` is empty.
- `<field>:diff`: Node metadata and GET_META differ for a compared field.

## Mitigations (implemented)

1. **`info()` prefers node metadata for names**
   - GET_META is not trusted for names on slots >127.
   - GET_META is only used when explicitly requested (`--use-meta`) or as a last-resort scan fallback.

2. **Inventory uses filesystem listing**
   - Listing relies on `/sounds` entries; empty slots are real empties.

## Remaining risks / next steps

1. Add a "preserve meta" path for move/copy once a reliable SET protocol for
   sound parameters is discovered.
2. Add an audit option to dump raw GET_META bytes for forensic debugging.
3. Consider a "strict" mode that refuses to show names if sources disagree.
