from domains.ai_recipe.partial_json import PartialDetailParser


def test_emits_sections_as_arrays_close():
    parser = PartialDetailParser()
    events: list[tuple[str, object]] = []
    events.extend(parser.feed('{"ingredients":[{"name":"계란","amount":"2개"}]'))
    assert events == []
    events.extend(parser.feed(',"steps":[{"order":1,"description":"볶는다"}]'))
    assert events == [
        ("ingredients", [{"name": "계란", "amount": "2개"}]),
    ]
    events.extend(parser.feed(',"tips":["약불"]}'))
    assert ("steps", [{"order": 1, "description": "볶는다"}]) in events
    assert ("tips", ["약불"]) in events


def test_section_emitted_only_once():
    parser = PartialDetailParser()
    first = parser.feed(
        '{"ingredients":[{"name":"계란","amount":"1"}],'
        '"steps":[],"tips":[]}'
    )
    second = parser.feed("")
    assert sum(1 for s, _ in first if s == "ingredients") == 1
    assert second == []


def test_ignores_incomplete_json():
    parser = PartialDetailParser()
    assert parser.feed('{"ingredients":[{"name":"계') == []


def test_finish_emits_closed_array_without_next_key():
    parser = PartialDetailParser()
    assert parser.feed('{"ingredients":[{"name":"계란","amount":"2개"}]}') == []
    events = parser.finish()
    assert events == [("ingredients", [{"name": "계란", "amount": "2개"}])]
