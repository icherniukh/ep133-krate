#!/usr/bin/env python3
"""
MIDI Proxy & Sniffer for EP-133.

Creates virtual MIDI ports to intercept and log traffic between an application
(like the Teenage Engineering Sample Tool) and the physical EP-133 device.

Usage:
  1. Run this tool: python3 midi_proxy.py --proxy
  2. Open the EP Sample Tool (or any MIDI app).
  3. In the app's MIDI settings, select:
     - Output: "EP-133 Proxy In"
     - Input:  "EP-133 Proxy Out"
  4. All SysEx traffic will be logged to the captures/ directory.
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import mido
import mido.ports
from mido.ports import BaseOutput

try:
    from core.types import Packed7 as _Packed7
except ImportError:
    _Packed7 = None  # pylint: disable=invalid-name

_original_send = None  # pylint: disable=invalid-name
_HUNT_KEYWORDS = {
    "get_meta": {"cmds": {0x75}},
    "meta_rsp": {"cmds": {0x35}},
    "info": {"cmds": {0x77}},
    "playback": {"fileops": {0x05}},  # TE Tool uses rotating devids 0x60-0x6A; match by FileOp
    "list": {"fileops": {0x04}},
    "meta": {"fileops": {0x07}},
    "meta_get": {"fileops": {0x07}, "subops": {0x02}},
    "meta_set": {"fileops": {0x07}, "subops": {0x01}},
    "put": {"fileops": {0x02}},
    "delete": {"fileops": {0x06}},
    "verify": {"fileops": {0x0B}},
    "any": {"any": True},
}
_HUNT_CMD_LABELS = {
    0x75: "GET_META",
    0x35: "META_RSP",
    0x77: "GET_INFO",
    0x76: "PLAYBACK",
}

def find_ep133():
    for port in mido.get_output_names():
        if 'EP-133' in port or 'EP-1320' in port:
            return port
    return None

def _hex_compact(data: bytes) -> str:
    return "".join(f"{b:02X}" for b in data)


def _parse_te_header(data: bytes) -> dict | None:
    if len(data) < 6:
        return None
    if data[0:3] != bytes([0x00, 0x20, 0x76]):
        return None
    return {
        "mfg": "002076",
        "family": f"{data[3]:02X}{data[4]:02X}",
        "cmd": data[5],
    }


def _format_jsonl(entry: dict) -> str:
    return json.dumps(entry, separators=(",", ":"))


def _format_tsv(entry: dict) -> str:
    cmd = entry.get("cmd")
    cmd_str = f"0x{cmd:02X}" if isinstance(cmd, int) else ""
    return "\t".join(
        [
            entry.get("ts", ""),
            entry.get("dir", ""),
            str(entry.get("len", "")),
            entry.get("mfg", ""),
            entry.get("family", ""),
            cmd_str,
            entry.get("hex", ""),
        ]
    )


def _format_plain(entry: dict) -> str:
    cmd = entry.get("cmd")
    cmd_str = f"0x{cmd:02X}" if isinstance(cmd, int) else "-"
    family = entry.get("family", "-")
    return (
        f"{entry.get('ts','')} {entry.get('dir','')} len={entry.get('len','')}"
        f" cmd={cmd_str} family={family} hex={entry.get('hex','')}"
    )


def _log_sysex(
    fp,
    formatter,
    direction: str,
    msg_data: bytes,
    raw_mode: bool,
    mid_events,
    hunt,
) -> None:
    full = bytes([0xF0]) + msg_data + bytes([0xF7])
    ts_ms = int(time.time() * 1000)
    if mid_events is not None:
        mid_events.append((ts_ms, direction, full))

    header = _parse_te_header(msg_data)
    finfo = None
    if header:
        payload = msg_data[7:]
        if payload[:1] == b"\x05":
            if _Packed7:
                raw_payload = _Packed7.unpack(payload[1:])
                finfo = _decode_fileop(raw_payload)

    if hunt and _hunt_match(hunt, header, finfo):
        ts = datetime.fromtimestamp(ts_ms / 1000.0).strftime("%H:%M:%S.%f")[:-3]
        cmd = header.get("cmd") if header else None
        cmd_label = _HUNT_CMD_LABELS.get(cmd, f"0x{cmd:02X}" if cmd is not None else "?")
        parts = [ts, direction, f"cmd={cmd_label}"]
        if finfo:
            if finfo.get("op"):
                parts.append(finfo["op"])
            if "slot" in finfo:
                parts.append(f"slot={finfo['slot']}")
            if "node" in finfo:
                parts.append(f"node={finfo['node']}")
            if "name" in finfo and finfo["name"]:
                parts.append(f"name=\"{finfo['name']}\"")
            fields = finfo.get("meta_fields")
            if isinstance(fields, dict):
                for key in ("active", "sym", "sample.start", "sample.end"):
                    if key in fields:
                        parts.append(f"{key}={fields[key]}")
        print("HUNT " + " ".join(parts))
        _hunt_count(hunt, header, finfo)

    if raw_mode:
        if fp is None:
            return
        dir_byte = b"T" if direction == "TX" else b"R"
        header_bytes = dir_byte + ts_ms.to_bytes(8, "little") + len(full).to_bytes(4, "little")
        fp.write(header_bytes + full)
        fp.flush()
        return
    if formatter is None or fp is None:
        return
    entry = {
        "ts": datetime.fromtimestamp(ts_ms / 1000.0).strftime("%H:%M:%S.%f")[:-3],
        "dir": direction,
        "len": len(full),
        "hex": _hex_compact(full),
    }
    if header:
        entry.update(header)
    fp.write(formatter(entry) + "\n")
    fp.flush()


def instrumented_send(self, msg):
    """Instrumented send that logs SysEx messages."""
    if hasattr(msg, "type") and msg.type == "sysex":
        _log_sysex(
            instrumented_send._log_fp,
            instrumented_send._formatter,
            "TX",
            bytes(msg.data),
            instrumented_send._raw_mode,
            instrumented_send._mid_events,
            instrumented_send._hunt,
        )
    return _original_send(self, msg)  # pylint: disable=not-callable

def _parse_args():
    parser = argparse.ArgumentParser(
        description="Capture EP-133 SysEx traffic to a file."
    )
    parser.add_argument(
        "output",
        nargs="?",
        help="Output file path (default: captures/sniffer-<timestamp>.<ext>)",
    )
    parser.add_argument(
        "--format",
        choices=["jsonl", "tsv", "plain", "raw", "mid"],
        default="jsonl",
        help="Output format (default: jsonl)",
    )
    parser.add_argument(
        "--proxy",
        action="store_true",
        help="Run as a proxy to capture both directions from another app.",
    )
    parser.add_argument(
        "--device",
        help="Explicit EP-133 port name (default: auto-detect)",
    )
    parser.add_argument(
        "--virtual-in",
        default="EP-133 Proxy In",
        help="Virtual input port name (app sends to this)",
    )
    parser.add_argument(
        "--virtual-out",
        default="EP-133 Proxy Out",
        help="Virtual output port name (app listens to this)",
    )
    parser.add_argument(
        "--spoof",
        action="store_true",
        help="Spoof the device name (uses 'EP-133' for virtual ports) to trick hardcoded apps.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print a JSONL capture file and exit.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors in pretty output.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of lines printed in pretty mode.",
    )
    parser.add_argument(
        "--hunt",
        action="append",
        metavar="KEY",
        help=(
            "Print matched traffic during capture. "
            "Keys: get_meta, meta_rsp, info, playback, list, meta, meta_get, meta_set, put, delete, verify, any, "
            "or cmd=0x75, fileop=0x04. Can be used multiple times."
        ),
    )
    return parser.parse_args()


def main():
    args = _parse_args()

    if args.pretty:
        if not args.output:
            print("Pretty mode requires an input file path.")
            sys.exit(2)
        if args.format == "mid":
            print("Pretty mode does not support .mid files.")
            sys.exit(2)
        pretty_print(
            Path(args.output),
            color=not args.no_color,
            limit=args.limit,
            raw=(args.format == "raw"),
        )
        return

    if args.spoof:
        args.virtual_in = "EP-133"
        args.virtual_out = "EP-133"

    out_path = Path(args.output) if args.output else None
    if out_path is None:
        out_dir = Path("captures")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        ext = {
            "jsonl": "jsonl",
            "tsv": "tsv",
            "plain": "log",
            "raw": "bin",
            "mid": "mid",
        }[args.format]
        out_path = out_dir / f"sniffer-{ts}.{ext}"

    device = args.device or find_ep133()
    if not device:
        print("EP-133 not found")
        sys.exit(1)

    print(f"Capturing traffic for: {device}")
    print(f"Writing {args.format} to: {out_path}")
    if args.proxy:
        print("Proxy mode enabled.")
        print(f"  App output -> {args.virtual_in}")
        print(f"  App input  <- {args.virtual_out}")
    print("Press Ctrl+C to stop\n")

    formatter = {
        "jsonl": _format_jsonl,
        "tsv": _format_tsv,
        "plain": _format_plain,
        "raw": None,
        "mid": None,
    }[args.format]
    raw_mode = args.format == "raw"
    mid_mode = args.format == "mid"
    mid_events = [] if mid_mode else None

    hunt = _parse_hunt(args.hunt)

    def run_capture(fp):
        if fp and args.format == "tsv" and out_path.stat().st_size == 0:
            fp.write("ts\tdir\tlen\tmfg\tfamily\tcmd\thex\n")

        if args.proxy:
            # Proxy between official app and device to capture both directions.
            in_real = mido.open_input(device)
            out_real = mido.open_output(device)
            in_virtual = mido.open_input(args.virtual_in, virtual=True)
            out_virtual = mido.open_output(args.virtual_out, virtual=True)
            try:
                while True:
                    for msg in in_virtual.iter_pending():
                        if msg.type == "sysex":
                            _log_sysex(
                                fp,
                                formatter,
                                "TX",
                                bytes(msg.data),
                                raw_mode,
                                mid_events,
                                hunt,
                            )
                        out_real.send(msg)
                    for msg in in_real.iter_pending():
                        if msg.type == "sysex":
                            _log_sysex(
                                fp,
                                formatter,
                                "RX",
                                bytes(msg.data),
                                raw_mode,
                                mid_events,
                                hunt,
                            )
                        out_virtual.send(msg)
                    time.sleep(0.001)
            except KeyboardInterrupt:
                print("\nStopped")
            finally:
                in_real.close()
                out_real.close()
                in_virtual.close()
                out_virtual.close()
        else:
            # Monkey-patch the BaseOutput.send method for this process only.
            _original_send = BaseOutput.send

            instrumented_send._log_fp = fp
            instrumented_send._formatter = formatter
            instrumented_send._raw_mode = raw_mode
            instrumented_send._mid_events = mid_events
            instrumented_send._hunt = hunt
            BaseOutput.send = instrumented_send
            try:
                # Also monitor incoming messages
                inport = mido.open_input(device)
                for msg in inport:
                    if msg.type == "sysex":
                        _log_sysex(
                            fp,
                            formatter,
                            "RX",
                            bytes(msg.data),
                            raw_mode,
                            mid_events,
                            hunt,
                        )
            except KeyboardInterrupt:
                print("\nStopped")
            finally:
                BaseOutput.send = _original_send

    if mid_mode:
        run_capture(None)
        _write_mid(out_path, mid_events)
        if hunt:
            _print_hunt_summary(hunt)
        return

    open_mode = "ab" if raw_mode else "a"
    encoding = None if raw_mode else "utf-8"
    with open(out_path, open_mode, encoding=encoding) as fp:
        run_capture(fp)
    if hunt:
        _print_hunt_summary(hunt)


def _parse_hunt(specs: list[str] | None) -> dict | None:
    if not specs:
        return None
    cmds: set[int] = set()
    fileops: set[int] = set()
    subops: set[int] = set()
    any_flag = False
    for raw in specs:
        spec = str(raw).strip().lower()
        if not spec:
            continue
        if spec.startswith("cmd="):
            val = _parse_int(spec[4:])
            cmds.add(val)
            continue
        if spec.startswith("fileop="):
            val = _parse_int(spec[7:])
            fileops.add(val)
            continue
        if spec in _HUNT_KEYWORDS:
            entry = _HUNT_KEYWORDS[spec]
            if entry.get("any"):
                any_flag = True
            cmds.update(entry.get("cmds", set()))
            fileops.update(entry.get("fileops", set()))
            subops.update(entry.get("subops", set()))
            continue
        print(f"Unknown --hunt key: {raw}")
        sys.exit(2)
    return {
        "cmds": cmds,
        "fileops": fileops,
        "subops": subops,
        "any": any_flag,
        "counts": {},
        "node_counts": {},
    }


def _parse_int(value: str) -> int:
    value = value.strip().lower()
    if value.startswith("0x"):
        return int(value, 16)
    return int(value, 10)


def _hunt_match(hunt: dict, header: dict | None, finfo: dict | None) -> bool:
    if not hunt:
        return False
    if hunt.get("any"):
        return True
    if header:
        cmd = header.get("cmd")
        if cmd in hunt.get("cmds", set()):
            return True
    if finfo:
        fileop = finfo.get("fileop")
        if fileop in hunt.get("fileops", set()):
            subops = hunt.get("subops", set())
            if not subops:
                return True
            subop = finfo.get("subop")
            if subop in subops:
                return True
            return False
    return False


def _hunt_count(hunt: dict, header: dict | None, finfo: dict | None) -> None:
    if not hunt:
        return
    counts = hunt.setdefault("counts", {})
    key = None
    if finfo and finfo.get("op"):
        key = finfo["op"]
    elif header and header.get("cmd") is not None:
        cmd = header["cmd"]
        key = _HUNT_CMD_LABELS.get(cmd, f"CMD_0x{cmd:02X}")
    if key:
        counts[key] = counts.get(key, 0) + 1
    if finfo and finfo.get("op") in ("META_GET", "META_SET"):
        node = finfo.get("node")
        if node is not None:
            node_counts = hunt.setdefault("node_counts", {})
            op_nodes = node_counts.setdefault(finfo["op"], {})
            op_nodes[node] = op_nodes.get(node, 0) + 1


def _print_hunt_summary(hunt: dict) -> None:
    counts = hunt.get("counts") or {}
    if not counts:
        print("HUNT summary: no matches")
        return
    print("HUNT summary:")
    for key in sorted(counts.keys()):
        print(f"  {key}: {counts[key]}")
    node_counts = hunt.get("node_counts") or {}
    for op in ("META_GET", "META_SET"):
        nodes = node_counts.get(op)
        if not nodes:
            continue
        top = sorted(nodes.items(), key=lambda item: (-item[1], item[0]))[:10]
        top_str = ", ".join(f"{node}={count}" for node, count in top)
        print(f"  {op} top nodes: {top_str}")


def _color(text: str, code: str, enable: bool) -> str:
    if not enable:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def _format_hex_color(data: bytes, color: bool) -> str:
    if not data:
        return ""
    parts = []
    for i, b in enumerate(data):
        hx = f"{b:02X}"
        if i in (0, len(data) - 1):
            parts.append(_color(hx, "1;37", color))
        elif i in (1, 2, 3):
            parts.append(_color(hx, "34", color))
        elif i in (4, 5):
            parts.append(_color(hx, "36", color))
        elif i == 6:
            parts.append(_color(hx, "35", color))
        elif i == 7:
            parts.append(_color(hx, "33", color))
        elif i == 8 and b == 0x05:
            parts.append(_color(hx, "32", color))
        else:
            parts.append(_color(hx, "90", color))
    return " ".join(parts)


def _decode_fileop(raw: bytes) -> dict:
    info: dict = {}
    if not raw:
        return info
    fileop = raw[0]
    subop = raw[1] if len(raw) > 1 else None
    info["fileop"] = fileop
    info["subop"] = subop
    if fileop == 0x02 and subop == 0x00 and len(raw) >= 11:
        info["op"] = "PUT_INIT"
        slot = (raw[3] << 8) | raw[4]
        node = (raw[5] << 8) | raw[6]
        size = int.from_bytes(raw[7:11], "big")
        rest = raw[11:]
        name = rest.split(b"\x00", 1)[0]
        meta = rest[len(name) + 1 :]
        info.update(
            {
                "slot": slot,
                "node": node,
                "size": size,
                "name": name.decode("utf-8", errors="replace"),
                "meta": meta.decode("utf-8", errors="replace").strip("\x00"),
            }
        )
    elif fileop == 0x02 and subop == 0x01 and len(raw) >= 4:
        info["op"] = "PUT_DATA"
        info["offset"] = (raw[2] << 8) | raw[3]
    elif fileop == 0x06 and len(raw) >= 3:
        info["op"] = "DELETE"
        info["slot"] = (raw[1] << 8) | raw[2]
    elif fileop == 0x07 and len(raw) >= 3:
        if subop == 0x01:
            info["op"] = "META_SET"
        elif subop == 0x02:
            info["op"] = "META_GET"
        else:
            info["op"] = "META"
        if len(raw) >= 4:
            info["node"] = (raw[2] << 8) | raw[3]
        if subop == 0x01 and len(raw) > 4:
            payload = raw[4:]
            try:
                text = payload.decode("utf-8", errors="replace").strip("\x00")
                info["meta"] = text
                if text.startswith("{") and text.endswith("}"):
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        if "name" in parsed:
                            info["name"] = parsed.get("name") or ""
                        fields = {}
                        for key in ("active", "sym", "sample.start", "sample.end"):
                            if key in parsed:
                                fields[key] = parsed[key]
                        if fields:
                            info["meta_fields"] = fields
            except Exception:
                pass
    elif fileop == 0x0B and len(raw) >= 3:
        info["op"] = "VERIFY"
        info["slot"] = raw[2]
    return info


def _encode_vlq(value: int) -> bytes:
    value = max(value, 0)
    parts = [value & 0x7F]
    value >>= 7
    while value:
        parts.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(parts))


def _build_track(name: str | None, events: list[tuple[int, bytes]], tempo_us: int | None = None) -> bytes:
    chunks = []
    if name is not None:
        name_bytes = name.encode("ascii", errors="replace")
        chunks.append(_encode_vlq(0) + b"\xFF\x03" + _encode_vlq(len(name_bytes)) + name_bytes)
    if tempo_us is not None:
        tempo_bytes = tempo_us.to_bytes(3, "big")
        chunks.append(_encode_vlq(0) + b"\xFF\x51\x03" + tempo_bytes)
    for delta, ev in events:
        chunks.append(_encode_vlq(delta) + ev)
    chunks.append(_encode_vlq(0) + b"\xFF\x2F\x00")
    data = b"".join(chunks)
    return b"MTrk" + len(data).to_bytes(4, "big") + data


def _write_mid(path: Path, events: list[tuple[int, str, bytes]] | None) -> None:
    ppqn = 1000
    tempo_us = 1_000_000
    events = events or []
    if events:
        start_ms = min(ts for ts, _, _ in events)
    else:
        start_ms = int(time.time() * 1000)

    indexed = [(i, ts - start_ms, direction, data) for i, (ts, direction, data) in enumerate(events)]

    def build_track_events(direction: str) -> list[tuple[int, bytes]]:
        selected = [(rel, i, data) for i, rel, dirn, data in indexed if dirn == direction]
        selected.sort(key=lambda row: (row[0], row[1]))
        last_rel = 0
        out = []
        for rel, _, data in selected:
            delta = int(rel - last_rel)
            last_rel = rel
            payload = data[1:] if data[:1] == b"\xF0" else data
            ev = b"\xF0" + _encode_vlq(len(payload)) + payload
            out.append((delta, ev))
        return out

    meta_track = _build_track("META", [], tempo_us=tempo_us)
    tx_track = _build_track("TX", build_track_events("TX"))
    rx_track = _build_track("RX", build_track_events("RX"))

    header = b"MThd" + (6).to_bytes(4, "big")
    header += (1).to_bytes(2, "big")  # format 1
    header += (3).to_bytes(2, "big")  # tracks
    header += ppqn.to_bytes(2, "big")

    with open(path, "wb") as fp:
        fp.write(header)
        fp.write(meta_track)
        fp.write(tx_track)
        fp.write(rx_track)


def _iter_raw_entries(fp):
    while True:
        dir_byte = fp.read(1)
        if not dir_byte:
            break
        ts_bytes = fp.read(8)
        if len(ts_bytes) < 8:
            break
        len_bytes = fp.read(4)
        if len(len_bytes) < 4:
            break
        msg_len = int.from_bytes(len_bytes, "little")
        data = fp.read(msg_len)
        if len(data) < msg_len:
            break
        ts_ms = int.from_bytes(ts_bytes, "little")
        ts = datetime.fromtimestamp(ts_ms / 1000.0).strftime("%H:%M:%S.%f")[:-3]
        direction = "TX" if dir_byte == b"T" else "RX"
        yield {
            "ts": ts,
            "dir": direction,
            "len": len(data),
            "hex": _hex_compact(data),
        }


def pretty_print(
    path: Path, color: bool = True, limit: int | None = None, raw: bool = False
) -> None:
    count = 0
    if raw:
        with open(path, "rb") as f:
            for entry in _iter_raw_entries(f):
                hex_str = entry.get("hex")
                if not hex_str:
                    continue
                data = bytes.fromhex(hex_str)
                ts = entry.get("ts", "")
                direction = entry.get("dir", "?")
                dir_color = "32" if direction == "TX" else "36"
                dir_label = _color(direction, dir_color, color)
                info_parts = []
                if (
                    len(data) >= 9
                    and data[0] == 0xF0
                    and data[-1] == 0xF7
                    and data[1:4] == bytes([0x00, 0x20, 0x76])
                    and data[4:6] == bytes([0x33, 0x40])
                ):
                    dev = data[6]
                    seq = data[7]
                    info_parts.append(f"dev=0x{dev:02X}")
                    info_parts.append(f"seq=0x{seq:02X}")
                    payload = data[8:-1]
                    if payload[:1] == b"\x05":
                        raw_payload = _Packed7.unpack(payload[1:])
                        finfo = _decode_fileop(raw_payload)
                        if finfo.get("op"):
                            info_parts.append(finfo["op"])
                        if "slot" in finfo:
                            info_parts.append(f"slot={finfo['slot']}")
                        if "offset" in finfo:
                            info_parts.append(f"off={finfo['offset']}")
                        if "size" in finfo:
                            info_parts.append(f"size={finfo['size']}")
                        if "node" in finfo:
                            info_parts.append(f"node={finfo['node']}")
                        if "name" in finfo:
                            info_parts.append(f"name=\"{finfo['name']}\"")
                info = " ".join(info_parts)
                hex_out = _format_hex_color(data, color)
                line_out = f"{ts} {dir_label} {info} | {hex_out}".rstrip()
                print(line_out)
                count += 1
                if limit is not None and count >= limit:
                    return
        return

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            hex_str = entry.get("hex")
            if not hex_str:
                continue
            data = bytes.fromhex(hex_str)
            ts = entry.get("ts", "")
            direction = entry.get("dir", "?")
            dir_color = "32" if direction == "TX" else "36"
            dir_label = _color(direction, dir_color, color)
            info_parts = []
            if (
                len(data) >= 9
                and data[0] == 0xF0
                and data[-1] == 0xF7
                and data[1:4] == bytes([0x00, 0x20, 0x76])
                and data[4:6] == bytes([0x33, 0x40])
            ):
                dev = data[6]
                seq = data[7]
                info_parts.append(f"dev=0x{dev:02X}")
                info_parts.append(f"seq=0x{seq:02X}")
                payload = data[8:-1]
                if payload[:1] == b"\x05":
                    raw = _Packed7.unpack(payload[1:])
                    finfo = _decode_fileop(raw)
                    if finfo.get("op"):
                        info_parts.append(finfo["op"])
                    if "slot" in finfo:
                        info_parts.append(f"slot={finfo['slot']}")
                    if "offset" in finfo:
                        info_parts.append(f"off={finfo['offset']}")
                    if "size" in finfo:
                        info_parts.append(f"size={finfo['size']}")
                    if "node" in finfo:
                        info_parts.append(f"node={finfo['node']}")
                    if "name" in finfo:
                        info_parts.append(f"name=\"{finfo['name']}\"")
            info = " ".join(info_parts)
            hex_out = _format_hex_color(data, color)
            line_out = f"{ts} {dir_label} {info} | {hex_out}".rstrip()
            print(line_out)
            count += 1
            if limit is not None and count >= limit:
                break

if __name__ == '__main__':
    main()
