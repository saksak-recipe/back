from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from core.config import settings
from domains.ai_recipe.schemas import AiRecipeCacheRecord, AiRecipeCandidate
from domains.ai_recipe.tools import TOP_K, AgentSession, build_tools

MAX_TOOL_LOOPS = 8


class AgentFailedError(Exception):
    """에이전트가 유효한 결과를 만들지 못함."""


LIST_SYSTEM = (
    "You are a Korean home-cooking assistant. "
    f"Use tools to inspect ingredients and propose exactly {TOP_K} recipes "
    "the user can mostly cook with fridge items. "
    "Always call propose_recipe_candidates with exactly "
    f"{TOP_K} recipes before finishing."
)

DETAIL_SYSTEM = (
    "You are a Korean home-cooking assistant. "
    "Expand the given recipe summary into concrete ingredient amounts, "
    "ordered cooking steps, and optional tips. "
    "Always call expand_recipe_detail before finishing."
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
            timeout=60,
        )

    def run_list(self, owned_names: list[str]) -> list[AiRecipeCandidate]:
        session = AgentSession(owned_names=owned_names)
        self._run(
            system=LIST_SYSTEM,
            user=(
                "Propose recipes for these fridge ingredients. "
                "Call get_user_ingredients first if needed."
            ),
            tools=build_tools(session),
        )
        if len(session.candidates) != TOP_K:
            raise AgentFailedError(
                f"agent did not propose {TOP_K} recipe candidates"
            )
        return session.candidates

    def run_detail(
        self,
        owned_names: list[str],
        summary: AiRecipeCacheRecord,
    ) -> dict[str, Any]:
        session = AgentSession(owned_names=owned_names)
        self._run(
            system=DETAIL_SYSTEM,
            user=(
                f"Recipe: {summary.recipe_name}\n"
                f"Ingredients: {', '.join(summary.recipe_ingredients)}\n"
                f"Difficulty: {summary.recipe_difficulty}\n"
                f"Time: {summary.time}\n"
                "Call expand_recipe_detail with amounts, steps, tips."
            ),
            tools=build_tools(session),
        )
        if session.detail is None:
            raise AgentFailedError("agent did not expand recipe detail")
        return session.detail

    def _run(self, *, system: str, user: str, tools: list[BaseTool]) -> None:
        tool_map = {tool.name: tool for tool in tools}
        try:
            llm = self._llm.bind_tools(tools)
        except Exception as exc:
            raise AgentFailedError("failed to bind recipe agent tools") from exc

        messages: list[Any] = [
            SystemMessage(content=system),
            HumanMessage(content=user),
        ]
        for _ in range(MAX_TOOL_LOOPS):
            try:
                ai: AIMessage = llm.invoke(messages)
            except Exception as exc:
                raise AgentFailedError("recipe agent model invocation failed") from exc

            messages.append(ai)
            if not ai.tool_calls:
                return

            for call in ai.tool_calls:
                name = call["name"]
                tool = tool_map.get(name)
                output = (
                    f"error: unknown tool {name}"
                    if tool is None
                    else tool.invoke(call.get("args") or {})
                )
                messages.append(
                    ToolMessage(content=str(output), tool_call_id=call["id"])
                )
