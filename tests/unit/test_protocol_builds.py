from ko2_protocol import (
    build_info_request,
    build_delete_request,
    build_download_init_request,
    build_download_chunk_request,
    build_file_list_request,
    build_metadata_get_request,
    build_upload_init_request,
    CMD_FILE,
    FileOp,
    MetaType,
    UPLOAD_PARENT_NODE,
)
from ko2_wire import Packed7


def _decode_payload(msg: bytes) -> bytes:
    assert msg[0] == CMD_FILE
    return Packed7.unpack(msg[1:])


def test_build_info_request_slot_1():
    assert build_info_request(1) == bytes([0x05, 0x08, 0x07, 0x02, 0x00, 0x01, 0x00, 0x00])


def test_build_delete_request_slot_129_decodes_raw():
    msg = build_delete_request(129)
    raw = _decode_payload(msg)
    assert raw == bytes([FileOp.DELETE, 0x00, 0x81])


def test_build_download_init_request_slot_129_decodes_raw():
    msg = build_download_init_request(129)
    raw = _decode_payload(msg)
    # Slot 129 in raw 16-bit big-endian: hi=0x00, lo=0x81
    assert raw[:4] == bytes([FileOp.GET, 0x00, 0x00, 0x81])


def test_build_download_chunk_request_page_128_decodes_raw():
    msg = build_download_chunk_request(128)
    raw = _decode_payload(msg)
    # payload_raw = [FileOp.GET, GET_DATA, page_lo, page_hi]
    assert raw[0] == FileOp.GET
    assert raw[2:] == bytes([0x00, 0x01])


def test_build_file_list_request_node_1000_page_0_decodes_raw():
    msg = build_file_list_request(1000, page=0)
    raw = _decode_payload(msg)
    assert raw == bytes([FileOp.LIST, 0x00, 0x00, 0x03, 0xE8])


def test_build_metadata_get_request_node_1000_page_0_decodes_raw():
    msg = build_metadata_get_request(1000, page=0)
    raw = _decode_payload(msg)
    assert raw == bytes([FileOp.METADATA, MetaType.GET, 0x03, 0xE8, 0x00, 0x00])


def test_build_upload_init_request_slot_12_includes_parent_node():
    msg = build_upload_init_request(12, file_size=1000, channels=1, samplerate=46875, name="test")
    raw = Packed7.unpack(msg)
    assert raw[0:7] == bytes([FileOp.PUT, 0x00, 0x05, 0x00, 0x0C, 0x03, 0xE8])
    assert raw[5] == (UPLOAD_PARENT_NODE >> 8) & 0xFF
    assert raw[6] == UPLOAD_PARENT_NODE & 0xFF
