from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

JOURNAL_PATTERN = "Journal*.log"
SHARED_HISTORY_FILE = ".journal_sync_history.jsonl"


@dataclass
class SyncResult:
    copied: int
    deduped: int
    queued: int
    replayed: int
    offline: bool


def synchronize(local_root: str | Path, nextcloud_root: str | Path, state_db_path: str | Path) -> SyncResult:
    local_root = Path(local_root)
    nextcloud_root = Path(nextcloud_root)
    state_db_path = Path(state_db_path)

    conn = sqlite3.connect(state_db_path)
    _init_db(conn)

    journals = _discover_journals(local_root)
    synced_hashes = _load_synced_hashes(conn)

    changed = []
    for file_path in journals:
        relative = str(file_path.relative_to(local_root))
        digest = _sha256(file_path)
        if synced_hashes.get(relative) != digest:
            changed.append((file_path, relative, digest))

    if not _is_nextcloud_available(nextcloud_root):
        queued = 0
        for file_path, relative, digest in changed:
            _queue_pending(conn, relative, str(file_path), digest)
            _append_local_history(conn, "queued_offline", relative, "queued while nextcloud unavailable")
            queued += 1

        conn.commit()
        conn.close()
        return SyncResult(copied=0, deduped=0, queued=queued, replayed=0, offline=True)

    copied = 0
    deduped = 0
    replayed = 0
    handled_paths: set[str] = set()

    for relative, source_path, digest in _load_pending(conn):
        source = Path(source_path)
        if not source.exists():
            fallback = local_root / relative
            if fallback.exists():
                source = fallback
            else:
                continue

        was_copied = _copy_if_needed(source, nextcloud_root / relative, digest)
        if was_copied:
            copied += 1
            event = "replayed_copy"
        else:
            deduped += 1
            event = "replayed_dedup"

        replayed += 1
        handled_paths.add(relative)
        _mark_synced(conn, relative, digest)
        _remove_pending(conn, relative)
        _append_shared_history(nextcloud_root, event, relative, digest)
        _append_local_history(conn, event, relative, "replayed pending sync")

    for file_path, relative, digest in changed:
        if relative in handled_paths:
            continue

        was_copied = _copy_if_needed(file_path, nextcloud_root / relative, digest)
        if was_copied:
            copied += 1
            event = "copied"
        else:
            deduped += 1
            event = "deduped"

        _mark_synced(conn, relative, digest)
        _remove_pending(conn, relative)
        _append_shared_history(nextcloud_root, event, relative, digest)
        _append_local_history(conn, event, relative, "online sync")

    conn.commit()
    conn.close()
    return SyncResult(copied=copied, deduped=deduped, queued=0, replayed=replayed, offline=False)


def _discover_journals(local_root: Path) -> list[Path]:
    return sorted(path for path in local_root.glob(JOURNAL_PATTERN) if path.is_file())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_nextcloud_available(nextcloud_root: Path) -> bool:
    try:
        nextcloud_root.mkdir(parents=True, exist_ok=True)
        probe = nextcloud_root / ".sync_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True


def _copy_if_needed(source: Path, destination: Path, source_digest: str) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.is_file() and _sha256(destination) == source_digest:
        return False

    shutil.copy2(source, destination)
    return True


def _append_shared_history(nextcloud_root: Path, event: str, relative_path: str, digest: str) -> None:
    history_path = nextcloud_root / SHARED_HISTORY_FILE
    entry = {
        "timestamp": _now_utc(),
        "event": event,
        "relative_path": relative_path,
        "hash": digest,
    }
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, separators=(",", ":")) + "\n")


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS synced_files (
            relative_path TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            last_synced_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_files (
            relative_path TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            queued_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS local_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at TEXT NOT NULL,
            event TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            detail TEXT NOT NULL
        )
        """
    )


def _load_synced_hashes(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT relative_path, content_hash FROM synced_files").fetchall()
    return {relative: digest for relative, digest in rows}


def _load_pending(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    return conn.execute(
        "SELECT relative_path, source_path, content_hash FROM pending_files ORDER BY queued_at ASC"
    ).fetchall()


def _queue_pending(conn: sqlite3.Connection, relative_path: str, source_path: str, content_hash: str) -> None:
    conn.execute(
        """
        INSERT INTO pending_files(relative_path, source_path, content_hash, queued_at)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(relative_path) DO UPDATE SET
            source_path = excluded.source_path,
            content_hash = excluded.content_hash,
            queued_at = excluded.queued_at
        """,
        (relative_path, source_path, content_hash, _now_utc()),
    )


def _remove_pending(conn: sqlite3.Connection, relative_path: str) -> None:
    conn.execute("DELETE FROM pending_files WHERE relative_path = ?", (relative_path,))


def _mark_synced(conn: sqlite3.Connection, relative_path: str, content_hash: str) -> None:
    conn.execute(
        """
        INSERT INTO synced_files(relative_path, content_hash, last_synced_at)
        VALUES(?, ?, ?)
        ON CONFLICT(relative_path) DO UPDATE SET
            content_hash = excluded.content_hash,
            last_synced_at = excluded.last_synced_at
        """,
        (relative_path, content_hash, _now_utc()),
    )


def _append_local_history(conn: sqlite3.Connection, event: str, relative_path: str, detail: str) -> None:
    conn.execute(
        "INSERT INTO local_history(recorded_at, event, relative_path, detail) VALUES(?, ?, ?, ?)",
        (_now_utc(), event, relative_path, detail),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Elite Dangerous journal files to a Nextcloud folder")
    parser.add_argument("local_root")
    parser.add_argument("nextcloud_root")
    parser.add_argument(
        "--state-db",
        default=".journal_sync_state.sqlite3",
        help="Path for local sqlite state database (default: .journal_sync_state.sqlite3)",
    )
    args = parser.parse_args()

    result = synchronize(args.local_root, args.nextcloud_root, args.state_db)
    print(json.dumps(result.__dict__, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
