# 0005: Multi-device synchronization

Status: accepted for the first vertical slice.

## Context

Tower and Deck can produce identical filenames and copies of the same journal. Shared mutable
remote filenames, timestamps, or databases create collision and overwrite risks.

## Decision

Generate and persist a random device UUID per installation. Use `v1/devices/<device>/objects/<hash>`
and `v1/devices/<device>/manifests/<hash>.json`. Keep source provenance on imported snapshots;
never substitute the receiving device's ID. Clients can replicate imported immutable manifests
under their original origin. Keep each SQLite state directory local and independent.

Remote manifests are the discoverable publication set. Validate manifest filename hashes, device
binding, schema, object hash, and derived fields before local ingestion. There is no shared mutable
head, clock-based winner, deletion propagation, or remote queue/SQLite. Endpoint identity hashes the
collection URL and username so reconfiguration cannot reuse acknowledgements from another account.

## Consequences

Filename collisions cannot overwrite another device's history. Equal bytes deduplicate locally;
separate device archives can duplicate them remotely. Installations must not share generated state
or copy a live database between devices. Read/write access to the collection confers trusted-device
power; signatures and explicit device registration remain future work. Concurrent new publications
may be picked up on the next one-shot sync.
