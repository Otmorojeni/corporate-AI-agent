import asyncio
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.llm_client import LLMClient
from src.core.product_detector import detect_products
from src.core.matcher import TermMatcher
from src.core.retriever import DocumentRetriever

mod = importlib.import_module("scripts.03_evaluate_train")
TRAIN_BENCHMARK = mod.TRAIN_BENCHMARK

async def main():
    client = LLMClient()
    matcher = TermMatcher()
    retriever = DocumentRetriever()

    print("=" * 80)
    print("ИЗМЕРЕНИЕ РАСХОДА ТОКЕНОВ ПО ВСЕМ ЭТАЛОННЫМ ЗАПРОСАМ (Лимит: 32 000)")
    print("=" * 80)

    totals = []
    for c in TRAIN_BENCHMARK:
        query = c["query"]
        cid = c["id"]
        prods = detect_products(query)
        terms = matcher.match_terms(query, prods)
        chunks = retriever.retrieve(query, prods, terms, top_k=4)
        sys_prompt = client._build_system_prompt(prods, terms, chunks)

        resp = await client.client.chat.completions.create(
            model=client.model_name,
            temperature=0.0,
            max_tokens=600,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": query},
            ],
        )
        u = resp.usage
        totals.append(u.total_tokens)
        print(f"Запрос #{cid}: Prompt: {u.prompt_tokens:4d} | Completion: {u.completion_tokens:3d} | TOTAL: {u.total_tokens:4d} токенов (Запас: {32000 - u.total_tokens:5d})")

    max_t = max(totals)
    avg_t = sum(totals) / len(totals)
    print("-" * 80)
    print(f"Максимальный расход: {max_t} токенов ({(max_t / 32000) * 100:.2f}% от лимита 32 000)")
    print(f"Средний расход:     {avg_t:.1f} токенов ({(avg_t / 32000) * 100:.2f}% от лимита)")
    print(f"Свободный запас:    {32000 - max_t} токенов ({(1 - max_t / 32000) * 100:.2f}% свободно)")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
