# 0002: Conflict resolution

Status: accepted for the first vertical slice.

## Context

Several devices may hold equal, growing, truncated, recovered, or divergent copies of a session.
A last-writer-wins choice or event-level deduplication can discard evidence, legitimate repeated
events, biological analysis, sales, or deaths.

## Decision

Retain every distinct raw object and manifest. Derive strict-prefix lineage only from validated
complete bytes, independent of ingestion order. Equal complete prefixes share one feed selection;
strict prefixes yield to maximal snapshots in the same Fileheader group. Never deduplicate an
individual event or reorder events by timestamp. Divergent maximal snapshots are conflicts.

Normal export fails on conflicts. Explicit `--allow-conflicts` produces separately isolated
generic branches for review. Flat consumer layouts also refuse original-basename collisions.
There is no silent branch selection, event synthesis, or automatic accounting repair.

## Consequences

Compatible copies consolidate without losing provenance. Divergent evidence survives, but it
requires human review. Explicit branch export can repeat shared-prefix events and must not be
blindly imported together. Byte-equivalent JSON with different formatting/line endings is kept
conservatively rather than normalized. Large histories may need indexed prefix comparisons later.
