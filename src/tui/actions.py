from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class WorkerRequest:
    op: str
    payload: dict[str, Any] = field(default_factory=dict)


def refresh_inventory() -> WorkerRequest:
    return WorkerRequest(op="refresh_inventory")


def fetch_details(slot: int) -> WorkerRequest:
    return WorkerRequest(op="fetch_details", payload={"slot": int(slot)})


def download(slot: int, output_path: str) -> WorkerRequest:
    return WorkerRequest(op="download", payload={"slot": int(slot), "output_path": output_path})


def upload(slot: int, input_path: str, name: str | None = None) -> WorkerRequest:
    return WorkerRequest(
        op="upload",
        payload={"slot": int(slot), "input_path": input_path, "name": name},
    )


def copy(src: int, dst: int) -> WorkerRequest:
    return WorkerRequest(op="copy", payload={"src": int(src), "dst": int(dst)})


def move(src: int, dst: int) -> WorkerRequest:
    return WorkerRequest(op="move", payload={"src": int(src), "dst": int(dst)})


def rename(slot: int, new_name: str) -> WorkerRequest:
    return WorkerRequest(op="rename", payload={"slot": int(slot), "new_name": new_name})


def delete(slot: int) -> WorkerRequest:
    return WorkerRequest(op="delete", payload={"slot": int(slot)})


def bulk_delete(slots: list[int]) -> WorkerRequest:
    return WorkerRequest(op="bulk_delete", payload={"slots": [int(s) for s in slots]})


def squash(start: int = 1, end: int = 999) -> WorkerRequest:
    return WorkerRequest(op="squash", payload={"start": start, "end": end})


def optimize_all(min_size: int = 0) -> WorkerRequest:
    return WorkerRequest(op="optimize_all", payload={"min_size": min_size})


def optimize(slots: list[int], mono: bool = True, rate: int | None = None, speed: float | None = None, pitch: float = 0.0) -> WorkerRequest:
    return WorkerRequest(op="optimize", payload={
        "slots": [int(s) for s in slots],
        "mono": mono,
        "rate": rate,
        "speed": speed,
        "pitch": pitch,
    })


def waveform(slot: int, width: int = 320, height: int = 24) -> WorkerRequest:
    return WorkerRequest(op="waveform", payload={"slot": int(slot), "width": int(width), "height": int(height)})


def audition(slot: int, duration_s: float = 0.0) -> WorkerRequest:
    return WorkerRequest(op="audition", payload={"slot": int(slot), "duration_s": float(duration_s)})


def batch_upload(files_and_slots: list[tuple[Path | str, int]]) -> WorkerRequest:
    return WorkerRequest(
        op="batch_upload",
        payload={"files_and_slots": [(str(p), int(s)) for p, s in files_and_slots]},
    )


def stop() -> WorkerRequest:
    return WorkerRequest(op="stop")
