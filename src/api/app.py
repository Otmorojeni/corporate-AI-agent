from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.schemas import (
    HealthResponse,
    AbbreviationExtractionResponse,
    AssistantQueryRequest,
    AssistantQueryResponse,
)

app = FastAPI(
    title="Corporate Abbreviation Assistant API",
    version="1",
    description="Ответы по базе знаний с использованием самостоятельно извлечённых из PDF аббревиатур для понимания запросов и выбора значения по контексту.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Проверка доступности сервиса",
    operation_id="health",
)
async def health():
    return HealthResponse(status="ok")


# Imports of routes will be added as core components are ready
