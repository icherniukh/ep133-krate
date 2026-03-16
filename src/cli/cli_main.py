import sys
import importlib

from core.client import find_device
from cli.display import View, JsonView, SilentView, TerminalView
from cli.parser import build_parser

from .cmd_slots import (
    cmd_ls,
    cmd_info,
    cmd_rename,
    cmd_delete,
    cmd_move,
    cmd_copy,
    cmd_squash,
    cmd_group,
)
from .cmd_transfer import cmd_get, cmd_put
from .cmd_system import cmd_status, cmd_audit, cmd_fs_ls
from .cmd_audio import (
    cmd_optimize,
    cmd_optimize_all,
    cmd_audition,
    cmd_fingerprint,
)

def cmd_tui(args, view: View):
    try:
        module = importlib.import_module("tui.app")
        app_cls = getattr(module, "TUIApp")
    except ImportError:
        view.error("TUI dependencies are missing. Install `textual` and try again.")
        return 1
    except AttributeError:
        view.error("TUI module is installed but missing TUIApp.")
        return 1

    debug_arg = getattr(args, "debug", None)
    debug_enabled = debug_arg is not None
    debug_path = None if debug_arg in (None, "__AUTO__") else debug_arg

    app = app_cls(
        device_name=args.device,
        debug=debug_enabled,
        debug_log=debug_path,
        dialog_log=getattr(args, "dialog_log", None),
        alt_file_picker=getattr(args, "alt_file_picker", False),
    )
    app.run()
    return 0

def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    view: View = (
        JsonView() if args.json else SilentView() if args.quiet else TerminalView()
    )

    device = find_device()
    if not device and args.command != "tui":
        view.error("EP-133 not found. Connect via USB.")
        return 1
    args.device = device 

    commands = {
        "ls": cmd_ls,
        "info": cmd_info,
        "status": cmd_status,
        "audit": cmd_audit,
        "get": cmd_get,
        "put": cmd_put,
        "mv": cmd_move,
        "move": cmd_move,
        "cp": cmd_copy,
        "copy": cmd_copy,
        "delete": cmd_delete,
        "rm": cmd_delete,
        "remove": cmd_delete,
        "audition": cmd_audition,
        "play": cmd_audition,
        "optimize": cmd_optimize,
        "optimize-all": cmd_optimize_all,
        "group": cmd_group,
        "squash": cmd_squash,
        "fs-ls": cmd_fs_ls,
        "rename": cmd_rename,
        "fingerprint": cmd_fingerprint,
        "tui": cmd_tui,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args, view)

    return 0

if __name__ == "__main__":
    sys.exit(main())
