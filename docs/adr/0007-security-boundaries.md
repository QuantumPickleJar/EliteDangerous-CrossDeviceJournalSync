# 0007: Security boundaries

Status: accepted for the first vertical slice.

## Context

Journals reveal commander activity. Nextcloud credentials and private device/account details must
not leak through source control, logs, errors, APIs, or diagnostic attachments. Public CI must run
without access to any real archive or credential.

## Decision

Use a hidden local prompt and allowlisted OS credential-store backends, with no plaintext fallback
or password CLI option. Require HTTPS WebDAV, disable redirects, bound responses, parse XML with
external-entity protections, validate remote path components, and report fixed transport codes.
Keep configuration nonsecret but private. Store no absolute source path in remote manifests.

Expose optional GET-only API on IPv4 loopback with no CORS, no request logging, and Host/Origin
checks. Responses omit private identifiers, raw events, addresses, and credentials. Provide no
network-bind option, mutation interface, or bulk diagnostic dump. Synthetic-only examples explicitly
disable default discovery. Tests and CI use generated/mock data and reserved example hostnames.

## Consequences

Other local processes remain inside the trust boundary; API authentication is not implemented.
Archive/manifests/exports still contain private original data. SHA-256 gives integrity, not device
authentication. Nextcloud writers are trusted, and end-to-end encryption/signatures are future
work. OS filesystem permissions, disk encryption, vault session availability, and backups require
local validation. Optional Tailscale/private HTTP would require its own security decision before
implementation; none is needed for normal use.
