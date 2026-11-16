import json
import tempfile
import unittest
from pathlib import Path

from journal_sync import SHARED_HISTORY_FILE, synchronize


class JournalSyncTests(unittest.TestCase):
    def test_online_sync_copies_file_and_writes_shared_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = root / "local"
            nextcloud = root / "nextcloud"
            local.mkdir()
            nextcloud.mkdir()

            journal = local / "Journal.01.log"
            journal.write_text("event-a", encoding="utf-8")

            result = synchronize(local, nextcloud, root / "state.sqlite3")

            self.assertFalse(result.offline)
            self.assertEqual(result.copied, 1)
            self.assertEqual((nextcloud / journal.name).read_text(encoding="utf-8"), "event-a")

            history_lines = (nextcloud / SHARED_HISTORY_FILE).read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(history_lines), 1)
            payload = json.loads(history_lines[0])
            self.assertEqual(payload["event"], "copied")
            self.assertEqual(payload["relative_path"], journal.name)

    def test_deduplicates_against_existing_nextcloud_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = root / "local"
            nextcloud = root / "nextcloud"
            local.mkdir()
            nextcloud.mkdir()

            journal = local / "Journal.02.log"
            journal.write_text("same-content", encoding="utf-8")
            (nextcloud / journal.name).write_text("same-content", encoding="utf-8")

            result = synchronize(local, nextcloud, root / "state.sqlite3")

            self.assertFalse(result.offline)
            self.assertEqual(result.copied, 0)
            self.assertEqual(result.deduped, 1)

    def test_offline_queue_is_replayed_when_nextcloud_returns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = root / "local"
            local.mkdir()

            journal = local / "Journal.03.log"
            journal.write_text("offline-first", encoding="utf-8")

            fake_nextcloud = root / "nextcloud"
            fake_nextcloud.write_text("not a directory", encoding="utf-8")

            state_db = root / "state.sqlite3"
            offline_result = synchronize(local, fake_nextcloud, state_db)
            self.assertTrue(offline_result.offline)
            self.assertEqual(offline_result.queued, 1)

            fake_nextcloud.unlink()
            fake_nextcloud.mkdir()

            online_result = synchronize(local, fake_nextcloud, state_db)
            self.assertFalse(online_result.offline)
            self.assertEqual(online_result.replayed, 1)
            self.assertEqual(online_result.copied, 1)
            self.assertEqual((fake_nextcloud / journal.name).read_text(encoding="utf-8"), "offline-first")


if __name__ == "__main__":
    unittest.main()
