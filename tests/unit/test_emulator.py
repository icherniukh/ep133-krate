import json

from ko2_emulator import EP133Emulator, DOWNLOAD_CHUNK_SIZE
from ko2_models import (
    DeleteRequest,
    DownloadChunkRequest,
    DownloadInitRequest,
    FileListRequest,
    MetadataGetRequest,
    MetadataSetRequest,
    UploadChunkRequest,
    UploadEndRequest,
    UploadInitRequest,
    UploadVerifyRequest,
    parse_file_list_response,
    slot_from_sound_entry,
)
from ko2_types import Packed7, U14LE
from ko2_client import _extract_download_file_size


def _decode_file_response(raw: bytes) -> tuple[int, int, int, bytes]:
    assert raw[0] == 0xF0 and raw[-1] == 0xF7
    cmd = raw[6]
    seq = raw[7]
    file_cmd = raw[8]
    status = raw[9]
    payload = Packed7.unpack(raw[10:-1])
    assert file_cmd == 0x05
    return cmd, seq, status, payload


def _extract_size_from_download_init(payload: bytes) -> int:
    size = _extract_download_file_size(payload)
    assert size is not None
    return size


def test_emulator_list_files_returns_entries():
    emu = EP133Emulator()
    req = FileListRequest(node_id=1000, page=0).build(seq=7)

    responses = emu.handle_sysex(req)
    assert len(responses) == 1

    resp, _delay = responses[0]
    cmd, seq, status, payload = _decode_file_response(resp)
    assert cmd == (0x6A - 0x40)
    assert seq == 7
    assert status == 0

    entries = parse_file_list_response(payload)
    assert entries
    slots = [slot_from_sound_entry(e) for e in entries]
    assert 1 in slots


def test_emulator_metadata_get_and_set_roundtrip():
    emu = EP133Emulator()

    get_req = MetadataGetRequest(node_id=1, page=0).build(seq=1)
    get_resp = emu.handle_sysex(get_req)[0][0]
    _cmd, _seq, _status, payload = _decode_file_response(get_resp)
    meta = json.loads(payload[2:].decode("utf-8"))
    assert meta["name"]

    set_req = MetadataSetRequest(node_id=1, metadata_json=json.dumps({"name": "renamed kick"})).build(seq=2)
    set_resp = emu.handle_sysex(set_req)[0][0]
    _cmd, _seq, status, _payload = _decode_file_response(set_resp)
    assert status == 0

    get_req2 = MetadataGetRequest(node_id=1, page=0).build(seq=3)
    get_resp2 = emu.handle_sysex(get_req2)[0][0]
    _cmd, _seq, _status, payload2 = _decode_file_response(get_resp2)
    meta2 = json.loads(payload2[2:].decode("utf-8"))
    assert meta2["name"] == "renamed kick"


def test_emulator_upload_download_delete_roundtrip():
    emu = EP133Emulator()
    slot = 900
    pcm = bytes((i % 256 for i in range(DOWNLOAD_CHUNK_SIZE + 111)))

    init_req = UploadInitRequest(
        slot=slot,
        file_size=len(pcm),
        name="enc-test",
        metadata_json=json.dumps({"name": "enc-test", "channels": 1, "samplerate": 46875}),
    ).build(seq=10)
    init_resp = emu.handle_sysex(init_req)[0][0]
    _cmd, _seq, status, _payload = _decode_file_response(init_resp)
    assert status == 0

    chunk_req = UploadChunkRequest(chunk_index=0, data=pcm).build(seq=11)
    chunk_resp = emu.handle_sysex(chunk_req)[0][0]
    _cmd, _seq, status, _payload = _decode_file_response(chunk_resp)
    assert status == 0

    end_req = UploadEndRequest(chunk_index=1).build(seq=12)
    end_resp = emu.handle_sysex(end_req)[0][0]
    _cmd, _seq, status, _payload = _decode_file_response(end_resp)
    assert status == 0

    verify_req = UploadVerifyRequest(slot=slot).build(seq=13)
    verify_resp = emu.handle_sysex(verify_req)[0][0]
    _cmd, _seq, status, _payload = _decode_file_response(verify_resp)
    assert status == 0

    dl_init_req = DownloadInitRequest(slot=slot).build(seq=14)
    dl_init_resp = emu.handle_sysex(dl_init_req)[0][0]
    _cmd, _seq, status, payload = _decode_file_response(dl_init_resp)
    assert status == 0
    assert _extract_size_from_download_init(payload) == len(pcm)

    page0_req = DownloadChunkRequest(page=0).build(seq=15)
    page0_resp = emu.handle_sysex(page0_req)[0][0]
    _cmd, _seq, status, payload0 = _decode_file_response(page0_resp)
    assert status == 0
    p0, _ = U14LE.decode(payload0[:2])
    assert int(p0.to_python()) == 0
    assert payload0[2 : 2 + DOWNLOAD_CHUNK_SIZE] == pcm[:DOWNLOAD_CHUNK_SIZE]

    page1_req = DownloadChunkRequest(page=1).build(seq=16)
    page1_resp = emu.handle_sysex(page1_req)[0][0]
    _cmd, _seq, status, payload1 = _decode_file_response(page1_resp)
    assert status == 0
    p1, _ = U14LE.decode(payload1[:2])
    assert int(p1.to_python()) == 1
    assert payload1[2:] == pcm[DOWNLOAD_CHUNK_SIZE:]

    del_req = DeleteRequest(slot=slot).build(seq=17)
    del_resp = emu.handle_sysex(del_req)[0][0]
    _cmd, _seq, status, _payload = _decode_file_response(del_resp)
    assert status == 0

    dl_init_req2 = DownloadInitRequest(slot=slot).build(seq=18)
    dl_init_resp2 = emu.handle_sysex(dl_init_req2)[0][0]
    _cmd, _seq, status, _payload = _decode_file_response(dl_init_resp2)
    assert status != 0
