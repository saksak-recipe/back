from langchain_core.documents import Document

from domains.ingredient_matching.matching import (
    classify_ingredients,
    normalize_name,
)
from domains.rag.schemas import RecipeRecommendation


def build_ingredient_query(names: list[str]) -> str:
    return "parsed_ingredients: " + ", ".join(names)


def is_recipe_name_in_ingredients(
    recipe_name: str, ingredient_names: list[str]
) -> bool:
    """레시피명이 보유 식재료와 같으면 재료명 매칭으로 본다."""
    normalized_recipe = normalize_name(recipe_name)
    if not normalized_recipe:
        return False
    return normalized_recipe in {normalize_name(n) for n in ingredient_names}


def parse_page_content(page_content: str) -> tuple[str, str]:
    recipe_name = ""
    parsed_ingredients = ""
    for line in page_content.splitlines():
        if line.startswith("recipe_name:"):
            recipe_name = line.removeprefix("recipe_name:").strip()
        elif line.startswith("parsed_ingredients:"):
            parsed_ingredients = line.removeprefix("parsed_ingredients:").strip()
    return recipe_name, parsed_ingredients


def split_ingredient_names(raw: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        name = part.strip()
        if not name:
            continue
        key = normalize_name(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def map_document_to_recipe(
    doc: Document,
    score: float,
    owned_names: list[str] | None = None,
) -> RecipeRecommendation | None:
    content_name, parsed_ingredients = parse_page_content(doc.page_content)
    meta = doc.metadata or {}
    # 신규 적재: recipe_name은 metadata. 구 적재: page_content에 포함.
    recipe_name = str(meta.get("recipe_name", "") or "").strip() or content_name
    if not recipe_name:
        return None

    ingredients = split_ingredient_names(parsed_ingredients)
    owned, missing = classify_ingredients(ingredients, owned_names or [])

    return RecipeRecommendation(
        recipe_name=recipe_name,
        owned_ingredients=owned,
        missing_ingredients=missing,
        board_name=str(meta.get("board_name", "") or ""),
        author_name=str(meta.get("author_name", "") or ""),
        recipe_difficulty=str(meta.get("recipe_difficulty", "") or ""),
        time=str(meta.get("time", "") or ""),
        score=float(score),
    )
