from __future__ import annotations

import json
import re
from typing import Any

_SECTION_KEYS = ("ingredients", "steps", "tips")


class PartialDetailParser:
    """Accumulate streamed JSON text; emit each top-level array once when closed."""

    def __init__(self) -> None:
        self._buf = ""
        self._emitted: set[str] = set()

    def feed(self, chunk: str) -> list[tuple[str, Any]]:
        if chunk:
            self._buf += chunk
        return self._emit_ready(require_next_key=True)

    def finish(self) -> list[tuple[str, Any]]:
        return self._emit_ready(require_next_key=False)

    def _emit_ready(self, *, require_next_key: bool) -> list[tuple[str, Any]]:
        events: list[tuple[str, Any]] = []
        for key in _SECTION_KEYS:
            if key in self._emitted:
                continue
            key_index = _SECTION_KEYS.index(key)
            if any(pred not in self._emitted for pred in _SECTION_KEYS[:key_index]):
                continue
            value = self._try_extract_array(key, require_next_key=require_next_key)
            if value is not None:
                self._emitted.add(key)
                events.append((key, value))
        return events

    def _try_extract_array(
        self, key: str, *, require_next_key: bool
    ) -> list[Any] | None:
        # Find `"key":` then parse balanced [...] from that position.
        match = re.search(rf'"{key}"\s*:', self._buf)
        if not match:
            return None
        if require_next_key:
            key_index = _SECTION_KEYS.index(key)
            if key_index + 1 < len(_SECTION_KEYS):
                next_key = _SECTION_KEYS[key_index + 1]
                if not re.search(rf'"{next_key}"\s*:', self._buf):
                    return None
        start = self._buf.find("[", match.end())
        if start < 0:
            return None
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(self._buf)):
            ch = self._buf[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(self._buf[start : i + 1])
                    except json.JSONDecodeError:
                        return None
                    if isinstance(parsed, list):
                        return parsed
                    return None
        return None
