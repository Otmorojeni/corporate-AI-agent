import re
import fitz  # PyMuPDF
from typing import List, Dict, Tuple, Optional
from src.schemas import ExtractedAbbreviation, AbbreviationOccurrence
# Регулярки для поиска определений:
# 1. АББР (Расшифровка...) -> CTS (Corporate Transport Server)
PATTERN_ACR_FIRST = re.compile(
    r"\b([A-ZА-ЯЁ]{2,10})\b\s*[\(\[\{]([A-Za-zА-Яа-яЁё0-9\s,\-\–\—]{3,80})[\)\]\}]"
)
# 2. Расшифровка (АББР) -> Corporate Transport Server (CTS)
PATTERN_EXP_FIRST = re.compile(
    r"([A-Za-zА-Яа-яЁё0-9\s,\-\–\—]{3,80})\s*[\(\[\{]\b([A-ZА-ЯЁ]{2,10})\b[\)\]\}]"
)
# Стоп-слова, которые точно не являются аббревиатурами
STOP_WORDS = {"PDF", "HTTP", "HTTPS", "URL", "HTML", "JSON", "XML", "API", "REST", "SQL", "IEEE", "RFC"}
def is_valid_acronym(canonical: str, expansion: str) -> bool:
    """Проверяет валидность: длина, отсутствие мусора, сопоставление букв."""
    canon = canonical.strip()
    exp = expansion.strip()
    if canon in STOP_WORDS or len(canon) < 2 or len(canon) > 10:
        return False
    if len(exp) < 3 or len(exp) > 120:
        return False
    # Исключаем технический код, пути к файлам и параметры
    if "/" in exp or "\\" in exp or "http" in exp.lower() or "=" in exp:
        return False
    words = [w for w in re.split(r"[\s\-_]+", exp) if w]
    if len(words) == 0:
        return False
    # Эвристика: первые буквы слов расшифровки должны коррелировать с аббревиатурой
    letters = "".join(w[0].upper() for w in words if w[0].isalpha())
    canon_upper = canon.upper()
    # Хотя бы 50% букв аббревиатуры должны совпадать с заглавными буквами слов
    common = sum(1 for c in canon_upper if c in letters)
    if common >= max(2, len(canon_upper) * 0.5):
        return True
    # Для русского/английского смешанного текста разрешаем если длина слов совпадает
    if len(words) == len(canon):
        return True
    return False
def extract_from_pdf_document(doc:fitz.Document) -> List[ExtractedAbbreviation]:
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
        # Поиск паттерна 1: АББР (Расшифровка)
        for m in PATTERN_ACR_FIRST.finditer(text):
            canon = m.group(1).strip()
            exp = m.group(2).strip()
            if is_valid_acronym(canon, exp):
                # Формируем цитату с контекстом вокруг совпадения
                start = max(0, m.start() - 40)
                end = min(len(text), m.end() + 40)
                quote = text[start:end].replace("\n", " ").strip()
                
                found_data.setdefault(canon, {}).setdefault(exp, []).append(
                    AbbreviationOccurrence(page=page_num, quote=quote[:1000])
                )
        # Поиск паттерна 2: Расшифровка (АББР)
        for m in PATTERN_EXP_FIRST.finditer(text):
            exp = m.group(1).strip()
            canon = m.group(2).strip()
            if is_valid_acronym(canon, exp):
                start = max(0, m.start() - 40)
                end = min(len(text), m.end() + 40)
                quote = text[start:end].replace("\n", " ").strip()
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
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    return extract_from_pdf_document(doc)
def extract_abbreviations_from_file(file_path: str) -> List[ExtractedAbbreviation]:
    """Точка входа для офлайн-скрипта генерации словаря"""
    doc = fitz.open(file_path)
    return extract_from_pdf_document(doc)