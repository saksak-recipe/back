from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import tool

from domains.ai_recipe.schemas import AiRecipeCandidate, AiRecipeIngredient, AiRecipeStep
from domains.rag.mapper import classify_ingredients

TOP_K = 5


@dataclass
class AgentSession:
    owned_names: list[str]
    candidates: list[AiRecipeCandidate] = field(default_factory=list)
    detail: dict[str, Any] | None = None


def build_tools(session: AgentSession):
    @tool
    def get_user_ingredients() -> str:
        """Return the user's fridge ingredient names as JSON list."""
        return json.dumps(session.owned_names, ensure_ascii=False)

    @tool
    def classify_owned_missing(recipe_ingredients: list[str]) -> str:
        """Classify recipe ingredients into owned vs missing using exact normalized match."""
        owned, missing = classify_ingredients(recipe_ingredients, session.owned_names)
        return json.dumps(
            {"owned_ingredients": owned, "missing_ingredients": missing},
            ensure_ascii=False,
        )

    @tool
    def propose_recipe_candidates(recipes: list[dict[str, Any]]) -> str:
        """Submit exactly 5 recipe candidates. Each needs recipe_name, recipe_ingredients, recipe_difficulty, time."""
        if len(recipes) != TOP_K:
            return f"error: must propose exactly {TOP_K} recipes, got {len(recipes)}"
        parsed: list[AiRecipeCandidate] = []
        for item in recipes:
            parsed.append(AiRecipeCandidate.model_validate(item))
        session.candidates = parsed
        return f"ok: stored {TOP_K} candidates"

    @tool
    def expand_recipe_detail(
        ingredients: list[dict[str, Any]],
        steps: list[dict[str, Any]],
        tips: list[str] | None = None,
    ) -> str:
        """Submit full recipe detail: ingredients[{name,amount}], steps[{order,description}], tips."""
        parsed_ingredients = [AiRecipeIngredient.model_validate(i) for i in ingredients]
        parsed_steps = [AiRecipeStep.model_validate(s) for s in steps]
        session.detail = {
            "ingredients": parsed_ingredients,
            "steps": parsed_steps,
            "tips": tips or [],
        }
        return "ok: detail stored"

    return [
        get_user_ingredients,
        classify_owned_missing,
        propose_recipe_candidates,
        expand_recipe_detail,
    ]
