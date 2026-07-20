from langchain_core.documents import Document

from domains.rag.schemas import RecipeRecommendation


def build_ingredient_query(names: list[str]) -> str:
    return "parsed_ingredients: " + ", ".join(names)


def parse_page_content(page_content: str) -> tuple[str, str]:
    recipe_name = ""
    parsed_ingredients = ""
    for line in page_content.splitlines():
        if line.startswith("recipe_name:"):
            recipe_name = line.removeprefix("recipe_name:").strip()
        elif line.startswith("parsed_ingredients:"):
            parsed_ingredients = line.removeprefix("parsed_ingredients:").strip()
    return recipe_name, parsed_ingredients


def map_document_to_recipe(
    doc: Document, score: float
) -> RecipeRecommendation | None:
    recipe_name, parsed_ingredients = parse_page_content(doc.page_content)
    if not recipe_name:
        return None
    meta = doc.metadata or {}
    return RecipeRecommendation(
        recipe_name=recipe_name,
        parsed_ingredients=parsed_ingredients,
        board_name=str(meta.get("board_name", "") or ""),
        author_name=str(meta.get("author_name", "") or ""),
        recipe_difficulty=str(meta.get("recipe_difficulty", "") or ""),
        time=str(meta.get("time", "") or ""),
        score=float(score),
    )
