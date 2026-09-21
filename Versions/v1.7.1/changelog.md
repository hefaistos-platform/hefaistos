# v1.7.1

_Generated on 2026-09-21_

## Changes
- Address code review: handle dual Entra+OIDC case in reset_local_login
- Add OIDC_AND_LOCAL_BREAKGLASS auth mode for generic OIDC breakglass support
- Address code review: normalize existing usernames to lowercase, split long line
- Add reset_local_login management command for OIDC lockout recovery

## Fixes
- None

## Removals
- None

## Database Migrations
- backend/identity/migrations/0023_authprovidersettings_oidc_breakglass_mode.py
