#!/usr/bin/env python3
"""EP-133 KO-II MIDI emulator for E2E tests.

This emulator exposes virtual MIDI ports and responds to a subset of the KO-II
SysEx protocol used by this repository's client/tests.
"""

from __future__ import annotations

import json
import math
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import mido

from ko2_models import (
    CMD_FILE,
    DEVICE_FAMILY,
    FileOp,
    MetaType,
    SAMPLE_RATE,
    SYSEX_END,
    SYSEX_START,
    SysExCmd,
    TE_MFG_ID,
)
from ko2_types import Packed7, U14LE


DOWNLOAD_CHUNK_SIZE = 433


@dataclass
class SampleSlot:
    slot: int
    name: str
    data: bytes
    metadata: dict
    flags: int = 0x1D

    @property
    def filename(self) -> str:
        return f"{self.slot:03d}.pcm"

    @property
    def size(self) -> int:
        return len(self.data)


@dataclass
class PendingUpload:
    slot: int
    expected_size: int
    name: str
    metadata: dict
    buffer: bytearray = field(default_factory=bytearray)
    ended: bool = False


class EP133Emulator:
    def __init__(
        self,
        port_name: str = "EP-133 Emulator",
        response_delay_ms: int = 15,
        page_delay_ms: int = 6,
    ):
        self.port_name = port_name
        self.response_delay_ms = response_delay_ms
        self.page_delay_ms = page_delay_ms

        self._inport = None
        self._outport = None
        self._ioport = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

        self._samples: dict[int, SampleSlot] = {}
        self._pending: dict[int, PendingUpload] = {}
        self._download_slot: int | None = None
        self._populate_default_samples()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop.clear()
        # Prefer a single virtual IO port: opening separate virtual input/output
        # ports with the same name can abort some CoreMIDI/rtmidi builds.
        self._ioport = None
        self._inport = None
        self._outport = None
        try:
            self._ioport = mido.open_ioport(self.port_name, virtual=True)
        except Exception:
            # Fallback for backends that don't expose virtual ioports.
            # Open output first, then input, to minimize CoreMIDI instability.
            self._outport = mido.open_output(self.port_name, virtual=True)
            self._inport = mido.open_input(self.port_name, virtual=True)
        self._thread = threading.Thread(target=self._run, name="ep133-emulator", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._ioport:
            self._ioport.close()
            self._ioport = None
        if self._inport:
            self._inport.close()
            self._inport = None
        if self._outport:
            self._outport.close()
            self._outport = None

    def __enter__(self) -> "EP133Emulator":
        self.start()
        return self

    def __exit__(self, *_args) -> None:
        self.stop()

    def _run(self) -> None:
        in_port = self._ioport or self._inport
        out_port = self._ioport or self._outport
        if in_port is None or out_port is None:
            return
        while not self._stop.is_set():
            for msg in in_port.iter_pending():
                if msg.type != "sysex":
                    continue
                raw = bytes([SYSEX_START]) + bytes(msg.data) + bytes([SYSEX_END])
                responses = self.handle_sysex(raw)
                for resp, delay in responses:
                    time.sleep(delay)
                    out_port.send(mido.Message("sysex", data=resp[1:-1]))
            time.sleep(0.001)

    def handle_sysex(self, raw: bytes) -> list[tuple[bytes, float]]:
        """Handle one incoming SysEx message and return responses.

        Return value: list of (response_bytes, delay_seconds).
        """
        if len(raw) < 9 or raw[0] != SYSEX_START or raw[-1] != SYSEX_END:
            return []
        if raw[1:4] != TE_MFG_ID or raw[4:6] != DEVICE_FAMILY:
            return []

        cmd = raw[6]
        seq = raw[7] & 0x7F

        # Device init packets; no response required for this client.
        if cmd == SysExCmd.INIT:
            return []

        if len(raw) < 10 or raw[8] != CMD_FILE:
            # Optional lightweight INFO response.
            if cmd == SysExCmd.INFO:
                resp = self._build_sysex_response(
                    cmd=0x21,
                    seq=seq,
                    payload=b"\x01\x00\x00emulator:ep133;fw:2.0.5",
                    file_group=False,
                )
                return [(resp, self.response_delay_ms / 1000.0)]
            return []

        try:
            payload = Packed7.unpack(raw[9:-1])
        except Exception:
            return [
                (
                    self._build_file_response(cmd=max(0x20, cmd - 0x40), seq=seq, status=1, payload=b""),
                    self.response_delay_ms / 1000.0,
                )
            ]

        if cmd == SysExCmd.LIST_FILES:
            return self._handle_list_files(seq, payload)
        if cmd == SysExCmd.DOWNLOAD:
            return self._handle_download(seq, payload)
        if cmd == SysExCmd.UPLOAD_DATA:
            return self._handle_upload_data(seq, payload)
        if cmd == SysExCmd.UPLOAD:
            return self._handle_upload(seq, payload)

        return []

    def _handle_list_files(self, seq: int, payload: bytes) -> list[tuple[bytes, float]]:
        if len(payload) < 1:
            return [(self._build_file_response(0x2A, seq, 1, b""), self._delay())]

        op = payload[0]
        if op == FileOp.LIST:
            if len(payload) < 5:
                return [(self._build_file_response(0x2A, seq, 1, b""), self._delay())]
            page = int.from_bytes(payload[1:3], "big")
            node_id = int.from_bytes(payload[3:5], "big")
            entries = self._encode_directory_entries(node_id=node_id, page=page)
            out = page.to_bytes(2, "big") + entries
            return [(self._build_file_response(0x2A, seq, 0, out), self._page_delay())]

        if op == FileOp.METADATA:
            if len(payload) < 4:
                return [(self._build_file_response(0x2A, seq, 1, b""), self._delay())]
            sub = payload[1]
            node_id = int.from_bytes(payload[2:4], "big")

            if sub == MetaType.GET:
                page = int.from_bytes(payload[4:6], "big") if len(payload) >= 6 else 0
                meta = self._metadata_for_node(node_id)
                blob = json.dumps(meta, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                start = page * 320
                chunk = blob[start : start + 320]
                out = page.to_bytes(2, "big") + chunk
                return [(self._build_file_response(0x2A, seq, 0, out), self._page_delay())]

            if sub == MetaType.SET:
                text = payload[4:].rstrip(b"\x00").decode("utf-8", errors="replace")
                try:
                    patch = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    patch = {}
                self._apply_metadata_set(node_id, patch)
                return [(self._build_file_response(0x2A, seq, 0, b""), self._delay())]

        return [(self._build_file_response(0x2A, seq, 1, b""), self._delay())]

    def _handle_download(self, seq: int, payload: bytes) -> list[tuple[bytes, float]]:
        if len(payload) < 2:
            return [(self._build_file_response(0x3D, seq, 1, b""), self._delay())]

        if payload[0] != FileOp.GET:
            return [(self._build_file_response(0x3D, seq, 1, b""), self._delay())]

        subtype = payload[1]
        if subtype == 0x00:
            slot = int.from_bytes(payload[2:4], "big") if len(payload) >= 4 else 0
            sample = self._samples.get(slot)
            if not sample:
                return [(self._build_file_response(0x3D, seq, 2, b""), self._delay())]
            self._download_slot = slot
            out = (
                bytes([FileOp.GET, 0x00, 0x05])
                + sample.size.to_bytes(4, "big")
                + b"\x00"
                + sample.filename.encode("utf-8")
                + b"\x00"
            )
            return [(self._build_file_response(0x3D, seq, 0, out), self._delay())]

        if subtype == 0x01 and len(payload) >= 4:
            page, _ = U14LE.decode(payload[2:4])
            page_index = int(page.to_python())
            sample = self._current_download_sample()
            if sample is None:
                return [(self._build_file_response(0x3D, seq, 2, b""), self._delay())]
            start = page_index * DOWNLOAD_CHUNK_SIZE
            chunk = sample.data[start : start + DOWNLOAD_CHUNK_SIZE]
            out = U14LE(page_index).encode() + chunk
            return [(self._build_file_response(0x3D, seq, 0, out), self._page_delay())]

        return [(self._build_file_response(0x3D, seq, 1, b""), self._delay())]

    def _handle_upload_data(self, seq: int, payload: bytes) -> list[tuple[bytes, float]]:
        if len(payload) < 2:
            return [(self._build_file_response(0x2C, seq, 1, b""), self._delay())]

        op = payload[0]
        sub = payload[1]

        if op == FileOp.PUT and sub == 0x00:
            if len(payload) < 11:
                return [(self._build_file_response(0x2C, seq, 1, b""), self._delay())]
            slot = int.from_bytes(payload[3:5], "big")
            size = int.from_bytes(payload[7:11], "big")
            tail = payload[11:]
            name_bytes, _, meta_bytes = tail.partition(b"\x00")
            name = name_bytes.decode("utf-8", errors="replace") or f"slot-{slot:03d}"
            meta_text = meta_bytes.decode("utf-8", errors="replace").rstrip("\x00")
            try:
                metadata = json.loads(meta_text) if meta_text else {}
            except json.JSONDecodeError:
                metadata = {}
            self._pending[slot] = PendingUpload(
                slot=slot,
                expected_size=size,
                name=name,
                metadata=metadata,
            )
            return [(self._build_file_response(0x2C, seq, 0, b""), self._delay())]

        if op == FileOp.PUT and sub == 0x01:
            if len(payload) < 4:
                return [(self._build_file_response(0x2C, seq, 1, b""), self._delay())]
            chunk = payload[4:]
            # Single active upload is sufficient for current tests/client usage.
            pending = self._latest_pending_upload()
            if pending is not None:
                if chunk:
                    pending.buffer.extend(chunk)
                else:
                    pending.ended = True
            return [(self._build_file_response(0x2C, seq, 0, b""), self._page_delay())]

        if op == FileOp.VERIFY:
            slot = int.from_bytes(payload[2:4], "big") if len(payload) >= 4 else 0
            pending = self._pending.get(slot)
            if pending is not None:
                self._commit_upload(pending)
                self._pending.pop(slot, None)
            return [(self._build_file_response(0x2C, seq, 0, b""), self._delay())]

        return [(self._build_file_response(0x2C, seq, 1, b""), self._delay())]

    def _handle_upload(self, seq: int, payload: bytes) -> list[tuple[bytes, float]]:
        if len(payload) >= 3 and payload[0] == FileOp.DELETE:
            slot = int.from_bytes(payload[1:3], "big")
            with self._lock:
                self._samples.pop(slot, None)
            return [(self._build_file_response(0x3E, seq, 0, b""), self._delay())]
        return [(self._build_file_response(0x3E, seq, 1, b""), self._delay())]

    def _encode_directory_entries(self, node_id: int, page: int, page_size: int = 24) -> bytes:
        if node_id != 1000:
            return b""

        with self._lock:
            slots = sorted(self._samples)
            chunk = slots[page * page_size : (page + 1) * page_size]
            parts = []
            for slot in chunk:
                sample = self._samples[slot]
                node = int(slot)
                hi = (node >> 8) & 0xFF
                lo = node & 0xFF
                parts.append(
                    bytes([hi, lo, sample.flags])
                    + sample.size.to_bytes(4, "big")
                    + sample.filename.encode("utf-8")
                    + b"\x00"
                )
            return b"".join(parts)

    def _metadata_for_node(self, node_id: int) -> dict:
        with self._lock:
            sample = self._samples.get(node_id)
            if sample:
                return dict(sample.metadata)
            return {
                "name": f"slot {node_id:03d}",
                "channels": 1,
                "samplerate": SAMPLE_RATE,
                "format": "s16",
            }

    def _apply_metadata_set(self, node_id: int, patch: dict) -> None:
        if not isinstance(patch, dict):
            return
        with self._lock:
            sample = self._samples.get(node_id)
            if not sample:
                return
            sample.metadata.update(patch)
            if patch.get("name"):
                sample.name = str(patch.get("name"))

    def _latest_pending_upload(self) -> Optional[PendingUpload]:
        if not self._pending:
            return None
        # dict preserves insertion order in modern Python
        return next(reversed(self._pending.values()))

    def _commit_upload(self, pending: PendingUpload) -> None:
        data = bytes(pending.buffer)
        if pending.expected_size > 0:
            data = data[: pending.expected_size]

        meta = self._default_metadata(slot=pending.slot, name=pending.name)
        if isinstance(pending.metadata, dict):
            meta.update(pending.metadata)
        if "name" not in meta or not meta["name"]:
            meta["name"] = pending.name
        name = str(meta.get("name") or pending.name)

        with self._lock:
            self._samples[pending.slot] = SampleSlot(
                slot=pending.slot,
                name=name,
                data=data,
                metadata=meta,
            )

    def _current_download_sample(self) -> Optional[SampleSlot]:
        with self._lock:
            if self._download_slot is not None and self._download_slot in self._samples:
                return self._samples[self._download_slot]
            if self._samples:
                first_slot = sorted(self._samples)[0]
                return self._samples[first_slot]
            return None

    def _build_file_response(self, cmd: int, seq: int, status: int, payload: bytes) -> bytes:
        packed = Packed7.pack(payload)
        return bytes(
            [
                SYSEX_START,
                *TE_MFG_ID,
                *DEVICE_FAMILY,
                cmd & 0x7F,
                seq & 0x7F,
                CMD_FILE,
                status & 0x7F,
                *packed,
                SYSEX_END,
            ]
        )

    def _build_sysex_response(self, cmd: int, seq: int, payload: bytes, file_group: bool) -> bytes:
        if file_group:
            return self._build_file_response(cmd=cmd, seq=seq, status=0, payload=payload)
        return bytes(
            [
                SYSEX_START,
                *TE_MFG_ID,
                *DEVICE_FAMILY,
                cmd & 0x7F,
                seq & 0x7F,
                *payload,
                SYSEX_END,
            ]
        )

    def _delay(self) -> float:
        return self.response_delay_ms / 1000.0

    def _page_delay(self) -> float:
        return self.page_delay_ms / 1000.0

    def _populate_default_samples(self) -> None:
        seed_names = [
            "afterparty kick",
            "afterparty snare",
            "afterparty clap",
            "nt hh closed a",
            "nt hh closed b",
            "nt hh open",
            "epiano 360 bass",
            "digital stab",
            "acid one-shot",
            "vocal chop",
        ]
        for slot in range(1, 121):
            name = seed_names[(slot - 1) % len(seed_names)]
            data = self._make_pcm(slot=slot)
            meta = self._default_metadata(slot=slot, name=name)
            self._samples[slot] = SampleSlot(slot=slot, name=name, data=data, metadata=meta)

    @staticmethod
    def _default_metadata(slot: int, name: str) -> dict:
        return {
            "name": name,
            "sym": f"S{slot:03d}",
            "channels": 1,
            "samplerate": SAMPLE_RATE,
            "format": "s16",
            "sound.playmode": "oneshot",
            "sound.rootnote": 60,
            "sound.pitch": 0,
            "sound.pan": 0,
            "sound.amplitude": 100,
            "envelope.attack": 0,
            "envelope.release": 255,
        }

    @staticmethod
    def _make_pcm(slot: int, duration_sec: float = 0.22) -> bytes:
        frames = int(SAMPLE_RATE * duration_sec)
        freq = 110.0 + (slot % 24) * 11.0
        out = bytearray()
        for i in range(frames):
            val = int(14000 * math.sin((2.0 * math.pi * freq * i) / SAMPLE_RATE))
            out.extend(struct.pack("<h", val))
        return bytes(out)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run EP-133 KO-II MIDI emulator")
    parser.add_argument("--port", default="EP-133 Emulator", help="Virtual MIDI port name")
    parser.add_argument("--delay-ms", type=int, default=15, help="Default response delay")
    parser.add_argument("--page-delay-ms", type=int, default=6, help="Paged/chunk response delay")
    args = parser.parse_args()

    with EP133Emulator(
        port_name=args.port,
        response_delay_ms=args.delay_ms,
        page_delay_ms=args.page_delay_ms,
    ):
        print(f"EP-133 emulator running on virtual port: {args.port}")
        print("Press Ctrl+C to stop")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
