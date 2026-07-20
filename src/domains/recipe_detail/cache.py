import hashlib
import time
from dataclasses import dataclass

from domains.recipe_detail.normalize import normalize_text
from domains.recipe_detail.schemas import RecipeDetailResponse


def cache_key(board_name: str, author_name: str) -> str:
    raw = f"{normalize_text(board_name)}|{normalize_text(author_name)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class _Entry:
    value: RecipeDetailResponse
    expires_at: float


class RecipeDetailCache:
    def __init__(self, ttl_seconds: int = 86400) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, _Entry] = {}

    def get(self, key: str) -> RecipeDetailResponse | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() >= entry.expires_at:
            self._store.pop(key, None)
            return None
        return entry.value.model_copy(update={"cached": True})

    def set(self, key: str, value: RecipeDetailResponse) -> None:
        stored = value.model_copy(update={"cached": False})
        self._store[key] = _Entry(
            value=stored,
            expires_at=time.monotonic() + self._ttl,
        )
