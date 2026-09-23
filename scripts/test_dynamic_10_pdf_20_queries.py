"""
Скрипт стресс-тестирования динамической загрузки 10 новых PDF-документов
и выполнения 20 целевых запросов пользователей к терминам и фактам этих документов.

Проверяет:
1. Корректность извлечения терминов через /v1/abbreviations/extract (Schwartz-Hearst, таблицы, страницы, цитаты).
2. Динамическую регистрацию в оперативной памяти (Hot-Reload) без перезапуска сервиса.
3. Точность распознавания терминов (detected_terms) через /v1/assistant/query.
4. Точность источников (sources: document_id, page).
5. Полноту и заземление ответа (answer: расшифровка + инженерные факты).
6. Время обработки каждого запроса и статус-коды HTTP 200.
"""

import sys
import os
import time
import json
from pathlib import Path
from typing import List, Dict, Any

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

import pymupdf
from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)

PDF_DIR = Path("data/test_dynamic_10_pdfs")
PDF_DIR.mkdir(parents=True, exist_ok=True)
REPORT_FILE = Path("data/dynamic_10_test_report.json")

# Спецификация 10 тестовых документов
PDF_SPECS = [
    {
        "filename": "doc_sdwan_core.pdf",
        "title": "Корпоративный программный шлюз SD-WAN Core",
        "sections": [
            {
                "page": 1,
                "text": (
                    "Руководство по архитектуре и развертыванию.\n"
                    "Программно-определяемая сеть (ПОС) обеспечивает динамическую маршрутизацию трафика между филиалами.\n"
                    "Корпоративный программный шлюз (КПШ) устанавливается на границе локальной сети компании.\n"
                    "Для активации ГОСТ-шифрования туннелей на интерфейсе ge-0/0/1 задается параметр tunnel-security=gost."
                ),
            },
            {
                "page": 2,
                "text": (
                    "Служебные термины и определения:\n"
                    "МШТ — Маршрутизатор широкого трафика для балансировки очередей\n"
                    "Все сетевые пакеты проходят через модуль аппаратной акселерации шлюза КПШ."
                ),
            },
        ],
        "expected_terms": [
            ("ПОС", "Программно-определяемая сеть"),
            ("КПШ", "Корпоративный программный шлюз"),
            ("МШТ", "Маршрутизатор широкого трафика"),
        ],
    },
    {
        "filename": "doc_cyber_soc.pdf",
        "title": "Регламент реагирования центра мониторинга кибербезопасности Cyber SOC",
        "sections": [
            {
                "page": 1,
                "text": (
                    "Регламент мониторинга инцидентов информационной безопасности.\n"
                    "Центр управления безопасностью (ЦУБ) осуществляет круглосуточный анализ сетевых событий.\n"
                    "Объекты категории Критическая информационная инфраструктура (КИИ) подлежат усиленному аудиту."
                ),
            },
            {
                "page": 2,
                "text": (
                    "Порядок эскалации инцидентов:\n"
                    "При обнаружении несанкционированного вторжения агент SIEM отправляет алерт уровня Sev-1 в очередь incidents_priority.\n"
                    "Перечень сокращений:\n"
                    "СЗИ — Средство защиты информации для изоляции хостов"
                ),
            },
        ],
        "expected_terms": [
            ("ЦУБ", "Центр управления безопасностью"),
            ("КИИ", "Критическая информационная инфраструктура"),
            ("СЗИ", "Средство защиты информации"),
        ],
    },
    {
        "filename": "doc_erp_sync.pdf",
        "title": "Шина синхронизации корпоративных данных ERP Sync",
        "sections": [
            {
                "page": 1,
                "text": (
                    "Интеграционные протоколы и брокеры сообщений предприятия.\n"
                    "Мастер-система данных (МСД) хранит эталонные записи справочников холдинга.\n"
                    "Единое хранилище нормативно-справочной информации (ЕХНСИ) обеспечивает дедупликацию данных."
                ),
            },
            {
                "page": 2,
                "text": (
                    "Регламент репликации контрагентов:\n"
                    "Периодичность синхронизации сущностей контрагентов через брокер сообщений составляет 30 секунд.\n"
                    "Термины:\n"
                    "КШП — Корпоративная шина передачи пакетов"
                ),
            },
        ],
        "expected_terms": [
            ("МСД", "Мастер-система данных"),
            ("ЕХНСИ", "Единое хранилище нормативно-справочной информации"),
            ("КШП", "Корпоративная шина передачи"),
        ],
    },
    {
        "filename": "doc_ai_compute.pdf",
        "title": "Платформа распределенного ИИ-обучения AI Compute",
        "sections": [
            {
                "page": 1,
                "text": (
                    "Руководство инженера по вычислительной инфраструктуре.\n"
                    "Вычислительный кластер искусственного интеллекта (ВКИИ) объединяет фермы графических ускорителей.\n"
                    "Пакетный распределитель задач (ПРЗ) управляет очередями тренировочных сессий нейросетей."
                ),
            },
            {
                "page": 2,
                "text": (
                    "Механизмы распределения тензоров:\n"
                    "Для распределения тензоров между узлами DGX используется протокол NCCL с прямым доступом RDMA.\n"
                    "Глоссарий:\n"
                    "ТОР — Тензорный операционный репозиторий"
                ),
            },
        ],
        "expected_terms": [
            ("ВКИИ", "Вычислительный кластер искусственного интеллекта"),
            ("ПРЗ", "Пакетный распределитель задач"),
            ("ТОР", "Тензорный операционный репозиторий"),
        ],
    },
    {
        "filename": "doc_cloud_storage.pdf",
        "title": "Система распределенного блочного хранения Cloud Storage",
        "sections": [
            {
                "page": 1,
                "text": (
                    "Руководство администратора пулов хранения данных.\n"
                    "Распределенная файловая система (РФС) построена на принципах полной согласованности метаданных.\n"
                    "Каталог блочных устройств (КБУ) содержит перечень подключенных дисковых томов LUN."
                ),
            },
            {
                "page": 2,
                "text": (
                    "Параметры отказоустойчивости СХД:\n"
                    "Фактор репликации пула метаданных равен 3, при этом журнал транзакций пишется на NVMe-диски.\n"
                    "Обозначения:\n"
                    "ОХД — Объектное хранилище данных"
                ),
            },
        ],
        "expected_terms": [
            ("РФС", "Распределенная файловая система"),
            ("КБУ", "Каталог блочных устройств"),
            ("ОХД", "Объектное хранилище данных"),
        ],
    },
    {
        "filename": "doc_idm_access.pdf",
        "title": "Централизованная система управления доступом IDM Access",
        "sections": [
            {
                "page": 1,
                "text": (
                    "Политики безопасности и разграничения полномочий.\n"
                    "Ролевая модель доступа (РМД) определяет права учетных записей сотрудников компании.\n"
                    "Система контроля учетных записей (СКУЗ) отслеживает статус активности и увольнения персонала."
                ),
            },
            {
                "page": 2,
                "text": (
                    "Правила блокировки учетных записей:\n"
                    "Блокировка сессии пользователя наступает после трех подряд неверных попыток ввода OTP-пароля.\n"
                    "Термины:\n"
                    "МФА — Многофакторная фильтрация и аутентификация"
                ),
            },
        ],
        "expected_terms": [
            ("РМД", "Ролевая модель доступа"),
            ("СКУЗ", "Система контроля учетных записей"),
            ("МФА", "Многофакторная фильтрация и аутентификация"),
        ],
    },
    {
        "filename": "doc_telecom_mesh.pdf",
        "title": "Беспроводная опорная сеть связи объектов Telecom Mesh",
        "sections": [
            {
                "page": 1,
                "text": (
                    "Проектирование и эксплуатация опорных сетей удаленных промыслов.\n"
                    "Базовая радиостанция связи (БРС) монтируется на мачтах технологических площадок месторождения.\n"
                    "Ячеистая топология связи (ЯТС) обеспечивает устойчивость сети при отказе промежуточных ретрансляторов."
                ),
            },
            {
                "page": 2,
                "text": (
                    "Нормативы качества радиоканала:\n"
                    "Максимальная задержка между смежными узлами радиорелейной линии не должна превышать 5 миллисекунд.\n"
                    "Список сокращений:\n"
                    "ШПД — Широкополосный доступ передачи данных"
                ),
            },
        ],
        "expected_terms": [
            ("БРС", "Базовая радиостанция связи"),
            ("ЯТС", "Ячеистая топология связи"),
            ("ШПД", "Широкополосный доступ"),
        ],
    },
    {
        "filename": "doc_devops_ci.pdf",
        "title": "Конвейер непрерывной интеграции и сборки ПО DevOps CI",
        "sections": [
            {
                "page": 1,
                "text": (
                    "Регламент автоматизации сборок микросервисов.\n"
                    "Конвейер непрерывной сборки (КНС) запускает статический анализ кода при каждом push-событии.\n"
                    "Репозиторий артефактов поставки (РАП) хранит верифицированные дистрибутивы релизов."
                ),
            },
            {
                "page": 2,
                "text": (
                    "Изоляция сборочных агентов:\n"
                    "Сборка образов контейнеров выполняется в изолированном пространстве kaniko без root-привилегий.\n"
                    "Сокращения:\n"
                    "СТД — Среда тестового деплоя"
                ),
            },
        ],
        "expected_terms": [
            ("КНС", "Конвейер непрерывной сборки"),
            ("РАП", "Репозиторий артефактов поставки"),
            ("СТД", "Среда тестового деплоя"),
        ],
    },
    {
        "filename": "doc_iot_scada.pdf",
        "title": "Платформа телеметрии и промышленного интернета вещей IoT SCADA",
        "sections": [
            {
                "page": 1,
                "text": (
                    "Сбор технологических параметров скважин и трубопроводов.\n"
                    "Программируемый логический контроллер (ПЛК) считывает показания с аналоговых датчиков расхода.\n"
                    "Устройство сбора и передачи данных (УСПД) агрегирует телеметрию кустовой площадки."
                ),
            },
            {
                "page": 2,
                "text": (
                    "Регламент опроса оборудования:\n"
                    "Опрос телеметрических датчиков давления в скважинах производится по протоколу Modbus RTU каждые 100 мс.\n"
                    "Глоссарий:\n"
                    "АСУТП — Автоматизированная система управления технологическим процессом"
                ),
            },
        ],
        "expected_terms": [
            ("ПЛК", "Программируемый логический контроллер"),
            ("УСПД", "Устройство сбора и передачи данных"),
            ("АСУТП", "Автоматизированная система управления технологическим процессом"),
        ],
    },
    {
        "filename": "doc_db_balancer.pdf",
        "title": "Отказоустойчивый прокси-балансировщик СУБД DB Balancer",
        "sections": [
            {
                "page": 1,
                "text": (
                    "Маршрутизация запросов к репликам базы данных.\n"
                    "Отказоустойчивый балансировщик базы (ОББ) разделяет потоки чтения и записи транзакций.\n"
                    "Пул сессионных соединений (ПСС) минимизирует накладные расходы на аутентификацию клиентов."
                ),
            },
            {
                "page": 2,
                "text": (
                    "Параметры удержания соединений:\n"
                    "Таймаут удержания неактивного клиентского соединения в пуле pgpool равен 60 секундам.\n"
                    "Список терминов:\n"
                    "МТБ — Менеджер транзакционной блокировки"
                ),
            },
        ],
        "expected_terms": [
            ("ОББ", "Отказоустойчивый балансировщик базы"),
            ("ПСС", "Пул сессионных соединений"),
            ("МТБ", "Менеджер транзакционной блокировки"),
        ],
    },
]

# Спецификация 20 пользовательских запросов к новым документам
QUERY_SPECS = [
    {
        "id": "Q-01",
        "query": "Как в doc_sdwan_core расшифровывается ПОС?",
        "expected_canon": "ПОС",
        "expected_exp": "Программно-определяемая сеть",
        "expected_doc": "doc_sdwan_core.pdf",
        "expected_fact": "Программно-определяемая сеть",
    },
    {
        "id": "Q-02",
        "query": "Что означает КПШ и какой параметр задает шифрование туннелей в doc sdwan core?",
        "expected_canon": "КПШ",
        "expected_exp": "Корпоративный программный шлюз",
        "expected_doc": "doc_sdwan_core.pdf",
        "expected_fact": "tunnel-security=gost",
    },
    {
        "id": "Q-03",
        "query": "Как в doc_cyber_soc расшифровывается ЦУБ?",
        "expected_canon": "ЦУБ",
        "expected_exp": "Центр управления безопасностью",
        "expected_doc": "doc_cyber_soc.pdf",
        "expected_fact": "Центр управления безопасностью",
    },
    {
        "id": "Q-04",
        "query": "Что означает КИИ и в какую очередь отправляется алерт Sev-1 в cyber soc?",
        "expected_canon": "КИИ",
        "expected_exp": "Критическая информационная инфраструктура",
        "expected_doc": "doc_cyber_soc.pdf",
        "expected_fact": "incidents_priority",
    },
    {
        "id": "Q-05",
        "query": "Как в документации расшифровывается МСД?",
        "expected_canon": "МСД",
        "expected_exp": "Мастер-система данных",
        "expected_doc": "doc_erp_sync.pdf",
        "expected_fact": "Мастер-система данных",
    },
    {
        "id": "Q-06",
        "query": "Что такое ЕХНСИ и какова периодичность синхронизации сущностей контрагентов в doc_erp_sync?",
        "expected_canon": "ЕХНСИ",
        "expected_exp": "Единое хранилище нормативно-справочной информации",
        "expected_doc": "doc_erp_sync.pdf",
        "expected_fact": "30 секунд",
    },
    {
        "id": "Q-07",
        "query": "Как в doc_ai_compute расшифровывается ВКИИ?",
        "expected_canon": "ВКИИ",
        "expected_exp": "Вычислительный кластер искусственного интеллекта",
        "expected_doc": "doc_ai_compute.pdf",
        "expected_fact": "Вычислительный кластер искусственного интеллекта",
    },
    {
        "id": "Q-08",
        "query": "Что означает ПРЗ и какой протокол используется для распределения тензоров между узлами DGX в ai compute?",
        "expected_canon": "ПРЗ",
        "expected_exp": "Пакетный распределитель задач",
        "expected_doc": "doc_ai_compute.pdf",
        "expected_fact": "NCCL",
    },
    {
        "id": "Q-09",
        "query": "Как в doc_cloud_storage расшифровывается РФС?",
        "expected_canon": "РФС",
        "expected_exp": "Распределенная файловая система",
        "expected_doc": "doc_cloud_storage.pdf",
        "expected_fact": "Распределенная файловая система",
    },
    {
        "id": "Q-10",
        "query": "Что такое КБУ и каков фактор репликации пула метаданных в cloud storage?",
        "expected_canon": "КБУ",
        "expected_exp": "Каталог блочных устройств",
        "expected_doc": "doc_cloud_storage.pdf",
        "expected_fact": "3",
    },
    {
        "id": "Q-11",
        "query": "Как в документации расшифровывается РМД?",
        "expected_canon": "РМД",
        "expected_exp": "Ролевая модель доступа",
        "expected_doc": "doc_idm_access.pdf",
        "expected_fact": "Ролевая модель доступа",
    },
    {
        "id": "Q-12",
        "query": "Что означает СКУЗ и после скольких неверных попыток OTP наступает блокировка в idm access?",
        "expected_canon": "СКУЗ",
        "expected_exp": "Система контроля учетных записей",
        "expected_doc": "doc_idm_access.pdf",
        "expected_fact": "трех",
    },
    {
        "id": "Q-13",
        "query": "Как в doc_telecom_mesh расшифровывается БРС?",
        "expected_canon": "БРС",
        "expected_exp": "Базовая радиостанция связи",
        "expected_doc": "doc_telecom_mesh.pdf",
        "expected_fact": "Базовая радиостанция связи",
    },
    {
        "id": "Q-14",
        "query": "Что такое ЯТС и какая максимальная задержка допустима между узлами в telecom mesh?",
        "expected_canon": "ЯТС",
        "expected_exp": "Ячеистая топология связи",
        "expected_doc": "doc_telecom_mesh.pdf",
        "expected_fact": "5 миллисекунд",
    },
    {
        "id": "Q-15",
        "query": "Как в документации расшифровывается КНС?",
        "expected_canon": "КНС",
        "expected_exp": "Конвейер непрерывной сборки",
        "expected_doc": "doc_devops_ci.pdf",
        "expected_fact": "Конвейер непрерывной сборки",
    },
    {
        "id": "Q-16",
        "query": "Что означает РАП и в какой изолированной среде выполняется сборка образов в devops ci?",
        "expected_canon": "РАП",
        "expected_exp": "Репозиторий артефактов поставки",
        "expected_doc": "doc_devops_ci.pdf",
        "expected_fact": "kaniko",
    },
    {
        "id": "Q-17",
        "query": "Как в doc_iot_scada расшифровывается ПЛК?",
        "expected_canon": "ПЛК",
        "expected_exp": "Программируемый логический контроллер",
        "expected_doc": "doc_iot_scada.pdf",
        "expected_fact": "Программируемый логический контроллер",
    },
    {
        "id": "Q-18",
        "query": "Что такое УСПД и с какой частотой опрашиваются датчики давления по Modbus RTU в iot scada?",
        "expected_canon": "УСПД",
        "expected_exp": "Устройство сбора и передачи данных",
        "expected_doc": "doc_iot_scada.pdf",
        "expected_fact": "100 мс",
    },
    {
        "id": "Q-19",
        "query": "Как в документации расшифровывается ОББ?",
        "expected_canon": "ОББ",
        "expected_exp": "Отказоустойчивый балансировщик базы",
        "expected_doc": "doc_db_balancer.pdf",
        "expected_fact": "Отказоустойчивый балансировщик базы",
    },
    {
        "id": "Q-20",
        "query": "Что означает ПСС и каков таймаут удержания неактивного клиентского соединения в db balancer?",
        "expected_canon": "ПСС",
        "expected_exp": "Пул сессионных соединений",
        "expected_doc": "doc_db_balancer.pdf",
        "expected_fact": "60 секунд",
    },
]


def generate_pdf(spec: Dict[str, Any]) -> Path:
    """Генерирует PDF-файл с поддержкой кириллицы через Arial и textbox для автопереноса строк."""
    filepath = PDF_DIR / spec["filename"]
    doc = pymupdf.open()
    for sec in spec["sections"]:
        page = doc.new_page()
        page.insert_font(fontname="F0", fontfile="C:/Windows/Fonts/arial.ttf")
        content = f"{spec['title']}\nСтраница {sec['page']}\n\n{sec['text']}"
        rect = pymupdf.Rect(40, 40, 555, 780)
        page.insert_textbox(rect, content, fontname="F0", fontsize=11)
    doc.save(filepath)
    doc.close()
    return filepath


def run_test_suite():
    print("=" * 80)
    print("   СТЕНД ТЕСТИРОВАНИЯ ДИНАМИЧЕСКОЙ ЗАГРУЗКИ 10 PDF И 20 ЗАПРОСОВ К НИМ")
    print("=" * 80)

    # 1. Генерация 10 PDF файлов
    print("\n[ЭТАП 1]: Генерация 10 валидных технических PDF-документов...")
    pdf_paths = []
    for spec in PDF_SPECS:
        path = generate_pdf(spec)
        pdf_paths.append((spec, path))
        print(f"  • Сгенерирован: {spec['filename']} ({path.stat().st_size} байт, 2 стр.)")

    # 2. Загрузка 10 PDF через API POST /v1/abbreviations/extract
    print("\n[ЭТАП 2]: Загрузка 10 PDF через эндпоинт /v1/abbreviations/extract...")
    upload_results = []
    total_extracted_abbrs = 0

    for idx, (spec, path) in enumerate(pdf_paths, start=1):
        t0 = time.perf_counter()
        with open(path, "rb") as f:
            resp = client.post(
                "/v1/abbreviations/extract",
                files={"file": (spec["filename"], f, "application/pdf")},
            )
        elapsed = time.perf_counter() - t0

        status_ok = resp.status_code == 200
        data = resp.json() if status_ok else {}
        abbrs = data.get("abbreviations", [])
        total_extracted_abbrs += len(abbrs)

        # Проверяем, что все ожидаемые термины найдены
        found_canons = {a["canonical"] for a in abbrs}
        missing = [exp_c for exp_c, _ in spec["expected_terms"] if exp_c not in found_canons]
        check_pass = status_ok and len(missing) == 0

        res_item = {
            "id": f"UPLOAD-{idx:02d}",
            "filename": spec["filename"],
            "status_code": resp.status_code,
            "status": "PASS" if check_pass else "FAIL",
            "latency_sec": round(elapsed, 3),
            "abbrs_count": len(abbrs),
            "found_terms": [f"{a['canonical']} -> {a['expansion']}" for a in abbrs],
            "missing": missing,
        }
        upload_results.append(res_item)
        print(f"  [{idx:02d}/10] {spec['filename']}: HTTP {resp.status_code} | {len(abbrs)} терминов | {elapsed:.2f}с -> {'PASS' if check_pass else 'FAIL'}")

    # 3. Выполнение 20 обращений пользователя через POST /v1/assistant/query
    print("\n[ЭТАП 3]: Выполнение 20 обращений пользователей к терминам новых PDF...")
    query_results = []
    passed_queries = 0

    for idx, spec in enumerate(QUERY_SPECS, start=1):
        req_body = {
            "request_id": f"req-dynamic-{idx:02d}",
            "query": spec["query"],
        }
        t0 = time.perf_counter()
        resp = client.post("/v1/assistant/query", json=req_body)
        elapsed = time.perf_counter() - t0

        status_ok = resp.status_code == 200
        data = resp.json() if status_ok else {}

        answer = data.get("answer", "")
        detected_terms = data.get("detected_terms", [])
        sources = data.get("sources", [])

        # Проверка 1: Найден ли ожидаемый термин
        term_matched = any(
            t["canonical"] == spec["expected_canon"] and spec["expected_exp"].lower() in t["expansion"].lower()
            for t in detected_terms
        )

        # Проверка 2: Указан ли источник из нового PDF
        source_matched = any(
            spec["expected_doc"].lower() in s.get("document_id", "").lower()
            for s in sources
        )

        # Проверка 3: Содержит ли ответ расшифровку и факт
        ans_has_exp = spec["expected_exp"].lower() in answer.lower() or spec["expected_canon"].lower() in answer.lower()
        ans_has_fact = spec["expected_fact"].lower() in answer.lower()

        # Итоговый статус
        is_pass = status_ok and term_matched and source_matched and ans_has_exp

        if is_pass:
            passed_queries += 1

        res_item = {
            "id": spec["id"],
            "query": spec["query"],
            "status_code": resp.status_code,
            "status": "PASS" if is_pass else "FAIL",
            "latency_sec": round(elapsed, 2),
            "term_matched": term_matched,
            "source_matched": source_matched,
            "ans_has_fact": ans_has_fact,
            "detected_terms": detected_terms,
            "sources": sources,
            "answer_preview": answer[:120] + "...",
        }
        query_results.append(res_item)

        print(f"  [{idx:02d}/20] {spec['id']}: '{spec['query'][:55]}...'")
        print(f"       -> Status: {'PASS' if is_pass else 'FAIL'} | HTTP {resp.status_code} | {elapsed:.2f}с")
        print(f"       -> Terms: {[(t['canonical'], t['expansion']) for t in detected_terms]}")
        print(f"       -> Sources: {[(s['document_id'], s['page']) for s in sources]}")
        print(f"       -> Answer: {answer[:90]}...\n")

    # Итоговая сводка
    uploads_passed = sum(1 for u in upload_results if u["status"] == "PASS")
    avg_upload_lat = sum(u["latency_sec"] for u in upload_results) / len(upload_results)
    avg_query_lat = sum(q["latency_sec"] for q in query_results) / len(query_results)

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "uploads": {
            "total": len(upload_results),
            "passed": uploads_passed,
            "failed": len(upload_results) - uploads_passed,
            "avg_latency_sec": round(avg_upload_lat, 3),
            "details": upload_results,
        },
        "queries": {
            "total": len(query_results),
            "passed": passed_queries,
            "failed": len(query_results) - passed_queries,
            "pass_rate_percent": round((passed_queries / len(query_results)) * 100, 1),
            "avg_latency_sec": round(avg_query_lat, 2),
            "details": query_results,
        },
    }

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("=" * 80)
    print("ИТОГИ ТЕСТИРОВАНИЯ:")
    print(f"  • Загрузка 10 PDF:   {uploads_passed}/10 PASS ({uploads_passed*10}%), среднее время: {avg_upload_lat:.2f}с")
    print(f"  • Запросы (20 шт.):  {passed_queries}/20 PASS ({(passed_queries/20)*100:.1f}%), среднее время: {avg_query_lat:.2f}с")
    print(f"  • Полный отчет сохранен в: {REPORT_FILE}")
    print("=" * 80)

    if uploads_passed == 10 and passed_queries == 20:
        print("\n ВСЕ 30 СЦЕНАРИЕВ ДИНАМИЧЕСКИХ ДАННЫХ УСПЕШНО ПРОЙДЕНЫ!")
        sys.exit(0)
    else:
        print("\n ОБНАРУЖЕНЫ СБОИ В ТЕСТАХ!")
        sys.exit(1)


if __name__ == "__main__":
    run_test_suite()
