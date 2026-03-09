# EP-133 KO-II Tools - Project Status

## 📊 Progress Overview (as of 2026-03-07)

**Current Milestone:** Phase 2 (TUI) MVP foundation implemented.

**Protocol Understanding:** `[########--] 80%`
- Confirmed: LIST/GET/PUT/DELETE, METADATA SET, VERIFY, upload metadata fields, pad mapping A + partial B/C/D.
- Partial: Project ops, memory reporting, node hierarchy semantics.
- Unknown: PLAYBACK/AUDITION wire protocol.

**Project Phases:**
- Phase 1 (CLI): `[##########] 100% Done`
- Phase 2 (TUI): `[#####-----] ~50% (MVP running)`
- Phase 3 (Desktop/Web/Mobile): `[----------] 0%`

---

## 🏛 Architectural Decisions

### 2026-03-02: View-oriented CLI output architecture
**Context**:
`ko2.py` had ~80 bare `print()+Colors.*` calls inline in command functions, making them untestable and coupling business logic to terminal formatting. The `RendererProtocol` name was also misleading ("renderer" implies transform-and-return, not fire-and-forget I/O).

**Decision**:
Introduced `View` protocol in `ko2_display.py` with 10 domain-semantic methods (`section`, `step`, `success`, `error`, `warn`, `info`, `kv`, `progress`, `render_samples`, `sample_detail`). Three implementations:
- **`TerminalView`**: colored ANSI output (default)
- **`SilentView`**: all no-ops — `--quiet` backend and test double
- **`JsonView`**: structured JSON output — `--json` backend

All 16 `cmd_*` functions receive `view: View` as an injected parameter. `main()` constructs the view from `--json`/`--quiet` flags. Layout helpers (`_row`, `_table_header`, etc.) are private to `TerminalView`.

**Consequences**:
- Every `cmd_*` function is unit-testable via `Mock(spec=View)` — no stdout patching needed.
- `--json` and `--quiet` output modes added at zero cost to command logic.
- `Colors.*` fully removed from `ko2.py`; `ko2_utils.py` deleted (utilities consolidated into `ko2_display.SampleFormat`).

---

### 2026-02-24: "Golden Standard" Descriptor DSL Architecture
**Context**: 
The procedural approach (manually shifting bits) was replaced by a `dataclass`-based layer. However, that layer still suffered from asymmetry (manual unpacking on receive) and anti-patterns (overriding pack methods for variable-length strings).

**Decision**:
We implemented a true **Descriptor-based Domain Specific Language (DSL)** natively in Python (similar to SQLAlchemy/Django ORM) for the entire protocol.
- **`ko2_types.py`**: Minimal, primitive types (`U7`, `BE16`, `Packed7`).
- **`ko2_models.py`**: The Domain Layer. Contains all Opcodes, Message structures, and Logical Parsers. Messages are defined using declarative fields (`U7Field`, `BE16Field`, `JsonField`).
- **`ko2_operations.py`**: Stateful, multi-step operations (e.g., `UploadTransaction`).
- **`ko2_client.py`**: Thin transport interface speaking the `Message` domain.

**Consequences**:
- 100% symmetry for serialization/deserialization.
- Zero transport leakage (`ko2_client` knows nothing about `Packed7` or JSON byte-packing).
- Synchronous and thread-safe design, paving the way for async TUI worker threads (Textual framework).

---

## 🛠 Currently Working Operations (CLI)

| Operation | Command | Notes |
|-----------|---------|-------|
| **List Samples** | `ko2 ls [--page N] [--all]` | Scan by pages (100 slots), show size/duration |
| **Query Metadata** | `ko2 info <slot\|range>` | Get name, size, duration. |
| **Download Sample** | `ko2 get <slot> [file]` | Downloads to WAV (46875Hz). 7-bit page encoding fixed. |
| **Upload Sample** | `ko2 put <file> <slot>` | Audio + metadata set. Safe 44.1kHz support. |
| **Delete Sample** | `ko2 rm <slot>` | Big-endian slot formatting verified. |
| **Optimize Sample** | `ko2 optimize <slot>` | Backup + optimize + replace |
| **Optimize All** | `ko2 optimize-all [--min KB]`| Batch optimize stereo samples (downmix to mono) |
| **Squash Slots** | `ko2 squash` | Fill gaps sequentially (dry-run default) |

---

## 🔍 Technical Gaps & Investigation Priorities

These are the remaining mysteries in the EP-133 protocol that require further reverse-engineering.
See **`docs/CAPTURE_WISHLIST.md`** for a scenario-by-scenario list of what to sniff and the
exact `midi_proxy.py` command for each.

1. **Playback/Audition (0x76)** 
   - Protocol unknown. We need to capture the official app triggering an audition to unblock Phase 3.
2. **Project Query & Switching (0x7C)** 
   - Switching is documented, but listing projects is not yet captured or implemented. Required for backup/restore features.
3. **Memory Statistics** 
   - No known command to query free memory. 64 MB assumed as a fallback, but newer hardware ships with 128 MB.
4. **Pad Mapping & Hierarchy Semantics** 
   - Group A mapping is fully captured (`9201-9212`). Groups B/C/D are only partially captured.
   - `META_SET` operations show `active` toggles on nodes `2000/5100/5300/5400/9100/9300/9500`, but UI semantics are still unclear.
5. **GET_META (0x75) Reliability & Corruption** 
   - `GET_META` is known to be unreliable because it can return stale data for deleted slots. The official app relies entirely on `/sounds` (FILE LIST) and Node `METADATA GET` instead. Our runtime paths now do the same; `GET_META` is retained only for explicit audit/debug comparisons.
6. **Project file format (.ppak)**
   - Documented in `PPAK_FORMAT.md`, but no SysEx path for extracting it has been found. It might rely on USB Mass Storage or undocumented bulk transfers.

---

→ See BACKLOG.md for all open items

---

## Config Changes Log (2026-03-06)

Changes made from insights report recommendations. Revert instructions included.

### 1. `.claude/CLAUDE.md` (CREATED)
- **What:** New project-level CLAUDE.md with protocol rules, source-of-truth hierarchy, fabrication policy, architecture map, test command.
- **Revert:** `rm /Users/ivan/proj/ko2-tools/.claude/CLAUDE.md`

### 2. `~/.claude/commands/onboard.md` (MODIFIED)
- **What:** Added Step 2b to read PROTOCOL.md / PROTOCOL_EVIDENCE.md / STATUS.md during onboarding.
- **Revert:** Remove the "Step 2b: Protocol Docs" block from `~/.claude/commands/onboard.md`

### 3. `.claude/skills/review/SKILL.md` (CREATED)
- **What:** Evidence-based review skill requiring doc-reading, test run, and source citations.
- **Revert:** `rm -r /Users/ivan/proj/ko2-tools/.claude/skills/review/`

### 4. `.git/hooks/pre-commit` (CREATED)
- **What:** Runs `python3 -m pytest tests/unit/ -x -q --tb=short` before every commit.
- **Revert:** `rm /Users/ivan/proj/ko2-tools/.git/hooks/pre-commit`

### 5. `.claude/settings.local.json` (MODIFIED)
- **What:** Removed 9 cruft entries (comment-as-commands, loop fragments, dotfiles diffs, one-off curl calls).
- **Revert:** Re-add the removed entries (see original content in git: `git show HEAD:.claude/settings.local.json` — note: this file is gitignored, so backup manually before execution)

### 6. `.claude/settings.json` (MODIFIED)
- **What:** Added PostToolUse hook for Python syntax checking after edits.
- **Revert:** Remove the `"hooks"` key from `.claude/settings.json`
