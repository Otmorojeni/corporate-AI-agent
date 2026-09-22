import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
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

STOP_WORDS = {
    "И", "В", "С", "А", "О", "К", "У", "НЕ", "НА", "ПО", "ЗА", "ОТ", "ДО", 
    "ИЗ", "БЕЗ", "ПРИ", "ПРО", "ДЛЯ", "ТО", "ЖЕ", "НО", "ДА", "НИ", "КАК",
    "ЧТО", "ГДЕ", "КТО", "ГДE", "ИЛИ", "ЕСЛИ", "ПРИ", "ТАК", "ЭТО"
}


def transliterate_acronym(text: str) -> str:
    """Транслитерирует русские буквы в латинские для поиска аббревиатур (ВПА -> VPA, СНМП -> SNMP)."""
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
        raw_words = re.findall(r"[a-zA-Zа-яА-Я0-9_-]+", query)
        
        # Собираем формы валидных слов-кандидатов (длина >= 2, не стоп-слова)
        word_candidates = []
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

        # 1. Если продукты определены в вопросе, ищем термины для каждого продукта
        if detected_products:
            for prod in detected_products:
                prod_terms = self.terms_by_product.get(prod, [])
                # Группируем по канонической форме для выбора лучшей расшифровки
                terms_by_canon: Dict[str, List[Dict]] = {}
                for entry in prod_terms:
                    canon_upper = entry["canonical"].upper()
                    terms_by_canon.setdefault(canon_upper, []).append(entry)

                for canon_upper, entries in terms_by_canon.items():
                    term_matched = False
                    for orig, upper_w, trans_w in word_candidates:
                        if upper_w == canon_upper or trans_w == canon_upper:
                            term_matched = True
                            break
                        if len(canon_upper) >= 3:
                            if fuzz.ratio(upper_w, canon_upper) >= 85 or fuzz.ratio(trans_w, canon_upper) >= 85:
                                term_matched = True
                                break

                    if term_matched and entries:
                        # Берем первую (каноническую) словарную запись
                        best_entry = entries[0]
                        canon = best_entry["canonical"]
                        exp = best_entry["expansion"]
                        pair = (canon, exp)
                        if pair not in seen_pairs:
                            seen_pairs.add(pair)
                            matched_terms.append(DetectedTerm(canonical=canon, expansion=exp))

        # 2. Если термины не найдены через продукты, или продуктов не было:
        # ищем однозначные совпадения по всей базе
        if not matched_terms:
            for canon_upper, entries in self.canonical_index.items():
                term_matched = False
                for orig, upper_w, trans_w in word_candidates:
                    if upper_w == canon_upper or trans_w == canon_upper:
                        term_matched = True
                        break
                    if len(canon_upper) >= 3:
                        if fuzz.ratio(upper_w, canon_upper) >= 85 or fuzz.ratio(trans_w, canon_upper) >= 85:
                            term_matched = True
                            break

                if term_matched and entries:
                    # Если найдено несколько продуктов, выбираем первый
                    best_entry = entries[0]
                    canon = best_entry["canonical"]
                    exp = best_entry["expansion"]
                    pair = (canon, exp)
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        matched_terms.append(DetectedTerm(canonical=canon, expansion=exp))

        # Ограничение openapi.yaml: не более 16 терминов
        return matched_terms[:16]
