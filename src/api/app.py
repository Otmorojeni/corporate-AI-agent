"""
Главная точка входа ASGI-приложения FastAPI.
Инициализирует маршрутизацию, CORS и OpenAPI документацию сервиса.
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import router

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"

app = FastAPI(
    title="Corporate Abbreviation Assistant API",
    version="1",
    description=(
        "Ответы по базе знаний с использованием самостоятельно извлечённых из PDF "
        "аббревиатур для понимания запросов и выбора значения по контексту."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение всех официальных маршрутов по openapi.yaml
app.include_router(router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def serve_ui():
    """Интерактивный веб-интерфейс для демонстрации решения на питчинге."""
    if INDEX_HTML.exists():
        return HTMLResponse(content=INDEX_HTML.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Корпоративный ассистент активен. Откройте /docs</h1>")

