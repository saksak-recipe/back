from collections.abc import Awaitable, Callable

from core.exception.exceptions import BadRequestException
from domains.ocr.llm_parser import parse_receipt_text
from domains.ocr.naver_client import extract_text
from domains.ocr.schemas import OcrReceiptResponse

MAX_IMAGE_BYTES = 10 * 1024 * 1024
_MIME_TO_FORMAT = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
_EXT_TO_FORMAT = {
    ".jpg": "jpg",
    ".jpeg": "jpg",
    ".png": "png",
    ".webp": "webp",
}

ExtractTextFn = Callable[..., Awaitable[str]]
ParseReceiptTextFn = Callable[..., Awaitable[list[str]]]


class OcrService:
    def __init__(
        self,
        *,
        api_url: str,
        secret_key: str,
        openai_api_key: str,
        llm_model: str,
        extract_text_fn: ExtractTextFn = extract_text,
        parse_receipt_text_fn: ParseReceiptTextFn = parse_receipt_text,
    ) -> None:
        self._api_url = api_url
        self._secret_key = secret_key
        self._openai_api_key = openai_api_key
        self._llm_model = llm_model
        self._extract_text = extract_text_fn
        self._parse_receipt_text = parse_receipt_text_fn

    def _resolve_format(
        self, content_type: str | None, filename: str | None
    ) -> str:
        if content_type:
            fmt = _MIME_TO_FORMAT.get(content_type.lower())
            if fmt:
                return fmt
        if filename and "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1].lower()
            fmt = _EXT_TO_FORMAT.get(ext)
            if fmt:
                return fmt
        raise BadRequestException(detail="지원하지 않는 이미지 형식입니다.")

    async def parse_receipt(
        self,
        image_bytes: bytes,
        content_type: str | None,
        filename: str | None,
    ) -> OcrReceiptResponse:
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise BadRequestException(detail="이미지 크기는 10MB 이하여야 합니다.")
        if not image_bytes:
            raise BadRequestException(detail="이미지 파일이 비어 있습니다.")

        image_format = self._resolve_format(content_type, filename)
        ocr_text = await self._extract_text(
            image_bytes,
            format=image_format,
            api_url=self._api_url,
            secret_key=self._secret_key,
        )
        ingredients = await self._parse_receipt_text(
            ocr_text,
            api_key=self._openai_api_key,
            model=self._llm_model,
        )
        return OcrReceiptResponse(ingredients=ingredients)
