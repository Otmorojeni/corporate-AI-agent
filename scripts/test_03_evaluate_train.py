import os
import sys
import time
import asyncio
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas import AssistantQueryRequest
from src.core.pipeline import process_user_query

# 5 эталонных запросов из evaluation__train.xlsx
TRAIN_BENCHMARK = [
    {
        "id": 1,
        "query": "Как в документации eXpress расшифровывается CTS?",
        "expected_terms": [("CTS", "Corporate Transport Server")],
        "mandatory_facts": [
            "Corporate Transport Server"
        ]
    },
    {
        "id": 2,
        "query": "Что требуется установить на защищаемом компьютере перед добавлением поддержки SNMP в Kaspersky Embedded Systems Security?",
        "expected_terms": [("SNMP", "Simple Network Management Protocol")],
        "mandatory_facts": [
            "Simple Network Management Protocol",
            "Microsoft SNMP"
        ]
    },
    {
        "id": 3,
        "query": "Как DKP обрабатывает первое обращение к защищённому ресурсу уже аутентифицированного пользователя и пользователя с единственным внешним провайдером?",
        "expected_terms": [("DKP", "Deckhouse Kubernetes Platform")],
        "mandatory_facts": [
            "Deckhouse Kubernetes Platform",
            ["исходному ресурсу", "обратно к ресурсу", "первоначально обращался"],
            "провайдер"
        ]
    },
    {
        "id": 4,
        "query": "В Deckhouse несколько сервисов NLB должны использовать общий адрес, а VPA — подбирать ресурсы контейнера. Как настроить общий адрес и почему лимиты не изменятся автоматически?",
        "expected_terms": [
            ("NLB", "Network Load Balancer"),
            ("VPA", "Vertical Pod Autoscaler")
        ],
        "mandatory_facts": [
            "Network Load Balancer",
            "Vertical Pod Autoscaler",
            "network.deckhouse.io/load-balancer-shared-ip-key",
            "requests"
        ]
    },
    {
        "id": 5,
        "query": "Как в ЛИНТЕР загрузить реплицируемые данные с ненулевым WAL, а в Tarantool восстановить данные после потери памяти с помощью WAL?",
        "expected_terms": [
            ("WAL", "Write Access Level"),
            ("WAL", "write ahead log")
        ],
        "mandatory_facts": [
            "Write Access Level",
            "write ahead log",
            "-ux",
            ["checkpoint", "контрольн"]
        ]
    }
]


async def evaluate_single(case: dict) -> dict:
    req = AssistantQueryRequest(request_id=f"eval-{case['id']}", query=case["query"])
    start_t = time.time()
    resp = await process_user_query(req)
    latency = time.time() - start_t

    # 1. Оценка R (Recognition)
    detected_canons = [t.canonical.upper() for t in resp.detected_terms]
    expected_canons = [exp[0].upper() for exp in case["expected_terms"]]
    r_score = 1.0 if sorted(detected_canons) == sorted(expected_canons) else 0.0

    # 2. Оценка E (Expansion)
    e_score = 1.0
    detected_pairs = [(t.canonical.upper(), t.expansion.strip().lower()) for t in resp.detected_terms]
    for canon, exp in case["expected_terms"]:
        match = any(
            c == canon.upper() and (exp.lower() in d_exp or d_exp in exp.lower())
            for c, d_exp in detected_pairs
        )
        if not match:
            e_score = 0.0
            break

    # 3. Оценка A (Answer & Mandatory facts)
    a_score = 1.0
    ans_lower = resp.answer.lower()
    for fact in case["mandatory_facts"]:
        if isinstance(fact, list):
            if not any(f.lower() in ans_lower for f in fact):
                a_score = 0.0
                break
        else:
            if fact.lower() not in ans_lower:
                a_score = 0.0
                break

    quality = (r_score + e_score + a_score) / 3.0 * 100.0

    return {
        "id": case["id"],
        "query": case["query"],
        "answer": resp.answer,
        "detected_terms": [(t.canonical, t.expansion) for t in resp.detected_terms],
        "sources": [(s.document_id, s.page) for s in resp.sources] if resp.sources else [],
        "latency": latency,
        "R": r_score,
        "E": e_score,
        "A": a_score,
        "quality": quality,
    }


async def main():
    print("=" * 70)
    print("   ЗАПУСК БЕНЧМАРКА НА ЭТАЛОННОЙ ВЫБОРКЕ (evaluation__train.xlsx)")
    print("=" * 70)

    results = []
    for case in TRAIN_BENCHMARK:
        print(f"\n[Запрос #{case['id']}]: {case['query']}")
        res = await evaluate_single(case)
        results.append(res)
        print(f"  R: {res['R']:.1f} | E: {res['E']:.1f} | A: {res['A']:.1f} | Quality: {res['quality']:.1f}% | Время: {res['latency']:.2f}с")
        print(f"  Термины: {res['detected_terms']}")
        print(f"  Источники: {res['sources']}")
        print(f"  Ответ: {res['answer'][:200]}...")

    avg_r = sum(r["R"] for r in results) / len(results)
    avg_e = sum(r["E"] for r in results) / len(results)
    avg_a = sum(r["A"] for r in results) / len(results)
    avg_quality = sum(r["quality"] for r in results) / len(results)
    avg_latency = sum(r["latency"] for r in results) / len(results)

    print("\n" + "=" * 70)
    print("ИТОГОВЫЕ МЕТРИКИ НА ТРЕНИРОВОЧНОЙ ВЫБОРКЕ:")
    print(f"  Среднее R (распознавание): {avg_r * 100:.1f}%")
    print(f"  Среднее E (значение):      {avg_e * 100:.1f}%")
    print(f"  Среднее A (ответ):         {avg_a * 100:.1f}%")
    print(f"  ОБЩИЙ QUALITY:            {avg_quality:.1f}%")
    print(f"  Средняя задержка:          {avg_latency:.2f} сек/запрос")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
