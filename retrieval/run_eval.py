"""Run a retriever over the eval set and print a report.

Usage:
    py -3.13 run_eval.py                      # PageIndex over the default corpus
    py -3.13 run_eval.py --corpus "C:\\...\\other-corpus"
    py -3.13 run_eval.py --evalset other.jsonl --k 8

Calls the retriever, so it hits the OpenAI API (costs). The pure-logic test that
needs no API is `py -3.13 retriever.py`.
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retriever import load_evalset, evaluate
from pageindex_retriever import PageIndexRetriever

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CORPUS = os.path.join(os.path.dirname(HERE), "pageindex-corpus")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=DEFAULT_CORPUS, help="corpus dir (has .pageindex + manifest.json)")
    ap.add_argument("--evalset", default=os.environ.get("AIO_EVALSET", os.path.join(HERE, "evalset.jsonl")))
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    cases = load_evalset(args.evalset)
    retriever = PageIndexRetriever(args.corpus)
    report = evaluate(retriever, cases, k=args.k)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n{report['retriever']}: {report['hits']}/{report['total']} passed "
          f"(rate {report['rate']})")


if __name__ == "__main__":
    main()
