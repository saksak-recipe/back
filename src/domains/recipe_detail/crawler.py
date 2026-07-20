import json

from bs4 import BeautifulSoup

from domains.recipe_detail.matcher import SearchCandidate
from domains.recipe_detail.schemas import (
    RecipeDetailResponse,
    RecipeIngredient,
    RecipeStep,
)

BASE_URL = "https://www.10000recipe.com"
USER_AGENT = (
    "saksak-recipe-bot/1.0 (+https://github.com/local; personal non-commercial use)"
)


def parse_search_html(html: str) -> list[SearchCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchCandidate] = []

    for item in soup.select("li.common_sp_list_li"):
        link = item.select_one("a.common_sp_link[href]")
        if link is None:
            continue

        href = link.get("href")
        if not isinstance(href, str):
            continue

        recipe_id = href.rstrip("/").split("/")[-1]
        title = item.select_one(".common_sp_caption_tit")
        author = item.select_one(".common_sp_caption_rv_name b")
        results.append(
            SearchCandidate(
                recipe_id=recipe_id,
                title=title.get_text(strip=True) if title else "",
                author=author.get_text(strip=True) if author else "",
            )
        )

    return results


def _split_ingredient(raw: str) -> RecipeIngredient:
    parts = raw.strip().split()
    if len(parts) >= 2:
        return RecipeIngredient(name=parts[0], amount=" ".join(parts[1:]))
    return RecipeIngredient(name=raw.strip(), amount="")


def _load_recipe_ld(soup: BeautifulSoup) -> dict[str, object] | None:
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue

        candidates: list[object]
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict) and isinstance(data.get("@graph"), list):
            candidates = data["@graph"]
        else:
            candidates = [data]

        for item in candidates:
            if isinstance(item, dict) and item.get("@type") == "Recipe":
                return item

    return None


def parse_detail_html(html: str, recipe_id: str) -> RecipeDetailResponse:
    soup = BeautifulSoup(html, "html.parser")
    recipe = _load_recipe_ld(soup) or {}

    image = recipe.get("image")
    if isinstance(image, list) and image:
        first_image = image[0]
        main_image = (
            first_image
            if isinstance(first_image, str)
            else first_image.get("url")
            if isinstance(first_image, dict)
            else None
        )
    elif isinstance(image, str):
        main_image = image
    else:
        main_image = None

    raw_ingredients = recipe.get("recipeIngredient")
    ingredients = [
        _split_ingredient(raw)
        for raw in raw_ingredients
        if isinstance(raw, str)
    ] if isinstance(raw_ingredients, list) else []

    raw_steps = recipe.get("recipeInstructions")
    steps: list[RecipeStep] = []
    if isinstance(raw_steps, list):
        for order, step in enumerate(raw_steps, start=1):
            if isinstance(step, dict):
                image_url = step.get("image")
                if isinstance(image_url, list) and image_url:
                    image_url = image_url[0]
                steps.append(
                    RecipeStep(
                        order=order,
                        description=step.get("text")
                        if isinstance(step.get("text"), str)
                        else "",
                        image_url=image_url if isinstance(image_url, str) else None,
                    )
                )
            elif isinstance(step, str):
                steps.append(RecipeStep(order=order, description=step))

    tips = [
        text
        for tip in soup.select(".view_step .tip")
        if (text := tip.get_text(strip=True))
    ]
    if tips and steps:
        steps[0] = steps[0].model_copy(update={"tip": tips[0]})

    return RecipeDetailResponse(
        board_name="",
        author_name="",
        recipe_name=recipe.get("name") if isinstance(recipe.get("name"), str) else "",
        source_url=f"{BASE_URL}/recipe/{recipe_id}",
        main_image_url=main_image,
        ingredients=ingredients,
        steps=steps,
        tips=tips,
        cached=False,
    )
