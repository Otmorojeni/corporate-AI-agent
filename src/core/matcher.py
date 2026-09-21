import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from rapidfuzz import fuzz
from src.schemas import DetectedTerm
from src.config import settings

# Простая таблица транслитерации для аббревиатур (русский <-> английский)
RU_TO_EN_MAP = {
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'E',
    'Ж': 'ZH', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
    'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
    'Ф': 'F', 'Х': 'H', 'Ц': 'TS', 'Ч': 'CH', 'Ш': 'SH', 'Щ': 'SCH',
    'Ы': 'Y', 'Э': 'E', 'Ю': 'YU', 'Я': 'YA'
}

def transliterate_acronym(text: str) -> str:
    """Транслитерирует русские буквы в латинские для поиска аббревиатур (ВПА -> VPA, СНМП -> SNMP)."""
    # Специфические частые подстановки
    custom = {
        'ВПА': 'VPA', 'НЛБ': 'NLB', 'ДКП': 'DKP', 'СНМП': 'SNMP', 
        'СТС': 'CTS', 'ВАЛ': 'WAL', 'УГ': 'UG', 'КЕСС': 'KESS'
    }
    upper = text.upper()
    if upper in custom:
        return custom[upper]
    res = []
    for ch in upper:
        res.append(RU_TO_EN_MAP.get(ch, ch))
    return "".join(res)


class TermMatcher:
    def __init__(self, terms_file: Optional[Path] = None):
        self.terms_file = terms_file or settings.TERMS_FILE
        self.terms_by_product: Dict[str, List[Dict]] = {}
        self.all_terms: List[Dict] = []
        self.canonical_index: Dict[str, List[Dict]] = {}
        self.load_terms()

    def load_terms(self):
        """Загружает словарь terms.jsonl в память."""
        self.terms_by_product = {}
        self.all_terms = []
        self.canonical_index = {}

        if not self.terms_file.exists():
            # Если файл еще не создан Участником 1, используем базовые начальные записи
            self._load_seed_terms()
            return

        with open(self.terms_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    self.all_terms.append(entry)
                    prod = entry.get("product", "general")
                    self.terms_by_product.setdefault(prod, []).append(entry)
                    
                    canon = entry.get("canonical", "").strip().upper()
                    if canon:
                        self.canonical_index.setdefault(canon, []).append(entry)
                except json.JSONDecodeError:
                    continue

    def _load_seed_terms(self):
        """Начальные проверенные термины для отладки пайплайна."""
        seed = [
            {"canonical": "CTS", "expansion": "Corporate Transport Server", "product": "express"},
            {"canonical": "SNMP", "expansion": "Simple Network Management Protocol", "product": "kaspersky"},
            {"canonical": "DKP", "expansion": "Deckhouse Kubernetes Platform", "product": "deckhouse"},
            {"canonical": "NLB", "expansion": "Network Load Balancer", "product": "deckhouse"},
            {"canonical": "VPA", "expansion": "Vertical Pod Autoscaler", "product": "deckhouse"},
            {"canonical": "WAL", "expansion": "Write Access Level", "product": "linter"},
            {"canonical": "WAL", "expansion": "write ahead log", "product": "tarantool"},
        ]
        for entry in seed:
            self.all_terms.append(entry)
            prod = entry.get("product", "general")
            self.terms_by_product.setdefault(prod, []).append(entry)
            canon = entry.get("canonical", "").strip().upper()
            self.canonical_index.setdefault(canon, []).append(entry)

    def match_terms(self, query: str, detected_products: List[str]) -> List[DetectedTerm]:
        """
        Находит аббревиатуры в тексте вопроса с учетом опечаток и продуктов.
        Разрешает омонимы (Disambiguation).
        """
        # Разбиваем запрос на токены (слова без знаков препинания)
        raw_words = re.findall(r"[a-zA-Zа-яА-Я0-9_-]+", query)
        detected_terms_map: Dict[Tuple[str, str], DetectedTerm] = {}

        # 1. Сначала определяем пул кандидатов: если продукты найдены, приоритет им
        product_pool = []
        for p in detected_products:
            product_pool.extend(self.terms_by_product.get(p, []))
            
        # Если продукт не определен, смотрим все термины
        search_pool = product_pool if product_pool else self.all_terms

        # Собираем формы слов (оригинал + верхний регистр + транслит)
        word_variants = []
        for w in raw_words:
            upper_w = w.upper()
            trans_w = transliterate_acronym(w)
            word_variants.append((w, upper_w, trans_w))

        # 2. Ищем совпадения по терминам пула
        # Для случаев, когда упомянуто несколько продуктов с одинаковым термином (как WAL в Linter и Tarantool)
        for entry in search_pool:
            canon = entry.get("canonical", "").strip().upper()
            expansion = entry.get("expansion", "").strip()
            if not canon or not expansion:
                continue

            term_matched = False
            for orig, upper_w, trans_w in word_variants:
                # Точное совпадение
                if upper_w == canon or trans_w == canon:
                    term_matched = True
                    break
                # Нечеткое совпадение с опечатками (для аббревиатур длина >= 3)
                if len(canon) >= 3:
                    ratio1 = fuzz.ratio(upper_w, canon)
                    ratio2 = fuzz.ratio(trans_w, canon)
                    if max(ratio1, ratio2) >= 85:
                        term_matched = True
                        break

            if term_matched:
                key = (canon, expansion)
                if key not in detected_terms_map:
                    detected_terms_map[key] = DetectedTerm(
                        canonical=entry.get("canonical"),
                        expansion=expansion
                    )

        # 3. Дополнительная проверка: если продукт не был в detected_products,
        # но в вопросе есть уникальная аббревиатура из базы
        if not detected_terms_map:
            for canon, entries in self.canonical_index.items():
                for orig, upper_w, trans_w in word_variants:
                    if upper_w == canon or trans_w == canon:
                        for entry in entries:
                            exp = entry.get("expansion", "")
                            key = (entry.get("canonical"), exp)
                            if key not in detected_terms_map:
                                detected_terms_map[key] = DetectedTerm(
                                    canonical=entry.get("canonical"),
                                    expansion=exp
                                )

        # Ограничение по openapi.yaml: не более 16 терминов
        return list(detected_terms_map.values())[:16]
