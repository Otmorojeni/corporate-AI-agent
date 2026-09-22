"""
Модуль нечеткого сопоставления аббревиатур и контекстной дисамбигуации.
Обеспечивает:
1. Поиск терминов в запросе с учетом опечаток (RapidFuzz >= 85%).
2. Фонетическую транслитерацию (русский <-> английский, например СТС -> CTS).
3. Разрешение омонимов по контексту продукта (например, WAL в ЛИНТЕР vs Tarantool).
4. Защиту от ложных срабатываний на русские союзы и предлоги.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from rapidfuzz import fuzz

from src.schemas import DetectedTerm
from src.config import settings

# Предварительно скомпилированная регулярка разбиения на слова
RE_WORDS = re.compile(r"[a-zA-Zа-яА-Я0-9_-]+")

# Кастомная транслитерация частых технических сокращений
CUSTOM_TRANSLIT = {
    "ВПА": "VPA", "НЛБ": "NLB", "ДКП": "DKP", "СНМП": "SNMP",
    "СТС": "CTS", "ВАЛ": "WAL", "УГ": "UG", "КЕСС": "KESS"
}

# Общая таблица побуквенной транслитерации для аббревиатур
RU_TO_EN_MAP = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E",
    "Ж": "ZH", "З": "Z", "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
    "Ф": "F", "Х": "H", "Ц": "TS", "Ч": "CH", "Ш": "SH", "Щ": "SCH",
    "Ы": "Y", "Э": "E", "Ю": "YU", "Я": "YA"
}

# Стоп-слова, предлоги и союзы, исключаемые из поиска аббревиатур
STOP_WORDS = {
    "И", "В", "С", "А", "О", "К", "У", "НЕ", "НА", "ПО", "ЗА", "ОТ", "ДО",
    "ИЗ", "БЕЗ", "ПРИ", "ПРО", "ДЛЯ", "ТО", "ЖЕ", "НО", "ДА", "НИ", "КАК",
    "ЧТО", "ГДЕ", "КТО", "ГДE", "ИЛИ", "ЕСЛИ", "ТАК", "ЭТО", "МНЕ", "ВАМ",
    "ЕГО", "ИХ", "ЕЕ", "МЫ", "ВЫ", "ОНИ", "ОН", "ОНА", "ОНО",
    "OR", "AND", "THE", "IN", "ON", "AT", "TO", "FOR", "OF", "IS", "ARE"
}


def transliterate_acronym(text: str) -> str:
    """
    Транслитерирует русские буквы в латинские для поиска аббревиатур (ВПА -> VPA, СНМП -> SNMP).
    """
    upper = text.upper()
    if upper in CUSTOM_TRANSLIT:
        return CUSTOM_TRANSLIT[upper]
    return "".join(RU_TO_EN_MAP.get(ch, ch) for ch in upper)


class TermMatcher:
    """
    Класс индексации и контекстного сопоставления терминов.
    """

    def __init__(self, terms_file: Optional[Path] = None):
        self.terms_file = terms_file or settings.TERMS_FILE
        self.terms_by_product: Dict[str, List[Dict]] = {}
        self.all_terms: List[Dict] = []
        self.canonical_index: Dict[str, List[Dict]] = {}
        self.load_terms()

    def load_terms(self) -> None:
        """Загружает словарь terms.jsonl в память и строит продуктовые индексы."""
        self.terms_by_product.clear()
        self.all_terms.clear()
        self.canonical_index.clear()

        if not self.terms_file.exists():
            return

        with open(self.terms_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    canon = entry.get("canonical", "").strip()
                    exp = entry.get("expansion", "").strip()

                    # Фильтрация некорректных или замусоренных записей
                    if not canon or not exp or len(canon) < 2 or canon.upper() in STOP_WORDS:
                        continue

                    self.all_terms.append(entry)
                    prod = entry.get("product", "general")
                    self.terms_by_product.setdefault(prod, []).append(entry)
                    self.canonical_index.setdefault(canon.upper(), []).append(entry)
                except json.JSONDecodeError:
                    continue

    def match_terms(self, query: str, detected_products: List[str]) -> List[DetectedTerm]:
        """
        Находит аббревиатуры в тексте вопроса с учетом опечаток и контекста продуктов.
        Разрешает омонимы (например, WAL для Linter vs Tarantool).
        """
        raw_words = RE_WORDS.findall(query)

        # Отбираем валидные слова-кандидаты (длина >= 2, не стоп-слова)
        word_candidates: List[Tuple[str, str, str]] = []
        for w in raw_words:
            upper_w = w.upper()
            if len(upper_w) < 2 or upper_w in STOP_WORDS:
                continue
            trans_w = transliterate_acronym(w)
            word_candidates.append((w, upper_w, trans_w))

        if not word_candidates:
            return []

        matched_terms: List[DetectedTerm] = []
        seen_pairs: Set[Tuple[str, str]] = set()

        # 1. Если продукты определены в вопросе, ищем термины по каждому продукту
        if detected_products:
            for prod in detected_products:
                prod_terms = self.terms_by_product.get(prod, [])
                terms_by_canon: Dict[str, List[Dict]] = {}
                for entry in prod_terms:
                    canon_upper = entry["canonical"].upper()
                    terms_by_canon.setdefault(canon_upper, []).append(entry)

                for canon_upper, entries in terms_by_canon.items():
                    term_matched = False
                    canon_len = len(canon_upper)

                    for orig_w, upper_w, trans_w in word_candidates:
                        # Точное совпадение (включая транслитерацию)
                        if upper_w == canon_upper or trans_w == canon_upper:
                            term_matched = True
                            break

                        # Нечеткое сопоставление разрешено ТОЛЬКО для длинных аббревиатур (>= 4 символов),
                        # чтобы исключить ложные совпадения коротких 3-буквенных слов (например, REAL -> RAL)
                        if canon_len >= 4 and abs(len(upper_w) - canon_len) <= 1:
                            if orig_w.isupper() or len(orig_w) >= 4:
                                if fuzz.ratio(upper_w, canon_upper) >= 88 or fuzz.ratio(trans_w, canon_upper) >= 88:
                                    term_matched = True
                                    break

                    if term_matched and entries:
                        best_entry = entries[0]
                        canon = best_entry["canonical"]
                        exp = best_entry["expansion"]
                        pair = (canon, exp)
                        if pair not in seen_pairs:
                            seen_pairs.add(pair)
                            matched_terms.append(DetectedTerm(canonical=canon, expansion=exp))

        # 2. Если продукт не определен в вопросе:
        # Ищем ТОЛЬКО точные совпадения по всей базе канонических форм (включая транслитерацию),
        # либо если слово в запросе написано ПОЛНОСТЬЮ ЗАГЛАВНЫМИ БУКВАМИ (длина >= 4) с высоким сходством.
        # Это категорически предотвращает ложные срабатывания на обычные слова с заглавной буквы
        # (например, "Реал" не будет сопоставляться с "RAL").
        if not matched_terms:
            for canon_upper, entries in self.canonical_index.items():
                term_matched = False
                canon_len = len(canon_upper)

                for orig_w, upper_w, trans_w in word_candidates:
                    # Точное совпадение
                    if upper_w == canon_upper or trans_w == canon_upper:
                        term_matched = True
                        break

                    # Нечеткий поиск без указания продукта допустим ТОЛЬКО для слов,
                    # написанных полностью заглавными буквами (напр. SNMP c опечаткой) и длиной >= 4
                    if canon_len >= 4 and orig_w.isupper() and abs(len(upper_w) - canon_len) <= 1:
                        if fuzz.ratio(upper_w, canon_upper) >= 90 or fuzz.ratio(trans_w, canon_upper) >= 90:
                            term_matched = True
                            break

                if term_matched and entries:
                    best_entry = entries[0]
                    canon = best_entry["canonical"]
                    exp = best_entry["expansion"]
                    pair = (canon, exp)
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        matched_terms.append(DetectedTerm(canonical=canon, expansion=exp))

        # Ограничение openapi.yaml: не более 16 терминов
        return matched_terms[:16]
