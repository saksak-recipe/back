import asyncio
import json

from bs4 import BeautifulSoup
import httpx

from core.exception.exceptions import ExternalServiceException
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


class RecipeCrawler:
    _semaphore = asyncio.Semaphore(3)

    async def search(self, query: str) -> list[SearchCandidate]:
        html = await self._get(
            f"{BASE_URL}/recipe/list.html",
            params={
                "q": query.strip(),
                "order": "accuracy",
                "lastcate": "order",
            },
        )
        try:
            return parse_search_html(html)
        except Exception as exc:
            raise ExternalServiceException("레시피 검색 결과를 파싱하지 못했어요") from exc

    async def fetch_detail(self, recipe_id: str) -> RecipeDetailResponse:
        html = await self._get(f"{BASE_URL}/recipe/{recipe_id}")
        try:
            detail = parse_detail_html(html, recipe_id)
            if not detail.recipe_name and not detail.ingredients and not detail.steps:
                raise ExternalServiceException("레시피 상세 정보가 비어 있어요")
            return detail
        except Exception as exc:
            raise ExternalServiceException("레시피 상세 정보를 파싱하지 못했어요") from exc

    async def _get(
        self,
        url: str,
        params: dict[str, str] | None = None,
    ) -> str:
        try:
            async with self._semaphore:
                async with httpx.AsyncClient(
                    timeout=10.0,
                    headers={"User-Agent": USER_AGENT},
                ) as client:
                    response = await client.get(url, params=params)
            if response.status_code != httpx.codes.OK:
                raise ExternalServiceException("레시피 사이트 요청에 실패했어요")
            return response.text
        except ExternalServiceException:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise ExternalServiceException("레시피 사이트 요청 중 오류가 발생했어요") from exc


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
            recipe_type = item.get("@type") if isinstance(item, dict) else None
            if recipe_type == "Recipe" or (
                isinstance(recipe_type, list) and "Recipe" in recipe_type
            ):
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
                steps.append(
                    RecipeStep(
                        order=order,
                        description=step.get("text")
                        if isinstance(step.get("text"), str)
                        else "",
                    )
                )
            elif isinstance(step, str):
                steps.append(RecipeStep(order=order, description=step))

    tips: list[str] = []
    seen: set[str] = set()
    for selector in (".view_step .tip", ".view_step_tip dd"):
        for tip in soup.select(selector):
            text = tip.get_text(strip=True)
            if not text or text in seen:
                continue
            seen.add(text)
            tips.append(text)

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
