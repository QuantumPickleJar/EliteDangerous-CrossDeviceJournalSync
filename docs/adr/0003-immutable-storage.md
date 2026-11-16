# 0003: Immutable storage

Status: accepted for the first vertical slice.

## Context

Original journal evidence must survive recovery, synchronization failures, and repeated scans.
Mutable consolidated files cannot serve as the only archive. A portable local state store must
support transaction recovery and avoid concurrent worker races.

## Decision

Store full raw byte strings under SHA-256 paths. Write via a same-directory temporary file,
flush/fsync, then atomic replacement while holding the archive writer lock. If a path already
exists, verify it and refuse corruption rather than overwrite it. Store canonical manifests,
derived lineage, and transfer jobs in local SQLite schema 1 with WAL/FULL synchronization.
Objects are written before a manifest transaction. Unknown SQLite schema versions are rejected.

Use a filesystem lock for the lifetime of Store, including queue processing. Retain unindexed
objects after rejected or interrupted ingestion. No garbage collection or remote deletion is
implemented. Backups include the whole stopped state directory, not a live main SQLite file alone.

## Consequences

Local deduplication is exact and content-addressed. Crash interruption can leave safe orphan
objects; `verify` checks hashes and manifest consistency without repairing evidence. Full
snapshots cost extra disk space and comparisons cost time. Filesystem/power-loss guarantees
and ACLs are outside the application transaction; backup/restore validation remains necessary.
