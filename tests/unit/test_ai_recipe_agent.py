from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage

from domains.ai_recipe.agent import MAX_TOOL_LOOPS, AgentFailedError, AiRecipeAgent
from domains.ai_recipe.schemas import AiRecipeCacheRecord


def _five_recipes():
    return [
        {
            "recipe_name": f"요리{i}",
            "recipe_ingredients": ["계란", "밥"],
            "recipe_difficulty": "초급",
            "time": "10분",
        }
        for i in range(5)
    ]


def _summary() -> AiRecipeCacheRecord:
    return AiRecipeCacheRecord(
        recipe_id="11111111-1111-1111-1111-111111111111",
        recipe_name="계란볶음밥",
        recipe_ingredients=["계란", "밥"],
        owned_ingredients=["계란"],
        missing_ingredients=["밥"],
        recipe_difficulty="초급",
        time="15분",
    )


def test_run_list_uses_tools_and_returns_candidates():
    llm = MagicMock()
    llm.bind_tools.return_value = llm
    llm.invoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "propose_recipe_candidates",
                    "args": {"recipes": _five_recipes()},
                    "id": "call_1",
                }
            ],
        ),
        AIMessage(content="done"),
    ]

    candidates = AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").run_list(["계란"])

    assert len(candidates) == 5
    assert candidates[0].recipe_name == "요리0"


def test_run_list_recovers_after_invalid_tool_args():
    llm = MagicMock()
    llm.bind_tools.return_value = llm
    llm.invoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "propose_recipe_candidates",
                    "args": {"recipes": [{}, {}, {}, {}, {}]},
                    "id": "invalid_call",
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "propose_recipe_candidates",
                    "args": {"recipes": _five_recipes()},
                    "id": "valid_call",
                }
            ],
        ),
        AIMessage(content="done"),
    ]

    candidates = AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").run_list(["계란"])

    assert len(candidates) == 5
    retry_messages = llm.invoke.call_args_list[1].args[0]
    error_message = next(
        message
        for message in retry_messages
        if getattr(message, "tool_call_id", None) == "invalid_call"
    )
    assert str(error_message.content).startswith("error:")


def test_run_list_raises_when_no_candidates():
    llm = MagicMock()
    llm.bind_tools.return_value = llm
    llm.invoke.return_value = AIMessage(content="sorry")

    with pytest.raises(AgentFailedError):
        AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").run_list(["계란"])


def test_run_detail_expands():
    llm = MagicMock()
    llm.bind_tools.return_value = llm
    llm.invoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "expand_recipe_detail",
                    "args": {
                        "ingredients": [{"name": "계란", "amount": "2개"}],
                        "steps": [{"order": 1, "description": "볶는다"}],
                        "tips": ["약불"],
                    },
                    "id": "call_1",
                }
            ],
        ),
        AIMessage(content="done"),
    ]

    detail = AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").run_detail(
        ["계란"], _summary()
    )

    assert detail["tips"] == ["약불"]


def test_run_stops_after_max_tool_loops():
    llm = MagicMock()
    llm.bind_tools.return_value = llm
    llm.invoke.return_value = AIMessage(
        content="",
        tool_calls=[{"name": "get_user_ingredients", "args": {}, "id": "call_1"}],
    )

    with pytest.raises(AgentFailedError):
        AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").run_list(["계란"])

    assert llm.invoke.call_count == MAX_TOOL_LOOPS


def test_run_wraps_llm_error_as_cause():
    llm = MagicMock()
    llm.bind_tools.return_value = llm
    upstream_error = RuntimeError("openai unavailable")
    llm.invoke.side_effect = upstream_error

    with pytest.raises(AgentFailedError) as exc_info:
        AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").run_detail(
            ["계란"], _summary()
        )

    assert exc_info.value.__cause__ is upstream_error
