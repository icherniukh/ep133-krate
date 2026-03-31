import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

class LocalTab(toga.Box):
    def __init__(self, app):
        super().__init__(style=Pack(direction=COLUMN, flex=1, padding=8))
        self.app = app
        
        # Header / Import Button
        self.btn_import = toga.Button(
            "+ Import from iOS Files", 
            on_press=self.on_import_files,
            style=Pack(padding_bottom=16, font_weight="bold")
        )
        self.add(self.btn_import)
        
        # File List
        self.file_list = toga.DetailedList(
            data=[
                {"title": "imported_kick.wav", "subtitle": "Local • 42KB", "icon": None},
                {"title": "voice_memo_1.m4a", "subtitle": "Local • Needs Conversion", "icon": None},
            ],
            on_select=self.on_file_selected,
            style=Pack(flex=1)
        )
        self.add(self.file_list)

    def on_import_files(self, widget):
        print("Trigger iOS Document Picker")
        
    def on_file_selected(self, widget, row):
        if row:
            print(f"Selected local file: {row.title}")
