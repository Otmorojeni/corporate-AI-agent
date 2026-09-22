import re
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from rank_bm25 import BM25Okapi
from src.schemas import DetectedTerm
from src.config import settings

CHUNKS_FILE = settings.CHUNKS_FILE


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
    return [w.lower() for w in re.findall(r"[a-zA-Zа-яА-Я0-9_-]+", text)]


class DocumentRetriever:
    def __init__(self, chunks_file: Optional[Path] = None):
        self.chunks_file = chunks_file or CHUNKS_FILE
        self.chunks_by_product: Dict[str, List[Dict]] = {}
        self.bm25_by_product: Dict[str, BM25Okapi] = {}
        self.all_chunks: List[Dict] = []
        self.all_bm25: Optional[BM25Okapi] = None
        self._load_and_index()

    def _load_and_index(self):
        if not self.chunks_file.exists():
            # Если файл индекса еще не создан, но папка corpus доступна, создаем автоматически
            corpus_dir = settings.CORPUS_DIR
            if corpus_dir.exists():
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

        # Формируем расширенный поисковый запрос
        query_words = tokenize_text(query)
        expanded_words = list(query_words)

        # Добавляем русско-английские соответствия
        for w in query_words:
            if w in RU_EN_TECHNICAL_EXPANSIONS:
                expanded_words.extend(RU_EN_TECHNICAL_EXPANSIONS[w])

        # Добавляем слова из расшифровок найденных терминов
        if detected_terms:
            for term in detected_terms:
                exp_words = tokenize_text(term.expansion)
                expanded_words.extend(exp_words)

        results: List[Tuple[float, Dict]] = []

        # 1. Если продукты определены, ищем внутри соответствующих индексов
        target_products = [p for p in (products or []) if p in self.bm25_by_product]

        if target_products:
            # Если упомянуто несколько продуктов (например, Linter и Tarantool),
            # выделяем квоту чанков на каждый продукт
            per_prod_k = max(2, top_k // len(target_products)) if len(target_products) > 1 else top_k
            
            for prod in target_products:
                prod_results = []
                bm25 = self.bm25_by_product[prod]
                chunks = self.chunks_by_product[prod]
                scores = bm25.get_scores(expanded_words)

                # Бустим совпадения точных ключевых слов
                for idx, score in enumerate(scores):
                    chunk = chunks[idx]
                    chunk_text = chunk["text"]
                    chunk_text_lower = chunk_text.lower()
                    
                    boost = 0.0
                    if detected_terms:
                        for term in detected_terms:
                            if term.canonical in chunk_text:
                                boost += 3.0
                            if term.expansion.lower() in chunk_text_lower:
                                boost += 5.0
                                
                    final_score = float(score) + boost
                    prod_results.append((final_score, chunk))
                
                prod_results.sort(key=lambda x: x[0], reverse=True)
                
                # Добавляем лучшие чанки данного продукта
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
            # Если продукт не определен, ищем по всему корпусу
            if self.all_bm25 and self.all_chunks:
                scores = self.all_bm25.get_scores(expanded_words)
                for idx, score in enumerate(scores):
                    chunk = self.all_chunks[idx]
                    results.append((float(score), chunk))

        # Сортируем по убыванию релевантности
        results.sort(key=lambda x: x[0], reverse=True)

        # Дедуплицируем чанки с одной страницы
        unique_chunks = []
        seen = set()
        for score, chunk in results:
            key = (chunk["document_id"], chunk["page"])
            if key not in seen:
                seen.add(key)
                unique_chunks.append(chunk)
            if len(unique_chunks) >= top_k:
                break

        return unique_chunks
