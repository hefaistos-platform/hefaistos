# Backup and Restore

## Purpose
Describe data protection and recovery workflows for HEFAISTOS operations.

## Audience
Operators responsible for business continuity and rollback readiness.

## Prerequisites
Storage path for backup archives and access to running containers.

## Steps / Workflow
1. Run backup workflow to create archive in default or external target path.
2. Verify archive integrity and retention policy.
3. Run restore workflow from selected backup artifact during recovery.

## Validation / Expected result
A valid archive is produced and restoration can reconstruct required platform data.

## Troubleshooting
If restore fails, verify archive permissions, service state, and database compatibility.

## Related pages
- [System Update](system-update.md)
- [Firewall and Service Management](firewall-and-service-management.md)
- [Installation](../getting-started/installation.md)
