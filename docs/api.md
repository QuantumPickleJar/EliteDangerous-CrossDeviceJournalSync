# Integration contracts (v1)

Future Elite Companion Decky and VR consumers use the read-only HTTP API. No UI component,
credential access, journal mutation, upload, or consumer import operation is exposed here.

Start explicitly with `journal-cloud --state-dir <local-state> serve --port 8765`. The service
binds only to `127.0.0.1`. Use `http://127.0.0.1:8765` as the base URL; this local HTTP endpoint
is unrelated to HTTPS WebDAV transport. It reads committed SQLite state in read-only mode and
can coexist with a scan/sync writer. Initialize/capture state first. No authentication is
provided against other local processes. Do not forward this port to a network.

## HTTP routes

All successful responses use JSON and `Cache-Control: no-store`. Only GET is implemented.
Unsupported methods return 501. Unknown routes return JSON 404, unavailable/corrupt state
returns JSON 503, and foreign Host or any Origin header returns JSON 403. No CORS is enabled.
The API is intended for local non-browser integrations. Stop the foreground service with Ctrl+C.

`GET /v1/health`:

```json
{"api_version":"v1","version":"0.1.0a1","read_only":true}
```

`GET /v1/status` (counts include all retained endpoint histories):

```json
{"api_version":"v1","snapshots":2,"transfers":{"transport_verified":1,"ingested":1},"consumer_import":"unknown"}
```

`GET /v1/sessions` returns an unpaginated list of snapshot summaries ordered by manifest ID:

```json
{"api_version":"v1","snapshots":[{"session":"<64 lowercase hex>","snapshot":"<64 lowercase hex>","complete_hash":"<64 lowercase hex>","complete_size":123,"commander_count":1}]}
```

Angle-bracket values are descriptive placeholders, not valid content hashes. `session` is the
canonical Fileheader hash; `snapshot` is the canonical manifest hash. Multiple snapshots may
share a session or complete hash. Do not add snapshot event counts together as unique history.
The API omits commander identifiers, raw events, source names, paths, device IDs, server URLs,
credentials, and request logging. The archive itself contains private data.

Integrations must tolerate additive fields and unknown future state labels. Missing fields
must not be interpreted as an acknowledgement. Breaking changes require `/v2`. No pagination,
event streaming, raw-journal endpoint, mutation API, or import confirmation exists yet.

## CLI JSON

`status` includes `api_version`, local snapshot count, transfer counts, safe failure records
(`id`, `direction`, `state`, `attempts`, fixed `error` code), `cloud_configured`,
`archive_ingestion: local_validated_snapshots_only`, `remote_archive_ingestion: unknown`, and
`consumer_import: unknown`. Snapshot counts are capture/provenance records, not unique sessions.

`scan` reports discovered, accepted, and rejected counts. Repeated accepted files can be
idempotent captures; accepted is not the count of newly inserted manifests. Malformed complete
records retain raw objects but have no manifest and therefore no sync/feed publication.

`sync` adds `discovery_error` and `current_endpoint_transfers`. Without cloud configuration it
reports `cloud: not_configured` and exits 0. Uploads end in `transport_verified`; validated local
downloads end in `ingested`. These are independent of remote archive and consumer import status.
Retryable errors use `retry`, permanent/exhausted errors use `failed`; see architecture for timing.
`--retry-failed` resets only terminal jobs at the current endpoint, never successful jobs.

Exit codes: 0 for successful work (including optional unconfigured cloud), 1 for validation,
I/O, integrity, configuration/credential failure, rejected scan files, archive lock contention,
or sync discovery/retry/failed state; argparse usage errors return 2. Errors omit exception
traces and private values. Journal validation errors include a fixed safe reason. The version
command and argparse help/usage are text; operational results are JSON.

## Persistent contracts

Manifest schema 1 contains `schema`, `device`, `source_name`, `source_mtime_ns`, `source_size`,
`raw_hash`, `complete_hash`, `complete_size`, `session`, `commanders`, and `timestamp`. IDs use
SHA-256 over canonical sorted/compact ASCII-escaped JSON. This schema is strict: unrecognized
fields require a future version. `commanders` are sorted unique identifiers from Commander or
LoadGame events (FID preferred, name fallback); they are private. Lineage is derived from bytes
and is not trusted remote input. See [architecture](architecture.md) for paths and validation.

Feed schema 1 (`feed.json`) contains `schema`, `consumer`, `files`, `conflicts`, and
`consumer_import`. Each file gives its relative POSIX `path`, `session`, `complete_hash`,
`events_bytes`, and `commander_count`. Files contain complete original bytes. The index is
written last; a directory without it is incomplete and must not be imported. Consumer layouts
are an explicit compatibility surface, but successful real EDDiscovery/EDEXO import must be
confirmed locally. No proprietary consumer files are distributed.
