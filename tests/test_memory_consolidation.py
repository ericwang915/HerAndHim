"""
Tests for write-time memory consolidation (Mem0-lite).

The consolidation layer sits in front of MemoryManager.remember: it retrieves
similar existing memories and asks the LLM for a single
{op: ADD|UPDATE|DELETE|NOOP, key, value} decision. Every failure mode must
fall back to the original last-write-wins behaviour.
"""
import json
from unittest.mock import MagicMock

import pytest

from herandhim.core.memory.consolidation import (
    MemoryOp,
    consolidate,
    decide,
    find_similar,
)
from herandhim.core.memory.manager import MemoryManager


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_provider(payload):
    """Mock LLMProvider whose chat() returns *payload* (dict → JSON string)."""
    content = json.dumps(payload) if isinstance(payload, dict) else payload
    provider = MagicMock()
    provider.chat.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=content))]
    )
    return provider


def make_manager(tmp_path, provider=None):
    return MemoryManager(memory_dir=str(tmp_path / "memory"), provider=provider)


# ── find_similar ─────────────────────────────────────────────────────────────

class TestFindSimilar:
    def test_empty_store(self):
        assert find_similar("user_city", "Shanghai", {}) == {}

    def test_returns_related_entries(self):
        existing = {
            "user_city": "lives in Beijing",
            "favourite_food": "loves sushi",
            "user_job": "software engineer",
        }
        similar = find_similar("user_location", "user moved to Shanghai city", existing)
        assert "user_city" in similar

    def test_respects_top_k(self):
        existing = {f"fact_{i}": f"fact number {i}" for i in range(20)}
        similar = find_similar("fact_new", "fact number twenty one", existing, top_k=3)
        assert len(similar) <= 3


# ── decide ───────────────────────────────────────────────────────────────────

class TestDecide:
    def test_update_decision_parsed(self):
        provider = make_provider(
            {"op": "UPDATE", "key": "user_city", "value": "Shanghai (moved 2026)"}
        )
        op = decide("user_location", "moved to Shanghai",
                    {"user_city": "Beijing"}, provider)
        assert op == MemoryOp("UPDATE", "user_city", "Shanghai (moved 2026)")

    def test_fenced_json_accepted(self):
        provider = make_provider(
            '```json\n{"op": "NOOP", "key": "user_city", "value": ""}\n```'
        )
        op = decide("user_city", "Beijing", {"user_city": "Beijing"}, provider)
        assert op.op == "NOOP"

    def test_invalid_op_raises(self):
        provider = make_provider({"op": "MERGE", "key": "x", "value": "y"})
        with pytest.raises(ValueError):
            decide("x", "y", {"a": "b"}, provider)

    def test_update_on_unknown_key_downgraded_to_add(self):
        provider = make_provider(
            {"op": "UPDATE", "key": "hallucinated_key", "value": "z"}
        )
        op = decide("user_city", "Shanghai", {"user_city": "Beijing"}, provider)
        assert op == MemoryOp("ADD", "user_city", "Shanghai")


# ── consolidate (never raises) ───────────────────────────────────────────────

class TestConsolidate:
    def test_no_similar_memories_skips_llm(self):
        provider = MagicMock()
        op = consolidate("user_city", "Shanghai", {}, provider)
        assert op == MemoryOp("ADD", "user_city", "Shanghai")
        provider.chat.assert_not_called()

    def test_protected_key_skips_llm(self):
        provider = MagicMock()
        op = consolidate("bot_name", "Luna", {"bot_name": "Ada"}, provider)
        assert op == MemoryOp("ADD", "bot_name", "Luna")
        provider.chat.assert_not_called()

    def test_bad_json_falls_back_to_add(self):
        provider = make_provider("definitely not json")
        op = consolidate("user_city", "Shanghai",
                         {"user_city": "Beijing"}, provider)
        assert op == MemoryOp("ADD", "user_city", "Shanghai")

    def test_provider_error_falls_back_to_add(self):
        provider = MagicMock()
        provider.chat.side_effect = ConnectionError("boom")
        op = consolidate("user_city", "Shanghai",
                         {"user_city": "Beijing"}, provider)
        assert op == MemoryOp("ADD", "user_city", "Shanghai")


# ── MemoryManager integration ────────────────────────────────────────────────

class TestRememberConsolidation:
    def test_contradiction_resolved_to_one_current_city(self, tmp_path):
        """lives in A, then moved to B → exactly one current-city memory."""
        provider = make_provider(
            {"op": "UPDATE", "key": "user_city", "value": "Shanghai (moved 2026-05)"}
        )
        mgr = make_manager(tmp_path, provider)
        mgr.storage.set("user_city", "Beijing")

        result = mgr.remember("just moved to Shanghai", key="user_location")

        assert "updated" in result
        all_mem = mgr.list_all()
        assert all_mem["user_city"] == "Shanghai (moved 2026-05)"
        assert "user_location" not in all_mem  # no duplicate key invented

    def test_noop_keeps_store_unchanged(self, tmp_path):
        provider = make_provider({"op": "NOOP", "key": "user_city", "value": ""})
        mgr = make_manager(tmp_path, provider)
        mgr.storage.set("user_city", "Beijing")

        result = mgr.remember("lives in Beijing", key="city_of_user")

        assert "unchanged" in result
        assert mgr.list_all() == {"user_city": "Beijing"}

    def test_delete_removes_invalidated_memory(self, tmp_path):
        provider = make_provider({"op": "DELETE", "key": "user_dog", "value": ""})
        mgr = make_manager(tmp_path, provider)
        mgr.storage.set("user_dog", "has a dog called Rex")

        result = mgr.remember("sadly Rex was rehomed, no dog anymore", key="dog_update")

        assert "removed" in result
        assert "user_dog" not in mgr.list_all()

    def test_first_write_stores_directly_without_llm(self, tmp_path):
        provider = MagicMock()
        mgr = make_manager(tmp_path, provider)

        result = mgr.remember("Shanghai", key="user_city")

        assert "stored" in result
        assert mgr.list_all()["user_city"] == "Shanghai"
        provider.chat.assert_not_called()

    def test_llm_failure_falls_back_to_last_write_wins(self, tmp_path):
        provider = make_provider("not json at all")
        mgr = make_manager(tmp_path, provider)
        mgr.storage.set("user_city", "Beijing")

        mgr.remember("Shanghai", key="user_city")

        assert mgr.list_all()["user_city"] == "Shanghai"

    def test_no_provider_keeps_original_behaviour(self, tmp_path):
        mgr = make_manager(tmp_path, provider=None)
        result = mgr.remember("Beijing", key="user_city")
        assert result == "Memory stored: [user_city] = Beijing"

    def test_consolidation_disabled_via_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERANDHIM_MEMORY_CONSOLIDATION", "false")
        provider = MagicMock()
        mgr = make_manager(tmp_path, provider)
        mgr.storage.set("user_city", "Beijing")

        mgr.remember("Shanghai", key="user_city")

        assert mgr.list_all()["user_city"] == "Shanghai"
        provider.chat.assert_not_called()
