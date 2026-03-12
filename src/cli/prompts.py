def confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        resp = input(f"{prompt} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return resp in ("y", "yes")
