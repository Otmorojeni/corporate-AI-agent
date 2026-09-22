import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Settings:
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
