from __future__ import annotations

from datetime import date
from typing import Protocol

from domains.ingredient.service import compute_status
from domains.ingredient_matching.matching import names_match


class _HasNameAndExpiry(Protocol):
    ingredient_name: str
    expiration_date: date | None


def urgent_names(
    ingredients: list[_HasNameAndExpiry],
    today: date | None = None,
) -> list[str]:
    today = today or date.today()
    names: list[str] = []
    seen: set[str] = set()
    for item in ingredients:
        status = compute_status(item.expiration_date, today)
        if status not in ("expired", "soon"):
            continue
        key = item.ingredient_name.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(item.ingredient_name)
    return names


def count_urgent_owned(owned_ingredients: list[str], urgent: list[str]) -> int:
    return sum(
        1
        for owned in owned_ingredients
        if any(names_match(owned, u) for u in urgent)
    )
