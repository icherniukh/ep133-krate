# Capture Wishlist

Scenarios where we need sniffed MIDI traffic from the official TE Sample Tool
to fill protocol gaps. For each scenario: what to do in the app, why it matters,
and the capture command to run first.

Capture tool: `python midi_proxy.py --proxy --spoof captures/<name>.jsonl`
The `--proxy` + `--spoof` flags intercept both directions between the official app
and the device, making the virtual port look like the real device to the app.

---

## 1. Device info query (opcode 0x78)

**Why:** `device_info()` in `ko2_client.py` always returns `None` because it sends
opcode `0x77` (INFO), but from `sniffer-slot22.jsonl` event 61 we can see the
device returns the full info string (`product:EP-133;os_version:2.0.5;serial:...`)
in response to opcode `0x78`. We have the RX side but not the TX — we don't know
the exact request format. Fixing this unblocks KO2-010 (`device_info()` stub).

**Steps:**
1. Start capture
2. Plug in EP-133 (or relaunch official app with device already connected)
3. Wait for the app to display device info (model, firmware version, serial number)
4. Stop capture

**Command:**
```bash
python midi_proxy.py --proxy --spoof --hunt cmd=0x78 --hunt any \
  captures/sniffer-device-info.jsonl
```

---

## 2. Sample playback / audition (opcode 0x76)

**Why:** `PLAYBACK (0x76)` is completely unknown — TX format, parameters, and device
response are all undocumented. Blocking KO2-007 (TUI audition via Tab key) and
Phase 3. Response code `0x36` appears in `sniffer-slot22.jsonl` but those events
turned out to be metadata responses, not playback.

**Steps:**
1. Start capture
2. In the official app, click a sample slot to audition/preview it
3. Audition a few different slots (vary size, mono vs stereo)
4. Stop capture

**Command:**
```bash
python midi_proxy.py --proxy --spoof --hunt cmd=0x76 \
  captures/sniffer-playback.jsonl
```

---

## 3. Official app download (if it exists)

**Why:** We have no captures of the official app performing a sample download from
the device. We cannot verify whether the official app sends any post-download reset
signal (equivalent to our `_initialize()` after `get()`). Our fix is confirmed
correct from TUI captures, but seeing the official app's download sequence would
close the loop — specifically whether opcode `0x78` doubles as the reset/close
signal after a completed download.

**Steps:**
1. Start capture
2. If the official app has an export/download button, select a slot and trigger it
3. Complete the transfer
4. Stop capture — note the TX messages sent after the last RX data chunk

**Command:**
```bash
python midi_proxy.py --proxy --spoof --hunt cmd=0x7D --hunt any \
  captures/sniffer-download.jsonl
```

Note: If the official app has no download feature this scenario is N/A.
The `--hunt cmd=0x7D` filter highlights any `DOWNLOAD` opcode traffic.

---

## 4. Project listing and switching (opcode 0x7C)

**Why:** Project switching is partially documented but listing available projects is
not captured. Required for backup/restore features and multi-project support.

**Steps:**
1. Start capture
2. Open the project switcher in the official app
3. Browse the project list (scroll through it)
4. Switch to a different project
5. Switch back to the original project
6. Stop capture

**Command:**
```bash
python midi_proxy.py --proxy --spoof --hunt cmd=0x7C \
  captures/sniffer-project-ops.jsonl
```

---

## 5. Memory / storage statistics query

**Why:** `sniffer-slot22.jsonl` event 59 shows the device returning
`"free_space_in_bytes":29257802,"max_capacity":62853120` in a RX payload — but we
don't know which TX command triggered it. This is the only known source for actual
free/used memory figures. Right now `cmd_status` falls back to an assumed 64 MB
because `device_info()` returns `None` (see KO2-010).

**Steps:**
1. Start capture
2. Launch the official app or navigate to any screen that shows storage/free space
3. Stop capture

Then inspect the capture for short TX messages immediately before any RX response
containing `free_space_in_bytes`.

**Command:**
```bash
python midi_proxy.py --proxy --spoof --hunt any \
  captures/sniffer-storage-stats.jsonl
```

---

## 6. Pad mapping — Groups B, C, D

**Why:** Group A pad mapping (nodes `9201-9212`) is fully captured in
`sniffer-padmap-A.jsonl`. Groups B, C, D have only partial coverage. Full mapping
is needed to support pad assignment operations in the TUI/CLI.

**Steps:**
1. Start capture
2. In the official app, assign a sample to a pad in Group B
3. Assign a sample to a pad in Group C
4. Assign a sample to a pad in Group D
5. Clear/re-assign one pad in each group
6. Stop capture

**Command:**
```bash
python midi_proxy.py --proxy --spoof --hunt meta_set --hunt meta_get \
  captures/sniffer-padmap-BCD.jsonl
```

---

## 7. Full session startup / INIT handshake

**Why:** Our `_initialize()` sends opcode `0x61` (TE-specific INIT). The official
app appears to send `0x78` as part of its startup handshake (seen as the device
response in `sniffer-slot22.jsonl` event 61). We don't know if `0x78` is a
"device info query", a "session open" signal, or both. Our `0x61` works for
resetting device state after download/upload, but capturing the full official
startup sequence would reveal whether there are steps we're skipping.

**Steps:**
1. Start capture
2. Quit the official app completely if already running
3. Relaunch the official app from scratch with device connected
4. Wait until the app has fully initialized (inventory loaded, device name shown)
5. Stop capture — focus on the first 20-30 TX/RX pairs

**Command:**
```bash
python midi_proxy.py --proxy --spoof --hunt any \
  captures/sniffer-startup.jsonl
```

---

## 8. Sample trim and loop point editing

**Why:** `sniffer-padtrim.jsonl` exists but the `META_SET` operations there toggle
`active` on nodes `2000/5100/5300/5400/9100/9300/9500` and the UI semantics of
those toggles are unclear. Need a capture that pairs a specific UI action (set loop
start, set loop end, enable/disable loop) with the resulting SysEx so we can map
each parameter to its node/field.

**Steps:**
1. Start capture
2. Open a sample in the official app and set a loop start point
3. Set a loop end point
4. Toggle looping on, then off
5. Adjust trim start and trim end
6. Stop capture

**Command:**
```bash
python midi_proxy.py --proxy --spoof --hunt meta_set \
  captures/sniffer-trim-loop.jsonl
```

---

## Reviewing a capture

```bash
# Pretty-print with decoded fields
python midi_proxy.py --pretty captures/sniffer-<name>.jsonl

# Filter to a specific opcode while reviewing
python midi_proxy.py --pretty --hunt cmd=0x76 captures/sniffer-<name>.jsonl

# First N messages only
python midi_proxy.py --pretty --limit 50 captures/sniffer-<name>.jsonl
```
