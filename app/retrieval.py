"""
Deterministic local retrieval for the Aster & Row knowledge base.

The retriever:
- indexes loaded Markdown chunks;
- uses lexical TF-IDF similarity;
- prefers active, official, customer-facing policy content;
- keeps multiple relevant authoritative sources so genuine conflicts can be detected;
- never executes or treats retrieved text as instructions.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List

from app.knowledge import load_documents


TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'-]*")


def tokenize(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


@dataclass
class RetrievedChunk:
    chunk: Dict[str, Any]
    score: float


class KnowledgeRetriever:
    def __init__(self, knowledge_path: str = "knowledge-base") -> None:
        self.chunks = load_documents(knowledge_path)
        self.documents = [
            " ".join(
                [
                    str(chunk.get("title") or ""),
                    " ".join(chunk.get("heading_path") or []),
                    str(chunk.get("content") or ""),
                ]
            )
            for chunk in self.chunks
        ]

        self.doc_tokens = [tokenize(doc) for doc in self.documents]
        self.doc_freq: Counter[str] = Counter()

        for tokens in self.doc_tokens:
            for token in set(tokens):
                self.doc_freq[token] += 1

        self.num_docs = len(self.documents)

    def _idf(self, token: str) -> float:
        df = self.doc_freq.get(token, 0)
        return math.log((self.num_docs + 1) / (df + 1)) + 1.0

    def _similarity(self, query_tokens: List[str], doc_tokens: List[str]) -> float:
        if not query_tokens or not doc_tokens:
            return 0.0

        query_counts = Counter(query_tokens)
        doc_counts = Counter(doc_tokens)

        query_norm = 0.0
        doc_norm = 0.0
        dot = 0.0

        for token, count in query_counts.items():
            weight = count * self._idf(token)
            query_norm += weight * weight

            doc_weight = doc_counts.get(token, 0) * self._idf(token)
            dot += weight * doc_weight

        for token, count in doc_counts.items():
            weight = count * self._idf(token)
            doc_norm += weight * weight

        if query_norm == 0 or doc_norm == 0:
            return 0.0

        return dot / math.sqrt(query_norm * doc_norm)

    @staticmethod
    def _metadata_boost(chunk: Dict[str, Any]) -> float:
        """
        Metadata affects ranking, but never turns an irrelevant passage
        into a relevant one.
        """
        boost = 0.0

        if chunk.get("status") == "active":
            boost += 0.15
        elif chunk.get("status") == "superseded":
            boost -= 0.20

        if chunk.get("policy_authority") == "official":
            boost += 0.15

        if chunk.get("audience") == "customer":
            boost += 0.10
        elif chunk.get("audience") == "internal":
            boost -= 0.20

        return boost

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.08,
    ) -> List[RetrievedChunk]:
        query_tokens = tokenize(query)

        scored: List[RetrievedChunk] = []

        for chunk, doc_tokens in zip(self.chunks, self.doc_tokens):
            lexical_score = self._similarity(query_tokens, doc_tokens)

            if lexical_score < min_score:
                continue

            score = lexical_score + self._metadata_boost(chunk)

            scored.append(
                RetrievedChunk(
                    chunk=chunk,
                    score=score,
                )
            )

        scored.sort(
            key=lambda result: (
                result.score,
                result.chunk.get("status") == "active",
                result.chunk.get("policy_authority") == "official",
            ),
            reverse=True,
        )

        return scored[:top_k]

    @staticmethod
    def format_source(result: RetrievedChunk) -> str:
        chunk = result.chunk
        heading_path = " > ".join(chunk.get("heading_path") or [])

        return (
            f"{chunk.get('filename')} — {heading_path}"
        )

    def search_with_sources(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        results = self.search(query, top_k=top_k)

        return [
            {
                "filename": result.chunk.get("filename"),
                "heading": result.chunk.get("heading"),
                "heading_path": result.chunk.get("heading_path"),
                "content": result.chunk.get("content"),
                "title": result.chunk.get("title"),
                "status": result.chunk.get("status"),
                "policy_authority": result.chunk.get("policy_authority"),
                "audience": result.chunk.get("audience"),
                "score": round(result.score, 4),
                "source": self.format_source(result),
            }
            for result in results
        ]
