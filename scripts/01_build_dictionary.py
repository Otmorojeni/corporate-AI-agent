import os
import json
import hashlib
from pathlib import Path
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
    all_records = []
    
    products = [d.name for d in CORPUS_DIR.iterdir() if d.is_dir()]
    print(f"Найдено продуктов: {len(products)}")
    for product in sorted(products):
        prod_dir = CORPUS_DIR / product
        pdf_files = list(prod_dir.glob("*.pdf"))
        print(f"[{product}] Обработка {len(pdf_files)} PDF-файлов...")
        for pdf_path in pdf_files:
            rel_doc_id = f"{product}/{pdf_path.name}"
            file_sha256 = get_file_sha256(pdf_path)
            try:
                extracted = extract_abbreviations_from_file(str(pdf_path))
                for item in extracted:
                    # Формируем запись строго по требованиям Раздела 6 README
                    record = {
                        "canonical": item.canonical,
                        "kind": "abbreviation",
                        "expansion": item.expansion,
                        "product": product,
                        "context": f"Документация {product}",
                        "aliases": [item.canonical],
                        "sources": [
                            {
                                "document_id": rel_doc_id,
                                "page": occ.page,
                                "quote": occ.quote,
                                "sha256": file_sha256,
                            }
                            for occ in item.occurrences
                        ],
                        "manual_reviewed": False
                    }
                    all_records.append(record)
            except Exception as e:
                print(f"Ошибка в файле {pdf_path.name}: {e}")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nГОТОВО! Сохранено {len(all_records)} записей в {OUTPUT_FILE}")
if __name__ == "__main__":
    main()