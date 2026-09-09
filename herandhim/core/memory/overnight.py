"""
Overnight (quiet-hours) memory consolidation.

Problem
-------
Write-time consolidation (see ``consolidation.py``) reconciles each single
``remember()`` against the store, but a long-lived Markdown memory still
accumulates noise over weeks: near-duplicate keys that slipped past the
write-time pass, stale preferences that were never contradicted outright,
and entries that quietly lost relevance.

Approach
--------
A nightly batch pass over each Markdown memory store that reuses the exact
same helpers as write-time consolidation (``find_similar`` + ``decide`` —
no second LLM protocol):

1. **Soft decay** (optional, off by default): entries whose last update is
   older than ``memory.overnightArchiveDays`` are moved to ``ARCHIVE.md``
   in the same memory directory.  Nothing is ever hard-deleted.
2. **Merge pass**: each recently-updated entry is treated as the "incoming
   fact" and compared against the rest of the store.  When similar entries
   exist, one small LLM call decides UPDATE (merge into one key), DELETE
   (an entry was invalidated — it gets archived, not deleted), or leave
   alone (ADD/NOOP).

Safety
------
- ``PROTECTED_KEYS`` are never scanned, never shown to the LLM as merge
  targets, and never archived.
- Destructive outcomes archive to ``ARCHIVE.md`` first; if the archive
  write fails, the entry stays in MEMORY.md.
- Every step is wrapped so a failure is a logged no-op — MEMORY.md is only
  ever rewritten through the same ``MemoryStorage`` paths used everywhere
  else.
- The LLM budget is capped per store per night (``DEFAULT_MAX_LLM_CALLS``).

Markdown files remain the source of truth throughout — no graph store, no
extra database.

Enabled explicitly (opt-in) with ``memory.overnightConsolidation: true`` in
herandhim.json or ``HERANDHIM_MEMORY_OVERNIGHT_CONSOLIDATION=true``.
"""

from __future__ import annotations

import glob
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from .consolidation import PROTECTED_KEYS, decide, find_similar
from .storage import MemoryStorage

if TYPE_CHECKING:
    from ..llm.base import LLMProvider

logger = logging.getLogger(__name__)

ARCHIVE_FILE = "ARCHIVE.md"
REPORT_FILE = "overnight_consolidation.md"

# Only entries touched within this window are merge candidates — the rest of
# the store was already reconciled on previous nights.
DEFAULT_SCAN_DAYS = 7
# Per-store nightly cap on LLM decisions, so one big store can't burn the
# operator's API key overnight.
DEFAULT_MAX_LLM_CALLS = 20


@dataclass
class StoreReport:
    """Outcome of one nightly pass over one memory directory."""

    memory_dir: str
    scanned: int = 0
    merged: int = 0
    archived: int = 0
    unchanged: int = 0
    errors: int = 0
    llm_calls: int = 0
    actions: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"scanned={self.scanned} merged={self.merged} "
            f"archived={self.archived} unchanged={self.unchanged} "
            f"errors={self.errors} ({self.llm_calls} LLM calls)"
        )


def _now_naive() -> datetime:
    """Current bot-local time as a naive datetime, matching the naive
    ``> Updated:`` timestamps that MemoryStorage writes."""
    from .. import timectx
    return timectx.now_in_bot_tz().replace(tzinfo=None)


def _parse_updated(ts: str) -> datetime | None:
    try:
        return datetime.strptime(ts.strip(), "%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return None


def archive_entry(storage: MemoryStorage, key: str, reason: str) -> bool:
    """Move one entry from MEMORY.md to ARCHIVE.md (soft delete).

    Appends the full entry to ARCHIVE.md first and only deletes from
    MEMORY.md once the archive write succeeded — a failed archive never
    loses the memory.  Protected keys are refused outright.
    """
    if key in PROTECTED_KEYS:
        return False
    entry = storage.data.get(key)
    if entry is None:
        return False

    path = os.path.join(storage.memory_dir, ARCHIVE_FILE)
    stamp = _now_naive().strftime("%Y-%m-%d %H:%M:%S")
    block = (
        f"## {key}\n"
        f"> Archived: {stamp} — {reason}\n"
        f"> Updated: {entry.get('updated', '')}\n\n"
        f"{entry.get('value', '')}\n\n"
    )
    try:
        is_new = not os.path.exists(path)
        with open(path, "a", encoding="utf-8") as f:
            if is_new:
                f.write("# Archived Memories\n\n")
            f.write(block)
    except OSError as exc:
        logger.warning("[Overnight] Archive write failed for [%s] — keeping entry: %s", key, exc)
        return False

    storage.delete(key)
    return True


def _apply_batch_op(storage: MemoryStorage, key: str, op, report: StoreReport) -> None:
    """Apply one write-time-style MemoryOp in the batch context.

    Unlike write-time, the "incoming fact" is an entry that already exists
    on disk, so ADD (which is also decide()'s safe fallback) means "distinct
    fact — leave it alone".
    """
    if op.op in ("NOOP", "ADD"):
        report.unchanged += 1
        return
    if op.op == "UPDATE":
        storage.set(op.key, op.value)
        report.merged += 1
        if op.key != key:
            if archive_entry(storage, key, f"merged into [{op.key}]"):
                report.archived += 1
            report.actions.append(f"merged [{key}] → [{op.key}]")
        else:
            report.actions.append(f"rewrote [{key}]")
        return
    if op.op == "DELETE":
        if archive_entry(storage, op.key, f"invalidated (contradicted by [{key}])"):
            report.archived += 1
            report.actions.append(f"archived [{op.key}] — invalidated by [{key}]")


def consolidate_store(
    storage: MemoryStorage,
    provider: "LLMProvider",
    *,
    scan_days: int = DEFAULT_SCAN_DAYS,
    archive_days: int = 0,
    max_llm_calls: int = DEFAULT_MAX_LLM_CALLS,
) -> StoreReport:
    """Run the nightly pass over one memory store. Never raises."""
    report = StoreReport(memory_dir=storage.memory_dir)
    now = _now_naive()

    # ── 1. Soft decay: archive entries that haven't been touched in ages ──
    if archive_days > 0:
        for key in list(storage.data.keys()):
            if key in PROTECTED_KEYS:
                continue
            updated = _parse_updated(storage.data[key].get("updated", ""))
            if updated is None:
                continue  # unknown age — keep
            age = (now - updated).days
            if age >= archive_days:
                try:
                    if archive_entry(storage, key, f"stale ({age} days without update)"):
                        report.archived += 1
                        report.actions.append(f"archived [{key}] — stale for {age} days")
                except Exception as exc:  # noqa: BLE001
                    report.errors += 1
                    logger.warning("[Overnight] Decay of [%s] failed (non-fatal): %s", key, exc)

    # ── 2. Merge pass over recently-updated entries ────────────────────────
    def _is_recent(entry: dict) -> bool:
        updated = _parse_updated(entry.get("updated", ""))
        # Entries without a parseable timestamp (e.g. hand-edited files) are
        # treated as recent so they still get reconciled.
        return updated is None or (now - updated).days <= scan_days

    candidates = [
        k for k, e in storage.data.items()
        if k not in PROTECTED_KEYS and _is_recent(e)
    ]
    report.scanned = len(candidates)

    for key in candidates:
        entry = storage.data.get(key)
        if entry is None:
            continue  # already merged/archived earlier tonight
        value = entry.get("value", "")
        # Protected keys are excluded from the comparison corpus so the LLM
        # can never name them as an UPDATE/DELETE target.
        others = {
            k: e.get("value", "")
            for k, e in storage.data.items()
            if k != key and k not in PROTECTED_KEYS
        }
        if not others:
            break

        try:
            similar = find_similar(key, value, others)
        except Exception as exc:  # noqa: BLE001
            report.errors += 1
            logger.warning("[Overnight] Similarity search failed for [%s]: %s", key, exc)
            continue
        if not similar:
            continue

        if report.llm_calls >= max_llm_calls:
            report.actions.append(
                f"LLM budget reached ({max_llm_calls}) — remaining entries left untouched"
            )
            break
        report.llm_calls += 1

        try:
            op = decide(key, value, similar, provider)
        except Exception as exc:  # noqa: BLE001
            report.errors += 1
            logger.warning("[Overnight] LLM decision failed for [%s] (non-fatal): %s", key, exc)
            continue

        try:
            _apply_batch_op(storage, key, op, report)
        except Exception as exc:  # noqa: BLE001
            report.errors += 1
            logger.warning("[Overnight] Applying %s to [%s] failed (non-fatal): %s", op.op, key, exc)

    return report


def _memory_dirs(home: str) -> list[str]:
    """All memory directories with a MEMORY.md: per-group stores + global."""
    dirs = glob.glob(os.path.join(home, "context", "groups", "*", "memory"))
    dirs.append(os.path.join(home, "context", "memory"))
    return sorted(
        os.path.normpath(d) for d in dirs
        if os.path.isfile(os.path.join(d, "MEMORY.md"))
    )


def _write_report(home: str, reports: list[StoreReport]) -> None:
    """Overwrite context/logs/overnight_consolidation.md with the latest run."""
    logs_dir = os.path.join(home, "context", "logs")
    stamp = _now_naive().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"# Overnight Memory Consolidation — {stamp}", ""]
    for r in reports:
        rel = os.path.relpath(r.memory_dir, home)
        lines.append(f"## {rel}")
        lines.append(f"- {r.summary()}")
        for action in r.actions:
            lines.append(f"- {action}")
        lines.append("")
    try:
        os.makedirs(logs_dir, exist_ok=True)
        with open(os.path.join(logs_dir, REPORT_FILE), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except OSError as exc:
        logger.warning("[Overnight] Failed to write nightly report (non-fatal): %s", exc)


def run_overnight_consolidation(
    provider: "LLMProvider",
    session_manager=None,
    home: str | None = None,
) -> list[StoreReport]:
    """Run the nightly pass over every memory store. Never raises.

    When *session_manager* is given, live agents' in-memory ``MemoryStorage``
    objects are consolidated directly (instead of a fresh on-disk load), so
    an agent's next write can't resurrect entries the night pass archived.
    """
    from ... import config as _cfg

    if home is None:
        home = str(_cfg.HERANDHIM_HOME)

    archive_days = _cfg.get_int(
        "memory", "overnightArchiveDays",
        env="HERANDHIM_MEMORY_OVERNIGHT_ARCHIVE_DAYS", default=0,
    )

    # Prefer the storage objects live agents are already holding.
    live: dict[str, MemoryStorage] = {}
    if session_manager is not None:
        for sid in session_manager.list_sessions():
            agent = session_manager.get(sid)
            storage = getattr(getattr(agent, "memory", None), "storage", None)
            if isinstance(storage, MemoryStorage):
                live.setdefault(os.path.normpath(storage.memory_dir), storage)

    reports: list[StoreReport] = []
    for d in _memory_dirs(home):
        try:
            storage = live.get(d) or MemoryStorage(d)
            report = consolidate_store(storage, provider, archive_days=archive_days)
            reports.append(report)
            logger.info("[Overnight] %s — %s", d, report.summary())
        except Exception as exc:  # noqa: BLE001
            logger.exception("[Overnight] Pass over %s failed (non-fatal): %s", d, exc)

    if not reports:
        logger.info("[Overnight] No memory stores found — nothing to consolidate.")
        return []

    _write_report(home, reports)
    logger.info(
        "[Overnight] Nightly consolidation done: %d store(s), %d merged, %d archived, %d errors.",
        len(reports),
        sum(r.merged for r in reports),
        sum(r.archived for r in reports),
        sum(r.errors for r in reports),
    )
    return reports
