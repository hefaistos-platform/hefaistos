# Connectors Overview

## Purpose
Provide a high-level map of event-driven connectors and their operational roles.

## Audience
Platform operators and integrators.

## Prerequisites
RabbitMQ-enabled deployment and connector services configured.

## Steps / Workflow
1. Review connector responsibilities (rule sync, notifications, threat intel, git push, deploy).
2. Map connector events and consumers to your deployment needs.
3. Enable required connector profiles and validate event flow.

## Validation / Expected result
Expected domain events trigger corresponding connector actions without backlog.

## Troubleshooting
If connector actions do not run, verify broker connectivity, token configuration, and profile activation.

## Related pages
- [MISP Intake Model](misp-intake-model.md)
- [Git Sync and Push](git-sync-and-push.md)
- [Service Matrix](../operations/service-matrix.md)
