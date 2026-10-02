# Firewall and Service Management

## Purpose
Capture operational controls for service lifecycle commands and network exposure.

## Audience
Infrastructure operators and administrators.

## Prerequisites
Administrative shell access to deployment host.

## Steps / Workflow
1. Apply firewall setup for exposed NGINX ports.
2. Use compose commands for start, stop, status, and logs.
3. Use profile-specific start modes for core, workers, and full runtime needs.

## Validation / Expected result
Only intended ports are exposed and service lifecycle commands operate predictably.

## Troubleshooting
If connectivity fails, validate firewall policy ordering and compose network/container status.

## Related pages
- [Service Matrix](service-matrix.md)
- [Quick Start](../getting-started/quick-start.md)
- [Security and CORS](../configuration/security-and-cors.md)
