# HEFAISTOS Authentication Setup (SHARP)

This document defines the SHARP authentication direction selected for HEFAISTOS:

- Primary: `Microsoft Entra ID (OIDC)`
- Secondary: `Generic OIDC` (Okta/Auth0/Keycloak/authentik/etc.)
- Safety fallback: `1 local superuser` break-glass account

This is an operator and implementation guide for the upcoming `Configuration -> Authentication` tab.

---

## 1. Target Authentication Model

HEFAISTOS will support these sign-in methods:

1. Entra OIDC
2. Generic OIDC
3. Local username/password (break-glass admin only, optional policy)

The application will continue issuing its own internal JWT session token after external login succeeds.  
External IdP authentication establishes identity; HEFAISTOS JWT carries app session context.

---

## 2. Recommended Production Mode

Recommended mode for production:

- `Entra OIDC` enabled and set as default login method
- `Generic OIDC` optionally enabled for non-Entra tenants/environments
- Local login disabled for normal users
- Keep exactly one local `is_superuser` break-glass account for emergency access

This gives strong SSO posture while preserving disaster recovery access if IdP is unavailable or misconfigured.

---

## 3. Supported Operating Modes

### Mode A: Entra Only

- Enabled providers: Entra OIDC
- Local login: disabled (or break-glass only)
- Best for: single-tenant Microsoft identity estate

### Mode B: Generic OIDC Only

- Enabled providers: Generic OIDC
- Local login: disabled (or break-glass only)
- Best for: non-Microsoft IdP deployments

### Mode C: Entra + Generic OIDC

- Enabled providers: both
- Default provider: Entra (recommended when present)
- Local login: break-glass only
- Best for: mixed tenants or MSSP-style multi-org environments

### Mode D: Entra + 1 Local Superuser Admin (Recommended baseline)

- Enabled providers: Entra OIDC (and optionally Generic OIDC)
- Local login: blocked for standard users, allowed only for designated break-glass superuser account
- Best for: secure-by-default with operational fallback

---

## 4. How Authentication Will Work

### 4.1 Login Flow (OIDC)

1. User clicks `Sign in with Entra` or `Sign in with OIDC`.
2. Browser is redirected to provider authorization endpoint.
3. Provider authenticates user and returns authorization code.
4. Backend exchanges code for tokens at token endpoint.
5. Backend validates:
   - issuer
   - audience/client id
   - signature/JWKS
   - nonce/state
   - token expiration
6. Backend resolves user identity (subject/email/upn) and maps roles/groups.
7. Backend creates/updates local HEFAISTOS user record (if auto-provision enabled).
8. Backend issues HEFAISTOS JWT for app/API session.
9. Frontend uses HEFAISTOS JWT exactly as today.

### 4.2 Local Break-Glass Flow

1. User selects `Local Admin Login` (shown only when break-glass mode is enabled).
2. Backend validates local credentials.
3. Backend checks account is in approved break-glass allowlist.
4. Backend issues HEFAISTOS JWT.

Hardening requirements:

- random long password (stored in secret manager)
- MFA required for break-glass user
- login alerts enabled
- periodic credential rotation
- no daily operational use

---

## 5. User Provisioning and Role Mapping

Recommended baseline:

- `autoProvisionUsers = true`
- `syncClaimsOnEachLogin = true`
- map IdP group/app-role claims to HEFAISTOS roles:
  - `HEF-Admins` -> `ADMIN`
  - `HEF-Analysts` -> `ANALYST`
  - `HEF-Reviewers` -> `REVIEWER`
  - default fallback -> `VIEWER`

If claim mapping fails, deny elevated role assignment and default to least privilege (`VIEWER`) or deny login based on policy.

---

## 6. New Configuration UI: `Configuration -> Authentication`

Planned top-level controls:

- `Authentication Mode` (single select)
  - `ENTRA_ONLY`
  - `OIDC_ONLY`
  - `ENTRA_AND_OIDC`
  - `ENTRA_AND_LOCAL_BREAKGLASS`
- `Default Login Provider`
  - `ENTRA`
  - `OIDC`
  - `LOCAL` (only if enabled by policy)
- toggles:
  - `Allow Local Break-Glass Login`
  - `Auto-Provision Users`
  - `Sync Claims On Login`
  - `Enforce MFA For Local Break-Glass`

Provider panels:

- `Microsoft Entra OIDC`
  - tenant id
  - client id
  - client secret
  - authority/issuer
  - redirect URI
  - scopes
  - claim mapping (email, username, groups/roles)
- `Generic OIDC`
  - issuer URL
  - discovery URL (optional if derivable)
  - client id
  - client secret
  - redirect URI
  - scopes
  - claim mapping

Break-glass panel:

- allowed local usernames (allowlist)
- mandatory MFA toggle
- alert email/webhook target for local-admin login events

---

## 7. Microsoft Entra OAuth App Permissions

For HEFAISTOS Entra OIDC login, configure the Entra app registration with these minimum permissions/scopes:

- Required OIDC scopes:
  - `openid` (required for ID token / sign-in identity)
  - `profile` (basic profile claims)
  - `email` (email claim when available)
- Optional but recommended:
  - `offline_access` (if you want refresh-token based long-lived sessions)

Important notes:

- For basic OIDC login, HEFAISTOS does **not** need Microsoft Graph application permissions by default.
- If you later implement Graph lookups for group overage resolution or advanced directory sync, add Graph permissions only then (for example `User.Read` and/or group read permissions depending on the chosen flow).
- Prefer app roles or explicit claims mapping for authorization in HEFAISTOS instead of broad directory-read permissions when possible.

---

## 8. Environment and Secret Handling

Do not store client secrets in plaintext config.

Use existing HEFAISTOS secret patterns (`.secrets` + container mounted files) for:

- `ENTRA_CLIENT_SECRET`
- `OIDC_CLIENT_SECRET`

Example names (implementation target):

- `.secrets/entra_client_secret`
- `.secrets/oidc_client_secret`

---

## 9. Rollout Plan (Safe Path)

1. Add OIDC auth backend support in backend.
2. Add Authentication settings model + GraphQL queries/mutations.
3. Add new `Authentication` tab under `Configuration`.
4. Seed one local break-glass superuser and verify MFA.
5. Enable Entra in staging, validate mapping and login.
6. Disable local login for non-break-glass users.
7. Promote to production.

---

## 10. Operational Decision (Current)

Selected by product decision:

- Build and roll out `Entra OIDC + Generic OIDC`.
- Operate as `Entra + 1 local superuser break-glass` by default.

This means:

- day-to-day user authentication should happen via Entra (or configured OIDC provider),
- HEFAISTOS keeps one protected local superuser account only for emergency recovery.

---

## 11. Multi-Organization OIDC Behavior (How Org Choice Works)

Authentication settings are organization-scoped.

- Each organization has its own:
  - Entra tenant/client configuration
  - Generic OIDC issuer/client configuration
  - claim mapping + role mapping rules
  - break-glass policy

### Login-time organization choice

For OIDC login:

1. User selects organization on the login page.
2. User clicks `Sign In with Entra` or `Sign In with OIDC`.
3. HEFAISTOS starts OIDC using that organization's auth settings.
4. Organization context is bound into OIDC `state`.
5. Callback validates `state` and completes login against the same organization config.
6. User provisioning/sync occurs inside that target organization.

### Why this is required

In multi-tenant environments, different organizations may use different Entra tenants or different OIDC providers.  
Explicit org selection avoids ambiguous routing and prevents accidental cross-tenant authentication context.
