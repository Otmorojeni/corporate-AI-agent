"""
Модуль полнотекстового поиска (RAG) по корпусу документации 17 программных продуктов.
Реализует:
1. Шардированный BM25Okapi поиск с привязкой к document_id и page.
2. Кросс-языковое техническое расширение запросов (RU -> EN).
3. Квотирование чанков при одновременном упоминании нескольких продуктов.
4. Быстрый двухэтапный скоринг (BM25 топ-50 + точный бустинг терминов).
"""

import heapq
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pymupdf
from rank_bm25 import BM25Okapi

from src.schemas import DetectedTerm
from src.config import settings

logger = logging.getLogger(__name__)

# Предварительно скомпилированная регулярка токенизации
RE_TOKEN = re.compile(r"[a-zA-Zа-яА-Я0-9_-]+")

# Словарь русско-английских соответствий для поиска в англоязычных разделах документации
RU_EN_TECHNICAL_EXPANSIONS = {
    "восстановить": ["restore", "recovery"],
    "восстановление": ["restore", "recovery"],
    "памяти": ["memory", "ram"],
    "память": ["memory", "ram"],
    "потери": ["lost", "loss"],
    "потеря": ["lost", "loss"],
    "журнал": ["log", "logging"],
    "журнала": ["log", "logging"],
    "хранилище": ["storage"],
    "запрос": ["request", "query"],
    "данные": ["data"],
    "пользователь": ["user"],
    "пользователя": ["user"],
    "настройка": ["config", "configuration", "settings"],
    "настроить": ["config", "configure", "set"],
    "аутентификация": ["authentication", "auth"],
    "провайдер": ["provider"],
    "установить": ["install", "setup"],
    "установка": ["install", "installation"],
    "поддержка": ["support"],
    "репликация": ["replication", "replica"],
    "лимиты": ["limits", "limit"],
    "ресурсы": ["resources", "resource"],
}


def tokenize_text(text: str) -> List[str]:
    """Разбивает текст на строчные токены для BM25."""
    return [w.lower() for w in RE_TOKEN.findall(text)]


class DocumentRetriever:
    """
    Класс управления RAG-индексами и поиска контекста по базе знаний.
    """

    def __init__(self, chunks_file: Optional[Path] = None):
        self.chunks_file = chunks_file or settings.CHUNKS_FILE
        self.chunks_by_product: Dict[str, List[Dict]] = {}
        self.bm25_by_product: Dict[str, BM25Okapi] = {}
        self.all_chunks: List[Dict] = []
        self.all_bm25: Optional[BM25Okapi] = None
        self._load_and_index()

    def _load_and_index(self) -> None:
        """Загружает чанки и строит BM25 индексы."""
        if not self.chunks_file.exists():
            corpus_dir = settings.CORPUS_DIR
            if corpus_dir.exists():
                logger.info("Файл чанков отсутствует. Запуск автоматической индексации...")
                import importlib
                rag_mod = importlib.import_module("scripts.02_build_rag_index")
                rag_mod.build_corpus_chunks()
            else:
                return

        with open(self.chunks_file, "r", encoding="utf-8") as f:
            self.chunks_by_product = json.load(f)

        for prod, chunks in self.chunks_by_product.items():
            if not chunks:
                continue
            tokenized_corpus = [tokenize_text(c["text"]) for c in chunks]
            self.bm25_by_product[prod] = BM25Okapi(tokenized_corpus)
            self.all_chunks.extend(chunks)

        if self.all_chunks:
            all_tokenized = [tokenize_text(c["text"]) for c in self.all_chunks]
            self.all_bm25 = BM25Okapi(all_tokenized)

    def add_dynamic_document(self, filename: str, content: bytes, product: Optional[str] = None) -> int:
        """
        Динамически парсит загруженный PDF-файл в памяти,
        разбивает на чанки и мгновенно переиндексирует BM25 без перезапуска сервиса.
        Возвращает количество добавленных чанков.
        """
        try:
            doc = pymupdf.open(stream=content, filetype="pdf")
        except Exception as e:
            logger.warning("Failed to open PDF stream for dynamic indexing: %s", e)
            return 0

        prod_key = product or Path(filename).stem.lower()
        rel_doc_id = filename

        new_chunks: List[Dict] = []
        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            raw_text = doc[page_idx].get_text("text")
            if not raw_text:
                continue
            lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
            cleaned = "\n".join(lines)
            if len(cleaned) < 40:
                continue

            if len(cleaned) > 2500:
                mid = len(cleaned) // 2
                split_pos = cleaned.find("\n", mid)
                if split_pos == -1:
                    split_pos = mid
                p1 = cleaned[:split_pos].strip()
                p2 = cleaned[split_pos:].strip()
                if len(p1) >= 40:
                    new_chunks.append({"document_id": rel_doc_id, "page": page_num, "text": p1})
                if len(p2) >= 40:
                    new_chunks.append({"document_id": rel_doc_id, "page": page_num, "text": p2})
            else:
                new_chunks.append({"document_id": rel_doc_id, "page": page_num, "text": cleaned})

        if not new_chunks:
            return 0

        # Добавляем в общий список чанков и продуктовый список
        self.all_chunks.extend(new_chunks)
        self.chunks_by_product.setdefault(prod_key, []).extend(new_chunks)

        # Мгновенная переиндексация BM25 для данного продукта
        prod_tokenized = [t for t in (tokenize_text(c["text"]) for c in self.chunks_by_product[prod_key]) if t]
        if prod_tokenized and any(len(doc_tokens) > 0 for doc_tokens in prod_tokenized):
            try:
                self.bm25_by_product[prod_key] = BM25Okapi(prod_tokenized)
            except Exception as e:
                logger.warning("Failed to build product BM25 for '%s': %s", prod_key, e)

        # Мгновенная переиндексация глобального BM25
        all_tokenized = [t for t in (tokenize_text(c["text"]) for c in self.all_chunks) if t]
        if all_tokenized and any(len(doc_tokens) > 0 for doc_tokens in all_tokenized):
            try:
                self.all_bm25 = BM25Okapi(all_tokenized)
            except Exception as e:
                logger.warning("Failed to build global BM25: %s", e)

        logger.info(
            "Dynamically indexed %d chunks from '%s' under product '%s' (total chunks now: %d)",
            len(new_chunks),
            filename,
            prod_key,
            len(self.all_chunks),
        )
        return len(new_chunks)

    def retrieve(
        self,
        query: str,
        products: Optional[List[str]] = None,
        detected_terms: Optional[List[DetectedTerm]] = None,
        top_k: int = 4,
    ) -> List[Dict]:
        """
        Ищет наиболее релевантные фрагменты документации (чанки)
        с фильтрацией по продукту и гибридным бустингом.
        """
        if not self.chunks_by_product:
            return []

        # 1. Формирование расширенного поискового запроса
        query_words = tokenize_text(query)
        expanded_words = list(query_words)

        for w in query_words:
            if w in RU_EN_TECHNICAL_EXPANSIONS:
                expanded_words.extend(RU_EN_TECHNICAL_EXPANSIONS[w])

        if detected_terms:
            for term in detected_terms:
                expanded_words.extend(tokenize_text(term.expansion))

        results: List[Tuple[float, Dict]] = []

        # 2. Определение области поиска
        target_products = [p for p in (products or []) if p in self.bm25_by_product]

        if target_products:
            # Справедливое квотирование чанков при нескольких продуктах
            per_prod_k = max(2, top_k // len(target_products)) if len(target_products) > 1 else top_k

            for prod in target_products:
                bm25 = self.bm25_by_product[prod]
                chunks = self.chunks_by_product[prod]
                scores = bm25.get_scores(expanded_words)

                # ОПТИМИЗАЦИЯ: выбираем топ-50 кандидатов по базовому скору BM25 через кучу
                # вместо дорогого полного прохода по всем чанкам с вызовом .lower()
                num_candidates = min(50, len(chunks))
                top_candidates = heapq.nlargest(num_candidates, enumerate(scores), key=lambda x: x[1])

                prod_results: List[Tuple[float, Dict]] = []
                for idx, base_score in top_candidates:
                    chunk = chunks[idx]
                    chunk_text = chunk["text"]
                    chunk_lower = chunk_text.lower()

                    boost = 0.0
                    if detected_terms:
                        for term in detected_terms:
                            if term.canonical in chunk_text:
                                boost += 3.0
                            if term.expansion.lower() in chunk_lower:
                                boost += 5.0

                    final_score = float(base_score) + boost
                    prod_results.append((final_score, chunk))

                prod_results.sort(key=lambda x: x[0], reverse=True)

                seen_prod_pages = set()
                prod_added = 0
                for score, chunk in prod_results:
                    key = (chunk["document_id"], chunk["page"])
                    if key not in seen_prod_pages:
                        seen_prod_pages.add(key)
                        results.append((score, chunk))
                        prod_added += 1
                    if prod_added >= per_prod_k:
                        break
        else:
            # Если продукт не указан:
            if self.all_bm25 and self.all_chunks:
                if detected_terms:
                    # 1. Если есть подтвержденные термины (напр. "Что такое DKP?"),
                    # ищем по всей базе знаний с бустингом терминов
                    scores = self.all_bm25.get_scores(expanded_words)
                    num_candidates = min(50, len(self.all_chunks))
                    top_candidates = heapq.nlargest(num_candidates, enumerate(scores), key=lambda x: x[1])
                    for idx, score in top_candidates:
                        chunk = self.all_chunks[idx]
                        chunk_text = chunk["text"]
                        chunk_lower = chunk_text.lower()
                        boost = 0.0
                        for term in detected_terms:
                            if term.canonical in chunk_text:
                                boost += 3.0
                            if term.expansion.lower() in chunk_lower:
                                boost += 5.0
                        results.append((float(score) + boost, chunk))
                else:
                    # 2. Если нет ни продуктов, ни аббревиатур:
                    # Фильтруем стоп-слова и союзы, требуем минимальный порог релевантности
                    from src.core.matcher import STOP_WORDS
                    content_words = [w for w in query_words if len(w) >= 3 and w.upper() not in STOP_WORDS]
                    if content_words:
                        scores = self.all_bm25.get_scores(content_words)
                        num_candidates = min(50, len(self.all_chunks))
                        top_candidates = heapq.nlargest(num_candidates, enumerate(scores), key=lambda x: x[1])
                        for idx, score in top_candidates:
                            # Порог релевантности: совпадение должно быть существенным
                            if score >= 10.0:
                                results.append((float(score), self.all_chunks[idx]))

        results.sort(key=lambda x: x[0], reverse=True)

        # Дедупликация чанков с одной и той же страницы
        unique_chunks: List[Dict] = []
        seen_pages = set()
        for _, chunk in results:
            key = (chunk["document_id"], chunk["page"])
            if key not in seen_pages:
                seen_pages.add(key)
                unique_chunks.append(chunk)
            if len(unique_chunks) >= top_k:
                break

        return unique_chunks
