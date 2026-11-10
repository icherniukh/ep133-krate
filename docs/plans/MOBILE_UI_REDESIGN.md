# Krate Mobile UI Architecture: "The Staging Area"

This document defines the layout, widget mapping, and foundational Toga code for the Krate iOS application.

## 1. Visual Wireframes

### Main Screen (Device Tab)
```text
+---------------------------------------+
|  Krate                        [Tools] |  <-- Navigation Bar (toga.Command)
+---------------------------------------+
|  [========= Memory: 64% =========]    |  <-- toga.ProgressBar
|  24MB Free  |  12MB Stereo Wasted     |  <-- toga.Label (row)
+---------------------------------------+
|  1  | Kick Main            | 0.4s     |  <-- toga.DetailedList (Row)
|     | 45KB • 46kHz         |          |      Title: "1  | Kick Main"
+---------------------------------------+      Subtitle: "45KB • 46kHz • 0.4s"
|  2  | Snare Alt         ⚠️ | 0.2s     |      Icon: Warning if stereo
|     | 80KB • 48kHz (St)    |          |
+---------------------------------------+
|  3  | Hat Closed           | 0.1s     |
|     | 12KB • 46kHz         |          |
+---------------------------------------+
| ...                                   |
+---------------------------------------+
| [ *Device (999)* ]   [  Local (12)  ] |  <-- toga.OptionContainer (Tab Bar)
+---------------------------------------+
```

### The Inspector (Bottom Sheet / Detail View)
```text
+---------------------------------------+
|  < Back     2 • Snare Alt             |
+---------------------------------------+
|                                       |
|  [WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW]   |  <-- toga.Canvas (Waveform render)
|  [WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW]   |
|                                       |
+---------------------------------------+
|            [ ▶ AUDITION ]             |  <-- toga.Button (large, accent color)
+---------------------------------------+
|  [ Rename ]  [ Optimize ]  [ Delete ] |  <-- toga.Box (ROW)
|                                       |
|  [      Pull to Local Inbox       ]   |  <-- toga.Button (full width)
+---------------------------------------+
```

## 2. Toga View Hierarchy & Widget Mapping

*   **`KrateApp(toga.App)`**
    *   Main Content: `toga.OptionContainer` (Tab bar)
    *   **Tab 1: `DeviceTab`** (Inherits `toga.Box`, direction `COLUMN`)
        *   `HeaderBox` (`toga.Box`, direction `COLUMN`)
            *   `toga.ProgressBar` (Memory usage)
            *   `toga.Label` (Memory stats)
        *   `toga.DetailedList` (Slot list)
            *   `on_select`: Pushes `InspectorView` or slides up custom Box.
    *   **Tab 2: `LocalTab`** (Inherits `toga.Box`, direction `COLUMN`)
        *   `toga.Button` ("+ Import from iOS Files")
        *   `toga.DetailedList` (Local inbox files)

## 3. Foundational Toga Code (Skeletons)

This code is designed to be copied into `src/mobile/screens/` and `src/mobile/app.py` when you are ready.

### `app.py` (Main Tab Bar Setup)
```python
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

class KrateApp(toga.App):
    def startup(self):
        # The main Tab Bar
        self.tabs = toga.OptionContainer()
        
        # Initialize Tabs
        self.device_tab = DeviceTab(self)
        self.local_tab = LocalTab(self)
        
        self.tabs.add("Device", self.device_tab)
        self.tabs.add("Local", self.local_tab)
        
        # Tools Menu (Top Right)
        tools_cmd = toga.Command(
            self.action_open_tools,
            text="Tools",
            tooltip="Bulk operations and settings"
        )
        self.commands.add(tools_cmd)

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = self.tabs
        self.main_window.show()

    def action_open_tools(self, widget):
        pass # Open squash/optimize-all modal
```

### `screens/device_tab.py`
```python
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
            # Here you would typically push a new view to a NavigationContainer 
            # or slide up a custom "Inspector" Box.
            print(f"Opening Inspector for {row.title}")
            # widget.selection = None # Deselect after tap
```

### `screens/inspector.py`
```python
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

class InspectorView(toga.Box):
    """
    Can be used as a pushed screen in a NavigationContainer 
    or a floating modal bottom-sheet.
    """
    def __init__(self, slot_data):
        super().__init__(style=Pack(direction=COLUMN, padding=16, flex=1))
        
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
```
