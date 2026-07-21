from __future__ import annotations

from domains.ingredient_matching.synonyms import SYNONYM_GROUPS

_MIN_SUBSTRING_LEN = 2
_alias_to_canonical: dict[str, str] | None = None


def normalize_name(name: str) -> str:
    return name.strip().casefold().replace(" ", "")


def _alias_map() -> dict[str, str]:
    global _alias_to_canonical
    if _alias_to_canonical is None:
        mapping: dict[str, str] = {}
        for canonical, aliases in SYNONYM_GROUPS.items():
            c = normalize_name(canonical)
            mapping[c] = c
            for alias in aliases:
                a = normalize_name(alias)
                if a:
                    mapping[a] = c
        _alias_to_canonical = mapping
    return _alias_to_canonical


def canonical_of(name: str) -> str:
    n = normalize_name(name)
    if not n:
        return ""
    return _alias_map().get(n, n)


def names_match(a: str, b: str) -> bool:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if canonical_of(a) == canonical_of(b):
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(shorter) < _MIN_SUBSTRING_LEN:
        return False
    return shorter in longer


def classify_ingredients(
    recipe_ingredients: list[str], owned_names: list[str]
) -> tuple[list[str], list[str]]:
    owned_list = [n for n in owned_names if normalize_name(n)]
    owned: list[str] = []
    missing: list[str] = []
    for name in recipe_ingredients:
        if any(names_match(name, o) for o in owned_list):
            owned.append(name)
        else:
            missing.append(name)
    return owned, missing
