import json
import subprocess
import sys
from pathlib import Path

import pytest
from filelock import Timeout

from elite_journal_cloud.api.server import read_resource
from elite_journal_cloud.config import Config, secure_keyring
from elite_journal_cloud.feed.export import export
from elite_journal_cloud.journal.snapshot import JournalError, canonical
from elite_journal_cloud.storage.store import Store


def command(state: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- fixed interpreter and synthetic arguments
        [sys.executable, "-m", "elite_journal_cloud", "--state-dir", str(state), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_offline_cli_end_to_end_and_idempotence(tmp_path: Path, journal: Path) -> None:
    state = tmp_path / "state"
    assert command(state, "init", "--root", str(journal.parent)).returncode == 0
    original = (state / "config.json").read_bytes()
    assert command(state, "init", "--root", str(journal.parent)).returncode == 0
    assert (state / "config.json").read_bytes() == original
    result = command(state, "scan", "--no-defaults")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"discovered": 2, "accepted": 2, "rejected": 0}
    assert command(state, "scan", "--no-defaults").returncode == 0
    status = json.loads(command(state, "status").stdout)
    assert status["snapshots"] == 2
    assert status["consumer_import"] == "unknown"
    assert json.loads(command(state, "sync").stdout)["cloud"] == "not_configured"
    assert json.loads(command(state, "verify").stdout)["ok"]
    assert command(state, "export", str(tmp_path / "feed")).returncode == 0
    assert command(state, "export", str(tmp_path / "feed")).returncode == 1
    assert len(list((tmp_path / "feed").rglob("*.log"))) == 2
    assert command(state, "--version").stdout.strip() == "0.1.0a1"


def test_api_read_only_and_no_private_identifiers(tmp_path: Path, journal: Path) -> None:
    with Store(tmp_path) as store:
        store.ingest(journal, "synthetic-device")
        before = list(store.db.iterdump())
        for route in ("/v1/health", "/v1/status", "/v1/sessions"):
            code, body = read_resource(tmp_path, route)
            assert code == 200
            encoded = json.dumps(body)
            assert "SYNTHETIC-FID" not in encoded
            assert "Synthetic Commander" not in encoded
            assert "source_name" not in encoded
        assert read_resource(tmp_path, "/v2/status")[0] == 404
        assert before == list(store.db.iterdump())


def test_no_plaintext_keyring_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    class UnsafeBackend:
        pass

    monkeypatch.setattr("keyring.get_keyring", lambda: UnsafeBackend())
    with pytest.raises(ValueError, match="supported OS credential store unavailable"):
        secure_keyring()


def test_cli_redacts_config_errors(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "config.json").write_text('{"password":"synthetic-private-value"}')
    result = command(tmp_path, "status")
    assert result.returncode == 1
    assert "synthetic-private-value" not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr


def test_cli_rejected_source_returns_failure(tmp_path: Path) -> None:
    source = tmp_path / "input/Journal.260101120000.01.log"
    source.parent.mkdir()
    source.write_bytes(b"invalid\n")
    result = command(tmp_path / "state", "scan", "--root", str(source.parent))
    assert result.returncode == 1
    assert json.loads(result.stdout)["rejected"] == 1
    assert "invalid" not in result.stdout


def test_corrupt_manifest_blocks_verify_and_feed(journal: Path, tmp_path: Path) -> None:
    with Store(tmp_path / "state") as store:
        store.ingest(journal, "synthetic-device")
        manifest = store.manifests()[0]
        manifest["complete_size"] -= 3
        with store.db:
            store.db.execute("UPDATE snapshots SET manifest=?", (canonical(manifest),))
        assert not store.verify()["ok"]
        with pytest.raises(JournalError):
            export(store, tmp_path / "feed")


def test_config_device_is_stable_and_random(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    config = Config.load(path)
    config.save(path)
    assert Config.load(path).device == config.device
    assert Config.load(tmp_path / "other.json").device != config.device


def test_writer_lock_prevents_live_worker_recovery(journal: Path, tmp_path: Path) -> None:
    with Store(tmp_path) as store:
        store.ingest(journal, "synthetic-device")
        store.enqueue("synthetic-endpoint", "upload", "v1/test")
        with store.db:
            store.db.execute("UPDATE transfers SET state='in_progress'")
        with pytest.raises(Timeout):
            with Store(tmp_path):
                pytest.fail("second writer entered archive")
        assert store.status()["transfers"] == {"in_progress": 1}


def test_http_api_guards_and_methods(tmp_path: Path, journal: Path) -> None:
    import threading

    import httpx

    from elite_journal_cloud.api.server import make_server

    with Store(tmp_path) as store:
        store.ingest(journal, "synthetic")
    with make_server(tmp_path, 0) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            with httpx.Client(trust_env=False) as client:
                response = client.get(url + "/v1/status")
                assert response.status_code == 200
                assert response.json()["snapshots"] == 1
                assert response.headers["Cache-Control"] == "no-store"
                assert (
                    client.get(
                        url + "/v1/status", headers={"Origin": "https://example.invalid"}
                    ).status_code
                    == 403
                )
                assert (
                    client.get(url + "/v1/status", headers={"Host": "example.invalid"}).status_code
                    == 403
                )
                assert client.post(url + "/v1/status").status_code == 501
                assert client.get(url + "/v9/status").status_code == 404
        finally:
            server.shutdown()
            worker.join(timeout=5)
