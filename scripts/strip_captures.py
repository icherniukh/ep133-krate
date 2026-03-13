#!/usr/bin/env python3
"""
Strip bulk audio data from evidence capture files, and extract a targeted
excerpt from the large tui session log.

Always backs up captures/ to captures-backup/ before touching anything.
Safe to run multiple times — won't overwrite an existing backup.

Usage:
    python3 scripts/strip_captures.py
    python3 scripts/strip_captures.py --dry-run
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CAPTURES = REPO_ROOT / "captures"
BACKUP = REPO_ROOT / "captures-backup"

# JSONL files to strip. Consecutive runs of lines with len > threshold are
# collapsed to 3 examples + a _stripped marker. Threshold is in SysEx bytes
# (the `len` field in each record), not line length.
STRIP_TARGETS = [
    "sniffer-padmap-A.jsonl",    # 1.0 MB — pad mapping with inline audio upload
    "sniffer-readmeta.jsonl",    # 516 KB — metadata reads interspersed with download chunks
    "sniffer-padtrim.jsonl",     # 98 KB  — pad trim with upload data
]
LEN_THRESHOLD = 300  # bytes; anything above is a bulk audio data chunk
KEEP_EXAMPLES = 3    # examples to keep per contiguous run

# Tui session excerpt
TUI_SOURCE = CAPTURES / "tui-2026-03-03-042744.jsonl"
TUI_EXTRACT = CAPTURES / "evidence-download-state-bug.jsonl"
TUI_HITS = [302886, 649340]  # line indices of DELETE TX events
TUI_WINDOW = 30              # lines of context on each side


def backup():
    if BACKUP.exists():
        print(f"Backup already exists at {BACKUP} — skipping.")
        return
    print(f"Backing up {CAPTURES} → {BACKUP} ...")
    shutil.copytree(CAPTURES, BACKUP)
    print("Backup done.")


def strip_jsonl(path: Path, dry_run: bool) -> tuple[int, int]:
    """
    Keep all control/metadata lines (len <= threshold).
    For bulk data chunks (len > threshold): keep the first KEEP_EXAMPLES
    globally as format examples, strip the rest and append a single summary
    marker at the end of the file.
    Returns (original_line_count, new_line_count).
    """
    with open(path) as f:
        lines = f.readlines()

    out = []
    examples_kept = 0
    total_stripped = 0

    for line in lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            out.append(line)
            continue

        if obj.get("len", 0) > LEN_THRESHOLD:
            if examples_kept < KEEP_EXAMPLES:
                out.append(line)
                examples_kept += 1
            else:
                total_stripped += 1
        else:
            out.append(line)

    if total_stripped:
        marker = {
            "_stripped": total_stripped,
            "_reason": f"bulk audio data chunks (len>{LEN_THRESHOLD}) — "
                       f"{examples_kept} examples retained above",
        }
        out.append(json.dumps(marker) + "\n")

    if not dry_run:
        with open(path, "w") as f:
            f.writelines(out)

    return len(lines), len(out)


def extract_tui(dry_run: bool):
    """Extract DELETE TX events + context from the large tui session log."""
    if not TUI_SOURCE.exists():
        print(f"  {TUI_SOURCE.name}: not found — skipping extract")
        return

    print(f"Reading {TUI_SOURCE.name} ({TUI_SOURCE.stat().st_size // 1_048_576} MB)...")
    with open(TUI_SOURCE) as f:
        lines = f.readlines()

    included = set()
    for hit in TUI_HITS:
        start = max(0, hit - TUI_WINDOW)
        end = min(len(lines), hit + TUI_WINDOW + 1)
        included.update(range(start, end))

    # If there's a gap between windows, insert a gap marker
    out_lines = []
    prev = None
    for i in sorted(included):
        if prev is not None and i > prev + 1:
            gap = i - prev - 1
            marker = {"_gap": gap, "_note": f"{gap} lines omitted"}
            out_lines.append(json.dumps(marker) + "\n")
        out_lines.append(lines[i])
        prev = i

    header = (
        "// Evidence excerpt from tui-2026-03-03-042744.jsonl (314 MB, not tracked)\n"
        "// Shows device remaining in download mode after GET completes:\n"
        "// DELETE TX at original line 302886 and 649340 are followed by stale GET\n"
        "// responses instead of DELETE ACK, confirming _initialize() is required.\n"
    )

    if not dry_run:
        with open(TUI_EXTRACT, "w") as f:
            f.write(header)
            f.writelines(out_lines)
        print(f"  Wrote {len(out_lines)} lines → {TUI_EXTRACT.name}")
    else:
        print(f"  [dry-run] Would write {len(out_lines)} lines → {TUI_EXTRACT.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Show what would change, don't modify files")
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN — no files will be modified ===\n")

    backup()

    print("\nStripping bulk audio chunks from JSONL evidence files:")
    for name in STRIP_TARGETS:
        path = CAPTURES / name
        if not path.exists():
            print(f"  {name}: not found — skipping")
            continue
        before, after = strip_jsonl(path, args.dry_run)
        saved = before - after
        action = "[dry-run]" if args.dry_run else "done"
        print(f"  {name}: {before} → {after} lines (-{saved}) {action}")

    print("\nExtracting tui session evidence:")
    extract_tui(args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
