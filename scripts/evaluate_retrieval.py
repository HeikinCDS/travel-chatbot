"""Compare the FTS5 baseline with JomVoyage hybrid semantic retrieval."""

from __future__ import annotations

import json
from pathlib import Path
import statistics
import sys
from time import perf_counter


PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from recommendation_engine.recommendation_engine import recommend_attractions
from recommendation_engine.semantic_search import SemanticRanker


CASES_PATH = PROJECT_DIR / "evaluation" / "retrieval_queries.json"
TOP_K = 3


def rank_metrics(expected_ids, retrieved_ids):
    """Return Hit@K and reciprocal rank for one fixed query."""

    expected = set(expected_ids)
    for index, attraction_id in enumerate(retrieved_ids, start=1):
        if attraction_id in expected:
            return 1, 1.0 / index
    return 0, 0.0


def run_case(case, *, semantic_ranker, semantic_mode):
    started = perf_counter()
    results = recommend_attractions(
        state=case["state"],
        interest=case["interest"],
        query_text=case["query"],
        semantic_ranker=semantic_ranker,
        semantic_mode=semantic_mode,
        limit=TOP_K,
    )
    elapsed_ms = (perf_counter() - started) * 1000
    retrieved_ids = [item["attraction_id"] for item in results]
    hit, reciprocal_rank = rank_metrics(
        case["expected_ids"],
        retrieved_ids,
    )
    return {
        "hit": hit,
        "reciprocal_rank": reciprocal_rank,
        "elapsed_ms": elapsed_ms,
        "names": [item["attraction_name"] for item in results],
    }


def summarise(results):
    return {
        "hit_at_3": sum(item["hit"] for item in results) / len(results),
        "mrr": sum(item["reciprocal_rank"] for item in results) / len(results),
        "average_ms": statistics.fmean(item["elapsed_ms"] for item in results),
        "warm_average_ms": statistics.fmean(
            item["elapsed_ms"] for item in results[1:] or results
        ),
        "median_ms": statistics.median(
            item["elapsed_ms"] for item in results
        ),
        "maximum_ms": max(item["elapsed_ms"] for item in results),
    }


def main():
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    adaptive_ranker = SemanticRanker()
    always_ranker = SemanticRanker()
    fts_results = []
    adaptive_results = []
    always_results = []

    print(f"Evaluating {len(cases)} fixed queries at Top-{TOP_K}\n")
    for case in cases:
        fts = run_case(
            case,
            semantic_ranker=False,
            semantic_mode="off",
        )
        adaptive = run_case(
            case,
            semantic_ranker=adaptive_ranker,
            semantic_mode="adaptive",
        )
        always = run_case(
            case,
            semantic_ranker=always_ranker,
            semantic_mode="always",
        )
        fts_results.append(fts)
        adaptive_results.append(adaptive)
        always_results.append(always)
        marker = "PASS" if adaptive["hit"] else "MISS"
        print(
            f"{case['id']} {marker:<4} | FTS: {', '.join(fts['names'])} "
            f"| Adaptive: {', '.join(adaptive['names'])} "
            f"| Always: {', '.join(always['names'])}"
        )

    fts_summary = summarise(fts_results)
    adaptive_summary = summarise(adaptive_results)
    always_summary = summarise(always_results)
    print("\nSummary")
    print("-" * 68)
    print(
        f"FTS5   Hit@3: {fts_summary['hit_at_3']:.1%} | "
        f"MRR: {fts_summary['mrr']:.3f} | "
        f"average: {fts_summary['average_ms']:.1f} ms | "
        f"median: {fts_summary['median_ms']:.1f} ms"
    )
    print(
        f"Adaptive Hit@3: {adaptive_summary['hit_at_3']:.1%} | "
        f"MRR: {adaptive_summary['mrr']:.3f} | "
        f"average: {adaptive_summary['average_ms']:.1f} ms | "
        f"median: {adaptive_summary['median_ms']:.1f} ms | "
        f"maximum: {adaptive_summary['maximum_ms']:.1f} ms"
    )
    print(
        f"Always Hit@3: {always_summary['hit_at_3']:.1%} | "
        f"MRR: {always_summary['mrr']:.3f} | "
        f"average: {always_summary['average_ms']:.1f} ms | "
        f"warm average: {always_summary['warm_average_ms']:.1f} ms"
    )


if __name__ == "__main__":
    main()
