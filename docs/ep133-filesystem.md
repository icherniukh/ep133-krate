# EP-133 KO-II: Slot IDs vs Node IDs

## Overview

There are two different addressing systems used in the EP-133 KO-II SysEx protocol: **Slot IDs** (001-999) and **Filesystem Node IDs** (e.g., 1000, 2000, 3101...). The confusion typically arises because both specify locations or objects on the device, but they apply to entirely different conceptual layers.

## Slot IDs (1-999)

*   **Used for:** Actual sample/audio data locations in the `ko2.py` utilities (`ko2.py info <slot>`, `ko2.py put <file> <slot>`, `ko2.py get <slot>`).
*   **Format:** 1 to 999.
*   **Description:** This represents the flat list of 999 individual sound slots on the device. When you upload a completely new sound, you place it into a specific slot ID (e.g., slot 10). Sound slot numbers are global across all projects.

## Node IDs (e.g., 1000, 2000, 3101...)

*   **Used for:** The EP-133 internal filesystem directory and file structure, particularly representing pads, projects, groups, and folders.
*   **Format:** Numeric IDs based on a formula.
*   **Description:** Node IDs point to specific organizational locations or folders in the device's internal filesystem. For instance:
    *   **Node 1000** is the `/sounds/` directory. When uploading raw files via `PUT`, the files are placed in this directory (the parent node is 1000).
    *   **Pad assignments** use specific node IDs to tie a physical pad to a sound slot.
    *   Node IDs encode the `Project`, `Group/Bank (A/B/C/D)`, and `Pad (1-12)`.

### How Node IDs map to Pads

According to the [rcy Python library](abrilstudios/rcy) (`src/python/ep133/pad_mapping.py`), the EP-133 has a quirky mapping for assigning sounds to physical pads.

Physical pads are numbered bottom-to-top (1-3 on bottom row), but the filesystem stores them top-to-bottom (files 01-03 on top row).

**Formula for a Pad Node ID:**
`node_id = 2000 + (project_num * 1000) + 100 + group_offset + file_num_mapped_from_pad`

Where:
*   `project_num`: 1 to 9
*   `group_offset`: A=100, B=200, C=300, D=400
*   `file_num_mapped_from_pad`: Pad 1 (bottom left) maps to file 10. Pad 12 (top right) maps to file 3.

**Example: Assigning a sound to Project 1, Bank A, Pad 1**
1. Base offset: `2000`
2. Project 1: `+ (1 * 1000) = 3000`
3. Group/Pad base: `+ 100 = 3100`
4. Bank A: `+ 100 = 3200`
5. Pad 1 maps to file 10: `+ 10 = 3210`

The Node ID `3210` represents Project 1, Bank A, Pad 1. 
To assign a sample to this pad, you would set the metadata of Node ID `3210` to point to a specific **Slot ID** (e.g., slot `10`).

## Conclusion

*   **Slot = Audio Data Location.** If you want to upload a `.wav` file, you put it in a **Slot ID** (1-999).
*   **Node = Filesystem/Pad Location.** If you want to assign that uploaded audio to a specific pad, or list folders, you address the **Node ID**. When assigning a sound to a pad, the Node ID's metadata (`sym` property) references the Slot ID.
