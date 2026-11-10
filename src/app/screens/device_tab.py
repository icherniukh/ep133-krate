import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

class DeviceTab(toga.Box):
    def __init__(self, app):
        super().__init__(style=Pack(direction=COLUMN, flex=1))
        self.app = app
        
        # --- 1. Memory Header ---
        self.header_box = toga.Box(style=Pack(direction=COLUMN, padding=8))
        self.memory_bar = toga.ProgressBar(max=100, value=64, style=Pack(padding_bottom=4))
        self.memory_labels = toga.Box(style=Pack(direction=ROW))
        self.memory_labels.add(toga.Label("24MB Free", style=Pack(flex=1, font_size=12)))
        self.memory_labels.add(toga.Label("12MB Stereo Wasted", style=Pack(font_size=12, color="red")))
        
        self.header_box.add(self.memory_bar)
        self.header_box.add(self.memory_labels)
        self.add(self.header_box)
        
        # --- 2. Slot List ---
        # DetailedList natively supports title, subtitle, and an icon. Perfect for iOS.
        self.slot_list = toga.DetailedList(
            data=[
                {"title": "1 | Kick Main", "subtitle": "45KB • 46kHz • 0.4s", "icon": None},
                {"title": "2 | Snare Alt", "subtitle": "80KB • 48kHz (St) • 0.2s", "icon": "⚠️"},
            ],
            on_select=self.on_slot_selected,
            style=Pack(flex=1)
        )
        self.add(self.slot_list)

    def on_slot_selected(self, widget, row):
        if row:
            print(f"Opening Inspector for {row.title}")
            # widget.selection = None # Deselect after tap
