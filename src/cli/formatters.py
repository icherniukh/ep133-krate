def short_text(text: str, width: int) -> str:
    if text is None:
        text = ""
    text = str(text)
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."

def sanitize_field(text: str) -> str:
    if text is None:
        return ""
    return str(text).replace("\t", " ").replace("\n", " ").replace("\r", " ")

def format_bar(used: int, total: int, width: int = 28) -> str:
    if total <= 0:
        return ""
    ratio = min(1.0, max(0.0, used / total))
    filled = int(round(ratio * width))
    return "█" * filled + "░" * (width - filled)
