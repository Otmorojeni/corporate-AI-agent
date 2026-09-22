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


if __name__ == "__main__":
    tests = [
        test_health_endpoint,
        test_query_validation_error,
        test_extract_non_pdf_error,
        test_extract_oversized_pdf,
        test_extract_valid_pdf,
        test_query_endpoint_structure,
        test_multi_product_query,
    ]
    print(f"Запуск {len(tests)} тестов контракта...")
    for t in tests:
        print(f"  Выполняется {t.__name__}...", end="", flush=True)
        t()
        print(" OK!")
    print("\nВсе тесты успешно пройдены!")
