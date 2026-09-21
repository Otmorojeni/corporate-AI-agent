from typing import List
from src.schemas import (
    AssistantQueryRequest,
    AssistantQueryResponse,
    DetectedTerm,
    SourceReference,
)
from src.core.product_detector import detect_products
from src.core.matcher import TermMatcher
from src.core.llm_client import LLMClient

# Синглтоны компонентов для быстрой работы без повторной загрузки
matcher = TermMatcher()
llm_client = LLMClient()


async def process_user_query(req: AssistantQueryRequest) -> AssistantQueryResponse:
    query = req.query.strip()
    
    # 1. Распознавание упомянутых продуктов (из 17 продуктовых семейств)
    products = detect_products(query)
    
    # 2. Нечеткий поиск аббревиатур с учетом опечаток и дисамбигуацией по продукту
    detected_terms: List[DetectedTerm] = matcher.match_terms(query, products)
    
    # 3. Поиск фрагментов базы знаний (RAG)
    # Если Участник 1 предоставит retriever, он подключится сюда
    context_chunks = []
    sources: List[SourceReference] = []
    
    # 4. Генерация содержательного ответа через LLM
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
