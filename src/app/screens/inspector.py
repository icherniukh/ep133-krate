import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

class InspectorView(toga.Box):
    """
    Detail view for a single slot or local file.
    """
    def __init__(self, slot_data=None):
        super().__init__(style=Pack(direction=COLUMN, padding=16, flex=1))
        self.slot_data = slot_data
        
        # Header
        title = slot_data.get("title", "Unknown") if slot_data else "Inspector"
        self.lbl_title = toga.Label(title, style=Pack(font_size=18, font_weight="bold", padding_bottom=16))
        self.add(self.lbl_title)

        # Waveform Canvas Placeholder
        self.waveform_canvas = toga.Canvas(style=Pack(height=150, padding_bottom=16))
        self.add(self.waveform_canvas)
        
        # Audition Button
        self.btn_audition = toga.Button(
            "▶ AUDITION", 
            style=Pack(padding_bottom=16, font_weight="bold")
        )
        self.add(self.btn_audition)
        
        # Quick Actions
        action_row = toga.Box(style=Pack(direction=ROW, padding_bottom=16))
        action_row.add(toga.Button("Rename", style=Pack(flex=1, padding_right=4)))
        action_row.add(toga.Button("Optimize", style=Pack(flex=1, padding_right=4)))
        action_row.add(toga.Button("Delete", style=Pack(flex=1)))
        self.add(action_row)
        
        # Pull to Local
        self.btn_pull = toga.Button("Pull to Local Inbox", style=Pack(flex=1))
        self.add(self.btn_pull)
