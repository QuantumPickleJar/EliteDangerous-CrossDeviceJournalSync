"""Deterministic complete-record feed. Conflicts require an explicit export decision."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from elite_journal_cloud.feed.adapters import relative_path
from elite_journal_cloud.journal.snapshot import JournalError, canonical, digest
from elite_journal_cloud.storage.store import Store, atomic_write


class FeedConflict(JournalError):
    pass


def plan(store: Store) -> tuple[list[dict[str, Any]], list[str]]:
    sessions: dict[str, dict[str, dict[str, Any]]] = {}
    for manifest in store.manifests():
        snap = sessions.setdefault(manifest["session"], {})
        key = manifest["complete_hash"]
        raw = store.read(manifest["raw_hash"])
        validated = store.validate_manifest(manifest, raw)
        if key not in snap:
            snap[key] = {"data": validated.complete, "manifest": manifest}
    chosen = []
    conflicts = []
    for session, variants in sorted(sessions.items()):
        maximal = [
            v
            for v in variants.values()
            if not any(
                len(other["data"]) > len(v["data"]) and other["data"].startswith(v["data"])
                for other in variants.values()
            )
        ]
        if len(maximal) > 1:
            conflicts.append(session)
        chosen.extend(maximal)
    chosen.sort(
        key=lambda v: (
            v["manifest"]["timestamp"],
            v["manifest"]["session"],
            v["manifest"]["complete_hash"],
        )
    )
    return chosen, conflicts


def export(
    store: Store, destination: Path, *, allow_conflicts: bool = False, consumer: str = "generic"
) -> dict[str, object]:
    selected, conflicts = plan(store)
    if conflicts and not allow_conflicts:
        raise FeedConflict("divergent sessions; review conflicts or use --allow-conflicts")
    # Refuse managed-feed replacement: removing old files under a watched directory can
    # cause consumer reimports. Export each generation to a fresh directory instead.
    entries = []
    outputs: dict[Path, bytes] = {}
    for item in selected:
        manifest = item["manifest"]
        # Each session stays intact, including any commander changes. Opaque directory
        # names keep commander identifiers out of filenames, but journal contents are private.
        commander = digest(canonical(manifest["commanders"]))[:16]
        session = manifest["session"]
        content = manifest["complete_hash"]
        # Preserve the original basename for consumers that parse Elite's filename format.
        relative = relative_path(consumer, commander, session, content, manifest["source_name"])
        if relative in outputs:
            raise FeedConflict("consumer basename collision; use generic export for review")
        outputs[relative] = item["data"]
        entries.append(
            {
                "path": relative.as_posix(),
                "session": session,
                "complete_hash": content,
                "events_bytes": len(item["data"]),
                "commander_count": len(manifest["commanders"]),
            }
        )
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise JournalError("export destination must be empty; use a fresh generation directory")
    for relative, data in outputs.items():
        atomic_write(destination / relative, data)
    report = {
        "schema": 1,
        "consumer": consumer,
        "files": entries,
        "conflicts": conflicts,
        "consumer_import": "unknown",
    }
    atomic_write(destination / "feed.json", canonical(report) + b"\n")
    return report
