"""PageIndex adapter for the shared Retriever contract (local mode).

PageIndex fuses retrieval with reasoning: local mode returns a grounded ANSWER
with citations, not a ranked chunk list. So retrieve() returns a single Passage
carrying that answer plus its cited sources as provenance -- enough for the
source/fact-level eval. When a local node-level retrieval API surfaces, retrieve()
can return several ranked Passages instead, no interface change.
"""
from __future__ import annotations
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retriever import Passage

INDEX_MODEL = "gpt-5.6-luna"
CHAT_MODEL = "gpt-5.6-terra"


class PageIndexRetriever:
    name = "pageindex"

    def __init__(self, corpus_dir: str):
        self.corpus_dir = corpus_dir
        self.storage = os.path.join(corpus_dir, ".pageindex")
        self.manifest = os.path.join(corpus_dir, "manifest.json")

    def _doc_ids(self) -> list[str]:
        if not os.path.exists(self.manifest):
            return []
        with open(self.manifest, encoding="utf-8") as fh:
            m = json.load(fh)
        return [v["doc_id"] for v in m.values() if v.get("doc_id")]

    def retrieve(self, query: str, k: int = 5, doc_ids: list[str] | None = None) -> list[Passage]:
        """Retrieve across the index; pass a non-empty doc_ids list to scope to those docs."""
        from pageindex import PageIndexClient
        ids = list(doc_ids) if doc_ids else self._doc_ids()
        if not ids:
            return []
        client = PageIndexClient(index_model=INDEX_MODEL, chat_model=CHAT_MODEL,
                                 storage_path=self.storage)
        answer = client.chat(query, doc_id=ids)   # tree-search + reasoning, grounded
        return [Passage(text=str(answer), source="pageindex-corpus",
                        locator="chat-grounded", method=self.name)]


def _selftest():
    import types

    calls = {}

    class _FakeClient:
        def __init__(self, **kw):
            calls["init"] = kw

        def chat(self, query, doc_id):
            calls["doc_id"] = doc_id
            return "grounded answer"

    r = PageIndexRetriever("/nonexistent-corpus")
    r._doc_ids = lambda: ["pi-all-1", "pi-all-2"]
    fake_mod = types.ModuleType("pageindex")
    fake_mod.PageIndexClient = _FakeClient
    sys.modules["pageindex"] = fake_mod
    try:
        out = r.retrieve("q", doc_ids=["pi-scoped"])
        assert calls["doc_id"] == ["pi-scoped"], calls
        assert out and out[0].text == "grounded answer", out
        r.retrieve("q")
        assert calls["doc_id"] == ["pi-all-1", "pi-all-2"], calls
    finally:
        sys.modules.pop("pageindex", None)
    print("OK pageindex_retriever selftest")


if __name__ == "__main__":
    _selftest()
