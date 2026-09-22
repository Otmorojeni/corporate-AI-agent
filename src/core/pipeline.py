from typing import List
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

# Синглтоны компонентов для мгновенной обработки запросов без повторной загрузки
matcher = TermMatcher()
retriever = DocumentRetriever()
llm_client = LLMClient()


async def process_user_query(req: AssistantQueryRequest) -> AssistantQueryResponse:
    query = req.query.strip()
    
    # 1. Распознавание упомянутых продуктов (из 17 продуктовых семейств)
    products = detect_products(query)
    
    # 2. Нечеткий поиск аббревиатур с учетом опечаток и дисамбигуацией по продукту
    detected_terms: List[DetectedTerm] = matcher.match_terms(query, products)
    
    # 3. Поиск фрагментов базы знаний (RAG)
    context_chunks = retriever.retrieve(
        query=query,
        products=products,
        detected_terms=detected_terms,
        top_k=4
    )
    
    # Формируем список уникальных источников strictly по контракту openapi.yaml
    sources: List[SourceReference] = []
    seen_sources = set()
    for c in context_chunks:
        doc_id = c.get("document_id")
        page_num = c.get("page")
        if doc_id and page_num:
            key = (doc_id, page_num)
            if key not in seen_sources:
                seen_sources.add(key)
                sources.append(SourceReference(document_id=doc_id, page=page_num))
    
    # 4. Генерация содержательного ответа через LLM на основе найденных фактов
    answer = await llm_client.generate_answer(
        query=query,
        products=products,
        detected_terms=detected_terms,
        context_chunks=context_chunks,
    )
    
    # 5. Возврат строго по контракту openapi.yaml
    return AssistantQueryResponse(
        request_id=req.request_id,
        answer=answer,
        detected_terms=detected_terms,
        sources=sources if sources else None,
    )
