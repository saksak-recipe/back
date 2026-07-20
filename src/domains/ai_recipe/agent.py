from __future__ import annotations

from typing import TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from core.config import settings
from domains.ai_recipe.schemas import (
    AiRecipeCacheRecord,
    AiRecipeCandidate,
    AiRecipeCandidateList,
    AiRecipeDetailPayload,
)

TOP_K = 5
LLM_TIMEOUT_SECONDS = 20

T = TypeVar("T", bound=BaseModel)


class AgentFailedError(Exception):
    """에이전트가 유효한 결과를 만들지 못함."""


LIST_SYSTEM = (
    "You are a Korean home-cooking assistant. "
    f"Propose exactly {TOP_K} everyday Korean home-cooking recipes "
    "the user can mostly cook with fridge ingredients. "
    "Prefer using owned ingredients; missing staples are OK in small amounts. "
    "Vary recipes across requests even when ingredients stay the same."
)

DETAIL_SYSTEM = (
    "You are a Korean home-cooking assistant. "
    "Expand the given recipe summary into concrete ingredient amounts, "
    "ordered cooking steps, and optional tips."
)


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

    def run_list(self, owned_names: list[str]) -> list[AiRecipeCandidate]:
        result = self._invoke_structured(
            schema=AiRecipeCandidateList,
            system=LIST_SYSTEM,
            user=(
                f"Fridge ingredients: {', '.join(owned_names)}\n"
                f"Return exactly {TOP_K} distinct recipes."
            ),
        )
        if len(result.recipes) != TOP_K:
            raise AgentFailedError(
                f"agent did not propose {TOP_K} recipe candidates"
            )
        return result.recipes

    def run_detail(
        self,
        owned_names: list[str],
        summary: AiRecipeCacheRecord,
    ) -> dict[str, object]:
        _ = owned_names
        result = self._invoke_structured(
            schema=AiRecipeDetailPayload,
            system=DETAIL_SYSTEM,
            user=(
                f"Recipe: {summary.recipe_name}\n"
                f"Ingredients: {', '.join(summary.recipe_ingredients)}\n"
                f"Difficulty: {summary.recipe_difficulty}\n"
                f"Time: {summary.time}\n"
                "Provide amounts, ordered steps, and optional tips."
            ),
        )
        if not result.ingredients or not result.steps:
            raise AgentFailedError("agent did not expand recipe detail")
        return {
            "ingredients": result.ingredients,
            "steps": result.steps,
            "tips": result.tips,
        }

    def _invoke_structured(self, *, schema: type[T], system: str, user: str) -> T:
        try:
            structured = self._llm.with_structured_output(schema)
            raw = structured.invoke(
                [
                    SystemMessage(content=system),
                    HumanMessage(content=user),
                ]
            )
        except Exception as exc:
            raise AgentFailedError("recipe agent model invocation failed") from exc

        if isinstance(raw, schema):
            return raw
        try:
            return schema.model_validate(raw)
        except Exception as exc:
            raise AgentFailedError(
                "recipe agent returned invalid structured output"
            ) from exc
