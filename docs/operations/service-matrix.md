# Service Matrix

## Purpose
Document compose profile-based service activation and runtime topology.

## Audience
Operators planning startup modes and resource usage.

## Prerequisites
Docker Compose deployment configured.

## Steps / Workflow
1. Select startup mode (core-only, workers, observability, devtools, full runtime).
2. Start services with matching profile flags.
3. Use one-shot batch profiles for migrations and seed tasks.

## Validation / Expected result
Running services match expected profile counts and operational role mapping.

## Troubleshooting
If required services are missing, inspect profile flags and compose override behavior.

## Related pages
- [System Update](system-update.md)
- [Quick Start](../getting-started/quick-start.md)
- Source detail: `Docs/compose-service-matrix.md`
