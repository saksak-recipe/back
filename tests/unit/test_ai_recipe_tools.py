import json

from domains.ai_recipe.tools import AgentSession, build_tools


def _tool_map(session: AgentSession):
    return {t.name: t for t in build_tools(session)}


def test_get_user_ingredients():
    session = AgentSession(owned_names=["계란", "양파"])
    tools = _tool_map(session)
    result = tools["get_user_ingredients"].invoke({})
    assert json.loads(result) == ["계란", "양파"]


def test_propose_recipe_candidates_stores_five():
    session = AgentSession(owned_names=["계란"])
    tools = _tool_map(session)
    payload = {
        "recipes": [
            {
                "recipe_name": f"요리{i}",
                "recipe_ingredients": ["계란", "밥"],
                "recipe_difficulty": "초급",
                "time": "10분",
            }
            for i in range(5)
        ]
    }
    result = tools["propose_recipe_candidates"].invoke(payload)
    assert "ok" in result.lower() or "5" in result
    assert len(session.candidates) == 5
    assert session.candidates[0].recipe_name == "요리0"


def test_propose_rejects_wrong_count():
    session = AgentSession(owned_names=["계란"])
    tools = _tool_map(session)
    result = tools["propose_recipe_candidates"].invoke(
        {"recipes": [{"recipe_name": "하나만", "recipe_ingredients": ["계란"]}]}
    )
    assert "5" in result  # error mentioning need 5
    assert session.candidates == []


def test_classify_owned_missing():
    session = AgentSession(owned_names=["계란", "양파"])
    tools = _tool_map(session)
    result = json.loads(
        tools["classify_owned_missing"].invoke(
            {"recipe_ingredients": ["계란", "밥", "양파"]}
        )
    )
    assert result["owned_ingredients"] == ["계란", "양파"]
    assert result["missing_ingredients"] == ["밥"]


def test_expand_recipe_detail_stores():
    session = AgentSession(owned_names=["계란"])
    tools = _tool_map(session)
    tools["expand_recipe_detail"].invoke(
        {
            "ingredients": [{"name": "계란", "amount": "2개"}],
            "steps": [{"order": 1, "description": "볶는다"}],
            "tips": ["약불"],
        }
    )
    assert session.detail is not None
    assert session.detail["tips"] == ["약불"]
