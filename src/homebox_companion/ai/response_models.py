"""Pydantic response models for structured LLM output.

These models are passed as ``response_format`` to LiteLLM so the provider
can enforce the JSON schema at the token level (structured outputs).

The callers in ``tools/vision/`` still perform post-hoc validation via
``TypeAdapter`` as defense-in-depth; these wrapper models serve a different
purpose — telling the *provider* what shape to produce.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, create_model

from ..tools.vision.models import DetectedItem, _build_cached_model, _to_cache_key

if TYPE_CHECKING:
    from ..core.persistent_settings import CustomFieldDefinition


def _vision_model(model: type[BaseModel]) -> type[BaseModel]:
    fields: dict[str, Any] = {
        name: (field.annotation, field)
        for name, field in model.model_fields.items()
        if name not in {"tag_ids", "parent_id"}
    }
    return create_model("VisionExtraction", **fields)


VisionItem = _vision_model(DetectedItem)


class ItemsResponse(BaseModel):
    """Wrapper for responses containing a list of detected items.

    Used by detector and corrector, which expect ``{"items": [...]}``.
    """

    items: list[VisionItem]  # ty: ignore[invalid-type-form]


def get_items_response_model(
    custom_fields: list[CustomFieldDefinition] | None,
) -> type[BaseModel]:
    """Get a Pydantic model for ``{"items": [...]}`` responses.

    Returns the static ``ItemsResponse`` when no custom fields are
    configured, or builds a dynamic wrapper around the dynamic
    ``DetectedItem`` subclass.
    """
    if not custom_fields:
        return ItemsResponse
    return _build_dynamic_items_response(_to_cache_key(custom_fields))


def get_single_item_response_model(
    custom_fields: list[CustomFieldDefinition] | None,
) -> type[BaseModel]:
    """Get a Pydantic model for single-item responses.

    Used by the analyzer which returns a flat ``DetectedItem``, not
    wrapped in ``{"items": [...]}``.
    """
    if not custom_fields:
        return VisionItem
    return _vision_model(_build_cached_model(_to_cache_key(custom_fields)))


@lru_cache(maxsize=4)
def _build_dynamic_items_response(
    cache_key: tuple[tuple[str, str, str, str], ...],
) -> type[BaseModel]:
    """Build a cached ``ItemsResponse`` variant with dynamic item model."""
    dynamic_item = _vision_model(_build_cached_model(cache_key))
    return create_model(
        "DynamicItemsResponse",
        __base__=BaseModel,
        items=(list[dynamic_item], ...),  # ty: ignore
    )
