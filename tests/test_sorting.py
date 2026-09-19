"""Sort policy and Jev contract tests without paid model calls."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from homebox_companion.ai import decisions
from homebox_companion.ai.decisions import ChoiceAnswer
from homebox_companion.ai.response_models import get_items_response_model
from homebox_companion.core.exceptions import LLMServiceError
from homebox_companion.tools.vision.models import DetectedItem
from homebox_companion.tools.vision.prompts import build_detection_system_prompt, build_detection_user_prompt
from server.services import sorting


@pytest.mark.asyncio
async def test_jev_contract_and_tag_confidence(monkeypatch):
    monkeypatch.setattr(decisions.settings, "jev_api_key", "test-key")
    monkeypatch.setattr(decisions, "acquire_rate_limit", AsyncMock())
    requests = []

    def respond(request):
        requests.append(request)
        body = json.loads(request.content)
        assert body["model"] == "typesafe/jev-1.13"
        assert "messages" not in body
        return httpx.Response(
            200,
            json={
                "answers": {
                    "network": {"type": "choice", "choice": "yes", "confidence": 0.95},
                    "tools": {"type": "choice", "choice": "yes", "confidence": 0.3},
                }
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(decisions.httpx, "AsyncClient", lambda **kwargs: client)
    item = DetectedItem(name="Switch", tagIds=["vision-guess"])
    await decisions.assign_tags([item], [{"id": "network", "name": "Networking"}, {"id": "tools", "name": "Tools"}])
    assert item.tag_ids == ["network"]
    assert str(requests[0].url) == "https://openrouter.ai/api/alpha/decisions"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer",
    [
        {"type": "choice", "choice": "invented", "confidence": 0.99},
        {"type": "choice", "choice": "yes"},
        {"type": "choice", "choice": "yes", "confidence": 2},
    ],
)
async def test_invalid_jev_answer_fails_closed(monkeypatch, answer):
    monkeypatch.setattr(decisions.settings, "jev_api_key", "test-key")
    monkeypatch.setattr(decisions, "acquire_rate_limit", AsyncMock())
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"answers": {"q": answer}}))
    )
    monkeypatch.setattr(decisions.httpx, "AsyncClient", lambda **kwargs: client)
    with pytest.raises(LLMServiceError):
        await decisions.decide({}, {"q": {"type": "choice", "criteria": {"yes": "Fits"}}})


@pytest.mark.asyncio
async def test_key_is_required_even_without_tags(monkeypatch):
    monkeypatch.setattr(decisions.settings, "jev_api_key", "")
    with pytest.raises(LLMServiceError, match="HBC_JEV_API_KEY"):
        await decisions.assign_tags([DetectedItem(name="Switch")], [])


def test_vision_does_not_own_tags():
    assert "tagIds" not in json.dumps(get_items_response_model(None).model_json_schema())
    assert "tagIds" not in build_detection_user_prompt()
    assert "Networking" not in build_detection_system_prompt(tags=[{"id": "t", "name": "Networking"}])


@pytest.mark.asyncio
async def test_inventory_pagination_and_nested_evidence():
    client = AsyncMock()
    client.list_items.side_effect = [
        {
            "total": 2,
            "items": [
                {"id": "shelf", "name": "Misleading name", "entityType": {"isLocation": True}},
            ],
        },
        {
            "total": 2,
            "items": [
                {"id": "empty", "name": "Networking", "entityType": {"isLocation": True}},
            ],
        },
        {
            "total": 2,
            "items": [
                {"id": "box", "name": "Case", "parent": {"id": "shelf"}},
            ],
        },
        {
            "total": 2,
            "items": [
                {"id": "switch", "name": "Network switch", "parent": {"id": "box"}, "quantity": 2},
            ],
        },
    ]
    names, profiles = await sorting.inventory_profiles(client, "user-token")
    assert client.list_items.call_args_list[1].kwargs["page"] == 2
    assert client.list_items.call_args_list[0].kwargs["is_location"] is True
    assert client.list_items.call_args_list[2].kwargs["is_location"] is False
    assert client.list_items.call_args_list[3].kwargs["page"] == 2
    assert names["empty"] == "Networking"
    assert "empty" not in profiles
    assert "Network switch" in profiles["shelf"]
    assert "Misleading name" not in profiles["shelf"]


@pytest.mark.asyncio
async def test_grouping_confidence_collective_proposals_and_box(monkeypatch):
    monkeypatch.setattr(sorting, "inventory_profiles", AsyncMock(return_value=({"s": "Shelf"}, {"s": "[]"})))
    monkeypatch.setattr(
        sorting,
        "choose_destination",
        AsyncMock(
            side_effect=[
                ChoiceAnswer(type="choice", choice="s", confidence=0.95),
                ChoiceAnswer(type="choice", choice="s", confidence=0.5),
                ChoiceAnswer(type="choice", choice="needs_home", confidence=0.9),
            ]
        ),
    )
    propose = AsyncMock(
        return_value={"locations": [{"name": "Supplies", "description": "Keep together", "item_ids": ["1", "2"]}]}
    )
    monkeypatch.setattr(sorting, "json_completion", propose)
    result = await sorting.sort_items(
        [
            DetectedItem(name="Switch", quantity=8),
            DetectedItem(name="Odd cable"),
            DetectedItem(name="Glue"),
        ],
        AsyncMock(),
        "token",
        True,
    )
    assert [len(group.items) for group in result.groups] == [1, 2]
    assert result.groups[1].items[0].reason == "low_confidence"
    assert result.box is not None
    assert result.box.recommendation == "keep_together"
    assert result.box.dominant_share == 0.8
    assert result.box.assigned_share == 0.8
    propose.assert_awaited_once()
    assert "Glue" in propose.call_args.kwargs["messages"][1]["content"]
    assert "Odd cable" in propose.call_args.kwargs["messages"][1]["content"]


def test_unplaced_items_count_against_box_cohesion():
    groups = [
        sorting.DestinationGroup(
            location_id="s",
            name="Shelf",
            items=[sorting.SortItem(id="0", item=DetectedItem(name="Switch"), confidence=0.9, reason="matched")],
        ),
        sorting.DestinationGroup(
            location_id=None,
            name="Needs a home",
            items=[
                sorting.SortItem(
                    id="1", item=DetectedItem(name="Unknown", quantity=9), confidence=0.2, reason="low_confidence"
                )
            ],
        ),
    ]
    assert sorting.summarize_box(groups).recommendation == "disperse"
    assert sorting.summarize_box([]).recommendation == "empty"
    assert sorting.summarize_box(groups[1:]).recommendation == "needs_home"


@pytest.mark.asyncio
async def test_large_inventory_uses_all_evidence(monkeypatch):
    profiles = {f"s{i}": json.dumps([{"item": {"name": f"item{i}", "description": "x" * 3000}}]) for i in range(10)}
    seen = []

    async def decide(state, questions):
        criteria = questions["destination"]["criteria"]
        seen.extend(criteria.values())
        return {"destination": ChoiceAnswer(type="choice", choice=next(iter(criteria)), confidence=0.85)}

    monkeypatch.setattr(sorting, "decide", decide)
    answer = await sorting.choose_destination(DetectedItem(name="Switch"), profiles)
    assert answer.choice in profiles
    assert answer.confidence == 0.85
    for i in range(10):
        assert any(f"item{i}" in evidence for evidence in seen)


@pytest.mark.asyncio
async def test_sort_endpoint_accepts_photos_without_a_location(monkeypatch):
    from fastapi import FastAPI

    from server.api import sort as sort_api
    from server.dependencies import VisionContext, get_vision_context, require_llm_configured

    app = FastAPI()
    app.include_router(sort_api.router)
    app.dependency_overrides[require_llm_configured] = lambda: "test"
    app.dependency_overrides[get_vision_context] = lambda: VisionContext(
        token="user-token",
        tags=[],
        field_preferences=None,
        output_language=None,
        default_tag_id=None,
        custom_fields=[],
    )
    detection = AsyncMock(return_value=[DetectedItem(name="Switch")])
    routing = AsyncMock(return_value=sorting.SortResult(groups=[]))
    monkeypatch.setattr(sort_api, "detect_items_from_bytes", detection)
    monkeypatch.setattr(sort_api, "sort_items", routing)
    monkeypatch.setattr(sort_api, "get_client", lambda: "scoped-client")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/sort", files={"images": ("pile.jpg", b"image", "image/jpeg")}, data={"mystery_box": "true"}
        )
    assert response.status_code == 200
    assert routing.call_args.args[1:] == ("scoped-client", "user-token", True)
    assert detection.call_args.kwargs["extra_instructions"]


@pytest.mark.asyncio
async def test_invalid_proposals_preserve_pick_list(monkeypatch):
    monkeypatch.setattr(sorting, "inventory_profiles", AsyncMock(return_value=({}, {})))
    monkeypatch.setattr(
        sorting,
        "json_completion",
        AsyncMock(
            return_value={"locations": [{"name": "New", "description": "Invalid IDs", "item_ids": ["invented"]}]}
        ),
    )
    result = await sorting.sort_items([DetectedItem(name="Unknown")], AsyncMock(), "token", False)
    assert result.groups[0].items[0].item.name == "Unknown"
    assert result.proposed_locations == []
    assert result.proposal_error


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["detect", "analyze", "correct"])
async def test_every_vision_operation_delegates_tags(monkeypatch, operation):
    from homebox_companion.tools.vision import analyzer, corrector, detector

    module = {"detect": detector, "analyze": analyzer, "correct": corrector}[operation]
    monkeypatch.setattr(module, "require_jev_configured", lambda: None)
    output = {"name": "Switch", "tagIds": ["vision-guess"]}
    monkeypatch.setattr(
        module, "vision_completion", AsyncMock(return_value=(output if operation == "analyze" else {"items": [output]}))
    )

    async def tag(items, tags):
        for item in items:
            item.tag_ids = ["jev-choice"]

    tagger = AsyncMock(side_effect=tag)
    monkeypatch.setattr(module, "assign_tags", tagger)
    if operation == "detect":
        items = await detector._detect_items_from_data_uris(["data:image/jpeg;base64,eA=="])
    elif operation == "analyze":
        items = [await analyzer.analyze_item_details_from_images(["image"], "Switch", None)]
    else:
        items = await corrector.correct_item("image", {"name": "Switch"}, "Fix it")
    assert items[0].tag_ids == ["jev-choice"]
    tagger.assert_awaited_once()
