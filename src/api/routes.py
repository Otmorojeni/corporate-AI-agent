import logging
import time
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from src.schemas import (
    HealthResponse,
    AbbreviationExtractionResponse,
    AssistantQueryRequest,
    AssistantQueryResponse,
)
from src.core.extractor import extract_abbreviations_from_bytes
from src.core.pipeline import process_user_query, matcher, retriever
from src.core.product_detector import register_dynamic_product

logger = logging.getLogger("corporate_agent.api")

router = APIRouter()

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MiB per openapi.yaml


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Проверка доступности сервиса",
    operation_id="health",
    tags=["Service"],
)
async def health():
    return HealthResponse(status="ok")


@router.post(
    "/v1/abbreviations/extract",
    response_model=AbbreviationExtractionResponse,
    summary="Извлечь подтверждённые аббревиатуры из загруженного PDF",
    operation_id="extractAbbreviations",
    tags=["Abbreviations"],
    responses={
        413: {"description": "Размер файла превышает 50 МиБ."},
        415: {"description": "Передан файл, не являющийся PDF."},
        422: {"description": "PDF не удалось обработать."},
    },
)
async def extract_abbreviations(file: UploadFile = File(..., description="PDF-файл размером до 50 МиБ.")):
    t0 = time.perf_counter()
    filename = file.filename or ""
    content_type = file.content_type or ""

    # 1. Проверка формата файла (HTTP 415)
    if not filename.lower().endswith(".pdf") and "pdf" not in content_type.lower():
        logger.warning("Rejected non-PDF upload: filename='%s', content_type='%s'", filename, content_type)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Передан файл, не являющийся PDF.",
        )

    # 2. Проверка размера файла (HTTP 413)
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        logger.warning("Rejected oversized upload: filename='%s', size=%d bytes", filename, len(content))
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Размер файла превышает 50 МиБ.",
        )

    # 3. Извлечение аббревиатур (HTTP 422 при поврежденном файле)
    try:
        abbreviations = extract_abbreviations_from_bytes(content)

        # Динамическая регистрация в памяти:
        # Позволяет ассистенту мгновенно отвечать на вопросы по новому PDF
        # без привязки к обучающему датасету и без перезапуска сервера
        stem = Path(filename).stem if filename else "custom_doc"
        matcher.add_dynamic_terms(abbreviations, product=stem)
        retriever.add_dynamic_document(filename=filename or "custom_doc.pdf", content=content, product=stem)
        register_dynamic_product(stem)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "Extracted %d abbreviations and dynamically indexed '%s' (%d bytes) in %.1fms",
            len(abbreviations),
            filename,
            len(content),
            elapsed_ms,
        )
        return AbbreviationExtractionResponse(abbreviations=abbreviations)
    except Exception as e:
        logger.exception("Failed to parse PDF '%s': %s", filename, e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"PDF не удалось обработать: {str(e)}",
        )


@router.post(
    "/v1/assistant/query",
    response_model=AssistantQueryResponse,
    summary="Ответ на запрос сотрудника",
    operation_id="queryAssistant",
    tags=["Assistant"],
    responses={
        422: {"description": "Некорректный запрос"},
    },
)
async def query_assistant(req: AssistantQueryRequest):
    t0 = time.perf_counter()
    try:
        response = await process_user_query(req)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info("Processed query req_id='%s' in %.1fms", req.request_id, elapsed_ms)
        return response
    except Exception as e:
        # Graceful fallback: сервис не должен возвращать 500
        logger.exception("Error processing assistant query req_id='%s': %s", req.request_id, e)
        return AssistantQueryResponse(
            request_id=req.request_id,
            answer="Не удалось найти информацию по вашему запросу в текущей версии документации.",
            detected_terms=[],
            sources=[],
        )
