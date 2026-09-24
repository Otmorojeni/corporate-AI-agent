import os
import sys
import time
import json
from pathlib import Path
from difflib import SequenceMatcher

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import openpyxl
from starlette.testclient import TestClient
from src.api.app import app

client = TestClient(app)
XLSX_PATH = PROJECT_ROOT / "evaluation__train.xlsx"

def load_train_cases():
    wb = openpyxl.load_workbook(XLSX_PATH)
    ws = wb.active
    rows = [r for r in ws.iter_rows(values_only=True) if any(x is not None for x in r)]
    cases = []
    for idx, r in enumerate(rows[1:], 1):
        query = str(r[0]).strip()
        abbr_raw = str(r[1]).strip() if r[1] is not None else ""
        expected_abbrs = [a.strip() for a in abbr_raw.splitlines() if a.strip()]
        ref_answer = str(r[2]).strip() if r[2] is not None else ""
        mandatory_facts = str(r[3]).strip() if len(r) > 3 and r[3] is not None else ""
        cases.append({
            "case_id": f"Case-{idx:02d}",
            "query": query,
            "expected_abbrs": expected_abbrs,
            "ref_answer": ref_answer,
            "mandatory_facts": mandatory_facts
        })
    return cases

def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def word_jaccard(a: str, b: str) -> float:
    w1 = set(a.lower().split())
    w2 = set(b.lower().split())
    if not w1 and not w2:
        return 1.0
    return len(w1 & w2) / len(w1 | w2)

def main():
    cases = load_train_cases()
    print(f"Loaded {len(cases)} cases from {XLSX_PATH}")
    
    results = []
    
    for case in cases:
        cid = case["case_id"]
        q = case["query"]
        print(f"\n--- Testing {cid}: '{q[:50]}...' ---")
        
        runs = []
        for run_idx in range(3):
            req_id = f"real-eval-{cid.lower()}-run{run_idx+1}"
            t0 = time.perf_counter()
            resp = client.post("/v1/assistant/query", json={"request_id": req_id, "query": q})
            elapsed = time.perf_counter() - t0
            
            data = resp.json()
            ans = data.get("answer", "")
            terms = data.get("detected_terms", [])
            sources = data.get("sources", [])
            runs.append({
                "run": run_idx + 1,
                "elapsed": elapsed,
                "answer": ans,
                "detected_terms": terms,
                "sources_count": len(sources)
            })
            print(f"  Run {run_idx+1}: {elapsed:.2f}s | len(ans)={len(ans)} | terms={[t['canonical'] for t in terms]}")

        # Analysis of repeatability
        ans1, ans2, ans3 = runs[0]["answer"], runs[1]["answer"], runs[2]["answer"]
        terms1 = [t["canonical"] for t in runs[0]["detected_terms"]]
        terms2 = [t["canonical"] for t in runs[1]["detected_terms"]]
        terms3 = [t["canonical"] for t in runs[2]["detected_terms"]]
        
        terms_identical = (terms1 == terms2 == terms3)
        exact_string_match = (ans1 == ans2 == ans3)
        
        sim_1_2 = text_similarity(ans1, ans2)
        sim_2_3 = text_similarity(ans2, ans3)
        sim_1_3 = text_similarity(ans1, ans3)
        avg_text_sim = (sim_1_2 + sim_2_3 + sim_1_3) / 3.0
        
        jaccard_1_2 = word_jaccard(ans1, ans2)
        jaccard_2_3 = word_jaccard(ans2, ans3)
        jaccard_1_3 = word_jaccard(ans1, ans3)
        avg_jaccard = (jaccard_1_2 + jaccard_2_3 + jaccard_1_3) / 3.0
        
        latencies = [r["elapsed"] for r in runs]
        
        case_res = {
            "case_id": cid,
            "query": q,
            "expected_abbrs": case["expected_abbrs"],
            "latencies": latencies,
            "avg_latency": sum(latencies) / len(latencies),
            "terms_identical": terms_identical,
            "exact_string_match": exact_string_match,
            "avg_text_similarity": avg_text_sim,
            "avg_word_jaccard": avg_jaccard,
            "runs": runs
        }
        results.append(case_res)
        print(f"  Exact Match: {exact_string_match}")
        print(f"  Avg Text Similarity: {avg_text_sim * 100:.2f}%")
        print(f"  Avg Word Jaccard: {avg_jaccard * 100:.2f}%")
        if not exact_string_match:
            print(f"  Diff sample (Run 1 vs Run 2):\n    Run 1: {ans1[:100]}...\n    Run 2: {ans2[:100]}...")

    # Save detailed output
    out_file = PROJECT_ROOT / "data" / "real_repeatability_benchmark.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved detailed benchmark to {out_file}")

if __name__ == "__main__":
    main()
