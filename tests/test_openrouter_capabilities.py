"""OpenRouter routing preferences must not change vision capability detection."""

from unittest.mock import AsyncMock

import pytest

from homebox_companion.ai import llm, model_capabilities
from homebox_companion.core import config


@pytest.mark.asyncio
async def test_nitro_vision_request_preserves_images_and_model(monkeypatch):
    model = "openrouter/google/gemini-3.8-flash:nitro"
    base = model.removesuffix(":nitro")
    monkeypatch.setattr(config.settings, "llm_allow_unsafe_models", False)
    monkeypatch.setattr(llm, "_resolve_model_for_capabilities", lambda: model)
    monkeypatch.setattr(model_capabilities.litellm, "supports_vision", lambda name: name == base)
    monkeypatch.setattr(model_capabilities.litellm, "supports_response_schema", lambda name: name == base)
    complete = AsyncMock(return_value={"items": []})
    monkeypatch.setattr(llm, "json_completion", complete)
    model_capabilities.get_model_capabilities.cache_clear()
    try:
        await llm.vision_completion("Identify", "Test", ["data:image/png;base64,eA=="])
        content = complete.call_args.args[0][1]["content"]
        assert content[1]["image_url"]["url"] == "data:image/png;base64,eA=="
        assert model_capabilities.get_model_capabilities(model).model == model
    finally:
        model_capabilities.get_model_capabilities.cache_clear()
