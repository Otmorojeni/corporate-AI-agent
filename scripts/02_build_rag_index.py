import os
import sys
import json
from pathlib import Path
import pymupdf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CORPUS_DIR = PROJECT_ROOT / "corpus"
OUTPUT_CHUNKS_FILE = PROJECT_ROOT / "data" / "chunks_by_product.json"


def clean_page_text(text: str) -> str:
    """Удаляет лишние пустые строки и нормализует пробелы."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return "\n".join(lines)


def build_corpus_chunks():
    OUTPUT_CHUNKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    products = [d.name for d in CORPUS_DIR.iterdir() if d.is_dir()]
    print(f"Индексация базы знаний по {len(products)} продуктам...")

    chunks_by_product = {}
    total_pages = 0
    total_chunks = 0

    for product in sorted(products):
        prod_dir = CORPUS_DIR / product
        pdf_files = sorted(list(prod_dir.glob("*.pdf")))
        chunks_by_product[product] = []

        print(f"[{product}] Обработка {len(pdf_files)} PDF-документов...")
        for pdf_path in pdf_files:
            rel_doc_id = f"{product}/{pdf_path.name}"
            try:
                doc = pymupdf.open(pdf_path)
                for page_idx in range(len(doc)):
                    page_num = page_idx + 1
                    total_pages += 1
                    raw_text = doc[page_idx].get_text("text")
                    cleaned = clean_page_text(raw_text)

                    if len(cleaned) < 40:
                        continue

                    # Если страница очень большая (> 2500 символов), разбиваем на две части
                    if len(cleaned) > 2500:
                        mid = len(cleaned) // 2
                        # Ищем ближайший перенос строки
                        split_pos = cleaned.find("\n", mid)
                        if split_pos == -1:
                            split_pos = mid
                        part1 = cleaned[:split_pos].strip()
                        part2 = cleaned[split_pos:].strip()

                        if len(part1) >= 40:
                            chunks_by_product[product].append({
                                "document_id": rel_doc_id,
                                "page": page_num,
                                "text": part1
                            })
                            total_chunks += 1
                        if len(part2) >= 40:
                            chunks_by_product[product].append({
                                "document_id": rel_doc_id,
                                "page": page_num,
                                "text": part2
                            })
                            total_chunks += 1
                    else:
                        chunks_by_product[product].append({
                            "document_id": rel_doc_id,
                            "page": page_num,
                            "text": cleaned
                        })
                        total_chunks += 1
            except Exception as e:
                print(f"Ошибка при обработке {pdf_path.name}: {e}")

    with open(OUTPUT_CHUNKS_FILE, "w", encoding="utf-8") as f:
        json.dump(chunks_by_product, f, ensure_ascii=False, indent=2)

    print(f"\nИНДЕКСАЦИЯ ЗАВЕРШЕНА!")
    print(f"Всего страниц обработано: {total_pages}")
    print(f"Всего чанков сохранено: {total_chunks}")
    print(f"Файл сохранен: {OUTPUT_CHUNKS_FILE}")


if __name__ == "__main__":
    build_corpus_chunks()
