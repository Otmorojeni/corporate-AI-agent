import io
import sys
from pathlib import Path
import pymupdf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from starlette.testclient import TestClient
from src.api.app import app

client = TestClient(app)


def test_health_endpoint():
    """GET /health возвращает 200 OK и статус 'ok'."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_query_endpoint_structure():
    """POST /v1/assistant/query возвращает ответ строго по openapi.yaml."""
    payload = {
        "request_id": "test-req-001",
        "query": "Как в документации eXpress расшифровывается CTS?",
    }
    response = client.post("/v1/assistant/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] == "test-req-001"
    assert "answer" in data
    assert isinstance(data["answer"], str)
    assert len(data["answer"]) > 0
    assert "detected_terms" in data
    assert isinstance(data["detected_terms"], list)
    assert len(data["detected_terms"]) >= 1
    term = data["detected_terms"][0]
    assert term["canonical"] == "CTS"
    assert term["expansion"] == "Corporate Transport Server"


def test_query_validation_error():
    """POST /v1/assistant/query возвращает 422 при отсутствии обязательного поля request_id."""
    response = client.post("/v1/assistant/query", json={"query": "привет"})
    assert response.status_code == 422


def test_extract_non_pdf_error():
    """POST /v1/abbreviations/extract возвращает 415 для не-PDF файлов."""
    response = client.post(
        "/v1/abbreviations/extract",
        files={"file": ("test.txt", b"plain text", "text/plain")},
    )
    assert response.status_code == 415


def test_extract_oversized_pdf():
    """POST /v1/abbreviations/extract возвращает 413 при превышении лимита 50 МиБ."""
    # 51 МиБ фиктивных данных с расширением .pdf
    fake_large_pdf = b"%PDF-1.4 " + (b"0" * (51 * 1024 * 1024))
    response = client.post(
        "/v1/abbreviations/extract",
        files={"file": ("large.pdf", fake_large_pdf, "application/pdf")},
    )
    assert response.status_code == 413


def test_extract_valid_pdf():
    """POST /v1/abbreviations/extract успешно извлекает аббревиатуры из валидного PDF."""
    # Генерируем реальный валидный PDF в памяти
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(
        (50, 72),
        "Сервер корпоративной коммуникации Corporate Transport Server (CTS) обеспечивает защищенный обмен сообщениями.",
        fontsize=12,
    )
    pdf_bytes = doc.tobytes()
    doc.close()

    response = client.post(
        "/v1/abbreviations/extract",
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "abbreviations" in data
    assert isinstance(data["abbreviations"], list)
    assert len(data["abbreviations"]) >= 1

    cts = next((a for a in data["abbreviations"] if a["canonical"] == "CTS"), None)
    assert cts is not None
    assert cts["expansion"] == "Corporate Transport Server"
    assert len(cts["occurrences"]) >= 1
    assert cts["occurrences"][0]["page"] == 1
    assert "CTS" in cts["occurrences"][0]["quote"]


def test_multi_product_query():
    """Проверка запроса с несколькими продуктами и омонимами (ЛИНТЕР и Tarantool)."""
    payload = {
        "request_id": "test-req-multi-002",
        "query": "Как в ЛИНТЕР и Tarantool используется WAL?",
    }
    response = client.post("/v1/assistant/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] == "test-req-multi-002"
    assert len(data["detected_terms"]) >= 1
    terms = {t["canonical"]: t["expansion"] for t in data["detected_terms"]}
    assert "WAL" in terms


def test_off_topic_query():
    """Проверка, что офф-топик запрос не порождает ложных терминов и случайных источников."""
    payload = {
        "request_id": "test-req-offtopic-003",
        "query": "Реал мадрид or Барселона ?",
    }
    response = client.post("/v1/assistant/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] == "test-req-offtopic-003"
    assert data["detected_terms"] == []
    assert data["sources"] is None or data["sources"] == []
    assert len(data["answer"]) > 0


def test_dynamic_pdf_workflow():
    """
    Проверка чек-поинта: обработка совершенно нового, ранее не существовавшего PDF-файла.
    1. Загрузка нового PDF через /v1/abbreviations/extract без каких-либо хардкодов.
    2. Извлечение новой аббревиатуры.
    3. Автоматическая регистрация в памяти сервиса.
    4. Успешный ответ на запрос через /v1/assistant/query с цитированием нового документа.
    """
    # Создаем тестовый PDF в памяти
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(
        (50, 100),
        "User Guide for Next-Generation Cloud Platform.\n\n"
        "In this architecture, the central system component is KPM (Knowledge Platform Management).\n"
        "Knowledge Platform Management (KPM) provides unified enterprise document storage,\n"
        "distributed data synchronization, and automated cluster administration across all nodes.\n"
    )
    pdf_bytes = doc.write()
    doc.close()

    filename = "unseen_cloud_platform.pdf"

    # Шаг 1: Извлечение аббревиатур из нового файла
    extract_resp = client.post(
        "/v1/abbreviations/extract",
        files={"file": (filename, pdf_bytes, "application/pdf")},
    )
    assert extract_resp.status_code == 200, f"Extract failed: {extract_resp.text}"
    extract_data = extract_resp.json()
    assert "abbreviations" in extract_data
    abbrs = {a["canonical"]: a["expansion"] for a in extract_data["abbreviations"]}
    assert "KPM" in abbrs
    assert "Knowledge Platform Management" in abbrs["KPM"]

    # Шаг 2: Вопрос ассистенту по новому документу
    query_resp = client.post(
        "/v1/assistant/query",
        json={
            "request_id": "test-dynamic-req-004",
            "query": "What is KPM in unseen_cloud_platform and what does it do?",
        },
    )
    assert query_resp.status_code == 200, f"Query failed: {query_resp.text}"
    query_data = query_resp.json()
    assert query_data["request_id"] == "test-dynamic-req-004"
    assert len(query_data["detected_terms"]) >= 1
    terms = {t["canonical"]: t["expansion"] for t in query_data["detected_terms"]}
    assert "KPM" in terms
    assert "Knowledge Platform Management" in terms["KPM"]

    # Проверяем, что источник указывает на загруженный файл
    assert query_data["sources"] is not None and len(query_data["sources"]) >= 1
    doc_ids = [s["document_id"] for s in query_data["sources"]]
    assert filename in doc_ids


def test_ui_endpoints():
    """Проверка доступности веб-интерфейса и чистоты схемы OpenAPI."""
    # 1. Проверка корневой страницы и страницы /ui
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "Корпоративный AI-Ассистент" in res_root.text

    res_ui = client.get("/ui")
    assert res_ui.status_code == 200
    assert "Корпоративный AI-Ассистент" in res_ui.text

    # 2. Проверка статических файлов CSS и JS
    res_css = client.get("/style.css")
    assert res_css.status_code == 200
    assert "text/css" in res_css.headers.get("content-type", "")

    res_js = client.get("/app.js")
    assert res_js.status_code == 200
    assert "javascript" in res_js.headers.get("content-type", "")

    # 3. Проверка динамического отображения модели из переменных окружения
    from src.config import settings
    assert settings.MODEL_NAME in res_root.text
    assert "{{MODEL_NAME}}" not in res_root.text

    # 4. Проверка эндпоинта динамической конфигурации
    res_cfg = client.get("/ui/config")
    assert res_cfg.status_code == 200
    cfg_data = res_cfg.json()
    assert cfg_data["model_name"] == settings.MODEL_NAME

    # 5. Проверка чистоты OpenAPI: в схему включены ТОЛЬКО регламентные методы
    res_schema = client.get("/openapi.json")
    assert res_schema.status_code == 200
    paths = set(res_schema.json().get("paths", {}).keys())
    assert paths == {"/health", "/v1/abbreviations/extract", "/v1/assistant/query"}


if __name__ == "__main__":
    tests = [
        test_health_endpoint,
        test_query_validation_error,
        test_extract_non_pdf_error,
        test_extract_oversized_pdf,
        test_extract_valid_pdf,
        test_query_endpoint_structure,
        test_multi_product_query,
        test_off_topic_query,
        test_dynamic_pdf_workflow,
        test_ui_endpoints,
    ]
    print(f"Запуск {len(tests)} тестов контракта...")
    for t in tests:
        print(f"  Выполняется {t.__name__}...", end="", flush=True)
        t()
        print(" OK!")
    print("\nВсе тесты успешно пройдены!")

