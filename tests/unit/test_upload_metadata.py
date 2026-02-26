from ko2_client import EP133Client


def test_build_upload_metadata_includes_loop_fields_when_small():
    meta = EP133Client.build_upload_metadata(channels=2, samplerate=44100, frames=1000)

    assert meta["channels"] == 2
    assert meta["samplerate"] == 44100
    assert meta["sound.loopstart"] == 0
    assert meta["sound.loopend"] == 999
    assert meta["sound.rootnote"] == 60
    assert meta["sound.amplitude"] == 100
    assert meta["sound.playmode"] == "oneshot"


def test_build_upload_metadata_omits_loop_fields_when_large():
    meta = EP133Client.build_upload_metadata(
        channels=1, samplerate=46875, frames=0x1FFFF + 2
    )

    assert meta["channels"] == 1
    assert meta["samplerate"] == 46875
    assert "sound.loopstart" not in meta
    assert "sound.loopend" not in meta
    # sound.rootnote is always included (not tied to loop range)
    assert meta["sound.rootnote"] == 60
    assert meta["sound.amplitude"] == 100
