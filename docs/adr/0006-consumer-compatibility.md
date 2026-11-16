# 0006: Consumer compatibility

Status: accepted for the first vertical slice; real consumer validation remains pending.

## Context

EDDiscovery and EDEXO are independent consumers. Recovered analysis and accounting history is
sensitive to ordering, missing records, duplicate imports, sales, deaths, and commander context.
Their proprietary files and the maintainer's private archive are not available for CI.

## Decision

Export complete original bytes in original file order. Consolidate only compatible snapshots.
Preserve original journal basenames. Keep commander groupings explicit; multi-commander files
remain intact and are flagged by count. Write a deterministic schema-1 feed index last into a
fresh generation directory. A missing index means an incomplete export.

The generic adapter isolates commander/session/content branches. EDDiscovery/EDEXO adapters expose
flat per-commander folders and refuse basename collisions. Each consumer is configured/imported
independently using a separate local test profile. No consumer automation, acknowledgement claim,
proprietary redistribution, or historical credit target is part of the exporter.

## Consequences

Synthetic tests verify byte preservation, event ordering, repeated events, prefix collapse,
commander separation, and conflict refusal. Real consumer versions and recovery evidence need
separate local Tower procedures. Re-importing multiple generations can duplicate records; safe
watcher/cutover policy is future alpha work. The unresolved historical 17-event census difference
is carried as a separate issue, not 'fixed' by modifying journal history.
