import json
from pathlib import Path

import pytest

from elite_journal_cloud.feed.export import FeedConflict, export, plan
from elite_journal_cloud.journal.discovery import JOURNAL_DIR, discover
from elite_journal_cloud.journal.snapshot import JournalError, digest, validate
from elite_journal_cloud.storage.store import Store


def test_partial_crlf_and_original_bytes(journal: Path, tmp_path: Path) -> None:
    raw = journal.read_bytes().replace(b"\n", b"\r\n")
    growing = tmp_path / journal.name
    growing.write_bytes(raw + b'{"timestamp": "incomplete')
    with Store(tmp_path / "state") as store:
        store.ingest(growing, "synthetic-deck")
        manifest = store.manifests()[0]
        assert store.read(manifest["raw_hash"]) == growing.read_bytes()
        assert manifest["complete_size"] == len(raw)
        report = export(store, tmp_path / "feed")
        assert len(report["files"]) == 1
        assert next((tmp_path / "feed").rglob("*.log")).read_bytes() == raw
        assert store.verify()["ok"]
    assert growing.read_bytes() == raw + b'{"timestamp": "incomplete'


@pytest.mark.parametrize(
    "suffix",
    [
        b"not-json\n",
        b"[]\n",
        b"{}\n",
        b"\xff\n",
        b'{"event":"Test","timestamp":"x"}\n',
        b'{"event":"Test","timestamp":"2026-01-01T00:00:00Z","value":NaN}\n',
    ],
)
def test_invalid_complete_record_quarantined(journal: Path, tmp_path: Path, suffix: bytes) -> None:
    path = tmp_path / journal.name
    raw = journal.read_bytes() + suffix
    path.write_bytes(raw)
    with Store(tmp_path / "state") as store:
        with pytest.raises(JournalError):
            store.ingest(path, "synthetic-deck")
        assert not store.manifests()
        assert store.read(digest(raw)) == raw


def test_partial_header_and_missing_header() -> None:
    for raw in (
        b'{"event":"Fileheader"}',
        b'{"event":"Shutdown","timestamp":"2026-01-01T00:00:00Z"}\n',
    ):
        with pytest.raises(JournalError):
            validate(raw)


def test_prefixes_devices_lineage_and_event_order(journal: Path, tmp_path: Path) -> None:
    raw = journal.read_bytes()
    source = tmp_path / journal.name
    source.write_bytes(b"\n".join(raw.split(b"\n")[:3]) + b"\n")
    with Store(tmp_path / "state") as store:
        store.ingest(source, "synthetic-deck")
        source.write_bytes(raw)
        store.ingest(source, "synthetic-deck")
        store.ingest(source, "synthetic-tower")
        store.ingest(source, "synthetic-tower")
        assert len(store.manifests()) == 3
        assert store.db.execute("SELECT count(*) FROM lineage").fetchone()[0] == 2
        assert len(list((store.root / "objects").glob("*/*"))) == 2
        selected, conflicts = plan(store)
        assert len(selected) == 1 and not conflicts
        export(store, tmp_path / "one")
        export(store, tmp_path / "two")
        assert (tmp_path / "one/feed.json").read_bytes() == (
            tmp_path / "two/feed.json"
        ).read_bytes()
        output = next((tmp_path / "one").rglob("*.log")).read_bytes()
        assert output == raw
        names = [json.loads(line)["event"] for line in output.splitlines()]
        assert names == [
            "Fileheader",
            "Commander",
            "LoadGame",
            "ScanOrganic",
            "ScanOrganic",
            "ScanOrganic",
            "SellOrganicData",
            "Died",
            "Resurrect",
            "Shutdown",
        ]
        with pytest.raises(JournalError):
            export(store, tmp_path / "one")


def test_divergent_history_never_silently_lost(journal: Path, tmp_path: Path) -> None:
    source = tmp_path / journal.name
    with Store(tmp_path / "state") as store:
        store.ingest(journal, "synthetic-deck")
        source.write_bytes(journal.read_bytes().replace(b'"Cost":0', b'"Cost":25'))
        store.ingest(source, "synthetic-tower")
        with pytest.raises(FeedConflict):
            export(store, tmp_path / "default")
        report = export(store, tmp_path / "review", allow_conflicts=True)
        assert len(report["conflicts"]) == 1
        assert len(list((tmp_path / "review").rglob("*.log"))) == 2
        assert len(store.manifests()) == 2


def test_repeat_events_and_commander_boundaries(journal: Path, tmp_path: Path) -> None:
    source = tmp_path / journal.name
    repeated = journal.read_bytes() + journal.read_bytes().splitlines(keepends=True)[3]
    source.write_bytes(repeated)
    with Store(tmp_path / "state") as store:
        store.ingest(source, "synthetic-deck")
        store.ingest(journal.parent / "Journal.260102120000.01.log", "synthetic-tower")
        export(store, tmp_path / "feed")
        outputs = [p.read_bytes() for p in (tmp_path / "feed").rglob("*.log")]
        assert repeated in outputs
        assert len(outputs) == 2
        assert len(list((tmp_path / "feed").iterdir())) == 3  # Two commanders + index.


def test_corruption_detected_no_overwrite(journal: Path, tmp_path: Path) -> None:
    with Store(tmp_path) as store:
        store.ingest(journal, "synthetic")
        sha = store.manifests()[0]["raw_hash"]
        store.object_path(sha).write_bytes(b"corrupt")
        assert not store.verify()["ok"]
        with pytest.raises(JournalError):
            store.ingest(journal, "synthetic")
        with pytest.raises(JournalError):
            export(store, tmp_path / "feed")


@pytest.mark.parametrize(
    "field,value",
    [
        ("device", "../escape"),
        ("source_name", "C:escape"),
        ("source_name", "../Journal.test.log"),
        ("complete_size", -1),
        ("raw_hash", "0" * 64),
        ("commanders", ["forged"]),
        ("schema", 2),
    ],
)
def test_untrusted_metadata_rejected(
    journal: Path, tmp_path: Path, field: str, value: object
) -> None:
    with Store(tmp_path / "first") as store:
        store.ingest(journal, "synthetic")
        manifest = store.manifests()[0]
    manifest[field] = value
    with Store(tmp_path / "second") as store:
        with pytest.raises(JournalError):
            store.import_snapshot(manifest, journal.read_bytes())
        assert not store.manifests()


def test_discover_windows_proton_custom_and_duplicates(tmp_path: Path) -> None:
    windows = tmp_path / "home" / JOURNAL_DIR / "Journal.260101120000.01.log"
    proton = (
        tmp_path
        / "external/steamapps/compatdata/359320/pfx/drive_c/users/steamuser"
        / JOURNAL_DIR
        / "Journal.260102120000.01.log"
    )
    for path in (windows, proton):
        path.parent.mkdir(parents=True)
        path.touch()
    assert discover([windows.parent], [tmp_path / "external"], home=tmp_path / "home") == sorted(
        [windows, proton], key=str
    )
    assert discover(home=tmp_path / "empty") == []


@pytest.mark.parametrize("consumer", ["eddiscovery", "edexo"])
def test_consumer_flat_commander_layout(journal: Path, tmp_path: Path, consumer: str) -> None:
    with Store(tmp_path / "state") as store:
        store.ingest(journal, "synthetic")
        report = export(store, tmp_path / "feed", consumer=consumer)
        paths = list((tmp_path / "feed").rglob("*.log"))
        assert len(paths) == 1
        assert paths[0].name == journal.name
        assert paths[0].parent.parent == tmp_path / "feed"
        assert paths[0].read_bytes() == journal.read_bytes()
        assert report["consumer"] == consumer


def test_consumer_basename_collision_refused(journal: Path, tmp_path: Path) -> None:
    source = tmp_path / journal.name
    source.write_bytes(journal.read_bytes().replace(b'"Cost":0', b'"Cost":25'))
    with Store(tmp_path / "state") as store:
        store.ingest(journal, "synthetic-a")
        store.ingest(source, "synthetic-b")
        with pytest.raises(FeedConflict, match="basename collision"):
            export(store, tmp_path / "feed", allow_conflicts=True, consumer="edexo")
        assert not (tmp_path / "feed").exists()
