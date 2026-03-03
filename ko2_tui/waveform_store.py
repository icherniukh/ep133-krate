from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


class WaveformStore:
    """Single-file key/value storage for slot waveform previews."""

    def __init__(self, path: str | Path | None = None, capture_dir: str | Path = "captures"):
        if path is None:
            root = Path(capture_dir)
            root.mkdir(parents=True, exist_ok=True)
            self.path = root / "waveform-kv.json"
        else:
            self.path = Path(path)
            self.path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._loaded = False
        self._data: dict[str, Any] = {"version": 3, "slots": {}, "fingerprints": {}}

    def get_for_slot(self, slot: int, signature: dict[str, Any]) -> dict[str, Any] | None:
        self._ensure_loaded()
        with self._lock:
            entry = self._slot_entry_locked(int(slot), signature)
            if not isinstance(entry, dict):
                return None
            bins = self._bins_for_slot_entry_locked(entry)
            if isinstance(bins, dict):
                return bins
            return None

    def get_entry_for_slot(self, slot: int, signature: dict[str, Any] | None = None) -> dict[str, Any] | None:
        self._ensure_loaded()
        with self._lock:
            entry = self._slot_entry_locked(int(slot), signature)
            if isinstance(entry, dict):
                out = dict(entry)
                fp = self._fingerprint_for_slot_entry_locked(entry)
                bins = self._bins_for_slot_entry_locked(entry)
                if isinstance(fp, dict):
                    out["fp"] = dict(fp)
                if isinstance(bins, dict):
                    out["bins"] = bins
                return out
            return None

    def set_for_slot(
        self,
        slot: int,
        signature: dict[str, Any],
        bins: dict[str, Any],
        fingerprint: dict[str, Any] | None = None,
    ) -> None:
        self._ensure_loaded()
        with self._lock:
            slots = self._slots()
            fps = self._fingerprints()
            slot_key = str(int(slot))

            fp = dict(fingerprint) if isinstance(fingerprint, dict) else {}
            hash_hex = str(fp.get("sha256") or "").strip().lower()
            if hash_hex:
                fp_row = fps.get(hash_hex)
                if not isinstance(fp_row, dict):
                    fp_row = {}
                merged = dict(fp_row)
                merged.update(fp)
                merged["sha256"] = hash_hex
                if isinstance(bins, dict):
                    merged["bins"] = bins
                fps[hash_hex] = merged
                slots[slot_key] = {"sig": dict(signature), "hash": hash_hex}
            else:
                entry = {"sig": dict(signature), "bins": bins}
                if fp:
                    entry["fp"] = fp
                slots[slot_key] = entry
            self._save_locked()

    def get_fingerprint(self, hash_hex: str) -> dict[str, Any] | None:
        self._ensure_loaded()
        key = str(hash_hex or "").strip().lower()
        if not key:
            return None
        with self._lock:
            fp = self._fingerprints().get(key)
            if isinstance(fp, dict):
                return dict(fp)
            return None

    def set_fingerprint(self, hash_hex: str, data: dict[str, Any]) -> None:
        self._ensure_loaded()
        key = str(hash_hex or "").strip().lower()
        if not key:
            return
        with self._lock:
            current = self._fingerprints().get(key)
            row = dict(current) if isinstance(current, dict) else {}
            row.update(dict(data))
            row["sha256"] = key
            self._fingerprints()[key] = row
            self._save_locked()

    def _slots(self) -> dict[str, Any]:
        slots = self._data.get("slots")
        if isinstance(slots, dict):
            return slots
        self._data["slots"] = {}
        return self._data["slots"]

    def _fingerprints(self) -> dict[str, Any]:
        fps = self._data.get("fingerprints")
        if isinstance(fps, dict):
            return fps
        self._data["fingerprints"] = {}
        return self._data["fingerprints"]

    def _slot_entry_locked(self, slot: int, signature: dict[str, Any] | None = None) -> dict[str, Any] | None:
        entry = self._slots().get(str(int(slot)))
        if not isinstance(entry, dict):
            return None
        if signature is not None and entry.get("sig") != signature:
            return None
        return entry

    def _fingerprint_for_slot_entry_locked(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        fp = entry.get("fp")
        if isinstance(fp, dict):
            return fp
        hash_hex = str(entry.get("hash") or "").strip().lower()
        if not hash_hex:
            return None
        row = self._fingerprints().get(hash_hex)
        if isinstance(row, dict):
            return row
        return None

    def _bins_for_slot_entry_locked(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        bins = entry.get("bins")
        if isinstance(bins, dict):
            return bins
        fp = self._fingerprint_for_slot_entry_locked(entry)
        if isinstance(fp, dict):
            b = fp.get("bins")
            if isinstance(b, dict):
                return b
        return None

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if self.path.exists():
                try:
                    loaded = json.loads(self.path.read_text(encoding="utf-8"))
                except Exception:
                    loaded = None
                if isinstance(loaded, dict):
                    self._data = loaded
            self._data.setdefault("version", 3)
            self._data.setdefault("slots", {})
            self._data.setdefault("fingerprints", {})
            self._normalize_locked()
            self._loaded = True

    def _save_locked(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self._data, separators=(",", ":"), ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def _normalize_locked(self) -> None:
        """Migrate legacy mixed slot records into hash-first normalized layout."""
        fps = self._fingerprints()
        slots = self._slots()
        for slot_key, raw in list(slots.items()):
            if not isinstance(raw, dict):
                continue
            entry = dict(raw)
            fp = entry.get("fp") if isinstance(entry.get("fp"), dict) else None
            bins = entry.get("bins") if isinstance(entry.get("bins"), dict) else None
            hash_hex = str(entry.get("hash") or "").strip().lower()

            if not hash_hex and fp and isinstance(fp.get("sha256"), str):
                hash_hex = str(fp.get("sha256") or "").strip().lower()
            if not hash_hex and isinstance(entry.get("sha256"), str):
                hash_hex = str(entry.get("sha256") or "").strip().lower()

            if hash_hex:
                row = fps.get(hash_hex)
                merged = dict(row) if isinstance(row, dict) else {}
                if fp:
                    merged.update(fp)
                if bins:
                    merged["bins"] = bins
                merged["sha256"] = hash_hex
                fps[hash_hex] = merged
                slots[str(slot_key)] = {
                    "sig": dict(entry.get("sig") or {}),
                    "hash": hash_hex,
                }
            else:
                # Keep legacy slot-only entry when hash isn't available.
                slots[str(slot_key)] = entry

        self._data["version"] = 3
