"""
policy_rag.py

Retrieval over the policy documents in copilot/policies/. Uses TF-IDF +
cosine similarity rather than an embeddings API call -- fully local, no
API key required, which matters because retrieval is the one part of the
copilot that should work identically whether or not a real LLM is
configured (see llm.py).

check_margin_policy() then does something a plain RAG answer wouldn't:
it pulls the numeric floor out of the retrieved text and compares it
against the ACTUAL predicted margin, so a policy conflict is a computed
fact, not a paraphrase the LLM might get wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

POLICIES_DIR = Path(__file__).resolve().parent / "policies"


@dataclass
class PolicyChunk:
    source: str
    text: str


def _load_chunks() -> list[PolicyChunk]:
    chunks = []
    for path in sorted(POLICIES_DIR.glob("*.md")):
        text = path.read_text()
        for para in [p.strip() for p in text.split("\n\n") if p.strip() and not p.strip().startswith("#")]:
            chunks.append(PolicyChunk(source=path.name, text=para.replace("\n", " ")))
    return chunks


_CHUNKS: list[PolicyChunk] = _load_chunks()
_VECTORIZER = TfidfVectorizer()
_MATRIX = _VECTORIZER.fit_transform([c.text for c in _CHUNKS]) if _CHUNKS else None


def retrieve(query: str, k: int = 3) -> list[PolicyChunk]:
    if _MATRIX is None:
        return []
    qv = _VECTORIZER.transform([query])
    sims = cosine_similarity(qv, _MATRIX)[0]
    top_idx = sims.argsort()[::-1][:k]
    return [_CHUNKS[i] for i in top_idx if sims[i] > 0]


def _extract_pct(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    return float(m.group(1)) / 100 if m else None


def find_min_margin_for_category(category: str) -> tuple[float, str] | None:
    """Returns (min_margin_pct, source_chunk_text) or None if no policy chunk mentions this category."""
    category_words = category.replace("_", " ")
    chunks = retrieve(f"minimum margin {category_words}", k=8)
    for c in chunks:
        if category_words in c.text.lower() or category.split("_")[0] in c.text.lower():
            pct = _extract_pct(c.text)
            if pct is not None:
                return pct, c.text
    return None


def check_margin_policy(category: str, predicted_margin_pct: float) -> dict:
    found = find_min_margin_for_category(category)
    if found is None:
        return {"conflict": False, "policy_min_margin_pct": None, "note": "no category-specific policy chunk found"}
    min_required, source_text = found
    conflict = predicted_margin_pct < min_required
    return {
        "conflict": conflict,
        "policy_min_margin_pct": min_required,
        "predicted_margin_pct": predicted_margin_pct,
        "source_text": source_text,
        "note": (
            f"predicted margin {predicted_margin_pct:.1%} is below the {min_required:.0%} policy floor for "
            f"{category}"
            if conflict
            else f"predicted margin {predicted_margin_pct:.1%} satisfies the {min_required:.0%} policy floor"
        ),
    }
