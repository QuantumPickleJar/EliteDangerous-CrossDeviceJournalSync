"""Consumer directory layouts, with no proprietary consumer dependencies."""

from __future__ import annotations

from pathlib import Path

from elite_journal_cloud.journal.snapshot import JournalError

CONSUMERS = ("generic", "eddiscovery", "edexo")


def relative_path(consumer: str, commander: str, session: str, content: str, name: str) -> Path:
    """Consumer adapters expose flat per-commander folders with original basenames.

    Generic export isolates branches. Consumers must be pointed at a single commander
    folder; duplicate basenames in that layout are refused by the exporter.
    """
    if consumer not in CONSUMERS:
        raise JournalError("unsupported consumer adapter")
    if consumer == "generic":
        return Path(commander) / session / content / name
    return Path(commander) / name
