from pathlib import Path

from core.client import EP133Client, SlotEmptyError, EP133Error
from cli.display import View
from cli.parser import validate_slot
from cli.prompts import confirm

def cmd_get(args, view: View):
    slot = validate_slot(args.slot)
    output = Path(args.output) if getattr(args, "output", None) else None

    if output and output.exists():
        if not confirm(f"File '{output}' already exists. Overwrite?", bool(getattr(args, "yes", False))):
            view.step("Cancelled")
            return 0

    with EP133Client(args.device) as client:
        try:
            view.step(f"Downloading slot {slot}...")
            result_path = client.get(slot, output)
            view.success(f"Downloaded to {result_path}")
        except SlotEmptyError:
            view.error(f"Slot {slot} is empty")
            return 1
        except EP133Error as e:
            view.error(f"Error: {e}")
            return 1

    return 0

def cmd_put(args, view: View):
    input_path = Path(args.file)

    if not input_path.exists():
        view.error(f"File not found: {input_path}")
        return 1

    with EP133Client(args.device) as client:
        try:
            name = getattr(args, "name", None)
            pitch = getattr(args, "pitch", 0.0)
            view.step(f"Uploading {input_path.name} → slot {args.slot}...")
            def _print_progress(curr, total):
                print(f"\r  Uploading... {curr/total*100:.1f}%", end="", flush=True)
            client.put(input_path, args.slot, name=name, progress_callback=_print_progress, pitch=pitch)
            print(" done")
            view.success(f"Uploaded to slot {args.slot}")
        except EP133Error as e:
            view.error(f"Error: {e}")
            return 1
        except ValueError as e:
            view.error(f"Invalid file: {e}")
            return 1

    return 0
