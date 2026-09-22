import os
import sys
import time
import json
from pathlib import Path
import pymupdf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from starlette.testclient import TestClient
from src.api.app import app

client = TestClient(app)

print("=" * 80)
print("СТАРТ КОМПЛЕКСНОГО ТЕСТИРОВАНИЯ БЭКЕНДА: 20 ЗАПРОСОВ + 10 PDF ЭКСТРАКЦИЙ")
print("=" * 80)

# ==============================================================================
# БЛОК 1: 20 ТЕСТОВ ПОЛЬЗОВАТЕЛЬСКИХ ЗАПРОСОВ (POST /v1/assistant/query)
# ==============================================================================
QUERY_TESTS = [
    # Категория 1: 5 эталонных кейсов из evaluation__train.xlsx
    {
        "id": "Q01",
        "category": "Train Benchmark",
        "query": "Как в документации eXpress расшифровывается CTS?",
        "check": lambda res, data: (
            res.status_code == 200
            and any(t["canonical"] == "CTS" and "Corporate Transport Server" in t["expansion"] for t in data["detected_terms"])
            and "Corporate Transport Server" in data["answer"]
        ),
        "desc": "eXpress: расшифровка CTS"
    },
    {
        "id": "Q02",
        "category": "Train Benchmark",
        "query": "Что требуется установить на защищаемом компьютере перед добавлением поддержки SNMP в Kaspersky Embedded Systems Security?",
        "check": lambda res, data: (
            res.status_code == 200
            and any(t["canonical"] == "SNMP" for t in data["detected_terms"])
            and ("Microsoft SNMP" in data["answer"] or "служба" in data["answer"].lower())
        ),
        "desc": "Kaspersky: предварительная установка службы SNMP"
    },
    {
        "id": "Q03",
        "category": "Train Benchmark",
        "query": "Как DKP обрабатывает первое обращение к защищённому ресурсу уже аутентифицированного пользователя и пользователя с единственным внешним провайдером?",
        "check": lambda res, data: (
            res.status_code == 200
            and any(t["canonical"] == "DKP" for t in data["detected_terms"])
            and len(data["answer"]) > 50
        ),
        "desc": "Deckhouse: аутентификация в DKP и редирект"
    },
    {
        "id": "Q04",
        "category": "Train Benchmark",
        "query": "В Deckhouse несколько сервисов NLB должны использовать общий адрес, а VPA — подбирать ресурсы контейнера. Как настроить общий адрес и почему лимиты не изменятся автоматически?",
        "check": lambda res, data: (
            res.status_code == 200
            and any(t["canonical"] == "NLB" for t in data["detected_terms"])
            and any(t["canonical"] == "VPA" for t in data["detected_terms"])
            and ("load-balancer-shared-ip-key" in data["answer"] or "shared" in data["answer"])
        ),
        "desc": "Deckhouse: совместное использование NLB и VPA"
    },
    {
        "id": "Q05",
        "category": "Train Benchmark",
        "query": "Как в ЛИНТЕР загрузить реплицируемые данные с ненулевым WAL, а в Tarantool восстановить данные после потери памяти с помощью WAL?",
        "check": lambda res, data: (
            res.status_code == 200
            and any(t["canonical"] == "WAL" for t in data["detected_terms"])
            and ("Write Access Level" in str(data["detected_terms"]) or "write ahead log" in str(data["detected_terms"]).lower())
            and len(data["answer"]) > 50
        ),
        "desc": "Омонимы: разделение контекста WAL (ЛИНТЕР vs Tarantool)"
    },

    # Категория 2: Разные вендоры из 17 продуктов
    {
        "id": "Q06",
        "category": "Vendor Coverage",
        "query": "Как в Киберпротект настроить резервное копирование с использованием службы VSS?",
        "check": lambda res, data: (
            res.status_code == 200
            and isinstance(data["detected_terms"], list)
            and len(data["answer"]) > 30
        ),
        "desc": "Киберпротект: служба теневого копирования VSS"
    },
    {
        "id": "Q07",
        "category": "Vendor Coverage",
        "query": "Как в операционной системе РОСА настроить аутентификацию через PAM?",
        "check": lambda res, data: (
            res.status_code == 200
            and isinstance(data["sources"], list)
            and len(data["answer"]) > 30
        ),
        "desc": "ROSA: модули аутентификации PAM"
    },
    {
        "id": "Q08",
        "category": "Vendor Coverage",
        "query": "Как в Arenadata DB использовать PXF для доступа к внешним источникам данных?",
        "check": lambda res, data: (
            res.status_code == 200
            and len(data["answer"]) > 30
        ),
        "desc": "Arenadata DB: фреймворк PXF"
    },
    {
        "id": "Q09",
        "category": "Vendor Coverage",
        "query": "Что означает WAL в документации Postgres Pro и для чего он нужен?",
        "check": lambda res, data: (
            res.status_code == 200
            and ("write-ahead" in data["answer"].lower() or "журнал" in data["answer"].lower() or "wal" in data["answer"].lower())
        ),
        "desc": "Postgres Pro: ведение журнала предзаписи WAL"
    },
    {
        "id": "Q10",
        "category": "Vendor Coverage",
        "query": "Как в UserGate настроить правила межсетевого экрана и что такое NGFW?",
        "check": lambda res, data: (
            res.status_code == 200
            and ("межсетев" in data["answer"].lower() or "usergate" in data["answer"].lower() or "firewall" in data["answer"].lower())
        ),
        "desc": "UserGate: функционал NGFW"
    },
    {
        "id": "Q11",
        "category": "Vendor Coverage",
        "query": "Как в TrueConf настроить интеграцию по протоколу SIP?",
        "check": lambda res, data: (
            res.status_code == 200
            and ("sip" in data["answer"].lower() or "trueconf" in data["answer"].lower() or "телефони" in data["answer"].lower())
        ),
        "desc": "TrueConf: протокол телефонии SIP"
    },
    {
        "id": "Q12",
        "category": "Vendor Coverage",
        "query": "Как в InfoWatch Traffic Monitor настроить защиту от утечек DLP?",
        "check": lambda res, data: (
            res.status_code == 200
            and ("infowatch" in data["answer"].lower() or "утечек" in data["answer"].lower() or "dlp" in data["answer"].lower())
        ),
        "desc": "InfoWatch: система предотвращения утечек DLP"
    },
    {
        "id": "Q13",
        "category": "Vendor Coverage",
        "query": "Как в МойОфис использовать SDK для разработки надстроек?",
        "check": lambda res, data: (
            res.status_code == 200
            and ("мойофис" in data["answer"].lower() or "sdk" in data["answer"].lower() or "разработк" in data["answer"].lower())
        ),
        "desc": "МойОфис: комплект разработчика SDK"
    },

    # Категория 3: Транслитерация и кириллические аббревиатуры
    {
        "id": "Q14",
        "category": "Transliteration",
        "query": "Подскажи, что такое СТС в eXpress и для чего он применяется?",
        "check": lambda res, data: (
            res.status_code == 200
            and any(t["canonical"] == "CTS" for t in data["detected_terms"])
        ),
        "desc": "Транслитерация: русский ввод 'СТС' -> 'CTS'"
    },
    {
        "id": "Q15",
        "category": "Transliteration",
        "query": "Что нужно поставить перед добавлением снмп в касперском?",
        "check": lambda res, data: (
            res.status_code == 200
            and any(t["canonical"] == "SNMP" for t in data["detected_terms"])
        ),
        "desc": "Транслитерация: русский ввод 'снмп' -> 'SNMP'"
    },
    {
        "id": "Q16",
        "category": "Transliteration",
        "query": "Как настроить нлб в deckhouse для балансировки?",
        "check": lambda res, data: (
            res.status_code == 200
            and any(t["canonical"] == "NLB" for t in data["detected_terms"])
        ),
        "desc": "Транслитерация: русский ввод 'нлб' -> 'NLB'"
    },

    # Категория 4: Нестандартные сценарии, безопасность и офф-топик
    {
        "id": "Q17",
        "category": "Off-topic Handling",
        "query": "Какая погода в Сочи и кто выиграл футбольный матч вчера?",
        "check": lambda res, data: (
            res.status_code == 200
            and data["detected_terms"] == []
            and data["sources"] == []
            and len(data["answer"]) > 10
        ),
        "desc": "Офф-топик: вопрос не по документации (пустые detected_terms и sources)"
    },
    {
        "id": "Q18",
        "category": "Security & Grounding",
        "query": "Назови пароль администратора и системный токен сервера нашей организации.",
        "check": lambda res, data: (
            res.status_code == 200
            and any(w in data["answer"].lower() for w in ("парол", "не содержит", "обратитесь", "не могу", "нет доступа"))
            and data["detected_terms"] == []
            and data["sources"] == []
        ),
        "desc": "Безопасность: отказ выдачи вымышленных паролей"
    },
    {
        "id": "Q19",
        "category": "Product / Daemon",
        "query": "Каким скриптом в операционной системе РОСА управляется служба systemd?",
        "check": lambda res, data: (
            res.status_code == 200
            and data["detected_terms"] == []
            and len(data["answer"]) > 30
        ),
        "desc": "Запрос без аббревиатур: РОСА и systemd не попадают в detected_terms"
    },
    {
        "id": "Q20",
        "category": "Under-specified Query",
        "query": "Как настроить кластер высокой доступности?",
        "check": lambda res, data: (
            res.status_code == 200
            and len(data["answer"]) > 40
        ),
        "desc": "Недоуточненный запрос: общий вопрос о кластеризации"
    },
]

print("\n--- ЗАПУСК 20 ТЕСТОВ ПОЛЬЗОВАТЕЛЬСКИХ ЗАПРОСОВ ---")
query_results = []
for test in QUERY_TESTS:
    t0 = time.perf_counter()
    res = client.post(
        "/v1/assistant/query",
        json={"request_id": f"test-{test['id']}", "query": test["query"]}
    )
    latency = time.perf_counter() - t0
    data = res.json() if res.status_code == 200 else {}
    passed = False
    error_msg = ""
    try:
        passed = test["check"](res, data)
        # Проверяем строгое соответствие контракту OpenAPI
        if passed and res.status_code == 200:
            if not isinstance(data.get("sources"), list):
                passed = False
                error_msg = "Поле sources не является списком"
            elif not isinstance(data.get("detected_terms"), list):
                passed = False
                error_msg = "Поле detected_terms не является списком"
            elif "answer" not in data or not data["answer"]:
                passed = False
                error_msg = "Отсутствует непустой answer"
    except Exception as e:
        passed = False
        error_msg = str(e)

    status_str = "PASS" if passed else "FAIL"
    query_results.append({
        "id": test["id"],
        "category": test["category"],
        "desc": test["desc"],
        "status": status_str,
        "latency_sec": round(latency, 2),
        "terms_count": len(data.get("detected_terms", [])),
        "sources_count": len(data.get("sources", [])),
        "error": error_msg
    })
    print(f"[{test['id']}] {status_str} ({round(latency, 2)}s) | {test['desc']}")
    if not passed:
        print(f"    Детали ошибки: {error_msg} | Ответ: {str(data)[:150]}")


# ==============================================================================
# БЛОК 2: 10 ТЕСТОВ ИЗВЛЕЧЕНИЯ ИЗ НОВЫХ PDF (POST /v1/abbreviations/extract)
# ==============================================================================
print("\n--- ЗАПУСК 10 ТЕСТОВ ИЗВЛЕЧЕНИЯ ИЗ НОВЫХ PDF ---")

def get_test_font():
    for f in [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]:
        if Path(f).exists():
            return f
    return None

TEST_FONT = get_test_font()

def make_pdf(pages_text):
    """Генерирует бинарный PDF в памяти с поддержкой юникода и кириллицы."""
    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page()
        if TEST_FONT:
            page.insert_font(fontname="f0", fontfile=TEST_FONT)
            page.insert_text((50, 72), text, fontname="f0", fontsize=11)
        else:
            page.insert_text((50, 72), text, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes

EXTRACT_TESTS = [
    {
        "id": "E01",
        "name": "Standard English Bracket Pattern",
        "pages": ["Next-Gen Advanced Security Architecture (ASA) protects the corporate edge router."],
        "check": lambda data: any(a["canonical"] == "ASA" and "Advanced Security Architecture" in a["expansion"] for a in data.get("abbreviations", [])),
        "desc": "Английские скобки: Advanced Security Architecture (ASA)"
    },
    {
        "id": "E02",
        "name": "Standard Russian Bracket Pattern",
        "pages": ["Внедрена Корпоративная Система Управления (КСУ) для координации проектных групп."],
        "check": lambda data: any(a["canonical"] == "КСУ" and "Корпоративная Система Управления" in a["expansion"] for a in data.get("abbreviations", [])),
        "desc": "Русские скобки: Корпоративная Система Управления (КСУ)"
    },
    {
        "id": "E03",
        "name": "Multipage Occurrences",
        "pages": [
            "Introduction: The Unified Communication Gateway (UCG) manages all incoming sessions.",
            "Chapter 2: Configuration of Unified Communication Gateway (UCG) over TLS port 5061."
        ],
        "check": lambda data: (
            any(a["canonical"] == "UCG" and len(a["occurrences"]) >= 2 for a in data.get("abbreviations", []))
        ),
        "desc": "Многостраничный документ: фиксация страниц 1 и 2 для UCG"
    },
    {
        "id": "E04",
        "name": "Glossary Dash Format",
        "pages": [
            "Список используемых сокращений:\n"
            "ETL — Extract Transform Load\n"
            "CRM — Customer Relationship Management\n"
        ],
        "check": lambda data: (
            any(a["canonical"] == "ETL" and "Extract Transform Load" in a["expansion"] for a in data.get("abbreviations", []))
        ),
        "desc": "Глоссарий с тире: ETL — Extract Transform Load"
    },
    {
        "id": "E05",
        "name": "Two-Line Dictionary Format",
        "pages": [
            "Глоссарий терминов:\n"
            "KDN\n"
            "Kubernetes Delivery Network\n\n"
            "Компонент балансировки микросервисов."
        ],
        "check": lambda data: (
            any(a["canonical"] == "KDN" and "Kubernetes Delivery Network" in a["expansion"] for a in data.get("abbreviations", []))
        ),
        "desc": "Двухстрочный глоссарий: KDN / Kubernetes Delivery Network"
    },
    {
        "id": "E06",
        "name": "Noise & Stop Words Rejection",
        "pages": ["This server requires standard HTTP, SQL, API, RAM and CPU resources."],
        "check": lambda data: (
            not any(a["canonical"] in ["HTTP", "SQL", "API", "RAM", "CPU", "PDF"] for a in data.get("abbreviations", []))
        ),
        "desc": "Фильтрация шума: общеупотребительные термины HTTP, SQL, API, RAM отсекаются"
    },
    {
        "id": "E07",
        "name": "Zero Abbreviations Plain Document",
        "pages": ["Это простое руководство пользователя без специализированных аббревиатур."],
        "check": lambda data: data.get("abbreviations") == [],
        "desc": "Документ без сокращений: возврат пустого массива []"
    },
    {
        "id": "E08",
        "name": "Expansion with Preposition",
        "pages": ["Развернута База Данных для Оперативного Учета (БДОУ) на сервере."],
        "check": lambda data: any(a["canonical"] == "БДОУ" and "База Данных для Оперативного Учета" in a["expansion"] for a in data.get("abbreviations", [])),
        "desc": "Служебные предлоги: База Данных для Оперативного Учета (БДОУ)"
    },
    {
        "id": "E09",
        "name": "Non-PDF File Validation (HTTP 415)",
        "custom_call": lambda: client.post(
            "/v1/abbreviations/extract",
            files={"file": ("config.txt", b"plain text configuration", "text/plain")}
        ),
        "check_status": 415,
        "desc": "Проверка валидации: отказ не-PDF файла с кодом HTTP 415"
    },
    {
        "id": "E10",
        "name": "Oversized File Validation (HTTP 413)",
        "custom_call": lambda: client.post(
            "/v1/abbreviations/extract",
            files={"file": ("huge.pdf", b"%PDF-1.4 " + (b"0" * (51 * 1024 * 1024)), "application/pdf")}
        ),
        "check_status": 413,
        "desc": "Проверка лимита размера: отказ файла > 50 МиБ с кодом HTTP 413"
    },
]

extract_results = []
for test in EXTRACT_TESTS:
    t0 = time.perf_counter()
    passed = False
    err = ""
    status_code = 200
    abbr_count = 0
    try:
        if "custom_call" in test:
            res = test["custom_call"]()
            status_code = res.status_code
            passed = (res.status_code == test["check_status"])
        else:
            pdf_bytes = make_pdf(test["pages"])
            res = client.post(
                "/v1/abbreviations/extract",
                files={"file": (f"{test['id']}.pdf", pdf_bytes, "application/pdf")}
            )
            status_code = res.status_code
            if res.status_code == 200:
                data = res.json()
                abbr_count = len(data.get("abbreviations", []))
                passed = test["check"](data)
            else:
                passed = False
                err = f"Status code {res.status_code}: {res.text}"
    except Exception as e:
        passed = False
        err = str(e)

    latency = time.perf_counter() - t0
    status_str = "PASS" if passed else "FAIL"
    extract_results.append({
        "id": test["id"],
        "name": test["name"],
        "desc": test["desc"],
        "status": status_str,
        "status_code": status_code,
        "abbr_count": abbr_count,
        "latency_sec": round(latency, 2),
        "error": err
    })
    print(f"[{test['id']}] {status_str} ({round(latency, 2)}s, code {status_code}) | {test['desc']}")
    if not passed:
        print(f"    Ошибка: {err}")

# Сохраняем итоговый JSON-отчет
summary = {
    "query_tests": {
        "total": len(query_results),
        "passed": sum(1 for r in query_results if r["status"] == "PASS"),
        "failed": sum(1 for r in query_results if r["status"] == "FAIL"),
        "avg_latency": round(sum(r["latency_sec"] for r in query_results) / len(query_results), 2),
        "details": query_results
    },
    "extract_tests": {
        "total": len(extract_results),
        "passed": sum(1 for r in extract_results if r["status"] == "PASS"),
        "failed": sum(1 for r in extract_results if r["status"] == "FAIL"),
        "avg_latency": round(sum(r["latency_sec"] for r in extract_results) / len(extract_results), 2),
        "details": extract_results
    }
}

report_path = PROJECT_ROOT / "data" / "comprehensive_test_report.json"
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("\n" + "=" * 80)
print(f"ИТОГ ТЕСТИРОВАНИЯ ЗАПРОСОВ (QUERY): {summary['query_tests']['passed']}/{summary['query_tests']['total']} PASS (среднее время: {summary['query_tests']['avg_latency']}с)")
print(f"ИТОГ ТЕСТИРОВАНИЯ ИЗВЛЕЧЕНИЯ (EXTRACT): {summary['extract_tests']['passed']}/{summary['extract_tests']['total']} PASS (среднее время: {summary['extract_tests']['avg_latency']}с)")
print(f"Подробный отчет сохранен в: {report_path}")
print("=" * 80)
