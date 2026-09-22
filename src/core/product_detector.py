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
        r"ред\s*виртуализац[а-я]*", r"red\s*virtualization", r"редвирт[а-я]*"
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


def detect_products(query: str) -> List[str]:
    """
    Определяет, какие продукты из 17 семейств упомянуты в запросе пользователя.
    Возвращает список идентификаторов продуктов в порядке их появления в тексте.
    Если продукты не найдены явно, возвращает пустой список.
    """
    matched_positions = []
    
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
            
    # Сортируем по позиции упоминания в вопросе
    matched_positions.sort(key=lambda x: x[0])
    return [p for _, p in matched_positions]
