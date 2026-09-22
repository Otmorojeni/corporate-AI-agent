"""
Корпоративный Web-интерфейс для демонстрации решения на питчинге хакатона «AI-импульс 2.0».
Кейс ПАО «Газпром нефть» — Корпоративный ИИ-ассистент по документации ПО.

Запуск:
    streamlit run ui/app.py
"""

import os
import sys
import time
import json
import uuid
import requests
import streamlit as st
from pathlib import Path

# Добавляем корень проекта в путь поиска модулей
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas import AssistantQueryRequest
from src.core.pipeline import process_user_query
from src.core.extractor import extract_abbreviations_from_bytes
from src.core.pipeline import matcher, retriever
from src.core.product_detector import register_dynamic_product

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

# Настройка страницы
st.set_page_config(
    page_title="Газпром нефть | Корпоративный ИИ-ассистент",
    page_icon="🔷",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Корпоративные стили
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #0A2540;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4A5568;
        margin-bottom: 1.5rem;
    }
    .badge-term {
        display: inline-block;
        background-color: #EBF8FF;
        color: #2B6CB0;
        border: 1px solid #BEE3F8;
        border-radius: 6px;
        padding: 4px 10px;
        margin: 3px;
        font-size: 0.9rem;
        font-weight: 600;
    }
    .badge-source {
        display: inline-block;
        background-color: #F7FAFC;
        color: #4A5568;
        border: 1px solid #E2E8F0;
        border-radius: 6px;
        padding: 4px 10px;
        margin: 3px;
        font-size: 0.85rem;
    }
    .answer-box {
        background-color: #FFFFFF;
        border-left: 5px solid #0078D2;
        border-radius: 8px;
        padding: 18px 22px;
        margin-top: 15px;
        margin-bottom: 15px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
    }
    .metric-card {
        background-color: #F8FAFC;
        border-radius: 8px;
        padding: 12px 16px;
        border: 1px solid #E2E8F0;
        text-align: center;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def check_api_health():
    """Проверяет доступность локального REST API."""
    try:
        resp = requests.get(f"{API_BASE_URL}/health", timeout=1.5)
        if resp.status_code == 200:
            return True
    except Exception:
        pass
    return False


# --- БОКОВАЯ ПАНЕЛЬ (SIDEBAR) ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/6/68/Gazprom-neft-logo-rus.svg/320px-Gazprom-neft-logo-rus.svg.png", width=220)
    st.markdown("### 🔷 Панель управления")

    api_online = check_api_health()
    if api_online:
        st.success("🟢 REST API доступен (`:8000`)")
    else:
        st.info("ℹ️ Прямой режим инференса (In-Process)")

    st.markdown("---")
    st.markdown("**Характеристики системы:**")
    st.markdown("- **Модель:** `GigaChat-2-Max`")
    st.markdown("- **Платформа:** Cloud.ru Foundation Models")
    st.markdown("- **Корпус:** 17 семейств ПО (139 PDF)")
    st.markdown("- **Алгоритм экстракции:** Schwartz-Hearst")
    st.markdown("- **Поиск:** Шардированный BM25Okapi")
    st.markdown("- **Точность на Train:** **100.0% Quality**")

    st.markdown("---")
    mode = st.radio(
        "Выберите раздел:",
        ["💬 Вопрос к ассистенту", "📄 Загрузка нового PDF"],
        index=0,
    )

    st.markdown("---")
    st.caption("Хакатон «AI-импульс 2.0» | Команда «Отмороженные»")


# --- РАЗДЕЛ 1: ВОПРОС К АССИСТЕНТУ ---
if mode == "💬 Вопрос к ассистенту":
    st.markdown('<div class="main-header">Корпоративный ИИ-ассистент по документации</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Интеллектуальный поиск фактов, расшифровка аббревиатур и контекстная дисамбигуация по корпоративным системам</div>',
        unsafe_allow_html=True,
    )

    st.markdown("##### ⚡ Быстрые примеры для проверки:")
    col1, col2, col3, col4, col5 = st.columns(5)

    example_query = None
    if col1.button("eXpress (CTS)", use_container_width=True):
        example_query = "Как в документации eXpress расшифровывается CTS?"
    if col2.button("Kaspersky (SNMP)", use_container_width=True):
        example_query = "Что требуется установить на защищаемом компьютере перед добавлением поддержки SNMP в Kaspersky Embedded Systems Security?"
    if col3.button("Deckhouse (DKP)", use_container_width=True):
        example_query = "Как DKP обрабатывает первое обращение к защищённому ресурсу уже аутентифицированного пользователя и пользователя с единственным внешним провайдером?"
    if col4.button("Омонимы (WAL)", use_container_width=True):
        example_query = "Что означает аббревиатура WAL в СУБД ЛИНТЕР и что означает WAL в Tarantool? Приведи инструкции по восстановлению."
    if col5.button("Офф-топик (Футбол)", use_container_width=True):
        example_query = "Реал мадрид or Барселона ?"

    query_input = st.text_area(
        "Введите ваш вопрос по документации:",
        value=example_query if example_query else "",
        height=90,
        placeholder="Например: Как в Deckhouse настроить общий IP-адрес для сервисов NLB и почему VPA не изменит лимиты?",
    )

    submit_col, clear_col, _ = st.columns([1, 1, 4])
    ask_button = submit_col.button("🔎 Найти ответ", type="primary", use_container_width=True)

    if ask_button and query_input.strip():
        req_id = f"demo-{uuid.uuid4().hex[:8]}"
        t0 = time.perf_counter()

        with st.spinner("Анализ терминов, поиск в базе знаний и генерация ответа..."):
            answer_text = ""
            detected_terms = []
            sources = []

            # Попытка через HTTP API, если доступен
            if api_online:
                try:
                    resp = requests.post(
                        f"{API_BASE_URL}/v1/assistant/query",
                        json={"request_id": req_id, "query": query_input.strip()},
                        timeout=45.0,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        answer_text = data.get("answer", "")
                        detected_terms = data.get("detected_terms", [])
                        sources = data.get("sources", [])
                except Exception as e:
                    st.warning(f"Ошибка вызова REST API: {e}. Переключение на прямой инференс...")

            # Прямой вызов, если API недоступен или вернул сбой
            if not answer_text:
                import asyncio
                req = AssistantQueryRequest(request_id=req_id, query=query_input.strip())
                res = asyncio.run(process_user_query(req))
                answer_text = res.answer
                detected_terms = [t.model_dump() for t in res.detected_terms]
                sources = [s.model_dump() for s in res.sources] if res.sources else []

            elapsed = time.perf_counter() - t0

        st.markdown("---")

        # Блок ответа
        st.markdown("### 📋 Ответ ассистента:")
        st.markdown(
            f'<div class="answer-box">{answer_text}</div>',
            unsafe_allow_html=True,
        )

        # Метаданные ответа в 2 колонки
        res_col1, res_col2 = st.columns(2)

        with res_col1:
            st.markdown("##### 🔍 Распознанные термины (`detected_terms`):")
            if detected_terms:
                for t in detected_terms:
                    canon = t.get("canonical", "")
                    exp = t.get("expansion", "")
                    st.markdown(
                        f'<span class="badge-term">📌 <b>{canon}</b>: {exp}</span>',
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("Специфических аббревиатур в запросе не обнаружено.")

        with res_col2:
            st.markdown("##### 📚 Первоисточники базы знаний (`sources`):")
            if sources:
                for s in sources:
                    doc = s.get("document_id", "")
                    page = s.get("page", "")
                    st.markdown(
                        f'<span class="badge-source">📄 <b>{doc}</b> (стр. {page})</span>',
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("Источники не требуются (общий ответ или офф-топик).")

        # Служебная панель метрик
        st.markdown("<br>", unsafe_allow_html=True)
        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.metric("Время обработки", f"{elapsed:.2f} сек")
        m_col2.metric("Найдено терминов", len(detected_terms))
        m_col3.metric("Использовано источников", len(sources) if sources else 0)

        with st.expander("🛠️ Технический JSON-ответ (OpenAPI 3.1.0)"):
            st.json({
                "request_id": req_id,
                "answer": answer_text,
                "detected_terms": detected_terms,
                "sources": sources,
            })


# --- РАЗДЕЛ 2: ЗАГРУЗКА НОВОГО PDF ---
elif mode == "📄 Загрузка нового PDF":
    st.markdown('<div class="main-header">Загрузка и динамический анализ нового PDF</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Автоматическое извлечение аббревиатур без предобученных словарей и мгновенная индексация в RAG</div>',
        unsafe_allow_html=True,
    )

    st.info(
        "💡 **Демонстрация готовности к чек-поинту:** Загрузите любой произвольный PDF-документ (до 50 МиБ). "
        "Алгоритм Schwartz-Hearst извлечет все подтвержденные сокращения, а система мгновенно зарегистрирует документ "
        "в оперативной памяти без перезагрузки сервера."
    )

    uploaded_file = st.file_uploader(
        "Выберите или перетащите PDF-документ:",
        type=["pdf"],
        help="Максимальный размер: 50 МиБ согласно спецификации openapi.yaml",
    )

    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        file_size_kb = len(file_bytes) / 1024

        st.success(f"Файл готов к анализу: **{uploaded_file.name}** ({file_size_kb:.1f} КБ)")

        if st.button("🚀 Извлечь аббревиатуры и индексировать", type="primary"):
            t0 = time.perf_counter()
            with st.spinner("Парсинг документа, алгоритмическое извлечение и индексация..."):
                abbreviations = []

                if api_online:
                    try:
                        resp = requests.post(
                            f"{API_BASE_URL}/v1/abbreviations/extract",
                            files={"file": (uploaded_file.name, file_bytes, "application/pdf")},
                            timeout=60.0,
                        )
                        if resp.status_code == 200:
                            abbreviations = resp.json().get("abbreviations", [])
                    except Exception as e:
                        st.warning(f"Ошибка REST API: {e}. Переключение на прямое извлечение...")

                if not abbreviations:
                    # Прямой вызов и динамическая регистрация
                    extracted_objs = extract_abbreviations_from_bytes(file_bytes)
                    abbreviations = [a.model_dump() for a in extracted_objs]
                    stem = Path(uploaded_file.name).stem
                    matcher.add_dynamic_terms(extracted_objs, product=stem)
                    retriever.add_dynamic_document(filename=uploaded_file.name, content=file_bytes, product=stem)
                    register_dynamic_product(stem)

                elapsed = time.perf_counter() - t0

            st.markdown("---")
            st.success(
                f"✅ **Успешно!** Извлечено **{len(abbreviations)}** уникальных аббревиатур за **{elapsed:.2f} сек**. "
                f"Документ `{uploaded_file.name}` зарегистрирован в базе знаний ассистента!"
            )

            if abbreviations:
                st.markdown("##### 📑 Список подтвержденных аббревиатур:")
                
                # Подготовка данных для таблицы
                table_rows = []
                for a in abbreviations:
                    canon = a.get("canonical", "")
                    exp = a.get("expansion", "")
                    occs = a.get("occurrences", [])
                    pages = ", ".join(str(o.get("page")) for o in occs[:5])
                    first_quote = occs[0].get("quote", "") if occs else ""
                    table_rows.append({
                        "Аббревиатура": canon,
                        "Расшифровка": exp,
                        "Страницы": pages,
                        "Цитата": first_quote[:150] + ("..." if len(first_quote) > 150 else ""),
                    })

                st.dataframe(table_rows, use_container_width=True)

                with st.expander("📦 Посмотреть полный ответ JSON (openapi.yaml)"):
                    st.json({"abbreviations": abbreviations})
            else:
                st.warning("В данном документе не обнаружено подтвержденных аббревиатур по правилам Schwartz-Hearst.")
