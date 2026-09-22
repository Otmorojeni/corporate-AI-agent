"""
Сквозной конвейер (Pipeline) обработки запроса пользователя.
Обеспечивает координацию:
1. Детектора продуктов.
2. Матчера и дисамбигуатора терминов.
3. Поисковика контекстных фрагментов (RAG).
4. Генеративного LLM-модуля.
5. Формирования ответа строго по контракту OpenAPI.
"""

import time
import logging
from typing import List, Set

from src.schemas import (
    AssistantQueryRequest,
    AssistantQueryResponse,
    DetectedTerm,
    SourceReference,
)
from src.core.product_detector import detect_products
from src.core.matcher import TermMatcher
from src.core.retriever import DocumentRetriever
from src.core.llm_client import LLMClient

logger = logging.getLogger("corporate_agent.pipeline")

# Синглтоны компонентов для мгновенной обработки запросов без повторной инициализации
matcher = TermMatcher()
retriever = DocumentRetriever()
llm_client = LLMClient()


async def process_user_query(req: AssistantQueryRequest) -> AssistantQueryResponse:
    """
    Обрабатывает входящий запрос сотрудника:
    1. Извлекает продукты и аббревиатуры.
    2. Выполняет контекстный поиск фактов в базе знаний.
    3. Генерирует фактологически заземленный ответ через LLM.
    4. Возвращает ответ строго по схеме OpenAPI.
    """
    start_total = time.perf_counter()
    query = req.query.strip()

    # 1. Распознавание упомянутых продуктов
    t0 = time.perf_counter()
    products = detect_products(query)
    t_det = (time.perf_counter() - t0) * 1000

    # 2. Нечеткий поиск аббревиатур и дисамбигуация
    t0 = time.perf_counter()
    detected_terms: List[DetectedTerm] = matcher.match_terms(query, products)
    t_match = (time.perf_counter() - t0) * 1000

    # 3. Поиск фрагментов базы знаний (RAG)
    t0 = time.perf_counter()
    context_chunks = retriever.retrieve(
        query=query,
        products=products,
        detected_terms=detected_terms,
        top_k=4
    )
    t_ret = (time.perf_counter() - t0) * 1000

    # Сбор уникальных источников строго по openapi.yaml
    sources: List[SourceReference] = []
    seen_sources: Set[tuple] = set()
    for c in context_chunks:
        doc_id = c.get("document_id")
        page_num = c.get("page")
        if doc_id and page_num:
            key = (doc_id, page_num)
            if key not in seen_sources:
                seen_sources.add(key)
                sources.append(SourceReference(document_id=doc_id, page=page_num))

    # 4. Генерация содержательного ответа через LLM
    t0 = time.perf_counter()
    answer = await llm_client.generate_answer(
        query=query,
        products=products,
        detected_terms=detected_terms,
        context_chunks=context_chunks,
    )
    t_llm = (time.perf_counter() - t0) * 1000

    total_ms = (time.perf_counter() - start_total) * 1000
    logger.info(
        "Req: %s | Prods: %s | Terms: %d | Chunks: %d | Time: %.1fms (det: %.1fms, match: %.1fms, rag: %.1fms, llm: %.1fms)",
        req.request_id,
        products,
        len(detected_terms),
        len(context_chunks),
        total_ms,
        t_det,
        t_match,
        t_ret,
        t_llm,
    )

    # 5. Проверка на off-topic или отказ:
    # Если в вопросе не было ни продуктов, ни аббревиатур, и модель сообщает, что вопрос вне темы
    # или не относится к корпоративному ПО, мы не возвращаем случайные фоновые источники
    is_off_topic_or_refusal = (
        not detected_terms and not products and (
            "только на вопросы" in answer.lower() or
            "только по" in answer.lower() or
            "только с вопросами" in answer.lower() or
            "корпоративный ассистент" in answer.lower() or
            "не относится" in answer.lower() or
            "не найдена" in answer.lower() or
            "не удалось найти" in answer.lower() or
            "уточните ваш вопрос" in answer.lower() or
            "уточнив его связь" in answer.lower() or
            "повтори свой вопрос" in answer.lower()
        )
    )
    if is_off_topic_or_refusal:
        sources = []

    # 6. Формирование валидного ответа
    return AssistantQueryResponse(
        request_id=req.request_id,
        answer=answer,
        detected_terms=detected_terms,
        sources=sources if sources else None,
    )
