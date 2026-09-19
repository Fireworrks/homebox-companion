"""Photograph a pile without selecting a location."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from homebox_companion import detect_items_from_bytes, settings

from ..dependencies import VisionContext, get_client, get_vision_context, require_llm_configured, validate_files_size
from ..services.sorting import SortResult, sort_items

router = APIRouter()


@router.post("/sort", response_model=SortResult, dependencies=[Depends(require_llm_configured)])
async def sort_pile(
    images: Annotated[list[UploadFile], File()],
    ctx: Annotated[VisionContext, Depends(get_vision_context)],
    mystery_box: Annotated[bool, Form()] = False,
) -> SortResult:
    if not 1 <= len(images) <= settings.capture_max_images:
        raise HTTPException(400, f"Provide between 1 and {settings.capture_max_images} images.")
    data = await validate_files_size(images)
    detected = await detect_items_from_bytes(
        data[0][0],
        data[0][1],
        tags=ctx.tags,
        additional_images=data[1:],
        field_preferences=ctx.field_preferences,
        output_language=ctx.output_language,
        custom_fields=ctx.custom_fields,
        extract_extended_fields=True,
        extra_instructions="Identify the individual contents of this pile or box so each can be put away separately.",
    )
    return await sort_items(detected, get_client(), ctx.token, mystery_box)
