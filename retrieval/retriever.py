"""Shared retrieval contract + a tiny evaluator.

Every retrieval method -- PageIndex now; vector, graph later -- implements the
same `Retriever` protocol, so they can be measured on ONE eval set and, when the
need is proven, fused behind ONE reranker. That single downstream reranker is what
makes heterogeneous methods comparable ("uniform quality"); this module is the
common interface it will sit on top of.

No retriever and no API calls live here. Adapters are sibling files
(pageindex_retriever.py); the eval set is evalset.jsonl.

Self-test (no API): py -3.13 retriever.py
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, Optional
import json


@dataclass
class Passage:
    """One retrieved unit, uniform across methods so they can be compared/merged."""
    text: str
    source: str                      # doc name / id it came from
    locator: str = ""                # page / section / node, if known
    score: Optional[float] = None    # method-native score (not comparable across methods)
    method: str = ""                 # which retriever produced it
    parent: Optional[str] = None     # full section text (small-to-big); None if method has none


class Retriever(Protocol):
    """Contract every method implements. Keep retrieve() pure retrieval (no chat UI)."""
    name: str
    def retrieve(self, query: str, k: int = 5) -> list[Passage]: ...


# --------- eval set ---------
@dataclass
class EvalCase:
    query: str
    expect_contains: list[str] = field(default_factory=list)  # ALL of these must appear
    expect_any: list[str] = field(default_factory=list)       # at least ONE must appear (paraphrase-robust)
    expect_source: str = ""                                   # doc/section that should be cited
    must_not_use: list[str] = field(default_factory=list)     # hard-negative: NONE may appear in retrieved text/source
    note: str = ""


def load_evalset(path: str) -> list[EvalCase]:
    """One JSON object per line (jsonl). Blank lines and #-comments ignored."""
    cases = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            d = json.loads(line)
            cases.append(EvalCase(
                query=d["query"],
                expect_contains=d.get("expect_contains", []),
                expect_any=d.get("expect_any", []),
                expect_source=d.get("expect_source", ""),
                must_not_use=d.get("must_not_use", []),
                note=d.get("note", ""),
            ))
    return cases


def _case_hit(case: EvalCase, passages: list[Passage]) -> bool:
    """Pass if EVERY required substring appears in retrieved text, and (if given)
    the expected source is cited somewhere. Output-level check, so it works the
    same for PageIndex (answer) and future vector/graph (chunks)."""
    blob = "\n".join(p.text for p in passages).lower()
    src = "\n".join(f"{p.source} {p.locator}" for p in passages).lower()
    # hard-negative first: surfacing a forbidden (wrong-context) source fails the case,
    # even if the wanted substrings also happen to appear.
    if any(bad.lower() in (blob + " " + src) for bad in case.must_not_use):
        return False
    if any(sub.lower() not in blob for sub in case.expect_contains):
        return False
    if case.expect_any and not any(sub.lower() in blob for sub in case.expect_any):
        return False
    if case.expect_source and case.expect_source.lower() not in (blob + " " + src):
        return False
    return True


def evaluate(retriever, cases: list[EvalCase], k: int = 5) -> dict:
    """Run retriever over cases; return {retriever, hits, total, rate, per_case}."""
    per, hits = [], 0
    for c in cases:
        passages = retriever.retrieve(c.query, k=k)
        ok = _case_hit(c, passages)
        hits += int(ok)
        per.append({"query": c.query, "pass": ok, "n_passages": len(passages)})
    total = len(cases)
    return {
        "retriever": getattr(retriever, "name", "?"),
        "hits": hits, "total": total,
        "rate": round(hits / total, 3) if total else 0.0,
        "per_case": per,
    }


def _selftest():
    p = [Passage(text="vendor concentration raises supply-chain risk", source="sample-paper.pdf", locator="§1.1")]
    assert _case_hit(EvalCase("q", expect_contains=["vendor", "supply-chain"], expect_source="sample-paper"), p)
    assert not _case_hit(EvalCase("q", expect_contains=["logistics"]), p)       # missing substring -> fail
    assert not _case_hit(EvalCase("q", expect_source="policy-x"), p)            # wrong source -> fail
    assert _case_hit(EvalCase("q", expect_any=["risk", "logistics"]), p)        # one present -> pass
    assert not _case_hit(EvalCase("q", expect_any=["logistics", "tariffs"]), p)  # none present -> fail
    assert not _case_hit(EvalCase("q", must_not_use=["sample-paper"]), p)  # forbidden source surfaced -> fail
    assert _case_hit(EvalCase("q", expect_any=["vendor"], must_not_use=["unrelated topic"]), p)  # forbidden absent -> pass
    assert evaluate(_Stub(p), [EvalCase("q", expect_contains=["vendor"])])["rate"] == 1.0
    print("retriever selftest OK")


class _Stub:
    name = "stub"
    def __init__(self, passages): self._p = passages
    def retrieve(self, query, k=5): return self._p


if __name__ == "__main__":
    _selftest()
