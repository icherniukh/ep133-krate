import sys
import cli.cmd_slots
from ko2_display import View
from types import SimpleNamespace
from ko2_client import SlotEmptyError

class FakeClient:
    def __init__(self, sounds, log):
        self._sounds = sounds
        self._log = log

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def list_sounds(self):
        return self._sounds

    def info(self, slot, include_size=False, node_entry=None):
        if slot not in self._sounds:
            raise SlotEmptyError(f"slot {slot} empty")
        e = self._sounds[slot]
        return SimpleNamespace(
            slot=slot,
            name=e.get("name", f"slot{slot:03d}.pcm"),
            size_bytes=int(e.get("size", 0)),
            samplerate=46875,
            channels=1,
            sym="",
            format="s16",
            channels_known=True,
        )

    def get(self, slot, path):
        if slot not in self._sounds:
            raise SlotEmptyError(f"slot {slot} empty")
        if path is not None:
            path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
        self._log.append(("get", slot))
        return path

    def put(self, path, slot, name=None, progress=False, pitch=0.0):
        self._log.append(("put", slot, name))

    def delete(self, slot):
        self._log.append(("delete", slot))


class MockView(View):
    def step(self, m): pass
    def success(self, m): print("SUCCESS:", m)
    def error(self, m): print("ERROR CAUGHT:", m)
    def info(self, m): pass
    def progress(self, c, t, m=""): pass
    def section(self, m): pass
    def kv(self, k, v): pass

def test():
    sounds = {1: {"name": "001.pcm", "node_id": 1, "size": 100}}
    log = []
    client = FakeClient(sounds, log)

    class Args:
        device = None
        src = 1
        dst = 2
        raw = True
        yes = True

    cli.cmd_slots.EP133Client = lambda *a, **k: client
    import core.ops
    core.ops.backup_copy = lambda *a, **k: None

    rc = cli.cmd_slots.cmd_move(Args(), MockView())
    print("rc =", rc)

if __name__ == "__main__":
    test()
