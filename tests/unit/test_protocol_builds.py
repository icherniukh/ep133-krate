import pytest
from core.models import CMD_FILE, FileOp, MetaType, UPLOAD_PARENT_NODE
from core.types import Packed7
from core.models import (
    MetadataGetLegacyRequest, DeleteRequest, DownloadInitRequest, 
    DownloadChunkRequest, FileListRequest, MetadataGetRequest, UploadInitRequest
)


def _decode_payload(msg: bytes) -> bytes:
    """Strip CMD_FILE header and unpack 7-bit payload."""
    assert msg[0] == CMD_FILE
    return Packed7.unpack(msg[1:])


def test_build_info_request_slot_1():
    # Legacy GET_META (0x75) uses standard 7-bit packing with a BE16 slot.
    # Payload for slot=1: [0x07, 0x02, 0x00, 0x01, 0x00, 0x00]
    # No bytes have MSB set, so pack_flags is 0x00.
    msg = MetadataGetLegacyRequest(slot=1).pack_payload()
    assert msg[0] == 0x05  # CMD_FILE
    assert msg[1] == 0x00  # pack_flags
    assert msg[2:] == bytes([0x07, 0x02, 0x00, 0x01, 0x00, 0x00])


def test_build_delete_request_slot_129_decodes_raw():
    msg = DeleteRequest(slot=129).pack_payload()
    raw = _decode_payload(msg)
    assert raw == bytes([FileOp.DELETE, 0x00, 0x81])


def test_build_download_init_request_slot_129_decodes_raw():
    msg = DownloadInitRequest(slot=129).pack_payload()
    raw = _decode_payload(msg)
    # Slot 129 in raw 16-bit big-endian: hi=0x00, lo=0x81
    assert raw[:4] == bytes([FileOp.GET, 0x00, 0x00, 0x81])


def test_build_download_chunk_request_page_128_decodes_raw():
    msg = DownloadChunkRequest(page=128).pack_payload()
    raw = _decode_payload(msg)
    # payload_raw = [FileOp.GET, GET_DATA, page_lo, page_hi]
    assert raw[0] == FileOp.GET
    assert raw[2:] == bytes([0x00, 0x01])


def test_build_file_list_request_node_1000_page_0_decodes_raw():
    msg = FileListRequest(node_id=1000, page=0).pack_payload()
    raw = _decode_payload(msg)
    assert raw == bytes([FileOp.LIST, 0x00, 0x00, 0x03, 0xE8])


def test_build_metadata_get_request_node_1000_page_0_decodes_raw():
    msg = MetadataGetRequest(node_id=1000, page=0).pack_payload()
    raw = _decode_payload(msg)
    assert raw == bytes([FileOp.METADATA, MetaType.GET, 0x03, 0xE8, 0x00, 0x00])


def test_build_upload_init_request_slot_12_includes_parent_node():
    metadata = '{"channels":1,"samplerate":46875}'
    msg = UploadInitRequest(
        slot=12, file_size=1000, name="test", metadata_json=metadata
    ).pack_payload()
    raw = _decode_payload(msg)
    assert raw[0:7] == bytes([FileOp.PUT, 0x00, 0x05, 0x00, 0x0C, 0x03, 0xE8])
