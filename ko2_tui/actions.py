from __future__ import annotations

from dataclasses import dataclass, field
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


def rename(slot: int, new_name: str) -> WorkerRequest:
    return WorkerRequest(op="rename", payload={"slot": int(slot), "new_name": new_name})


def delete(slot: int) -> WorkerRequest:
    return WorkerRequest(op="delete", payload={"slot": int(slot)})


def bulk_delete(slots: list[int]) -> WorkerRequest:
    return WorkerRequest(op="bulk_delete", payload={"slots": [int(s) for s in slots]})


def stop() -> WorkerRequest:
    return WorkerRequest(op="stop")
