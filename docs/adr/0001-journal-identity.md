# 0001: Journal identity and snapshot semantics

Status: accepted for the first vertical slice.

## Context

Game journals grow, copies move between devices, and incomplete JSON tails are normal during
play. A filename, mtime, or device identity alone cannot establish journal content equality.
A Fileheader can identify a grouping while different histories still share that grouping.

## Decision

Hash the canonical first complete Fileheader for session grouping, including its timestamp,
part, build, and other original header fields. Hash full raw bytes separately for immutable
capture identity. Keep the complete-prefix hash/count separately, with an optional partial tail
retained only in the raw object. Derive commanders from the unmodified records. Manifest identity
includes source basename, original mtime/size, device, and derived snapshot metadata.

A valid snapshot requires Fileheader first, UTF-8 timestamped JSON event objects, and complete
LF-terminated records. A BOM and CRLF are preserved. Unknown events/fields remain untouched.
Reads use the size observed at open; shrink is rejected. Appends are observed on a later scan.
Partial or malformed input can leave a locally retained unindexed object, never a published event.

## Consequences

Compatible repeated captures are safe. Header-part differences remain distinct; no speculative
merging of multipart files occurs. Header equality alone is not sufficient to deduplicate history:
exact complete-byte equality/prefix tests are required. Restored/changed mtimes can create new
provenance records for identical raw objects. In-place concurrent rewrites and sessions beyond
128 MiB need separate handling; final scans after game exit are part of migration acceptance.
