"""
Write-time memory consolidation (Mem0-lite).

Problem
-------
``MemoryManager.remember`` is last-write-wins per key.  The agent invents new
keys for the same fact ("user_city", "user_location", "where_user_lives"),
contradictions stack, and recall gets noisy.

Approach
--------
Before ``storage.set``, retrieve the top-k most similar existing memories via
the same BM25 hybrid retrieval that ``recall()`` uses, then make one small LLM
call that decides a single operation::

    {"op": "ADD" | "UPDATE" | "DELETE" | "NOOP", "key": ..., "value": ...}

and apply it.  Markdown files stay the source of truth — no graph store, no
extra database.  Every failure mode (no provider, LLM error, bad JSON, invalid
op) falls back to the original last-write-wins behaviour, so consolidation can
never lose a write.

Enabled by default when the MemoryManager has a provider; turn it off with
``memory.consolidation: false`` in herandhim.json or
``HERANDHIM_MEMORY_CONSOLIDATION=false``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..llm.base import LLMProvider

logger = logging.getLogger(__name__)

VALID_OPS = {"ADD", "UPDATE", "DELETE", "NOOP"}
DEFAULT_TOP_K = 5

# System-managed keys written by onboarding/internal code with exact keys the
# rest of the codebase looks up verbatim — never let the LLM rename these.
PROTECTED_KEYS = {
    "bot_name", "user_name", "user_profile",
    "assistant_personality", "assistant_focus_area",
    "assistant_tone", "assistant_domain",
    "onboarding_completed", "agent_culture",
}


@dataclass
class MemoryOp:
    """One consolidation decision."""
    op: str
    key: str
    value: str


def _fact_text(key: str, value: str) -> str:
    # Underscored keys ("user_city") tokenise as one BM25 token; split them so
    # "user_location" and "user_city" actually share terms.
    return f"{key.replace('_', ' ')}: {value}"


def find_similar(
    key: str,
    content: str,
    existing: dict[str, str],
    top_k: int = DEFAULT_TOP_K,
) -> dict[str, str]:
    """Return the top-k existing memories most similar to the incoming fact.

    Uses the same sparse BM25 retrieval as ``MemoryManager.recall``. BM25's idf
    goes non-positive on very small corpora (a term present in every doc), so
    when it returns nothing we fall back to plain word overlap — recall is what
    matters here; the LLM decision provides the precision.
    """
    if not existing:
        return {}

    from ..retrieval.retriever import HybridRetriever
    from ..retrieval.sparse import _tokenize

    query = _fact_text(key, content)
    corpus = [
        {"source": k, "content": _fact_text(k, v)}
        for k, v in existing.items()
    ]
    retriever = HybridRetriever(
        provider=None,
        use_sparse=True,
        use_dense=False,
        use_reranker=False,
    )
    retriever.fit(corpus)
    hits = retriever.retrieve(query, top_k=top_k)
    if hits:
        return {h["source"]: existing[h["source"]] for h in hits if h["source"] in existing}

    query_tokens = set(_tokenize(query))
    scored = sorted(
        (
            (len(query_tokens & set(_tokenize(_fact_text(k, v)))), k)
            for k, v in existing.items()
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return {k: existing[k] for overlap, k in scored[:top_k] if overlap > 0}


def _build_prompt(key: str, content: str, similar: dict[str, str]) -> str:
    existing_lines = "\n".join(f"- [{k}]: {v}" for k, v in similar.items())
    return (
        "You maintain the long-term memory store of an AI companion. "
        "A new fact is about to be saved. Compare it against the existing "
        "similar memories and decide ONE operation:\n"
        "- ADD: genuinely new information — store it (you may pick a cleaner key).\n"
        "- UPDATE: it changes or refines an existing memory — return that EXISTING "
        "key with the merged, current value (e.g. moved city: keep ONE current city).\n"
        "- DELETE: it invalidates an existing memory and nothing new needs storing "
        "— return that existing key.\n"
        "- NOOP: already known; nothing to change.\n\n"
        f"NEW FACT:\nkey: {key}\nvalue: {content}\n\n"
        f"EXISTING SIMILAR MEMORIES:\n{existing_lines}\n\n"
        'Return ONLY valid JSON, no explanation: '
        '{"op": "ADD|UPDATE|DELETE|NOOP", "key": "...", "value": "..."}'
    )


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
    if raw.endswith("```"):
        raw = raw[: raw.rfind("```")]
    return raw.strip()


def decide(
    key: str,
    content: str,
    similar: dict[str, str],
    provider: "LLMProvider",
) -> MemoryOp:
    """One small LLM call deciding what to do with the incoming fact.

    Raises on any provider/parse failure — the caller falls back to a plain
    ADD (the pre-consolidation behaviour).
    """
    response = provider.chat(
        messages=[{"role": "user", "content": _build_prompt(key, content, similar)}],
        tools=[],
        tool_choice="none",
    )
    raw = _strip_fences(response.choices[0].message.content or "")
    data = json.loads(raw)

    op = str(data.get("op", "")).strip().upper()
    if op not in VALID_OPS:
        raise ValueError(f"invalid consolidation op: {op!r}")

    target_key = str(data.get("key", "")).strip() or key
    value = str(data.get("value", "")).strip() or content

    if op in ("UPDATE", "DELETE") and target_key not in similar:
        # The LLM must not touch keys it wasn't shown; treat as a plain ADD
        # under the proposed key rather than guessing.
        logger.debug(
            "[Consolidation] %s targets unknown key %r — downgrading to ADD.",
            op, target_key,
        )
        return MemoryOp("ADD", key, content)

    return MemoryOp(op, target_key, value)


def consolidate(
    key: str,
    content: str,
    existing: dict[str, str],
    provider: "LLMProvider",
    top_k: int = DEFAULT_TOP_K,
) -> MemoryOp:
    """Decide how to store the incoming fact against existing memories.

    Never raises: any failure returns ``ADD(key, content)``, i.e. the original
    last-write-wins behaviour.
    """
    if key in PROTECTED_KEYS:
        return MemoryOp("ADD", key, content)

    try:
        similar = find_similar(key, content, existing, top_k=top_k)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Consolidation] Similarity search failed (non-fatal): %s", exc)
        return MemoryOp("ADD", key, content)

    if not similar:
        return MemoryOp("ADD", key, content)  # nothing to reconcile — skip the LLM call

    try:
        op = decide(key, content, similar, provider)
        logger.debug("[Consolidation] %s [%s] (was key=%s)", op.op, op.key, key)
        return op
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Consolidation] LLM decision failed (non-fatal): %s", exc)
        return MemoryOp("ADD", key, content)
