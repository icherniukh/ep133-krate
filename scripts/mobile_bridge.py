#!/usr/bin/env python3
"""
krate-bridge — HTTP bridge daemon for the Krate mobile app.

Exposes EP-133 KO-II operations over HTTP so the Toga companion app
(running on iOS/Android) can control the device via a Mac/PC host.

Usage:
    python scripts/mobile_bridge.py [--host HOST] [--port PORT] [--device DEVICE]

The bridge must run on a machine that has the EP-133 connected via USB.
The Toga app talks to this bridge over the local network.

Install mobile extras first:
    pip install ep133-krate[mobile]
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional

# Ensure the src/ tree is importable when running from the repo root.
_repo_root = Path(__file__).resolve().parent.parent  # pylint: disable=invalid-name
sys.path.insert(0, str(_repo_root / "src"))

try:
    from fastapi import FastAPI, File, HTTPException, Query, UploadFile
    import uvicorn
except ImportError as exc:
    print(
        "fastapi and uvicorn are required for the bridge. "
        "Install with: pip install ep133-krate[mobile]",
        file=sys.stderr,
    )
    sys.exit(1)

# pylint: disable=wrong-import-position
from core.client import EP133Client, find_device
# pylint: enable=wrong-import-position

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
_log = logging.getLogger("krate-bridge")

app = FastAPI(title="krate-bridge", version="0.1.0")

# Global client — opened once at startup, shared across requests.
# EP133Client is synchronous; FastAPI runs in a single process here, so a
# module-level client is safe for the bridge's single-user use case.
_client: Optional[EP133Client] = None
_client_lock = threading.Lock()


def _get_client() -> EP133Client:
    if _client is None:
        raise HTTPException(status_code=503, detail="Device client not initialised")
    return _client


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    """Liveness probe — always returns 200 while the bridge is running."""
    return {"status": "ok", "device": _client.device_name if _client else None}


@app.get("/slots")
def list_slots() -> list[dict]:
    """Return all occupied sample slots as a JSON list.

    Each item: {"slot": int, "name": str, "size": int, "node_id": int | null}
    """
    client = _get_client()
    with _client_lock:
        try:
            sounds = client.list_sounds()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Device error: {exc}") from exc

        result = []
        for slot, entry in sorted(sounds.items()):
            result.append(
                {
                    "slot": slot,
                    "name": entry.get("name", ""),
                    "size": entry.get("size", 0),
                    "node_id": entry.get("node_id"),
                }
            )
    return result


@app.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    slot: int = Query(..., ge=1, le=999, description="Target slot number (1–999)"),
) -> dict:
    """Accept an audio file and upload it to the EP-133 at the given slot.

    The file is written to a temporary directory, then passed to
    EP133Client.put() which handles conversion and the SysEx upload sequence.
    FastAPI runs plain def routes in a thread pool, so the synchronous
    EP133Client.put() call does not block the event loop.
    """
    client = _get_client()
    contents = file.file.read()
    suffix = Path(file.filename or "upload.wav").suffix or ".wav"

    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td) / f"upload{suffix}"
        tmp_path.write_bytes(contents)
        with _client_lock:
            try:
                client.put(tmp_path, slot=slot, name=Path(file.filename or "").stem or None)
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Upload failed: {exc}") from exc

    return {"status": "ok", "slot": slot, "filename": file.filename}


@app.delete("/slots/{slot}")
def delete_slot(slot: int) -> dict:
    """Delete the sample at the given slot."""
    client = _get_client()
    with _client_lock:
        try:
            client.delete(slot)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Delete failed: {exc}") from exc
    return {"status": "ok", "slot": slot}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="krate-bridge: mobile HTTP bridge for EP-133 KO-II")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    parser.add_argument("--device", default=None, help="MIDI device name (auto-detected if omitted)")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    device_name = args.device or find_device()
    if not device_name:
        _log.error("EP-133 not found. Connect the device via USB and try again.")
        sys.exit(1)

    _log.info("Opening device: %s", device_name)
    _client = EP133Client(device_name=device_name)
    _client.connect()

    if args.host == "0.0.0.0":
        _log.warning("Bridge is accessible to all hosts on the network. Use --host 127.0.0.1 to restrict to localhost.")

    _log.info("krate-bridge listening on %s:%d", args.host, args.port)
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    finally:
        _client.close()
