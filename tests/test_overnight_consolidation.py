"""
Tests for overnight (quiet-hours) memory consolidation.

The nightly batch pass reuses the write-time helpers (find_similar + decide)
to merge duplicates and archive invalidated/stale entries.  Destructive
outcomes must archive to ARCHIVE.md (never hard-delete), protected keys must
never be touched, and every failure mode must leave MEMORY.md intact.
"""
import json
import os
from unittest.mock import MagicMock

from herandhim.core.memory.overnight import (
    ARCHIVE_FILE,
    REPORT_FILE,
    archive_entry,
    consolidate_store,
    run_overnight_consolidation,
)
from herandhim.core.memory.storage import MemoryStorage


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_provider(payload):
    """Mock LLMProvider whose chat() returns *payload* (dict → JSON string)."""
    content = json.dumps(payload) if isinstance(payload, dict) else payload
    provider = MagicMock()
    provider.chat.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=content))]
    )
    return provider


def make_storage(tmp_path, entries=None):
    storage = MemoryStorage(str(tmp_path / "memory"))
    for key, value in (entries or {}).items():
        storage.set(key, value)
    return storage


def read_archive(storage):
    path = os.path.join(storage.memory_dir, ARCHIVE_FILE)
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


# ── archive_entry ────────────────────────────────────────────────────────────

class TestArchiveEntry:
    def test_moves_entry_to_archive(self, tmp_path):
        storage = make_storage(tmp_path, {"user_dog": "has a dog called Rex"})
        assert archive_entry(storage, "user_dog", "invalidated") is True
        assert "user_dog" not in storage.list_all()
        archive = read_archive(storage)
        assert "## user_dog" in archive
        assert "has a dog called Rex" in archive
        assert "invalidated" in archive

    def test_protected_key_refused(self, tmp_path):
        storage = make_storage(tmp_path, {"bot_name": "Luna"})
        assert archive_entry(storage, "bot_name", "any reason") is False
        assert storage.list_all() == {"bot_name": "Luna"}
        assert read_archive(storage) == ""

    def test_missing_key_is_noop(self, tmp_path):
        storage = make_storage(tmp_path)
        assert archive_entry(storage, "ghost", "reason") is False


# ── consolidate_store: merge pass ────────────────────────────────────────────

class TestMergePass:
    def test_duplicates_merged_into_one_key(self, tmp_path):
        """Two near-duplicate city entries end up as one, the other archived."""
        provider = make_provider(
            {"op": "UPDATE", "key": "user_city", "value": "Shanghai (moved 2026)"}
        )
        storage = make_storage(tmp_path, {
            "user_city": "user lives in Beijing",
            "user_location": "user moved to Shanghai city",
        })

        report = consolidate_store(storage, provider)

        all_mem = storage.list_all()
        assert all_mem["user_city"] == "Shanghai (moved 2026)"
        assert "user_location" not in all_mem
        assert "## user_location" in read_archive(storage)
        assert report.merged >= 1
        assert report.archived >= 1

    def test_delete_archives_instead_of_hard_delete(self, tmp_path):
        provider = make_provider({"op": "DELETE", "key": "user_dog", "value": ""})
        storage = make_storage(tmp_path, {
            "user_dog": "user has a dog called Rex",
            "dog_update": "user dog Rex was rehomed, no dog anymore",
        })

        report = consolidate_store(storage, provider)

        assert "user_dog" not in storage.list_all()
        assert "user has a dog called Rex" in read_archive(storage)
        assert report.archived >= 1

    def test_noop_leaves_store_unchanged(self, tmp_path):
        provider = make_provider({"op": "NOOP", "key": "user_city", "value": ""})
        storage = make_storage(tmp_path, {
            "user_city": "user lives in Beijing",
            "city_of_user": "user is in Beijing",
        })
        before = storage.list_all()

        consolidate_store(storage, provider)

        assert storage.list_all() == before
        assert read_archive(storage) == ""

    def test_unrelated_entries_skip_llm(self, tmp_path):
        provider = MagicMock()
        storage = make_storage(tmp_path, {"alpha_zzz": "qwerty asdf"})

        report = consolidate_store(storage, provider)

        provider.chat.assert_not_called()
        assert report.llm_calls == 0
        assert storage.list_all() == {"alpha_zzz": "qwerty asdf"}

    def test_llm_failure_is_logged_noop(self, tmp_path):
        provider = MagicMock()
        provider.chat.side_effect = ConnectionError("boom")
        storage = make_storage(tmp_path, {
            "user_city": "user lives in Beijing",
            "user_location": "user moved to Shanghai city",
        })
        before = storage.list_all()

        report = consolidate_store(storage, provider)

        assert storage.list_all() == before
        assert report.errors >= 1

    def test_bad_json_is_logged_noop(self, tmp_path):
        provider = make_provider("definitely not json")
        storage = make_storage(tmp_path, {
            "user_city": "user lives in Beijing",
            "user_location": "user moved to Shanghai city",
        })
        before = storage.list_all()

        # decide() raises on bad JSON → decide's caller in write-time falls
        # back to ADD; overnight treats ADD/failure as "leave alone".
        report = consolidate_store(storage, provider)

        assert storage.list_all() == before
        assert report.errors + report.unchanged >= 1

    def test_llm_budget_respected(self, tmp_path):
        provider = make_provider({"op": "NOOP", "key": "x", "value": ""})
        storage = make_storage(
            tmp_path,
            {f"user fact {i}": f"user fact number {i}" for i in range(6)},
        )

        report = consolidate_store(storage, provider, max_llm_calls=2)

        assert report.llm_calls <= 2
        assert provider.chat.call_count <= 2


# ── consolidate_store: protected keys ────────────────────────────────────────

class TestProtectedKeys:
    def test_protected_keys_never_scanned_or_shown_to_llm(self, tmp_path):
        provider = MagicMock()
        storage = make_storage(tmp_path, {
            "bot_name": "Luna",
            "user_name": "Chen",
            "user_profile": "user name is Chen",
        })

        consolidate_store(storage, provider)

        # All entries are protected or only similar to protected ones —
        # the LLM must never be consulted about them.
        provider.chat.assert_not_called()
        assert set(storage.list_all()) == {"bot_name", "user_name", "user_profile"}

    def test_llm_cannot_update_protected_key(self, tmp_path):
        """Even if the LLM names a protected key, decide() downgrades the op
        because that key was never in the similar set shown to it."""
        provider = make_provider(
            {"op": "UPDATE", "key": "user_name", "value": "hijacked"}
        )
        storage = make_storage(tmp_path, {
            "user_name": "Chen",
            "user_city": "user Chen lives in Beijing",
            "user_location": "user Chen moved to Shanghai",
        })

        consolidate_store(storage, provider)

        assert storage.list_all()["user_name"] == "Chen"

    def test_protected_keys_never_age_archived(self, tmp_path):
        provider = MagicMock()
        storage = make_storage(tmp_path, {"bot_name": "Luna"})
        storage.data["bot_name"]["updated"] = "2020-01-01 00:00:00"
        storage._save_memory_md()

        report = consolidate_store(storage, provider, archive_days=30)

        assert storage.list_all() == {"bot_name": "Luna"}
        assert report.archived == 0


# ── consolidate_store: age-based soft decay ──────────────────────────────────

class TestSoftDecay:
    def test_stale_entry_archived(self, tmp_path):
        provider = MagicMock()
        storage = make_storage(tmp_path, {"old_pref": "used to like pineapple pizza"})
        storage.data["old_pref"]["updated"] = "2020-01-01 00:00:00"
        storage._save_memory_md()

        report = consolidate_store(storage, provider, archive_days=90)

        assert "old_pref" not in storage.list_all()
        assert "pineapple pizza" in read_archive(storage)
        assert report.archived == 1

    def test_fresh_entry_kept(self, tmp_path):
        provider = MagicMock()
        storage = make_storage(tmp_path, {"new_pref": "likes matcha"})

        report = consolidate_store(storage, provider, archive_days=90)

        assert storage.list_all() == {"new_pref": "likes matcha"}
        assert report.archived == 0

    def test_decay_disabled_by_default(self, tmp_path):
        provider = MagicMock()
        storage = make_storage(tmp_path, {"old_pref": "ancient fact"})
        storage.data["old_pref"]["updated"] = "2020-01-01 00:00:00"
        storage._save_memory_md()

        report = consolidate_store(storage, provider)  # archive_days defaults to 0

        assert "old_pref" in storage.list_all()
        assert report.archived == 0


# ── run_overnight_consolidation ──────────────────────────────────────────────

class TestNightlyRun:
    def _make_home(self, tmp_path, entries):
        home = tmp_path / "home"
        storage = MemoryStorage(str(home / "context" / "memory"))
        for k, v in entries.items():
            storage.set(k, v)
        return home

    def test_writes_nightly_report(self, tmp_path):
        provider = make_provider({"op": "NOOP", "key": "x", "value": ""})
        home = self._make_home(tmp_path, {"user_city": "Beijing"})

        reports = run_overnight_consolidation(provider, home=str(home))

        assert len(reports) == 1
        report_path = home / "context" / "logs" / REPORT_FILE
        assert report_path.is_file()
        assert "Overnight Memory Consolidation" in report_path.read_text(encoding="utf-8")

    def test_no_memory_store_is_noop(self, tmp_path):
        provider = MagicMock()
        reports = run_overnight_consolidation(provider, home=str(tmp_path / "empty"))
        assert reports == []
        provider.chat.assert_not_called()

    def test_includes_per_group_stores(self, tmp_path):
        provider = make_provider({"op": "NOOP", "key": "x", "value": ""})
        home = self._make_home(tmp_path, {"user_city": "Beijing"})
        group_storage = MemoryStorage(
            str(home / "context" / "groups" / "telegram_1" / "memory")
        )
        group_storage.set("group_fact", "hello")

        reports = run_overnight_consolidation(provider, home=str(home))

        assert len(reports) == 2

    def test_uses_live_agent_storage(self, tmp_path):
        """When a live agent holds the same memory dir, its in-memory storage
        object is consolidated directly (no stale-cache resurrection)."""
        provider = make_provider({"op": "DELETE", "key": "user_dog", "value": ""})
        home = self._make_home(tmp_path, {
            "user_dog": "user has a dog called Rex",
            "dog_update": "user dog Rex was rehomed, no dog anymore",
        })
        live_storage = MemoryStorage(str(home / "context" / "memory"))

        sm = MagicMock()
        sm.list_sessions.return_value = ["telegram:1"]
        agent = MagicMock()
        agent.memory.storage = live_storage
        sm.get.return_value = agent

        run_overnight_consolidation(provider, session_manager=sm, home=str(home))

        # The live object itself was mutated, not just the file on disk.
        assert "user_dog" not in live_storage.list_all()


# ── Scheduler registration ───────────────────────────────────────────────────

class TestRegistration:
    def test_disabled_by_default(self):
        from herandhim.scheduler.overnight import register_overnight_consolidation
        scheduler = MagicMock()
        assert register_overnight_consolidation(scheduler, MagicMock()) is False
        scheduler.add_job.assert_not_called()

    def test_enabled_via_env(self, monkeypatch):
        from herandhim.scheduler.overnight import JOB_ID, register_overnight_consolidation
        monkeypatch.setenv("HERANDHIM_MEMORY_OVERNIGHT_CONSOLIDATION", "true")
        scheduler = MagicMock()

        assert register_overnight_consolidation(scheduler, MagicMock()) is True

        scheduler.add_job.assert_called_once()
        assert scheduler.add_job.call_args.kwargs["id"] == JOB_ID

    def test_custom_hour_via_env(self, monkeypatch):
        from herandhim.scheduler.overnight import register_overnight_consolidation
        monkeypatch.setenv("HERANDHIM_MEMORY_OVERNIGHT_CONSOLIDATION", "true")
        monkeypatch.setenv("HERANDHIM_MEMORY_OVERNIGHT_HOUR", "4")
        scheduler = MagicMock()

        register_overnight_consolidation(scheduler, MagicMock())

        trigger = scheduler.add_job.call_args.kwargs["trigger"]
        assert "hour='4'" in str(trigger)

    def test_no_provider_not_registered(self, monkeypatch):
        from herandhim.scheduler.overnight import register_overnight_consolidation
        monkeypatch.setenv("HERANDHIM_MEMORY_OVERNIGHT_CONSOLIDATION", "true")
        scheduler = MagicMock()
        assert register_overnight_consolidation(scheduler, None) is False
        scheduler.add_job.assert_not_called()
