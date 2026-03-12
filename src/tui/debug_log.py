from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from core.types import Packed7


@dataclass
class TraceEvent:
    ts: str
    dir: str
    len: int
    hex: str
    cmd: int | None = None
    family: str | None = None
    op: str | None = None
    fileop: int | None = None
    subop: int | None = None
    status: int | None = None
    slot: int | None = None
    node: int | None = None
    name: str | None = None

    def to_json(self) -> str:
        data = {k: v for k, v in asdict(self).items() if v is not None}
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)

    def ui_line(self) -> str:
        parts = [f"MIDI {self.dir}"]
        if self.cmd is not None:
            parts.append(f"cmd=0x{self.cmd:02X}")
        if self.op:
            parts.append(self.op)
        if self.status is not None:
            parts.append(f"st=0x{self.status:02X}")
        if self.slot is not None:
            parts.append(f"slot={self.slot}")
        if self.node is not None:
            parts.append(f"node={self.node}")
        if self.name:
            parts.append(f'name="{self.name}"')
        return " ".join(parts)


class DebugLogger:
    def __init__(
        self,
        enabled: bool,
        output_path: str | Path | None = None,
        capture_dir: str | Path = "captures",
    ):
        self.enabled = bool(enabled)
        self.path: Path | None = None
        self._fp = None
        self._lock = threading.Lock()

        if not self.enabled:
            return

        if output_path is None:
            capture_root = Path(capture_dir)
            capture_root.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
            self.path = capture_root / f"tui-{ts}.jsonl"
        else:
            self.path = Path(output_path)
            self.path.parent.mkdir(parents=True, exist_ok=True)

        self._fp = self.path.open("a", encoding="utf-8")

    def close(self) -> None:
        with self._lock:
            if self._fp:
                self._fp.close()
                self._fp = None

    def record(self, direction: str, raw: bytes) -> TraceEvent | None:
        if not self.enabled:
            return None
        event = _build_event(direction=direction, raw=raw)
        with self._lock:
            if self._fp:
                self._fp.write(event.to_json() + "\n")
                self._fp.flush()
        return event


def _build_event(direction: str, raw: bytes) -> TraceEvent:
    body = _strip_sysex(raw)
    cmd = None
    family = None
    op = None
    fileop = None
    subop = None
    status = None
    slot = None
    node = None
    name = None

    if len(body) >= 6 and body[0:3] == bytes([0x00, 0x20, 0x76]):
        family = f"{body[3]:02X}{body[4]:02X}"
        cmd = body[5]

        if len(body) > 7 and body[7:8] == b"\x05":
            finfo = {}
            decoded_payload = b""
            payload_candidates = []
            if direction == "RX" and len(body) > 9:
                status = body[8]
                payload_candidates.append(body[9:])
            if len(body) > 8:
                payload_candidates.append(body[8:])

            for candidate in payload_candidates:
                try:
                    decoded = Packed7.unpack(candidate)
                    maybe = _decode_fileop(decoded)
                except Exception:
                    continue
                if not decoded_payload:
                    decoded_payload = decoded
                if maybe.get("fileop") in {0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x0B}:
                    finfo = maybe
                    break
            op = finfo.get("op")
            fileop = finfo.get("fileop")
            subop = finfo.get("subop")
            slot = finfo.get("slot")
            node = finfo.get("node")
            name = finfo.get("name")
            if op is None and direction == "RX":
                if cmd == 0x3D and decoded_payload:
                    op = "GET_INIT_RSP"
                    name = _extract_name_from_payload(decoded_payload)
                elif cmd == 0x2A:
                    op = "LIST_RSP"
                elif cmd == 0x37:
                    op = "GENERIC_RSP"
            if op is None:
                op = _cmd_label(cmd)
        else:
            op = _cmd_label(cmd)

    return TraceEvent(
        ts=datetime.now().strftime("%H:%M:%S.%f")[:-3],
        dir=direction,
        len=len(raw),
        hex=raw.hex().upper(),
        cmd=cmd,
        family=family,
        op=op,
        fileop=fileop,
        subop=subop,
        status=status,
        slot=slot,
        node=node,
        name=name,
    )


def _strip_sysex(raw: bytes) -> bytes:
    if len(raw) >= 2 and raw[0] == 0xF0 and raw[-1] == 0xF7:
        return raw[1:-1]
    return raw


def _decode_fileop(raw: bytes) -> dict[str, Any]:
    info: dict[str, Any] = {}
    if not raw:
        return info

    fileop = raw[0]
    subop = raw[1] if len(raw) > 1 else None
    info["fileop"] = fileop
    info["subop"] = subop

    if fileop == 0x02 and subop == 0x00 and len(raw) >= 11:
        info["op"] = "PUT_INIT"
        info["slot"] = (raw[3] << 8) | raw[4]
        info["node"] = (raw[5] << 8) | raw[6]
        rest = raw[11:]
        name = rest.split(b"\x00", 1)[0]
        info["name"] = name.decode("utf-8", errors="replace")
    elif fileop == 0x02 and subop == 0x01:
        info["op"] = "PUT_DATA"
    elif fileop == 0x03:
        if subop == 0x00:
            if len(raw) >= 7 and raw[2] == 0x05:
                info["op"] = "GET_INIT_RSP"
            elif len(raw) >= 4:
                info["op"] = "GET_INIT"
                info["slot"] = (raw[2] << 8) | raw[3]
            else:
                info["op"] = "GET"
        elif subop == 0x01:
            info["op"] = "GET_DATA"
        else:
            info["op"] = "GET"
    elif fileop == 0x04:
        info["op"] = "LIST"
        if len(raw) >= 5:
            info["node"] = (raw[3] << 8) | raw[4]
    elif fileop == 0x06 and len(raw) >= 3:
        info["op"] = "DELETE"
        info["slot"] = (raw[1] << 8) | raw[2]
    elif fileop == 0x07:
        info["op"] = "META_SET" if subop == 0x01 else "META_GET" if subop == 0x02 else "META"
        if len(raw) >= 4:
            info["node"] = (raw[2] << 8) | raw[3]
    elif fileop == 0x0B:
        info["op"] = "VERIFY"
        if len(raw) >= 4:
            info["slot"] = (raw[2] << 8) | raw[3]

    return info


def _cmd_label(cmd: int | None) -> str | None:
    if cmd is None:
        return None
    labels = {
        0x61: "INIT",
        0x6A: "LIST_FILES",
        0x6C: "UPLOAD_DATA",
        0x6D: "UPLOAD_END",
        0x75: "GET_META",
        0x76: "PLAYBACK",
        0x77: "INFO",
        0x7C: "PROJECT",
        0x7D: "DOWNLOAD",
        0x7E: "UPLOAD",
        0x20: "INIT_RSP",
        0x21: "INFO_RSP",
        0x2A: "LIST_RSP",
        0x35: "META_RSP",
        0x37: "GENERIC_RSP",
        0x3D: "DOWNLOAD_RSP",
    }
    return labels.get(cmd)


def _extract_name_from_payload(payload: bytes) -> str | None:
    import re

    m = re.search(rb"([0-9]{1,3}\.pcm)", payload)
    if m:
        try:
            return m.group(1).decode("utf-8", errors="replace")
        except Exception:
            pass

    dot = payload.find(b".pcm")
    if dot == -1:
        return None
    start = dot
    while start > 0 and payload[start - 1] not in (0x00,):
        start -= 1
    end = payload.find(b"\x00", dot)
    if end == -1:
        end = dot + 4
    raw = payload[start:end]
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return None
    return text or None
