from starlette.testclient import TestClient
from src.api.app import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_query_endpoint_structure():
    payload = {
        "request_id": "test-req-001",
        "query": "Как в документации eXpress расшифровывается CTS?"
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
    # Отсутствует обязательное поле request_id
    response = client.post("/v1/assistant/query", json={"query": "привет"})
    assert response.status_code == 422


def test_extract_non_pdf_error():
    # Передача текстового файла вместо PDF
    response = client.post(
        "/v1/abbreviations/extract",
        files={"file": ("test.txt", b"plain text", "text/plain")}
    )
    assert response.status_code == 415
