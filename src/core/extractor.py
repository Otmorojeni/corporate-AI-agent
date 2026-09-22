import re
from typing import List, Dict, Tuple, Optional
import pymupdf  # PyMuPDF
from src.schemas import ExtractedAbbreviation, AbbreviationOccurrence

STOP_WORDS = {
    "PDF", "HTTP", "HTTPS", "URL", "HTML", "JSON", "XML", "API", "REST", "SQL", 
    "IEEE", "RFC", "TCP", "UDP", "IP", "DNS", "SSH", "TLS", "SSL", "OS", "ОС", 
    "CPU", "RAM", "GB", "MB", "KB", "ГБ", "МБ", "КБ"
}

# Стоп-слова, которые могут стоять внутри расшифровки между начальными буквами
CONNECTOR_WORDS = {
    "of", "and", "for", "the", "in", "on", "at", "to", "a", "an", "by", "with",
    "по", "и", "для", "в", "на", "с", "из", "или", "о", "об"
}

GLOSSARY_HEADERS = [
    "термины и определения",
    "список сокращений",
    "перечень сокращений",
    "обозначения и сокращения",
    "глоссарий",
    "термины, определения и сокращения",
    "список терминов",
]


def extract_expansion_backward(preceding_text: str, canon: str) -> Optional[str]:
    """
    Алгоритм обратного пословного выравнивания (Schwartz-Hearst).
    Ищет в предшествующем тексте слова, начинающиеся на буквы аббревиатуры canon,
    двигаясь справа налево. Отсекает любой лишний текст предложения.
    """
    words = re.findall(r"[a-zA-Zа-яА-Я0-9]+", preceding_text)
    if not words:
        return None

    canon_upper = canon.upper()
    c_idx = len(canon_upper) - 1
    matched_words = []

    for w in reversed(words):
        if c_idx < 0:
            break
        w_upper = w.upper()
        target_char = canon_upper[c_idx]

        if w_upper.startswith(target_char):
            matched_words.append(w)
            c_idx -= 1
        elif w.lower() in CONNECTOR_WORDS:
            # Разрешаем служебные слова между буквами аббревиатуры
            matched_words.append(w)
        else:
            if matched_words:
                break

    if c_idx < 0 and matched_words:
        matched_words.reverse()
        first_word = matched_words[0]
        last_word = matched_words[-1]
        
        # Находим точную подстроку в исходном тексте для сохранения регистра и дефисов
        pattern = re.escape(first_word) + r"[\s\-_]+.*?" + re.escape(last_word)
        m = list(re.finditer(pattern, preceding_text, re.IGNORECASE | re.DOTALL))
        if m:
            clean_res = re.sub(r"\s+", " ", m[-1].group(0)).strip()
            # Проверяем разумную длину расшифровки
            if 3 <= len(clean_res) <= 120:
                return clean_res
        clean_res = " ".join(matched_words)
        if 3 <= len(clean_res) <= 120:
            return clean_res

    return None


def extract_expansion_forward(following_text: str, canon: str) -> Optional[str]:
    """
    Проверяет паттерн АББР (Расшифровка...)
    """
    words = re.findall(r"[a-zA-Zа-яА-Я0-9]+", following_text)
    if not words:
        return None

    canon_upper = canon.upper()
    c_idx = 0
    matched_words = []

    for w in words:
        if c_idx >= len(canon_upper):
            break
        w_upper = w.upper()
        target_char = canon_upper[c_idx]

        if w_upper.startswith(target_char):
            matched_words.append(w)
            c_idx += 1
        elif w.lower() in CONNECTOR_WORDS:
            matched_words.append(w)
        else:
            if matched_words:
                break

    if c_idx == len(canon_upper) and matched_words:
        first_word = matched_words[0]
        last_word = matched_words[-1]
        pattern = re.escape(first_word) + r"[\s\-_]+.*?" + re.escape(last_word)
        m = list(re.finditer(pattern, following_text, re.IGNORECASE | re.DOTALL))
        if m:
            clean_res = re.sub(r"\s+", " ", m[0].group(0)).strip()
            if 3 <= len(clean_res) <= 120:
                return clean_res
        clean_res = " ".join(matched_words)
        if 3 <= len(clean_res) <= 120:
            return clean_res

    return None


def parse_glossary_page(text: str) -> List[Tuple[str, str, str]]:
    """
    Парсит термины из страниц глоссария / таблиц сокращений.
    Возвращает список кортежей (canonical, expansion, quote).
    """
    results = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    i = 0
    while i < len(lines):
        line = lines[i]

        # 1. Формат: АББР на отдельной строке, следующая строка — расшифровка
        if re.match(r"^[A-ZА-ЯЁ]{2,10}$", line):
            canon = line
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                # Отсекаем пояснение после тире
                parts = re.split(r"[\—\–\-]", next_line, maxsplit=1)
                exp_cand = re.sub(r"\s+", " ", parts[0]).strip()
                words = re.findall(r"[a-zA-Zа-яА-Я0-9]+", exp_cand)
                letters = "".join(w[0].upper() for w in words if w)

                # Проверяем соответствие букв
                if letters == canon.upper() or (
                    len(words) >= 2 and sum(1 for c in canon.upper() if c in letters) >= max(2, len(canon) * 0.7)
                ):
                    quote = f"{canon}: {next_line}"
                    results.append((canon, exp_cand, quote))
                elif len(parts) > 1 and len(words) == len(canon):
                    if all(w[0].upper() == c for w, c in zip(words, canon.upper())):
                        quote = f"{canon}: {next_line}"
                        results.append((canon, exp_cand, quote))

        # 2. Формат: АББР — Расшифровка на одной строке
        m = re.match(r"^([A-ZА-ЯЁ]{2,10})\s*[\—\–\-]\s*(.+)$", line)
        if m:
            canon = m.group(1).strip()
            rest = m.group(2).strip()
            parts = re.split(r"[\—\–\-]", rest, maxsplit=1)
            exp_cand = re.sub(r"\s+", " ", parts[0]).strip()
            words = re.findall(r"[a-zA-Zа-яА-Я0-9]+", exp_cand)
            letters = "".join(w[0].upper() for w in words if w)
            if letters == canon.upper() or (
                len(words) >= 2 and sum(1 for c in canon.upper() if c in letters) >= max(2, len(canon) * 0.7)
            ):
                results.append((canon, exp_cand, line))

        i += 1
    return results


def extract_from_pdf_document(doc: pymupdf.Document) -> List[ExtractedAbbreviation]:
    """
    Извлекает подтвержденные аббревиатуры из открытого документа PyMuPDF.
    Сохраняет страницу и дословную цитату.
    """
    found_data: Dict[str, Dict[str, List[AbbreviationOccurrence]]] = {}

    # Регулярки для поиска скобок
    # 1. ... (АББР)
    pattern_bracket_acronym = re.compile(r"[\(\[\{]\s*([A-ZА-ЯЁ]{2,10})\s*[\)\]\}]")
    # 2. АББР (...)
    pattern_acronym_bracket = re.compile(r"\b([A-ZА-ЯЁ]{2,10})\s*[\(\[\{]([^\)\]\}]+)[\)\]\}]")

    for page_idx in range(len(doc)):
        page_num = page_idx + 1
        page = doc[page_idx]
        text = page.get_text("text")
        if not text:
            continue

        text_lower = text.lower()
        is_glossary = any(header in text_lower for header in GLOSSARY_HEADERS)

        # 1. Если это страница глоссария, применяем табличный парсер
        if is_glossary:
            glossary_terms = parse_glossary_page(text)
            for canon, exp, quote in glossary_terms:
                if canon in STOP_WORDS or len(canon) < 2:
                    continue
                found_data.setdefault(canon, {}).setdefault(exp, []).append(
                    AbbreviationOccurrence(page=page_num, quote=quote[:1000])
                )

        # 2. Паттерн: Расшифровка (АББР)
        for m in pattern_bracket_acronym.finditer(text):
            canon = m.group(1).strip()
            if canon in STOP_WORDS or len(canon) < 2:
                continue

            # Берем до 120 символов перед скобкой
            start_pos = max(0, m.start() - 120)
            preceding = text[start_pos:m.start()]
            exp = extract_expansion_backward(preceding, canon)

            if exp:
                q_start = max(0, m.start() - 60)
                q_end = min(len(text), m.end() + 60)
                quote = re.sub(r"\s+", " ", text[q_start:q_end]).strip()
                found_data.setdefault(canon, {}).setdefault(exp, []).append(
                    AbbreviationOccurrence(page=page_num, quote=quote[:1000])
                )

        # 3. Паттерн: АББР (Расшифровка)
        for m in pattern_acronym_bracket.finditer(text):
            canon = m.group(1).strip()
            inside = m.group(2).strip()
            if canon in STOP_WORDS or len(canon) < 2:
                continue

            exp = extract_expansion_forward(inside, canon)
            if exp:
                q_start = max(0, m.start() - 40)
                q_end = min(len(text), m.end() + 40)
                quote = re.sub(r"\s+", " ", text[q_start:q_end]).strip()
                found_data.setdefault(canon, {}).setdefault(exp, []).append(
                    AbbreviationOccurrence(page=page_num, quote=quote[:1000])
                )

    # Собираем результат в формате openapi.yaml
    result: List[ExtractedAbbreviation] = []
    for canon, exp_dict in found_data.items():
        for exp, occs in exp_dict.items():
            # Дедуплицируем цитаты на одной и той же странице
            unique_occs = []
            seen_pages = set()
            for o in occs:
                if o.page not in seen_pages:
                    unique_occs.append(o)
                    seen_pages.add(o.page)

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
    return extract_from_pdf_document(doc)


def extract_abbreviations_from_file(file_path: str) -> List[ExtractedAbbreviation]:
    """Точка входа для офлайн-скрипта генерации словаря"""
    doc = pymupdf.open(file_path)
    return extract_from_pdf_document(doc)