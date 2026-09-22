import os
import sys
import json
import hashlib
from pathlib import Path
from typing import Dict, Tuple, List

# Добавляем корень проекта в sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.extractor import extract_abbreviations_from_file

CORPUS_DIR = Path("corpus")
OUTPUT_FILE = Path("data/terms.jsonl")


def get_file_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    products = [d.name for d in CORPUS_DIR.iterdir() if d.is_dir()]
    print(f"Найдено продуктов: {len(products)}")

    # (product, canonical, expansion) -> list of sources
    aggregated: Dict[Tuple[str, str, str], List[dict]] = {}

    for product in sorted(products):
        prod_dir = CORPUS_DIR / product
        pdf_files = sorted(list(prod_dir.glob("*.pdf")))
        print(f"[{product}] Обработка {len(pdf_files)} PDF-файлов...")

        for pdf_path in pdf_files:
            rel_doc_id = f"{product}/{pdf_path.name}"
            file_sha256 = get_file_sha256(pdf_path)

            try:
                extracted = extract_abbreviations_from_file(str(pdf_path))
                for item in extracted:
                    key = (product, item.canonical, item.expansion)
                    if key not in aggregated:
                        aggregated[key] = []

                    for occ in item.occurrences:
                        # Проверяем, нет ли уже такого источника
                        if not any(
                            s["document_id"] == rel_doc_id and s["page"] == occ.page
                            for s in aggregated[key]
                        ):
                            aggregated[key].append({
                                "document_id": rel_doc_id,
                                "page": occ.page,
                                "quote": occ.quote,
                                "sha256": file_sha256,
                            })
            except Exception as e:
                print(f"Ошибка в файле {pdf_path.name}: {e}")

    # Формируем финальный список записей строго по схеме раздела 6 README
    records = []
    for (product, canonical, expansion), sources in aggregated.items():
        records.append({
            "canonical": canonical,
            "kind": "abbreviation",
            "expansion": expansion,
            "product": product,
            "context": f"Документация {product}",
            "aliases": [canonical],
            "sources": sources,
            "manual_reviewed": False,
        })

    # Сортируем для воспроизводимости
    records.sort(key=lambda r: (r["product"], r["canonical"], r["expansion"]))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\nГОТОВО! Сохранено {len(records)} чистых словарных записей в {OUTPUT_FILE}")


if __name__ == "__main__":
    main()