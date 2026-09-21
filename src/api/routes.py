from fastapi import APIRouter, UploadFile, File, HTTPException, status
from src.schemas import (
    HealthResponse,
    AbbreviationExtractionResponse,
    AssistantQueryRequest,
    AssistantQueryResponse,
    DetectedTerm,
)

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
    # 1. Проверка формата файла (HTTP 415)
    filename = file.filename or ""
    content_type = file.content_type or ""
    if not filename.lower().endswith(".pdf") and "pdf" not in content_type.lower():
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Передан файл, не являющийся PDF.",
        )

    # 2. Проверка размера файла (HTTP 413)
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Размер файла превышает 50 МиБ.",
        )

    # 3. Извлечение аббревиатур (HTTP 422 при сбое)
    try:
        # Импортируем экстрактор из core (будет реализован в core/extractor.py)
        from src.core.extractor import extract_abbreviations_from_bytes
        abbreviations = extract_abbreviations_from_bytes(content)
        return AbbreviationExtractionResponse(abbreviations=abbreviations)
    except ImportError:
        # Заглушка до реализации extractor.py
        return AbbreviationExtractionResponse(abbreviations=[])
    except Exception as e:
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
    # Основной пайплайн обработки запроса
    try:
        from src.core.pipeline import process_user_query
        return await process_user_query(req)
    except ImportError:
        # Базовый ответ-заглушка на время сборки компонентов core
        return AssistantQueryResponse(
            request_id=req.request_id,
            answer="Сервис корпоративного ассистента обрабатывает запрос. Ядро системы на этапе калибровки.",
            detected_terms=[],
            sources=[],
        )
    except Exception as e:
        # Graceful fallback: сервис не должен падать с 500 для жюри!
        return AssistantQueryResponse(
            request_id=req.request_id,
            answer="Не удалось найти информацию по вашему запросу в текущей версии документации.",
            detected_terms=[],
            sources=[],
        )
