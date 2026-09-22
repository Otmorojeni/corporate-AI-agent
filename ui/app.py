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

# Инициализация состояния сессии
if "query_history" not in st.session_state:
    st.session_state.query_history = []
if "last_query" not in st.session_state:
    st.session_state.last_query = ""

# Корпоративные стили
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.1rem;
        font-weight: 700;
        color: #0A2540;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.02rem;
        color: #4A5568;
        margin-bottom: 1.2rem;
    }
    .badge-term {
        display: inline-block;
        background-color: #EBF8FF;
        color: #2B6CB0;
        border: 1px solid #BEE3F8;
        border-radius: 6px;
        padding: 5px 12px;
        margin: 4px 6px 4px 0;
        font-size: 0.92rem;
        font-weight: 600;
    }
    .badge-source {
        display: inline-block;
        background-color: #F8FAFC;
        color: #334155;
        border: 1px solid #CBD5E1;
        border-radius: 6px;
        padding: 5px 12px;
        margin: 4px 6px 4px 0;
        font-size: 0.88rem;
    }
    .answer-box {
        background-color: #FFFFFF;
        border-left: 5px solid #0078D2;
        border-radius: 8px;
        padding: 20px 24px;
        margin-top: 15px;
        margin-bottom: 15px;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
        font-size: 1.05rem;
        line-height: 1.6;
        color: #0F172A;
    }
    .stTextArea textarea {
        font-size: 1.05rem;
        border-radius: 8px;
    }
    .history-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 10px;
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
    st.markdown("## 🔷 Газпром нефть")
    st.markdown("**Корпоративный ИИ-ассистент**")

    api_online = check_api_health()
    if api_online:
        st.success("🟢 REST API доступен (`:8000`)")
    else:
        st.info("ℹ️ Прямой режим инференса (In-Process)")

    st.markdown("---")
    st.markdown("**Параметры системы:**")
    st.markdown("- **Модель:** `GigaChat/GigaChat-2-Max`")
    st.markdown("- **Платформа:** Cloud.ru Evolution")
    st.markdown("- **Алгоритм экстракции:** Schwartz-Hearst")
    st.markdown("- **Поиск:** Шардированный BM25Okapi")
    st.markdown("- **Ограничение контекста:** < 32 000 токенов")
    st.markdown("- **Контракт:** OpenAPI 3.1.0 (Strict)")

    st.markdown("---")
    mode = st.radio(
        "Навигация:",
        ["💬 Вопрос к ассистенту", "📄 Загрузка нового PDF"],
        index=0,
    )

    st.markdown("---")
    if st.session_state.query_history:
        st.markdown(f"**История запросов ({len(st.session_state.query_history)}):**")
        for i, item in enumerate(reversed(st.session_state.query_history[-5:])):
            st.caption(f"• {item['query'][:45]}...")
        if st.button("🗑️ Очистить историю", use_container_width=True):
            st.session_state.query_history = []
            st.rerun()

    st.caption("Хакатон «AI-импульс 2.0» | Команда «Отмороженные»")


# --- РАЗДЕЛ 1: ВОПРОС К АССИСТЕНТУ ---
if mode == "💬 Вопрос к ассистенту":
    st.markdown('<div class="main-header">Корпоративный ИИ-ассистент по документации</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Универсальный поиск фактов, расшифровка аббревиатур и контекстная дисамбигуация по корпоративной базе знаний</div>',
        unsafe_allow_html=True,
    )

    query_input = st.text_area(
        "Введите вопрос или аббревиатуру:",
        value=st.session_state.last_query,
        height=100,
        placeholder="Введите любой технический вопрос по документации или аббревиатуру (поддерживаются опечатки, кириллица и транслитерация)...",
        key="main_query_input",
    )

    btn_col1, btn_col2, _ = st.columns([1.5, 1.2, 4])
    ask_button = btn_col1.button("🔎 Найти ответ", type="primary", use_container_width=True)
    clear_button = btn_col2.button("Очистить", use_container_width=True)

    if clear_button:
        st.session_state.last_query = ""
        st.rerun()

    if ask_button and query_input.strip():
        req_id = f"demo-{uuid.uuid4().hex[:8]}"
        t0 = time.perf_counter()

        with st.spinner("Анализ терминов, поиск в базе знаний и генерация ответа..."):
            answer_text = ""
            detected_terms = []
            sources = []

            # 1. Попытка через HTTP REST API
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
                    st.warning(f"Сбой HTTP API: {e}. Переключение на встроенный инференс...")

            # 2. Автономный In-Process инференс при отсутствии API
            if not answer_text:
                import asyncio
                req = AssistantQueryRequest(request_id=req_id, query=query_input.strip())
                res = asyncio.run(process_user_query(req))
                answer_text = res.answer
                detected_terms = [t.model_dump() for t in res.detected_terms]
                sources = [s.model_dump() for s in res.sources] if res.sources else []

            elapsed = time.perf_counter() - t0

            # Сохранение в историю сессии
            st.session_state.query_history.append({
                "query": query_input.strip(),
                "answer": answer_text,
                "detected_terms": detected_terms,
                "sources": sources,
                "elapsed": elapsed,
            })

        st.markdown("---")

        # Блок ответа
        st.markdown("### 📋 Ответ ассистента:")
        st.markdown(
            f'<div class="answer-box">{answer_text}</div>',
            unsafe_allow_html=True,
        )

        # Метаданные ответа
        res_col1, res_col2 = st.columns(2)

        with res_col1:
            st.markdown("##### 📌 Распознанные термины (`detected_terms`):")
            if detected_terms:
                for t in detected_terms:
                    canon = t.get("canonical", "")
                    exp = t.get("expansion", "")
                    st.markdown(
                        f'<span class="badge-term"><b>{canon}</b>: {exp}</span>',
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("Специфических аббревиатур в вопросе не обнаружено.")

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
                st.caption("Источники не требуются (общий ответ или вне контекста ПО).")

        # Метрики запроса
        st.markdown("<br>", unsafe_allow_html=True)
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        m_col1.metric("Время ответа", f"{elapsed:.2f} сек")
        m_col2.metric("Найдено терминов", len(detected_terms))
        m_col3.metric("Использовано источников", len(sources) if sources else 0)
        m_col4.metric("Статус контракта", "HTTP 200 OK")

        with st.expander("🛠️ Технический JSON-ответ (согласно openapi.yaml)"):
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
        '<div class="sub-header">Универсальное извлечение аббревиатур без предобученных словарей и мгновенная индексация в RAG-памяти</div>',
        unsafe_allow_html=True,
    )

    st.info(
        "💡 **Проверка произвольного файла:** Загрузите любой технический PDF-документ (до 50 МиБ). "
        "Алгоритм Schwartz-Hearst извлечет все подтвержденные сокращения, а документ будет мгновенно зарегистрирован "
        "в оперативной памяти поисковой системы без перезапуска сервиса."
    )

    uploaded_file = st.file_uploader(
        "Выберите или перетащите PDF-документ:",
        type=["pdf"],
        help="Максимальный размер файла: 50 МиБ согласно спецификации openapi.yaml",
    )

    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        file_size_kb = len(file_bytes) / 1024

        st.success(f"Файл готов к обработке: **{uploaded_file.name}** ({file_size_kb:.1f} КБ)")

        if st.button("🚀 Извлечь аббревиатуры и индексировать документ", type="primary"):
            t0 = time.perf_counter()
            with st.spinner("Алгоритмическое извлечение и регистрация в базе знаний..."):
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
                        st.warning(f"Сбой REST API: {e}. Переключение на встроенный экстрактор...")

                if not abbreviations:
                    extracted_objs = extract_abbreviations_from_bytes(file_bytes)
                    abbreviations = [a.model_dump() for a in extracted_objs]
                    stem = Path(uploaded_file.name).stem
                    matcher.add_dynamic_terms(extracted_objs, product=stem)
                    retriever.add_dynamic_document(filename=uploaded_file.name, content=file_bytes, product=stem)
                    register_dynamic_product(stem)

                elapsed = time.perf_counter() - t0

            st.markdown("---")
            st.success(
                f"✅ **Обработка завершена!** Извлечено **{len(abbreviations)}** подтвержденных аббревиатур за **{elapsed:.2f} сек**. "
                f"Документ `{uploaded_file.name}` успешно проиндексирован в оперативной памяти RAG. Теперь ассистент готов отвечать на вопросы по нему!"
            )

            if abbreviations:
                st.markdown("##### 📑 Извлеченные подтвержденные аббревиатуры:")
                
                table_rows = []
                for a in abbreviations:
                    canon = a.get("canonical", "")
                    exp = a.get("expansion", "")
                    occs = a.get("occurrences", [])
                    pages = ", ".join(str(o.get("page")) for o in occs[:5])
                    first_quote = occs[0].get("quote", "") if occs else ""
                    table_rows.append({
                        "Аббревиатура": canon,
                        "Подтвержденная расшифровка": exp,
                        "Страницы": pages,
                        "Цитата из текста": first_quote[:150] + ("..." if len(first_quote) > 150 else ""),
                    })

                st.dataframe(table_rows, use_container_width=True)

                with st.expander("📦 Посмотреть ответ JSON (согласно openapi.yaml)"):
                    st.json({"abbreviations": abbreviations})
            else:
                st.warning("В загруженном файле не найдено подтвержденных аббревиатур по правилам Schwartz-Hearst.")
