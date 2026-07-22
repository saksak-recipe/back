from fastapi import APIRouter, Depends, File, UploadFile, status

from api.deps import get_ocr_service
from core.exception.exceptions import (
    BadRequestException,
    ExternalServiceException,
    UnAuthorizedException,
)
from core.exception.openapi import create_error_response
from domains.ocr.schemas import OcrReceiptResponse
from domains.ocr.service import OcrService

router = APIRouter(prefix="/ocr", tags=["ocr"])


@router.post(
    "/receipt",
    status_code=status.HTTP_200_OK,
    response_model=OcrReceiptResponse,
    responses=create_error_response(
        UnAuthorizedException,
        BadRequestException,
        ExternalServiceException,
    ),
)
async def parse_receipt(
    image: UploadFile = File(...),
    service: OcrService = Depends(get_ocr_service),
) -> OcrReceiptResponse:
    image_bytes = await image.read()
    return await service.parse_receipt(
        image_bytes,
        content_type=image.content_type,
        filename=image.filename,
    )
