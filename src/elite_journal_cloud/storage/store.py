"""Immutable objects plus transactional provenance and durable transfer state."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Self

from filelock import FileLock

from elite_journal_cloud.journal.snapshot import (
    MAX_SNAPSHOT_BYTES,
    JournalError,
    Snapshot,
    canonical,
    digest,
    validate,
)

HEX = re.compile(r"[a-f0-9]{64}\Z")
DEVICE = re.compile(r"[a-zA-Z0-9_-]{1,64}\Z")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class Store:
    """One writer/worker per archive, including across processes; lock released on crash."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = FileLock(str(root / "archive.lock"), timeout=5)
        self.lock.acquire()
        try:
            self.db = sqlite3.connect(root / "state.sqlite3")
            self.db.row_factory = sqlite3.Row
            if self.db.execute("PRAGMA user_version").fetchone()[0] not in {0, 1}:
                raise JournalError("unsupported local state version")
            self.db.executescript("""
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=FULL;
                PRAGMA user_version=1;
                CREATE TABLE IF NOT EXISTS snapshots(
                    id TEXT PRIMARY KEY, manifest BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS lineage(
                    child TEXT NOT NULL, parent TEXT NOT NULL,
                    PRIMARY KEY(child,parent));
                CREATE TABLE IF NOT EXISTS transfers(
                    id INTEGER PRIMARY KEY, endpoint TEXT NOT NULL,
                    direction TEXT NOT NULL, path TEXT NOT NULL, snapshot TEXT,
                    state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL DEFAULT 0, error TEXT,
                    UNIQUE(endpoint,direction,path));
                UPDATE transfers SET state='retry', next_attempt=0, error='interrupted'
                    WHERE state='in_progress';
            """)
            self.db.commit()
        except BaseException:
            if hasattr(self, "db"):
                self.db.close()
            self.lock.release()
            raise

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.db.close()
        self.lock.release()

    def object_path(self, sha: str) -> Path:
        if not HEX.fullmatch(sha):
            raise JournalError("invalid object hash")
        return self.root / "objects" / sha[:2] / sha

    def read(self, sha: str) -> bytes:
        path = self.object_path(sha)
        if path.stat().st_size > MAX_SNAPSHOT_BYTES:
            raise JournalError("object exceeds size limit")
        data = path.read_bytes()
        if digest(data) != sha:
            raise JournalError("object integrity failure")
        return data

    def put(self, data: bytes) -> str:
        if len(data) > MAX_SNAPSHOT_BYTES:
            raise JournalError("object exceeds size limit")
        sha = digest(data)
        path = self.object_path(sha)
        if path.exists():
            self.read(sha)  # Never overwrite a corrupt immutable object silently.
        else:
            atomic_write(path, data)
        return sha

    def manifests(self) -> list[dict[str, Any]]:
        manifests = []
        for row in self.db.execute("SELECT id,manifest FROM snapshots ORDER BY id"):
            manifest = json.loads(row["manifest"])
            if digest(canonical(manifest)) != row["id"]:
                raise JournalError("manifest integrity failure")
            manifests.append(manifest)
        return manifests

    def ingest(self, path: Path, device: str) -> str:
        if not DEVICE.fullmatch(device):
            raise JournalError("invalid device ID")
        # Read exactly the size observed at open; growth is picked up on the next scan.
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if before.st_size > MAX_SNAPSHOT_BYTES:
                raise JournalError("source exceeds size limit")
            raw = stream.read(before.st_size)
            after = os.fstat(stream.fileno())
        if len(raw) != before.st_size or after.st_size < before.st_size:
            raise JournalError("source shrank during capture; rescan required")
        self.put(raw)
        snap = validate(raw)
        manifest = {
            "schema": 1,
            "device": device,
            "source_name": path.name,
            "source_mtime_ns": before.st_mtime_ns,
            "source_size": len(raw),
            "raw_hash": snap.raw_hash,
            "complete_hash": snap.complete_hash,
            "complete_size": len(snap.complete),
            "session": snap.session,
            "commanders": list(snap.commanders),
            "timestamp": snap.timestamp,
        }
        return self.import_snapshot(manifest, raw)

    @staticmethod
    def validate_manifest(manifest: dict[str, Any], raw: bytes) -> Snapshot:
        """Remote and on-disk metadata must match the validated object."""
        expected = {
            "schema",
            "device",
            "source_name",
            "source_mtime_ns",
            "source_size",
            "raw_hash",
            "complete_hash",
            "complete_size",
            "session",
            "commanders",
            "timestamp",
        }
        if (
            set(manifest) != expected
            or type(manifest["schema"]) is not int
            or manifest["schema"] != 1
        ):
            raise JournalError("unsupported manifest schema")
        if not isinstance(manifest["device"], str) or not DEVICE.fullmatch(manifest["device"]):
            raise JournalError("invalid device ID")
        name = manifest["source_name"]
        if (
            not isinstance(name, str)
            or len(name) > 255
            or not re.fullmatch(r"Journal\.[A-Za-z0-9_.-]+\.log", name)
        ):
            raise JournalError("invalid source filename")
        if type(manifest["source_mtime_ns"]) is not int or manifest["source_mtime_ns"] < 0:
            raise JournalError("invalid source metadata")
        snap = validate(raw)
        actual = {
            "source_size": len(raw),
            "raw_hash": snap.raw_hash,
            "complete_hash": snap.complete_hash,
            "complete_size": len(snap.complete),
            "session": snap.session,
            "commanders": list(snap.commanders),
            "timestamp": snap.timestamp,
        }
        if any(manifest[k] != v for k, v in actual.items()) or any(
            type(manifest[k]) is not int for k in ("source_size", "complete_size")
        ):
            raise JournalError("manifest does not match object")
        if len(canonical(manifest)) > 65536:
            raise JournalError("manifest exceeds size limit")
        return snap

    def import_snapshot(self, manifest: dict[str, Any], raw: bytes) -> str:
        snap = self.validate_manifest(manifest, raw)
        self.put(raw)
        encoded = canonical(manifest)
        identity = digest(encoded)
        parents: list[tuple[str, str]] = []
        # Lineage is derived from validated bytes, never trusted from remote metadata.
        for other in self.manifests():
            if other["session"] != snap.session:
                continue
            previous = self.read(other["raw_hash"])[: other["complete_size"]]
            old_id = digest(canonical(other))
            if len(previous) < len(snap.complete) and snap.complete.startswith(previous):
                parents.append((identity, old_id))
            elif len(snap.complete) < len(previous) and previous.startswith(snap.complete):
                parents.append((old_id, identity))
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO snapshots VALUES (?,?)", (identity, encoded))
            self.db.executemany("INSERT OR IGNORE INTO lineage VALUES (?,?)", parents)
        return identity

    def verify(self) -> dict[str, object]:
        failures = []
        count = 0
        for path in sorted((self.root / "objects").glob("*/*")):
            count += 1
            try:
                self.read(path.name)
            except (OSError, JournalError):
                failures.append(path.name)
        for row in self.db.execute("SELECT id,manifest FROM snapshots ORDER BY id"):
            try:
                manifest = json.loads(row["manifest"])
                if digest(canonical(manifest)) != row["id"]:
                    raise JournalError("manifest integrity failure")
                self.validate_manifest(manifest, self.read(manifest["raw_hash"]))
            except (OSError, ValueError, KeyError, TypeError):
                failures.append(row["id"])
        return {"objects": count, "failures": sorted(set(failures)), "ok": not failures}

    def enqueue(
        self, endpoint: str, direction: str, path: str, snapshot: str | None = None
    ) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO transfers(endpoint,direction,path,snapshot) VALUES(?,?,?,?)",
                (endpoint, direction, path, snapshot),
            )

    def status(self) -> dict[str, object]:
        states = {
            row[0]: row[1]
            for row in self.db.execute("SELECT state, count(*) FROM transfers GROUP BY state")
        }
        errors = [
            dict(row)
            for row in self.db.execute(
                "SELECT id,direction,state,attempts,error FROM transfers "
                "WHERE state IN ('retry','failed') ORDER BY id"
            )
        ]
        return {
            "api_version": "v1",
            "snapshots": len(self.manifests()),
            "transfers": states,
            "failures": errors,
            "archive_ingestion": "local_validated_snapshots_only",
            "consumer_import": "unknown",
            "remote_archive_ingestion": "unknown",
        }
