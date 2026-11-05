# v1.10.0

_Generated on 2026-11-05_

## Changes
- chore: untrack stray .DS_Store files added by the previous commit
- Maieutic Engine
- chore: restore .DS_Store to base (accidentally committed with -a)
- feat(maieutic): complete ADE question bank (all 16 subcategories)
- feat(maieutic): ADE question bank format, validator, selection and first four questions
- feat(maieutic): add author-only MaieuticDraft with server-enforced finish lock
- docs(maieutic): confirm metadata-only admin view
- style(platform-data): restore original mixed line endings in schema.py
- docs(maieutic): define finished-session locking and Instance Sharing scope
- feat(framework-updates): add ADE framework section with staged import, diff, promote and rollback
- feat(platform-data): import ADE framework as staged, promotable snapshots
- docs(maieutic): add Maieutic 3.0 spec and plan, note upcoming change in current guide

## Fixes
- None

## Removals
- docs(maieutic): lock TLP after finish, delete by author/admin/superuser, exclude transcript from sharing

## Database Migrations
- backend/ai_assistant/migrations/0020_maieutic_draft.py
- backend/platform_data/migrations/0014_ade_framework.py
