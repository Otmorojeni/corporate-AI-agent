"""
Модуль идентификации программных продуктов в запросе пользователя.
Поддерживает распознавание 17 продуктовых семейств по ключевым синонимам,
склонениям и сленговым названиям (русский и английский языки).
"""

import re
from typing import Dict, List, Tuple

# 17 официальных продуктовых семейств и их ключевые синонимы/словоформы
PRODUCT_PATTERNS: Dict[str, List[str]] = {
    "arenadata_db": [
        r"arenadata\s*db", r"arenadata", r"аренадат[а-я]*", r"\badb\b"
    ],
    "aurora": [
        r"аврор[а-я]*", r"aurora"
    ],
    "cyberprotect": [
        r"киберпротект[а-я]*", r"cyberprotect", r"кибер\s*бэкап[а-я]*", r"cyberbackup"
    ],
    "deckhouse": [
        r"deckhouse", r"декхаус[а-я]*", r"\bdkp\b", r"\bd8\b"
    ],
    "express": [
        r"\bexpress\b", r"экспресс[а-я]*", r"\bcts\b"
    ],
    "infowatch": [
        r"infowatch", r"инфовотч[а-я]*", r"инфоватч[а-я]*", r"traffic\s*monitor"
    ],
    "kaspersky": [
        r"kaspersky", r"касперск[а-я]*", r"\bkess\b", r"\bkes\b", r"\bksc\b"
    ],
    "linter": [
        r"линтер[а-я]*", r"linter"
    ],
    "loginom": [
        r"loginom", r"логином[а-я]*"
    ],
    "myoffice": [
        r"мойофис[а-я]*", r"мой\s*офис[а-я]*", r"myoffice", r"squadus", r"сквадус[а-я]*"
    ],
    "postgres_pro": [
        r"postgres\s*pro", r"постгрес\s*про", r"постгрес[а-я]*", r"postgres", r"\bpgpro\b"
    ],
    "red_database": [
        r"ред\s*баз[а-я]*\s*данных", r"red\s*database", r"\brdb\b", r"ред\s*бд"
    ],
    "red_virtualization": [
        r"ред\s*виртуализац[а-я]*", r"red\s*virtualization", r"ред\s*вирт[а-я]*"
    ],
    "rosa": [
        r"рос[а-я]\b", r"\brosa\b", r"rosa\s*linux", r"роса\s*линукс", r"роса\s*хром", r"роса\s*барий"
    ],
    "tarantool": [
        r"tarantool", r"тарантул[а-я]*"
    ],
    "trueconf": [
        r"trueconf", r"труконф[а-я]*"
    ],
    "usergate": [
        r"usergate", r"юзергейт[а-я]*", r"\bug\b"
    ],
}

# Скомпилированные регулярные выражения для максимальной скорости
COMPILED_PATTERNS = {
    product: [re.compile(pat, re.IGNORECASE) for pat in patterns]
    for product, patterns in PRODUCT_PATTERNS.items()
}

# Канонические названия продуктов для нечеткого поиска опечаток (Damerau-Levenshtein <= 1)
PRIMARY_PRODUCT_NAMES = {
    "kaspersky": "kaspersky",
    "касперский": "kaspersky",
    "deckhouse": "deckhouse",
    "декхаус": "deckhouse",
    "tarantool": "tarantool",
    "тарантул": "tarantool",
    "linter": "linter",
    "линтер": "linter",
    "литер": "linter",
    "express": "express",
    "экспресс": "express",
    "postgres": "postgres_pro",
    "постгрес": "postgres_pro",
    "arenadata": "arenadata_db",
    "аренадата": "arenadata_db",
    "cyberprotect": "cyberprotect",
    "киберпротект": "cyberprotect",
    "infowatch": "infowatch",
    "инфовотч": "infowatch",
    "loginom": "loginom",
    "логином": "loginom",
    "trueconf": "trueconf",
    "труконф": "trueconf",
    "usergate": "usergate",
    "юзергейт": "usergate",
}

RE_PROD_WORD = re.compile(r"[a-zA-Zа-яА-Я0-9_-]+")


def detect_products(query: str) -> List[str]:
    """
    Определяет, какие продукты из 17 семейств упомянуты в запросе пользователя.
    Возвращает список идентификаторов продуктов в порядке их появления в тексте.
    Устойчив к опечаткам в названиях продуктов (eXpres, Kaspersk, Deckhous, Tarantol).
    """
    from rapidfuzz.distance import DamerauLevenshtein

    matched_positions = []
    seen_products = set()

    # 1. Быстрый поиск по регулярным выражениям
    for product, regex_list in COMPILED_PATTERNS.items():
        first_pos = None
        for r in regex_list:
            match = r.search(query)
            if match:
                pos = match.start()
                if first_pos is None or pos < first_pos:
                    first_pos = pos
        if first_pos is not None:
            matched_positions.append((first_pos, product))
            seen_products.add(product)

    # 2. Нечеткий поиск опечаток в названиях продуктов (расстояние Дамерау-Левенштейна <= 1)
    words = RE_PROD_WORD.finditer(query)
    for m in words:
        w = m.group().lower()
        if len(w) >= 5:
            for name, prod in PRIMARY_PRODUCT_NAMES.items():
                if prod not in seen_products:
                    # Допускаем не более 1 опечатки (вставка, удаление, замена, перестановка)
                    if DamerauLevenshtein.distance(w, name) <= 1:
                        matched_positions.append((m.start(), prod))
                        seen_products.add(prod)
                        break

    # Сортируем по позиции упоминания в вопросе
    matched_positions.sort(key=lambda x: x[0])
    return [p for _, p in matched_positions]


def register_dynamic_product(product_name: str) -> None:
    """
    Динамически регистрирует новое имя продукта/документа в детекторе.
    Позволяет при загрузке нового PDF находить его имя в вопросах пользователей.
    """
    norm = product_name.strip().lower()
    if not norm or norm in PRODUCT_PATTERNS:
        return
    pattern = re.compile(rf"\b{re.escape(norm)}\b", re.IGNORECASE)
    PRODUCT_PATTERNS[norm] = [rf"\b{re.escape(norm)}\b"]
    COMPILED_PATTERNS[norm] = [pattern]
    if len(norm) >= 4:
        PRIMARY_PRODUCT_NAMES[norm] = norm

