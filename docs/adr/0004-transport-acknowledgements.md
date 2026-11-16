# 0004: Transport and acknowledgement states

Status: accepted for the first vertical slice.

## Context

A successful HTTP response does not prove correct stored bytes, another archive's ingestion,
or EDDiscovery/EDEXO import. Offline devices and process termination require durable work state.

## Decision

Use Nextcloud HTTPS WebDAV with certificate verification, conditional immutable PUT, and GET/hash
verification. Publish an immutable manifest only after its referenced object verifies. Discover
manifest publications with Depth-1 PROPFIND. A download job validates the manifest and referenced
object before committing local ingestion. A whole job reruns after interruption.

Persist endpoint-scoped jobs before transfer. States are pending, in_progress, retry, failed,
transport_verified (upload), and ingested (download). Retry network/server failures with bounded
exponential delay and at most eight failed attempts. Explicit retry resets terminal current-endpoint
jobs. Under the exclusive archive lock, reopening resets interrupted in_progress work to retry.
Discovery failures are reported separately and retried on a later invocation.

## Consequences

Transfer, ingestion, and consumer acknowledgements remain separate. Remote ingestion and consumer
import are always unknown unless a future explicit protocol supplies evidence. A verified PUT is
not such evidence. No server-side receiver or private transport is required. Discovery is not a
durable job, byte-range resume is absent, and large listings have a bounded size rather than pagination.
