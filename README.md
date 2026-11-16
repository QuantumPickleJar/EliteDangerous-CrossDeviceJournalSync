# EliteDangerous-CrossDeviceJournalSync

Nextcloud-powered sync service for Elite Dangerous journals across Windows and Steam Deck, including offline recovery, deduplication, and shared history.

## Usage

```bash
python journal_sync.py <local_journal_dir> <nextcloud_sync_dir> --state-db <state_db_path>
```

- `local_journal_dir`: directory containing `Journal*.log` files.
- `nextcloud_sync_dir`: local Nextcloud-synced directory shared across devices.
- `state_db_path`: local sqlite state/queue database path.

The synchronizer:
- copies changed journal files into the Nextcloud folder,
- queues updates while Nextcloud is unavailable,
- replays queued updates when Nextcloud becomes available,
- avoids duplicate uploads by hash,
- appends shared sync history to `.journal_sync_history.jsonl` in the Nextcloud folder.
