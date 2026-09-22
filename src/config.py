"""
Конфигурация проекта и управление переменными окружения.
Загружает переменные из системной среды или .env файла.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Базовая директория проекта
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    """Глобальные настройки сервера, путей и подключения к API."""
    # API settings
    API_KEY: str = os.getenv("API_KEY", "")
    BASE_URL: str = os.getenv("BASE_URL", "https://foundation-models.api.cloud.ru/v1")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "GigaChat/GigaChat-2-Max")

    # Directories and files
    CORPUS_DIR: Path = Path(os.getenv("CORPUS_DIR", str(BASE_DIR / "corpus")))
    TERMS_FILE: Path = Path(os.getenv("TERMS_FILE", str(BASE_DIR / "data" / "terms.jsonl")))
    INDICES_DIR: Path = Path(os.getenv("INDICES_DIR", str(BASE_DIR / "data" / "indices")))
    CHUNKS_FILE: Path = Path(os.getenv("CHUNKS_FILE", str(BASE_DIR / "data" / "chunks_by_product.json")))

    # Server settings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

settings = Settings()
