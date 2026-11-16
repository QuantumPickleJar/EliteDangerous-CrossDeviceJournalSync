from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

import httpx
import pytest

from elite_journal_cloud.journal.snapshot import canonical, digest
from elite_journal_cloud.storage.store import Store
from elite_journal_cloud.sync.engine import SyncEngine
from elite_journal_cloud.sync.webdav import TransferError, WebDAV

BASE = "https://cloud.example.invalid/remote.php/dav/files/synthetic/JournalCloud/"


class MockDAV:
    """Synthetic in-memory WebDAV service; no network or real credentials."""

    def __init__(self) -> None:
        self.dirs = {""}
        self.files: dict[str, bytes] = {}
        self.requests: list[tuple[str, str]] = []
        self.offline = False
        self.fail_manifest_once = False
        self.corrupt_get = False

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.offline:
            raise httpx.ConnectError("synthetic secret must not escape", request=request)
        path = str(request.url).removeprefix(BASE).rstrip("/")
        self.requests.append((request.method, path))
        parent = path.rpartition("/")[0]
        if request.method == "MKCOL":
            if path in self.dirs:
                return httpx.Response(405)
            if parent not in self.dirs:
                return httpx.Response(409)
            self.dirs.add(path)
            return httpx.Response(201)
        if request.method == "PUT":
            if self.fail_manifest_once and "/manifests/" in path:
                self.fail_manifest_once = False
                return httpx.Response(503)
            if parent not in self.dirs:
                return httpx.Response(409)
            assert request.headers["If-None-Match"] == "*"
            if path in self.files:
                return httpx.Response(412)
            self.files[path] = request.content
            return httpx.Response(201)
        if request.method == "GET":
            if path not in self.files:
                return httpx.Response(404)
            return httpx.Response(200, content=b"corrupt" if self.corrupt_get else self.files[path])
        assert request.method == "PROPFIND"
        assert request.headers["Depth"] == "1"
        if path not in self.dirs:
            return httpx.Response(404)
        children = [p for p in self.dirs | self.files.keys() if p.rpartition("/")[0] == path]
        hrefs = [
            "<d:response><d:href>" + escape(BASE + quote(p, safe="/")) + "</d:href></d:response>"
            for p in [path, *sorted(children)]
        ]
        return httpx.Response(
            207,
            content=(
                '<d:multistatus xmlns:d="DAV:">' + "".join(hrefs) + "</d:multistatus>"
            ).encode(),
        )

    def adapter(self) -> WebDAV:
        return WebDAV(
            BASE,
            "synthetic-user",
            "synthetic-app-password",
            transport=httpx.MockTransport(self.handle),
        )


def test_two_device_round_trip(journal: Path, tmp_path: Path) -> None:
    dav = MockDAV()
    remote = dav.adapter()
    with Store(tmp_path / "deck") as store:
        store.ingest(journal, "synthetic-deck")
        result = SyncEngine(store, remote).run(now=0)
        assert result["transfers"] == {"transport_verified": 1}
        assert result["consumer_import"] == "unknown"
        manifest = store.manifests()[0]
    with Store(tmp_path / "tower") as store:
        result = SyncEngine(store, remote).run(now=0)
        assert result["transfers"] == {"ingested": 1}
        assert store.manifests() == [manifest]
        assert store.read(manifest["raw_hash"]) == journal.read_bytes()
        assert store.verify()["ok"]
    assert all(path.startswith("v1/") for path in dav.files)
    assert all("synthetic-deck" in path for path in dav.files)
    remote.close()


def test_offline_backoff_restart_and_publication_order(journal: Path, tmp_path: Path) -> None:
    dav = MockDAV()
    remote = dav.adapter()
    dav.offline = True
    with Store(tmp_path) as store:
        store.ingest(journal, "synthetic-deck")
        result = SyncEngine(store, remote).run(now=10)
        assert result["transfers"] == {"retry": 1}
        row = store.db.execute("SELECT * FROM transfers").fetchone()
        assert row["next_attempt"] == 12 and row["attempts"] == 1
        assert row["error"] == "network_error"
    dav.offline = False
    dav.fail_manifest_once = True
    with Store(tmp_path) as store:
        engine = SyncEngine(store, remote)
        engine.run(now=11)
        assert not dav.files  # Backoff survives process restart.
        engine.run(now=12)
        assert len(dav.files) == 1 and "/objects/" in next(iter(dav.files))
        assert store.status()["transfers"] == {"retry": 1}
        engine.run(now=16)
        assert store.status()["transfers"] == {"transport_verified": 1}
        assert len(dav.files) == 2
    gets = [p for method, p in dav.requests if method == "GET"]
    assert "/objects/" in gets[0]
    assert "/manifests/" in gets[-1]
    remote.close()


def test_recover_interrupted_in_progress(journal: Path, tmp_path: Path) -> None:
    dav = MockDAV()
    remote = dav.adapter()
    with Store(tmp_path) as store:
        store.ingest(journal, "synthetic-deck")
        SyncEngine(store, remote).enqueue_uploads()
        with store.db:
            store.db.execute("UPDATE transfers SET state='in_progress',attempts=1")
    with Store(tmp_path) as store:
        assert store.status()["transfers"] == {"retry": 1}
        result = SyncEngine(store, remote).run(now=0)
        assert result["transfers"] == {"transport_verified": 1}
    remote.close()


def test_download_corruption_never_ingested(journal: Path, tmp_path: Path) -> None:
    dav = MockDAV()
    remote = dav.adapter()
    with Store(tmp_path / "a") as store:
        store.ingest(journal, "synthetic-deck")
        SyncEngine(store, remote).run(now=0)
    object_path = next(p for p in dav.files if "/objects/" in p)
    dav.files[object_path] = b"corrupt"
    with Store(tmp_path / "b") as store:
        result = SyncEngine(store, remote).run(now=0)
        assert result["transfers"] == {"failed": 1}
        assert not store.manifests()
        assert result["failures"][0]["error"] == "invalid_remote_snapshot"
    remote.close()


def test_put_corruption_blocks_manifest(journal: Path, tmp_path: Path) -> None:
    dav = MockDAV()
    dav.corrupt_get = True
    remote = dav.adapter()
    with Store(tmp_path) as store:
        store.ingest(journal, "synthetic-deck")
        result = SyncEngine(store, remote).run(now=0)
        assert result["transfers"] == {"failed": 1}
        assert all("/manifests/" not in p for p in dav.files)
        dav.corrupt_get = False
        result = SyncEngine(store, remote).run(now=1, retry_failed=True)
        assert result["transfers"] == {"transport_verified": 1}
    remote.close()


def test_exhaustion_and_target_isolation(journal: Path, tmp_path: Path) -> None:
    dav = MockDAV()
    dav.offline = True
    remote = dav.adapter()
    with Store(tmp_path) as store:
        store.ingest(journal, "synthetic-deck")
        engine = SyncEngine(store, remote)
        for attempt in range(8):
            result = engine.run(now=attempt * 10000)
        assert result["transfers"] == {"failed": 1}
        assert result["failures"][0]["attempts"] == 8
        other = WebDAV(
            BASE + "other/", "synthetic", "synthetic", transport=httpx.MockTransport(dav.handle)
        )
        assert other.endpoint != remote.endpoint
        SyncEngine(store, other).enqueue_uploads()
        assert store.db.execute("SELECT count(*) FROM transfers").fetchone()[0] == 2
        other.close()
    remote.close()


@pytest.mark.parametrize(
    "url",
    [
        "http://cloud.example.invalid/",
        "https://user:pass@example.invalid/",
        "https://example.invalid/?token=synthetic",
        "https://example.invalid/#secret",
    ],
)
def test_https_no_url_secrets(url: str) -> None:
    with pytest.raises(ValueError):
        WebDAV(url, "synthetic", "synthetic")


def test_no_redirect_auth_forwarding() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example.invalid/"})

    remote = WebDAV(BASE, "synthetic", "synthetic", transport=httpx.MockTransport(handler))
    with pytest.raises(TransferError, match="http_302"):
        remote.request("GET", "v1/test")
    assert len(seen) == 1
    remote.close()


@pytest.mark.parametrize(
    "href",
    [
        "https://other.example.invalid/v1/devices/evil",
        BASE + "v1/devices/%2e%2e",
        BASE + "elsewhere/evil",
    ],
)
def test_malicious_listing_rejected(href: str) -> None:
    body = (
        '<d:multistatus xmlns:d="DAV:"><d:response><d:href>'
        + href
        + "</d:href></d:response></d:multistatus>"
    ).encode()
    remote = WebDAV(
        BASE,
        "synthetic",
        "synthetic",
        transport=httpx.MockTransport(
            lambda request, content=body: httpx.Response(207, content=content)
        ),
    )
    with pytest.raises(TransferError, match="invalid_dav_listing"):
        remote.listdir("v1/devices")
    remote.close()


def test_manifest_hash_and_device_binding(journal: Path, tmp_path: Path) -> None:
    dav = MockDAV()
    remote = dav.adapter()
    with Store(tmp_path) as store:
        store.ingest(journal, "synthetic-deck")
        manifest = store.manifests()[0]
        encoded = canonical(manifest)
        path = f"v1/devices/other-device/manifests/{digest(encoded)}.json"
        dav.files[path] = encoded
        with pytest.raises(TransferError, match="invalid_remote_snapshot"):
            SyncEngine(store, remote).download(path)
        dav.files[path] = b"{}"
        with pytest.raises(TransferError, match="manifest_integrity_failure"):
            SyncEngine(store, remote).download(path)
    remote.close()


def test_synced_growing_snapshot_deduplicated_feed(journal: Path, tmp_path: Path) -> None:
    from elite_journal_cloud.feed.export import export

    dav = MockDAV()
    remote = dav.adapter()
    growing = tmp_path / journal.name
    raw = journal.read_bytes()
    growing.write_bytes(b"\n".join(raw.split(b"\n")[:4]) + b"\n" + b'{"event":')
    with Store(tmp_path / "deck") as store:
        store.ingest(growing, "synthetic-deck")
        SyncEngine(store, remote).run(now=0)
        growing.write_bytes(raw)
        store.ingest(growing, "synthetic-deck")
        SyncEngine(store, remote).run(now=10)
    with Store(tmp_path / "tower") as store:
        store.ingest(journal, "synthetic-tower")
        SyncEngine(store, remote).run(now=20)
    # A separate invocation sees previously imported jobs and terminal state after restart.
    with Store(tmp_path / "tower") as store:
        SyncEngine(store, remote).run(now=30)
        assert len(store.manifests()) == 3
        assert store.verify()["ok"]
        report = export(store, tmp_path / "feed", consumer="edexo")
        assert len(report["files"]) == 1
        assert next((tmp_path / "feed").rglob("*.log")).read_bytes() == raw
    remote.close()


def test_listing_xml_security_and_response_bound() -> None:
    for body in (
        b"<invalid/>",
        b'<!DOCTYPE x [<!ENTITY a SYSTEM "file:///synthetic">]>'
        b'<d:multistatus xmlns:d="DAV:">&a;</d:multistatus>',
    ):
        remote = WebDAV(
            BASE,
            "synthetic",
            "synthetic",
            transport=httpx.MockTransport(
                lambda request, content=body: httpx.Response(207, content=content)
            ),
        )
        with pytest.raises(TransferError, match="invalid_dav_listing"):
            remote.listdir("v1/devices")
        remote.close()
    remote = WebDAV(
        BASE,
        "synthetic",
        "synthetic",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 10)),
    )
    with pytest.raises(TransferError, match="response_too_large"):
        remote.request("GET", "v1/test", limit=9)
    with pytest.raises(TransferError, match="unsafe_remote_path"):
        remote.request("GET", "../test")
    remote.close()


def test_incomplete_device_publication_skipped(journal: Path, tmp_path: Path) -> None:
    dav = MockDAV()
    dav.dirs.update({"v1", "v1/devices", "v1/devices/incomplete"})
    remote = dav.adapter()
    with Store(tmp_path) as store:
        store.ingest(journal, "synthetic-deck")
        result = SyncEngine(store, remote).run(now=0)
        assert result["discovery_error"] is None
        assert result["transfers"] == {"transport_verified": 1}
    remote.close()
