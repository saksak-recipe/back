from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.config import settings
from domains.ai_recipe.schemas import (
    AiRecipeCacheRecord,
    AiRecipeCandidate,
    AiRecipeCandidateList,
    AiRecipeDetailPayload,
)

TOP_K = 5
LLM_TIMEOUT_SECONDS = 25


class AgentFailedError(Exception):
    """에이전트가 유효한 결과를 만들지 못함."""


LIST_SYSTEM = (
    "You are a Korean home-cooking assistant. "
    f"Propose exactly {TOP_K} recipes "
    "the user can mostly cook with fridge items. "
    "Prefer using urgent/expiring ingredients when listed. "
    "Return only the structured recipe list."
)

DETAIL_SYSTEM = (
    "You are a Korean home-cooking assistant. "
    "Expand the given recipe summary into concrete ingredient amounts, "
    "ordered cooking steps, and optional tips. "
    "Return only the structured recipe detail."
)


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end < start:
        raise ValueError("no json object")
    return text[start : end + 1]


class AiRecipeAgent:
    def __init__(
        self,
        llm: BaseChatModel | None = None,
        model_name: str | None = None,
    ) -> None:
        self._model_name = model_name or settings.AI_RECIPE_MODEL
        self._llm = llm or ChatOpenAI(
            model=self._model_name,
            api_key=settings.OPENAI_API_KEY.get_secret_value(),
            timeout=LLM_TIMEOUT_SECONDS,
        )

    def run_list(
        self,
        owned_names: list[str],
        urgent_names: list[str] | None = None,
    ) -> list[AiRecipeCandidate]:
        urgent = urgent_names or []
        urgent_line = (
            f"우선 소진(유통기한 임박/지남): {', '.join(urgent)}\n"
            if urgent
            else ""
        )
        try:
            structured = self._llm.with_structured_output(AiRecipeCandidateList)
            result = structured.invoke(
                [
                    SystemMessage(content=LIST_SYSTEM),
                    HumanMessage(
                        content=(
                            f"{urgent_line}"
                            f"냉장고 재료: {', '.join(owned_names)}\n"
                            f"정확히 {TOP_K}개 레시피를 제안하세요."
                        )
                    ),
                ]
            )
        except Exception as exc:
            raise AgentFailedError("recipe list structured invoke failed") from exc

        recipes = list(result.recipes)
        if len(recipes) != TOP_K:
            raise AgentFailedError(
                f"expected {TOP_K} recipes, got {len(recipes)}"
            )
        return recipes

    def run_detail(
        self,
        owned_names: list[str],
        summary: AiRecipeCacheRecord,
    ) -> dict[str, Any]:
        try:
            structured = self._llm.with_structured_output(AiRecipeDetailPayload)
            result = structured.invoke(
                [
                    SystemMessage(content=DETAIL_SYSTEM),
                    HumanMessage(
                        content=(
                            f"Recipe: {summary.recipe_name}\n"
                            f"Ingredients: {', '.join(summary.recipe_ingredients)}\n"
                            f"Owned fridge ingredients: {', '.join(owned_names)}\n"
                            f"Difficulty: {summary.recipe_difficulty}\n"
                            f"Time: {summary.time}\n"
                            "Provide ingredient amounts, ordered steps, and tips."
                        )
                    ),
                ]
            )
        except Exception as exc:
            raise AgentFailedError("recipe detail structured invoke failed") from exc

        return {
            "ingredients": result.ingredients,
            "steps": result.steps,
            "tips": result.tips,
        }

    def stream_detail(
        self,
        owned_names: list[str],
        summary: AiRecipeCacheRecord,
    ):
        from domains.ai_recipe.partial_json import PartialDetailParser

        messages = [
            SystemMessage(content=DETAIL_SYSTEM),
            HumanMessage(
                content=(
                    f"Recipe: {summary.recipe_name}\n"
                    f"Ingredients: {', '.join(summary.recipe_ingredients)}\n"
                    f"Owned fridge ingredients: {', '.join(owned_names)}\n"
                    f"Difficulty: {summary.recipe_difficulty}\n"
                    f"Time: {summary.time}\n"
                    "Provide ingredient amounts, ordered steps, and tips.\n"
                    "Respond with a single JSON object with keys "
                    "ingredients, steps, tips."
                )
            ),
        ]
        parser = PartialDetailParser()
        buf = ""
        try:
            for chunk in self._llm.stream(messages):
                text = chunk.content if isinstance(chunk.content, str) else ""
                if not text:
                    continue
                buf += text
                for event in parser.feed(text):
                    yield event
            for event in parser.finish():
                yield event
            json_text = _extract_json_object(buf) if "```" in buf else buf
            payload = AiRecipeDetailPayload.model_validate_json(json_text)
        except Exception as exc:
            raise AgentFailedError("recipe detail stream failed") from exc

        yield (
            "complete",
            {
                "ingredients": payload.ingredients,
                "steps": payload.steps,
                "tips": payload.tips,
            },
        )
