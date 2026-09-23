"""
Модуль автоматического извлечения аббревиатур и их подтвержденных расшифровок из PDF-документов.
Реализует:
1. Алгоритм обратного пословного выравнивания (Schwartz-Hearst).
2. Парсер таблиц глоссариев и списков терминов.
3. Фильтрацию стоп-слов и нормализацию цитат со страницами.
"""

import re
from typing import Dict, List, Optional, Tuple
import pymupdf

from src.schemas import AbbreviationOccurrence, ExtractedAbbreviation

# Стоп-слова, которые не являются целевыми аббревиатурами
STOP_WORDS = {
    "PDF", "HTTP", "HTTPS", "URL", "HTML", "JSON", "XML", "API", "REST", "SQL",
    "IEEE", "RFC", "TCP", "UDP", "IP", "DNS", "SSH", "TLS", "SSL", "OS", "ОС",
    "CPU", "RAM", "GB", "MB", "KB", "ГБ", "МБ", "КБ",
    # Имена продуктов и их части (по указанию кейсодержателя не подлежат расшифровке)
    "DB", "РЕД", "RED", "ВИРТ", "VIRT", "РОСА", "ROSA", "ЛИНТЕР", "LINTER", "PRO", "БД"
}

# Служебные слова-связки, допустимые внутри расшифровки между начальными буквами
CONNECTOR_WORDS = {
    "of", "and", "for", "the", "in", "on", "at", "to", "a", "an", "by", "with",
    "по", "и", "для", "в", "на", "с", "из", "или", "о", "об", "к", "от", "при", "под", "до"
}

# Заголовки разделов с глоссариями и перечнями сокращений (русский и английский языки)
GLOSSARY_HEADERS = (
    "термины и определения",
    "список сокращений",
    "перечень сокращений",
    "обозначения и сокращения",
    "глоссарий",
    "термины, определения и сокращения",
    "список терминов",
    "термины и сокращения",
    "сокращения и обозначения",
    "условные обозначения",
    "список используемых сокращений",
    "glossary",
    "acronyms",
    "list of acronyms",
    "abbreviations",
    "list of abbreviations",
    "terms and definitions",
    "terms & definitions",
    "definitions",
)

# Предварительно скомпилированные регулярные выражения (оптимизация производительности)
RE_WORD = re.compile(r"[a-zA-Zа-яА-Я0-9]+")
RE_SPACES = re.compile(r"\s+")
RE_DELIM_SPLIT = re.compile(r"[\—\–\-\:\―\‒]")
RE_BRACKET_ACRONYM = re.compile(r"[\(\[\{]\s*([A-Za-zА-Яа-яЁё]{2,10})\s*[\)\]\}]")
RE_ACRONYM_BRACKET = re.compile(r"\b([A-Za-zА-Яа-яЁё]{2,10})\s*[\(\[\{]([^\)\]\}]+)[\)\]\}]")
RE_GLOSSARY_SINGLE = re.compile(r"^[A-Za-zА-Яа-яЁё]{2,10}$")
RE_GLOSSARY_LINE = re.compile(r"^([A-Za-zА-Яа-яЁё]{2,10})(?:\s*[\—\–\-\:\―\‒]\s*|\t+|\s{2,})(.+)$")


def check_single_word_compound(canon: str, word: str) -> bool:
    """Проверяет соответствие сложного составного слова (напр. ВКС -> Видеоконференцсвязь)."""
    canon_lower = canon.lower()
    w_lower = word.lower()
    if not w_lower.startswith(canon_lower[0]):
        return False
    pos = 0
    for char in canon_lower:
        pos = w_lower.find(char, pos)
        if pos == -1:
            return False
        pos += 1
    return True


def parse_glossary_line(line: str) -> Optional[Tuple[str, str]]:
    """
    Проверяет отдельную строку текста на формат: АББР [тире/двоеточие/табуляция] Расшифровка.
    Проверяет согласованность первых букв слов расшифровки с аббревиатурой.
    """
    m = RE_GLOSSARY_LINE.match(line)
    if not m:
        return None
    canon = m.group(1).strip()
    if sum(1 for c in canon if c.isupper()) < 2:
        return None
    rest = m.group(2).strip()
    parts = RE_DELIM_SPLIT.split(rest, maxsplit=1)
    exp_cand = RE_SPACES.sub(" ", parts[0]).strip().strip(" .,;:-—–")
    words = RE_WORD.findall(exp_cand)
    if not words:
        return None
    letters = "".join(w[0].upper() for w in words if w)
    canon_upper = canon.upper()

    if letters == canon_upper or (
        len(words) >= 2 and sum(1 for c in canon_upper if c in letters) >= max(2, len(canon) * 0.7)
    ):
        return (canon, exp_cand)
    elif len(words) == 1 and len(canon) >= 2 and check_single_word_compound(canon, words[0]):
        return (canon, exp_cand)
    elif len(parts) > 1 and len(words) == len(canon):
        if all(w[0].upper() == c for w, c in zip(words, canon_upper)):
            return (canon, exp_cand)
    return None


def extract_expansion_backward(preceding_text: str, canon: str) -> Optional[str]:
    """
    Алгоритм обратного пословного выравнивания (Schwartz-Hearst с бэктрекингом).
    
    Двигаясь справа налево от скобки, сопоставляет начальные буквы предшествующих слов
    с символами аббревиатуры canon. Корректно обрабатывает связующие союзы и предлоги,
    даже если предлог начинается с той же буквы, что и слово расшифровки.
    """
    words = RE_WORD.findall(preceding_text)
    if not words:
        return None

    # Ограничиваемся последними 20 словами перед скобкой
    words = words[-20:]
    canon_upper = canon.upper()

    def match_helper(w_idx: int, c_idx: int, matched: List[str]) -> Optional[List[str]]:
        if c_idx < 0:
            return matched
        if w_idx < 0:
            return None

        w = words[w_idx]
        w_upper = w.upper()
        target_char = canon_upper[c_idx]
        is_conn = w.lower() in CONNECTOR_WORDS

        # Вариант 1: Если слово НЕ служебное и начинается с целевой буквы
        if not is_conn and w_upper.startswith(target_char):
            res = match_helper(w_idx - 1, c_idx - 1, [w] + matched)
            if res:
                return res

        # Вариант 2: Если слово служебное (предлог/союз)
        if is_conn:
            # 2a: Пропускаем служебное слово (не расходуем букву аббревиатуры)
            res = match_helper(w_idx - 1, c_idx, [w] + matched)
            if res:
                return res
            # 2b: Сопоставляем как букву (на случай редких сокращений типа DoD)
            if w_upper.startswith(target_char):
                res = match_helper(w_idx - 1, c_idx - 1, [w] + matched)
                if res:
                    return res

        return None

    matched_words = match_helper(len(words) - 1, len(canon_upper) - 1, [])
    if matched_words:
        first_word = matched_words[0]
        last_word = matched_words[-1]

        # Быстрый поиск границ подстроки в исходном тексте
        first_pos = preceding_text.rfind(first_word)
        if first_pos != -1:
            last_pos = preceding_text.find(last_word, first_pos)
            if last_pos != -1:
                end_pos = last_pos + len(last_word)
                raw_substring = preceding_text[first_pos:end_pos]
                clean_res = RE_SPACES.sub(" ", raw_substring).strip().strip(" .,;:-—–")
                if 3 <= len(clean_res) <= 120:
                    return clean_res

        clean_fallback = " ".join(matched_words).strip(" .,;:-—–")
        if 3 <= len(clean_fallback) <= 120:
            return clean_fallback

    return None


def extract_expansion_forward(following_text: str, canon: str) -> Optional[str]:
    """
    Проверяет прямой паттерн: АББР (Расшифровка...) с поддержкой бэктрекинга.
    """
    words = RE_WORD.findall(following_text)
    if not words:
        return None

    words = words[:20]
    canon_upper = canon.upper()

    def match_fwd(w_idx: int, c_idx: int, matched: List[str]) -> Optional[List[str]]:
        if c_idx >= len(canon_upper):
            return matched
        if w_idx >= len(words):
            return None

        w = words[w_idx]
        w_upper = w.upper()
        target_char = canon_upper[c_idx]
        is_conn = w.lower() in CONNECTOR_WORDS

        # Вариант 1: Не служебное слово, начинается с буквы
        if not is_conn and w_upper.startswith(target_char):
            res = match_fwd(w_idx + 1, c_idx + 1, matched + [w])
            if res:
                return res

        # Вариант 2: Служебное слово
        if is_conn:
            res = match_fwd(w_idx + 1, c_idx, matched + [w])
            if res:
                return res
            if w_upper.startswith(target_char):
                res = match_fwd(w_idx + 1, c_idx + 1, matched + [w])
                if res:
                    return res

        return None

    matched_words = match_fwd(0, 0, [])
    if matched_words:
        clean_res = " ".join(matched_words).strip(" .,;:-—–")
        if 3 <= len(clean_res) <= 120:
            return clean_res

    return None


def parse_glossary_page(text: str) -> List[Tuple[str, str, str]]:
    """
    Парсит термины из страниц глоссария и таблиц сокращений.
    Возвращает список кортежей (canonical, expansion, quote).
    """
    results: List[Tuple[str, str, str]] = []
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    for i, line in enumerate(lines):
        # 1. Формат: АББР на отдельной строке, следующая строка — расшифровка
        if RE_GLOSSARY_SINGLE.match(line):
            canon = line
            if sum(1 for c in canon if c.isupper()) >= 2 and i + 1 < len(lines):
                next_line = lines[i + 1]
                parts = RE_DELIM_SPLIT.split(next_line, maxsplit=1)
                exp_cand = RE_SPACES.sub(" ", parts[0]).strip().strip(" .,;:-—–")
                words = RE_WORD.findall(exp_cand)
                letters = "".join(w[0].upper() for w in words if w)

                if letters == canon.upper() or (
                    len(words) >= 2 and sum(1 for c in canon.upper() if c in letters) >= max(2, len(canon) * 0.7)
                ):
                    quote = f"{canon}: {next_line}"
                    results.append((canon, exp_cand, quote))
                elif len(words) == 1 and len(canon) >= 2 and check_single_word_compound(canon, words[0]):
                    quote = f"{canon}: {next_line}"
                    results.append((canon, exp_cand, quote))
                elif len(parts) > 1 and len(words) == len(canon):
                    if all(w[0].upper() == c for w, c in zip(words, canon.upper())):
                        quote = f"{canon}: {next_line}"
                        results.append((canon, exp_cand, quote))

        # 2. Формат: АББР [разделитель] Расшифровка на одной строке
        res_line = parse_glossary_line(line)
        if res_line:
            canon, exp_cand = res_line
            results.append((canon, exp_cand, line))

    return results


def extract_from_pdf_document(doc: pymupdf.Document) -> List[ExtractedAbbreviation]:
    """
    Извлекает подтвержденные аббревиатуры из открытого документа PyMuPDF.
    Сохраняет страницу и дословную цитату.
    """
    # canonical -> {expansion -> list of occurrences}
    found_data: Dict[str, Dict[str, List[AbbreviationOccurrence]]] = {}

    for page_idx in range(len(doc)):
        page_num = page_idx + 1
        page = doc[page_idx]
        text = page.get_text("text")
        if not text:
            continue
        text = text.replace("\xa0", " ").replace("\x00", "\t")

        # 1. Парсинг глоссариев и списков определений (однострочные и двухстрочные форматы)
        glossary_terms = parse_glossary_page(text)
        for canon, exp, quote in glossary_terms:
            if canon in STOP_WORDS or len(canon) < 2 or sum(1 for c in canon if c.isupper()) < 2:
                continue
            found_data.setdefault(canon, {}).setdefault(exp, []).append(
                AbbreviationOccurrence(page=page_num, quote=quote[:1000])
            )

        # 2. Паттерн: ... Расшифровка (АББР)
        for m in RE_BRACKET_ACRONYM.finditer(text):
            canon = m.group(1).strip()
            if canon in STOP_WORDS or len(canon) < 2 or sum(1 for c in canon if c.isupper()) < 2:
                continue

            start_pos = max(0, m.start() - 120)
            preceding = text[start_pos:m.start()]
            exp = extract_expansion_backward(preceding, canon)

            if exp:
                q_start = max(0, m.start() - 60)
                q_end = min(len(text), m.end() + 60)
                quote = RE_SPACES.sub(" ", text[q_start:q_end]).strip()
                found_data.setdefault(canon, {}).setdefault(exp, []).append(
                    AbbreviationOccurrence(page=page_num, quote=quote[:1000])
                )

        # 3. Паттерн: АББР (Расшифровка...)
        for m in RE_ACRONYM_BRACKET.finditer(text):
            canon = m.group(1).strip()
            if canon in STOP_WORDS or len(canon) < 2 or sum(1 for c in canon if c.isupper()) < 2:
                continue

            inside = m.group(2).strip()
            exp = extract_expansion_forward(inside, canon)
            if exp:
                q_start = max(0, m.start() - 40)
                q_end = min(len(text), m.end() + 40)
                quote = RE_SPACES.sub(" ", text[q_start:q_end]).strip()
                found_data.setdefault(canon, {}).setdefault(exp, []).append(
                    AbbreviationOccurrence(page=page_num, quote=quote[:1000])
                )

    # Формирование ответа строго по openapi.yaml
    result: List[ExtractedAbbreviation] = []
    for canon, exp_dict in found_data.items():
        for exp, occs in exp_dict.items():
            unique_occs: List[AbbreviationOccurrence] = []
            seen_pages = set()
            for occ in occs:
                if occ.page not in seen_pages:
                    unique_occs.append(occ)
                    seen_pages.add(occ.page)

            result.append(
                ExtractedAbbreviation(
                    canonical=canon,
                    expansion=exp,
                    occurrences=unique_occs[:100],
                )
            )

    return result[:2048]


def extract_abbreviations_from_bytes(file_bytes: bytes) -> List[ExtractedAbbreviation]:
    """Точка входа для эндпоинта POST /v1/abbreviations/extract"""
    doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    try:
        return extract_from_pdf_document(doc)
    finally:
        doc.close()


def extract_abbreviations_from_file(file_path: str) -> List[ExtractedAbbreviation]:
    """Точка входа для офлайн-скрипта генерации словаря"""
    doc = pymupdf.open(file_path)
    try:
        return extract_from_pdf_document(doc)
    finally:
        doc.close()