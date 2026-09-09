"""
Quiet-hours scheduling for overnight memory consolidation.

Registers a nightly APScheduler job (default 03:30 in the scheduler's local
timezone — well inside the default proactive quiet window of 0–8) that runs
the batch pass in ``herandhim.core.memory.overnight``.

Opt-in: nothing is registered unless ``memory.overnightConsolidation`` is
``true`` in herandhim.json (or ``HERANDHIM_MEMORY_OVERNIGHT_CONSOLIDATION=true``).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .. import config
from ..core.memory.overnight import run_overnight_consolidation

if TYPE_CHECKING:
    from ..core.llm.base import LLMProvider
    from ..session_manager import SessionManager

logger = logging.getLogger(__name__)

JOB_ID = "overnight_memory_consolidation"
DEFAULT_HOUR = 3
# :30 keeps clear of the 00:01 daily planner and any on-the-hour user jobs.
RUN_MINUTE = 30


async def _overnight_job(provider: "LLMProvider", session_manager) -> None:
    # run_overnight_consolidation makes blocking LLM calls — keep them off
    # the event loop.
    await asyncio.to_thread(run_overnight_consolidation, provider, session_manager)


def register_overnight_consolidation(
    scheduler: AsyncIOScheduler,
    provider: "LLMProvider",
    session_manager: "SessionManager | None" = None,
) -> bool:
    """Register the nightly consolidation job. Returns True when registered."""
    enabled = config.get_bool(
        "memory", "overnightConsolidation",
        env="HERANDHIM_MEMORY_OVERNIGHT_CONSOLIDATION", default=False,
    )
    if not enabled:
        logger.info(
            "[Overnight] Disabled (memory.overnightConsolidation is off) — not registered."
        )
        return False
    if provider is None:
        logger.info("[Overnight] No LLM provider — not registered.")
        return False

    hour = config.get_int(
        "memory", "overnightHour",
        env="HERANDHIM_MEMORY_OVERNIGHT_HOUR", default=DEFAULT_HOUR,
    )
    hour = min(max(hour, 0), 23)

    scheduler.add_job(
        _overnight_job,
        trigger=CronTrigger(hour=hour, minute=RUN_MINUTE),
        id=JOB_ID,
        args=[provider, session_manager],
        replace_existing=True,
    )
    logger.info(
        "[Overnight] Nightly memory consolidation registered (runs at %02d:%02d local).",
        hour, RUN_MINUTE,
    )
    return True
