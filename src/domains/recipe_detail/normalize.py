import re


def normalize_text(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", value.strip())
    return collapsed.casefold()
