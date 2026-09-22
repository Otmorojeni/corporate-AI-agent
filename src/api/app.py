"""
Главная точка входа ASGI-приложения FastAPI.
Инициализирует маршрутизацию, CORS и OpenAPI документацию сервиса.
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import router
from src.config import BASE_DIR, settings

UI_DIR = BASE_DIR / "ui"
INDEX_HTML = UI_DIR / "index.html"
STYLE_CSS = UI_DIR / "style.css"
APP_JS = UI_DIR / "app.js"

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
        content = INDEX_HTML.read_text(encoding="utf-8")
        # Динамическая подстановка названия модели из переменных окружения
        content = content.replace("{{MODEL_NAME}}", settings.MODEL_NAME)
        return HTMLResponse(content=content)
    return HTMLResponse(content="<h1>Корпоративный ассистент активен. Откройте /docs</h1>")


@app.get("/ui/config", include_in_schema=False)
async def get_ui_config():
    """Динамические параметры окружения LLM для веб-интерфейса."""
    return {
        "model_name": settings.MODEL_NAME,
        "base_url": settings.BASE_URL,
    }


@app.get("/style.css", include_in_schema=False)
@app.get("/ui/style.css", include_in_schema=False)
async def serve_css():
    """Стили оформления для веб-интерфейса."""
    if STYLE_CSS.exists():
        return FileResponse(
            STYLE_CSS,
            media_type="text/css",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
        )
    return Response(status_code=404)


@app.get("/app.js", include_in_schema=False)
@app.get("/ui/app.js", include_in_schema=False)
async def serve_js():
    """Клиентский JavaScript для веб-интерфейса."""
    if APP_JS.exists():
        return FileResponse(
            APP_JS,
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
        )
    return Response(status_code=404)

