"""Restart-safe one-shot synchronization; no consumer-import claims."""

from __future__ import annotations

import json
import time
from typing import Any

from elite_journal_cloud.journal.snapshot import JournalError, canonical, digest
from elite_journal_cloud.storage.store import DEVICE, HEX, Store
from elite_journal_cloud.sync.webdav import TransferError, WebDAV


class SyncEngine:
    def __init__(self, store: Store, remote: WebDAV):
        self.store = store
        self.remote = remote

    @staticmethod
    def manifest_path(manifest: dict[str, Any]) -> str:
        return f"v1/devices/{manifest['device']}/manifests/{digest(canonical(manifest))}.json"

    def enqueue_uploads(self) -> None:
        for manifest in self.store.manifests():
            identity = digest(canonical(manifest))
            self.store.enqueue(
                self.remote.endpoint, "upload", self.manifest_path(manifest), identity
            )

    def discover_downloads(self) -> None:
        self.remote.mkdir("v1")
        self.remote.mkdir("v1/devices")
        for device in self.remote.listdir("v1/devices"):
            if not DEVICE.fullmatch(device):
                raise TransferError("invalid_device_listing", True)
            directory = f"v1/devices/{device}/manifests"
            try:
                names = self.remote.listdir(directory)
            except TransferError as exc:
                if exc.code == "http_404":  # Device creation interrupted before publication.
                    continue
                raise
            for name in names:
                if not name.endswith(".json") or not HEX.fullmatch(name[:-5]):
                    raise TransferError("invalid_manifest_listing", True)
                self.store.enqueue(self.remote.endpoint, "download", f"{directory}/{name}")

    def upload(self, manifest: dict[str, Any]) -> None:
        raw = self.store.read(manifest["raw_hash"])
        self.store.validate_manifest(manifest, raw)
        base = f"v1/devices/{manifest['device']}"
        for path in ("v1", "v1/devices", base, base + "/objects", base + "/manifests"):
            self.remote.mkdir(path)
        self.remote.immutable_put(f"{base}/objects/{manifest['raw_hash']}", raw)
        # Manifest is the publication marker; object verification must precede it.
        self.remote.immutable_put(self.manifest_path(manifest), canonical(manifest))

    def download(self, path: str) -> None:
        encoded = self.remote.request("GET", path, limit=65536)
        if digest(encoded) != path.rsplit("/", 1)[-1][:-5]:
            raise TransferError("manifest_integrity_failure", True)
        try:
            manifest = json.loads(encoded)
            if not isinstance(manifest, dict) or canonical(manifest) != encoded:
                raise ValueError
            if manifest.get("device") != path.split("/")[2]:
                raise ValueError
            sha = manifest.get("raw_hash")
            if not isinstance(sha, str) or not HEX.fullmatch(sha):
                raise ValueError
            raw = self.remote.request("GET", f"v1/devices/{manifest['device']}/objects/{sha}")
            self.store.import_snapshot(manifest, raw)
        except (ValueError, KeyError, TypeError, RecursionError):
            raise TransferError("invalid_remote_snapshot", True) from None

    def run(self, *, now: float | None = None, retry_failed: bool = False) -> dict[str, object]:
        now = time.time() if now is None else now
        self.enqueue_uploads()
        if retry_failed:
            with self.store.db:
                self.store.db.execute(
                    "UPDATE transfers SET state='pending', attempts=0,next_attempt=0,error=NULL "
                    "WHERE endpoint=? AND state='failed'",
                    (self.remote.endpoint,),
                )
        discovery_error = None
        try:
            self.discover_downloads()
        except TransferError as exc:
            discovery_error = exc.code
        jobs = self.store.db.execute(
            "SELECT * FROM transfers WHERE endpoint=? AND state IN ('pending','retry') "
            "AND next_attempt<=? ORDER BY id",
            (self.remote.endpoint, now),
        ).fetchall()
        manifests = {digest(canonical(m)): m for m in self.store.manifests()}
        for job in jobs:
            attempts = job["attempts"] + 1
            with self.store.db:
                self.store.db.execute(
                    "UPDATE transfers SET state='in_progress', attempts=? WHERE id=?",
                    (attempts, job["id"]),
                )
            try:
                if job["direction"] == "upload":
                    self.upload(manifests[job["snapshot"]])
                    state = "transport_verified"
                else:
                    self.download(job["path"])
                    state = "ingested"
                with self.store.db:
                    self.store.db.execute(
                        "UPDATE transfers SET state=?, error=NULL WHERE id=?", (state, job["id"])
                    )
            except (TransferError, OSError, JournalError) as exc:
                code = exc.code if isinstance(exc, TransferError) else "local_integrity_or_io_error"
                permanent = not isinstance(exc, TransferError) or exc.permanent
                state = "failed" if permanent or attempts >= 8 else "retry"
                with self.store.db:
                    self.store.db.execute(
                        "UPDATE transfers SET state=?,error=?,next_attempt=? WHERE id=?",
                        (state, code, now + min(3600, 2**attempts), job["id"]),
                    )
        current = dict(
            self.store.db.execute(
                "SELECT state,count(*) FROM transfers WHERE endpoint=? GROUP BY state",
                (self.remote.endpoint,),
            )
        )
        return {
            **self.store.status(),
            "discovery_error": discovery_error,
            "current_endpoint_transfers": current,
        }
