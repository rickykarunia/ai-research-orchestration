"""Run every retriever over the eval-set, dump raw outputs for the rag-eval subagent.

    py -3.13 compare.py

Both methods run in this one interpreter (Python313 has pageindex + fastembed).
Writes eval-results.json = [{query, expect_*, note, methods:{pageindex:[...], vector:[...]}}].
The rag-eval subagent reads that + evalset.jsonl and judges semantically.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retriever import load_evalset
from pageindex_retriever import PageIndexRetriever
from vector_store import VectorRetriever

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PAGEINDEX_CORPUS = os.path.join(ROOT, "pageindex-corpus")
VECTOR_CORPUS = os.path.join(ROOT, "vector-corpus")


def _passages(r, q):
    try:
        return [vars(p) for p in r.retrieve(q, k=5)]
    except Exception as e:
        return [{"error": str(e)}]


def main():
    cases = load_evalset(os.environ.get("AIO_EVALSET", os.path.join(HERE, "evalset.jsonl")))
    retrievers = [PageIndexRetriever(PAGEINDEX_CORPUS), VectorRetriever(VECTOR_CORPUS)]
    results = []
    for c in cases:
        row = {"query": c.query, "expect_contains": c.expect_contains,
               "expect_any": c.expect_any, "must_not_use": c.must_not_use,
               "note": c.note, "methods": {}}
        for r in retrievers:
            print(f"[{r.name}] {c.query[:50]}", flush=True)
            row["methods"][r.name] = _passages(r, c.query)
        results.append(row)
    out = os.environ.get("AIO_EVAL_OUT", os.path.join(HERE, "eval-results.json"))
    json.dump(results, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\nwrote {out}: {len(results)} query x {len(retrievers)} methods")


if __name__ == "__main__":
    main()
